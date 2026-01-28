from nexus_router import events as E
from nexus_router.dispatch import FakeAdapter
from nexus_router.event_store import EventStore
from nexus_router.router import Router


def test_apply_allowed_succeeds():
    """Apply mode succeeds with an adapter that has 'apply' capability."""
    store = EventStore(":memory:")
    # FakeAdapter has 'apply' capability by default
    adapter = FakeAdapter()
    adapter.set_response("t", "m", {"result": "applied"})
    router = Router(store, adapter=adapter)

    resp = router.run({
        "mode": "apply",
        "goal": "test",
        "policy": {"allow_apply": True},
        "plan_override": [
            {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
        ],
    })

    run_id = resp["run"]["run_id"]
    types = [e.type for e in store.read_events(run_id)]
    assert E.RUN_COMPLETED in types
    assert resp["results"][0]["simulated"] is False
