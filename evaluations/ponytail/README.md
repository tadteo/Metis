# Ponytail coding-policy pilot

This optional, attributed policy encourages reuse and sufficient implementation while
preserving Metis scientific requirements, tests and evidence. It is **not enabled by
default**: the 2026-10-01 live attempts did not establish successful task completion
or cost savings. See [results](results.md). The upstream MIT source/license and exact
revision are packaged under `src/autoresearch/assets/ponytail/`.

## Use for a new experimental study

From the repository, create a separate specification directory; no user settings or
existing runs are changed:

```python
import runpy
from pathlib import Path
from autoresearch.config import load_config

pilot = runpy.run_path("evaluations/ponytail/run.py")
specs = pilot["prepare_specs"](Path("/absolute/private/ponytail-specs"), True)
config = load_config(Path("/absolute/private/research.json"))
config.specification_dir = str(specs)
Path("/absolute/private/ponytail-research.json").write_text(config.model_dump_json(indent=2))
```

Use that configuration when creating a new run. The bundle changes only coding-step
instructions/version; tool permissions, model routing, protected checks and critics
remain intact. The resolved instructions are archived and checked on resumption.
Use an ordinary configuration without `specification_dir` for the original policy.
Do not point an existing run at the new bundle.

## Reproduce the cost/quality comparison

```bash
PYTHONPATH=src python evaluations/ponytail/run.py \
  --config /absolute/private/provider.json \
  --output /absolute/private/new-pilot --pairs 3 --attempt-cap 0.4
```

Requires the chosen configured provider credential and an available Docker image.
The output directory must not exist. The runner uses `config.provider` for both arms,
resets project data/references/mounts, disables cache/frontier/network acquisition,
and copies only the public synthetic fixture into each coding workspace. API calls
send that fixture and packaged instructions to the configured endpoint. Credentials
stay in provider transport and are never mounted into Docker. Explicitly choose an
appropriate Docker image (prefer a digest) in the supplied configuration.

The private output contains the frozen fixture, declared order/limits/hashes,
per-attempt results, versioned specs, complete call accounting, coding checkpoints
and independent acceptance receipts. Attempts are registered before model calls.
Baseline/Ponytail order alternates across pairs. Provider failures stop the battery;
remaining planned slots are unattempted, not successful or silently removed.

The hidden suite evaluates only exported `summary.py`, independently of the agent's
checks. It requires all seven groups of assertions to complete, including failures,
invalid records, CSV quoting, duplicates and sample-statistic accuracy. Test code is
withheld from the agent but the full behavioral requirements are supplied. This
checks functionality; it is not an adversarially secure grader or a research-quality
benchmark. Ordinary CI tests the scorer against correct, incorrect and early-exit
implementations with no paid calls.

`--single-response` is a separately labelled code-generation probe with a temporary
single-response role. It cannot validate the iterative coding pipeline. Do not pool
its measurements with coding-loop attempts. The $0.40/$0.50 per-attempt caps are
conservative accounted estimates, not billing guarantees. `call_usage[].estimated`
marks uncertain reservations; separate them from provider-reported token usage.
No automatic promotion is performed. Default adoption requires complete quality
passes and lower aggregate cost on the declared coding-loop trial; broader quality
and provider generalization need additional evidence.
