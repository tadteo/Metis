"""Legacy adoption must not orphan specialist execution or uncertain billing."""

import json

import pytest

from autoresearch.config import ResearchConfig
from autoresearch.contracts import RunState
from autoresearch.legacy import assert_no_pending_work
from autoresearch.store import Store


class JournalStore(Store):
    # This narrow public protocol is supplied by the integrated Store accounting change.
    def outstanding_calls(self, run_id):
        return getattr(self, "pending_calls", [])


def fixture(tmp_path):
    store = JournalStore(tmp_path)
    state = RunState(id="abcdef123456", title="Migration fixture", objective="Retain every attempt")
    store.create(state, ResearchConfig(mode="demo"))
    return store, state


def write(store, run_id, relative, record):
    path = store.run_dir(run_id) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record))
    return path


def test_legacy_without_specialist_work_or_reservations_is_ready(tmp_path):
    store, state = fixture(tmp_path)
    assert_no_pending_work(store, state.id)


@pytest.mark.parametrize("reserved", [0, 1])
def test_unsettled_calls_block_even_when_the_reserved_price_is_zero(tmp_path, reserved):
    store, state = fixture(tmp_path)
    store.pending_calls = [
        {"id": "uncertain-call", "role": "limitations", "reserved": reserved, "status": "reserved"}
    ]
    with pytest.raises(ValueError, match="model-call reservations"):
        assert_no_pending_work(store, state.id)


@pytest.mark.parametrize("pending", [None, {"job_id": "remote-job"}, {"started": True}])
def test_incomplete_coding_blocks_without_top_level_pending_experiment(tmp_path, pending):
    store, state = fixture(tmp_path)
    path = write(
        store,
        state.id,
        "coding/session/checkpoint.json",
        {"schema_version": 1, "pending": pending, "completed": None},
    )
    before = path.read_bytes()
    with pytest.raises(ValueError, match="coding"):
        assert_no_pending_work(store, state.id)
    assert path.read_bytes() == before
    assert store.get_run(state.id).model_dump() == state.model_dump()


def test_completed_coding_and_inspection_journals_are_preserved_and_accepted(tmp_path):
    store, state = fixture(tmp_path)
    output = {"summary": "Completed local checks; scientific evaluation remains independent"}
    write(
        store,
        state.id,
        "coding/session/checkpoint.json",
        {
            "schema_version": 1,
            "completed": output,
            "pending": {"output": {"plans": [{"tool": "finish"}]}},
        },
    )
    write(
        store,
        state.id,
        "inspection/session/checkpoint.json",
        {"schema_version": 1, "output": output},
    )
    assert_no_pending_work(store, state.id)


@pytest.mark.parametrize(
    "pending",
    [{"job_id": "unreconciled"}, {"started": True}, {"output": {"plans": [{"tool": "command"}]}}],
)
def test_completion_does_not_hide_an_unreconciled_coding_command(tmp_path, pending):
    store, state = fixture(tmp_path)
    write(
        store,
        state.id,
        "coding/session/checkpoint.json",
        {"schema_version": 1, "completed": {"summary": "Claimed completion"}, "pending": pending},
    )
    with pytest.raises(ValueError, match="coding"):
        assert_no_pending_work(store, state.id)


def test_unfinished_independent_inspection_cannot_be_silently_restarted(tmp_path):
    store, state = fixture(tmp_path)
    write(
        store,
        state.id,
        "inspection/session/checkpoint.json",
        {
            "schema_version": 1,
            "history": [{"summary": "Already paid investigation"}],
            "output": None,
        },
    )
    with pytest.raises(ValueError, match="inspection"):
        assert_no_pending_work(store, state.id)


@pytest.mark.parametrize("completed,accounting", [(False, "settled"), (True, "reserved")])
def test_writer_failure_or_completion_does_not_hide_pending_work(tmp_path, completed, accounting):
    store, state = fixture(tmp_path)
    write(
        store,
        state.id,
        "paper_orchestra/session/accounting.json",
        {"status": accounting, "pid": 99999999},
    )
    write(
        store,
        state.id,
        "paper_orchestra/session/failure.json",
        {"error": "Prior failure preserved"},
    )
    if completed:
        write(
            store,
            state.id,
            "paper_orchestra/session/completed.json",
            {"schema_version": 1, "pdf_sha256": "a" * 64, "source_sha256": "b" * 64},
        )
    with pytest.raises(ValueError, match="writer"):
        assert_no_pending_work(store, state.id)


def test_completed_writer_with_settled_accounting_is_ready(tmp_path):
    store, state = fixture(tmp_path)
    write(store, state.id, "paper_orchestra/session/accounting.json", {"status": "settled"})
    write(
        store,
        state.id,
        "paper_orchestra/session/completed.json",
        {"schema_version": 1, "pdf_sha256": "a" * 64, "source_sha256": "b" * 64},
    )
    assert_no_pending_work(store, state.id)


@pytest.mark.parametrize(
    "content",
    [
        "not JSON",
        "[]",
        '{"schema_version":1,"schema_version":2}',
        '{"schema_version":1,"completed":{}}',
    ],
)
def test_unknown_or_malformed_coding_journal_blocks_migration(tmp_path, content):
    store, state = fixture(tmp_path)
    path = write(store, state.id, "coding/session/checkpoint.json", {})
    path.write_text(content)
    with pytest.raises(ValueError, match="coding"):
        assert_no_pending_work(store, state.id)


@pytest.mark.parametrize("level", ["family", "session", "checkpoint"])
def test_journal_symlinks_are_rejected_without_touching_the_target(tmp_path, level):
    store, state = fixture(tmp_path / "store")
    target = tmp_path / "outside"
    target.mkdir()
    secret = target / "checkpoint.json"
    secret.write_text('{"private": "must stay untouched"}')
    family = store.run_dir(state.id) / "coding"
    if level == "family":
        family.symlink_to(target, target_is_directory=True)
    else:
        family.mkdir()
        session = family / "session"
        if level == "session":
            session.symlink_to(target, target_is_directory=True)
        else:
            session.mkdir()
            (session / "checkpoint.json").symlink_to(secret)
    with pytest.raises(ValueError, match="unsafe"):
        assert_no_pending_work(store, state.id)
    assert secret.read_text() == '{"private": "must stay untouched"}'


@pytest.mark.parametrize("plans", [7, None, {}, "finish"])
def test_malformed_pending_plans_fail_with_actionable_error(tmp_path, plans):
    store, state = fixture(tmp_path)
    write(
        store,
        state.id,
        "coding/session/checkpoint.json",
        {
            "schema_version": 1,
            "completed": {"summary": "Claimed completion"},
            "pending": {"output": {"plans": plans}},
        },
    )
    with pytest.raises(ValueError, match="coding action"):
        assert_no_pending_work(store, state.id)


def test_parent_symlink_swap_is_refused_before_reading_journal(tmp_path, monkeypatch):
    import autoresearch.legacy as legacy

    store, state = fixture(tmp_path / "store")
    checkpoint = write(
        store,
        state.id,
        "coding/session/checkpoint.json",
        {
            "schema_version": 1,
            "completed": {"summary": "Finished"},
            "pending": None,
        },
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "checkpoint.json"
    secret.write_text("not a checkpoint; must not be read")
    original = legacy.parent_descriptor

    def swapped(root, relative):
        checkpoint.parent.rename(checkpoint.parent.with_name("saved-session"))
        checkpoint.parent.symlink_to(outside, target_is_directory=True)
        return original(root, relative)

    monkeypatch.setattr(legacy, "parent_descriptor", swapped)
    with pytest.raises(ValueError, match="unsafe"):
        assert_no_pending_work(store, state.id)
    assert secret.read_text() == "not a checkpoint; must not be read"
