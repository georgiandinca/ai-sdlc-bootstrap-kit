---
title: "Onboarding — first-run setup"
status: approved
owner: EM
author: AI-SDLC Bootstrap Kit
created: 2026-06-26
classification: internal
last-reviewed: 2026-07-02
ai-trust: working
---

# Onboarding — first-run setup

This file is **only loaded when `USER.md` does not exist** at the repo root. It is the gatekeeper — every AI harness reads this before doing any real work. Once `USER.md` exists, skip this file entirely and read `USER.md` instead.

> **To the AI agent reading this:** You execute these steps yourself using your tools (terminal, ask-the-user, write-file). Do not tell the user to run commands — run them. Only fall back to asking the user when a step needs elevated privileges, a GUI installer, or interactive credentials. Do not proceed with project work until onboarding is complete and `USER.md` has been created.

Onboarding runs in two phases: **Phase A — Global** (identity, environment, preferences; the same for every seat), then **Phase B — Seat** (the operator's seat and everything that follows from it). Step 0 is the gate.

---

## Step 0 — Confirm `USER.md` is missing

```bash
test -f USER.md && echo "EXISTS" || echo "MISSING"
```

- `EXISTS` → **skip this entire file.** Read `USER.md` and proceed to `AGENTS.md` §0.
- `MISSING` → continue with Phase A.

---

# Phase A — Global setup (every seat)

## A1 — Detect the operating system

```bash
uname -s 2>/dev/null
```

| Output | Resolved OS | Next |
|---|---|---|
| `Darwin` | **macOS** | A2 |
| `Linux` (+ `grep -qi microsoft /proc/version` → match) | **Windows (WSL)** | A2 — Windows commands |
| `Linux` (no WSL match) | **Linux** | A2 |
| `MINGW*` / `MSYS*` | **Windows (Git Bash)** | A2 |
| `uname` not found | **Windows (cmd/PowerShell)** | A2 |

Record the resolved OS.

## A2 — Verify and install prerequisites

Check each tool. If missing, **install it yourself.** Only ask the user if installation needs elevated privileges, a GUI, or a restart.

> **Seat-aware tooling.** Git, Python 3, and pre-commit are the baseline for **every** seat. Node.js ≥ 22 and pandoc are only needed by seats that build the dashboard or binary deliverables — if the operator's seat won't (you confirm the seat in Phase B), you may skip them now and install later.

### macOS — Homebrew

```bash
command -v brew >/dev/null 2>&1 || {
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || eval "$(brew --prefix)/bin/brew shellenv"
}
```

| Tool | Install | Verify |
|---|---|---|
| Git | `brew install git` | `git --version` |
| Node.js ≥ 22 | `brew install node@22 && brew link --force node@22` | `node --version` |
| Python 3 | `brew install python@3` | `python3 --version` |
| pre-commit | `pip3 install pre-commit` | `pre-commit --version` |
| pandoc *(optional — for binary deliverables)* | `brew install pandoc` | `pandoc --version` |

### Windows (Git Bash / PowerShell) — winget, with fallbacks

```bash
command -v winget >/dev/null 2>&1 && echo "WINGET_OK" || echo "NO_WINGET"
```

| Tool | winget | Fallback |
|---|---|---|
| Git | `winget install --id Git.Git -e` | already present in Git Bash |
| Node.js ≥ 22 | `winget install --id OpenJS.NodeJS.LTS -e` | nvm-windows |
| Python 3 | `winget install --id Python.Python.3.12 -e` | python.org installer — **tell user to check "Add to PATH"** |
| pre-commit | `pip install pre-commit` | same |
| pandoc *(optional)* | `winget install --id JohnMacFarlane.Pandoc -e` | pandoc.org installer |

After winget installs, **reopen the shell** before verifying.

### Linux — apt / dnf

| Tool | Debian/Ubuntu | RHEL/Fedora |
|---|---|---|
| Git | `sudo apt install -y git` | `sudo dnf install -y git` |
| Node.js ≥ 22 | `curl -fsSL https://deb.nodesource.com/setup_22.x \| sudo -E bash - && sudo apt install -y nodejs` | `curl -fsSL https://rpm.nodesource.com/setup_22.x \| sudo bash - && sudo dnf install -y nodejs` |
| Python 3 | `sudo apt install -y python3 python3-pip` | `sudo dnf install -y python3 python3-pip` |
| pre-commit | `pip3 install pre-commit` | `pip3 install pre-commit` |

**If a `sudo` command fails** (no admin): tell the user which tool needs admin and provide the command. Continue onboarding — do not block.

### Verify everything

```bash
echo "=== Verification ==="
git --version
node --version
python3 --version 2>/dev/null || python --version 2>/dev/null
pre-commit --version
```

If any tool reports a PATH issue, **fix it** — find where it lives (`which <tool>` / `pip show <tool>`) and append `export PATH="$PATH:<dir>"` to `~/.zshrc` (macOS) or `~/.bashrc` (Linux / Git Bash), then re-verify.

## A3 — Activate repo hooks (once per clone)

```bash
pip install pre-commit
pre-commit install --hook-type commit-msg   # also installs the pre-commit stage
```

This wires up the **SKILL.md / frontmatter validators** and the **commit-message ticket check** (`scripts/git/commit_msg_ticket.py`). See `AGENTS.md` and `WORKING-AGREEMENT.md` §5.

## A4 — (Optional) Seed the knowledge layer

If the project's knowledge sources are present under `docs/knowledge/sources/`, build the local index so agents can ground on it (pillar 5):

```bash
python3 scripts/knowledge/ingest.py --build
```

If there are no sources yet, skip — this is safe to run later. See `docs/knowledge/README.md`.

## A5 — Identity

Use your interactive tool (ask-the-user / prompt) to collect:

> "What is your full name (as on your git / company profile)?"
> "What is your email address?"

Used for `author` in YAML frontmatter (`AGENTS.md` §4.2).

## A6 — Communication preferences

- **Tone:** Professional & Direct / Warm & Collaborative / Formal & Precise
- **Detail level:** Comprehensive / Balanced / Concise
- **Language:** `<PRIMARY_LANGUAGE>` (default) / other / Bilingual
- **Technical depth:** Role-adapted (default) / Always detailed / Always high-level

---

# Phase B — Seat setup

## B1 — Seat

> "Which seat are you on this project?"
1. Architect 2. Engineering Manager 3. Product (PO/PM) 4. Developer 5. QA

Accept a custom seat, but recommend the closest match.

## B2 — Git comfort

Read the seat's **git-comfort default** from [`scripts/session/seat-profiles.json`](./scripts/session/seat-profiles.json) (the `git_comfort_default` for the chosen seat; for a custom seat, ask explicitly). Propose it and let the user confirm or change it:

> "Based on your seat I'd set your **git-comfort** to `<default>`. Keep it, or change it? (git-native / guided / hidden)"

Meaning: `git-native` = you drive git directly (branches, commits, PRs); `guided` = intent-verbs with a brief explanation of the git underneath; `hidden` = git fully abstracted ("save my work" / "get the latest" / "send for review"). Record the confirmed level — it is written to `USER.md` at Finalize and governs how git surfaces to this operator in later sessions (see `docs/ai-context/lifecycle-moments.md`).

## B3 — Load the seat's playbook

Invoke the seat's role-contract skill — `playbook-<seat>` (the `playbook` value for the seat in `seat-profiles.json`, e.g. `playbook-architect`). This loads the seat's mandate, decision rights, and working relationships for the session.

## B4 — Activate the seat's MCP profile

From the seat's `connectors` in `seat-profiles.json`, tell the operator which connectors their seat uses (e.g. issue-tracker, docs-wiki, knowledge) under the scoped-write posture (`AGENTS.md §4.3`). Connectors that are placeholders/disabled in `.mcp.json` are noted but not yet active.

## B5 — First task

Offer the seat's `first_task` from `seat-profiles.json` (e.g. Architect → an ADR stub; Product → a user story; Developer → a feature branch). Optional, but it gives the operator one concrete action in their seat.

---

## Finalize — Create `USER.md` and proceed

1. Write `USER.md` at the repo root from the shape in [`USER.md.example`](./USER.md.example), filling in identity (A5), communication preferences (A6), seat (B1), and git-comfort (B2). Keep it under 100 lines. It is git-ignored.
2. Summarize what was set up (name, seat, git-comfort, preferences) and tool installation status.
3. **If anything failed, write it into the `Onboarding status` section of `USER.md`** with the exact retry command, so future sessions pick it up automatically.
4. Tell the user onboarding is complete.
5. Proceed to `AGENTS.md` §0 to load the project brief.

**Switching seats later:** run `scripts/session/switch-seat.sh <seat>` — it re-runs Phase B only (seat + git-comfort + playbook), leaving identity and environment untouched.

---

## Notes for AI harnesses

- **Claude Code**: interactive prompts for questions, shell for commands, file-write for `USER.md`. The `SessionStart` hook (`scripts/session/start.sh`) reminds you of the session ritual and injects the saved seat's context.
- **Other agents**: use the platform's Q&A / terminal / file-write equivalents. The scripts are plain shell/Python and run anywhere.
