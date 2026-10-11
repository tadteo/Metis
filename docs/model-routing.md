# Models and provider routing

Settings shows a compact **Available to Metis** inventory with Configure and Add model.
New settings include Grok and Gemini Flash. Keys are resolved separately on each
execution host from the vault, server session or environment. **Configured** means
local endpoint/key configuration is present; it does not verify account entitlement,
provider health or a real API request. Other OpenAI-compatible models can be added
by model ID, endpoint, key variable and token estimates. This is a configured list,
not live discovery of every model an account can access.

For a new run with inventory enabled, Metis selects only enabled models with local
access configuration. By default the [automatic model selection](#automatic-model-selection)
planner then chooses a primary and ordered fallbacks per role from that pool. With
`model_selection.enabled: false`, routine roles use the lowest sum of configured
input/output per-million-token estimates and critical roles retain the configured
primary if eligible, otherwise another permitted model. The existing escalation
mechanism stays inside the eligible pool. Either deterministic policy is a hypothesis,
not measured optimal routing or a quality guarantee. Routes and eligible membership are
frozen in each run. For ordinary inventory-routed
orchestration, transport failures, HTTP 429 and HTTP 5xx can trigger at most two
alternatives from that frozen permitted pool: a planned role uses its frozen plan order
(only its planned models); other roles are ordered by configured token estimates.
When alternatives exist, each candidate uses one transport attempt per output-validation
attempt; single-model pools retain configured retries. Failures
and successes are separately reserved, charged and recorded. A failed model is
skipped for 60 seconds within the current runner/stage; already-dispatched parallel
calls finish. Cooldowns reset across stages/restarts; long-window quota exhaustion
persists until its reset (see [quota-aware routing](#quota-aware-routing)). All alternatives failing leaves
a blocked checkpoint, unless [quota waiting](usage.md#wait-for-provider-quota-opt-in)
is enabled and every permitted model returned HTTP 429 or a 503 `UNAVAILABLE` overload response.
Independently of that option, the provider's own short retries for HTTP 429 and the
503 overload response honour an advertised `Retry-After` or Gemini `retryDelay`, capped
at 30 seconds per retry. Budget exhaustion and operator pause stop further dispatch.
Quota-aware routing (below) stops those retries when a quota is exhausted for a long window.
Authentication/configuration errors and malformed scientific outputs do not trigger
provider fallback. There is no claim that alternate models have equivalent quality.

Explicit panels, frontier escalation, held-out evaluators, external commands, native
writer calls and experimental comparison arms retain their fixed routes. Legacy
configurations without inventory retain their explicit behavior. Activity records
show switches, failed calls and actual successful/cache-producing models; the browser
shows an inline notice while work continues. Opening the page never retries a call.
This is a runtime behavior change for new runs; existing pinned runs are not silently
upgraded, reset or reconfigured.

Project settings offer **All available models** or **Only selected models**. An empty
or inaccessible allowed pool fails setup; it never falls back to an excluded model.
Explicit role/panel overrides outside the pool also fail. External role commands
cannot be used with restricted projects because their provider use is unverifiable.
Native manuscript search/image models must be permitted too; setup warns and the
writer blocks an incompatible restricted configuration before making calls.

Older explicit configurations stay explicit. Saving a model in the inventory enables
automatic selection for future runs. Editing advanced routing instead switches back
to explicit routing; project permissions remain and require a configured inventory.
A file with conflicting primary/inventory model identities is rejected. Appearance,
budgets, scientific gates and Laya remain independent.

The optional legacy `google-flash` recipe remains available under Advanced model
settings and for explicit configurations. It is not needed for fresh inventory setup.
The CLI equivalent is `metis settings profile google-flash`. Inspect the result with
`metis settings show`. A file can also call
`apply_model_profile(config, "google-flash")` from `autoresearch.model_profiles` and
serialize the returned `ResearchConfig`. Profile application makes no API request.

| Work | Routing added by the profile |
| --- | --- |
| Limitation extraction and initial hypotheses | Flash |
| Claim extraction and review summaries | Flash |
| Literature preparation, historian, baseline scout and novelty questions | Flash |
| Initial manuscript text through PaperOrchestra | Flash `writing_writer` override |
| Existing cheap-role policy: novelty, filtering, artifact selection | Flash if no cheap provider already exists |
| Coding, experiment design, technical answers, candidate selection, integrity and final review | Retain the primary provider and explicit overrides |
| Escalation | Retain the frontier provider; otherwise use the primary provider |

Existing role providers, panels, command adapters, cheap/frontier providers and
explicitly named PaperOrchestra models take precedence and are preserved. Applying
the recipe twice is idempotent. Advanced JSON and each run's System view expose the
resolved configuration. The profile does not claim that a configured primary model
is more capable than Flash; choose that model based on measured task performance.
Scientific iteration counts, independent critics and measured acceptance gates stay
in force. Google text routing does not replace native writer search/image workflows.

Google uses the documented compatible endpoint
`https://generativelanguage.googleapis.com/v1beta/openai`, structured JSON and medium
reasoning. Published standard estimates, checked **2026-09-30**, are $0.75 input and
$3.75 output per million tokens, including thinking in output usage. Google lists
those promotional prices through 2026-12-31; review configured rates afterward
($1.50/$7.50 is the listed January rate). Caching, tool fees and compute may change
actual invoices; estimates do not establish a total research cost.
Sources: [compatibility](https://ai.google.dev/gemini-api/docs/openai),
[model](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash),
[pricing](https://ai.google.dev/gemini-api/docs/pricing).

## Provider presets

`src/autoresearch/assets/provider_presets.json` is a versioned catalog (schema 1, catalog
`2026-10-08`) validated by `autoresearch.provider_presets.PresetCatalog`. It lists Google
Gemini (Flash models and the paid Gemini 3.1 Pro preview), Mistral La Plateforme, Groq,
Cerebras, OpenRouter free models, xAI, the paid providers OpenAI (GPT-6 Astra, GPT-6.1 Sol,
GPT-6 Luna), Anthropic Claude (Fable 5.1, Opus 5.5, Sonnet 5.5, Haiku 5.5 and legacy Haiku
4.5, through the [native adapter](#anthropic-adapter)) and DeepSeek (Flash and V4 Pro), and
a generic loopback OpenAI-compatible server. Per model it records the endpoint, model ID, key
variable, JSON-mode and streaming support, context window, maximum output, list prices,
free-tier limits (requests per second/minute/hour/day, tokens per minute/hour/day/month),
a provider-published capability note and the data-use caveat. Every number is a
`{value, source_url, checked_at}` object; anything a provider does not publish is null.
`basis: "observed"` marks a value seen in a provider response rather than on a page (the
Gemini 3.8 Flash 20 requests/day quota, from a 2026-10-08 `QuotaFailure`); every surface
labels it "observed on one account, not published". Capability
notes repeat the provider's own description and are **not** Metis measurements.

Adding a preset creates an ordinary inventory entry whose `provider` holds the request
settings and whose optional `preset` field (`ModelPreset`) carries the catalog metadata.
Each entry also gets a flat `limits` object (`ModelLimits`): `context_window_tokens`,
`max_output_tokens`, `requests_per_second|minute|hour|day` and
`tokens_per_minute|hour|day|month`, null when unpublished. Rate fields hold the
*free-tier* figures unless you add the model as **paid**. The
[request-size guard](#optional-request-size-guard) enforces `context_window_tokens` and
`tokens_per_minute` as hard limits: a request estimated above either is not sent. Free
figures are small (Groq 8,000 tokens/minute, Cerebras about 65k context), so on a paid
plan choose **Paid** when adding the provider (`--tier paid` in the CLI). Paid entries
keep the context window (the paid figure where the catalog has one) and leave rate
limits empty, because paid limits depend on your account. Other limit fields are stored
for model selection. Change any value with `metis settings set` or an imported inventory. Selection code can also read the sourced values via
`entry.preset.model` and `provider_presets.limits(model)`. Mapping rules:
unpublished JSON/streaming support maps to off; maximum output stays at or below the
Metis default (12,000); an unpublished price keeps the conservative $2/$6 default
estimate, while a loopback server is priced at zero. Re-adding a preset refreshes its
metadata, enables the model again and keeps your own price and limit edits. A
different model that happens to share the generated ID keeps its row; the new entry
gets a distinct ID. Browser edits can keep stored metadata but never supply it, and the
local preset accepts only a plain loopback address. `preset` is omitted from
serialization when absent, so saved inventories and pinned run configurations hash
exactly as before; editing a model's ID or endpoint drops its preset metadata.

Free tiers are small. Gemini publishes free limits only in AI Studio, Mistral only in its
console; Groq, Cerebras and OpenRouter publish them per model. Read the data-use caveat
before sending private research: Google's and Mistral's free tiers may use your content
to improve or train models, and OpenRouter free variants can be served by providers that
log prompts. Prices and limits change; check the source URL before relying on a figure.
The detailed source list and open questions are in
[the provider presets plan](plans/provider-presets.md) and, for the paid providers,
[the main providers plan](plans/main-providers.md).

Paid presets may also record a cache-read price, long-context prices (OpenAI above 272K input
tokens, Gemini Pro above 200k and Claude Haiku 5.5 above 100k: the higher rate applies to the
whole request) and a sourced **request shape**. The request shape says whether to send
`temperature`, which output-limit field to use, and which effort to send. OpenAI's GPT-6
models take `max_completion_tokens` and no `temperature`. DeepSeek ignores `temperature` in
its default thinking mode, so Metis omits it. Current Claude models (all except Haiku 4.5)
return HTTP 400 for a non-default `temperature`. These values are copied onto
`ProviderConfig` (`send_temperature`, `max_tokens_field`, `reasoning_effort`,
`cached_input_per_million`, `adapter`). Each field is omitted from serialization at its
default, so existing configurations hash as before. Cache reads are charged at the cached
rate, scaled like input above a long-context threshold. Without a cached rate they are
charged at the full input rate, as before. DeepSeek lists peak prices; off-peak hours cost
half, so recorded charges are an upper bound there. These providers have no free tier, so add
them as **Paid**. A free-tier entry is excluded from selection as *not offered on the free
tier*.

Capability tiers follow one scale, `light < standard < strong < frontier`. `unknown` ranks
like `standard`, the critical-role floor. Each tier is a provider claim:

| Tier | Meaning | Paid models |
|---|---|---|
| frontier | The provider's flagship or most capable line | GPT-6 Astra, Claude Fable 5.1, Claude Opus 5.5, Gemini 3.1 Pro |
| strong | Described as near-flagship | GPT-6.1 Sol, Claude Sonnet 5.5 |
| standard | No capability positioning published | DeepSeek Flash, DeepSeek V4 Pro |
| light | Efficient or high-volume models | GPT-6 Luna, Claude Haiku 5.5 and 4.5 |

## Anthropic adapter

`ProviderConfig.adapter: "anthropic"` selects `autoresearch.anthropic_provider.AnthropicProvider`.
It sends requests to the Messages API through the official `anthropic` SDK (pinned
`1.12.1`). `providers.create_provider` picks the transport for each model. Inventory,
quota-aware routing, the request-size guard and automatic model selection treat both
transports the same way.

- **Request.** The Metis system prompt is a top-level `system` block marked
  `cache_control: ephemeral`, so its unchanged bytes are reused within the five-minute cache
  window. For split-context requests the stable project/brief block is a second breakpoint.
  Metis sends no assistant prefill and no tools, and never forces `tool_choice`. It sends no
  `thinking` setting, so Opus 5.5, Sonnet 5.5, Haiku 5.5 and Fable 5.1 think adaptively and
  Haiku 4.5 runs without thinking. `reasoning_effort` becomes `output_config.effort`: `none`
  and `minimal` map to `low`; `low`, `medium`, `high`, `xhigh` and `max` pass through. The
  presets send each model's documented default explicitly: Opus 5.5 `medium`, Sonnet 5.5
  `high`, Fable 5.1 `high`, Haiku 5.5 `medium`. Haiku 4.5 gets no effort because it does not
  support one. Only Haiku 4.5 receives `temperature`. Thinking counts against the
  12,000-token output limit that presets set by default; raise `max_output_tokens` for
  models that think at length.
- **Streaming.** With `streaming` on (the preset default) the adapter streams the response
  and emits the same progress events as compatible endpoints. A stream that fails after it
  starts, or ends without `message_stop`, is *interrupted*: the estimate is charged, nothing
  is accepted and nothing is resent. An SSE `error` event is a known failure. It is still
  not resent within the request, but `overloaded_error` and `api_error` are recoverable,
  and overload is rate limited, so fallback and quota waiting apply.
- **Response.** Only `text` blocks are read; thinking blocks are ignored. The text must be
  one JSON object (one surrounding Markdown fence is tolerated). Metis requests carry no
  schema, so `output_config.format` is not used. The shared prompt instruction and the
  existing strict-parse and repair loop enforce JSON. `stop_reason: refusal` is a
  non-recoverable failure, with `stop_details.category` recorded in
  `ProviderError.details.refusal_category`. `max_tokens` counts as a truncated, invalid
  object. Anthropic's server-side refusal fallback is not enabled; Metis's own fallback
  rules apply.
- **Accounting.** Input tokens are counted as `input_tokens + cache_creation_input_tokens +
  cache_read_input_tokens`. Cache reads become `cached_input_tokens`, charged at the
  preset's cache-read price. Cache writes cost 1.25 × the input price, the published price
  for five-minute writes. Reservations use the same byte bound as other transports, which
  covers the write premium for ordinary text.
- **Errors.** The SDK's own retries are off (`max_retries=0`), so Metis's retry and
  fallback rules apply unchanged.

  | Response | Behaviour |
  | --- | --- |
  | 429 | Classified as short or long window (see [quota-aware routing](#quota-aware-routing)). Reads `retry-after` and the RFC 3339 `anthropic-ratelimit-{requests,tokens,input-tokens,output-tokens}-reset` headers. |
  | 429 spend cap (`enforced_spend_limit_reached`) | Recoverable for fallback. Never retried or waited for. The model is recorded as exhausted until the next month starts (UTC); after raising the cap, `metis resume RUN --clear-quota` clears the record. |
  | 529 `overloaded_error` | Rate limited and recoverable, eligible for quota waiting like Gemini's 503 overload. |
  | Other 5xx | Recoverable. An advertised `retry-after` (up to 30 s) is honoured. |
  | 400, 401, 403, 404, 413 | Non-recoverable. |
  | Connection errors and timeouts | Recoverable; charged at the estimate. |

  Error messages include the Anthropic request id and never the key. The key comes only
  from `credentials.resolve(api_key_env)`. The SDK never falls back to `ANTHROPIC_API_KEY`,
  profiles or proxies, and it does not follow redirects. Headers set in
  `ANTHROPIC_CUSTOM_HEADERS` are removed.
- **Manuscript writer.** PaperOrchestra calls models through the OpenAI SDK only. If a
  writer slot (`writing_writer`, `writing_reflection`, `writing_plotting` or the primary
  model they inherit) resolves to an Anthropic model, the writer preflight fails with a
  clear message. Route those roles to an OpenAI-compatible model. The writer Docker image
  does not install `anthropic`.
## Automatic model selection

Goal: the lowest expected charge and the fewest quota-bound days while critical roles
get capable models. Two parts, both recorded per run.

**Deterministic planner** (`model_selection.plan_models`; no model or network call).
It runs inside `prepare_models`, so at run creation, in `metis check` /
`metis settings check` and in the browser/TUI setup checks (`model-plan` check and a
`model_plan` summary in the readiness JSON). Routable roles are the workflow's agents
plus `model_router` (only when the router step will run) whose policy is `default` or
`cheap`. Fixed routes are listed with
their reason and never planned: inherited coding/inspection steps, held-out review,
System 1 typed advice, the native manuscript writer slots, external commands, explicit
panels and explicit role overrides; frontier escalation keeps its route.

The versioned policy (version 2) is the `selection` block of
[`policies/models.json`](../src/autoresearch/specs/policies/models.json): routine roles
(the cheap-policy roles plus the economical roles of the Google Flash profile and
`model_router`), the critical capability floor (`standard`), a context margin (1.2),
JSON-mode requirement, prompt/output token estimates per handler or role, and expected
calls per role as a factor times pipeline/coding settings (for example `novelty` =
`seed_count × critics`, coding roles = a quarter of `coding.max_steps` per session).
These are rough estimates. When the private outcome store holds at least five calls for
a role, its recorded p90 input tokens replace the estimate. Run creation uses the
store; the setup preview has no store and shows the plan without recorded outcomes, so
the frozen plan can differ slightly from the preview.

For each role and model the hard constraints are: the model is offered on the chosen
plan (a free-tier entry whose provider says *not available on the free tier* is
excluded), estimated prompt × margin + output fits the context window, prompt + output
fits tokens/minute, JSON mode is on, and for critical roles the provider-published tier
is at least the floor (`capable_routine_roles`, currently `model_router`, keep the floor
too). Unknown tiers (custom models) stay eligible and rank like `standard`. `model_selection.exclude_data_use_caveats: true` also excludes free tiers
whose provider publishes a data-use caveat. If no model fits a role's size estimates, the
size limits are relaxed (never the floor or the other constraints) with a warning, and
the [request-size guard](#optional-request-size-guard) decides each call. If still no
model qualifies, creation fails with a clear message when the floor or the data-use
setting is the cause; otherwise the role keeps the primary with a warning.

Ranking: critical roles by provider tier, then no charge before charge, then observed
failure rate, then the configured primary, then cost; routine roles by expected charge
(free and local models charge 0; paid models at their configured prices), then observed
failure rate, then tier. Roles are assigned largest first (critical before routine).
Within the best band, a model is used while its published daily quota
(`requests_per_day`, `tokens_per_day`, `tokens_per_hour × 24`, `tokens_per_month / 30`)
stays within the run's current planned days (at least one); free models in a band are
balanced by planned calls. When the preferred band is full for the day, critical work may
spill only to an equally capable band (for example the same tier on a paid plan) and
routine work to the next cheapest band, as runtime fallback would, but spill to a
charged band only while the expected charge stays within `budget.usd`; otherwise the
paid model stays a fallback and the days estimate grows. A plan whose expected charge
still exceeds the budget carries a warning (shown as a `model-plan` warning in setup). If nothing fits, the
least-loaded preferred model is chosen and the days estimate grows. Each role's frozen
order is its primary, then every other eligible model in rank order with another
provider first within a band (separate quota pools).

The plan reports, per role, class, expected calls, prompt basis, primary, fallbacks,
exclusion reasons, the reason for the choice, expected charge and list-price
equivalent; and in total, expected calls, expected charge, list-price equivalent, the
days needed when published daily quotas bind (with the binding model) and which models
publish no daily quota. Days ignore models without published daily quotas, so they are
a lower bound when such models carry work.

**Router agent** (`model_router`, agent version 1.0.0, catalog 3.4.0;
`model_selection.router` = `auto` (default: on only with at least two models in the
frozen pool), `on` or `off`). After Start/Step/Resume, before the first stage call, one
accounted, budgeted, cached `model_router` call runs on the planner's route for that
role. Its `operational` context policy sends only the explicit context: per-role class,
purpose, estimates, planner choice and eligible models; model metadata (prices, limits,
JSON mode, provider tier and capability note with source, data-use caveat); recorded
outcome summaries; totals. No research state, project specification or evidence is
sent. The validator rejects the whole answer on any unknown role, missing role, model
outside the role's eligible list, duplicate, more than two fallbacks, missing rationale,
an expected charge above both `budget.usd` and the planner's own estimate, or more
quota-bound days than the planner's plan. The request contains no endpoints or key
variable names, and outcome summaries are keyed by inventory ID. A provider failure, an invalid structured output
after repairs, a non-`accept` decision or a rejection keeps the planner's plan (the
recorded reason is privacy-redacted). Such failures never block the run. Budget
exhaustion and a pause request stop the step as for any call; the router is then tried
again on the next Start.

**Freezing and records.** Planner routes are written into the run configuration
(`role_providers` and `planned_routes`) and so into the behavior bundle. Creation stores
`model-plan.json` (planner inputs, settings, model facts, per-role scores/exclusions,
totals, warnings, observed outcomes) and a `model_plan_created` event;
`RunState.model_plan.planner` holds its artifact ID and SHA-256. The router step stores
`model-plan-refined.json` (router output, validation result, final routes, rationales)
and a `model_plan_refined`, `model_plan_router_rejected` or `model_plan_router_failed`
event; `RunState.model_plan.refinement` holds its reference and status. An applied
refinement is re-validated against the frozen `planned_routes` and its planner record
hash, and applied as an
ephemeral execution view each step (as the sealed research protocol is); the stored
configuration never changes, so behavior verification still passes. `model_plan` is
operational state, excluded from model-facing views and writer fingerprints. Quota-aware
routing is unchanged: exhausted models are skipped and the next planned model takes the
slot. The run's **AI system** view (browser, TUI, `metis system --run`) shows the final
routes, why, the source (planner or validated router) and totals.

**Observed outcomes.** Real provider calls record, per attempt, role, model identity,
outcome (`valid` with its repair attempt, `schema_invalid`, `provider_failure` or
`rate_limited`), tokens, latency and cost in the private Store table `model_outcomes`
(cross-run, not part of run exports). Inherited coding/inspection steps are recorded
under their calling role. Scripted providers, demo runs and external commands are not
recorded. Each run's private `model-plan.json` keeps the aggregated summaries for its
own pool and roles only. Quota limits are shown but never count as failures. With
at least five samples for a (role, model), or else for the model, the failure rate
(provider failures per non-quota attempt + half of first-try schema failures) moves a model down by quarter
steps within its rank. Sample counts are shown. These are operational records, not
research-quality measurements; the paper specification (D07) requires separate producer
and critic invocations, not different models, and the planner makes no claim of model
diversity or quality parity.

Example (offline, 2026-10-08 catalog, keys for Google, Mistral, Groq, Cerebras and
OpenRouter free tiers; default pipeline): Groq `gpt-oss-120b` is excluded from every
role (8,000 tokens/minute is below every estimated request); Cerebras `gpt-oss-120b`
carries short critical panels but not coding (65k context); coding and long critical
roles go to Mistral Medium (no published free quota); Gemini 3.8 Flash (20 requests/day,
observed) and OpenRouter Nemotron Super (50/day) are filled to one day; routine roles
are spread across Gemini 3.6 Flash and Mistral Small. About 446 calls, expected charge
$0, list-price equivalent about $28, one day on the models with published quotas.

If the configured primary model is unusable, the default route and (unless one is
configured) frontier escalation use the model carrying the most planned critical calls,
preferring one without a published daily quota because frontier escalation is a fixed
route without fallback.

`model_selection` is a run setting (`metis settings set model_selection.router '"off"'`),
not one of the scoped model settings inherited through workspaces and SSH parent
snapshots; set it where runs are created.

## Quota-aware routing

A 429 is either a short-window limit (per-minute requests or tokens; advertised delay
at most `SHORT_WINDOW_SECONDS` = 60 s) or long-window quota exhaustion: an advertised
delay above 60 s, a Google `QuotaFailure` violation whose `quotaId` names a daily (or
longer) window, or OpenAI-style `x-ratelimit-remaining-requests|tokens: 0` with an
`x-ratelimit-reset-*` beyond 60 s, or Anthropic's
`anthropic-ratelimit-<kind>-remaining: 0` with an RFC 3339 `-reset` beyond 60 s. Exhaustion stops in-request retries after the
first attempt and raises `ProviderError(rate_limited=True)` with an absolute
`quota_exhausted_until` and the quota id, value and metric. A daily quota with no
advertised reset, or with an advertised delay shorter than one hour, waits one hour
(`UNKNOWN_RESET_SECONDS`) and is then probed again.

Each exhaustion is stored in `RunState.model_quota_exhausted`, keyed by model identity
(endpoint, model, key reference), and recorded as a `model_quota_exhausted` event.
The record survives stages and restarts and is pruned after its reset. It is
operational state: it is excluded from model prompts, the writer fingerprint and the
writer's `raw_materials/state.json`, so it never changes a cache key. (The older
`quota_wait_*` counters are still included in prompts and writer materials; removing
them would change existing cache keys and fingerprints.) Agents running in parallel
may each spend one request on a model before the first records its exhaustion.
External command roles never call the provider, so exhaustion does not apply to them.
`metis resume RUN --clear-quota` forgets all records (for example after rotating the
key or upgrading the tier), drops a scheduled quota wait and records
`model_quota_cleared`. Fallback skips an exhausted model without sending a request
and its alternative slot goes to the next eligible model of the frozen permitted pool
in the existing cost order. When every permitted model is exhausted, the error carries
the earliest reset, and an enabled quota wait schedules the next attempt then (capped
by `max_interval_seconds`); a capped wake-up only reschedules. The first call after a
wait is a single-attempt probe (the flag is consumed by that first dispatch; later
calls in the step retry normally), so its reservation is one attempt, not `retries + 1`.
Rejected attempts are settled as before: once each, at the conservative request
estimate when the response reports no usage.

Fixed routes are never swapped. If a protected route's model (explicit panel,
frontier escalation, held-out evaluator, external command, explicit configuration
without inventory) is exhausted, no request is sent and the call fails with a
non-recoverable rate-limited error: the run waits for that model's reset when quota
waiting is enabled, otherwise it blocks for an explicit Resume.

### Optional request-size guard

If a model declares token limits, a request whose estimated input (request bytes / 4,
`BYTES_PER_TOKEN`) exceeds the model's context window or tokens-per-minute quota is
not sent. A `model_request_oversized` event is recorded and fallback tries the next
permitted model. If no permitted model fits, the run blocks with a clear error; it
never waits for a quota that cannot help. Without metadata the guard is inactive.
The estimate is a heuristic, not a tokenizer count.

Metadata interface (read defensively by `routing.model_limits`; all fields optional):
positive integers `context_window_tokens` and `tokens_per_minute` on the model's
`ProviderConfig` or its inventory entry, either directly or under a `limits`
mapping/object. Aliases `context_window`, `max_input_tokens`,
`input_tokens_per_minute` and `tpm` are accepted. Inventory entries added from a
[provider preset](#provider-presets) carry `limits.context_window_tokens` and
`limits.tokens_per_minute`, so the guard is active for them.

## Laya

Open **System 1 → Laya → Configure** and enter an
existing service address, checkpoint/model name and estimated request cost. The
default address is loopback on the **Metis server host**; for an SSH workspace it
means the remote host. These controls do not install or start a Laya server.
An authenticated service can use the separate optional API key field, or the
configured environment reference. Unauthenticated local services need no key.

Laya supplies typed advice to idea filtering and artifact selection. It cannot
write hypotheses, code or manuscripts, approve a result, or skip the normal reasoning
agent. Failures retain their receipts and follow the normal reasoning path. Enabling
it can add cost and latency; savings are unmeasured. See [the typed contract](laya.md).

For CLI setup, use `metis settings set laya.base_url '"http://127.0.0.1:8000"'`
and `metis settings set laya.enabled true` once a service is available. Retain
configured `laya` settings when applying the Google profile; it never enables Laya
implicitly.

## Validation boundary

Offline tests exercise the Google HTTP envelope/accounting, routing inheritance,
custom override preservation, saved-setting isolation, Laya session credentials and
advisory fallback, and quota-aware routing with mocked 429 bodies modeled on the
redacted 2026-10-07 Gemini responses. No such test establishes live endpoint access, research quality
or cost savings. Evaluate matched public tasks and report all failures plus compute
billing before recommending a cheaper policy as equivalent.

See [settings inheritance](settings-inheritance.md) for local/SSH defaults and project overrides.
