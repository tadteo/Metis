# Public examples

`regression.json` is an inexpensive **live-model** integration task with generated public
synthetic data, three random seeds and a protected evaluator. Its 0.5 target is an
illustrative threshold, **not a published SOTA result**. It does not validate novelty.
Run from the repository root after installing dependencies and setting `XAI_API_KEY`:

```sh
uv run metis new --title 'Synthetic regression' \
  --objective 'Investigate the limitations of a linear predictor on the specified nonlinear data; preserve the evaluation protocol.' \
  --config examples/regression.json
uv run metis run RUN_ID
```

The default executor uses Docker. Pre-pull the configured image, and pin its digest
before a reproducibility study. Agent-generated training changes execute without
network access, with the evaluator snapshot mounted read-only. The metrics protocol
is `metrics.json` with finite numbers, produced by the trusted evaluator after training.
The evaluator's read-only mount protects its source, not every possible attack from a
hostile co-resident process; use stronger cluster isolation for untrusted workloads.

For a private project such as ATOM, create configuration outside this repository. Set
`source_dir`, a minimal `include` list, `baseline_argv`, an independent `evaluator_argv`,
`protected_paths`, required metric directions, actual published full-benchmark `sota`,
reproduction tolerances, dataset/split/seed/compute requirements in `specification`, and
an execution profile. Data and cluster credentials must remain outside Git. No ATOM
repository, dataset, metric, result, or cluster access is assumed by this example.

`uv run metis demo` is a distinct offline fixture: scripted agents and review
scores, real synthetic regression subprocesses, no paid API calls.
