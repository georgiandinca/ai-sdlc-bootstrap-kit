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

To make AI usage measurable (pillar 7 — the dashboard and retro loop), every commit is classifiable as **human**, **AI**, or **mixed**. The dashboard's `commits` table and `collect_commits.py` implement this.

## Primary signal — git-ai line-level notes

**[git-ai](https://usegitai.com)** records exactly which lines an agent wrote, in git notes at **`refs/notes/ai`** (format `authorship/3.0.0`): an attestation block mapping files to `s_…` (AI session) / `h_…` (human) line ranges, a `---` divider, then JSON metadata (agent tool, model, author). It captures automatically via agent tool-call hooks and adds no git-hot-path overhead.

- Install (per developer endpoint, optional): `curl -sSL https://usegitai.com/install.sh | bash` then `git ai install-hooks`.
- Sync notes with the team: `git fetch origin 'refs/notes/*:refs/notes/*'` (git-ai pushes/fetches them automatically once installed).
- The collector reads these notes with plain `git notes --ref=ai show <sha>` — **the git-ai binary is not required on the machine running the dashboard.**

Per commit: **ai** (only AI lines), **human** (only human/untracked lines), **mixed** (both).

## Fallback — the `Co-Authored-By` trailer

Commits without a git-ai note (existing history, or tools without git-ai) are classified from the commit trailer: an AI `Co-Authored-By:` (name/email matching `anthropic`/`claude`/`copilot`/`cursor`/`windsurf`/`bot`) → **ai-assisted**; otherwise **human**. This is coarser (commit-level, not line-level) and is marked `source: trailer` in the dashboard.

## Reading it

`python3 dashboard/collect_commits.py` populates the `commits` table; the dashboard's **Commit attribution** tab shows AI/mixed/human volume next to the utilization **rework** rate — volume is never read alone. Deep defect-linkage (which bug fixed which AI-authored code) is Phase 4 (knowledge graph).
