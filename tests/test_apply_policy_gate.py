from nexus_router.event_store import EventStore
from nexus_router.router import Router
from nexus_router import events as E

def test_apply_denied_causes_run_failed():
    store = EventStore(":memory:")
    router = Router(store)

    resp = router.run({
        "mode": "apply",
        "goal": "test",
        "policy": {"allow_apply": False},
        "plan_override": [{"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}],
    })

    run_id = resp["run"]["run_id"]
    types = [e.type for e in store.read_events(run_id)]
    assert E.RUN_FAILED in types
