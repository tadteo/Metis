"""Critical official-writer contract, resume, provenance and failure tests."""

from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from autoresearch.config import ResearchConfig
from autoresearch.contracts import ExperimentResult, Idea, RunState
from autoresearch.paper_orchestra import (
    UPSTREAM_REVISION,
    PaperOrchestraConfig,
    PaperOrchestraError,
    _command,
    _resolved_config,
    _usage_rows,
    materialize_raw_materials,
    verify_checkout,
)
from autoresearch.paper_orchestra_setup import extract_reference_archive
from autoresearch.paper_orchestra_worker import CallJournal, StageJournal, strict_compile
from autoresearch.store import Store
from autoresearch.writing import compose_manuscript


def research_state() -> RunState:
    return RunState(
        id="abcdefabcdef",
        title="Measured study",
        objective="Improve a real method",
        selected_idea="best",
        ideas=[Idea(id="best", title="Best", hypothesis="Mechanism")],
        experiments=[
            ExperimentResult(id="ok", status="completed", metrics={"score": 0.7}),
            ExperimentResult(id="bad", status="failed", exit_code=1, stderr="Failure"),
        ],
    )


def test_raw_materials_preserve_all_attempts_and_claim_provenance(tmp_path: Path) -> None:
    state = research_state()
    materialize_raw_materials(state, tmp_path)
    text = (tmp_path / "experimental_log.md").read_text()
    assert '"id": "bad"' in text and '"status": "failed"' in text
    assert '"score": 0.7' in text and "Repeated seeds alone" in text
    assert json.loads((tmp_path / "evidence_claims.json").read_text())[0]["experiment_id"] == "ok"
    assert (tmp_path / "idea_sparse.md").is_file()
    assert (tmp_path / "figures/info.json").is_file()


def test_live_writer_never_falls_back_when_upstream_missing(tmp_path: Path) -> None:
    config = ResearchConfig()
    store = Store(tmp_path)
    state = research_state()
    store.create(state, config)
    with pytest.raises(PaperOrchestraError, match="no reconstructed writer fallback"):
        compose_manuscript(state, store=store, config=config)


def test_checkout_rejects_wrong_revision_and_modifications(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    responses = iter([UPSTREAM_REVISION + "\n", " M methods/paper_writer.py\n"])
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: next(responses))
    with pytest.raises(PaperOrchestraError, match="clean checkout"):
        verify_checkout(tmp_path)
    responses = iter(["wrong\n", ""])
    with pytest.raises(PaperOrchestraError, match="clean checkout"):
        verify_checkout(tmp_path)


def test_stage_resume_skips_completed_work_and_rejects_corruption(tmp_path: Path) -> None:
    path = tmp_path / "outline.json"
    calls = []

    def run() -> dict[str, str]:
        calls.append("ran")
        path.write_text('{"outline": "measured"}')
        return {"phase": "outline"}

    assert StageJournal(tmp_path).run("outline", run, [path]) == {"phase": "outline"}
    assert StageJournal(tmp_path).run("outline", run, [path]) == {"phase": "outline"}
    assert len(calls) == 1
    path.write_text("corrupted")
    with pytest.raises(PaperOrchestraError, match="changed"):
        StageJournal(tmp_path).run("outline", run, [path])


def test_failed_stage_is_not_marked_complete(tmp_path: Path) -> None:
    def fail() -> None:
        raise RuntimeError("upstream failure")

    with pytest.raises(RuntimeError):
        StageJournal(tmp_path).run("literature", fail, [tmp_path / "missing"])
    assert not (tmp_path / "checkpoint.json").exists()


class Response:
    def __init__(self, data: dict[str, Any]):
        self.data = data

    def model_dump_json(self) -> str:
        return json.dumps(self.data)


def options() -> dict[str, Any]:
    return PaperOrchestraConfig(max_cost_usd=10).model_dump(mode="json")


def test_api_usage_measured_cache_and_failed_attempts_persist(tmp_path: Path) -> None:
    ledger = CallJournal(tmp_path, options())
    calls = []

    def request() -> Response:
        calls.append(True)
        return Response(
            {
                "text": "answer",
                "usage_metadata": {
                    "prompt_token_count": 10,
                    "candidates_token_count": 20,
                    "thoughts_token_count": 3,
                },
            }
        )

    price = {"input_per_million": 2, "output_per_million": 12, "max_output_tokens": 100}
    for _ in range(2):
        CallJournal(tmp_path, options()).invoke(
            "google", "native", {"prompt": "test"}, request, Response, price
        )
    assert len(calls) == 1
    rows = _usage_rows(tmp_path / "usage.jsonl")
    assert len(rows) == 1 and rows[0]["output_tokens"] == 23
    assert rows[0]["cost_usd"] == pytest.approx((10 * 2 + 23 * 12) / 1e6)
    assert rows[0]["estimated"] is False

    def fail() -> Any:
        raise TimeoutError("network timeout")

    with pytest.raises(TimeoutError):
        ledger.invoke("google", "native", {"prompt": "new"}, fail, Response)
    rows = _usage_rows(tmp_path / "usage.jsonl")
    assert len(rows) == 2 and rows[1]["status"] == "failed"
    assert rows[1]["estimated"] and rows[1]["cost_usd"] == 1


def test_api_budget_exhaustion_prevents_request(tmp_path: Path) -> None:
    ledger = CallJournal(tmp_path, {**options(), "max_cost_usd": 0.1})
    with pytest.raises(PaperOrchestraError, match="budget exhausted"):
        ledger.invoke("google", "unpriced", {}, lambda: pytest.fail("must not call API"), Response)


def test_compile_nonzero_cannot_pass_despite_pdf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def command(*args: Any, **kwargs: Any) -> Any:
        (tmp_path / "paper.pdf").write_bytes(b"%PDF-stale")
        return SimpleNamespace(returncode=1, stdout="fatal compiler error", stderr="error")

    monkeypatch.setattr(subprocess, "run", command)
    with pytest.raises(PaperOrchestraError, match="compile failed"):
        strict_compile(tmp_path)(str(tmp_path), str(tmp_path / "final.pdf"), "paper")
    assert not (tmp_path / "paper.pdf").exists()
    assert not (tmp_path / "final.pdf").exists()
    record = json.loads((tmp_path / "compile-diagnostics.jsonl").read_text())
    assert record["exit_code"] == 1 and "-no-shell-escape" in record["argv"]


def test_writer_container_mounts_no_home_or_docker_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UNRELATED_API_KEY", "must-not-pass")
    config = _resolved_config(ResearchConfig())
    argv, env = _command(tmp_path, tmp_path / "upstream", config)
    assert "UNRELATED_API_KEY" not in env
    assert "--read-only" in argv and "--cap-drop=ALL" in argv
    assert not any("docker.sock" in item for item in argv)
    assert all("must-not-pass" not in item for item in argv)


def test_configured_provider_inherited_for_writing_roles() -> None:
    config = ResearchConfig()
    resolved = _resolved_config(config)
    assert (
        resolved["compatible_models"][resolved["writer_model_name"]]["model"]
        == config.provider.model
    )
    assert resolved["literature_model_name"].startswith("gemini")
    assert resolved["max_reflections"] == 3


@pytest.mark.parametrize("entry", ["../escape.txt", "/escape.txt", "..\\escape.txt"])
def test_plotting_archive_rejects_traversal(tmp_path: Path, entry: str) -> None:
    archive = tmp_path / "input.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(entry, "bad")
    with pytest.raises(PaperOrchestraError, match="Unsafe path"):
        extract_reference_archive(archive, tmp_path / "target")


def test_plotting_archive_rejects_symlink(tmp_path: Path) -> None:
    archive = tmp_path / "input.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        info = zipfile.ZipInfo("link")
        info.external_attr = 0o120777 << 16
        bundle.writestr(info, "../../secret")
    with pytest.raises(PaperOrchestraError, match="Symlink"):
        extract_reference_archive(archive, tmp_path / "target")


def test_parent_settlement_recovers_once_after_crash(tmp_path: Path) -> None:
    from autoresearch.paper_orchestra import _write_json, settle_worker_accounting

    config = ResearchConfig()
    state = research_state()
    store = Store(tmp_path / "store")
    store.create(state, config)
    base = tmp_path / "job"
    base.mkdir()
    reservation = store.reserve(state.id, "paper_orchestra", 2, "request")
    _write_json(
        base / "accounting.json",
        {"status": "reserved", "reservation": reservation, "previous_ids": [], "started_at": 0},
    )
    (base / "usage.jsonl").write_text(
        json.dumps(
            {
                "id": "child",
                "model": "native",
                "provider": "google",
                "cost_usd": 0.5,
                "input_tokens": 12,
                "output_tokens": 3,
            }
        )
        + "\n"
    )
    settle_worker_accounting(store, state, base)
    settle_worker_accounting(store, state, base)
    assert store.usage(state.id)["cost_usd"] == 0.5
    assert store.usage(state.id)["reserved_usd"] == 0
    assert len([e for e in store.events(state.id) if e["kind"] == "paper_orchestra_api_call"]) == 1


def test_subordinate_call_count_limit_is_enforced(tmp_path: Path) -> None:
    ledger = CallJournal(tmp_path, {**options(), "max_calls_total": 0})
    with pytest.raises(PaperOrchestraError, match="call limit"):
        ledger.invoke("google", "native", {}, lambda: pytest.fail("must not call API"), Response)


def test_upstream_secret_print_is_redacted() -> None:
    from io import StringIO

    from autoresearch.paper_orchestra_worker import RedactedStream

    output = StringIO()
    RedactedStream(output, ["sensitive-token"]).write("Using S2 API Key: sensitive-token\n")
    assert output.getvalue() == "Using S2 API Key: [REDACTED]\n"


def test_plot_executor_cannot_overwrite_host_through_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from autoresearch.paper_orchestra import _serve_plot_requests

    victim = tmp_path / "usage.jsonl"
    victim.write_text("immutable accounting")
    folder = tmp_path / "plot_requests" / ("a" * 64)
    folder.mkdir(parents=True)
    (folder / "ready.json").write_text("{}")
    (folder / "code.txt").write_text("# plot")

    def hostile_plot(*args: Any, **kwargs: Any) -> Any:
        if args[0][1] == "rm":
            return SimpleNamespace(returncode=0, stdout="", stderr="", timed_out=False)
        (folder / "stdout.log").symlink_to(victim)
        (folder / "result.json.tmp").symlink_to(victim)
        return SimpleNamespace(returncode=0, stdout="corruption", stderr="", timed_out=False)

    monkeypatch.setattr("autoresearch.paper_orchestra._run", hostile_plot)
    with pytest.raises(PaperOrchestraError, match="symlink"):
        _serve_plot_requests(tmp_path, options())
    assert victim.read_text() == "immutable accounting"


def test_atomic_json_ignores_attacker_named_temporary_file(tmp_path: Path) -> None:
    from autoresearch.paper_orchestra import _write_json

    victim = tmp_path / "private"
    victim.write_text("secret")
    (tmp_path / "result.json.tmp").symlink_to(victim)
    _write_json(tmp_path / "result.json", {"exit_code": 0})
    assert victim.read_text() == "secret"
    assert json.loads((tmp_path / "result.json").read_text()) == {"exit_code": 0}


def test_plot_timeout_forces_named_container_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from autoresearch.paper_orchestra import _serve_plot_requests

    folder = tmp_path / "plot_requests" / ("b" * 64)
    folder.mkdir(parents=True)
    (folder / "ready.json").write_text("{}")
    (folder / "code.txt").write_text("# plot")
    calls = []

    def run(argv: list[str], **kwargs: Any) -> Any:
        calls.append((argv, kwargs))
        return SimpleNamespace(
            returncode=-15 if argv[1] == "run" else 0,
            stdout="bounded",
            stderr="",
            timed_out=argv[1] == "run",
        )

    monkeypatch.setattr("autoresearch.paper_orchestra._run", run)
    _serve_plot_requests(tmp_path, options())
    assert calls[0][1]["limit"] == 1_000_000
    name = calls[0][0][calls[0][0].index("--name") + 1]
    assert calls[1][0] == ["docker", "rm", "--force", name]
    assert json.loads((folder / "result.json").read_text())["exit_code"] is None


def test_conservative_price_stays_marked_estimated(tmp_path: Path) -> None:
    ledger = CallJournal(tmp_path, options())
    price = {
        "input_per_million": 4,
        "output_per_million": 12,
        "max_output_tokens": 100,
        "conservative": True,
    }
    ledger.invoke(
        "xai",
        "configured-model",
        {},
        lambda: Response({"usage": {"prompt_tokens": 1, "completion_tokens": 2}}),
        Response,
        price,
    )
    assert _usage_rows(tmp_path / "usage.jsonl")[0]["estimated"] is True


def test_generated_plot_cannot_forge_host_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading
    import time

    from autoresearch.paper_orchestra import _serve_plot_requests
    from autoresearch.paper_orchestra_worker import isolated_plot

    outcomes = []

    def consumer() -> None:
        try:
            isolated_plot(tmp_path)("# malicious plotting code")
            outcomes.append("success")
        except PaperOrchestraError:
            outcomes.append("failed")

    thread = threading.Thread(target=consumer)
    thread.start()
    for _ in range(100):
        if list((tmp_path / "plot_requests").glob("*/ready.json")):
            break
        time.sleep(0.01)

    def hostile_code(argv: list[str], **kwargs: Any) -> Any:
        if argv[1] == "rm":
            return SimpleNamespace(returncode=0, stdout="", stderr="", timed_out=False)
        workload = kwargs["cwd"]
        (workload / "image.jpg").write_bytes(b"fake image")
        (workload / "result.json").write_text('{"exit_code": 0}')
        # The consumer must continue waiting for the host-owned control record.
        time.sleep(0.25)
        assert not outcomes
        assert "source=" + str(workload) + ",target=/plot" in " ".join(argv)
        return SimpleNamespace(returncode=7, stdout="", stderr="failed", timed_out=False)

    monkeypatch.setattr("autoresearch.paper_orchestra._run", hostile_code)
    _serve_plot_requests(tmp_path, options())
    thread.join(timeout=2)
    assert outcomes == ["failed"]
