# Nexus-Router Architecture

## Philosophy

**The router is the law. Adapters are citizens.**

Nexus-router is a deterministic orchestration layer for AI tool execution. It provides:

1. **Plan-driven execution** - Steps are declared, not improvised
2. **Full event sourcing** - Every state change is recorded and replayable
3. **Capability governance** - Adapters declare what they can do; the router enforces it
4. **Mode separation** - `dry_run` simulates, `apply` executes

## Core Concepts

### Execution Modes

| Mode | Adapter Called? | Side Effects? | Use Case |
|------|-----------------|---------------|----------|
| `dry_run` | Never | No | Planning, validation, cost estimation |
| `apply` | Yes | Yes | Actual tool execution |

The router enforces this strictly:
- In `dry_run` mode, the adapter is **never called**, regardless of its capabilities
- In `apply` mode, the adapter **must have** the `apply` capability

### The Adapter Protocol

Adapters implement a simple protocol:

```python
class DispatchAdapter(Protocol):
    @property
    def adapter_id(self) -> str:
        """Stable identifier for this adapter."""
        ...

    @property
    def adapter_kind(self) -> str:
        """Type identifier (e.g., "null", "fake", "subprocess")."""
        ...

    @property
    def capabilities(self) -> FrozenSet[str]:
        """Declared capabilities."""
        ...

    def call(
        self, tool: str, method: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a tool call and return structured output."""
        ...
```

### Built-in Adapters

| Adapter | Capabilities | Purpose |
|---------|-------------|---------|
| `NullAdapter` | `dry_run` | Default adapter; simulation only |
| `FakeAdapter` | `dry_run`, `apply` | Testing; configurable responses |
| `SubprocessAdapter` | `apply`, `timeout`, `external` | Real subprocess execution |

### Capabilities

Standard capability constants:

| Capability | Meaning |
|------------|---------|
| `dry_run` | Safe for simulation mode |
| `apply` | Can execute real operations |
| `timeout` | Supports timeout constraints |
| `external` | Makes external network/system calls |

Adapters **must declare** their capabilities. The router **enforces** them at runtime:
- `apply` mode requires `CAPABILITY_APPLY`
- Missing capability → `CAPABILITY_MISSING` error → run fails gracefully

## The AdapterRegistry (v0.6+)

Multi-adapter support without global state:

```python
registry = AdapterRegistry(default_adapter_id="subprocess")
registry.register(SubprocessAdapter(base_cmd=["python", "tool.py"]))
registry.register(FakeAdapter(adapter_id="fake-for-tests"))

router = Router(store, adapters=registry)
```

### Registry API

```python
# Registration
registry.register(adapter)                    # Register adapter
registry.get("adapter-id")                    # Get by ID (raises KeyError if missing)
registry.get_default()                        # Get default adapter

# Introspection
registry.list_ids()                           # ["adapter1", "adapter2", ...]
registry.list_adapters()                      # [{"adapter_id": ..., "capabilities": [...]}, ...]
registry.find_by_capability("apply")          # ["adapter1", ...]

# Capability enforcement
registry.has_capability("adapter-id", "apply")     # True/False
registry.require_capability("adapter-id", "apply") # Raises NexusOperationalError if missing
```

### Tool Introspection

```python
from nexus_router.tool import list_adapters

result = list_adapters(registry)
# {"adapters": [...], "default_adapter_id": "...", "total": N}

result = list_adapters(registry, capability="apply")
# Filter by capability
```

## Declarative Adapter Selection (v0.7+)

Requests can explicitly select which adapter to use and require specific capabilities:

```python
# Request schema with dispatch section
request = {
    "goal": "process files",
    "mode": "apply",
    "dispatch": {
        "adapter_id": "subprocess:python:abc123",  # Explicit adapter
        "require_capabilities": ["timeout", "external"]  # Required capabilities
    },
    "plan_override": [...]
}
```

### Selection Order

1. If `dispatch.adapter_id` is specified → use that adapter (selection_source="request")
2. Else → use `registry.get_default()` (selection_source="default")

### Capability Enforcement

- If `dispatch.require_capabilities` is specified, all listed capabilities must be present
- `apply` mode always requires `CAPABILITY_APPLY` (implicit)
- Missing capability → `CAPABILITY_MISSING` error → run fails before any steps execute

### New Event Type

`DISPATCH_SELECTED` event is emitted after `RUN_STARTED`:

```json
{
  "adapter_id": "subprocess:python:abc123",
  "adapter_kind": "subprocess",
  "capabilities": ["apply", "timeout", "external"],
  "selection_source": "request"
}
```

### Error Codes

| Code | Meaning |
|------|---------|
| `UNKNOWN_ADAPTER` | Requested adapter_id not found in registry |
| `CAPABILITY_MISSING` | Adapter lacks a required capability |

### Response Dispatch Section

Every response includes a `dispatch` section:

```json
{
  "dispatch": {
    "adapter_id": "subprocess:python:abc123",
    "adapter_kind": "subprocess",
    "selection_source": "request"
  }
}
```

## Event Sourcing

Every run produces an immutable event stream:

```
RUN_STARTED → DISPATCH_SELECTED → PLAN_CREATED → STEP_STARTED → TOOL_CALL_REQUESTED →
  TOOL_CALL_SUCCEEDED|FAILED → STEP_COMPLETED → ... → RUN_COMPLETED|FAILED
```

Events are stored in SQLite with:
- Monotonic sequence numbers (no gaps)
- Timestamps
- JSON payloads

### Platform Invariants (v0.6.1+)

These invariants are **enforced** and **replay-visible**:

1. **TOOL_CALL_REQUESTED** always includes:
   - `adapter_id` - Which adapter will handle the call
   - `adapter_capabilities` - Capability snapshot at request time

2. **Capability failure** emits:
   - `TOOL_CALL_FAILED` with `error_code="CAPABILITY_MISSING"`
   - Terminal `RUN_FAILED` event
   - Details include `required_capability` and `adapter_capabilities`

3. **get_default()** is deterministic:
   - Returns the adapter matching `default_adapter_id` set at registry construction
   - Raises `KeyError` if that adapter is not registered

4. **Legacy `adapter` parameter** (v0.7+):
   - If both `adapter` and `adapters` provided, `ValueError` is raised
   - Single `adapter` is wrapped into a temporary registry (for backwards compatibility)
   - Prefer using `adapters` registry for new code

### Replay & Validation

```python
from nexus_router.tool import replay

result = replay({"db_path": "nexus.db", "run_id": "run-123"})
# Replays events and validates invariants
```

## Exception Taxonomy

```
NexusError (base)
├── NexusOperationalError  # Expected failures (timeout, permission, capability)
│   └── error_code: TIMEOUT, NONZERO_EXIT, CAPABILITY_MISSING, etc.
└── NexusBugError          # Unexpected failures (bugs, invariant violations)
    └── error_code: BUG_ERROR, UNKNOWN_ERROR, etc.
```

- **Operational errors** are recorded and terminate the step gracefully
- **Bug errors** are recorded and re-raised (caller sees exception)

## Platform Rules for Adapters

Adapters MUST:
1. **Declare capabilities honestly** - Don't claim `apply` if you can't execute
2. **Be deterministic** - Same inputs → same outputs (for replay)
3. **Not swallow bugs** - Re-raise `NexusBugError` after recording
4. **Not mutate global state** - Each adapter instance is independent
5. **Return structured output** - JSON-serializable dict

Adapters MUST NOT:
1. Call other adapters directly
2. Modify the event store
3. Bypass capability enforcement
4. Hold resources after `call()` returns

## Directory Structure

```
nexus_router/
├── tool.py          # Public API: run(), inspect(), replay(), export(), import_bundle()
├── router.py        # Core orchestration logic
├── dispatch.py      # Adapter protocol, registry, built-in adapters
├── event_store.py   # SQLite-backed event sourcing
├── events.py        # Event type constants
├── exceptions.py    # Exception taxonomy
├── policy.py        # Policy gates (allow_apply)
├── provenance.py    # Artifact provenance tracking
├── inspect.py       # Run inspection
├── replay.py        # Event replay and validation
├── export.py        # Bundle export
├── import_.py       # Bundle import
└── schema.py        # JSON Schema validation
```

## Version History

| Version | Changes |
|---------|---------|
| 0.1 | Initial release - basic routing |
| 0.2 | Event sourcing, provenance |
| 0.3 | Export/import bundles |
| 0.4 | SubprocessAdapter, exception taxonomy |
| 0.5 | Hardening: redaction, output limits, error codes |
| 0.6 | **Platform**: AdapterRegistry, capabilities, enforcement |
| 0.6.1 | Platform invariants: adapter_capabilities in events, adapter_kind, deprecation warning |
| 0.7 | **Declarative Selection**: dispatch.adapter_id, require_capabilities, DISPATCH_SELECTED event |
