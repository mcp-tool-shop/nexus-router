"""Tests for Router with AdapterRegistry (v0.6 platform feature)."""

from __future__ import annotations

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

    def test_registry_takes_precedence_over_adapter(self) -> None:
        """When both adapter and adapters are provided, registry wins."""
        store = EventStore(":memory:")

        legacy_adapter = FakeAdapter(adapter_id="legacy")
        registry = AdapterRegistry(default_adapter_id="registry-default")
        registry_adapter = FakeAdapter(adapter_id="registry-default")
        registry.register(registry_adapter)

        router = Router(store, adapter=legacy_adapter, adapters=registry)

        # Router should use registry's default, not legacy adapter
        assert router.adapter.adapter_id == "registry-default"

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
