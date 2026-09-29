"""Upstream-style swallowed transport errors cannot certify completed writing stages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autoresearch.paper_orchestra import PaperOrchestraConfig, PaperOrchestraError
from autoresearch.paper_orchestra_worker import CallJournal, StageJournal


class Response:
    def __init__(self, data: dict[str, Any]):
        self.data = data

    def model_dump_json(self) -> str:
        return json.dumps(self.data)


def options(**overrides: Any) -> dict[str, Any]:
    return PaperOrchestraConfig(max_cost_usd=10).model_dump(mode="json") | overrides


def test_swallowed_budget_refusal_is_recorded_and_blocks_checkpoint(tmp_path: Path) -> None:
    calls = CallJournal(tmp_path, options(max_cost_usd=0.1))
    output = tmp_path / "review.json"

    def upstream() -> None:
        try:
            calls.invoke(
                "google",
                "native",
                {"prompt": "review"},
                lambda: pytest.fail("refused request must not reach network"),
                Response,
            )
        except PaperOrchestraError:
            output.write_text('{"Error": "budget refused"}')

    with pytest.raises(PaperOrchestraError, match="unresolved"):
        StageJournal(tmp_path).run("reflection", upstream, [output])
    assert not (tmp_path / "checkpoint.json").exists()
    rows = [json.loads(line) for line in (tmp_path / "requests.jsonl").read_text().splitlines()]
    assert rows[-1]["status"] == "failed" and rows[-1]["stage"] == "reflection"


def test_swallowed_failure_resumes_same_stage_after_transport_recovers(tmp_path: Path) -> None:
    output = tmp_path / "review.json"
    attempts = []

    def upstream() -> None:
        calls = CallJournal(tmp_path, options())

        def transport() -> Response:
            attempts.append(True)
            if len(attempts) == 1:
                raise TimeoutError("synthetic interruption")
            return Response({"text": "reviewed"})

        try:
            result = calls.invoke("google", "native", {"prompt": "review"}, transport, Response)
            output.write_text(result.model_dump_json())
        except TimeoutError:
            output.write_text('{"Error": "network failure"}')

    with pytest.raises(PaperOrchestraError, match="unresolved"):
        StageJournal(tmp_path).run("reflection", upstream, [output])
    StageJournal(tmp_path).run("reflection", upstream, [output])
    assert len(attempts) == 2
    StageJournal(tmp_path).run("reflection", lambda: pytest.fail("already completed"), [output])
    assert json.loads(output.read_text())["text"] == "reviewed"


def test_earlier_success_does_not_resolve_later_identical_failure(tmp_path: Path) -> None:
    calls = CallJournal(tmp_path, options())
    output = tmp_path / "reviews.json"

    def upstream() -> None:
        calls.invoke(
            "google",
            "native",
            {"prompt": "same ensemble input"},
            lambda: Response({"text": "first reviewer"}),
            Response,
        )
        try:
            calls.invoke(
                "google",
                "native",
                {"prompt": "same ensemble input"},
                lambda: (_ for _ in ()).throw(TimeoutError("second reviewer failed")),
                Response,
            )
        except TimeoutError:
            output.write_text('{"review": "only first reviewer"}')

    with pytest.raises(PaperOrchestraError, match="unresolved"):
        StageJournal(tmp_path).run("reflection", upstream, [output])
    assert not (tmp_path / "checkpoint.json").exists()


def test_adapter_error_before_billing_cannot_complete_stage(tmp_path: Path) -> None:
    from autoresearch.paper_orchestra_worker import Transports

    transport = Transports(CallJournal(tmp_path, options()))
    output = tmp_path / "review.json"

    def upstream() -> None:
        try:
            transport.openai(model="unconfigured", messages=[])
        except PaperOrchestraError:
            output.write_text('{"Error": "adapter misconfigured"}')

    with pytest.raises(PaperOrchestraError, match="unresolved"):
        StageJournal(tmp_path).run("reflection", upstream, [output])
    assert not (tmp_path / "usage.jsonl").exists()
    assert '"status": "failed"' in (tmp_path / "requests.jsonl").read_text()


def test_nested_executor_failure_keeps_stage_identity(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from autoresearch.paper_orchestra_worker import propagated_stage_context

    output = tmp_path / "literature.json"
    calls = CallJournal(tmp_path, options(max_cost_usd=0.1))

    def nested() -> None:
        try:
            calls.invoke(
                "google",
                "native",
                {"prompt": "nested discovery"},
                lambda: pytest.fail("blocked before send"),
                Response,
            )
        except PaperOrchestraError:
            pass

    def upstream() -> None:
        with ThreadPoolExecutor() as outer:

            def middle() -> None:
                with ThreadPoolExecutor() as inner:
                    inner.submit(nested).result()

            outer.submit(middle).result()
        output.write_text('{"citations": []}')

    original_submit = ThreadPoolExecutor.submit
    with propagated_stage_context(), pytest.raises(PaperOrchestraError, match="unresolved"):
        StageJournal(tmp_path).run("literature", upstream, [output])
    assert ThreadPoolExecutor.submit is original_submit
    receipts = [json.loads(line) for line in (tmp_path / "requests.jsonl").read_text().splitlines()]
    assert {row["stage"] for row in receipts} == {"literature"}


def test_other_stage_success_cannot_resolve_failed_request(tmp_path: Path) -> None:
    calls = CallJournal(tmp_path, options())
    output = tmp_path / "output.json"

    def failed() -> None:
        try:
            calls.invoke(
                "google",
                "native",
                {"prompt": "identical"},
                lambda: (_ for _ in ()).throw(TimeoutError("failure")),
                Response,
            )
        except TimeoutError:
            output.write_text("{}")

    with pytest.raises(PaperOrchestraError, match="unresolved"):
        StageJournal(tmp_path).run("literature", failed, [output])

    def succeeded() -> None:
        calls.invoke(
            "google",
            "native",
            {"prompt": "identical"},
            lambda: Response({"text": "succeeded elsewhere"}),
            Response,
        )
        output.write_text("{}")

    StageJournal(tmp_path).run("plotting", succeeded, [output])
    with pytest.raises(PaperOrchestraError, match="unresolved"):
        StageJournal(tmp_path).run("literature", lambda: None, [output])


def test_poisoned_checkpoint_reexecutes_stage_and_invalidates_dependents(tmp_path: Path) -> None:
    output = tmp_path / "review.json"
    output.write_text("{}")
    journal = StageJournal(tmp_path)
    journal.run("literature", lambda: None, [output])
    journal.run("sections", lambda: None, [output])
    calls = CallJournal(tmp_path, options(max_cost_usd=0.1))

    def upstream() -> None:
        try:
            calls.invoke(
                "google",
                "native",
                {"prompt": "retrieval"},
                lambda: pytest.fail("blocked"),
                Response,
            )
        except PaperOrchestraError:
            pass

    # Model the old worker's ordering: its checkpoint was written before error validation.
    before = (tmp_path / "checkpoint.json").read_text()
    (tmp_path / "checkpoint.json").unlink()
    with pytest.raises(PaperOrchestraError, match="unresolved"):
        StageJournal(tmp_path).run("literature", upstream, [output])
    (tmp_path / "checkpoint.json").write_text(before)
    calls = CallJournal(tmp_path, options())

    def recover() -> None:
        calls.invoke(
            "google",
            "native",
            {"prompt": "retrieval"},
            lambda: Response({"text": "retrieved"}),
            Response,
        )
        output.write_text('{"retrieved": true}')

    StageJournal(tmp_path).run("literature", recover, [output])
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert set(checkpoint["stages"]) == {"literature"}
    assert (tmp_path / "checkpoint-invalidations.jsonl").is_file()
    assert '"status": "failed"' in (tmp_path / "requests.jsonl").read_text()


def test_worker_lock_prevents_second_spender_and_records_terminal_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from autoresearch import paper_orchestra_worker as worker

    def execute_once(base: Path, upstream: Path) -> None:
        status = json.loads((base / "worker-status.json").read_text())
        assert status["status"] == "running" and status["pid"] > 0
        with pytest.raises(PaperOrchestraError, match="owns this job"):
            worker.execute(base, upstream)

    monkeypatch.setattr(worker, "_execute", execute_once)
    worker.execute(tmp_path, tmp_path)
    assert json.loads((tmp_path / "worker-status.json").read_text())["status"] == "completed"

    def failure(*args: Any) -> None:
        raise RuntimeError("synthetic worker failure")

    monkeypatch.setattr(worker, "_execute", failure)
    with pytest.raises(RuntimeError, match="synthetic"):
        worker.execute(tmp_path, tmp_path)
    status = json.loads((tmp_path / "worker-status.json").read_text())
    assert status["status"] == "failed" and status["error_type"] == "RuntimeError"


def test_actual_pinned_refinement_agent_recovers_after_budget_refusal(tmp_path: Path) -> None:
    """Opt-in SDK fixture smoke; imports the real agent, rendering and parsing code."""
    import os
    import subprocess
    import sys

    upstream = os.environ.get("AUTORESEARCH_UPSTREAM_FIXTURE")
    if not upstream:
        pytest.skip("Set AUTORESEARCH_UPSTREAM_FIXTURE to the pinned official checkout")
    script = r"""
import json, os, sys, time
from pathlib import Path
from types import SimpleNamespace
import httpx
import requests
import pymupdf
from google.genai import types
from autoresearch.paper_orchestra import PaperOrchestraConfig, PaperOrchestraError, verify_checkout
from autoresearch.paper_orchestra_worker import CallJournal, StageJournal, Transports

def forbidden_network(*args, **kwargs):
    raise AssertionError("This smoke test must never access a live service")
httpx.Client.send = forbidden_network
requests.Session.request = forbidden_network
upstream, base = Path(sys.argv[1]), Path(sys.argv[2])
verify_checkout(upstream)
os.environ['GEMINI_API_KEY'] = 'public-fixture-key'
options = PaperOrchestraConfig(max_cost_usd=0.1).model_dump(mode='json')
journal = CallJournal(base, options)
transports = Transports(journal)
transports.install()
sent = []
def sdk_response(**kwargs):
    sent.append(kwargs)
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role='model', parts=[types.Part(
            text=json.dumps({'figure_and_tables': {}, 'other_issues': []}))]))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=12, candidates_token_count=8))
transports.native_client = lambda **kwargs: SimpleNamespace(models=SimpleNamespace(generate_content=sdk_response))
sys.path.insert(0, str(upstream))
from methods.agents.content_refinement_agent import ContentRefinementAgent
time.sleep = lambda _: None
for name in ['log.md', 'guidelines.md', 'citations.json']:
    (base/name).write_text('{}')
with pymupdf.open() as pdf:
    page = pdf.new_page()
    page.insert_text((72,72), 'Synthetic fixture. No scientific measurements or evaluation.')
    pdf.save(base/'paper.pdf')
agent = ContentRefinementAgent(str(base/'log.md'), str(base/'citations.json'),
    str(base/'guidelines.md'), model_name='fixture-native', work_dir=str(base/'reflection'))
output = base/'format-review.json'
def upstream_action():
    result = agent._get_formatting_review(str(base/'paper.pdf'), 'fmt_loop_1')
    output.write_text(json.dumps(result))
try:
    StageJournal(base).run('reflection', upstream_action, [output])
except PaperOrchestraError as error:
    assert 'unresolved' in str(error)
else:
    raise AssertionError('Upstream swallowed budget refusal incorrectly completed the stage')
assert not sent and not (base/'checkpoint.json').exists()
options['max_cost_usd'] = 5
StageJournal(base).run('reflection', upstream_action, [output])
assert len(sent) == 1
assert json.loads(output.read_text()) == {'figure_and_tables': {}, 'other_issues': []}
rows = [json.loads(line) for line in (base/'requests.jsonl').read_text().splitlines()]
assert sum(row['status'] == 'failed' for row in rows) == 5
assert rows[-1]['status'] == 'completed'
print('REAL_UPSTREAM_RECOVERY_PASSED')
"""
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": str(tmp_path),
    }
    result = subprocess.run(
        [sys.executable, "-c", script, upstream, str(tmp_path)],
        env=environment,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "REAL_UPSTREAM_RECOVERY_PASSED" in result.stdout
