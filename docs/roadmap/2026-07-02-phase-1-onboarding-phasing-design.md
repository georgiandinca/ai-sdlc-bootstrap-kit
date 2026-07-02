# Phase 1 — Onboarding Global + Per-Seat Phasing: Design

**Status:** approved · **Version:** 1.0 · **Author:** Georgian Dinca (+ AI) · **Created:** 2026-07-02 · **Last reviewed:** 2026-07-02

Design for Phase 1 of the [evolution roadmap](./2026-07-01-ai-sdlc-evolution-roadmap.md), built on top of [Phase 0](./2026-07-02-phase-0-shared-primitives-design.md) (branch `feat/phase-1-onboarding-phasing` stacks on `feat/phase-0-shared-primitives`). Phase 1 turns **seat** from a stored label into a real **phase**: onboarding splits into Global (Phase A) and Seat (Phase B), a `seat-profiles.json` manifest becomes the single source of per-seat data, and the SessionStart hook loads the seat's context live every session.

All mechanisms used are confirmed current Claude Code features (official docs): `.claude/rules/` with `paths:` frontmatter, `paths:`-scoped skills, nested `CLAUDE.md`/`@imports`, and SessionStart `additionalContext` injection. Scope selected: **roadmap-complete** (includes the per-seat MCP profile).

---

## 1. Locked decisions

| Decision | Choice |
|---|---|
| Scope | Roadmap-complete: A/B split, seat-switch, live seat context, `.claude/rules/`, first-task tutorial, per-seat MCP profile |
| Per-seat data home | **`scripts/session/seat-profiles.json`** — single source; Phase 0's git-comfort default table **moves out of `ONBOARDING.md` into it** |
| Seat source of truth at runtime | **`USER.md`** (start.sh reads it; falls back to the personal-env `SESSION_SEAT`) |
| Progressive disclosure | Two complements: SessionStart injects seat identity + playbook (role side); `.claude/rules/` `paths`-scoped to artefact areas (artefact side) |
| Manifest validator + CI gate | **Include** (`validate-seat-profiles.py`, wired into governance gate + pre-commit), mirroring Phase 0 |

---

## 2. Component 1 — `ONBOARDING.md` restructured into Phase A / Phase B

The current linear Steps 0–7 are regrouped (no capability removed, only re-sequenced and labelled):

**Phase A — Global (every seat):**
- Step 0 — `USER.md` gate (unchanged).
- A1 — OS detect (was Step 1).
- A2 — prerequisites (was Step 2). **Baseline for everyone** = Git, Python 3, pre-commit. **Seat-optional** = Node ≥22, pandoc (a `hidden`-comfort Product operator is not walked through dev tooling they won't use; installed later if their seat needs it).
- A3 — activate repo hooks (was Step 3).
- A4 — seed knowledge, optional (was Step 4).
- A5 — identity: name + email (was Step 5.1).
- A6 — communication preferences (was Step 5.3).

**Phase B — Seat (per-seat):**
- B1 — seat selection (was Step 5.2).
- B2 — git-comfort (was Step 5.2b); **the default is now read from `seat-profiles.json`**, not a hard-coded table.
- B3 — **load the seat's playbook**: announce the seat and invoke `playbook-<seat>`.
- B4 — **activate the seat's MCP profile**: surface the connectors from the seat's `seat-profiles.json` entry.
- B5 — **seat first-task tutorial**: offer the seat's `first_task`.

**Finalize:** write `USER.md` (identity, seat, git-comfort, comms prefs) → confirm → proceed to `AGENTS.md` §0.

Seat-switch (Component 5) re-runs **Phase B only**.

## 3. Component 2 — `scripts/session/seat-profiles.json` (+ validator)

The single machine-readable source of per-seat data (parallels Phase 0's `moments.json`).

Per-seat fields: `id`, `git_comfort_default`, `playbook`, `connectors`, `first_task`.

```json
{
  "version": 1,
  "seats": [
    { "id": "Architect", "git_comfort_default": "git-native", "playbook": "playbook-architect",
      "connectors": ["issue-tracker", "docs-wiki", "knowledge"],
      "first_task": "Record a first ADR stub at docs/architecture/decisions/ADR-0001-<topic>.md." },
    { "id": "EM", "git_comfort_default": "git-native", "playbook": "playbook-em",
      "connectors": ["issue-tracker", "docs-wiki", "knowledge"],
      "first_task": "Draft an engineering-spec stub, or record the code repos in AGENTS.md §2." },
    { "id": "Product", "git_comfort_default": "hidden", "playbook": "playbook-product",
      "connectors": ["issue-tracker", "docs-wiki"],
      "first_task": "Draft a first user story with acceptance criteria." },
    { "id": "Developer", "git_comfort_default": "git-native", "playbook": "playbook-dev",
      "connectors": ["issue-tracker", "knowledge", "context7"],
      "first_task": "Open a feature branch for your first change." },
    { "id": "QA", "git_comfort_default": "guided", "playbook": "playbook-qa",
      "connectors": ["issue-tracker", "knowledge"],
      "first_task": "Write a test-plan stub with one traceability entry." }
  ]
}
```

**`scripts/validate-seat-profiles.py`** (stdlib only; same shape/exit contract as Phase 0's validators):
- valid JSON with a non-empty `seats` list;
- each seat has all five fields;
- `id` ∈ {Architect, EM, Product, Developer, QA}, all five present, unique;
- `git_comfort_default` ∈ {git-native, guided, hidden};
- the `playbook` skill directory exists at `.claude/skills/<playbook>/`;
- every `connectors` entry is a key in `.mcp.json`'s `mcpServers`;
- resolves paths against `repo_root = Path(__file__).resolve().parent.parent` (i.e. `template/`), like the sibling validators.

Wired into `.gitlab-ci.yml` governance gate + `template/.pre-commit-config.yaml`. Unit-tested with stdlib `unittest`.

## 4. Component 3 — Live seat context (SessionStart injection)

Extend `scripts/session/start.sh` to:
- read **Seat** and **Git comfort** from `USER.md` (grep; fall back to personal-env `SESSION_SEAT`);
- look up the seat's `playbook` and `connectors` in `seat-profiles.json` (via a small `python3 -c` read, no jq dependency);
- print a **seat-context block** to stdout (which becomes session context): *"Operating as `<seat>` (git-comfort `<level>`). Load `playbook-<seat>`. Seat connectors: `<list>`."*

Remains read-only, always exits 0, and is additive to the existing status line + session-ritual text (Phase 2 layers sync behaviour on top).

## 5. Component 4 — `.claude/rules/` (artefact-scoped progressive disclosure)

`.claude/rules/` scopes by **file path**, not by role, so rules encode **artefact-area** guidance that loads only when those artefacts are touched. Ship three representative rules under `template/.claude/rules/` (frontmatter uses the `paths:` schema — these live under `.claude/`, not `docs/`, so the governance frontmatter contract does not apply):

| Rule file | `paths:` | Guidance |
|---|---|---|
| `adr-conventions.md` | `docs/architecture/decisions/**` | ADR numbering, status, decision/rationale shape |
| `knowledge-sources.md` | `docs/knowledge/**` | source frontmatter, trust tiers, ingestion note |
| `test-artefacts.md` | `docs/**/test-plan*`, `tests/**` | test-plan shape, traceability expectations |

Projects extend the set. These complement (don't replace) the role playbooks.

## 6. Component 5 — Seat-switch command

`scripts/session/switch-seat.sh [seat]`:
- resolves the new seat (arg or prompt), looks up its `git_comfort_default` from `seat-profiles.json`;
- updates the `- **Seat:**` and `- **Git comfort:**` lines in `USER.md` (via `sed`);
- prints confirmation + instructs the agent to load `playbook-<new-seat>`.
- Does **not** touch Phase A (identity/env). It is the runtime realisation of "seat-switch re-runs Phase B only."

## 7. Component 6 — Per-seat first-task tutorial

Content lives in `seat-profiles.json` (`first_task`); ONBOARDING Phase B (B5) offers it. No separate file — the manifest is the source, onboarding is the driver.

## 8. Component 7 — Per-seat MCP profile

The `connectors` array in `seat-profiles.json` is the per-seat MCP profile (grounded in `AGENTS.md §4.3`'s scoped-write posture). ONBOARDING B4 and the SessionStart block surface it; the validator checks each connector exists in `.mcp.json`. It becomes live scoping the moment a project enables real connectors — no inert prose.

## 9. Supporting — `AGENTS.md` pointers

- §0 (startup) — note onboarding runs as **Phase A (Global) → Phase B (Seat)**, and that seat/git-comfort load live each session.
- §5 (seats) — point at `scripts/session/seat-profiles.json` as the per-seat data source (git-comfort default, playbook, connectors, first task).

Minimal pointers only; `CLAUDE.md` stays a pure pointer.

## 10. Data flow

```
seat-profiles.json ──┬─► ONBOARDING Phase B (git-comfort default, connectors, first_task)
                     ├─► start.sh SessionStart block (seat → playbook + connectors)
                     └─► switch-seat.sh (new seat → git-comfort default → USER.md)
USER.md (seat, git-comfort) ──► start.sh reads it each session ──► seat context injected
.claude/rules/*  ──(paths match)──► artefact guidance loads on demand
validate-seat-profiles.py ──► CI gate + pre-commit
```

## 11. Acceptance criteria

1. `ONBOARDING.md` is organised as Phase A (Global) and Phase B (Seat); every current step is preserved under the right phase; git-comfort default is read from `seat-profiles.json` (table removed from ONBOARDING).
2. `scripts/session/seat-profiles.json` exists with all five seats and validates.
3. `scripts/validate-seat-profiles.py` passes and is wired into the governance gate + pre-commit; unit tests pass.
4. `start.sh` prints a seat-context block derived from `USER.md` + `seat-profiles.json`, and still exits 0 with no `USER.md`.
5. `scripts/session/switch-seat.sh` updates `USER.md`'s seat + git-comfort from a chosen seat.
6. Three `.claude/rules/*.md` exist with valid `paths:` frontmatter.
7. `AGENTS.md` carries the two pointers; `CLAUDE.md` unchanged.
8. Full governance gate green.

## 12. Out of scope (deferred)

- Runtime git automation driven by git-comfort (auto-sync, checkpoint, intent-verbs) → **Phase 2**.
- The `checkpoint`/`record-decision` handlers and `Stop`-hook wiring → **Phase 2**.
- Real MCP connector configuration (URLs/auth) → per-project, not the kit.
- Dashboard / knowledge graph → Phases 3–4.

## 13. Decisions log

- Scope: roadmap-complete (incl. per-seat MCP profile as `connectors` in the manifest).
- Per-seat data consolidated in `seat-profiles.json`; git-comfort default table moved there from `ONBOARDING.md`.
- `start.sh` reads seat/git-comfort from `USER.md` (primary), personal env fallback.
- `.claude/rules/` scoped to artefact areas (three representative rules).
