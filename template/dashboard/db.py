#!/usr/bin/env python3
"""Shared SQLite access for the dashboard (app + collector).

connect() opens the DB, ensures the schema (idempotent DDL from schema.sql),
and seeds synthetic rows from seed.sql only when the DB file was just created.
ensure_schema() is safe to call on a pre-existing DB — it adds any missing
tables (e.g. the Phase 3 `commits` table) without touching existing data.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "utilization.db"
SCHEMA = HERE / "schema.sql"
SEED = HERE / "seed.sql"


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict) -> None:
    """Add any missing columns to a pre-existing table (SQLite has no
    ALTER TABLE IF NOT EXISTS; new columns also live in schema.sql for
    fresh DBs)."""
    # Check if table exists first; PRAGMA table_info returns empty for non-existent tables
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None

    if not table_exists:
        return  # Fresh DB, skip migration; schema.sql will create the table with all columns

    have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, decl in columns.items():
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def ensure_schema(conn: sqlite3.Connection) -> None:
    _ensure_columns(conn, "sessions", {
        "session_id": "TEXT",
        "model": "TEXT",
        "cache_read_tokens": "INTEGER NOT NULL DEFAULT 0",
        "user": "TEXT",
    })
    if SCHEMA.exists():
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()


def connect(db_path=DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    first_run = not db_path.exists()
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    if first_run and SEED.exists():
        conn.executescript(SEED.read_text(encoding="utf-8"))
        conn.commit()
    return conn
