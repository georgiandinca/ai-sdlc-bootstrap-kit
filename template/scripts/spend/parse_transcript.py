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
