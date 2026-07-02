#!/usr/bin/env python3
"""Unit tests for dashboard/db.py (stdlib unittest)."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

MOD = Path(__file__).resolve().parent.parent / "db.py"
spec = importlib.util.spec_from_file_location("dashboard_db", MOD)
db = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db)


def tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


class DbTests(unittest.TestCase):
    def test_first_run_creates_and_seeds(self):
        with tempfile.TemporaryDirectory() as d:
            conn = db.connect(Path(d) / "u.db")
            self.assertTrue({"sessions", "commits"} <= tables(conn))
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0], 0)
            conn.close()

    def test_reconnect_does_not_duplicate_seeds(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "u.db"
            c1 = db.connect(p); n1 = c1.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]; c1.close()
            c2 = db.connect(p); n2 = c2.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]; c2.close()
            self.assertEqual(n1, n2)

    def test_migrates_preexisting_sessions_only_db(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "u.db"
            raw = sqlite3.connect(p)
            raw.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, seat TEXT NOT NULL)")
            raw.execute("INSERT INTO sessions (ts, seat) VALUES ('2026-01-01T00:00:00','Developer')")
            raw.commit(); raw.close()
            conn = db.connect(p)  # not first run -> ensure_schema adds commits, no seed
            self.assertIn("commits", tables(conn))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1)
            conn.close()


if __name__ == "__main__":
    unittest.main()
