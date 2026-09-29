"""Reproducible entry point; protocol and data are operator protected."""

import argparse
import json
import os
from pathlib import Path


def main() -> None:
    # Materialized as model.py beside this script by the evaluation suite.
    from model import fit_predict  # type: ignore[import-not-found]

    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["subset", "full"], required=True)
    args = parser.parse_args()
    seed = int(os.environ.get("AUTORESEARCH_SEED", "0"))
    protocol = json.loads(Path("protocol.json").read_text())
    data = json.loads(Path("train_data.json").read_text())
    test = json.loads(Path("test_features.json").read_text())
    indices = protocol["subset_indices"] if args.split == "subset" else list(range(len(data["y"])))
    predictions = fit_predict(
        [data["x"][i] for i in indices],
        [data["y"][i] for i in indices],
        test,
        protocol["kind"],
        seed,
    )
    Path("predictions.json").write_text(
        json.dumps({"predictions": predictions, "seed": seed, "split": args.split}, allow_nan=False)
    )


if __name__ == "__main__":
    main()
