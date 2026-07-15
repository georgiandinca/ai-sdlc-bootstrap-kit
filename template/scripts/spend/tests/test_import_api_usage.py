#!/usr/bin/env python3
"""Unit tests for the Anthropic Admin cost-report importer (no network)."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import import_api_usage as imp  # noqa: E402

PAYLOAD = json.loads((HERE / "fixtures" / "cost_report.json").read_text(encoding="utf-8"))


class TestRowsFromCostReport(unittest.TestCase):
    def test_buckets_become_spend_rows(self):
        rows = imp.rows_from_cost_report(PAYLOAD, eur_per_usd=0.92)
        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first["source"], "anthropic-api")
        self.assertEqual(first["granularity"], "tokens")
        self.assertEqual(first["seat"], "(org)")
        self.assertEqual(first["period_start"], "2026-06-22")
        self.assertEqual(first["period_end"], "2026-06-23")
        self.assertAlmostEqual(first["cost_eur"], 5.0 * 0.92)

    def test_unknown_shape_fails_loudly(self):
        with self.assertRaises(ValueError):
            imp.rows_from_cost_report({"totally": "different"}, eur_per_usd=1.0)

    def test_amount_accepts_numbers_and_strings(self):
        payload = {"data": [{"starting_at": "2026-01-01T00:00:00Z",
                             "ending_at": "2026-01-02T00:00:00Z",
                             "results": [{"amount": 2, "currency": "USD"}]}]}
        rows = imp.rows_from_cost_report(payload, eur_per_usd=1.0)
        self.assertAlmostEqual(rows[0]["cost_eur"], 2.0)


if __name__ == "__main__":
    unittest.main()
