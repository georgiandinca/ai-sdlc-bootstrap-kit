#!/usr/bin/env python3
"""End-to-end test of the SessionEnd collector shell hook."""
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parents[2]          # .../template
HOOK = TEMPLATE / "scripts" / "session" / "collect-usage.sh"


class TestCollectUsage(unittest.TestCase):
    def _run(self, payload, db):
        return subprocess.run(
            ["bash", str(HOOK)], input=json.dumps(payload), text=True,
            cwd=TEMPLATE, env={"PATH": "/usr/bin:/bin:/usr/local/bin",
                               "SDLC_USAGE_DB": str(db)},
            capture_output=True, timeout=60,
        )

    def test_records_session_from_hook_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "u.db"
            payload = {"session_id": "hook-sess-1",
                       "transcript_path": str(HERE / "fixtures" / "transcript_ok.jsonl")}
            proc = self._run(payload, db)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            conn = sqlite3.connect(db)
            row = conn.execute(
                "SELECT tokens_in, cache_read_tokens FROM sessions "
                "WHERE session_id='hook-sess-1'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row, (1700, 11000))

    def test_never_breaks_the_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "u.db"
            for payload in ({}, {"transcript_path": "/does/not/exist.jsonl",
                                 "session_id": "x"}):
                proc = self._run(payload, db)
                self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_writes_committed_ledger_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "u.db"
            ledger = Path(tmp) / "ledger"
            payload = {"session_id": "hook-sess-2",
                       "transcript_path": str(HERE / "fixtures" / "transcript_ok.jsonl")}
            proc = subprocess.run(
                ["bash", str(HOOK)], input=json.dumps(payload), text=True,
                cwd=TEMPLATE, env={"PATH": "/usr/bin:/bin:/usr/local/bin",
                                   "SDLC_USAGE_DB": str(db),
                                   "SDLC_SESSIONS_DIR": str(ledger),
                                   "USER": "hooktester"},
                capture_output=True, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            csvs = list(ledger.glob("*.csv"))
            self.assertEqual(len(csvs), 1, "hook must write exactly one ledger CSV")
            self.assertIn("hook-sess-2", csvs[0].read_text(encoding="utf-8"))

    def test_error_log_is_redacted(self):
        # Planted secret: synthetic, built from parts so no scanner mistakes it for real.
        planted = "pa" + "ss-pl4nted"
        errlog = TEMPLATE / "scripts" / "session" / ".usage-errors.log"
        before = errlog.read_text(encoding="utf-8") if errlog.exists() else ""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "u.db"
            payload = {"session_id": "x",
                       "transcript_path": f"/does/not/exist?password={planted}"}
            proc = self._run(payload, db)
            self.assertEqual(proc.returncode, 0, proc.stderr)
        after = errlog.read_text(encoding="utf-8")
        new = after[len(before):]
        self.assertIn("password=<redacted:key_value>", new)
        self.assertNotIn(planted, new)


if __name__ == "__main__":
    unittest.main()
