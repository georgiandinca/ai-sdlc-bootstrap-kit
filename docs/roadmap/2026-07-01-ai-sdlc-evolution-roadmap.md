# AI-SDLC Bootstrap Kit — Evolution Roadmap

**Status:** approved · **Version:** 0.1 · **Author:** Georgian Dinca (+ AI) · **Created:** 2026-07-01 · **Last reviewed:** 2026-07-01

This roadmap sequences four improvements to the kit into buildable phases. It is a **decomposition artefact**, not a design: each phase below earns its own design spec → implementation plan → build cycle. Approve the *shape and order* here; the detail is deferred to per-phase specs.

---

## 1. Context

Four improvements were requested for the kit:

1. Improve onboarding by separating a **global** phase from a **per-seat** phase.
2. Add **hooks and scripts** that keep context in sync (pull, commit on code/docs) and are usable by **non-git-literate** seats (PO, PM, some QA), triggered at natural moments in a conversation.
3. Add a **knowledge / code-review graph** over both docs and code, with per-repo context isolation and a global (federated) view.
4. Add a **local dashboard** of project stats — AI vs mixed vs human commits, and per lines-of-code — for use in review/retro meetings.

The central finding from reviewing the current kit: **none of these are greenfield.** Each is the completion of an existing stub, and all four rest on the same four primitives. The kit already ships: `ONBOARDING.md` (a flat 7-step flow), `USER.md` (seat + comms prefs), five `playbook-<seat>` skills, `scripts/session/{start,sync,wrapup}.sh`, a `SessionStart` hook, a keyword-search `knowledge/ingest.py` stub with the `knowledge` MCP slot declared-but-disabled, and a `dashboard/` (Streamlit + SQLite) with a schema but no data pipeline.

### 1.1 Shared primitives

The phases are ordered by a small dependency set, because they reuse the same foundations:

- **The `USER.md` seat + git-comfort model** — who the operator is, which seat, and how much git to expose.
- **The session lifecycle moments** — named points in a working session where automation may fire.
- **The knowledge layer** — the queryable project memory over docs and code.
- **The commit-attribution convention** — how a change is marked AI / mixed / human.

Design against these primitives, not as four silos.

### 1.2 Best-practice grounding

The design choices below track the 2026 consensus on AI-augmented SDLC: a layered context hierarchy where a role is a *thin slice* (role prompt + global context + task instructions + retrieved snippets) rather than a monolithic dump; `SessionStart` stdout used to inject live repo state; commit on session-stop rather than per-edit; GraphRAG-over-code (entities + relationships) rather than flat chunks; and explicit, self-reported commit attribution paired with *quality* metrics to avoid a volume-only vanity board. The field's dominant failure mode is **verification debt / spec drift** — confident code that quietly solves the wrong problem — which the governance gates and a quality-paired dashboard exist to counter. Sources are listed in §5.

---

## 2. Phase 0 — Shared primitives *(enabling)*

**Goal.** Establish the foundations the other phases reuse. Small, but first.

**Deliverables.**
- Extend the `USER.md` schema with a **`git-comfort`** axis — `git-native` | `guided` | `hidden` — alongside the existing `seat`. This one field drives whether git is exposed or abstracted downstream.
- Document the **session lifecycle moments** as a named contract: `session-start`, `checkpoint` ("I'm done with X"), `decision-made`, `session-end`. Every hook binds to one of these.
- Ratify the **commit-attribution convention**: the `Co-Authored-By` trailer already emitted on AI commits is the baseline signal (AI / mixed / human per commit); `git-ai` (line-level attribution via git notes, agent self-reported) is the documented upgrade path.

**Acceptance signal.** `USER.md.example` carries the new field; a short `docs/ai-context/` note defines the moments and the attribution convention; nothing downstream is broken.

**Unblocks.** Phases 1, 2, 3.

---

## 3. Phase 1 — Onboarding: global + per-seat phasing

**Goal.** Turn the flat onboarding into two explicit phases so seat context is a *phase*, not a label.

**Depends on.** Phase 0 (`git-comfort`).

**Deliverables.**
- **Phase A (Global):** identity, workspace shape, trust tiers, and `git-comfort` — everyone, every seat.
- **Phase B (Seat):** load *only* the confirmed seat's playbook, wire that seat's MCP profile, and run a seat-specific "first task" mini-tutorial (PO drafts a story; Dev opens a branch; QA writes a test-plan stub).
- **Seat-switch** as a first-class action that re-runs Phase B only.
- **Progressive disclosure** via `.claude/rules/` matchers so task-scoped guidance loads only when relevant, keeping session context lean.

**Acceptance signal.** A new operator completes Global then Seat; switching seats re-runs only Phase B; `AGENTS.md` is not dumped wholesale at start.

---

## 4. Phase 2 — Conversational context-sync hooks

**Goal.** Bind git actions to conversational moments and hide git from non-dev seats.

**Depends on.** Phase 0 (moments + git-comfort); soft-depends on Phase 1 (seat known).

**Deliverables.**
- **Auto-sync on `session-start`:** the `SessionStart` hook runs `sync.sh` (clean-tree guarded) and reports in plain language ("Pulled 2 updates; you have 3 unsaved doc changes — save them?").
- **Intent-verbs wrapping git** for non-devs: "save my work" → commit+push; "get the latest" → pull; "send for review" → open PR. A thin skill/CLI wraps git; the operator never sees a rebase.
- **`Stop`-hook safety net:** at `session-end`, detect uncommitted doc changes and offer a checkpoint commit to a personal branch — so a non-dev cannot lose work by closing the terminal.
- **Role-aware behaviour** keyed off `git-comfort`: `git-native` stays git-native; `guided`/`hidden` get the abstracted verbs and auto-checkpoints.

**Acceptance signal.** A `hidden`-comfort PO can start a session, work, and "save" / "send for review" without typing a git command; a `git-native` Dev sees no behavioural change.

---

## 5. Phase 3 — Metrics dashboard

**Goal.** Populate the existing dashboard with AI / mixed / human commit stats and per-LOC breakdowns for retro meetings.

**Depends on.** Phase 0 (attribution convention). Independent of Phases 1–2 — a candidate to pull forward as an early quick win.

**Deliverables.**
- **Collector** parsing `git log` + `numstat` (+ git notes when `git-ai` is adopted) → the existing SQLite schema → read by the existing Streamlit app. Run from the `session-end` wrapup hook or a cron.
- **Classification** of each commit: human-only / AI-authored / mixed.
- **Retro metrics:** AI-authored %, mixed %, per-seat AI adoption, LOC-by-author-type over time.
- **Quality pairing (guardrail):** every volume metric is shown next to a quality metric (e.g. rework / defect rate on AI-touched code) so the board never becomes a "lines written" vanity metric. Full quality linkage (bug-fix → the AI code it fixed) is enriched by Phase 4.

**Acceptance signal.** `streamlit run` shows populated AI/mixed/human and per-LOC charts from real repo history, with at least one quality metric beside the volume metrics.

---

## 6. Phase 4 — Knowledge / code-review graph

**Goal.** Replace the keyword stub with a graph over docs *and* code, isolated per repo and queryable globally.

**Depends on.** No hard dependency; benefits from Phase 3 (dashboard quality metrics get richer once the graph links commits to the code they touch).

**Deliverables.**
- **Namespaced subgraphs:** one per code repo, one per docs tree, plus a shared **global overlay**. Queries run scoped (this repo) or federated (whole project) — matching the multi-repo posture in `AGENTS.md §2`.
- **Two ingestion pipelines** into the same graph: **docs** (frontmatter → nodes/edges — the frontmatter you already validate) and **code** (tree-sitter/AST → file / function / class / dependency structure).
- **Traceability edges** — the high-value payload: ADR → code modules that implement it → tests that cover it → story that requested it. This is the traceability QA and Architect already co-own, made queryable.
- **Local-first store** (e.g. an embedded graph or a SQLite-backed edge table, matching the dashboard's storage choice), exposed via the **already-declared-but-disabled `knowledge` MCP slot** under scoped-read.

**Acceptance signal.** The `knowledge` MCP answers a scoped query ("what implements ADR-0003 in repo X?") and a federated query across repos, grounded on ingested nodes with sources.

---

## 7. Dependencies and order

```
Phase 0 ──┬─► Phase 1 ──► Phase 2   (daily-driver UX)
          ├─► Phase 3   (quick win, independent)
          └─► Phase 4   (big lift) ◄── enriched by Phase 3
```

**Recommended order:** `0 → 1 → 2 → 3 → 4`. Phase 3 may be pulled forward to immediately after Phase 0 for an early, visible win.

---

## 8. Cross-cutting principles and risks

- **Verification debt / spec drift is the primary risk.** As agents do more, wire the dashboard's quality metrics into the retro so drift is caught. The dashboard is a drift alarm, not just a report.
- **git-comfort is the pivot** between dev and non-dev ergonomics — set once in Phase 0, honoured by Phases 1 and 2.
- **Attribution should be explicit, not heuristic.** Start from the `Co-Authored-By` trailer; upgrade to `git-ai` line-level notes rather than guessing from code patterns.
- **Anti-bloat holds** (kit principle): a rule, hook, or metric earns its place only by removing a recurring real question or a real loss.

---

## 9. What's next

Each phase becomes its own design spec (`docs/superpowers/specs/…` or `docs/roadmap/…`) and then an implementation plan. Immediate next step: drill into **Phase 1 — Onboarding global + per-seat phasing** via the brainstorming → writing-plans flow.
