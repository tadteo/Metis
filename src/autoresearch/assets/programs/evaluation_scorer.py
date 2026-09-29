"""Operator-owned scorer: finite predictions and fixed held-out targets."""

import json
import math
import os
from pathlib import Path


def main() -> None:
    protected = Path(__file__).parent
    protocol = json.loads((protected / "protocol.json").read_text())
    y = json.loads((protected / "test_targets.json").read_text())
    output = json.loads(Path("predictions.json").read_text())
    predictions = output["predictions"]
    assert output["seed"] == int(os.environ.get("AUTORESEARCH_SEED", "0"))
    assert output["split"] in {"subset", "full"}
    kind = os.environ.get("AUTORESEARCH_EXPERIMENT_KIND", "")
    expected = (
        "subset"
        if kind in {"baseline", "subset", "subset_engineer", "evaluation_subset"}
        else "full"
    )
    assert output["split"] == expected, "wrong subset/full protocol for the experiment stage"
    assert len(predictions) == len(y)
    assert all(
        isinstance(p, (int, float)) and not isinstance(p, bool) and math.isfinite(p)
        for p in predictions
    )
    if protocol["kind"] == "classification":
        assert set(predictions) <= set(protocol["class_labels"])
        score = sum(a == b for a, b in zip(predictions, y, strict=False)) / len(y)
    else:
        mean = sum(y) / len(y)
        score = 1 - sum((a - b) ** 2 for a, b in zip(predictions, y, strict=False)) / sum(
            (b - mean) ** 2 for b in y
        )
    Path("metrics.json").write_text(json.dumps({"score": score}, allow_nan=False))


if __name__ == "__main__":
    main()
