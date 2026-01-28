"""
nexus-router-adapter-{kind}: {Kind} adapter for nexus-router.

Replace this module with your actual adapter implementation.
Rename the package from nexus_router_adapter_example to nexus_router_adapter_{kind}.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Optional

from nexus_router.dispatch import CAPABILITY_APPLY
from nexus_router.exceptions import NexusOperationalError

__all__ = [
    "ExampleAdapter",
    "create_adapter",
    "ADAPTER_KIND",
    "DEFAULT_CAPABILITIES",
    "ADAPTER_MANIFEST",
]
__version__ = "0.1.0"

# Module-level metadata (per ADAPTER_SPEC.md)
ADAPTER_KIND = "example"  # TODO: Change to your adapter kind
DEFAULT_CAPABILITIES: FrozenSet[str] = frozenset({CAPABILITY_APPLY})

# Adapter manifest (v0.10+)
ADAPTER_MANIFEST = {
    "schema_version": 1,
    "kind": "example",  # TODO: Must match ADAPTER_KIND
    "capabilities": ["apply"],  # TODO: Must match DEFAULT_CAPABILITIES
    "supported_router_versions": ">=0.12,<1.0",
    "config_schema": {
        "adapter_id": {
            "type": "string",
            "required": False,
            "description": "Custom adapter ID",
        },
        # TODO: Add your config parameters here
        # "your_param": {
        #     "type": "string",
        #     "required": True,
        #     "description": "Description of the parameter",
        # },
    },
    "error_codes": [
        # TODO: Add error codes your adapter may raise
        # "TIMEOUT",
        # "CONNECTION_FAILED",
    ],
}


class ExampleAdapter:
    """
    Example adapter implementation.

    TODO: Replace with your actual adapter class.
    Implements the DispatchAdapter protocol.
    """

    def __init__(
        self,
        *,
        adapter_id: Optional[str] = None,
        # TODO: Add your config parameters
    ) -> None:
        """
        Create an adapter instance.

        Args:
            adapter_id: Optional custom ID. Defaults to "{kind}".
            TODO: Document your parameters
        """
        self._adapter_id = adapter_id or ADAPTER_KIND
        self._capabilities = DEFAULT_CAPABILITIES
        # TODO: Initialize your adapter

    @property
    def adapter_id(self) -> str:
        """Stable identifier for this adapter instance."""
        return self._adapter_id

    @property
    def adapter_kind(self) -> str:
        """Type identifier."""
        return ADAPTER_KIND

    @property
    def capabilities(self) -> FrozenSet[str]:
        """Declared capabilities."""
        return self._capabilities

    def call(self, tool: str, method: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call.

        Args:
            tool: Tool name.
            method: Method name.
            args: Arguments dict.

        Returns:
            Result dict.

        Raises:
            NexusOperationalError: On expected failures (timeout, network, etc.)
        """
        # TODO: Implement your dispatch logic
        # Example:
        # try:
        #     result = self._client.call(tool, method, args)
        #     return result
        # except TimeoutError as e:
        #     raise NexusOperationalError(
        #         "Operation timed out",
        #         error_code="TIMEOUT",
        #         details={"tool": tool, "method": method},
        #     ) from e

        # Placeholder implementation
        return {
            "tool": tool,
            "method": method,
            "args": args,
            "result": "TODO: implement",
        }


def create_adapter(
    *,
    adapter_id: Optional[str] = None,
    # TODO: Add your config parameters
) -> ExampleAdapter:
    """
    Create an adapter instance.

    This is the standard factory function per ADAPTER_SPEC.md.

    Args:
        adapter_id: Optional custom ID.
        TODO: Document your parameters

    Returns:
        An adapter instance implementing DispatchAdapter protocol.
    """
    return ExampleAdapter(
        adapter_id=adapter_id,
        # TODO: Pass your config parameters
    )
