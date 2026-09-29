# Capability evaluation

The bundled real-data battery contains two modest public research-method tasks:
handwritten digit classification and regression on diabetes progression data.
It uses scikit-learn's packaged [digits](https://scikit-learn.org/1.7/modules/generated/sklearn.datasets.load_digits.html)
and [diabetes](https://scikit-learn.org/1.7/modules/generated/sklearn.datasets.load_diabetes.html)
datasets. These are real observations, not the polynomial plumbing fixture.
Their size makes them useful for repeatable integration and method experiments;
they are **not** substitutes for the paper's frontier-research benchmark or
independent evidence of comparable autonomous scientific ability.

The package extra `evaluation` pins scikit-learn and NumPy for preparation.
Generated task workloads use pure Python and run in the normal configured Docker
executor without additional numerical libraries. `prepare_suite` fixes stratified
classification splits (ordinary regression splits), records exact row indices,
selects a registered training subset and saves dataset/protocol hashes. It provides
standardized nearest-centroid and ridge baselines, protected evaluators, baseline
commands and complete live research configurations. All preprocessing uses training
rows only. The published datasets remain publicly accessible: protected evaluation
files prevent edits, not knowledge of labels; code and leakage audits remain
necessary. This is explicitly a fixed-protocol evaluation, not a secret benchmark.
Every protected task file also has an explicit `sha256:relative/file` entry in the
operator manifest. The executor verifies these bytes before running a workload;
altered files fail immediately. Descriptive dataset names and URLs remain metadata,
not hash-verified provenance claims.

`baseline_suite` executes both subset and full baselines for each registered seed.
Every attempt is recorded before execution; failures cannot populate reference
metrics. Receipts support resumption without repeating completed measurements.
Interrupted work without a receipt stays uncertain. The `project.sota` values in
these evaluation configurations mean **measured registered reference baseline**,
not a published SOTA claim. The specification records this distinction.

```python
from pathlib import Path
from autoresearch.config import load_config
from autoresearch.evaluation import prepare_suite, baseline_suite, run_suite, report_suite
from autoresearch.store import Store

root = Path("/absolute/private/evaluation")
prepare_suite(root, load_config(Path("research.json")))
baseline_suite(root)  # configured Docker executor, no model API calls
run_suite(Store(), root)  # real APIs, official writer, actual research stages
print(report_suite(Store(), root))
```

Use `run_suite(..., max_steps=1)` for a bounded checkpointed run; rerunning resumes
the same task/variant. Configure API credentials and the official PaperOrchestra
checkout/environment before attempting the complete research run. Baseline-only
success is reported separately from autonomous task completion. The report counts
creation failures, provider failures, blocked runs, budget exhaustion and scientific
failure in attempted task/variant denominators. Negative experiments and coding
command failures remain in the underlying run journal.

Each task report separates:

- Independent idea/novelty quality from proposed-idea counts.
- Baseline reproduction from coding-session and command-check success.
- Experiment execution with valid metrics from scientific correctness.
- Full-idea improvement rate from component ablation execution and quality.
- Retrieved/inspectable/full-text literature coverage from unknown retrieval recall.
- Independent writing/reviewer quality from the in-loop review score.
- Detected integrity failures from whether an audit was completed.
- API tokens/cost and unresolved external compute billing.
- Wall-clock time, experiment time and coding-check time.

Independent quality results are imported into `suite.json` as `quality_ratings`
entries with `task`, `variant`, `dimension`, `rater_id`, `independent: true`, a score
in `[0,1]` and `evidence_artifacts`. Dimensions are `idea_novelty`,
`ablation_quality`, `paper_writing` and `reviewer_quality`. Use blinded human or
held-out model assessments against preregistered rubrics; do not reuse the optimizing
ScholarPeer panel. Missing judgments remain null, as do literature recall without
an independently assembled relevant-paper set and compute cost without billing.
A review-quality rating is never converted to a venue acceptance probability.

## Paired ablations

`variants(config, reference_config)` emits executable configurations for configured
routing, a two-reference retrieval budget, one critic, and disabled frontier
escalation, plus Pareto versus independent scientific-critic result preference.
If Laya is enabled in the operator's config, a Laya-enabled/disabled pair is also
emitted. An operator-supplied verified reference model/coding configuration adds
a `published-routing` comparator. The implementation never invents credentials,
endpoints or currently unavailable paper model names. Register separate task/variant
attempts with `run_suite(..., variant="single-critic")` and compare each dimension,
failed-attempt fraction and cost under the same datasets, seeds and scientific
budgets. Reduced variants are evaluation controls, not claims of sufficient novelty
coverage or production recommendations.

The two-reference control explicitly reduces both the retrieval budget and the
minimum-evidence gate to two, while the production default requires at least three
inspectable independent papers. Neither gate establishes exhaustive novelty.
This compares the combined retrieval/gating policy; retrieval recall additionally
requires independent relevant-paper labels. The paper's original exact
agent prompts, private task environments and unavailable model versions cannot be
manufactured by an ablation config. Record unavailable comparison arms as missing
measurements with their specific cause.

Local strict numerical preference, reconstructed prompt semantics and model
routing require independent paired scientific judgments in addition to executable
success. External coding-agent adapters can be supplied through `role_commands`
with explicit subordinate cost caps. The official writer and Appendix-G reviewer
are assessed through writing/reviewer quality dimensions rather than architectural
similarity. Statistical significance requires a registered analysis; identical
seed-level deterministic baselines are reproducibility checks only.

`evaluations/baseline-results.json` contains actual public-data baseline measurements
from this repair. It explicitly records zero autonomous research attempts and no
capability-parity conclusion. Run complete live tasks and obtain independent
ratings before adding a stronger capability claim.
