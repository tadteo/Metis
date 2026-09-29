"""Synthetic polynomial-regression workload for the offline demo only."""

import argparse
import json
import os
import random


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--degree", type=int, default=1)
    p.add_argument("--split", choices=["subset", "full"], default="subset")
    p.add_argument("--ridge", type=float, default=0.01)
    a = p.parse_args()
    rng = random.Random(int(os.environ.get("AUTORESEARCH_SEED", "0")))  # noqa: S311 - deterministic scientific fixture
    n = 64 if a.split == "subset" else 256
    train = [(rng.uniform(-2, 2), rng.gauss(0, 0.15)) for _ in range(n)]
    test = [(rng.uniform(-2, 2), rng.gauss(0, 0.15)) for _ in range(n)]
    d = a.degree + 1
    matrix = [
        [sum(x ** (i + j) for x, e in train) + (a.ridge if i == j else 0) for j in range(d)]
        + [sum(x**i * (1.5 * x + 0.8 * x * x + e) for x, e in train)]
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
                matrix[j] = [v - scale * w for v, w in zip(matrix[j], matrix[i], strict=False)]
    w = [row[-1] for row in matrix]
    mse = (
        sum(
            (sum(v * x**i for i, v in enumerate(w)) - (1.5 * x + 0.8 * x * x + e)) ** 2
            for x, e in test
        )
        / n
    )
    metrics = {"score": 1 / (1 + mse), "mse": mse}
    with open("metrics.json", "w") as f:
        json.dump(metrics, f)
    print(json.dumps({"metrics": metrics, "n_train": n, "n_test": n, "degree": a.degree}))


if __name__ == "__main__":
    main()
