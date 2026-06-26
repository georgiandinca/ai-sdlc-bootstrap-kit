# FOLDER-INDEX — directory map

A map of every directory in this workspace and what belongs there. When in doubt about where something goes, start here, then `WORKING-AGREEMENT.md` §3.

```
<PROJECT_NAME>/
├── AGENTS.md                       # canonical brief (read first)
├── CLAUDE.md                       # pointer → AGENTS.md
├── README.md                       # human setup
├── ONBOARDING.md                   # first-run gatekeeper
├── WORKING-AGREEMENT.md            # cross-tool organisation, lifecycle, session ritual
├── INDEX.md                        # cross-artefact index (received docs, ADRs, decisions)
├── USER.md                         # per-user, git-ignored (created at onboarding)
├── .gitignore
├── .mcp.json                       # MCP connectors (Roles × Skills × MCP matrix)
├── .pre-commit-config.yaml         # local fast gates (skills, frontmatter, commit msg)
│
├── .claude/
│   ├── settings.json               # Claude Code hooks (session-start ritual)
│   └── skills/                     # INVOKABLE Agent Skills (auto-discovered)
│       ├── README.md
│       ├── playbook-architect/     # role-seat contracts — invoke to reason from a seat
│       ├── playbook-em/
│       ├── playbook-product/
│       ├── playbook-dev/
│       ├── playbook-qa/
│       └── skill-creator/          # create / improve skills
│
├── .github/
│   └── workflows/
│       ├── ai-governance.yml       # validate skills + frontmatter on PRs / main
│       └── docs.yml                # (optional) build a docs site
│
├── scripts/
│   ├── bootstrap.sh                # initialise a new project from the kit
│   ├── validate-skills.py          # SKILL.md conformity (agentskills.io)
│   ├── validate-frontmatter.py     # frontmatter contract on docs
│   ├── session/                    # start.sh, sync.sh, wrapup.sh, config
│   ├── git/                        # commit_msg_ticket.py (issue-key hook)
│   └── knowledge/                  # ingest.py (RAG/KG ingestion stub)
│
├── docs/                           # THE KNOWLEDGE TREE (additive, demand-driven)
│   ├── received/                   # immutable client / stakeholder input
│   ├── drafts/                     # exploratory, not authoritative
│   ├── architecture/
│   │   └── decisions/              # numbered ADRs (ADR-0001-…)
│   ├── governance/                 # RACI, rollout, sign-offs, internal rules
│   ├── knowledge/                  # sources for the KG/RAG/vector layer (pillar 5)
│   │   ├── README.md
│   │   ├── schema.md
│   │   └── sources/                # the ingestable source documents
│   ├── onboarding/                 # how to join the project
│   ├── methodology/                # framework + continuous-improvement loop (pillar 7)
│   └── ai-context/
│       ├── README.md               # AI context contract
│       └── skills/<role>/          # READ-ON-DEMAND MCP task playbooks (not auto-invoked)
│
└── dashboard/                      # AI-utilization dashboard (DB + web)
    ├── README.md
    ├── app.py                      # Streamlit app
    ├── schema.sql
    └── requirements.txt
```

## Two kinds of skill, two homes

- **Invokable** skills — `.claude/skills/<name>/SKILL.md`, auto-discovered and triggered by the agent.
- **Read-on-demand** MCP task playbooks — `docs/ai-context/skills/<role>/`, reference docs the agent reads when relevant, not auto-invoked.

See `.claude/skills/README.md` and `docs/ai-context/README.md`.
