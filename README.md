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

## What v0.1.1 is (and isn't)

This release is a correct, minimal event-sourced router core:

- event log with monotonic sequencing
- policy gating for apply (`allow_apply`, `max_steps`)
- schema validation on requests
- provenance bundle with sha256 digest
- fixture-driven plan (`plan_override`)

It does not dispatch real tools yet (that's v0.2+).

## Concurrency

v0.1.1 is single-writer per run. Concurrent writers to the same run_id are unsupported.
