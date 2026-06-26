---
title: "<PROJECT_NAME> — Team Working Agreement"
status: under-review
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-06-26
classification: internal
last-reviewed: 2026-06-26
ai-trust: working
---

# `<PROJECT_NAME>` — Team Working Agreement

**How we organise project information across our tools and how AI agents plug in.**

**Companion files:** [`AGENTS.md`](./AGENTS.md) (canonical brief, read first), [`CLAUDE.md`](./CLAUDE.md), [`README.md`](./README.md), [`INDEX.md`](./INDEX.md).

---

## 1. Purpose & scope

This agreement defines **how the team organises information across our tools and repos, and how AI agents and external collaborators plug in**, so that:

- Every team member knows where to put or find something without asking.
- AI agents (Claude, Copilot, …) can tell what is reliable — they all read [`AGENTS.md`](./AGENTS.md).
- Material is versioned and recoverable as the project evolves.
- We don't spend more time organising than using the information.

---

## 2. Tool map & content classification

### 2.1 Tool map — each tool owns what it is best at

Things are written **once**, in their owning tool. Cross-references point to the canonical location; nothing is duplicated by default.

| Tool | Owns | Doesn't own |
|---|---|---|
| **Git** (`<GitHub/GitLab/Bitbucket>`) | Code; governance knowledge (this `docs/` tree): ADRs, specs, architecture artefacts (`.md`, `.excalidraw`, `.drawio`), the knowledge sources, AI skills/playbooks, the cross-artefact index | Meeting notes, free-form prose, signed PDFs, decks under active edit, brainstorm boards |
| **Issue tracker** (`<Jira/Linear/GitHub Issues>`) | Epics / stories / bugs / risks; sprint & milestone planning; status | Knowledge — link out to Git/wiki instead of pasting into tickets |
| **Docs / wiki** (`<Confluence/Notion>`) | Decisions log (short prose); meeting notes; runbooks; narrative docs | Source-of-truth for architecture (Git wins); work items (tracker wins) |
| **File share** (`<SharePoint/Drive>`) | Signed PDFs & legal originals; client deliverables under formal review; large binaries | Drafts that should be versioned line-by-line (use Git); structured knowledge (use the wiki) |
| **Chat** (`<Teams/Slack>`) | Synchronous chat; ad-hoc calls; quick file-sharing | Anything we want to find again in 30 days — promote to one of the above |

Adding a new tool requires a justification at the next milestone review (anti-bloat clause, §8).

### 2.2 Content classification

Three labels, applied everywhere via folder location or metadata:

- **Public** — shareable with anyone. Default for Git public folders.
- **Internal** — team + named externals only. Default for the wiki & file share.
- **Restricted** — named people only. ACL'd file share, or `.private/` in Git.

---

## 3. Workspace structure

```
<PROJECT_NAME>/
├── AGENTS.md            # canonical brief
├── CLAUDE.md            # pointer → AGENTS.md
├── README.md            # setup
├── ONBOARDING.md        # first-run gatekeeper
├── WORKING-AGREEMENT.md # this document
├── INDEX.md             # cross-artefact index
├── .claude/skills/      # invokable role playbooks + skill-creator
├── .github/workflows/   # CI: AI-governance gates
├── scripts/             # session ritual, validators, hooks, bootstrap, ingest
├── docs/                # knowledge tree (see §3.1)
└── dashboard/           # AI-utilization dashboard
```

### 3.1 The knowledge tree (`docs/`) — additive, demand-driven

```
docs/
├── received/            # immutable client / stakeholder input
├── drafts/              # exploratory, not authoritative
├── architecture/
│   └── decisions/       # numbered ADRs (ADR-0001-…)
├── governance/          # RACI, rollout, sign-offs, internal rules
├── knowledge/           # sources ingested into the KG/RAG/vector layer (pillar 5)
├── onboarding/          # how to join the project
├── methodology/         # the framework + continuous-improvement loop (pillar 7)
└── ai-context/          # trust tiers, MCP posture, read-on-demand role playbooks
    ├── README.md
    └── skills/<role>/…  # MCP task playbooks (read-on-demand, not auto-invoked)
```

New folders are **additive** — nothing existing moves. A new folder must justify itself by removing a recurring "where does X go?" question (anti-bloat, §8).

---

## 4. Lifecycle model — location + tag

Maturity is signalled two ways.

### 4.1 Location-based (the hard boundary)
- **Git:** `docs/drafts/<topic>/` (exploratory) vs `docs/<topic>/` (canonical).
- **Wiki:** a `Drafts` parent page vs the topic parent page.
- **File share:** a working folder vs a final-deliverables folder.

### 4.2 Tag-based (within the canonical area)
Every long-lived Markdown deliverable carries the frontmatter block from `AGENTS.md` §4.2 — `status`, `owner` (accountable seat) distinct from `author` (human creator) and `created`, plus `classification`, `last-reviewed`, `ai-trust`.

### 4.3 Promotion ritual
Moving drafts → canonical (or `under-review` → `approved`) is a **deliberate act**:
- **Git:** a PR named `promote: <path>` with the responsible seat identified.
- **Wiki:** a page-move with a one-line edit comment naming the approver.

**We do not promote silently.**

---

## 5. AI context contract & session ritual

The full operational contract lives in [`docs/ai-context/README.md`](./docs/ai-context/README.md). Summary:

### 5.1 Trust tiers
See `AGENTS.md` §4.2 (Authoritative / Working / Exploratory / Restricted).

### 5.2 Skills as versioned artefacts
Team AI skills live in two homes by kind:
- **Invokable Agent Skills** (auto-discovered): `.claude/skills/<name>/SKILL.md` — the `playbook-<seat>` role contracts, `skill-creator`, and any generic baseline. Conform to [agentskills.io](https://agentskills.io/specification).
- **MCP task playbooks** (read-on-demand): `docs/ai-context/skills/<role>/` — *how we run this project* over the connectors.

Both are versioned, PR-reviewed, and shared. Personal prompts stay personal.

### 5.3 MCP / connector posture — scoped write
See `AGENTS.md` §4.3. Every AI write is **attributable to a named seat + session** and leaves a reviewable trail. No silent changes to load-bearing artefacts.

### 5.4 Sync discipline
- **Pull-on-demand** for live state via MCP.
- **Promote-on-stable** for load-bearing content: a human exports to Markdown/PNG in `docs/<topic>/` with a `source:` frontmatter line. No background sync, no mirror jobs.

### 5.5 Session lifecycle ritual

Every agent session follows a lightweight ritual (the git workflow on the board: **Repo → Edit → Pull Request**):

- **Session start.** Confirm which seat you are operating as. The Claude Code hook (`.claude/settings.json`) runs `scripts/session/start.sh`, which prints git identity, branch, and sync state, and offers a fast-forward sync (`scripts/session/sync.sh`) — run it **only on explicit confirmation**.
- **Authoring.** New Markdown carries `owner` = confirmed seat, `author` = `git config user.name`/`user.email`, `created` = today. Don't default `owner` to the Architect.
- **Session end.** Offer to commit + open a PR: `scripts/session/wrapup.sh "<message>" <paths>`. The script branches off a protected branch, commits, pushes, and opens a PR (or prints the PR URL). **AI never pushes a protected branch to origin.**
- **Commit messages.** Reference the issue key (`<TICKET-123>`) so the host links commits to the issue. The `commit-msg` hook (`scripts/git/commit_msg_ticket.py`) enforces or nudges this; `[no-ticket]` exempts genuine non-ticket commits.

The scripts are plain shell and can be run by hand for any editor that doesn't support Claude Code hooks.

---

## 6. External collaboration

- **Incoming** from clients/stakeholders lands in `docs/received/<source>/<YYYY-MM-DD>-<name>.<ext>` — immutable. A one-line entry in `INDEX.md` records source and date.
- **Outgoing** formal deliverables go through the file share with explicit classification; interim material via chat/email. Don't share repo URLs externally before checking classification.

---

## 7. Roles & responsibilities for information architecture

| Seat | Responsibility |
|---|---|
| **Architect** | Workspace shape; `AGENTS.md`; ADRs; AI-context contract; arbitrates "where does X go". |
| **EM** | Code repos; engineering specs; runbooks; CI; co-signs ADRs. |
| **Product (PO/PM)** | Backlog & priority; acceptance criteria; roadmap, milestones, plan. |
| **Developer** | Code + unit tests; implementation decisions. |
| **QA** | Test strategy, plans, traceability; quality gates; owns `docs/qa/` if created. |
| **Everyone** | Honours the lifecycle ritual; never promotes silently; tags classification; confirms their seat at session start; follows wrap-up. |

---

## 8. Adaptation cadence

- **Per-milestone review.** Changes via PR; merge requires the agreed approvals.
- **Architect patches.** Typo/clarification PRs land without ceremony.
- **Anti-bloat clause.** A new folder, lifecycle state, or tool must justify itself by removing a recurring "where does X go?" question. If we can't name the question, we don't add the rule.

---

## Appendix — Glossary

| Term | Meaning |
|---|---|
| **Canonical area** | A topic folder in Git (`docs/<topic>/`) or a topic parent page in the wiki. The opposite of drafts/working areas. |
| **Promotion** | A deliberate move of an artefact from drafts/working to canonical (or `under-review` → `approved`). |
| **Trust tier** | The AI-context label from location + frontmatter — Authoritative / Working / Exploratory / Restricted (`AGENTS.md` §4.2). |
| **Scoped write** | The MCP posture (§5.3): AI may write tracker items & wiki drafts under a named seat; protected branches and final deliverables stay human-applied. |
| **Named seat** | One of the project roles: Architect, EM, Product, Developer, QA. |
