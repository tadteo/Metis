# Contributing

Contributions should improve scientific reliability and maintain a clear distinction between implemented behavior, assumptions and measured capability.

## Development

Use Python 3.11+ and the committed lockfile:

```bash
uv sync --frozen --group dev
uv run pre-commit install
uv run ruff format .
uv run ruff check .
uv run mypy src
uv run autoresearch validate-specs
uv run pytest
node --test tests/test_web_ui.mjs
uv run python scripts/scan_secrets.py
uv run autoresearch demo
```

No model credentials or external cluster are needed for offline tests and the demo. Live provider tests and cluster runs are opt-in and must not be introduced into ordinary CI. When changing dependencies, pin direct versions, regenerate `uv.lock`, explain the reason and verify a clean frozen install.

## Change boundaries

- Preserve the published stage and feedback structure. Describe changes to scientific stopping rules in [the fidelity ledger](docs/fidelity.md), with supporting evidence when a simplification is proposed.
- Keep providers, role policies, execution backends and persistence behind their existing typed interfaces. Validate external JSON, command arguments, paths and metrics at the boundary.
- Add focused tests for consequential behavior: experiment scheduling/resumption, evidence integrity, budget accounting, stage transitions and security checks. Avoid tests that only mirror implementation details.
- Distinguish scientific rejection from execution failure, unresolved evidence, cancellation and budget exhaustion. Do not silently convert an unknown outcome into success.
- Preserve failed-experiment history, code/evidence provenance and independent critic calls. Do not optimize cost by deleting scientific stages.
- Keep examples public and synthetic. Never add runtime databases, actual research prompts, credentials, private paths, cluster accounts or unpublished artifacts to tests, screenshots or issues.

## Pull requests

Explain the concrete problem, resulting behavior and relevant validation. Include before/after behavior when it helps review. Link the relevant primary source when implementing paper behavior. State which assumptions or fidelity limitations changed. Passing control-flow tests does not establish research capability or publication quality.

Avoid large unrelated reformatting changes. Record integration requirements and compatibility constraints in the documentation. New public dependencies should have a compatible license and a clear need. Contributions are licensed under the repository's Apache-2.0 license.


## AI behavior artifacts

Treat `src/autoresearch/specs/` changes as behavior changes. Keep prompt instructions
outside implementation strings, increment affected versions, validate references and
role-specific structured outputs, and add adverse/repair fixtures when behavior changes.
Preserve attributed upstream prompts. Workflow edits must keep scientific feedback loops
and pass declared-edge/evidence tests. A prompt change cannot bypass a protected evaluator.
Use `uv build --wheel` followed by `AUTORESEARCH_TEST_WHEEL=dist uv run pytest tests/test_package.py`
for the installed-artifact release check. Read [docs/ai-system.md](docs/ai-system.md) before
adding handlers, tools or migration behavior.
