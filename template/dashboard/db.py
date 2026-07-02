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


def ensure_schema(conn: sqlite3.Connection) -> None:
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
