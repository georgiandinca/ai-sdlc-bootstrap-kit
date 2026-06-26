# AI context contract

Operational rules for every AI agent on this project (Claude, Copilot, …). This expands [`AGENTS.md` §4](../../AGENTS.md) into day-to-day practice. **If this file and `AGENTS.md` ever disagree, `AGENTS.md` wins.**

## 1. Trust tiers (recap)

| Tier | Sources | Rule |
|---|---|---|
| **Authoritative** | `docs/received/`, approved ADRs, the standards/regulations corpus you vendor in | cite directly |
| **Working** | canonical `docs/<topic>/` with `status: draft\|under-review`; mirrored wiki pages | use **with citation + status flag** |
| **Exploratory** | `docs/drafts/**`, chat, brainstorm boards, working files | read only if the user names the path |
| **Restricted** | `.private/**`, ACL'd locations | read only on explicit, path-referenced request; never leak elsewhere |

## 2. MCP / connector posture — scoped write

| Surface | AI may | Human applies |
|---|---|---|
| **Issue tracker** | create/modify backlog & sprint items under a named seat | — (reviewed in-tool) |
| **Docs / wiki** | write drafts | promotion of a draft to canonical |
| **Knowledge store** | ingest & query | curation / deletion of sources |
| **Git host** | branches / PRs | merge to a protected branch; AI never pushes it |

Every AI write must be **attributable to a named seat and a session** and leave a reviewable trail. No silent changes to load-bearing artefacts.

## 3. Knowledge grounding (pillar 5)

Before answering from memory, check whether the project's own knowledge answers it:

```bash
python3 scripts/knowledge/ingest.py --query "your question"
```

Cite the source file and its trust tier. If the index is empty or stale, say so — don't invent. The schema and how-to live in [`../knowledge/README.md`](../knowledge/README.md). In production this query path is served by the `knowledge` MCP server in [`../../.mcp.json`](../../.mcp.json).

## 4. Skills as versioned artefacts — two homes

| Kind | Location | Behaviour |
|---|---|---|
| **Invokable Agent Skills** | [`../../.claude/skills/<name>/SKILL.md`](../../.claude/skills/) | auto-discovered & triggered; conform to agentskills.io |
| **MCP task playbooks** (read-on-demand) | `docs/ai-context/skills/<role>/` (here) | reference docs — *how we run this project* over the connectors; not auto-invoked |

The `playbook-<seat>` role contracts live in `.claude/skills/` (invokable). The connector-specific operational playbooks live here:

```
docs/ai-context/skills/
├── product/   # backlog & sprint automation over the issue-tracker MCP
└── qa/        # test-traceability over the tracker + knowledge MCP
```

**Conformity gate.** Every `SKILL.md` is validated by [`../../scripts/validate-skills.py`](../../scripts/validate-skills.py); every governed doc by [`../../scripts/validate-frontmatter.py`](../../scripts/validate-frontmatter.py). Both run locally (pre-commit) and in CI (the enforced merge gate).

## 5. Sync discipline

- **Pull-on-demand** for live state via MCP.
- **Promote-on-stable** for load-bearing content: a human exports to Markdown/PNG in `docs/<topic>/` with a `source:` frontmatter line. No background sync, no mirror jobs.
