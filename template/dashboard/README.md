# AI-utilization dashboard (DB + web)

The board's pillar ④ — *Dashboard utilization (DB + web)* — and the visible half of pillar 7's improvement loop. A minimal, runnable **Streamlit** app over a local **SQLite** database.

```bash
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

On first run it creates `utilization.db` from [`schema.sql`](./schema.sql) (seeded with a few synthetic rows so it renders immediately). `*.db` is git-ignored.

## What it shows

The small, stable metric set from [`../docs/methodology/continuous-improvement.md`](../docs/methodology/continuous-improvement.md): sessions, acceptance rate, rework rate, **cost per accepted unit**, and **grounding rate**, broken down by seat and over time.

## Feeding it real data

The dashboard *reads*; your harness *writes* to the `sessions` table. Two common paths:

- **Direct write** — have your agent wrapper insert a row per session (seat, task, tokens, cost, outcome, grounded).
- **Import** — periodically import an export of your AI tool's usage logs and map columns to the schema.

```sql
INSERT INTO sessions (ts, seat, tool, task, ticket, tokens_in, tokens_out, cost_usd, outcome, grounded)
VALUES ('2026-06-26T10:00:00', 'Developer', 'claude', 'fix auth bug', 'PROJ-123', 15000, 3000, 0.18, 'accepted', 1);
```

## Growing it

- Swap SQLite for Postgres (the schema maps directly) when multiple machines write.
- Add a web front-end (e.g. a Next.js app on Vercel) reading the same DB if you want a hosted, always-on view instead of a local Streamlit run.
- Keep the metric set small — resist dashboard bloat (pillar 7).
