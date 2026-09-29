"""Machine-checkable fidelity evidence; architecture never implies measured parity."""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .contracts import Model, Stage


class Component(Model):
    component: str
    published_behavior: str
    implementation: str
    status: Literal["exact", "integrated", "reconstructed", "missing"]
    classification: Literal[1, 2, 3, 4]
    category: Literal["paper_fidelity", "engineering_extension", "user_model_substitution", "capability_evaluation"]
    evidence: list[str] = Field(min_length=1)
    test_evaluation: list[str] = Field(min_length=1)
    remaining_gap: str
    unavailable_reason: str = ""


def load_matrix() -> dict[str, Any]:
    path = Path(__file__).parent / "assets" / "fidelity.json"
    value: dict[str, Any] = json.loads(path.read_text())
    validate_matrix(value)
    return value


def validate_matrix(value: dict[str, Any], root: Path | None = None) -> None:
    if value.get("schema_version") != 1:
        raise ValueError("unsupported fidelity matrix schema")
    rows = [Component.model_validate(row) for row in value["components"]]
    ids = [row.component for row in rows]
    if len(ids) != len(set(ids)) or not {stage.value for stage in Stage}.issubset(ids):
        raise ValueError("matrix must cover every stage exactly once")
    for row in rows:
        if row.status == "missing" and (row.classification != 4 or not row.unavailable_reason):
            raise ValueError("missing requires a checked primary-source unavailability reason")
        if root:
            for filename in row.test_evaluation:
                if not (root / filename.split("::")[0]).is_file():
                    raise ValueError(f"missing matrix validation artifact: {filename}")
    if value.get("scientific_parity") is not False:
        raise ValueError("parity requires measured external evidence and a new audited schema")
