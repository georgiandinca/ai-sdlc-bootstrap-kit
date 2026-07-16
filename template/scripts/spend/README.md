# scripts/spend — AI consumption collectors

Feed the dashboard (`dashboard/utilization.db`) with real money data.
All scripts are stdlib-only and idempotent — re-running is a no-op.

| Script | Source | Writes | Granularity |
|---|---|---|---|
| `../session/collect-usage.sh` | Claude Code transcript, on SessionEnd (automatic) | `sessions` | per-session tokens |
| `import_api_usage.py` | Anthropic Admin cost report (`ANTHROPIC_ADMIN_KEY` env) | `spend` | tokens (org-level) |
| `import_invoice.py` | Cursor / Copilot / Claude Max invoices (CSV) | `spend` | invoice / flat-rate |
| `import_tickets.py` | JIRA ledger (`docs/product/jira/issues.csv`) + EM actuals CSV | `tickets` | — |

Monthly ritual (before the retro):

    python3 scripts/spend/import_api_usage.py --from 2026-06-01 --to 2026-07-01
    python3 scripts/spend/import_invoice.py --csv invoices/2026-06.csv
    python3 scripts/spend/import_tickets.py --ledger docs/product/jira/issues.csv --actuals actuals/2026-06.csv

**Double-counting caveat.** `import_api_usage.py` pulls the org-wide Admin
cost report, which includes Claude Code's own API usage. If the SessionEnd
collector (`collect-usage.sh` → `sessions`) is already active for this same
billing org, importing the full cost report double-counts those tokens in
`period_rollup`'s "AI € this period" and the client report. Import the cost
report only for API spend that is **not** already captured as sessions (e.g.
other tools/services on the same org key), or skip it entirely and rely on
sessions + invoices.

- `prices.json` — model → USD/Mtok (+ `eur_per_usd`). A maintained config:
  refresh from the pricing docs when models change. Unknown models cost 0 and
  are flagged on the Waste tab — never a guessed price.
- `config.json` — `points_to_days`, `day_rate_eur`, `working_days_per_month`,
  `closed_statuses`.
- Secrets are env-only (`ANTHROPIC_ADMIN_KEY`); nothing secret in git.
- **Batch discount (token-economy rule 7):** non-interactive jobs through the
  Batch API cost 50% of standard — spend rows for batch work land at that
  rate automatically since they come from the cost report. The dashboard
  does not yet break out batch share (no rate flag on spend rows) — check
  the cost report directly until that lands.

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
