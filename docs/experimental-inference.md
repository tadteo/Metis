# Metered model decisions in experiments

Generated Docker code has neither network access nor model credentials. A study
that benchmarks model decisions therefore needs an operator-provided inference
resource. The standalone `scripts/experimental_inference.py` service uses the
existing run's Store ledger and saved provider configurations; it does not change
scientific stages, pinned runtime, model routing or the run's spending limit.

Start it with the same controller interpreter/runtime and state directory:

```sh
PYTHONPATH=src python scripts/experimental_inference.py RUN_ID --state-dir /private/run-store
```

Copy `scripts/metis_decisions.py` into the admitted research project as a recorded
operator resource before baseline preparation. For an existing paused intake,
record the supplied source/hash and answer its question through `metis intervene`
then `metis resume`; do not overwrite configuration or behavior identity. Keep the
controller process alive while Docker commands execute. It uses a separate process
lock, leaving the engine's run lease intact. Each service is restricted to one run.
This operator tool is distributed in the repository, not the installed wheel.

Inside a sandbox command:

```python
from metis_decisions import decide
receipt = decide("reference", "Classify the supplied public trace. Return JSON.",
                 sample="development-case-001-reference")
assert receipt["status"] == "completed", receipt
print(receipt["data"], receipt["usage"], receipt["call_id"])
```

Aliases are `reference` (saved primary provider) and `cheap` (saved cheap provider,
when present). They are fixed by the controller manifest; no arbitrary endpoint,
credential, model name, shell command or host file path is accepted. Requests are
bounded JSON files in `metis-inference/` at the workspace root. Only existing
`coding/*/workspace` and `experiments/*` layouts are serviced. Path traversal,
symlinks and malformed requests are refused. Invalid inputs produce no API call;
a client timeout requires inspecting the request, not assuming a model failure.

Each explicit request uses one API attempt, temperature zero, JSON output, and
256–2048 maximum output tokens, capped by the saved provider limit. Automatic
transport retries are disabled for experimental calls so every deliberate retry
has its own receipt and call count. All other saved transport/pricing settings
remain in use. Shared monetary and call limits are enforced before dispatch;
failed responses and unknown usage retain conservative charges. Provider invoices
can differ from configured rates. Local compute cost remains separate.

Identical request/sample combinations reuse the original attempt across commands,
workspaces and controller restarts; the same `call_id` is not a fresh sample.
Use a new sample ID for an intentional repeat or retry, retaining earlier failures.
No automatic retry occurs after an uncertain interrupted request. Its reservation
remains held until explicitly reconciled. If a receipt was saved before interruption,
recovery settles it without repeating inference. Paused/terminal runs accept no new
paid requests. A pause cannot cancel a request already dispatched.

The service archives its source, provider/rate manifest, input, actual redacted
outbound request and response/usage receipts as private run artifacts. Privacy
redaction is part of the measured input transformation; account for it in the
experimental protocol. Model output is also redacted before reaching the sandbox.
The response's `receipt_sha256` hashes its fields excluding that hash itself.

**Sandbox response files are working copies, not a trusted scientific oracle.**
Independent verification must compare reported model outputs and costs with the
controller-owned `experimental_inference_receipt` artifacts and their call IDs.
A workload can edit its copy; it cannot authorize changes to the private ledger.
Pin the service/source and data protocol before acceptance. Replay speed is not
model inference latency, missing responses are not correct predictions, and LLM
agreement is not an independently established ground-truth label.

This service supplies access only. It does not install Laya, supply a labelled
corpus, certify model quality or provision PaperOrchestra. It leaves all scientific
validation and failure-preservation requirements intact.
