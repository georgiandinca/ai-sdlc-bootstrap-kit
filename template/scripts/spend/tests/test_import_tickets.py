#!/usr/bin/env python3
"""Unit tests for the JIRA-ledger → tickets importer."""
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2] / "dashboard"))
import import_tickets as imp  # noqa: E402
import db as dbmod  # noqa: E402

CFG = json.loads((HERE.parent / "config.json").read_text(encoding="utf-8"))


class TestImportTickets(unittest.TestCase):
    def test_ledger_mapping(self):
        with open(HERE / "fixtures" / "issues_sample.csv", encoding="utf-8") as f:
            rows = imp.tickets_from_ledger(f, CFG)
        by_key = {r["ticket"]: r for r in rows}
        self.assertEqual(by_key["PROJ-1"]["status"], "closed")
        self.assertEqual(by_key["PROJ-1"]["estimate_human_days"],
                         3 * CFG["points_to_days"])
        self.assertEqual(by_key["PROJ-2"]["status"], "open")
        self.assertIsNone(by_key["PROJ-3"]["estimate_human_days"])  # no points
        self.assertEqual(by_key["PROJ-1"]["evidence_tier"], "pre-estimate")

    def test_upsert_preserves_actuals(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = dbmod.connect(Path(tmp) / "u.db")
            with open(HERE / "fixtures" / "issues_sample.csv", encoding="utf-8") as f:
                imp.upsert_tickets(conn, imp.tickets_from_ledger(f, CFG))
            with open(HERE / "fixtures" / "actuals_sample.csv", encoding="utf-8") as f:
                imp.upsert_tickets(conn, imp.apply_actuals(f))
            # re-import the ledger — must NOT wipe the actuals
            with open(HERE / "fixtures" / "issues_sample.csv", encoding="utf-8") as f:
                imp.upsert_tickets(conn, imp.tickets_from_ledger(f, CFG))
            row = conn.execute(
                "SELECT actual_human_days, evidence_tier FROM tickets "
                "WHERE ticket='PROJ-1'").fetchone()
            self.assertEqual(row, (1.0, "calibration"))

    def test_low_actual_is_flagged_in_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = dbmod.connect(Path(tmp) / "u.db")
            with open(HERE / "fixtures" / "issues_sample.csv", encoding="utf-8") as f:
                imp.upsert_tickets(conn, imp.tickets_from_ledger(f, CFG))
            with open(HERE / "fixtures" / "actuals_sample.csv", encoding="utf-8") as f:
                imp.upsert_tickets(conn, imp.apply_actuals(f))
            row = conn.execute(
                "SELECT hde, flagged_low_actual FROM roi_view WHERE ticket='PROJ-3'"
            ).fetchone()
            self.assertIsNone(row[0])           # absurd HDE suppressed
            self.assertEqual(row[1], 1)         # ...but flagged for review

    def test_apply_actuals_rejects_unknown_evidence_tier(self):
        csv_text = "ticket,actual_human_days,evidence_tier\nPROJ-1,1.0,calibraton\n"
        with self.assertRaises(ValueError):
            imp.apply_actuals(io.StringIO(csv_text))


if __name__ == "__main__":
    unittest.main()
