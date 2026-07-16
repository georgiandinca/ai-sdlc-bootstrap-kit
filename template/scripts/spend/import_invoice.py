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
