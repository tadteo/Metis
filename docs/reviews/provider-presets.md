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
