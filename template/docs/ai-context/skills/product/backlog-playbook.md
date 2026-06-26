---
title: "Product — backlog & sprint automation playbook (MCP, read-on-demand)"
status: draft
owner: Product
author: AI-SDLC Bootstrap Kit
created: 2026-06-26
classification: internal
last-reviewed: 2026-06-26
ai-trust: working
---

# Product — backlog & sprint automation over the issue-tracker MCP

A **read-on-demand** playbook (not an auto-invoked skill): *how we run the backlog over the connector.* Pair it with the invokable [`playbook-product`](../../../../.claude/skills/playbook-product/SKILL.md) role contract.

> Fill the `<PLACEHOLDERS>` for your tracker (Jira / Linear / GitHub Issues). The patterns are tracker-agnostic.

## Posture

Scoped write (`AGENTS.md` §4.3): the AI **may create & modify** epics, stories, sprints, and links **under the Product seat**. Every write is attributable to the seat + session and reviewed in-tool. Promotion of narrative docs to the wiki stays human-applied.

## Conventions

- **Hierarchy:** Epic → Story → (Sub-task). Bugs are their own type (QA-owned, see the QA playbook).
- **Keys:** project prefix `<TICKET>` (e.g. `<TICKET>-123`). Branch and commit reference the key (`WORKING-AGREEMENT.md` §5.5).
- **No specs pasted into tickets** — link out to the canonical doc in Git/wiki. Exception: the acceptance criteria are mirrored into the story so testers see them in-tool.
- **Definition of ready** before a story enters a sprint: clear intent, testable AC, estimate, no blocking dependency.

## Common operations (describe what the AI should do, then do it)

1. **Create an epic** — title, goal, linked roadmap doc, milestone. Confirm with the Product seat before creating.
2. **Slice stories from an epic** — each story independently valuable, vertically sliced, with testable AC. Surface coverage gaps.
3. **Refine** — keep top-of-backlog stories ready; flag stale (old `story age`) items.
4. **Plan a sprint** — propose a pull from the prioritised backlog within the capacity the EM commits (`playbook-em`). Product proposes, EM commits.
5. **Report status** — link to live tracker state via MCP (pull-on-demand); don't snapshot into docs.

## Guardrails

- Confirm before bulk operations or anything outward-facing.
- One unified backlog; tech debt enters at a Product-set, value-weighted priority (with Architect + EM input).
- Never invent dates or commitments — those are Product decisions made with the EM/PM reality check.
