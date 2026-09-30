"""Supported process and filesystem boundaries shared by trusted runtime components.

These primitives do not authorize commands or sandbox model code. Callers own the
execution policy, private workspace selection, environment allowlist and receipts.
"""

from .errors import ExecutionError
from .filesystem import (
    copy_file,
    file_identity,
    parent_descriptor,
    read_text,
    relative_parts,
    write_file,
)
from .process import ProcessResult, run_process
from .programs import program_source
from .serialization import content_digest

__all__ = [
    "ExecutionError",
    "file_identity",
    "copy_file",
    "ProcessResult",
    "content_digest",
    "parent_descriptor",
    "program_source",
    "read_text",
    "relative_parts",
    "run_process",
    "write_file",
]
