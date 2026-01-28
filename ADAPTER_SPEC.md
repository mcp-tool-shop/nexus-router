# Nexus-Router Adapter Specification

Version: 1.0 (nexus-router v0.8+)

## Overview

This document defines the contract for nexus-router adapter packages. Adapters are external packages that provide dispatch implementations for tool execution.

## Stability Guarantees

### Spec Stability

The following are **stable within major version 0.x** (additive changes only):

1. **Factory signature**: `create_adapter(*, adapter_id: str | None = None, **config) -> DispatchAdapter`
2. **Required protocol fields**: `adapter_id`, `adapter_kind`, `capabilities`, `call()`
3. **Loader error type**: `AdapterLoadError` is the only exception `load_adapter()` raises

Breaking changes will only occur in major version bumps.

### Capability Governance

**Capabilities are core-defined.** Adapters MUST NOT invent new capabilities.

Current standard capabilities (nexus-router v0.8):
- `dry_run`, `apply`, `timeout`, `external`

To propose a new capability, open an issue on the nexus-router repository.

### Error Taxonomy

Adapters MUST map failures to the correct exception type:

| Failure Type | Exception | Router Behavior |
|--------------|-----------|-----------------|
| Expected (timeout, network, validation) | `NexusOperationalError` | Records event, terminates gracefully |
| Unexpected (bugs, invariants) | `NexusBugError` or propagate | Records event, re-raises |
| Load failure | N/A (loader handles) | `AdapterLoadError` raised to caller |

### Validation Check IDs

The `validate_adapter()` tool returns checks with stable IDs. **Check IDs are stable within 0.x** - they may be added but never renamed or removed.

| Check ID | Purpose |
|----------|---------|
| `LOAD_OK` | Factory loads without errors |
| `PROTOCOL_FIELDS` | Required fields exist and call() is callable |
| `ADAPTER_ID_FORMAT` | adapter_id is non-empty string |
| `ADAPTER_KIND_FORMAT` | adapter_kind is non-empty string |
| `CAPABILITIES_TYPE` | capabilities is iterable of strings |
| `CAPABILITIES_VALID` | Only standard capabilities declared |
| `MANIFEST_PRESENT` | Module exposes `ADAPTER_MANIFEST` (warn if absent) |
| `MANIFEST_SCHEMA` | Manifest has required fields with correct types |
| `MANIFEST_KIND_MATCH` | Manifest `kind` matches `adapter_kind` |
| `MANIFEST_CAPS_MATCH` | Manifest `capabilities` matches instance |

Adapter authors can write CI around these IDs with confidence.

## Package Contract

### Required Entrypoint

Every adapter package MUST expose a factory function:

```python
# your_adapter_package/__init__.py
from nexus_router.dispatch import DispatchAdapter

def create_adapter(*, adapter_id: str | None = None, **config) -> DispatchAdapter:
    """
    Create an adapter instance.

    Args:
        adapter_id: Optional custom ID. If None, use a sensible default.
        **config: Adapter-specific configuration.

    Returns:
        A DispatchAdapter instance.
    """
    ...
```

### Optional Metadata

Packages MAY expose module-level metadata for documentation purposes:

```python
ADAPTER_KIND = "http"
DEFAULT_CAPABILITIES = frozenset({"apply", "timeout", "external"})
```

**Note:** The adapter instance's `capabilities` property is the source of truth, not module-level constants.

### Adapter Manifest (Optional)

Packages MAY expose an `ADAPTER_MANIFEST` dict for machine-readable metadata:

```python
ADAPTER_MANIFEST = {
    "schema_version": 1,
    "kind": "http",
    "capabilities": ["apply", "timeout", "external"],
    "supported_router_versions": ">=0.9,<1.0",
    "config_schema": {
        "base_url": {
            "type": "string",
            "required": True,
            "description": "Base URL for HTTP dispatch",
        },
        "timeout_s": {
            "type": "number",
            "required": False,
            "default": 10,
            "description": "Request timeout in seconds",
        },
        "headers": {
            "type": "object",
            "required": False,
            "description": "Custom HTTP headers",
        },
    },
    "error_codes": ["TIMEOUT", "CONNECTION_FAILED", "HTTP_ERROR", "INVALID_JSON"],
}
```

#### Manifest Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | int | Yes | Always `1` for this spec version |
| `kind` | string | Yes | Must match `adapter_kind` property |
| `capabilities` | list[string] | Yes | Must match `capabilities` property |
| `supported_router_versions` | string | No | PEP 440 version specifier |
| `config_schema` | dict | No | Configuration key documentation |
| `error_codes` | list[string] | No | Error codes this adapter may raise |

#### Config Schema Entry

Each key in `config_schema` is a dict with:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | `"string"`, `"number"`, `"boolean"`, `"object"`, `"array"` |
| `required` | bool | Yes | Whether this config key is required |
| `default` | any | No | Default value if not provided |
| `description` | string | No | Human-readable description |

#### Manifest Governance

1. **Manifests are advisory** — the adapter instance is the source of truth
2. **Manifests must match** — `validate_adapter()` cross-checks manifest against instance
3. **Manifests cannot extend** — no new capabilities or fields beyond the spec
4. **Manifests are static** — pure data, no code execution

#### Validation Behavior

When `validate_adapter()` encounters a manifest:

| Scenario | Behavior |
|----------|----------|
| No manifest | `MANIFEST_PRESENT` emits warning (not failure) |
| Manifest exists | Validate schema and cross-check with instance |
| `kind` mismatch | `MANIFEST_KIND_MATCH` fails |
| `capabilities` mismatch | `MANIFEST_CAPS_MATCH` fails |
| Invalid schema | `MANIFEST_SCHEMA` fails |

## Adapter Protocol

Adapters MUST implement the `DispatchAdapter` protocol:

```python
from typing import Any, Dict, FrozenSet

class DispatchAdapter(Protocol):
    @property
    def adapter_id(self) -> str:
        """Stable identifier for this adapter instance."""
        ...

    @property
    def adapter_kind(self) -> str:
        """Type identifier (e.g., "http", "grpc", "subprocess")."""
        ...

    @property
    def capabilities(self) -> FrozenSet[str]:
        """Declared capabilities."""
        ...

    def call(self, tool: str, method: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool call and return structured output."""
        ...
```

## Capabilities

Adapters MUST declare capabilities from the standard set:

| Capability | Meaning | When to Declare |
|------------|---------|-----------------|
| `dry_run` | Safe for simulation | Can return meaningful simulated output |
| `apply` | Can execute operations | **Required for apply mode** |
| `timeout` | Enforces timeouts | Supports timeout configuration |
| `external` | Calls external systems | Makes network/system calls |

**Important:** Do NOT invent new capabilities. Capability names are controlled by nexus-router core. If you need a new capability, propose it upstream.

## Error Handling

### Expected Failures → NexusOperationalError

Use `NexusOperationalError` for expected failures:

```python
from nexus_router.exceptions import NexusOperationalError

raise NexusOperationalError(
    "Connection timeout after 30s",
    error_code="TIMEOUT",
    details={"url": url, "timeout_s": 30},
) from original_exception  # Use exception chaining to preserve cause
```

Standard error codes:
- `TIMEOUT` - Operation timed out
- `NONZERO_EXIT` - Process returned non-zero
- `INVALID_JSON` - Output was not valid JSON
- `CONNECTION_FAILED` - Network connection failed
- `HTTP_ERROR` - HTTP request failed (include status code in details)

### Unexpected Failures → NexusBugError or Let Exception Propagate

For bugs in your adapter code, either:
1. Raise `NexusBugError` with details
2. Let the exception propagate (router will record it)

```python
from nexus_router.exceptions import NexusBugError

raise NexusBugError(
    "Invariant violation: response missing required field",
    error_code="BUG_ERROR",
    details={"field": "result"},
)
```

## Security Requirements

### Redaction

Adapters MUST NOT include secrets in outputs or error details:

```python
# BAD - leaks API key
raise NexusOperationalError(
    "Auth failed",
    details={"api_key": "sk-secret123"}  # NEVER DO THIS
)

# GOOD - redact sensitive values
raise NexusOperationalError(
    "Auth failed",
    details={"api_key": "[REDACTED]"}
)
```

If your adapter accepts sensitive configuration (API keys, tokens), use redaction hooks:

```python
def _redact_config(config: dict) -> dict:
    """Redact sensitive config for logging/events."""
    safe = config.copy()
    for key in ("api_key", "token", "secret", "password"):
        if key in safe:
            safe[key] = "[REDACTED]"
    return safe
```

### No Global State

Adapters MUST NOT:
- Modify global variables on import
- Register themselves automatically
- Cache state between unrelated calls (unless explicitly documented)

## Determinism

Adapters SHOULD be deterministic:
- Same inputs → same outputs (where possible)
- Document any non-deterministic behavior (e.g., timestamps, random IDs)

This enables replay validation.

## Testing Requirements

Adapter packages SHOULD include:

1. **Unit tests** for the factory function
2. **Protocol compliance tests** verifying adapter_id, adapter_kind, capabilities
3. **Error handling tests** for expected failure modes
4. **Integration tests** (if applicable) with mocked external systems

Example test structure:

```python
def test_create_adapter_default_id():
    adapter = create_adapter(base_url="http://example.com")
    assert adapter.adapter_id is not None
    assert adapter.adapter_kind == "http"

def test_capabilities():
    adapter = create_adapter(base_url="http://example.com")
    assert "apply" in adapter.capabilities

def test_timeout_error():
    adapter = create_adapter(base_url="http://slow.example.com", timeout_s=0.001)
    with pytest.raises(NexusOperationalError) as exc:
        adapter.call("tool", "method", {})
    assert exc.value.error_code == "TIMEOUT"
```

## Loading Adapters

Host processes load adapters using `nexus_router.plugins.load_adapter()`:

```python
from nexus_router.plugins import load_adapter, AdapterLoadError
from nexus_router.dispatch import AdapterRegistry

try:
    # Load adapter from installed package
    adapter = load_adapter(
        "nexus_router_adapter_http:create_adapter",
        adapter_id="my-http",
        base_url="https://api.example.com",
        timeout_s=30,
    )
except AdapterLoadError as e:
    print(f"Load failed: {e}")
    print(f"Factory ref: {e.factory_ref}")
    print(f"Cause: {e.cause}")
    raise

# Register into explicit registry
registry = AdapterRegistry(default_adapter_id="my-http")
registry.register(adapter)

# Use with router
router = Router(store, adapters=registry)
```

### Loader Safety Net

The `load_adapter()` function enforces these invariants:

1. **Factory ref format**: Must be `module:function` with non-empty parts
2. **Callable check**: Factory must be callable
3. **Protocol validation**: Returned object must have `adapter_id`, `adapter_kind`, `capabilities`, `call()`
4. **Capabilities type**: Must be a set-like collection of strings

All failures are wrapped in `AdapterLoadError` with:
- `factory_ref`: The original factory reference
- `cause`: The underlying exception (if any)
- `details`: Dict with `factory_ref`, `cause` (str), `cause_type`

**`AdapterLoadError` is the only exception callers should expect from `load_adapter()`.**

## Inspecting Adapters

Use `inspect_adapter()` to get human-readable information about an adapter:

```python
from nexus_router.plugins import inspect_adapter

result = inspect_adapter(
    "nexus_router_adapter_http:create_adapter",
    config={"base_url": "https://example.com"},
)

# Check validation status
print(f"OK: {result.ok}")
print(f"Kind: {result.adapter_kind}")
print(f"Capabilities: {result.capabilities}")

# Get config parameters (from manifest)
for param in result.config_params or []:
    print(f"  {param['name']}: {param['type']} ({'required' if param['required'] else 'optional'})")

# Get error codes (from manifest)
print(f"Error codes: {result.error_codes}")

# Render full report
print(result.render())
```

The `inspect_adapter()` function:
- Runs full `validate_adapter()` validation
- Extracts config schema from manifest into `config_params`
- Extracts error codes and supported versions
- Provides `render()` for human-readable output

### Tool API

Use via the public tool API:

```python
from nexus_router.tool import inspect_adapter

response = inspect_adapter({
    "factory_ref": "nexus_router_adapter_http:create_adapter",
    "config": {"base_url": "https://example.com"},
    "render": True,  # Include rendered text
})

print(response["rendered"])
```

## Naming Convention

Adapter packages SHOULD follow the naming pattern:

```
nexus-router-adapter-{kind}
```

Examples:
- `nexus-router-adapter-http`
- `nexus-router-adapter-grpc`
- `nexus-router-adapter-k8s`

The Python module name uses underscores:
- `nexus_router_adapter_http`

## Versioning

Adapter packages SHOULD:
- Follow semantic versioning
- Document which nexus-router versions they support
- Pin minimum nexus-router version in dependencies

```toml
[project]
dependencies = [
    "nexus-router>=0.9.0,<1.0",
]
```

## Recommended pyproject.toml

```toml
[project]
name = "nexus-router-adapter-{kind}"
version = "0.1.0"
dependencies = [
    "nexus-router>=0.9.0,<1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "ruff>=0.1",
    # Add adapter-specific test dependencies here
]

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "W"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

## Continuous Integration

Use the provided CI template to ensure your adapter stays compliant.

### Setup

1. Copy `templates/adapter-ci.yml` to `.github/workflows/adapter-ci.yml`
2. Set `ADAPTER_FACTORY_REF` to your factory reference (e.g., `nexus_router_adapter_http:create_adapter`)
3. Set `ADAPTER_CONFIG` to minimal config needed (no secrets, no network!)

### What the CI Does

| Step | Purpose |
|------|---------|
| Install | Installs adapter with `[dev]` extras + nexus-router |
| Lint | Runs `ruff check .` |
| Typecheck | Runs `mypy` if configured |
| Tests | Runs `pytest` |
| **Validate** | Runs `validate_adapter` as gate |

### Minimal Config

The `ADAPTER_CONFIG` environment variable must work without:
- Network access
- Secrets or API keys
- External services

Example for HTTP adapter:
```yaml
ADAPTER_CONFIG: '{"base_url": "https://example.com"}'
```

This config is only used for validation - your tests can use mocks for actual HTTP calls.

### CI Badge

Add this badge to your README:

```markdown
[![adapter-ci](https://github.com/YOUR-ORG/nexus-router-adapter-{kind}/actions/workflows/adapter-ci.yml/badge.svg)](https://github.com/YOUR-ORG/nexus-router-adapter-{kind}/actions/workflows/adapter-ci.yml)
```

## Reference Implementation

See `nexus-router-adapter-http` for a complete reference implementation:
- https://github.com/mcp-tool-shop/nexus-router-adapter-http

## Checklist for New Adapters

- [ ] Implements `DispatchAdapter` protocol
- [ ] Exposes `create_adapter()` factory function
- [ ] Declares capabilities from standard set
- [ ] Uses `NexusOperationalError` for expected failures
- [ ] Redacts sensitive data in errors/logs
- [ ] No global state or import side effects
- [ ] Includes unit tests
- [ ] Documents configuration options
- [ ] Follows naming convention
- [ ] CI workflow configured with `validate_adapter` gate
