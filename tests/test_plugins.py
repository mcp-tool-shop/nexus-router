"""Tests for plugin loading (v0.8 feature)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nexus_router import events as E
from nexus_router.dispatch import AdapterRegistry, CAPABILITY_APPLY, CAPABILITY_DRY_RUN
from nexus_router.event_store import EventStore
from nexus_router.plugins import AdapterLoadError, get_adapter_metadata, load_adapter
from nexus_router.router import Router


# Add fixtures directory to path for testing
FIXTURES_DIR = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIXTURES_DIR))


class TestLoadAdapterBasics:
    """Test basic load_adapter functionality."""

    def test_load_adapter_success(self) -> None:
        """Successfully load adapter from toy package."""
        adapter = load_adapter("toy_adapter_pkg:create_adapter")

        assert adapter.adapter_id == "toy"
        assert adapter.adapter_kind == "toy"
        assert CAPABILITY_DRY_RUN in adapter.capabilities
        assert CAPABILITY_APPLY in adapter.capabilities

    def test_load_adapter_with_config(self) -> None:
        """Load adapter with configuration options."""
        adapter = load_adapter(
            "toy_adapter_pkg:create_adapter",
            adapter_id="custom-id",
            prefix="my-prefix",
        )

        assert adapter.adapter_id == "custom-id"

        # Verify config is used
        result = adapter.call("tool", "method", {"x": 1})
        assert result["prefix"] == "my-prefix"

    def test_load_adapter_call_works(self) -> None:
        """Loaded adapter can execute calls."""
        adapter = load_adapter(
            "toy_adapter_pkg:create_adapter",
            prefix="test",
        )

        result = adapter.call("my-tool", "my-method", {"arg": "value"})

        assert result["prefix"] == "test"
        assert result["tool"] == "my-tool"
        assert result["method"] == "my-method"
        assert result["args"] == {"arg": "value"}
        assert result["result"] == "test:my-tool:my-method"


class TestLoadAdapterErrors:
    """Test error handling in load_adapter."""

    def test_invalid_factory_ref_no_colon(self) -> None:
        """Invalid factory_ref without colon raises AdapterLoadError."""
        with pytest.raises(AdapterLoadError) as exc:
            load_adapter("invalid_format")

        assert exc.value.error_code == "ADAPTER_LOAD_FAILED"
        assert "Expected 'module:function'" in str(exc.value)
        assert exc.value.factory_ref == "invalid_format"

    def test_invalid_factory_ref_empty_module(self) -> None:
        """Invalid factory_ref with empty module raises AdapterLoadError."""
        with pytest.raises(AdapterLoadError) as exc:
            load_adapter(":function")

        assert "must be non-empty" in str(exc.value)

    def test_invalid_factory_ref_empty_function(self) -> None:
        """Invalid factory_ref with empty function raises AdapterLoadError."""
        with pytest.raises(AdapterLoadError) as exc:
            load_adapter("module:")

        assert "must be non-empty" in str(exc.value)

    def test_module_not_found(self) -> None:
        """Non-existent module raises AdapterLoadError."""
        with pytest.raises(AdapterLoadError) as exc:
            load_adapter("nonexistent_module_xyz:create_adapter")

        assert exc.value.error_code == "ADAPTER_LOAD_FAILED"
        assert "Failed to import module" in str(exc.value)
        assert exc.value.cause is not None

    def test_function_not_found(self) -> None:
        """Non-existent function raises AdapterLoadError."""
        with pytest.raises(AdapterLoadError) as exc:
            load_adapter("toy_adapter_pkg:nonexistent_function")

        assert "has no attribute" in str(exc.value)

    def test_not_callable(self) -> None:
        """Non-callable attribute raises AdapterLoadError."""
        with pytest.raises(AdapterLoadError) as exc:
            load_adapter("toy_adapter_pkg:NOT_A_FUNCTION")

        assert "is not callable" in str(exc.value)

    def test_factory_raises(self) -> None:
        """Factory that raises gets wrapped in AdapterLoadError."""
        with pytest.raises(AdapterLoadError) as exc:
            load_adapter("toy_adapter_pkg:create_adapter_raises")

        assert "Factory" in str(exc.value)
        assert "raised" in str(exc.value)
        assert exc.value.cause is not None
        assert "Intentional factory error" in str(exc.value.cause)

    def test_factory_returns_non_adapter(self) -> None:
        """Factory returning non-adapter raises AdapterLoadError."""
        with pytest.raises(AdapterLoadError) as exc:
            load_adapter("toy_adapter_pkg:not_callable_thing")

        assert "did not return a valid DispatchAdapter" in str(exc.value)


class TestGetAdapterMetadata:
    """Test adapter metadata extraction."""

    def test_get_metadata(self) -> None:
        """Extract metadata from adapter."""
        adapter = load_adapter(
            "toy_adapter_pkg:create_adapter",
            adapter_id="meta-test",
        )

        metadata = get_adapter_metadata(adapter)

        assert metadata["adapter_id"] == "meta-test"
        assert metadata["adapter_kind"] == "toy"
        assert set(metadata["capabilities"]) == {CAPABILITY_DRY_RUN, CAPABILITY_APPLY}


class TestPluginWithRouter:
    """Test loaded adapters work with Router."""

    def test_loaded_adapter_in_registry(self) -> None:
        """Loaded adapter can be registered and used."""
        adapter = load_adapter(
            "toy_adapter_pkg:create_adapter",
            adapter_id="loaded-toy",
            prefix="from-plugin",
        )

        registry = AdapterRegistry(default_adapter_id="loaded-toy")
        registry.register(adapter)

        store = EventStore(":memory:")
        router = Router(store, adapters=registry)

        resp = router.run(
            {
                "goal": "test plugin",
                "mode": "apply",
                "policy": {"allow_apply": True},
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test",
                        "call": {"tool": "t", "method": "m", "args": {"x": 1}},
                    }
                ],
            }
        )

        assert resp["dispatch"]["adapter_id"] == "loaded-toy"
        assert resp["dispatch"]["adapter_kind"] == "toy"
        assert resp["results"][0]["output"]["prefix"] == "from-plugin"

    def test_loaded_adapter_selected_by_dispatch(self) -> None:
        """Loaded adapter can be selected via dispatch.adapter_id."""
        toy1 = load_adapter(
            "toy_adapter_pkg:create_adapter",
            adapter_id="toy-1",
            prefix="one",
        )
        toy2 = load_adapter(
            "toy_adapter_pkg:create_adapter",
            adapter_id="toy-2",
            prefix="two",
        )

        registry = AdapterRegistry(default_adapter_id="toy-1")
        registry.register(toy1)
        registry.register(toy2)

        store = EventStore(":memory:")
        router = Router(store, adapters=registry)

        # Select toy-2 via dispatch
        resp = router.run(
            {
                "goal": "test dispatch selection",
                "mode": "apply",
                "policy": {"allow_apply": True},
                "dispatch": {"adapter_id": "toy-2"},
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test",
                        "call": {"tool": "t", "method": "m", "args": {}},
                    }
                ],
            }
        )

        assert resp["dispatch"]["adapter_id"] == "toy-2"
        assert resp["dispatch"]["selection_source"] == "request"
        assert resp["results"][0]["output"]["prefix"] == "two"

    def test_dispatch_selected_event_with_loaded_adapter(self) -> None:
        """DISPATCH_SELECTED event works with loaded adapters."""
        adapter = load_adapter(
            "toy_adapter_pkg:create_adapter",
            adapter_id="dispatch-test",
        )

        registry = AdapterRegistry(default_adapter_id="dispatch-test")
        registry.register(adapter)

        store = EventStore(":memory:")
        router = Router(store, adapters=registry)

        resp = router.run(
            {
                "goal": "test dispatch event",
                "mode": "apply",
                "policy": {"allow_apply": True},
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test",
                        "call": {"tool": "t", "method": "m", "args": {}},
                    }
                ],
            }
        )

        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)
        dispatch_events = [e for e in events if e.type == E.DISPATCH_SELECTED]

        assert len(dispatch_events) == 1
        payload = dispatch_events[0].payload
        assert payload["adapter_id"] == "dispatch-test"
        assert payload["adapter_kind"] == "toy"
        assert set(payload["capabilities"]) == {CAPABILITY_DRY_RUN, CAPABILITY_APPLY}


class TestPluginWithCustomCapabilities:
    """Test loaded adapters with custom capabilities."""

    def test_require_capabilities_with_loaded_adapter(self) -> None:
        """require_capabilities enforced for loaded adapters."""
        # Adapter with only dry_run capability
        adapter = load_adapter(
            "toy_adapter_pkg:create_adapter",
            adapter_id="dry-only",
            capabilities=frozenset({"dry_run"}),
        )

        registry = AdapterRegistry(default_adapter_id="dry-only")
        registry.register(adapter)

        store = EventStore(":memory:")
        router = Router(store, adapters=registry)

        # Request requires 'apply' capability
        resp = router.run(
            {
                "goal": "test require capabilities",
                "mode": "dry_run",
                "dispatch": {
                    "require_capabilities": ["apply"],  # adapter lacks this
                },
                "plan_override": [],
            }
        )

        # Should fail with CAPABILITY_MISSING
        assert "error" in resp
        assert resp["error"]["code"] == "CAPABILITY_MISSING"
