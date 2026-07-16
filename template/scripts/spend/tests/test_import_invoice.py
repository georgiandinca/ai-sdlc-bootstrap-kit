#!/usr/bin/env python3
"""Unit tests for the invoice/flat-rate spend importer."""
import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2] / "dashboard"))
import import_invoice as imp  # noqa: E402
import db as dbmod  # noqa: E402


class TestImportInvoice(unittest.TestCase):
    def test_rows_from_csv(self):
        with open(HERE / "fixtures" / "invoice_sample.csv", encoding="utf-8") as f:
            rows = imp.rows_from_csv(f)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[3]["seat"], "(org)")      # blank seat normalised
        self.assertEqual(rows[0]["cost_eur"], 20.0)

    def test_rejects_bad_granularity(self):
        bad = io.StringIO("source,period_start,period_end,seat,cost_eur,granularity,notes\n"
                          "cursor,2026-06-01,2026-07-01,QA,5.0,monthly,x\n")
        with self.assertRaises(ValueError):
            imp.rows_from_csv(bad)

    def test_upsert_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = dbmod.connect(Path(tmp) / "u.db")
            base = conn.execute("SELECT COUNT(*) FROM spend").fetchone()[0]  # seeds
            with open(HERE / "fixtures" / "invoice_sample.csv", encoding="utf-8") as f:
                n1 = imp.upsert_spend(conn, imp.rows_from_csv(f))
            with open(HERE / "fixtures" / "invoice_sample.csv", encoding="utf-8") as f:
                imp.upsert_spend(conn, imp.rows_from_csv(f))   # re-import: no-op
            self.assertEqual(n1, 4)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM spend").fetchone()[0], base + 4)


if __name__ == "__main__":
    unittest.main()
