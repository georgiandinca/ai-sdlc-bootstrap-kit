---
title: "The AI-augmented SDLC framework — seven pillars"
status: approved
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-06-26
classification: internal
last-reviewed: 2026-06-26
ai-trust: working
---

# The AI-augmented SDLC framework — seven pillars

This project treats AI agents as **first-class collaborators across the whole software development life cycle** — discovery, design, build, test, operate — under explicit governance, with every load-bearing change attributable to a named human seat. The framework rests on seven pillars. This document is the map; each pillar links to where it lives in the repo.

```
                         ┌─────────────────────────────────────────────┐
   Sources  ──ingest──▶  │  KNOWLEDGE LAYER  (KG / RAG / vector store)  │ ◀── pillar 5
                         └───────────────────────┬─────────────────────┘
                                                 │ ground on
                                                 ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ Architect│   │    EM    │   │ Product  │   │Developer │   │    QA    │  ◀── pillar 6
   └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘
        │  each seat = invokable Skill (.claude/skills) + scoped MCP (.mcp.json)
        ▼              ▼              ▼              ▼              ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │  GOVERNANCE & RULES (pillar 3)  →  enforced by CI/CD (pillar 4)       │
   │  AGENTS.md · WORKING-AGREEMENT.md · trust tiers · scoped-write MCP    │
   └─────────────────────────────────────────────────────────────────────┘
        ▲                                                          │
        │  feedback: retros, cost/quality metrics, dashboard       ▼
   ┌─────────────────────────────────────────────────────────────────────┐
   │  HUMAN METHODOLOGY & CONTINUOUS IMPROVEMENT (pillar 7)                │
   └─────────────────────────────────────────────────────────────────────┘
   Setup (pillar 1) bootstraps it all · Onboarding (pillar 2) gets each person in
```

## The seven pillars

### 1. Setup
One-command bootstrap of a governed, AI-ready repository — `scripts/bootstrap.sh` copies the template, substitutes the project placeholders, initialises git, and installs the hooks. **Where:** [`../../scripts/bootstrap.sh`](../../scripts/bootstrap.sh), [`../../README.md`](../../README.md).

### 2. Onboarding
Per-machine, per-user first-run that installs tooling, activates hooks, optionally seeds the knowledge index, and creates the git-ignored `USER.md` so the agent can tailor itself to each person. **Where:** [`../../ONBOARDING.md`](../../ONBOARDING.md), [`../onboarding/`](../onboarding/).

### 3. Governance & internal rules
The canonical brief, the working agreement, the **trust tiers** (what an AI may rely on), and the **scoped-write MCP posture** (what an AI may change, and how it stays attributable). No silent changes to load-bearing artefacts. **Where:** [`../../AGENTS.md`](../../AGENTS.md), [`../../WORKING-AGREEMENT.md`](../../WORKING-AGREEMENT.md), [`../ai-context/README.md`](../ai-context/README.md), [`../governance/`](../governance/).

### 4. CI/CD for the AI framework — rules as scripts
The governance rules are expressed as runnable scripts and enforced as merge gates: `validate-skills.py` (skills conform to agentskills.io), `validate-frontmatter.py` (the maturity/trust contract), and the commit↔issue hook. Local pre-commit gives fast feedback; CI is the non-bypassable gate. **Where:** [`../../.github/workflows/ai-governance.yml`](../../.github/workflows/ai-governance.yml), [`../../scripts/`](../../scripts/), [`../../.pre-commit-config.yaml`](../../.pre-commit-config.yaml).

### 5. Knowledge layer (KG / RAG / vector)
Project sources are **ingested** into a queryable store the agents **ground** on instead of guessing. The kit ships a dependency-light ingestion stub and a documented path to a production vector store / knowledge graph (or a hosted `knowledge` MCP server). **Where:** [`../knowledge/`](../knowledge/), [`../../scripts/knowledge/ingest.py`](../../scripts/knowledge/ingest.py).

### 6. Roles × Skills × MCP
Each named seat (Architect, EM, Product, Developer, QA) has an **invokable role-contract skill** and a **scoped set of MCP connectors**. The matrix is the operating model: who owns what, which skills they invoke, which tools they may act in. **Where:** [`../../.claude/skills/`](../../.claude/skills/), [`../../.mcp.json`](../../.mcp.json), `AGENTS.md` §5.

### 7. Human methodology & continuous improvement
The human stays in the loop. Retros, the AI-utilization dashboard (DB + web), and a cost/quality feedback loop turn usage into improvements to the rules, skills, and knowledge. **Where:** [`./continuous-improvement.md`](./continuous-improvement.md), [`../../dashboard/`](../../dashboard/).

## How a unit of work flows through it

1. **Confirm seat** at session start (pillar 6) — the ritual in `WORKING-AGREEMENT.md` §5.5.
2. **Ground** the task on the knowledge layer (pillar 5); cite sources + trust tier (pillar 3).
3. **Act** within the seat's scoped-write posture — draft in the wiki, create tracker items, write code on a branch (pillar 6).
4. **Gate** the change: frontmatter + skills validate locally then in CI (pillar 4).
5. **Promote** deliberately (drafts→canonical, `under-review`→`approved`) via PR — never silently (pillar 3).
6. **Reflect**: the dashboard and retro feed improvements back into rules/skills/knowledge (pillar 7).

> This framework is the kit's opinionated default. Adapt it per the anti-bloat clause (`WORKING-AGREEMENT.md` §8): change a rule only when it removes a recurring real question.
