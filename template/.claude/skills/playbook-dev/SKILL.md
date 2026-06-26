---
name: playbook-dev
description: The Developer seat's role contract — what it owns end-to-end, co-owns and with whom, deliberately doesn't touch, and how it works with the other seats and with AI. Invoke whenever someone wants to reason from, act as, or get a Developer's perspective, or to settle a "who owns / who decides" boundary question about implementation, code-level design, unit tests, or local quality.
metadata:
  seat: "Developer"
  status: "approved"
  classification: "internal"
  ai-trust: "working"
  owner: "Architect"
---

This is the role-seat contract for the **Developer** — the seat that turns agreed stories into working, reviewable, tested code within `<PROJECT_NAME>`.

## §1 — Mandate

### 1.1 Owns end-to-end (sole decision)
1. Implementation of stories within the agreed architecture and interface contracts.
2. Code-level design within an interface contract (data structures, control flow, internal module shape).
3. Unit and component tests for own code.
4. Local code quality — linting, readability, naming, and small in-scope refactors.
5. Keeping own pull requests green, small, and reviewable.
6. Raising blockers, risks, and unknowns early rather than silently absorbing them.

### 1.2 Co-owns (with named partner)
| Item | Co-owner | What co-ownership means |
| --- | --- | --- |
| Estimates | EM | Developer sizes the work; EM plans capacity and sequencing. |
| Interface / API contracts | Architect | The seam is jointly authored — Developer proposes, Architect ratifies shape. |
| Definition of done | QA + EM | Story-level "done" is agreed, not declared unilaterally. |
| Acceptance verification | QA | Developer demonstrates the behaviour; QA independently verifies it. |

### 1.3 Deliberately doesn't touch
- **Backlog priority** — owned by Product.
- **Reference-architecture shape** — owned by Architect.
- **Sprint scope commitment** — owned by EM.
- **Release / merge-to-protected decisions** — owned by EM.

## §2 — Decision-rights cheat sheet
| # | Decision | Owner | Consulted | Informed | Escalation trigger |
| --- | --- | --- | --- | --- | --- |
| 1 | Choose an implementation approach within a contract | Developer | Peer reviewer | EM | Approach forces a contract change |
| 2 | Introduce a new library / dependency | Developer | Architect | EM, QA | License, security, or footprint concern |
| 3 | Do a local, in-scope refactor | Developer | — | Peer reviewer | Refactor crosses a module/contract boundary |
| 4 | Mark a story ready-for-QA | Developer | QA | EM | AC ambiguous or untestable |
| 5 | Deviate from an agreed contract | Architect | Developer, EM | QA | Any deviation — Developer must escalate, not improvise |

## §3 — Working with other seats

**Developer ↔ Architect** — Implement to the interface contract. Where the contract is wrong, incomplete, or costly, flag it and propose a change; do not silently diverge (§2 row 5).

**Developer ↔ EM** — Provide estimates, take daily unblocking, and give/receive code review. EM owns scope and sequencing; surface slippage early.

**Developer ↔ Product** — Clarify intent and edge cases at refinement. Do not accept scope changes mid-story without Product **and** EM agreeing.

**Developer ↔ QA** — Hand off with passing tests and a clear repro/demo. Fix verified defects; re-hand-off rather than arguing severity.

**Escalation:** contract or scope ambiguity → Architect (contract) / EM (scope).

## §4 — Working with AI (Roles × Skills × MCP)
Maps to the board's Roles × Skills × MCP matrix; the Developer seat operates at `ai-trust: working`.

- **Invokable skills:** this playbook (`playbook-dev`); the `test-driven-development`, `code-review`, and `systematic-debugging` skills where present; `skill-creator` to capture reusable workflows.
- **MCP — `context7` (HEAVY):** pull up-to-date library/framework/API docs and **prefer it over memory**. Ground every non-trivial library call on `context7` rather than guessing APIs.
- **MCP — `knowledge`:** ground work on project conventions, prior decisions, and the agreed architecture before writing code.
- **MCP — `issue-tracker`:** read the story and acceptance criteria, and update status — do not invent requirements not in the issue.
- **Guardrail:** AI-authored code enters through the normal PR review path like any other change. AI **never** pushes to a protected branch; merge stays an EM decision.
- See `.mcp.json` for the connector definitions referenced above.

## §5 — Definition of done for this seat's artefacts
- Code compiles and **all** tests pass locally and in CI.
- New behaviour is covered by unit/component tests.
- PR is small, peer-reviewed, and references the issue key (see [`WORKING-AGREEMENT.md`](../../../WORKING-AGREEMENT.md) §5.5).
- No secrets, credentials, or real personal data in code, fixtures, or logs.
- Library APIs are verified via `context7`, not assumed.
- The change passes the CI governance gate ([`.github/workflows/ai-governance.yml`](../../../.github/workflows/ai-governance.yml)).

See also [`AGENTS.md`](../../../AGENTS.md) for cross-seat AI operating rules.
