"""Tests for nexus-router.export and nexus-router.import tools."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any, Dict, cast

import jsonschema

from nexus_router.tool import export, import_bundle, replay, run


def _load_schema(name: str) -> Dict[str, Any]:
    with resources.files("nexus_router").joinpath(f"schemas/{name}").open(
        "r", encoding="utf-8"
    ) as f:
        return cast(Dict[str, Any], json.load(f))


EXPORT_REQUEST_SCHEMA = _load_schema("nexus-router.export.request.v0.3.json")
EXPORT_RESPONSE_SCHEMA = _load_schema("nexus-router.export.response.v0.3.json")
IMPORT_REQUEST_SCHEMA = _load_schema("nexus-router.import.request.v0.3.json")
IMPORT_RESPONSE_SCHEMA = _load_schema("nexus-router.import.response.v0.3.json")


class TestExportContract:
    """Contract tests: validate export request/response against schemas."""

    def test_minimal_request_valid(self) -> None:
        """Minimal valid request passes schema validation."""
        request = {"db_path": "/path/to/db.sqlite", "run_id": "abc-123"}
        jsonschema.validate(request, EXPORT_REQUEST_SCHEMA)

    def test_full_request_valid(self) -> None:
        """Full request with all fields passes schema validation."""
        request = {
            "db_path": "/path/to/db.sqlite",
            "run_id": "abc-123",
            "include_provenance": False,
            "format": "bundle_v0_3",
        }
        jsonschema.validate(request, EXPORT_REQUEST_SCHEMA)


class TestImportContract:
    """Contract tests: validate import request/response against schemas."""

    def test_minimal_request_valid(self) -> None:
        """Minimal valid request passes schema validation."""
        request = {
            "db_path": "/path/to/db.sqlite",
            "bundle": {
                "bundle_version": "0.3",
                "run": {
                    "run_id": "test-id",
                    "mode": "dry_run",
                    "goal": "test",
                    "status": "COMPLETED",
                    "created_at": "2026-01-01T00:00:00.000Z",
                },
                "events": [],
                "digests": {"sha256": "a" * 64},
            },
        }
        jsonschema.validate(request, IMPORT_REQUEST_SCHEMA)

    def test_full_request_valid(self) -> None:
        """Full request with all fields passes schema validation."""
        request = {
            "db_path": "/path/to/db.sqlite",
            "bundle": {
                "bundle_version": "0.3",
                "exported_at": "2026-01-01T00:00:00.000Z",
                "run": {
                    "run_id": "test-id",
                    "mode": "dry_run",
                    "goal": "test",
                    "status": "COMPLETED",
                    "created_at": "2026-01-01T00:00:00.000Z",
                },
                "events": [],
                "digests": {"sha256": "a" * 64},
            },
            "mode": "new_run_id",
            "new_run_id": "my-custom-id",
            "verify_digest": False,
            "replay_after_import": False,
        }
        jsonschema.validate(request, IMPORT_REQUEST_SCHEMA)


class TestExportGoldenFixtures:
    """Golden fixture tests for export tool."""

    def test_export_happy_path(self, tmp_path: Path) -> None:
        """Export a valid run produces valid bundle."""
        db_path = str(tmp_path / "test.db")

        # Create a valid run
        resp = run(
            {
                "goal": "export test",
                "mode": "dry_run",
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test step",
                        "call": {"tool": "my-tool", "method": "my_method", "args": {}},
                    }
                ],
            },
            db_path=db_path,
        )
        run_id = resp["run"]["run_id"]

        response = export({"db_path": db_path, "run_id": run_id})

        # Validate response schema
        jsonschema.validate(response, EXPORT_RESPONSE_SCHEMA)

        assert response["ok"] is True
        artifact = response["artifact"]
        assert artifact["bundle_version"] == "0.3"
        assert "exported_at" in artifact
        assert artifact["run"]["run_id"] == run_id
        assert artifact["run"]["mode"] == "dry_run"
        assert artifact["run"]["goal"] == "export test"
        assert len(artifact["events"]) > 0
        assert "sha256" in artifact["digests"]
        assert len(artifact["digests"]["sha256"]) == 64
        assert artifact["provenance"]["source_run_id"] == run_id

    def test_export_without_provenance(self, tmp_path: Path) -> None:
        """Export with include_provenance=False omits provenance."""
        db_path = str(tmp_path / "test.db")

        resp = run(
            {"goal": "no prov test", "mode": "dry_run", "plan_override": []},
            db_path=db_path,
        )
        run_id = resp["run"]["run_id"]

        response = export(
            {"db_path": db_path, "run_id": run_id, "include_provenance": False}
        )

        assert response["ok"] is True
        assert "provenance" not in response["artifact"]

    def test_export_run_not_found(self, tmp_path: Path) -> None:
        """Export with invalid run_id returns error."""
        db_path = str(tmp_path / "test.db")

        # Create DB with at least one run
        run({"goal": "init", "mode": "dry_run", "plan_override": []}, db_path=db_path)

        response = export({"db_path": db_path, "run_id": "nonexistent"})

        jsonschema.validate(response, EXPORT_RESPONSE_SCHEMA)

        assert response["ok"] is False
        assert response["error"]["code"] == "RUN_NOT_FOUND"

    def test_export_deterministic(self, tmp_path: Path) -> None:
        """Repeated exports of same run produce same digest."""
        db_path = str(tmp_path / "test.db")

        resp = run(
            {"goal": "determinism test", "mode": "dry_run", "plan_override": []},
            db_path=db_path,
        )
        run_id = resp["run"]["run_id"]

        # Export twice
        response1 = export({"db_path": db_path, "run_id": run_id})
        response2 = export({"db_path": db_path, "run_id": run_id})

        # Digests should be identical (exported_at will differ)
        digest1 = response1["artifact"]["digests"]["sha256"]
        digest2 = response2["artifact"]["digests"]["sha256"]
        assert digest1 == digest2


class TestImportGoldenFixtures:
    """Golden fixture tests for import tool."""

    def test_import_happy_path(self, tmp_path: Path) -> None:
        """Import a valid bundle succeeds."""
        source_db = str(tmp_path / "source.db")
        target_db = str(tmp_path / "target.db")

        # Create a run in source
        resp = run(
            {
                "goal": "import test",
                "mode": "dry_run",
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "test step",
                        "call": {"tool": "my-tool", "method": "my_method", "args": {}},
                    }
                ],
            },
            db_path=source_db,
        )
        original_run_id = resp["run"]["run_id"]

        # Export from source
        export_resp = export({"db_path": source_db, "run_id": original_run_id})
        bundle = export_resp["artifact"]

        # Import to target
        import_resp = import_bundle({"db_path": target_db, "bundle": bundle})

        jsonschema.validate(import_resp, IMPORT_RESPONSE_SCHEMA)

        assert import_resp["status"] == "ok"
        assert import_resp["imported_run_id"] == original_run_id
        assert import_resp["events_inserted"] > 0
        assert import_resp["replay_ok"] is True
        assert import_resp.get("violations", []) == []

    def test_import_reject_on_conflict(self, tmp_path: Path) -> None:
        """Import with existing run_id rejects by default."""
        db_path = str(tmp_path / "test.db")

        # Create initial run
        resp = run(
            {"goal": "conflict test", "mode": "dry_run", "plan_override": []},
            db_path=db_path,
        )
        run_id = resp["run"]["run_id"]

        # Export it
        export_resp = export({"db_path": db_path, "run_id": run_id})
        bundle = export_resp["artifact"]

        # Try to import again (same run_id exists)
        import_resp = import_bundle({"db_path": db_path, "bundle": bundle})

        jsonschema.validate(import_resp, IMPORT_RESPONSE_SCHEMA)

        assert import_resp["status"] == "skipped"
        assert import_resp["conflict"]["reason"] == "run_id_exists"
        assert import_resp["conflict"]["existing_run_id"] == run_id

    def test_import_new_run_id(self, tmp_path: Path) -> None:
        """Import with mode=new_run_id creates new run."""
        db_path = str(tmp_path / "test.db")

        # Create initial run
        resp = run(
            {"goal": "new id test", "mode": "dry_run", "plan_override": []},
            db_path=db_path,
        )
        original_run_id = resp["run"]["run_id"]

        # Export it
        export_resp = export({"db_path": db_path, "run_id": original_run_id})
        bundle = export_resp["artifact"]

        # Import with new_run_id mode
        import_resp = import_bundle(
            {"db_path": db_path, "bundle": bundle, "mode": "new_run_id"}
        )

        assert import_resp["status"] == "ok"
        assert import_resp["imported_run_id"] != original_run_id
        assert import_resp["replay_ok"] is True

    def test_import_custom_new_run_id(self, tmp_path: Path) -> None:
        """Import with mode=new_run_id and custom ID uses that ID."""
        source_db = str(tmp_path / "source.db")
        target_db = str(tmp_path / "target.db")

        resp = run(
            {"goal": "custom id test", "mode": "dry_run", "plan_override": []},
            db_path=source_db,
        )

        export_resp = export({"db_path": source_db, "run_id": resp["run"]["run_id"]})
        bundle = export_resp["artifact"]

        import_resp = import_bundle(
            {
                "db_path": target_db,
                "bundle": bundle,
                "mode": "new_run_id",
                "new_run_id": "my-custom-id-12345",
            }
        )

        assert import_resp["status"] == "ok"
        assert import_resp["imported_run_id"] == "my-custom-id-12345"

    def test_import_overwrite(self, tmp_path: Path) -> None:
        """Import with mode=overwrite replaces existing run."""
        db_path = str(tmp_path / "test.db")

        # Create initial run
        resp = run(
            {"goal": "overwrite test 1", "mode": "dry_run", "plan_override": []},
            db_path=db_path,
        )
        run_id = resp["run"]["run_id"]

        # Export it
        export_resp = export({"db_path": db_path, "run_id": run_id})
        bundle = export_resp["artifact"]

        # Modify bundle goal (but keep same run_id)
        bundle["run"]["goal"] = "overwrite test 2"
        # Recalculate digest
        import hashlib
        digest_content = {"run": bundle["run"], "events": bundle["events"]}
        digest_json = json.dumps(digest_content, sort_keys=True, separators=(",", ":"))
        bundle["digests"]["sha256"] = hashlib.sha256(digest_json.encode()).hexdigest()

        # Import with overwrite
        import_resp = import_bundle(
            {"db_path": db_path, "bundle": bundle, "mode": "overwrite"}
        )

        assert import_resp["status"] == "ok"
        assert import_resp["imported_run_id"] == run_id

    def test_import_digest_verification(self, tmp_path: Path) -> None:
        """Import rejects bundle with invalid digest."""
        source_db = str(tmp_path / "source.db")
        target_db = str(tmp_path / "target.db")

        resp = run(
            {"goal": "digest test", "mode": "dry_run", "plan_override": []},
            db_path=source_db,
        )

        export_resp = export({"db_path": source_db, "run_id": resp["run"]["run_id"]})
        bundle = export_resp["artifact"]

        # Tamper with digest
        bundle["digests"]["sha256"] = "0" * 64

        import_resp = import_bundle({"db_path": target_db, "bundle": bundle})

        assert import_resp["status"] == "error"
        assert import_resp["error"]["code"] == "DIGEST_MISMATCH"

    def test_import_skip_digest_verification(self, tmp_path: Path) -> None:
        """Import with verify_digest=False accepts invalid digest."""
        source_db = str(tmp_path / "source.db")
        target_db = str(tmp_path / "target.db")

        resp = run(
            {"goal": "skip digest test", "mode": "dry_run", "plan_override": []},
            db_path=source_db,
        )

        export_resp = export({"db_path": source_db, "run_id": resp["run"]["run_id"]})
        bundle = export_resp["artifact"]

        # Tamper with digest
        bundle["digests"]["sha256"] = "0" * 64

        import_resp = import_bundle(
            {"db_path": target_db, "bundle": bundle, "verify_digest": False}
        )

        # Should succeed despite invalid digest
        assert import_resp["status"] == "ok"


class TestRoundTrip:
    """End-to-end round trip tests."""

    def test_export_import_roundtrip(self, tmp_path: Path) -> None:
        """Export -> import -> replay produces identical results."""
        source_db = str(tmp_path / "source.db")
        target_db = str(tmp_path / "target.db")

        # Create a run with multiple steps
        resp = run(
            {
                "goal": "roundtrip test",
                "mode": "dry_run",
                "plan_override": [
                    {
                        "step_id": "s1",
                        "intent": "first step",
                        "call": {"tool": "t1", "method": "m1", "args": {"x": 1}},
                    },
                    {
                        "step_id": "s2",
                        "intent": "second step",
                        "call": {"tool": "t2", "method": "m2", "args": {"y": 2}},
                    },
                ],
            },
            db_path=source_db,
        )
        original_run_id = resp["run"]["run_id"]

        # Export
        export_resp = export({"db_path": source_db, "run_id": original_run_id})
        assert export_resp["ok"] is True

        # Import
        import_resp = import_bundle(
            {"db_path": target_db, "bundle": export_resp["artifact"]}
        )
        assert import_resp["status"] == "ok"

        # Replay both and compare
        source_replay = replay({"db_path": source_db, "run_id": original_run_id})
        target_replay = replay(
            {"db_path": target_db, "run_id": import_resp["imported_run_id"]}
        )

        assert source_replay["ok"] is True
        assert target_replay["ok"] is True

        # Run views should be equivalent
        source_view = source_replay["run_view"]
        target_view = target_replay["run_view"]

        assert source_view["mode"] == target_view["mode"]
        assert source_view["goal"] == target_view["goal"]
        assert source_view["outcome"] == target_view["outcome"]
        assert len(source_view["steps"]) == len(target_view["steps"])
        assert set(source_view["tools_used"]) == set(target_view["tools_used"])

    def test_export_import_with_remapped_id(self, tmp_path: Path) -> None:
        """Export -> import with new_run_id works correctly."""
        source_db = str(tmp_path / "source.db")

        resp = run(
            {"goal": "remap test", "mode": "dry_run", "plan_override": []},
            db_path=source_db,
        )
        original_run_id = resp["run"]["run_id"]

        export_resp = export({"db_path": source_db, "run_id": original_run_id})

        # Import to same DB with new ID
        import_resp = import_bundle(
            {
                "db_path": source_db,
                "bundle": export_resp["artifact"],
                "mode": "new_run_id",
                "new_run_id": "remapped-id",
            }
        )

        assert import_resp["status"] == "ok"
        assert import_resp["imported_run_id"] == "remapped-id"

        # Both runs should replay successfully
        original_replay = replay({"db_path": source_db, "run_id": original_run_id})
        remapped_replay = replay({"db_path": source_db, "run_id": "remapped-id"})

        assert original_replay["ok"] is True
        assert remapped_replay["ok"] is True
