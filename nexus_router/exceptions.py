"""Exception taxonomy for nexus-router dispatch."""

from __future__ import annotations

from typing import Any, Dict, Optional


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

    Attributes:
        error_code: Machine-readable error category (e.g., TIMEOUT, NONZERO_EXIT)
        details: Optional dict with additional context (e.g., timeout_s, stderr_excerpt)
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "OPERATIONAL_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


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

    Attributes:
        error_code: Machine-readable error category
        details: Optional dict with additional context
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "BUG_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}
