# Official PaperOrchestra integration

Inspected 2026-09-29. Live drafting and revision import the official agents from [google-research/paper-orchestra at ca1b3fa01c2970fc7cda32d16245db38d57b3f56](https://github.com/google-research/paper-orchestra/tree/ca1b3fa01c2970fc7cda32d16245db38d57b3f56). There is no reconstructed writer fallback. A missing dependency, exhausted budget, invalid artifact, subprocess failure or incomplete workflow leaves a failed, resumable stage with its diagnostics.

## Primary-source audit and implemented behavior

The [PaperOrchestra paper](https://arxiv.org/html/2604.05018v1#S4) specifies outline generation, plotting, literature review, section writing and iterative content refinement. Its [released workflow](https://github.com/google-research/paper-orchestra/blob/ca1b3fa01c2970fc7cda32d16245db38d57b3f56/methods/paper_writer_with_plotting.py) supplies the concrete agent constructors, inputs, parallel literature/plotting branch and outputs. We import those agent classes and their released prompts unchanged, and reproduce that stage order. The three reflection rounds and three plotting critic rounds are defaults in the released workflow, rather than a locally guessed scientific limit.

`raw_materials/idea_sparse.md` contains the selected hypothesis, verified limitations, previous manuscript and revision feedback. `experimental_log.md` contains every attempted experiment, baseline, ablation/rebuttal plan, reference and history record, including failed and negative runs. Additional JSON files preserve the complete state and an experiment-ID/metric/value ledger; the selected code is copied with credential files excluded. The template comes from upstream's complete `templates/iclr2025` directory, including conference style, bibliography style, math macros and guidelines.

Google-grounded discovery and Semantic Scholar title matching remain the official literature algorithm. Exact S2 HTTP results, abstracts, identifiers, publication metadata, search queries, failures and Google grounding metadata are retained. The emitted BibTeX keys map to retrieved `Evidence` records returned to ScientistTwo; they are not fabricated from generated bibliography prose. Final citation-support verification remains a separate integrity check.

The plotting implementation additionally expects PaperBanana reference images and style guides. The source checkout does **not** contain the references and silently omits retrieval when they are absent. Our setup fetches the [official PaperVizAgent repository](https://github.com/google-research/papervizagent/tree/e088a8fff74cc363b6897c0843631fff76484908), pinned at `e088a8fff74cc363b6897c0843631fff76484908`, plus the now-released [PaperBananaBench archive](https://huggingface.co/datasets/dwzhu/PaperBananaBench/tree/a876264bcd1e826a0320f805f8fb1cd705cf510f). Archive revision: `a876264bcd1e826a0320f805f8fb1cd705cf510f`; SHA-256: `a980d23954c0cb47017cdaa8a9029dbea3598791fd269a457482033821927e37`; size: 265,846,711 bytes. The inspected archive contains 298 diagram reference examples and 240 plot reference examples. The released upstream retriever uses its first 200 diagram examples and all plot examples. Missing examples now fail explicitly. Plotting can be deliberately disabled in configuration for an ablation; this is not the default.

## Setup

From an installed repository environment, provision private runtime dependencies outside the Git checkout:

```bash
python -m autoresearch.paper_orchestra_setup /path/to/private/upstreams
docker build -f .docker/paper-orchestra.Dockerfile -t scientisttwo-paper-orchestra:pinned .
```

The setup command downloads and retains the checksum-verified reference archive, checks extraction paths, and prints the configuration paths. Each reuse derives expected file hashes from that pinned archive, verifies a clean plotting checkout and tracked style guides, and checks the exact materialized snapshot. An editable installation receipt cannot authorize modified reference bytes; unexpected files, symlinks and changed assets fail verification. The Python runtime is resolved to exact versions and distribution hashes in `.docker/paper-orchestra-requirements.txt`. The Dockerfile pins the Python release; Debian TeX system packages are installed from the distribution repository, so their precise versions are captured by the image rather than a cross-platform apt lock. Preserve the built image digest for an exact environment replay.

Add to the normal project configuration (keep credentials exclusively in environment variables):

```json
{
  "paper_orchestra": {
    "checkout_dir": "/path/to/private/upstreams/paper-orchestra",
    "paperbanana_dir": "/path/to/private/upstreams/PaperBanana",
    "backend": "docker",
    "docker_image": "scientisttwo-paper-orchestra:pinned",
    "research_cutoff": "2026-09",
    "max_cost_usd": 15,
    "timeout_seconds": 86400,
    "use_plotting": true
  }
}
```

Set the credentials requested by your configured provider, `GEMINI_API_KEY` for the native Google grounded-search/image workflows, and optionally `SEMANTIC_SCHOLAR_API_KEY` for S2 capacity. `preflight_writer(config)` reports configuration/dependency errors without making paid model calls. The default Docker execution needs a running Docker daemon. Deliberate local execution requires `backend: "local"`, `allow_local: true`, a compatible Python with the locked requirements, and `pdflatex`/`bibtex`; it is not sandboxed.

## Routing and accounting

Empty `writer_model_name`, `reflection_model_name` and `plotting_model_name` inherit the project's configured provider, including Grok, through role overrides `writing_writer`, `writing_reflection` and `writing_plotting`. `compatible_models` can map explicitly named models to complete provider configurations. PDF visual review renders every page when using compatible vision APIs, preserving visual input. An incapable multimodal endpoint fails rather than silently removing images. Native Google literature and image generation remain configurable as `literature_model_name` and `image_model_name`; a compatible substitution cannot discard Google Search or image generation tools.

To compare closest released behavior, explicitly set writer, reflection and plotting model names to `gemini-3.1-pro-preview`, retain the native literature/image defaults and run matched evaluation tasks. To use the user's model substitutions, leave the text-role names empty and compare resulting writing/citation quality and costs. The integration itself establishes no performance parity for substitutions.

Every underlying model/API attempt has a durable reservation and record containing provider, actual model, tokens, timing, cost estimate, request hash and status. Response caches retain native usage and grounding metadata. `native_prices` accepts per-model `input_per_million`, `output_per_million`, `request_usd` (including tool/image fees where applicable), and `max_output_tokens`; supply current account-specific rates. Unknown prices or usage incur the configurable `unpriced_call_usd` conservative estimate, marked `estimated: true`, never a fictitious zero cost. This is an estimate, not a provider-enforced spending limit. The worker enforces recorded cost and call-count ceilings before dispatch, and the parent settles aggregate cost without double-counting child events. Reservations left by interrupted calls remain charged conservatively.

## Checkpoints and artifacts

Jobs are keyed by scientific inputs, the catalog identity and resolved configuration. A durable attempt intent precedes the idempotent aggregate reservation. Recovery accounts only newly incurred subordinate usage through the generic Store ledger, without billing or counting a child twice. Container and complete local process-group exit must be verified before repairing journals or settling a reservation; a disconnected Docker client or an exited leader is not proof that spending stopped. Uncertain workers retain their reservations and require reconciliation before resume. Torn JSONL tail bytes are archived by hash after shutdown; complete records and all prior attempts remain intact. The worker holds exclusive job ownership and records every stage-scoped transport attempt, including adapter and budget failures before dispatch. Unresolved requests prevent checkpoint completion even when upstream code catches the exception. Only a later successful identical request in the same stage resolves a failure; an earlier success or success in another stage cannot erase it. Poisoned checkpoints and dependent checkpoints are invalidated with an audit record. Atomic stage checkpoints retain completed outline, literature, plotting, section and reflection work with artifact hashes. Successful model responses and S2 requests are cached; interrupted stages resume using those responses. In-stage Python agent state is reconstructed by replaying the stage, not serialized. Retries of identical malformed responses receive a fresh response occurrence; replay preserves the original call sequence. A source/configuration change creates a new job rather than reusing stale work.

Versioned artifacts include raw materials, final and intermediate LaTeX, `.bib`, generated figures/code, search evidence, per-call records, process logs, compile diagnostics, checkpoint files, final PDF and SHA-256 manifests. Reference-dataset copies are excluded from manuscript bundles because they have separately pinned provenance. The strict compiler uses `-no-shell-escape`, checks every process return code, removes stale PDFs on error and recompiles the exact final source; a nonzero process cannot be reported as a successful compile.

Generated plotting code runs in separate credential-free containers with no network and only its dedicated workload input/output subdirectory mounted. Host completion records are outside that writable mount, so generated code cannot forge a successful process result. Logs are bounded and named containers are forcibly removed after failures/timeouts. The model-calling worker mounts the official source read-only and receives only explicitly needed API environment variables; it never receives the host home or Docker socket. TeX processes receive no API credentials and restrict input/output paths. Upstream's S2 helper prints its API key at import; a stream redactor installed before upstream import prevents that secret entering logs. All research traces remain private runtime data; do not publish raw run bundles without review.

## Validation and remaining limits

`tests/test_writing.py` covers failure propagation, exact checkout verification, input evidence, completed-stage replay/corruption, subprocess failure despite a stale PDF, per-call usage/cache/budgets, constrained Docker launch and secure archive extraction. The pinned reference archive was downloaded and its exact checksum/layout inspected during this repair. The complete hash-locked runtime (84 packages) was installed in an isolated temporary environment. The opt-in `tests/test_writing_upstream.py` passed against the actual pinned source: all five upstream agents imported and the real `OutlineAgent.run` executed through the routed transport with a deterministic local response. This does not make paid API calls. Run it with `PAPER_ORCHESTRA_TEST_CHECKOUT=/path/to/upstream PYTHONPATH=src python -m pytest tests/test_writing_upstream.py` in the writer runtime with pytest installed. A full paid writing run, generated PDF quality evaluation and substitution ablation require configured credentials, TeX/runtime availability and real scientific results; they are not claimed by unit tests. No live Docker or TeX success is asserted by these fixtures. A separate CI job repeats the actual pinned SDK/source smoke and real refinement recovery with deterministic model responses and a PDF/TeX fixture; it tests integration and replay, not document quality.

The writer and PaperVizAgent code are Apache-2.0, Copyright Google LLC. Their source/license remains in the runtime checkout; no upstream prompt package is relabeled as original work. PaperBananaBench papers/images retain their upstream rights and are fetched into private runtime storage, not redistributed with this repository. PaperWritingBench, the writer paper's separate 200-paper evaluation corpus, is not bundled by the inspected official writer repository; its absence does not prevent execution on ScientistTwo experiment state.

Writer reconciliation regressions also cover stage-scoped failures and ownership (`tests/test_writer_recovery.py`), surviving process descendants and torn journals (`tests/test_writer_supervision.py`), crash-recoverable aggregate attempts (`tests/test_writer_accounting.py`) and pinned archive/snapshot verification (`tests/test_plot_assets.py`). No paid call is required for these checks; the actual upstream recovery smoke remains opt-in. Local process-group supervision assumes workers do not deliberately detach into a different session; Docker remains the isolated default.
