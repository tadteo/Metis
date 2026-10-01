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


def test_pilot_outputs_are_not_exported_as_clean_experiment_source(tmp_path: Path) -> None:
    store, state, config, context = setup(tmp_path)
    result = run_coding(
        state,
        scripted(
            [
                {
                    "tool": "command",
                    "argv": ["python3", "-c", "open('predictions.json','w').write('[1,2,3]')"],
                },
                {"tool": "finish", "criterion": "pilot generated predictions"},
            ]
        ),
        store,
        config,
        context,
    )
    assert not result.files
    folder = next((store.run_dir(state.id) / "coding").iterdir())
    assert (folder / "workspace/predictions.json").exists()


@pytest.mark.parametrize("declare", [True, False])
def test_generated_source_export_can_recreate_a_clean_experiment(
    tmp_path: Path, declare: bool
) -> None:
    import shutil
    import subprocess

    store, state, config, context = setup(tmp_path)
    source = "def increment(x): return x + 1\n"
    model = "from increment import increment\ndef predict(x): return increment(x)\n"
    actions = [
        {
            "tool": "command",
            "argv": [
                "python3",
                "-c",
                f"open('increment.py','w').write({source!r}); open('model.py','w').write({model!r}); open('predictions.json','w').write('[999]')",
            ],
        },
        {"tool": "command", "argv": ["python3", "test_model.py"]},
        {
            "tool": "finish",
            "criterion": "Protected test passed",
            "paths": ["increment.py"] if declare else [],
        },
    ]
    result = run_coding(state, scripted(actions), store, config, context)
    assert {edit.path for edit in result.files} == (
        {"model.py", "increment.py"} if declare else {"model.py"}
    )
    fresh = tmp_path / "formal"
    shutil.copytree(Path(context["source_dir"]), fresh)
    for edit in result.files:
        (fresh / edit.path).write_text(edit.content)
    check = subprocess.run(
        ["python3", "test_model.py"], cwd=fresh, capture_output=True, check=False
    )
    assert (check.returncode == 0) is declare
    folder = next((store.run_dir(state.id) / "coding").iterdir())
    assert (folder / "workspace/predictions.json").read_text() == "[999]"
    assert not (fresh / "predictions.json").exists()


def test_exact_replacement_registers_command_generated_source(tmp_path: Path) -> None:
    store, state, config, context = setup(tmp_path)
    result = run_coding(
        state,
        scripted(
            [
                {
                    "tool": "command",
                    "argv": ["python3", "-c", "open('generated.py','w').write('value = 1')"],
                },
                {
                    "tool": "edit",
                    "replacements": [
                        {"path": "generated.py", "old_text": "value = 1", "new_text": "value = 2"}
                    ],
                },
                {
                    "tool": "command",
                    "argv": ["python3", "-c", "from generated import value; assert value == 2"],
                },
                {"tool": "finish", "criterion": "Generated source value checked"},
            ]
        ),
        store,
        config,
        context,
    )
    assert [edit.path for edit in result.files] == ["generated.py"]


def test_missing_explicit_source_export_is_reported_as_failed_action(tmp_path: Path) -> None:
    store, state, config, context = setup(tmp_path)
    config.coding.max_steps = 2
    with pytest.raises(CodingFailure, match="step budget"):
        run_coding(
            state,
            scripted(
                [
                    {"tool": "command", "argv": ["python3", "-c", "print('check')"]},
                    {"tool": "finish", "criterion": "Check passed", "paths": ["typo.py"]},
                ]
            ),
            store,
            config,
            context,
        )
    folder = next((store.run_dir(state.id) / "coding").iterdir())
    saved = json.loads((folder / "checkpoint.json").read_text())
    assert "does not exist" in saved["steps"][-1]["observation"]["error"]
    assert not saved.get("completed")


def test_rejected_edit_does_not_poison_a_later_valid_finish(tmp_path: Path) -> None:
    store, state, config, context = setup(tmp_path)
    result = run_coding(
        state,
        scripted(
            [
                {"tool": "edit", "edits": [{"path": "evaluate.py", "content": "forbidden"}]},
                {
                    "tool": "command",
                    "argv": [
                        "python3",
                        "-c",
                        "assert open('evaluate.py').read() == '# operator-owned protocol\\n'",
                    ],
                },
                {"tool": "finish", "criterion": "Protected script intact"},
            ]
        ),
        store,
        config,
        context,
    )
    assert not result.files
    folder = next((store.run_dir(state.id) / "coding").iterdir())
    saved = json.loads((folder / "checkpoint.json").read_text())
    assert "error" in saved["steps"][0]["observation"]


def test_exhaustion_identifies_last_failed_command_and_preserved_checkpoint(tmp_path: Path) -> None:
    store, state, config, context = setup(tmp_path)
    config.coding.max_steps = 2
    with pytest.raises(CodingFailure) as caught:
        run_coding(
            state,
            scripted(
                [
                    {"tool": "command", "argv": ["python3", "test_model.py"]},
                    {"tool": "read", "path": "model.py"},
                ]
            ),
            store,
            config,
            context,
        )
    checkpoint = next((store.run_dir(state.id) / "coding").glob("*/checkpoint.json"))
    message = str(caught.value)
    assert f"coding/{checkpoint.parent.name}/checkpoint.json" in message
    assert "Last recorded failure: step 1, command" in message
    assert "exit code 1" in message
    assert "AssertionError" in message
    assert "2/2 steps" in message
    record = json.loads(checkpoint.read_text())
    assert len(record["steps"]) == 2
    assert record["steps"][0]["observation"]["result"]["status"] == "failed"


@pytest.mark.parametrize("budget", ["step", "command", "wall-clock"])
def test_budget_diagnostics_redact_bound_and_preserve_history(
    tmp_path: Path, monkeypatch, budget: str
) -> None:
    store, state, config, context = setup(tmp_path)
    config.coding.max_steps = 1 if budget == "step" else 3
    config.coding.max_commands = 1
    config.privacy.redact_patterns = ["private-project"]
    monkeypatch.setenv("DIAGNOSTIC_TEST_TOKEN", "credential-value-for-diagnostics")
    session = CodingSession(state, scripted([]), store, config, context)
    actions = [
        {
            "tool": "command",
            "argv": [
                "python3",
                "-c",
                "import sys; print('private-project credential-value-for-diagnostics ' + 'x' * 2000 + ' private-project credential-value-for-diagnostics', file=sys.stderr); sys.exit(7)",
            ],
        }
    ]
    if budget == "command":
        actions.append({"tool": "command", "argv": ["python3", "-c", "pass"]})
    base = scripted(actions)

    def call(role: str, ctx: dict[str, Any]) -> AgentOutput:
        if budget == "wall-clock":
            session.record["created_at"] = 0
        return base(role, ctx)

    session.call = call
    with pytest.raises(CodingFailure, match=f"{budget} budget exhausted") as caught:
        session.run()
    message = str(caught.value)
    assert len(message) < 1500
    assert "private-project" not in message
    assert "credential-value-for-diagnostics" not in message
    assert "[REDACTED]" in message
    assert "exit code 7" in message
    record = json.loads(session.checkpoint_path.read_text())
    assert record["commands"] == 1
    assert "x" * 2000 in record["steps"][0]["observation"]["result"]["stderr"]
    assert "private-project" in record["steps"][0]["observation"]["result"]["stderr"]


def test_wall_budget_without_prior_steps_still_locates_checkpoint(tmp_path: Path) -> None:
    store, state, config, context = setup(tmp_path)
    session = CodingSession(state, scripted([]), store, config, context)
    session.record["created_at"] = 0
    with pytest.raises(CodingFailure) as caught:
        session.run()
    assert "0/64 steps" in str(caught.value)
    assert f"coding/{session.id}/checkpoint.json" in str(caught.value)
    assert "Last recorded failure" not in str(caught.value)


def test_oversized_observation_can_be_paged_after_session_recovery(tmp_path: Path) -> None:
    from autoresearch.coding import CodingAction

    store, state, config, context = setup(tmp_path)
    config.coding.max_context_chars = 4096
    session = CodingSession(state, lambda *_: AgentOutput(summary="Unused"), store, config, context)
    observation = {"action": [{"tool": "command"}], "observation": {"stderr": "測定失敗\n" * 1000}}
    session.record["steps"] = [observation]
    session.save()
    checkpoint = (session.folder / "checkpoint.json").read_bytes()
    view = session._context()
    assert len(json.dumps(view["recent_steps"])) <= 2048
    request = view["recent_steps"][0]["history_request"]
    restored = CodingSession(
        state, lambda *_: AgentOutput(summary="Unused"), store, config, context
    )
    fragments = []
    while True:
        page = restored.observation(CodingAction.model_validate(request))
        fragments.append(page["step_json"])
        assert len(json.dumps(page)) < 2048
        assert page["sha256"] == view["recent_steps"][0]["sha256"]
        if page["next_char"] is None:
            break
        request["start_char"] = page["next_char"]
    assert json.loads("".join(fragments)) == observation
    assert (session.folder / "checkpoint.json").read_bytes() == checkpoint
    with pytest.raises(ValueError, match="one existing step"):
        restored.observation(CodingAction(tool="history", offset=100, limit=1, start_char=0))


def test_history_pages_redact_structured_and_split_secrets_before_serialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from autoresearch.coding import CodingAction
    from autoresearch.privacy import redact

    monkeypatch.setenv("TEST_HISTORY_KEY", "synthetic-boundary-value")
    store, state, config, context = setup(tmp_path)
    config.privacy.redact_patterns = ["private-pattern-value"]
    session = CodingSession(state, lambda *_: AgentOutput(summary="Unused"), store, config, context)
    step = {
        "action": [{"tool": "read"}],
        "observation": {
            "password": "private-synthetic-test-value",
            "text": "prefix synthetic-boundary-value private-pattern-value tail",
        },
    }
    session.record["steps"] = [step]
    offset = 0
    pages = []
    while True:
        page = session.observation(
            CodingAction(tool="history", offset=0, limit=1, start_char=offset, char_limit=7)
        )
        # Same final model-facing privacy pass as AgentRunner, after paging.
        pages.append(redact(page, config.privacy.redact_patterns)["step_json"])
        if page["next_char"] is None:
            break
        offset = page["next_char"]
    reconstructed = json.loads("".join(pages))
    assert reconstructed == redact(step, config.privacy.redact_patterns)
    assert session.record["steps"] == [step]
    assert page["original_sha256"] != page["sha256"]


def test_recent_history_redacts_before_bibliographic_bounds(tmp_path: Path) -> None:
    from autoresearch.contracts import Evidence

    store, state, config, context = setup(tmp_path)
    secret = "synthetic-display-test-boundary-value"  # noqa: S105 - public privacy fixture
    config.privacy.redact_patterns = [secret]
    session = CodingSession(state, lambda *_: AgentOutput(summary="Unused"), store, config, context)
    paper = Evidence(
        id="fixture",
        title="A" * 1010 + secret,
        url="https://example.org",
        retrieval={"venue": "V" * 500 + secret},
    ).model_dump()
    session.record["steps"] = [
        {"action": [{"tool": "discover"}], "observation": {"evidence": [paper]}}
    ]
    assert "synthetic" not in json.dumps(session._context()["recent_steps"])
    assert session.record["steps"][0]["observation"]["evidence"][0] == paper
