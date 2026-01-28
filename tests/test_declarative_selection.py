"""Tests for declarative adapter selection (v0.7 feature)."""

from __future__ import annotations

import pytest

from nexus_router import events as E
from nexus_router.dispatch import (
    CAPABILITY_APPLY,
    CAPABILITY_DRY_RUN,
    CAPABILITY_TIMEOUT,
    AdapterRegistry,
    FakeAdapter,
    NullAdapter,
    SubprocessAdapter,
)
from nexus_router.event_store import EventStore
from nexus_router.router import Router
from nexus_router.tool import run


class TestRequestSelectsAdapter:
    """Test that request dispatch.adapter_id selects the adapter."""

    def test_request_selects_adapter_by_id(self) -> None:
        """Request can explicitly select an adapter by ID."""
        store = EventStore(":memory:")
        registry = AdapterRegistry(default_adapter_id="default-fake")

        default_adapter = FakeAdapter(adapter_id="default-fake")
        selected_adapter = FakeAdapter(adapter_id="selected-adapter")
        selected_adapter.set_response("t", "m", {"from": "selected"})

        registry.register(default_adapter)
        registry.register(selected_adapter)

        router = Router(store, adapters=registry)
        resp = router.run(
            {
                "mode": "apply",
                "goal": "test selection",
                "policy": {"allow_apply": True},
                "dispatch": {"adapter_id": "selected-adapter"},
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test",
                        "call": {"tool": "t", "method": "m", "args": {}},
                    }
                ],
            }
        )

        # Should use selected adapter, not default
        assert resp["dispatch"]["adapter_id"] == "selected-adapter"
        assert resp["dispatch"]["selection_source"] == "request"
        assert resp["results"][0]["output"]["from"] == "selected"

    def test_dispatch_selected_event_emitted(self) -> None:
        """DISPATCH_SELECTED event is emitted with selection details."""
        store = EventStore(":memory:")
        registry = AdapterRegistry(default_adapter_id="fake")
        adapter = FakeAdapter(adapter_id="fake")
        adapter.set_response("t", "m", {"ok": True})
        registry.register(adapter)

        router = Router(store, adapters=registry)
        resp = router.run(
            {
                "mode": "apply",
                "goal": "test dispatch event",
                "policy": {"allow_apply": True},
                "dispatch": {"adapter_id": "fake"},
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
        assert payload["adapter_id"] == "fake"
        assert payload["adapter_kind"] == "fake"
        assert payload["selection_source"] == "request"
        assert set(payload["capabilities"]) == {CAPABILITY_DRY_RUN, CAPABILITY_APPLY}


class TestDefaultAdapterUsed:
    """Test that default adapter is used when no dispatch specified."""

    def test_no_dispatch_uses_default(self) -> None:
        """Without dispatch object, default adapter is used."""
        store = EventStore(":memory:")
        registry = AdapterRegistry(default_adapter_id="the-default")

        adapter = FakeAdapter(adapter_id="the-default")
        adapter.set_response("t", "m", {"default": True})
        registry.register(adapter)
        registry.register(FakeAdapter(adapter_id="not-default"))

        router = Router(store, adapters=registry)
        resp = router.run(
            {
                "mode": "apply",
                "goal": "test default",
                "policy": {"allow_apply": True},
                # No dispatch object
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test",
                        "call": {"tool": "t", "method": "m", "args": {}},
                    }
                ],
            }
        )

        assert resp["dispatch"]["adapter_id"] == "the-default"
        assert resp["dispatch"]["selection_source"] == "default"

    def test_empty_dispatch_uses_default(self) -> None:
        """Empty dispatch object uses default adapter."""
        store = EventStore(":memory:")
        registry = AdapterRegistry(default_adapter_id="my-default")
        adapter = FakeAdapter(adapter_id="my-default")
        adapter.set_response("t", "m", {"ok": True})
        registry.register(adapter)

        router = Router(store, adapters=registry)
        resp = router.run(
            {
                "mode": "apply",
                "goal": "test empty dispatch",
                "policy": {"allow_apply": True},
                "dispatch": {},  # Empty dispatch
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test",
                        "call": {"tool": "t", "method": "m", "args": {}},
                    }
                ],
            }
        )

        assert resp["dispatch"]["adapter_id"] == "my-default"
        assert resp["dispatch"]["selection_source"] == "default"


class TestUnknownAdapterFails:
    """Test that unknown adapter ID causes operational failure."""

    def test_unknown_adapter_fails_run(self) -> None:
        """Unknown adapter_id causes run failure with UNKNOWN_ADAPTER."""
        store = EventStore(":memory:")
        registry = AdapterRegistry(default_adapter_id="exists")
        registry.register(FakeAdapter(adapter_id="exists"))

        router = Router(store, adapters=registry)
        resp = router.run(
            {
                "mode": "dry_run",
                "goal": "test unknown adapter",
                "dispatch": {"adapter_id": "does-not-exist"},
                "plan_override": [],
            }
        )

        # Run should fail with error response
        assert "error" in resp
        assert resp["error"]["code"] == "UNKNOWN_ADAPTER"
        assert resp["dispatch"]["selection_source"] == "failed"

        # Event stream should show failure
        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)
        failed_events = [e for e in events if e.type == E.RUN_FAILED]
        assert len(failed_events) == 1
        assert failed_events[0].payload["error_code"] == "UNKNOWN_ADAPTER"

    def test_unknown_adapter_shows_available(self) -> None:
        """Unknown adapter error includes list of available adapters."""
        store = EventStore(":memory:")
        registry = AdapterRegistry(default_adapter_id="a")
        registry.register(FakeAdapter(adapter_id="a"))
        registry.register(FakeAdapter(adapter_id="b"))

        router = Router(store, adapters=registry)
        resp = router.run(
            {
                "mode": "dry_run",
                "goal": "test error details",
                "dispatch": {"adapter_id": "unknown"},
                "plan_override": [],
            }
        )

        # Error message should include available adapters
        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)
        failed = [e for e in events if e.type == E.RUN_FAILED][0]
        assert set(failed.payload["details"]["available_adapters"]) == {"a", "b"}


class TestRequireCapabilitiesEnforced:
    """Test that dispatch.require_capabilities is enforced."""

    def test_required_capability_present_succeeds(self) -> None:
        """Adapter with required capability succeeds."""
        store = EventStore(":memory:")
        registry = AdapterRegistry(default_adapter_id="fake")
        adapter = FakeAdapter(adapter_id="fake")  # Has dry_run and apply
        adapter.set_response("t", "m", {"ok": True})
        registry.register(adapter)

        router = Router(store, adapters=registry)
        resp = router.run(
            {
                "mode": "apply",
                "goal": "test require capabilities",
                "policy": {"allow_apply": True},
                "dispatch": {
                    "adapter_id": "fake",
                    "require_capabilities": ["apply", "dry_run"],
                },
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

    def test_required_capability_missing_fails_run(self) -> None:
        """Adapter missing required capability fails run."""
        store = EventStore(":memory:")
        registry = AdapterRegistry(default_adapter_id="null")
        registry.register(NullAdapter(adapter_id="null"))  # Only has dry_run

        router = Router(store, adapters=registry)
        resp = router.run(
            {
                "mode": "dry_run",
                "goal": "test require timeout",
                "dispatch": {
                    "adapter_id": "null",
                    "require_capabilities": ["timeout"],  # NullAdapter lacks this
                },
                "plan_override": [],
            }
        )

        # Run should fail with CAPABILITY_MISSING
        assert "error" in resp
        assert resp["error"]["code"] == "CAPABILITY_MISSING"

        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)
        failed = [e for e in events if e.type == E.RUN_FAILED][0]
        assert failed.payload["error_code"] == "CAPABILITY_MISSING"

    def test_require_capabilities_multiple(self) -> None:
        """Multiple required capabilities all enforced."""
        store = EventStore(":memory:")
        registry = AdapterRegistry(default_adapter_id="fake")
        # FakeAdapter with only dry_run capability
        adapter = FakeAdapter(
            adapter_id="fake",
            capabilities=frozenset({CAPABILITY_DRY_RUN}),
        )
        registry.register(adapter)

        router = Router(store, adapters=registry)
        resp = router.run(
            {
                "mode": "dry_run",
                "goal": "test multiple require",
                "dispatch": {
                    "require_capabilities": ["dry_run", "apply"],  # apply is missing
                },
                "plan_override": [],
            }
        )

        # Should fail on missing apply
        assert "error" in resp
        assert resp["error"]["code"] == "CAPABILITY_MISSING"


class TestLegacyAdapterParameter:
    """Test legacy adapter parameter behavior in v0.7."""

    def test_legacy_adapter_wrapped_in_registry(self) -> None:
        """Single adapter param creates temporary registry."""
        store = EventStore(":memory:")
        adapter = FakeAdapter(adapter_id="legacy-adapter")
        adapter.set_response("t", "m", {"legacy": True})

        # Using legacy pattern
        router = Router(store, adapter=adapter)
        resp = router.run(
            {
                "mode": "apply",
                "goal": "test legacy",
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

        assert resp["dispatch"]["adapter_id"] == "legacy-adapter"
        assert resp["results"][0]["output"]["legacy"] is True

    def test_dual_adapter_raises_value_error(self) -> None:
        """Providing both adapter and adapters raises ValueError."""
        store = EventStore(":memory:")
        adapter = FakeAdapter(adapter_id="single")
        registry = AdapterRegistry(default_adapter_id="registry")
        registry.register(FakeAdapter(adapter_id="registry"))

        with pytest.raises(ValueError, match="Cannot provide both"):
            Router(store, adapter=adapter, adapters=registry)


class TestDispatchResponseSection:
    """Test the dispatch section in response."""

    def test_response_includes_dispatch_section(self) -> None:
        """Response always includes dispatch section."""
        store = EventStore(":memory:")
        registry = AdapterRegistry(default_adapter_id="fake")
        adapter = FakeAdapter(adapter_id="fake")
        adapter.set_response("t", "m", {"ok": True})
        registry.register(adapter)

        router = Router(store, adapters=registry)
        resp = router.run(
            {
                "mode": "apply",
                "goal": "test response",
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

        assert "dispatch" in resp
        assert resp["dispatch"]["adapter_id"] == "fake"
        assert resp["dispatch"]["adapter_kind"] == "fake"
        assert resp["dispatch"]["selection_source"] == "default"

    def test_tool_run_includes_dispatch(self, tmp_path) -> None:
        """tool.run() response includes dispatch section."""
        db_path = str(tmp_path / "test.db")
        registry = AdapterRegistry(default_adapter_id="fake")
        adapter = FakeAdapter(adapter_id="fake")
        adapter.set_response("t", "m", {"ok": True})
        registry.register(adapter)

        resp = run(
            {
                "goal": "test tool.run dispatch",
                "mode": "apply",
                "policy": {"allow_apply": True},
                "dispatch": {"adapter_id": "fake"},
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

        assert resp["dispatch"]["adapter_id"] == "fake"
        assert resp["dispatch"]["selection_source"] == "request"
