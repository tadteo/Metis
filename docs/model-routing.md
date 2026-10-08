# Google Flash, the primary model, and Laya

Settings shows a compact **Available to Metis** inventory with Configure and Add model.
New settings include Grok and Gemini Flash. Keys are resolved separately on each
execution host from the vault, server session or environment. **Configured** means
local endpoint/key configuration is present; it does not verify account entitlement,
provider health or a real API request. Other OpenAI-compatible models can be added
by model ID, endpoint, key variable and token estimates. This is a configured list,
not live discovery of every model an account can access.

For a new run with inventory enabled, Metis selects only enabled models with local
access configuration. Routine roles use the lowest sum of configured input/output
per-million-token estimates. Critical roles retain the configured primary if eligible,
otherwise another permitted model. The existing escalation mechanism stays inside the
eligible pool. This deterministic cost policy is a hypothesis, not measured optimal
routing or a quality guarantee. Routes and eligible membership are frozen in each run. For ordinary inventory-routed
orchestration, transport failures, HTTP 429 and HTTP 5xx can trigger at most two
alternatives from that frozen permitted pool, ordered by configured token estimates.
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

## Quota-aware routing

A 429 is either a short-window limit (per-minute requests or tokens; advertised delay
at most `SHORT_WINDOW_SECONDS` = 60 s) or long-window quota exhaustion: an advertised
delay above 60 s, a Google `QuotaFailure` violation whose `quotaId` names a daily (or
longer) window, or OpenAI-style `x-ratelimit-remaining-requests|tokens: 0` with an
`x-ratelimit-reset-*` beyond 60 s. Exhaustion stops in-request retries after the
first attempt and raises `ProviderError(rate_limited=True)` with an absolute
`quota_exhausted_until` and the quota id, value and metric. A daily quota with no
advertised reset uses one hour (`UNKNOWN_RESET_SECONDS`) and is then probed again.

Each exhaustion is stored in `RunState.model_quota_exhausted`, keyed by model identity
(endpoint, model, key reference), and recorded as a `model_quota_exhausted` event.
The record survives stages and restarts and is pruned after its reset. It is
operational state: it is excluded from model prompts and writer fingerprints, so it
never changes a cache key. Fallback skips an exhausted model without sending a request
and its alternative slot goes to the next eligible model of the frozen permitted pool
in the existing cost order. When every permitted model is exhausted, the error carries
the earliest reset, and an enabled quota wait schedules the next attempt then (capped
by `max_interval_seconds`); a capped wake-up only reschedules. The first call after a
wait is a single-attempt probe, so its reservation is one attempt, not `retries + 1`.
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
`input_tokens_per_minute` and `tpm` are accepted. The inventory schema does not yet
define these fields; the provider preset catalog is expected to supply them.

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
