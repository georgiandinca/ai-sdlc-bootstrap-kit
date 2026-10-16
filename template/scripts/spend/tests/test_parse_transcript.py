#!/usr/bin/env python3
"""Unit tests for the transcript parser + pricing (pure functions)."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import parse_transcript as pt  # noqa: E402

PRICES = json.loads((HERE.parent / "prices.json").read_text(encoding="utf-8"))


class TestParseUsage(unittest.TestCase):
    def test_ok_transcript(self):
        with open(HERE / "fixtures" / "transcript_ok.jsonl", encoding="utf-8") as f:
            per_model, skipped = pt.parse_usage(f)
        self.assertEqual(skipped, 0)
        u = per_model["claude-opus-4-8"]
        self.assertEqual(u["input_tokens"], 1400)
        self.assertEqual(u["output_tokens"], 300)
        self.assertEqual(u["cache_read_input_tokens"], 11000)
        self.assertEqual(u["cache_creation_input_tokens"], 300)
        t = pt.totals(per_model)
        self.assertEqual(t["tokens_in"], 1700)          # input + cache_creation
        self.assertEqual(t["cache_read_tokens"], 11000)
        self.assertEqual(t["model"], "claude-opus-4-8")

    def test_messy_transcript_is_defensive(self):
        with open(HERE / "fixtures" / "transcript_messy.jsonl", encoding="utf-8") as f:
            per_model, skipped = pt.parse_usage(f)
        self.assertEqual(skipped, 1)                    # the non-JSON line only
        self.assertIn("experimental-model-x", per_model)

    def test_empty(self):
        per_model, skipped = pt.parse_usage([])
        self.assertEqual((per_model, skipped), ({}, 0))
        self.assertIsNone(pt.totals({})["model"])


class TestPricing(unittest.TestCase):
    def test_known_model(self):
        per_model = {"claude-opus-4-8": {
            "input_tokens": 1_000_000, "output_tokens": 1_000_000,
            "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000}}
        cost, unknown = pt.price_usage(per_model, PRICES)
        p = PRICES["models"]["claude-opus-4-8"]
        self.assertAlmostEqual(cost, p["input"] + p["output"] + p["cache_read"] + p["cache_write"])
        self.assertEqual(unknown, [])

    def test_dated_variant_matches_by_prefix(self):
        per_model = {"claude-opus-4-8-20260101": {
            "input_tokens": 1_000_000, "output_tokens": 0,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
        cost, unknown = pt.price_usage(per_model, PRICES)
        self.assertEqual(unknown, [])
        self.assertAlmostEqual(cost, PRICES["models"]["claude-opus-4-8"]["input"])

    def test_unknown_model_costs_zero_and_is_flagged(self):
        per_model = {"experimental-model-x": {
            "input_tokens": 999, "output_tokens": 1,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
        cost, unknown = pt.price_usage(per_model, PRICES)
        self.assertEqual(cost, 0.0)
        self.assertEqual(unknown, ["experimental-model-x"])


import sqlite3
import tempfile


class TestMainUpsert(unittest.TestCase):
    def _run(self, tmp, session_id="sess-1"):
        db = Path(tmp) / "u.db"
        rc = pt.main([
            "--transcript", str(HERE / "fixtures" / "transcript_ok.jsonl"),
            "--session-id", session_id, "--seat", "Developer",
            "--ticket", "PROJ-7", "--db", str(db),
        ])
        self.assertEqual(rc, 0)
        return db

    def test_insert_then_idempotent_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._run(tmp)
            conn = sqlite3.connect(db)
            n0 = conn.execute("SELECT COUNT(*) FROM sessions WHERE session_id='sess-1'").fetchone()[0]
            self.assertEqual(n0, 1)
            # outcome preserved across re-runs (wrapup ritual owns it)
            conn.execute("UPDATE sessions SET outcome='accepted' WHERE session_id='sess-1'")
            conn.commit(); conn.close()
            self._run(tmp)  # same session id → upsert, not duplicate
            conn = sqlite3.connect(db)
            row = conn.execute(
                "SELECT COUNT(*), MAX(outcome), MAX(cache_read_tokens), MAX(model) "
                "FROM sessions WHERE session_id='sess-1'").fetchone()
            self.assertEqual(row[0], 1)
            self.assertEqual(row[1], "accepted")
            self.assertEqual(row[2], 11000)
            self.assertEqual(row[3], "claude-opus-4-8")

    def test_missing_transcript_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = pt.main(["--transcript", str(Path(tmp) / "nope.jsonl"),
                          "--session-id", "x", "--db", str(Path(tmp) / "u.db")])
            self.assertEqual(rc, 2)

    def test_user_recorded_and_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "u.db"
            args = ["--transcript", str(HERE / "fixtures" / "transcript_ok.jsonl"),
                    "--session-id", "sess-u", "--db", str(db)]
            self.assertEqual(pt.main(args + ["--user", "geo"]), 0)
            conn = sqlite3.connect(db)
            self.assertEqual(conn.execute(
                "SELECT user FROM sessions WHERE session_id='sess-u'").fetchone()[0], "geo")
            conn.close()
            # a re-run WITHOUT --user must not erase the recorded identity
            self.assertEqual(pt.main(args), 0)
            conn = sqlite3.connect(db)
            self.assertEqual(conn.execute(
                "SELECT user FROM sessions WHERE session_id='sess-u'").fetchone()[0], "geo")


# Planted secrets: synthetic, built from parts so no scanner mistakes them for real ones.
PLANTED_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0" + "k1L2m3N4o5P6q7R8"
PLANTED_PASSWORD = "hunter" + "2-planted"


class TestPlantedSecrets(unittest.TestCase):
    """Nothing the transcript or the hook hands over reaches the DB unredacted."""

    def test_db_row_is_redacted_and_notes_hold_counts_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "t.jsonl"
            transcript.write_text("\n".join(json.dumps(r) for r in (
                {"type": "user", "message": {"role": "user",
                                             "content": f"password={PLANTED_PASSWORD}"}},
                {"type": "assistant", "message": {
                    "role": "assistant", "model": f"model-{PLANTED_TOKEN}",
                    "usage": {"input_tokens": 10, "output_tokens": 2}}},
            )) + "\n", encoding="utf-8")
            db = Path(tmp) / "u.db"
            rc = pt.main(["--transcript", str(transcript), "--session-id", "planted-1",
                          "--task", f"rotate password={PLANTED_PASSWORD}",
                          "--db", str(db)])
            self.assertEqual(rc, 0)
            conn = sqlite3.connect(db)
            dump = "\n".join(conn.iterdump())
            row = conn.execute("SELECT task, model, notes FROM sessions "
                               "WHERE session_id='planted-1'").fetchone()
            conn.close()
            self.assertNotIn(PLANTED_TOKEN, dump)
            self.assertNotIn(PLANTED_PASSWORD, dump)
            self.assertEqual(row[0], "rotate password=<redacted:key_value>")
            self.assertEqual(row[1], "model-<redacted:token_shape>")
            self.assertIn("redacted: 1 key_value, 2 token_shape", row[2])


if __name__ == "__main__":
    unittest.main()
