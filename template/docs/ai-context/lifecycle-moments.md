---
title: "Session lifecycle moments"
status: approved
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-07-02
classification: internal
last-reviewed: 2026-07-02
ai-trust: working
---

# Session lifecycle moments

A **lifecycle moment** is a natural point in a working session where the framework may act on the operator's behalf — sync the repo, checkpoint work, record a decision, or wrap up. Binding automation to *moments* (not to git commands) is what lets non-git-literate seats work safely: the operator signals intent in conversation, and the framework does the git.

The machine-readable contract is [`scripts/session/moments.json`](../../scripts/session/moments.json); this document is its human companion. Phases 2–3 of the evolution roadmap import the manifest to fire hooks and classify work. Keep the two in sync — the `validate-moments.py` gate enforces the manifest's shape.

## The four moments

| Moment | Fires when | Handler | Status |
|---|---|---|---|
| `session-start` | a new working session begins | `scripts/session/start.sh` (+ `sync.sh`) | active |
| `checkpoint` | the operator finishes a topic / says "I'm done with X" | `scripts/session/checkpoint.sh` | planned (Phase 2) |
| `decision-made` | a decision or ADR is reached in conversation | `scripts/session/record-decision.sh` | planned (Phase 2) |
| `session-end` | the operator signals they are wrapping up | `scripts/session/wrapup.sh` | active |

## Behaviour by git-comfort

Each moment declares a behaviour per `git-comfort` level (recorded in `USER.md`):

- **`auto`** — the framework performs the action and reports it in plain language.
- **`offer`** — the framework asks first, then acts on agreement.
- **`skip`** — the framework does nothing for this level.

The intent: `hidden` operators (typically Product) get `auto` sync / checkpoint / wrap-up so they never lose work or think about git; `git-native` operators get `offer` so nothing happens behind their back.

## The `status` field

`status: planned` marks moments whose handler is introduced in a later phase. The `session-end` handler exists today (`wrapup.sh`); its `Stop`-hook binding is wired in Phase 2. The `validate-moments.py` gate only requires a handler file to exist for `active` moments.
