"""Checkpointed ScientistTwo workflow, preserving criticism and scientific feedback loops."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import os
import re
import shutil
import stat
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from . import behavior
from .agents import AgentRunner
from .coding import CodingPending
from .config import ResearchConfig
from .contracts import (
    AgentOutput,
    ExperimentResult,
    ExperimentSpec,
    Idea,
    RunState,
    Stage,
)
from .demo import BENCHMARK
from .execution import Executor
from .integrity import analysis_input
from .literature import Literature
from .privacy import redact
from .providers import Provider
from .research_stages import HANDLERS
from .research_stages.experimentation import (
    candidate_completed,
    finish_batch,
    next_candidate,
    strictly_better,
)
from .runtime_support import parent_descriptor as _parent
from .runtime_support import read_text as _read
from .runtime_support import write_file as _write
from .source_policy import source_is_excluded
from .store import BudgetExceeded, Store, now
from .workflow import WorkflowTransitionError, get_workflow

EXPERIMENT_STAGES = {
    stage
    for stage, node in get_workflow().nodes.items()
    if node.handler == "experimentation.execute"
}

TERMINAL = {"completed", "failed", "stopped"}


class Engine:
    def __init__(
        self,
        store: Store,
        config: ResearchConfig | None = None,
        *,
        provider: Provider | None = None,
        executor: Executor | None = None,
        literature: Literature | None = None,
        stage_handlers: Mapping[Stage, Callable[[RunState, ResearchConfig, AgentRunner], None]]
        | None = None,
        runner_factory: Callable[[Store, ResearchConfig], AgentRunner] | None = None,
    ):
        self.store, self.config = store, config or ResearchConfig()
        self.provider, self.executor, self.literature = provider, executor, literature
        self.stage_handlers = dict(stage_handlers or {})
        self.runner_factory = runner_factory
        get_workflow().validate_handlers(set(HANDLERS))

    def _behavior_extensions(self, config: ResearchConfig) -> dict[str, Any]:
        return behavior.extension_manifest(
            {
                "provider": self.provider,
                "executor": self.executor,
                "literature": self.literature,
                "runner_factory": self.runner_factory,
                **{
                    f"stage:{stage.value}": handler
                    for stage, handler in self.stage_handlers.items()
                },
            },
            strict=config.mode == "live",
        )

    def create(self, title: str, objective: str, demo: bool = False) -> RunState:
        if (
            not title.strip()
            or not objective.strip()
            or len(title) > 200
            or len(objective) > 100000
        ):
            raise ValueError("title and objective must be nonempty and within length limits")
        config = self.config.model_copy(deep=True)
        if config.specification_dir:
            config.specification_dir = str(
                Path(config.specification_dir).expanduser().resolve(strict=True)
            )
        state = RunState(
            id=uuid.uuid4().hex[:12],
            title=title,
            objective=objective,
            created_at=now(),
            updated_at=now(),
        )
        if demo or config.mode == "demo":
            config.mode = "demo"
            config.role_commands = {}
            config.search_enabled = False
            config.execution.backend = "local"
            config.execution.allow_local = True
            config.project.source_dir = ""
            config.project.sota = {"score": 0.5}
            config.project.metrics = {"score": "max"}
            config.project.primary_metric = "score"
            config.project.baseline_argv = []
            config.project.evaluator_argv = []
            config.project.protected_paths = []
            config.project.specification = "Offline synthetic regression fixture; scripted judgments are not scientific validation."
            config.project.seeds = [0, 1]
            config.references = []
        for role, argv in config.role_commands.items():
            executable = shutil.which(argv[0]) if argv else None
            if executable is None:
                raise ValueError(f"{role}: adapter executable is unavailable")
            config.role_commands[role] = [str(Path(executable).resolve(strict=True)), *argv[1:]]
        bundle = behavior.snapshot(config, extensions=self._behavior_extensions(config))
        state.behavior = behavior.identity(bundle)
        self.store.create(state, config)
        source = self.store.run_dir(state.id) / "source"
        source.mkdir(mode=0o700)
        if config.mode == "demo":
            (source / "benchmark.py").write_text(BENCHMARK)
        elif config.project.source_dir:
            original = Path(config.project.source_dir).expanduser().resolve(strict=True)
            if not original.is_dir():
                raise ValueError("source_dir must be a directory")
            self._copy_source(original, source, config.project.include)
        self.store.artifact(
            state.id, "configuration", "config.json", config.model_dump_json(indent=2)
        )
        behavior.archive(self.store, state, bundle)
        return state

    def pause(self, run_id: str) -> None:
        self.store.set_paused(run_id, True)
        self.store.event(run_id, "pause_requested", self.store.get_run(run_id).stage, {})

    def resume(self, run_id: str) -> RunState:
        self.store.set_paused(run_id, False)
        with self.store.lease(run_id):
            state = self.store.get_run(run_id)
            if state.status not in TERMINAL:
                state.status, state.error = "ready", ""
                self.store.save(state, "resumed")
            return state

    def cancel_experiment(self, run_id: str) -> RunState:
        with self.store.lease(run_id):
            state = self.store.get_run(run_id)
            config = self.store.get_config(run_id)
            if not state.pending_experiment or not state.pending_job_id:
                raise ValueError(
                    "no resumable scheduler job to cancel; request pause for synchronous execution"
                )
            (self.executor or Executor(config.execution)).cancel(state.pending_job_id)
            result = ExperimentResult(
                id=state.pending_experiment.id,
                status="cancelled",
                job_id=state.pending_job_id,
                stderr="Cancelled explicitly by operator",
                provenance={
                    "kind": state.stage.value,
                    "seed": state.pending_experiment.seed,
                    "workspace": state.pending_experiment.workspace,
                },
            )
            state.experiments.append(result)
            state.memory.append(
                {
                    "kind": "experiment",
                    "status": "cancelled",
                    "id": result.id,
                    "stage": state.stage.value,
                    "idea": state.current_idea,
                    "reason": "operator cancellation",
                }
            )
            state.pending_experiment, state.pending_job_id = None, None
            state.batch_results, state.active_output = [], None
            state.status = "paused"
            self.store.set_paused(run_id, True)
            self.store.save(
                state, "experiment_cancelled", {"id": result.id, "job_id": result.job_id}
            )
            return state

    def intervene(self, run_id: str, note: str, stage: str | None = None) -> RunState:
        if not note.strip() or len(note) > 100000:
            raise ValueError("intervention must contain a note of at most 100000 characters")
        with self.store.lease(run_id):
            state = self.store.get_run(run_id)
            target = Stage(stage) if stage else None
            get_workflow().validate_intervention(state, target)
            state.feedback = note
            state.memory.append(
                {
                    "kind": "human_intervention",
                    "note": note,
                    "stage": state.stage.value,
                    "timestamp": now(),
                }
            )
            if target is not None:
                state.stage = target
                state.active_output = None
                state.batch_results = []
            state.status, state.error = "ready", ""
            self.store.save(
                state,
                "human_intervention",
                {
                    "note": note,
                    "stage": stage,
                    "workflow_bypass": True,
                    "workflow_digest": get_workflow().digest,
                },
            )
            return state

    def run(self, run_id: str, max_steps: int | None = None) -> RunState:
        steps = 0
        while max_steps is None or steps < max_steps:
            state = self.step(run_id)
            steps += 1
            if state.status in TERMINAL | {"blocked", "budget_exhausted", "paused"}:
                return state
            if state.status == "waiting":
                time.sleep(min(self.store.get_config(run_id).execution.slurm_poll_seconds, 10))
        return self.store.get_run(run_id)

    def step(self, run_id: str) -> RunState:
        with self.store.lease(run_id):
            state = self.store.get_run(run_id)
            config = self.store.get_config(run_id)
            if state.status in TERMINAL:
                return state
            if self.store.is_paused(run_id):
                state.status = "paused"
                self.store.save(state)
                return state
            # Errors require explicit resume, so a watch loop cannot silently retry paid work.
            if state.status in {"blocked", "budget_exhausted"}:
                return state
            previous = state.stage
            try:
                behavior.verify(
                    self.store, state, config, extensions=self._behavior_extensions(config)
                )
                runner = (
                    self.runner_factory(self.store, config)
                    if self.runner_factory
                    else AgentRunner(self.store, config, self.provider, literature=self.literature)
                )
                elapsed = (
                    datetime.fromisoformat(now()) - datetime.fromisoformat(state.created_at)
                ).total_seconds()
                if elapsed > config.budget.wall_seconds:
                    raise BudgetExceeded("wall-clock budget reached")
                state.status = "running"
                handler = self.stage_handlers.get(state.stage)
                if handler:
                    handler(state, config, runner)
                    get_workflow().validate_transition(previous, state)
                else:
                    self._advance(state, config, runner)
                if state.status == "running":
                    state.status = "ready"
                self.store.save(
                    state,
                    "transition",
                    {
                        "from": previous.value,
                        "to": state.stage.value,
                        "status": state.status,
                        "outcome": state.outcome,
                        "idea": state.current_idea,
                        "workflow_digest": get_workflow().digest,
                    },
                )
            except WorkflowTransitionError as exc:
                # Keep attempted results and diagnostics, but never checkpoint an illegal edge.
                state.stage, state.status, state.error = previous, "blocked", str(exc)
                self.store.save(
                    state, "workflow_violation", {"reason": str(exc), "stage": previous.value}
                )
            except CodingPending as exc:
                state.status = "paused" if self.store.is_paused(run_id) else "waiting"
                self.store.save(state, "coding_pending", {"reason": str(exc)})
            except BudgetExceeded as exc:
                state.status, state.error = "budget_exhausted", str(exc)
                self.store.save(state, "budget_exhausted", {"reason": state.error})
            except Exception as exc:
                state.status = "blocked"
                state.error = str(
                    redact(f"{type(exc).__name__}: {exc}", config.privacy.redact_patterns)
                )[:2000]
                self.store.save(
                    state, "stage_error", {"error": state.error, "stage": previous.value}
                )
            return state

    def _advance(self, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
        workflow = get_workflow()
        previous = s.stage
        handler = workflow.nodes[previous].handler
        HANDLERS[handler](self, s, c, agents)
        workflow.validate_transition(previous, s)

    def _judge(
        self, s: RunState, agents: AgentRunner, context: dict[str, Any] | None = None
    ) -> AgentOutput:
        out = agents.run(s, s.stage, context)
        s.feedback = out.feedback or out.summary
        s.memory.append(
            {
                "kind": "critique",
                "stage": s.stage.value,
                "idea": s.current_idea,
                "decision": out.decision,
                "stage_decision": out.stage_decision,
                "feedback": s.feedback,
                "score": out.score,
                "version": s.version,
            }
        )
        return out

    def _execute_pending(
        self, s: RunState, executor: Executor, spec: ExperimentSpec
    ) -> ExperimentResult:
        """Reconcile execution intent before dispatch; never replay an unknown local run."""
        receipts = self.store.run_dir(s.id) / "receipts"
        receipts.mkdir(exist_ok=True, mode=0o700)
        receipt_name = f"{spec.id}.json"
        started_name = f"{spec.id}.started.json"
        if (receipts / receipt_name).exists():
            result = ExperimentResult.model_validate_json(_read(receipts, receipt_name, 32_000_000))
        elif s.pending_job_id:
            result = executor.poll(spec, s.pending_job_id)
        elif (
            executor.config.backend == "slurm"
            and (Path(spec.workspace) / ".autoresearch-execution.json").exists()
        ):
            # Executor validates the saved specification and recovers the scheduler ID.
            # An uncertain submission remains blocked until its saved job is reconciled.
            result = executor.run(spec)
        elif (receipts / started_name).exists():
            started = json.loads(_read(receipts, started_name, 32_000_000))
            if started["spec"] != spec.model_dump(mode="json"):
                raise ValueError("started execution specification changed before reconciliation")
            result = ExperimentResult(
                id=spec.id,
                status="failed",
                stderr=(
                    "Interrupted experiment has no durable receipt; execution outcome is unknown. "
                    "The workspace and logs are retained. Inspect them before a new attempt; "
                    "this experiment ID will not be replayed."
                ),
                provenance={
                    "uncertain_execution": True,
                    "failure_kind": "interrupted_unknown_outcome",
                    "argv": spec.argv,
                    "started_at": started["started_at"],
                },
            )
        else:
            _write(
                receipts,
                started_name,
                json.dumps(
                    {
                        "spec": spec.model_dump(mode="json"),
                        "started_at": now(),
                    }
                ),
            )
            self.store.event(s.id, "execution_started", s.stage, {"id": spec.id})
            result = executor.run(spec)
        if result.id != spec.id:
            raise ValueError("execution result identifier does not match pending experiment")
        if result.status == "pending":
            if not result.job_id:
                raise ValueError("pending execution did not provide a resumable scheduler job ID")
            s.pending_job_id, s.status = result.job_id, "waiting"
            self.store.save(s, "execution_waiting", {"id": spec.id, "job_id": result.job_id})
        else:
            _write(receipts, receipt_name, result.model_dump_json())
        return result

    def _experiment(self, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
        if len(s.experiments) >= c.budget.max_experiments:
            raise BudgetExceeded("experiment budget reached")
        if (
            c.mode == "live"
            and s.stage == Stage.BASELINE
            and (not c.project.source_dir or not c.project.sota)
        ):
            raise ValueError(
                "live experiments require source_dir and original full-benchmark sota metrics in project config"
            )
        if c.mode == "live" and self.executor is None and not c.project.evaluator_argv:
            raise ValueError(
                "live experiments require an operator-owned protected evaluator; model-generated metrics alone cannot validate research"
            )
        if c.mode == "live" and not all(key in c.project.sota for key in c.project.metrics):
            raise ValueError("original SOTA must specify every required metric")
        executor = self.executor or Executor(c.execution)
        if s.active_output is None:
            context: dict[str, Any] = {
                "source_files": self._source_context(self._source_for(s))
                if c.mode == "demo"
                else {},
                "source_dir": str(self._source_for(s)),
                "current_plan": s.plans[s.plan_index]
                if s.plans and s.stage in {Stage.ABLATION, Stage.REBUTTAL}
                else None,
            }
            s.active_output = agents.run(s, s.stage, context)
            if (
                s.stage in {Stage.ABLATION_REFINE, Stage.META_REFINE}
                and c.mode == "live"
                and (
                    len(s.active_output.ideas) != 1
                    or not s.active_output.ideas[0].hypothesis.strip()
                )
            ):
                s.active_output = None
                raise ValueError(
                    "method refinement requires exactly one revised hypothesis with its implementation"
                )
            self._validate_edits(s.active_output, c)
            if s.stage == Stage.BASELINE and c.project.baseline_argv:
                s.active_output.argv = c.project.baseline_argv
            if not s.active_output.argv:
                raise ValueError("coding agent must propose an executable argv")
        if s.pending_experiment is None:
            seed = c.project.seeds[len(s.batch_results)]
            exp_id = f"exp-{uuid.uuid4().hex[:12]}"
            workspace = self.store.run_dir(s.id) / "experiments" / exp_id
            self._snapshot(
                self._source_for(s),
                workspace,
            )
            self._restore_protected(s.id, workspace, c)
            for edit in s.active_output.files:
                _write(workspace, edit.path, edit.content)
            for relative in s.active_output.deleted_files:
                with _parent(workspace, relative) as (descriptor, name):
                    os.unlink(name, dir_fd=descriptor)
            input_snapshot = self.store.run_dir(s.id) / "inputs" / exp_id
            self._snapshot(workspace, input_snapshot)
            self.store.artifact(
                s.id,
                "code_modifications",
                f"edits-{exp_id}.json",
                json.dumps([edit.model_dump() for edit in s.active_output.files], indent=2),
            )
            s.pending_experiment = ExperimentSpec(
                id=exp_id,
                kind=s.stage,
                workspace=str(workspace),
                argv=s.active_output.argv,
                files=s.active_output.files,
                seed=seed,
                timeout_seconds=c.project.experiment_timeout,
                metadata={
                    "metric_units": c.project.metric_units,
                    "analysis_artifacts": c.project.analysis_artifacts,
                    "analysis_inputs": [
                        analysis_input(result)
                        for result in s.experiments
                        if result.status == "completed"
                    ],
                    "idea_id": s.current_idea,
                    "selected_idea": s.selected_idea,
                    "input_snapshot": str(input_snapshot),
                    "round": s.round,
                    "plan": s.plans[s.plan_index]
                    if s.plans and s.stage in {Stage.ABLATION, Stage.REBUTTAL}
                    else None,
                    "evaluator_argv": c.project.evaluator_argv,
                    "dataset_manifest": c.project.dataset_manifest,
                    "protected_files": self._protected_files(workspace, c),
                    "specification_sha256": hashlib.sha256(
                        c.project.specification.encode()
                    ).hexdigest(),
                },
            )
            self.store.save(
                s,
                "experiment_planned",
                {"id": exp_id, "kind": s.stage.value, "argv": s.active_output.argv, "seed": seed},
            )
        spec = s.pending_experiment
        result = self._execute_pending(s, executor, spec)
        if result.status == "pending":
            return
        result.provenance.update(
            {
                "workspace": spec.workspace,
                "input_snapshot": spec.metadata.get("input_snapshot"),
                "kind": spec.kind,
                "idea_id": s.current_idea,
                "seed": spec.seed,
                "selected_idea": spec.metadata.get("selected_idea"),
                "plan": spec.metadata.get("plan"),
                "specification_sha256": spec.metadata.get("specification_sha256"),
            }
        )
        if result.status == "completed" and not all(
            key in result.metrics for key in c.project.metrics
        ):
            result.status, result.stderr = "failed", "Missing required measured metrics"
        if result.status == "completed":
            audit = agents.run(
                s,
                "experiment_integrity",
                {
                    "experiment": result.model_dump(),
                    "proposed_files": [edit.model_dump() for edit in spec.files],
                    "source_dir": str(spec.workspace),
                    "source_files": self._source_context(Path(spec.workspace))
                    if c.mode == "demo"
                    else {},
                    "specification": c.project.specification,
                },
            )
            self.store.event(
                s.id,
                "experiment_integrity",
                s.stage,
                {"id": result.id, "decision": audit.decision, "feedback": audit.feedback},
            )
            if audit.decision != "accept":
                result.status, result.stderr = (
                    "failed",
                    "Integrity audit: " + (audit.feedback or audit.summary),
                )
        s.experiments.append(result)
        s.batch_results.append(result)
        s.memory.append(
            {
                "kind": "experiment",
                "stage": s.stage.value,
                "idea": s.current_idea,
                "id": result.id,
                "status": result.status,
                "metrics": result.metrics,
                "failure": result.stderr,
                "provenance": result.provenance,
            }
        )
        self.store.event(s.id, "experiment_completed", s.stage, result.model_dump())
        s.pending_experiment, s.pending_job_id = None, None
        if len(s.batch_results) < len(c.project.seeds):
            return
        successful = all(r.status == "completed" for r in s.batch_results)
        metrics = (
            {
                key: sum(r.metrics[key] for r in s.batch_results) / len(s.batch_results)
                for key in c.project.metrics
            }
            if successful
            else {}
        )
        # Seedwise values stay intact; the declared preference rule compares mean metrics.
        workspace = s.batch_results[0].provenance["workspace"]
        proposal = s.active_output
        s.memory.append(
            {
                "kind": "experiment_batch",
                "stage": s.stage.value,
                "idea": s.current_idea,
                "workspace": str(workspace),
                "experiment_ids": [result.id for result in s.batch_results],
                "successful": successful,
            }
        )
        s.active_output = None
        s.batch_results = []
        self._experiment_finished(s, c, successful, metrics, str(workspace), proposal)

    def _experiment_finished(
        self,
        s: RunState,
        c: ResearchConfig,
        successful: bool,
        metrics: dict[str, float],
        workspace: str,
        proposal: AgentOutput | None = None,
    ) -> None:
        finish_batch(self, s, c, successful, metrics, workspace, proposal)

    @staticmethod
    def _workspace_experiment_ids(s: RunState, workspace: str) -> list[str]:
        batch = next(
            (
                item
                for item in reversed(s.memory)
                if item.get("kind") == "experiment_batch" and item.get("workspace") == workspace
            ),
            None,
        )
        if batch is not None:
            return list(batch["experiment_ids"])
        return [
            result.id for result in s.experiments if result.provenance.get("workspace") == workspace
        ]

    def _selected_experiments(
        self, s: RunState, c: ResearchConfig, best: Idea
    ) -> list[ExperimentResult]:
        batch = next(
            (
                item
                for item in reversed(s.memory)
                if item.get("kind") == "experiment_batch"
                and item.get("workspace") == best.workspace
            ),
            None,
        )
        experiments = {result.id: result for result in s.experiments}
        if not batch or not isinstance(batch.get("experiment_ids"), list):
            raise ValueError("selected candidate lacks its complete seed-batch provenance")
        originals = [
            experiments[identifier]
            for identifier in batch["experiment_ids"]
            if identifier in experiments
        ]
        expected_kinds = {"full", "full_engineer", "ablation_refine", "meta_refine"}
        if (
            len(originals) != len(c.project.seeds)
            or [result.provenance.get("seed") for result in originals] != c.project.seeds
            or any(
                result.status != "completed" or result.provenance.get("kind") not in expected_kinds
                for result in originals
            )
        ):
            raise ValueError(
                "selected candidate lacks completed full-benchmark evidence for every configured seed"
            )
        return originals

    def _reproduce_selected(self, s: RunState, c: ResearchConfig, best: Idea) -> bool:
        originals = self._selected_experiments(s, c, best)
        if c.integrity.rerun_supplementary:
            originals.extend(
                result
                for result in s.experiments
                if result.status == "completed"
                and result.provenance.get("kind") in {"ablation", "rebuttal"}
                and result.provenance.get("selected_idea") == best.id
            )
        completed_ids = {
            result.provenance.get("reproduced_from")
            for result in s.experiments
            if result.status == "completed"
            and result.provenance.get("kind") == "reproduction"
            and result.provenance.get("selected_idea") == best.id
        }
        remaining = [result for result in originals if result.id not in completed_ids]
        if not remaining:
            s.counters["reproduced_final"] = len(originals)
            return True
        if len(s.experiments) >= c.budget.max_experiments:
            raise BudgetExceeded("experiment budget reached during independent score reproduction")
        original = remaining[0]
        if s.pending_experiment is not None:
            spec = s.pending_experiment
            if (
                spec.kind != "reproduction"
                or spec.metadata.get("reproduced_from") != original.id
                or spec.metadata.get("selected_idea") != best.id
            ):
                raise ValueError("pending reproduction does not match the selected experiment")
        else:
            argv = original.provenance.get("argv")
            source = original.provenance.get("input_snapshot")
            if not isinstance(argv, list) or not argv or not isinstance(source, str):
                raise ValueError(
                    "selected experiment lacks its pristine pre-execution inputs or command"
                )
            exp_id = f"verify-{uuid.uuid4().hex[:12]}"
            workspace = self.store.run_dir(s.id) / "experiments" / exp_id
            self._snapshot(
                Path(source),
                workspace,
            )
            self._restore_protected(s.id, workspace, c)
            spec = ExperimentSpec(
                id=exp_id,
                kind="reproduction",
                workspace=str(workspace),
                argv=argv,
                seed=int(original.provenance["seed"]),
                timeout_seconds=c.project.experiment_timeout,
                metadata={
                    "metric_units": original.provenance.get("metric_units", c.project.metric_units),
                    "analysis_artifacts": original.provenance.get("analysis_artifacts", []),
                    "registered_statistical_plan": original.provenance.get(
                        "registered_statistical_plan"
                    ),
                    "analysis_inputs": original.provenance.get("analysis_inputs", []),
                    "evaluator_argv": c.project.evaluator_argv,
                    "dataset_manifest": c.project.dataset_manifest,
                    "protected_files": self._protected_files(workspace, c),
                    "reproduced_from": original.id,
                    "selected_idea": best.id,
                },
            )
            s.pending_experiment = spec
            self.store.save(
                s,
                "reproduction_planned",
                {"id": spec.id, "original_id": original.id, "seed": spec.seed},
            )
        executor = self.executor or Executor(c.execution)
        result = self._execute_pending(s, executor, spec)
        if result.status == "pending":
            return False
        result.provenance.update(
            {
                "workspace": spec.workspace,
                "kind": "reproduction",
                "seed": spec.seed,
                "reproduced_from": original.id,
                "selected_idea": best.id,
            }
        )
        matches = result.status == "completed" and all(
            key in result.metrics
            and math.isclose(
                result.metrics[key], value, rel_tol=c.project.reproduction_tolerance, abs_tol=1e-10
            )
            for key, value in original.metrics.items()
        )
        expected_analyses = {
            path: record["analysis"]
            for path, record in original.provenance.get("statistical_analyses", {}).items()
            if isinstance(record, dict) and "analysis" in record and "error" not in record
        }
        reproduced_analyses = result.provenance.get("statistical_analyses", {})
        matches = matches and all(
            isinstance(reproduced_analyses.get(path), dict)
            and "error" not in reproduced_analyses[path]
            and reproduced_analyses[path].get("analysis") == analysis
            for path, analysis in expected_analyses.items()
        )
        if not matches and result.status == "completed":
            result.status = "failed"
            result.stderr = (
                "Measured result or statistical analysis disagrees with the archived evidence."
            )
        s.experiments.append(result)
        s.memory.append(
            {
                "kind": "score_verification",
                "id": result.id,
                "original_id": original.id,
                "seed": spec.seed,
                "status": result.status,
                "metrics": result.metrics,
                "failure": result.stderr,
                "selected_idea": best.id,
            }
        )
        self.store.event(s.id, "score_verification", s.stage, result.model_dump())
        s.pending_experiment, s.pending_job_id = None, None
        if not matches:
            raise ValueError("selected implementation failed independent rerun tolerance")
        s.counters["reproduced_final"] = len(originals) - len(remaining) + 1
        return len(remaining) == 1

    def _finish_candidate(self, s: RunState, c: ResearchConfig) -> None:
        candidate_completed(self, s, c)

    @staticmethod
    def _next_candidate(s: RunState) -> None:
        next_candidate(s)

    @staticmethod
    def _idea(s: RunState, idea_id: str | None = None) -> Idea:
        key = idea_id or s.current_idea
        for idea in s.ideas:
            if idea.id == key:
                return idea
        raise ValueError("current/selected candidate does not exist")

    def _source_for(self, s: RunState) -> Path:
        if s.stage == Stage.BASELINE:
            return self.store.run_dir(s.id) / "source"
        if s.stage == Stage.SUBSET:
            for item in reversed(s.memory):
                if item["kind"] == "baseline_workspace":
                    return Path(item["workspace"])
        idea = self._idea(
            s,
            s.selected_idea
            if s.stage in {Stage.ABLATION, Stage.ABLATION_REFINE, Stage.REBUTTAL, Stage.META_REFINE}
            else None,
        )
        return (
            self._pristine_input(s, idea.workspace)
            if idea.workspace
            else self.store.run_dir(s.id) / "source"
        )

    @staticmethod
    def _pristine_input(s: RunState, workspace: str) -> Path:
        original = next(
            (e for e in reversed(s.experiments) if e.provenance.get("workspace") == workspace), None
        )
        if original is None or not isinstance(original.provenance.get("input_snapshot"), str):
            raise ValueError(
                "candidate lacks pristine input provenance; do not inherit executed outputs"
            )
        return Path(original.provenance["input_snapshot"])

    @staticmethod
    def _add_ideas(s: RunState, ideas: list[Idea], evolved: bool) -> list[str]:
        ids = {i.id for i in s.ideas}
        added = []
        for idea in ideas:
            if (
                not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", idea.id)
                or idea.id in ids
                or not idea.hypothesis.strip()
            ):
                continue
            if evolved and any(parent not in ids for parent in idea.parents):
                raise ValueError("evolved hypothesis references an unknown parent")
            idea.round, idea.status = s.round, "evolved" if evolved else "seed"
            s.ideas.append(idea)
            added.append(idea.id)
            ids.add(idea.id)
        return added

    @staticmethod
    def _better(metrics: dict[str, float], reference: dict[str, float], c: ResearchConfig) -> bool:
        return strictly_better(metrics, reference, c)

    @staticmethod
    def _protected_files(workspace: Path, config: ResearchConfig) -> list[str]:
        return sorted(
            str(path.relative_to(workspace))
            for path in workspace.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and any(
                fnmatch.fnmatch(str(path.relative_to(workspace)), pattern)
                for pattern in config.project.protected_paths
            )
        )

    @staticmethod
    def _validate_edits(output: AgentOutput, c: ResearchConfig) -> None:
        for relative in output.deleted_files:
            if any(fnmatch.fnmatch(relative, pattern) for pattern in c.project.protected_paths):
                raise ValueError("agent tried to delete a protected evaluator or specification")
        for edit in output.files:
            if edit.path in c.project.protected_paths or any(
                fnmatch.fnmatch(edit.path, pattern) for pattern in c.project.protected_paths
            ):
                raise ValueError("agent tried to edit a protected evaluator or specification")
            if len(edit.content.encode()) > 10_000_000:
                raise ValueError("model file edit exceeds size limit")

    @staticmethod
    def _snapshot(source: Path, destination: Path) -> None:
        """Never follow workload-created symlinks back into the host filesystem."""
        if source.is_symlink() or not source.is_dir():
            raise ValueError("snapshot source must be a real directory")
        destination.mkdir(parents=True, mode=0o700)
        ignored = {"metrics.json", "__pycache__"}
        for item in source.rglob("*"):
            relative = item.relative_to(source)
            if any(
                part in ignored or part.startswith(".autoresearch-") or part.endswith(".log")
                for part in relative.parts
            ):
                continue
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or not (
                stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)
            ):
                raise ValueError("workload snapshot contains a symlink or special file")
            target = destination / relative
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            else:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor = os.open(item, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(descriptor, "rb") as stream, target.open("xb") as output:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise ValueError("snapshot contains a special file")
                    shutil.copyfileobj(stream, output)
                os.chmod(target, stat.S_IMODE(info.st_mode) & 0o700)

    def _restore_protected(self, run_id: str, workspace: Path, config: ResearchConfig) -> None:
        source = self.store.run_dir(run_id) / "source"
        for relative in self._protected_files(source, config):
            target = workspace / relative
            if target.is_symlink():
                raise ValueError("protected evaluator path became a symlink")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, target)

    @staticmethod
    def _source_context(path: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        total = 0
        for item in sorted(path.rglob("*")):
            if (
                item.is_file()
                and not item.is_symlink()
                and item.suffix in {".py", ".toml", ".md", ".json", ".sh"}
                and not item.name.startswith(".autoresearch")
            ):
                size = item.stat().st_size
                if size > 1_000_000 or total + size > 2_000_000:
                    raise ValueError(
                        "source exceeds prompt context limit; supply a narrower project include list"
                    )
                try:
                    result[str(item.relative_to(path))] = item.read_text()
                except UnicodeDecodeError:
                    continue
                total += size
        return result

    @staticmethod
    def _copy_source(original: Path, target: Path, include: list[str]) -> None:
        for path in original.rglob("*"):
            relative = path.relative_to(original)
            if path.is_symlink() or source_is_excluded(relative):
                continue
            if path.is_file() and any(
                fnmatch.fnmatch(str(relative), pattern) for pattern in include
            ):
                if path.stat().st_size > 5_000_000:
                    raise ValueError("source file exceeds snapshot size limit")
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)

    @staticmethod
    def _stop(s: RunState, outcome: str, failed: bool = False) -> None:
        s.status, s.outcome = "failed" if failed else "stopped", outcome
