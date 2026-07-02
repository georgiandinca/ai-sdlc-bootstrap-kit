# AGENTS.md — `<PROJECT_NAME>`

**Canonical brief for every AI agent and every team member working in this project.**

This is the single source of truth that **all AI tools read** — Claude (Claude Code + claude.ai), GitHub Copilot, Cursor, and any other agent that resolves `AGENTS.md`. Keeping the brief here keeps every tool consistent. **Read it before doing anything else.**

> **Where this file lives.** The canonical copy is at the repo root. `CLAUDE.md` (and any other tool-specific file) is a thin pointer to this file. **Edit the brief here; don't fork it.**
>
> **Placeholders.** Anything in `<ANGLE_BRACKETS>` is a value you fill in when you bootstrap the project (see `scripts/bootstrap.sh`). Search for `<` to find them all.

---

## 0. Startup — user identity and onboarding

Every AI agent **must** execute this sequence at the start of every session in this repo:

1. **Check for `USER.md`** at the repo root.
2. **If `USER.md` does not exist** → load and follow [`ONBOARDING.md`](./ONBOARDING.md). Do not proceed with project work until onboarding is complete and `USER.md` has been created.
3. **If `USER.md` exists** → read it. Use the user's name, role/seat, and communication preferences to tailor all responses for the rest of this session.

### What lives in `USER.md`

`USER.md` is a **per-user, git-ignored** file that stores:

| Field | Purpose |
|---|---|
| **Full name** | How to address the user |
| **Email** | Used for the `author` field in YAML frontmatter (§4.2) |
| **Seat** | Their role on this project (from the seat list in §5) |
| **Git comfort** | How much git to surface to this seat — `git-native` / `guided` / `hidden`; governs session-sync ergonomics (see [`docs/ai-context/lifecycle-moments.md`](./docs/ai-context/lifecycle-moments.md)) |
| **Communication preferences** | Tone, detail level, language, technical depth — adapts the AI's style |
| **Preferences** | AI-managed section for accumulated preferences |
| **Onboarding status** | AI-managed section tracking what failed during onboarding — check each session and retry pending fixes |

### Rules for `USER.md`

- **Keep it under 100 lines.** Thin, durable facts only — no session state, no temporary notes.
- **Never store secrets.** No passwords, tokens, API keys.
- **The AI may update it** as it learns preferences, but confirms before removing existing entries.
- **It is git-ignored.** It never leaves the user's machine. Do not reference its contents in commits, PRs, or deliverables.

---

## 1. Mission

> Fill this in for your project. One paragraph: what are we building, for whom, by when, and under which hard constraints?

`<PROJECT_NAME>` is `<ONE_LINE_DESCRIPTION>`. The team delivers it following an **AI-augmented Software Development Life Cycle (SDLC)**: AI agents are first-class collaborators across discovery, design, build, test, and operate — under explicit governance, with every load-bearing change attributable to a named human seat.

This repository is bootstrapped from the **AI-SDLC Bootstrap Kit**. The kit encodes seven pillars (see [`docs/methodology/framework.md`](./docs/methodology/framework.md)):

1. **Setup** — one-command bootstrap of a governed, AI-ready repo.
2. **Onboarding** — per-machine, per-user first-run that installs tooling and creates `USER.md`.
3. **Governance & internal rules** — this brief, the Working Agreement, trust tiers, and the MCP write posture.
4. **CI/CD for the AI framework** — rules expressed as scripts and enforced as merge gates.
5. **Knowledge layer** — sources ingested into a Knowledge Graph / RAG / vector store the agents can ground on.
6. **Roles × Skills × MCP** — each seat has invokable skills and a scoped set of MCP connectors.
7. **Human methodology & continuous improvement** — the dashboard, retros, and cost/quality feedback loop that keep the human in the loop.

## 2. The workspace — what lives where

```
<PROJECT_NAME>/
├── AGENTS.md                  # this brief — canonical, read first
├── CLAUDE.md                  # thin pointer → AGENTS.md
├── README.md                  # human setup
├── ONBOARDING.md              # first-run gatekeeper (loaded only when USER.md is missing)
├── WORKING-AGREEMENT.md       # how we organise across tools, lifecycle, MCP posture
├── USER.md                    # per-user, git-ignored (created at onboarding)
├── FOLDER-INDEX.md            # directory map
├── INDEX.md                   # cross-tool / cross-artefact index
├── .claude/skills/            # invokable Agent Skills (role playbooks + skill-creator)
├── .github/workflows/         # CI: AI-governance gates
├── scripts/                   # session ritual, validators, git hooks, bootstrap, ingest
├── docs/                      # the knowledge tree (see §2.1 and FOLDER-INDEX.md)
└── dashboard/                 # AI-utilization dashboard (DB + web)
```

> If your project also holds application code (frontend, backend, services), add those folders/repos here and describe their stack. The brief governs all of them.

### 2.1 The knowledge tree (`docs/`)

The `docs/` tree is **additive and demand-driven** — roles create topic folders as needs arise, following the lifecycle ritual (`WORKING-AGREEMENT.md` §4). Durable, shared knowledge lives here:

| Folder | Holds |
|---|---|
| `docs/received/` | Immutable client / stakeholder input — never modified |
| `docs/drafts/` | Exploratory, not authoritative |
| `docs/architecture/decisions/` | Numbered ADRs (`ADR-0001-…`) |
| `docs/governance/` | RACI, rollout plans, sign-offs, internal rules |
| `docs/knowledge/` | Sources ingested into the KG/RAG/vector layer (pillar 5) |
| `docs/onboarding/` | How to join the project |
| `docs/methodology/` | The framework, working-agreement rationale, continuous-improvement loop (pillar 7) |
| `docs/ai-context/` | Trust tiers, MCP posture, read-on-demand role playbooks, session lifecycle moments, commit-attribution convention |

## 3. Hard constraints (non-negotiable)

> Replace these with your project's real constraints. Examples to adapt:

- **Deadline / milestones.** `<KEY_DATES>` are binding. Surface slippage early.
- **No secrets in the repo.** Never commit tokens, passwords, keys, or real personal data. Use clearly synthetic example data.
- **License / IP posture.** `<LICENSE_AND_IP_RULES>` (e.g. open-source-first, third-party license review).
- **Standards on critical paths.** `<MANDATORY_STANDARDS>` — no proprietary shortcuts where a standard applies.
- **No fabrication.** No invented dates, identifiers, decisions, or citations. If unknown, say so.

## 4. AI tools & the trust contract

### 4.1 Tools in use

| Tool | Used by | Reads `AGENTS.md`? | Notes |
|---|---|---|---|
| **Claude** (Claude Code, claude.ai) | All seats | Yes — primary | Main agent. Skill-driven (`.claude/skills/playbook-<seat>/`). |
| **GitHub Copilot** (IDE, chat) | All seats, in-flow | Honour this brief manually; point it here | In-document drafting; promote anything load-bearing into a governed file. |
| **`<OTHER_AGENT>`** | `<SEATS>` | `<yes/no>` | `<notes>` |

### 4.2 Trust tiers — what an AI may rely on

| Tier | Sources | Rule |
|---|---|---|
| **Authoritative** | `docs/received/`, approved ADRs (`status: approved`), the regulations/standards corpus you vendor in | Cite directly; do not paraphrase from memory. |
| **Working** | Canonical `docs/<topic>/` with `status: draft\|under-review` | Use **with citation + status flag**. |
| **Exploratory** | `docs/drafts/**`, chat, brainstorm boards, working files | Do **not** read unless the user names the file/path. |
| **Restricted** | `.private/**`, ACL'd locations | Read only when the user asks and references the path; never leak into deliverables elsewhere. |

**Naming a path is explicit.** For Exploratory and Restricted sources, "search the repo" or "look around" does **not** grant permission — the user must reference the specific file.

Maturity is signalled by **location + frontmatter**. Every long-lived Markdown deliverable carries:

```yaml
---
title: "…"
status: draft | under-review | approved | superseded
owner: <accountable seat>    # governance seat — NOT necessarily the creator
author: Name <email>         # actual human creator — from USER.md, fallback to git config
created: YYYY-MM-DD           # set once
classification: public | internal | restricted
last-reviewed: YYYY-MM-DD
ai-trust: authoritative | working | exploratory
---
```

`owner` is the accountable seat (default: the seat confirmed at session start); `author`/`created` record who actually made the file. Never hard-code a seat you are not operating as.

### 4.3 MCP / connector posture — **scoped write**

We run MCP connectors so agents can act in our tools (issue tracker, docs/wiki, knowledge store). The posture is **scoped write**, not blanket read-only:

| Surface | AI may… | Human applies… |
|---|---|---|
| **Issue tracker** (`<Jira/Linear/GitHub Issues>`) | create & modify backlog/sprint items under a named-seat owner | nothing extra — every write is attributable to a seat + session and reviewed in-tool |
| **Docs / wiki** (`<Confluence/Notion/…>`) | write drafts | promotion of a draft to canonical (page owner) |
| **Knowledge store** (`<vector DB / KG>`) | ingest & query | curation / deletion of sources (knowledge owner) |
| **Git host** (`<GitHub/GitLab/Bitbucket>`) | open branches / PRs | merge to a protected branch via review; AI never pushes a protected branch to origin |

Guardrail: **no silent changes.** An AI never modifies a load-bearing artefact without a named human owner and a reviewable trail. See `WORKING-AGREEMENT.md` §5 and `docs/ai-context/README.md`.

### 4.4 Knowledge grounding (pillar 5)

When a question can be answered from the project's own knowledge, **ground on it instead of guessing.** The ingestion stub and schema live under `docs/knowledge/` and `scripts/knowledge/ingest.py`. Cite the source file and its trust tier (§4.2). If the knowledge store is empty or stale, say so rather than inventing an answer.

### 4.5 Commit attribution

Every commit is classifiable as **human**, **AI-authored**, or **mixed** so AI usage stays measurable (pillar 7). AI-assisted commits carry a `Co-Authored-By: <agent> <email>` trailer. The convention — and the `git-ai` upgrade path for line-level attribution — is in [`docs/ai-context/attribution.md`](./docs/ai-context/attribution.md).

## 5. Roles & named seats

This template ships with the **full SDLC team**. Each seat has an invokable role-contract skill in `.claude/skills/playbook-<seat>/` and a scoped MCP profile in `.mcp.json`.

| Seat | Owns (information-architecture view) | Playbook |
|---|---|---|
| **Architect** | Workspace shape; ADRs; AI-context contract; arbitrates "where does X go". | `playbook-architect` |
| **Engineering Manager (EM)** | Code repos; engineering specs; dev runbooks; CI; co-signs ADRs. | `playbook-em` |
| **Product (PO/PM)** | Backlog, priority, acceptance criteria; roadmap, milestones, plan. | `playbook-product` |
| **Developer** | Code + unit tests in the relevant repo; implementation decisions. | `playbook-dev` |
| **QA** | Test strategy, test plans, traceability; quality gates. | `playbook-qa` |

> **Naming discipline.** Fill `<SEAT_HOLDERS>` with first names only. Don't invent a name for an unfilled seat — refer to it by role.

## 6. Languages

- Default for new artefacts: **`<PRIMARY_LANGUAGE>`** unless the audience requires otherwise.
- Do not auto-translate user-provided text unless asked.

## 7. Deliverable format rule — markdown is the source of truth

**Markdown is the single source of truth, and the primary form committed to Git.** We do not commit binary `.docx`/`.pptx` deliverables — they don't diff and bloat the repo. When a binary is needed (a stakeholder deliverable, a deck), **generate it on demand from the markdown** and deliver it through the sharing channel, not Git. Diagrams are committed as source (`.excalidraw` / `.drawio` / Mermaid) with a PNG export alongside when needed.

## 8. What to do when asked

1. **Check the trust tier first** (§4.2). Cite Authoritative directly; flag Working with status; ignore Exploratory unless named.
2. **Ground on the knowledge layer** (§4.4) before answering from memory.
3. **Distinguish "decided" from "recommended."** Treat unmarked claims as proposals until confirmed by a named seat or an approved ADR.
4. **Flag deadlines & dependencies.**
5. **Respect the MCP posture** (§4.3) and the session ritual (`WORKING-AGREEMENT.md` §5) — never promote silently.
6. **Put outputs in the right place** under a sensible `docs/<topic>/` folder; **ask before creating a new top-level folder.**
7. **Confirm your seat at session start** and stamp new artefacts with `owner` = that seat, `author`/`created` from git. Don't default ownership to the Architect.
8. **No fabricated facts.** If unknown, say so.

---

**Companion files:** [`WORKING-AGREEMENT.md`](./WORKING-AGREEMENT.md) (how we organise across tools), [`CLAUDE.md`](./CLAUDE.md) (thin pointer), [`README.md`](./README.md) (setup), [`ONBOARDING.md`](./ONBOARDING.md) (first-run), [`FOLDER-INDEX.md`](./FOLDER-INDEX.md) (directory map), [`INDEX.md`](./INDEX.md) (cross-artefact index), [`docs/ai-context/README.md`](./docs/ai-context/README.md) (AI context contract).
