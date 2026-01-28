# nexus-router

Event-sourced MCP router with provenance + integrity.

[![CI](https://github.com/mcp-tool-shop/nexus-router/actions/workflows/ci.yml/badge.svg)](https://github.com/mcp-tool-shop/nexus-router/actions/workflows/ci.yml)

## Platform Philosophy

- **Router is the law** — all execution flows through the event log
- **Adapters are citizens** — they follow the contract or they don't run
- **Contracts over conventions** — stability guarantees are versioned and enforced
- **Replay before execution** — every run can be verified after the fact
- **Validation before trust** — `validate_adapter()` runs before adapters touch production
- **Self-describing ecosystem** — manifests generate docs, not the other way around

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

## Dispatch Adapters (v0.4+)

Adapters execute tool calls. Pass an adapter to `run()`:

```python
from nexus_router.tool import run
from nexus_router.dispatch import SubprocessAdapter

# Create adapter for external command
adapter = SubprocessAdapter(
    ["python", "-m", "my_tool_cli"],
    timeout_s=30.0,
)

resp = run({
    "goal": "execute real tool",
    "mode": "apply",
    "policy": {"allow_apply": True},
    "plan_override": [
        {"step_id": "s1", "intent": "do something", "call": {"tool": "my-tool", "method": "action", "args": {"x": 1}}}
    ]
}, adapter=adapter)
```

### SubprocessAdapter

Calls external commands with this contract:

```bash
<base_cmd> call <tool> <method> --json-args-file <path>
```

The external command must:
- Read JSON payload from the args file: `{"tool": "...", "method": "...", "args": {...}}`
- Print JSON result to stdout on success
- Exit with code 0 on success, non-zero on failure

Error codes: `TIMEOUT`, `NONZERO_EXIT`, `INVALID_JSON_OUTPUT`, `COMMAND_NOT_FOUND`

### Built-in adapters

- `NullAdapter`: Returns simulated output (default, used in `dry_run`)
- `FakeAdapter`: Configurable responses for testing

## What this version is (and isn't)

v1.0 is a **platform-grade** event-sourced router with a complete adapter ecosystem:

**Core Router:**
- Event log with monotonic sequencing
- Policy gating (`allow_apply`, `max_steps`)
- Schema validation on all requests
- Provenance bundle with SHA256 digest
- Export/import with integrity verification
- Replay with invariant checking
- Error taxonomy: operational vs bug errors

**Adapter Ecosystem:**
- Formal adapter contract ([ADAPTER_SPEC.md](ADAPTER_SPEC.md))
- `validate_adapter()` — compliance lint tool
- `inspect_adapter()` — developer experience front door
- `generate_adapter_docs()` — auto-generated documentation
- CI template with validation gate
- Adapter template for 2-minute onboarding

## Concurrency

Single-writer per run. Concurrent writers to the same run_id are unsupported.

## Adapter Ecosystem (v0.8+)

Create custom adapters to dispatch tool calls to any backend.

### Official Adapters

| Adapter | Description | Install |
|---------|-------------|---------|
| [nexus-router-adapter-http](https://github.com/mcp-tool-shop/nexus-router-adapter-http) | HTTP/REST dispatch | `pip install nexus-router-adapter-http` |
| [nexus-router-adapter-stdout](https://github.com/mcp-tool-shop/nexus-router-adapter-stdout) | Debug logging | `pip install nexus-router-adapter-stdout` |

See [ADAPTERS.generated.md](ADAPTERS.generated.md) for full documentation.

### Creating Adapters

Use the [adapter template](https://github.com/mcp-tool-shop/nexus-router-adapter-template) to create new adapters in 2 minutes:

```bash
# Fork the template, then:
pip install -e ".[dev]"
pytest -v  # Validates against nexus-router spec
```

See [ADAPTER_SPEC.md](ADAPTER_SPEC.md) for the full contract.

### Validation Tools

```python
from nexus_router.plugins import inspect_adapter

result = inspect_adapter(
    "nexus_router_adapter_http:create_adapter",
    config={"base_url": "https://example.com"},
)
print(result.render())  # Human-readable validation report
```

## Versioning & Stability

### v1.x Guarantees

The following are **stable in v1.x** (breaking changes only in v2.0):

| Contract | Scope |
|----------|-------|
| Validation check IDs | `LOAD_OK`, `PROTOCOL_FIELDS`, `MANIFEST_*`, etc. |
| Manifest schema | `schema_version: 1` |
| Adapter factory signature | `create_adapter(*, adapter_id=None, **config)` |
| Capability set | `dry_run`, `apply`, `timeout`, `external` (additive only) |
| Event types | Core event payloads (additive only) |

### Deprecation Policy

- Deprecations announced in minor versions with warnings
- Removed in next major version
- Upgrade notes provided in release changelog

### Adapter Compatibility

Adapters declare supported router versions in their manifest:

```python
ADAPTER_MANIFEST = {
    "supported_router_versions": ">=1.0,<2.0",
    ...
}
```

The `validate_adapter()` tool checks compatibility.
