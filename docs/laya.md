# Laya typed advice

Laya is an optional advisory decision service. Its published non-generative API is
`POST /v1/systemone`, with `state`, typed `questions`, `model` and `max_len` fields.
The adapter follows the [official HTTP server](https://github.com/NandhaKishorM/laya/blob/main/laya/serve.py)
and [typed answer documentation](https://github.com/NandhaKishorM/laya#self-hosting-http-server-jev-compatible),
checked on 2026-09-29. It does not pretend Laya can generate scientific prose or code.

`laya.enabled` adds a `noul` probability about whether an idea-filtering or artifact-selection
decision requires deeper reasoning. Every normal reasoning agent still runs and judges the
scientific evidence. An unavailable service or malformed answer records a failed advisory
attempt and falls back to that reasoning path. This is an engineering routing extension,
not a claim that Laya was used in ScientistTwo or matches its scientific capability.

The client also validates public `choice` and `score` answer types. Numeric probabilities
must be finite numbers in [0,1], scores must stay within their declared ordered criteria,
and choices must name a declared option. Booleans, strings posing as numbers and invalid
usage blocks are rejected. Extra upstream routing/diagnostic metadata is retained.
The configured per-call cost is reserved before the request and settled even after an HTTP
or response-validation failure. Missing token usage remains explicitly estimated; configured
costs are estimates rather than provider invoices.

Credentials use the configured environment reference and optional bearer authentication.
Endpoints require HTTPS except on loopback. Requests do not follow redirects or environment
proxies. Run privacy redaction is applied before transport, and `privacy.cache=false` disables
advisory response caching. Cache identities include the run and scientific input. Oversized
state is refused locally rather than truncated by this adapter; upstream tokenizer behavior
still depends on its checkpoint and token limits.

Preflight validates optional Laya endpoint/credential syntax without making an API call.
Warnings preserve the normal reasoning fallback. Writer setup gaps similarly remain visible
warnings because initial research can proceed before manuscript stages; `ready` establishes
local startup readiness, not full-pipeline or remote-service readiness. Optional Docker probes
require nonempty successful daemon and image responses. No images are pulled or jobs submitted.

`tests/test_laya.py` uses the real HTTP transport with mocked responses and exercises an actual
AgentRunner critic panel after advisory failure. These are contract/accounting tests, not a live
inference-quality or scientific-capability measurement.

Model access now exposes the enable switch, service address, model, credential
reference and estimated request charge. **Key for → Laya** uses the same host
vault/session credential resolution as ordinary providers, with environment fallback.
An unreadable vault becomes a failed advisory attempt; no secret is written into
configuration. The [Google routing profile](model-routing.md) preserves Laya settings
and keeps every scientific reasoning call.
