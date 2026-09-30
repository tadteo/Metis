"""Agent entry exercises actual accounting, private files and executable measurements."""

from __future__ import annotations

import base64
import hashlib
import json

import pytest

from autoresearch.agents import AgentRunner
from autoresearch.config import ResearchConfig
from autoresearch.contracts import (
    AgentOutput,
    AgentResponse,
    Evidence,
    ExecutionConfig,
    FileEdit,
    Idea,
    Stage,
    Usage,
)
from autoresearch.engine import Engine
from autoresearch.literature import Literature
from autoresearch.research_inputs import PaperInput, ResearchBrief, resolved_config
from autoresearch.store import Store


class Papers(Literature):
    def __init__(self, config):
        super().__init__(config, providers=[])

    def behavior_identity(self):
        return {"fixture": "public-synthetic-papers-v1"}

    def search(self, query, count=40):
        self.last_report = {"query": query, "synthetic": True}
        return [
            Evidence(
                id="paper",
                title="Synthetic regression reference",
                url="https://example.org/paper",
                full_text="Table 1, full benchmark: error 2.0. Fixed split: inputs 1,2; labels 2,4.",
            )
        ]


class IntakeProvider:
    def __init__(self, needs_input=False):
        self.calls = 0
        self.needs_input = needs_input

    def behavior_identity(self):
        return {"fixture": "intake-v1", "needs_input": self.needs_input}

    def complete(self, request):
        self.calls += 1
        if self.needs_input:
            output = AgentOutput(
                summary="Need a scientific choice",
                plans=[{"tool": "finish"}],
                structured=ResearchBrief(
                    outcome="needs_input", question="Which benchmark should define the question?"
                ).model_dump(),
            )
        elif self.calls == 1:
            output = AgentOutput(
                summary="Find independent context",
                plans=[{"tool": "discover", "query": "regression reference"}],
            )
        else:
            output = AgentOutput(
                summary="Grounded task",
                plans=[{"tool": "finish"}],
                structured=ResearchBrief(
                    outcome="grounded",
                    problem="Improve prediction under the fixed benchmark",
                    reference_method="Published linear predictor",
                    sources=["paper"],
                ).model_dump(),
            )
        return AgentResponse(
            data=output.model_dump(),
            model="scripted",
            provider="fixture",
            usage=Usage(cost_usd=0.01),
        )


def inquiry(tmp_path, provider=None):
    config = ResearchConfig(
        entry_mode="agent", execution=ExecutionConfig(backend="local", allow_local=True)
    )
    config.pipeline.critics = 1
    store = Store(tmp_path / "private")
    provider = provider or IntakeProvider()
    engine = Engine(store, config, provider=provider, literature=Papers(config))
    return store, engine, provider


def test_empty_project_creation_is_free_and_intake_uses_run_ledger(tmp_path):
    store, engine, provider = inquiry(tmp_path)
    state = engine.create("Question", "Improve the benchmark")
    assert state.stage == Stage.INTAKE and provider.calls == 0
    assert store.usage(state.id)["calls"] == 0
    result = engine.step(state.id)
    assert result.stage == Stage.LIMITATIONS, result.error
    assert result.intake_outcome == "grounded"
    assert result.research_brief["sources"] == ["paper"]
    assert store.usage(state.id)["calls"] == 2
    assert store.get_config(state.id).project.sota == {}


def test_clarification_is_versioned_deduplicated_and_does_not_start_calls(tmp_path):
    store, engine, provider = inquiry(tmp_path, IntakeProvider(needs_input=True))
    state = engine.create("Question", "Study learning")
    result = engine.step(state.id)
    assert result.status == "paused" and result.stage == Stage.INTAKE
    calls = provider.calls
    with pytest.raises(ValueError, match="Resolve research intake"):
        engine.intervene(state.id, "skip it", "limitations")
    answered = engine.intervene(state.id, "Use the published regression benchmark")
    assert answered.input_revision == 1 and not answered.research_brief
    duplicate = engine.intervene(state.id, "Use the published regression benchmark")
    assert duplicate.input_revision == 1
    assert engine.step(state.id).status == "paused"
    assert provider.calls == calls
    assert len([a for a in store.artifacts(state.id) if a["kind"] == "research_brief"]) == 1


def test_intake_budget_exhaustion_retains_discovery_and_never_skips_stage(tmp_path):
    store, engine, provider = inquiry(tmp_path)
    engine.config.budget.max_calls = 1
    state = engine.create("Question", "Improve regression")
    result = engine.step(state.id)
    assert result.status == "budget_exhausted", result.error
    assert result.stage == Stage.INTAKE and result.evidence
    assert provider.calls == 1
    assert list(store.run_dir(state.id).glob("coding/*/checkpoint.json"))


def test_attachment_text_and_extraction_failure_are_preserved_without_calls(tmp_path):
    store, engine, provider = inquiry(tmp_path)
    papers = [
        {"name": "Paper", "text": "A public synthetic task description."},
        {"name": "Broken PDF", "content_base64": base64.b64encode(b"%PDF-broken").decode()},
    ]
    state = engine.create("Question", "Use associated papers", papers=papers)
    assert provider.calls == 0 and len(state.materials) == 2
    assert "page 1" in state.evidence[0].full_text
    assert state.materials[1]["extraction_error"]
    assert state.evidence[0].content_hash == hashlib.sha256(papers[0]["text"].encode()).hexdigest()
    with pytest.raises(ValueError):
        PaperInput(name="nothing")


DATA = "[2, 4]"
TRAIN = "import json\njson.dump([2, 3], open('predictions.json', 'w'))\n"
SCORER = "import json\na=json.load(open('predictions.json')); b=json.load(open('labels.json'))\nassert len(a)==len(b)\njson.dump({'error':sum(abs(x-y) for x,y in zip(a,b))/len(b)},open('metrics.json','w'))\n"
CHECK = "import json, subprocess, sys\njson.dump([2,4],open('predictions.json','w'))\nsubprocess.run([sys.executable,'score.py'],check=True)\nassert json.load(open('metrics.json'))['error']==0\njson.dump([0,0],open('predictions.json','w'))\nsubprocess.run([sys.executable,'score.py'],check=True)\nassert json.load(open('metrics.json'))['error']==3\n"


def proposal():
    return AgentOutput(
        summary="Implement synthetic baseline",
        argv=["python3", "train.py"],
        files=[
            FileEdit(path=name, content=text)
            for name, text in [
                ("train.py", TRAIN),
                ("score.py", SCORER),
                ("check.py", CHECK),
                ("labels.json", DATA),
            ]
        ],
        structured={
            "protocol": {
                "metrics": {"error": "min"},
                "sota": {"error": 2.0},
                "reference_sources": {
                    "error": {"evidence_id": "paper", "location": "Table 1", "excerpt": "error 2.0"}
                },
                "specification": "Fixed synthetic benchmark, inputs 1,2 and labels 2,4; subset and full coincide only in this test.",
                "evaluator_argv": ["python3", "score.py"],
                "protected_paths": ["score.py", "labels.json"],
                "dataset_manifest": {
                    "sha256:labels.json": hashlib.sha256(DATA.encode()).hexdigest()
                },
                "measurement_checks": [["python3", "check.py"]],
                "measurement_artifacts": ["predictions.json"],
            }
        },
    )


class BaselineRunner(AgentRunner):
    def run(self, state, role, context=None):
        if role == "baseline":
            return proposal()
        if role == "experiment_integrity":
            # Explicit scripted reviewer fixture; does not establish scientific validity.
            return AgentOutput(
                summary="Synthetic reviewer accepts known fixture", decision="accept"
            )
        return super().run(state, role, context)


def test_baseline_from_empty_workspace_seals_measurement_and_ignores_imported_command(tmp_path):
    store, engine, provider = inquiry(tmp_path)
    engine.config.project.baseline_argv = ["python3", "nonexistent-old-command.py"]
    engine.runner_factory = lambda st, c: BaselineRunner(st, c)
    # Stable adapter identity is explicit; there are no model/network calls in this fixture.
    engine.runner_factory.behavior_identity = lambda: {"fixture": "baseline-runner-v1"}
    state = engine.create("Baseline", "Reproduce fixed synthetic regression")
    state.stage = Stage.BASELINE
    state.evidence = Papers(engine.config).search("fixture")
    state.ideas = [Idea(id="idea", title="Idea", hypothesis="Test improvement")]
    state.queue = ["idea"]
    store.save(state)
    result = engine.step(state.id)
    assert result.stage == Stage.SUBSET, result.error
    assert result.baseline == {"error": 0.5}
    assert result.research_protocol
    assert result.experiments[0].provenance["argv"] == ["python3", "train.py"]
    assert result.experiments[0].provenance["measurement_artifacts"]["predictions.json"]["sha256"]
    pinned = store.get_config(state.id)
    assert pinned.project.sota == {} and pinned.project.evaluator_argv == []
    view = resolved_config(pinned, result, store)
    assert view.project.sota == {"error": 2.0} and view.project.metrics == {"error": "min"}
    scorer = store.run_dir(state.id) / result.research_protocol["source_path"] / "score.py"
    scorer.write_text("# changed")
    with pytest.raises(ValueError, match="assets changed"):
        resolved_config(pinned, result, store)


class RepairRunner(BaselineRunner):
    def run(self, state, role, context=None):
        if role == "baseline" and state.counters.get("protocol_repairs", 0) == 0:
            result = proposal()
            result.structured["protocol"].pop("reference_sources")
            return result
        return super().run(state, role, context)


def baseline_fixture(tmp_path, runner=BaselineRunner):
    store, engine, provider = inquiry(tmp_path)

    def factory(st, c):
        return runner(st, c)

    factory.behavior_identity = lambda: {"fixture": runner.__name__}
    engine.runner_factory = factory
    state = engine.create("Baseline", "Synthetic regression benchmark")
    state.stage = Stage.BASELINE
    state.evidence = Papers(engine.config).search("fixture")
    state.ideas = [Idea(id="idea", title="Idea", hypothesis="Test improvement")]
    state.queue = ["idea"]
    store.save(state)
    return store, engine, state


def test_malformed_protocol_repairs_without_user_resume_and_retains_attempt(tmp_path):
    store, engine, state = baseline_fixture(tmp_path, RepairRunner)
    first = engine.step(state.id)
    assert first.stage == Stage.BASELINE and first.status == "ready", first.error
    assert first.active_output is None and first.counters["protocol_repairs"] == 1
    second = engine.step(state.id)
    assert second.stage == Stage.SUBSET, second.error
    assert any(a["kind"] == "rejected_protocol" for a in store.artifacts(state.id))


class AuditRepairRunner(BaselineRunner):
    def run(self, state, role, context=None):
        if role == "experiment_integrity" and not state.counters.get("protocol_repairs"):
            return AgentOutput(summary="Measurement needs clearer controls", decision="refine")
        return super().run(state, role, context)


def test_rejected_protocol_audit_reenters_baseline_coding(tmp_path):
    store, engine, state = baseline_fixture(tmp_path, AuditRepairRunner)
    assert engine.step(state.id).status == "ready"
    assert engine.step(state.id).stage == Stage.SUBSET
    assert len([a for a in store.artifacts(state.id) if a["kind"] == "protocol_inspection"]) == 2


class InstrumentedRunner(BaselineRunner):
    def run(self, state, role, context=None):
        if role == "baseline":
            out = proposal()
            out.files[0].content += SCORER
            p = out.structured["protocol"]
            p.update(
                measurement_mode="instrumented",
                measurement_paths=["train.py"],
                evaluator_argv=[],
                measurement_checks=[["python3", "-c", "assert 2 + 2 == 4"]],
            )
            return out
        return super().run(state, role, context)


def test_instrumented_measurement_checks_without_metrics_and_requires_rerun(tmp_path):
    store, engine, state = baseline_fixture(tmp_path, InstrumentedRunner)
    result = engine.step(state.id)
    assert result.stage == Stage.SUBSET, result.error
    assert result.baseline == {"error": 0.5}
    assert result.experiments[0].provenance["measurement_reproduction"]["status"] == "completed"
    assert any(a["kind"] == "measurement_reproduction" for a in store.artifacts(state.id))


@pytest.mark.parametrize(
    "original,changed", [(b"\x80", b"\x81"), (b"x" * 11000000 + b"a", b"x" * 11000000 + b"b")]
)
def test_artifact_identity_covers_binary_and_large_file_bytes(tmp_path, original, changed):
    from autoresearch.runtime_support import file_identity

    file = tmp_path / "measurements.bin"
    file.write_bytes(original)
    first = file_identity(tmp_path, file.name)
    assert first == {"sha256": hashlib.sha256(original).hexdigest(), "bytes": len(original)}
    file.write_bytes(changed)
    assert first != file_identity(tmp_path, file.name)


def test_agent_preflight_accepts_empty_project_and_defers_unavailable_compute(
    tmp_path, monkeypatch
):
    from autoresearch.setup import preflight

    config = ResearchConfig(entry_mode="agent")
    config.provider.base_url = "http://127.0.0.1:1234/v1"
    config.provider.api_key_env = "SYNTHETIC_LOCAL_KEY"
    monkeypatch.setattr("shutil.which", lambda command: None)
    result = preflight(config, probe_runtime=True)
    assert result["ready"], result
    assert not any(
        check["name"] in {"baseline", "evaluator", "metrics"} for check in result["checks"]
    )


class CodingProvider(IntakeProvider):
    def complete(self, request):
        from autoresearch.inspection import DIMENSIONS

        context = json.loads(request.prompt)
        if request.role == "coding_step":
            p = proposal()
            actions = [
                {"tool": "list"},
                {"tool": "edit", "edits": [edit.model_dump() for edit in p.files]},
                {"tool": "command", "argv": ["python3", "check.py"]},
                {"tool": "finish", "criterion": "Zero-error and deliberate-error checks pass"},
            ]
            step = context["steps_completed"]
            output = AgentOutput(
                summary="Scripted coding fixture",
                plans=[actions[step]],
                argv=p.argv,
                structured=p.structured if step == 3 else {},
            )
        elif request.role == "inspection_step":
            if context["inspection_step"] == 0:
                output = AgentOutput(
                    summary="Read actual scoring source",
                    plans=[{"tool": "read", "path": "score.py"}],
                )
            else:
                output = AgentOutput(
                    summary="Scripted independent inspection",
                    plans=[{"tool": "finish"}],
                    structured={
                        "inspection_findings": [
                            {
                                "dimension": dimension,
                                "path": "score.py",
                                "start_line": 1,
                                "end_line": 4,
                                "conclusion": "Known fixture computes absolute error from actual predictions and fixed labels.",
                            }
                            for dimension in DIMENSIONS["experiment_integrity"]
                        ]
                    },
                )
        else:
            return super().complete(request)
        self.calls += 1
        return AgentResponse(
            data=output.model_dump(),
            model="scripted",
            provider="fixture",
            usage=Usage(cost_usd=0.01),
        )


def test_real_coding_loop_builds_empty_project_and_independent_inspection_runs(tmp_path):
    store, engine, provider = inquiry(tmp_path, CodingProvider())
    state = engine.create("Empty workspace", "Reproduce the fixed regression benchmark")
    state = engine.step(state.id)
    assert state.stage == Stage.LIMITATIONS
    # The separately tested scientific seed loop is not replaced; this fixture focuses on baseline tooling.
    state.stage = Stage.BASELINE
    state.ideas = [Idea(id="candidate", title="Candidate", hypothesis="Try a mechanism")]
    state.queue = ["candidate"]
    store.save(state)
    state = engine.step(state.id)
    assert state.stage == Stage.SUBSET, state.error
    assert state.baseline == {"error": 0.5}
    artifacts = store.artifacts(state.id)
    assert any(a["kind"] == "coding_command" for a in artifacts)
    assert any(a["kind"] == "protocol_inspection" for a in artifacts)
    assert store.usage(state.id)["calls"] == provider.calls
    assert store.get_config(state.id).project.evaluator_argv == []


@pytest.mark.parametrize("defect", ["citation", "missing_asset"])
def test_protocol_grounding_and_missing_asset_errors_automatically_repair(tmp_path, defect):
    class BrokenProposal(BaselineRunner):
        def run(self, state, role, context=None):
            output = super().run(state, role, context)
            if role == "baseline" and not state.counters.get("protocol_repairs"):
                if defect == "citation":
                    output.structured["protocol"]["reference_sources"]["error"]["excerpt"] = (
                        "invented 2.0"
                    )
                else:
                    output.files = [edit for edit in output.files if edit.path != "labels.json"]
            return output

    store, engine, state = baseline_fixture(tmp_path, BrokenProposal)
    first = engine.step(state.id)
    assert first.stage == Stage.BASELINE and first.status == "ready", first.error
    assert first.counters["protocol_repairs"] == 1
    assert engine.step(state.id).stage == Stage.SUBSET
    assert any(a["kind"] == "rejected_protocol" for a in store.artifacts(state.id))


def test_instrumented_scheduler_jobs_resume_their_own_specification(tmp_path):
    from autoresearch.contracts import ExperimentResult
    from autoresearch.execution import Executor

    class Scheduler(Executor):
        def __init__(self):
            super().__init__(ExecutionConfig(backend="slurm"))
            self.jobs = {}
            self.polled = []

        def behavior_identity(self):
            return {"fixture": "deterministic-scheduler-v1"}

        def run(self, spec, *, command_only=False):
            if command_only:
                return ExperimentResult(id=spec.id, status="completed")
            assert spec.id not in self.jobs, "submission must not repeat"
            job = str(100 + len(self.jobs))
            self.jobs[spec.id] = job
            return ExperimentResult(id=spec.id, status="pending", job_id=job)

        def poll(self, spec, job_id):
            assert self.jobs[spec.id] == job_id
            self.polled.append(spec.id)
            return ExperimentResult(id=spec.id, status="completed", metrics={"error": 0.5})

    store, engine, state = baseline_fixture(tmp_path, InstrumentedRunner)
    scheduler = Scheduler()
    engine.executor = scheduler
    # Pin adapter identity before creation instead of weakening behavior verification.
    engine.config = store.get_config(state.id)
    state = engine.create("Scheduler fixture", "Synthetic instrumented benchmark")
    state.stage = Stage.BASELINE
    state.evidence = Papers(engine.config).search("fixture")
    state.ideas = [Idea(id="idea", title="Idea", hypothesis="Improve")]
    state.queue = ["idea"]
    store.save(state)
    first = engine.step(state.id)
    assert first.status == "waiting", first.error
    original_id = first.pending_experiment.id
    assert first.pending_job_spec_id == original_id

    # Reconstruct engine between every poll, as a stopped/restarted worker does.
    def restart():
        return Engine(
            store,
            engine.config,
            executor=scheduler,
            runner_factory=engine.runner_factory,
            provider=engine.provider,
            literature=engine.literature,
        )

    second = restart().step(state.id)
    assert second.status == "waiting", second.error
    assert second.pending_job_spec_id == "measurement-" + original_id
    assert len(scheduler.jobs) == 2
    third = restart().step(state.id)
    assert third.stage == Stage.SUBSET, third.error
    assert scheduler.polled == [original_id, "measurement-" + original_id]
    assert not third.pending_job_id and not third.pending_job_spec_id
    assert len(third.experiments) == 1
    assert third.experiments[0].provenance["measurement_reproduction"]["status"] == "completed"


def test_failed_baseline_retains_source_and_reaudits_new_protocol_version(tmp_path):
    class FailingBaseline(BaselineRunner):
        def run(self, state, role, context=None):
            out = super().run(state, role, context)
            if role == "baseline":
                if not state.counters.get("baseline_repairs"):
                    out.argv = ["python3", "missing.py"]
                else:
                    from pathlib import Path

                    assert (Path(context["source_dir"]) / "score.py").exists()
                    assert (Path(context["source_dir"]) / "train.py").exists()
            return out

    store, engine, state = baseline_fixture(tmp_path, FailingBaseline)
    first = engine.step(state.id)
    assert first.stage == Stage.BASELINE and first.status == "ready", first.error
    assert first.experiments[0].status == "failed"
    assert not first.research_protocol
    assert first.experiments[0].provenance["research_protocol"]["version"] == 1
    second = engine.step(state.id)
    assert second.stage == Stage.SUBSET, second.error
    assert second.research_protocol["version"] == 2
    assert second.experiments[0].status == "failed"
    assert second.experiments[1].status == "completed"
    assert len([a for a in store.artifacts(state.id) if a["kind"] == "protocol_inspection"]) == 2


def test_accepted_baseline_cannot_unseal_protocol_after_failed_reentry(tmp_path):
    class ReentryFailure(BaselineRunner):
        def run(self, state, role, context=None):
            out = super().run(state, role, context)
            if role == "baseline" and state.baseline:
                out.argv = ["python3", "missing.py"]
                out.files = [
                    edit for edit in out.files if edit.path not in {"score.py", "labels.json"}
                ]
            return out

    store, engine, state = baseline_fixture(tmp_path, ReentryFailure)
    accepted = engine.step(state.id)
    assert accepted.stage == Stage.SUBSET
    original = accepted.research_protocol
    engine.intervene(state.id, "Retry the baseline implementation", "baseline")
    failed = engine.step(state.id)
    assert failed.stage == Stage.BASELINE and failed.status == "ready", failed.error
    assert failed.research_protocol == original
    assert failed.baseline == accepted.baseline
    assert failed.experiments[-1].status == "failed"
    assert not any(item.get("kind") == "protocol_invalidated" for item in failed.memory)


def test_existing_partial_project_is_copied_and_original_preserved(tmp_path):
    source = tmp_path / "existing"
    source.mkdir()
    original = "# Author's partial implementation; no runnable benchmark yet."
    (source / "method.py").write_text(original)
    store, engine, _ = inquiry(tmp_path)
    engine.config.project.source_dir = str(source)
    state = engine.create("Partial project", "Complete a reproducible reference benchmark")
    copied = store.run_dir(state.id) / "source" / "method.py"
    assert copied.read_text() == original
    copied.write_text("# private working copy")
    assert (source / "method.py").read_text() == original
    assert state.stage == Stage.INTAKE


@pytest.mark.parametrize("auxiliary", ["measurement_check", "measurement_reproduction"])
def test_auxiliary_scheduler_cancellation_resumes_from_its_own_receipt(tmp_path, auxiliary):
    from autoresearch.contracts import ExperimentResult
    from autoresearch.execution import Executor

    class AuxiliaryScheduler(Executor):
        def __init__(self):
            super().__init__(ExecutionConfig(backend="slurm"))
            self.submitted = []
            self.cancelled = []

        def behavior_identity(self):
            return {"fixture": "auxiliary-cancellation-v1", "auxiliary": auxiliary}

        def run(self, spec, *, command_only=False):
            if spec.kind == auxiliary:
                self.submitted.append(spec.id)
                return ExperimentResult(id=spec.id, status="pending", job_id="321")
            return Executor(ExecutionConfig(backend="local", allow_local=True)).run(
                spec, command_only=command_only
            )

        def poll(self, spec, job_id):
            pytest.fail(
                "A cancelled job must be read from its receipt, never polled or resubmitted"
            )

        def cancel(self, job_id):
            self.cancelled.append(job_id)

    store, engine, _ = baseline_fixture(tmp_path, InstrumentedRunner)
    scheduler = AuxiliaryScheduler()
    engine.executor = scheduler
    state = engine.create("Cancellation", "Synthetic benchmark")
    state.stage = Stage.BASELINE
    state.evidence = Papers(engine.config).search("fixture")
    state.ideas = [Idea(id="idea", title="Idea", hypothesis="Improve")]
    state.queue = ["idea"]
    store.save(state)
    pending = engine.step(state.id)
    assert pending.status == "waiting", pending.error
    actual_id = pending.pending_job_spec_id
    resumed_engine = Engine(
        store,
        engine.config,
        executor=scheduler,
        runner_factory=engine.runner_factory,
        provider=engine.provider,
        literature=engine.literature,
    )
    cancelled = resumed_engine.cancel_experiment(state.id)
    assert cancelled.status == "paused"
    assert not cancelled.pending_job_id and not cancelled.pending_job_spec_id
    assert scheduler.cancelled == ["321"]
    assert cancelled.experiments == []
    receipt = json.loads((store.run_dir(state.id) / "receipts" / f"{actual_id}.json").read_text())
    assert receipt["id"] == actual_id and receipt["status"] == "cancelled"
    resumed_engine.resume(state.id)
    result = resumed_engine.step(state.id)
    assert result.status == "ready" and result.stage == Stage.BASELINE, result.error
    assert scheduler.submitted == [actual_id]
    if auxiliary == "measurement_check":
        assert result.experiments == []
        assert result.counters["protocol_repairs"] == 1
    else:
        assert len(result.experiments) == 1
        assert result.experiments[0].status == "failed"
        assert result.experiments[0].provenance["measurement_reproduction"]["status"] == "cancelled"


def test_pdf_attachment_extracts_page_text_and_preserves_original(tmp_path):
    import io

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 100 Td (Public synthetic benchmark: error 2.0) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    original = buffer.getvalue()
    store, engine, provider = inquiry(tmp_path)
    state = engine.create(
        "PDF input",
        "Study this supplied benchmark",
        papers=[{"name": "Public fixture", "content_base64": base64.b64encode(original).decode()}],
    )
    assert provider.calls == 0
    assert "[page 1]" in state.evidence[0].full_text
    assert "Public synthetic benchmark: error 2.0" in state.evidence[0].full_text
    material = state.materials[0]
    assert not material["extraction_error"]
    assert (store.run_dir(state.id) / "papers" / material["file"]).read_bytes() == original


def test_explicit_configured_cli_overrides_saved_agent_entry(tmp_path, capsys):
    from autoresearch.cli import main
    from autoresearch.settings import load_settings, save_settings

    store = Store(tmp_path / "private")
    config, revision = load_settings(store)
    config.entry_mode = "agent"
    save_settings(store, config, revision)
    assert (
        main(
            [
                "--state-dir",
                str(store.root),
                "new",
                "--configured",
                "--objective",
                "Use an imported configured benchmark",
            ]
        )
        == 0
    )
    state = json.loads(capsys.readouterr().out)
    assert state["stage"] == "limitations"
    assert store.get_config(state["id"]).entry_mode == "configured"
