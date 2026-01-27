from nexus_router.event_store import EventStore
from nexus_router.router import Router
from nexus_router import events as E

def test_required_events_in_order_empty_plan():
    store = EventStore(":memory:")
    router = Router(store)

    resp = router.run({"mode": "dry_run", "goal": "test", "plan_override": []})
    run_id = resp["run"]["run_id"]

    types = [e.type for e in store.read_events(run_id)]
    assert types[0] == E.RUN_STARTED
    assert E.PLAN_CREATED in types
    assert E.PROVENANCE_EMITTED in types
    assert types[-1] == E.RUN_COMPLETED
