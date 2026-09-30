# Google Flash, the primary model, and Laya

The opt-in `google-flash` profile adds Gemini 3.8 Flash alongside the configured
primary model (Grok by default). It is a cost/quality hypothesis, not a measured
optimal policy. Existing runs keep their recorded configuration.

On the **Settings** page, choose **Global defaults**, a workspace or a project, then **Open scope** and **Add Google Flash routing**. Enable the routing override first for a non-global scope. This updates
the form only. Select **Google Gemini** under **Key for** to connect `GEMINI_API_KEY`,
then save settings for future runs. Primary and Google keys use the existing host
vault/session options. A missing Google key is a readiness error; it never silently
routes paid requests to another provider.

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

Enable **Use Laya for optional decision advice** in Model access and enter an
existing service address, checkpoint/model name and estimated request cost. The
default address is loopback on the **Metis server host**; for an SSH workspace it
means the remote host. These controls do not install or start a Laya server.
An authenticated service can use a saved Laya key selected under **Key for**, or the
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
