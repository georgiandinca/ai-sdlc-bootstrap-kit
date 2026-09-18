---
title: "Kit installer skill — install and onboard the kit in any project (design)"
status: draft
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-09-18
classification: internal
ai-trust: working
---

# Kit Installer Skill — `install-ai-sdlc-kit`

**Goal.** Today the kit is installed by hand: point an agent at a local clone of this
repo, ask it to run `scripts/bootstrap.sh`, then ask it to start onboarding. That works
for the kit's author and nobody else. This theme turns those two steps into **one
invokable skill, installable from the public repo, that works in any project** — it
first works out which situation the project is in (no kit / kit present but this
operator not onboarded / fully set up), then does only what that situation needs.

The skill also resolves the question `bootstrap.sh` never asked: **where the kit
lives relative to the code** — inside the repo, at a monorepo root, beside the repos,
or above them.

**Trade-offs accepted (brainstorm):** the skill reports version drift but never updates
an installed kit (that is Theme 2, safe template propagation); non-Claude agents can run
the skill but cannot auto-trigger it; and in the sidecar/parent layouts the governance
hooks protect the kit's own repo, not the code repos — documented, not solved.

---

## 1. Decisions (resolved in brainstorming)

| # | Decision | Choice |
|---|---|---|
| 1 | Kit source | **Clone the public repo** `https://github.com/georgiandinca/ai-sdlc-bootstrap-kit` at a pinned tag/branch into a temp dir. No local-path mode — it only ever works on the author's machine. |
| 2 | Install into an existing project | **`bootstrap.sh` gains a merge mode.** Never clobber: create what is missing, append marked blocks to known files, report real collisions and leave them untouched. |
| 3 | Layouts supported | **All four**, detected/asked in order: `embedded` → `monorepo` → `sidecar` → `parent`. |
| 4 | Pointer files in code repos | **Ask per repo, default yes**, record the answer in the manifest and `AGENTS.md` §2. Merge into an existing context file via a marked block — never overwrite. |
| 5 | Other AI tools | **Ask which tools the team uses**, write one marked pointer block per chosen tool. `AGENTS.md` stays canonical for every tool that reads it. |
| 6 | Hooks / pre-commit | **Flexible**: hooks at the kit root, merged into an existing `.pre-commit-config.yaml` in a code repo, or skipped (no versioning / not wanted). |
| 7 | Onboarding | **Delegate, never duplicate.** The skill hands over to the installed `ONBOARDING.md`; it holds no copy of the steps. |
| 8 | Version drift | **Detect and report only.** Updating an installed kit stays with Theme 2. |
| 9 | Distribution | **Claude Code plugin** from this repo, plus a documented clone-and-point route for other agents and a `--non-interactive` terminal route. |
| 10 | Project README | The installed project's README is **generated with that project's specifics** (name, layout, repos and roles, where to start), not the generic template copy. |

---

## 2. Where the pieces live

```
AI-SDLC-Bootstrap-Kit/
├── .claude-plugin/
│   ├── plugin.json                 # NEW — plugin manifest
│   └── marketplace.json            # NEW — so `/plugin marketplace add <repo>` works
├── .claude/skills/install-ai-sdlc-kit/
│   ├── SKILL.md                    # NEW — decides; stays short
│   ├── scripts/detect-situation.sh # NEW — the situation report (JSON on stdout)
│   └── references/
│       ├── layouts.md              # NEW — the four layouts in detail
│       └── pointer-blocks.md       # NEW — block templates per tool/harness
└── template/
    ├── scripts/bootstrap.sh        # CHANGED — merge mode, layouts, manifest, README
    └── scripts/tests/test_bootstrap.sh  # NEW — layout/merge/idempotence tests
```

The manifest `.ai-sdlc/kit.json` is **not shipped in `template/`** — `bootstrap.sh`
generates it at the kit root of the installed project (§7).

The skill sits at the **kit repo root**, deliberately not in `template/`: it installs the
template, it is not part of what gets installed.

**Exact plugin manifest field names and file placement are verified against the current
Claude Code plugin documentation at implementation time** — not from memory.

---

## 3. The situation check

`detect-situation.sh` is read-only, runs before anything else, and prints one JSON
object. It never writes, never clones, and exits 0 even when things are missing —
"missing" is a finding, not an error.

```jsonc
{
  "cwd": "/path/to/project",
  "git": { "is_repo": true, "root": "…", "remote": "git@…", "branch": "main",
           "dirty": false, "has_commits": true },
  "kit": { "state": "absent|present-uncommitted|present-committed",
           "root": "…", "manifest": { "version": "1.2.0", "commit": "…",
           "layout": "embedded", "repos": [ … ], "hooks": "kit", "tools": ["claude"] } },
  "user_md": false,
  "hooks": { "config": true, "installed": false, "pre_commit_available": true },
  "layout_signals": {
     "workspace_files": ["pnpm-workspace.yaml"],
     "child_repos": ["apps/api"],
     "sibling_repos": ["../acme-web"]
  },
  "tooling": { "python3": "3.12.4", "pyyaml": true, "git": "2.45.0" }
}
```

**Layout signals, in the asking order:**

| Layout | Signals |
|---|---|
| `embedded` | cwd is a git repo with source in it and no workspace markers |
| `monorepo` | `pnpm-workspace.yaml`, `turbo.json`, `nx.json`, `lerna.json`, `go.work`, Cargo workspace, or `packages/`+`apps/` with per-package manifests |
| `sidecar` | sibling folders of cwd that are git repos |
| `parent` | child folders that are git repos while cwd is not (or is an empty repo) |

Signals **propose**, the operator **confirms**. A wrong guess costs one keystroke; an
unasked question costs a wrong install.

### Decision table

| Situation | Path |
|---|---|
| `kit.state = absent` | §4 Setup, then §5 Onboarding |
| `kit.state = present-uncommitted` | Report it, offer to commit, then re-evaluate |
| `kit.state = present-committed`, `user_md = false` | §5 Onboarding only |
| `kit.state = present-committed`, `user_md = true` | §6 Status report |

---

## 4. Setup

1. **Confirm the layout** (proposed from the signals, asked in the order above).
2. **Collect the project facts** — name, one-line description, ticket prefix, host.
3. **Collect the repos and their roles** for `monorepo` / `sidecar` / `parent`
   (e.g. `acme-api` = backend, `acme-web` = frontend). These become `AGENTS.md` §2.
4. **Ask the hooks mode** — `kit` (install at the kit root), `repo` (merge into an
   existing `.pre-commit-config.yaml`), `none`.
5. **Ask which AI tools the team uses** — each chosen tool gets a pointer block.
6. **Ask per code repo** whether to write a pointer into it (default yes).
7. **Show the full plan** — every file to be created, every file to be appended to,
   every collision that will be left alone — and get a yes.
8. **Clone the kit** at the pinned ref into a temp dir.
9. **Run `bootstrap.sh`** with the collected flags.
10. **Commit** — on a new branch when the target repo already has commits, so the
    install lands as a reviewable PR; directly on the current branch for a fresh repo.

### Safety rules

- Never write outside the confirmed target paths.
- Never overwrite an existing file; append inside markers or report and skip.
- Never commit without showing what will be committed.
- Never run the install when the target repo is dirty without saying so first.

---

## 5. Onboarding hand-off

The skill verifies `USER.md` is absent, then instructs the agent to read the installed
project's `ONBOARDING.md` and follow it, and stops there. It holds **no copy** of the
onboarding steps: one source of truth, no drift when `ONBOARDING.md` improves.

If `USER.md` exists, onboarding is skipped entirely (matching `AGENTS.md` §0).

---

## 6. Status report (already set up)

Reads the manifest and reports, each with a fix offered:

- **Version drift** — installed version/commit vs the public repo's latest tag, with the
  changelog between them. **Report only; no file updates** (Theme 2).
- **Hooks not installed** — offer `pre-commit install`.
- **Repos missing from `AGENTS.md` §2** — a sibling/child repo that appeared since install.
- **A code repo without a pointer block** — offer to add it.
- **Placeholders still unfilled** — the `<ANGLE_BRACKET>` list from `bootstrap.sh`.

---

## 7. Changes to `bootstrap.sh`

New flags, all with interactive defaults so existing usage keeps working:

| Flag | Values | Meaning |
|---|---|---|
| `--layout` | `embedded`\|`monorepo`\|`sidecar`\|`parent` | Where the kit sits relative to the code |
| `--merge` | — | Install into a non-empty target without clobbering |
| `--hooks` | `kit`\|`repo`\|`none` | Where pre-commit is wired, or not at all |
| `--no-git` | — | Do not init a repo or commit |
| `--repos` | `name=role,…` | Repos and their roles for `AGENTS.md` §2 |
| `--tools` | `claude,copilot,…` | Which pointer blocks to write |
| `--non-interactive` | — | Fail rather than prompt on a missing value |

### Merge semantics

| Target file state | Action |
|---|---|
| Absent | Create from the template |
| Present, kit-owned (has markers) | Replace the block between the markers |
| Present, project-owned, known-mergeable (`README.md`, `.gitignore`, `CLAUDE.md`, `AGENTS.md`, `.pre-commit-config.yaml`) | Append a marked block |
| Present, project-owned, not mergeable | Leave untouched, report, suggest the kit's version alongside |

Marked block shape — the same in every file type, comment syntax adapted:

```markdown
<!-- ai-sdlc-kit:begin -->
…generated content…
<!-- ai-sdlc-kit:end -->
```

Markers make a second run **update in place** instead of appending a second copy.

### The manifest — `.ai-sdlc/kit.json`

Committed, written at install, read by every later run:

```jsonc
{
  "kit": { "version": "1.2.0", "commit": "abc1234", "source": "https://github.com/…",
           "installed": "2026-09-18" },
  "layout": "sidecar",
  "project": { "name": "Acme Wallet", "slug": "acme-wallet" },
  "repos": [ { "path": "../acme-api", "role": "backend", "pointer": true } ],
  "hooks": "kit",
  "tools": ["claude", "copilot"]
}
```

### The generated README

The installed project's `README.md` is written from a template carrying that project's
own facts — name, description, layout (with a diagram of where the kit sits relative to
the repos), the repos and their roles, how to start (open the agent here; onboarding
runs), and the day-to-day entry points. When the project already has a README, the kit's
section is appended as a marked block instead.

---

## 8. Testing

`template/scripts/tests/test_bootstrap.sh` — no framework, exits non-zero on failure,
runs entirely in temp dirs:

1. Fresh install for each of the four layouts → expected tree, manifest correct.
2. Merge into a populated project → the project's own `README.md`, `.gitignore` and
   `CLAUDE.md` keep their original content, with the kit's block appended.
3. Idempotence → a second run updates blocks in place; no duplicates, no growth.
4. Collision → a non-mergeable conflicting file is left byte-identical and reported.
5. `--no-git` / `--hooks none` → no repo initialised, no hooks wired.
6. `--non-interactive` with a missing required value → non-zero exit, clear message.

The skill's own `SKILL.md` is validated by `validate-skills.py`.

**CI gap to close:** `.github/workflows/ci.yml` runs `validate-skills.py` with no
arguments, whose default roots resolve inside `template/` — a skill at the kit root is
validated by nothing today. Add the root skills path to that step (and to
`.gitlab-ci.yml`, which mirrors it).

---

## 9. Out of scope

- Updating or re-syncing an installed kit (Theme 2 — safe template propagation).
- Any change to `template/` beyond `bootstrap.sh`, the generated README and the manifest.
- Support for other agents beyond a pointer file and the documented manual route.
- Installing the code repos themselves (cloning, dependencies, environments).

---

## 10. Acceptance signal

From a clean machine with no kit clone: install the plugin, open any project, ask for the
kit. The skill reports the situation, proposes the right layout, installs without
overwriting a single existing file, hands over to `ONBOARDING.md`, and a second
invocation in the same project reports "set up, nothing to do" rather than installing
again.
