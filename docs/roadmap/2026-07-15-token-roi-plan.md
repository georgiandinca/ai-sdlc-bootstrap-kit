# AI Consumption, Token Economy & ROI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Feed the dashboard's `sessions` table with real Claude Code telemetry, add a `spend` table for invoice/flat-rate money, ship an enforced token-economy pack, and compute a defensible human-day-equivalent ROI with two new dashboard tabs — per `docs/roadmap/2026-07-15-token-roi-design.md`.

**Architecture:** Collectors write, dashboard reads. A SessionEnd hook (`collect-usage.sh` → `parse_transcript.py`) upserts one `sessions` row per Claude Code session. Two importers (`import_invoice.py`, `import_api_usage.py`) upsert `spend` rows; `import_tickets.py` fills `tickets` from the JIRA ledger. `roi_view` (SQL) + `roi.py` (stdlib) compute per-ticket and per-period ROI; `app.py` gains Waste-signals and ROI tabs. The technique pack ships as `.claude/rules/token-economy.md`, seat-profile model routing, and a brief-churn CI check.

**Tech Stack:** Python 3.12 stdlib only for all scripts and their tests (`sqlite3`, `csv`, `json`, `urllib`, `unittest`) — matches the Phase-3/4/JIRA posture. `dashboard/app.py` may use pandas/streamlit (already in `dashboard/requirements.txt`); `dashboard/roi.py` is stdlib so CI can test it without installing pandas. Bash for the hook. GitLab CI (kit) + GitHub workflow (template) governance gates.

## Global Constraints

- **Stdlib only** in `scripts/` and `dashboard/roi.py` / `dashboard/db.py` and every test file. No new entries in `dashboard/requirements.txt`.
- **All work lives under `template/`** except this plan/spec (repo-root `docs/roadmap/`) and `.gitlab-ci.yml` (repo root). Paths below are relative to the repo root unless stated.
- **Hooks never break sessions**: every hook script path ends `exit 0`; failures append to `template/scripts/session/.usage-errors.log`.
- **Idempotent writes**: `sessions` upserts on unique `session_id`; `spend` upserts on `(source, period_start, seat)`; `tickets` upserts on primary key `ticket`. Re-running any collector is a no-op.
- **Honesty guards**: unknown model → cost 0 + note (never guessed); unattributed rows kept, never dropped; ROI excludes tickets without estimates but reports coverage; `spend.granularity` always set.
- **`spend.seat`**: `NOT NULL DEFAULT '(org)'` — the literal string `'(org)'` means org-level/unattributable (avoids SQLite's NULLs-are-distinct-in-UNIQUE trap).
- **Money units**: `sessions.cost_usd` stays USD (Anthropic prices are USD); `spend.cost_eur` and everything in `roi.py` is EUR, converted via `eur_per_usd` in `template/scripts/spend/prices.json`.
- **Tests are unittest files executable directly** (`python3 path/to/test_x.py`), like `scripts/knowledge/tests/`.
- **Branch**: create `feat/token-roi` from `main` before Task 1.
- **Commit trailer** — end every commit message with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

## File Structure

**Create:**
- `template/scripts/spend/prices.json` — model → USD/Mtok price table + `eur_per_usd`.
- `template/scripts/spend/config.json` — `points_to_days`, `day_rate_eur`, `working_days_per_month`, `closed_statuses`.
- `template/scripts/spend/parse_transcript.py` — transcript JSONL → priced `sessions` upsert.
- `template/scripts/spend/import_invoice.py` — invoice/flat-rate CSV → `spend` upsert.
- `template/scripts/spend/import_api_usage.py` — Anthropic Admin cost report → `spend` upsert.
- `template/scripts/spend/import_tickets.py` — JIRA ledger CSV (+ actuals CSV) → `tickets` upsert.
- `template/scripts/spend/README.md` — how to run each importer; batch-discount note (technique 7).
- `template/scripts/spend/tests/` — `test_parse_transcript.py`, `test_import_invoice.py`, `test_import_api_usage.py`, `test_import_tickets.py`, `fixtures/` (transcript JSONLs, invoice CSV, cost-report JSON, ledger CSV).
- `template/scripts/session/collect-usage.sh` — SessionEnd hook.
- `template/scripts/check-brief-churn.py` + `template/scripts/tests/test_check_brief_churn.py`.
- `template/.claude/rules/token-economy.md` — the enforced technique rule file.
- `template/dashboard/roi.py` — stdlib ROI logic + client-report HTML renderer.
- `template/dashboard/tests/` — `test_schema.py`, `test_roi.py`.

**Modify:**
- `template/dashboard/schema.sql` — sessions columns, `spend`, `tickets`, `roi_view`, indexes.
- `template/dashboard/db.py` — `_ensure_columns` migration helper.
- `template/dashboard/seed.sql` — synthetic `spend` + `tickets` rows.
- `template/dashboard/app.py` — two new tabs.
- `template/dashboard/README.md` — document the new tabs + collectors.
- `template/.claude/settings.json` — add collect-usage.sh to SessionEnd.
- `template/scripts/session/seat-profiles.json` — `default_model` + `escalation_hint` per seat.
- `template/.github/workflows/ai-governance.yml` and `.gitlab-ci.yml` — run new tests + churn check.
- `template/FOLDER-INDEX.md` — add `scripts/spend/` line.

---

## Task 1: Schema deltas, db.py migration, seeds

**Files:**
- Modify: `template/dashboard/schema.sql`, `template/dashboard/db.py`, `template/dashboard/seed.sql`
- Test: `template/dashboard/tests/test_schema.py`

**Interfaces:**
- Produces: tables `spend(id, source, period_start, period_end, seat, cost_eur, granularity, notes)` and `tickets(ticket, estimate_human_days, actual_human_days, day_rate_eur, evidence_tier, status, closed_at)`; view `roi_view` (columns: `ticket, estimate_human_days, actual_human_days, day_rate_eur, evidence_tier, closed_at, ai_cost_usd, human_cost_eur, value_eur, hde, flagged_low_actual`); `sessions` gains `session_id TEXT` (unique index `idx_sessions_session_id`), `model TEXT`, `cache_read_tokens INTEGER NOT NULL DEFAULT 0`. `db.connect(db_path)` migrates pre-existing DBs.

- [ ] **Step 1: Write the failing test** — create `template/dashboard/tests/test_schema.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/dashboard/tests/test_schema.py`
Expected: FAIL — `no such table: spend` (and missing columns).

- [ ] **Step 3: Implement.** Append to `template/dashboard/schema.sql` (and extend the `CREATE TABLE IF NOT EXISTS sessions` block with the three new columns after `notes TEXT` — add `, session_id TEXT, model TEXT, cache_read_tokens INTEGER NOT NULL DEFAULT 0`; fresh DBs get them directly, old DBs via db.py):

```sql
-- Consumption + ROI (token-roi theme). spend = money that does not arrive as
-- per-session tokens; seat '(org)' means org-level / unattributable.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_session_id ON sessions(session_id);

CREATE TABLE IF NOT EXISTS spend (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,                 -- anthropic-api | cursor | copilot | claude-max | other
    period_start TEXT NOT NULL,                 -- ISO date, inclusive
    period_end   TEXT NOT NULL,                 -- ISO date, exclusive
    seat         TEXT NOT NULL DEFAULT '(org)',
    cost_eur     REAL NOT NULL,
    granularity  TEXT NOT NULL,                 -- tokens | invoice | flat-rate
    notes        TEXT,
    UNIQUE (source, period_start, seat)
);

CREATE TABLE IF NOT EXISTS tickets (
    ticket              TEXT PRIMARY KEY,
    estimate_human_days REAL,
    actual_human_days   REAL,
    day_rate_eur        REAL,
    evidence_tier       TEXT NOT NULL DEFAULT 'pre-estimate',
                        -- calibration | pre-estimate | velocity | post-hoc
    status              TEXT NOT NULL DEFAULT 'open',
    closed_at           TEXT
);

-- Per-ticket ROI over closed tickets. Session tokens only on the AI side —
-- invoice/flat-rate spend cannot honestly be split per ticket; it joins the
-- ROI at period level (dashboard/roi.py). Actuals < 0.1 day are flagged, not
-- allowed to produce absurd HDE values.
CREATE VIEW IF NOT EXISTS roi_view AS
SELECT
    t.ticket, t.estimate_human_days, t.actual_human_days, t.day_rate_eur,
    t.evidence_tier, t.closed_at,
    COALESCE(s.ai_cost_usd, 0)             AS ai_cost_usd,
    t.actual_human_days * t.day_rate_eur   AS human_cost_eur,
    t.estimate_human_days * t.day_rate_eur AS value_eur,
    CASE WHEN t.actual_human_days >= 0.1
         THEN t.estimate_human_days / t.actual_human_days END AS hde,
    CASE WHEN t.actual_human_days IS NOT NULL AND t.actual_human_days < 0.1
         THEN 1 ELSE 0 END                 AS flagged_low_actual
FROM tickets t
LEFT JOIN (
    SELECT ticket, SUM(cost_usd) AS ai_cost_usd
    FROM sessions WHERE ticket IS NOT NULL GROUP BY ticket
) s ON s.ticket = t.ticket
WHERE t.status = 'closed';
```

In `template/dashboard/db.py`, replace `ensure_schema` with:

```python
def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict) -> None:
    """Add any missing columns to a pre-existing table (SQLite has no
    ALTER TABLE IF NOT EXISTS; new columns also live in schema.sql for
    fresh DBs)."""
    have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, decl in columns.items():
        if name not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def ensure_schema(conn: sqlite3.Connection) -> None:
    _ensure_columns(conn, "sessions", {
        "session_id": "TEXT",
        "model": "TEXT",
        "cache_read_tokens": "INTEGER NOT NULL DEFAULT 0",
    })
    if SCHEMA.exists():
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
```

(`_ensure_columns` runs first so the unique index / view in schema.sql never reference a missing column; `PRAGMA table_info` on a not-yet-created table returns nothing, so fresh DBs skip it and get the columns from schema.sql.)

Append to `template/dashboard/seed.sql`:

```sql
INSERT INTO spend (source, period_start, period_end, seat, cost_eur, granularity, notes) VALUES
  ('claude-max',    '2026-06-01', '2026-07-01', 'Developer', 90.0, 'flat-rate', 'seed: Max seat, monthly'),
  ('cursor',        '2026-06-01', '2026-07-01', 'QA',        20.0, 'invoice',   'seed: Cursor Pro'),
  ('anthropic-api', '2026-06-22', '2026-06-23', '(org)',      4.6, 'tokens',    'seed: usage API, one day');

INSERT INTO tickets (ticket, estimate_human_days, actual_human_days, day_rate_eur, evidence_tier, status, closed_at) VALUES
  ('<TICKET>-101', 2.0, 1.0, 500, 'pre-estimate', 'closed', '2026-06-23T12:00:00'),
  ('<TICKET>-090', 1.5, 1.5, 500, 'post-hoc',     'closed', '2026-06-24T12:00:00'),
  ('<TICKET>-077', 3.0, 1.5, 500, 'calibration',  'closed', '2026-06-25T12:00:00'),
  ('<TICKET>-112', 2.0, NULL, 500, 'pre-estimate', 'open',   NULL);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/dashboard/tests/test_schema.py`
Expected: PASS (4 tests).

- [ ] **Step 5: Delete the stale derived DB and commit** (schema changed; `utilization.db` is regenerated on next run — it is git-ignored per `*.db`, but remove the local copy so the next dashboard run rebuilds):

```bash
rm -f template/dashboard/utilization.db
git add template/dashboard/schema.sql template/dashboard/db.py template/dashboard/seed.sql template/dashboard/tests/test_schema.py
git commit -m "feat(dashboard): spend/tickets tables, roi_view, sessions telemetry columns

Refs: token-roi design §3

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 2: prices/config + transcript parser (pure functions)

**Files:**
- Create: `template/scripts/spend/prices.json`, `template/scripts/spend/config.json`, `template/scripts/spend/parse_transcript.py`, `template/scripts/spend/tests/fixtures/transcript_ok.jsonl`, `.../transcript_messy.jsonl`
- Test: `template/scripts/spend/tests/test_parse_transcript.py`

**Interfaces:**
- Produces: `parse_usage(lines) -> (per_model: dict[str, dict[str, int]], skipped: int)` — per-model keys `input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens`; `price_usage(per_model, prices: dict) -> (cost_usd: float, unknown_models: list[str])`; `totals(per_model) -> dict` with keys `tokens_in` (= input + cache_creation), `tokens_out`, `cache_read_tokens`, `model` (dominant by total tokens, or `None`). Prices match by exact id, else longest key that is a prefix of the model string (handles dated variants).

- [ ] **Step 1: Create the fixtures.** `transcript_ok.jsonl` (two assistant messages, one model):

```jsonl
{"type":"user","message":{"role":"user","content":"hi"}}
{"type":"assistant","message":{"role":"assistant","model":"claude-opus-4-8","usage":{"input_tokens":1000,"output_tokens":200,"cache_read_input_tokens":5000,"cache_creation_input_tokens":300}}}
{"type":"assistant","message":{"role":"assistant","model":"claude-opus-4-8","usage":{"input_tokens":400,"output_tokens":100,"cache_read_input_tokens":6000,"cache_creation_input_tokens":0}}}
```

`transcript_messy.jsonl` (malformed line, unknown model, missing usage, empty line):

```jsonl
{"type":"assistant","message":{"role":"assistant","model":"claude-opus-4-8","usage":{"input_tokens":100,"output_tokens":50,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}}
not json at all {{{

{"type":"assistant","message":{"role":"assistant","model":"experimental-model-x","usage":{"input_tokens":10,"output_tokens":5}}}
{"type":"assistant","message":{"role":"assistant","model":"claude-opus-4-8"}}
```

- [ ] **Step 2: Write the failing test** — `template/scripts/spend/tests/test_parse_transcript.py`:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 template/scripts/spend/tests/test_parse_transcript.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'parse_transcript'`.

- [ ] **Step 4: Implement.** `template/scripts/spend/prices.json` (USD per Mtok; cache_read = 0.1× input, cache_write = 1.25× input at 5-min TTL — a maintained config, refresh from platform.claude.com/docs/en/pricing when models change):

```json
{
  "eur_per_usd": 0.92,
  "models": {
    "claude-fable-5":    {"input": 10.0, "output": 50.0, "cache_read": 1.0, "cache_write": 12.5},
    "claude-opus-4-8":   {"input": 5.0,  "output": 25.0, "cache_read": 0.5, "cache_write": 6.25},
    "claude-opus-4-7":   {"input": 5.0,  "output": 25.0, "cache_read": 0.5, "cache_write": 6.25},
    "claude-opus-4-6":   {"input": 5.0,  "output": 25.0, "cache_read": 0.5, "cache_write": 6.25},
    "claude-sonnet-5":   {"input": 3.0,  "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
    "claude-sonnet-4-6": {"input": 3.0,  "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
    "claude-haiku-4-5":  {"input": 1.0,  "output": 5.0,  "cache_read": 0.1, "cache_write": 1.25}
  }
}
```

`template/scripts/spend/config.json`:

```json
{
  "points_to_days": 0.5,
  "day_rate_eur": 500.0,
  "working_days_per_month": 20,
  "closed_statuses": ["Done", "Closed", "Resolved"]
}
```

`template/scripts/spend/parse_transcript.py` (pure functions half; `main` comes in Task 3):

```python
#!/usr/bin/env python3
"""Parse a Claude Code transcript (JSONL) into per-session token usage, price
it, and upsert one row into the dashboard's sessions table.

The transcript format is OBSERVED, not a contract: malformed lines are
skipped and counted; unknown models cost 0 and are flagged in notes — never
a guessed price. Stdlib only.

Usage:
  parse_transcript.py --transcript <path.jsonl> --session-id <uuid> \
      --db dashboard/utilization.db [--seat Developer] [--ticket PROJ-123]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRICES_PATH = HERE / "prices.json"

_USAGE_KEYS = ("input_tokens", "output_tokens",
               "cache_read_input_tokens", "cache_creation_input_tokens")


def parse_usage(lines):
    """Sum message.usage across JSONL lines, per model.

    Returns (per_model, skipped) where skipped counts unparseable lines.
    Lines without a usage dict are ignored silently (user turns, meta rows).
    """
    per_model = defaultdict(lambda: {k: 0 for k in _USAGE_KEYS})
    skipped = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        msg = rec.get("message") if isinstance(rec, dict) else None
        usage = msg.get("usage") if isinstance(msg, dict) else None
        if not isinstance(usage, dict):
            continue
        model = msg.get("model") or "unknown"
        agg = per_model[model]
        for key in _USAGE_KEYS:
            value = usage.get(key, 0)
            if isinstance(value, (int, float)):
                agg[key] += int(value)
    return dict(per_model), skipped


def _price_for(model, prices):
    models = prices.get("models", {})
    if model in models:
        return models[model]
    for key in sorted(models, key=len, reverse=True):
        if model.startswith(key):
            return models[key]
    return None


def price_usage(per_model, prices):
    """Return (cost_usd, unknown_models). Unknown models cost 0 — flagged,
    never guessed."""
    cost, unknown = 0.0, []
    for model, u in per_model.items():
        p = _price_for(model, prices)
        if p is None:
            unknown.append(model)
            continue
        cost += (u["input_tokens"] * p.get("input", 0)
                 + u["output_tokens"] * p.get("output", 0)
                 + u["cache_read_input_tokens"] * p.get("cache_read", 0)
                 + u["cache_creation_input_tokens"] * p.get("cache_write", 0)) / 1_000_000
    return cost, sorted(unknown)


def totals(per_model):
    """Session-level sums. tokens_in = fresh input + cache writes; cache
    reads are tracked separately (cache-hit ratio = cache_read / (cache_read
    + tokens_in)). model = dominant model by total tokens."""
    tokens_in = sum(u["input_tokens"] + u["cache_creation_input_tokens"]
                    for u in per_model.values())
    tokens_out = sum(u["output_tokens"] for u in per_model.values())
    cache_read = sum(u["cache_read_input_tokens"] for u in per_model.values())
    model = None
    if per_model:
        model = max(per_model, key=lambda m: sum(per_model[m].values()))
    return {"tokens_in": tokens_in, "tokens_out": tokens_out,
            "cache_read_tokens": cache_read, "model": model}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 template/scripts/spend/tests/test_parse_transcript.py`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add template/scripts/spend
git commit -m "feat(spend): transcript usage parser + model price table (pure, stdlib)

Refs: token-roi design §4

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 3: transcript parser main() — priced upsert into sessions

**Files:**
- Modify: `template/scripts/spend/parse_transcript.py`
- Test: `template/scripts/spend/tests/test_parse_transcript.py` (append a class)

**Interfaces:**
- Consumes: `dashboard/db.py: connect(db_path)` (ensures schema + migration from Task 1).
- Produces: `upsert_session(conn, row: dict) -> None` (keys: `ts, seat, task, ticket, tokens_in, tokens_out, cost_usd, notes, session_id, model, cache_read_tokens`); CLI `main(argv) -> int` (0 on success; 2 on missing transcript). `outcome` stays `'unknown'` on insert and is **not** overwritten on re-run (the wrap-up ritual sets it).

- [ ] **Step 1: Append the failing test class** to `test_parse_transcript.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/spend/tests/test_parse_transcript.py`
Expected: FAIL — `AttributeError: module 'parse_transcript' has no attribute 'main'`.

- [ ] **Step 3: Implement** — append to `parse_transcript.py`:

```python
def upsert_session(conn, row):
    conn.execute(
        """INSERT INTO sessions (ts, seat, tool, task, ticket, tokens_in,
               tokens_out, cost_usd, outcome, grounded, notes, session_id,
               model, cache_read_tokens)
           VALUES (:ts, :seat, 'claude', :task, :ticket, :tokens_in,
               :tokens_out, :cost_usd, 'unknown', 0, :notes, :session_id,
               :model, :cache_read_tokens)
           ON CONFLICT(session_id) DO UPDATE SET
               tokens_in=excluded.tokens_in, tokens_out=excluded.tokens_out,
               cost_usd=excluded.cost_usd, model=excluded.model,
               cache_read_tokens=excluded.cache_read_tokens,
               notes=excluded.notes""",
        row,
    )
    conn.commit()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--seat", default="unknown")
    ap.add_argument("--ticket", default=None)
    ap.add_argument("--task", default=None)
    ap.add_argument("--db", required=True)
    args = ap.parse_args(argv)

    transcript = Path(args.transcript)
    if not transcript.is_file():
        print(f"[parse-transcript] no transcript at {transcript}", file=sys.stderr)
        return 2

    with open(transcript, encoding="utf-8", errors="replace") as f:
        per_model, skipped = parse_usage(f)
    prices = (json.loads(PRICES_PATH.read_text(encoding="utf-8"))
              if PRICES_PATH.exists() else {"models": {}})
    cost_usd, unknown = price_usage(per_model, prices)
    t = totals(per_model)

    notes = []
    if skipped:
        notes.append(f"skipped {skipped} malformed transcript lines")
    if unknown:
        notes.append("unpriced models (cost=0): " + ", ".join(unknown))

    sys.path.insert(0, str(HERE.parents[1] / "dashboard"))
    import db as dbmod  # noqa: E402

    conn = dbmod.connect(args.db)
    try:
        upsert_session(conn, {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "seat": args.seat, "task": args.task, "ticket": args.ticket,
            "tokens_in": t["tokens_in"], "tokens_out": t["tokens_out"],
            "cost_usd": round(cost_usd, 4),
            "notes": "; ".join(notes) or None,
            "session_id": args.session_id, "model": t["model"],
            "cache_read_tokens": t["cache_read_tokens"],
        })
    finally:
        conn.close()
    print(f"[parse-transcript] {args.session_id}: {t['tokens_in']}in/"
          f"{t['tokens_out']}out/{t['cache_read_tokens']}cache ${cost_usd:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/scripts/spend/tests/test_parse_transcript.py`
Expected: PASS (9 tests). Note: `dbmod.connect` seeds `seed.sql` into a brand-new DB — the test asserts on `session_id='sess-1'` specifically, so seeds don't interfere.

- [ ] **Step 5: Commit**

```bash
git add template/scripts/spend
git commit -m "feat(spend): parse_transcript main() upserts priced sessions rows

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 4: collect-usage.sh SessionEnd hook

**Files:**
- Create: `template/scripts/session/collect-usage.sh` (mode 755)
- Modify: `template/.claude/settings.json`
- Test: `template/scripts/spend/tests/test_collect_usage.py`

**Interfaces:**
- Consumes: Claude Code SessionEnd hook stdin JSON (`{"session_id": ..., "transcript_path": ..., ...}`); `scripts/session/lib.sh: sdlc_seat`; `parse_transcript.py` CLI.
- Produces: a `sessions` row per ended session. Env override `SDLC_USAGE_DB` (default `dashboard/utilization.db` relative to repo root) — used by tests. Never exits non-zero.

- [ ] **Step 1: Write the failing test** — `template/scripts/spend/tests/test_collect_usage.py`:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/spend/tests/test_collect_usage.py`
Expected: FAIL — hook script does not exist (`No such file or directory`).

- [ ] **Step 3: Implement** — `template/scripts/session/collect-usage.sh`:

```bash
#!/usr/bin/env bash
# SessionEnd hook: record the ended Claude Code session's token usage into
# the dashboard DB (token-roi design §4). Reads the hook payload JSON from
# stdin (session_id, transcript_path). Telemetry may be lost; a session
# ritual must never break: every path exits 0, failures append to
# scripts/session/.usage-errors.log.
set -u

root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
# In the kit repo the workspace root is the kit, not template/ — resolve to
# the directory that actually holds scripts/session (template/ in the kit,
# repo root in a generated project).
[ -d "$root/scripts/session" ] || root="$root/template"
[ -d "$root/scripts/session" ] || exit 0
cd "$root" || exit 0
errlog="scripts/session/.usage-errors.log"
log_err() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >> "$errlog" 2>/dev/null; }

payload=$(cat 2>/dev/null || true)
read_field() {
  printf '%s' "$payload" | python3 -c \
    'import json,sys;print(json.load(sys.stdin).get(sys.argv[1],""))' "$1" 2>/dev/null || true
}
transcript=$(read_field transcript_path)
session_id=$(read_field session_id)

if [ -z "$transcript" ] || [ ! -f "$transcript" ]; then
  log_err "no usable transcript in hook payload (transcript='$transcript')"
  exit 0
fi
[ -n "$session_id" ] || session_id=$(basename "$transcript" .jsonl)

seat="unknown"
if [ -f scripts/session/lib.sh ]; then
  # shellcheck disable=SC1091
  . scripts/session/lib.sh 2>/dev/null || true
  s=$(sdlc_seat 2>/dev/null || true); [ -n "$s" ] && seat="$s"
fi
branch=$(git branch --show-current 2>/dev/null || true)
ticket=$(printf '%s' "$branch" | grep -oE '[A-Z][A-Z0-9]+-[0-9]+' | head -n1 || true)

db="${SDLC_USAGE_DB:-dashboard/utilization.db}"
if python3 scripts/spend/parse_transcript.py \
     --transcript "$transcript" --session-id "$session_id" \
     --seat "$seat" ${ticket:+--ticket "$ticket"} --db "$db" 2>>"$errlog"; then
  :
else
  log_err "parse_transcript failed for $transcript"
fi
exit 0
```

Then `chmod +x template/scripts/session/collect-usage.sh`, and in `template/.claude/settings.json` change the SessionEnd block to:

```json
    "SessionEnd": [
      {
        "hooks": [
          { "type": "command", "command": "bash scripts/session/auto-save.sh 2>/dev/null || true" },
          { "type": "command", "command": "bash scripts/session/collect-usage.sh 2>/dev/null || true" }
        ]
      }
    ],
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/scripts/spend/tests/test_collect_usage.py`
Expected: PASS (2 tests). Also add `scripts/session/.usage-errors.log` to `template/.gitignore` (append a line `scripts/session/.usage-errors.log`).

- [ ] **Step 5: Commit**

```bash
git add template/scripts/session/collect-usage.sh template/.claude/settings.json template/.gitignore template/scripts/spend/tests/test_collect_usage.py
git commit -m "feat(session): SessionEnd hook records real token usage into the dashboard

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 5: import_invoice.py — invoice / flat-rate CSV → spend

**Files:**
- Create: `template/scripts/spend/import_invoice.py`, `template/scripts/spend/tests/fixtures/invoice_sample.csv`
- Test: `template/scripts/spend/tests/test_import_invoice.py`

**Interfaces:**
- Produces: `rows_from_csv(fileobj) -> list[dict]` (validates `source`, `granularity`, ISO dates, float `cost_eur`; blank seat → `'(org)'`; raises `ValueError` naming the row on bad input); `upsert_spend(conn, rows) -> int` (rows written; conflict target `(source, period_start, seat)`); CLI `main(["--csv", path, "--db", path])`.
- CSV header (canonical, verbatim): `source,period_start,period_end,seat,cost_eur,granularity,notes`

- [ ] **Step 1: Create the fixture** `invoice_sample.csv`:

```csv
source,period_start,period_end,seat,cost_eur,granularity,notes
cursor,2026-06-01,2026-07-01,Developer,20.00,invoice,Cursor Pro June
copilot,2026-06-01,2026-07-01,QA,19.00,invoice,Copilot Business June
claude-max,2026-06-01,2026-07-01,Architect,90.00,flat-rate,Max 5x June
anthropic-api,2026-06-01,2026-07-01,,231.50,tokens,org API spend June
```

- [ ] **Step 2: Write the failing test** — `test_import_invoice.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 template/scripts/spend/tests/test_import_invoice.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'import_invoice'`.

- [ ] **Step 4: Implement** — `template/scripts/spend/import_invoice.py`:

```python
#!/usr/bin/env python3
"""Import invoice-level / flat-rate AI spend (Cursor, Copilot, Claude Max
seats, aggregated API bills) into the dashboard's spend table.

CSV columns: source,period_start,period_end,seat,cost_eur,granularity,notes
  - granularity: tokens | invoice | flat-rate (the honesty flag — the
    dashboard never mixes granularities without labelling them)
  - blank seat -> '(org)' (org-level / unattributable)
Re-importing the same file is a no-op (upsert on source+period_start+seat).

Usage:  import_invoice.py --csv invoices/2026-06.csv [--db dashboard/utilization.db]
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = {"anthropic-api", "cursor", "copilot", "claude-max", "other"}
GRANULARITIES = {"tokens", "invoice", "flat-rate"}


def rows_from_csv(fileobj):
    rows = []
    for i, rec in enumerate(csv.DictReader(fileobj), start=2):
        src = (rec.get("source") or "").strip()
        gran = (rec.get("granularity") or "").strip()
        if src not in SOURCES:
            raise ValueError(f"line {i}: unknown source '{src}' (want one of {sorted(SOURCES)})")
        if gran not in GRANULARITIES:
            raise ValueError(f"line {i}: unknown granularity '{gran}' (want one of {sorted(GRANULARITIES)})")
        try:
            start = date.fromisoformat((rec.get("period_start") or "").strip())
            end = date.fromisoformat((rec.get("period_end") or "").strip())
            cost = float(rec.get("cost_eur") or "")
        except ValueError as exc:
            raise ValueError(f"line {i}: {exc}") from exc
        if end <= start:
            raise ValueError(f"line {i}: period_end must be after period_start")
        rows.append({
            "source": src,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "seat": (rec.get("seat") or "").strip() or "(org)",
            "cost_eur": cost,
            "granularity": gran,
            "notes": (rec.get("notes") or "").strip() or None,
        })
    return rows


def upsert_spend(conn, rows):
    for row in rows:
        conn.execute(
            """INSERT INTO spend (source, period_start, period_end, seat,
                   cost_eur, granularity, notes)
               VALUES (:source, :period_start, :period_end, :seat,
                   :cost_eur, :granularity, :notes)
               ON CONFLICT(source, period_start, seat) DO UPDATE SET
                   period_end=excluded.period_end, cost_eur=excluded.cost_eur,
                   granularity=excluded.granularity, notes=excluded.notes""",
            row,
        )
    conn.commit()
    return len(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--db", default=str(HERE.parents[1] / "dashboard" / "utilization.db"))
    args = ap.parse_args(argv)

    sys.path.insert(0, str(HERE.parents[1] / "dashboard"))
    import db as dbmod  # noqa: E402

    with open(args.csv, encoding="utf-8") as f:
        rows = rows_from_csv(f)
    conn = dbmod.connect(args.db)
    try:
        n = upsert_spend(conn, rows)
    finally:
        conn.close()
    print(f"[import-invoice] upserted {n} spend rows from {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 template/scripts/spend/tests/test_import_invoice.py`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add template/scripts/spend
git commit -m "feat(spend): invoice/flat-rate CSV importer (idempotent upsert)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 6: import_api_usage.py — Anthropic Admin cost report → spend

**Files:**
- Create: `template/scripts/spend/import_api_usage.py`, `template/scripts/spend/tests/fixtures/cost_report.json`
- Test: `template/scripts/spend/tests/test_import_api_usage.py`

**Interfaces:**
- Consumes: `GET https://api.anthropic.com/v1/organizations/cost_report?starting_at=...&ending_at=...` with headers `x-api-key: $ANTHROPIC_ADMIN_KEY`, `anthropic-version: 2023-06-01` (Admin API key, `sk-ant-admin...`; paginated via `next_page`/`page`). **The response shape is defensive-parsed** — `rows_from_cost_report` raises `ValueError` listing the top-level keys it got when the shape is unrecognized, so a drifted API fails loudly, never silently undercounts. Verify field names against platform.claude.com Admin API docs on first live run.
- Produces: `rows_from_cost_report(payload: dict, eur_per_usd: float) -> list[dict]` (spend rows, `source='anthropic-api'`, `granularity='tokens'`, `seat='(org)'` — the org report has no seat dimension); `fetch_cost_report(starting_at, ending_at, api_key) -> list[dict]` (network, follows pagination); `upsert_spend` is **imported from `import_invoice`** (single writer).
- Env: `ANTHROPIC_ADMIN_KEY` (never in git, never in config.json).

- [ ] **Step 1: Create the fixture** `cost_report.json` (one page, two daily buckets; `amount` is a decimal-string USD amount):

```json
{
  "data": [
    {"starting_at": "2026-06-22T00:00:00Z", "ending_at": "2026-06-23T00:00:00Z",
     "results": [{"amount": "3.50", "currency": "USD"}, {"amount": "1.50", "currency": "USD"}]},
    {"starting_at": "2026-06-23T00:00:00Z", "ending_at": "2026-06-24T00:00:00Z",
     "results": [{"amount": "2.00", "currency": "USD"}]}
  ],
  "has_more": false,
  "next_page": null
}
```

- [ ] **Step 2: Write the failing test** — `test_import_api_usage.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 template/scripts/spend/tests/test_import_api_usage.py`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Implement** — `template/scripts/spend/import_api_usage.py`:

```python
#!/usr/bin/env python3
"""Import org-level Anthropic API spend from the Admin cost-report endpoint
into the dashboard's spend table (source='anthropic-api', granularity=
'tokens', seat='(org)' — the org report has no per-seat dimension).

Auth: ANTHROPIC_ADMIN_KEY env var (an Admin API key). Never stored in git.
Amounts are USD; converted to EUR via eur_per_usd in prices.json.
Defensive: an unrecognized response shape raises with the keys it saw —
loud failure, never a silent undercount.

Usage:  ANTHROPIC_ADMIN_KEY=sk-ant-admin... \
        import_api_usage.py --from 2026-06-01 --to 2026-07-01 [--db ...]
        import_api_usage.py --from-json fixtures/cost_report.json   # offline
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "https://api.anthropic.com/v1/organizations/cost_report"


def rows_from_cost_report(payload, eur_per_usd):
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        keys = sorted(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
        raise ValueError(f"unrecognized cost_report shape (got {keys}); "
                         "check the Admin API docs and update this parser")
    rows = []
    for bucket in payload["data"]:
        usd = 0.0
        for result in bucket.get("results", []):
            usd += float(result.get("amount", 0))
        rows.append({
            "source": "anthropic-api",
            "period_start": str(bucket["starting_at"])[:10],
            "period_end": str(bucket["ending_at"])[:10],
            "seat": "(org)",
            "cost_eur": usd * eur_per_usd,
            "granularity": "tokens",
            "notes": "admin cost_report",
        })
    return rows


def fetch_cost_report(starting_at, ending_at, api_key):
    """Fetch all pages. Network-facing; everything else stays pure."""
    pages, page = [], None
    while True:
        params = {"starting_at": f"{starting_at}T00:00:00Z",
                  "ending_at": f"{ending_at}T00:00:00Z"}
        if page:
            params["page"] = page
        req = urllib.request.Request(
            API + "?" + urllib.parse.urlencode(params),
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        pages.append(payload)
        page = payload.get("next_page")
        if not payload.get("has_more") or not page:
            return pages


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--from-json", help="parse a saved response instead of calling the API")
    ap.add_argument("--db", default=str(HERE.parents[1] / "dashboard" / "utilization.db"))
    args = ap.parse_args(argv)

    prices = json.loads((HERE / "prices.json").read_text(encoding="utf-8"))
    eur = prices.get("eur_per_usd", 1.0)

    if args.from_json:
        pages = [json.loads(Path(args.from_json).read_text(encoding="utf-8"))]
    else:
        if not (args.start and args.end):
            ap.error("--from and --to are required unless --from-json is given")
        key = os.environ.get("ANTHROPIC_ADMIN_KEY")
        if not key:
            print("[import-api-usage] ANTHROPIC_ADMIN_KEY not set", file=sys.stderr)
            return 2
        pages = fetch_cost_report(args.start, args.end, key)

    rows = [r for p in pages for r in rows_from_cost_report(p, eur)]

    sys.path.insert(0, str(HERE.parents[1] / "dashboard"))
    sys.path.insert(0, str(HERE))
    import db as dbmod  # noqa: E402
    from import_invoice import upsert_spend  # noqa: E402

    conn = dbmod.connect(args.db)
    try:
        n = upsert_spend(conn, rows)
    finally:
        conn.close()
    print(f"[import-api-usage] upserted {n} spend rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 template/scripts/spend/tests/test_import_api_usage.py`
Expected: PASS (3 tests). Offline smoke: `python3 template/scripts/spend/import_api_usage.py --from-json template/scripts/spend/tests/fixtures/cost_report.json --db /tmp/t.db` → `upserted 2 spend rows`.

- [ ] **Step 6: Commit**

```bash
git add template/scripts/spend
git commit -m "feat(spend): Anthropic Admin cost-report importer (env-only auth, defensive parse)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 7: import_tickets.py — JIRA ledger + actuals → tickets

**Files:**
- Create: `template/scripts/spend/import_tickets.py`, `template/scripts/spend/tests/fixtures/issues_sample.csv`, `.../actuals_sample.csv`
- Test: `template/scripts/spend/tests/test_import_tickets.py`

**Interfaces:**
- Consumes: the JIRA ledger CSV at `docs/product/jira/issues.csv` (canonical columns from the JIRA-ledger theme: `key, type, title, status, assignee, reporter, labels, sprint, epic, parent, priority, story_points, created, updated, resolution, url, description`); `config.json` (`points_to_days`, `day_rate_eur`, `closed_statuses`).
- Produces: `tickets_from_ledger(fileobj, cfg) -> list[dict]` (estimate = `story_points × points_to_days`, `None` when no points; `status` mapped to `closed` iff ledger status in `closed_statuses`, `closed_at` from `updated` when closed; `evidence_tier='pre-estimate'`; `day_rate_eur` from cfg); `apply_actuals(fileobj) -> list[dict]` from an actuals CSV `ticket,actual_human_days,evidence_tier` (tier optional); `upsert_tickets(conn, rows) -> int` — ledger rows never overwrite an existing non-NULL `actual_human_days`; actuals rows only update `actual_human_days`/`evidence_tier`.

- [ ] **Step 1: Create fixtures.** `issues_sample.csv`:

```csv
key,type,title,status,assignee,reporter,labels,sprint,epic,parent,priority,story_points,created,updated,resolution,url,description
PROJ-1,Story,Login form,Done,dev1,po1,,S1,,,High,3,2026-06-01,2026-06-20,Done,https://x/PROJ-1,desc
PROJ-2,Story,Data layer,In Progress,dev2,po1,,S1,,,High,5,2026-06-02,2026-06-25,,https://x/PROJ-2,desc
PROJ-3,Bug,Fix crash,Done,dev1,qa1,,S1,,,High,,2026-06-03,2026-06-21,Done,https://x/PROJ-3,desc
```

`actuals_sample.csv`:

```csv
ticket,actual_human_days,evidence_tier
PROJ-1,1.0,calibration
PROJ-3,0.05,
```

- [ ] **Step 2: Write the failing test** — `test_import_tickets.py`:

```python
#!/usr/bin/env python3
"""Unit tests for the JIRA-ledger → tickets importer."""
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 template/scripts/spend/tests/test_import_tickets.py`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Implement** — `template/scripts/spend/import_tickets.py`:

```python
#!/usr/bin/env python3
"""Fill the dashboard's tickets table (the ROI join point).

Two inputs, one writer:
  --ledger  docs/product/jira/issues.csv (the JIRA-ledger theme's CSV):
            estimate = story_points × points_to_days (config.json);
            status 'closed' iff the ledger status is in closed_statuses.
            Never overwrites recorded actuals.
  --actuals a small CSV `ticket,actual_human_days,evidence_tier` maintained
            by the EM (or exported from time tracking). Only touches
            actual_human_days / evidence_tier.

Usage:
  import_tickets.py --ledger docs/product/jira/issues.csv
  import_tickets.py --actuals actuals.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "config.json"


def _cfg():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def tickets_from_ledger(fileobj, cfg):
    closed = {s.lower() for s in cfg["closed_statuses"]}
    rows = []
    for rec in csv.DictReader(fileobj):
        key = (rec.get("key") or "").strip()
        if not key:
            continue
        points = (rec.get("story_points") or "").strip()
        estimate = float(points) * cfg["points_to_days"] if points else None
        is_closed = (rec.get("status") or "").strip().lower() in closed
        rows.append({
            "ticket": key,
            "estimate_human_days": estimate,
            "day_rate_eur": cfg["day_rate_eur"],
            "evidence_tier": "pre-estimate",
            "status": "closed" if is_closed else "open",
            "closed_at": (rec.get("updated") or "").strip() or None if is_closed else None,
            "_kind": "ledger",
        })
    return rows


def apply_actuals(fileobj):
    rows = []
    for i, rec in enumerate(csv.DictReader(fileobj), start=2):
        key = (rec.get("ticket") or "").strip()
        if not key:
            raise ValueError(f"line {i}: ticket is required")
        try:
            actual = float(rec.get("actual_human_days") or "")
        except ValueError as exc:
            raise ValueError(f"line {i}: bad actual_human_days") from exc
        rows.append({
            "ticket": key,
            "actual_human_days": actual,
            "evidence_tier": (rec.get("evidence_tier") or "").strip() or None,
            "_kind": "actuals",
        })
    return rows


def upsert_tickets(conn, rows):
    for row in rows:
        if row["_kind"] == "ledger":
            conn.execute(
                """INSERT INTO tickets (ticket, estimate_human_days,
                       day_rate_eur, evidence_tier, status, closed_at)
                   VALUES (:ticket, :estimate_human_days, :day_rate_eur,
                       :evidence_tier, :status, :closed_at)
                   ON CONFLICT(ticket) DO UPDATE SET
                       estimate_human_days=excluded.estimate_human_days,
                       day_rate_eur=excluded.day_rate_eur,
                       status=excluded.status, closed_at=excluded.closed_at""",
                row,
            )
        else:
            conn.execute(
                """INSERT INTO tickets (ticket, actual_human_days, evidence_tier)
                   VALUES (:ticket, :actual_human_days,
                           COALESCE(:evidence_tier, 'pre-estimate'))
                   ON CONFLICT(ticket) DO UPDATE SET
                       actual_human_days=excluded.actual_human_days,
                       evidence_tier=COALESCE(:evidence_tier, tickets.evidence_tier)""",
                row,
            )
    conn.commit()
    return len(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger")
    ap.add_argument("--actuals")
    ap.add_argument("--db", default=str(HERE.parents[1] / "dashboard" / "utilization.db"))
    args = ap.parse_args(argv)
    if not (args.ledger or args.actuals):
        ap.error("give --ledger and/or --actuals")

    sys.path.insert(0, str(HERE.parents[1] / "dashboard"))
    import db as dbmod  # noqa: E402

    conn = dbmod.connect(args.db)
    try:
        n = 0
        if args.ledger:
            with open(args.ledger, encoding="utf-8") as f:
                n += upsert_tickets(conn, tickets_from_ledger(f, _cfg()))
        if args.actuals:
            with open(args.actuals, encoding="utf-8") as f:
                n += upsert_tickets(conn, apply_actuals(f))
    finally:
        conn.close()
    print(f"[import-tickets] upserted {n} ticket rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 template/scripts/spend/tests/test_import_tickets.py`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add template/scripts/spend
git commit -m "feat(spend): tickets importer — JIRA ledger estimates + EM actuals

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 8: dashboard/roi.py — ROI logic + client report (stdlib)

**Files:**
- Create: `template/dashboard/roi.py`
- Test: `template/dashboard/tests/test_roi.py`

**Interfaces:**
- Consumes: `roi_view`, `sessions`, `spend` tables; `scripts/spend/prices.json` (`eur_per_usd`).
- Produces:
  - `ticket_rows(conn) -> list[dict]` — `roi_view` rows as dicts.
  - `amortized_spend_eur(conn, start_iso, end_iso) -> float` — pro-rata day overlap; idle flat-rate seats still amortize.
  - `period_rollup(conn, start_iso, end_iso, eur_per_usd) -> dict` — keys `ai_sessions_eur, ai_spend_eur, ai_total_eur`.
  - `roi_summary(conn, eur_per_usd) -> dict` — keys `roi` (blended float or `None`), `band` ((lo, hi) or `None`), `per_tier` (dict tier→roi), `coverage` ((used, closed)), `flagged` (list of tickets with absurd actuals). Excludes tickets without estimate or actual; per-ticket AI cost = session tokens only (design §3).
  - `render_client_report(summary, rollup, rows, period_label) -> str` — self-contained HTML with methodology footnote + coverage line.
- Tier constant: `TIER_ORDER = ["calibration", "pre-estimate", "velocity", "post-hoc"]`.

- [ ] **Step 1: Write the failing test** — `template/dashboard/tests/test_roi.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/dashboard/tests/test_roi.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'roi'`.

- [ ] **Step 3: Implement** — `template/dashboard/roi.py`:

```python
#!/usr/bin/env python3
"""ROI logic for the dashboard (token-roi design §3, §6). Stdlib only so CI
can test it without pandas; app.py wraps these for display.

Per-ticket AI cost = session tokens only. Invoice/flat-rate spend cannot
honestly be split per ticket, so it joins the ROI at period level
(period_rollup) — coarse money is counted exactly once, where it is honest.
"""
from __future__ import annotations

import html
from datetime import date

TIER_ORDER = ["calibration", "pre-estimate", "velocity", "post-hoc"]


def _d(value):
    return date.fromisoformat(str(value)[:10])


def ticket_rows(conn):
    cols = ["ticket", "estimate_human_days", "actual_human_days", "day_rate_eur",
            "evidence_tier", "closed_at", "ai_cost_usd", "human_cost_eur",
            "value_eur", "hde", "flagged_low_actual"]
    return [dict(zip(cols, row)) for row in conn.execute(
        f"SELECT {', '.join(cols)} FROM roi_view ORDER BY closed_at")]


def amortized_spend_eur(conn, start_iso, end_iso):
    lo, hi = _d(start_iso), _d(end_iso)
    total = 0.0
    for ps, pe, cost in conn.execute(
            "SELECT period_start, period_end, cost_eur FROM spend"):
        p0, p1 = _d(ps), _d(pe)
        days = (p1 - p0).days
        if days <= 0:
            continue
        overlap = (min(p1, hi) - max(p0, lo)).days
        if overlap > 0:
            total += cost * overlap / days
    return total


def period_rollup(conn, start_iso, end_iso, eur_per_usd):
    sessions_usd = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM sessions WHERE ts >= ? AND ts < ?",
        (start_iso, end_iso)).fetchone()[0]
    spend_eur = amortized_spend_eur(conn, start_iso, end_iso)
    sessions_eur = sessions_usd * eur_per_usd
    return {"ai_sessions_eur": sessions_eur, "ai_spend_eur": spend_eur,
            "ai_total_eur": sessions_eur + spend_eur}


def _roi(rows, eur_per_usd):
    value = sum(r["value_eur"] for r in rows)
    cost = sum(r["human_cost_eur"] + r["ai_cost_usd"] * eur_per_usd for r in rows)
    return value / cost if cost > 0 else None


def roi_summary(conn, eur_per_usd):
    rows = ticket_rows(conn)          # closed tickets only (the view filters)
    usable = [r for r in rows
              if r["estimate_human_days"] is not None
              and r["actual_human_days"] is not None
              and not r["flagged_low_actual"]]
    per_tier = {}
    for tier in TIER_ORDER:
        tier_roi = _roi([r for r in usable if r["evidence_tier"] == tier], eur_per_usd)
        if tier_roi is not None:
            per_tier[tier] = tier_roi
    band = (min(per_tier.values()), max(per_tier.values())) if per_tier else None
    return {
        "roi": _roi(usable, eur_per_usd),
        "band": band,
        "per_tier": per_tier,
        "coverage": (len(usable), len(rows)),
        "flagged": sorted(r["ticket"] for r in rows if r["flagged_low_actual"]),
    }


def render_client_report(summary, rollup, rows, period_label):
    used, closed = summary["coverage"]
    roi_txt = f"{summary['roi']:.2f}" if summary["roi"] is not None else "n/a"
    band_txt = (f"{summary['band'][0]:.2f} – {summary['band'][1]:.2f}"
                if summary["band"] else "n/a")
    tier_rows = "".join(
        f"<tr><td>{html.escape(t)}</td><td>{v:.2f}</td></tr>"
        for t, v in summary["per_tier"].items())
    ticket_trs = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(r[c] if r[c] is not None else '—'))}</td>"
                         for c in ("ticket", "estimate_human_days",
                                   "actual_human_days", "ai_cost_usd", "hde",
                                   "evidence_tier")) + "</tr>"
        for r in rows)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>AI ROI report — {html.escape(period_label)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:52rem;margin:2rem auto;padding:0 1rem}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:.35rem .6rem;text-align:left}}
h1{{font-size:1.4rem}}.kpi{{font-size:2rem;font-weight:700}}.note{{color:#555;font-size:.85rem}}</style>
</head><body>
<h1>AI utilization &amp; ROI — {html.escape(period_label)}</h1>
<p class="kpi">ROI {roi_txt}</p>
<p>Evidence-weighted band: <strong>{band_txt}</strong> ·
   ROI computed over {used} of {closed} closed tickets.</p>
<p>AI spend this period: €{rollup['ai_total_eur']:.2f}
   (sessions €{rollup['ai_sessions_eur']:.2f} + subscriptions/invoices
   €{rollup['ai_spend_eur']:.2f}, flat-rate amortized pro-rata).</p>
<h2>ROI by evidence tier</h2><table><tr><th>Tier</th><th>ROI</th></tr>{tier_rows}</table>
<h2>Per-ticket detail</h2>
<table><tr><th>Ticket</th><th>Estimate (days)</th><th>Actual (days)</th>
<th>AI cost (USD)</th><th>HDE</th><th>Evidence</th></tr>{ticket_trs}</table>
<p class="note"><strong>Methodology.</strong> Value = pre-work estimate ×
day rate; cost = actual human-days × day rate + AI spend. Human-day-equivalent
(HDE) = estimate ÷ actual. Evidence tiers, strongest first: calibration A/B,
pre-work estimate, historical velocity, post-hoc judgment. Tickets without an
estimate or actual are excluded from the ratio but counted in coverage;
per-ticket AI cost covers session tokens only — invoice/flat-rate spend is
amortized at period level. Flagged tickets (actual &lt; 0.1 day):
{html.escape(', '.join(summary['flagged']) or 'none')}.</p>
</body></html>"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/dashboard/tests/test_roi.py`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add template/dashboard/roi.py template/dashboard/tests/test_roi.py
git commit -m "feat(dashboard): stdlib ROI logic — amortization, evidence band, client report

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 9: dashboard tabs — Waste signals + ROI

**Files:**
- Modify: `template/dashboard/app.py`

**Interfaces:**
- Consumes: `roi.py` (Task 8), `load()` helper (works unchanged — pandas ignores `parse_dates` columns that are absent), `dbmod.connect()`.
- Produces: 4 tabs: `["Utilization", "Commit attribution", "Waste signals", "ROI"]`.

- [ ] **Step 1: Implement.** In `app.py`, add imports near the top (after `import db as dbmod`):

```python
import json

import roi as roimod

_PRICES = Path(__file__).resolve().parents[1] / "scripts" / "spend" / "prices.json"
EUR_PER_USD = (json.loads(_PRICES.read_text(encoding="utf-8")).get("eur_per_usd", 1.0)
               if _PRICES.exists() else 1.0)
```

Add the two tab functions (after `attribution_tab`):

```python
def waste_tab(sessions: pd.DataFrame, spend: pd.DataFrame) -> None:
    """Technique-pack validation (token-economy.md): each chart names the
    technique it validates; a technique with no effect after two sprints is a
    deletion candidate at retro."""
    if sessions.empty:
        st.info("No sessions yet — scripts/session/collect-usage.sh writes real rows on SessionEnd.")
        return
    view = _date_filter(sessions, "waste_dates")
    if view.empty:
        st.warning("No sessions in range."); return
    view = view.copy()
    view["cache_read_tokens"] = view.get("cache_read_tokens", 0).fillna(0)
    total_tokens = (view["tokens_in"] + view["tokens_out"]).sum() or 1
    accepted = int((view["outcome"] == "accepted").sum())
    rework_tokens = (view.loc[view["outcome"].isin(["reworked", "rejected"]),
                              ["tokens_in", "tokens_out"]].sum().sum())
    cache_denom = view["cache_read_tokens"].sum() + view["tokens_in"].sum() or 1
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cost / accepted outcome",
              f"${view['cost_usd'].sum() / accepted:.2f}" if accepted else "—",
              help="Headline: total AI $ ÷ accepted sessions. Should fall over time.")
    c2.metric("Rework burn", f"{rework_tokens / total_tokens:.0%}",
              help="Tokens spent in reworked/rejected sessions — the #1 waste lever (technique 5).")
    c3.metric("Cache-hit ratio", f"{view['cache_read_tokens'].sum() / cache_denom:.0%}",
              help="cache_read ÷ (cache_read + fresh input) — technique 2, prompt-cache hygiene.")
    c4.metric("Unattributed", f"{view['ticket'].isna().mean():.0%}",
              help="Sessions with no ticket. Visible, never dropped.")
    left, right = st.columns(2)
    with left:
        st.subheader("Cost by model — technique 1 (routing)")
        st.bar_chart(view.groupby(view["model"].fillna("unknown"))["cost_usd"].sum())
        st.subheader("Tokens per session — technique 3 (context hygiene)")
        st.bar_chart((view["tokens_in"] + view["tokens_out"]).reset_index(drop=True))
    with right:
        st.subheader("Cost: grounded vs ungrounded — technique 4")
        st.bar_chart(view.groupby(view["grounded"].map({0: "ungrounded", 1: "grounded"}))["cost_usd"].sum())
        st.subheader("Cache-hit ratio by seat — technique 2")
        ratios = view.groupby("seat").apply(
            lambda g: g["cache_read_tokens"].sum()
            / max(1, g["cache_read_tokens"].sum() + g["tokens_in"].sum()))
        st.bar_chart(ratios)
    unpriced = view["notes"].fillna("").str.contains("unpriced models")
    if unpriced.any():
        st.warning(f"{int(unpriced.sum())} session(s) contain unpriced models "
                   "(cost recorded as 0) — update scripts/spend/prices.json.")
    if not spend.empty:
        st.subheader("Non-session spend (granularity is the honesty flag)")
        st.dataframe(spend, use_container_width=True, hide_index=True)


def roi_tab() -> None:
    conn = dbmod.connect()
    try:
        summary = roimod.roi_summary(conn, EUR_PER_USD)
        rows = roimod.ticket_rows(conn)
        col1, col2 = st.columns(2)
        start = col1.date_input("Period start", key="roi_start",
                                value=pd.Timestamp.today().replace(day=1))
        end = col2.date_input("Period end", key="roi_end",
                              value=pd.Timestamp.today())
        rollup = roimod.period_rollup(conn, str(start), str(end), EUR_PER_USD)
    finally:
        conn.close()
    used, closed = summary["coverage"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ROI", f"{summary['roi']:.2f}" if summary["roi"] is not None else "—",
              help="Value delivered ÷ (human cost + AI cost). 1.4 ⇒ 1 dev + AI ≈ 1.4 devs.")
    c2.metric("Evidence band",
              f"{summary['band'][0]:.2f}–{summary['band'][1]:.2f}" if summary["band"] else "—",
              help="Range across evidence tiers: calibration > pre-estimate > velocity > post-hoc.")
    c3.metric("Coverage", f"{used} / {closed}",
              help="Closed tickets included in the ratio — never a cherry-picked subset.")
    c4.metric("AI € this period", f"€{rollup['ai_total_eur']:.0f}",
              help="Session tokens + amortized subscriptions/invoices, counted once.")
    if summary["flagged"]:
        st.warning("Flagged (actual < 0.1 day, review before trusting): "
                   + ", ".join(summary["flagged"]))
    st.subheader("Per-ticket detail")
    df = pd.DataFrame(rows)
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.subheader("HDE trend (by close month)")
        df2 = df.dropna(subset=["hde", "closed_at"]).copy()
        if not df2.empty:
            df2["month"] = df2["closed_at"].str[:7]
            st.line_chart(df2.groupby("month")["hde"].mean())
    else:
        st.info("No closed tickets yet — run scripts/spend/import_tickets.py.")
    label = f"{start} → {end}"
    st.download_button(
        "Download client report (HTML)",
        data=roimod.render_client_report(summary, rollup, rows, label),
        file_name=f"ai-roi-report-{start}.html", mime="text/html",
    )
    st.caption("Methodology: HDE = estimate ÷ actual; evidence tiers weight the band; "
               "per-ticket AI cost is session tokens only, coarse spend joins at period level.")
```

Update `main()`:

```python
    sessions = load("sessions")
    commits = load("commits")
    spend = load("spend")
    tab1, tab2, tab3, tab4 = st.tabs(
        ["Utilization", "Commit attribution", "Waste signals", "ROI"])
    with tab1:
        utilization_tab(sessions)
    with tab2:
        attribution_tab(commits, sessions)
    with tab3:
        waste_tab(sessions, spend)
    with tab4:
        roi_tab()
```

- [ ] **Step 2: Compile-check (streamlit isn't a CI dep — a syntax/undefined-name gate is what we can automate):**

Run: `python3 -m py_compile template/dashboard/app.py && echo OK`
Expected: `OK`

- [ ] **Step 3: Manual verify (developer machine with the dashboard deps):**

Run: `pip install -r template/dashboard/requirements.txt && (cd template && streamlit run dashboard/app.py)`
Expected: four tabs render from seed data; Waste signals shows KPIs; ROI shows a ratio, band, coverage `3 / 4` (seeds), and the download button produces an HTML file that opens in a browser.

- [ ] **Step 4: Commit**

```bash
git add template/dashboard/app.py
git commit -m "feat(dashboard): Waste-signals + ROI tabs with client HTML export

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 10: token-economy rule + seat-profile model routing

**Files:**
- Create: `template/.claude/rules/token-economy.md`
- Modify: `template/scripts/session/seat-profiles.json`

**Interfaces:**
- Produces: seat profiles gain two optional fields per seat: `default_model` (string) and `escalation_hint` (string). `validate-seat-profiles.py` checks required fields only, so additions pass; verify in Step 3.

- [ ] **Step 1: Write the rule** — `template/.claude/rules/token-economy.md`:

```markdown
# Token economy

Enforced defaults for AI token spend (design: docs/roadmap token-roi theme).
Each rule has a metric proxy on the dashboard's **Waste signals** tab; a rule
that shows no measurable effect after two sprints is a deletion candidate at
retro (anti-bloat). Techniques 1 (model routing) and 5 (plan-before-code)
live in the seat profiles and playbooks; this file holds the agent-behavior
rules.

## 2 — Prompt-cache hygiene
Keep the briefs byte-stable within a sprint: no mid-session edits to
`AGENTS.md`, `CLAUDE.md`, or rule files. Cache reads cost ~10× less than
fresh input; every brief edit invalidates the prefix cache for everyone.
Batch brief changes and land them between sprints. CI warns when AGENTS.md
churns (scripts/check-brief-churn.py).
*Proxy: cache-hit ratio per seat.*

## 3 — Context hygiene
One ticket per session; `/clear` between tickets. Read the files you need
with targeted ranges instead of dumping whole files or directories into
context. Don't re-read files you already read this session.
*Proxy: tokens-per-session distribution (long tail flagged).*

## 6 — Subagent scoping
Exploration (broad searches, many-file reads, log scans) goes to a scoped
subagent whose raw output never enters the main context — bring back the
conclusion, not the file dumps. Keep the main session for decisions and
edits.
*Proxy: tokens-in per accepted outcome.*

## 7 — Batch / off-peak
Non-interactive jobs (bulk doc generation, triage sweeps, dataset
processing) go through the Batch API at 50% of standard price — see
scripts/spend/README.md.
*Proxy: share of API spend at batch rate.*

## Grounding (pointer)
Answer from the knowledge layer (pillar 5) instead of pasting documents into
the prompt — see `.claude/rules/knowledge-sources.md`.
*Proxy: grounded vs ungrounded cost.*
```

- [ ] **Step 2: Add routing fields to `seat-profiles.json`** — add to each seat object (after `"playbook"`):

| seat | `default_model` | `escalation_hint` |
|---|---|---|
| Architect | `opus` | `Design, ADRs and reviews stay on opus; use haiku for mechanical doc formatting.` |
| EM | `sonnet` | `Escalate to opus for delivery-risk analysis; haiku for report collation.` |
| Product | `sonnet` | `Escalate to opus for roadmap/strategy work; haiku for backlog housekeeping.` |
| Developer | `sonnet` | `Escalate to opus for cross-cutting design or gnarly debugging; haiku for boilerplate, renames and log-scraping.` |
| QA | `sonnet` | `Escalate to opus for test-strategy design; haiku for test-data generation.` |

E.g. the Developer entry becomes:

```json
    { "id": "Developer", "git_comfort_default": "git-native", "playbook": "playbook-dev",
      "default_model": "sonnet",
      "escalation_hint": "Escalate to opus for cross-cutting design or gnarly debugging; haiku for boilerplate, renames and log-scraping.",
      "connectors": ["issue-tracker", "knowledge", "context7"],
      "first_task": "Open a feature branch for your first change." },
```

- [ ] **Step 3: Verify validators still pass**

Run: `cd template && python3 scripts/validate-seat-profiles.py && python3 scripts/validate-frontmatter.py; cd ..`
Expected: both exit 0 (the seat validator checks required fields; extra fields are allowed. If it errors on the new keys, extend its `REQUIRED_FIELDS`-adjacent logic to ignore unknown fields — it already should).

- [ ] **Step 4: Commit**

```bash
git add template/.claude/rules/token-economy.md template/scripts/session/seat-profiles.json
git commit -m "feat(rules): token-economy pack + per-seat model routing defaults

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 11: brief-churn check + CI wiring

**Files:**
- Create: `template/scripts/check-brief-churn.py`
- Test: `template/scripts/tests/test_check_brief_churn.py`
- Modify: `template/.github/workflows/ai-governance.yml`, `.gitlab-ci.yml` (repo root)

**Interfaces:**
- Produces: `churn_count(path, days, cwd) -> int` (commits touching `path` in the last `days` days, via `git log --since`); CLI `main(argv) -> int` — prints the count, warns above `--warn` (default 3), exits 1 above `--max` (default 10). Defaults tuned so normal setup work passes and only cache-hostile churn fails.

- [ ] **Step 1: Write the failing test** — `template/scripts/tests/test_check_brief_churn.py`:

```python
#!/usr/bin/env python3
"""Unit tests for the AGENTS.md churn check (token-economy technique 2)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import importlib
churn = importlib.import_module("check-brief-churn")


def make_repo(tmp, commits):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp, check=True, capture_output=True,
                       env={"PATH": "/usr/bin:/bin:/usr/local/bin",
                            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                            "HOME": tmp})
    git("init", "-q")
    for i in range(commits):
        Path(tmp, "AGENTS.md").write_text(f"v{i}\n", encoding="utf-8")
        git("add", "AGENTS.md")
        git("commit", "-q", "-m", f"edit {i}")


class TestChurn(unittest.TestCase):
    def test_counts_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp, 4)
            self.assertEqual(churn.churn_count("AGENTS.md", days=14, cwd=tmp), 4)

    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp, 4)
            self.assertEqual(churn.main(["--days", "14", "--warn", "3",
                                         "--max", "10", "--cwd", tmp]), 0)   # warn only
            self.assertEqual(churn.main(["--days", "14", "--warn", "1",
                                         "--max", "2", "--cwd", tmp]), 1)    # over max


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/tests/test_check_brief_churn.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'check-brief-churn'`.

- [ ] **Step 3: Implement** — `template/scripts/check-brief-churn.py`:

```python
#!/usr/bin/env python3
"""Flag cache-hostile churn on the canonical brief (token-economy rule 2).

Every AGENTS.md edit invalidates the prompt-cache prefix for every operator.
This gate counts commits touching the brief in a recent window: prints the
count, warns above --warn, fails (exit 1) above --max. Stdlib only.

Usage:  check-brief-churn.py [--path AGENTS.md] [--days 14] [--warn 3] [--max 10]
"""
from __future__ import annotations

import argparse
import subprocess


def churn_count(path="AGENTS.md", days=14, cwd=None):
    out = subprocess.run(
        ["git", "log", f"--since={days} days ago", "--oneline", "--", path],
        capture_output=True, text=True, check=True, cwd=cwd,
    ).stdout
    return len([line for line in out.splitlines() if line.strip()])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", default="AGENTS.md")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--warn", type=int, default=3)
    ap.add_argument("--max", type=int, default=10)
    ap.add_argument("--cwd", default=None, help="repo dir (default: cwd)")
    args = ap.parse_args(argv)

    n = churn_count(args.path, args.days, args.cwd)
    print(f"[brief-churn] {n} commit(s) touched {args.path} in the last {args.days} days")
    if n > args.max:
        print(f"[brief-churn] FAIL: > --max {args.max} — cache-hostile brief churn; "
              "batch brief edits between sprints (rules/token-economy.md §2)")
        return 1
    if n > args.warn:
        print(f"[brief-churn] WARN: > --warn {args.warn} — keep the brief byte-stable "
              "within a sprint (rules/token-economy.md §2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/scripts/tests/test_check_brief_churn.py`
Expected: PASS (2 tests).

- [ ] **Step 5: Wire CI.** In `template/.github/workflows/ai-governance.yml`, after the "Run knowledge-graph unit tests" step, add:

```yaml
      - name: Run consumption/ROI unit tests (token-roi theme)
        run: |
          python3 dashboard/tests/test_schema.py
          python3 dashboard/tests/test_roi.py
          python3 scripts/spend/tests/test_parse_transcript.py
          python3 scripts/spend/tests/test_collect_usage.py
          python3 scripts/spend/tests/test_import_invoice.py
          python3 scripts/spend/tests/test_import_api_usage.py
          python3 scripts/spend/tests/test_import_tickets.py
          python3 scripts/tests/test_check_brief_churn.py

      - name: Brief-churn gate (token-economy rule 2)
        run: python3 scripts/check-brief-churn.py --path AGENTS.md
```

Note: `actions/checkout@v4` is shallow by default (`fetch-depth: 1`), which under-counts `git log` — add `with: fetch-depth: 0` to the existing checkout step.

In `.gitlab-ci.yml` (repo root), inside the `ai-governance` job's `script:` list, after the `test_export_jira.py` line, add:

```yaml
  - echo "Running consumption/ROI unit tests (token-roi theme)…"
  - python3 template/dashboard/tests/test_schema.py
  - python3 template/dashboard/tests/test_roi.py
  - python3 template/scripts/spend/tests/test_parse_transcript.py
  - python3 template/scripts/spend/tests/test_collect_usage.py
  - python3 template/scripts/spend/tests/test_import_invoice.py
  - python3 template/scripts/spend/tests/test_import_api_usage.py
  - python3 template/scripts/spend/tests/test_import_tickets.py
  - python3 template/scripts/tests/test_check_brief_churn.py
  - echo "Brief-churn gate (token-economy rule 2)…"
  - python3 template/scripts/check-brief-churn.py --path template/AGENTS.md
  - python3 -m py_compile template/dashboard/app.py
```

(GitLab clones with full history by default via `GIT_DEPTH`; the kit's CI sets none, but if the job ever runs shallow, `git log --since` degrades to a lower count — a warn-side error, acceptable.)

- [ ] **Step 6: Run everything CI will run, locally**

Run:
```bash
cd template && for t in dashboard/tests/test_schema.py dashboard/tests/test_roi.py \
  scripts/spend/tests/test_parse_transcript.py scripts/spend/tests/test_collect_usage.py \
  scripts/spend/tests/test_import_invoice.py scripts/spend/tests/test_import_api_usage.py \
  scripts/spend/tests/test_import_tickets.py scripts/tests/test_check_brief_churn.py; do \
  python3 "$t" || break; done; cd ..
python3 template/scripts/check-brief-churn.py --path template/AGENTS.md
```
Expected: all PASS; churn gate prints a count and exits 0.

- [ ] **Step 7: Commit**

```bash
git add template/scripts/check-brief-churn.py template/scripts/tests/test_check_brief_churn.py template/.github/workflows/ai-governance.yml .gitlab-ci.yml
git commit -m "ci: consumption/ROI test suite + AGENTS.md brief-churn gate

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 12: docs + final verification

**Files:**
- Create: `template/scripts/spend/README.md`
- Modify: `template/dashboard/README.md`, `template/FOLDER-INDEX.md`

- [ ] **Step 1: Write `template/scripts/spend/README.md`:**

```markdown
# scripts/spend — AI consumption collectors

Feed the dashboard (`dashboard/utilization.db`) with real money data.
All scripts are stdlib-only and idempotent — re-running is a no-op.

| Script | Source | Writes | Granularity |
|---|---|---|---|
| `../session/collect-usage.sh` | Claude Code transcript, on SessionEnd (automatic) | `sessions` | per-session tokens |
| `import_api_usage.py` | Anthropic Admin cost report (`ANTHROPIC_ADMIN_KEY` env) | `spend` | tokens (org-level) |
| `import_invoice.py` | Cursor / Copilot / Claude Max invoices (CSV) | `spend` | invoice / flat-rate |
| `import_tickets.py` | JIRA ledger (`docs/product/jira/issues.csv`) + EM actuals CSV | `tickets` | — |

Monthly ritual (before the retro):

    python3 scripts/spend/import_api_usage.py --from 2026-06-01 --to 2026-07-01
    python3 scripts/spend/import_invoice.py --csv invoices/2026-06.csv
    python3 scripts/spend/import_tickets.py --ledger docs/product/jira/issues.csv --actuals actuals/2026-06.csv

- `prices.json` — model → USD/Mtok (+ `eur_per_usd`). A maintained config:
  refresh from the pricing docs when models change. Unknown models cost 0 and
  are flagged on the Waste tab — never a guessed price.
- `config.json` — `points_to_days`, `day_rate_eur`, `working_days_per_month`,
  `closed_statuses`.
- Secrets are env-only (`ANTHROPIC_ADMIN_KEY`); nothing secret in git.
- **Batch discount (token-economy rule 7):** non-interactive jobs through the
  Batch API cost 50% of standard — spend rows for batch work land at that
  rate automatically since they come from the cost report.
```

- [ ] **Step 2: Update `template/dashboard/README.md`.** Replace the "What it shows" section's tab list with four tabs (add the two below to the existing bullets) and extend "Feeding it real data":

```markdown
- **Waste signals** — the token-economy pack, validated: cost per accepted
  outcome, rework burn, cache-hit ratio, cost by model, grounded vs
  ungrounded, unattributed share. Read top-to-bottom at retro: "is the pack
  working?" (`.claude/rules/token-economy.md`).
- **ROI** — human-day-equivalent ROI over closed tickets with an
  evidence-tier band and a coverage indicator, plus a client-report HTML
  export. Per-ticket AI cost is session tokens only; invoice/flat-rate spend
  joins at period level (counted exactly once).
```

and under *Feeding it real data*:

```markdown
- **Sessions** — automatic: `scripts/session/collect-usage.sh` runs on
  SessionEnd and prices the transcript (`scripts/spend/parse_transcript.py`).
  Set the outcome (accepted/reworked/rejected) in your wrap-up ritual.
- **Spend & tickets** — run the importers in `scripts/spend/` (see its
  README) monthly, before the retro.
```

- [ ] **Step 3: Update `template/FOLDER-INDEX.md`** — in the `scripts/` block add a line after `│   ├── session/ …`:

```
│   ├── spend/                      # AI consumption collectors + ROI inputs (prices, importers)
```

and in the `dashboard/` block add after `│   ├── schema.sql`:

```
    ├── roi.py                      # ROI logic (HDE, evidence band, client report)
```

- [ ] **Step 4: Full local verification sweep**

Run:
```bash
cd template
python3 scripts/validate-skills.py
python3 scripts/validate-frontmatter.py
python3 scripts/validate-moments.py
python3 scripts/validate-seat-profiles.py
for t in dashboard/tests/test_schema.py dashboard/tests/test_roi.py \
  scripts/spend/tests/test_parse_transcript.py scripts/spend/tests/test_collect_usage.py \
  scripts/spend/tests/test_import_invoice.py scripts/spend/tests/test_import_api_usage.py \
  scripts/spend/tests/test_import_tickets.py scripts/tests/test_check_brief_churn.py; do
  echo "== $t"; python3 "$t" || exit 1
done
python3 -m py_compile dashboard/app.py
python3 scripts/knowledge/ingest.py --build
cd ..
```
Expected: every validator/test passes; the knowledge build still succeeds (proves no regression in shared scripts).

- [ ] **Step 5: End-to-end hook smoke** (proves the real wiring, not just units):

```bash
cd template
echo '{"session_id":"smoke-1","transcript_path":"scripts/spend/tests/fixtures/transcript_ok.jsonl"}' \
  | SDLC_USAGE_DB=/tmp/smoke.db bash scripts/session/collect-usage.sh
python3 -c "import sqlite3; print(sqlite3.connect('/tmp/smoke.db').execute(
  \"SELECT session_id, tokens_in, cost_usd FROM sessions WHERE session_id='smoke-1'\").fetchone())"
cd ..
```
Expected: prints `('smoke-1', 1700, <cost>)` with cost > 0.

- [ ] **Step 6: Commit and wrap up**

```bash
git add template/scripts/spend/README.md template/dashboard/README.md template/FOLDER-INDEX.md
git commit -m "docs: spend collectors README, dashboard tabs, folder index

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Then follow the project's merge flow (superpowers:finishing-a-development-branch): merge `feat/token-roi` into local `main` as with previous themes.
