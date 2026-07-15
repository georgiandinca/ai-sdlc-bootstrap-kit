# AI-utilization dashboard (DB + web)

The board's pillar ④ — *Dashboard utilization (DB + web)* — and the visible half of pillar 7's improvement loop. A minimal, runnable **Streamlit** app over a local **SQLite** database.

```bash
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

On first run it creates `utilization.db` from [`schema.sql`](./schema.sql) (seeded with a few synthetic rows so it renders immediately). `*.db` is git-ignored.

## What it shows

Four tabs over a local SQLite DB:

- **Utilization** — the session metric set (sessions, acceptance/rework, grounding), by seat and over time.
- **Commit attribution** — AI / mixed / human commits and lines of code, by author/seat and over time, shown next to the utilization rework rate (volume is never read alone).
- **Waste signals** — the token-economy pack, validated: cost per accepted
  outcome, rework burn, cache-hit ratio, cost by model, grounded vs
  ungrounded, unattributed share. Read top-to-bottom at retro: "is the pack
  working?" (`.claude/rules/token-economy.md`).
- **ROI** — human-day-equivalent ROI over closed tickets with an
  evidence-tier band and a coverage indicator, plus a client-report HTML
  export. Per-ticket AI cost is session tokens only; invoice/flat-rate spend
  joins at period level (counted exactly once) — unless you also import the
  org cost report for tokens already collected as sessions, which
  double-counts them; see `scripts/spend/README.md`.

## Feeding it real data

- **Sessions** — automatic: `scripts/session/collect-usage.sh` runs on
  SessionEnd and prices the transcript (`scripts/spend/parse_transcript.py`).
  Set the outcome (accepted/reworked/rejected) in your wrap-up ritual.
- **Spend & tickets** — run the importers in `scripts/spend/` (see its
  README) monthly, before the retro.
- **Commits** — run the collector before a retro:

  ```bash
  python3 dashboard/collect_commits.py                 # all commits
  python3 dashboard/collect_commits.py --since main~50 # a recent range
  ```

  It classifies each commit AI/mixed/human from **git-ai** line-level notes (`refs/notes/ai`) when present, else the `Co-Authored-By` trailer. See [`../docs/ai-context/attribution.md`](../docs/ai-context/attribution.md). (Optional: schedule it via cron.)

## Growing it

- Swap SQLite for Postgres (the schema maps directly) when multiple machines write.
- Add a web front-end (e.g. a Next.js app on Vercel) reading the same DB if you want a hosted, always-on view instead of a local Streamlit run.
- Keep the metric set small — resist dashboard bloat (pillar 7).
