"""Real HTTP boundary tests: the local console is not a cross-origin control API."""

from __future__ import annotations

import http.client
import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from autoresearch.contracts import ExperimentSpec
from autoresearch.engine import Engine
from autoresearch.store import Store
from autoresearch.web import MAX_BODY_BYTES, ResearchServer


class FakeRemoteManager:
    """Exercise HTTP routing without SSH processes, credentials or user configuration."""

    def __init__(self, root: Path):
        self.root = root
        self.saved: list[dict[str, Any]] = []
        self.actions: list[tuple[str, str]] = []
        self.answers: list[tuple[str, str]] = []
        self.closed = 0

    def hosts(self) -> list[str]:
        return ["test-cluster"]

    def profiles(self) -> list[dict[str, Any]]:
        return self.saved

    def save_profile(self, profile: Any) -> dict[str, Any]:
        result: dict[str, Any] = profile.model_dump(mode="json")
        self.saved.append(result)
        return result

    def _action(self, action: str, name: str) -> dict[str, Any]:
        self.actions.append((action, name))
        return {"status": "connected" if action == "connect" else action, "host": "test-cluster"}

    def probe(self, name: str) -> dict[str, Any]:
        return self._action("probe", name)

    def install(self, name: str) -> dict[str, Any]:
        return self._action("install", name)

    def connect(self, name: str) -> dict[str, Any]:
        return self._action("connect", name)

    def disconnect(self, name: str) -> dict[str, Any]:
        return self._action("disconnect", name)

    def status(self, name: str) -> dict[str, Any]:
        return self._action("status", name)

    def authenticate(self, name: str) -> dict[str, Any]:
        self.actions.append(("authenticate", name))
        return self.authentication("session-one")

    def authentication(self, session_id: str) -> dict[str, Any]:
        return {"session_id": session_id, "status": "authenticating", "output": "MFA code: "}

    def answer_authentication(self, session_id: str, answer: str) -> dict[str, Any]:
        self.answers.append((session_id, answer))
        return {"session_id": session_id, "status": "authenticated", "output": ""}

    def cancel_authentication(self, session_id: str) -> dict[str, Any]:
        return {"session_id": session_id, "status": "cancelled", "output": ""}

    def close(self) -> None:
        self.closed += 1


@pytest.fixture(autouse=True)
def offline_remote_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("autoresearch.web._remote_manager", FakeRemoteManager)


@pytest.fixture
def server(tmp_path: Path) -> Iterator[ResearchServer]:
    instance = ResearchServer(Store(tmp_path / "private"), port=0)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)


def request(
    server: ResearchServer,
    method: str = "GET",
    path: str = "/api/runs",
    body: dict[str, Any] | None = None,
    *,
    authenticated: bool = True,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any, dict[str, str]]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    request_headers = {"Content-Type": "application/json"}
    if authenticated:
        request_headers["Authorization"] = f"Bearer {server.token}"
    request_headers.update(headers or {})
    connection.request(
        method, path, body=None if body is None else json.dumps(body), headers=request_headers
    )
    response = connection.getresponse()
    raw = response.read()
    content = (
        json.loads(raw) if "application/json" in response.getheader("Content-Type", "") else raw
    )
    result = response.status, content, dict(response.getheaders())
    connection.close()
    return result


def test_local_console_bootstrap_and_security_headers(server: ResearchServer) -> None:
    status, html, headers = request(server, path="/", authenticated=False)
    assert status == 200
    assert b"Research console" in html
    assert headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    status, bootstrap, _ = request(server, path="/api/bootstrap", authenticated=False)
    assert status == 200
    assert bootstrap["token"] == server.token
    assert "integrity" in bootstrap["stages"]
    assert server.token.encode() not in html


@pytest.mark.parametrize("path", ["/", "/api/bootstrap", "/api/runs"])
def test_dns_rebinding_hosts_are_denied(server: ResearchServer, path: str) -> None:
    status, _, _ = request(server, path=path, headers={"Host": "attacker.example:8765"})
    assert status == 403


@pytest.mark.parametrize(
    "headers",
    [{"Origin": "https://attacker.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}],
)
def test_cross_origin_requests_are_denied(server: ResearchServer, headers: dict[str, str]) -> None:
    assert request(server, path="/api/bootstrap", authenticated=False, headers=headers)[0] == 403
    assert (
        request(server, "POST", "/api/runs", {"title": "No", "objective": "No"}, headers=headers)[0]
        == 403
    )
    assert server.store.list_runs() == []


def test_api_requires_bearer_token_for_reads_and_mutations(server: ResearchServer) -> None:
    assert request(server, authenticated=False)[0] == 401
    assert request(server, "POST", body={}, authenticated=False)[0] == 401
    assert request(server, headers={"Authorization": "Bearer invalid"})[0] == 401
    assert request(server)[0] == 200


def test_run_creation_inspection_intervention_and_events(server: ResearchServer) -> None:
    status, created, _ = request(
        server,
        "POST",
        "/api/runs",
        {"title": "A scientific question", "objective": "Test a hypothesis.", "demo": True},
    )
    assert status == 201
    run_id = created["run"]["id"]
    assert request(server)[1]["runs"][0]["id"] == run_id
    status, detail, _ = request(server, path=f"/api/runs/{run_id}")
    assert status == 200
    assert detail["config"]["mode"] == "demo"
    assert detail["working"] is False
    status, _, _ = request(
        server, "POST", f"/api/runs/{run_id}/intervene", {"note": "Check deterministic seeds."}
    )
    assert status == 200
    history = request(server, path=f"/api/runs/{run_id}/events")[1]["events"]
    assert history
    assert (
        request(server, path=f"/api/runs/{run_id}/events?after={history[-1]['seq']}")[1]["events"]
        == []
    )
    assert request(server, "POST", f"/api/runs/{run_id}/pause", {})[0] == 202


def test_invalid_input_cannot_create_runs_or_escape_asset_directory(server: ResearchServer) -> None:
    assert request(server, "POST", "/api/runs", {"title": "", "objective": "x"})[0] == 400
    assert (
        request(server, "POST", "/api/runs", {"title": "x", "objective": "x", "demo": "yes"})[0]
        == 400
    )
    assert request(server, path="/../../config.py")[0] == 400
    assert request(server, path="/api/runs/%2e%2e")[0] == 400
    assert request(server, path="/api/runs/missing")[0] in {400, 404}
    assert (
        request(
            server, "POST", "/api/runs", {}, headers={"Content-Length": str(MAX_BODY_BYTES + 1)}
        )[0]
        == 400
    )
    assert server.store.list_runs() == []


def test_duplicate_workers_rejected_and_pause_remains_available(
    server: ResearchServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = request(
        server,
        "POST",
        "/api/runs",
        {"title": "Concurrency", "objective": "Test checkpoint control.", "demo": True},
    )[1]
    run_id = created["run"]["id"]
    started = threading.Event()
    release = threading.Event()

    def blocking_run(self: Engine, run_id: str, max_steps: int | None = None) -> None:
        started.set()
        release.wait(timeout=5)

    monkeypatch.setattr(Engine, "run", blocking_run)
    try:
        assert request(server, "POST", f"/api/runs/{run_id}/run", {"steps": 1})[0] == 202
        assert started.wait(timeout=2)
        assert request(server, "POST", f"/api/runs/{run_id}/run", {})[0] == 409
        assert request(server, "POST", f"/api/runs/{run_id}/cancel-experiment", {})[0] == 409
        assert (
            request(server, "POST", f"/api/runs/{run_id}/intervene", {"note": "Not yet"})[0] == 409
        )
        assert request(server, "POST", f"/api/runs/{run_id}/pause", {})[0] == 202
    finally:
        release.set()
        server.workers[run_id].join(timeout=5)


def test_nonloopback_bind_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="loopback"):
        ResearchServer(Store(tmp_path), host="0.0.0.0", port=0)  # noqa: S104


def test_budget_update_is_explicit_and_does_not_start_run(server: ResearchServer) -> None:
    created = request(
        server,
        "POST",
        "/api/runs",
        {"title": "Budget control", "objective": "Inspect spending limits.", "demo": True},
    )[1]
    run_id = created["run"]["id"]
    previous = server.store.get_config(run_id)
    status, result, _ = request(
        server, "POST", f"/api/runs/{run_id}/budget", {"usd": 45, "max_calls": 3000}
    )
    assert status == 200
    assert result["budget"]["usd"] == 45
    assert result["budget"]["max_calls"] == 3000
    assert result["budget"]["max_experiments"] == previous.budget.max_experiments
    assert not server.working(run_id)
    assert (
        request(server, "POST", f"/api/runs/{run_id}/budget", {"execution": {"allow_local": True}})[
            0
        ]
        == 400
    )


def test_artifact_download_requires_auth_and_confines_file_paths(server: ResearchServer) -> None:
    created = request(
        server,
        "POST",
        "/api/runs",
        {"title": "Artifact inspection", "objective": "Inspect saved artifacts.", "demo": True},
    )[1]
    run_id = created["run"]["id"]
    artifact = server.store.artifact(
        run_id, "manuscript", "draft.md", "# Research\nA reproducible result.\n"
    )
    path = f"/api/runs/{run_id}/artifacts/{artifact['id']}"
    status, content, headers = request(server, path=path)
    assert status == 200
    assert content.startswith(b"# Research")
    assert headers["Content-Disposition"].startswith("attachment;")
    assert request(server, path=path, authenticated=False)[0] == 401
    target = server.store.run_dir(run_id) / artifact["path"]
    target.unlink()
    target.symlink_to(server.store.db_path)
    assert request(server, path=path)[0] == 400


def test_cancel_experiment_retains_a_cancelled_receipt_and_requires_explicit_resume(
    server: ResearchServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Engine(server.store).create("Pending benchmark", "Test scheduler cancellation", demo=True)
    assert request(server, "POST", f"/api/runs/{run.id}/cancel-experiment", {})[0] == 400
    run.pending_experiment = ExperimentSpec(
        id="job-experiment",
        kind="full",
        workspace=str(server.store.run_dir(run.id)),
        argv=["python3", "benchmark.py"],
    )
    run.pending_job_id = "31415"
    server.store.save(run)
    cancelled: list[str] = []

    def cancel(self: Any, job_id: str) -> None:
        cancelled.append(job_id)

    monkeypatch.setattr("autoresearch.engine.Executor.cancel", cancel)
    status, result, _ = request(server, "POST", f"/api/runs/{run.id}/cancel-experiment", {})
    assert status == 200
    assert cancelled == ["31415"]
    assert result["run"]["status"] == "paused"
    assert result["run"]["pending_job_id"] is None
    assert result["run"]["experiments"][-1]["status"] == "cancelled"
    assert server.store.is_paused(run.id)
    assert not server.working(run.id)


def test_incomplete_live_setup_is_rejected_before_creating_a_run(server: ResearchServer) -> None:
    status, result, _ = request(
        server, "POST", "/api/runs", {"title": "Live", "objective": "Actual research"}
    )
    assert status == 400
    assert result["readiness"]["ready"] is False
    assert server.store.list_runs() == []


def test_console_exposes_editable_defaults_and_preflight(server: ResearchServer) -> None:
    status, result, _ = request(server, path="/api/config")
    assert status == 200
    assert result["config"]["provider"]["api_key_env"] == "XAI_API_KEY"
    assert request(server, path="/api/config", authenticated=False)[0] == 401
    status, checked, _ = request(server, "POST", "/api/preflight", {"config": result["config"]})
    assert status == 200
    assert checked["ready"] is False
    assert any(c["name"] == "source" and c["status"] == "error" for c in checked["checks"])


def test_live_form_configuration_is_saved_without_starting_research(
    server: ResearchServer, tmp_path: Path
) -> None:
    from autoresearch.config import ResearchConfig

    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("print('training')\n")
    (source / "evaluate.py").write_text("print('evaluate')\n")
    config = ResearchConfig.model_validate(
        {
            "provider": {"base_url": "http://127.0.0.1:9999/v1", "model": "configured-model"},
            "project": {
                "source_dir": str(source),
                "baseline_argv": ["python3", "train.py"],
                "evaluator_argv": ["python3", "evaluate.py"],
                "protected_paths": ["evaluate.py"],
                "sota": {"score": 0.6},
            },
            "execution": {"backend": "local", "allow_local": True},
            "budget": {"usd": 3},
        }
    ).model_dump(mode="json")
    assert request(server, "POST", "/api/preflight", {"config": config})[1]["ready"]
    status, result, _ = request(
        server,
        "POST",
        "/api/runs",
        {
            "title": "Configured live run",
            "objective": "Test the configured benchmark.",
            "config": config,
        },
    )
    assert status == 201
    run_id = result["run"]["id"]
    detail = request(server, path=f"/api/runs/{run_id}")[1]
    assert detail["config"]["project"]["source_dir"] == str(source)
    assert detail["config"]["provider"]["model"] == "configured-model"
    assert detail["config"]["budget"]["usd"] == 3
    assert detail["readiness"]["ready"]
    assert not detail["working"]
    assert detail["usage"]["calls"] == 0
    assert (server.store.run_dir(run_id) / "source" / "evaluate.py").exists()


def test_demo_requires_explicit_action_even_with_demo_server_defaults(
    server: ResearchServer,
) -> None:
    from autoresearch.config import ResearchConfig

    server.config = ResearchConfig(mode="demo")
    status, _, _ = request(
        server, "POST", "/api/runs", {"title": "Live", "objective": "Live research"}
    )
    assert status == 400
    assert server.store.list_runs() == []


def test_recorded_ai_definitions_are_authenticated_and_inspectable(server: ResearchServer) -> None:
    run = Engine(server.store).create("Public fixture", "Inspect AI system", demo=True)
    path = f"/api/runs/{run.id}/behavior"
    assert request(server, path=path, authenticated=False)[0] == 401
    status, info, _ = request(server, path=path)
    assert status == 200
    assert info["identity"]["bundle_sha256"] == run.behavior.bundle_sha256
    assert "meta_refine" in info["workflow"]["nodes"]
    assert info["agents"]["subset"]["handler"] == "coding"
    assert info["prompts"]["subset"]
    assert server.store.usage(run.id)["calls"] == 0


def test_pdf_download_preserves_verified_binary_content_and_filename(
    server: ResearchServer,
) -> None:
    state = Engine(server.store).create("PDF inspection", "Download exact bytes", demo=True)
    content = b"%PDF-1.7\nfixture binary \x00\xff\n"
    record = server.store.artifact_bytes(state.id, "paper_orchestra_pdf", "paper-v1.pdf", content)
    status, downloaded, headers = request(
        server, path=f"/api/runs/{state.id}/artifacts/{record['id']}"
    )
    assert status == 200 and downloaded == content
    assert headers["Content-Type"] == "application/pdf"
    assert headers["Content-Disposition"] == 'attachment; filename="paper-v1.pdf"'


@pytest.mark.parametrize("exit_kind", ["normal", "interrupt", "http_failure"])
def test_console_exit_pauses_and_joins_all_workers_before_returning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exit_kind: str
) -> None:
    from autoresearch.web import serve

    store = Store(tmp_path)
    runs = [
        Engine(store).create("Shutdown fixture", "Preserve checkpoints", demo=True)
        for _ in range(2)
    ]
    started = {run.id: threading.Event() for run in runs}
    paused = {run.id: threading.Event() for run in runs}
    release = threading.Event()
    instances: list[ResearchServer] = []
    errors: list[BaseException] = []
    original_pause = Engine.pause

    def pause(engine: Engine, run_id: str) -> None:
        original_pause(engine, run_id)
        paused[run_id].set()

    def run(engine: Engine, run_id: str, max_steps: int | None = None) -> None:
        with store.lease(run_id):
            started[run_id].set()
            assert release.wait(timeout=5), "test must release its simulated paid call"
            assert store.is_paused(run_id)
            checkpoint = store.get_run(run_id)
            checkpoint.status = "paused"
            store.save(checkpoint, "shutdown_checkpoint")

    def listener(instance: ResearchServer, poll_interval: float = 0.5) -> None:
        instances.append(instance)
        for state in runs:
            instance.start_run(state.id)
        assert all(event.wait(timeout=2) for event in started.values())
        if exit_kind == "interrupt":
            raise KeyboardInterrupt
        if exit_kind == "http_failure":
            raise OSError("synthetic HTTP listener failure")

    def launch() -> None:
        try:
            serve(store, port=0)
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(Engine, "pause", pause)
    monkeypatch.setattr(Engine, "run", run)
    monkeypatch.setattr(ResearchServer, "serve_forever", listener)
    console = threading.Thread(target=launch)
    console.start()
    try:
        assert all(event.wait(timeout=2) for event in paused.values())
        instance = instances[0]
        assert console.is_alive(), "server close must wait for in-flight research checkpoints"
        assert all(not worker.daemon for worker in instance.workers.values())
        with pytest.raises(RuntimeError, match="closing"):
            instance.start_run(runs[0].id, resume=True)
        assert store.is_paused(runs[0].id)
    finally:
        release.set()
        console.join(timeout=5)
        for instance in instances:
            for worker in instance.workers.values():
                worker.join(timeout=5)
    assert not console.is_alive()
    assert all(store.get_run(state.id).status == "paused" for state in runs)
    assert all(not instance.worker_errors for instance in instances)
    assert len(errors) == (1 if exit_kind == "http_failure" else 0)
    if errors:
        assert isinstance(errors[0], OSError)
        assert "synthetic HTTP listener failure" in str(errors[0])


@pytest.fixture
def managed_server(tmp_path: Path) -> Iterator[ResearchServer]:
    instance = ResearchServer(
        Store(tmp_path / "remote"),
        port=0,
        token="m" * 43,
        managed_remote=True,
        remote_label="test-cluster",
    )
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)


def test_managed_bootstrap_requires_token_and_never_loads_ssh_configuration(
    managed_server: ResearchServer,
) -> None:
    assert managed_server.remote_manager is None
    status, html, _ = request(managed_server, path="/", authenticated=False)
    assert status == 200
    assert managed_server.token.encode() not in html
    assert request(managed_server, path="/api/bootstrap", authenticated=False)[0] == 401
    assert (
        request(managed_server, path="/api/bootstrap", headers={"Authorization": "Bearer wrong"})[0]
        == 401
    )
    status, bootstrap, _ = request(managed_server, path="/api/bootstrap")
    assert status == 200
    assert bootstrap["managed_remote"] is True
    assert bootstrap["remote_label"] == "test-cluster"
    assert bootstrap["token"] == managed_server.token
    assert request(managed_server, path="/api/remote-health", authenticated=False)[0] == 401
    assert request(managed_server, path="/api/remote-health")[1] == {
        "status": "running",
        "remote_label": "test-cluster",
    }


def test_managed_server_cannot_start_without_explicit_token(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit session token"):
        ResearchServer(Store(tmp_path), port=0, managed_remote=True)


@pytest.mark.parametrize("host", ["127.0.0.1:49152", "localhost:12345"])
def test_managed_forwarding_accepts_ephemeral_loopback_port_only_with_matching_origin(
    managed_server: ResearchServer,
    server: ResearchServer,
    host: str,
) -> None:
    headers = {"Host": host, "Origin": f"http://{host}"}
    assert request(managed_server, path="/api/bootstrap", headers=headers)[0] == 200
    assert (
        request(managed_server, path="/api/bootstrap", headers=headers, authenticated=False)[0]
        == 401
    )
    assert request(server, path="/api/bootstrap", headers=headers)[0] == 403
    assert (
        request(
            managed_server,
            path="/api/bootstrap",
            headers={"Host": host, "Origin": "http://127.0.0.1:8765"},
        )[0]
        == 403
    )
    assert request(managed_server, headers={**headers, "Sec-Fetch-Site": "cross-site"})[0] == 403


@pytest.mark.parametrize(
    "host",
    [
        "attacker.example:49152",
        "127.1:49152",
        "localhost.attacker.example:49152",
        "127.0.0.1:0",
        "127.0.0.1:65536",
        "localhost",
        "127.0.0.1:12/",
        "user@localhost:12",
    ],
)
def test_managed_forwarding_denies_invalid_authorities(
    managed_server: ResearchServer, host: str
) -> None:
    assert request(managed_server, path="/api/bootstrap", headers={"Host": host})[0] == 403


@pytest.mark.parametrize(
    "header,status",
    [("Host", 403), ("Origin", 403), ("Authorization", 401), ("Sec-Fetch-Site", 403)],
)
def test_managed_duplicate_security_headers_are_denied(
    managed_server: ResearchServer, header: str, status: int
) -> None:
    authority = f"127.0.0.1:{managed_server.server_address[1]}"
    values = {
        "Host": authority,
        "Origin": f"http://{authority}",
        "Authorization": f"Bearer {managed_server.token}",
        "Sec-Fetch-Site": "same-origin",
    }
    connection = http.client.HTTPConnection(
        "127.0.0.1", managed_server.server_address[1], timeout=5
    )
    try:
        connection.putrequest("GET", "/api/bootstrap", skip_host=True)
        for name, value in values.items():
            connection.putheader(name, value)
        connection.putheader(header, values[header])
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == status
        response.read()
    finally:
        connection.close()


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/remotes", None),
        ("POST", "/api/remotes", {"name": "fixture", "host": "test-cluster"}),
        ("POST", "/api/remotes/fixture/authenticate", {}),
        ("POST", "/api/remotes/fixture/connect", {}),
        ("GET", "/api/remotes/authentication/session-one", None),
        ("POST", "/api/remotes/authentication/session-one/answer", {"answer": "dummy-response"}),
    ],
)
def test_nested_remote_management_is_disabled(
    managed_server: ResearchServer, method: str, path: str, body: dict[str, Any] | None
) -> None:
    assert request(managed_server, method, path, body)[0] == 403


@pytest.mark.parametrize("profile_name", ["fixture", "authentication"])
def test_remote_profiles_manual_targets_and_actions_are_explicit(
    server: ResearchServer, profile_name: str
) -> None:
    status, initial, _ = request(server, path="/api/remotes")
    assert status == 200
    assert initial == {"hosts": ["test-cluster"], "profiles": []}
    profile = {
        "name": profile_name,
        "host": "researcher@test.example",
        "port": 2202,
        "python": "python3",
        "directory": "~/runtime",
    }
    status, saved, _ = request(server, "POST", "/api/remotes", profile)
    assert status == 200
    assert saved["host"] == profile["host"]
    assert saved["port"] == 2202
    manager = server.remote_manager
    assert isinstance(manager, FakeRemoteManager)
    assert manager.actions == [], "Saving cannot install or connect"
    for action in ["probe", "install", "connect", "disconnect", "authenticate"]:
        assert request(server, path=f"/api/remotes/{profile_name}/{action}")[0] == 404
        assert request(server, "POST", f"/api/remotes/{profile_name}/{action}", {})[0] == 200
    assert manager.actions == [
        (action, profile_name)
        for action in ["probe", "install", "connect", "disconnect", "authenticate"]
    ]
    assert request(server, path=f"/api/remotes/{profile_name}/status")[1]["status"] == "status"
    assert (
        request(server, path="/api/remotes/authentication/session-one")[1]["status"]
        == "authenticating"
    )
    assert (
        request(server, "POST", "/api/remotes", {**profile, "password": "never-persist"})[0] == 400
    )
    assert len(manager.saved) == 1


@pytest.mark.parametrize(
    "path",
    [
        "/api/remotes",
        "/api/remotes/fixture/connect",
        "/api/remotes/fixture/install",
        "/api/remotes/fixture/authenticate",
        "/api/remotes/authentication/session-one/answer",
        "/api/remotes/authentication/session-one/cancel",
    ],
)
def test_remote_mutations_require_auth_and_reject_cross_site(
    server: ResearchServer, path: str
) -> None:
    assert request(server, "POST", path, {}, authenticated=False)[0] == 401
    assert (
        request(server, "POST", path, {}, headers={"Origin": "http://attacker.example"})[0] == 403
    )
    assert request(server, "POST", path, {}, headers={"Sec-Fetch-Site": "cross-site"})[0] == 403


def test_ssh_prompt_lifecycle_preserves_response_without_echo_or_research_logging(
    server: ResearchServer,
) -> None:
    status, started, _ = request(server, "POST", "/api/remotes/fixture/authenticate", {})
    assert status == 200
    assert started["session_id"] == "session-one"
    path = "/api/remotes/authentication/session-one"
    assert request(server, path=path, authenticated=False)[0] == 401
    assert request(server, path=path)[1]["output"] == "MFA code: "
    answer = "  dummy response  "
    status, result, _ = request(server, "POST", f"{path}/answer", {"answer": answer})
    assert status == 200
    assert result["status"] == "authenticated"
    assert answer not in json.dumps(result)
    manager = server.remote_manager
    assert isinstance(manager, FakeRemoteManager)
    assert manager.answers == [("session-one", answer)]
    for invalid in ["bad\nresponse", "bad\rresponse", "\x00", "x" * 4097, 123]:
        assert request(server, "POST", f"{path}/answer", {"answer": invalid})[0] == 400
    assert len(manager.answers) == 1
    assert request(server, "POST", f"{path}/answer", {"answer": ""})[0] == 200
    assert manager.answers[-1] == ("session-one", "")
    assert request(server, "POST", f"{path}/cancel", {})[1]["status"] == "cancelled"
    assert server.store.list_runs() == []


def test_long_remote_action_keeps_console_responsive(
    server: ResearchServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = server.remote_manager
    assert isinstance(manager, FakeRemoteManager)
    entered, release = threading.Event(), threading.Event()
    results: list[int] = []

    def probe(name: str) -> dict[str, str]:
        entered.set()
        assert release.wait(timeout=5)
        return {"status": "ready"}

    monkeypatch.setattr(manager, "probe", probe)
    worker = threading.Thread(
        target=lambda: results.append(request(server, "POST", "/api/remotes/fixture/probe", {})[0])
    )
    worker.start()
    try:
        assert entered.wait(timeout=2)
        assert request(server)[0] == 200
    finally:
        release.set()
        worker.join(timeout=5)
    assert results == [200]


def test_server_close_releases_remote_manager_once(tmp_path: Path) -> None:
    instance = ResearchServer(Store(tmp_path), port=0)
    manager = instance.remote_manager
    assert isinstance(manager, FakeRemoteManager)
    instance.server_close()
    instance.server_close()
    assert manager.closed == 1


def test_settings_api_auth_persistence_conflicts_and_existing_run_isolation(
    server: ResearchServer,
) -> None:
    from autoresearch.config import ResearchConfig
    from autoresearch.settings import load_settings

    run = Engine(server.store).create("Previous run", "Keep defaults frozen", demo=True)
    before = server.store.get_config(run.id)
    status, defaults, _ = request(server, path="/api/config")
    assert status == 200 and defaults["revision"] == 0
    assert "Metis welcomes you." in defaults["guide"]
    config = defaults["config"]
    config["provider"]["model"] = "saved-in-browser"
    body = {"config": config, "revision": 0}
    assert request(server, "POST", "/api/settings", body, authenticated=False)[0] == 401
    assert request(server, "POST", "/api/settings", body)[0] == 200
    assert request(server, "POST", "/api/settings", body)[0] == 409
    assert (
        request(
            server, "POST", "/api/settings", {"revision": 1, "config": {"budget": {"usd": -1}}}
        )[0]
        == 400
    )
    status, current, _ = request(server, path="/api/config")
    assert status == 200 and current["revision"] == 1
    assert current["config"]["provider"]["model"] == "saved-in-browser"
    assert load_settings(Store(server.store.root))[0].provider.model == "saved-in-browser"
    assert server.store.get_config(run.id) == before
    assert len(server.store.list_runs()) == 1
    assert server.store.usage(run.id)["calls"] == 0
    # A launch config seeds the editor; saving explicitly replaces the defaults.
    server.config = ResearchConfig(provider={"model": "launch-override"})
    assert (
        request(server, path="/api/config")[1]["config"]["provider"]["model"] == "launch-override"
    )
    assert request(server, "POST", "/api/settings", {"revision": 1, "config": config})[0] == 200
    assert server.config is None


def test_settings_validation_normalizes_replacement_without_saving(server: ResearchServer) -> None:
    from autoresearch.settings import load_settings

    body = {
        "config": {
            "role_providers": {},
            "project": {"metrics": {"accuracy": "max"}, "primary_metric": "accuracy"},
        }
    }
    assert request(server, "POST", "/api/settings/validate", body, authenticated=False)[0] == 401
    status, result, _ = request(server, "POST", "/api/settings/validate", body)
    assert status == 200
    assert result["config"]["role_providers"] == {}
    assert result["config"]["project"]["metrics"] == {"accuracy": "max"}
    assert result["config"]["budget"]["usd"] == 25
    assert load_settings(server.store)[1] == 0
    assert server.store.list_runs() == []


def test_appearance_persists_and_requires_authentication(server: ResearchServer) -> None:
    from autoresearch.appearance import load_theme

    assert (
        request(server, "POST", "/api/appearance", {"theme": "cream"}, authenticated=False)[0]
        == 401
    )
    assert request(server, "POST", "/api/appearance", {"theme": "invalid"})[0] == 400
    assert request(server, "POST", "/api/appearance", {"theme": "cream"})[0] == 200
    assert load_theme(server.store) == "cream"
    assert request(server, path="/api/bootstrap")[1]["appearance"]["theme"] == "cream"
    assert server.store.list_runs() == []


def test_onboarding_requires_auth_and_never_creates_research(
    server: ResearchServer, tmp_path: Path
) -> None:
    source = tmp_path / "fixture-project"
    source.mkdir()
    (source / "README.md").write_text("Public synthetic fixture")
    status, _, _ = request(
        server, "POST", "/api/onboarding/inspect", {"source_dir": str(source)}, authenticated=False
    )
    assert status == 401
    status, result, _ = request(
        server, "POST", "/api/onboarding/inspect", {"source_dir": str(source)}
    )
    assert status == 200
    assert result["files"] == ["README.md"]
    assert server.store.list_runs() == []
    status, result, _ = request(server, "GET", "/api/onboarding")
    assert status == 200
    assert result == {"proposals": []}


def test_reviewed_ai_preparation_http_does_not_save_or_execute(
    server: ResearchServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from autoresearch.contracts import AgentResponse, Usage

    source = tmp_path / "setup-fixture"
    source.mkdir()
    (source / "README.md").write_text("Use python3 train.py")
    (source / "train.py").write_text("# synthetic; never executed")
    config = {"project": {"source_dir": str(source)}}
    status, preview, _ = request(
        server,
        "POST",
        "/api/onboarding/prepare",
        {"config": config, "objective": "Fixture question", "maximum_usd": 1},
    )
    assert status == 200
    assert preview["status"] == "prepared"
    assert preview["request_preview"]["prompt"]["objective"] == "Fixture question"
    response = AgentResponse(
        data={
            "summary": "Fixture",
            "structured": {
                "summary": "Fixture proposal",
                "suggestions": [
                    {
                        "field": "project.baseline_argv",
                        "value": ["python3", "train.py"],
                        "reason": "Documented",
                        "evidence": ["README.md"],
                    }
                ],
            },
        },
        usage=Usage(cost_usd=0.01),
        provider="fixture",
        model="fixture",
    )
    monkeypatch.setattr(
        "autoresearch.onboarding.CompatibleProvider.complete", lambda self, req: response
    )
    status, generated, _ = request(
        server, "POST", "/api/onboarding/generate", {"id": preview["id"]}
    )
    assert status == 200
    assert generated["status"] == "complete"
    status, applied, _ = request(
        server,
        "POST",
        "/api/onboarding/apply",
        {"id": preview["id"], "config": config, "selected": [0]},
    )
    assert status == 200
    assert applied["config"]["project"]["baseline_argv"] == ["python3", "train.py"]
    assert server.store.list_runs() == []
    status, duplicate, _ = request(
        server, "POST", "/api/onboarding/generate", {"id": preview["id"]}
    )
    assert status == 400
    assert "already submitted" in duplicate["error"]
