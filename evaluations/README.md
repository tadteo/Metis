# Evaluation artifacts

`baseline-results.json` is an executed real-public-data baseline report, including
all 12 attempted subset/full/seed combinations. It is a reproducibility and
executor check; autonomous model-guided research was not run for these results.

See [the evaluation protocol](../docs/evaluation.md) for preparation, full live
execution, paired substitutions/ablations, independent quality judgments and
complete failure denominators. Runtime datasets, credentials, configurations and
research state belong in a private evaluation directory, not this repository.

`baseline-results-superseded.json` preserves the earlier measurements and their provenance.
Its diabetes inputs used loader scaling before splitting; independent review rejected that
protocol. The current report was rerun with raw inputs and training-only standardization.
No prior attempt was removed from the evidence record.
