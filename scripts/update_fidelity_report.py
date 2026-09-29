"""Regenerate packaged fidelity data and both human-readable reports."""

import json
from pathlib import Path

from autoresearch.fidelity import render_report, validate_matrix

root = Path(__file__).resolve().parents[1]
value = json.loads((root / "docs/fidelity.json").read_text())
validate_matrix(value, root, verify_commits=True)
(root / "src/autoresearch/assets/fidelity.json").write_text(json.dumps(value, indent=2) + "\n")
(root / "fidelity-report.md").write_text(render_report(value))
(root / "docs/fidelity.md").write_text(render_report(value, prefix="../"))
