---
title: "Example source — project coding standards"
source: "authored"
ai-trust: working
classification: internal
last-reviewed: 2026-06-26
---

# Example knowledge source — coding standards

> This is a **sample** source so the knowledge layer is non-empty out of the box. Replace or
> delete it, then add your real sources. After changing sources, rebuild:
> `python3 scripts/knowledge/ingest.py --build`

Agents ground answers about "our conventions" on sources like this one (`AGENTS.md` §4.4). Keep one topic per file.

## Conventions (example content)

- **Language & style:** follow `<LANGUAGE>`'s standard formatter/linter; CI fails on lint errors.
- **Commits:** reference the issue key (`<TICKET>-123`); small, reviewable PRs (`WORKING-AGREEMENT.md` §5.5).
- **Tests:** new behaviour ships with tests; no real personal data in fixtures.
- **Secrets:** never committed; use env vars / a secrets manager.
- **Dependencies:** justify new ones; verify library APIs via the `context7` MCP rather than memory.

> Replace this with your project's actual standards, architecture notes, glossary, domain primers,
> decision records worth grounding on, and any stakeholder material you've converted to Markdown.
