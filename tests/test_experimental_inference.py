"""Offline file-service checks using real provider transport and shared accounting."""

import fcntl
import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from autoresearch.config import ResearchConfig
from autoresearch.contracts import RunState, Usage
from autoresearch.providers import CompatibleProvider
from autoresearch.store import BudgetExceeded, Store

SPEC = importlib.util.spec_from_file_location(
    "experimental_inference", Path(__file__).parents[1] / "scripts/experimental_inference.py"
)
assert SPEC and SPEC.loader
service_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(service_module)


def setup(tmp_path, monkeypatch, *, usd=1, max_calls=10, handler=None):
    store = Store(tmp_path / "store")
    config = ResearchConfig()
    config.budget.usd, config.budget.max_calls = usd, max_calls
    config.provider.api_key_env = "FIXTURE_API_KEY"
    config.cheap_provider = config.provider.model_copy(update={"model": "cheap-fixture"})
    monkeypatch.setenv("FIXTURE_API_KEY", "fixture-not-a-real-secret")
    state = RunState(
        id="a" * 12,
        title="Public service fixture",
        objective="Test shared accounting",
        created_at=datetime.now(UTC).isoformat(),
    )
    store.create(state, config)
    requests = []

    def respond(request):
        requests.append(request)
        if handler:
            return handler(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"decision":"retry"}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(
        service_module, "CompatibleProvider", lambda cfg: CompatibleProvider(cfg, client=client)
    )
    service = service_module.Service(store, state.id)
    service.register()
    return service, requests


def request(**changes):
    return {
        "model": "reference",
        "sample": "case-1",
        "system": "Return JSON",
        "prompt": "A process timed out. Classify it.",
        "max_output_tokens": 256,
        **changes,
    }


def enqueue(service, value, workspace="coding/session/workspace"):
    queue = service.root / workspace / "metis-inference"
    queue.mkdir(parents=True, exist_ok=True)
    key = service_module.digest(value)
    (queue / (key + ".request.json")).write_text(json.dumps(value))
    return queue / (key + ".response.json")


def test_file_roundtrip_shared_usage_and_replay_across_workspaces(tmp_path, monkeypatch):
    service, calls = setup(tmp_path, monkeypatch)
    value = request()
    output = enqueue(service, value)
    service.poll()
    receipt = json.loads(output.read_text())
    assert receipt["status"] == "completed"
    assert receipt["data"] == {"decision": "retry"}
    assert "fixture-not-a-real-secret" not in output.read_text()
    assert calls[0].headers["Authorization"] == "Bearer fixture-not-a-real-secret"
    assert service.store.usage(service.run_id)["cost_usd"] == pytest.approx(0.00026)
    output.write_text('{"forged": true}')
    other = enqueue(service, value, "experiments/example")
    restarted = service_module.Service(service.store, service.run_id)
    restarted.poll()
    assert json.loads(output.read_text()) == json.loads(other.read_text()) == receipt
    assert len(calls) == 1
    assert service.store.usage(service.run_id)["model_calls_attempted"] == 1
    service.execute(request(sample="deliberate-repeat"))
    assert len(calls) == 2


@pytest.mark.parametrize("limit", ["money", "calls"])
def test_existing_agent_spend_and_call_limits_prevent_dispatch(tmp_path, monkeypatch, limit):
    service, calls = setup(tmp_path, monkeypatch, usd=0.01, max_calls=1 if limit == "calls" else 10)
    call = service.store.reserve(service.run_id, "intake", 0.009, "previous")
    service.store.settle(call, Usage(cost_usd=0.009))
    with pytest.raises(BudgetExceeded):
        service.execute(request())
    assert not calls


def test_provider_outage_one_attempt_and_estimated_charge(tmp_path, monkeypatch):
    service, calls = setup(tmp_path, monkeypatch, handler=lambda _: httpx.Response(503))
    receipt = service.execute(request())
    assert receipt["status"] == "failed"
    assert receipt["usage"]["estimated"]
    assert receipt["usage"]["cost_usd"] > 0
    assert len(calls) == 1  # Saved provider retries do not create hidden attempts.
    assert service.store.usage(service.run_id)["reserved_usd"] == 0
    service.execute(request())
    assert len(calls) == 1


def test_crash_after_send_never_reissues_uncertain_call(tmp_path, monkeypatch):
    def crash(_):
        raise KeyboardInterrupt

    service, calls = setup(tmp_path, monkeypatch, handler=crash)
    with pytest.raises(KeyboardInterrupt):
        service.execute(request())
    recovered = service_module.Service(service.store, service.run_id).execute(request())
    assert recovered["status"] == "uncertain"
    assert len(calls) == 1
    assert service.store.usage(service.run_id)["reserved_usd"] > 0


def test_crash_before_settlement_recovers_receipt_without_spending_again(tmp_path, monkeypatch):
    service, calls = setup(tmp_path, monkeypatch)
    with monkeypatch.context() as patch:
        patch.setattr(
            service, "publish_receipt", lambda _: (_ for _ in ()).throw(KeyboardInterrupt())
        )
        with pytest.raises(KeyboardInterrupt):
            service.execute(request())
    assert service.store.usage(service.run_id)["reserved_usd"] > 0
    recovered = service_module.Service(service.store, service.run_id).execute(request())
    assert recovered["status"] == "completed"
    assert len(calls) == 1
    assert service.store.usage(service.run_id)["reserved_usd"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "arbitrary-host"},
        {"endpoint": "https://example.invalid"},
        {"max_output_tokens": True},
        {"max_output_tokens": 999999},
        {"prompt": "x" * 20001},
        {"prompt": "\U0001f600" * 12000},
    ],
)
def test_invalid_requests_never_dispatch(tmp_path, monkeypatch, changes):
    service, calls = setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        service.execute(request(**changes))
    assert not calls


def test_symlink_paths_and_forged_names_never_dispatch(tmp_path, monkeypatch):
    service, calls = setup(tmp_path, monkeypatch)
    output = enqueue(service, request())
    req = output.with_name(output.name.replace("response", "request"))
    outside = tmp_path / "outside.json"
    outside.write_text(req.read_text())
    req.unlink()
    req.symlink_to(outside)
    service.poll()
    assert not calls and not output.exists()
    req.unlink()
    req.write_text(outside.read_text())
    output.symlink_to(outside)
    service.poll()
    assert outside.read_text() == req.read_text()
    # A valid request can be billed once, but the external response target is never written.
    assert len(calls) <= 1
    other = service.root / "experiments" / "escaped"
    other.parent.mkdir(exist_ok=True)
    other.symlink_to(tmp_path)
    queue = tmp_path / "metis-inference"
    queue.mkdir()
    (queue / (service_module.digest(request(sample="other")) + ".request.json")).write_text(
        json.dumps(request(sample="other"))
    )
    service.poll()
    assert len(calls) <= 1


def test_pause_and_manifest_drift_stop_new_calls(tmp_path, monkeypatch):
    service, calls = setup(tmp_path, monkeypatch)
    service.store.set_paused(service.run_id, True)
    assert service.execute(request())["status"] == "paused"
    assert not calls
    service.manifest["retries"] = 3
    with pytest.raises(ValueError, match="changed"):
        service.register()


def test_malformed_and_deep_requests_do_not_stop_polling(tmp_path, monkeypatch):
    service, calls = setup(tmp_path, monkeypatch)
    queue = service.root / "coding/session/workspace/metis-inference"
    queue.mkdir(parents=True)
    for i, text in enumerate(
        [
            '{"model":"reference","model":"cheap"}',
            "[" * 1500 + "0" + "]" * 1500,
            '"' + "x" * 40000 + '"',
            '{"x":NaN}',
        ]
    ):
        (queue / (f"{i:064x}" + ".request.json")).write_text(text)
    service.poll()
    assert not calls
    output = enqueue(service, request())
    service.poll()
    assert json.loads(output.read_text())["status"] == "completed"


def test_budget_refusal_with_unsafe_response_keeps_service_alive(tmp_path, monkeypatch):
    service, calls = setup(tmp_path, monkeypatch, usd=0.00001)
    output = enqueue(service, request())
    original = service_module.write_file

    def fail_response(root, name, content, **kwargs):
        if name.endswith(".response.json"):
            raise service_module.ExecutionError("changed path")
        return original(root, name, content, **kwargs)

    monkeypatch.setattr(service_module, "write_file", fail_response)
    service.poll()
    assert not calls and not output.exists()


def test_service_process_excludes_second_instance(tmp_path, monkeypatch):
    service, _ = setup(tmp_path, monkeypatch)
    with (service.journal / "service.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run(
            [
                sys.executable,
                str(Path(service_module.__file__)),
                service.run_id,
                "--state-dir",
                str(service.store.root),
            ],
            env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
            capture_output=True,
            text=True,
            timeout=10,
        )
    assert result.returncode != 0
    assert "BlockingIOError" in result.stderr


def test_client_waits_for_controller_after_stale_pause_response(tmp_path, monkeypatch):
    import threading

    spec = importlib.util.spec_from_file_location(
        "metis_decisions", Path(__file__).parents[1] / "scripts/metis_decisions.py"
    )
    assert spec and spec.loader
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    service, calls = setup(tmp_path, monkeypatch)
    value = request()
    output = enqueue(service, value)
    output.write_text(json.dumps({"request_id": service_module.digest(value), "status": "paused"}))
    monkeypatch.chdir(output.parent.parent)
    finished = threading.Event()

    def serve():
        while not finished.wait(0.05):
            service.poll()

    worker = threading.Thread(target=serve)
    worker.start()
    try:
        receipt = client.decide(
            value["model"],
            value["prompt"],
            sample=value["sample"],
            system=value["system"],
            max_output_tokens=256,
            timeout=5,
        )
    finally:
        finished.set()
        worker.join()
    assert receipt["status"] == "completed"
    assert len(calls) == 1
