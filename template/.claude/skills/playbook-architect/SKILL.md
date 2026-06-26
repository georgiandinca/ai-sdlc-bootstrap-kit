---
name: playbook-architect
description: The Architect seat's role contract — what it owns end-to-end, co-owns and with whom, deliberately doesn't touch, and how it works with the other seats and with AI. Invoke whenever someone wants to reason from, act as, or get the Architect's perspective, or to settle a "who owns / who decides" boundary question about system shape, ADRs, technical standards, or where an artefact belongs.
metadata:
  seat: "Architect"
  status: "approved"
  classification: "internal"
  ai-trust: "working"
  owner: "Architect"
---

The **Architect** is the seat accountable for the shape of the `<PROJECT_NAME>` system: how it decomposes, the decisions of record behind it, and the contracts that keep the knowledge layer and the codebase grounded.

## §1 — Mandate

### 1.1 Owns end-to-end (sole decision)
1. **Reference architecture & component decomposition** — the canonical system shape and how it breaks into parts.
2. **ADRs (architecture decision records)** — authoring, sequencing, and promoting decisions from draft to approved.
3. **The AI-context contract & trust tiers** — what AI may read/write and at what confidence level (`AGENTS.md`).
4. **Technical standards & conventions on critical paths** — the rules that load-bearing code must follow.
5. **Arbitration of "where does X go" / workspace shape** — folder topology and the home for each artefact.
6. **The knowledge-layer schema** — what gets ingested, how it is grounded, and how it is queried.

### 1.2 Co-owns (with named partner)
| Item | Co-owner | What co-owned means |
| --- | --- | --- |
| Use-case feasibility | Product | Architect flags technical viability and cost; Product decides whether to pursue. |
| Non-functional requirements | EM | Architect sets the NFR targets; EM owns how they are met and sustained in delivery. |
| Tech-debt prioritisation | EM + Product | Architect names the debt and its risk; EM + Product sequence it against feature work. |
| Interface / API contracts | Developer | The seam is jointly authored — Architect frames it, Developer implements and refines it. |

### 1.3 Deliberately doesn't touch
- **Backlog priority order** — Product.
- **Sprint mechanics & velocity** — EM.
- **Acceptance-criteria approval** — Product.
- **Commercial terms** — outside the seat entirely.

## §2 — Decision-rights cheat sheet
| # | Decision | Owner | Consulted | Informed | Escalation trigger |
| --- | --- | --- | --- | --- | --- |
| 1 | Approve an ADR (draft → approved) | Architect | EM, Developer | Product, QA | EM and Architect disagree on a load-bearing decision. |
| 2 | Set a technical standard on a critical path | Architect | EM, Developer | QA | Standard would materially slow delivery or break an SLA. |
| 3 | Arbitrate folder placement of an artefact | Architect | affected seat | all seats | Placement crosses two seats' ownership. |
| 4 | Approve a new top-level folder | Architect | EM, Product | all seats | Anti-bloat clause (§5) cannot be satisfied. |
| 5 | Change the knowledge-layer schema | Architect | EM | Product, QA, Developer | Change invalidates existing grounding or ingestion. |

## §3 — Working with other seats

### Architect ↔ EM
- Architect owns architecture *shape*; EM owns engineering *execution* against it.
- ADRs that affect delivery are **co-signed** by both.
- EM raises when a decision is unbuildable within current constraints.

### Architect ↔ Product
- Architect supplies feasibility *evidence*, not the go/no-go: **Architect flags, Product decides**.
- Architect surfaces cost and risk early enough to shape scope.

### Architect ↔ Developer
- Interface and API contracts are the shared seam — **jointly authored**.
- Architect frames the boundary; Developer owns the implementation behind it and feeds reality back.

### Architect ↔ QA
- Architect makes the system **testable** and defines how NFRs are verified.
- QA challenges whether stated NFRs are observable and measurable.

**Escalation rule:** unresolved cross-seat disputes go to the **Director / sponsor** as tiebreaker. See `WORKING-AGREEMENT.md` for the full path.

## §4 — Working with AI (Roles × Skills × MCP)
- **Invokable skills:** this playbook (`playbook-architect`); `brainstorming` and `writing-plans` when shaping options before an ADR; `skill-creator` to evolve seat skills as the system changes.
- **Knowledge connector — heavy use:** grounds every ADR and load-bearing claim on ingested sources before it is written.
- **`context7` connector:** pulls authoritative library/framework docs when evaluating a technology or interface.
- **`docs-wiki` connector:** drafts ADRs and specs; promotion to approved stays a deliberate, human-confirmed step.
- **`issue-tracker` connector:** read-mostly — pulls context on debt and constraints; does not reprioritise the backlog.
- **Scoped-write guardrail:** no silent changes to load-bearing artefacts; ADRs move draft → approved only on explicit decision. See `AGENTS.md` for connector scopes in `.mcp.json`.

## §5 — Definition of done for this seat's artefacts
- An ADR carries the frontmatter contract (`AGENTS.md` §4.2) — status, classification, owner, and AI-trust tier.
- Every decision states **context / decision / consequences**, not just the verdict.
- Load-bearing claims are **grounded on the knowledge layer** or carry an explicit citation.
- New folders are **justified per the anti-bloat clause** (§2 row 4) before they are created.
- Approved ADRs live in [`docs/architecture/decisions/`](../../../docs/architecture/decisions/) and are linked from whatever they govern.
