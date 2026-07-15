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
