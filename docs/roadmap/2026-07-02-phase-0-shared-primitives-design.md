# Phase 0 — Shared Primitives: Design

**Status:** approved · **Version:** 1.0 · **Author:** Georgian Dinca (+ AI) · **Created:** 2026-07-02 · **Last reviewed:** 2026-07-02

Design for Phase 0 of the [evolution roadmap](./2026-07-01-ai-sdlc-evolution-roadmap.md). Phase 0 lays down the three primitives the later phases import: the **`git-comfort`** axis, the **session lifecycle moments** (definition + machine-readable manifest), and the **commit-attribution convention**. All changes live under `template/` so every bootstrapped project inherits them.

---

## 1. Locked decisions

From brainstorming:

| Decision | Choice |
|---|---|
| Phase 0 concreteness | Definitions **+ live git-comfort in onboarding + machine-readable moments manifest** |
| `git-comfort` levels | Three: `git-native` \| `guided` \| `hidden` |
| How set | **Seat-suggested default, user confirms/changes** |
| Manifest format | **JSON** (`scripts/session/moments.json`) |
| Manifest validator + CI gate | **Include** (`validate-moments.py`, wired into governance gate + pre-commit) |
| Attribution doc | **Own file** (`docs/ai-context/attribution.md`) |
| `AGENTS.md` pointers | **Include** (minimal references to the new primitives) |

---

## 2. Component A — `git-comfort`

The pivot primitive: one value that decides how much git a seat sees. Consumed by Phases 1–2; **captured only** in Phase 0.

**Semantics**
- `git-native` — full git; the operator drives branches/commits/PRs directly.
- `guided` — intent-verbs with brief explanations ("saving your work — that's a commit + push").
- `hidden` — git fully abstracted behind intent-verbs (save / get latest / send for review); the operator never sees git mechanics.

**File changes**
1. `template/USER.md.example` — add under **Identity**:
   ```markdown
   - **Git comfort:** <git-native | guided | hidden>
   ```
2. `template/ONBOARDING.md` — insert Step 5.2b immediately after seat selection:
   > "Based on your seat I'd set your **git-comfort** to `<default>` — `<one-line explanation>`. Keep it, or change it? (git-native / guided / hidden)"

   Seat → suggested default:

   | Seat | Default |
   |---|---|
   | Architect | `git-native` |
   | EM | `git-native` |
   | Developer | `git-native` |
   | QA | `guided` |
   | Product (PO/PM) | `hidden` |
   | Custom seat | ask explicitly (no default) |

3. `template/ONBOARDING.md` Step 6 — `git-comfort` is written into `USER.md` alongside seat.

**Storage & consumption.** `USER.md` is the human-readable source of truth. Runtime consumption (mirroring to the personal env, driving hook behaviour) is **out of scope for Phase 0** — Phase 2 owns it. Phase 0 only guarantees the value is captured and stored.

---

## 3. Component B — session lifecycle moments

Two artefacts: a human doc and a machine manifest.

### 3.1 `template/docs/ai-context/lifecycle-moments.md` (new)

Carries the required frontmatter contract (`title`, `status`, `owner`, `classification`, `ai-trust`; recommended `author`, `created`, `last-reviewed`) so the frontmatter validator passes. Defines the four moments in prose, points at `scripts/session/moments.json` as the machine contract, and explains the `behavior_by_comfort` model (`auto` = do it and report; `offer` = ask first; `skip` = don't).

### 3.2 `template/scripts/session/moments.json` (new)

The contract Phases 2–3 import. Per-moment fields: `id`, `trigger` (conversational cue), `handler` (script path), `hook` (Claude Code event or `null`), `status` (`active` | `planned`), `behavior_by_comfort` (per level: `auto` | `offer` | `skip`).

The four moments:

| id | trigger | handler | hook | status | native / guided / hidden |
|---|---|---|---|---|---|
| `session-start` | a new working session begins | `scripts/session/start.sh` (+`sync.sh`) | `SessionStart` | active | offer / offer / **auto** |
| `checkpoint` | "I'm done with X" / topic shift | `scripts/session/checkpoint.sh` *(Phase 2)* | `null` | planned | offer / offer / **auto** |
| `decision-made` | a decision/ADR is reached | `scripts/session/record-decision.sh` *(Phase 2)* | `null` | planned | offer / offer / offer |
| `session-end` | the operator is wrapping up | `scripts/session/wrapup.sh` | `Stop` *(P2 wires)* | active | offer / offer / **auto** |

Full manifest:
```json
{
  "version": 1,
  "moments": [
    {
      "id": "session-start",
      "trigger": "A new working session begins.",
      "handler": "scripts/session/start.sh",
      "hook": "SessionStart",
      "status": "active",
      "behavior_by_comfort": { "git-native": "offer", "guided": "offer", "hidden": "auto" }
    },
    {
      "id": "checkpoint",
      "trigger": "The operator finishes a topic or says 'I'm done with X'.",
      "handler": "scripts/session/checkpoint.sh",
      "hook": null,
      "status": "planned",
      "behavior_by_comfort": { "git-native": "offer", "guided": "offer", "hidden": "auto" }
    },
    {
      "id": "decision-made",
      "trigger": "A decision or ADR is reached in conversation.",
      "handler": "scripts/session/record-decision.sh",
      "hook": null,
      "status": "planned",
      "behavior_by_comfort": { "git-native": "offer", "guided": "offer", "hidden": "offer" }
    },
    {
      "id": "session-end",
      "trigger": "The operator signals they are wrapping up.",
      "handler": "scripts/session/wrapup.sh",
      "hook": "Stop",
      "status": "active",
      "behavior_by_comfort": { "git-native": "offer", "guided": "offer", "hidden": "auto" }
    }
  ]
}
```

`status: planned` marks handlers created in Phase 2; the validator does not require those files to exist yet. `session-end`'s handler exists (`wrapup.sh`) but its `Stop`-hook wiring is Phase 2 — the `hook` field records the intended binding as contract.

---

## 4. Component C — attribution convention

### `template/docs/ai-context/attribution.md` (new)

Frontmatter-compliant. Ratifies:
- **Baseline signal:** AI-assisted commits carry a **`Co-Authored-By: <agent> <email>`** trailer. Tool-agnostic — Claude Code, Copilot, and Cursor all comply, so classification does not depend on any one tool.
- **Three classes:** `human` (no AI trailer), `AI-authored` (agent-made commit carrying the trailer), `mixed` (AI trailer + subsequent human edits). The **precise `mixed` rule is deferred to Phase 3**'s classifier; Phase 0 only fixes the vocabulary and the trailer convention.
- **Upgrade path:** `git-ai` (line-level attribution stored in git notes, agent self-reported) for when per-line precision is needed. Phase 0 does **not** install git-ai or build any classifier.

---

## 5. Validation & governance

### `template/scripts/validate-moments.py` (new)

Mirrors the shape of `validate-skills.py` / `validate-frontmatter.py`:
- Loads `scripts/session/moments.json`; fails on invalid JSON.
- Requires each moment to carry `id`, `trigger`, `handler`, `hook`, `status`, `behavior_by_comfort`.
- Enforces enums: `status` ∈ {`active`, `planned`}; every `behavior_by_comfort` value ∈ {`auto`, `offer`, `skip`}; keys exactly {`git-native`, `guided`, `hidden`}.
- Requires the `handler` file to exist **only when `status == "active"`**.
- Requires unique `id`s.
- Exit 0 if valid, 1 otherwise (same contract as the sibling validators).

**Wiring**
- `.gitlab-ci.yml` governance gate — add a line: `python3 template/scripts/validate-moments.py`.
- `template/.pre-commit-config.yaml` — add a hook running the validator when `scripts/session/moments.json` changes.

---

## 6. `AGENTS.md` pointers

Minimal references so the canonical brief points at the new primitives (canonical rule: content lives in `AGENTS.md`, `CLAUDE.md` stays a pointer):
- **Seat area (§5):** note that each operator also has a **`git-comfort`** level in `USER.md`, and that it governs how git surfaces to that seat.
- **Trust/attribution area (§4):** a short subsection referencing `docs/ai-context/attribution.md` for the commit-attribution convention.
- **Session/workspace area:** a pointer to `docs/ai-context/lifecycle-moments.md` and `scripts/session/moments.json` as the lifecycle-moments contract.

Each pointer is one or two lines; no behavioural rules are added to `AGENTS.md` in Phase 0.

---

## 7. Data flow

```
ONBOARDING (Step 5.2b) ──► git-comfort ──► USER.md          (captured; consumed in Phase 2)
lifecycle-moments.md ◄──describes──► moments.json           (contract; imported in Phases 2–3)
attribution.md ──► convention ──► Phase 3 commit classifier (documented; built in Phase 3)
validate-moments.py ──► CI gate + pre-commit                (keeps moments.json honest)
AGENTS.md ──► pointers ──► the three primitives             (discoverability)
```

---

## 8. Acceptance criteria

1. `template/USER.md.example` carries the `Git comfort:` field with the three-value enum.
2. `template/ONBOARDING.md` captures git-comfort (seat-suggested default, confirm/change) and writes it to `USER.md` at Step 6.
3. `template/scripts/session/moments.json` exists with all four moments and validates.
4. `template/scripts/validate-moments.py` passes on the committed manifest and is wired into both the `.gitlab-ci.yml` governance gate and `template/.pre-commit-config.yaml`.
5. `template/docs/ai-context/lifecycle-moments.md` and `attribution.md` exist and pass the frontmatter validator.
6. `AGENTS.md` carries the three minimal pointers; `CLAUDE.md` remains a pure pointer.
7. CI governance stage is green.

---

## 9. Out of scope (deferred)

- Runtime consumption of `git-comfort` (mirroring to personal env, driving hook behaviour) → **Phase 2**.
- The `checkpoint.sh` and `record-decision.sh` handlers, and `Stop`-hook wiring → **Phase 2**.
- Intent-verb git wrappers → **Phase 2**.
- The commit classifier and the precise `mixed` rule → **Phase 3**.
- Installing `git-ai` → later, if/when line-level precision is needed.

---

## 10. Decisions log

- **Concreteness:** most concrete rung — definitions + live onboarding capture + JSON manifest.
- **git-comfort:** three levels, seat-suggested with user confirm.
- **Manifest:** JSON, Python-native, jq-optional for bash.
- **Validator, attribution doc, AGENTS.md pointers:** all three included.
