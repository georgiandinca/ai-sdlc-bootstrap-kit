#!/usr/bin/env python3
"""Unit tests for the stdlib ROI logic over a seeded fixture DB."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import db as dbmod  # noqa: E402
import roi  # noqa: E402


def fixture_conn(tmp):
    conn = dbmod.connect(Path(tmp) / "u.db")
    conn.execute("DELETE FROM sessions"); conn.execute("DELETE FROM spend")
    conn.execute("DELETE FROM tickets")
    conn.executescript("""
    INSERT INTO sessions (ts, seat, ticket, tokens_in, tokens_out, cost_usd, outcome)
      VALUES ('2026-06-10T10:00:00','Developer','T-1',1000,200,10.0,'accepted'),
             ('2026-06-11T10:00:00','Developer','T-2',1000,200,20.0,'accepted'),
             ('2026-06-12T10:00:00','QA', NULL,  500,100, 5.0,'accepted');
    INSERT INTO spend (source, period_start, period_end, seat, cost_eur, granularity)
      VALUES ('claude-max','2026-06-01','2026-07-01','Developer',300.0,'flat-rate');
    INSERT INTO tickets (ticket, estimate_human_days, actual_human_days,
                         day_rate_eur, evidence_tier, status, closed_at) VALUES
      ('T-1', 2.0, 1.0, 500, 'calibration',  'closed', '2026-06-10T18:00:00'),
      ('T-2', 1.0, 1.0, 500, 'post-hoc',     'closed', '2026-06-11T18:00:00'),
      ('T-3', 1.0, NULL,500, 'pre-estimate', 'closed', '2026-06-12T18:00:00'),
      ('T-4', 1.0, 0.02,500, 'pre-estimate', 'closed', '2026-06-13T18:00:00'),
      ('T-5', 1.0, 1.0, 500, 'pre-estimate', 'open',   NULL);
    """)
    conn.commit()
    return conn


class TestRoi(unittest.TestCase):
    def test_amortization_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = fixture_conn(tmp)
            # 30-day month, 300 EUR → 10 EUR/day; 15 days overlap = 150 EUR
            self.assertAlmostEqual(
                roi.amortized_spend_eur(conn, "2026-06-01", "2026-06-16"), 150.0)
            # zero overlap
            self.assertAlmostEqual(
                roi.amortized_spend_eur(conn, "2026-08-01", "2026-09-01"), 0.0)

    def test_period_rollup(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = fixture_conn(tmp)
            r = roi.period_rollup(conn, "2026-06-01", "2026-07-01", eur_per_usd=1.0)
            self.assertAlmostEqual(r["ai_sessions_eur"], 35.0)
            self.assertAlmostEqual(r["ai_spend_eur"], 300.0)
            self.assertAlmostEqual(r["ai_total_eur"], 335.0)

    def test_roi_summary_honesty_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = fixture_conn(tmp)
            s = roi.roi_summary(conn, eur_per_usd=1.0)
            # T-1 + T-2 usable; T-3 no actual, T-4 flagged, T-5 open
            self.assertEqual(s["coverage"], (2, 4))
            self.assertEqual(s["flagged"], ["T-4"])
            # blended: value (2+1)*500=1500 ; cost (1+1)*500 + 10 + 20 = 1030
            self.assertAlmostEqual(s["roi"], 1500.0 / 1030.0)
            self.assertIn("calibration", s["per_tier"])
            lo, hi = s["band"]
            self.assertLessEqual(lo, s["roi"])
            self.assertGreaterEqual(hi, s["roi"])

    def test_client_report_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = fixture_conn(tmp)
            s = roi.roi_summary(conn, eur_per_usd=1.0)
            r = roi.period_rollup(conn, "2026-06-01", "2026-07-01", 1.0)
            html = roi.render_client_report(s, r, roi.ticket_rows(conn), "June 2026")
            self.assertIn("ROI computed over 2 of 4 closed tickets", html)
            self.assertIn("June 2026", html)
            self.assertIn("Methodology", html)


if __name__ == "__main__":
    unittest.main()
