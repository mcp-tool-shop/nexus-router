"""nexus-router.export: Deterministic, portable snapshot of a run."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

BUNDLE_VERSION = "0.3"


def export_run(
    *,
    db_path: str,
    run_id: str,
    include_provenance: bool = True,
) -> Dict[str, Any]:
    """
    Export a run as a deterministic, portable bundle.

    Args:
        db_path: Path to SQLite database file.
        run_id: The run ID to export.
        include_provenance: Whether to include provenance record (default True).

    Returns:
        Dict with ok, artifact (bundle), and optional error.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Get run row
        run_row = conn.execute(
            "SELECT run_id, mode, goal, status, created_at FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()

        if run_row is None:
            return {
                "ok": False,
                "error": {"code": "RUN_NOT_FOUND", "message": f"Run {run_id} not found"},
            }

        # Get all events ordered by seq
        event_rows = conn.execute(
            "SELECT event_id, run_id, seq, type, payload_json, ts "
            "FROM events WHERE run_id = ? ORDER BY seq ASC",
            (run_id,),
        ).fetchall()

        # Build canonical run object
        run_data: Dict[str, Any] = {
            "run_id": run_row["run_id"],
            "mode": run_row["mode"],
            "goal": run_row["goal"],
            "status": run_row["status"],
            "created_at": run_row["created_at"],
        }

        # Build canonical events list
        events_data: List[Dict[str, Any]] = []
        for row in event_rows:
            events_data.append({
                "event_id": row["event_id"],
                "run_id": row["run_id"],
                "seq": row["seq"],
                "type": row["type"],
                "payload": json.loads(row["payload_json"]),
                "ts": row["ts"],
            })

        # Compute deterministic digest over {run, events} only
        # Using canonical JSON with sorted keys for reproducibility
        digest_content = {
            "run": run_data,
            "events": events_data,
        }
        digest_json = json.dumps(digest_content, sort_keys=True, separators=(",", ":"))
        sha256_digest = hashlib.sha256(digest_json.encode("utf-8")).hexdigest()

        # Build bundle
        exported_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        artifact: Dict[str, Any] = {
            "bundle_version": BUNDLE_VERSION,
            "exported_at": exported_at,
            "run": run_data,
            "events": events_data,
            "digests": {
                "sha256": sha256_digest,
            },
        }

        # Optionally include provenance record
        if include_provenance:
            artifact["provenance"] = {
                "export_method": "nexus-router.export",
                "source_db_path": db_path,
                "source_run_id": run_id,
                "export_version": BUNDLE_VERSION,
            }

        return {"ok": True, "artifact": artifact}

    finally:
        conn.close()


def _compute_bundle_digest(bundle: Dict[str, Any]) -> str:
    """Recompute SHA256 digest for a bundle's {run, events}."""
    digest_content = {
        "run": bundle["run"],
        "events": bundle["events"],
    }
    digest_json = json.dumps(digest_content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(digest_json.encode("utf-8")).hexdigest()


def verify_bundle_digest(bundle: Dict[str, Any]) -> Optional[str]:
    """
    Verify a bundle's digest.

    Returns:
        None if valid, error message if invalid.
    """
    if "digests" not in bundle or "sha256" not in bundle["digests"]:
        return "Bundle missing digests.sha256"

    expected = bundle["digests"]["sha256"]
    actual = _compute_bundle_digest(bundle)

    if actual != expected:
        return f"Digest mismatch: expected {expected}, got {actual}"

    return None
