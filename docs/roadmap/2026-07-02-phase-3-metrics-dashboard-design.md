# Phase 3 — Metrics Dashboard: Design

**Status:** approved · **Version:** 1.0 · **Author:** Georgian Dinca (+ AI) · **Created:** 2026-07-02 · **Last reviewed:** 2026-07-02

Design for Phase 3 of the [evolution roadmap](./2026-07-01-ai-sdlc-evolution-roadmap.md), on `main` after Phases 0–2 merged (branch `feat/phase-3-metrics-dashboard`). Phase 3 adds **commit-attribution** metrics (AI / mixed / human by LOC) to the existing dashboard, using **git-ai line-level notes with a `Co-Authored-By` trailer fallback**, so a review/retro can see how much of the codebase AI is writing — paired with quality, never volume alone.

The existing `dashboard/` tracks *session utilization* (tokens/cost/outcome/grounding in a `sessions` table). Phase 3 **adds a second, complementary domain** (a `commits` table + collector + a dashboard tab); it does not replace the utilization view.

---

## 1. Locked decisions

| Decision | Choice |
|---|---|
| Classification | **git-ai line-level** (`refs/notes/ai`, `authorship/3.0.0`) with a **`Co-Authored-By` trailer fallback** for commits without a note |
| git-ai install | **Optional** onboarding step; the dashboard degrades to trailer-level (human vs AI-assisted) without it |
| Collector trigger | A **manual script** run before a retro; cron documented but not wired |
| Shared DB access | Extract **`dashboard/db.py`** (`connect` + idempotent `ensure_schema` + first-run seed), used by both `app.py` and the collector |

## 2. The git-ai note format (what the parser must handle)

`git notes --ref=ai show <sha>` returns (no git-ai binary required):
```
<file path>
  <key> <line-ranges>
  ...
---
{ "schema_version": "authorship/3.0.0", "sessions": {…}, "humans": {…}, … }
```
- Keys: `s_<hex>::t_<hex>` and bare `<16hex>` (legacy) → **AI**; `h_<hex>` → **human-typed**.
- Ranges: comma-separated single/hyphenated line numbers (`1-10,15-20`); line count = Σ(hi−lo+1).
- JSON `sessions[*].agent_id.tool` gives the tool (`claude`, `cursor`, …).
- Split on a line that is exactly `---`; parse the JSON below it.

## 3. Component 1 — adopt git-ai (docs + onboarding)

- **Rewrite `docs/ai-context/attribution.md`:** git-ai is the **primary** line-level mechanism (`refs/notes/ai`, format above); the `Co-Authored-By` trailer is the documented **fallback** for un-noted commits (existing history, non-git-ai tools). Keep the three classes (human / AI / mixed) and define them precisely against the note (see §5).
- **Optional onboarding step** in `ONBOARDING.md` Phase A: install git-ai (`curl -sSL https://usegitai.com/install.sh | bash`, then `git ai install-hooks`), marked opt-in — skipping it only lowers resolution to trailer-level.
- **Document notes sync:** `git fetch origin 'refs/notes/*:refs/notes/*'` so the collector sees the team's attribution.
- Tweak `AGENTS.md §4.5` wording (git-ai now primary, trailer is fallback).

## 4. Component 2 — schema restructure (`schema.sql` + `seed.sql`)

- **`schema.sql` becomes DDL-only** (idempotent): the existing `sessions` table **plus** a new `commits` table:
  `sha` (PK), `ts`, `author_name`, `author_email`, `seat`, `klass` (`human`|`ai`|`mixed`|`ai-assisted`), `source` (`git-ai`|`trailer`), `ai_lines`, `human_lines`, `insertions`, `deletions`, `files_changed`, `tool`, `subject`, `ticket` + `idx_commits_ts` / `idx_commits_klass`.
- **`seed.sql` (new)** holds the first-run synthetic rows — the existing `sessions` seeds (moved out of `schema.sql`) plus a few synthetic `commits` rows — so the dashboard renders before any collection. Seeds run **only on first run**.

## 5. Component 3 — shared `dashboard/db.py`

`connect(db_path=DB_PATH) -> sqlite3.Connection`: detect first run, `ensure_schema(conn)` always, seed on first run.
`ensure_schema(conn)`: `executescript(schema.sql)` — idempotent `CREATE TABLE/INDEX IF NOT EXISTS`, so a **pre-Phase-3 `utilization.db` gains the `commits` table** on next open.
`connect` seeds from `seed.sql` only when the DB file didn't exist. `app.py` and `collect_commits.py` both import `connect`.

## 6. Component 4 — collector `dashboard/collect_commits.py` (stdlib only)

`collect_commits.py [--since <ref>] [--db <path>]` (default: all commits). For each commit (`git log --no-merges --numstat --format=…`):
- metadata: `sha`, author date (ISO `ts`), author name/email, subject, ticket (from a `[A-Z]+-\d+` in subject/branch).
- `insertions`/`deletions`/`files_changed` from `--numstat`.
- **git-ai note:** `git notes --ref=ai show <sha>` (exit ≠0 ⇒ absent). Parse per §2 → `ai_lines` (Σ AI-key ranges), `human_lines` (Σ `h_`-key ranges), `tool`.
- **Classify:**
  - note present → `ai` (ai_lines>0, human_lines≈0) · `human` (ai_lines≈0) · `mixed` (both>0); `source=git-ai`.
  - no note, AI `Co-Authored-By` trailer (name/email matches an AI marker: `anthropic`, `claude`, `copilot`, `cursor`, `windsurf`, `bot`) → `ai-assisted`; `source=trailer`; `ai_lines`=insertions (coarse).
  - else → `human`; `source=trailer`.
- `seat`: best-effort from a `session/<seat>/` branch containing the commit (`git branch --contains`), else NULL — commit→seat is not reliably recoverable, so author is the primary unit.
- Idempotent **upsert by `sha`** (`INSERT OR REPLACE`). Prints a per-class summary.

## 7. Component 5 — dashboard tab (`app.py`)

Refactor `app.py` to use `db.connect()`, and split the page into two `st.tabs`:
- **Utilization** — the existing session metrics (unchanged).
- **Commit attribution** — headline **AI / mixed / human** commit % and **AI-LOC %**; charts: class over time, **LOC-by-class stacked**, by author (and seat when present), by tool; a table of recent commits.
- **Quality pairing (guardrail):** the attribution tab shows one paired quality number (the utilization **rework/acceptance** rate over the same date range) with a caption that volume must be read next to quality. **Deep defect-linkage** (bug-fix → the AI code it fixed) is **Phase 4** (knowledge graph).

## 8. Data flow

```
git history ──► collect_commits.py ──(git notes refs/notes/ai | Co-Authored-By)──► classify
   └─► commits table (via db.connect/ensure_schema)  ◄── app.py reads (Commit attribution tab)
sessions table (existing) ──► app.py (Utilization tab) ──► paired quality number on attribution tab
git-ai (optional, per-endpoint) ──► writes refs/notes/ai on new commits ──► line-level resolution
```

## 9. Acceptance criteria

1. `schema.sql` is idempotent DDL (sessions + commits); `seed.sql` holds first-run seeds; re-running `ensure_schema` on an existing DB adds `commits` without duplicating seeds.
2. `db.py` `connect`/`ensure_schema` work first-run and on a pre-existing sessions-only DB (migration).
3. `collect_commits.py` classifies a human commit, an AI-trailer commit, and a commit with a synthetic `refs/notes/ai` note correctly (human / ai-assisted / ai|mixed), with correct line counts, idempotently.
4. `app.py` imports `db.py`, compiles, and renders two tabs including Commit attribution with the paired quality number.
5. `attribution.md` documents git-ai as primary + trailer fallback; onboarding has the optional git-ai step; notes-sync documented.
6. Full governance gate green; `python3 -m py_compile` clean on the three dashboard modules.

## 10. Out of scope (deferred)

- Deep defect/rework linkage (AI code → the bug that fixed it) → **Phase 4** (knowledge graph).
- Postgres / hosted (Next.js on Vercel) deployment — the README already sketches the path.
- Retroactive line-level attribution of pre-git-ai history (impossible; trailer fallback covers it).
- Auto-wiring the collector into a hook or cron (documented only).

## 11. Decisions log

- git-ai line-level primary + `Co-Authored-By` trailer fallback; parser reads `refs/notes/ai` via plain `git notes` (no git-ai binary needed on the retro machine).
- git-ai install optional; collector manual; shared `db.py`; schema split into DDL + seed for idempotent migration.
- Commit→seat is best-effort (often NULL); author is the primary attribution unit.
- Quality pairing = show the utilization rework rate beside the volume charts; deep linkage deferred to Phase 4.
