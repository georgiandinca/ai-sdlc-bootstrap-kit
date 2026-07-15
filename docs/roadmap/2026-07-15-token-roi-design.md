---
title: "AI consumption, token economy & ROI (design)"
status: draft
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-07-15
classification: internal
ai-trust: working
---

# AI Consumption, Token Economy & ROI

**Goal.** Make the kit answer, with defensible numbers, the question every sponsor asks:
*"a human-day costs ~€500; if we add ~€500/day of AI spend, is the output worth two
devs — more, less — and what is the project's ROI on AI usage?"* Three layers:
(1) **Measure** — real consumption collectors finally feed the dashboard's `sessions`
table and a new `spend` table across four heterogeneous sources; (2) **Optimize** — a
token-economy technique pack shipped as *enforced template defaults from day one*, each
technique paired with a metric proxy that validates it; (3) **Value** — a
**human-day-equivalent (HDE)** ROI model over per-ticket estimates, with evidence-tier
banding and a client-facing export.

**Non-negotiable framing.** This is a *template kit*. The feature ships runnable
reference collectors, a seeded dashboard that renders on a fresh clone, and an honest
data model: every number carries its **granularity** (tokens vs invoice vs flat-rate)
and every ROI figure its **evidence tier**. No metric is shown without its coverage.

---

## 1. Decisions (resolved in brainstorming)

| # | Decision | Choice |
|---|---|---|
| 1 | Where it lives | **Extend the kit's dashboard in place** (Option 1) — SQLite + Streamlit, new collectors + tabs; no separate tool, no hosted stack. |
| 2 | Consumption sources | **All four from day one**: Claude Code sessions (per-token), direct Anthropic API (usage API), Cursor/Copilot (invoice CSV), Claude Max subscriptions (flat-rate amortized). |
| 3 | Multi-source model | **One `spend` table** (borrowed from the ledger alternative) for non-session money, with a `granularity` honesty flag — never force invoice data into `sessions`. |
| 4 | ROI baseline | **Triangulate all four methods**, tagged by `evidence_tier`: calibration A/B > pre-work estimates > historical velocity > post-hoc judgment. Pre-work estimates per ticket are the workhorse. |
| 5 | Audiences | Client/sponsor (€-denominated ROI report), team/EM (waste signals for the pillar-7 retro), consultancy pre-sales (**cross-project aggregation deferred** — see §8). |
| 6 | Optimization posture | **Enforce best practices from day one** (user decision, overrides measure-first): the technique pack ships as template rules/hooks/defaults; the dashboard *validates* each technique, and the retro prunes what shows no effect after two sprints. |
| 7 | Hook safety | Telemetry may be lost; a session ritual may never break. All collectors follow the existing `… 2>/dev/null || true` hook pattern. |
| 8 | Idempotency | `sessions` gains `session_id TEXT UNIQUE` (Claude Code session UUID); importers upsert on `(source, period_start, seat)`. Re-runs and double-fires are no-ops. |

---

## 2. Architecture

Collectors **write**, the dashboard only **reads**. Everything stays SQLite
(`dashboard/utilization.db`); `commits` is untouched.

| Unit | File | Purpose | Deterministic? |
|---|---|---|---|
| **Session collector** | `scripts/session/collect-usage.sh` (+ `scripts/spend/parse_transcript.py`) | On SessionEnd: parse the just-ended Claude Code transcript JSONL, sum per-message usage (input/output/cache-read/cache-write, per model), price it, insert one `sessions` row (seat from seat profile, ticket from branch). | No (filesystem) |
| **API importer** | `scripts/spend/import_api_usage.py` | Anthropic Admin/Usage API → `spend` rows (`granularity='tokens'`). Env-only credentials. | No (network) |
| **Invoice importer** | `scripts/spend/import_invoice.py` | CSV import for Cursor/Copilot invoices and Claude Max seats → `spend` rows (`granularity='invoice'` / `'flat-rate'`). | Yes |
| **Prices** | `scripts/spend/prices.json` | Model → €/Mtoken table + `EUR_PER_USD`. Unknown model → cost 0 + `notes` flag, never a guess. | — |
| **ROI logic** | `dashboard/roi.py` + `roi_view` in `schema.sql` | Pure SQL/pandas: per-ticket AI cost + human cost + HDE; aggregation to sprint/project. | Yes |
| **Dashboard** | `dashboard/app.py` | Two new tabs: **Waste signals**, **ROI** (with client HTML export). | Yes |

```
Claude Code session ──SessionEnd──▶ collect-usage.sh ─▶ sessions   ┐
Anthropic Usage API ──▶ import_api_usage.py ─────────▶ spend      │
Cursor/Copilot/Max invoices ─▶ import_invoice.py ────▶ spend      ├─▶ roi_view ─▶ ROI tab ─▶ client export
JIRA ledger (issues.csv) ─▶ estimates ───────────────▶ tickets    │
git ─▶ collect_commits.py (existing) ────────────────▶ commits    ┘
```

---

## 3. Data model (deltas to `dashboard/schema.sql`)

**`sessions` — three column additions** (existing charts unaffected):

```sql
ALTER TABLE sessions ADD COLUMN session_id        TEXT UNIQUE;  -- Claude Code UUID (idempotency)
ALTER TABLE sessions ADD COLUMN model             TEXT;         -- dominant model of the session
ALTER TABLE sessions ADD COLUMN cache_read_tokens INTEGER NOT NULL DEFAULT 0;
```

**`spend` — new.** One row per source × period × seat for money that does not arrive
as per-session tokens:

```sql
CREATE TABLE IF NOT EXISTS spend (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,          -- anthropic-api | cursor | copilot | claude-max | other
    period_start TEXT NOT NULL,          -- ISO date
    period_end   TEXT NOT NULL,
    seat         TEXT NOT NULL DEFAULT '(org)',  -- '(org)' = unattributable org-level
                                         -- spend (NOT NULL because SQLite treats
                                         -- NULLs as distinct in UNIQUE, which would
                                         -- break re-import idempotency)
    cost_eur     REAL NOT NULL,
    granularity  TEXT NOT NULL,          -- tokens | invoice | flat-rate
    notes        TEXT,
    UNIQUE (source, period_start, seat)
);
```

Flat-rate Max seats land as monthly rows amortized over working days by `roi.py`; an
idle subscription still amortizes — idle cost is real cost.

**`tickets` — new.** The ROI join point:

```sql
CREATE TABLE IF NOT EXISTS tickets (
    ticket              TEXT PRIMARY KEY,          -- e.g. ACME-123
    estimate_human_days REAL,                      -- from refinement (or story_points × factor)
    actual_human_days   REAL,
    day_rate_eur        REAL,
    evidence_tier       TEXT NOT NULL DEFAULT 'pre-estimate',
                        -- calibration | pre-estimate | velocity | post-hoc
    status              TEXT NOT NULL DEFAULT 'open',   -- open | closed
    closed_at           TEXT
);
```

Estimates come from the JIRA ledger (`docs/product/jira/issues.csv` story points × a
configurable points→days factor in `scripts/spend/config.json`) or manual entry.

**`roi_view` — new SQL view.** Per closed ticket: `ai_cost_eur` (matched `sessions`
by ticket — **session-level tokens only**; invoice/flat-rate money cannot honestly be
split per ticket), `human_cost_eur` (`actual_human_days × day_rate`), `value_eur`
(`estimate_human_days × day_rate`), `hde` (estimate ÷ actual), per-ticket ROI.
Sprint/project ROI aggregates this view **and then adds the period's `spend` rows** to
the cost side — so coarse money is counted exactly once, at the level where it is
honest. No new storage.

**The ROI formula** (the €500 + €500 question, computed not asserted):

```
ROI = value_delivered_eur / (human_cost_eur + ai_cost_eur)
    = Σ estimate_human_days × day_rate / (Σ actual_human_days × day_rate + Σ ai_cost)
```

shown as a **band** weighted by evidence tier, never a bare point estimate.

---

## 4. Session collector (the piece that makes `sessions` real)

`SessionEnd` chain gains one call (after `auto-save.sh`):
`bash scripts/session/collect-usage.sh 2>/dev/null || true`.

1. Resolve the transcript: newest `~/.claude/projects/<project-slug>/*.jsonl` matching
   the ending session (filename = session UUID = `session_id`).
2. `parse_transcript.py` (stdlib-only, same posture as Phase-3/4 scripts): stream the
   JSONL, skip malformed lines, sum `message.usage` fields per model.
3. Price via `prices.json`; seat from `scripts/session/seat-profiles.json` active
   profile; ticket from branch name (`ACME-123-…` → `ACME-123`), else NULL →
   "unattributed" bucket, visible on the dashboard, never dropped.
4. Upsert into `sessions` on `session_id`. `outcome` stays `unknown` at insert; the
   existing wrap-up ritual (`wrapup.sh`) prompts the operator to set
   accepted/reworked/rejected — unchanged behaviour, now with real token data attached.
5. Any failure → append to `scripts/session/.usage-errors.log`, exit 0.

The transcript JSONL is an **observed format, not a contract**: the parser is
defensive, versioned by fixtures, and a format drift degrades to a logged error — never
a broken session.

---

## 5. Token-economy pack (enforced day one, validated forever)

One new rule file — **`.claude/rules/token-economy.md`** (~1 page) — plus small deltas
to existing artefacts. Anti-bloat: each technique has a metric proxy on the Waste tab;
**a technique showing no effect after two sprints is a deletion candidate at retro.**

| # | Technique | Ships as | Validated by |
|---|---|---|---|
| 1 | **Model routing** — mechanical work on cheap models, design/review on the big model | `seat-profiles.json` gains `default_model` + `escalation_hint` per seat; playbooks reference it | cost per accepted outcome, by model |
| 2 | **Prompt-cache hygiene** — briefs byte-stable within a sprint | rule + CI check in `ai-governance.yml` flagging AGENTS.md churn above a threshold | `cache_read_tokens ÷ tokens_in` per seat |
| 3 | **Context hygiene** — one ticket per session, `/clear` between tickets, targeted reads | rule; multi-ticket sessions aren't detectable in `wrapup.sh`, so the Waste tab's flagged long tail is the enforcement surface | tokens-per-session distribution, flagged long tail |
| 4 | **Ground, don't paste** — knowledge layer over document dumping | pointer to pillar 5; now measured | `grounded` flag vs `tokens_in` correlation |
| 5 | **Plan-before-code** — design gate cuts rework loops (the #1 token multiplier) | already in playbooks; `outcome` makes it measurable | rework burn: % tokens in reworked/rejected sessions |
| 6 | **Subagent scoping** — exploration in subagents, main context stays lean | rule, per-seat guidance | tokens_in per accepted outcome trend |
| 7 | **Batch/off-peak** — non-interactive jobs at the 50% batch discount | `scripts/spend/README.md` + rule | share of API spend at batch rate |

---

## 6. Dashboard tabs

**Tab 3 — Waste signals** (team/EM, feeds the pillar-7 retro). KPI row: **cost per
accepted outcome** (headline; should fall over time), **rework burn**, cache-hit ratio,
unattributed share. Below: one chart per technique proxy (§5), each annotated with the
technique it validates — the retro reads the tab top-to-bottom as *"is the pack
working?"*.

**Tab 4 — ROI** (client/sponsor). Built on `roi_view`:

- **Headline ratio** for the selected period: *"€14,500 total spend → work estimated
  at 41 human-days (€20,500) → ROI 1.41 ⇒ 1 dev + AI ≈ 1.4 devs"*.
- **Evidence-tier band** — the ratio as a range weighted by tier, with a legend
  (calibration > pre-estimate > velocity > post-hoc).
- **Coverage indicator** — *"ROI computed over 34 of 41 closed tickets"*; tickets
  without estimates are excluded from the ratio but never hidden.
- **Per-ticket table** — estimate vs actual vs AI €, HDE, sortable; where bad
  estimates become visible, keeping the baseline honest.
- **Trend** — HDE per sprint.
- **Client export** — one button renders the current filter to a self-contained HTML
  one-pager (spend by source incl. flat-rate amortization, ROI band, coverage,
  methodology footnote). The artefact you hand a sponsor.

---

## 7. Error handling & honesty guards

| Case | Behaviour |
|---|---|
| Hook failure of any kind | log to `.usage-errors.log`, exit 0 — never break the session |
| Malformed transcript lines | skip line, count in `notes` |
| Unknown model in prices.json | cost 0 + flag; warning surfaces on Waste tab (no guessed prices, no silent undercount) |
| Missing ticket/branch | row kept with `ticket NULL` → explicit "unattributed" bucket |
| Double-fire / re-run / re-import | upserts on `session_id` / `(source, period_start, seat)` — no-ops |
| Ticket without estimate | excluded from ROI ratio, counted in coverage indicator |
| Open tickets | excluded until `closed` |
| Absurd actuals (< 0.1 human-day) | flagged for review, not allowed to produce a 40× HDE |
| Idle flat-rate seat | still amortizes — idle subscription cost is real cost |

---

## 8. Out of scope (this theme)

- **Cross-project consultancy benchmarks** — each bootstrapped project's DB is local;
  anonymized aggregation across clients is a later theme once ≥2 projects run this.
- Per-message storage (per-session sums only), worklog import from JIRA, Postgres,
  hosted dashboards, non-Claude per-token telemetry (Cursor/Copilot stay invoice-level).

---

## 9. Testing

Same pattern as the JIRA ledger: pure-Python units with fixtures, run by
`ai-governance.yml`.

- `parse_transcript.py` against fixture JSONLs: normal, malformed lines, unknown
  model, cache-heavy, empty session.
- Importers against fixture CSV / canned API JSON, including double-import idempotency.
- `roi_view` against a seeded fixture DB: mixed evidence tiers, missing estimates,
  open tickets, zero-actual flag.
- `seed.sql` gains synthetic `spend` + `tickets` rows → all four tabs render on a
  fresh clone.
- CI: one new job step for the above + the AGENTS.md-churn check (§5, technique 2).
