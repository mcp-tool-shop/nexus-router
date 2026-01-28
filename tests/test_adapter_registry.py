"""Tests for AdapterRegistry (v0.6 platform feature)."""

from __future__ import annotations

import pytest

from nexus_router.dispatch import (
    CAPABILITY_APPLY,
    CAPABILITY_DRY_RUN,
    CAPABILITY_EXTERNAL,
    CAPABILITY_TIMEOUT,
    AdapterRegistry,
    FakeAdapter,
    NullAdapter,
    SubprocessAdapter,
)
from nexus_router.exceptions import NexusOperationalError


class TestAdapterCapabilities:
    """Test capability declarations on built-in adapters."""

    def test_null_adapter_capabilities(self) -> None:
        """NullAdapter has only dry_run capability."""
        adapter = NullAdapter()
        assert adapter.capabilities == frozenset({CAPABILITY_DRY_RUN})
        assert CAPABILITY_APPLY not in adapter.capabilities

    def test_fake_adapter_default_capabilities(self) -> None:
        """FakeAdapter has dry_run and apply by default."""
        adapter = FakeAdapter()
        assert CAPABILITY_DRY_RUN in adapter.capabilities
        assert CAPABILITY_APPLY in adapter.capabilities

    def test_fake_adapter_custom_capabilities(self) -> None:
        """FakeAdapter can have custom capabilities."""
        caps = frozenset({CAPABILITY_DRY_RUN, CAPABILITY_TIMEOUT})
        adapter = FakeAdapter(capabilities=caps)
        assert adapter.capabilities == caps
        assert CAPABILITY_APPLY not in adapter.capabilities

    def test_subprocess_adapter_capabilities(self) -> None:
        """SubprocessAdapter has apply, timeout, and external capabilities."""
        adapter = SubprocessAdapter(base_cmd=["echo"])
        assert CAPABILITY_APPLY in adapter.capabilities
        assert CAPABILITY_TIMEOUT in adapter.capabilities
        assert CAPABILITY_EXTERNAL in adapter.capabilities
        assert CAPABILITY_DRY_RUN not in adapter.capabilities


class TestAdapterRegistryBasics:
    """Test basic registry operations."""

    def test_register_and_get(self) -> None:
        """Can register and retrieve adapters."""
        registry = AdapterRegistry()
        adapter = FakeAdapter(adapter_id="test-adapter")
        registry.register(adapter)

        retrieved = registry.get("test-adapter")
        assert retrieved is adapter

    def test_get_nonexistent_raises(self) -> None:
        """Getting unknown adapter raises KeyError."""
        registry = AdapterRegistry()
        with pytest.raises(KeyError, match="not-registered"):
            registry.get("not-registered")

    def test_duplicate_registration_raises(self) -> None:
        """Registering same ID twice raises ValueError."""
        registry = AdapterRegistry()
        adapter1 = FakeAdapter(adapter_id="dup")
        adapter2 = FakeAdapter(adapter_id="dup")

        registry.register(adapter1)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(adapter2)

    def test_default_adapter(self) -> None:
        """Registry returns default adapter."""
        registry = AdapterRegistry(default_adapter_id="my-default")
        adapter = FakeAdapter(adapter_id="my-default")
        registry.register(adapter)

        assert registry.get_default() is adapter
        assert registry.default_adapter_id == "my-default"

    def test_default_adapter_not_registered(self) -> None:
        """Default adapter must be registered to be retrieved."""
        registry = AdapterRegistry(default_adapter_id="missing")
        with pytest.raises(KeyError):
            registry.get_default()


class TestAdapterRegistryListing:
    """Test registry listing and filtering."""

    def test_list_ids(self) -> None:
        """list_ids returns all registered adapter IDs."""
        registry = AdapterRegistry()
        registry.register(FakeAdapter(adapter_id="a"))
        registry.register(FakeAdapter(adapter_id="b"))
        registry.register(NullAdapter(adapter_id="c"))

        ids = registry.list_ids()
        assert set(ids) == {"a", "b", "c"}

    def test_list_adapters(self) -> None:
        """list_adapters returns adapter info dicts."""
        registry = AdapterRegistry()
        registry.register(FakeAdapter(adapter_id="fake1"))
        registry.register(NullAdapter(adapter_id="null1"))

        adapters = registry.list_adapters()
        assert len(adapters) == 2

        adapter_map = {a["adapter_id"]: a for a in adapters}
        assert "fake1" in adapter_map
        assert "null1" in adapter_map
        assert set(adapter_map["fake1"]["capabilities"]) == {
            CAPABILITY_DRY_RUN,
            CAPABILITY_APPLY,
        }
        assert set(adapter_map["null1"]["capabilities"]) == {CAPABILITY_DRY_RUN}

    def test_find_by_capability(self) -> None:
        """find_by_capability returns adapters with specific capability."""
        registry = AdapterRegistry()
        registry.register(FakeAdapter(adapter_id="fake1"))
        registry.register(
            FakeAdapter(
                adapter_id="fake2", capabilities=frozenset({CAPABILITY_DRY_RUN})
            )
        )
        registry.register(NullAdapter(adapter_id="null1"))

        # All three have dry_run
        dry_run_ids = registry.find_by_capability(CAPABILITY_DRY_RUN)
        assert set(dry_run_ids) == {"fake1", "fake2", "null1"}

        # Only fake1 has apply
        apply_ids = registry.find_by_capability(CAPABILITY_APPLY)
        assert apply_ids == ["fake1"]


class TestAdapterRegistryCapabilityEnforcement:
    """Test capability checking and enforcement."""

    def test_has_capability(self) -> None:
        """has_capability checks if adapter has capability."""
        registry = AdapterRegistry()
        registry.register(FakeAdapter(adapter_id="fake"))
        registry.register(NullAdapter(adapter_id="null"))

        assert registry.has_capability("fake", CAPABILITY_APPLY)
        assert registry.has_capability("fake", CAPABILITY_DRY_RUN)
        assert not registry.has_capability("null", CAPABILITY_APPLY)
        assert registry.has_capability("null", CAPABILITY_DRY_RUN)

    def test_require_capability_passes(self) -> None:
        """require_capability passes when adapter has capability."""
        registry = AdapterRegistry()
        registry.register(FakeAdapter(adapter_id="fake"))

        # Should not raise
        registry.require_capability("fake", CAPABILITY_APPLY)

    def test_require_capability_fails(self) -> None:
        """require_capability raises when adapter lacks capability."""
        registry = AdapterRegistry()
        registry.register(NullAdapter(adapter_id="null"))

        with pytest.raises(NexusOperationalError) as exc_info:
            registry.require_capability("null", CAPABILITY_APPLY)

        assert exc_info.value.error_code == "CAPABILITY_MISSING"
        assert "null" in exc_info.value.details["adapter_id"]
        assert exc_info.value.details["required_capability"] == CAPABILITY_APPLY
