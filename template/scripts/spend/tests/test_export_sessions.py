#!/usr/bin/env python3
"""Unit tests for the per-user session-ledger exporter."""
import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2] / "dashboard"))
import export_sessions as ex  # noqa: E402
import db as dbmod  # noqa: E402


def _seed_db(path, rows):
    """rows: (ts, seat, session_id, user, tokens_in, tokens_out) tuples."""
    conn = dbmod.connect(path)
    conn.execute("DELETE FROM sessions")  # drop seed.sql rows for determinism
    for r in rows:
        conn.execute(
            "INSERT INTO sessions (ts, seat, session_id, user, tokens_in, tokens_out) "
            "VALUES (?, ?, ?, ?, ?, ?)", r)
    conn.commit(); conn.close()


class TestSanitize(unittest.TestCase):
    def test_email_local_part_style(self):
        self.assertEqual(ex.sanitize_user("Geo.Dinca+x"), "geo.dinca-x")

    def test_empty_or_all_junk_is_none(self):
        self.assertIsNone(ex.sanitize_user("  "))
        self.assertIsNone(ex.sanitize_user("+++"))
        self.assertIsNone(ex.sanitize_user(None))


class TestResolveUser(unittest.TestCase):
    def test_override_wins_and_is_sanitized(self):
        self.assertEqual(ex.resolve_user("Geo@X"), "geo-x")


class TestExport(unittest.TestCase):
    def _export(self, tmp, rows, user="geo"):
        db = Path(tmp) / "u.db"
        _seed_db(db, rows)
        out = Path(tmp) / "ledger"
        rc = ex.main(["--db", str(db), "--out-dir", str(out), "--user", user])
        return rc, out / f"{user}.csv"

    def test_golden_csv_sorted_and_claims_null_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, path = self._export(tmp, [
                ("2026-07-02T10:00:00", "QA", "s2", None, 20, 2),
                ("2026-07-01T10:00:00", "Developer", "s1", "geo", 10, 1),
            ])
            self.assertEqual(rc, 0)
            with open(path, encoding="utf-8", newline="") as f:
                got = list(csv.reader(f))
            self.assertEqual(got[0], ex.HEADER)
            self.assertEqual(len(got), 3)
            self.assertEqual(got[1][0], "s1")                       # ts sort
            self.assertEqual([r[2] for r in got[1:]], ["geo", "geo"])  # NULL claimed

    def test_regeneration_is_byte_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, path = self._export(tmp, [("2026-07-01T10:00:00", "QA", "s1", "geo", 1, 1)])
            first = path.read_bytes()
            rc = ex.main(["--db", str(Path(tmp) / "u.db"),
                          "--out-dir", str(Path(tmp) / "ledger"), "--user", "geo"])
            self.assertEqual(rc, 0)
            self.assertEqual(path.read_bytes(), first)

    def test_teammate_rows_never_reexported(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, path = self._export(tmp, [
                ("2026-07-01T10:00:00", "QA", "mine", "geo", 1, 1),
                ("2026-07-01T11:00:00", "QA", "theirs", "ana", 2, 2),
            ])
            with open(path, encoding="utf-8", newline="") as f:
                ids = [r[0] for r in csv.reader(f)][1:]
            self.assertEqual(ids, ["mine"])

    def test_no_session_id_rows_excluded_and_no_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, path = self._export(tmp, [("2026-07-01T10:00:00", "QA", None, "geo", 1, 1)])
            self.assertEqual(rc, 0)
            self.assertFalse(path.exists())

    def test_missing_db_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = ex.main(["--db", str(Path(tmp) / "none.db"),
                          "--out-dir", str(Path(tmp) / "ledger"), "--user", "geo"])
            self.assertEqual(rc, 0)
            self.assertFalse((Path(tmp) / "none.db").exists())  # export never creates a DB

    def test_no_identity_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "u.db"
            _seed_db(db, [("t", "QA", "s1", None, 1, 1)])
            old_git = ex._git_config
            old_user = os.environ.pop("USER", None)
            ex._git_config = lambda key: ""
            try:
                rc = ex.main(["--db", str(db), "--out-dir", str(Path(tmp) / "l")])
            finally:
                ex._git_config = old_git
                if old_user is not None:
                    os.environ["USER"] = old_user
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
