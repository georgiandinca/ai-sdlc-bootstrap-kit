# AI-SDLC Bootstrap Kit

A **bootstrap skeleton for AI-augmented software projects** — drop it into a new repo and you start with AI agents as governed, first-class collaborators across the whole Software Development Life Cycle.

It turns a hand-drawn operating model (one whiteboard, titled *AUTOMATIZARE*) into a runnable scaffold: a canonical agent brief, role-seat skills, scoped MCP connectors, a knowledge layer agents ground on, governance rules enforced as CI gates, an onboarding gatekeeper, and a utilization dashboard with a human-owned improvement loop.

> **New to it?** Read [`docs/SPEC.md`](./docs/SPEC.md) for the full specification, then [`template/AGENTS.md`](./template/AGENTS.md) to see the brief a generated project gets.

## Repository layout

```
AI-SDLC-Bootstrap-Kit/
├── README.md                # you are here — what the kit is, how to use it
├── docs/                    # THE KIT's own docs (not a generated project's)
│   ├── SPEC.md              # specification of the template
│   ├── visuals/             # framework diagrams (Excalidraw + Mermaid)
│   └── presentation/        # the pitch deck
└── template/                # THE SKELETON — copied into a new project by bootstrap.sh
    ├── AGENTS.md  CLAUDE.md  ONBOARDING.md  WORKING-AGREEMENT.md  README.md …
    ├── .claude/skills/       # invokable role playbooks + skill-creator
    ├── .github/workflows/    # CI: AI-governance gates
    ├── scripts/              # session ritual, validators, hooks, bootstrap, ingest
    ├── docs/                 # the generated project's knowledge tree
    └── dashboard/            # AI-utilization dashboard (DB + web)
```

## The seven pillars

The kit operationalises an AI-augmented SDLC as seven pillars — see [`template/docs/methodology/framework.md`](./template/docs/methodology/framework.md):

| # | Pillar | Where it lives in `template/` |
|---|---|---|
| 1 | **Setup** | `scripts/bootstrap.sh` |
| 2 | **Onboarding** | `ONBOARDING.md`, `docs/onboarding/` |
| 3 | **Governance & rules** | `AGENTS.md`, `WORKING-AGREEMENT.md`, `docs/ai-context/` |
| 4 | **CI/CD for the AI framework** | `.github/workflows/ai-governance.yml`, `scripts/validate-*.py` |
| 5 | **Knowledge layer (KG/RAG/vector)** | `docs/knowledge/`, `scripts/knowledge/ingest.py` |
| 6 | **Roles × Skills × MCP** | `.claude/skills/playbook-*`, `.mcp.json` |
| 7 | **Human methodology & continuous improvement** | `docs/methodology/continuous-improvement.md`, `dashboard/` |

## Install the kit into a project

Three routes, pick whichever fits your setup.

**Claude Code plugin.** In any project, install the kit's marketplace once, then the plugin:

```bash
claude plugin marketplace add georgiandinca/ai-sdlc-bootstrap-kit
claude plugin install ai-sdlc-kit@ai-sdlc-bootstrap-kit
```

Then, in that project, ask the agent to set up the kit — for example `/ai-sdlc-kit:install-ai-sdlc-kit` — and it drives detection, layout choice and merge for you.

**Other coding agents (not Claude Code).** Clone the kit alongside or into your project, then point your agent at the skill's instructions:

```bash
git clone https://github.com/georgiandinca/ai-sdlc-bootstrap-kit /tmp/ai-sdlc-kit
```

Point the agent at `/tmp/ai-sdlc-kit/.claude/skills/install-ai-sdlc-kit/SKILL.md` and ask it to follow those instructions for your project.

**Terminal, no agent.** Run `bootstrap.sh` directly. `--layout` picks where the kit sits relative to the project's code — `embedded` (default), `monorepo`, `sidecar` or `parent`; run `--help` for what each means. `--merge` makes the install non-destructive: on a non-empty target it merges file-by-file / block-by-block instead of clobbering, and the pre-existing files stay untouched wherever the kit has nothing to add.

```bash
# From the kit root:
template/scripts/bootstrap.sh \
  --name "Acme Wallet" \
  --slug acme-wallet \
  --dir ../acme-wallet \
  --desc "A consumer payments wallet" \
  --ticket ACME \
  --host github \
  --layout embedded \
  --merge
```

This copies the template, substitutes `<PLACEHOLDERS>`, initialises git, and installs the hooks. Then open the new repo in Claude Code — it runs `ONBOARDING.md` to create your per-user `USER.md`, and you fill the remaining placeholders (`AGENTS.md` §1 mission, §3 constraints, §4 connectors).

## Verify the template locally

```bash
cd template
pip install "pyyaml>=6"
python3 scripts/validate-skills.py          # skills conform to agentskills.io
python3 scripts/validate-frontmatter.py     # doc maturity/trust contract
python3 scripts/knowledge/ingest.py --build # knowledge layer builds
```

These are the same gates the generated project's CI runs ([`template/.github/workflows/ai-governance.yml`](./template/.github/workflows/ai-governance.yml)).

## Design principles

- **One brief, every tool.** `AGENTS.md` is canonical; `CLAUDE.md` and friends are thin pointers that can't drift.
- **Attributable, never silent.** Every AI change to a load-bearing artefact has a named seat and a reviewable trail (scoped-write MCP posture).
- **Rules as code.** Governance is expressed as scripts and enforced as merge gates.
- **Ground, don't guess.** Agents answer from the project's knowledge layer, with the source's trust tier.
- **Human owns the loop.** Promotion, sign-off, and curation stay human; the dashboard + retro turn usage into improvements.
- **Anti-bloat.** A rule earns its place only by removing a recurring real question.

## Provenance

Distilled from a real multi-repo programme's governance setup, generalised and stripped of all project specifics, and aligned to the *AUTOMATIZARE* whiteboard model.

## Contributing

Contributions are welcome — see [`CONTRIBUTING.md`](./CONTRIBUTING.md) for the
workflow, local checks, and conventions, and [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md)
for community expectations. Security issues: please follow [`SECURITY.md`](./SECURITY.md)
rather than opening a public issue.

## License

Released under the [MIT License](./LICENSE) — you are free to use, copy, modify,
and distribute this kit, including in commercial and closed-source projects.
