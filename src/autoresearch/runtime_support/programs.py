"""Read packaged standalone programs as source without importing or executing them."""

from importlib.resources import files
from typing import Literal

ProgramName = Literal[
    "demo_benchmark",
    "evaluation_model",
    "evaluation_scorer",
    "evaluation_train",
    "slurm_runner",
]
PROGRAM_NAMES: tuple[ProgramName, ...] = (
    "demo_benchmark",
    "evaluation_model",
    "evaluation_scorer",
    "evaluation_train",
    "slurm_runner",
)


def program_source(name: ProgramName) -> str:
    """Return an allowlisted program for copying into a private execution workspace.

    The files are deliberately standalone: remote workers and experiment images
    need Python and task dependencies, not the orchestration package itself.
    """
    if name not in PROGRAM_NAMES:
        raise ValueError("Unknown packaged runtime program")
    return (
        files("autoresearch")
        .joinpath("assets", "programs", f"{name}.py")
        .read_text(encoding="utf-8")
    )
