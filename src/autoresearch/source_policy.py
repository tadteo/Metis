"""Shared exclusions for research source snapshots and local setup checks.

Include globs select project files; they cannot opt credential or private runtime
paths back in. This filename policy does not detect arbitrary secrets in prose.
"""

from pathlib import PurePath

_EXCLUDED_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".ssh",
    ".aws",
    ".azure",
    ".gnupg",
    ".kube",
    ".docker",
    ".config",
    ".codex",
    ".agents",
    ".secrets",
    ".credentials",
    ".netrc",
    ".git-credentials",
    ".pypirc",
    ".npmrc",
    ".yarnrc",
    ".yarnrc.yml",
    "auth.json",
    "authorized_keys",
    "known_hosts",
    "runtime",
    "private",
    "data",
}
_CREDENTIAL_PREFIXES = (
    ".env",
    "credentials",
    "secrets",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "service-account",
    "service_account",
)
_KEY_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


def source_is_excluded(relative: str | PurePath) -> bool:
    """Return whether any component is a protected source-exclusion name."""
    return any(
        part.lower() in _EXCLUDED_NAMES
        or part.lower().startswith(_CREDENTIAL_PREFIXES)
        or part.lower().endswith(_KEY_SUFFIXES)
        for part in PurePath(relative).parts
    )
