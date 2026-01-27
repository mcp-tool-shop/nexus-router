from nexus_router.event_store import EventStore
from nexus_router.router import Router
from nexus_router import events as E


def test_max_steps_exceeded_causes_run_failed():
    store = EventStore(":memory:")
    router = Router(store)

    resp = router.run({
        "mode": "dry_run",
        "goal": "test",
        "policy": {"max_steps": 1},
        "plan_override": [
            {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}},
            {"step_id": "s2", "intent": "y", "call": {"tool": "t", "method": "m", "args": {}}},
        ],
    })

    run_id = resp["run"]["run_id"]
    events = store.read_events(run_id)
    types = [e.type for e in events]
    assert E.RUN_FAILED in types

    failed_event = next(e for e in events if e.type == E.RUN_FAILED and e.payload.get("reason") == "max_steps_exceeded")
    assert failed_event.payload["max_steps"] == 1
    assert failed_event.payload["plan_steps"] == 2


def test_max_steps_boundary_allowed():
    store = EventStore(":memory:")
    router = Router(store)

    resp = router.run({
        "mode": "dry_run",
        "goal": "test",
        "policy": {"max_steps": 2},
        "plan_override": [
            {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}},
            {"step_id": "s2", "intent": "y", "call": {"tool": "t", "method": "m", "args": {}}},
        ],
    })

    run_id = resp["run"]["run_id"]
    types = [e.type for e in store.read_events(run_id)]
    assert E.RUN_COMPLETED in types
