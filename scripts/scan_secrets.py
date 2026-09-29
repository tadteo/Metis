#!/usr/bin/env python3
"""Scan public Git content without printing matched secrets.

The default checks tracked files plus nonignored untracked files. --staged reads
the index, so a cleaned working tree cannot conceal a secret staged for commit.
Ignored untracked runtime data is not read. This is a guardrail, not a DLP system.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MAX_BYTES = 8 * 1024 * 1024
TOKEN_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("API token", re.compile(r"\b(?:xai-|sk-(?:or-v1-)?)[A-Za-z0-9_-]{16,}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}\b")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
)
ASSIGNMENT = re.compile(
    r"(?i)(?:[A-Z0-9_]*(?:API[_-]?KEY|ACCESS[_-]?TOKEN|SECRET|PASSWORD))"
    r"\s*[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_+/=-]{16,})"
)
HOME_PATH = re.compile(r"/(?:Users|home)/([A-Za-z0-9_.@-]+)(?=/|\b)")
WINDOWS_HOME = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+([A-Za-z0-9_.@-]+)")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
FAKE_PARTS = re.compile(
    r"(?:^|[-_])(?:test|fake|dummy|example|placeholder|redacted)(?:[-_]|$)", re.I
)
PLACEHOLDERS = {"your_api_key", "your_token", "replace_me", "changeme", "not_a_real_secret"}
PRIVATE_PARTS = {".ssh", ".aws", ".kube", "private", "runtime", ".autoresearch", "exports"}
PRIVATE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db"}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    reason: str


def placeholder(value: str) -> bool:
    lowered = value.lower()
    return (
        lowered in PLACEHOLDERS
        or bool(FAKE_PARTS.search(value))
        or lowered.startswith(("your_", "replace_", "example_"))
    )


def scan_text(path: str, content: str) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(content.splitlines(), 1):
        reasons: set[str] = set()
        if PRIVATE_KEY.search(line):
            reasons.add("private key material")
        for label, pattern in TOKEN_RULES:
            if any(not placeholder(match.group()) for match in pattern.finditer(line)):
                reasons.add(label)
        if any(not placeholder(match.group(1)) for match in ASSIGNMENT.finditer(line)):
            reasons.add("literal credential assignment")
        if HOME_PATH.search(line) or WINDOWS_HOME.search(line):
            reasons.add("personal absolute home path")
        findings.extend(Finding(path, number, reason) for reason in sorted(reasons))
    return findings


def private_filename(path: str) -> bool:
    parts = PurePosixPath(path).parts
    name = parts[-1]
    return (
        bool(PRIVATE_PARTS.intersection(parts))
        or (name.startswith(".env") and name != ".env.example")
        or PurePosixPath(name).suffix.lower() in PRIVATE_SUFFIXES
        or name in {"id_rsa", "id_ed25519", ".netrc", "autoresearch.json", "project.json"}
        or name.endswith((".local.json", ".private.json"))
    )


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError("Git content could not be inspected; run inside the repository")
    return result.stdout


def scan_repository(root: Path, staged: bool = False) -> list[Finding]:
    listing = (
        git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
        if staged
        else git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    )
    findings: list[Finding] = []
    for raw_name in sorted(set(listing.split(b"\0")) - {b""}):
        name = raw_name.decode("utf-8", errors="surrogateescape")
        path = root / name
        if private_filename(name):
            findings.append(Finding(name, 0, "private runtime or credential file in public tree"))
        if staged:
            index_entry = git(root, "ls-files", "--stage", "-z", "--", name)
            if index_entry.startswith(b"120000 "):
                findings.append(Finding(name, 0, "staged symlink requires public-artifact review"))
                continue
            content = git(root, "show", f":{name}")
        else:
            if path.is_symlink():
                findings.append(
                    Finding(name, 0, "symlink requires explicit public-artifact review")
                )
                continue
            if not path.exists():
                continue
            if not path.is_file() or not path.resolve().is_relative_to(root):
                findings.append(Finding(name, 0, "unsupported or escaping public file"))
                continue
            if path.stat().st_size > MAX_BYTES:
                findings.append(Finding(name, 0, "file exceeds public scan size limit"))
                continue
            content = path.read_bytes()
        if len(content) > MAX_BYTES:
            findings.append(Finding(name, 0, "file exceeds public scan size limit"))
            continue
        if b"\0" in content:
            # Binary files cannot hide private names, but need manual content review.
            continue
        findings.extend(scan_text(name, content.decode("utf-8", errors="replace")))
    return findings


def self_test() -> None:
    secret = "xai-" + "A1b2C3d4E5f6G7h8J9k0"
    assert scan_text("sample.txt", secret)
    assert not scan_text("sample.txt", "xai-test-" + "0" * 32)
    assert scan_text("sample.txt", "/" + "Users" + "/" + "person" + "/private.txt")
    assert scan_text("sample.txt", "-----BEGIN " + "PRIVATE KEY-----")
    assert not scan_text("sample.txt", "XAI_API_KEY=\napi_key_env: XAI_API_KEY")
    assert private_filename(".env.production")
    assert private_filename("runtime/run.json")
    assert not private_filename(".env.example")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="Scan exact staged content")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("Secret scanner self-test passed.")
        return 0
    try:
        root = Path(git(args.root.resolve(), "rev-parse", "--show-toplevel").decode().strip())
        findings = scan_repository(root, staged=args.staged)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Public-file scan failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.reason}", file=sys.stderr)
    if findings:
        print(
            "Remove private content before publishing. Matched values were not printed.",
            file=sys.stderr,
        )
        return 1
    print("Public-file scan passed (heuristic checks; review exports separately).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
