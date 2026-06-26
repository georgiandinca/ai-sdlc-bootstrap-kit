---
title: "Human methodology & continuous improvement"
status: approved
owner: EM
author: AI-SDLC Bootstrap Kit
created: 2026-06-26
classification: internal
last-reviewed: 2026-06-26
ai-trust: working
---

# Human methodology & continuous improvement (pillar 7)

AI agents accelerate the work; **humans own the loop that keeps the work good and the cost honest.** This pillar is the feedback machine: observe how AI is used, judge quality and cost, and feed improvements back into the rules (pillar 3), the skills (pillar 6), and the knowledge (pillar 5).

## The loop

```
   observe ──▶ measure ──▶ review (retro) ──▶ improve ──▶ observe …
   (dashboard)  (metrics)   (humans decide)   (PRs to rules/skills/knowledge)
```

1. **Observe** — the AI-utilization dashboard (`../../dashboard/`) records sessions: seat, task, tokens/cost, accept/reject, rework.
2. **Measure** — a small, stable set of metrics (below). Resist metric bloat.
3. **Review** — a recurring human retro reads the metrics and the qualitative signal.
4. **Improve** — each decision becomes a concrete change: a sharper `description` on a skill, a new knowledge source, a tightened rule, a removed rule that wasn't earning its keep.

## Metrics that matter (keep it small)

| Metric | Why | Source |
|---|---|---|
| **AI-assisted throughput** | Is AI actually moving work? | dashboard sessions ↔ tracker items |
| **Acceptance rate** | Fraction of AI output kept vs. discarded/heavily reworked | dashboard `outcome` |
| **Rework rate** | Output that shipped then needed fixing | dashboard + tracker |
| **Cost per accepted unit** | The honest cost — tokens/$ per kept change | dashboard `tokens`/`cost` |
| **Grounding rate** | Share of answers grounded on the knowledge layer vs. memory | review sampling |
| **Gate health** | CI governance-gate pass rate, time-to-green | CI |

These map to the board's **"HUMAN — Methodology / Cost Improvement"** note: the point of measuring is to drive *cost* and *quality* improvement, not surveillance.

## Retro cadence & agenda

- **Cadence:** per sprint or per milestone (match your delivery rhythm).
- **Agenda:**
  1. Read the six metrics — what moved, what didn't?
  2. Where did AI help most / least this period? (one example each)
  3. Did any seat hit a rule that slowed it without adding safety? (anti-bloat candidate)
  4. What knowledge was missing when an agent guessed? (→ add a source)
  5. Which skill failed to trigger, or over-triggered? (→ `skill-creator`)
  6. Pick **at most three** improvements; open a PR for each.

## What "human in the loop" means here

- **Promotion is human.** Drafts → canonical, `under-review` → `approved` (pillar 3).
- **Sign-off is human.** Quality gates, releases, merges to protected branches.
- **Curation is human.** What enters the knowledge layer, and what gets pruned.
- **The rules are the team's.** This methodology is itself versioned — change it via PR when a retro says so.

> Continuous improvement that never changes anything is theatre. Every retro should leave a diff.
