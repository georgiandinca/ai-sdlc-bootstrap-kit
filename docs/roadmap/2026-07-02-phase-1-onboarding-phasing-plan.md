# Phase 1 — Onboarding Global + Per-Seat Phasing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn seat from a stored label into a real phase — split onboarding into Phase A (Global) / Phase B (Seat), add a `seat-profiles.json` single source (+ validator), inject seat context live at SessionStart, add artefact-scoped `.claude/rules/`, and a seat-switch command.

**Architecture:** One JSON manifest + one stdlib validator (mirroring Phase 0's `moments.json`/`validate-moments.py`), two bash edits/additions to the session scripts, an `ONBOARDING.md` restructure, three `.claude/rules/` files, and `AGENTS.md` pointers. All under `template/` except the repo-root `.gitlab-ci.yml`. Built on the Phase 0 branch.

**Tech Stack:** Python 3.12 (stdlib: json, pathlib, unittest), JSON, Bash, Markdown/YAML frontmatter, GitLab CI, pre-commit.

## Global Constraints

- All created/modified files live under `template/` **except** `.gitlab-ci.yml` (repo root).
- `validate-seat-profiles.py` uses the Python **standard library only** (`json`, `pathlib`). Tests use stdlib `unittest`.
- Validators exit **0 on success, 1 on failure**, printing `ok    <path>` / `FAIL  <path>` lines — matching `validate-skills.py` / `validate-frontmatter.py` / `validate-moments.py`.
- The five known seats are exactly: **Architect, EM, Product, Developer, QA**. Playbook dirs: `playbook-architect`, `playbook-em`, `playbook-product`, `playbook-dev`, `playbook-qa`. git-comfort defaults: Architect/EM/Developer = `git-native`, QA = `guided`, Product = `hidden`.
- `.mcp.json` declares these connector keys: `issue-tracker`, `docs-wiki`, `knowledge`, `context7`.
- Manifest/validator resolve paths against `repo_root = Path(__file__).resolve().parent.parent` (i.e. `template/`).
- Bash scripts stay POSIX-portable across macOS (BSD) and Linux (GNU): use `sed -i.bak … && rm -f *.bak`, no GNU-only flags.
- `.claude/rules/*.md` use the `paths:` frontmatter schema (NOT the governance doc frontmatter) — they live under `.claude/`, so the doc frontmatter validator does not apply.
- `CLAUDE.md` stays a pure pointer.
- Match kit house style/spelling (`artefact`, `-ise`).
- Every commit message ends with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

**Created:**
- `template/scripts/validate-seat-profiles.py` — manifest validator.
- `template/scripts/tests/test_validate_seat_profiles.py` — unittest suite.
- `template/scripts/session/seat-profiles.json` — per-seat manifest.
- `template/scripts/session/switch-seat.sh` — seat-switch command.
- `template/.claude/rules/adr-conventions.md`, `knowledge-sources.md`, `test-artefacts.md`.

**Modified:**
- `.gitlab-ci.yml` — add validator + test to the governance gate.
- `template/.pre-commit-config.yaml` — add `validate-seat-profiles` hook.
- `template/ONBOARDING.md` — restructure into Phase A / Phase B.
- `template/scripts/session/start.sh` — inject seat-context block.
- `template/AGENTS.md` — two pointers.

---

## Task 1: Seat-profiles validator with unit tests

**Files:**
- Create: `template/scripts/validate-seat-profiles.py`
- Test: `template/scripts/tests/test_validate_seat_profiles.py`

**Interfaces:**
- Produces: `validate_manifest(data: dict, base_dir: Path) -> list[str]`; `main() -> int`. Constants: `REQUIRED_FIELDS`, `KNOWN_SEATS = {"Architect","EM","Product","Developer","QA"}`, `COMFORTS = {"git-native","guided","hidden"}`.

- [ ] **Step 1: Write the failing test**

Create `template/scripts/tests/test_validate_seat_profiles.py`:

```python
#!/usr/bin/env python3
"""Unit tests for validate-seat-profiles.py (stdlib unittest — no extra deps)."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent.parent / "validate-seat-profiles.py"
spec = importlib.util.spec_from_file_location("validate_seat_profiles", MODULE_PATH)
vsp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vsp)

PLAYBOOKS = {
    "Architect": "playbook-architect", "EM": "playbook-em", "Product": "playbook-product",
    "Developer": "playbook-dev", "QA": "playbook-qa",
}
DEFAULTS = {"Architect": "git-native", "EM": "git-native", "Product": "hidden",
            "Developer": "git-native", "QA": "guided"}


def full_manifest():
    return {"version": 1, "seats": [
        {"id": sid, "git_comfort_default": DEFAULTS[sid], "playbook": PLAYBOOKS[sid],
         "connectors": ["issue-tracker"], "first_task": "do a thing"}
        for sid in ["Architect", "EM", "Product", "Developer", "QA"]
    ]}


class ValidateSeatProfilesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        for pb in PLAYBOOKS.values():
            (self.base / ".claude" / "skills" / pb).mkdir(parents=True)
        (self.base / ".mcp.json").write_text(json.dumps(
            {"mcpServers": {"issue-tracker": {}, "docs-wiki": {}, "knowledge": {}, "context7": {}}}))

    def tearDown(self):
        self._tmp.cleanup()

    def test_valid_manifest_passes(self):
        self.assertEqual(vsp.validate_manifest(full_manifest(), self.base), [])

    def test_missing_required_field(self):
        m = full_manifest(); del m["seats"][0]["first_task"]
        self.assertTrue(any("first_task" in e for e in vsp.validate_manifest(m, self.base)))

    def test_bad_git_comfort_default(self):
        m = full_manifest(); m["seats"][0]["git_comfort_default"] = "expert"
        self.assertTrue(any("git_comfort_default" in e for e in vsp.validate_manifest(m, self.base)))

    def test_unknown_seat_id(self):
        m = full_manifest(); m["seats"][0]["id"] = "Wizard"
        self.assertTrue(any("known seats" in e for e in vsp.validate_manifest(m, self.base)))

    def test_missing_known_seat(self):
        m = full_manifest(); m["seats"].pop()  # drop QA
        self.assertTrue(any("missing seats" in e for e in vsp.validate_manifest(m, self.base)))

    def test_duplicate_id(self):
        m = full_manifest(); m["seats"][1]["id"] = "Architect"
        self.assertTrue(any("duplicate" in e for e in vsp.validate_manifest(m, self.base)))

    def test_playbook_dir_missing(self):
        m = full_manifest(); m["seats"][0]["playbook"] = "playbook-nope"
        self.assertTrue(any("playbook skill dir not found" in e for e in vsp.validate_manifest(m, self.base)))

    def test_connector_not_in_mcp(self):
        m = full_manifest(); m["seats"][0]["connectors"] = ["ghost-connector"]
        self.assertTrue(any("not declared in .mcp.json" in e for e in vsp.validate_manifest(m, self.base)))

    def test_empty_seats(self):
        self.assertTrue(any("empty" in e for e in vsp.validate_manifest({"seats": []}, self.base)))

    def test_root_not_object(self):
        self.assertTrue(any("root" in e for e in vsp.validate_manifest([], self.base)))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 template/scripts/tests/test_validate_seat_profiles.py`
Expected: FAIL — `FileNotFoundError` / import error because `validate-seat-profiles.py` does not exist yet.

- [ ] **Step 3: Write the validator**

Create `template/scripts/validate-seat-profiles.py`:

```python
#!/usr/bin/env python3
"""Validate the per-seat profiles manifest (scripts/session/seat-profiles.json).

seat-profiles.json is the single source of per-seat data — git-comfort default,
role playbook, MCP connectors, and the onboarding first task. Phase 1 onboarding,
the SessionStart hook, and switch-seat.sh read it; this validator keeps it honest,
like validate-skills.py / validate-frontmatter.py / validate-moments.py.

Checks:
  - valid JSON with a non-empty "seats" list
  - each seat has: id, git_comfort_default, playbook, connectors, first_task
  - id in the known seat set; all known seats present; ids unique
  - git_comfort_default in {git-native, guided, hidden}
  - playbook skill dir exists at .claude/skills/<playbook>/
  - every connector is a key in .mcp.json's mcpServers (skipped if .mcp.json absent)

Usage:  validate-seat-profiles.py
Exit 0 if valid, 1 otherwise.
"""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED_FIELDS = ["id", "git_comfort_default", "playbook", "connectors", "first_task"]
KNOWN_SEATS = {"Architect", "EM", "Product", "Developer", "QA"}
COMFORTS = {"git-native", "guided", "hidden"}
MANIFEST_REL = "scripts/session/seat-profiles.json"
MCP_REL = ".mcp.json"


def _mcp_server_keys(base_dir: Path) -> set:
    mcp_path = base_dir / MCP_REL
    if not mcp_path.exists():
        return set()
    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    servers = data.get("mcpServers")
    return set(servers.keys()) if isinstance(servers, dict) else set()


def validate_manifest(data, base_dir: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest root must be a JSON object"]
    seats = data.get("seats")
    if not isinstance(seats, list):
        return ["manifest must have a 'seats' list"]
    if not seats:
        errors.append("'seats' list is empty")

    connector_keys = _mcp_server_keys(base_dir)
    seen_ids: set = set()
    for i, s in enumerate(seats):
        if not isinstance(s, dict):
            errors.append(f"seats[{i}]: must be a JSON object")
            continue
        sid = s.get("id", f"<index {i}>")
        for field in REQUIRED_FIELDS:
            if field not in s or s[field] in (None, "", []):
                errors.append(f"{sid}: missing required field '{field}'")
        if "id" in s:
            if s["id"] in seen_ids:
                errors.append(f"{sid}: duplicate id")
            seen_ids.add(s["id"])
            if s["id"] not in KNOWN_SEATS:
                errors.append(f"{sid}: id not in known seats {sorted(KNOWN_SEATS)}")
        gcd = s.get("git_comfort_default")
        if gcd is not None and gcd not in COMFORTS:
            errors.append(f"{sid}: git_comfort_default={gcd!r} not in {sorted(COMFORTS)}")
        playbook = s.get("playbook")
        if isinstance(playbook, str) and playbook:
            if not (base_dir / ".claude" / "skills" / playbook).is_dir():
                errors.append(f"{sid}: playbook skill dir not found: .claude/skills/{playbook}/")
        connectors = s.get("connectors")
        if isinstance(connectors, list) and connector_keys:
            for c in connectors:
                if c not in connector_keys:
                    errors.append(f"{sid}: connector {c!r} not declared in .mcp.json mcpServers")
    missing = KNOWN_SEATS - seen_ids
    if missing:
        errors.append(f"missing seats: {sorted(missing)}")
    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    manifest_path = repo_root / MANIFEST_REL
    if not manifest_path.exists():
        print(f"FAIL  {MANIFEST_REL}\n  - manifest file not found")
        return 1
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL  {MANIFEST_REL}\n  - invalid JSON: {exc}")
        return 1
    errors = validate_manifest(data, repo_root)
    if errors:
        print(f"FAIL  {MANIFEST_REL}")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"ok    {MANIFEST_REL} ({len(data.get('seats', []))} seats)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 template/scripts/tests/test_validate_seat_profiles.py`
Expected: PASS — `OK`, 10 tests.

- [ ] **Step 5: Commit**

```bash
git add template/scripts/validate-seat-profiles.py template/scripts/tests/test_validate_seat_profiles.py
git commit -m "feat: add seat-profiles manifest validator

Stdlib validator (validate_manifest + main) checking the per-seat
manifest against known seats, git-comfort enum, playbook dirs, and
.mcp.json connectors, with a unittest suite.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: The seat-profiles manifest

**Files:**
- Create: `template/scripts/session/seat-profiles.json`

**Interfaces:**
- Consumes: `validate-seat-profiles.py` (Task 1). The five playbook dirs and `.mcp.json` connectors it references already exist in the kit.

- [ ] **Step 1: Create the manifest**

Create `template/scripts/session/seat-profiles.json`:

```json
{
  "version": 1,
  "seats": [
    { "id": "Architect", "git_comfort_default": "git-native", "playbook": "playbook-architect",
      "connectors": ["issue-tracker", "docs-wiki", "knowledge"],
      "first_task": "Record a first ADR stub at docs/architecture/decisions/ADR-0001-<topic>.md." },
    { "id": "EM", "git_comfort_default": "git-native", "playbook": "playbook-em",
      "connectors": ["issue-tracker", "docs-wiki", "knowledge"],
      "first_task": "Draft an engineering-spec stub, or record the code repos in AGENTS.md section 2." },
    { "id": "Product", "git_comfort_default": "hidden", "playbook": "playbook-product",
      "connectors": ["issue-tracker", "docs-wiki"],
      "first_task": "Draft a first user story with acceptance criteria." },
    { "id": "Developer", "git_comfort_default": "git-native", "playbook": "playbook-dev",
      "connectors": ["issue-tracker", "knowledge", "context7"],
      "first_task": "Open a feature branch for your first change." },
    { "id": "QA", "git_comfort_default": "guided", "playbook": "playbook-qa",
      "connectors": ["issue-tracker", "knowledge"],
      "first_task": "Write a test-plan stub with one traceability entry." }
  ]
}
```

- [ ] **Step 2: Validate the real manifest**

Run: `python3 template/scripts/validate-seat-profiles.py`
Expected: PASS — `ok    scripts/session/seat-profiles.json (5 seats)`, exit 0.

- [ ] **Step 3: Commit**

```bash
git add template/scripts/session/seat-profiles.json
git commit -m "feat: add per-seat profiles manifest

Five seats with git-comfort default, playbook, MCP connectors, and an
onboarding first task. Single source consumed by onboarding, the
SessionStart hook, and switch-seat.sh.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Wire the validator into CI and pre-commit

**Files:**
- Modify: `.gitlab-ci.yml` (repo root)
- Modify: `template/.pre-commit-config.yaml`

- [ ] **Step 1: Add validator + test to the governance gate**

Read `.gitlab-ci.yml`. In the `ai-governance` job's `script:` list, immediately **after** the line `- python3 template/scripts/tests/test_validate_moments.py` (added in Phase 0), insert:

```yaml
  - echo "Validating per-seat profiles manifest…"
  - python3 template/scripts/validate-seat-profiles.py
  - echo "Running seat-profiles validator unit tests…"
  - python3 template/scripts/tests/test_validate_seat_profiles.py
```

- [ ] **Step 2: Verify the CI file parses and commands pass**

Run: `python3 -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml')); print('yaml-ok')"` → `yaml-ok`.
Run: `python3 template/scripts/validate-seat-profiles.py && python3 template/scripts/tests/test_validate_seat_profiles.py` → validator `ok`, tests `OK`, exit 0.

- [ ] **Step 3: Add the pre-commit hook**

Read `template/.pre-commit-config.yaml`. Following the existing local-hook pattern (the `validate-moments` hook added in Phase 0), add after it:

```yaml
      - id: validate-seat-profiles
        name: Validate per-seat profiles manifest
        entry: python3 scripts/validate-seat-profiles.py
        language: system
        files: ^scripts/session/seat-profiles\.json$
        pass_filenames: false
```

- [ ] **Step 4: Verify the pre-commit config parses**

Run: `python3 -c "import yaml; yaml.safe_load(open('template/.pre-commit-config.yaml')); print('yaml-ok')"` → `yaml-ok`.

- [ ] **Step 5: Commit**

```bash
git add .gitlab-ci.yml template/.pre-commit-config.yaml
git commit -m "ci: gate the seat-profiles manifest

Run validate-seat-profiles.py + its unit tests in the ai-governance
stage, and add a validate-seat-profiles pre-commit hook.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Restructure `ONBOARDING.md` into Phase A / Phase B

**Files:**
- Modify (full rewrite): `template/ONBOARDING.md`

**Interfaces:**
- Consumes: `seat-profiles.json` (Task 2) for git-comfort defaults, playbook, connectors, first_task.

- [ ] **Step 1: Replace the file with the restructured version**

Overwrite `template/ONBOARDING.md` with exactly this content (all current capabilities preserved; regrouped into Phase A / Phase B; the git-comfort default table replaced by a `seat-profiles.json` reference):

````markdown
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
````

- [ ] **Step 2: Verify structure and frontmatter**

Run: `grep -nE '^# Phase [AB]|^## (Step 0|A[1-6]|B[1-5]|Finalize)' template/ONBOARDING.md`
Expected: Phase A and Phase B headers plus Step 0, A1–A6, B1–B5, and Finalize all present, in order.
Run: `python3 template/scripts/validate-frontmatter.py template/ONBOARDING.md`
Expected: `ok`, exit 0.
Run: `grep -c 'git_comfort_default\|Suggested default' template/ONBOARDING.md` — expected `0` for the old table phrase "Suggested default" (confirm the hard-coded table is gone; the file now references `seat-profiles.json`).

- [ ] **Step 3: Commit**

```bash
git add template/ONBOARDING.md
git commit -m "feat: restructure onboarding into Phase A (Global) / Phase B (Seat)

Regroup the linear steps into a Global phase (identity, env, prefs) and
a Seat phase (seat, git-comfort, playbook load, MCP profile, first task).
git-comfort default now reads from seat-profiles.json instead of a
hard-coded table; add the switch-seat note.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Inject seat context at SessionStart (`start.sh`)

**Files:**
- Modify: `template/scripts/session/start.sh`

**Interfaces:**
- Consumes: `USER.md` (Seat, Git comfort), `seat-profiles.json` (playbook, connectors).

- [ ] **Step 1: Write a failing functional test**

Create a temporary check that proves the seat-context block is NOT yet emitted. Run:

```bash
cd "$(mktemp -d)" && git init -q && mkdir -p scripts/session
cp /Users/georgiandinca/ps/AI/SDLC/template/scripts/session/start.sh scripts/session/start.sh
cp /Users/georgiandinca/ps/AI/SDLC/template/scripts/session/seat-profiles.json scripts/session/seat-profiles.json
printf -- '- **Seat:** Developer\n- **Git comfort:** git-native\n' > USER.md
bash scripts/session/start.sh 2>/dev/null | grep -c 'seat-context'
```
Expected: `0` (start.sh does not yet emit a seat-context block). Note the temp dir path or just leave it; return to the repo with `cd /Users/georgiandinca/ps/AI/SDLC`.

- [ ] **Step 2: Add the seat-context block to `start.sh`**

In `template/scripts/session/start.sh`, insert the following block immediately **before** the final `cat <<'EOF' … EOF` session-ritual heredoc (i.e. after the `echo "[session-start] repo=…"` status line and before `[session ritual]`):

```bash
# --- seat context (Phase 1): load the saved seat + git-comfort and its profile ---
seat_u=""; comfort_u=""
if [ -f USER.md ]; then
  seat_u=$(grep -iE '^- \*\*Seat:\*\*' USER.md | head -1 | sed -E 's/^- \*\*Seat:\*\* *//; s/ *$//')
  comfort_u=$(grep -iE '^- \*\*Git comfort:\*\*' USER.md | head -1 | sed -E 's/^- \*\*Git comfort:\*\* *//; s/ *$//')
fi
seat="${seat_u:-${SESSION_SEAT:-}}"
if [ -n "$seat" ] && [ -f scripts/session/seat-profiles.json ]; then
  profile=$(python3 - "$seat" <<'PY' 2>/dev/null || true
import json, sys
from pathlib import Path
seat = sys.argv[1]
try:
    data = json.loads(Path("scripts/session/seat-profiles.json").read_text())
except Exception:
    sys.exit(0)
for s in data.get("seats", []):
    if str(s.get("id", "")).lower() == seat.lower():
        print(f"{s.get('playbook','')}|{','.join(s.get('connectors', []))}")
        break
PY
)
  playbook="${profile%%|*}"; connectors="${profile#*|}"
  echo "[seat-context] operating as: ${seat} (git-comfort: ${comfort_u:-unset})"
  [ -n "$playbook" ] && echo "[seat-context] load skill: ${playbook} | seat connectors: ${connectors}"
fi
```

- [ ] **Step 3: Re-run the functional test to verify it now passes**

```bash
cd "$(mktemp -d)" && git init -q && mkdir -p scripts/session
cp /Users/georgiandinca/ps/AI/SDLC/template/scripts/session/start.sh scripts/session/start.sh
cp /Users/georgiandinca/ps/AI/SDLC/template/scripts/session/seat-profiles.json scripts/session/seat-profiles.json
printf -- '- **Seat:** Developer\n- **Git comfort:** git-native\n' > USER.md
bash scripts/session/start.sh 2>/dev/null | grep 'seat-context'
cd /Users/georgiandinca/ps/AI/SDLC
```
Expected: two `[seat-context]` lines — `operating as: Developer (git-comfort: git-native)` and `load skill: playbook-dev | seat connectors: issue-tracker,knowledge,context7`.
Then verify graceful no-USER.md behavior and syntax:
Run: `bash -n template/scripts/session/start.sh` → exits 0 (valid syntax).

- [ ] **Step 4: Commit**

```bash
git add template/scripts/session/start.sh
git commit -m "feat: inject seat context at SessionStart

start.sh reads Seat + Git comfort from USER.md (fallback SESSION_SEAT),
looks up the seat's playbook + connectors in seat-profiles.json, and
prints a seat-context block so the seat loads live each session.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Seat-switch command (`switch-seat.sh`)

**Files:**
- Create: `template/scripts/session/switch-seat.sh`

**Interfaces:**
- Consumes: `seat-profiles.json` (git_comfort_default, playbook). Mutates: `USER.md`.

- [ ] **Step 1: Write the script**

Create `template/scripts/session/switch-seat.sh` (make it executable, `chmod +x`):

```bash
#!/usr/bin/env bash
# Switch the operator's seat: re-runs "Phase B" of onboarding without touching
# identity or environment. Updates USER.md's Seat + Git comfort from
# seat-profiles.json. Portable across macOS (BSD) and Linux (GNU) sed.
set -uo pipefail

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "not inside a git repo"; exit 1; }
cd "$repo_root"
[ -f USER.md ] || { echo "no USER.md — run onboarding first (see ONBOARDING.md)"; exit 1; }
[ -f scripts/session/seat-profiles.json ] || { echo "no seat-profiles.json"; exit 1; }

new_seat="${1:-}"
if [ -z "$new_seat" ]; then
  echo "Usage: scripts/session/switch-seat.sh <Architect|EM|Product|Developer|QA>"
  exit 2
fi

# Resolve canonical id, git-comfort default, and playbook for the requested seat.
resolved=$(python3 - "$new_seat" <<'PY'
import json, sys
from pathlib import Path
seat = sys.argv[1]
try:
    data = json.loads(Path("scripts/session/seat-profiles.json").read_text())
except Exception:
    sys.exit(1)
for s in data.get("seats", []):
    if str(s.get("id", "")).lower() == seat.lower():
        print(f"{s['id']}|{s.get('git_comfort_default','')}|{s.get('playbook','')}")
        sys.exit(0)
sys.exit(1)
PY
) || { echo "unknown seat: ${new_seat} (must be one of Architect/EM/Product/Developer/QA)"; exit 2; }

canonical="${resolved%%|*}"; rest="${resolved#*|}"
comfort="${rest%%|*}"; playbook="${rest#*|}"

# Update USER.md in place (exact-case markers; portable -i.bak then remove backup).
if grep -qE '^- \*\*Seat:\*\*' USER.md; then
  sed -i.bak -E "s|^- \*\*Seat:\*\*.*|- **Seat:** ${canonical}|" USER.md
else
  printf -- '- **Seat:** %s\n' "${canonical}" >> USER.md
fi
if grep -qE '^- \*\*Git comfort:\*\*' USER.md; then
  sed -i.bak -E "s|^- \*\*Git comfort:\*\*.*|- **Git comfort:** ${comfort}|" USER.md
else
  printf -- '- **Git comfort:** %s\n' "${comfort}" >> USER.md
fi
rm -f USER.md.bak

echo "[switch-seat] seat -> ${canonical} (git-comfort ${comfort})."
echo "[switch-seat] load the ${playbook} skill for this seat. Change git-comfort in USER.md if it doesn't fit."
```

- [ ] **Step 2: Functional test**

```bash
cd "$(mktemp -d)" && git init -q && mkdir -p scripts/session
cp /Users/georgiandinca/ps/AI/SDLC/template/scripts/session/switch-seat.sh scripts/session/switch-seat.sh
cp /Users/georgiandinca/ps/AI/SDLC/template/scripts/session/seat-profiles.json scripts/session/seat-profiles.json
printf -- '- **Seat:** Developer\n- **Git comfort:** git-native\n' > USER.md
bash scripts/session/switch-seat.sh QA
echo "--- USER.md now ---"; grep -E 'Seat:|Git comfort:' USER.md
cd /Users/georgiandinca/ps/AI/SDLC
```
Expected: output `seat -> QA (git-comfort guided)`; USER.md shows `- **Seat:** QA` and `- **Git comfort:** guided`. Also run `bash -n template/scripts/session/switch-seat.sh` → exit 0.

- [ ] **Step 3: Commit**

```bash
git add template/scripts/session/switch-seat.sh
git commit -m "feat: add switch-seat command

scripts/session/switch-seat.sh re-runs Phase B only: resolves the new
seat's git-comfort default + playbook from seat-profiles.json and
updates USER.md in place (portable sed). Identity/env untouched.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Artefact-scoped `.claude/rules/`

**Files:**
- Create: `template/.claude/rules/adr-conventions.md`
- Create: `template/.claude/rules/knowledge-sources.md`
- Create: `template/.claude/rules/test-artefacts.md`

- [ ] **Step 1: Create the three rule files**

Create `template/.claude/rules/adr-conventions.md`:

```markdown
---
paths:
  - "docs/architecture/decisions/**"
---
# ADR conventions

When creating or editing an Architecture Decision Record:
- Name it `ADR-<NNNN>-<kebab-topic>.md` with a zero-padded number.
- Carry the frontmatter contract (title, status, owner, classification, ai-trust).
- Structure: **Context** → **Decision** → **Consequences**. State the decision as a completed choice ("We will …"), not a proposal.
- `status: approved` only after the accountable seat signs off; until then `draft` / `under-review`.
- Supersede rather than delete: set the old ADR `status: superseded` and link the replacement.
```

Create `template/.claude/rules/knowledge-sources.md`:

```markdown
---
paths:
  - "docs/knowledge/**"
---
# Knowledge sources

Files under `docs/knowledge/sources/` are ingestable inputs for the knowledge layer (pillar 5).
- Treat them per their trust tier (`AGENTS.md` §4.2); cite the source file when grounding an answer.
- After adding or changing sources, rebuild the index: `python3 scripts/knowledge/ingest.py --build`.
- `docs/knowledge/schema.md` is exempt from the frontmatter contract; source docs still carry it.
- Do not paraphrase Authoritative sources from memory — quote and cite.
```

Create `template/.claude/rules/test-artefacts.md`:

```markdown
---
paths:
  - "docs/**/test-plan*"
  - "tests/**"
---
# Test artefacts

When working on test plans or tests:
- A test plan states scope, approach, and **traceability** — each acceptance criterion maps to at least one test.
- Keep test IDs stable so traceability links survive edits.
- QA owns test strategy and quality gates (see `playbook-qa`); flag any acceptance criterion with no covering test.
```

- [ ] **Step 2: Verify the frontmatter parses as YAML**

Run:
```bash
for f in adr-conventions knowledge-sources test-artefacts; do
  python3 -c "import yaml,sys; t=open('template/.claude/rules/$f.md').read(); fm=t.split('---')[1]; d=yaml.safe_load(fm); assert isinstance(d.get('paths'),list) and d['paths'], '$f paths'; print('$f ok')"
done
```
Expected: `adr-conventions ok`, `knowledge-sources ok`, `test-artefacts ok`.

- [ ] **Step 3: Commit**

```bash
git add template/.claude/rules/
git commit -m "feat: add artefact-scoped .claude/rules

Three paths-scoped rules that load on demand when their artefacts are
touched: ADR conventions (docs/architecture/decisions), knowledge
sources (docs/knowledge), and test artefacts (test plans / tests).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: `AGENTS.md` pointers

**Files:**
- Modify: `template/AGENTS.md`

- [ ] **Step 1: Add the Phase A/B note in §0**

In `template/AGENTS.md` §0, immediately **after** the numbered startup list (the line ending "…tailor all responses for the rest of this session.") and **before** the `### What lives in USER.md` heading, insert:

```markdown
> **Onboarding runs in two phases.** `ONBOARDING.md` runs **Phase A (Global)** — identity, environment, preferences (every seat) — then **Phase B (Seat)** — seat, git-comfort, the seat's playbook, MCP profile, and a first task. Seat and git-comfort are recorded in `USER.md` and load live each session via the SessionStart hook. Switch seats later with `scripts/session/switch-seat.sh <seat>`.
```

- [ ] **Step 2: Add the seat-profiles pointer in §5**

In `template/AGENTS.md` §5, immediately **after** the "Naming discipline" blockquote (the line "…refer to it by role."), insert:

```markdown
Per-seat data — git-comfort default, role playbook, MCP connectors, and the onboarding first task — is declared in [`scripts/session/seat-profiles.json`](./scripts/session/seat-profiles.json) and validated by `scripts/validate-seat-profiles.py`.
```

- [ ] **Step 3: Verify**

Run: `grep -n "Onboarding runs in two phases" template/AGENTS.md && grep -n "seat-profiles.json" template/AGENTS.md`
Expected: one match each.
Run: `git diff --name-only` — confirm `template/CLAUDE.md` is NOT listed.

- [ ] **Step 4: Commit**

```bash
git add template/AGENTS.md
git commit -m "docs: point AGENTS.md at the Phase A/B model and seat-profiles

Note the two-phase onboarding + live seat loading in §0, and reference
seat-profiles.json as the per-seat data source in §5. CLAUDE.md stays a
pure pointer.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] Run the full governance gate locally, as CI does:

```bash
python3 template/scripts/validate-skills.py
python3 template/scripts/validate-frontmatter.py
python3 template/scripts/validate-moments.py
python3 template/scripts/tests/test_validate_moments.py
python3 template/scripts/validate-seat-profiles.py
python3 template/scripts/tests/test_validate_seat_profiles.py
python3 template/scripts/knowledge/ingest.py --build
```
Expected: every command exits 0.

- [ ] `git status` clean; `git log --oneline main..HEAD` shows the Phase 1 task commits atop the Phase 0 commits.

---

## Self-review against the spec

- **Component 1 (ONBOARDING A/B):** Task 4. ✓
- **Component 2 (seat-profiles.json + validator):** Tasks 1, 2. ✓
- **Component 3 (live seat context):** Task 5. ✓
- **Component 4 (.claude/rules):** Task 7. ✓
- **Component 5 (switch-seat):** Task 6. ✓
- **Component 6 (first-task tutorial):** in seat-profiles.json (Task 2) + ONBOARDING B5 (Task 4). ✓
- **Component 7 (per-seat MCP profile):** `connectors` in seat-profiles.json (Task 2), surfaced in ONBOARDING B4 (Task 4) + start.sh (Task 5), validated (Task 1). ✓
- **Supporting (AGENTS.md pointers, CI/pre-commit):** Tasks 8, 3. ✓
- **Acceptance criteria 1–8:** each maps to a task verification; the Final verification block runs the whole gate. ✓
- **Out-of-scope** (git automation, checkpoint/decision handlers, real connector config, dashboard/graph) is absent from every task. ✓
