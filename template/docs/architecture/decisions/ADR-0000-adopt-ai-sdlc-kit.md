---
title: "ADR-0000 — Adopt the AI-SDLC Bootstrap Kit"
status: approved
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-06-26
classification: internal
last-reviewed: 2026-06-26
ai-trust: working
---

# ADR-0000 — Adopt the AI-SDLC Bootstrap Kit

> This is the seed ADR every project gets. It records the decision to run this project on the
> AI-augmented SDLC framework, and doubles as the **template** for future ADRs — copy its shape.

## Status

Accepted — 2026-06-26.

## Context

`<PROJECT_NAME>` uses AI agents as first-class collaborators across the SDLC. Doing that safely needs a shared operating model: a single brief every tool reads, explicit trust tiers, a scoped-write posture for AI in our tools, rules enforced as CI gates, a knowledge layer agents can ground on, and a human-owned improvement loop. Re-inventing this per project is wasteful and drifts.

## Decision

Adopt the **AI-SDLC Bootstrap Kit** and its seven-pillar framework ([`../../methodology/framework.md`](../../methodology/framework.md)) as the project's operating model:

1. `AGENTS.md` is the canonical brief; `CLAUDE.md` and other tool files are thin pointers.
2. Maturity & trust are signalled by **location + frontmatter** (§4.2) and enforced by `scripts/validate-frontmatter.py`.
3. AI acts under a **scoped-write MCP posture** — attributable to a named seat, never silent.
4. The named seats are **Architect, EM, Product, Developer, QA**, each with an invokable playbook skill and a scoped MCP profile.
5. Governance rules run as **CI gates** (`.github/workflows/ai-governance.yml`).
6. Knowledge is **ingested and grounded on** (`docs/knowledge/`), not guessed.
7. A **human-owned continuous-improvement loop** (`docs/methodology/continuous-improvement.md`) feeds usage back into the rules.

## Consequences

**Positive.** Every contributor and every AI tool shares one model; changes are attributable and reviewable; rules are testable; new joiners onboard via `ONBOARDING.md` in one pass.

**Costs / trade-offs.** Frontmatter and the session ritual add light ceremony; the knowledge layer needs curation; the rules must be maintained (and pruned per the anti-bloat clause, `WORKING-AGREEMENT.md` §8).

**Follow-ups.** Fill the `<PLACEHOLDERS>` in `AGENTS.md` (§1 mission, §3 constraints, §4 tool/connector specifics); wire `.mcp.json` to the real connectors; add the first knowledge sources.

---

### ADR template (copy for ADR-0001+)

```markdown
---
title: "ADR-NNNN — <short decision title>"
status: under-review        # draft | under-review | approved | superseded
owner: <accountable seat>
author: Name <email>
created: YYYY-MM-DD
classification: internal
last-reviewed: YYYY-MM-DD
ai-trust: working
---

# ADR-NNNN — <short decision title>

## Status
<draft | under-review | approved | superseded — and date; if superseded, link the successor>

## Context
<the forces at play: requirements, constraints, what makes this a decision>

## Decision
<what we decided, stated plainly>

## Consequences
<positive, costs/trade-offs, follow-ups>
```
