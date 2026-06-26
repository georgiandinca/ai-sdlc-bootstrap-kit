---
name: playbook-product
description: The Product (PO/PM) seat's role contract — what it owns end-to-end, co-owns and with whom, deliberately doesn't touch, and how it works with the other seats and with AI. Invoke whenever someone wants to reason from, act as, or get the Product perspective, or to settle a "who owns / who decides" boundary question about scope, backlog priority, acceptance criteria, roadmap, milestones, or plan.
metadata:
  seat: "Product"
  status: "approved"
  classification: "internal"
  ai-trust: "working"
  owner: "Architect"
---

# Product seat playbook

The **Product** seat — combining **Product Owner** and **Product Manager** — owns *what* gets built, *why*, *in what order*, and *by when*, for `<PROJECT_NAME>`.

## §1 — Mandate

### 1.1 Owns end-to-end (sole decision)

1. **Scope / MVP definition** — what is in, what is out, what is the minimum viable slice.
2. **Backlog priority order** — the ranked sequence of epics and stories.
3. **Acceptance criteria** — the user-facing definition of done for each story.
4. **Product roadmap** — themes and outcomes across the horizon.
5. **Milestones, dates & the delivery plan** — what lands when, and the commitment behind it.
6. **Dependency tracking & status reporting** — surfacing cross-team and external dependencies and their state.
7. **Stakeholder / user research strategy** — who to learn from and how that evidence shapes the backlog.

### 1.2 Co-owns (with named partner)

| Item | Co-owner | Meaning |
| --- | --- | --- |
| Sprint capacity allocation | EM | Product proposes the pull; EM commits to what the team can take. |
| Use-case feasibility | Architect | Architect flags constraints and risk; Product decides whether to proceed. |
| Tech-debt prioritisation | Architect + EM | Architect/EM size and surface the debt; Product sequences it against feature work. |
| Acceptance-criteria technical-correctness input | Architect + QA | Architect/QA validate that AC are technically coherent and verifiable; Product owns the AC themselves. |

### 1.3 Deliberately doesn't touch

- **Reference architecture & decomposition** — owned by the Architect.
- **Engineering practice & sprint mechanics** — owned by the EM.
- **Implementation decisions** — owned by the Developer.
- **Test strategy mechanics** — Product approves the AC; QA owns *how* to verify them.

## §2 — Decision-rights cheat sheet

| # | Decision | Owner | Consulted | Informed | Escalation trigger |
| --- | --- | --- | --- | --- | --- |
| 1 | Add / drop a scope item | Product | Architect, EM | All seats | Materially threatens a committed date |
| 2 | Approve acceptance criteria | Product | Architect, QA | Developer | AC not testable / no verification path |
| 3 | Set priority order | Product | EM, stakeholders | All seats | Priority conflicts with a dependency or commitment |
| 4 | Commit a roadmap date | Product | EM, Architect | Stakeholders | Capacity cannot meet the date |
| 5 | Approve a sprint pull | Product + EM | Developer | QA | Product and EM cannot converge on the pull |
| 6 | Accept a mandatory / compliance feature for sequencing | Product | Architect, EM, QA | All seats | Compliance deadline collides with capacity |

## §3 — Working with other seats

**Product ↔ Architect.** Product brings the use case; the Architect brings feasibility evidence. The Architect *flags* constraints, risk, and cost; **Product decides** whether and when to proceed.

**Product ↔ EM.** The most intimate operational interaction: Product holds priority, EM holds capacity. They **converge before any commit** — Product proposes the pull, EM confirms what the team can take, and no date is committed until both agree.

**Product ↔ Developer.** Product is the source of truth on *intent* during refinement — answering "what does done look like and why." **No story-level technical intervention**; how it is built is the Developer's call.

**Product ↔ QA.** Product approves the acceptance criteria; QA verifies them. The definition of done is **jointly held** — Product owns the user-facing bar, QA owns the evidence that it is met.

**Escalation.** A scope-versus-capacity deadlock that Product and EM cannot resolve escalates to the `<DIRECTOR / SPONSOR>`.

## §4 — Working with AI (Roles × Skills × MCP)

Ties to the board's Roles × Skills × MCP matrix; the Product seat's AI trust level is **working**.

- **Invokable skills:** this playbook; `brainstorming` and `writing-plans` (if present) for discovery and spec shaping; `skill-creator` to capture repeatable Product workflows.
- **MCP — issue-tracker (HEAVY):** create and modify epics, stories, sprints, and links under the Product seat. This is the primary **scoped-write** surface for Product.
- **MCP — docs-wiki:** draft PRDs and roadmap pages for human review.
- **MCP — knowledge:** ground product decisions on ingested sources (research, prior decisions, stakeholder input) rather than assertion.
- **Scoped-write guardrail:** every AI write to the tracker is attributable to the **Product seat + session** and reviewed in-tool; promotion of wiki drafts to canonical stays **human-applied**.
- Connectors are declared in `.mcp.json`; use only what the matrix grants the Product seat.

## §5 — Definition of done for this seat's artefacts

- Scope and roadmap docs carry the frontmatter contract (`AGENTS.md` §4.2).
- Acceptance criteria are **testable** and **approved** before a story enters a sprint.
- Every AI-created tracker item names the **Product seat** as its author.
- Dependencies and dates are **surfaced, not buried** — visible in the plan and status report.

---

See [`AGENTS.md`](../../../AGENTS.md), [`WORKING-AGREEMENT.md`](../../../WORKING-AGREEMENT.md), and the seat notes under [`docs/ai-context/skills/product/`](../../../docs/ai-context/skills/product/).
