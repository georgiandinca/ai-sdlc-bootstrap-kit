# Phase 0 — Shared Primitives Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay down the three shared primitives — the `git-comfort` axis, the session lifecycle-moments manifest (+ validator), and the commit-attribution convention — that Phases 1–3 import.

**Architecture:** Documentation + one JSON manifest + one stdlib Python validator, all under `template/` (the skeleton every project is bootstrapped from), plus one CI-root edit. The validator mirrors the existing `validate-skills.py` / `validate-frontmatter.py` pattern and is wired into the same governance gate and pre-commit config. No runtime behaviour changes — those are deferred to Phases 2–3.

**Tech Stack:** Python 3.12 (stdlib only: `json`, `pathlib`, `sys`, `unittest`), JSON, Markdown with YAML frontmatter, GitLab CI, pre-commit.

## Global Constraints

- All created/modified files live under `template/` **except** `.gitlab-ci.yml`, which is at the repo root.
- `validate-moments.py` uses the **Python standard library only** (`json`, `pathlib`, `sys`). No `pyyaml`. Tests use stdlib `unittest`.
- Validators exit **0 on success, 1 on failure**, printing `ok    <path>` / `FAIL  <path>` lines — matching `validate-skills.py` and `validate-frontmatter.py`.
- New `template/docs/**/*.md` (outside `drafts/`, `received/`, `knowledge/`) MUST carry frontmatter: `title`, `status` ∈ {draft, under-review, approved, superseded}, `owner`, `classification` ∈ {public, internal, restricted}, `ai-trust` ∈ {authoritative, working, exploratory}; recommended `author`, `created`, `last-reviewed`.
- Manifest `handler` paths are relative to the project root (`template/` in this kit); the validator resolves them against `repo_root = Path(__file__).resolve().parent.parent`.
- `CLAUDE.md` stays a pure pointer — never add rules there.
- Match kit house style and spelling (`artefact`, `-ise`).
- Every commit message ends with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

**Created:**
- `template/scripts/validate-moments.py` — manifest validator (stdlib).
- `template/scripts/tests/test_validate_moments.py` — unittest suite for the validator.
- `template/scripts/session/moments.json` — the lifecycle-moments manifest.
- `template/docs/ai-context/lifecycle-moments.md` — human companion to the manifest.
- `template/docs/ai-context/attribution.md` — commit-attribution convention.

**Modified:**
- `.gitlab-ci.yml` — add validator + test to the governance gate.
- `template/.pre-commit-config.yaml` — add a `validate-moments` local hook.
- `template/USER.md.example` — add the `Git comfort` field.
- `template/ONBOARDING.md` — add Step 5.2b (git-comfort capture) + Step 6 mention.
- `template/AGENTS.md` — three minimal pointers (§0 table row, §2.1 table cell, new §4.5).

---

## Task 1: Manifest validator (`validate-moments.py`) with unit tests

**Files:**
- Create: `template/scripts/validate-moments.py`
- Test: `template/scripts/tests/test_validate_moments.py`

**Interfaces:**
- Produces: `validate_manifest(data: dict, base_dir: Path) -> list[str]` (returns error strings, empty = valid); `main() -> int` (reads `repo_root/scripts/session/moments.json`, prints, returns exit code). Constants: `REQUIRED_FIELDS`, `STATUSES = {"active","planned"}`, `COMFORT_KEYS = {"git-native","guided","hidden"}`, `BEHAVIORS = {"auto","offer","skip"}`.

- [ ] **Step 1: Write the failing test**

Create `template/scripts/tests/test_validate_moments.py`:

```python
#!/usr/bin/env python3
"""Unit tests for validate-moments.py (stdlib unittest — no extra deps)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent.parent / "validate-moments.py"
spec = importlib.util.spec_from_file_location("validate_moments", MODULE_PATH)
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)

NOWHERE = Path("/nonexistent-base-dir")


def good_moment(**over):
    m = {
        "id": "session-start",
        "trigger": "A new working session begins.",
        "handler": "scripts/session/start.sh",
        "hook": "SessionStart",
        "status": "planned",  # planned → handler need not exist on disk
        "behavior_by_comfort": {"git-native": "offer", "guided": "offer", "hidden": "auto"},
    }
    m.update(over)
    return m


class ValidateManifestTests(unittest.TestCase):
    def test_valid_manifest_passes(self):
        self.assertEqual(vm.validate_manifest({"version": 1, "moments": [good_moment()]}, NOWHERE), [])

    def test_missing_required_field(self):
        m = good_moment()
        del m["trigger"]
        errs = vm.validate_manifest({"moments": [m]}, NOWHERE)
        self.assertTrue(any("trigger" in e for e in errs))

    def test_bad_status(self):
        errs = vm.validate_manifest({"moments": [good_moment(status="live")]}, NOWHERE)
        self.assertTrue(any("status" in e for e in errs))

    def test_bad_behavior_value(self):
        m = good_moment(behavior_by_comfort={"git-native": "maybe", "guided": "offer", "hidden": "auto"})
        errs = vm.validate_manifest({"moments": [m]}, NOWHERE)
        self.assertTrue(any("behavior_by_comfort" in e for e in errs))

    def test_bad_comfort_keys(self):
        errs = vm.validate_manifest({"moments": [good_moment(behavior_by_comfort={"native": "offer"})]}, NOWHERE)
        self.assertTrue(any("keys" in e for e in errs))

    def test_duplicate_ids(self):
        errs = vm.validate_manifest({"moments": [good_moment(), good_moment()]}, NOWHERE)
        self.assertTrue(any("duplicate" in e for e in errs))

    def test_active_handler_missing(self):
        errs = vm.validate_manifest({"moments": [good_moment(status="active", handler="scripts/session/nope.sh")]}, NOWHERE)
        self.assertTrue(any("handler not found" in e for e in errs))

    def test_active_handler_present(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "scripts" / "session").mkdir(parents=True)
            (base / "scripts" / "session" / "start.sh").write_text("#!/usr/bin/env bash\n")
            m = good_moment(status="active", handler="scripts/session/start.sh")
            self.assertEqual(vm.validate_manifest({"moments": [m]}, base), [])

    def test_empty_moments(self):
        errs = vm.validate_manifest({"moments": []}, NOWHERE)
        self.assertTrue(any("empty" in e for e in errs))

    def test_root_not_object(self):
        errs = vm.validate_manifest([], NOWHERE)
        self.assertTrue(any("root" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 template/scripts/tests/test_validate_moments.py`
Expected: FAIL — `FileNotFoundError` / import error because `template/scripts/validate-moments.py` does not exist yet.

- [ ] **Step 3: Write the validator**

Create `template/scripts/validate-moments.py`:

```python
#!/usr/bin/env python3
"""Validate the session lifecycle-moments manifest (scripts/session/moments.json).

The manifest binds each conversational "moment" in a working session to a handler
script, a Claude Code hook, and a per-git-comfort behaviour. Phases 2-3 import it;
this validator keeps it honest, the same way validate-skills.py and
validate-frontmatter.py guard their contracts.

Checks:
  - valid JSON with a top-level "moments" list (non-empty)
  - each moment has: id, trigger, handler, hook, status, behavior_by_comfort
  - status in {active, planned}
  - behavior_by_comfort keys == {git-native, guided, hidden}; values in {auto, offer, skip}
  - ids are unique
  - handler file exists when status == "active"

Usage:  validate-moments.py           # validate scripts/session/moments.json
Exit 0 if valid, 1 otherwise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_FIELDS = ["id", "trigger", "handler", "hook", "status", "behavior_by_comfort"]
STATUSES = {"active", "planned"}
COMFORT_KEYS = {"git-native", "guided", "hidden"}
BEHAVIORS = {"auto", "offer", "skip"}
MANIFEST_REL = "scripts/session/moments.json"


def validate_manifest(data, base_dir: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest root must be a JSON object"]
    moments = data.get("moments")
    if not isinstance(moments, list):
        return ["manifest must have a 'moments' list"]
    if not moments:
        errors.append("'moments' list is empty")

    seen_ids: set = set()
    for i, m in enumerate(moments):
        if not isinstance(m, dict):
            errors.append(f"moments[{i}]: must be a JSON object")
            continue
        mid = m.get("id", f"<index {i}>")
        for field in REQUIRED_FIELDS:
            if field not in m:
                errors.append(f"{mid}: missing required field '{field}'")
        if "id" in m:
            if m["id"] in seen_ids:
                errors.append(f"{mid}: duplicate id")
            seen_ids.add(m["id"])
        status = m.get("status")
        if status is not None and status not in STATUSES:
            errors.append(f"{mid}: status={status!r} not in {sorted(STATUSES)}")
        bbc = m.get("behavior_by_comfort")
        if isinstance(bbc, dict):
            if set(bbc.keys()) != COMFORT_KEYS:
                errors.append(f"{mid}: behavior_by_comfort keys must be exactly {sorted(COMFORT_KEYS)}")
            for k, v in bbc.items():
                if v not in BEHAVIORS:
                    errors.append(f"{mid}: behavior_by_comfort[{k}]={v!r} not in {sorted(BEHAVIORS)}")
        elif bbc is not None:
            errors.append(f"{mid}: behavior_by_comfort must be an object")
        handler = m.get("handler")
        if status == "active" and isinstance(handler, str):
            if not (base_dir / handler).exists():
                errors.append(f"{mid}: active handler not found: {handler}")
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
    print(f"ok    {MANIFEST_REL} ({len(data.get('moments', []))} moments)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 template/scripts/tests/test_validate_moments.py`
Expected: PASS — `OK` with 10 tests run.

- [ ] **Step 5: Commit**

```bash
git add template/scripts/validate-moments.py template/scripts/tests/test_validate_moments.py
git commit -m "feat: add lifecycle-moments manifest validator

Stdlib validator (validate_manifest + main) mirroring the existing
validate-skills/validate-frontmatter pattern, with a unittest suite.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: The manifest (`moments.json`)

**Files:**
- Create: `template/scripts/session/moments.json`

**Interfaces:**
- Consumes: `validate-moments.py` from Task 1.
- Produces: the manifest imported by Phases 2–3. `active` handlers referenced (`scripts/session/start.sh`, `scripts/session/wrapup.sh`) already exist in the kit.

- [ ] **Step 1: Create the manifest**

Create `template/scripts/session/moments.json`:

```json
{
  "version": 1,
  "moments": [
    {
      "id": "session-start",
      "trigger": "A new working session begins.",
      "handler": "scripts/session/start.sh",
      "hook": "SessionStart",
      "status": "active",
      "behavior_by_comfort": { "git-native": "offer", "guided": "offer", "hidden": "auto" }
    },
    {
      "id": "checkpoint",
      "trigger": "The operator finishes a topic or says 'I'm done with X'.",
      "handler": "scripts/session/checkpoint.sh",
      "hook": null,
      "status": "planned",
      "behavior_by_comfort": { "git-native": "offer", "guided": "offer", "hidden": "auto" }
    },
    {
      "id": "decision-made",
      "trigger": "A decision or ADR is reached in conversation.",
      "handler": "scripts/session/record-decision.sh",
      "hook": null,
      "status": "planned",
      "behavior_by_comfort": { "git-native": "offer", "guided": "offer", "hidden": "offer" }
    },
    {
      "id": "session-end",
      "trigger": "The operator signals they are wrapping up.",
      "handler": "scripts/session/wrapup.sh",
      "hook": "Stop",
      "status": "active",
      "behavior_by_comfort": { "git-native": "offer", "guided": "offer", "hidden": "auto" }
    }
  ]
}
```

- [ ] **Step 2: Validate the real manifest**

Run: `python3 template/scripts/validate-moments.py`
Expected: PASS — `ok    scripts/session/moments.json (4 moments)`, exit 0. (The two `active` handlers exist; the two `planned` handlers are not required yet.)

- [ ] **Step 3: Commit**

```bash
git add template/scripts/session/moments.json
git commit -m "feat: add session lifecycle-moments manifest

Four moments (session-start, checkpoint, decision-made, session-end)
with handler, hook, status, and per-git-comfort behaviour. Validated
by validate-moments.py.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Wire the validator into CI and pre-commit

**Files:**
- Modify: `.gitlab-ci.yml` (repo root)
- Modify: `template/.pre-commit-config.yaml`

**Interfaces:**
- Consumes: `validate-moments.py` (Task 1), `moments.json` (Task 2).

- [ ] **Step 1: Add the validator + test to the governance gate**

Read `.gitlab-ci.yml`. In the `ai-governance` job's `script:` list, immediately **after** the line `- python3 template/scripts/validate-frontmatter.py` (and its preceding `echo`), insert:

```yaml
  - echo "Validating session lifecycle-moments manifest…"
  - python3 template/scripts/validate-moments.py
  - echo "Running validator unit tests…"
  - python3 template/scripts/tests/test_validate_moments.py
```

- [ ] **Step 2: Verify the CI edit is well-formed and the commands pass locally**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.gitlab-ci.yml')); print('yaml-ok')"`
Expected: `yaml-ok`.
Run: `python3 template/scripts/validate-moments.py && python3 template/scripts/tests/test_validate_moments.py`
Expected: validator prints `ok …`; tests print `OK`; overall exit 0.

- [ ] **Step 3: Add the pre-commit hook**

Read `template/.pre-commit-config.yaml`. Following the existing local-hook pattern (same style as the `validate-skills` / `validate-frontmatter` hooks already there), add under the `repo: local` hooks list:

```yaml
      - id: validate-moments
        name: Validate session lifecycle-moments manifest
        entry: python3 scripts/validate-moments.py
        language: system
        files: ^scripts/session/moments\.json$
        pass_filenames: false
```

(Note: `entry` uses the project-relative path `scripts/validate-moments.py` because pre-commit runs from the bootstrapped project root, where `template/` is the root.)

- [ ] **Step 4: Verify the pre-commit config parses**

Run: `python3 -c "import yaml; yaml.safe_load(open('template/.pre-commit-config.yaml')); print('yaml-ok')"`
Expected: `yaml-ok`.

- [ ] **Step 5: Commit**

```bash
git add .gitlab-ci.yml template/.pre-commit-config.yaml
git commit -m "ci: gate the lifecycle-moments manifest

Run validate-moments.py + its unit tests in the ai-governance stage,
and add a validate-moments pre-commit hook on moments.json.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `git-comfort` in onboarding

**Files:**
- Modify: `template/USER.md.example`
- Modify: `template/ONBOARDING.md`

- [ ] **Step 1: Add the field to `USER.md.example`**

In `template/USER.md.example`, under **## Identity**, add a line immediately after the `**Seat:**` line:

```markdown
- **Git comfort:** <git-native | guided | hidden>
```

- [ ] **Step 2: Add Step 5.2b to `ONBOARDING.md`**

In `template/ONBOARDING.md`, immediately after the `### 5.2 Seat` block (before `### 5.3 Communication preferences`), insert:

```markdown
### 5.2b Git comfort

Based on the seat, propose a **git-comfort** level and ask the user to confirm or change it:

> "Based on your seat I'd set your **git-comfort** to `<default>`. Keep it, or change it? (git-native / guided / hidden)"

| Seat | Suggested default | Meaning |
|---|---|---|
| Architect / EM / Developer | `git-native` | You drive git directly — branches, commits, PRs. |
| QA | `guided` | Intent-verbs with a brief explanation of the git underneath. |
| Product (PO/PM) | `hidden` | Git fully abstracted — "save my work", "get the latest", "send for review". |
| Custom seat | *(ask explicitly — no default)* | — |

Record the confirmed level. It is written to `USER.md` (Step 6) and governs how git surfaces to this operator in later sessions (see `docs/ai-context/lifecycle-moments.md`).
```

- [ ] **Step 3: Reference git-comfort in Step 6**

In `template/ONBOARDING.md` Step 6, change the sentence so it reads (add "seat, git-comfort," to the enumerated answers):

> Write `USER.md` at the repo root from the shape in [`USER.md.example`](./USER.md.example), filling in the answers from Step 5 (name, email, seat, **git-comfort**, communication preferences). Keep it under 100 lines. It is git-ignored.

- [ ] **Step 4: Verify the edits are present and coherent**

Run: `grep -n "Git comfort" template/USER.md.example`
Expected: one match (the new field).
Run: `grep -n "5.2b Git comfort" template/ONBOARDING.md && grep -n "git-comfort" template/ONBOARDING.md`
Expected: the new step heading matches and at least one `git-comfort` reference in Step 6.

- [ ] **Step 5: Commit**

```bash
git add template/USER.md.example template/ONBOARDING.md
git commit -m "feat: capture git-comfort during onboarding

Add the Git comfort field to USER.md.example and Step 5.2b to
ONBOARDING.md: seat-suggested default (git-native/guided/hidden),
user confirms, written to USER.md.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: The ai-context docs (`lifecycle-moments.md`, `attribution.md`)

**Files:**
- Create: `template/docs/ai-context/lifecycle-moments.md`
- Create: `template/docs/ai-context/attribution.md`

**Interfaces:**
- Consumes: `moments.json` (Task 2) — the lifecycle doc references it.
- Verified by: the existing `template/scripts/validate-frontmatter.py`.

- [ ] **Step 1: Create `lifecycle-moments.md`**

Create `template/docs/ai-context/lifecycle-moments.md`:

```markdown
---
title: "Session lifecycle moments"
status: approved
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-07-02
classification: internal
last-reviewed: 2026-07-02
ai-trust: working
---

# Session lifecycle moments

A **lifecycle moment** is a natural point in a working session where the framework may act on the operator's behalf — sync the repo, checkpoint work, record a decision, or wrap up. Binding automation to *moments* (not to git commands) is what lets non-git-literate seats work safely: the operator signals intent in conversation, and the framework does the git.

The machine-readable contract is [`scripts/session/moments.json`](../../scripts/session/moments.json); this document is its human companion. Phases 2–3 of the evolution roadmap import the manifest to fire hooks and classify work. Keep the two in sync — the `validate-moments.py` gate enforces the manifest's shape.

## The four moments

| Moment | Fires when | Handler | Status |
|---|---|---|---|
| `session-start` | a new working session begins | `scripts/session/start.sh` (+ `sync.sh`) | active |
| `checkpoint` | the operator finishes a topic / says "I'm done with X" | `scripts/session/checkpoint.sh` | planned (Phase 2) |
| `decision-made` | a decision or ADR is reached in conversation | `scripts/session/record-decision.sh` | planned (Phase 2) |
| `session-end` | the operator signals they are wrapping up | `scripts/session/wrapup.sh` | active |

## Behaviour by git-comfort

Each moment declares a behaviour per `git-comfort` level (recorded in `USER.md`):

- **`auto`** — the framework performs the action and reports it in plain language.
- **`offer`** — the framework asks first, then acts on agreement.
- **`skip`** — the framework does nothing for this level.

The intent: `hidden` operators (typically Product) get `auto` sync / checkpoint / wrap-up so they never lose work or think about git; `git-native` operators get `offer` so nothing happens behind their back.

## The `status` field

`status: planned` marks moments whose handler is introduced in a later phase. The `session-end` handler exists today (`wrapup.sh`); its `Stop`-hook binding is wired in Phase 2. The `validate-moments.py` gate only requires a handler file to exist for `active` moments.
```

- [ ] **Step 2: Create `attribution.md`**

Create `template/docs/ai-context/attribution.md`:

```markdown
---
title: "Commit-attribution convention"
status: approved
owner: EM
author: AI-SDLC Bootstrap Kit
created: 2026-07-02
classification: internal
last-reviewed: 2026-07-02
ai-trust: working
---

# Commit-attribution convention

To make AI usage measurable (pillar 7 — the dashboard and retro loop), every commit is classifiable as **human**, **AI-authored**, or **mixed**. This document fixes the convention; the classifier that consumes it is built in Phase 3 of the evolution roadmap.

## Baseline signal — the `Co-Authored-By` trailer

An AI-assisted commit carries a trailer naming the agent:

```
Co-Authored-By: <Agent Name> <email>
```

This is **tool-agnostic** — Claude Code, GitHub Copilot, and Cursor all emit or support this trailer — so classification never depends on a single vendor. A commit with no AI trailer is treated as **human**.

## The three classes

| Class | Rule |
|---|---|
| **human** | No AI `Co-Authored-By` trailer. |
| **AI-authored** | An agent produced the commit and it carries the trailer. |
| **mixed** | AI-produced content later edited by a human. |

> The precise, reproducible rule for **mixed** (how much human editing tips a commit from AI-authored to mixed) is defined in Phase 3, where the classifier lives. Phase 0 fixes only the vocabulary and the trailer convention.

## Upgrade path — line-level attribution

When per-commit granularity is not enough, the convention upgrades to **`git-ai`** (git-ai-project): agents self-report exactly which lines they wrote, stored in **git notes** without rewriting history, viewable via `git log --show-notes=ai`. Phase 0 does **not** install `git-ai` or build any classifier — it only records this as the sanctioned path to line-level precision.
```

- [ ] **Step 3: Verify both docs satisfy the frontmatter contract**

Run: `python3 template/scripts/validate-frontmatter.py template/docs/ai-context/lifecycle-moments.md template/docs/ai-context/attribution.md`
Expected: two `ok` lines, exit 0, no missing-field warnings.

- [ ] **Step 4: Commit**

```bash
git add template/docs/ai-context/lifecycle-moments.md template/docs/ai-context/attribution.md
git commit -m "docs: add lifecycle-moments and attribution conventions

Human companion to moments.json, and the commit-attribution
convention (Co-Authored-By baseline, three classes, git-ai upgrade
path). Both carry the frontmatter contract.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `AGENTS.md` pointers

**Files:**
- Modify: `template/AGENTS.md`

**Interfaces:**
- Consumes: `lifecycle-moments.md`, `attribution.md` (Task 5).

- [ ] **Step 1: Add the git-comfort row to the §0 `USER.md` fields table**

In `template/AGENTS.md`, in the "What lives in `USER.md`" table (§0), insert a row immediately after the `**Seat**` row:

```markdown
| **Git comfort** | How much git to surface to this seat — `git-native` / `guided` / `hidden`; governs session-sync ergonomics (see [`docs/ai-context/lifecycle-moments.md`](./docs/ai-context/lifecycle-moments.md)) |
```

- [ ] **Step 2: Extend the §2.1 `docs/ai-context/` table cell**

In the §2.1 knowledge-tree table, change the `docs/ai-context/` row's "Holds" cell to:

```markdown
| `docs/ai-context/` | Trust tiers, MCP posture, read-on-demand role playbooks, session lifecycle moments, commit-attribution convention |
```

- [ ] **Step 3: Add §4.5 (Commit attribution)**

In `template/AGENTS.md`, immediately after the §4.4 block (Knowledge grounding) and before `## 5. Roles & named seats`, insert:

```markdown
### 4.5 Commit attribution

Every commit is classifiable as **human**, **AI-authored**, or **mixed** so AI usage stays measurable (pillar 7). AI-assisted commits carry a `Co-Authored-By: <agent> <email>` trailer. The convention — and the `git-ai` upgrade path for line-level attribution — is in [`docs/ai-context/attribution.md`](./docs/ai-context/attribution.md).
```

- [ ] **Step 4: Verify the pointers are present and `CLAUDE.md` is untouched**

Run: `grep -n "Git comfort" template/AGENTS.md && grep -n "4.5 Commit attribution" template/AGENTS.md && grep -n "session lifecycle moments" template/AGENTS.md`
Expected: one match each.
Run: `git diff --name-only` — confirm `template/CLAUDE.md` is **not** listed (it stays a pure pointer).

- [ ] **Step 5: Commit**

```bash
git add template/AGENTS.md
git commit -m "docs: point AGENTS.md at the Phase 0 primitives

Add a git-comfort row to the USER.md field table, extend the
ai-context tree cell, and add §4.5 referencing the attribution
convention. CLAUDE.md remains a pure pointer.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] Run the full governance gate locally, exactly as CI does:

```bash
python3 template/scripts/validate-skills.py
python3 template/scripts/validate-frontmatter.py
python3 template/scripts/validate-moments.py
python3 template/scripts/tests/test_validate_moments.py
python3 template/scripts/knowledge/ingest.py --build
```
Expected: every command exits 0.

- [ ] Confirm all six tasks' files exist and are committed: `git status` is clean; `git log --oneline -6` shows the six task commits.

---

## Self-review against the spec

- **Component A (git-comfort):** Task 4 (USER.md.example field, ONBOARDING Step 5.2b + Step 6), plus the §0 pointer in Task 6. ✓
- **Component B (lifecycle moments):** Task 2 (`moments.json`), Task 5 (`lifecycle-moments.md`), Task 1 (validator). ✓
- **Component C (attribution):** Task 5 (`attribution.md`), Task 6 §4.5 pointer. ✓
- **Validation & governance:** Task 1 (validator + tests), Task 3 (CI + pre-commit). ✓
- **AGENTS.md pointers:** Task 6 (all three). ✓
- **Acceptance criteria 1–7:** each maps to a task's verification step; the Final verification block runs the whole gate. ✓
- **Out-of-scope items** (runtime consumption, checkpoint/record-decision handlers, classifier, git-ai install) are absent from every task, as intended. ✓
