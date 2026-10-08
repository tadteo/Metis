# Review: provider presets

Branch `codex/provider-presets`, base `07db7c5`, reviewed range `07db7c5..0430f97`.
Reviewer: an independent read-only review agent (not the implementing agent). It made no
edits or provider calls and reran the focused Python, web and browser suites.

Initial verdict: **request changes**. Backward compatibility (fields omitted when null,
unchanged behavior hashes), save paths, authentication, key isolation, catalog provenance,
copy and accessibility were found sound.

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | Blocking | A custom `base_url` on the local preset was not validated: a remote address was priced at $0 with no key, and URL userinfo reached settings. | `loopback_endpoint` requires an http(s) loopback host without userinfo, query or fragment; `to_entry` enforces it for every surface. Tests cover remote, userinfo, query and scheme cases. |
| 2 | Should-fix | `add_to_inventory` matched by ID *or* identity, so a colliding ID could relabel an unrelated endpoint and drop another row. | Matches by identity only; a colliding ID gets a `-2` suffix; no row is dropped. Test added. |
| 3 | Should-fix | Ordinary browser inventory edits could submit forged `preset` metadata. | `sanitize_inventory` keeps a stored preset only for the same ID and identity; otherwise null. Applied on `/api/settings/inventory`, and after re-review also on `/api/settings/models` and `/api/settings` (finding A). Only the `add_presets` path reads the packaged catalog. Web tests post forged and modified metadata to all three endpoints. |
| 4 | Should-fix | The observed Gemini 20 requests/day figure was shown as published. | `limits_text` appends "(observed on one account, not published)"; readiness says "Catalog figures checked". Test added. |
| 5 | Should-fix | Docs described `limits` as editable and enforced by routing, which this branch does not do. | Code comments and docs now say the free-tier figures are stored for later routing, not enforced, and editable via `settings set`/import. |
| 6 | Should-fix | Missing edge-case tests (URL override, ID collision, forged preset, stale revision, observed label). | Added; stale `add_presets` revision returns 409. Managed-remote global rejection reuses the existing guard on the same code path. |
| 7 | Nit | TUI saved a key for the local preset. | Skipped with an explicit message. The TUI action still saves the current form; noted in the plan. |
| 8 | Nit | Action labels differed (Add to Metis vs Add preset). | TUI button now reads **Add to Metis**. |
| 9 | Nit | Provider key URL was not shown in the browser. | `catalog_view` includes `key_url`; the dialog shows a "Get a … key" link when published. |
| 10 | Nit | Re-adding a disabled preset left it disabled. | Re-adding enables it; user prices and limits are retained. |
| 11 | Nit | `preset add --base-url` printed the catalog endpoint. | The summary prints the saved endpoint. |

## Re-review (`0430f97..870fcc7`)

Verdict: **approve with fixes**. Findings 1, 2 and 4–11 verified fixed; no regressions
found (catalog path correctly bypasses sanitizing, stale revisions still conflict,
legacy serialization unchanged). Remaining:

| # | Severity | Finding | Resolution |
|---|---|---|---|
| A | Should-fix | `/api/settings/models` and `/api/settings` still accepted forged `preset` objects. | Both handlers sanitize against the stored scope inventory before saving (handlers only; CLI/TUI legitimately add presets through the save functions). Tests added for both. |
| B | Nit | TUI identified the local preset by its ID. | Uses `find(reference)[0].key_required`. |
| C | Nit | No test for `add_presets` on managed-remote global defaults. | Test asserts HTTP 400 with the managed message. |

`/api/settings/parent` (managed remote receiving the controller's global snapshot) is
left unchanged: its sender is the local console, which builds metadata from the
catalog. Merge is outside this task.

## Final verification (`870fcc7..de250af`, merge into `main` at `68dcec2`)

Verifier: an independent read-only agent (not the implementer). No source edits, no
provider calls, no credentials read. A throwaway merge worktree branched from `main`
(`68dcec2`) merged `codex/provider-presets` (`de250af`) with `--no-ff`; it was removed after
verification.

Verdict: **fix first** (one should-fix regression, V1, plus a doc fix at merge, V2).
Commit `3328372` correctly resolves A, B and C.

**3328372 / finding A.** `/api/settings/models` (`web.py:568-576`) and `/api/settings`
(`web.py:624-633`) now pass the incoming inventory through `_catalog_metadata_only` →
`sanitize_inventory` (`provider_presets.py:335`). A stored `preset` is kept only for the same
ID and identity; otherwise it is dropped. `/api/settings/inventory` sanitizes too, and only
`add_presets` reads the packaged catalog. `/api/settings/model-profile` and
`/api/settings/validate` do not persist. `/api/settings/parent` (`web.py:595`) is not sanitized,
but it is **not exploitable**. It needs the per-tunnel bearer token (`remote.py:876`), and a
token holder can already write the same values through `/api/settings`. The sender's global
row was sanitized when written. `preset` is used only for display and provenance on this
branch (`setup.py:487`, TUI, browser). Not a merge blocker; optionally sanitize it later for
defense in depth. Note: sanitizing never covers `limits` or prices. That is by design, because
they are user-editable (finding 5). So "forged" limits or prices from an authenticated caller
are ordinary user edits, not privilege escalation. Nit: server-side sanitizing drops `preset`
but keeps `limits` when an entry's identity changes through a raw API post. The browser
dialog drops both (`model-inventory.js:116`).

| # | Severity | Finding | Required change |
|---|---|---|---|
| V1 | Should-fix (regression) | Each preset entry serializes to ~3.4 KB. With the full catalog (22 models) added, the browser's inventory edit body is 75,870 bytes. Non-run requests are capped at 64 KiB (`web.py:243`). Reproduced in the merged tree: `add_presets` with all references → 200; any later `/api/settings/inventory` or `/api/settings/models` edit with that inventory → 400 "Request body exceeds the 65536 byte limit". `/api/settings` and the managed-remote `/api/settings/parent` sync (`remote.py:865`) use the same limit, so sync reports "pending: update the remote runtime". The threshold is about 19 preset models; `ModelInventory` allows 100. | Raise the body limit for settings endpoints. 100 entries × ~3.5 KB ≈ 350 KB, so ~1 MiB fits. Alternatively, have the browser omit `preset`; the server already restores it from storage. Parent sync would still need the larger limit. Add a web test that saves an inventory holding every catalog model. |
| V2 | Should-fix (at merge) | `docs/model-routing.md` conflicts (both sides add a section; keeping both resolves it). After the merge, the presets text "Nothing in this change enforces them" is false: quota routing's `_guard_size` reads `limits.context_window_tokens`/`tokens_per_minute`. The routing text "The inventory schema does not yet define these fields" is stale too. | Resolve by keeping both sections. State that the context window and TPM in `limits` feed the request-size guard, and that the other rate fields remain unenforced. |
| V3 | Should-fix (docs/behavior) | Preset `limits` copy free-tier figures, e.g. Groq TPM 8,000 and the Cerebras free context of 65,000 (131k paid). After the merge, the guard enforces them as hard limits. A paid-key user gets requests above ~32 KB refused on Groq models (`model_request_oversized`, then fallback or a block) until they edit `limits` via `metis settings set`. | Document this in the merged routing/presets text and the add confirmation. Later, add a tier choice or clear the free-tier TPM/context for paid keys. Not a merge blocker. |

**Interface between branches.** No glue is needed. `to_entry` sets
`AvailableModel.limits` (`provider_presets.ModelLimits`; `model_inventory.py:31`). It serializes
when non-null and round-trips through `ResearchConfig`. `routing.model_limits` (main,
`routing.py:142`) matches the inventory entry by `identity()` and reads `getattr(entry,
"limits")`. It finds `context_window_tokens`/`tokens_per_minute` there, and `_guard_size`
(`agents.py:861`) calls it with the run config. Probe in the merged tree, with
`groq:openai/gpt-oss-120b` added and set as `provider`:
`ModelLimits(context_window_tokens=131072, tokens_per_minute=8000)`. Without an inventory:
`None/None`. The two `ModelLimits` classes share a name in different modules, so there is no
clash.

**Merged-tree checks.** `uv sync --frozen --group dev --extra evaluation`; `ruff check`
passed; `ruff format --check` passed (175 files); `mypy src` passed (88 files). Ran
`metis validate-specs` and `scripts/scan_secrets.py`; the secret scan passed.
`node --test tests/*_ui.mjs` 108/108. Focused pytest
(`test_provider_presets`, `test_quota_aware_routing`, `test_web`, `test_model_inventory`,
`test_model_settings`, `test_settings`, `test_provider_quota_wait`): 191 passed. Full pytest:
1214 passed, 4 skipped (6 min 13 s). The full suite ran before the V1 probe test was added; the probe was then deleted.

**Catalog spot-check** (public pages fetched 2026-10-08). Groq rate-limits page:
gpt-oss-120b free 30 RPM, 1K RPD, 8K TPM, 200K TPD, matching the catalog. Cerebras
rate-limits page: gpt-oss-120b 5 RPM and 30K TPM (uncached), matching. Mistral Small 4 page:
256k context and $0.15/M input, matching.

### Author resolution

| # | Resolution |
|---|---|
| V1 | Settings endpoints (`/api/settings` and `/api/settings/*`, including `parent`) accept up to 1 MiB (`SETTINGS_BODY_BYTES`); other non-run endpoints keep 64 KiB. Tests save an inventory holding every catalog model through `/api/settings/inventory` (add and edit), `/api/settings/models` and `/api/settings`, and sync that >64 KiB global snapshot to a managed server via `/api/settings/parent`; another test pins the 64 KiB limit elsewhere. |
| V2 | Merged `main` (`68dcec2`) in `87bd6c0`, keeping both `docs/model-routing.md` sections. The presets text now says the request-size guard enforces `context_window_tokens` and `tokens_per_minute` as hard limits and the other rate fields are stored for selection; the routing text says preset entries carry those fields. |
| V3 | Added a per-add **Plan** choice (browser select, TUI select, CLI `--tier free|paid`, web `tier`). Paid entries store `preset.tier = "paid"`, no rate limits, and the paid context window where cataloged (`paid_context_window`, added for Cerebras: 131k / 128K, sourced). Re-adding with another plan replaces limits only if the user had not edited them. Limit text reads "Paid plan: rate limits depend on your account". Documented in usage and routing guides. |
| Nit | `sanitize_inventory` drops `limits` together with `preset` when a preset entry's identity changes through the raw API. Tested. |
