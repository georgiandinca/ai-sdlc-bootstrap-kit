# CLAUDE.md

**This file is only a pointer. The single source of truth is [AGENTS.md](./AGENTS.md) — read it first.**

Everything Claude Code needs lives in `AGENTS.md`: mission, hard constraints, trust tiers, the MCP posture, roles/seats, the knowledge-grounding rule, the deliverable rules, and how to read source documents. `AGENTS.md` is the shared brief every AI tool reads, which is exactly why it is the one place we maintain.

## ⛔ The rule for this file — do not break it

**`AGENTS.md` is canonical. `CLAUDE.md` carries no rules, facts, or guidance of its own — it only points to `AGENTS.md`.**

- **No change may land in `CLAUDE.md` unless the same content is already in `AGENTS.md`.** If you are about to write something here, write it in `AGENTS.md` instead and leave this file as a pointer.
- **A diff that touches `CLAUDE.md` but not `AGENTS.md` is a mistake** — there is nothing unique to update here.
- **If `CLAUDE.md` and `AGENTS.md` ever disagree, `AGENTS.md` wins** and `CLAUDE.md` must be corrected back into a pointer.

This rule exists so the two files can never drift: maintain `AGENTS.md`, and every tool — Claude Code included — stays consistent.

## Claude Code specifics

- **Bundled skills** are auto-discovered from [`.claude/skills/`](./.claude/skills/) — the `playbook-<seat>` role contracts and `skill-creator`. See [`.claude/skills/README.md`](./.claude/skills/README.md).
- **Session hooks** are configured in [`.claude/settings.json`](./.claude/settings.json) (SessionStart / SessionEnd / Stop) and run the `scripts/session/` scripts.
- **MCP servers** are declared in [`.mcp.json`](./.mcp.json).

---

**Companion files:** [`AGENTS.md`](./AGENTS.md) (the brief), [`ONBOARDING.md`](./ONBOARDING.md) (first-run setup), [`WORKING-AGREEMENT.md`](./WORKING-AGREEMENT.md), [`README.md`](./README.md), [`FOLDER-INDEX.md`](./FOLDER-INDEX.md), [`INDEX.md`](./INDEX.md).
