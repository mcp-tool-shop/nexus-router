"""nexus-router.import: Safe bundle loading into a database."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any, Dict, Optional

from .export import _compute_bundle_digest
from .replay import replay as _replay_impl


def import_bundle(
    *,
    db_path: str,
    bundle: Dict[str, Any],
    mode: str = "reject_on_conflict",
    new_run_id: Optional[str] = None,
    verify_digest: bool = True,
    replay_after_import: bool = True,
) -> Dict[str, Any]:
    """
    Import a bundle into a database safely.

    Args:
        db_path: Path to SQLite database file.
        bundle: The bundle object to import.
        mode: Conflict resolution mode:
            - "reject_on_conflict": Fail if run_id already exists (default)
            - "new_run_id": Generate or use provided new_run_id
            - "overwrite": Delete existing run and reimport
        new_run_id: Only used if mode is "new_run_id". If not provided, generates UUID.
        verify_digest: Verify bundle digest before import (default True).
        replay_after_import: Run replay after import to verify integrity (default True).

    Returns:
        Dict with status, imported_run_id, events_inserted, and optional violations.
    """
    # Validate bundle structure
    validation_error = _validate_bundle_structure(bundle)
    if validation_error:
        return {
            "status": "error",
            "error": {"code": "INVALID_BUNDLE", "message": validation_error},
        }

    # Verify digest if requested
    if verify_digest:
        digest_error = _verify_digest(bundle)
        if digest_error:
            return {
                "status": "error",
                "error": {"code": "DIGEST_MISMATCH", "message": digest_error},
            }

    run_data = bundle["run"]
    events_data = bundle["events"]
    original_run_id = run_data["run_id"]

    # Determine target run_id
    if mode == "new_run_id":
        target_run_id = new_run_id if new_run_id else str(uuid.uuid4())
    else:
        target_run_id = original_run_id

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Ensure schema exists
        _ensure_schema(conn)

        # Check for existing run
        existing = conn.execute(
            "SELECT run_id FROM runs WHERE run_id = ?",
            (target_run_id,),
        ).fetchone()

        if existing:
            if mode == "reject_on_conflict":
                return {
                    "status": "skipped",
                    "conflict": {
                        "reason": "run_id_exists",
                        "existing_run_id": target_run_id,
                    },
                }
            elif mode == "overwrite":
                # Delete existing run and events
                conn.execute("DELETE FROM events WHERE run_id = ?", (target_run_id,))
                conn.execute("DELETE FROM runs WHERE run_id = ?", (target_run_id,))
                conn.commit()
            # mode == "new_run_id" with collision: generate new ID
            elif mode == "new_run_id":
                target_run_id = str(uuid.uuid4())

        # Insert run
        conn.execute(
            "INSERT INTO runs(run_id, mode, goal, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                target_run_id,
                run_data["mode"],
                run_data["goal"],
                run_data["status"],
                run_data["created_at"],
            ),
        )

        # Insert events with original seq (or remapped run_id)
        events_inserted = 0
        for event in events_data:
            event_run_id = target_run_id  # Always use target run_id
            event_id = event["event_id"]

            # If we're remapping run_id, generate new event_id to avoid collision
            if target_run_id != original_run_id:
                event_id = str(uuid.uuid4())

            payload_json = json.dumps(event["payload"], sort_keys=True, separators=(",", ":"))

            # Remap run_id references in payload if present
            payload = event["payload"]
            if target_run_id != original_run_id:
                payload = _remap_run_id_in_payload(payload, original_run_id, target_run_id)
                payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))

            try:
                conn.execute(
                    "INSERT INTO events(event_id, run_id, seq, type, payload_json, ts) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        event_id,
                        event_run_id,
                        event["seq"],
                        event["type"],
                        payload_json,
                        event["ts"],
                    ),
                )
                events_inserted += 1
            except sqlite3.IntegrityError as e:
                conn.rollback()
                return {
                    "status": "error",
                    "error": {
                        "code": "SEQ_DUPLICATE",
                        "message": f"Duplicate seq {event['seq']}: {e}",
                    },
                }

        conn.commit()

        result: Dict[str, Any] = {
            "status": "ok",
            "imported_run_id": target_run_id,
            "events_inserted": events_inserted,
        }

        # Optionally run replay to verify integrity
        if replay_after_import:
            replay_result = _replay_impl(
                db_path=db_path,
                run_id=target_run_id,
                strict=True,
            )
            result["replay_ok"] = replay_result["ok"]
            if replay_result.get("violations"):
                result["violations"] = replay_result["violations"]

        return result

    finally:
        conn.close()


def _validate_bundle_structure(bundle: Dict[str, Any]) -> Optional[str]:
    """Validate required bundle fields."""
    if "bundle_version" not in bundle:
        return "Missing bundle_version"
    if "run" not in bundle:
        return "Missing run"
    if "events" not in bundle:
        return "Missing events"

    run = bundle["run"]
    required_run_fields = ["run_id", "mode", "goal", "status", "created_at"]
    for field in required_run_fields:
        if field not in run:
            return f"Missing run.{field}"

    for i, event in enumerate(bundle["events"]):
        required_event_fields = ["event_id", "run_id", "seq", "type", "payload", "ts"]
        for field in required_event_fields:
            if field not in event:
                return f"Missing events[{i}].{field}"

    return None


def _verify_digest(bundle: Dict[str, Any]) -> Optional[str]:
    """Verify bundle digest."""
    if "digests" not in bundle or "sha256" not in bundle["digests"]:
        return "Bundle missing digests.sha256"

    expected = bundle["digests"]["sha256"]
    actual = _compute_bundle_digest(bundle)

    if actual != expected:
        return f"Digest mismatch: expected {expected}, got {actual}"

    return None


def _remap_run_id_in_payload(
    payload: Dict[str, Any],
    old_run_id: str,
    new_run_id: str,
) -> Dict[str, Any]:
    """Recursively remap run_id references in payload."""
    if not isinstance(payload, dict):
        return payload

    result: Dict[str, Any] = {}
    for key, value in payload.items():
        if key == "run_id" and value == old_run_id:
            result[key] = new_run_id
        elif isinstance(value, dict):
            result[key] = _remap_run_id_in_payload(value, old_run_id, new_run_id)
        elif isinstance(value, list):
            remapped: list[Any] = [
                _remap_run_id_in_payload(item, old_run_id, new_run_id)
                if isinstance(item, dict) else item
                for item in value
            ]
            result[key] = remapped
        else:
            result[key] = value

    return result


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Ensure database schema exists."""
    conn.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS runs (
          run_id TEXT PRIMARY KEY,
          mode TEXT NOT NULL,
          goal TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );

        CREATE TABLE IF NOT EXISTS events (
          event_id TEXT PRIMARY KEY,
          run_id TEXT NOT NULL,
          seq INTEGER NOT NULL,
          type TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
          FOREIGN KEY(run_id) REFERENCES runs(run_id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_events_run_seq ON events(run_id, seq);
        CREATE INDEX IF NOT EXISTS ix_events_run ON events(run_id);
    """)
