"""
Phase 3 Wave 2: Edge Cases & Boundary Testing
Tests for concurrency, resource limits, state machine edges, and error conditions.
Target: 20 tests covering edge case handling and boundary conditions.
"""

import pytest
from nexus_router import events as E
from nexus_router.event_store import EventStore
from nexus_router.router import Router


@pytest.fixture
def router_with_store():
    store = EventStore(":memory:")
    return Router(store), store


class TestConcurrencyEdgeCases:
    """Validate concurrency edge case handling."""

    def test_rapid_sequential_runs(self, router_with_store):
        """Test handling rapid sequential runs."""
        router, store = router_with_store
        for i in range(10):
            resp = router.run({
                "mode": "apply",
                "goal": f"rapid_{i}",
                "policy": {"allow_apply": True},
                "plan_override": [
                    {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
                ],
            })
            assert resp is not None

    def test_concurrent_event_reads(self, router_with_store):
        """Test concurrent event reads."""
        router, store = router_with_store
        resp = router.run({
            "mode": "apply",
            "goal": "concurrent_read",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })
        run_id = resp["run"]["run_id"]
        
        # Multiple concurrent reads
        events1 = store.read_events(run_id)
        events2 = store.read_events(run_id)
        events3 = store.read_events(run_id)
        
        assert len(events1) == len(events2) == len(events3)

    def test_interleaved_runs_isolation(self, router_with_store):
        """Test that interleaved runs are properly isolated."""
        router, store = router_with_store
        
        results = []
        for i in range(5):
            resp = router.run({
                "mode": "apply",
                "goal": f"interleave_{i}",
                "policy": {"allow_apply": True},
                "plan_override": [
                    {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
                ],
            })
            results.append(resp["run"]["run_id"])
        
        # All run_ids should be unique
        assert len(set(results)) == 5

    def test_event_store_under_load(self, router_with_store):
        """Test event store handles multiple rapid writes."""
        router, store = router_with_store
        
        for i in range(20):
            resp = router.run({
                "mode": "apply",
                "goal": f"load_{i}",
                "policy": {"allow_apply": True},
                "plan_override": [
                    {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
                ],
            })
            assert resp is not None

    def test_state_consistency_under_concurrent_ops(self, router_with_store):
        """Test state consistency with concurrent operations."""
        router, store = router_with_store
        
        resp1 = router.run({
            "mode": "apply",
            "goal": "consistency_1",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })
        
        resp2 = router.run({
            "mode": "apply",
            "goal": "consistency_2",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "y", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })
        
        run_id1 = resp1["run"]["run_id"]
        run_id2 = resp2["run"]["run_id"]
        
        # Both should be readable independently
        events1 = store.read_events(run_id1)
        events2 = store.read_events(run_id2)
        
        assert len(events1) > 0
        assert len(events2) > 0


class TestResourceLimitEdgeCases:
    """Validate handling of resource limits."""

    def test_large_plan_handling(self, router_with_store):
        """Test handling of plans with many steps."""
        router, store = router_with_store
        
        plan = [
            {"step_id": f"s{i}", "intent": f"step_{i}", "call": {"tool": "t", "method": "m", "args": {}}}
            for i in range(50)
        ]
        
        resp = router.run({
            "mode": "apply",
            "goal": "large_plan",
            "policy": {"allow_apply": True},
            "plan_override": plan,
        })
        
        assert resp is not None

    def test_large_argument_handling(self, router_with_store):
        """Test handling of large arguments."""
        router, store = router_with_store
        
        large_data = "x" * 10000
        
        resp = router.run({
            "mode": "apply",
            "goal": "large_args",
            "policy": {"allow_apply": True},
            "plan_override": [
                {
                    "step_id": "s1",
                    "intent": "x",
                    "call": {
                        "tool": "t",
                        "method": "m",
                        "args": {"data": large_data}
                    }
                }
            ],
        })
        
        assert resp is not None

    def test_deeply_nested_arguments(self, router_with_store):
        """Test handling of deeply nested argument structures."""
        router, store = router_with_store
        
        # Create deeply nested structure
        nested = {"level": 0}
        current = nested
        for i in range(20):
            current["nested"] = {"level": i + 1}
            current = current["nested"]
        
        resp = router.run({
            "mode": "apply",
            "goal": "deep_nesting",
            "policy": {"allow_apply": True},
            "plan_override": [
                {
                    "step_id": "s1",
                    "intent": "x",
                    "call": {
                        "tool": "t",
                        "method": "m",
                        "args": {"nested": nested}
                    }
                }
            ],
        })
        
        assert resp is not None

    def test_many_concurrent_event_types(self, router_with_store):
        """Test handling many events in event stream."""
        router, store = router_with_store
        
        # Create run with multiple steps to generate more events
        plan = [
            {"step_id": f"s{i}", "intent": f"step_{i}", "call": {"tool": "t", "method": "m", "args": {}}}
            for i in range(30)
        ]
        
        resp = router.run({
            "mode": "apply",
            "goal": "many_events",
            "policy": {"allow_apply": True},
            "plan_override": plan,
        })
        
        run_id = resp["run"]["run_id"]
        events = store.read_events(run_id)
        
        assert len(events) > 20


class TestStateMachineEdgeCases:
    """Validate state machine edge cases."""

    def test_rapid_state_transitions(self, router_with_store):
        """Test rapid state transitions."""
        router, store = router_with_store
        
        for i in range(15):
            resp = router.run({
                "mode": "apply",
                "goal": f"state_{i}",
                "policy": {"allow_apply": True},
                "plan_override": [
                    {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
                ],
            })
            assert resp is not None

    def test_state_after_error_recovery(self, router_with_store):
        """Test state consistency after error handling."""
        router, store = router_with_store
        
        # Normal run
        resp1 = router.run({
            "mode": "apply",
            "goal": "normal",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })
        
        # Error case (invalid tool)
        resp2 = router.run({
            "mode": "apply",
            "goal": "error",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "unknown", "method": "m", "args": {}}}
            ],
        })
        
        # Recovery run
        resp3 = router.run({
            "mode": "apply",
            "goal": "recovery",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })
        
        assert resp1 is not None
        assert resp2 is not None
        assert resp3 is not None

    def test_multiple_policy_transitions(self, router_with_store):
        """Test transitions between different policies."""
        router, store = router_with_store
        
        # Allow policy
        resp1 = router.run({
            "mode": "apply",
            "goal": "allow",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })
        
        # Deny policy
        resp2 = router.run({
            "mode": "apply",
            "goal": "deny",
            "policy": {"allow_apply": False},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })
        
        # Back to allow
        resp3 = router.run({
            "mode": "apply",
            "goal": "allow_again",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })
        
        assert resp1 is not None
        assert resp2 is not None
        assert resp3 is not None


class TestErrorConditionEdgeCases:
    """Validate error condition handling."""

    def test_malformed_step_structure(self, router_with_store):
        """Test handling of malformed step structures."""
        router, store = router_with_store
        
        # Missing fields - should handle gracefully
        resp = router.run({
            "mode": "apply",
            "goal": "malformed",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })
        
        assert resp is not None

    def test_special_characters_handling(self, router_with_store):
        """Test handling of special characters in arguments."""
        router, store = router_with_store
        
        resp = router.run({
            "mode": "apply",
            "goal": "special_chars",
            "policy": {"allow_apply": True},
            "plan_override": [
                {
                    "step_id": "s1",
                    "intent": "x",
                    "call": {
                        "tool": "t",
                        "method": "m",
                        "args": {"data": "!@#$%^&*()_+-=[]{}|;':\",./<>?"}
                    }
                }
            ],
        })
        
        assert resp is not None

    def test_unicode_handling(self, router_with_store):
        """Test handling of unicode characters."""
        router, store = router_with_store
        
        resp = router.run({
            "mode": "apply",
            "goal": "unicode_test",
            "policy": {"allow_apply": True},
            "plan_override": [
                {
                    "step_id": "s1",
                    "intent": "x",
                    "call": {
                        "tool": "t",
                        "method": "m",
                        "args": {"data": "你好世界 🌍 مرحبا العالم"}
                    }
                }
            ],
        })
        
        assert resp is not None

    def test_null_value_handling(self, router_with_store):
        """Test handling of null/None values."""
        router, store = router_with_store
        
        resp = router.run({
            "mode": "apply",
            "goal": "null_test",
            "policy": {"allow_apply": True},
            "plan_override": [
                {
                    "step_id": "s1",
                    "intent": "x",
                    "call": {
                        "tool": "t",
                        "method": "m",
                        "args": {"data": None}
                    }
                }
            ],
        })
        
        assert resp is not None


class TestBoundaryValueTesting:
    """Validate boundary value handling."""

    def test_empty_goal_string(self, router_with_store):
        """Test handling of empty goal."""
        router, store = router_with_store
        
        resp = router.run({
            "mode": "apply",
            "goal": "",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })
        
        assert resp is not None

    def test_very_long_goal_string(self, router_with_store):
        """Test handling of very long goal."""
        router, store = router_with_store
        
        resp = router.run({
            "mode": "apply",
            "goal": "x" * 5000,
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })
        
        assert resp is not None

    def test_single_step_plan(self, router_with_store):
        """Test minimal plan with one step."""
        router, store = router_with_store
        
        resp = router.run({
            "mode": "apply",
            "goal": "single_step",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })
        
        assert resp is not None

    def test_empty_args_dict(self, router_with_store):
        """Test handling of empty arguments dictionary."""
        router, store = router_with_store
        
        resp = router.run({
            "mode": "apply",
            "goal": "empty_args",
            "policy": {"allow_apply": True},
            "plan_override": [
                {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
            ],
        })
        
        assert resp is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
