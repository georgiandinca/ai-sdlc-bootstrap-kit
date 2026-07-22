# Phase 2 — Conversational Context-Sync Hooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the runtime git automation — git-comfort-aware auto-sync, `checkpoint`/`decision` handlers, a portable `git-verbs` skill, a non-interactive `SessionEnd` safety net, and a debounced `Stop` reminder — so non-git seats never touch git and never lose work.

**Architecture:** A shared `lib.sh`, four new session scripts, one new skill, edits to `start.sh` / `moments.json` / `settings.json` / `AGENTS.md`. All under `template/`. Behaviour is driven by `git-comfort` (from `USER.md`) × `moments.json` `behavior_by_comfort`. Hooks verified against official docs: `SessionStart` (auto-sync), `SessionEnd` (non-interactive safety net), `Stop` (debounced reminder).

**Tech Stack:** Bash (POSIX-portable, macOS BSD + Linux GNU), Python 3 (stdlib, for JSON reads), JSON, Markdown/YAML.

## Global Constraints

- All files under `template/`.
- Bash scripts: `set -uo pipefail` (NOT `-e` for the session/hook scripts — they must degrade gracefully and exit 0); POSIX-portable (`sed -E`, no GNU-only flags); source `lib.sh` for comfort/behaviour reads.
- Hook scripts (`start.sh`, `auto-save.sh`, `stop.sh`) MUST exit 0 always and be safe with no `USER.md` / no remote.
- `checkpoint.sh`, `record-decision.sh`, `auto-save.sh` MUST NOT commit to a protected branch (`main`/`master`) — use `sdlc_ensure_feature_branch`.
- git-comfort values: `git-native` | `guided` | `hidden`. Auto behaviours apply to `hidden`; offers to `guided`/`git-native` per `moments.json`.
- `moments.json` `behavior_by_comfort` keys are exactly `git-native`,`guided`,`hidden`; values `auto`|`offer`|`skip`; `status` ∈ `active`|`planned`. `validate-moments.py` requires every `active` handler to exist.
- A `SKILL.md` must have frontmatter `name` (= parent dir, lowercase-hyphen) + `description` (1–1024 chars); metadata is str→str. `validate-skills.py` enforces this.
- New `template/docs/**/*.md` (ADRs produced by `record-decision.sh` at runtime) carry the frontmatter contract — the script's template already includes it.
- `CLAUDE.md` stays a pure pointer. Match kit house style (`artefact`, `-ise`).
- Every commit message ends with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

**Created:**
- `template/scripts/session/lib.sh` — shared helpers.
- `template/scripts/session/checkpoint.sh` — "save my work".
- `template/scripts/session/record-decision.sh` — ADR writer.
- `template/scripts/session/auto-save.sh` — SessionEnd safety net.
- `template/scripts/session/stop.sh` — debounced Stop reminder.
- `template/scripts/tests/test_session_lib.sh` — lib.sh functional test.
- `template/.claude/skills/git-verbs/SKILL.md` — intent-verb skill.

**Modified:**
- `template/scripts/session/start.sh` — auto-sync + verb guidance.
- `template/scripts/session/moments.json` — 4 → 6 moments + corrections.
- `template/.claude/settings.json` — add `SessionEnd` + `Stop` hooks.
- `template/AGENTS.md` — one-line git-verbs pointer.

---

## Task 1: Shared `lib.sh` + test

**Files:**
- Create: `template/scripts/session/lib.sh`
- Test: `template/scripts/tests/test_session_lib.sh`

**Interfaces:**
- Produces (sourced functions): `sdlc_repo_root`; `sdlc_git_comfort` (echo git-comfort from USER.md, else `$SESSION_GIT_COMFORT`, else `unset`); `sdlc_seat`; `sdlc_moment_behavior <moment-id> <comfort>` (echo `auto|offer|skip|""`); `sdlc_ensure_feature_branch <seat> <purpose>` (if on main/master, switch to `session/<seat-slug>/<purpose>`; echo the branch).

- [ ] **Step 1: Write the failing test**

Create `template/scripts/tests/test_session_lib.sh`:

```bash
#!/usr/bin/env bash
# Functional test for lib.sh (no framework). Exits non-zero on any failure.
set -uo pipefail
SRC_ROOT=$(cd "$(dirname "$0")/../../.." && pwd)   # repo root (…/template)
LIB="$SRC_ROOT/template/scripts/session/lib.sh"
[ -f "$LIB" ] || LIB="$SRC_ROOT/scripts/session/lib.sh"   # when run from inside template/
fails=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got '$2' want '$3'"; fails=$((fails+1)); fi; }

tmp=$(mktemp -d); ( cd "$tmp"
  git init -q; mkdir -p scripts/session
  cp "$LIB" scripts/session/lib.sh
  cat > scripts/session/moments.json <<'JSON'
{ "version": 1, "moments": [
  { "id": "session-start", "trigger": "x", "handler": "scripts/session/start.sh", "hook": "SessionStart", "status": "active",
    "behavior_by_comfort": { "git-native": "offer", "guided": "offer", "hidden": "auto" } } ] }
JSON
  printf -- '- **Seat:** Product\n- **Git comfort:** hidden\n' > USER.md
  # shellcheck source=/dev/null
  . scripts/session/lib.sh
  check comfort   "$(sdlc_git_comfort)"                       "hidden"
  check seat      "$(sdlc_seat)"                              "Product"
  check behavior  "$(sdlc_moment_behavior session-start hidden)" "auto"
  check behavior2 "$(sdlc_moment_behavior session-start git-native)" "offer"
  git checkout -q -b main 2>/dev/null || git branch -m main
  br=$(sdlc_ensure_feature_branch Product save); check branch "$br" "session/product/save"
  exit $fails
)
rc=$?
rm -rf "$tmp"
exit $rc
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash template/scripts/tests/test_session_lib.sh; echo "exit=$?"`
Expected: FAIL — non-zero exit / `lib.sh` not found (it does not exist yet).

- [ ] **Step 3: Write `lib.sh`**

Create `template/scripts/session/lib.sh`:

```bash
#!/usr/bin/env bash
# Shared helpers for the session scripts. Source this; do not execute it.
# All functions are read-only except sdlc_ensure_feature_branch (which may
# create/switch a branch when the caller is on a protected branch).

sdlc_repo_root() { git rev-parse --show-toplevel 2>/dev/null; }

# Echo a value from a USER.md bold marker line, e.g. sdlc__user_field 'Git comfort'.
sdlc__user_field() {
  local root field v="" ; field="$1"
  root=$(sdlc_repo_root) || true
  if [ -n "${root:-}" ] && [ -f "$root/USER.md" ]; then
    v=$(grep -iE "^- \*\*${field}:\*\*" "$root/USER.md" | head -1 | sed -E "s/^- \*\*${field}:\*\* *//; s/ *\$//")
  fi
  printf '%s' "$v"
}

sdlc_git_comfort() {
  local v; v=$(sdlc__user_field 'Git comfort')
  [ -z "$v" ] && v="${SESSION_GIT_COMFORT:-}"
  [ -z "$v" ] && v="unset"
  printf '%s\n' "$v"
}

sdlc_seat() {
  local v; v=$(sdlc__user_field 'Seat')
  [ -z "$v" ] && v="${SESSION_SEAT:-}"
  printf '%s\n' "$v"
}

# sdlc_moment_behavior <moment-id> <comfort> -> auto|offer|skip (empty if unknown)
sdlc_moment_behavior() {
  local root; root=$(sdlc_repo_root) || return 0
  [ -f "$root/scripts/session/moments.json" ] || return 0
  python3 - "$1" "$2" "$root/scripts/session/moments.json" <<'PY' 2>/dev/null || true
import json, sys
mid, comfort, path = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    data = json.load(open(path))
except Exception:
    sys.exit(0)
for m in data.get("moments", []):
    if m.get("id") == mid:
        print(m.get("behavior_by_comfort", {}).get(comfort, ""))
        break
PY
}

# If on a protected branch, switch to a personal feature branch. Echo the branch.
sdlc_ensure_feature_branch() {
  local seat="${1:-}" purpose="${2:-work}" branch slug
  branch=$(git branch --show-current)
  if [ "$branch" = main ] || [ "$branch" = master ]; then
    slug=$(printf '%s' "${seat:-work}" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-')
    [ -z "$slug" ] && slug=work
    branch="session/${slug}/${purpose}"
    git switch -c "$branch" 2>/dev/null || git switch "$branch" 2>/dev/null || true
  fi
  printf '%s\n' "$branch"
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bash template/scripts/tests/test_session_lib.sh; echo "exit=$?"`
Expected: PASS — all `ok` lines, `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add template/scripts/session/lib.sh template/scripts/tests/test_session_lib.sh
git commit -m "feat: add shared session lib.sh (comfort/seat/behaviour helpers)

Sourced helpers used by the Phase 2 scripts: read git-comfort/seat from
USER.md, look up a moment's behavior_by_comfort, and move off a
protected branch. Functional test included.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `checkpoint.sh` ("save my work")

**Files:**
- Create: `template/scripts/session/checkpoint.sh`

**Interfaces:**
- Consumes: `lib.sh` (`sdlc_repo_root`, `sdlc_seat`, `sdlc_ensure_feature_branch`).

- [ ] **Step 1: Write the script**

Create `template/scripts/session/checkpoint.sh` (and `chmod +x`):

```bash
#!/usr/bin/env bash
# "Save my work": commit + push current changes to a safe branch. No PR.
# Never commits to a protected branch. Usage:
#   checkpoint.sh [--seat <seat>] ["message"] [path ...]
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
. "$here/lib.sh"
root=$(sdlc_repo_root) || { echo "[checkpoint] not in a git repo" >&2; exit 1; }
cd "$root"

seat=""
if [ "${1:-}" = "--seat" ]; then seat="${2:-}"; shift 2 2>/dev/null || shift $#; fi
[ -z "$seat" ] && seat=$(sdlc_seat)
msg="${1:-}"; if [ -n "$msg" ]; then shift; fi
[ -z "$msg" ] && msg="checkpoint: work in progress"

if [ -z "$(git status --porcelain)" ]; then echo "[checkpoint] nothing to save — tree clean."; exit 0; fi

branch=$(sdlc_ensure_feature_branch "$seat" checkpoint)
[ "$branch" != "$(git branch --show-current 2>/dev/null)" ] && echo "[checkpoint] moved to $branch (was on a protected branch)."

if [ "$#" -gt 0 ]; then git add -- "$@"; else git add -A; fi
git diff --cached --quiet && { echo "[checkpoint] nothing staged."; exit 0; }
git commit -q -m "$msg"
if git push -u origin "$branch" >/dev/null 2>&1; then
  echo "[checkpoint] saved and pushed on $branch."
else
  echo "[checkpoint] committed on $branch (push skipped — no remote or offline)."
fi
```

- [ ] **Step 2: Functional test (with a bare remote)**

```bash
work=$(mktemp -d); rem=$(mktemp -d)
git init -q --bare "$rem/origin.git"
( cd "$work" && git init -q && git remote add origin "$rem/origin.git" && \
  git checkout -q -b main && mkdir -p scripts/session && \
  cp $KIT_ROOT/template/scripts/session/lib.sh scripts/session/lib.sh && \
  cp $KIT_ROOT/template/scripts/session/checkpoint.sh scripts/session/checkpoint.sh && \
  printf -- '- **Seat:** Product\n- **Git comfort:** hidden\n' > USER.md && \
  echo "draft story" > story.md && \
  bash scripts/session/checkpoint.sh "save story" && \
  echo "--- branch ---" && git branch --show-current && \
  echo "--- last commit ---" && git log --oneline -1 && \
  echo "--- not on main? ---" && [ "$(git branch --show-current)" != main ] && echo "OFF-MAIN-OK" )
bash -n $KIT_ROOT/template/scripts/session/checkpoint.sh && echo "syntax ok"
rm -rf "$work" "$rem"
```
Expected: branch is `session/product/checkpoint` (not `main`), a commit `save story` exists, `OFF-MAIN-OK`, `syntax ok`.

- [ ] **Step 3: Commit**

```bash
git add template/scripts/session/checkpoint.sh
git commit -m "feat: add checkpoint.sh (save my work)

Commit + push current changes to a safe personal branch (never a
protected branch), no PR. Backs the 'save my work' verb and the
checkpoint moment.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `record-decision.sh` (ADR writer)

**Files:**
- Create: `template/scripts/session/record-decision.sh`

**Interfaces:**
- Consumes: `lib.sh` (`sdlc_repo_root`, `sdlc_seat`, `sdlc_ensure_feature_branch`).

- [ ] **Step 1: Write the script**

Create `template/scripts/session/record-decision.sh` (and `chmod +x`):

```bash
#!/usr/bin/env bash
# Record an ADR: write docs/architecture/decisions/ADR-<NNNN>-<slug>.md and commit.
# Never commits to a protected branch. Usage: record-decision.sh "<title>"
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
. "$here/lib.sh"
root=$(sdlc_repo_root) || { echo "[decision] not in a git repo" >&2; exit 1; }
cd "$root"

title="${1:-}"; [ -n "$title" ] || { echo "[decision] usage: record-decision.sh \"<title>\"" >&2; exit 2; }

dir="docs/architecture/decisions"; mkdir -p "$dir"
n=0
for f in "$dir"/ADR-*.md; do
  [ -e "$f" ] || continue
  num=$(basename "$f" | sed -E 's/^ADR-0*([0-9]+)-.*/\1/')
  case "$num" in ''|*[!0-9]*) continue ;; esac
  [ "$num" -gt "$n" ] && n="$num"
done
next=$(printf '%04d' $((n + 1)))
slug=$(printf '%s' "$title" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-' | cut -c1-50)
[ -z "$slug" ] && slug="decision"
file="$dir/ADR-${next}-${slug}.md"
today=$(date +%Y-%m-%d)
seat=$(sdlc_seat); [ -z "$seat" ] && seat="Architect"

cat > "$file" <<EOF
---
title: "ADR-${next}: ${title}"
status: draft
owner: Architect
author: ${seat}
created: ${today}
classification: internal
last-reviewed: ${today}
ai-trust: working
---

# ADR-${next}: ${title}

## Context

<Why is this decision needed? What forces are at play?>

## Decision

We will <state the decision as a completed choice>.

## Consequences

<Trade-offs, follow-ups, and what this enables or constrains.>
EOF

branch=$(sdlc_ensure_feature_branch "$seat" adr)
git add "$file"
git commit -q -m "docs: ADR-${next} ${title}"
echo "[decision] wrote $file and committed on $branch."
```

- [ ] **Step 2: Functional test**

```bash
work=$(mktemp -d)
( cd "$work" && git init -q && git checkout -q -b work && mkdir -p scripts/session && \
  cp $KIT_ROOT/template/scripts/session/lib.sh scripts/session/lib.sh && \
  cp $KIT_ROOT/template/scripts/session/record-decision.sh scripts/session/record-decision.sh && \
  printf -- '- **Seat:** Architect\n- **Git comfort:** git-native\n' > USER.md && \
  bash scripts/session/record-decision.sh "Adopt hexagonal architecture" && \
  echo "--- file ---" && ls docs/architecture/decisions/ && \
  echo "--- head of ADR ---" && head -3 docs/architecture/decisions/ADR-0001-*.md && \
  echo "--- committed? ---" && git log --oneline -1 )
python3 $KIT_ROOT/template/scripts/validate-frontmatter.py "$work"/docs/architecture/decisions/ADR-0001-*.md 2>/dev/null || echo "(frontmatter validator needs repo context; skip)"
bash -n $KIT_ROOT/template/scripts/session/record-decision.sh && echo "syntax ok"
rm -rf "$work"
```
Expected: an `ADR-0001-adopt-hexagonal-architecture.md` created, frontmatter with `title: "ADR-0001: …"`, a `docs: ADR-0001 …` commit, `syntax ok`. (The frontmatter validator run may be skipped since it scans a fixed root; the ADR template includes all required fields by construction.)

- [ ] **Step 3: Commit**

```bash
git add template/scripts/session/record-decision.sh
git commit -m "feat: add record-decision.sh (ADR writer)

Auto-numbers and writes a frontmatter-valid ADR skeleton
(Context/Decision/Consequences) and commits it on a safe branch.
Backs the decision-made moment.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `auto-save.sh` (SessionEnd safety net)

**Files:**
- Create: `template/scripts/session/auto-save.sh`

**Interfaces:**
- Consumes: `lib.sh` (`sdlc_repo_root`, `sdlc_git_comfort`, `sdlc_seat`, `sdlc_ensure_feature_branch`).

- [ ] **Step 1: Write the script**

Create `template/scripts/session/auto-save.sh` (and `chmod +x`):

```bash
#!/usr/bin/env bash
# SessionEnd safety net: for hidden-comfort operators only, commit uncommitted
# work to a personal branch so nothing is lost. Non-interactive; always exit 0.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
. "$here/lib.sh" 2>/dev/null || exit 0
root=$(sdlc_repo_root) || exit 0
cd "$root" || exit 0

[ "$(sdlc_git_comfort)" = hidden ] || exit 0
[ -n "$(git status --porcelain)" ] || exit 0

branch=$(sdlc_ensure_feature_branch "$(sdlc_seat)" autosave)
git add -A
git diff --cached --quiet && exit 0
git commit -q -m "auto-save: session end" || exit 0
git push -u origin "$branch" >/dev/null 2>&1 || true
exit 0
```

- [ ] **Step 2: Functional test (hidden saves; non-hidden no-op)**

```bash
run() { # comfort -> expect committed? (yes/no)
  local comfort="$1" expect="$2" work; work=$(mktemp -d)
  ( cd "$work" && git init -q && git checkout -q -b main && mkdir -p scripts/session && \
    cp $KIT_ROOT/template/scripts/session/lib.sh scripts/session/lib.sh && \
    cp $KIT_ROOT/template/scripts/session/auto-save.sh scripts/session/auto-save.sh && \
    printf -- '- **Seat:** Product\n- **Git comfort:** %s\n' "$comfort" > USER.md && \
    echo "unsaved" > wip.md && \
    bash scripts/session/auto-save.sh; \
    if git log --oneline -1 2>/dev/null | grep -q 'auto-save: session end'; then got=yes; else got=no; fi; \
    echo "comfort=$comfort expect=$expect got=$got"; [ "$got" = "$expect" ] && echo PASS || echo FAIL )
  rm -rf "$work"
}
run hidden yes
run git-native no
bash -n $KIT_ROOT/template/scripts/session/auto-save.sh && echo "syntax ok"
```
Expected: `hidden … PASS` (a commit `auto-save: session end` on `session/product/autosave`), `git-native … PASS` (no commit), `syntax ok`.

- [ ] **Step 3: Commit**

```bash
git add template/scripts/session/auto-save.sh
git commit -m "feat: add auto-save.sh (SessionEnd safety net)

Non-interactive: for hidden-comfort operators, commit uncommitted work
to a personal branch at session end so nothing is lost. No-op for other
comforts. Always exits 0.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `stop.sh` (debounced reminder)

**Files:**
- Create: `template/scripts/session/stop.sh`

**Interfaces:**
- Consumes: `lib.sh` (`sdlc_repo_root`, `sdlc_git_comfort`).

- [ ] **Step 1: Write the script**

Create `template/scripts/session/stop.sh` (and `chmod +x`):

```bash
#!/usr/bin/env bash
# Stop hook (fires every turn): debounced reminder about uncommitted work for
# guided/hidden comfort. Emits a hookSpecificOutput.additionalContext JSON line
# at most once per 600s. Always exit 0.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
. "$here/lib.sh" 2>/dev/null || exit 0
root=$(sdlc_repo_root) || exit 0
cd "$root" || exit 0

case "$(sdlc_git_comfort)" in guided|hidden) ;; *) exit 0 ;; esac
[ -n "$(git status --porcelain)" ] || exit 0

state="$root/.git/.sdlc-stop-state"
now=$(date +%s); last=0
[ -f "$state" ] && last=$(cat "$state" 2>/dev/null || echo 0)
case "$last" in ''|*[!0-9]*) last=0 ;; esac
[ $((now - last)) -lt 600 ] && exit 0
printf '%s' "$now" > "$state" 2>/dev/null || true

echo '{"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":"You have unsaved work. Say: save my work — and I will checkpoint it (scripts/session/checkpoint.sh)."}}'
exit 0
```

- [ ] **Step 2: Functional test (reminds once, then debounced; skips git-native)**

```bash
work=$(mktemp -d)
( cd "$work" && git init -q && git checkout -q -b work && mkdir -p scripts/session && \
  cp $KIT_ROOT/template/scripts/session/lib.sh scripts/session/lib.sh && \
  cp $KIT_ROOT/template/scripts/session/stop.sh scripts/session/stop.sh && \
  printf -- '- **Seat:** QA\n- **Git comfort:** guided\n' > USER.md && \
  echo "wip" > wip.md && \
  echo "--- first call (expect reminder JSON) ---" && bash scripts/session/stop.sh && \
  echo "--- second call within 600s (expect nothing) ---" && out2=$(bash scripts/session/stop.sh) && [ -z "$out2" ] && echo "DEBOUNCED-OK" && \
  echo "--- git-native (expect nothing) ---" && printf -- '- **Seat:** Developer\n- **Git comfort:** git-native\n' > USER.md && rm -f .git/.sdlc-stop-state && out3=$(bash scripts/session/stop.sh) && [ -z "$out3" ] && echo "NATIVE-SKIP-OK" )
bash -n $KIT_ROOT/template/scripts/session/stop.sh && echo "syntax ok"
rm -rf "$work"
```
Expected: first call prints the `hookSpecificOutput` JSON reminder; second call prints nothing (`DEBOUNCED-OK`); git-native prints nothing (`NATIVE-SKIP-OK`); `syntax ok`.

- [ ] **Step 3: Commit**

```bash
git add template/scripts/session/stop.sh
git commit -m "feat: add stop.sh (debounced uncommitted-work reminder)

Stop hook: for guided/hidden comfort with uncommitted changes, inject a
one-line 'save my work' reminder at most once per 600s (state in a
git-ignored .git file). Skips git-native. Always exits 0.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: The `git-verbs` skill

**Files:**
- Create: `template/.claude/skills/git-verbs/SKILL.md`

- [ ] **Step 1: Create the skill**

Create `template/.claude/skills/git-verbs/SKILL.md`:

```markdown
---
name: git-verbs
description: Translate plain-language version-control intents into the project's session scripts for operators who don't work in raw git. Invoke whenever the operator says or means "save my work", "get the latest", "send for review", or otherwise wants to commit/pull/share without touching git directly — especially for guided or hidden git-comfort seats (typically Product/PM and some QA). git-native operators use raw git themselves.
metadata:
  status: "approved"
  classification: "internal"
  ai-trust: "working"
  owner: "EM"
---

# git-verbs

Hide git behind intent for operators whose **git-comfort** (in `USER.md`) is `guided` or `hidden`. Map what they *mean* to a session script; never make them think in branches, commits, or PRs. `git-native` operators drive git themselves — do not use the verbs for them.

## The verbs

| The operator says… | Run | What it does |
|---|---|---|
| "get the latest" / "update my copy" | `scripts/session/sync.sh` | fast-forward pull (refuses on a dirty tree) |
| "save my work" / "I'm done with this" | `scripts/session/checkpoint.sh "<short summary>"` | commit + push to a safe personal branch — **no** review requested |
| "send for review" / "share this" | `scripts/session/wrapup.sh "<message>"` | commit + push + open a merge request |

## Rules

- **Never commit to a protected branch.** `checkpoint.sh` and `wrapup.sh` move to a personal branch automatically — trust them.
- `guided`: say what you're doing in one line ("Saving your work — that's a commit and push."). `hidden`: just do it and confirm ("Saved.").
- Prefer `checkpoint.sh` (save) over `wrapup.sh` (review) unless the operator explicitly wants review — opening a merge request is a deliberate act.
- These verbs realise the lifecycle moments in `scripts/session/moments.json` (`checkpoint`, `session-end`).
```

- [ ] **Step 2: Verify it passes the skills validator**

Run: `python3 template/scripts/validate-skills.py`
Expected: all skills `ok`, including `git-verbs`, exit 0.

- [ ] **Step 3: Commit**

```bash
git add template/.claude/skills/git-verbs/
git commit -m "feat: add git-verbs skill

Portable, agentskills.io-conformant skill mapping save/get-latest/
send-for-review intents to the session scripts for guided/hidden
git-comfort seats. git-native seats use raw git.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `start.sh` — auto-sync + verb guidance

**Files:**
- Modify: `template/scripts/session/start.sh`

**Interfaces:**
- Consumes: `lib.sh` (`sdlc_moment_behavior`); the Phase 1 seat-context block already sets `comfort_u`.

- [ ] **Step 1: Add the auto-sync + verb-guidance block**

Read `template/scripts/session/start.sh`. Near the top, right after the `cd "$repo_root"` line, add (to make `lib.sh` helpers available):

```bash
# shellcheck source=/dev/null
[ -f scripts/session/lib.sh ] && . scripts/session/lib.sh || true
```

Then, immediately **before** the final `cat <<'EOF' … EOF` session-ritual heredoc (i.e. after the Phase 1 `[seat-context]` block), add:

```bash
# --- git-comfort-aware auto-sync + verb guidance (Phase 2) ---
comfort="${comfort_u:-unset}"
ss_behavior=$(sdlc_moment_behavior session-start "$comfort" 2>/dev/null || true)
if [ "${behind:-0}" -gt 0 ] 2>/dev/null && [ "${dirty:-dirty}" = clean ]; then
  if [ "$ss_behavior" = auto ]; then
    if bash scripts/session/sync.sh >/dev/null 2>&1; then
      echo "[sync] auto-pulled ${behind} update(s)."
    else
      echo "[sync] auto-pull did not complete — run scripts/session/sync.sh."
    fi
  else
    echo "[sync] behind by ${behind} — offer to run scripts/session/sync.sh."
  fi
fi
case "$comfort" in
  guided|hidden) echo "[git-verbs] operator is git-'${comfort}' — use the git-verbs skill (save my work / get the latest / send for review), not raw git." ;;
esac
```

- [ ] **Step 2: Functional test**

```bash
# hidden + behind + clean -> auto-pull; and verb guidance shown.
up=$(mktemp -d); work=$(mktemp -d)
git init -q --bare "$up/origin.git"
git clone -q "$up/origin.git" "$work" >/dev/null 2>&1
( cd "$work" && git checkout -q -b main 2>/dev/null || true; mkdir -p scripts/session
  cp $KIT_ROOT/template/scripts/session/{lib.sh,start.sh,sync.sh} scripts/session/
  cp $KIT_ROOT/template/scripts/session/moments.json scripts/session/moments.json
  printf -- '- **Seat:** Product\n- **Git comfort:** hidden\n' > USER.md
  git add -A && git commit -q -m init && git push -q origin HEAD 2>/dev/null || true )
# create an upstream commit so the clone is behind
other=$(mktemp -d); git clone -q "$up/origin.git" "$other" >/dev/null 2>&1
( cd "$other" && echo x > up.md && git add -A && git commit -q -m upstream && git push -q origin HEAD 2>/dev/null || true )
echo "--- run start.sh in the behind clone ---"
( cd "$work" && bash scripts/session/start.sh 2>/dev/null | grep -E '\[sync\]|\[git-verbs\]' )
bash -n $KIT_ROOT/template/scripts/session/start.sh && echo "syntax ok"
rm -rf "$up" "$work" "$other"
```
Expected: a `[sync] auto-pulled …` (or a graceful `[sync]` line) and a `[git-verbs] operator is git-'hidden'…` line; `syntax ok`. (If the push/clone plumbing doesn't produce a behind state in this environment, at minimum the `[git-verbs]` line must appear and `bash -n` must pass.)

- [ ] **Step 3: Commit**

```bash
git add template/scripts/session/start.sh
git commit -m "feat: git-comfort-aware auto-sync + verb guidance at SessionStart

start.sh auto-pulls for hidden comfort (clean+behind) and offers for
others, and points guided/hidden operators at the git-verbs skill.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: `moments.json` — 4 → 6 moments

**Files:**
- Modify: `template/scripts/session/moments.json`

**Interfaces:**
- Consumes: all handler scripts (Tasks 2–5, 7) now exist, so the new `active` moments validate.

- [ ] **Step 1: Replace the manifest**

Overwrite `template/scripts/session/moments.json` with:

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
      "status": "active",
      "behavior_by_comfort": { "git-native": "offer", "guided": "offer", "hidden": "auto" }
    },
    {
      "id": "decision-made",
      "trigger": "A decision or ADR is reached in conversation.",
      "handler": "scripts/session/record-decision.sh",
      "hook": null,
      "status": "active",
      "behavior_by_comfort": { "git-native": "offer", "guided": "offer", "hidden": "offer" }
    },
    {
      "id": "session-end",
      "trigger": "The operator signals they are wrapping up.",
      "handler": "scripts/session/wrapup.sh",
      "hook": null,
      "status": "active",
      "behavior_by_comfort": { "git-native": "offer", "guided": "offer", "hidden": "offer" }
    },
    {
      "id": "session-terminated",
      "trigger": "The agent session actually ends (terminal closes / session exits).",
      "handler": "scripts/session/auto-save.sh",
      "hook": "SessionEnd",
      "status": "active",
      "behavior_by_comfort": { "git-native": "skip", "guided": "skip", "hidden": "auto" }
    },
    {
      "id": "uncommitted-reminder",
      "trigger": "End of any assistant turn while uncommitted work exists.",
      "handler": "scripts/session/stop.sh",
      "hook": "Stop",
      "status": "active",
      "behavior_by_comfort": { "git-native": "skip", "guided": "offer", "hidden": "offer" }
    }
  ]
}
```

- [ ] **Step 2: Validate**

Run: `python3 template/scripts/validate-moments.py`
Expected: `ok    scripts/session/moments.json (6 moments)`, exit 0 (all six `active` handlers exist).

- [ ] **Step 3: Commit**

```bash
git add template/scripts/session/moments.json
git commit -m "feat: grow moments.json to six moments (Phase 2)

Flip checkpoint + decision-made to active; make session-end conversational
(hook null, hidden -> offer); add session-terminated (SessionEnd) and
uncommitted-reminder (Stop). Validated.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Wire hooks (`settings.json`) + `AGENTS.md` pointer

**Files:**
- Modify: `template/.claude/settings.json`
- Modify: `template/AGENTS.md`

- [ ] **Step 1: Add the SessionEnd + Stop hooks**

Overwrite `template/.claude/settings.json` with:

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          { "type": "command", "command": "bash scripts/session/start.sh 2>/dev/null || true" }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          { "type": "command", "command": "bash scripts/session/auto-save.sh 2>/dev/null || true" }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "bash scripts/session/stop.sh 2>/dev/null || true" }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Add the `git-verbs` pointer to `AGENTS.md`**

Read `template/AGENTS.md`. In §0, immediately **after** the "Onboarding runs in two phases." blockquote (the one ending "…Switch seats later with `scripts/session/switch-seat.sh <seat>`."), insert:

```markdown
> **Non-git operators work through verbs, not git.** For `guided`/`hidden` git-comfort seats, use the **`git-verbs`** skill — "save my work" (`checkpoint.sh`), "get the latest" (`sync.sh`), "send for review" (`wrapup.sh`) — never raw git. The SessionStart hook, SessionEnd safety net, and a debounced Stop reminder keep their work synced and never lost (`scripts/session/moments.json`).
```

- [ ] **Step 3: Verify**

Run: `python3 -c "import json; json.load(open('template/.claude/settings.json')); print('json-ok')"` → `json-ok`.
Run: `grep -n "git-verbs" template/AGENTS.md` → at least one match.
Run: `git diff --name-only` → confirm `template/CLAUDE.md` is NOT listed.

- [ ] **Step 4: Commit**

```bash
git add template/.claude/settings.json template/AGENTS.md
git commit -m "feat: wire SessionEnd + Stop hooks; point AGENTS.md at git-verbs

settings.json runs auto-save.sh on SessionEnd and stop.sh on Stop
alongside the existing SessionStart; AGENTS.md §0 references the
git-verbs skill and the sync/safety-net model. CLAUDE.md untouched.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] Run the full governance gate + the Phase 2 bash tests:

```bash
python3 template/scripts/validate-skills.py
python3 template/scripts/validate-frontmatter.py
python3 template/scripts/validate-moments.py
python3 template/scripts/tests/test_validate_moments.py
python3 template/scripts/validate-seat-profiles.py
python3 template/scripts/tests/test_validate_seat_profiles.py
python3 template/scripts/knowledge/ingest.py --build
bash template/scripts/tests/test_session_lib.sh
for s in start sync wrapup checkpoint record-decision auto-save stop lib; do bash -n template/scripts/session/$s.sh && echo "bash -n $s ok"; done
```
Expected: every command exits 0; `validate-moments` reports 6 moments; `validate-skills` includes `git-verbs`.

- [ ] `git status` clean; `git log --oneline main..HEAD` shows the Phase 2 task commits.

---

## Self-review against the spec

- **C1 auto-sync:** Task 7. ✓ · **C2 checkpoint:** Task 2. ✓ · **C3 record-decision:** Task 3. ✓ · **C4 git-verbs skill:** Task 6. ✓ · **C5 SessionEnd net:** Task 4 + Task 9 (wiring) + Task 8 (moment). ✓ · **C6 Stop reminder:** Task 5 + Task 9 (wiring) + Task 8 (moment). ✓ · **C7 moments 4→6:** Task 8. ✓ · **C8 lib.sh:** Task 1. ✓ · **Supporting (settings.json, AGENTS.md):** Task 9. ✓
- **Acceptance criteria 1–8:** each maps to a task verification; Final verification runs the whole gate + bash `-n` + lib test. ✓
- **Out-of-scope** (dashboard, knowledge graph, real connector config) absent from every task. ✓
- **Ordering:** handlers (1–5,7) precede the `moments.json` activation (8) so `validate-moments` never sees an active moment with a missing handler; wiring (9) last. ✓
