# Metis identity and attribution

Status: implemented, independently reviewed and validated; ready for integration.
Base: `3502385`. See [review and validation](../reviews/metis-identity.md).

## Requirement

User request (2026-09-29): name the project Metis, including GitHub and Codex;
retain ScientistTwo references as citations and inspiration. Metis is its own
research platform that builds on and extends the paper, not a copy.

## Boundary and sequence

Use isolated branch `codex/autoresearch-identity`. Update public branding, CLI,
package metadata, local agent identity, workflow asset names and current guides.
Keep scientific stage contracts and evidence gates unchanged. Preserve upstream
prompt attribution and historical plans, reviews, hashes and validation records.
Retain the Python import namespace, `autoresearch` command alias, environment
variables and state paths for compatibility. Version changed local prompt contracts;
existing pinned runs continue to reject drift rather than silently adopting a rename.

Run focused contracts, full CI-equivalent offline checks and the installed-wheel
check. Obtain independent review before committing and merging. Record actual
failures and limitations. Regenerate the evidence reports after path changes and
record the implementation commit in the canonical matrix after it exists.

## External naming

This checkout has no GitHub remote. Identify the exact repository before renaming;
the similarly named `tadteo/auto-improve-research` contains a different project.
The user subsequently requested creating a new repository on their GitHub account.
Create private `tadteo/Metis`, connect origin and push the reviewed integration.
Codex exposes no project rename tool and its native UI is blocked to computer use;
leave the project path and active worktrees intact and report that limitation.

## Acceptance

- Metis appears in web/TUI/CLI onboarding, package metadata and current guides.
- `metis` and the compatibility `autoresearch` entry point both execute the CLI.
- Current local prompt/workflow identity uses Metis; references to ScientistTwo
  explain source attribution, inspiration, explicit comparisons or historical facts.
- Scientific checks, source attribution and all existing run history remain intact.
- Tests, independent review, commits and merge evidence are recorded.
