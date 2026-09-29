"""Model credentials from process memory, an approved OS vault, or the environment.

The settings and run stores contain only the variable name. Never pass these
credentials to experiment subprocesses or write them to Metis-managed files.
"""

from __future__ import annotations

import os
import re
import threading
from typing import Literal

import keyring

SERVICE = "Metis model provider"
_SAFE_BACKENDS = {
    "keyring.backends.macOS",
    "keyring.backends.SecretService",
    "keyring.backends.kwallet",
    "keyring.backends.Windows",
}
_lock = threading.RLock()
_session: dict[str, str] = {}
_seen: set[str] = set()


class CredentialAccessError(RuntimeError):
    """Safe diagnostic for an unreadable host vault; never fall through to another key."""


def valid_name(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name))


def valid_secret(value: str) -> bool:
    return (
        8 <= len(value) <= 8192
        and value.isascii()
        and not any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
    )


def vault_available() -> bool:
    try:
        backend = keyring.get_keyring()
        return type(backend).__module__ in _SAFE_BACKENDS and backend.priority > 0
    except Exception:
        raise CredentialAccessError("Host credential vault could not be inspected.") from None


def _vault_get(name: str) -> str | None:
    if not vault_available():
        return None
    try:
        return keyring.get_password(SERVICE, name)
    except Exception:
        raise CredentialAccessError("Host credential vault could not be read.") from None


def resolve(name: str) -> tuple[str, Literal["session", "vault", "environment", "missing"]]:
    if not valid_name(name):
        return "", "missing"
    with _lock:
        value = _session.get(name)
        if value:
            return value, "session"
    value = _vault_get(name)
    if value:
        with _lock:
            _seen.add(value)
        return value, "vault"
    value = os.environ.get(name, "")
    if value:
        return value, "environment"
    return "", "missing"


def status(name: str) -> dict[str, str | bool]:
    if not valid_name(name):
        raise ValueError("Enter a valid key variable name first.")
    _, source = resolve(name)
    return {"source": source, "vault_available": vault_available()}


def save(name: str, secret: str, persistence: str) -> dict[str, str | bool]:
    if not valid_name(name):
        raise ValueError("Enter a valid key variable name first.")
    if not valid_secret(secret):
        raise ValueError(
            "API key must be at least 8 ASCII characters without whitespace or control characters."
        )
    if persistence not in {"vault", "session"}:
        raise ValueError("Choose host vault or current session storage.")
    if persistence == "vault":
        if not vault_available():
            raise RuntimeError(
                "No supported host credential vault is available. Choose current session storage."
            )
        try:
            keyring.set_password(SERVICE, name, secret)
            if keyring.get_password(SERVICE, name) != secret:
                raise RuntimeError("Vault readback did not match")
        except Exception:
            raise RuntimeError(
                "Host credential vault could not verify this key. It may have been saved; retry or choose current session storage."
            ) from None
        with _lock:
            _session.pop(name, None)
            _seen.add(secret)
        return {"source": "vault", "vault_available": True}
    else:
        if vault_available():
            try:
                if keyring.get_password(SERVICE, name) is not None:
                    keyring.delete_password(SERVICE, name)
            except Exception:
                raise RuntimeError(
                    "Host vault key could not be removed. Current session storage was not selected."
                ) from None
        with _lock:
            _session[name] = secret
            _seen.add(secret)
        return {"source": "session", "vault_available": vault_available()}


def clear(name: str) -> dict[str, str | bool]:
    if not valid_name(name):
        raise ValueError("Enter a valid key variable name first.")
    with _lock:
        _session.pop(name, None)
    available = vault_available()
    if available:
        try:
            if keyring.get_password(SERVICE, name) is not None:
                keyring.delete_password(SERVICE, name)
        except Exception:
            raise RuntimeError("Host credential vault could not remove this key.") from None
    if not available:
        result = status(name)
        result["vault_unverified"] = True
        return result
    return status(name)


def known_secrets() -> tuple[str, ...]:
    with _lock:
        return tuple(_seen)
