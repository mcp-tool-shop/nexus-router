# nexus-router

Event-sourced MCP router with provenance + integrity.

## Brand + Tool ID

- Brand/repo: `nexus-router`
- Python package: `nexus_router`
- MCP tool ID: `nexus-router.run`

## Install (dev)

```bash
pip install -e .
```

## Quick example

```python
from nexus_router.tool import run

resp = run({
  "goal": "demo",
  "mode": "dry_run",
  "plan_override": []
})

print(resp["run"]["run_id"])
print(resp["summary"])
```

## Persistence

Default `db_path=":memory:"` is ephemeral. Pass a file path to persist runs:

```python
resp = run({"goal": "demo"}, db_path="nexus-router.db")
```

## Portability (v0.3+)

Export runs as portable bundles and import into other databases:

```python
from nexus_router.tool import run, export, import_bundle, replay

# Create a run
resp = run({"goal": "demo", "mode": "dry_run", "plan_override": []}, db_path="source.db")
run_id = resp["run"]["run_id"]

# Export to bundle
bundle = export({"db_path": "source.db", "run_id": run_id})["artifact"]

# Import into another database
result = import_bundle({"db_path": "target.db", "bundle": bundle})
print(result["imported_run_id"])  # same run_id
print(result["replay_ok"])        # True (auto-verified)
```

**Conflict modes:**
- `reject_on_conflict` (default): Fail if run_id exists
- `new_run_id`: Generate new run_id, remap all references
- `overwrite`: Replace existing run

## Inspection & Replay (v0.2+)

```python
from nexus_router.tool import inspect, replay

# List runs in a database
info = inspect({"db_path": "nexus.db"})
print(info["counts"])  # {"total": 5, "completed": 4, "failed": 1, "running": 0}

# Replay and check invariants
result = replay({"db_path": "nexus.db", "run_id": "..."})
print(result["ok"])          # True if no violations
print(result["violations"])  # [] or list of issues
```

## What this version is (and isn't)

v0.3.0 is a correct, minimal event-sourced router core with full portability:

- Event log with monotonic sequencing
- Policy gating (`allow_apply`, `max_steps`)
- Schema validation on all requests
- Provenance bundle with SHA256 digest
- Export/import with integrity verification
- Replay with invariant checking
- Fixture-driven planning (`plan_override`)

It does not dispatch real tools yet (that's planned for v0.4+).

## Concurrency

Single-writer per run. Concurrent writers to the same run_id are unsupported.
