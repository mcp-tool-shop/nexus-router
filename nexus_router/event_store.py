from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List


SCHEMA_SQL = """
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
"""


@dataclass(frozen=True)
class EventRow:
    event_id: str
    run_id: str
    seq: int
    type: str
    payload: Dict[str, Any]
    ts: str


class EventStore:
    """
    SQLite-backed event store with monotonic sequencing.

    Note: v0.1.1 is single-writer per run. Concurrent writers to the same
    run_id are unsupported and may cause IntegrityError.
    """

    def __init__(self, db_path: str) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(SCHEMA_SQL)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def create_run(self, *, mode: str, goal: str) -> str:
        run_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO runs(run_id, mode, goal, status) VALUES (?, ?, ?, ?)",
            (run_id, mode, goal, "RUNNING"),
        )
        self.conn.commit()
        return run_id

    def append(self, run_id: str, event_type: str, payload: Dict[str, Any]) -> EventRow:
        with self.conn:
            (seq,) = self.conn.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 FROM events WHERE run_id=?",
                (run_id,),
            ).fetchone()

            event_id = str(uuid.uuid4())
            payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            self.conn.execute(
                "INSERT INTO events(event_id, run_id, seq, type, payload_json) VALUES (?, ?, ?, ?, ?)",
                (event_id, run_id, seq, event_type, payload_json),
            )
            (ts,) = self.conn.execute(
                "SELECT ts FROM events WHERE event_id=?",
                (event_id,),
            ).fetchone()

        return EventRow(
            event_id=event_id,
            run_id=run_id,
            seq=seq,
            type=event_type,
            payload=payload,
            ts=ts,
        )

    def read_events(self, run_id: str) -> List[EventRow]:
        rows = self.conn.execute(
            "SELECT event_id, run_id, seq, type, payload_json, ts FROM events WHERE run_id=? ORDER BY seq ASC",
            (run_id,),
        ).fetchall()
        return [
            EventRow(event_id=eid, run_id=rid, seq=seq, type=etype, payload=json.loads(pj), ts=ts)
            for (eid, rid, seq, etype, pj, ts) in rows
        ]

    def set_run_status(self, run_id: str, status: str) -> None:
        self.conn.execute("UPDATE runs SET status=? WHERE run_id=?", (status, run_id))
        self.conn.commit()
