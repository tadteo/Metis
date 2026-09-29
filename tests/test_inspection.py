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
