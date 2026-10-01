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
calls finish. Cooldowns reset across stages/restarts. All alternatives failing leaves
a blocked checkpoint. Budget exhaustion and operator pause stop further dispatch.
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
advisory fallback. No such test establishes live endpoint access, research quality
or cost savings. Evaluate matched public tasks and report all failures plus compute
billing before recommending a cheaper policy as equivalent.

See [settings inheritance](settings-inheritance.md) for local/SSH defaults and project overrides.
