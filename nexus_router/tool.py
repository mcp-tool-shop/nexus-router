from __future__ import annotations

import json
from importlib import resources
from typing import Any, Dict

from .event_store import EventStore
from .router import Router
from .schema import validate

TOOL_ID = "nexus-router.run"

_REQUEST_SCHEMA: Dict[str, Any] | None = None


def _load_request_schema() -> Dict[str, Any]:
    with resources.files("nexus_router").joinpath(
        "schemas/nexus-router.run.request.v0.1.json"
    ).open("r", encoding="utf-8") as f:
        return json.load(f)


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
    global _REQUEST_SCHEMA
    if _REQUEST_SCHEMA is None:
        _REQUEST_SCHEMA = _load_request_schema()

    validate(request, _REQUEST_SCHEMA)

    store = EventStore(db_path)
    try:
        router = Router(store)
        return router.run(request)
    finally:
        store.close()
