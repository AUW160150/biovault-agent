"""
BioVault Agent — SQLite Database Layer
---------------------------------------
Single source of truth for persistent state across container restarts.

Tables:
  documents       — intake queue, one row per uploaded document
  pipeline_results — per-stage outputs from the 4-stage pipeline
  safety_flags    — critical flags raised during processing
  agent_heartbeat — single-row liveness record updated every agent loop
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.getenv("DB_PATH", "/data/biovault.db")

_lock = threading.Lock()


def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def get_conn():
    """Thread-safe SQLite connection context manager."""
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist. Safe to call multiple times."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id                  TEXT PRIMARY KEY,
                filename            TEXT NOT NULL,
                file_path           TEXT NOT NULL,
                status              TEXT NOT NULL DEFAULT 'pending',
                uploaded_at         TEXT NOT NULL,
                processed_at        TEXT,
                critical_flags_count INTEGER NOT NULL DEFAULT 0,
                error_message       TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_documents_status
                ON documents(status);

            CREATE TABLE IF NOT EXISTS pipeline_results (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL REFERENCES documents(id),
                stage       TEXT NOT NULL,
                output_json TEXT NOT NULL,
                confidence  REAL,
                timestamp   TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_pipeline_results_doc
                ON pipeline_results(document_id);

            CREATE TABLE IF NOT EXISTS safety_flags (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL REFERENCES documents(id),
                flag_type   TEXT NOT NULL,
                severity    TEXT NOT NULL,
                details     TEXT NOT NULL,
                resolved    INTEGER NOT NULL DEFAULT 0,
                timestamp   TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_safety_flags_doc
                ON safety_flags(document_id);

            CREATE INDEX IF NOT EXISTS idx_safety_flags_resolved
                ON safety_flags(resolved);

            CREATE TABLE IF NOT EXISTS agent_heartbeat (
                id                          INTEGER PRIMARY KEY CHECK (id = 1),
                last_seen                   TEXT NOT NULL,
                documents_processed_total   INTEGER NOT NULL DEFAULT 0,
                flags_raised_total          INTEGER NOT NULL DEFAULT 0,
                started_at                  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event       TEXT NOT NULL,
                message     TEXT NOT NULL,
                document_id TEXT,
                stage       TEXT,
                level       TEXT NOT NULL DEFAULT 'info',
                timestamp   TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_agent_log_ts
                ON agent_log(timestamp DESC);
        """)

        # Seed the single heartbeat row if not present
        conn.execute("""
            INSERT OR IGNORE INTO agent_heartbeat (id, last_seen, started_at)
            VALUES (1, ?, ?)
        """, (_now(), _now()))


# ─── Document helpers ──────────────────────────────────────────────────────────

def insert_document(doc_id: str, filename: str, file_path: str) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO documents (id, filename, file_path, status, uploaded_at)
            VALUES (?, ?, ?, 'pending', ?)
        """, (doc_id, filename, file_path, _now()))


def get_next_pending() -> Optional[sqlite3.Row]:
    """Return the oldest pending document, or None."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM documents
            WHERE status = 'pending'
            ORDER BY uploaded_at ASC
            LIMIT 1
        """).fetchone()


def set_document_status(doc_id: str, status: str, error: str = None) -> None:
    with get_conn() as conn:
        if status == "complete":
            conn.execute("""
                UPDATE documents
                SET status = ?, processed_at = ?
                WHERE id = ?
            """, (status, _now(), doc_id))
        elif status == "failed":
            conn.execute("""
                UPDATE documents
                SET status = ?, processed_at = ?, error_message = ?
                WHERE id = ?
            """, (status, _now(), error, doc_id))
        else:
            conn.execute(
                "UPDATE documents SET status = ? WHERE id = ?",
                (status, doc_id)
            )


def increment_critical_flags(doc_id: str, count: int = 1) -> None:
    with get_conn() as conn:
        conn.execute("""
            UPDATE documents
            SET critical_flags_count = critical_flags_count + ?
            WHERE id = ?
        """, (count, doc_id))


def get_recent_documents(limit: int = 20) -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, filename, status, uploaded_at, processed_at,
                   critical_flags_count, error_message
            FROM documents
            ORDER BY uploaded_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def recover_stalled_documents() -> int:
    """Reset any 'processing' docs back to 'pending' on startup (fault recovery)."""
    with get_conn() as conn:
        cursor = conn.execute("""
            UPDATE documents SET status = 'pending'
            WHERE status = 'processing'
        """)
        return cursor.rowcount


# ─── Pipeline result helpers ───────────────────────────────────────────────────

def insert_pipeline_result(
    document_id: str,
    stage: str,
    output: dict,
    confidence: float = None,
) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO pipeline_results (document_id, stage, output_json, confidence, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (document_id, stage, json.dumps(output), confidence, _now()))


# ─── Safety flag helpers ───────────────────────────────────────────────────────

def insert_safety_flag(
    document_id: str,
    flag_type: str,
    severity: str,
    details: str,
) -> int:
    with get_conn() as conn:
        cursor = conn.execute("""
            INSERT INTO safety_flags (document_id, flag_type, severity, details, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (document_id, flag_type, severity, details, _now()))
        return cursor.lastrowid


def resolve_safety_flag(flag_id: int) -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "UPDATE safety_flags SET resolved = 1 WHERE id = ?",
            (flag_id,)
        )
        return cursor.rowcount > 0


def get_unresolved_flags() -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT sf.*, d.filename
            FROM safety_flags sf
            JOIN documents d ON d.id = sf.document_id
            WHERE sf.resolved = 0
            ORDER BY sf.timestamp DESC
        """).fetchall()
        return [dict(r) for r in rows]


def get_all_flags(limit: int = 50) -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT sf.*, d.filename
            FROM safety_flags sf
            JOIN documents d ON d.id = sf.document_id
            ORDER BY sf.timestamp DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


# ─── Heartbeat helpers ─────────────────────────────────────────────────────────

def update_heartbeat(docs_delta: int = 0, flags_delta: int = 0) -> None:
    with get_conn() as conn:
        conn.execute("""
            UPDATE agent_heartbeat
            SET last_seen                 = ?,
                documents_processed_total = documents_processed_total + ?,
                flags_raised_total        = flags_raised_total + ?
            WHERE id = 1
        """, (_now(), docs_delta, flags_delta))


def get_heartbeat() -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM agent_heartbeat WHERE id = 1").fetchone()
        return dict(row) if row else None


def write_log(
    event: str,
    message: str,
    document_id: str = None,
    stage: str = None,
    level: str = "info",
) -> None:
    """Write a timestamped agent activity entry. Keeps last 500 rows."""
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO agent_log (event, message, document_id, stage, level, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (event, message, document_id, stage, level, _now()))
        conn.execute("""
            DELETE FROM agent_log WHERE id NOT IN (
                SELECT id FROM agent_log ORDER BY id DESC LIMIT 500
            )
        """)


def get_recent_log(limit: int = 60) -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, event, message, document_id, stage, level, timestamp
            FROM agent_log ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status = 'pending'"
        ).fetchone()[0]
        processing = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status = 'processing'"
        ).fetchone()[0]
        complete = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status = 'complete'"
        ).fetchone()[0]
        failed = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status = 'failed'"
        ).fetchone()[0]
        unresolved_flags = conn.execute(
            "SELECT COUNT(*) FROM safety_flags WHERE resolved = 0"
        ).fetchone()[0]
        return {
            "total": total,
            "pending": pending,
            "processing": processing,
            "complete": complete,
            "failed": failed,
            "unresolved_flags": unresolved_flags,
        }


# ─── Utilities ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
