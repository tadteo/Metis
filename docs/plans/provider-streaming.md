# Stream long model responses

Base a21841f. User requests provider-supported progress and protection against losing
long Grok responses at the three-minute read timeout. Official xAI and Gemini docs
support chat SSE with usage. xAI also has deferred one-shot retrieval within 24 hours;
that is not recovery for our historical synchronous requests, which have no ID.

Use existing CompatibleProvider HTTP transport, structured-output validation and ledger.
Enable configurable streaming for compatible providers; accept ordinary JSON from servers
that ignore it. New provider defaults allow 3600 seconds of network inactivity, following
xAI reasoning guidance. Saved configuration and behavior are not silently rewritten.
Persist throttled response IDs and received-character counts in the private journal,
linked to the reservation. Save the accumulated answer once on completion/interruption
so secret redaction works across chunk boundaries; progress events contain no text. Never expose reasoning text; record its presence only.
Show progress inline in the existing research notice. EOF without DONE/finish or length
termination cannot become accepted research. Interrupted streams retain partial evidence,
settle unknown costs conservatively and do not silently regenerate after output began.
No new dependency, polling service, prompt pruning or scientific-gate changes.

Offline checks: real HTTP transport with SSE fragments, usage-only final event, comments,
malformed/truncated/disconnected streams, reasoning-only progress, configured timeout,
no retry after partial output, journal linkage and escaped inline progress. Run affected
and repository checks, independent review, commit and merge. Preserve original attempts.
Runtime changes require an explicit continuation; no paid retry during implementation.
Sources checked 2026-10-01:
- https://docs.x.ai/developers/model-capabilities/text/streaming
- https://docs.x.ai/developers/model-capabilities/text/reasoning
- https://docs.x.ai/developers/advanced-api-usage/deferred-chat-completions
- https://ai.google.dev/gemini-api/docs/openai

## Validation and scope

The initial SSE fixture failed with invalid/truncated JSON in the non-streaming transport.
Independent review found interim-usage undercharging and split-fragment redaction;
both were corrected and regression-tested. Reviewer approved the resulting transport.
The first full-suite run was stopped to apply those fixes. A later callback annotation
was made explicit for mypy; focused transport/behavior/agent checks passed afterward.

Actual synthetic page rendering was inspected at desktop and 390px in cream and
charcoal. The existing inline notice wraps, with run controls, costs and navigation
still visible. No modal, page replacement, new interactive element or focus change.
Progress contains status/counts/ID; accumulated answer text is saved only at completion
or handled interruption. Abrupt process death can lose in-memory answer text.

Full run: 1076 passed, 3 skipped, one behavior-identity guard failure when the callback
annotation changed during that test. The guard was preserved; the exact test was
rerun on stable source. Browser suite: 104 passed. Types, lint, format, specifications,
public scan, installed wheel test and isolated synthetic demo passed.
