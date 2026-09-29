"""Operator-owned evaluator. Never delegate edits of this file to research agents."""

import json
import math
import os
import random
from pathlib import Path

weights = json.loads(Path("model.json").read_text())["weights"]
if not isinstance(weights, list) or not 1 <= len(weights) <= 9:
    raise ValueError("invalid model shape")
if not all(isinstance(w, (float, int)) and math.isfinite(w) for w in weights):
    raise ValueError("invalid weights")
rng = random.Random(10000 + int(os.environ.get("AUTORESEARCH_SEED", "0")))  # noqa: S311 - reproducible scientific sampling
test = [(rng.uniform(-2, 2), rng.gauss(0, 0.15)) for _ in range(512)]
mse = sum(
    (sum(w * x**i for i, w in enumerate(weights)) - (1.5 * x + 0.8 * x * x + noise)) ** 2
    for x, noise in test
) / len(test)
Path("metrics.json").write_text(json.dumps({"score": 1 / (1 + mse), "mse": mse}))
print(json.dumps({"heldout_n": len(test), "mse": mse}))
