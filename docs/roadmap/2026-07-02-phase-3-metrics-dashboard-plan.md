# Phase 3 — Metrics Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add commit-attribution metrics (AI / mixed / human by LOC) to the dashboard — a `commits` table, a shared `db.py`, a stdlib collector that parses git-ai notes with a `Co-Authored-By` trailer fallback, and a dashboard tab paired with the existing utilization quality metrics.

**Architecture:** Split the SQLite schema into idempotent DDL (`schema.sql`) + first-run seeds (`seed.sql`); a shared `dashboard/db.py` (`connect`/`ensure_schema`); a `collect_commits.py` collector reading `refs/notes/ai` via plain `git notes` (no git-ai binary needed) with a trailer fallback; and a two-tab `app.py`. Plus docs: git-ai adoption in `attribution.md` + an optional onboarding step.

**Tech Stack:** Python 3.12 (stdlib: sqlite3, subprocess, json, re, argparse, unittest for the new code; Streamlit + pandas for `app.py` only), SQLite, Markdown.

## Global Constraints

- All files under `template/` (dashboard lives at `template/dashboard/`).
- The collector and `db.py` use the **Python standard library only**. `app.py` may use streamlit/pandas (already in `requirements.txt`).
- `schema.sql` is **idempotent DDL only** (`CREATE TABLE/INDEX IF NOT EXISTS`); all seed `INSERT`s live in `seed.sql` and run only on first DB creation.
- The git-ai note format is `authorship/3.0.0`: an attestation block (`<file>` then `  <key> <line-ranges>`), a line that is exactly `---`, then a JSON metadata object. Keys `s_…`/bare-hex ⇒ AI; `h_…` ⇒ human. Read notes with `git notes --ref=ai show <sha>`.
- Commit classes: `human` | `ai` | `mixed` | `ai-assisted`. `source` is `git-ai` | `trailer`.
- `commits` upserts by `sha` (`INSERT OR REPLACE`) — the collector is idempotent.
- `CLAUDE.md` stays a pure pointer. Match kit house style.
- Every commit message ends with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

**Created:**
- `template/dashboard/seed.sql` — first-run synthetic rows.
- `template/dashboard/db.py` — shared connect/ensure_schema.
- `template/dashboard/collect_commits.py` — attribution collector.
- `template/dashboard/tests/test_db.py`, `template/dashboard/tests/test_collect_commits.py`.

**Modified:**
- `template/dashboard/schema.sql` — DDL-only + new `commits` table (seeds moved out).
- `template/dashboard/app.py` — use `db.connect`; add the Commit-attribution tab.
- `template/dashboard/README.md` — commit-attribution + collector usage.
- `template/docs/ai-context/attribution.md` — git-ai primary + trailer fallback.
- `template/ONBOARDING.md` — optional git-ai install step (Phase A).
- `template/AGENTS.md` — §4.5 wording tweak.

---

## Task 1: Schema restructure (`schema.sql` DDL-only + `seed.sql`)

**Files:**
- Modify: `template/dashboard/schema.sql`
- Create: `template/dashboard/seed.sql`

- [ ] **Step 1: Rewrite `schema.sql` as idempotent DDL (sessions + commits)**

Overwrite `template/dashboard/schema.sql`:

```sql
-- AI-utilization + commit-attribution dashboard schema (board pillar 4/7).
-- Idempotent DDL ONLY — first-run seeds live in seed.sql. SQLite by default;
-- the columns map cleanly to Postgres if you outgrow it.

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,                      -- ISO 8601 timestamp
    seat        TEXT    NOT NULL,                      -- Architect | EM | Product | Developer | QA
    tool        TEXT    NOT NULL DEFAULT 'claude',
    task        TEXT,
    ticket      TEXT,
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    cost_usd    REAL    NOT NULL DEFAULT 0,
    outcome     TEXT    NOT NULL DEFAULT 'unknown',    -- accepted | reworked | rejected | unknown
    grounded    INTEGER NOT NULL DEFAULT 0,
    notes       TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_ts   ON sessions(ts);
CREATE INDEX IF NOT EXISTS idx_sessions_seat ON sessions(seat);

-- Commit attribution (Phase 3): one row per commit, AI/mixed/human by LOC.
CREATE TABLE IF NOT EXISTS commits (
    sha           TEXT PRIMARY KEY,
    ts            TEXT NOT NULL,                        -- author date, ISO 8601
    author_name   TEXT,
    author_email  TEXT,
    seat          TEXT,                                 -- best-effort; often NULL
    klass         TEXT NOT NULL DEFAULT 'human',        -- human | ai | mixed | ai-assisted
    source        TEXT NOT NULL DEFAULT 'trailer',      -- git-ai | trailer
    ai_lines      INTEGER NOT NULL DEFAULT 0,
    human_lines   INTEGER NOT NULL DEFAULT 0,
    insertions    INTEGER NOT NULL DEFAULT 0,
    deletions     INTEGER NOT NULL DEFAULT 0,
    files_changed INTEGER NOT NULL DEFAULT 0,
    tool          TEXT,                                 -- claude | cursor | copilot | ...
    subject       TEXT,
    ticket        TEXT
);
CREATE INDEX IF NOT EXISTS idx_commits_ts    ON commits(ts);
CREATE INDEX IF NOT EXISTS idx_commits_klass ON commits(klass);
```

- [ ] **Step 2: Create `seed.sql` (first-run synthetic rows)**

Create `template/dashboard/seed.sql`:

```sql
-- First-run synthetic rows so the dashboard renders immediately. Safe to delete;
-- real data comes from your harness (sessions) and collect_commits.py (commits).

INSERT INTO sessions (ts, seat, tool, task, ticket, tokens_in, tokens_out, cost_usd, outcome, grounded) VALUES
  ('2026-06-22T09:10:00', 'Developer', 'claude', 'implement login form',   '<TICKET>-101', 18000, 4200, 0.21, 'accepted', 1),
  ('2026-06-22T11:30:00', 'QA',        'claude', 'derive tests from AC',    '<TICKET>-101',  9000, 2600, 0.12, 'accepted', 1),
  ('2026-06-23T14:05:00', 'Product',   'claude', 'slice epic into stories', '<TICKET>-090', 12000, 5100, 0.18, 'reworked', 0),
  ('2026-06-24T10:00:00', 'Architect', 'claude', 'draft ADR-0001',          '<TICKET>-077', 22000, 6300, 0.31, 'accepted', 1),
  ('2026-06-24T16:40:00', 'Developer', 'claude', 'refactor data layer',     '<TICKET>-112', 27000, 8100, 0.39, 'rejected', 0),
  ('2026-06-25T09:20:00', 'EM',        'claude', 'tune CI governance gate',  '<TICKET>-006',  7000, 1900, 0.09, 'accepted', 1);

INSERT INTO commits (sha, ts, author_name, author_email, seat, klass, source, ai_lines, human_lines, insertions, deletions, files_changed, tool, subject, ticket) VALUES
  ('seed0001', '2026-06-22T09:12:00', 'Dev One', 'dev1@example.com', 'Developer', 'ai',    'git-ai',  180, 10, 190,  4, 3, 'claude', 'implement login form',        '<TICKET>-101'),
  ('seed0002', '2026-06-23T14:20:00', 'PO One',  'po1@example.com',  'Product',   'human', 'trailer',   0, 40,  40,  2, 1, NULL,     'refine acceptance criteria',  '<TICKET>-090'),
  ('seed0003', '2026-06-24T16:50:00', 'Dev Two', 'dev2@example.com', 'Developer', 'mixed', 'git-ai',  120, 60, 180, 30, 5, 'claude', 'refactor data layer',         '<TICKET>-112');
```

- [ ] **Step 3: Verify both apply and schema.sql is idempotent**

Run:
```bash
python3 - <<'PY'
import sqlite3, tempfile, pathlib
d = pathlib.Path("template/dashboard")
con = sqlite3.connect(":memory:")
con.executescript((d/"schema.sql").read_text())
con.executescript((d/"schema.sql").read_text())  # idempotent: no error
con.executescript((d/"seed.sql").read_text())
t = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
assert {"sessions","commits"} <= t, t
assert con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 6
assert con.execute("SELECT COUNT(*) FROM commits").fetchone()[0] == 3
print("schema+seed ok: tables", sorted(t))
PY
```
Expected: `schema+seed ok: tables ['commits', 'sessions']` (idempotent re-apply raised nothing).

- [ ] **Step 4: Commit**

```bash
git add template/dashboard/schema.sql template/dashboard/seed.sql
git commit -m "feat: split dashboard schema (DDL) from seeds; add commits table

schema.sql is now idempotent DDL for sessions + the new commit-attribution
'commits' table; first-run synthetic rows move to seed.sql.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Shared `dashboard/db.py` with tests

**Files:**
- Create: `template/dashboard/db.py`
- Test: `template/dashboard/tests/test_db.py`

**Interfaces:**
- Produces: `connect(db_path=DB_PATH) -> sqlite3.Connection`; `ensure_schema(conn) -> None`; module constants `DB_PATH`, `SCHEMA`, `SEED`.

- [ ] **Step 1: Write the failing test**

Create `template/dashboard/tests/test_db.py`:

```python
#!/usr/bin/env python3
"""Unit tests for dashboard/db.py (stdlib unittest)."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

MOD = Path(__file__).resolve().parent.parent / "db.py"
spec = importlib.util.spec_from_file_location("dashboard_db", MOD)
db = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db)


def tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


class DbTests(unittest.TestCase):
    def test_first_run_creates_and_seeds(self):
        with tempfile.TemporaryDirectory() as d:
            conn = db.connect(Path(d) / "u.db")
            self.assertTrue({"sessions", "commits"} <= tables(conn))
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0], 0)
            conn.close()

    def test_reconnect_does_not_duplicate_seeds(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "u.db"
            c1 = db.connect(p); n1 = c1.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]; c1.close()
            c2 = db.connect(p); n2 = c2.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]; c2.close()
            self.assertEqual(n1, n2)

    def test_migrates_preexisting_sessions_only_db(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "u.db"
            raw = sqlite3.connect(p)
            raw.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, seat TEXT NOT NULL)")
            raw.execute("INSERT INTO sessions (ts, seat) VALUES ('2026-01-01T00:00:00','Developer')")
            raw.commit(); raw.close()
            conn = db.connect(p)  # not first run -> ensure_schema adds commits, no seed
            self.assertIn("commits", tables(conn))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1)
            conn.close()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 template/dashboard/tests/test_db.py`
Expected: FAIL — `db.py` does not exist yet (module load error).

- [ ] **Step 3: Write `db.py`**

Create `template/dashboard/db.py`:

```python
#!/usr/bin/env python3
"""Shared SQLite access for the dashboard (app + collector).

connect() opens the DB, ensures the schema (idempotent DDL from schema.sql),
and seeds synthetic rows from seed.sql only when the DB file was just created.
ensure_schema() is safe to call on a pre-existing DB — it adds any missing
tables (e.g. the Phase 3 `commits` table) without touching existing data.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "utilization.db"
SCHEMA = HERE / "schema.sql"
SEED = HERE / "seed.sql"


def ensure_schema(conn: sqlite3.Connection) -> None:
    if SCHEMA.exists():
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.commit()


def connect(db_path=DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    first_run = not db_path.exists()
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    if first_run and SEED.exists():
        conn.executescript(SEED.read_text(encoding="utf-8"))
        conn.commit()
    return conn
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 template/dashboard/tests/test_db.py`
Expected: PASS — `OK`, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add template/dashboard/db.py template/dashboard/tests/test_db.py
git commit -m "feat: add shared dashboard db.py (connect + idempotent schema)

connect()/ensure_schema() apply schema.sql idempotently and seed only on
first creation, so a pre-Phase-3 utilization.db gains the commits table.
Used by app.py and the collector. Unit-tested.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Collector `dashboard/collect_commits.py` with tests

**Files:**
- Create: `template/dashboard/collect_commits.py`
- Test: `template/dashboard/tests/test_collect_commits.py`

**Interfaces:**
- Consumes: `db.connect`. Produces: `parse_note(note) -> (ai_lines, human_lines, tool)`; `classify(ai, human, has_note, has_ai_trailer) -> (klass, source)`; `collect(repo, since, db_path) -> (rows, summary)`; `main()`.

- [ ] **Step 1: Write the failing test**

Create `template/dashboard/tests/test_collect_commits.py`:

```python
#!/usr/bin/env python3
"""Functional test for collect_commits.py: classifies human / ai-assisted / mixed."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

MOD = Path(__file__).resolve().parent.parent / "collect_commits.py"
spec = importlib.util.spec_from_file_location("collect_commits", MOD)
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

NOTE = """foo.py
  s_aaaaaaaaaaaaaa::t_bbbbbbbbbbbbbb 1-10
  h_cccccccccccccc 11-14
---
{"schema_version":"authorship/3.0.0","base_commit_sha":"x","prompts":{},"sessions":{"s_aaaaaaaaaaaaaa":{"agent_id":{"tool":"claude","id":"c","model":"m"},"human_author":"d@e.com"}},"humans":{"h_cccccccccccccc":{"author":"D <d@e.com>"}}}"""


def git(repo, *args, **kw):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, **kw)


class CollectTests(unittest.TestCase):
    def test_parse_note_counts_ai_and_human(self):
        ai, human, tool = cc.parse_note(NOTE)
        self.assertEqual(ai, 10)      # s_ key range 1-10
        self.assertEqual(human, 4)    # h_ key range 11-14
        self.assertEqual(tool, "claude")

    def test_classify(self):
        self.assertEqual(cc.classify(10, 0, True, False)[0], "ai")
        self.assertEqual(cc.classify(10, 4, True, False)[0], "mixed")
        self.assertEqual(cc.classify(0, 0, False, True)[0], "ai-assisted")
        self.assertEqual(cc.classify(0, 0, False, False)[0], "human")

    def test_end_to_end_three_commits(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "h@e.com"); git(repo, "config", "user.name", "Human")
            # 1) human commit (no trailer)
            (repo / "a.py").write_text("x = 1\n")
            git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "plain human change")
            # 2) AI-trailer commit
            (repo / "b.py").write_text("y = 2\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "add b\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
            # 3) commit with a synthetic git-ai note
            (repo / "foo.py").write_text("\n".join(f"L{i}" for i in range(1, 15)) + "\n")
            git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "add foo")
            sha3 = git(repo, "rev-parse", "HEAD").stdout.strip()
            git(repo, "notes", "--ref=ai", "add", "-m", NOTE, sha3)
            dbp = Path(d) / "u.db"
            rows, summary = cc.collect(repo=str(repo), since=None, db_path=dbp)
            self.assertEqual(rows, 3)
            import sqlite3
            con = sqlite3.connect(dbp)
            by = dict(con.execute("SELECT subject, klass FROM commits").fetchall())
            self.assertEqual(by["plain human change"], "human")
            self.assertEqual(by["add b"], "ai-assisted")
            self.assertEqual(by["add foo"], "mixed")   # ai 10 + human 4
            ai_lines = con.execute("SELECT ai_lines FROM commits WHERE subject='add foo'").fetchone()[0]
            self.assertEqual(ai_lines, 10)
            con.close()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 template/dashboard/tests/test_collect_commits.py`
Expected: FAIL — `collect_commits.py` does not exist yet.

- [ ] **Step 3: Write `collect_commits.py`**

Create `template/dashboard/collect_commits.py`:

```python
#!/usr/bin/env python3
"""Collect commit attribution into the dashboard DB (commits table).

Classifies each commit AI / mixed / human by LOC using git-ai line-level notes
(refs/notes/ai, authorship/3.0.0) when present, falling back to the
Co-Authored-By trailer (human vs AI-assisted) otherwise. Reads notes with plain
`git notes` — the git-ai binary is NOT required on this machine.

Usage: collect_commits.py [--since <ref>] [--db <path>] [--repo <path>]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as dbmod  # noqa: E402

AI_MARKERS = re.compile(r"anthropic|claude|copilot|cursor|windsurf|\bbot\b", re.I)
TICKET_RE = re.compile(r"[A-Z][A-Z0-9]+-\d+")
SEAT_BRANCH_RE = re.compile(r"session/([a-z0-9-]+)/")


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _count_ranges(spec: str) -> int:
    total = 0
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            try:
                total += int(hi) - int(lo) + 1
            except ValueError:
                pass
        elif part.isdigit():
            total += 1
    return total


def parse_note(note: str):
    """Return (ai_lines, human_lines, tool) from a git-ai authorship/3.0.0 note."""
    lines = note.splitlines()
    div = next((i for i, l in enumerate(lines) if l.strip() == "---"), None)
    attest = lines[:div] if div is not None else lines
    meta_str = "\n".join(lines[div + 1:]) if div is not None else ""
    ai = human = 0
    for line in attest:
        if not (line.startswith("  ") or line.startswith("\t")):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        key, ranges = parts[0], parts[1]
        n = _count_ranges(ranges)
        if key.startswith("h_"):
            human += n
        else:
            ai += n
    tool = None
    if meta_str.strip():
        try:
            j = json.loads(meta_str)
            for s in (j.get("sessions") or {}).values():
                tool = (s.get("agent_id") or {}).get("tool")
                if tool:
                    break
        except (ValueError, TypeError):
            pass
    return ai, human, tool


def classify(ai, human, has_note, has_ai_trailer):
    if has_note:
        if ai > 0 and human > 0:
            return "mixed", "git-ai"
        if ai > 0:
            return "ai", "git-ai"
        return "human", "git-ai"
    if has_ai_trailer:
        return "ai-assisted", "trailer"
    return "human", "trailer"


def collect(repo=".", since=None, db_path=None):
    conn = dbmod.connect(db_path) if db_path is not None else dbmod.connect()
    rng = f"{since}..HEAD" if since else "HEAD"
    fmt = "%H%x1f%aI%x1f%an%x1f%ae%x1f%s%x1f%b%x1e"
    out = _git(repo, "log", "--no-merges", f"--pretty=format:{fmt}", rng).stdout
    rows = 0
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        fields = (rec.split("\x1f") + [""] * 6)[:6]
        sha, ts, an, ae, subj, body = fields
        # numstat
        ins = dels = files = 0
        for l in _git(repo, "show", "--numstat", "--format=", "-M", sha).stdout.splitlines():
            p = l.split("\t")
            if len(p) >= 3:
                files += 1
                if p[0].isdigit():
                    ins += int(p[0])
                if p[1].isdigit():
                    dels += int(p[1])
        # git-ai note
        note = _git(repo, "notes", "--ref=ai", "show", sha)
        has_note = note.returncode == 0 and note.stdout.strip() != ""
        ai_lines = human_lines = 0
        tool = None
        if has_note:
            ai_lines, human_lines, tool = parse_note(note.stdout)
        has_ai_trailer = any(
            l.lower().startswith("co-authored-by:") and AI_MARKERS.search(l)
            for l in body.splitlines()
        )
        klass, source = classify(ai_lines, human_lines, has_note, has_ai_trailer)
        if source == "trailer" and klass == "ai-assisted":
            ai_lines = ins
        m = TICKET_RE.search(subj) or TICKET_RE.search(body)
        ticket = m.group(0) if m else None
        seat = None
        bm = SEAT_BRANCH_RE.search(_git(repo, "branch", "--contains", sha, "--format=%(refname:short)").stdout)
        if bm:
            seat = bm.group(1)
        conn.execute(
            "INSERT OR REPLACE INTO commits (sha, ts, author_name, author_email, seat, klass, source, "
            "ai_lines, human_lines, insertions, deletions, files_changed, tool, subject, ticket) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sha, ts, an, ae, seat, klass, source, ai_lines, human_lines, ins, dels, files, tool, subj, ticket),
        )
        rows += 1
    conn.commit()
    summary = dict(conn.execute("SELECT klass, COUNT(*) FROM commits GROUP BY klass").fetchall())
    conn.close()
    return rows, summary


def main():
    ap = argparse.ArgumentParser(description="Collect commit attribution into the dashboard DB.")
    ap.add_argument("--since", help="collect commits since this ref (default: all)")
    ap.add_argument("--db", help="path to the SQLite DB (default: dashboard/utilization.db)")
    ap.add_argument("--repo", default=".", help="git repo to scan (default: cwd)")
    a = ap.parse_args()
    rows, summary = collect(repo=a.repo, since=a.since, db_path=a.db)
    print(f"collected {rows} commit(s): " + ", ".join(f"{k}={v}" for k, v in sorted(summary.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 template/dashboard/tests/test_collect_commits.py`
Expected: PASS — `OK`, 3 tests (parse, classify, end-to-end human/ai-assisted/mixed).

- [ ] **Step 5: Commit**

```bash
git add template/dashboard/collect_commits.py template/dashboard/tests/test_collect_commits.py
git commit -m "feat: add commit-attribution collector

Parses refs/notes/ai (authorship/3.0.0) via plain git notes for line-level
AI/mixed/human, with a Co-Authored-By trailer fallback; upserts into the
commits table. Stdlib only; functional test covers all three classes.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Dashboard tab (`app.py`)

**Files:**
- Modify (rewrite): `template/dashboard/app.py`

**Interfaces:**
- Consumes: `db.connect` (Task 2), the `sessions` + `commits` tables.

- [ ] **Step 1: Rewrite `app.py` with two tabs**

Overwrite `template/dashboard/app.py`:

```python
#!/usr/bin/env python3
"""AI-SDLC dashboard (board pillar 4 / 7). Two tabs over a local SQLite DB:
Utilization (AI session cost/outcome/grounding) and Commit attribution
(AI / mixed / human by LOC, from collect_commits.py). Volume is always shown
next to a quality metric — never volume alone.

Run:
    pip install -r dashboard/requirements.txt
    streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as dbmod  # noqa: E402


@st.cache_data(ttl=30)
def load(table: str) -> pd.DataFrame:
    conn = dbmod.connect()
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn, parse_dates=["ts"])
    finally:
        conn.close()
    return df


def _date_filter(df: pd.DataFrame, key: str) -> pd.DataFrame:
    if df.empty:
        return df
    dmin, dmax = df["ts"].min().date(), df["ts"].max().date()
    drange = st.sidebar.date_input("Date range", (dmin, dmax), key=key)
    if isinstance(drange, (list, tuple)) and len(drange) == 2:
        lo, hi = pd.Timestamp(drange[0]), pd.Timestamp(drange[1]) + pd.Timedelta(days=1)
        return df[(df["ts"] >= lo) & (df["ts"] < hi)]
    return df


def utilization_tab(sessions: pd.DataFrame) -> None:
    if sessions.empty:
        st.info("No sessions yet. Seed rows are in seed.sql; your harness writes real ones.")
        return
    view = _date_filter(sessions, "util_dates")
    if view.empty:
        st.warning("No sessions in range."); return
    view = view.assign(tokens_total=view["tokens_in"] + view["tokens_out"])
    n = len(view)
    accepted = int((view["outcome"] == "accepted").sum())
    reworked = int((view["outcome"] == "reworked").sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sessions", n)
    c2.metric("Acceptance rate", f"{accepted / n:.0%}")
    c3.metric("Rework rate", f"{reworked / n:.0%}")
    c4.metric("Grounding rate", f"{view['grounded'].mean():.0%}")
    left, right = st.columns(2)
    with left:
        st.subheader("Sessions by seat")
        st.bar_chart(view.groupby("seat").size().rename("sessions"))
    with right:
        st.subheader("Outcome mix")
        st.bar_chart(view.groupby("outcome").size().rename("sessions"))


def attribution_tab(commits: pd.DataFrame, sessions: pd.DataFrame) -> None:
    if commits.empty:
        st.info("No commits yet. Run `python3 dashboard/collect_commits.py` to populate.")
        return
    view = _date_filter(commits, "attr_dates")
    if view.empty:
        st.warning("No commits in range."); return
    n = len(view)
    ai = int((view["klass"].isin(["ai", "ai-assisted"])).sum())
    mixed = int((view["klass"] == "mixed").sum())
    human = int((view["klass"] == "human").sum())
    ai_loc = int(view["ai_lines"].sum())
    total_loc = int(view["ai_lines"].sum() + view["human_lines"].sum()) or 1
    # quality pairing: rework rate from sessions over the same window
    rework = "—"
    if not sessions.empty:
        s = _sessions_in_range(sessions, view)
        if len(s):
            rework = f"{(s['outcome'] == 'reworked').mean():.0%}"
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Commits", n)
    c2.metric("AI-involved", f"{ai / n:.0%}")
    c3.metric("Mixed", f"{mixed / n:.0%}")
    c4.metric("AI lines", f"{ai_loc / total_loc:.0%}")
    c5.metric("Rework rate (quality)", rework, help="Read volume next to quality — never alone.")
    st.caption("Deep defect-linkage (which bug fixed which AI code) is Phase 4 (knowledge graph).")
    left, right = st.columns(2)
    with left:
        st.subheader("Commits by class")
        st.bar_chart(view.groupby("klass").size().rename("commits"))
        st.subheader("Lines by class")
        st.bar_chart(pd.Series({"ai": view["ai_lines"].sum(), "human": view["human_lines"].sum()}))
    with right:
        st.subheader("Class over time")
        ot = view.assign(day=view["ts"].dt.date).groupby(["day", "klass"]).size().unstack(fill_value=0)
        st.line_chart(ot)
        by = "seat" if view["seat"].notna().any() else "author_name"
        st.subheader(f"AI lines by {by}")
        st.bar_chart(view.groupby(by)["ai_lines"].sum())
    st.subheader("Recent commits")
    st.dataframe(
        view.sort_values("ts", ascending=False)[
            ["ts", "author_name", "seat", "klass", "source", "ai_lines", "human_lines", "subject", "tool"]
        ],
        use_container_width=True, hide_index=True,
    )


def _sessions_in_range(sessions: pd.DataFrame, commits_view: pd.DataFrame) -> pd.DataFrame:
    lo, hi = commits_view["ts"].min(), commits_view["ts"].max()
    return sessions[(sessions["ts"] >= lo) & (sessions["ts"] <= hi)]


def main() -> None:
    st.set_page_config(page_title="AI-SDLC Dashboard", page_icon="🤖", layout="wide")
    st.title("🤖 AI-SDLC Dashboard")
    st.caption("Pillar 7 — usage + attribution, read together. Metrics: docs/methodology/continuous-improvement.md.")
    sessions = load("sessions")
    commits = load("commits")
    tab1, tab2 = st.tabs(["Utilization", "Commit attribution"])
    with tab1:
        utilization_tab(sessions)
    with tab2:
        attribution_tab(commits, sessions)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it compiles (streamlit runtime not required for a syntax check)**

Run: `python3 -m py_compile template/dashboard/app.py template/dashboard/db.py template/dashboard/collect_commits.py`
Expected: exit 0, no output.
Also confirm no reference to the old `get_conn`: `grep -n "get_conn" template/dashboard/app.py` → no matches.

- [ ] **Step 3: Commit**

```bash
git add template/dashboard/app.py
git commit -m "feat: dashboard commit-attribution tab

app.py uses the shared db.connect and adds a Commit-attribution tab
(AI/mixed/human commits + LOC, class over time, by seat/author) shown
next to the utilization rework rate. Volume never stands alone.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Docs — git-ai adoption, onboarding, README, AGENTS.md

**Files:**
- Modify (rewrite): `template/docs/ai-context/attribution.md`
- Modify: `template/ONBOARDING.md`, `template/dashboard/README.md`, `template/AGENTS.md`

- [ ] **Step 1: Rewrite `attribution.md`**

Overwrite `template/docs/ai-context/attribution.md`:

```markdown
---
title: "Commit-attribution convention"
status: approved
owner: EM
author: AI-SDLC Bootstrap Kit
created: 2026-07-02
classification: internal
last-reviewed: 2026-07-02
ai-trust: working
---

# Commit-attribution convention

To make AI usage measurable (pillar 7 — the dashboard and retro loop), every commit is classifiable as **human**, **AI**, or **mixed**. The dashboard's `commits` table and `collect_commits.py` implement this.

## Primary signal — git-ai line-level notes

**[git-ai](https://usegitai.com)** records exactly which lines an agent wrote, in git notes at **`refs/notes/ai`** (format `authorship/3.0.0`): an attestation block mapping files to `s_…` (AI session) / `h_…` (human) line ranges, a `---` divider, then JSON metadata (agent tool, model, author). It captures automatically via agent tool-call hooks and adds no git-hot-path overhead.

- Install (per developer endpoint, optional): `curl -sSL https://usegitai.com/install.sh | bash` then `git ai install-hooks`.
- Sync notes with the team: `git fetch origin 'refs/notes/*:refs/notes/*'` (git-ai pushes/fetches them automatically once installed).
- The collector reads these notes with plain `git notes --ref=ai show <sha>` — **the git-ai binary is not required on the machine running the dashboard.**

Per commit: **ai** (only AI lines), **human** (only human/untracked lines), **mixed** (both).

## Fallback — the `Co-Authored-By` trailer

Commits without a git-ai note (existing history, or tools without git-ai) are classified from the commit trailer: an AI `Co-Authored-By:` (name/email matching `anthropic`/`claude`/`copilot`/`cursor`/`windsurf`/`bot`) → **ai-assisted**; otherwise **human**. This is coarser (commit-level, not line-level) and is marked `source: trailer` in the dashboard.

## Reading it

`python3 dashboard/collect_commits.py` populates the `commits` table; the dashboard's **Commit attribution** tab shows AI/mixed/human volume next to the utilization **rework** rate — volume is never read alone. Deep defect-linkage (which bug fixed which AI-authored code) is Phase 4 (knowledge graph).
```

- [ ] **Step 2: Add the optional git-ai step to `ONBOARDING.md`**

In `template/ONBOARDING.md`, in **Phase A**, at the end of the `## A4 — (Optional) Seed the knowledge layer` section (immediately before the `---` that precedes `# Phase B`), insert a new optional step:

```markdown
## A5b — (Optional) Install git-ai for line-level attribution

For line-level AI/human commit attribution in the dashboard (pillar 7), install **git-ai** (per endpoint):

```bash
curl -sSL https://usegitai.com/install.sh | bash   # macOS / Linux / WSL
git ai install-hooks
```

Optional — skipping it only lowers the dashboard's resolution to the `Co-Authored-By` trailer (human vs AI-assisted). See [`docs/ai-context/attribution.md`](./docs/ai-context/attribution.md).
```

(Renumbering is not required — `A5b` slots in as an optional sibling; keep `A5 — Identity` / `A6 — Communication preferences` as they are.)

- [ ] **Step 3: Update `dashboard/README.md`**

In `template/dashboard/README.md`, replace the "## Feeding it real data" section body with a version that documents both domains and the collector. After the existing intro/run block, ensure these subsections exist (edit in place, preserving the file's heading style):

```markdown
## What it shows

Two tabs over a local SQLite DB:

- **Utilization** — the session metric set (sessions, acceptance/rework, grounding), by seat and over time.
- **Commit attribution** — AI / mixed / human commits and lines of code, by author/seat and over time, shown next to the utilization rework rate (volume is never read alone).

## Feeding it real data

- **Sessions** — your agent wrapper inserts a row per session (seat, tokens, cost, outcome, grounded), or you import an export of your AI tool's usage logs.
- **Commits** — run the collector before a retro:

  ```bash
  python3 dashboard/collect_commits.py                 # all commits
  python3 dashboard/collect_commits.py --since main~50 # a recent range
  ```

  It classifies each commit AI/mixed/human from **git-ai** line-level notes (`refs/notes/ai`) when present, else the `Co-Authored-By` trailer. See [`../docs/ai-context/attribution.md`](../docs/ai-context/attribution.md). (Optional: schedule it via cron.)
```

- [ ] **Step 4: Tweak `AGENTS.md` §4.5**

In `template/AGENTS.md` §4.5 (Commit attribution), update the sentence so git-ai is primary and the trailer is the fallback. Replace the existing §4.5 body paragraph with:

```markdown
Every commit is classifiable as **human**, **AI**, or **mixed** so AI usage stays measurable (pillar 7). The primary signal is **git-ai** line-level notes (`refs/notes/ai`); the `Co-Authored-By: <agent> <email>` trailer is the fallback for un-noted commits. The convention and the dashboard collector are in [`docs/ai-context/attribution.md`](./docs/ai-context/attribution.md).
```

- [ ] **Step 5: Verify**

Run: `python3 template/scripts/validate-frontmatter.py template/docs/ai-context/attribution.md` → `ok`, exit 0.
Run: `grep -n "A5b" template/ONBOARDING.md && grep -n "git-ai" template/AGENTS.md template/dashboard/README.md` → matches in each.
Run: `git diff --name-only` → `template/CLAUDE.md` NOT listed.

- [ ] **Step 6: Commit**

```bash
git add template/docs/ai-context/attribution.md template/ONBOARDING.md template/dashboard/README.md template/AGENTS.md
git commit -m "docs: adopt git-ai for line-level attribution

attribution.md makes git-ai the primary signal (refs/notes/ai) with the
Co-Authored-By trailer as fallback; add an optional git-ai onboarding
step, document the collector in the dashboard README, and update AGENTS.md 4.5.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] Run the full governance gate + the Phase 3 tests:

```bash
python3 template/scripts/validate-skills.py
python3 template/scripts/validate-frontmatter.py
python3 template/scripts/validate-moments.py
python3 template/scripts/tests/test_validate_moments.py
python3 template/scripts/validate-seat-profiles.py
python3 template/scripts/tests/test_validate_seat_profiles.py
python3 template/scripts/knowledge/ingest.py --build
python3 template/dashboard/tests/test_db.py
python3 template/dashboard/tests/test_collect_commits.py
python3 -m py_compile template/dashboard/app.py template/dashboard/db.py template/dashboard/collect_commits.py
```
Expected: every command exits 0.

- [ ] `git status` clean; `git log --oneline main..HEAD` shows the Phase 3 task commits.

---

## Self-review against the spec

- **C1 adopt git-ai (docs/onboarding):** Task 5. ✓
- **C2 commits table + schema split:** Task 1. ✓
- **C3 shared db.py:** Task 2. ✓
- **C4 collector:** Task 3. ✓
- **C5 dashboard tab + quality pairing:** Task 4. ✓
- **Acceptance criteria 1–6:** each maps to a task verification; Final verification runs the gate + the two dashboard test suites + py_compile. ✓
- **Out-of-scope** (deep defect-linkage, Postgres/hosted, retroactive line attribution, auto-wiring the collector) absent from every task. ✓
- **Ordering:** schema (1) → db.py (2) → collector (3) + app (4) → docs (5). ✓
