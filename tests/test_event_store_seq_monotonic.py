from nexus_router.event_store import EventStore

def test_seq_monotonic():
    store = EventStore(":memory:")
    run_id = store.create_run(mode="dry_run", goal="x")

    e0 = store.append(run_id, "A", {})
    e1 = store.append(run_id, "B", {})
    e2 = store.append(run_id, "C", {})

    assert [e0.seq, e1.seq, e2.seq] == [0, 1, 2]
