# Security and privacy

AutoResearch executes proposed code and sends selected research context to configured model and literature providers. Use private project inputs only when that processing is permitted. This repository is an independent research implementation; it has not undergone an external security audit.

## Trust boundaries

- **Model responses, retrieved documents and copied project files are untrusted.** Typed JSON output and command validation constrain transport and execution; they do not make generated code trustworthy.
- **Docker is the default live execution backend.** It isolates the experiment workspace, disables network access, drops capabilities and applies resource limits. It requires a trustworthy daemon and image. Container isolation is defense in depth, not proof that hostile code cannot escape.
- **Local execution is opt-in and not sandboxed.** An executable allowlist cannot make Python safe. Code can access resources available to the operating-system user; use a disposable account or container for untrusted projects.
- **Slurm uses your cluster account.** Scheduler jobs require shared experiment storage and suitable cluster policy. Do not expose credentials, unrelated private files or privileged mounts to jobs.
- **Custom role commands are trusted integrations.** They are configured by the operator, not selected by a model. Review their executable, credentials, environment, networking and artifact handling before enabling them.
- **The console is single-user and loopback-only.** Its session token, Host/Origin checks and browser policies defend against unintended website access. They do not protect against malicious programs already running as the same user. Do not publish it directly to the internet; use an SSH tunnel on a trusted machine.

## State and provider privacy

Credentials are referenced by environment variable names in configuration. Do not put literal secrets in JSON, objectives, prompts or code. The compatible provider requires HTTPS except on loopback, does not follow redirects and ignores ambient proxy settings.

The default state directory is `~/.local/state/autoresearch`, separate from the Git checkout. The database and private artifacts contain resumable research state, configuration, generated text, code and cached responses. Directory/file permissions reduce accidental local exposure; state is not encrypted by this application. Use encrypted storage and appropriate backup/access policy if required.

`privacy.traces` controls diagnostic agent traces:

- `redacted` is the default and removes known credential patterns and configured private patterns.
- `metadata` omits detailed agent prompt/output fields from the event trace.
- `full` retains detailed events, while known-secret redaction still applies.

**These settings do not erase checkpoint, cache or artifact content.** Resumption requires that state. Set `privacy.cache` to `false` to disable response caching; keep the entire runtime directory private in every mode. Redaction is a heuristic and cannot anonymize arbitrary prose or unpublished research.

Default exports contain metadata and artifact hashes. `export --include-private` adds research state and events and can disclose sensitive information despite redaction. Review a private export manually before sharing it. No default export is a substitute for privacy review when even project metadata is confidential.

## Public repository guardrails

`.gitignore` excludes common runtime, credential, cluster and dataset artifacts. The public-file scanner checks tracked and nonignored untracked files for likely secrets, personal absolute home paths and private filenames without printing matching values. Its staged mode reads Git's index, so pre-commit scans the version that would be committed.

```bash
uv run pre-commit install
uv run python scripts/scan_secrets.py
uv run python scripts/scan_secrets.py --staged
```

The scanner recognizes explicit fake/test placeholders used in fixtures. It is not a comprehensive secret detector, malware scanner or data loss prevention system. Binary contents require manual review. Keep public fixtures synthetic; never test with a real key. Enable repository-host secret scanning and push protection when available. Hooks can be bypassed, and CI runs after data has reached the repository host, so prevention starts with keeping private files outside the checkout.

## Reporting a vulnerability

Use the repository's **Security → Report a vulnerability** private advisory channel when enabled. Include a minimal synthetic reproduction, affected revision, impact and suggested remediation. Never include real credentials, private prompts or unpublished datasets. If private reporting is unavailable, open an issue requesting a confidential contact channel without disclosing exploit details or sensitive data.

This initial `0.1.x` implementation has no formal support SLA. Security corrections should target the current development branch and supported release line. If a credential was exposed, revoke or rotate it at the provider before investigating Git history; deleting a file does not invalidate an exposed credential.
