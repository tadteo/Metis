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
| 3 | Should-fix | Ordinary browser inventory edits could submit forged `preset` metadata. | `sanitize_inventory` keeps a stored preset only for the same ID and identity; otherwise null. Only the `add_presets` path reads the packaged catalog. Web test posts forged and modified metadata. |
| 4 | Should-fix | The observed Gemini 20 requests/day figure was shown as published. | `limits_text` appends "(observed on one account, not published)"; readiness says "Catalog figures checked". Test added. |
| 5 | Should-fix | Docs described `limits` as editable and enforced by routing, which this branch does not do. | Code comments and docs now say the free-tier figures are stored for later routing, not enforced, and editable via `settings set`/import. |
| 6 | Should-fix | Missing edge-case tests (URL override, ID collision, forged preset, stale revision, observed label). | Added; stale `add_presets` revision returns 409. Managed-remote global rejection reuses the existing guard on the same code path. |
| 7 | Nit | TUI saved a key for the local preset. | Skipped with an explicit message. The TUI action still saves the current form; noted in the plan. |
| 8 | Nit | Action labels differed (Add to Metis vs Add preset). | TUI button now reads **Add to Metis**. |
| 9 | Nit | Provider key URL was not shown in the browser. | `catalog_view` includes `key_url`; the dialog shows a "Get a … key" link when published. |
| 10 | Nit | Re-adding a disabled preset left it disabled. | Re-adding enables it; user prices and limits are retained. |
| 11 | Nit | `preset add --base-url` printed the catalog endpoint. | The summary prints the saved endpoint. |

Validation after fixes is recorded in the plan. A re-review of the fix commit is
requested before merge; merge is outside this task.
