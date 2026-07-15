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

    def test_bucket_without_results_fails_loudly(self):
        payload = {"data": [{"starting_at": "2026-01-01T00:00:00Z",
                             "ending_at": "2026-01-02T00:00:00Z"}]}
        with self.assertRaises(ValueError):
            imp.rows_from_cost_report(payload, eur_per_usd=1.0)

    def test_result_without_amount_fails_loudly(self):
        payload = {"data": [{"starting_at": "2026-01-01T00:00:00Z",
                             "ending_at": "2026-01-02T00:00:00Z",
                             "results": [{"currency": "USD"}]}]}
        with self.assertRaises(ValueError):
            imp.rows_from_cost_report(payload, eur_per_usd=1.0)


class TestFetchCostReport(unittest.TestCase):
    def setUp(self):
        self._orig_urlopen = imp.urllib.request.urlopen

    def tearDown(self):
        imp.urllib.request.urlopen = self._orig_urlopen

    def test_network_error_exits_with_clear_message(self):
        def boom(*args, **kwargs):
            raise imp.urllib.error.URLError("boom")

        imp.urllib.request.urlopen = boom
        with self.assertRaises(SystemExit) as ctx:
            imp.fetch_cost_report("2026-01-01", "2026-01-02", "sk-test")
        self.assertIn("cost_report request failed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
