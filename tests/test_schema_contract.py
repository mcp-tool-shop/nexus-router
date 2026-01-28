"""Contract tests: validate requests and responses against JSON schemas."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, Dict, cast

import jsonschema

from nexus_router.tool import run


def _load_schema(name: str) -> Dict[str, Any]:
    with resources.files("nexus_router").joinpath(f"schemas/{name}").open(
        "r", encoding="utf-8"
    ) as f:
        return cast(Dict[str, Any], json.load(f))


REQUEST_SCHEMA = _load_schema("nexus-router.run.request.v0.1.json")
RESPONSE_SCHEMA = _load_schema("nexus-router.run.response.v0.1.json")


def test_minimal_request_valid():
    """Minimal valid request passes schema validation."""
    request = {"goal": "test"}
    jsonschema.validate(request, REQUEST_SCHEMA)


def test_full_request_valid():
    """Full request with all optional fields passes schema validation."""
    request = {
        "goal": "comprehensive test",
        "mode": "dry_run",
        "context": {
            "artifacts": [
                {
                    "artifact_id": "file1",
                    "media_type": "text/plain",
                    "locator": "/path/to/file",
                    "digest": {"alg": "sha256", "value": "abc123"},
                }
            ]
        },
        "policy": {"allow_apply": True, "max_steps": 10},
        "plan_override": [
            {
                "step_id": "s1",
                "intent": "do something",
                "call": {"tool": "my-tool", "method": "my_method", "args": {"x": 1}},
                "expected_output_pointer": "/results/0",
            }
        ],
    }
    jsonschema.validate(request, REQUEST_SCHEMA)


def test_response_matches_schema():
    """Actual run response conforms to response schema."""
    request = {
        "goal": "schema contract test",
        "mode": "dry_run",
        "plan_override": [
            {
                "step_id": "s1",
                "intent": "test step",
                "call": {"tool": "t", "method": "m", "args": {}},
            }
        ],
    }

    response = run(request)

    # This will raise if response doesn't match schema
    jsonschema.validate(response, RESPONSE_SCHEMA)


def test_empty_plan_response_matches_schema():
    """Empty plan response conforms to response schema."""
    response = run({"goal": "empty plan test"})
    jsonschema.validate(response, RESPONSE_SCHEMA)


def test_failed_run_response_matches_schema():
    """Failed run (policy denied) response conforms to response schema."""
    request = {
        "goal": "policy test",
        "mode": "apply",
        "policy": {"allow_apply": False},
        "plan_override": [
            {"step_id": "s1", "intent": "x", "call": {"tool": "t", "method": "m", "args": {}}}
        ],
    }

    response = run(request)
    jsonschema.validate(response, RESPONSE_SCHEMA)
