---
title: "Team-level session telemetry — per-user committed ledger (design)"
status: draft
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-07-16
classification: internal
ai-trust: working
---

# Team-Level Session Telemetry — Per-User Committed Ledger

**Goal.** The token-roi theme (2026-07-15) made `sessions` real — but only for the
developer whose machine ran the session: `~/.claude/projects` is per-machine, so the
dashboard's utilization, waste, and ROI figures are single-dev while `commits`,
`tickets`, and `spend` are already team-level. This theme closes that gap with **zero
infrastructure**: each developer's existing SessionEnd hook additionally regenerates a
per-user CSV ledger *inside the repo* — `docs/metrics/sessions/<user>.csv` — which
lands with their normal PRs; a merging importer folds every user's CSV into the
`sessions` table. Same diff-friendly committed-ledger pattern the kit already uses for
JIRA (`docs/product/jira/issues.csv`). The dashboard works unchanged — after import it
simply shows the whole team.

**Trade-offs accepted (brainstorm):** data arrives with commit latency, not real time;
session metadata (`ticket`, `task`) becomes visible in the repo — fine for a team repo,
documented for sensitive client work (§7).

---

## 1. Decisions (resolved in brainstorming)

| # | Decision | Choice |
|---|---|---|
| 1 | Scope | **Ledger only.** Admin-API key→seat grouping in `import_api_usage.py` stays a follow-up (central cross-check), not part of this theme. |
| 2 | CSV contents | **Full row incl. `ticket`** — 1:1 mirror of the `sessions` columns. Ticket keys already appear in branch names and commit messages; a README privacy note covers sensitive repos. |
| 3 | Write path | **Regenerate from local DB.** `export_sessions.py` rewrites the user's CSV entirely from their local `sessions` table on every SessionEnd — idempotent, resumed sessions update in place, sorted output keeps diffs minimal, CSV always equals DB. (Rejected: append-per-session — duplicate rows on resume, never self-heals.) |
| 4 | User identity | Local part of `git config user.email`, sanitized to `[a-z0-9._-]`; fallback `user.name`, then `$USER`. New `user TEXT` column on `sessions` so local and imported rows are comparable. |
| 5 | Dedup / conflicts | Upsert on the existing unique `session_id` index; **larger `tokens_in + tokens_out` wins**, tie → incoming. Solves self-double-counting (own transcript parse vs own committed CSV) for free. |
| 6 | Hook safety | Unchanged posture: telemetry may be lost, a session ritual may never break — every failure logs to `.usage-errors.log`, hook exits 0. |

---

## 2. Architecture

```
per developer machine                                      repo (shared via git)
─────────────────────                                      ─────────────────────
SessionEnd hook (collect-usage.sh)
  ├─► parse_transcript.py ─► local sessions table          (existing)
  └─► export_sessions.py ──► docs/metrics/sessions/<user>.csv   (NEW)
                                        │ committed with normal PRs
any machine, or CI
  import_sessions.py ◄── docs/metrics/sessions/*.csv       (NEW, merging importer)
        └─► sessions table (upsert by session_id)
                └─► dashboard: Utilization / Waste / ROI unchanged, now team-wide
```

Two new stdlib-only scripts in `scripts/spend/` (they are consumption tooling, next to
`parse_transcript.py` and the other importers):

| Unit | Does | Interface | Depends on |
|---|---|---|---|
| `export_sessions.py` | Regenerates the calling user's CSV from the local DB | `--db PATH --out-dir docs/metrics/sessions [--user NAME]` | `dashboard/db.py`, git config |
| `import_sessions.py` | Merges all users' CSVs into the DB | `--db PATH --dir docs/metrics/sessions` | `dashboard/db.py` |
| `collect-usage.sh` (modified) | Calls export after successful parse | unchanged hook contract | both scripts |

`docs/metrics/sessions/` ships with a `README.md` (what the files are, privacy note)
and a `.gitkeep`-equivalent via that README — CSVs appear as developers work.

---

## 3. Data model (deltas to `dashboard/schema.sql`)

One column, via the existing `_ensure_columns` migration helper in `dashboard/db.py`
(same mechanism the token-roi theme used for `session_id`/`model`/`cache_read_tokens`):

```sql
-- sessions gains:
user TEXT              -- ledger identity (git email local part); NULL on legacy rows
```

`parse_transcript.py` gains `--user` (the hook passes the resolved identity) so
**local** rows carry `user` too — otherwise a developer's own rows would flip between
NULL (local parse) and set (imported CSV) depending on which ran last.

No new tables, no view changes: `roi_view` and the period rollups already aggregate
`sessions` without caring who produced a row.

---

## 4. CSV ledger format

One file per user: `docs/metrics/sessions/<user>.csv`. Header (fixed, validated on
import):

```
session_id,ts,user,seat,tool,task,ticket,model,tokens_in,tokens_out,cache_read_tokens,cost_usd,outcome,grounded,notes
```

- Written with the stdlib `csv` module (RFC 4180 quoting — `task`/`notes` may contain
  commas), UTF-8, `\n` line endings.
- Rows sorted by `ts` then `session_id`; the file is **fully regenerated** each time,
  so a resumed session updates its row in place and diffs touch only changed rows.
- Only rows with a non-empty `session_id` are exported (legacy/seed rows without one
  are not portable and stay local).
- `user` in every row equals the filename stem (enforced on export, checked on import).

---

## 5. Export (`export_sessions.py`)

1. Resolve identity: `git config user.email` local part → sanitize
   (lowercase; keep `[a-z0-9._-]`, map others to `-`; must be non-empty) →
   fallback `git config user.name` (same sanitizing) → fallback `$USER`.
   `--user` overrides (tests, unusual setups).
2. `SELECT` `sessions` rows where `session_id IS NOT NULL` **and `user` is the
   resolved identity or NULL**. NULL rows were written by this machine before the
   `user` column existed, so the exporting user claims them — correct on a
   per-developer machine. Rows imported from teammates carry *their* `user` value and
   are never re-exported under this user's stem (no ledger cross-pollination).
3. Write `<out-dir>/<user>.csv` atomically (temp file + `os.replace`).
4. Empty result set → write nothing, remove nothing (no churn, no destruction).

## 6. Import (`import_sessions.py`)

1. Glob `<dir>/*.csv` (skip `README.md`); empty dir → exit 0 with a "nothing to
   import" line.
2. Validate the header verbatim against §4; mismatch → loud `ValueError` naming the
   file (schema drift must fail, not silently mis-map columns).
3. Per row: `user` column must equal the filename stem — filename wins on mismatch
   and the row is imported with a note appended (`user column 'X' != file stem`);
   malformed row (wrong field count, non-integer tokens) → loud `ValueError` naming
   file + 1-based line.
4. Upsert by `session_id`: insert if new; if a row with that `session_id` exists,
   replace it **only when incoming `tokens_in + tokens_out` ≥ existing** (sessions
   only grow; a fresher local parse never loses to an older committed CSV).
5. Idempotent: re-running on the same files changes nothing (same pattern as
   `import_invoice.py`).

## 7. Error handling & honesty guards

| Failure | Behavior |
|---|---|
| Hook: export fails for any reason | Append to `scripts/session/.usage-errors.log`, hook still exits 0 — parse/DB write already succeeded, telemetry loss ≠ broken session |
| Export: no resolvable identity (no git config, no `$USER`) | Log to stderr (hook captures to errlog), write nothing, exit non-zero |
| Export: empty sessions table / no `session_id` rows | Write nothing, exit 0 |
| Import: unknown/missing CSV header | `ValueError` naming the file — never guess column order |
| Import: malformed row | `ValueError` naming file + line — never silently skip money data |
| Import: `user` ≠ filename stem | Filename wins, note appended to the row — files are per-user by contract |
| Self-double-counting (own transcripts parsed locally AND own CSV imported) | Same `session_id` → one row; greater-total-wins keeps the freshest figures |
| Privacy | `docs/metrics/sessions/README.md` states plainly: `ticket` and `task` are visible to everyone with repo access; for sensitive client work leave `task` empty (it already defaults to NULL) or strip tickets from branch names |

## 8. Dashboard

Utilization view gains one **"By user"** section: sessions count, total cost, tokens
per `user` (rows with NULL `user` shown as `(unattributed)` — kept visible, same
honesty rule as unattributed spend). No other view changes; Waste and ROI become
team-wide automatically once the import runs.

## 9. Out of scope (this theme)

- Anthropic Admin-API key→seat/user grouping in `import_api_usage.py` (central
  cross-check of the ledger) — logged follow-up.
- Automation of *running* the importer (cron/CI job writing a DB artifact); the
  importer is manual/CI-invoked like every other importer in the kit.
- Real-time team telemetry (shared Postgres, OpenTelemetry) — documented later
  options, not needed for the retro/ROI cadence.

## 10. Testing

Stdlib `unittest`, same layout as `scripts/spend/tests/`:

- **Export:** golden CSV from a seeded temp DB (sorting, quoting, header); regeneration
  idempotence (run twice → identical bytes); NULL-`user` rows claimed by exporter;
  rows without `session_id` excluded; identity sanitizing (`Geo.Dinca+x@y.z` →
  `geo.dinca-x`); empty DB → no file.
- **Import:** merge two users' files; upsert idempotence; greater-total-wins vs
  smaller incoming; header mismatch raises; malformed row raises with file+line;
  stem-mismatch note; empty dir exits clean.
- **Hook smoke:** existing SessionEnd smoke extended — after the hook runs, the CSV
  exists and contains the session row; export failure path leaves exit code 0.
- **CI:** new test files added to both `ai-governance.yml` and `.gitlab-ci.yml`.
