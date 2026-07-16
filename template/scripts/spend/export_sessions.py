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
