#!/usr/bin/env python3
"""Schema/migration tests for the spend + tickets + roi_view additions."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import db as dbmod  # noqa: E402


class TestSchema(unittest.TestCase):
    def _fresh(self):
        self.tmp = tempfile.TemporaryDirectory()
        return dbmod.connect(Path(self.tmp.name) / "u.db")

    def _cols(self, conn, table):
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}

    def test_new_tables_and_columns(self):
        conn = self._fresh()
        self.assertIn("session_id", self._cols(conn, "sessions"))
        self.assertIn("model", self._cols(conn, "sessions"))
        self.assertIn("cache_read_tokens", self._cols(conn, "sessions"))
        self.assertEqual(
            self._cols(conn, "spend"),
            {"id", "source", "period_start", "period_end", "seat",
             "cost_eur", "granularity", "notes"},
        )
        self.assertEqual(
            self._cols(conn, "tickets"),
            {"ticket", "estimate_human_days", "actual_human_days",
             "day_rate_eur", "evidence_tier", "status", "closed_at"},
        )

    def test_migrates_old_sessions_table(self):
        # Simulate a pre-existing DB created before this change.
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "old.db"
        raw = sqlite3.connect(path)
        raw.execute("""CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
            seat TEXT NOT NULL, tool TEXT NOT NULL DEFAULT 'claude',
            task TEXT, ticket TEXT, tokens_in INTEGER NOT NULL DEFAULT 0,
            tokens_out INTEGER NOT NULL DEFAULT 0, cost_usd REAL NOT NULL DEFAULT 0,
            outcome TEXT NOT NULL DEFAULT 'unknown',
            grounded INTEGER NOT NULL DEFAULT 0, notes TEXT)""")
        raw.execute("INSERT INTO sessions (ts, seat) VALUES ('2026-01-01T00:00:00','QA')")
        raw.commit(); raw.close()
        conn = dbmod.connect(path)
        self.assertIn("session_id", self._cols(conn, "sessions"))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1)

    def test_session_id_unique(self):
        conn = self._fresh()
        conn.execute("INSERT INTO sessions (ts, seat, session_id) VALUES ('t','QA','s1')")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO sessions (ts, seat, session_id) VALUES ('t','QA','s1')")
        # multiple NULL session_ids are allowed (seed rows)
        conn.execute("INSERT INTO sessions (ts, seat) VALUES ('t','QA')")
        conn.execute("INSERT INTO sessions (ts, seat) VALUES ('t','QA')")

    def test_roi_view_and_seeds(self):
        conn = self._fresh()
        rows = conn.execute("SELECT ticket, hde, flagged_low_actual FROM roi_view").fetchall()
        self.assertTrue(rows)  # seed.sql provides closed tickets
        self.assertTrue(conn.execute("SELECT COUNT(*) FROM spend").fetchone()[0] >= 3)
        # open tickets are excluded from the view
        open_in_view = conn.execute(
            "SELECT COUNT(*) FROM roi_view v JOIN tickets t ON t.ticket = v.ticket "
            "WHERE t.status != 'closed'").fetchone()[0]
        self.assertEqual(open_in_view, 0)


if __name__ == "__main__":
    unittest.main()
