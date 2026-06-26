---
title: "QA — test traceability playbook (MCP, read-on-demand)"
status: draft
owner: QA
author: AI-SDLC Bootstrap Kit
created: 2026-06-26
classification: internal
last-reviewed: 2026-06-26
ai-trust: working
---

# QA — test traceability over the tracker + knowledge MCP

A **read-on-demand** playbook (not an auto-invoked skill): *how we keep requirements, tests, and results traceable.* Pair it with the invokable [`playbook-qa`](../../../../.claude/skills/playbook-qa/SKILL.md) role contract.

## Posture

Scoped write (`AGENTS.md` §4.3): the AI **may create & manage** defect items and link them to tests/stories **under the QA seat**, and **may draft** test plans & traceability matrices in the wiki. A **human QA signs off** the quality gate — that is never delegated.

## The traceability chain

```
Requirement / AC  ──▶  Test case  ──▶  Test run / result  ──▶  Defect (if failed)
   (knowledge layer)     (test plan)      (CI / manual)          (tracker, QA seat)
```

Every acceptance criterion (`playbook-product`) must map to **at least one** test. The AI can build and maintain this matrix; surface any AC with no test.

## Common operations

1. **Derive tests from AC** — read the story's AC (grounded on the knowledge layer), propose test cases (happy path, edge, negative). Use **synthetic data only**.
2. **Build/refresh the traceability matrix** — AC ↔ test ↔ latest result. Draft in the wiki; flag gaps.
3. **File a defect** — reproducible steps with synthetic data, severity, linked story/test. Created under the QA seat via MCP.
4. **Verify a fix** — re-run the failing test; close the defect only when green.
5. **Report gate status** — which gates are green/red and why; feed CI gate-health into the metrics (`docs/methodology/continuous-improvement.md`).

## Guardrails

- Severity and release-readiness are QA calls; disputes escalate to EM + Product.
- Automate gates into CI where possible (`.github/workflows/ai-governance.yml` is the model); document the manual ones.
- No real personal data in test fixtures, ever.
