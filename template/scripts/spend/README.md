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
  rate automatically since they come from the cost report.
