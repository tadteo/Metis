"""Dependency-free synthetic regression training; writes model weights only."""

import argparse
import json
import os
import random
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--degree", type=int, default=1)
parser.add_argument("--split", choices=["subset", "full"], default="subset")
args = parser.parse_args()
if not 0 <= args.degree <= 8:
    raise ValueError("degree must be in [0,8]")
seed = int(os.environ.get("AUTORESEARCH_SEED", "0"))
rng = random.Random(seed)  # noqa: S311 - reproducible scientific sampling
n = 64 if args.split == "subset" else 256
samples = [(rng.uniform(-2, 2), rng.gauss(0, 0.15)) for _ in range(n)]
d = args.degree + 1
matrix = [
    [sum(x ** (i + j) for x, _ in samples) + (0.01 if i == j else 0) for j in range(d)]
    + [sum(x**i * (1.5 * x + 0.8 * x * x + noise) for x, noise in samples)]
    for i in range(d)
]
for i in range(d):
    pivot = max(range(i, d), key=lambda j: abs(matrix[j][i]))
    matrix[i], matrix[pivot] = matrix[pivot], matrix[i]
    scale = matrix[i][i]
    matrix[i] = [v / scale for v in matrix[i]]
    for j in range(d):
        if i != j:
            scale = matrix[j][i]
            matrix[j] = [v - scale * w for v, w in zip(matrix[j], matrix[i], strict=True)]
Path("model.json").write_text(json.dumps({"weights": [r[-1] for r in matrix]}))
