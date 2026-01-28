"""Exception taxonomy for nexus-router dispatch."""

from __future__ import annotations


class NexusError(Exception):
    """Base class for all nexus-router exceptions."""

    pass


class NexusOperationalError(NexusError):
    """
    Expected failures during dispatch.

    Examples:
    - Tool returned an error response
    - Timeout waiting for tool
    - Validation failure on tool input/output
    - Subprocess returned non-zero exit code

    These are recorded as TOOL_CALL_FAILED and cause RUN_FAILED,
    but do NOT re-raise (the run terminates gracefully).
    """

    def __init__(self, message: str, *, error_code: str = "OPERATIONAL_ERROR") -> None:
        super().__init__(message)
        self.error_code = error_code


class NexusBugError(NexusError):
    """
    Unexpected failures indicating a bug.

    Examples:
    - Invariant violation in router logic
    - Serialization/deserialization bugs
    - Internal coding errors
    - Adapter implementation bugs

    These are recorded as TOOL_CALL_FAILED (or RUN_FAILED),
    then re-raised so the caller sees the exception.
    """

    def __init__(self, message: str, *, error_code: str = "BUG_ERROR") -> None:
        super().__init__(message)
        self.error_code = error_code
