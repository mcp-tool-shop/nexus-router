"""Public tool interfaces for nexus-router."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, Dict, List, Optional, Union, cast

from .dispatch import AdapterRegistry, DispatchAdapter
from .event_store import EventStore
from .export import export_run as _export_impl
from .import_ import import_bundle as _import_impl
from .inspect import inspect as _inspect_impl
from .docs import generate_adapter_docs as _generate_docs_impl
from .plugins import inspect_adapter as _inspect_adapter_impl
from .plugins import validate_adapter as _validate_adapter_impl
from .replay import replay as _replay_impl
from .router import Router
from .schema import validate

# Tool IDs
TOOL_ID_RUN = "nexus-router.run"
TOOL_ID_INSPECT = "nexus-router.inspect"
TOOL_ID_REPLAY = "nexus-router.replay"
TOOL_ID_EXPORT = "nexus-router.export"
TOOL_ID_IMPORT = "nexus-router.import"
TOOL_ID_ADAPTERS = "nexus-router.adapters"
TOOL_ID_VALIDATE_ADAPTER = "nexus-router.validate_adapter"
TOOL_ID_INSPECT_ADAPTER = "nexus-router.inspect_adapter"
TOOL_ID_GENERATE_DOCS = "nexus-router.generate_adapter_docs"

# Legacy alias
TOOL_ID = TOOL_ID_RUN

# Schema cache
_SCHEMAS: Dict[str, Dict[str, Any]] = {}


def _load_schema(name: str) -> Dict[str, Any]:
    """Load a schema from package data with caching."""
    if name not in _SCHEMAS:
        with resources.files("nexus_router").joinpath(f"schemas/{name}").open(
            "r", encoding="utf-8"
        ) as f:
            _SCHEMAS[name] = cast(Dict[str, Any], json.load(f))
    return _SCHEMAS[name]


def run(
    request: Dict[str, Any],
    *,
    db_path: str = ":memory:",
    adapter: Optional[DispatchAdapter] = None,
    adapters: Optional[AdapterRegistry] = None,
) -> Dict[str, Any]:
    """
    Execute a nexus-router run.

    Args:
        request: Request dict conforming to nexus-router.run.request.v0.7 schema.
        db_path: SQLite database path. Default ":memory:" is ephemeral.
                 Pass a file path like "nexus-router.db" to persist runs.
        adapter: Optional dispatch adapter for tool calls. If None, uses NullAdapter.
                 In dry_run mode, adapter is never called (simulated output).
                 In apply mode, adapter.call() is invoked for each step.
                 DEPRECATED: Use adapters registry instead.
        adapters: Adapter registry for tool dispatch.
                  Supports declarative adapter selection via request.dispatch.adapter_id.

    Returns:
        Response dict conforming to nexus-router.run.response.v0.7 schema.

    Raises:
        jsonschema.ValidationError: If request doesn't match schema.
        ValueError: If both adapter and adapters are provided.
        NexusBugError: Re-raised after recording if adapter raises bug error.
    """
    schema = _load_schema("nexus-router.run.request.v0.7.json")
    validate(request, schema)

    store = EventStore(db_path)
    try:
        router = Router(store, adapter=adapter, adapters=adapters)
        return router.run(request)
    finally:
        store.close()


def list_adapters(
    adapters: AdapterRegistry,
    *,
    capability: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List registered adapters (nexus-router.adapters tool).

    Args:
        adapters: Adapter registry to query.
        capability: Optional capability filter.

    Returns:
        Response with adapter list.
    """
    if capability:
        adapter_ids = adapters.find_by_capability(capability)
        adapter_list = [
            {
                "adapter_id": aid,
                "adapter_kind": adapters.get(aid).adapter_kind,
                "capabilities": sorted(adapters.get(aid).capabilities),
            }
            for aid in adapter_ids
        ]
    else:
        adapter_list = adapters.list_adapters()

    return {
        "adapters": adapter_list,
        "default_adapter_id": adapters.default_adapter_id,
        "total": len(adapter_list),
    }


def inspect(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inspect the event store and return run summaries.

    Args:
        request: Request dict conforming to nexus-router.inspect.request.v0.2 schema.
                 Required: db_path
                 Optional: run_id, status, limit, offset, since

    Returns:
        Response dict conforming to nexus-router.inspect.response.v0.2 schema.

    Raises:
        jsonschema.ValidationError: If request doesn't match schema.
    """
    schema = _load_schema("nexus-router.inspect.request.v0.2.json")
    validate(request, schema)

    return _inspect_impl(
        db_path=request["db_path"],
        run_id=request.get("run_id"),
        status=request.get("status"),
        limit=request.get("limit", 50),
        offset=request.get("offset", 0),
        since=request.get("since"),
    )


def replay(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Replay a run from events and check invariants.

    Args:
        request: Request dict conforming to nexus-router.replay.request.v0.2 schema.
                 Required: db_path, run_id
                 Optional: strict (default True)

    Returns:
        Response dict conforming to nexus-router.replay.response.v0.2 schema.

    Raises:
        jsonschema.ValidationError: If request doesn't match schema.
    """
    schema = _load_schema("nexus-router.replay.request.v0.2.json")
    validate(request, schema)

    return _replay_impl(
        db_path=request["db_path"],
        run_id=request["run_id"],
        strict=request.get("strict", True),
    )


def export(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Export a run as a deterministic, portable bundle.

    Args:
        request: Request dict conforming to nexus-router.export.request.v0.3 schema.
                 Required: db_path, run_id
                 Optional: include_provenance (default True), format (default bundle_v0_3)

    Returns:
        Response dict conforming to nexus-router.export.response.v0.3 schema.

    Raises:
        jsonschema.ValidationError: If request doesn't match schema.
    """
    schema = _load_schema("nexus-router.export.request.v0.3.json")
    validate(request, schema)

    return _export_impl(
        db_path=request["db_path"],
        run_id=request["run_id"],
        include_provenance=request.get("include_provenance", True),
    )


def import_bundle(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Import a bundle into a database safely.

    Args:
        request: Request dict conforming to nexus-router.import.request.v0.3 schema.
                 Required: db_path, bundle
                 Optional: mode (default reject_on_conflict), new_run_id,
                          verify_digest (default True), replay_after_import (default True)

    Returns:
        Response dict conforming to nexus-router.import.response.v0.3 schema.

    Raises:
        jsonschema.ValidationError: If request doesn't match schema.
    """
    schema = _load_schema("nexus-router.import.request.v0.3.json")
    validate(request, schema)

    return _import_impl(
        db_path=request["db_path"],
        bundle=request["bundle"],
        mode=request.get("mode", "reject_on_conflict"),
        new_run_id=request.get("new_run_id"),
        verify_digest=request.get("verify_digest", True),
        replay_after_import=request.get("replay_after_import", True),
    )


def validate_adapter(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate an adapter package without dispatch (adapter lint tool).

    This is a read-only tool that checks adapter compliance with ADAPTER_SPEC.md.
    It loads the adapter but does not execute any calls.

    Args:
        request: Request dict with:
            factory_ref (required): Module and function reference ("module:function")
            config (optional): Configuration to pass to factory
            strict (optional): If True, unknown capabilities cause failure. Default True.

    Returns:
        Response dict with:
            ok: boolean - True if all checks pass
            metadata: adapter_id, adapter_kind, capabilities (if loaded successfully)
            checks: array of {id, status, message}
            error: string (if load failed)

    Example:
        >>> validate_adapter({
        ...     "factory_ref": "nexus_router_adapter_http:create_adapter",
        ...     "config": {"base_url": "https://example.com"},
        ... })
        {'ok': True, 'metadata': {...}, 'checks': [...]}

    Checks performed:
        LOAD_OK: load_adapter() succeeds
        PROTOCOL_FIELDS: adapter_id, adapter_kind, capabilities, call exist
        ADAPTER_ID_FORMAT: adapter_id is non-empty string
        ADAPTER_KIND_FORMAT: adapter_kind is non-empty string
        CAPABILITIES_TYPE: capabilities is a set-like of strings
        CAPABILITIES_VALID: only standard capabilities declared (strict mode)
    """
    factory_ref = request["factory_ref"]
    config = request.get("config", {})
    strict = request.get("strict", True)

    result = _validate_adapter_impl(factory_ref, config, strict=strict)
    return result.to_dict()


def inspect_adapter(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inspect an adapter package with human-friendly output.

    This is a read-only tool that validates an adapter and extracts
    metadata, config schema, and error codes for display.

    Args:
        request: Request dict with:
            factory_ref (required): Module and function reference ("module:function")
            config (optional): Configuration to pass to factory
            strict (optional): If True, unknown capabilities cause failure. Default True.
            render (optional): If True, include rendered text in response. Default False.

    Returns:
        Response dict with:
            ok: boolean - True if validation passes
            adapter_id: string - adapter identifier
            adapter_kind: string - adapter type
            capabilities: list[string] - declared capabilities
            supported_router_versions: string - PEP 440 version specifier (if manifest)
            config_params: list of config parameter info (if manifest)
            error_codes: list[string] - error codes adapter may raise (if manifest)
            manifest: dict - raw manifest (if present)
            validation: dict - validation result
            rendered: string - human-readable report (if render=True)

    Example:
        >>> inspect_adapter({
        ...     "factory_ref": "nexus_router_adapter_http:create_adapter",
        ...     "config": {"base_url": "https://example.com"},
        ...     "render": True,
        ... })
        {'ok': True, 'adapter_id': 'http:example.com', 'rendered': '...', ...}
    """
    factory_ref = request["factory_ref"]
    config = request.get("config", {})
    strict = request.get("strict", True)
    render = request.get("render", False)

    result = _inspect_adapter_impl(factory_ref, config, strict=strict)
    response = result.to_dict()

    if render:
        response["rendered"] = result.render()

    return response


def generate_adapter_docs(request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generate markdown documentation from adapter manifests.

    This is a read-only tool that inspects known adapters and generates
    consistent documentation from their manifests.

    Args:
        request: Optional request dict with:
            title (optional): Title for the adapters section. Default "Official Adapters".
            include_header (optional): Include file header. Default True.
            include_footer (optional): Include footer. Default True.

    Returns:
        Response dict with:
            markdown: string - generated markdown content
            adapters_ok: int - number of successfully documented adapters
            adapters_failed: int - number of failed adapters
            errors: list[string] - error messages for failed adapters

    Example:
        >>> generate_adapter_docs()
        {'markdown': '...', 'adapters_ok': 1, 'adapters_failed': 0, 'errors': []}
    """
    request = request or {}
    title = request.get("title", "Official Adapters")
    include_header = request.get("include_header", True)
    include_footer = request.get("include_footer", True)

    result = _generate_docs_impl(
        title=title,
        include_header=include_header,
        include_footer=include_footer,
    )

    return result.to_dict()
