"""Machine-checkable fidelity evidence; architecture never implies measured parity."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from .contracts import Model, Stage

Nonempty = Annotated[str, Field(min_length=1)]
Commit = Annotated[str, Field(pattern=r"^[0-9a-f]{7,40}$")]


class Component(Model):
    component: Nonempty
    published_behavior: Nonempty
    implementation: Nonempty
    implementation_files: list[Nonempty] = Field(min_length=1)
    commits: list[Commit] = Field(min_length=1)
    status: Literal["exact", "integrated", "reconstructed", "missing"]
    classification: Literal[1, 2, 3, 4]
    category: Literal[
        "paper_fidelity",
        "engineering_extension",
        "user_model_substitution",
        "capability_evaluation",
    ]
    evidence: list[Nonempty] = Field(min_length=1)
    test_evaluation: list[Nonempty] = Field(min_length=1)
    remaining_gap: Nonempty
    gap_type: Literal["none", "unpublished", "measurement", "substitution"]
    unavailable_reason: str = ""


def load_matrix() -> dict[str, Any]:
    value: dict[str, Any] = json.loads((Path(__file__).parent / "assets/fidelity.json").read_text())
    validate_matrix(value)
    return value


def _evidence_path(root: Path, reference: str) -> Path:
    relative = Path(reference.split("::")[0])
    target = (root / relative).resolve()
    if relative.is_absolute() or not target.is_relative_to(root.resolve()) or not target.is_file():
        raise ValueError(f"missing or unsafe matrix evidence artifact: {reference}")
    return target


def validate_matrix(
    value: dict[str, Any], root: Path | None = None, *, verify_commits: bool = False
) -> None:
    if value.get("schema_version") != 2:
        raise ValueError("unsupported fidelity matrix schema")
    rows = [Component.model_validate(row) for row in value["components"]]
    ids = [row.component for row in rows]
    if len(ids) != len(set(ids)) or not {stage.value for stage in Stage}.issubset(ids):
        raise ValueError("matrix must cover every stage exactly once")
    for row in rows:
        expected = {"exact": 1, "integrated": 2, "reconstructed": 3, "missing": 4}[row.status]
        if row.classification != expected:
            raise ValueError("fidelity status and primary-source classification disagree")
        if row.status == "missing" and (
            row.gap_type != "unpublished" or not row.unavailable_reason.strip()
        ):
            raise ValueError("missing requires a checked public-source unavailability reason")
        if any(
            not field.strip()
            for field in (row.published_behavior, row.implementation, row.remaining_gap)
        ):
            raise ValueError("fidelity explanations must not be blank")
        if len(set(row.commits)) != len(row.commits):
            raise ValueError("component commit references must be distinct")
        if row.status != "missing" and not any(
            path.startswith("tests/") for path in row.test_evaluation
        ):
            raise ValueError("implemented components require executable test evidence")
        if root:
            for reference in [*row.implementation_files, *row.test_evaluation]:
                target = _evidence_path(root, reference)
                parts = reference.split("::")
                if len(parts) > 1:
                    if target.suffix != ".py" or len(parts) != 2:
                        raise ValueError(f"unsupported test evidence reference: {reference}")
                    names = {
                        node.name
                        for node in ast.walk(ast.parse(target.read_text()))
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    }
                    if parts[1] not in names or not parts[1].startswith("test_"):
                        raise ValueError(f"missing matrix test node: {reference}")
            for reference in row.evidence:
                if not reference.startswith("https://"):
                    _evidence_path(root, reference)
    if verify_commits:
        if root is None:
            raise ValueError("a repository root is required to verify commits")
        for commit in sorted({commit for row in rows for commit in row.commits}):
            result = subprocess.run(
                ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
                cwd=root,
                capture_output=True,
                check=False,
            )
            if result.returncode:
                raise ValueError(f"matrix commit is absent from this history: {commit}")
    if value.get("scientific_parity") is not False:
        raise ValueError("parity requires measured external evidence and a new audited schema")


def render_report(value: dict[str, Any], *, prefix: str = "") -> str:
    """Render both reviewable reports from the validated canonical matrix."""
    validate_matrix(value)
    lines = [
        "# ScientistTwo fidelity report",
        "",
        f"Evidence reviewed: {value['reviewed_at']}.",
        "",
        "This report records implemented behavior and its evidence. Reconstructed means the published behavior is implemented with a local runtime; it does not mean the component was left unimplemented. Integrated means released upstream code is executed. Missing is reserved for specifically unpublished upstream artifacts.",
        "",
        "The honest prototype import is `6936a17`. Subsequent focused branches contain tests and independent review records. This is an independent implementation, not the authors' code or a measured reproduction of their research performance.",
        "",
        "Measured evidence includes offline integration/regression tests, public-data baseline executions and a retained live literature smoke record. Paid end-to-end writing, Docker/TeX execution and the original 107-task research benchmark are not certified. Simulated review scores are not venue acceptance probabilities.",
        "",
        "The loop retains the initial assessment plus up to two experimental rebuttal/revision cycles (the Table 5 interpretation); `seed_count=8` and `initial_candidates=2` are explicit local assumptions. See the paper specification for other substitutions and limits.",
        "",
        "| Component / status | Published behavior | Implementation | Commits | Tests / evidence | Remaining gap |",
        "|---|---|---|---|---|---|",
    ]

    def text(content: str) -> str:
        return content.replace("|", "\\|").replace("\n", " ")

    def link(reference: str) -> str:
        if reference.startswith("https://"):
            return f"[source]({reference})"
        target = prefix + reference.split("::")[0]
        return f"[{text(reference)}]({target})"

    for row in value["components"]:
        files = "; ".join(link(path) for path in row["implementation_files"])
        evidence = "; ".join(link(path) for path in row["test_evaluation"])
        sources = "; ".join(link(path) for path in row["evidence"])
        commits = ", ".join(f"`{commit}`" for commit in row["commits"])
        lines.append(
            "| "
            + " | ".join(
                [
                    text(row["component"]) + " / **" + row["status"] + "**",
                    text(row["published_behavior"]) + " " + sources,
                    text(row["implementation"]) + " " + files,
                    commits,
                    evidence,
                    text(row["remaining_gap"]),
                ]
            )
            + " |"
        )
    lines += [
        "",
        "## Continuing the work",
        "",
        f"Read [development workflow]({prefix}docs/development.md), [architecture]({prefix}docs/architecture.md), [paper specification]({prefix}docs/paper-spec.md), [evaluation guide]({prefix}docs/evaluation.md) and the focused plans/reviews before changing a component. Git history plus those documents and private persisted experiment state are the handoff.",
        "",
        "The canonical matrix is `docs/fidelity.json`; its packaged copy powers the CLI and consoles. Run `PYTHONPATH=src python scripts/update_fidelity_report.py` after editing it. CI validates stage coverage, source/test paths, test node names, commit ancestry, both JSON copies and these generated reports.",
        "",
    ]
    return "\n".join(lines)
