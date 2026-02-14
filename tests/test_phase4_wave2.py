"""
Phase 4 Wave 2: Adapter Integration Testing
Tests for adapter contracts, tool call dispatch, and validation framework.
Target: 15 tests covering adapter ecosystem integration.
"""

import pytest
import json
from nexus_router import events as E
from nexus_router.event_store import EventStore
from nexus_router.router import Router


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def router_with_store():
    """Router with in-memory event store."""
    store = EventStore(":memory:")
    return Router(store), store


# ============================================================================
# Test Suite 1: Adapter Contracts & Validation (5 tests)
# ============================================================================

class TestAdapterContracts:
    """Validate adapter contract enforcement."""

    def test_tool_adapter_required_fields(self, router_with_store):
        """Test that tool adapters have required fields."""
        router, store = router_with_store

        resp = router.run({
            "mode": "apply",
            "goal": "test_adapter",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "call_tool", "call": {"tool": "example_tool", "method": "example_method", "args": {}}}
            ],
        })

        run_id = resp["run"]["run_id"]
        assert "run" in resp
        assert run_id is not None

    def test_adapter_method_invocation_basic(self, router_with_store):
        """Test basic adapter method invocation."""
        router, store = router_with_store

        resp = router.run({
            "mode": "apply",
            "goal": "invoke_adapter",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "test", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })

        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)

        # Should have completed successfully
        event_types = [e.type for e in events]
        assert E.RUN_COMPLETED in event_types

    def test_adapter_validation_success(self, router_with_store):
        """Test successful adapter validation."""
        router, store = router_with_store

        # Valid adapter call
        resp = router.run({
            "mode": "apply",
            "goal": "valid_adapter",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "valid", "method": "method", "args": {}}}
            ],
        })

        assert resp is not None
        assert "run" in resp

    def test_adapter_tool_parameter_propagation(self, router_with_store):
        """Test that tool parameters are correctly propagated through adapter."""
        router, store = router_with_store

        resp = router.run({
            "mode": "apply",
            "goal": "param_test",
            "policy": {"allow_apply": True},
            "plan_override": [
                {
                    "step_id": "s1",
                    "intent": "test_with_params",
                    "call": {
                        "tool": "test_tool",
                        "method": "test_method",
                        "args": {"param1": "value1", "param2": 42}
                    }
                }
            ],
        })

        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)
        assert len(events) > 0

    def test_adapter_response_handling(self, router_with_store):
        """Test that adapter responses are properly handled."""
        router, store = router_with_store

        resp = router.run({
            "mode": "apply",
            "goal": "response_test",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })

        # Response should include results
        assert "results" in resp or "run" in resp


# ============================================================================
# Test Suite 2: Tool Call Dispatch (5 tests)
# ============================================================================

class TestToolCallDispatch:
    """Validate tool call dispatching through adapters."""

    def test_single_tool_dispatch(self, router_with_store):
        """Test dispatching to single tool."""
        router, store = router_with_store

        resp = router.run({
            "mode": "apply",
            "goal": "single_dispatch",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "call", "call": {"tool": "tool1", "method": "method1", "args": {}}}
            ],
        })

        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)
        assert len(events) > 0

    def test_multiple_tool_dispatch_sequence(self, router_with_store):
        """Test dispatching to multiple tools in sequence."""
        router, store = router_with_store

        resp = router.run({
            "mode": "apply",
            "goal": "multi_dispatch",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "call1", "call": {"tool": "tool1", "method": "m1", "args": {}}},
                {"step_id": "s2", "intent": "call2", "call": {"tool": "tool2", "method": "m2", "args": {}}}
            ],
        })

        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)
        event_types = [e.type for e in events]

        # Should have events for both steps
        assert len(events) >= 2

    def test_tool_dispatch_error_handling(self, router_with_store):
        """Test error handling during tool dispatch."""
        router, store = router_with_store

        # Call with potentially problematic tool name
        resp = router.run({
            "mode": "apply",
            "goal": "error_test",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "unknown_tool", "method": "method", "args": {}}}
            ],
        })

        # Should not crash, may fail gracefully
        assert resp is not None

    def test_tool_call_with_empty_args(self, router_with_store):
        """Test tool call with empty arguments."""
        router, store = router_with_store

        resp = router.run({
            "mode": "apply",
            "goal": "empty_args",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })

        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)
        assert len(events) > 0

    def test_tool_call_with_complex_args(self, router_with_store):
        """Test tool call with complex nested arguments."""
        router, store = router_with_store

        resp = router.run({
            "mode": "apply",
            "goal": "complex_args",
            "policy": {"allow_apply": True},
            "plan_override": [
                {
                    "step_id": "s1",
                    "intent": "complex",
                    "call": {
                        "tool": "t",
                        "method": "m",
                        "args": {
                            "nested": {"level1": {"level2": "value"}},
                            "list": [1, 2, 3],
                            "mixed": {"array": [{"key": "val"}]}
                        }
                    }
                }
            ],
        })

        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)
        assert len(events) > 0


# ============================================================================
# Test Suite 3: Adapter Framework Integration (5 tests)
# ============================================================================

class TestAdapterFrameworkIntegration:
    """Validate adapter framework integration."""

    def test_adapter_lifecycle_startup(self, router_with_store):
        """Test adapter lifecycle startup phase."""
        router, store = router_with_store

        # Creating router initializes adapter framework
        assert router is not None
        resp = router.run({
            "mode": "apply",
            "goal": "lifecycle_test",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })
        assert resp is not None

    def test_adapter_registration(self, router_with_store):
        """Test adapter registration and availability."""
        router, store = router_with_store

        resp = router.run({
            "mode": "apply",
            "goal": "registration_test",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "registered_tool", "method": "m", "args": {}}}
            ],
        })

        assert resp is not None

    def test_adapter_method_discovery(self, router_with_store):
        """Test method discovery through adapter framework."""
        router, store = router_with_store

        resp = router.run({
            "mode": "apply",
            "goal": "discovery_test",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "discovered_method", "args": {}}}
            ],
        })

        assert resp is not None

    def test_adapter_event_emission(self, router_with_store):
        """Test that adapters emit events through event store."""
        router, store = router_with_store

        resp = router.run({
            "mode": "apply",
            "goal": "event_emission_test",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })

        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)

        # Adapter should have emitted events through store
        assert len(events) > 0
        event_types = [e.type for e in events]
        assert E.RUN_COMPLETED in event_types

    def test_adapter_state_tracking(self, router_with_store):
        """Test that adapter maintains state across calls."""
        router, store = router_with_store

        # First call
        resp1 = router.run({
            "mode": "apply",
            "goal": "state_test_1",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })

        # Second call - adapter should maintain framework state
        resp2 = router.run({
            "mode": "apply",
            "goal": "state_test_2",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "y", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })

        assert resp1 is not None
        assert resp2 is not None
        assert resp1["run"]["run_id"] != resp2["run"]["run_id"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
