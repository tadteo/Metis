"""Pure-Python registered baseline; methods may be changed by the research agent."""

import math


def fit_predict(
    train_x: list[list[float]],
    train_y: list[float],
    test_x: list[list[float]],
    kind: str,
    seed: int,
) -> list[float]:
    n, d = len(train_x), len(train_x[0])
    means = [sum(row[j] for row in train_x) / n for j in range(d)]
    scales = [
        max(math.sqrt(sum((row[j] - means[j]) ** 2 for row in train_x) / n), 1e-12)
        for j in range(d)
    ]
    x = [[(row[j] - means[j]) / scales[j] for j in range(d)] for row in train_x]
    test = [[(row[j] - means[j]) / scales[j] for j in range(d)] for row in test_x]
    if kind == "classification":
        labels = sorted(set(train_y))
        centers = []
        for label in labels:
            rows = [row for row, y in zip(x, train_y, strict=False) if y == label]
            centers.append([sum(row[j] for row in rows) / len(rows) for j in range(d)])
        return [
            labels[
                min(
                    range(len(labels)),
                    key=lambda k: sum((row[j] - centers[k][j]) ** 2 for j in range(d)),
                )
            ]
            for row in test
        ]
    y_mean = sum(train_y) / n
    # Ridge alpha=1, intercept unpenalized, solved by Gaussian elimination.
    matrix = [
        [sum(row[j] * row[k] for row in x) + (1 if j == k else 0) for k in range(d)]
        + [sum(row[j] * (y - y_mean) for row, y in zip(x, train_y, strict=False))]
        for j in range(d)
    ]
    for j in range(d):
        pivot = max(range(j, d), key=lambda k: abs(matrix[k][j]))
        matrix[j], matrix[pivot] = matrix[pivot], matrix[j]
        scale = matrix[j][j]
        matrix[j] = [value / scale for value in matrix[j]]
        for k in range(d):
            if k != j:
                scale = matrix[k][j]
                matrix[k] = [a - scale * b for a, b in zip(matrix[k], matrix[j], strict=False)]
    weights = [row[-1] for row in matrix]
    return [y_mean + sum(a * b for a, b in zip(row, weights, strict=False)) for row in test]
