"""Dispatch adapters for nexus-router tool calls."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Protocol, Tuple

from .exceptions import NexusBugError, NexusOperationalError


class DispatchAdapter(Protocol):
    """
    Protocol for dispatch adapters.

    Adapters implement the transport layer for tool calls.
    The router decides what to call; the adapter decides how to call it.
    """

    @property
    def adapter_id(self) -> str:
        """Unique identifier for this adapter instance."""
        ...

    def call(self, tool: str, method: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call.

        Args:
            tool: Tool identifier (e.g., "file-system")
            method: Method name (e.g., "read_file")
            args: Arguments dict for the method

        Returns:
            JSON-serializable dict with the result.

        Raises:
            NexusOperationalError: For expected failures (timeout, tool error, etc.)
            NexusBugError: For unexpected failures (bugs in adapter)
            Other exceptions: Treated as bugs by the router
        """
        ...


class NullAdapter:
    """
    Adapter that returns deterministic placeholder outputs.

    Used for:
    - dry_run mode (default)
    - Testing without external dependencies
    - Development/debugging
    """

    def __init__(self, adapter_id: str = "null") -> None:
        self._adapter_id = adapter_id

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    def call(self, tool: str, method: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Return a deterministic placeholder result."""
        return {
            "simulated": True,
            "tool": tool,
            "method": method,
            "args_echo": args,
            "result": None,
        }


class FakeAdapter:
    """
    Adapter with configurable responses for testing.

    Allows tests to specify exact outputs or errors for specific
    (tool, method) combinations.
    """

    def __init__(self, adapter_id: str = "fake") -> None:
        self._adapter_id = adapter_id
        self._responses: Dict[Tuple[str, str], Callable[..., Dict[str, Any]]] = {}
        self._default_response: Optional[Callable[..., Dict[str, Any]]] = None
        self._call_log: list[Dict[str, Any]] = []

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def call_log(self) -> list[Dict[str, Any]]:
        """Log of all calls made to this adapter."""
        return self._call_log

    def set_response(
        self,
        tool: str,
        method: str,
        response: Dict[str, Any] | Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        """
        Set the response for a specific (tool, method) combination.

        Args:
            tool: Tool identifier
            method: Method name
            response: Either a dict to return, or a callable that takes args
                      and returns a dict (or raises an exception)
        """
        if callable(response):
            self._responses[(tool, method)] = response
        else:
            self._responses[(tool, method)] = lambda _args: response

    def set_default_response(
        self,
        response: Dict[str, Any] | Callable[[str, str, Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        """
        Set the default response for unregistered (tool, method) combinations.

        Args:
            response: Either a dict to return, or a callable that takes
                      (tool, method, args) and returns a dict
        """
        if callable(response):
            self._default_response = response
        else:
            self._default_response = lambda _t, _m, _a: response

    def set_operational_error(
        self,
        tool: str,
        method: str,
        message: str,
        error_code: str = "TOOL_ERROR",
    ) -> None:
        """Configure a specific call to raise NexusOperationalError."""

        def raise_error(_args: Dict[str, Any]) -> Dict[str, Any]:
            raise NexusOperationalError(message, error_code=error_code)

        self._responses[(tool, method)] = raise_error

    def set_bug_error(
        self,
        tool: str,
        method: str,
        message: str,
        error_code: str = "ADAPTER_BUG",
    ) -> None:
        """Configure a specific call to raise NexusBugError."""

        def raise_error(_args: Dict[str, Any]) -> Dict[str, Any]:
            raise NexusBugError(message, error_code=error_code)

        self._responses[(tool, method)] = raise_error

    def call(self, tool: str, method: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the configured response."""
        # Log the call
        self._call_log.append({"tool": tool, "method": method, "args": args})

        # Check for specific response
        key = (tool, method)
        if key in self._responses:
            return self._responses[key](args)

        # Check for default response
        if self._default_response is not None:
            return self._default_response(tool, method, args)

        # No response configured - return placeholder
        return {
            "fake": True,
            "tool": tool,
            "method": method,
            "args_echo": args,
            "result": None,
        }

    def reset(self) -> None:
        """Clear all configured responses and call log."""
        self._responses.clear()
        self._default_response = None
        self._call_log.clear()
