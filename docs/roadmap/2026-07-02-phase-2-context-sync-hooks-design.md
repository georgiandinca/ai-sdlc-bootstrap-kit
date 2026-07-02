# Phase 2 — Conversational Context-Sync Hooks: Design

**Status:** approved · **Version:** 1.0 · **Author:** Georgian Dinca (+ AI) · **Created:** 2026-07-02 · **Last reviewed:** 2026-07-02

Design for Phase 2 of the [evolution roadmap](./2026-07-01-ai-sdlc-evolution-roadmap.md), built on Phases 0–1 (branch `feat/phase-2-context-sync-hooks` off `main` after both merged). Phase 2 adds the **runtime git automation** that consumes the primitives: git-comfort-aware auto-sync, the two `planned` moment handlers, intent-verbs for non-git seats, and safety nets — so a `hidden`-comfort operator (PO/PM) never touches git and never loses work.

Hook semantics are docs-verified (official Claude Code docs): `SessionStart` (once, injects context, can run commands), `Stop` (**every turn**, injects context, no prompt), `SessionEnd` (once at termination, **non-interactive**, cleanup/auto-save only). This corrects the roadmap's "Stop-hook safety net": wrapping-up is **conversational**, the end-of-session safety net is **`SessionEnd`** (auto-commit, can't prompt), and `Stop` is only a **debounced** reminder.

---

## 1. Locked decisions

| Decision | Choice |
|---|---|
| Scope | Roadmap-complete-plus: auto-sync + handlers + intent-verbs + SessionEnd safety net + debounced Stop reminder |
| Intent-verbs mechanism | A new invokable **`git-verbs` skill** (portable, agentskills.io-conformant), not context injection |
| checkpoint / auto-save branch policy | **Never commit to a protected branch** — auto-create a personal branch (reuse `wrapup.sh` logic) |
| Stop reminder | Debounced to **once / 10 min**, guided+hidden only, only when uncommitted changes exist, state in a git-ignored file |
| Shared logic | A small **`scripts/session/lib.sh`** (read git-comfort/seat, look up a moment's `behavior_by_comfort`) |

---

## 2. Component 1 — git-comfort-aware auto-sync (`start.sh`)

Extend `scripts/session/start.sh` (SessionStart). It already fetches and computes `behind`/`ahead`. Add: read the operator's git-comfort and the `session-start` moment's `behavior_by_comfort` (via `lib.sh`):
- **`hidden` → `auto`:** if behind and tree clean, run `sync.sh` and report ("Pulled 2 updates."). `sync.sh`'s dirty-tree guard keeps it safe.
- **`guided` / `git-native` → `offer`:** report state and inject an offer ("You're 2 behind — want me to pull?").
Stays read-only except the guarded pull; always exits 0.

## 3. Component 2 — `checkpoint.sh` ("save my work" / `checkpoint` moment)

New `scripts/session/checkpoint.sh`: stage → commit → push, with a message (arg, or a generated `checkpoint: <summary>`). **Never commits to a protected branch** — if on `main`/`master`, create a personal branch first (same logic as `wrapup.sh`). **No PR.** Usage: `checkpoint.sh [--seat <seat>] ["message"] [path…]`. Flips `moments.json` `checkpoint` → `status: active`.

## 4. Component 3 — `record-decision.sh` (`decision-made` moment)

New `scripts/session/record-decision.sh "<title>"`: computes the next ADR number, writes `docs/architecture/decisions/ADR-<NNNN>-<slug>.md` with the frontmatter contract + **Context / Decision / Consequences** skeleton (per the Phase 1 `adr-conventions` rule), and commits it (branch-safe like checkpoint). Flips `moments.json` `decision-made` → `active`.

## 5. Component 4 — the `git-verbs` skill

New invokable skill `template/.claude/skills/git-verbs/SKILL.md` (agentskills.io-conformant — validated by `validate-skills.py`). Maps intent → script and states *when* to use verbs:

| Verb | Script | Meaning |
|---|---|---|
| "get the latest" | `sync.sh` | ff-pull |
| "save my work" | `checkpoint.sh` | commit + push, no PR |
| "send for review" | `wrapup.sh` | commit + push + MR |

Description triggers on save/sync/review intent. The skill says: **`git-native` seats use raw git; `guided`/`hidden` seats use these verbs.** `start.sh` points guided/hidden operators at the skill in its seat-context block.

## 6. Component 5 — SessionEnd safety net

New `scripts/session/auto-save.sh` + a `SessionEnd` hook in `settings.json`. **Non-interactive** (SessionEnd cannot prompt): for **`hidden`** comfort only, if there are uncommitted changes at termination, commit them to a personal branch (never protected) with an `auto-save: session end` message so nothing is lost. Other comforts → no-op, exit 0. New `moments.json` moment **`session-terminated`** (hook `SessionEnd`, `behavior_by_comfort` = `{git-native: skip, guided: skip, hidden: auto}`).

## 7. Component 6 — debounced Stop reminder

New `scripts/session/stop.sh` + a `Stop` hook. `Stop` fires every turn, so guard hard: inject a one-line reminder ("You have unsaved work — say *save my work* to checkpoint it.") **only when** (uncommitted changes exist) AND (comfort ∈ {guided, hidden}) AND (last reminder > **600 s** ago). Debounce state in a git-ignored file (`.git/.sdlc-stop-state`; hooks may write under `.git/`). `git-native` → never. New moment **`uncommitted-reminder`** (hook `Stop`, `{git-native: skip, guided: offer, hidden: offer}`).

## 8. Component 7 — `moments.json` corrections + growth (4 → 6)

| moment | change |
|---|---|
| `checkpoint` | `status`: planned → **active** (handler now exists) |
| `decision-made` | `status`: planned → **active** |
| `session-end` | `hook`: `"Stop"` → **`null`** (conversational wrapping-up); `hidden` behavior `auto` → **`offer`** (auto-opening an MR every session is too aggressive; the SessionEnd net covers "don't lose work") |
| `session-terminated` | **new**: hook `SessionEnd`, active, handler `auto-save.sh`, `{skip, skip, auto}` |
| `uncommitted-reminder` | **new**: hook `Stop`, active, handler `stop.sh`, `{skip, offer, offer}` |

`validate-moments.py` still enforces the manifest (all new `active` handlers must exist on disk).

## 9. Component 8 — shared `scripts/session/lib.sh`

Small sourceable helper used by the new scripts (DRY): `sdlc_repo_root`, `sdlc_git_comfort` (grep `USER.md`, fallback `SESSION_GIT_COMFORT`/unset), `sdlc_seat`, and `sdlc_moment_behavior <moment-id> <comfort>` (reads `moments.json` via `python3`, echoes `auto|offer|skip`). Keeps comfort/behavior logic in one tested place.

## 10. Supporting

- **`settings.json`:** add `SessionEnd` (→ `auto-save.sh`) and `Stop` (→ `stop.sh`) hooks alongside the existing `SessionStart`.
- **`AGENTS.md`:** one-line pointer to the `git-verbs` skill in the MCP/session area; `CLAUDE.md` untouched.
- **Tests:** `lib.sh` behavior lookup + `checkpoint.sh` / `record-decision.sh` / `auto-save.sh` / `stop.sh` exercised via functional tests in temp git repos (RED/GREEN); `validate-moments.py` + `validate-skills.py` pass on the updated manifest + new skill.

## 11. Data flow

```
USER.md (git-comfort) + moments.json (behavior_by_comfort) ──► lib.sh
  lib.sh ──► start.sh (SessionStart): auto-sync hidden / offer others
          ─► checkpoint.sh / record-decision.sh (conversational, comfort-aware)
          ─► auto-save.sh (SessionEnd): hidden-only non-interactive save
          ─► stop.sh (Stop): debounced reminder for guided/hidden
git-verbs skill ──► agent maps "save/get latest/send for review" → scripts
settings.json ──► wires SessionStart + SessionEnd + Stop
```

## 12. Acceptance criteria

1. `start.sh` auto-pulls for `hidden` (clean+behind) and offers for others; still exits 0 with no `USER.md`.
2. `checkpoint.sh` commits+pushes without a PR and never on a protected branch (branches off `main`).
3. `record-decision.sh` writes a numbered, frontmatter-valid ADR skeleton and commits it.
4. `git-verbs` skill exists and passes `validate-skills.py`.
5. `auto-save.sh` (SessionEnd) commits uncommitted work to a personal branch for `hidden` only, non-interactively; no-op otherwise.
6. `stop.sh` reminds only for guided/hidden, only with uncommitted changes, at most once/10 min.
7. `moments.json` has 6 moments with the corrections above and passes `validate-moments.py`; `settings.json` wires all three hooks.
8. Full governance gate green.

## 13. Out of scope (deferred)

- Metrics dashboard (Phase 3) and knowledge graph (Phase 4).
- Real MCP connector configuration (per project).
- Non-git checkpointing of external tools (issue tracker / wiki) — the MCP posture already covers those.

## 14. Decisions log

- Scope: roadmap-complete-plus (incl. debounced Stop reminder).
- Intent-verbs: a portable `git-verbs` skill, not context injection.
- checkpoint/auto-save never touch a protected branch.
- Stop debounce: once / 600 s, guided+hidden, uncommitted-only.
- Shared `lib.sh` for comfort/behavior reads.
- Corrected the roadmap's Stop-hook safety net → SessionEnd (non-interactive) + conversational wrapping-up.
