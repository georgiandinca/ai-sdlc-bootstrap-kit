# AI-utilization dashboard (DB + web)

The board's pillar ④ — *Dashboard utilization (DB + web)* — and the visible half of pillar 7's improvement loop. A minimal, runnable **Streamlit** app over a local **SQLite** database.

```bash
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

On first run it creates `utilization.db` from [`schema.sql`](./schema.sql) (seeded with a few synthetic rows so it renders immediately). `*.db` is git-ignored.

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

## Growing it

- Swap SQLite for Postgres (the schema maps directly) when multiple machines write.
- Add a web front-end (e.g. a Next.js app on Vercel) reading the same DB if you want a hosted, always-on view instead of a local Streamlit run.
- Keep the metric set small — resist dashboard bloat (pillar 7).
