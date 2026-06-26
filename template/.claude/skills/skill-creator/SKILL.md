---
name: skill-creator
description: Create new Agent Skills, and improve or evaluate existing ones, for this project. Invoke whenever someone wants to add a team skill, sharpen an existing skill's triggering/description, split or merge skills, or check a SKILL.md against the agentskills.io specification. Use it before hand-writing a new SKILL.md so the result conforms and triggers reliably.
metadata:
  status: "approved"
  classification: "internal"
  ai-trust: "working"
  owner: "Architect"
---

# skill-creator

Authoring guide for adding and improving the project's invokable Agent Skills. Skills are **versioned governance artefacts** (`WORKING-AGREEMENT.md` §5.2) — every change lands via PR and must pass the conformity gate.

## When to use this skill

- Adding a new team-wide skill (a workflow, a checklist, a role contract).
- Improving an existing skill — usually its `description` (the only thing the agent sees when deciding whether to trigger).
- Deciding whether something should be an **invokable skill** (here) or a **read-on-demand MCP playbook** (`docs/ai-context/skills/<role>/`).

## The anatomy of a SKILL.md

A skill is a directory under `.claude/skills/<name>/` containing `SKILL.md`. The file is YAML frontmatter + a Markdown body.

```markdown
---
name: <name>            # REQUIRED. 1-64 chars, lowercase a-z/0-9/hyphen, no leading/
                        # trailing/consecutive hyphens, and MUST equal the directory name.
description: <text>     # REQUIRED. 1-1024 chars. This is what the agent reads to decide
                        # whether to trigger — write it as "Use when …" + concrete triggers.
metadata:               # OPTIONAL. mapping of string -> string only.
  status: "approved"
  owner: "<seat>"
# license / compatibility / allowed-tools are also optional (see the spec).
---

<non-empty Markdown body: what the skill does, when, and the steps/checklist to follow>
```

## Writing a description that triggers reliably

The `description` is the single most important field — it is the only signal the agent uses to decide whether to load the skill. Make it:

1. **Start with the trigger condition** — "Use when …", "Invoke whenever …".
2. **Name concrete triggers** — the words and situations that should fire it, including phrasings a user might actually type.
3. **Disambiguate** — say what it is *not* for when a sibling skill is close.

Bad: `description: Helps with testing.`
Good: `description: Use when implementing any feature or bugfix, before writing implementation code — drives a test-first workflow. Triggers on "add tests", "TDD", "write a failing test first".`

## Invokable skill vs. read-on-demand playbook

| Put it in `.claude/skills/` (invokable) when… | Put it in `docs/ai-context/skills/<role>/` (read-on-demand) when… |
|---|---|
| The agent should auto-trigger it from context | It's reference material the agent reads only when a task clearly needs it |
| It's a reusable workflow/contract used across sessions | It documents *how we run this project* over a specific MCP connector |
| Triggering precision matters | It's long, narrow, and rarely the entry point |

## Process for adding or changing a skill

1. **Decide the home** (table above).
2. **Create `\.claude/skills/<name>/SKILL.md`** with the frontmatter above; `name` must equal the directory.
3. **Write the body** — concise, action-oriented; a checklist beats prose for procedures.
4. **Validate:** `python3 scripts/validate-skills.py .claude/skills/<name>/SKILL.md`
5. **Open a PR.** The CI gate ([`ai-governance.yml`](../../../.github/workflows/ai-governance.yml)) re-runs validation; merge when green and reviewed.

## Evaluating an existing skill

- Does the `description` fire on the situations it should — and stay quiet otherwise? Tighten wording, don't add logic to the body to compensate.
- Is the body still accurate after recent changes? Skills drift; review on touch.
- Is it doing too much? Split a skill that triggers on unrelated situations.

> For a richer authoring/eval harness, install the upstream `skill-creator` from the Anthropic agent-skills collection and copy it here; this file is the project's minimal, self-contained baseline.
