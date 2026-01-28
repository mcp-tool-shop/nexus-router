"""Tests for the adapter implementation."""

from __future__ import annotations

import pytest

# TODO: Replace with your actual package name
from nexus_router_adapter_example import (
    ADAPTER_KIND,
    ADAPTER_MANIFEST,
    DEFAULT_CAPABILITIES,
    ExampleAdapter,
    create_adapter,
)


class TestCreateAdapter:
    """Test the create_adapter factory function."""

    def test_create_adapter_default(self) -> None:
        """create_adapter() returns valid adapter with defaults."""
        adapter = create_adapter()

        assert adapter.adapter_id == ADAPTER_KIND
        assert adapter.adapter_kind == ADAPTER_KIND
        assert adapter.capabilities == DEFAULT_CAPABILITIES

    def test_create_adapter_custom_id(self) -> None:
        """create_adapter() accepts custom adapter_id."""
        adapter = create_adapter(adapter_id="my-custom-id")

        assert adapter.adapter_id == "my-custom-id"

    # TODO: Add tests for your specific config parameters


class TestAdapterProtocol:
    """Test adapter implements DispatchAdapter protocol correctly."""

    def test_adapter_id_property(self) -> None:
        """adapter_id is a non-empty string."""
        adapter = create_adapter()
        assert isinstance(adapter.adapter_id, str)
        assert len(adapter.adapter_id) > 0

    def test_adapter_kind_property(self) -> None:
        """adapter_kind matches ADAPTER_KIND constant."""
        adapter = create_adapter()
        assert adapter.adapter_kind == ADAPTER_KIND

    def test_capabilities_property(self) -> None:
        """capabilities is a frozenset of strings."""
        adapter = create_adapter()
        assert isinstance(adapter.capabilities, frozenset)
        for cap in adapter.capabilities:
            assert isinstance(cap, str)

    def test_call_is_callable(self) -> None:
        """call() method is callable."""
        adapter = create_adapter()
        assert callable(adapter.call)


class TestAdapterCall:
    """Test adapter.call() behavior."""

    def test_call_returns_dict(self) -> None:
        """call() returns a dict."""
        adapter = create_adapter()
        result = adapter.call("test_tool", "test_method", {"arg": "value"})
        assert isinstance(result, dict)

    # TODO: Add tests for your specific call behavior
    # TODO: Add tests for error handling (timeouts, connection failures, etc.)


class TestManifest:
    """Test ADAPTER_MANIFEST is valid."""

    def test_manifest_schema_version(self) -> None:
        """Manifest has schema_version 1."""
        assert ADAPTER_MANIFEST["schema_version"] == 1

    def test_manifest_kind_matches(self) -> None:
        """Manifest kind matches ADAPTER_KIND."""
        assert ADAPTER_MANIFEST["kind"] == ADAPTER_KIND

    def test_manifest_capabilities_match(self) -> None:
        """Manifest capabilities match DEFAULT_CAPABILITIES."""
        manifest_caps = set(ADAPTER_MANIFEST["capabilities"])
        assert manifest_caps == DEFAULT_CAPABILITIES


class TestValidation:
    """Test adapter passes nexus-router validation."""

    def test_validate_adapter(self) -> None:
        """Adapter passes validate_adapter() checks."""
        from nexus_router.plugins import validate_adapter

        # TODO: Update factory_ref to match your package name
        result = validate_adapter(
            "nexus_router_adapter_example:create_adapter",
            config={},  # TODO: Add minimal config if needed
        )

        assert result.ok is True, f"Validation failed: {[c.message for c in result.errors]}"

    def test_inspect_adapter(self) -> None:
        """Adapter passes inspect_adapter() and has manifest data."""
        from nexus_router.plugins import inspect_adapter

        # TODO: Update factory_ref to match your package name
        result = inspect_adapter(
            "nexus_router_adapter_example:create_adapter",
            config={},  # TODO: Add minimal config if needed
        )

        assert result.ok is True
        assert result.adapter_kind == ADAPTER_KIND
        assert result.manifest is not None
