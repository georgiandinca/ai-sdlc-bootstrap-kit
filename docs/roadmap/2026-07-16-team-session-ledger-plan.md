---
title: "Team-level session telemetry — per-user committed ledger (implementation plan)"
status: draft
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-07-16
classification: internal
ai-trust: working
---

# Team Session Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard's `sessions` table team-wide with zero infrastructure: each developer's SessionEnd hook regenerates `docs/metrics/sessions/<user>.csv` from their local DB; a merging importer folds every user's CSV back into any machine's DB.

**Architecture:** Two new stdlib scripts in `scripts/spend/` (`export_sessions.py`, `import_sessions.py`) around the existing `sessions` table, which gains one `user TEXT` column. The SessionEnd hook calls the exporter after a successful transcript parse. Design: `docs/roadmap/2026-07-16-team-session-ledger-design.md`.

**Tech Stack:** Python 3 stdlib (sqlite3, csv, argparse, subprocess), bash hook, unittest. Streamlit/pandas only inside `dashboard/app.py`.

## Global Constraints

- All kit changes live under `template/`; the only repo-root file touched is `.gitlab-ci.yml` (Task 8).
- `scripts/` code is **stdlib only** — no pandas, no requests, nothing pip-installed.
- Hook contract: `collect-usage.sh` exits **0 on every path**; failures append to `scripts/session/.usage-errors.log` (git-ignored). A session ritual never breaks.
- CSV header, verbatim and validated on import:
  `session_id,ts,user,seat,tool,task,ticket,model,tokens_in,tokens_out,cache_read_tokens,cost_usd,outcome,grounded,notes`
- Import failures are LOUD: `ValueError` naming file (and 1-based line for row errors). Never silently skip a row.
- Conflict policy: an existing `sessions` row is replaced only when incoming `tokens_in + tokens_out` ≥ existing (greater-total-wins; ties → incoming).
- Export claims rows whose `user` is the resolved identity **or NULL**; teammates' imported rows are never re-exported under this user's stem.
- Identity chain: `--user` override → `git config user.email` local part → `git config user.name` → `$USER`; sanitized to `[a-z0-9._-]` (lowercase, others → `-`, strip leading/trailing `-`/`.`).
- Never commit on main; work happens on `feat/team-session-ledger`.
- Every commit ends with the trailer exactly: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Test commands below run from the repo root; all test files are path-independent (they resolve paths via `__file__`).

---

### Task 1: `user` column on `sessions` (schema + migration)

**Files:**
- Modify: `template/dashboard/schema.sql` (sessions CREATE TABLE)
- Modify: `template/dashboard/db.py:39-43` (`ensure_schema` migration dict)
- Test: `template/dashboard/tests/test_schema.py`

**Interfaces:**
- Consumes: existing `_ensure_columns(conn, table, columns)` helper in `db.py`.
- Produces: `sessions.user TEXT` (NULL on legacy rows) — used by Tasks 2, 3, 4, 7.

- [ ] **Step 1: Write the failing tests** — add two methods to the existing `TestSchema` class in `template/dashboard/tests/test_schema.py`:

```python
    def test_sessions_user_column(self):
        conn = self._fresh()
        self.assertIn("user", self._cols(conn, "sessions"))

    def test_migrates_user_onto_old_sessions_table(self):
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
        raw.commit(); raw.close()
        conn = dbmod.connect(path)
        self.assertIn("user", self._cols(conn, "sessions"))
        conn.execute("INSERT INTO sessions (ts, seat, user) VALUES ('t','QA','geo')")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 template/dashboard/tests/test_schema.py`
Expected: FAIL — `'user' not found in {...}` (twice)

- [ ] **Step 3: Implement.** In `template/dashboard/schema.sql`, change the last line of the `sessions` CREATE TABLE from:

```sql
    notes       TEXT, session_id TEXT, model TEXT, cache_read_tokens INTEGER NOT NULL DEFAULT 0
```

to:

```sql
    notes       TEXT, session_id TEXT, model TEXT, cache_read_tokens INTEGER NOT NULL DEFAULT 0, user TEXT
```

In `template/dashboard/db.py`, extend the migration dict in `ensure_schema`:

```python
    _ensure_columns(conn, "sessions", {
        "session_id": "TEXT",
        "model": "TEXT",
        "cache_read_tokens": "INTEGER NOT NULL DEFAULT 0",
        "user": "TEXT",
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 template/dashboard/tests/test_schema.py`
Expected: PASS (all tests, including the pre-existing ones)

- [ ] **Step 5: Commit**

```bash
git add template/dashboard/schema.sql template/dashboard/db.py template/dashboard/tests/test_schema.py
git commit -m "feat: sessions.user column for team session ledger (schema + migration)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `parse_transcript.py --user`

**Files:**
- Modify: `template/scripts/spend/parse_transcript.py` (argparse, `upsert_session`, row dict)
- Test: `template/scripts/spend/tests/test_parse_transcript.py`

**Interfaces:**
- Consumes: `sessions.user` from Task 1.
- Produces: `upsert_session(conn, row)` now expects a `user` key in `row` (may be None). `main` accepts `--user NAME`. On conflict, `user` updates via `COALESCE(excluded.user, sessions.user)` — a later parse **without** `--user` never erases a recorded identity.

- [ ] **Step 1: Write the failing test** — add to the `TestMainUpsert` class in `template/scripts/spend/tests/test_parse_transcript.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/spend/tests/test_parse_transcript.py`
Expected: FAIL — `error: unrecognized arguments: --user geo` (argparse SystemExit)

- [ ] **Step 3: Implement.** In `parse_transcript.py`, replace `upsert_session` with:

```python
def upsert_session(conn, row):
    conn.execute(
        """INSERT INTO sessions (ts, seat, tool, task, ticket, tokens_in,
               tokens_out, cost_usd, outcome, grounded, notes, session_id,
               model, cache_read_tokens, user)
           VALUES (:ts, :seat, 'claude', :task, :ticket, :tokens_in,
               :tokens_out, :cost_usd, 'unknown', 0, :notes, :session_id,
               :model, :cache_read_tokens, :user)
           ON CONFLICT(session_id) DO UPDATE SET
               tokens_in=excluded.tokens_in, tokens_out=excluded.tokens_out,
               cost_usd=excluded.cost_usd, model=excluded.model,
               cache_read_tokens=excluded.cache_read_tokens,
               notes=excluded.notes,
               user=COALESCE(excluded.user, sessions.user)""",
        row,
    )
    conn.commit()
```

In `main`, add after the `--task` argument:

```python
    ap.add_argument("--user", default=None,
                    help="ledger identity (git email local part); hook-resolved")
```

and add `"user": args.user,` to the dict passed to `upsert_session` (after the `"cache_read_tokens"` entry).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 template/scripts/spend/tests/test_parse_transcript.py`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add template/scripts/spend/parse_transcript.py template/scripts/spend/tests/test_parse_transcript.py
git commit -m "feat: parse_transcript records ledger user; never erased by user-less re-runs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `export_sessions.py` — regenerate the user's committed ledger

**Files:**
- Create: `template/scripts/spend/export_sessions.py`
- Test: `template/scripts/spend/tests/test_export_sessions.py`

**Interfaces:**
- Consumes: `sessions` table incl. `user` (Tasks 1–2); `dashboard/db.py` `connect()`.
- Produces: `HEADER` list (imported by Task 4); `sanitize_user(raw) -> str|None`; `resolve_user(override=None) -> str|None`; `main(argv) -> int` (0 ok/nothing, 2 no identity). CLI: `--db PATH --out-dir DIR [--user NAME]`. Writes `<out-dir>/<user>.csv`, sorted by `ts, session_id`, atomic replace, full regeneration.

- [ ] **Step 1: Write the failing tests** — create `template/scripts/spend/tests/test_export_sessions.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 template/scripts/spend/tests/test_export_sessions.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'export_sessions'`

- [ ] **Step 3: Write the implementation** — create `template/scripts/spend/export_sessions.py` (mode 644, it is invoked via `python3`):

```python
#!/usr/bin/env python3
"""Regenerate this user's committed session ledger from the local dashboard DB.

Writes docs/metrics/sessions/<user>.csv — the WHOLE file, every run — from
the local sessions table (team-session-ledger design §5). Rows sorted by ts
then session_id so diffs touch only what changed; atomic replace so a killed
run never leaves a torn file. Stdlib only.

Usage:
  export_sessions.py --db dashboard/utilization.db \
      --out-dir docs/metrics/sessions [--user geo]
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

HEADER = ["session_id", "ts", "user", "seat", "tool", "task", "ticket",
          "model", "tokens_in", "tokens_out", "cache_read_tokens",
          "cost_usd", "outcome", "grounded", "notes"]


def sanitize_user(raw):
    """Lowercase; keep [a-z0-9._-]; anything else -> '-'; strip edge
    punctuation. Empty result -> None (caller must fall back or fail)."""
    s = re.sub(r"[^a-z0-9._-]", "-", (raw or "").strip().lower()).strip("-.")
    return s or None


def _git_config(key):
    try:
        out = subprocess.run(["git", "config", key], capture_output=True,
                             text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except OSError:
        return ""


def resolve_user(override=None):
    """Identity chain: override > git user.email local part > user.name > $USER."""
    if override:
        return sanitize_user(override)
    email = _git_config("user.email")
    if "@" in email:
        user = sanitize_user(email.split("@", 1)[0])
        if user:
            return user
    user = sanitize_user(_git_config("user.name"))
    if user:
        return user
    return sanitize_user(os.environ.get("USER"))


def rows_for_user(conn, user):
    """This user's exportable rows: session_id set, user = <user> or NULL
    (pre-column local rows are claimed by the exporting user — design §5).
    Teammates' imported rows carry their own user and are never re-exported."""
    cur = conn.execute(
        """SELECT session_id, ts, ?, seat, tool, task, ticket, model,
                  tokens_in, tokens_out, cache_read_tokens, cost_usd,
                  outcome, grounded, notes
           FROM sessions
           WHERE session_id IS NOT NULL AND (user IS NULL OR user = ?)
           ORDER BY ts, session_id""", (user, user))
    return [["" if v is None else v for v in row] for row in cur.fetchall()]


def write_ledger(rows, out_path):
    """Full regeneration, atomically: temp file in the target dir + os.replace."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(HEADER)
            writer.writerows(rows)
        os.replace(tmp, out_path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--user", default=None,
                    help="override the git-derived ledger identity")
    args = ap.parse_args(argv)

    user = resolve_user(args.user)
    if not user:
        print("[export-sessions] no resolvable user identity "
              "(set git config user.email)", file=sys.stderr)
        return 2
    if not Path(args.db).exists():
        print(f"[export-sessions] no DB at {args.db}; nothing to export")
        return 0

    sys.path.insert(0, str(HERE.parents[1] / "dashboard"))
    import db as dbmod  # noqa: E402

    conn = dbmod.connect(args.db)
    try:
        rows = rows_for_user(conn, user)
    finally:
        conn.close()
    if not rows:
        print(f"[export-sessions] nothing to export for {user}")
        return 0
    out = Path(args.out_dir) / f"{user}.csv"
    write_ledger(rows, out)
    print(f"[export-sessions] wrote {len(rows)} rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 template/scripts/spend/tests/test_export_sessions.py`
Expected: PASS — 9 tests

- [ ] **Step 5: Commit**

```bash
git add template/scripts/spend/export_sessions.py template/scripts/spend/tests/test_export_sessions.py
git commit -m "feat: export_sessions regenerates per-user committed session ledger CSV

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `import_sessions.py` — merge all users' ledgers

**Files:**
- Create: `template/scripts/spend/import_sessions.py`
- Test: `template/scripts/spend/tests/test_import_sessions.py`

**Interfaces:**
- Consumes: `HEADER` imported from `export_sessions` (Task 3); `sessions.user` (Task 1); `dashboard/db.py` `connect()`.
- Produces: `rows_from_csv(fileobj, stem, filename) -> list[dict]` (loud `ValueError` on drift); `upsert_sessions(conn, rows) -> int` (rows actually written); `main(argv) -> int`. CLI: `--dir DIR --db PATH` (both default to the kit layout).

- [ ] **Step 1: Write the failing tests** — create `template/scripts/spend/tests/test_import_sessions.py`:

```python
#!/usr/bin/env python3
"""Unit tests for the merging session-ledger importer."""
import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import import_sessions as im  # noqa: E402

HDR = ",".join(im.HEADER)


def _csv(*lines):
    return io.StringIO("\n".join((HDR,) + lines) + "\n")


def _row(session_id="s1", user="geo", tin=10, tout=2, **kw):
    d = {"session_id": session_id, "ts": "2026-07-01T10:00:00", "user": user,
         "seat": "Developer", "tool": "claude", "task": "", "ticket": "PROJ-1",
         "model": "claude-opus-4-8", "tokens_in": str(tin), "tokens_out": str(tout),
         "cache_read_tokens": "0", "cost_usd": "0.5", "outcome": "unknown",
         "grounded": "0", "notes": ""}
    d.update(kw)
    return ",".join(d[k] for k in im.HEADER)


class TestRowsFromCsv(unittest.TestCase):
    def test_header_mismatch_raises_loudly(self):
        bad = io.StringIO("session_id,nope\nx,y\n")
        with self.assertRaisesRegex(ValueError, "geo.csv"):
            im.rows_from_csv(bad, "geo", "geo.csv")

    def test_malformed_rows_name_file_and_line(self):
        with self.assertRaisesRegex(ValueError, r"geo\.csv line 2"):
            im.rows_from_csv(_csv("only,two"), "geo", "geo.csv")
        with self.assertRaisesRegex(ValueError, r"geo\.csv line 2"):
            im.rows_from_csv(_csv(_row(tokens_in="NaN")), "geo", "geo.csv")
        with self.assertRaisesRegex(ValueError, r"geo\.csv line 2"):
            im.rows_from_csv(_csv(_row(session_id="")), "geo", "geo.csv")

    def test_stem_mismatch_takes_filename_and_notes_it(self):
        rows = im.rows_from_csv(_csv(_row(user="impostor")), "geo", "geo.csv")
        self.assertEqual(rows[0]["user"], "geo")
        self.assertIn("impostor", rows[0]["notes"])

    def test_clean_rows_parse(self):
        rows = im.rows_from_csv(_csv(_row(), _row(session_id="s2")), "geo", "geo.csv")
        self.assertEqual([r["session_id"] for r in rows], ["s1", "s2"])
        self.assertEqual(rows[0]["tokens_in"], 10)
        self.assertEqual(rows[0]["cost_usd"], 0.5)
        self.assertIsNone(rows[0]["task"])


class TestImportMerge(unittest.TestCase):
    def _import(self, tmp, files, db=None):
        db = db or Path(tmp) / "u.db"
        d = Path(tmp) / "sessions"
        d.mkdir(exist_ok=True)
        for name, lines in files.items():
            (d / name).write_text("\n".join([HDR] + lines) + "\n", encoding="utf-8")
        rc = im.main(["--dir", str(d), "--db", str(db)])
        self.assertEqual(rc, 0)
        return db

    def _q(self, db, sql):
        conn = sqlite3.connect(db)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def test_merges_two_users(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._import(tmp, {
                "geo.csv": [_row("s1", "geo")],
                "ana.csv": [_row("s2", "ana")],
            })
            got = dict(self._q(db, "SELECT session_id, user FROM sessions "
                                   "WHERE session_id IN ('s1','s2')"))
            self.assertEqual(got, {"s1": "geo", "s2": "ana"})

    def test_greater_total_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._import(tmp, {"geo.csv": [_row("s1", "geo", tin=100, tout=10)]})
            # smaller incoming total must NOT overwrite
            self._import(tmp, {"geo.csv": [_row("s1", "geo", tin=5, tout=1)]}, db=db)
            self.assertEqual(self._q(db, "SELECT tokens_in FROM sessions "
                                         "WHERE session_id='s1'"), [(100,)])
            # larger incoming total replaces
            self._import(tmp, {"geo.csv": [_row("s1", "geo", tin=200, tout=10)]}, db=db)
            self.assertEqual(self._q(db, "SELECT tokens_in FROM sessions "
                                         "WHERE session_id='s1'"), [(200,)])

    def test_rerun_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {"geo.csv": [_row("s1"), _row("s9", tin=1)]}
            db = self._import(tmp, files)
            self._import(tmp, files, db=db)
            self.assertEqual(self._q(db, "SELECT COUNT(*) FROM sessions "
                                         "WHERE session_id IN ('s1','s9')"), [(2,)])

    def test_empty_dir_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "sessions"
            d.mkdir()
            self.assertEqual(im.main(["--dir", str(d),
                                      "--db", str(Path(tmp) / "u.db")]), 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 template/scripts/spend/tests/test_import_sessions.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'import_sessions'`

- [ ] **Step 3: Write the implementation** — create `template/scripts/spend/import_sessions.py`:

```python
#!/usr/bin/env python3
"""Merge every user's committed session ledger (docs/metrics/sessions/*.csv)
into the dashboard's sessions table (team-session-ledger design §6).

Upsert by session_id; an existing row is replaced only when the incoming
tokens_in + tokens_out is >= the existing total — sessions only grow, so a
fresher local parse never loses to an older committed CSV. Malformed files
fail LOUDLY (ValueError naming file + line): never silently skip money data.
Stdlib only.

Usage:  import_sessions.py [--dir docs/metrics/sessions] [--db dashboard/utilization.db]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from export_sessions import HEADER  # noqa: E402  (single source for the format)

_INT_FIELDS = ("tokens_in", "tokens_out", "cache_read_tokens", "grounded")


def rows_from_csv(fileobj, stem, filename):
    reader = csv.reader(fileobj)
    header = next(reader, None)
    if header != HEADER:
        raise ValueError(f"{filename}: unexpected header {header!r} "
                         f"(want {HEADER!r}) — schema drift, refusing to guess")
    rows = []
    for i, rec in enumerate(reader, start=2):
        if len(rec) != len(HEADER):
            raise ValueError(f"{filename} line {i}: {len(rec)} fields, "
                             f"want {len(HEADER)}")
        row = dict(zip(HEADER, rec))
        if not row["session_id"] or not row["ts"]:
            raise ValueError(f"{filename} line {i}: empty session_id or ts")
        try:
            for key in _INT_FIELDS:
                row[key] = int(row[key] or 0)
            row["cost_usd"] = float(row["cost_usd"] or 0)
        except ValueError as exc:
            raise ValueError(f"{filename} line {i}: {exc}") from exc
        for key in ("task", "ticket", "model", "notes"):
            row[key] = row[key] or None
        row["seat"] = row["seat"] or "unknown"
        row["tool"] = row["tool"] or "claude"
        row["outcome"] = row["outcome"] or "unknown"
        if row["user"] != stem:
            note = f"user column '{row['user']}' != file stem '{stem}'"
            row["notes"] = f"{row['notes']}; {note}" if row["notes"] else note
            row["user"] = stem  # files are per-user by contract (design §7)
        rows.append(row)
    return rows


def upsert_sessions(conn, rows):
    """Insert new sessions; replace an existing one only when the incoming
    token total >= the existing (greater-total-wins). Returns rows written."""
    written = 0
    for row in rows:
        cur = conn.execute(
            """INSERT INTO sessions (ts, seat, tool, task, ticket, tokens_in,
                   tokens_out, cost_usd, outcome, grounded, notes, session_id,
                   model, cache_read_tokens, user)
               VALUES (:ts, :seat, :tool, :task, :ticket, :tokens_in,
                   :tokens_out, :cost_usd, :outcome, :grounded, :notes,
                   :session_id, :model, :cache_read_tokens, :user)
               ON CONFLICT(session_id) DO UPDATE SET
                   ts=excluded.ts, seat=excluded.seat, tool=excluded.tool,
                   task=excluded.task, ticket=excluded.ticket,
                   tokens_in=excluded.tokens_in, tokens_out=excluded.tokens_out,
                   cost_usd=excluded.cost_usd, outcome=excluded.outcome,
                   grounded=excluded.grounded, notes=excluded.notes,
                   model=excluded.model,
                   cache_read_tokens=excluded.cache_read_tokens,
                   user=excluded.user
               WHERE excluded.tokens_in + excluded.tokens_out
                     >= sessions.tokens_in + sessions.tokens_out""",
            row,
        )
        written += cur.rowcount
    conn.commit()
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=str(HERE.parents[1] / "docs" / "metrics" / "sessions"))
    ap.add_argument("--db", default=str(HERE.parents[1] / "dashboard" / "utilization.db"))
    args = ap.parse_args(argv)

    files = sorted(Path(args.dir).glob("*.csv"))
    if not files:
        print(f"[import-sessions] nothing to import in {args.dir}")
        return 0

    sys.path.insert(0, str(HERE.parents[1] / "dashboard"))
    import db as dbmod  # noqa: E402

    conn = dbmod.connect(args.db)
    try:
        total = written = 0
        for path in files:
            with open(path, encoding="utf-8", newline="") as f:
                rows = rows_from_csv(f, path.stem, path.name)
            total += len(rows)
            written += upsert_sessions(conn, rows)
    finally:
        conn.close()
    print(f"[import-sessions] {written}/{total} rows upserted "
          f"from {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 template/scripts/spend/tests/test_import_sessions.py`
Expected: PASS — 8 tests

- [ ] **Step 5: Commit**

```bash
git add template/scripts/spend/import_sessions.py template/scripts/spend/tests/test_import_sessions.py
git commit -m "feat: import_sessions merges per-user ledgers, greater-total-wins upsert

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Hook wiring — SessionEnd exports the ledger

**Files:**
- Modify: `template/scripts/session/collect-usage.sh:42-50`
- Test: `template/scripts/spend/tests/test_collect_usage.py`

**Interfaces:**
- Consumes: `export_sessions.resolve_user` (Task 3), `parse_transcript --user` (Task 2).
- Produces: env override `SDLC_SESSIONS_DIR` (default `docs/metrics/sessions`), mirroring the existing `SDLC_USAGE_DB` pattern. Hook still exits 0 on every path.

- [ ] **Step 1: Write the failing test** — add to the `TestCollectUsage` class in `template/scripts/spend/tests/test_collect_usage.py`:

```python
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
```

(The identity stem is not asserted — it depends on the machine's git config; the fallback chain guarantees *some* identity resolves.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/spend/tests/test_collect_usage.py`
Expected: FAIL — `hook must write exactly one ledger CSV` (0 CSVs found)

- [ ] **Step 3: Implement.** In `template/scripts/session/collect-usage.sh`, replace the final block (from `db="${SDLC_USAGE_DB:-...}"` through `exit 0`) with:

```bash
user=$(python3 -c 'import sys; sys.path.insert(0, "scripts/spend"); from export_sessions import resolve_user; print(resolve_user() or "")' 2>/dev/null || true)

db="${SDLC_USAGE_DB:-dashboard/utilization.db}"
if python3 scripts/spend/parse_transcript.py \
     --transcript "$transcript" --session-id "$session_id" \
     --seat "$seat" ${ticket:+--ticket "$ticket"} ${user:+--user "$user"} \
     --db "$db" 2>>"$errlog"; then
  # Team ledger (design §5): regenerate this user's committed CSV. Failure
  # is telemetry loss, never a broken session — log and keep exit 0.
  ledger_dir="${SDLC_SESSIONS_DIR:-docs/metrics/sessions}"
  if ! python3 scripts/spend/export_sessions.py \
       --db "$db" --out-dir "$ledger_dir" ${user:+--user "$user"} 2>>"$errlog"; then
    log_err "export_sessions failed for $session_id"
  fi
else
  log_err "parse_transcript failed for $transcript"
fi
exit 0
```

- [ ] **Step 4: Run tests to verify they pass** (all three hook tests, including the never-breaks-the-session cases)

Run: `python3 template/scripts/spend/tests/test_collect_usage.py`
Expected: PASS — 3 tests

- [ ] **Step 5: Commit**

```bash
git add template/scripts/session/collect-usage.sh template/scripts/spend/tests/test_collect_usage.py
git commit -m "feat: SessionEnd hook regenerates the per-user committed session ledger

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Ledger directory README + spend README section

**Files:**
- Create: `template/docs/metrics/sessions/README.md`
- Modify: `template/scripts/spend/README.md` (append one section at the end)

**Interfaces:**
- Consumes: script names/CLIs from Tasks 3–5.
- Produces: the committed `docs/metrics/sessions/` directory (the README makes it exist in git before any CSV lands).

- [ ] **Step 1: Create `template/docs/metrics/sessions/README.md`** with exactly:

```markdown
# Per-user session ledgers

One CSV per developer — `<user>.csv`, where `<user>` is the local part of
their `git config user.email` (sanitized) — regenerated on every SessionEnd
by `scripts/session/collect-usage.sh` → `scripts/spend/export_sessions.py`
from that developer's **local** dashboard DB. The files land with normal
PRs; that is the whole transport: no server, no shared DB.

Merge everyone's ledgers into the dashboard on any machine:

    python3 scripts/spend/import_sessions.py

Re-running is a no-op (upsert by `session_id`; the larger token total wins,
so a fresher local parse is never overwritten by an older committed CSV).

**Privacy.** Rows carry `ticket` and `task`, visible to everyone with repo
access. For sensitive client work leave `task` empty (the collector defaults
it to empty) and/or keep ticket keys out of branch names. Data arrives with
commit latency — this ledger feeds retros and ROI reviews, not real-time
monitoring.
```

- [ ] **Step 2: Append to `template/scripts/spend/README.md`** (at the end of the file):

```markdown
## Team session ledger (export_sessions.py / import_sessions.py)

`sessions` telemetry is per-machine — `~/.claude/projects` only holds *your*
transcripts. The team sees each other's sessions through a committed ledger:

- `export_sessions.py --db dashboard/utilization.db --out-dir docs/metrics/sessions`
  — regenerates `docs/metrics/sessions/<user>.csv` from your local DB (the
  SessionEnd hook runs this for you; commit the CSV with your normal PRs).
- `import_sessions.py` — merges every `docs/metrics/sessions/*.csv` into the
  `sessions` table. Upsert by `session_id`, greater token total wins;
  malformed files fail loudly. Idempotent.

See `docs/metrics/sessions/README.md` for the privacy note.
```

- [ ] **Step 3: Verify** the new README renders sanely and the importer's default dir matches it:

Run: `python3 template/scripts/spend/import_sessions.py --db /tmp/ledger-doc-check.db && rm -f /tmp/ledger-doc-check.db`
Expected: `[import-sessions] nothing to import in .../template/docs/metrics/sessions` (dir exists, only README — `*.csv` glob is empty), exit 0

- [ ] **Step 4: Commit**

```bash
git add template/docs/metrics/sessions/README.md template/scripts/spend/README.md
git commit -m "docs: session-ledger directory README (transport + privacy) and spend README section

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Dashboard — "By user" section on Utilization

**Files:**
- Modify: `template/dashboard/app.py` — `utilization_tab` (append after the seat/outcome chart columns)

**Interfaces:**
- Consumes: `sessions.user` (arrives via `load("sessions")`'s `SELECT *`); module constant `EUR_PER_USD` already defined at `app.py:30`.
- Produces: no new interfaces; NULL `user` shows as `(unattributed)` — kept visible, same honesty rule as unattributed spend.

- [ ] **Step 1: Implement.** In `utilization_tab`, after the existing `left, right = st.columns(2)` block (the "Sessions by seat" / "Outcome mix" charts), append:

```python
    st.subheader("By user (team ledger)")
    by_user = (view.assign(user=view["user"].fillna("(unattributed)"))
               if "user" in view.columns
               else view.assign(user="(unattributed)"))
    by_user = by_user.groupby("user").agg(
        sessions=("ts", "size"),
        tokens_in=("tokens_in", "sum"),
        tokens_out=("tokens_out", "sum"),
        cost_usd=("cost_usd", "sum"),
    )
    by_user["cost_eur"] = (by_user.pop("cost_usd") * EUR_PER_USD).round(2)
    st.dataframe(by_user.sort_values("cost_eur", ascending=False))
    st.caption("Team-wide once teammates' ledgers are imported "
               "(python3 scripts/spend/import_sessions.py — see "
               "docs/metrics/sessions/README.md); until then this is "
               "this machine's sessions only.")
```

- [ ] **Step 2: Verify it compiles** (app.py has no unit tests — py_compile is the existing gate):

Run: `python3 -m py_compile template/dashboard/app.py`
Expected: exit 0, no output

- [ ] **Step 3: Commit**

```bash
git add template/dashboard/app.py
git commit -m "feat: Utilization view gains By-user breakdown for the team ledger

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: CI wiring (both pipelines) + full gate

**Files:**
- Modify: `template/.github/workflows/ai-governance.yml` (test list, after `test_import_tickets.py`)
- Modify: `.gitlab-ci.yml` (repo root; test list, after `template/scripts/spend/tests/test_import_tickets.py`)

**Interfaces:**
- Consumes: test files from Tasks 3–4.
- Produces: both CI pipelines run the two new suites.

- [ ] **Step 1: GitHub workflow.** In `template/.github/workflows/ai-governance.yml`, directly after the line `python3 scripts/spend/tests/test_import_tickets.py`, add:

```yaml
          python3 scripts/spend/tests/test_export_sessions.py
          python3 scripts/spend/tests/test_import_sessions.py
```

- [ ] **Step 2: GitLab CI.** In `.gitlab-ci.yml`, directly after the line `- python3 template/scripts/spend/tests/test_import_tickets.py`, add:

```yaml
  - python3 template/scripts/spend/tests/test_export_sessions.py
  - python3 template/scripts/spend/tests/test_import_sessions.py
```

- [ ] **Step 3: Run the full local gate** (every suite CI runs, from the repo root):

```bash
python3 template/dashboard/tests/test_schema.py &&
python3 template/dashboard/tests/test_roi.py &&
python3 template/scripts/spend/tests/test_parse_transcript.py &&
python3 template/scripts/spend/tests/test_collect_usage.py &&
python3 template/scripts/spend/tests/test_import_invoice.py &&
python3 template/scripts/spend/tests/test_import_api_usage.py &&
python3 template/scripts/spend/tests/test_import_tickets.py &&
python3 template/scripts/spend/tests/test_export_sessions.py &&
python3 template/scripts/spend/tests/test_import_sessions.py &&
python3 template/scripts/tests/test_check_brief_churn.py &&
python3 -m py_compile template/dashboard/app.py &&
echo GATE-OK
```

Expected: `GATE-OK`

- [ ] **Step 4: Commit**

```bash
git add template/.github/workflows/ai-governance.yml .gitlab-ci.yml
git commit -m "ci: run session-ledger export/import test suites in both pipelines

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
