"""Real executable feedback and failure/resume behavior of the coding harness."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from autoresearch.coding import CodingFailure, CodingSession, run_coding
from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentOutput, ExecutionConfig, RunState, Stage
from autoresearch.execution import ExecutionError
from autoresearch.store import Store


def setup(tmp_path: Path) -> tuple[Store, RunState, ResearchConfig, dict[str, Any]]:
    source = tmp_path / "repo"
    source.mkdir()
    (source / "model.py").write_text("def predict(value):\n    return value - 1\n")
    (source / "test_model.py").write_text("from model import predict\nassert predict(2) == 3\n")
    (source / "evaluate.py").write_text("# operator-owned protocol\n")
    config = ResearchConfig(execution=ExecutionConfig(backend="local", allow_local=True))
    config.project.source_dir = str(source)
    config.project.protected_paths = ["evaluate.py", "test_model.py"]
    store = Store(tmp_path / "private")
    state = RunState(
        id="abcdef123456",
        title="Coding integration",
        objective="Repair prediction",
        stage=Stage.SUBSET,
    )
    store.create(state, config)
    return store, state, config, {"source_dir": str(source), "original_role": "subset"}


def scripted(actions: list[dict[str, Any]]) -> Callable[[str, dict[str, Any]], AgentOutput]:
    def call(role: str, context: dict[str, Any]) -> AgentOutput:
        assert role == "coding_step"
        action = actions.pop(0)
        return AgentOutput(
            summary="Use real execution feedback", plans=[action], argv=["python3", "model.py"]
        )

    return call


def test_multistep_explore_failure_debug_multifile_repair_and_finish(tmp_path: Path) -> None:
    store, state, config, context = setup(tmp_path)
    seen: list[dict[str, Any]] = []
    actions = [
        {"tool": "list"},
        {"tool": "search", "query": "predict"},
        {"tool": "read", "path": "model.py"},
        {"tool": "command", "argv": ["python3", "test_model.py"]},
        {
            "tool": "edit",
            "edits": [
                {"path": "increment.py", "content": "def increment(x):\n    return x + 1\n"},
                {
                    "path": "model.py",
                    "content": "from increment import increment\ndef predict(value):\n    return increment(value)\n",
                },
            ],
        },
        {"tool": "command", "argv": ["python3", "test_model.py"]},
        {"tool": "finish", "criterion": "Protected prediction test passed on current code"},
    ]
    base = scripted(actions)

    def call(role: str, ctx: dict[str, Any]) -> AgentOutput:
        seen.append(ctx)
        return base(role, ctx)

    result = run_coding(state, call, store, config, context)
    assert {edit.path for edit in result.files} == {"model.py", "increment.py"}
    assert "return value - 1" in (Path(context["source_dir"]) / "model.py").read_text()
    assert not state.experiments  # checks/pilots are not duplicated formal experiments
    failed = seen[4]["recent_steps"][-1]["observation"]["result"]
    assert failed["status"] == "failed" and "AssertionError" in failed["stderr"]
    receipts = [a for a in store.artifacts(state.id) if a["kind"] == "coding_command"]
    assert len(receipts) == 2
    assert result.plans[0]["scientific_criterion_pending"]
    assert (
        run_coding(
            state,
            lambda *_: pytest.fail("completed session must not call model"),
            store,
            config,
            context,
        )
        == result
    )


def test_cannot_finish_after_failed_or_stale_check(tmp_path: Path) -> None:
    store, state, config, context = setup(tmp_path)
    config.coding.max_steps = 4
    with pytest.raises(CodingFailure, match="step budget"):
        run_coding(
            state,
            scripted(
                [
                    {"tool": "command", "argv": ["python3", "-c", "pass"]},
                    {"tool": "edit", "edits": [{"path": "model.py", "content": "broken"}]},
                    {"tool": "finish", "criterion": "old check"},
                    {"tool": "command", "argv": ["python3", "test_model.py"]},
                ]
            ),
            store,
            config,
            context,
        )
    checkpoint = json.loads(
        next((store.run_dir(state.id) / "coding").glob("*/checkpoint.json")).read_text()
    )
    assert "after the latest code edits" in checkpoint["steps"][2]["observation"]["error"]
    assert checkpoint["last_success_code"] is None


def test_resume_does_not_repeat_recorded_commands_and_retains_failed_attempts(
    tmp_path: Path,
) -> None:
    store, state, config, context = setup(tmp_path)
    calls = 0

    def crash_after_command(role: str, ctx: dict[str, Any]) -> AgentOutput:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("provider temporarily unavailable")
        return AgentOutput(
            summary="check", plans=[{"tool": "command", "argv": ["python3", "test_model.py"]}]
        )

    with pytest.raises(RuntimeError, match="temporarily"):
        run_coding(state, crash_after_command, store, config, context)
    output = run_coding(
        state,
        scripted(
            [
                {
                    "tool": "edit",
                    "replacements": [
                        {"path": "model.py", "old_text": "value - 1", "new_text": "value + 1"}
                    ],
                },
                {"tool": "command", "argv": ["python3", "test_model.py"]},
                {"tool": "finish", "criterion": "repaired test passes"},
            ]
        ),
        store,
        config,
        context,
    )
    assert len(output.files) == 1
    assert len([a for a in store.artifacts(state.id) if a["kind"] == "coding_command"]) == 2


def test_protected_files_enforced_for_edits_and_command_mutations(tmp_path: Path) -> None:
    store, state, config, context = setup(tmp_path)
    config.coding.max_steps = 2
    with pytest.raises(CodingFailure):
        run_coding(
            state,
            scripted(
                [
                    {"tool": "edit", "edits": [{"path": "evaluate.py", "content": "malicious"}]},
                    {
                        "tool": "command",
                        "argv": ["python3", "-c", "open('evaluate.py','w').write('malicious')"],
                    },
                ]
            ),
            store,
            config,
            context,
        )
    folder = next((store.run_dir(state.id) / "coding").iterdir())
    checkpoint = json.loads((folder / "checkpoint.json").read_text())
    assert "protected" in checkpoint["steps"][0]["observation"]["error"]
    assert checkpoint["steps"][1]["observation"]["result"]["status"] == "failed"
    assert (folder / "workspace" / "evaluate.py").read_text() == "# operator-owned protocol\n"


def test_arbitrary_text_files_late_lines_and_delete_are_supported(tmp_path: Path) -> None:
    store, state, config, context = setup(tmp_path)
    source = Path(context["source_dir"])
    (source / "large.cpp").write_text("// header\n" * 40000 + "int answer = 42;\n")
    session = CodingSession(state, scripted([]), store, config, context)
    from autoresearch.coding import CodingAction

    read = session.observation(CodingAction(tool="read", path="large.cpp", start_line=40001))
    assert "answer = 42" in read["text"]
    result = run_coding(
        state,
        scripted(
            [
                {"tool": "delete", "paths": ["large.cpp"]},
                {"tool": "command", "argv": ["python3", "-c", "pass"]},
                {"tool": "finish", "criterion": "source cleanup checked"},
            ]
        ),
        store,
        config,
        context,
    )
    assert result.deleted_files == ["large.cpp"]


@pytest.mark.parametrize("path", ["../secret", ".env", "a/.ssh/private", ".git/config"])
def test_path_and_credential_boundaries(tmp_path: Path, path: str) -> None:
    store, state, config, context = setup(tmp_path)
    session = CodingSession(state, scripted([]), store, config, context)
    from autoresearch.coding import CodingAction

    with pytest.raises(ExecutionError):
        session.observation(CodingAction(tool="read", path=path))


def test_interrupted_unreceipted_command_is_not_blindly_reexecuted(tmp_path: Path) -> None:
    store, state, config, context = setup(tmp_path)
    config.coding.max_steps = 1
    session = CodingSession(state, scripted([]), store, config, context)
    output = AgentOutput(
        summary="interrupted",
        plans=[
            {"tool": "command", "argv": ["python3", "-c", "open('duplicated','w').write('bad')"]}
        ],
    )
    session.record["pending"] = {"output": output.model_dump(), "started": True}
    session.record["commands"] = 1
    session.save()
    with pytest.raises(CodingFailure):
        run_coding(
            state, lambda *_: pytest.fail("must recover pending command"), store, config, context
        )
    assert not (session.root / "duplicated").exists()
    receipt = json.loads((session.folder / "command-0.json").read_text())
    assert receipt["status"] == "failed"
    assert receipt["provenance"]["uncertain_execution"] is True
