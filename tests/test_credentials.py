"""Synthetic keys only: no test reads or writes the user's OS credential vault."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from autoresearch import credentials
from autoresearch.config import ResearchConfig
from autoresearch.paper_orchestra import _command
from autoresearch.privacy import redact
from autoresearch.setup import preflight


def test_session_key_resolves_without_environment_or_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "METIS_TEST_SESSION_KEY"
    value = "synthetic-session-key-123456"
    monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(credentials, "vault_available", lambda: False)
    assert credentials.save(name, value, "session") == {
        "source": "session",
        "vault_available": False,
    }
    try:
        assert credentials.resolve(name) == (value, "session")
        assert name not in __import__("os").environ
        assert redact(f"sent {value}") == "sent [REDACTED]"
    finally:
        credentials._session.pop(name, None)
    assert credentials.resolve(name) == ("", "missing")


def test_vault_key_survives_session_reset_without_real_vault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "METIS_TEST_VAULT_KEY"
    value = "synthetic-vault-key-123456"
    stored: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(credentials, "vault_available", lambda: True)
    monkeypatch.setattr(
        credentials.keyring,
        "set_password",
        lambda service, user, key: stored.__setitem__((service, user), key),
    )
    monkeypatch.setattr(
        credentials.keyring, "get_password", lambda service, user: stored.get((service, user))
    )
    monkeypatch.setattr(
        credentials.keyring, "delete_password", lambda service, user: stored.pop((service, user))
    )
    try:
        assert credentials.save(name, value, "vault")["source"] == "vault"
        credentials._session.clear()
        assert credentials.resolve(name) == (value, "vault")
        assert redact(value) == "[REDACTED]"
    finally:
        credentials.clear(name)
    assert not stored


def test_unavailable_vault_never_falls_back_to_session(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "METIS_TEST_NO_VAULT_KEY"
    monkeypatch.setattr(credentials, "vault_available", lambda: False)
    with pytest.raises(RuntimeError, match="No supported host credential vault"):
        credentials.save(name, "synthetic-private-key-123456", "vault")
    assert credentials.resolve(name)[1] == "missing"


@pytest.mark.parametrize("secret", ["", "not ascii ♥", "two words", "line\nbreak", "x" * 8193])
def test_invalid_key_is_rejected_without_echo(secret: str) -> None:
    with pytest.raises(ValueError) as caught:
        credentials.save("METIS_TEST_INVALID_KEY", secret, "session")
    if secret:
        assert secret not in str(caught.value)


def test_custom_backend_is_not_assumed_secure(monkeypatch: pytest.MonkeyPatch) -> None:
    class UnsafeBackend:
        priority = 10

    monkeypatch.setattr(credentials.keyring, "get_keyring", lambda: UnsafeBackend())
    assert credentials.vault_available() is False


def test_status_never_returns_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "METIS_TEST_STATUS_KEY"
    monkeypatch.setattr(credentials, "vault_available", lambda: False)
    credentials.save(name, "synthetic-status-key-123456", "session")
    try:
        response: dict[str, Any] = credentials.status(name)
        assert "synthetic-status-key" not in str(response)
        assert set(response) == {"source", "vault_available"}
    finally:
        credentials._session.pop(name, None)


def test_preflight_and_trusted_writer_receive_the_named_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    name = "METIS_TEST_WRITER_KEY"
    value = "synthetic-writer-key-123456"
    monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(credentials, "vault_available", lambda: False)
    credentials.save(name, value, "session")
    try:
        config = ResearchConfig()
        config.provider.api_key_env = name
        checks = preflight(config)["checks"]
        provider = next(check for check in checks if check["name"] == "provider:default")
        assert provider["status"] == "ok"
        _, env = _command(
            tmp_path / "job",
            tmp_path / "upstream",
            {
                "compatible_models": {"writer": {"api_key_env": name}},
                "backend": "local",
                "allow_local": True,
                "python_executable": "python3",
            },
        )
        assert env[name] == value
    finally:
        credentials._session.pop(name, None)


def test_session_replaces_existing_vault_key(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "METIS_TEST_REPLACE_KEY"
    stored = {(credentials.SERVICE, name): "synthetic-old-vault-key"}
    monkeypatch.setattr(credentials, "vault_available", lambda: True)
    monkeypatch.setattr(
        credentials.keyring, "get_password", lambda service, user: stored.get((service, user))
    )
    monkeypatch.setattr(
        credentials.keyring, "delete_password", lambda service, user: stored.pop((service, user))
    )
    try:
        assert credentials.save(name, "synthetic-new-session-key", "session")["source"] == "session"
        assert not stored
    finally:
        credentials.clear(name)


def test_vault_save_requires_readback_and_never_claims_session_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "METIS_TEST_VERIFY_KEY"
    monkeypatch.setattr(credentials, "vault_available", lambda: True)
    monkeypatch.setattr(credentials.keyring, "set_password", lambda *_: None)
    monkeypatch.setattr(credentials.keyring, "get_password", lambda *_: None)
    with pytest.raises(RuntimeError, match="could not verify"):
        credentials.save(name, "synthetic-unverified-key", "vault")
    assert name not in credentials._session


def test_unreadable_vault_blocks_environment_fallback_and_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "METIS_TEST_LOCKED_VAULT_KEY"
    monkeypatch.setenv(name, "synthetic-environment-fallback")
    monkeypatch.setattr(credentials, "vault_available", lambda: True)

    def unreadable(*_: str) -> None:
        raise RuntimeError("raw backend detail")

    monkeypatch.setattr(credentials.keyring, "get_password", unreadable)
    with pytest.raises(credentials.CredentialAccessError, match="could not be read"):
        credentials.resolve(name)
    config = ResearchConfig()
    config.provider.api_key_env = name
    provider = next(
        check for check in preflight(config)["checks"] if check["name"] == "provider:default"
    )
    assert provider["status"] == "error"
    assert "raw backend detail" not in provider["message"]


def test_clear_drops_session_even_when_vault_read_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "METIS_TEST_CLEAR_LOCKED_KEY"
    monkeypatch.setattr(credentials, "vault_available", lambda: False)
    credentials.save(name, "synthetic-session-clear-key", "session")
    monkeypatch.setattr(credentials, "vault_available", lambda: True)

    def unreadable(*_: str) -> None:
        raise RuntimeError("raw backend detail")

    monkeypatch.setattr(credentials.keyring, "get_password", unreadable)
    with pytest.raises(RuntimeError, match="could not remove"):
        credentials.clear(name)
    assert name not in credentials._session


def test_clear_reports_unverified_vault_after_clearing_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "METIS_TEST_CLEAR_KEY"
    monkeypatch.setattr(credentials, "vault_available", lambda: False)
    credentials.save(name, "synthetic-clear-key-123456", "session")
    result = credentials.clear(name)
    assert result["vault_unverified"] is True
    assert credentials.resolve(name)[1] == "missing"


def test_writer_resolves_compatible_key_even_when_name_matches_native_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    name = "GEMINI_API_KEY"
    value = "synthetic-compatible-key-123456"
    monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(credentials, "vault_available", lambda: False)
    credentials.save(name, value, "session")
    try:
        _, env = _command(
            tmp_path / "job",
            tmp_path / "upstream",
            {
                "compatible_models": {"writer": {"api_key_env": name}},
                "backend": "local",
                "allow_local": True,
                "python_executable": "python3",
            },
        )
        assert env[name] == value
    finally:
        credentials._session.pop(name, None)


def test_offline_suite_cannot_use_real_vault_or_bill_external_http() -> None:
    import httpx

    assert credentials.vault_available() is False
    assert credentials.resolve("XAI_API_KEY") == ("", "missing")
    with httpx.Client(trust_env=False) as client:
        with pytest.raises(AssertionError, match="External HTTP is disabled"):
            client.post("https://api.x.ai/v1/chat/completions", json={"synthetic": True})
