# Bundled Agent Skills

These are **project-level AI skills** that ship with the repo, so every team member gets the same baseline the moment they clone and open the project in an agent — no plugin install required. They are **versioned governance artefacts**: change them in a PR like any other.

This directory is the `.claude/skills/` half of the board's **Roles × Skills × MCP** matrix — each seat has an invokable skill here; its MCP connectors are declared in [`../../.mcp.json`](../../.mcp.json).

## Role-seat contracts

The `playbook-<seat>` skills capture each named seat's **role contract** — what it owns end-to-end, co-owns and with whom, deliberately doesn't touch, and how it works with the other seats and with AI. Invoke one to reason from, act as, or get a seat's perspective (e.g. "act as the Architect", "what's the Product view"), or to settle a "who owns / who decides" boundary question.

| Skill | Seat |
|---|---|
| **playbook-architect** | Architect |
| **playbook-em** | Engineering Manager |
| **playbook-product** | Product (PO/PM) |
| **playbook-dev** | Developer |
| **playbook-qa** | QA |

These are **Architect-owned baselines**; each seat holder may amend their own via PR.

## Tooling skills

| Skill | Use it for |
|---|---|
| **skill-creator** | Create new skills, and improve / evaluate existing ones. Use it to add a team skill or sharpen one's triggering. |

> **Generic baseline (optional).** Teams commonly also bundle `brainstorming`, `writing-plans`, `test-driven-development`, `systematic-debugging`, and `code-review` here (e.g. from the Superpowers plugin) so the whole team shares one process baseline. Add the ones your team uses via PR; the playbooks reference them where relevant.

## Conformity to agentskills.io

Every `SKILL.md` is validated against the [agentskills.io](https://agentskills.io/specification) standard by [`../../scripts/validate-skills.py`](../../scripts/validate-skills.py):

- **Locally** via [`../../.pre-commit-config.yaml`](../../.pre-commit-config.yaml) — runs on every commit touching a `SKILL.md`.
- **Centrally** via [`../../.github/workflows/ai-governance.yml`](../../.github/workflows/ai-governance.yml) as the enforced merge gate.

Run it anytime: `python3 scripts/validate-skills.py`.

## Two kinds of skill, two homes

- **Invokable** skills — here in `.claude/skills/<name>/SKILL.md`, auto-discovered and triggered by the agent.
- **Read-on-demand** MCP task playbooks — under [`../../docs/ai-context/skills/<role>/`](../../docs/ai-context/skills/), reference docs the agent reads when relevant (*how we run this project* over the connectors), not auto-invoked.

See [`../../docs/ai-context/README.md`](../../docs/ai-context/README.md) for the full AI-context contract.
