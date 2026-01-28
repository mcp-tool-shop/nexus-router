# Nexus-Router Adapter Index

Known adapter packages for nexus-router.

## Official Adapters

| Package | Kind | Capabilities | Description |
|---------|------|--------------|-------------|
| [nexus-router-adapter-http](https://github.com/mcp-tool-shop/nexus-router-adapter-http) | `http` | `apply`, `timeout`, `external` | HTTP POST dispatch to REST endpoints |

## Built-in Adapters

These are included in nexus-router core:

| Class | Kind | Capabilities | Use Case |
|-------|------|--------------|----------|
| `NullAdapter` | `null` | `dry_run` | Default adapter; returns empty output |
| `FakeAdapter` | `fake` | `dry_run`, `apply` | Testing with configurable responses |
| `SubprocessAdapter` | `subprocess` | `apply`, `timeout`, `external` | Execute shell commands |

## Community Adapters

*None yet. Submit a PR to add your adapter!*

## Contributing an Adapter

1. Follow the [ADAPTER_SPEC.md](./ADAPTER_SPEC.md) contract
2. Use the naming convention: `nexus-router-adapter-{kind}`
3. Include tests verifying protocol compliance
4. Submit a PR to add your adapter to this index

### Required Information

When adding an adapter to this index, include:

- **Package name**: PyPI package name
- **Repository link**: GitHub/GitLab URL
- **Kind**: The `adapter_kind` value
- **Capabilities**: List of declared capabilities
- **Brief description**: One-line summary

### Index Entry Template

```markdown
| [nexus-router-adapter-{kind}](https://github.com/your-org/nexus-router-adapter-{kind}) | `{kind}` | `cap1`, `cap2` | Brief description |
```

### Badge Line (README.md)

Include these badges in your adapter's README:

```markdown
[![adapter-ci](https://github.com/YOUR-ORG/nexus-router-adapter-{kind}/actions/workflows/adapter-ci.yml/badge.svg)](https://github.com/YOUR-ORG/nexus-router-adapter-{kind}/actions/workflows/adapter-ci.yml)
![nexus-router](https://img.shields.io/badge/nexus--router-v0.9+-blue)
![capabilities](https://img.shields.io/badge/capabilities-apply%20%7C%20timeout-green)
![platform](https://img.shields.io/badge/platform-windows%20%7C%20linux%20%7C%20macos-lightgrey)
```

**Recommended badges:**

| Badge | Purpose |
|-------|---------|
| `adapter-ci` | CI status (from workflow) |
| `nexus-router` | Supported nexus-router versions |
| `capabilities` | Declared capabilities |
| `platform` | Tested platforms |

### CI Workflow

Copy the CI template from nexus-router to ensure your adapter stays compliant:

```bash
# From your adapter repo root
curl -o .github/workflows/adapter-ci.yml \
  https://raw.githubusercontent.com/mcp-tool-shop/nexus-router/main/templates/adapter-ci.yml
```

Then update `ADAPTER_FACTORY_REF` and `ADAPTER_CONFIG` in the workflow.

See [ADAPTER_SPEC.md](./ADAPTER_SPEC.md#continuous-integration) for full CI documentation.

## Validating Adapters

Use `validate_adapter` to lint your adapter before publishing:

```python
from nexus_router.tool import validate_adapter

result = validate_adapter({
    "factory_ref": "your_adapter_pkg:create_adapter",
    "config": {"base_url": "https://example.com"},
})

if result["ok"]:
    print("Adapter passed all checks!")
else:
    for check in result["checks"]:
        if check["status"] == "fail":
            print(f"FAIL: {check['id']}: {check['message']}")
```

Checks performed:
- `LOAD_OK` - Factory loads without errors
- `PROTOCOL_FIELDS` - Required fields exist (adapter_id, adapter_kind, capabilities, call)
- `ADAPTER_ID_FORMAT` - adapter_id is non-empty string
- `ADAPTER_KIND_FORMAT` - adapter_kind is non-empty string
- `CAPABILITIES_TYPE` - capabilities is iterable of strings
- `CAPABILITIES_VALID` - Only standard capabilities declared (strict mode)
