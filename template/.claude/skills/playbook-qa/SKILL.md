---
name: playbook-qa
description: The QA seat's role contract — what it owns end-to-end, co-owns and with whom, deliberately doesn't touch, and how it works with the other seats and with AI. Invoke whenever someone wants to reason from, act as, or get the QA perspective, or to settle a "who owns / who decides" boundary question about test strategy, test plans, traceability, quality gates, or release-readiness.
metadata:
  seat: "QA"
  status: "approved"
  classification: "internal"
  ai-trust: "working"
  owner: "Architect"
---

# Playbook: QA

This is the role-seat contract for the **QA** seat on `<PROJECT_NAME>` — the seat accountable for whether the product is provably good enough to ship.

## §1 — Mandate

### 1.1 Owns end-to-end (sole decision)

1. **Test strategy & test plans** — the approach, scope, levels, and coverage targets for `<PROJECT_NAME>`.
2. **Traceability** — the requirement/AC ↔ test ↔ result chain stays complete and current.
3. **Quality gates that block release** — what must be green (and how green) before anything ships.
4. **Acceptance verification against approved AC** — the formal check that a story does what it promised.
5. **Defect triage & severity** — what is a defect, how bad it is, and where it sits in the queue.
6. **Test data management** — synthetic only; **no real personal data** ever flows into test environments.

### 1.2 Co-owns (with named partner)

| Item | Co-owner | Meaning |
| --- | --- | --- |
| Acceptance criteria | Product | Product approves the AC; QA makes them verifiable (testable, unambiguous, measurable). |
| Definition of done | EM + Developer | QA contributes the quality bar; EM and Developer own delivery and craft components. |
| Non-functional / test environments | EM | EM provisions and maintains them; QA defines what they must exercise and prove. |
| Testability of designs | Architect | Architect shapes the system so it can be observed and verified; QA states the needs. |

### 1.3 Deliberately doesn't touch

- **Backlog priority** — owned by Product.
- **Implementation approach** — owned by Developer.
- **Architecture shape** — owned by Architect.
- **Sprint scope commitment** — owned by EM.

## §2 — Decision-rights cheat sheet

| # | Decision | Owner | Consulted | Informed | Escalation trigger |
| --- | --- | --- | --- | --- | --- |
| 1 | Sign off release-readiness / quality gate | QA | EM, Product | All seats | Gate red but release pressure to ship anyway |
| 2 | Set defect severity | QA | Developer, Product | EM | Severity disputed by owning seat |
| 3 | Accept a story as meeting AC | QA | Product | Developer, EM | AC ambiguous or untestable as written |
| 4 | Approve the test strategy | QA | Architect, EM | All seats | Strategy needs infra/architecture QA can't mandate |
| 5 | Block a release on a critical defect | QA | EM, Product | All seats | Block contested → escalate to EM + Product |

## §3 — Working with other seats

- **QA ↔ Product** — Product approves AC; QA verifies the build against them. Joint owners of the definition of done. Disagreement on "is this acceptable?" is resolved here before sign-off.
- **QA ↔ Developer** — Hand-off arrives with tests and a reproduction; QA verifies fixes against the original repro, not just the claim. Defects route back with synthetic-data steps.
- **QA ↔ EM** — Quality gates are wired into CI so they run automatically; EM owns the pipeline, QA owns the criteria the pipeline enforces.
- **QA ↔ Architect** — QA states testability and NFR-verification needs; Architect shapes the system to make them observable and measurable.

**Escalation:** a release-readiness dispute escalates to **EM + Product** jointly; if still unresolved, the **`<DIRECTOR_OR_SPONSOR>`** is the final tiebreaker.

## §4 — Working with AI (Roles × Skills × MCP)

Ties to the board's Roles × Skills × MCP matrix. AI is a `working`-trust collaborator for this seat: it accelerates, it does not sign off.

- **Invokable skills** — this playbook (role grounding); any test-generation / QA skills present in the repo; `skill-creator` to capture reusable QA patterns.
- **MCP — issue-tracker** — AI may create and manage bug/defect items and link them to tests **under the QA seat**; this is a *scoped-write* surface, not open-ended automation.
- **MCP — knowledge** — ground generated test cases on the actual requirements/AC held in the knowledge layer so tests verify the spec, not the model's guess.
- **MCP — docs-wiki** — draft test plans and traceability matrices for human review.
- **Hard line** — AI may generate tests and draft plans, but a **human QA signs off the quality gate**, and **every AI-created defect names the QA seat** as accountable owner.
- Connectors are defined in `.mcp.json`; trust tiers and seat ownership follow `AGENTS.md`.

## §5 — Definition of done for this seat's artefacts

- Test plans / strategy carry the frontmatter contract (`AGENTS.md` §4.2): seat, status, classification, ai-trust, owner.
- Every AC has **at least one traceable test**, and the requirement ↔ test ↔ result link is recorded.
- Quality-gate criteria are explicit and wired into CI wherever automatable (see [`.github/workflows/ai-governance.yml`](../../../.github/workflows/ai-governance.yml)).
- Defects are reproducible using **synthetic data only**, with steps another seat can replay.
- Sign-off is recorded — who signed, against which gate, at which version.

---

**See also:** [`AGENTS.md`](../../../AGENTS.md) · [`WORKING-AGREEMENT.md`](../../../WORKING-AGREEMENT.md) · [`.github/workflows/ai-governance.yml`](../../../.github/workflows/ai-governance.yml) · [`docs/ai-context/skills/qa/`](../../../docs/ai-context/skills/qa/)
