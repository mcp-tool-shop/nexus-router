"""Public tool interfaces for nexus-router."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, Dict, cast

from .event_store import EventStore
from .export import export_run as _export_impl
from .import_ import import_bundle as _import_impl
from .inspect import inspect as _inspect_impl
from .replay import replay as _replay_impl
from .router import Router
from .schema import validate

# Tool IDs
TOOL_ID_RUN = "nexus-router.run"
TOOL_ID_INSPECT = "nexus-router.inspect"
TOOL_ID_REPLAY = "nexus-router.replay"
TOOL_ID_EXPORT = "nexus-router.export"
TOOL_ID_IMPORT = "nexus-router.import"

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


def run(request: Dict[str, Any], *, db_path: str = ":memory:") -> Dict[str, Any]:
    """
    Execute a nexus-router run.

    Args:
        request: Request dict conforming to nexus-router.run.request.v0.1 schema.
        db_path: SQLite database path. Default ":memory:" is ephemeral.
                 Pass a file path like "nexus-router.db" to persist runs.

    Returns:
        Response dict conforming to nexus-router.run.response.v0.1 schema.

    Raises:
        jsonschema.ValidationError: If request doesn't match schema.
    """
    schema = _load_schema("nexus-router.run.request.v0.1.json")
    validate(request, schema)

    store = EventStore(db_path)
    try:
        router = Router(store)
        return router.run(request)
    finally:
        store.close()


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
