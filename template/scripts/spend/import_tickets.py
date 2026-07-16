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

EVIDENCE_TIERS = {"calibration", "pre-estimate", "velocity", "post-hoc"}


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
        tier = (rec.get("evidence_tier") or "").strip() or None
        if tier and tier not in EVIDENCE_TIERS:
            raise ValueError(
                f"line {i}: unknown evidence_tier '{tier}' "
                f"(want one of {sorted(EVIDENCE_TIERS)})")
        rows.append({
            "ticket": key,
            "actual_human_days": actual,
            "evidence_tier": tier,
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
