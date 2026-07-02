---
title: "Commit-attribution convention"
status: approved
owner: EM
author: AI-SDLC Bootstrap Kit
created: 2026-07-02
classification: internal
last-reviewed: 2026-07-02
ai-trust: working
---

# Commit-attribution convention

To make AI usage measurable (pillar 7 — the dashboard and retro loop), every commit is classifiable as **human**, **AI-authored**, or **mixed**. This document fixes the convention; the classifier that consumes it is built in Phase 3 of the evolution roadmap.

## Baseline signal — the `Co-Authored-By` trailer

An AI-assisted commit carries a trailer naming the agent:

```
Co-Authored-By: <Agent Name> <email>
```

This is **tool-agnostic** — Claude Code, GitHub Copilot, and Cursor all emit or support this trailer — so classification never depends on a single vendor. A commit with no AI trailer is treated as **human**.

## The three classes

| Class | Rule |
|---|---|
| **human** | No AI `Co-Authored-By` trailer. |
| **AI-authored** | An agent produced the commit and it carries the trailer. |
| **mixed** | AI-produced content later edited by a human. |

> The precise, reproducible rule for **mixed** (how much human editing tips a commit from AI-authored to mixed) is defined in Phase 3, where the classifier lives. Phase 0 fixes only the vocabulary and the trailer convention.

## Upgrade path — line-level attribution

When per-commit granularity is not enough, the convention upgrades to **`git-ai`** (git-ai-project): agents self-report exactly which lines they wrote, stored in **git notes** without rewriting history, viewable via `git log --show-notes=ai`. Phase 0 does **not** install `git-ai` or build any classifier — it only records this as the sanctioned path to line-level precision.
