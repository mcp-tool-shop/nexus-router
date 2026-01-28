"""Tests for Router with AdapterRegistry (v0.6 platform feature)."""

from __future__ import annotations

import warnings

from nexus_router import events as E
from nexus_router.dispatch import (
    CAPABILITY_APPLY,
    CAPABILITY_DRY_RUN,
    AdapterRegistry,
    FakeAdapter,
    NullAdapter,
)
from nexus_router.event_store import EventStore
from nexus_router.router import Router
from nexus_router.tool import list_adapters, run


class TestRouterWithRegistry:
    """Test router integration with adapter registry."""

    def test_router_uses_registry_default(self) -> None:
        """Router uses registry's default adapter."""
        store = EventStore(":memory:")
        registry = AdapterRegistry(default_adapter_id="fake")
        adapter = FakeAdapter(adapter_id="fake")
        adapter.set_response("t", "m", {"result": "ok"})
        registry.register(adapter)

        router = Router(store, adapters=registry)
        resp = router.run(
            {
                "mode": "apply",
                "goal": "test registry",
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

        assert resp["summary"]["adapter_id"] == "fake"
        assert resp["results"][0]["status"] == "ok"

    def test_dual_adapter_raises_value_error(self) -> None:
        """Providing both adapter and adapters raises ValueError (v0.7+)."""
        import pytest

        store = EventStore(":memory:")

        legacy_adapter = FakeAdapter(adapter_id="legacy")
        registry = AdapterRegistry(default_adapter_id="registry-default")
        registry_adapter = FakeAdapter(adapter_id="registry-default")
        registry.register(registry_adapter)

        with pytest.raises(ValueError, match="Cannot provide both"):
            Router(store, adapter=legacy_adapter, adapters=registry)

    def test_dry_run_with_null_adapter_in_registry(self) -> None:
        """dry_run mode works with NullAdapter in registry."""
        store = EventStore(":memory:")
        registry = AdapterRegistry(default_adapter_id="null")
        registry.register(NullAdapter(adapter_id="null"))

        router = Router(store, adapters=registry)
        resp = router.run(
            {
                "mode": "dry_run",
                "goal": "test dry_run",
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test",
                        "call": {"tool": "t", "method": "m", "args": {}},
                    }
                ],
            }
        )

        assert resp["summary"]["adapter_id"] == "null"
        assert resp["results"][0]["simulated"] is True
        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)
        assert E.RUN_COMPLETED in [e.type for e in events]


class TestCapabilityEnforcementInRouter:
    """Test runtime capability enforcement."""

    def test_apply_mode_requires_apply_capability(self) -> None:
        """Apply mode fails when adapter lacks 'apply' capability."""
        store = EventStore(":memory:")
        # NullAdapter only has dry_run capability
        router = Router(store, adapter=NullAdapter())

        resp = router.run(
            {
                "mode": "apply",
                "goal": "test capability",
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

        # Run should fail with CAPABILITY_MISSING
        assert resp["results"][0]["status"] == "error"
        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)
        failed = [e for e in events if e.type == E.TOOL_CALL_FAILED]
        assert len(failed) == 1
        assert failed[0].payload["error_code"] == "CAPABILITY_MISSING"

    def test_apply_mode_succeeds_with_apply_capability(self) -> None:
        """Apply mode succeeds when adapter has 'apply' capability."""
        store = EventStore(":memory:")
        adapter = FakeAdapter(adapter_id="fake-with-apply")
        adapter.set_response("t", "m", {"applied": True})
        router = Router(store, adapter=adapter)

        resp = router.run(
            {
                "mode": "apply",
                "goal": "test capability",
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

        assert resp["results"][0]["status"] == "ok"
        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)
        assert E.RUN_COMPLETED in [e.type for e in events]


class TestListAdaptersTool:
    """Test the nexus-router.adapters introspection tool."""

    def test_list_adapters_basic(self) -> None:
        """list_adapters returns all registered adapters."""
        registry = AdapterRegistry(default_adapter_id="fake1")
        registry.register(FakeAdapter(adapter_id="fake1"))
        registry.register(NullAdapter(adapter_id="null1"))

        result = list_adapters(registry)

        assert result["total"] == 2
        assert result["default_adapter_id"] == "fake1"
        adapter_ids = [a["adapter_id"] for a in result["adapters"]]
        assert "fake1" in adapter_ids
        assert "null1" in adapter_ids

    def test_list_adapters_with_capability_filter(self) -> None:
        """list_adapters filters by capability."""
        registry = AdapterRegistry(default_adapter_id="fake1")
        registry.register(FakeAdapter(adapter_id="fake1"))
        registry.register(NullAdapter(adapter_id="null1"))

        # Filter for apply capability - only FakeAdapter has it
        result = list_adapters(registry, capability=CAPABILITY_APPLY)

        assert result["total"] == 1
        assert result["adapters"][0]["adapter_id"] == "fake1"

        # Filter for dry_run - both have it
        result = list_adapters(registry, capability=CAPABILITY_DRY_RUN)
        assert result["total"] == 2


class TestToolRunWithRegistry:
    """Test the tool.run() function with registry."""

    def test_run_with_registry(self, tmp_path) -> None:
        """run() accepts adapters registry."""
        db_path = str(tmp_path / "test.db")

        registry = AdapterRegistry(default_adapter_id="fake")
        adapter = FakeAdapter(adapter_id="fake")
        adapter.set_response("t", "m", {"done": True})
        registry.register(adapter)

        resp = run(
            {
                "goal": "test with registry",
                "mode": "apply",
                "policy": {"allow_apply": True},
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test",
                        "call": {"tool": "t", "method": "m", "args": {}},
                    }
                ],
            },
            db_path=db_path,
            adapters=registry,
        )

        assert resp["summary"]["adapter_id"] == "fake"
        assert resp["results"][0]["output"]["done"] is True


# =============================================================================
# v0.6.1 Platform Invariants Tests
# =============================================================================


class TestPlatformInvariants:
    """Test platform invariants introduced in v0.6.1."""

    def test_tool_call_requested_includes_adapter_capabilities(self) -> None:
        """TOOL_CALL_REQUESTED event includes adapter_capabilities snapshot."""
        store = EventStore(":memory:")
        adapter = FakeAdapter(adapter_id="test-adapter")
        adapter.set_response("t", "m", {"result": "ok"})
        router = Router(store, adapter=adapter)

        resp = router.run(
            {
                "mode": "apply",
                "goal": "test invariants",
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
        requested = [e for e in events if e.type == E.TOOL_CALL_REQUESTED]
        assert len(requested) == 1

        payload = requested[0].payload
        assert "adapter_id" in payload
        assert payload["adapter_id"] == "test-adapter"
        assert "adapter_capabilities" in payload
        assert set(payload["adapter_capabilities"]) == {
            CAPABILITY_DRY_RUN,
            CAPABILITY_APPLY,
        }

    def test_dual_adapter_raises_value_error_v07(self) -> None:
        """Providing both adapter and adapters raises ValueError (v0.7+)."""
        import pytest

        store = EventStore(":memory:")

        legacy = FakeAdapter(adapter_id="legacy")
        registry = AdapterRegistry(default_adapter_id="registry")
        registry.register(FakeAdapter(adapter_id="registry"))

        with pytest.raises(ValueError, match="Cannot provide both"):
            Router(store, adapter=legacy, adapters=registry)

    def test_list_adapters_includes_adapter_kind(self) -> None:
        """list_adapters response includes adapter_kind for each adapter."""
        registry = AdapterRegistry(default_adapter_id="fake1")
        registry.register(FakeAdapter(adapter_id="fake1"))
        registry.register(NullAdapter(adapter_id="null1"))

        result = list_adapters(registry)

        for adapter_info in result["adapters"]:
            assert "adapter_kind" in adapter_info

        adapter_map = {a["adapter_id"]: a for a in result["adapters"]}
        assert adapter_map["fake1"]["adapter_kind"] == "fake"
        assert adapter_map["null1"]["adapter_kind"] == "null"

    def test_list_adapters_with_filter_includes_adapter_kind(self) -> None:
        """list_adapters with capability filter includes adapter_kind."""
        registry = AdapterRegistry(default_adapter_id="fake1")
        registry.register(FakeAdapter(adapter_id="fake1"))

        result = list_adapters(registry, capability=CAPABILITY_APPLY)

        assert result["total"] == 1
        assert result["adapters"][0]["adapter_kind"] == "fake"
