# Main paid model providers: OpenAI, Anthropic, Gemini Pro and DeepSeek

Base: `main` at `7c34a8d` (the task brief named `d9357f3`, an ancestor of that commit).
Branch: `codex/main-providers`, isolated worktree `Metis-main-providers`.

## Requirement and boundary

Add the main paid providers to the preset catalog, with every number sourced: OpenAI,
Anthropic Claude through a native adapter, Google's paid Gemini Pro model next to the
existing Flash presets, and DeepSeek. Add per-model request-shape flags where current models
reject `temperature` or need `max_completion_tokens`. Add a native `AnthropicProvider` that
implements the existing `Provider` protocol and takes part in inventory, quota-aware routing,
the request-size guard and automatic model selection without changes to those modules.

Out of scope: model selection profiles (`paper-faithful` / `budget`). The coordinator removed
them from this task on 2026-10-08. A separate spec on `codex/model-selection-controls` covers
them. Capability tiers use the existing scale `light < standard < strong < frontier`
(`unknown` ranks like `standard`), with basis `provider-published`. Live provider calls are
also out of scope. Every test uses mock transports.

Owned files: `providers.py`, the new `anthropic_provider.py`, `contracts.ProviderConfig`,
`provider_presets.py` and its JSON catalog, the `create_provider` wiring in `agents.py`,
`model_inventory.py`, `setup.py` and `onboarding.py`, the writer preflight and worker guard,
docs, and tests.

## Design

- **`ProviderConfig`** has four new fields. Each one is left out of serialization when it
  holds its default, so saved inventories, pinned run configurations and writer
  fingerprints hash exactly as before:
  - `adapter`: `openai_compatible` or `anthropic`.
  - `send_temperature`.
  - `max_tokens_field`: `max_tokens` or `max_completion_tokens`.
  - `cached_input_per_million`.
- **Presets.**
  - `PresetProvider.adapter` sets the transport.
  - `PresetModel` gains these optional fields, each also left out when absent:
    - `cached_input_per_million`.
    - `long_context_threshold`, with long input and output prices.
    - A sourced `request` shape: `send_temperature`, `max_tokens_field` and the
      `reasoning_effort` to send.
  - `to_entry` copies these onto `ProviderConfig`.
  - The existing 12,000-token output cap still applies.
- **Pricing.**
  - `price_usage` is shared by both transports.
  - Cache reads are charged at `cached_input_per_million`, scaled by the long-context factor
    when one applies. Without that field they are charged at the full input rate, as before.
  - Anthropic cache writes are charged at 1.25× input, the published price for five-minute
    writes.
  - DeepSeek's `prompt_cache_hit_tokens` counts as cached input.
- **`AnthropicProvider`** (`anthropic==1.12.1`; the SDK is imported only when a request is
  sent):
  - Request:
    - The system prompt is a top-level `system` text block with `cache_control: ephemeral`.
    - Split-context requests become one user message of text blocks. The stable reference
      block is a second cache breakpoint.
  - Never sent: assistant prefill, tools, `thinking`, or `temperature` unless
    `send_temperature` is set. `send_temperature` is set only for Haiku 4.5, and goes in
    `extra_body` because the 1.x SDK has no sampling keyword.
  - Effort: `output_config.effort` comes from `reasoning_effort`, mapped as
    none/minimal→low, low, medium, high, xhigh, max. The presets set each model's documented
    default explicitly: Opus 5.5 medium, Sonnet 5.5 high, Fable 5.1 high, Haiku 5.5 medium.
    Haiku 4.5 sends no effort and runs without thinking.
  - Streaming:
    - `.stream()` is used when `streaming` is set, which is the preset default.
    - Progress events match `CompatibleProvider`: waiting, reasoning, receiving, received,
      interrupted.
    - A stream that ends without `message_stop`, or fails after headers, is treated as
      interrupted. The usage estimate is charged, the call is not retried, and no output is
      accepted.
  - Response:
    - Only `text` blocks are read; thinking blocks are ignored.
    - One surrounding Markdown fence is removed, then the text goes through `strict_json`
      and must be a JSON object.
    - `stop_reason` handling:
      - `refusal`: a non-recoverable `ProviderError` recording `details.refusal_category`.
      - `max_tokens`, `pause_turn` and `tool_use`: treated as an invalid or truncated object.
  - JSON:
    - Metis requests carry no schema, so `output_config.format` (`json_schema` with
      `additionalProperties: false`) cannot express the open AgentOutput object.
    - The shared system prompt already requires one JSON object. The existing
      strict-parse and repair loop applies.
    - Forced `tool_choice` is never used.
  - Errors:
    - The SDK runs with `max_retries=0`; Metis's own retry loop runs as for compatible
      endpoints.
    - 429 is classified by `quota_window`, which now reads
      `anthropic-ratelimit-{requests,tokens,input-tokens,output-tokens}-{remaining,reset,limit}`
      (RFC 3339 resets) as well as `retry-after`. A long window raises
      `quota_exhausted_until` after a single attempt.
    - A spend-cap 429 (`enforced_spend_limit_reached`) never waits and stops retrying at once.
    - 529 `overloaded_error` is `rate_limited` and recoverable, like Gemini's 503 overload,
      so quota waiting can apply. Other 5xx are recoverable.
    - 400, 401, 403, 404 and 413 are non-recoverable.
    - Connection errors and timeouts are recoverable and charge the estimate.
    - The request id is included in error messages and in `ProviderError.details`.
  - Network and credentials:
    - No ambient proxy and no redirects: `DefaultHttpxClient(trust_env=False,
      follow_redirects=False)`.
    - The key comes only from `credentials.resolve(api_key_env)`. An explicit key also stops
      the SDK from falling back to `ANTHROPIC_API_KEY` or a profile.
    - No `httpx` object is passed to the SDK, which is built on `httpx2`.
- **Factory.** `providers.create_provider(config)` returns the transport for the adapter. The
  agent runner, inventory access checks, setup checks and onboarding use it.
- **Writer.**
  - PaperOrchestra calls models through the OpenAI SDK only.
  - `preflight_writer` reports a clear error when a writer slot resolves to an Anthropic
    model. The worker refuses such a slot as well.
  - The PaperOrchestra Docker requirements are unchanged and do not need `anthropic`.

## Dependency

- `anthropic==1.12.1` (MIT) is pinned in `pyproject.toml` and `uv.lock` was regenerated.
- Why: the official SDK supplies typed errors, SSE parsing, request ids and the current
  Messages API surface, and the brief required a native adapter.
- New transitive packages: `httpx2` and `httpcore2` (2.13.1), `httpx2-jsfetch`, `jiter`,
  `docstring-parser`, `sniffio` and `truststore`.
- Metis's own transport still uses `httpx==0.28.1`. The two libraries coexist and never
  exchange objects.

## Sources (all checked 2026-10-08)

Each source was read directly as Markdown or HTML, or through a fetch summary that was
cross-checked against the raw page.

- **Anthropic**
  - Prices: [pricing](https://platform.claude.com/docs/en/about-claude/pricing).
  - Model list:
    [models overview](https://platform.claude.com/docs/en/about-claude/models/overview).
  - Model pages for [Opus 5.5](https://platform.claude.com/docs/en/models/opus-5-5/overview),
    [Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/overview),
    [Haiku 5.5](https://platform.claude.com/docs/en/models/haiku-5-5/overview),
    [Haiku 4.5](https://platform.claude.com/docs/en/models/haiku-4-5/overview) and
    [Fable 5.1](https://platform.claude.com/docs/en/models/fable-5-1/overview).
  - Sampling restrictions:
    [thinking](https://platform.claude.com/docs/en/build-with-claude/thinking).
  - Effort levels and defaults:
    [effort](https://platform.claude.com/docs/en/build-with-claude/effort).
  - Rate-limit headers and the spend cap:
    [rate limits](https://platform.claude.com/docs/en/api/rate-limits).
  - JSON outputs:
    [structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).
    It also documents the incompatibility with citations and prefill.
  - Data use: [commercial terms](https://www.anthropic.com/legal/commercial-terms).
- **OpenAI**
  - Model pages for [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra),
    [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) and
    [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna). They give context,
    output limit, prices, cached prices, the price above 272K tokens and effort levels.
  - Prices: [pricing](https://developers.openai.com/api/docs/pricing).
  - The [latest-model guide](https://developers.openai.com/api/docs/guides/latest-model) says
    to remove `temperature` and `top_p` when effort is not `none`.
  - The [Chat Completions reference](https://developers.openai.com/api/docs/api-reference/chat/create)
    says `max_completion_tokens` covers reasoning tokens and calls `json_object` the older
    JSON mode.
  - Data use: [your data](https://developers.openai.com/api/docs/guides/your-data).
- **Google**
  - Model: [Gemini 3.1 Pro preview](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview).
  - Prices: [pricing](https://ai.google.dev/gemini-api/docs/pricing). Paid tier only; above
    200k tokens the prices are $4 input, $18 output and $0.40 caching.
- **DeepSeek**
  - Models and prices: [pricing](https://api-docs.deepseek.com/quick_start/pricing).
    `deepseek-flash` is served by V4.1-Flash and `deepseek-v4-pro` by V4-Pro-0813. Context is
    1M and output up to 384K. The catalog stores peak prices; off-peak prices are half.
  - JSON output: [JSON output](https://api-docs.deepseek.com/guides/json_mode).
  - Temperature: [thinking mode](https://api-docs.deepseek.com/guides/thinking_mode) says it
    has no effect in thinking mode.
  - Positioning: [V4.1-Flash release](https://api-docs.deepseek.com/news/news260910).
  - Data use and jurisdiction:
    [privacy policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html).

### Differences from the task brief's table

- **Sonnet 5.5 cache reads cost $0.10/MTok, not $0.20.** The pricing page says cache hits on
  Opus 5.5 and Sonnet 5.5 cost 5% of the input price, which is $0.10 on Sonnet 5.5.
- **Claude Haiku 5.5 (`claude-haiku-5-5`) is now the current Haiku.** It was released on
  2026-10-07. Prices are $0.10 input and $0.50 output, or $0.50 and $2.50 for prompts over
  100k tokens. Context is 1M and output up to 128K. Non-default sampling returns 400.
- **Claude Haiku 4.5 is legacy.** Its output limit is 64K and retirement is not sooner than
  2026-10-15. Both Haiku models are in the catalog.
- **OpenAI's current lineup is GPT-6 Astra, Sol and Luna.** There is no current
  "mini"-named model. Luna is the cheap model.
- **DeepSeek's pricing page lists `deepseek-flash` and `deepseek-v4-pro`.** It does not list
  `deepseek-chat` or `deepseek-reasoner`.

### Tier mapping (provider-published, not measured)

| Tier | Meaning | Models |
|---|---|---|
| frontier | The provider's most capable or flagship line | GPT-6 Astra, Claude Fable 5.1, Claude Opus 5.5, Gemini 3.1 Pro |
| strong | Described as near-flagship | GPT-6.1 Sol, Claude Sonnet 5.5 |
| standard | No capability positioning published | DeepSeek Flash, DeepSeek V4 Pro |
| light | Efficient or high-volume models | GPT-6 Luna, Claude Haiku 5.5, Claude Haiku 4.5 |

### Unverified or open

- Whether GPT-6 models reject `temperature` or ignore it. Metis omits it in either case, as
  the guide instructs.
- Whether Chat Completions `json_object` is explicitly supported on GPT-6. Structured Outputs
  are listed as supported.
- Whether DeepSeek trains on API inputs. Neither the privacy policy nor the platform terms
  say so.

## Acceptance

- Mocked tests, using the real SDK on an `httpx2` mock transport:
  - Request shape per model.
  - Effort mapping.
  - System prompt with `cache_control`, and split-context breakpoints.
  - Streaming progress, and interrupted streams.
  - Thinking blocks ignored.
  - Refusal category.
  - `max_tokens` truncation.
  - Usage and cost with cache reads and writes, and Haiku 5.5 long-context pricing.
  - Short-window 429 retries, and long-window 429 from `anthropic-ratelimit-*` headers.
  - Spend cap, 529 overload, and 4xx being non-recoverable.
  - Connection failure.
  - SDK retries disabled, and no proxy or redirect.
  - Factory selection.
- OpenAI and DeepSeek request-shape and cache-pricing tests; the default request shape is
  unchanged.
- Preset validation and tiers; serialization unchanged; writer preflight refusal.
- Full CONTRIBUTING checklist, plus the wheel/package check because a dependency changed.
- Independent review recorded in `docs/reviews/main-providers.md`.
