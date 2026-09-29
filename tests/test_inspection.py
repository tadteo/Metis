import pytest

from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentOutput, RunState
from autoresearch.inspection import DIMENSIONS, inspect_code
from autoresearch.store import Store


def setup(tmp_path):
    config = ResearchConfig()
    config.coding.max_steps = 6
    store = Store(tmp_path / "state")
    state = RunState(id="0123456789ab", title="Audit", objective="Trace every metric to evaluation")
    store.create(state, config)
    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text(
        "def score(prediction, label):\n    return (prediction == label).mean()\n"
    )
    return config, store, state, source


def finish(role="method_alignment", path="train.py", start=1, end=2):
    return AgentOutput(
        summary="Inspected implementation against executed evidence",
        plans=[{"tool": "finish"}],
        structured={
            "inspection_findings": [
                {
                    "dimension": dimension,
                    "path": path,
                    "start_line": start,
                    "end_line": end,
                    "conclusion": "The implementation computes measured accuracy from predictions and labels; evidence still requires independent execution.",
                }
                for dimension in DIMENSIONS[role]
            ]
        },
    )


def test_inspection_reads_large_repository_and_retains_exact_ranges(tmp_path):
    config, store, state, source = setup(tmp_path)
    (source / "large.py").write_text("# source context beyond old 2 MB limit\n" * 70000)
    seen = []

    def call(role, context):
        assert role == "inspection_step"
        seen.append(context)
        if len(seen) == 1:
            return AgentOutput(summary="Locate source", plans=[{"tool": "list", "limit": 1}])
        if len(seen) == 2:
            assert context["recent_observations"][-1]["observation"]["next_offset"] == 1
            return AgentOutput(
                summary="Read metric implementation", plans=[{"tool": "read", "path": "train.py"}]
            )
        return finish()

    result = inspect_code(
        state, "method_alignment", call, store, config, {"source_dir": str(source)}
    )
    assert result.structured["inspection"]["files_inspected"][0]["path"] == "train.py"
    assert result.structured["inspection"]["files_inspected"][0]["sha256"]
    assert len([a for a in store.artifacts(state.id) if a["kind"] == "inspection_step"]) == 3
    assert (source / "train.py").read_text().startswith("def score")


def test_empty_accept_cannot_finish_without_reading_code(tmp_path):
    config, store, state, source = setup(tmp_path)
    with pytest.raises(ValueError, match="exhausted"):
        inspect_code(
            state,
            "method_alignment",
            lambda role, context: finish(),
            store,
            config,
            {"source_dir": str(source)},
        )
    events = store.events(state.id)
    assert events[-1]["kind"] == "inspection_exhausted"


def test_cannot_cite_unread_source_lines(tmp_path):
    config, store, state, source = setup(tmp_path)

    def call(role, context):
        if context["inspection_step"] == 0:
            return AgentOutput(
                summary="Read first line", plans=[{"tool": "read", "path": "train.py", "limit": 1}]
            )
        return finish(start=1, end=2)

    with pytest.raises(ValueError, match="exhausted"):
        inspect_code(state, "method_alignment", call, store, config, {"source_dir": str(source)})


@pytest.mark.parametrize(
    "action",
    [
        {"tool": "edit", "path": "train.py", "content": "tampered"},
        {"tool": "command", "argv": ["python3", "evil.py"]},
        {"tool": "read", "path": "../secret.py"},
        {"tool": "read", "path": ".env"},
    ],
)
def test_auditor_cannot_mutate_execute_or_escape(tmp_path, action):
    config, store, state, source = setup(tmp_path)
    original = (source / "train.py").read_text()
    with pytest.raises(ValueError, match="exhausted"):
        inspect_code(
            state,
            "integrity",
            lambda role, context: AgentOutput(summary="Attempt invalid tool", plans=[action]),
            store,
            config,
            {"source_dir": str(source)},
        )
    assert (source / "train.py").read_text() == original


def test_audit_resume_reuses_finished_output_and_detects_changed_source(tmp_path):
    config, store, state, source = setup(tmp_path)
    count = 0

    def call(role, context):
        nonlocal count
        count += 1
        return (
            AgentOutput(summary="Read code", plans=[{"tool": "read", "path": "train.py"}])
            if count == 1
            else finish()
        )

    context = {"source_dir": str(source)}
    first = inspect_code(state, "method_alignment", call, store, config, context)
    second = inspect_code(state, "method_alignment", call, store, config, context)
    assert first == second
    assert count == 2
    (source / "train.py").write_text("def score(prediction, label):\n    return 1.0\n")
    with pytest.raises(ValueError, match="changed"):
        inspect_code(state, "method_alignment", call, store, config, context)


def test_symlink_source_is_rejected(tmp_path):
    config, store, state, source = setup(tmp_path)
    (source / "escape.py").symlink_to(tmp_path / "outside.py")
    with pytest.raises(Exception, match="symlink"):
        inspect_code(
            state,
            "integrity",
            lambda role, context: finish("integrity"),
            store,
            config,
            {"source_dir": str(source)},
        )


def test_search_and_history_retain_pagination(tmp_path):
    config, store, state, source = setup(tmp_path)
    seen = []

    def call(role, context):
        step = len(seen)
        seen.append(context)
        actions = [
            {"tool": "search", "query": "prediction", "limit": 1},
            {"tool": "read", "path": "train.py"},
            {"tool": "history", "offset": 0, "limit": 1},
        ]
        if step < len(actions):
            return AgentOutput(summary="Audit", plans=[actions[step]])
        assert (
            context["recent_observations"][-1]["observation"]["history"][0]["observation"]["total"]
            == 2
        )
        return finish()

    inspect_code(state, "method_alignment", call, store, config, {"source_dir": str(source)})
    assert seen[1]["recent_observations"][0]["observation"]["next_offset"] == 1


@pytest.mark.parametrize("change", ["metrics", "protocol", "objective", "new_source"])
def test_changed_scientific_inputs_require_fresh_inspection(tmp_path, change):
    from autoresearch.contracts import ExperimentResult

    config, store, state, source = setup(tmp_path)
    state.experiments = [
        ExperimentResult(id="same-id", status="completed", metrics={"accuracy": 0.5})
    ]
    calls = []

    def call(role, context):
        calls.append(context)
        return (
            AgentOutput(summary="Read", plans=[{"tool": "read", "path": "train.py"}])
            if context["inspection_step"] == 0
            else finish()
        )

    context = {"source_dir": str(source)}
    first = inspect_code(state, "method_alignment", call, store, config, context)
    if change == "metrics":
        state.experiments[0].metrics["accuracy"] = 0.9
    elif change == "protocol":
        config.project.specification = "A different immutable evaluation protocol"
    elif change == "objective":
        state.objective = "Audit a different scientific question"
    else:
        (source / "evaluate.py").write_text("raise RuntimeError('new evaluator')\n")
    second = inspect_code(state, "method_alignment", call, store, config, context)
    assert len(calls) == 4
    assert first.structured["inspection"]["session"] != second.structured["inspection"]["session"]


def test_failed_inspection_call_is_durable_and_retry_keeps_evidence(tmp_path):
    import json

    config, store, state, source = setup(tmp_path)
    context = {"source_dir": str(source)}

    def fail(role, context):
        raise RuntimeError("provider disconnected")

    with pytest.raises(RuntimeError, match="disconnected"):
        inspect_code(state, "method_alignment", fail, store, config, context)
    receipts = list(store.run_dir(state.id).glob("inspection/*/checkpoint.json"))
    assert len(receipts) == 1
    checkpoint = json.loads(receipts[0].read_text())
    assert checkpoint["failures"][0]["type"] == "RuntimeError"
    assert checkpoint["output"] is None
    calls = []

    def retry(role, context):
        calls.append(context)
        return (
            AgentOutput(summary="Read", plans=[{"tool": "read", "path": "train.py"}])
            if len(calls) == 1
            else finish()
        )

    inspect_code(state, "method_alignment", retry, store, config, context)
    assert json.loads(receipts[0].read_text())["failures"] == checkpoint["failures"]
    assert any(event["kind"] == "inspection_failure" for event in store.events(state.id))


def test_saved_run_resumes_prior_reads_after_provider_failure(tmp_path):
    import json

    config, store, state, source = setup(tmp_path)
    context = {"source_dir": str(source)}

    def interrupted(role, context):
        if context["inspection_step"] == 0:
            return AgentOutput(summary="Read", plans=[{"tool": "read", "path": "train.py"}])
        raise RuntimeError("temporary provider interruption")

    with pytest.raises(RuntimeError, match="interruption"):
        inspect_code(state, "method_alignment", interrupted, store, config, context)
    state.status = "failed"
    state.error = "temporary provider interruption"
    store.save(state)
    state = store.get_run(state.id)
    state.status, state.error = "running", ""
    observed = []

    def resumed(role, context):
        observed.append(context)
        return finish()

    inspect_code(state, "method_alignment", resumed, store, config, context)
    assert len(observed) == 1
    assert observed[0]["inspection_step"] == 1
    assert observed[0]["inspected_ranges"][0]["path"] == "train.py"
    checkpoints = list(store.run_dir(state.id).glob("inspection/*/checkpoint.json"))
    assert len(checkpoints) == 1
    assert len(json.loads(checkpoints[0].read_text())["failures"]) == 1
