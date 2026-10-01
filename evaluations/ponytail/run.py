"""Opt-in paired coding pilot. Never run in ordinary CI; requires API access + Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
import uuid
from functools import partial
from pathlib import Path

from autoresearch import behavior
from autoresearch.agents import AgentRunner
from autoresearch.catalog import ROOT, load_catalog
from autoresearch.coding import run_coding
from autoresearch.config import ProjectConfig, load_config
from autoresearch.contracts import ExperimentSpec, RunState, Stage
from autoresearch.execution import Executor
from autoresearch.providers import ProviderError
from autoresearch.store import Store

FIXTURE = Path(__file__).resolve().parent
POLICY = "prompts/coding_efficiency.md"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def prepare_specs(target: Path, enabled: bool) -> Path:
    """Create an isolated, versioned specification bundle for a new study."""
    shutil.copytree(ROOT, target)
    agents = json.loads((target / "agents.json").read_text())
    agent = agents["agents"]["coding_step"]
    agent["prompts"] = [name for name in agent["prompts"] if name != POLICY]
    agent["version"] = "4" if enabled else "3"
    if enabled:
        agent["prompts"].append(POLICY)
    write(target / "agents.json", agents)
    load_catalog(target)
    return target


def acceptance_passed(result) -> bool:
    return (
        result.status == "completed"
        and result.exit_code == 0
        and 'PONYTAIL_ACCEPTANCE {"tests": 7, "failures": 0, "errors": 0}'
        in result.stdout.splitlines()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--single-response",
        action="store_true",
        help="Separate code-generation probe; does not validate the coding loop",
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--attempt-cap", type=float, choices=(0.4, 0.5), default=0.5)
    parser.add_argument("--pairs", type=int, choices=range(1, 4), default=3)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    config = load_config(args.config)
    if config.mode != "live" or config.execution.backend != "docker":
        raise ValueError("Pilot requires live configuration and Docker execution")
    config.model_inventory = None
    config.allowed_models = None
    config.cheap_provider = config.frontier_provider = config.heldout_provider = None
    config.role_providers = {}
    config.role_panels = {}
    config.role_commands = {}
    config.role_command_max_cost_usd = {}
    config.prompt_overrides = {}
    config.privacy.cache = False
    config.pipeline.agents_per_role = config.pipeline.critics = 1
    config.pipeline.max_agent_repairs = 1
    config.provider.max_output_tokens = 3000
    config.provider.retries = 0
    config.provider.timeout_seconds = 90
    config.budget.usd = args.attempt_cap
    config.budget.max_calls = 24
    config.coding.max_steps = 20
    config.coding.max_commands = 6
    config.coding.wall_seconds = 600
    config.coding.command_timeout = 30
    shutil.copytree(FIXTURE, root / "fixture", ignore=shutil.ignore_patterns("__pycache__"))
    fixture = root / "fixture"
    task = (fixture / "task.md").read_text()
    source = root / "source"
    source.mkdir()
    for name in ("summary.py", "smoke.py", "task.md"):
        shutil.copyfile(fixture / name, source / name)
    config.project = ProjectConfig(
        source_dir=str(source), protected_paths=["smoke.py", "task.md"], specification=task
    )
    config.references = []
    config.search_enabled = False
    config.execution.readonly_mounts = {}
    config.execution.resource_hosts = []
    specs = {}
    for arm in ("baseline", "ponytail"):
        target = root / (arm + "-specs")
        prepare_specs(target, arm == "ponytail")
        if args.single_response:
            agents = json.loads((target / "agents.json").read_text())
            agent = dict(agents["agents"]["coding_step"])
            agent.update(
                role="coding_pilot",
                version="1",
                tools=[],
                validation=["argv"],
                model_policy="default",
                prompts=["prompts/pilot.md"],
            )
            agents["agents"]["coding_pilot"] = agent
            instruction = "Implement the supplied task in one response. Return AgentOutput JSON with the complete summary.py in files and argv=['python3','smoke.py']. Leave plans empty. No tools are available; do not claim execution."
            if arm == "ponytail":
                instruction += "\n" + (ROOT / POLICY).read_text()
            (target / "prompts/pilot.md").write_text(instruction)
            write(target / "agents.json", agents)
        specs[arm] = target
    order = [
        arm
        for pair in range(args.pairs)
        for arm in (("baseline", "ponytail") if pair % 2 == 0 else ("ponytail", "baseline"))
    ]
    write(
        root / "protocol.json",
        {
            "task": task,
            "mode": "single_response" if args.single_response else "coding_loop",
            "order": order,
            "pairs": args.pairs,
            "max_accounted_usd": args.pairs * 2 * args.attempt_cap,
            "fixture_sha256": {p.name: digest(p) for p in fixture.glob("*") if p.is_file()},
            "prompt_sha256": {
                arm: hashlib.sha256(
                    load_catalog(path)
                    .render("coding_pilot" if args.single_response else "coding_step")
                    .encode()
                ).hexdigest()
                for arm, path in specs.items()
            },
            "config": config.model_dump(mode="json"),
            "acceptance": "Every hidden unittest must pass on independently exported source; no feedback into agent",
            "adoption": "All registered attempts must pass; Ponytail aggregate accounted cost must be lower; no general quality claim",
        },
    )
    store = Store(root / "private")
    results = []
    for index, arm in enumerate(order):
        cfg = config.model_copy(deep=True)
        cfg.specification_dir = str(specs[arm])
        state = RunState(
            id=uuid.uuid4().hex[:12],
            title="CSV aggregation pilot",
            objective=task,
            stage=Stage.SUBSET,
        )
        bundle = behavior.snapshot(cfg)
        state.behavior = behavior.identity(bundle)
        store.create(state, cfg)
        behavior.archive(store, state, bundle)
        record = {
            "index": index,
            "pair": index // 2,
            "arm": arm,
            "run_id": state.id,
            "status": "started",
            "quality_passed": False,
        }
        results.append(record)
        write(root / "results.json", results)
        started = time.monotonic()
        runner = AgentRunner(store, cfg)
        print(json.dumps({"started": index, "arm": arm}), flush=True)
        try:
            if args.single_response:
                output = runner.run(
                    state,
                    "coding_pilot",
                    {
                        "task": task,
                        "source_files": {p.name: p.read_text() for p in source.iterdir()},
                    },
                )
            else:
                output = run_coding(
                    state,
                    partial(runner.run, state),
                    store,
                    cfg,
                    {
                        "source_dir": str(source),
                        "original_role": "subset",
                        "role_instruction": task,
                        "tool_protocol": runner.catalog.prompt("coding_step"),
                        "catalog_digest": runner.catalog.digest,
                    },
                )
            store.artifact(state.id, "pilot_output", "pilot-output.json", output.model_dump_json())
            exported = root / f"export-{index}"
            shutil.copytree(source, exported)
            # Executor safely applies the harness's exported FileEdits inside the sandbox workspace.
            shutil.copyfile(fixture / "acceptance.py", exported / "acceptance.py")
            result = Executor(cfg.execution).run(
                ExperimentSpec(
                    id=f"acceptance-{index}",
                    kind="coding-policy-acceptance",
                    workspace=str(exported),
                    argv=["python3", "acceptance.py"],
                    files=[f for f in output.files if f.path == "summary.py"],
                    timeout_seconds=30,
                    metadata={"protected_files": ["acceptance.py", "smoke.py", "task.md"]},
                ),
                command_only=True,
            )
            store.artifact(
                state.id, "pilot_acceptance", "pilot-acceptance.json", result.model_dump_json()
            )
            record.update(
                status="completed",
                quality_passed=acceptance_passed(result),
                acceptance=result.model_dump(mode="json"),
                output_sha256={
                    f.path: hashlib.sha256(f.content.encode()).hexdigest() for f in output.files
                },
                generated_lines=sum(len(f.content.splitlines()) for f in output.files),
            )
        except Exception as exc:
            record.update(
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                provider_failure=isinstance(exc, ProviderError),
            )
        record.update(wall_seconds=time.monotonic() - started, usage=store.usage(state.id))
        with store.connect() as db:
            record["call_usage"] = [
                json.loads(row[0])
                for row in db.execute("SELECT usage FROM calls WHERE run_id=?", (state.id,))
            ]
        checkpoints = list((store.run_dir(state.id) / "coding").glob("*/checkpoint.json"))
        if checkpoints:
            checkpoint = json.loads(checkpoints[0].read_text())
            record["coding_steps"] = len(checkpoint["steps"])
            record["commands"] = checkpoint["commands"]
        write(root / "results.json", results)
        print(
            json.dumps(
                {k: v for k, v in record.items() if k not in {"acceptance", "output_sha256"}}
            ),
            flush=True,
        )
        if record.get("provider_failure"):
            print(
                "Provider failure; stopping to preserve budget. Remaining registered arms unattempted.",
                flush=True,
            )
            break


if __name__ == "__main__":
    main()
