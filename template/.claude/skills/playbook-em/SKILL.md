---
name: playbook-em
description: The Engineering Manager (EM) seat's role contract — what it owns end-to-end, co-owns and with whom, deliberately doesn't touch, and how it works with the other seats and with AI. Invoke whenever someone wants to reason from, act as, or get the EM's perspective, or to settle a "who owns / who decides" boundary question about code repos, engineering practice, CI/CD, sprint cadence, or delivery capacity.
metadata:
  seat: "EM"
  status: "approved"
  classification: "internal"
  ai-trust: "working"
  owner: "Architect"
---

The **Engineering Manager (EM)** seat owns how `<PROJECT_NAME>` is built and shipped — engineering practice, delivery cadence, and the CI/CD gates that enforce the working agreement.

## §1 — Mandate

### 1.1 Owns end-to-end (sole decision)

1. Code repositories and branch/PR conventions (naming, protected branches, merge strategy).
2. Engineering practices — testing strategy, code review, coding standards, linting.
3. CI/CD pipelines and the AI-governance merge gates (see [`.github/workflows/ai-governance.yml`](../../../.github/workflows/ai-governance.yml)).
4. Sprint cadence, velocity tracking, and the team's capacity commitment.
5. Dev runbooks and on-call / operability practice.
6. Developer tooling and environments (local setup, secrets handling, reproducible builds).

### 1.2 Co-owns (with named partner)

| Item | Co-owner | Meaning |
|------|----------|---------|
| ADRs | Architect | Architect proposes shape; EM co-signs that it is buildable/operable. |
| Sprint capacity vs scope | Product | EM commits a velocity; Product proposes the scope to fit it. |
| Tech-debt prioritisation | Architect + Product | EM surfaces debt; ranking is jointly agreed. |
| Non-functional requirements | Architect | Architect sets targets; EM owns how CI verifies them. |

### 1.3 Deliberately doesn't touch

- Backlog priority order — **Product**.
- Acceptance-criteria approval — **Product**.
- Reference-architecture shape — **Architect**.
- Commercial terms (pricing, contracts, vendor deals).

## §2 — Decision-rights cheat sheet

| # | Decision | Owner | Consulted | Informed | Escalation trigger |
|---|----------|-------|-----------|----------|--------------------|
| 1 | Commit sprint scope vs capacity | EM | Product, Developers | Architect | Scope exceeds sustainable velocity |
| 2 | Change a CI gate | EM | Architect, QA | All seats | Gate change weakens an AI-governance rule |
| 3 | Set/revise a coding standard | EM | Developers, Architect | Product | Standard conflicts with reference architecture |
| 4 | Approve a release / merge to a protected branch | EM | QA, Architect | Product | Red CI or unmet definition of done |
| 5 | Approve a tech-debt sprint | EM + Product | Architect | All seats | Either co-owner vetoes |

## §3 — Working with other seats

**EM ↔ Architect** — Engineering execution consumes the architecture shape; the EM translates it into buildable, operable work and co-signs ADRs so every accepted decision is both sound and deliverable.

**EM ↔ Product** — Capacity-vs-scope is negotiated *before* a sprint is committed: Product proposes scope, EM commits velocity. Either seat can veto a tech-debt sprint.

**EM ↔ Developer** — Daily delivery: clearing blockers, sanity-checking estimates, enforcing review and standards, keeping the pipeline green.

**EM ↔ QA** — QA defines quality signals; EM wires them into CI as gates and co-owns the definition of done.

**Escalation** — A scope/velocity deadlock that the EM and Product cannot resolve goes to the `<DIRECTOR / SPONSOR>`.

## §4 — Working with AI (Roles × Skills × MCP)

Ties to the board's Roles × Skills × MCP matrix. See [`AGENTS.md`](../../../AGENTS.md) and [`WORKING-AGREEMENT.md`](../../../WORKING-AGREEMENT.md).

- **Invokable skills** — this playbook; a tdd / test skill and a code-review skill where present; `skill-creator` to author new seat skills.
- **MCP connectors** (from [`.mcp.json`](../../../.mcp.json)) — *issue-tracker* to manage sprints and capacity views; *docs-wiki* to draft runbooks and specs; *knowledge* to ground engineering decisions in prior context; *context7* for up-to-date library docs.
- **The EM OWNS the CI/CD AI-governance gates** — the [`scripts/validate-*.py`](../../../scripts/) checks and [`.github/workflows/ai-governance.yml`](../../../.github/workflows/ai-governance.yml) are this seat's "rules as scripts" pillar: governance is executable, not advisory.
- **Scoped-write guardrail** — AI agents write only within their granted scope and never push to a protected branch; merges are human-approved through the gates above.

## §5 — Definition of done for this seat's artefacts

- CI is green, **including the AI-governance gate**.
- Every PR is reviewed before merge to a protected branch.
- Runbooks carry the frontmatter contract (name / status / classification / ai-trust / owner).
- Commit messages reference the issue key per [`WORKING-AGREEMENT.md`](../../../WORKING-AGREEMENT.md) §5.5.
- No secrets are committed (verified by the pipeline).
