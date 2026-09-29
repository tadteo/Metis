"""Shared runtime boundary exceptions."""


class ExecutionError(ValueError):
    """A command, workspace, or scheduler request failed validation."""
