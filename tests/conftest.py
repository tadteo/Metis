"""Offline tests must never borrow credentials or bill an external HTTP service."""

from __future__ import annotations

import os

import httpx
import pytest
from keyring.backends.null import Keyring

from autoresearch import credentials


@pytest.fixture(autouse=True)
def isolate_credentials_and_external_http(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("METIS_SETTINGS_HOME", str(tmp_path / "global-settings"))
    # Tests can override these with synthetic backends/keys after fixture setup.
    monkeypatch.setattr(credentials.keyring, "get_keyring", lambda: Keyring())
    monkeypatch.setattr(credentials.keyring, "get_password", lambda *_: None)
    monkeypatch.setattr(credentials, "_session", {})
    monkeypatch.setattr(credentials, "_seen", set())
    for name in os.environ:
        if name.endswith("_API_KEY"):
            monkeypatch.delenv(name)
    original = httpx.HTTPTransport.handle_request

    def offline_transport(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        if request.url.host not in {"localhost", "127.0.0.1", "::1"}:
            raise AssertionError("External HTTP is disabled in offline tests; use MockTransport")
        return original(self, request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", offline_transport)
