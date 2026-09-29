"""Credential-free plotting subprocess, isolated by its parent container launcher.

Execution semantics follow PaperOrchestra's execute_plot_code_worker (Apache-2.0,
Copyright 2026 Google LLC), moved across a process boundary for isolation.
"""

from __future__ import annotations

import argparse
import importlib
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    code = (args.directory / "code.txt").read_text()
    match = re.search(r"```python(.*?)```", code, re.DOTALL)
    source = match.group(1).strip() if match else code.strip()
    plt = importlib.import_module("matplotlib.pyplot")
    plt.switch_backend("Agg")
    plt.close("all")
    plt.rcdefaults()
    # This process has no network, credentials or research-state mount under Docker.
    exec(compile(source, "generated_plot.py", "exec"), {})  # noqa: S102
    if not plt.get_fignums():
        raise RuntimeError("Generated plot code produced no figure")
    plt.savefig(args.directory / "image.jpg", format="jpeg", bbox_inches="tight", dpi=300)
    plt.close("all")


if __name__ == "__main__":
    main()
