"""
Toy adapter package for testing plugin loading.

This is a minimal adapter implementation used to test the
nexus_router.plugins.load_adapter() mechanism.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Optional


# Optional metadata
ADAPTER_KIND = "toy"
DEFAULT_CAPABILITIES = frozenset({"dry_run", "apply"})

# Adapter manifest (v0.10+)
ADAPTER_MANIFEST = {
    "schema_version": 1,
    "kind": "toy",
    "capabilities": ["apply", "dry_run"],
    "supported_router_versions": ">=0.9,<1.0",
    "config_schema": {
        "adapter_id": {
            "type": "string",
            "required": False,
            "default": "toy",
            "description": "Custom adapter ID",
        },
        "prefix": {
            "type": "string",
            "required": False,
            "default": "default",
            "description": "Prefix to include in responses",
        },
    },
    "error_codes": [],
}


class ToyAdapter:
    """A minimal adapter for testing."""

    def __init__(
        self,
        *,
        adapter_id: str = "toy",
        prefix: str = "toy",
        capabilities: Optional[FrozenSet[str]] = None,
    ) -> None:
        self._adapter_id = adapter_id
        self._prefix = prefix
        self._capabilities = capabilities or DEFAULT_CAPABILITIES

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def adapter_kind(self) -> str:
        return ADAPTER_KIND

    @property
    def capabilities(self) -> FrozenSet[str]:
        return self._capabilities

    def call(self, tool: str, method: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Return a response with the configured prefix."""
        return {
            "prefix": self._prefix,
            "tool": tool,
            "method": method,
            "args": args,
            "result": f"{self._prefix}:{tool}:{method}",
        }


def create_adapter(
    *,
    adapter_id: Optional[str] = None,
    prefix: str = "default",
    capabilities: Optional[FrozenSet[str]] = None,
) -> ToyAdapter:
    """
    Factory function for creating ToyAdapter instances.

    Args:
        adapter_id: Optional custom ID. Defaults to "toy".
        prefix: Prefix to include in responses.
        capabilities: Optional custom capabilities.

    Returns:
        A ToyAdapter instance.
    """
    return ToyAdapter(
        adapter_id=adapter_id or "toy",
        prefix=prefix,
        capabilities=capabilities,
    )


# For testing error cases
def create_adapter_raises(**config: Any) -> ToyAdapter:
    """Factory that raises an error."""
    raise ValueError("Intentional factory error for testing")


def not_callable_thing() -> None:
    """A function that returns None (invalid adapter)."""
    return None


# Not a function - for testing non-callable detection
NOT_A_FUNCTION = "this is a string"


class IncompleteAdapter:
    """Adapter missing protocol fields for testing."""

    @property
    def adapter_id(self) -> str:
        return "incomplete"

    # Missing: adapter_kind, capabilities, call


def create_incomplete_adapter(**config: Any) -> IncompleteAdapter:
    """Factory that returns an incomplete adapter."""
    return IncompleteAdapter()
