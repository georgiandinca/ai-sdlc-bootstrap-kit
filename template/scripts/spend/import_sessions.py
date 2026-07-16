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
