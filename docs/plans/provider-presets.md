# Provider presets with user key entry

Base `07db7c5` (main). Branch `codex/provider-presets`, worktree `Metis-provider-presets`.

## Requirement

The user has no model budget and wants to run Metis on the free tiers of several
providers, entering a separate key for each. A later task (C) will choose models per
agent for price and performance; it needs machine-readable metadata. This task supplies
that metadata and the setup flows. It does not change routing, retries or quota waiting.
A concurrent branch (`codex/quota-aware-routing`) owns `providers.py`, `agents.py`,
`routing.py` and `quota_wait.py`; none of those files is edited here.

## Boundary and interface

- Catalog: `src/autoresearch/assets/provider_presets.json` (schema 1, catalog date
  2026-10-08), validated by `PresetCatalog` in `src/autoresearch/provider_presets.py`.
  It sits in `assets/`, not `specs/`, so it does not alter the AI behavior catalog digest.
- Every number and request flag is `Sourced{value, source_url (HTTPS), checked_at, basis,
  note}`. Unknown values are null. `basis: "observed"` requires a note describing the
  observation. A check date later than the catalog version is rejected.
- `AvailableModel.preset: ModelPreset | None` carries `catalog_version`, provider id,
  label, `key_required`, key URL, data-use caveat and the full `PresetModel`. It is
  excluded from serialization when null, so existing saved inventories and pinned run
  configurations (whose behavior bundle hashes `config.model_dump`) are unchanged.
- `AvailableModel.limits: ModelLimits | None` (also omitted when null) holds flat
  limits copied from the preset (free-tier rate figures; not enforced on this branch): `context_window_tokens`,
  `max_output_tokens`, `requests_per_second|minute|hour|day`,
  `tokens_per_minute|hour|day|month`. Names follow the coordinator's interface note
  for `routing.model_limits` on `codex/quota-aware-routing` (reads
  `limits.context_window_tokens` and `limits.tokens_per_minute`); that branch is not
  edited here. Re-adding a preset fills `limits` only when the entry has none.
- Read interface for routing/quota work: `entry.preset.model.free_tier`,
  `entry.preset.model.context_window`, `provider_presets.limits(model)` →
  `{requests_per_second, requests_per_minute, requests_per_hour, requests_per_day,
  tokens_per_minute, tokens_per_hour, tokens_per_day, tokens_per_month}` with `None` for
  unknown, and `entry.preset.model.capability` (provider-published, never measured).
- Mapping (`to_entry`): unknown JSON mode/streaming → off; max output ≤ 12,000 (Metis
  default); unpublished remote price → $2/$6 default estimate; loopback → $0, no key.
  `add_to_inventory` refreshes metadata on an identical endpoint/model/key identity and
  keeps the user's own prices, limits and enabled state.
- Shared rules: `preset_changes` (browser and TUI), `summary`/`catalog_view` (CLI,
  browser), `preset_options`/`preset_detail` (TUI), `inventory_checks` (readiness).

## Surfaces

- Browser: **Settings → Available to Metis → ＋ Add provider**. Provider picker, literal
  data-use caveat, provider notes, per-model checkboxes with price, context, free-tier
  limits and provider description; one key field per provider, stored through the
  existing `/api/credentials` (vault or server session). The server maps references
  from the packaged catalog (`add_presets`), so browser input never supplies metadata.
  Inventory rows show published limits. Configure keeps metadata only while the model
  ID and endpoint are unchanged.
- TUI: **Settings → Model → Provider presets** picker, detail text, custom model ID
  (local), password key field, vault/session choice, **Add preset**.
- CLI: `metis settings preset list [--json] | show REF [--json] | add REF [--base-url URL]
  [--no-key] [--scope …]`. Key prompt is hidden, interactive only, and saved to the host
  vault; otherwise the user is told how to add it.
- Readiness: `preflight` adds `model:<id>` checks per enabled inventory model: key
  present/missing (no network), published limits, data-use caveat, catalog date.
  Missing keys are warnings; an empty usable pool remains the existing error.

## Sources (all checked 2026-10-08)

Research was delegated to three read-only agents using WebFetch/WebSearch on official
pages. WebFetch summarises pages, so short quotes were checked by a second fetch where
numbers looked suspicious (identical Gemini 3.6–3.8 Flash prices were confirmed twice).
Mistral figures were read from the raw HTML pricing objects of the model pages because a
summary had reported the cached price as the input price.

- Google: <https://ai.google.dev/gemini-api/docs/openai>, `/docs/models`,
  `/docs/models/gemini-3.8-flash`, `-3.7-flash`, `-3.6-flash`, `-3.5-flash`,
  `-3.5-flash-lite`, `/docs/pricing`, `/docs/rate-limits`, <https://ai.google.dev/gemini-api/terms>.
- Mistral: <https://docs.mistral.ai/models/mistral-small-4-0-26-03>,
  `/models/mistral-medium-3-5-26-04`, `/models/mistral-large-4-0`, `/models/codestral-25-08`,
  <https://docs.mistral.ai/capabilities/structured_output/json_mode>, <https://docs.mistral.ai/api>,
  <https://help.mistral.ai/en/articles/698531-why-am-i-hitting-api-rate-limits-and-how-do-i-increase-them>,
  <https://help.mistral.ai/en/articles/347617-do-you-use-my-user-data-to-train-your-artificial-intelligence-models>.
- Groq: <https://console.groq.com/docs/models>, `/docs/rate-limits`, `/docs/structured-outputs`,
  `/docs/your-data`, `/docs/model/openai/gpt-oss-120b`, `/openai/gpt-oss-20b`,
  `/qwen/qwen3.8-27b`, `/llama-3.3-70b-versatile`.
- Cerebras: <https://inference-docs.cerebras.ai/support/rate-limits>,
  `/models/openai-oss`, `/models/qwen-3.8-27b`, `/capabilities/structured-outputs`,
  <https://www.cerebras.ai/privacy-policy>.
- OpenRouter: <https://openrouter.ai/docs/api-reference/limits>,
  <https://openrouter.ai/docs/guides/privacy/provider-logging>, <https://openrouter.ai/api/v1/models>.
- xAI: <https://docs.x.ai/docs/models>, <https://docs.x.ai/docs/models/grok-4.7>,
  <https://docs.x.ai/docs/guides/structured-outputs>.
- Local: <https://docs.ollama.com/api/openai-compatibility> (vLLM and LM Studio default
  ports from their OpenAI-compatibility pages, recorded as notes).

Failed or unusable fetches (preserved): `ai.google.dev/.../gemini-3.8-flash-lite` (404;
no 3.6–3.8 Flash-Lite exists), `docs.mistral.ai/deployment/laplateforme/tier/` (404),
`mistral.ai/pricing` (no per-model API prices; a generic Large line conflicts with the
model page, which is used), `groq.com/pricing` (prices not rendered),
`inference-docs.cerebras.ai/support/pricing` (redirect without per-model prices),
`x.ai/legal/faq-enterprise` (403).

## Findings that differ from the brief

- Gemini free-tier limits are not published on any docs page (AI Studio only). Only the
  user's live observation (20 requests/day for gemini-3.8-flash, quota id
  `GenerateRequestsPerDayPerProjectPerModel-FreeTier`) is recorded, as `observed`. The
  `gemini-flash-latest` alias is documented without a target; the 3.8 mapping is the
  user's observation. Google lists 2.5 models as limited to earlier users.
- Flash-Lite variants: only `gemini-3.5-flash-lite` and `gemini-3.1-flash-lite` exist;
  3.1's model page was not checked, so its context/output/JSON fields are null.
- Mistral's docs now call the free plan **Free mode**. The help centre says Mistral *may*
  train on Free-mode inputs/outputs and offers an opt-out in Admin → Privacy; it does not
  say opting in is required. Numeric Free-mode limits appear only in the console (null).
  Mistral does not publish maximum output tokens (null). Magistral and Devstral are retired.
- Groq's free plan covers gpt-oss-120b/20b and qwen3.8-27b (30 RPM, 1K RPD, 8K TPM,
  200K TPD). `llama-3.3-70b-versatile` is Enterprise-tier ("Contact Sales"): included but
  marked not available on the free tier, with an unpublished price.
- Cerebras now lists only gpt-oss-120b and qwen-3.8-27b; the brief's llama/qwen-235b/
  zai-glm models are deprecated. Context and output values are published rounded
  ("65k", "32K"); the catalog stores the lower reading with a note.
- OpenRouter: 20 requests/minute; 50 requests/day, 1,000/day after buying at least 10
  credits. The selected `:free` models come from the live models API and change often;
  Dots3-Note lists an expiry of 2026-12-31. Nemotron 3 Ultra and North Mini Code do not
  accept `response_format`, so JSON mode maps to off.
- xAI: no free tier or credit programme found in current docs; grok-4.7 $2/$6 applies
  below 200k prompt tokens ($4/$12 at or above). Max output not published.

## Acceptance criteria

1. Catalog validates; every numeric value is sourced and dated or null (test walks raw JSON).
2. Preset → inventory mapping, metadata retention, user-edit preservation.
3. Keys never in settings files (CLI and TUI tests scan state files for the synthetic key;
   browser test asserts the inventory request excludes it).
4. CLI list/show/add/scoped add, browser API and dialog, TUI add flow.
5. Legacy inventories and pinned configs serialize byte-for-byte as before.
6. Readiness reports key present/missing, limits and caveats without network calls.

## Validation record

Focused: `tests/test_provider_presets.py` 14 passed; web preset/inventory 3 passed; browser
suites 108 passed (one initial failure: a test redeclared the `presetCatalog` global;
fixed in the test). First catalog-walk test failed because booleans are ints in Python;
configuration booleans (`key_required`, `custom_models`) are excluded while request flags
remain sourced objects. Two first-draft test expectations were wrong (an incomplete CLI
command returns exit 1, not argparse exit; the built-in Flash entry keeps its hashed ID
and gains metadata) and were corrected to the intended behavior.

Visual evidence (synthetic state, null keyring, no provider calls) under
`docs/evidence/provider-presets/`: browser inventory and Add provider dialog at
1280×860 in charcoal and cream, the key section, the inventory after saving a synthetic
session key (Groq row changes to Configured; the key string was absent from every state
file), and 390×844 narrow views (no horizontal overflow, scrollWidth 390). The dialog
opens with focus on the provider picker (visible terracotta focus ring); after save the
inventory reloads through `openInventory`, which focuses the settings title.
TUI SVGs at 80×24 and 120×40 in both themes show the Model section preset picker and
detail text; at 80×24 the panel scrolls within the settings area.

Repository checks at `870fcc7`: Ruff format (174 files) and lint pass; mypy 88 source
files; specs valid (48 agents / 29 stages); browser suites 108 passed; public-file scan
passes (it first flagged the test's synthetic key name, renamed to a `fake-` value);
full pytest 1186 passed, 4 skipped; installed-wheel check 1 passed; isolated offline
demo exit 0. Earlier full runs at the feature commit: 1178 passed, 4 skipped (twice).
Review findings and resolutions: [review](../reviews/provider-presets.md).

## Open risks

- Free-tier figures drift; the catalog is dated and must be re-checked. Account-level
  limits (Gemini, Mistral) remain unknown to Metis until task C or the quota work
  observes them.
- Selection by price would prefer $0 OpenRouter models for routine roles; task C should
  weigh limits and capability, not only price.
- OpenRouter free models lacking JSON mode rely on prompt-only JSON; output validation
  failures are expected to be higher.
- Groq json_object mode with streaming is not explicitly documented.
- Independent review is required before merge (not self-certified here).

After the re-review fix (`3328372`): format, lint, mypy, browser suites (108), public scan
and full pytest (1188 passed, 4 skipped) pass again.
