---
title: "Kit installer skill — implementation plan"
status: draft
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-09-18
classification: internal
ai-trust: working
---

# Kit Installer Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `install-ai-sdlc-kit` — an invokable, plugin-distributed skill that installs the AI-SDLC Bootstrap Kit into any project (four layouts, merging instead of clobbering) and hands over to the project's own onboarding.

**Architecture:** A read-only bash situation-check script in the skill decides which of three paths applies (install / onboard / report). Installation itself stays in `template/scripts/bootstrap.sh`, extended with a marker-based merge engine, layout awareness, a committed manifest, a generated project README, and pointer blocks. `SKILL.md` is the decision layer only; it holds no copy of the onboarding steps.

**Tech Stack:** POSIX-ish bash (macOS/BSD + GNU portable), Python 3 + PyYAML ≥ 6 (validators and the pre-commit merger only), git, pre-commit, GitHub Actions + GitLab CI.

**Spec:** [`docs/roadmap/2026-09-18-kit-installer-skill-design.md`](./2026-09-18-kit-installer-skill-design.md)

## Global Constraints

- **Branch:** all work lands on `feat/kit-installer-skill` (already created off `main`).
- **Shell portability:** every script starts `#!/usr/bin/env bash` + `set -uo pipefail` (not `-e`: these scripts probe deliberately for absent tools and read non-zero exits as findings; this matches every code sample below and the existing `template/scripts/tests/test_session_lib.sh`). No GNU-only flags. In-place edits use the kit's existing portable idiom: `sed -i.bak … && rm -f "$f.bak"`.
- **Marker strings are exact and never change:** HTML-comment files use `<!-- ai-sdlc-kit:begin -->` / `<!-- ai-sdlc-kit:end -->`; hash-comment files (`.gitignore`, YAML) use `# ai-sdlc-kit:begin` / `# ai-sdlc-kit:end`.
- **Never clobber:** no existing file is overwritten by any code in this plan. Files are created, or merged inside markers, or reported as collisions and left byte-identical.
- **Layout ids are exactly:** `embedded`, `monorepo`, `sidecar`, `parent`.
- **Manifest path:** `.ai-sdlc/kit.json` at the installed kit root; committed (not git-ignored).
- **Tests:** no framework. Shell tests exit non-zero on any failure and print `ok <name>` / `FAIL <name>: got … want …`, following `template/scripts/tests/test_session_lib.sh`. Tests run entirely in `mktemp -d` dirs and make **no network calls**.
- **Skill conformity:** every `SKILL.md` passes `python3 template/scripts/validate-skills.py <path>`; `name` equals its directory name.
- **Python:** stdlib + `pyyaml>=6` only. No new dependencies.
- **Commits:** conventional-commit subjects; every commit message ends with `Refs: <TICKET>-0`-style trailers only if the repo already uses them (the kit repo does not — omit).

---

### Task 1: Situation-check script

The skill's first action. Read-only, no network, exits 0 even when everything is missing.

**Files:**
- Create: `.claude/skills/install-ai-sdlc-kit/scripts/detect-situation.sh`
- Create: `.claude/skills/install-ai-sdlc-kit/scripts/tests/test-detect-situation.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `.gitlab-ci.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: `detect-situation.sh [--dir <path>]` printing one JSON object on stdout with the top-level keys `cwd`, `git`, `kit`, `user_md`, `hooks`, `layout_signals`, `tooling`. Later tasks and `SKILL.md` read these exact key paths: `git.is_repo`, `git.root`, `git.remote`, `git.branch`, `git.dirty`, `git.has_commits`, `kit.state` (`absent|present-uncommitted|present-committed`), `kit.root`, `kit.manifest` (object or `null`), `user_md` (bool), `hooks.config`, `hooks.installed`, `hooks.pre_commit_available`, `layout_signals.workspace_files` (array), `layout_signals.child_repos` (array), `layout_signals.sibling_repos` (array), `tooling.git`, `tooling.python3`, `tooling.pyyaml`.

- [ ] **Step 1: Write the failing test**

Create `.claude/skills/install-ai-sdlc-kit/scripts/tests/test-detect-situation.sh`:

```bash
#!/usr/bin/env bash
# Functional test for detect-situation.sh (no framework). Exits non-zero on any failure.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
DETECT="$HERE/../detect-situation.sh"
fails=0

check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got '$2' want '$3'"; fails=$((fails+1)); fi; }

# Read a dotted key out of the JSON report without a JSON parser dependency in the
# test harness: python3 is present in CI and is only a *test* dependency here.
jqp() { python3 -c '
import json,sys
d=json.load(sys.stdin)
for k in sys.argv[1].split("."):
    d = d[k] if isinstance(d, dict) else None
print(json.dumps(d))' "$1"; }

git_q() { git -c user.name=t -c user.email=t@t "$@" >/dev/null 2>&1; }

# --- Case A: plain empty directory, not a git repo -------------------------------
tmp=$(mktemp -d)
out=$("$DETECT" --dir "$tmp")
check A_is_repo   "$(printf '%s' "$out" | jqp git.is_repo)" "false"
check A_kit_state "$(printf '%s' "$out" | jqp kit.state)"   "\"absent\""
check A_user_md   "$(printf '%s' "$out" | jqp user_md)"     "false"
check A_manifest  "$(printf '%s' "$out" | jqp kit.manifest)" "null"
rm -rf "$tmp"

echo "---"
[ "$fails" -eq 0 ] && echo "all detect-situation tests passed" || echo "$fails test(s) failed"
exit "$fails"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `bash .claude/skills/install-ai-sdlc-kit/scripts/tests/test-detect-situation.sh`
Expected: FAIL — `detect-situation.sh: No such file or directory`.

- [ ] **Step 3: Write the minimal script that passes Case A**

Create `.claude/skills/install-ai-sdlc-kit/scripts/detect-situation.sh`:

```bash
#!/usr/bin/env bash
# detect-situation.sh — read-only situation report for the AI-SDLC kit installer.
#
# Prints one JSON object describing: whether this is a git repo, whether the kit is
# installed and committed, whether this operator is onboarded, the hook state, the
# layout signals, and the available tooling. Writes nothing. Makes no network calls.
# Exits 0 even when things are missing — "missing" is a finding, not an error.
#
# Usage: detect-situation.sh [--dir <path>]
set -uo pipefail

dir="$PWD"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dir) dir=${2:?}; shift 2 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "detect-situation: unknown arg: $1" >&2; exit 2 ;;
  esac
done
cd "$dir" 2>/dev/null || { echo "detect-situation: no such directory: $dir" >&2; exit 2; }
dir=$PWD

# --- JSON helpers (no jq dependency) ---------------------------------------------
json_str() {  # escape a bash string as a JSON string literal
  printf '"%s"' "$(printf '%s' "${1-}" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/	/\\t/g')"
}
json_bool() { [ "${1:-0}" = "1" ] && printf 'true' || printf 'false'; }

# --- git ---------------------------------------------------------------------------
is_repo=0; git_root=""; remote=""; branch=""; dirty=0; has_commits=0
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  is_repo=1
  git_root=$(git rev-parse --show-toplevel 2>/dev/null)
  remote=$(git remote get-url origin 2>/dev/null || printf '')
  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || printf '')
  [ -n "$(git status --porcelain 2>/dev/null)" ] && dirty=1
  git rev-parse HEAD >/dev/null 2>&1 && has_commits=1
fi

# --- kit ---------------------------------------------------------------------------
kit_state="absent"; kit_root=""; manifest="null"
if [ -f "$dir/.ai-sdlc/kit.json" ]; then
  kit_root="$dir"
  manifest=$(cat "$dir/.ai-sdlc/kit.json")
  if [ "$is_repo" = "1" ] && git ls-files --error-unmatch .ai-sdlc/kit.json >/dev/null 2>&1; then
    kit_state="present-committed"
  else
    kit_state="present-uncommitted"
  fi
fi

user_md=0; [ -f "$dir/USER.md" ] && user_md=1

# --- hooks -------------------------------------------------------------------------
hooks_config=0; [ -f "$dir/.pre-commit-config.yaml" ] && hooks_config=1
hooks_installed=0; [ -f "$dir/.git/hooks/pre-commit" ] && \
  grep -q "pre-commit" "$dir/.git/hooks/pre-commit" 2>/dev/null && hooks_installed=1
pre_commit_available=0; command -v pre-commit >/dev/null 2>&1 && pre_commit_available=1

# --- tooling -----------------------------------------------------------------------
v_git=$(git --version 2>/dev/null | awk '{print $3}')
v_py=$(python3 --version 2>/dev/null | awk '{print $2}')
pyyaml=0; python3 -c 'import yaml' >/dev/null 2>&1 && pyyaml=1

cat <<JSON
{
  "cwd": $(json_str "$dir"),
  "git": {
    "is_repo": $(json_bool "$is_repo"),
    "root": $(json_str "$git_root"),
    "remote": $(json_str "$remote"),
    "branch": $(json_str "$branch"),
    "dirty": $(json_bool "$dirty"),
    "has_commits": $(json_bool "$has_commits")
  },
  "kit": {
    "state": $(json_str "$kit_state"),
    "root": $(json_str "$kit_root"),
    "manifest": $manifest
  },
  "user_md": $(json_bool "$user_md"),
  "hooks": {
    "config": $(json_bool "$hooks_config"),
    "installed": $(json_bool "$hooks_installed"),
    "pre_commit_available": $(json_bool "$pre_commit_available")
  },
  "layout_signals": {
    "workspace_files": [],
    "child_repos": [],
    "sibling_repos": []
  },
  "tooling": {
    "git": $(json_str "$v_git"),
    "python3": $(json_str "$v_py"),
    "pyyaml": $(json_bool "$pyyaml")
  }
}
JSON
```

Then: `chmod +x .claude/skills/install-ai-sdlc-kit/scripts/detect-situation.sh .claude/skills/install-ai-sdlc-kit/scripts/tests/test-detect-situation.sh`

- [ ] **Step 4: Run the test and watch Case A pass**

Run: `bash .claude/skills/install-ai-sdlc-kit/scripts/tests/test-detect-situation.sh`
Expected: PASS — four `ok` lines, `all detect-situation tests passed`.

- [ ] **Step 5: Add the failing layout-signal cases**

Append to the test, before the final summary lines:

```bash
# --- Case B: monorepo signals ------------------------------------------------------
tmp=$(mktemp -d); ( cd "$tmp" && git_q init && : > pnpm-workspace.yaml )
out=$("$DETECT" --dir "$tmp")
check B_is_repo    "$(printf '%s' "$out" | jqp git.is_repo)" "true"
check B_workspace  "$(printf '%s' "$out" | jqp layout_signals.workspace_files)" '["pnpm-workspace.yaml"]'
rm -rf "$tmp"

# --- Case C: parent workspace (child repos) ----------------------------------------
tmp=$(mktemp -d); mkdir -p "$tmp/acme-api" "$tmp/acme-web"
( cd "$tmp/acme-api" && git_q init ); ( cd "$tmp/acme-web" && git_q init )
out=$("$DETECT" --dir "$tmp")
check C_children "$(printf '%s' "$out" | jqp layout_signals.child_repos)" '["acme-api", "acme-web"]'
rm -rf "$tmp"

# --- Case D: sidecar (sibling repos) -----------------------------------------------
tmp=$(mktemp -d); mkdir -p "$tmp/acme-sdlc" "$tmp/acme-api"
( cd "$tmp/acme-sdlc" && git_q init ); ( cd "$tmp/acme-api" && git_q init )
out=$("$DETECT" --dir "$tmp/acme-sdlc")
check D_siblings "$(printf '%s' "$out" | jqp layout_signals.sibling_repos)" '["acme-api"]'
rm -rf "$tmp"
```

- [ ] **Step 6: Run the test and watch B, C, D fail**

Run: `bash .claude/skills/install-ai-sdlc-kit/scripts/tests/test-detect-situation.sh`
Expected: FAIL on `B_workspace`, `C_children`, `D_siblings` — all report `[]`.

- [ ] **Step 7: Implement the layout signals**

In `detect-situation.sh`, insert before the `cat <<JSON` block:

```bash
# --- layout signals ---------------------------------------------------------------
json_array() {  # each remaining arg becomes one JSON string element
  local out="" a
  for a in "$@"; do
    [ -n "$out" ] && out="$out, "
    out="$out$(json_str "$a")"
  done
  printf '[%s]' "$out"
}

WORKSPACE_MARKERS="pnpm-workspace.yaml turbo.json nx.json lerna.json go.work"
workspace=()
for m in $WORKSPACE_MARKERS; do [ -e "$dir/$m" ] && workspace+=("$m"); done
# Cargo workspace: Cargo.toml containing a [workspace] table.
if [ -f "$dir/Cargo.toml" ] && grep -q '^\[workspace\]' "$dir/Cargo.toml" 2>/dev/null; then
  workspace+=("Cargo.toml")
fi

children=()
for d in "$dir"/*/; do
  [ -d "${d}.git" ] && children+=("$(basename "$d")")
done

siblings=()
parent=$(dirname "$dir")
if [ "$parent" != "$dir" ]; then
  for d in "$parent"/*/; do
    d=${d%/}
    [ "$d" = "$dir" ] && continue
    [ -d "$d/.git" ] && siblings+=("$(basename "$d")")
  done
fi
```

and replace the `layout_signals` object in the heredoc with:

```bash
  "layout_signals": {
    "workspace_files": $(json_array ${workspace+"${workspace[@]}"}),
    "child_repos": $(json_array ${children+"${children[@]}"}),
    "sibling_repos": $(json_array ${siblings+"${siblings[@]}"})
  },
```

Note the `${arr+"${arr[@]}"}` form — under `set -u` a bare `"${arr[@]}"` on an empty array errors on older bash (macOS ships bash 3.2).

- [ ] **Step 8: Run the test and watch everything pass**

Run: `bash .claude/skills/install-ai-sdlc-kit/scripts/tests/test-detect-situation.sh`
Expected: PASS — all cases `ok`.

- [ ] **Step 9: Add the failing kit-state case**

Append to the test before the summary:

```bash
# --- Case E: kit present, committed, operator onboarded ----------------------------
tmp=$(mktemp -d); ( cd "$tmp" && git_q init && mkdir -p .ai-sdlc && \
  printf '{"kit":{"version":"1.2.0"},"layout":"embedded"}\n' > .ai-sdlc/kit.json && \
  : > USER.md && git_q add .ai-sdlc/kit.json && git_q commit -m init )
out=$("$DETECT" --dir "$tmp")
check E_state    "$(printf '%s' "$out" | jqp kit.state)"         '"present-committed"'
check E_version  "$(printf '%s' "$out" | jqp kit.manifest.kit.version)" '"1.2.0"'
check E_user_md  "$(printf '%s' "$out" | jqp user_md)"           "true"
rm -rf "$tmp"

# --- Case F: kit present but never committed ---------------------------------------
tmp=$(mktemp -d); ( cd "$tmp" && git_q init && mkdir -p .ai-sdlc && \
  printf '{"kit":{"version":"1.2.0"}}\n' > .ai-sdlc/kit.json )
out=$("$DETECT" --dir "$tmp")
check F_state "$(printf '%s' "$out" | jqp kit.state)" '"present-uncommitted"'
rm -rf "$tmp"
```

- [ ] **Step 10: Run the test**

Run: `bash .claude/skills/install-ai-sdlc-kit/scripts/tests/test-detect-situation.sh`
Expected: PASS — Cases E and F already work from the Step 3 implementation. If `E_version` fails, the `jqp` helper walked into the embedded manifest correctly but the manifest was emitted as a string: check that `$manifest` is interpolated **unquoted** in the heredoc.

- [ ] **Step 11: Wire both CI files**

In `.github/workflows/ci.yml`, change the skills step and add the new test:

```yaml
      - name: Validate Agent Skills (agentskills.io)
        run: |
          python3 template/scripts/validate-skills.py
          python3 template/scripts/validate-skills.py .claude/skills
      - name: Installer skill — situation-check tests
        run: bash .claude/skills/install-ai-sdlc-kit/scripts/tests/test-detect-situation.sh
```

Apply the equivalent two changes to `.gitlab-ci.yml` (it mirrors this gate; match its existing job/step style).

- [ ] **Step 12: Run both validators locally**

Run:
```bash
python3 template/scripts/validate-skills.py
python3 template/scripts/validate-skills.py .claude/skills
```
Expected: the first prints `ok` for every template skill; the second reports no `SKILL.md` found yet (Task 6 adds it) and exits 0.

- [ ] **Step 13: Commit**

```bash
git add .claude/skills/install-ai-sdlc-kit .github/workflows/ci.yml .gitlab-ci.yml
git commit -m "feat(installer): read-only situation-check script for the kit installer

Reports git state, kit/manifest state, onboarding state, hook state and the
four layout signals as JSON. Wires kit-root skill validation into CI, which
previously only scanned template/.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Merge engine — marked blocks and no-clobber copy

The one piece of logic every later task depends on. Lives in its own sourceable library so it can be tested in isolation, mirroring `template/scripts/session/lib.sh`.

**Files:**
- Create: `template/scripts/lib/kit-merge.sh`
- Create: `template/scripts/tests/test_kit_merge.sh`
- Modify: `template/scripts/bootstrap.sh` (source the library)

**Interfaces:**
- Consumes: nothing.
- Produces, all callable after `. scripts/lib/kit-merge.sh`:
  - `kit_begin_marker <path>` / `kit_end_marker <path>` → the marker strings for that file's comment style (HTML comments for `.md`/`.html`, `#` comments otherwise).
  - `kit_merge_block <target> <content_file>` → creates, updates-in-place, or appends a marked block. Echoes exactly one of `created|updated|appended`. Idempotent.
  - `kit_copy_merge <src_dir> <dst_dir>` → copies the tree without overwriting. Echoes one line per file: `created <rel>`, `identical <rel>`, or `collision <rel>`.

- [ ] **Step 1: Write the failing test**

Create `template/scripts/tests/test_kit_merge.sh`:

```bash
#!/usr/bin/env bash
# Functional test for kit-merge.sh (no framework). Exits non-zero on any failure.
set -uo pipefail
SRC_ROOT=$(cd "$(dirname "$0")/../.." && pwd)     # …/template
LIB="$SRC_ROOT/scripts/lib/kit-merge.sh"
fails=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got '$2' want '$3'"; fails=$((fails+1)); fi; }

# shellcheck source=/dev/null
. "$LIB"

tmp=$(mktemp -d)
printf 'kit line one\nkit line two\n' > "$tmp/block.txt"

# --- 1. target absent -> created, with markers -------------------------------------
check created "$(kit_merge_block "$tmp/NEW.md" "$tmp/block.txt")" "created"
check created_has_begin "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/NEW.md")" "1"
check created_has_body  "$(grep -c 'kit line one' "$tmp/NEW.md")" "1"

# --- 2. project-owned file -> appended, original content untouched ------------------
printf '# Acme API\n\nOur own readme.\n' > "$tmp/README.md"
before=$(head -3 "$tmp/README.md")
check appended "$(kit_merge_block "$tmp/README.md" "$tmp/block.txt")" "appended"
check appended_kept_original "$(head -3 "$tmp/README.md")" "$before"
check appended_one_block "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/README.md")" "1"

# --- 3. second run with new content -> updated in place, still ONE block ------------
printf 'kit line CHANGED\n' > "$tmp/block2.txt"
check updated "$(kit_merge_block "$tmp/README.md" "$tmp/block2.txt")" "updated"
check updated_one_block "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/README.md")" "1"
check updated_new_body  "$(grep -c 'kit line CHANGED' "$tmp/README.md")" "1"
check updated_old_gone  "$(grep -c 'kit line one' "$tmp/README.md")" "0"
check updated_kept_original "$(head -3 "$tmp/README.md")" "$before"

# --- 4. hash-comment file gets hash markers ----------------------------------------
printf 'node_modules/\n' > "$tmp/.gitignore"
kit_merge_block "$tmp/.gitignore" "$tmp/block.txt" >/dev/null
check hash_marker "$(grep -c '^# ai-sdlc-kit:begin$' "$tmp/.gitignore")" "1"
check hash_no_html "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/.gitignore")" "0"

# --- 5. kit_copy_merge: create missing, keep existing, report collisions ------------
mkdir -p "$tmp/src/docs" "$tmp/dst"
printf 'kit version\n'    > "$tmp/src/AGENTS.md"
printf 'kit doc\n'        > "$tmp/src/docs/guide.md"
printf 'kit identical\n'  > "$tmp/src/SAME.md"
printf 'project version\n' > "$tmp/dst/AGENTS.md"
printf 'kit identical\n'   > "$tmp/dst/SAME.md"
report=$(kit_copy_merge "$tmp/src" "$tmp/dst")
check copy_created   "$(printf '%s\n' "$report" | grep -c '^created docs/guide.md$')" "1"
check copy_collision "$(printf '%s\n' "$report" | grep -c '^collision AGENTS.md$')"   "1"
check copy_identical "$(printf '%s\n' "$report" | grep -c '^identical SAME.md$')"     "1"
check copy_untouched "$(cat "$tmp/dst/AGENTS.md")" "project version"

rm -rf "$tmp"
echo "---"
[ "$fails" -eq 0 ] && echo "all kit-merge tests passed" || echo "$fails test(s) failed"
exit "$fails"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `bash template/scripts/tests/test_kit_merge.sh`
Expected: FAIL — `kit-merge.sh: No such file or directory`.

- [ ] **Step 3: Write the library**

Create `template/scripts/lib/kit-merge.sh`:

```bash
#!/usr/bin/env bash
# kit-merge.sh — marker-based merge helpers for the AI-SDLC kit installer.
#
# The kit never overwrites a file a project already owns. It either creates the
# file, or maintains its own block between markers inside it, or reports a
# collision and leaves the file byte-identical. Source this file; do not run it.
#
#   kit_merge_block <target> <content_file>   -> created | updated | appended
#   kit_copy_merge  <src_dir> <dst_dir>       -> "created|identical|collision <rel>" lines

kit_begin_marker() {
  case "$1" in
    *.md|*.markdown|*.html) printf '<!-- ai-sdlc-kit:begin -->' ;;
    *) printf '# ai-sdlc-kit:begin' ;;
  esac
}

kit_end_marker() {
  case "$1" in
    *.md|*.markdown|*.html) printf '<!-- ai-sdlc-kit:end -->' ;;
    *) printf '# ai-sdlc-kit:end' ;;
  esac
}

# kit_merge_block <target> <content_file>
kit_merge_block() {
  local target=$1 content=$2
  local begin end tmp
  begin=$(kit_begin_marker "$target")
  end=$(kit_end_marker "$target")

  if [ ! -f "$target" ]; then
    mkdir -p "$(dirname "$target")"
    { printf '%s\n' "$begin"; cat "$content"; printf '%s\n' "$end"; } > "$target"
    echo created
    return 0
  fi

  if grep -qF -- "$begin" "$target"; then
    tmp=$(mktemp)
    awk -v b="$begin" -v e="$end" -v f="$content" '
      BEGIN { while ((getline line < f) > 0) blk = blk line "\n" }
      $0 == b { print b; printf "%s", blk; print e; skip = 1; next }
      $0 == e { skip = 0; next }
      !skip   { print }
    ' "$target" > "$tmp" && mv "$tmp" "$target"
    echo updated
    return 0
  fi

  { printf '\n%s\n' "$begin"; cat "$content"; printf '%s\n' "$end"; } >> "$target"
  echo appended
}

# kit_copy_merge <src_dir> <dst_dir>
kit_copy_merge() {
  local src=$1 dst=$2 rel abs_src abs_dst
  ( cd "$src" && find . -type f -print ) | sed 's|^\./||' | sort | while read -r rel; do
    abs_src="$src/$rel"; abs_dst="$dst/$rel"
    if [ ! -e "$abs_dst" ]; then
      mkdir -p "$(dirname "$abs_dst")"
      cp -p "$abs_src" "$abs_dst"
      echo "created $rel"
    elif cmp -s "$abs_src" "$abs_dst"; then
      echo "identical $rel"
    else
      echo "collision $rel"
    fi
  done
}
```

- [ ] **Step 4: Run the test**

Run: `bash template/scripts/tests/test_kit_merge.sh`
Expected: PASS — every case `ok`, `all kit-merge tests passed`.

- [ ] **Step 5: Source the library from `bootstrap.sh`**

In `template/scripts/bootstrap.sh`, immediately after the `TEMPLATE_ROOT=` line, add:

```bash
# shellcheck source=/dev/null
. "$TEMPLATE_ROOT/scripts/lib/kit-merge.sh"
```

- [ ] **Step 6: Verify bootstrap still runs unchanged**

Run:
```bash
tmp=$(mktemp -d)
template/scripts/bootstrap.sh --name "Smoke Test" --slug smoke --dir "$tmp/smoke" --desc "smoke" --ticket SMK
test -f "$tmp/smoke/AGENTS.md" && echo "BOOTSTRAP OK"
rm -rf "$tmp"
```
Expected: the usual bootstrap output, then `BOOTSTRAP OK`.

- [ ] **Step 7: Wire the test into both CI files**

In `.github/workflows/ci.yml`, add under the validator-unit-tests steps:

```yaml
      - name: Merge-engine unit tests
        run: bash template/scripts/tests/test_kit_merge.sh
```

Mirror it in `.gitlab-ci.yml`.

- [ ] **Step 8: Commit**

```bash
git add template/scripts/lib/kit-merge.sh template/scripts/tests/test_kit_merge.sh \
        template/scripts/bootstrap.sh .github/workflows/ci.yml .gitlab-ci.yml
git commit -m "feat(bootstrap): marker-based merge engine that never clobbers

kit_merge_block maintains one kit-owned block per file (create / update in
place / append) and kit_copy_merge copies a tree reporting created, identical
and collision per file. Sourced by bootstrap.sh.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Layouts, repos, flags and the manifest

Teaches `bootstrap.sh` where the kit sits, which repos take part, and how to record both.

**Files:**
- Modify: `template/scripts/bootstrap.sh`
- Modify: `template/AGENTS.md` (add the empty anchor block in §2 — see the note below)
- Create: `template/scripts/tests/test_bootstrap.sh`

> **Spec amendment.** The design listed only `bootstrap.sh`, the generated README and the manifest as template changes. Writing the repo table into `AGENTS.md` §2 needs a stable anchor, so `template/AGENTS.md` gains one empty marked block in §2 and nothing else. Recorded here rather than silently done.

**Interfaces:**
- Consumes: `kit_merge_block`, `kit_copy_merge` from Task 2.
- Produces:
  - `bootstrap.sh` flags `--layout <embedded|monorepo|sidecar|parent>` (default `embedded`), `--merge`, `--repos "<path>=<role>,…"`, `--tools "<id>,…"`, `--hooks <kit|repo|none>` (default `kit`), `--no-git`, `--non-interactive`, `--kit-version <v>`, `--kit-commit <sha>`.
  - `.ai-sdlc/kit.json` with exactly the keys: `kit.version`, `kit.commit`, `kit.source`, `kit.installed`, `layout`, `project.name`, `project.slug`, `repos[]` (`path`, `role`, `pointer`), `hooks`, `tools[]`.
  - `.ai-sdlc/install-report.md` — the created / appended / collision list from this run.

- [ ] **Step 1: Write the failing test**

Create `template/scripts/tests/test_bootstrap.sh`:

```bash
#!/usr/bin/env bash
# Functional test for bootstrap.sh (no framework). Exits non-zero on any failure.
set -uo pipefail
SRC_ROOT=$(cd "$(dirname "$0")/../.." && pwd)     # …/template
BOOT="$SRC_ROOT/scripts/bootstrap.sh"
fails=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got '$2' want '$3'"; fails=$((fails+1)); fi; }
jqp() { python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."):
    d = d[k] if isinstance(d, dict) else None
print(json.dumps(d))' "$1" "$2"; }

export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

# --- 1. fresh embedded install -----------------------------------------------------
tmp=$(mktemp -d)
"$BOOT" --name "Acme Wallet" --slug acme-wallet --dir "$tmp/acme" --desc "wallet" \
        --ticket ACME --layout embedded --kit-version 1.2.0 --kit-commit abc1234 \
        --non-interactive >/dev/null 2>&1
check fresh_agents   "$([ -f "$tmp/acme/AGENTS.md" ] && echo yes)" "yes"
check fresh_manifest "$([ -f "$tmp/acme/.ai-sdlc/kit.json" ] && echo yes)" "yes"
check fresh_layout   "$(jqp "$tmp/acme/.ai-sdlc/kit.json" layout)"        '"embedded"'
check fresh_version  "$(jqp "$tmp/acme/.ai-sdlc/kit.json" kit.version)"   '"1.2.0"'
check fresh_name     "$(jqp "$tmp/acme/.ai-sdlc/kit.json" project.name)"  '"Acme Wallet"'
check fresh_hooks    "$(jqp "$tmp/acme/.ai-sdlc/kit.json" hooks)"         '"kit"'
rm -rf "$tmp"

# --- 2. merge into a populated project ---------------------------------------------
tmp=$(mktemp -d); proj="$tmp/api"; mkdir -p "$proj/src"
printf '# Acme API\n\nOur own readme.\n' > "$proj/README.md"
printf 'dist/\n' > "$proj/.gitignore"
printf 'console.log(1)\n' > "$proj/src/index.js"
( cd "$proj" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Acme API" --slug acme-api --dir "$proj" --desc "api" --ticket ACME \
        --layout embedded --merge --non-interactive >/dev/null 2>&1
check merge_kept_readme "$(head -1 "$proj/README.md")" "# Acme API"
check merge_block_once  "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$proj/README.md")" "1"
check merge_kept_ignore "$(head -1 "$proj/.gitignore")" "dist/"
check merge_kept_src    "$(cat "$proj/src/index.js")" "console.log(1)"
check merge_added_kit   "$([ -f "$proj/AGENTS.md" ] && echo yes)" "yes"
check merge_report      "$([ -f "$proj/.ai-sdlc/install-report.md" ] && echo yes)" "yes"

# --- 3. idempotence: a second run changes nothing structurally ----------------------
sum_before=$(cat "$proj/README.md" | wc -l | tr -d ' ')
"$BOOT" --name "Acme API" --slug acme-api --dir "$proj" --desc "api" --ticket ACME \
        --layout embedded --merge --non-interactive >/dev/null 2>&1
check idem_block_once "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$proj/README.md")" "1"
check idem_same_lines "$(cat "$proj/README.md" | wc -l | tr -d ' ')" "$sum_before"
rm -rf "$tmp"

# --- 4. repos + layout are recorded ------------------------------------------------
tmp=$(mktemp -d)
"$BOOT" --name "Acme" --slug acme --dir "$tmp/sdlc" --desc "d" --ticket ACME \
        --layout sidecar --repos "../acme-api=backend,../acme-web=frontend" \
        --tools "claude,copilot" --non-interactive >/dev/null 2>&1
check repos_layout "$(jqp "$tmp/sdlc/.ai-sdlc/kit.json" layout)" '"sidecar"'
check repos_count  "$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))["repos"]))' "$tmp/sdlc/.ai-sdlc/kit.json")" "2"
check repos_role   "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["repos"][0]["role"])' "$tmp/sdlc/.ai-sdlc/kit.json")" "backend"
check repos_tools  "$(python3 -c 'import json,sys;print(",".join(json.load(open(sys.argv[1]))["tools"]))' "$tmp/sdlc/.ai-sdlc/kit.json")" "claude,copilot"
check agents_table "$(grep -c 'acme-api' "$tmp/sdlc/AGENTS.md")" "1"
rm -rf "$tmp"

# --- 5. --no-git and --hooks none ---------------------------------------------------
tmp=$(mktemp -d)
"$BOOT" --name "NoGit" --slug nogit --dir "$tmp/ng" --desc "d" --ticket NG \
        --no-git --hooks none --non-interactive >/dev/null 2>&1
check nogit_no_repo "$([ -d "$tmp/ng/.git" ] && echo yes || echo no)" "no"
check nogit_hooks   "$(jqp "$tmp/ng/.ai-sdlc/kit.json" hooks)" '"none"'
rm -rf "$tmp"

# --- 5b. every layout installs and is recorded -------------------------------------
for lay in embedded monorepo sidecar parent; do
  tmp=$(mktemp -d)
  "$BOOT" --name "L $lay" --slug "l-$lay" --dir "$tmp/k" --desc "d" --ticket L \
          --layout "$lay" --non-interactive >/dev/null 2>&1
  check "layout_${lay}_agents"   "$([ -f "$tmp/k/AGENTS.md" ] && echo yes)" "yes"
  check "layout_${lay}_manifest" "$(jqp "$tmp/k/.ai-sdlc/kit.json" layout)" "\"$lay\""
  rm -rf "$tmp"
done

# --- 6. --non-interactive with a missing required value fails loudly ----------------
tmp=$(mktemp -d)
"$BOOT" --slug x --dir "$tmp/x" --non-interactive >/dev/null 2>&1
check ni_exit "$?" "2"
rm -rf "$tmp"

echo "---"
[ "$fails" -eq 0 ] && echo "all bootstrap tests passed" || echo "$fails test(s) failed"
exit "$fails"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `bash template/scripts/tests/test_bootstrap.sh`
Expected: FAIL on `fresh_manifest`, `fresh_layout`, `fresh_version`, `fresh_name`, `fresh_hooks`, every merge check, and the repos checks — `bootstrap: unknown arg: --layout`.

- [ ] **Step 3: Add the new flags**

In `template/scripts/bootstrap.sh`, extend the defaults line and the argument loop:

```bash
name=""; slug=""; dir=""; desc="<ONE_LINE_DESCRIPTION>"; ticket="<TICKET>"; host="github"; force=0
layout="embedded"; merge=0; repos=""; tools="claude"; hooks="kit"; no_git=0; non_interactive=0
kit_version=""; kit_commit=""
kit_source="https://github.com/georgiandinca/ai-sdlc-bootstrap-kit"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --name)   name=${2:?}; shift 2 ;;
    --slug)   slug=${2:?}; shift 2 ;;
    --dir)    dir=${2:?}; shift 2 ;;
    --desc)   desc=${2:?}; shift 2 ;;
    --ticket) ticket=${2:?}; shift 2 ;;
    --host)   host=${2:?}; shift 2 ;;
    --force)  force=1; shift ;;
    --layout) layout=${2:?}; shift 2 ;;
    --merge)  merge=1; shift ;;
    --repos)  repos=${2:?}; shift 2 ;;
    --tools)  tools=${2:?}; shift 2 ;;
    --hooks)  hooks=${2:?}; shift 2 ;;
    --no-git) no_git=1; shift ;;
    --non-interactive) non_interactive=1; shift ;;
    --kit-version) kit_version=${2:?}; shift 2 ;;
    --kit-commit)  kit_commit=${2:?}; shift 2 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "bootstrap: unknown arg: $1" >&2; exit 2 ;;
  esac
done

case "$layout" in
  embedded|monorepo|sidecar|parent) ;;
  *) echo "bootstrap: --layout must be embedded|monorepo|sidecar|parent (got '$layout')" >&2; exit 2 ;;
esac
case "$hooks" in
  kit|repo|none) ;;
  *) echo "bootstrap: --hooks must be kit|repo|none (got '$hooks')" >&2; exit 2 ;;
esac
```

Update the header comment block to document every new flag (it doubles as `--help`).

- [ ] **Step 4: Allow merging into a non-empty target**

Replace the non-empty guard with one that respects `--merge`:

```bash
if [ -d "$dir" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ] && [ "$force" -ne 1 ] && [ "$merge" -ne 1 ]; then
  echo "bootstrap: target '$dir' exists and is not empty (use --merge to install alongside, or --force to overwrite)" >&2
  exit 1
fi
```

and replace the `tar | tar` copy with a mode switch:

```bash
if [ "$merge" -eq 1 ]; then
  staging=$(mktemp -d)
  ( cd "$TEMPLATE_ROOT" && \
    tar --exclude='.git' --exclude='node_modules' --exclude='.venv' \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='docs/knowledge/.index' \
        -cf - . ) | ( cd "$staging" && tar -xf - )
  mkdir -p "$dir/.ai-sdlc"
  {
    echo "# AI-SDLC kit install report"
    echo
    echo "Generated by \`bootstrap.sh --merge\` on $(date -u '+%Y-%m-%d %H:%M UTC')."
    echo
    kit_copy_merge "$staging" "$dir" | sed 's/^/- /'
  } > "$dir/.ai-sdlc/install-report.md"
  rm -rf "$staging"
else
  ( cd "$TEMPLATE_ROOT" && \
    tar --exclude='.git' --exclude='node_modules' --exclude='.venv' \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='docs/knowledge/.index' \
        -cf - . ) | ( cd "$dir" && tar -xf - )
fi
```

- [ ] **Step 5: Run the test — merge cases should now pass, manifest cases still fail**

Run: `bash template/scripts/tests/test_bootstrap.sh`
Expected: `merge_kept_readme`, `merge_kept_ignore`, `merge_kept_src`, `merge_added_kit`, `merge_report` pass; the manifest, repos and `--no-git` checks still fail.

- [ ] **Step 6: Write the manifest and the `AGENTS.md` repo table**

Add to `bootstrap.sh`, after the placeholder substitution and before the git section:

```bash
# --- kit version/commit: explicit flags win, else read the kit's own git metadata ---
KIT_ROOT="$(cd "$TEMPLATE_ROOT/.." && pwd)"
[ -n "$kit_version" ] || kit_version=$(git -C "$KIT_ROOT" describe --tags --always 2>/dev/null || echo "unknown")
[ -n "$kit_commit" ]  || kit_commit=$(git -C "$KIT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")

json_escape() { printf '%s' "${1-}" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }

# repos "path=role,path=role" -> JSON array; also a Markdown table for AGENTS.md §2
repos_json="[]"; repos_table=""
if [ -n "$repos" ]; then
  repos_json=""; old_ifs=$IFS; IFS=','
  for pair in $repos; do
    p=${pair%%=*}; r=${pair#*=}
    [ -n "$repos_json" ] && repos_json="$repos_json,"
    repos_json="$repos_json{\"path\":\"$(json_escape "$p")\",\"role\":\"$(json_escape "$r")\",\"pointer\":false}"
    repos_table="$repos_table| \`$p\` | $r |
"
  done
  IFS=$old_ifs
  repos_json="[$repos_json]"
fi

tools_json=""; old_ifs=$IFS; IFS=','
for t in $tools; do
  [ -n "$tools_json" ] && tools_json="$tools_json,"
  tools_json="$tools_json\"$(json_escape "$t")\""
done
IFS=$old_ifs
tools_json="[$tools_json]"

mkdir -p "$dir/.ai-sdlc"
cat > "$dir/.ai-sdlc/kit.json" <<JSON
{
  "kit": {
    "version": "$(json_escape "$kit_version")",
    "commit": "$(json_escape "$kit_commit")",
    "source": "$(json_escape "$kit_source")",
    "installed": "$(date -u '+%Y-%m-%d')"
  },
  "layout": "$(json_escape "$layout")",
  "project": { "name": "$(json_escape "$name")", "slug": "$(json_escape "$slug")" },
  "repos": $repos_json,
  "hooks": "$(json_escape "$hooks")",
  "tools": $tools_json
}
JSON

# AGENTS.md §2 — the repo table, inside the kit's marked block
if [ -f "$dir/AGENTS.md" ]; then
  block=$(mktemp)
  {
    echo "**Layout:** \`$layout\` — this kit governs the repositories below."
    if [ -n "$repos_table" ]; then
      echo
      echo "| Repository | Role |"
      echo "|---|---|"
      printf '%s' "$repos_table"
    fi
  } > "$block"
  kit_merge_block "$dir/AGENTS.md" "$block" >/dev/null
  rm -f "$block"
fi
```

- [ ] **Step 7: Add the anchor block to the template's `AGENTS.md`**

In `template/AGENTS.md` §2, directly after the blockquote about application code, add an empty block so the merge updates in place rather than appending at the end of the file:

```markdown
<!-- ai-sdlc-kit:begin -->
<!-- ai-sdlc-kit:end -->
```

- [ ] **Step 8: Honour `--no-git` and record `--hooks`**

Wrap the existing git section in a guard, and make the hook install respect the mode:

```bash
if [ "$no_git" -eq 0 ] && [ ! -d .git ]; then
  git init -q
  git add -A
  git commit -qm "chore: bootstrap $name from AI-SDLC Bootstrap Kit

Refs: ${ticket}-0" 2>/dev/null || git commit -qm "chore: bootstrap $name from AI-SDLC Bootstrap Kit"
  echo "[bootstrap] initialised git repo with an initial commit."
fi

if [ "$hooks" = "kit" ] && command -v pre-commit >/dev/null 2>&1; then
  pre-commit install >/dev/null 2>&1 || true
  echo "[bootstrap] installed pre-commit hooks."
elif [ "$hooks" = "none" ]; then
  echo "[bootstrap] hooks skipped (--hooks none)."
fi
```

(`--hooks repo` is implemented in Task 5; for now it behaves like `none` and prints `[bootstrap] --hooks repo handled separately`.)

- [ ] **Step 9: Require the mandatory values under `--non-interactive`**

Replace the two existing `required` checks with:

```bash
missing=""
[ -n "$name" ] || missing="$missing --name"
[ -n "$dir" ]  || missing="$missing --dir"
if [ -n "$missing" ]; then
  echo "bootstrap: missing required flag(s):$missing" >&2
  exit 2
fi
```

- [ ] **Step 10: Run the test**

Run: `bash template/scripts/tests/test_bootstrap.sh`
Expected: PASS — every case `ok`, `all bootstrap tests passed`.

- [ ] **Step 11: Wire the test into both CI files**

`.github/workflows/ci.yml`:

```yaml
      - name: Bootstrap unit tests
        run: bash template/scripts/tests/test_bootstrap.sh
```

Mirror it in `.gitlab-ci.yml`.

- [ ] **Step 12: Commit**

```bash
git add template/scripts/bootstrap.sh template/AGENTS.md \
        template/scripts/tests/test_bootstrap.sh .github/workflows/ci.yml .gitlab-ci.yml
git commit -m "feat(bootstrap): layouts, repos, merge install and a committed manifest

Adds --layout/--merge/--repos/--tools/--hooks/--no-git/--non-interactive,
writes .ai-sdlc/kit.json and an install report, and fills the AGENTS.md
section 2 repo table inside a kit-owned block.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Pointers and the generated project README

**Research finding that narrows this task** (verified against official docs, 2026-09-18): `AGENTS.md` is read natively, with no configuration, by OpenAI Codex (CLI + cloud), Cursor, Windsurf/Cascade, Google Antigravity and GitHub Copilot on github.com. Those tools need **no pointer file** — the kit's `AGENTS.md` already reaches them. Only two need anything:

| Tool id | What it needs | Why |
|---|---|---|
| `claude` | `CLAUDE.md` containing `@AGENTS.md` | Claude Code reads `CLAUDE.md`, not `AGENTS.md` (already shipped in the template; only code repos need one written) |
| `gemini` | `.gemini/settings.json` → `{"context":{"fileName":["AGENTS.md","GEMINI.md"]}}` | Gemini CLI defaults to `GEMINI.md` only |
| `copilot` | *optional* `.github/copilot-instructions.md` pointer | Belt-and-braces: VS Code gates `AGENTS.md` behind `chat.useAgentsMdFile`, whose default the docs do not state |

Every other tool id is accepted and recorded in the manifest but writes nothing, and the installer says so rather than silently doing nothing.

**Files:**
- Create: `template/scripts/lib/kit-pointers.sh`
- Create: `template/scripts/tests/test_kit_pointers.sh`
- Modify: `template/scripts/bootstrap.sh`

**Interfaces:**
- Consumes: `kit_merge_block` (Task 2); `$layout`, `$repos`, `$tools`, `$name`, `$slug`, `$kit_version`, `$kit_source` (Task 3).
- Produces, after `. scripts/lib/kit-pointers.sh`:
  - `kit_write_tool_pointers <dir> <tools_csv>` → one line per tool: `pointer <tool> <action>` where action is `created|updated|appended|none`.
  - `kit_write_repo_pointer <repo_dir> <rel_kit_path> <kit_url>` → writes `AGENTS.md` + `CLAUDE.md` pointer blocks in a code repo; echoes `repo-pointer <dir> <action>`.
  - `kit_readme_block <name> <layout> <repos_table> <kit_version> <kit_source>` → prints the project-specific README block to stdout.

- [ ] **Step 1: Write the failing test**

Create `template/scripts/tests/test_kit_pointers.sh`:

```bash
#!/usr/bin/env bash
# Functional test for kit-pointers.sh (no framework). Exits non-zero on any failure.
set -uo pipefail
SRC_ROOT=$(cd "$(dirname "$0")/../.." && pwd)     # …/template
fails=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got '$2' want '$3'"; fails=$((fails+1)); fi; }
# shellcheck source=/dev/null
. "$SRC_ROOT/scripts/lib/kit-merge.sh"
# shellcheck source=/dev/null
. "$SRC_ROOT/scripts/lib/kit-pointers.sh"

# --- 1. claude pointer is created when absent --------------------------------------
tmp=$(mktemp -d)
kit_write_tool_pointers "$tmp" "claude" >/dev/null
check claude_created "$(grep -c '@AGENTS.md' "$tmp/CLAUDE.md")" "1"
rm -rf "$tmp"

# --- 2. existing CLAUDE.md keeps its content, gains one block ----------------------
tmp=$(mktemp -d); printf '# CLAUDE.md\n\nProject notes.\n' > "$tmp/CLAUDE.md"
kit_write_tool_pointers "$tmp" "claude" >/dev/null
check claude_kept  "$(head -1 "$tmp/CLAUDE.md")" "# CLAUDE.md"
check claude_block "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/CLAUDE.md")" "1"
kit_write_tool_pointers "$tmp" "claude" >/dev/null     # idempotent
check claude_block_once "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/CLAUDE.md")" "1"
rm -rf "$tmp"

# --- 3. gemini settings: created, then merged without losing existing keys ---------
tmp=$(mktemp -d)
kit_write_tool_pointers "$tmp" "gemini" >/dev/null
check gemini_created "$(python3 -c 'import json,sys;print("AGENTS.md" in json.load(open(sys.argv[1]))["context"]["fileName"])' "$tmp/.gemini/settings.json")" "True"
mkdir -p "$tmp/g2/.gemini"; printf '{"theme":"dark","context":{"fileName":["GEMINI.md"]}}\n' > "$tmp/g2/.gemini/settings.json"
kit_write_tool_pointers "$tmp/g2" "gemini" >/dev/null
check gemini_kept_theme "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["theme"])' "$tmp/g2/.gemini/settings.json")" "dark"
check gemini_added "$(python3 -c 'import json,sys;print(",".join(json.load(open(sys.argv[1]))["context"]["fileName"]))' "$tmp/g2/.gemini/settings.json")" "AGENTS.md,GEMINI.md"
kit_write_tool_pointers "$tmp/g2" "gemini" >/dev/null  # idempotent, no duplicate entry
check gemini_no_dupe "$(python3 -c 'import json,sys;f=json.load(open(sys.argv[1]))["context"]["fileName"];print(len(f))' "$tmp/g2/.gemini/settings.json")" "2"
rm -rf "$tmp"

# --- 4. a tool that needs nothing reports "none" ------------------------------------
tmp=$(mktemp -d)
check cursor_none "$(kit_write_tool_pointers "$tmp" "cursor")" "pointer cursor none"
check cursor_nofiles "$(ls -A "$tmp" | wc -l | tr -d ' ')" "0"
rm -rf "$tmp"

# --- 5. code-repo pointer names both the path and the clone URL --------------------
tmp=$(mktemp -d); mkdir -p "$tmp/acme-api"
kit_write_repo_pointer "$tmp/acme-api" "../acme-sdlc" "https://example.com/acme-sdlc.git" >/dev/null
check repo_agents "$(grep -c '\.\./acme-sdlc/AGENTS.md' "$tmp/acme-api/AGENTS.md")" "1"
check repo_url    "$(grep -c 'example.com/acme-sdlc.git' "$tmp/acme-api/AGENTS.md")" "1"
check repo_claude "$(grep -c '@\.\./acme-sdlc/AGENTS.md' "$tmp/acme-api/CLAUDE.md")" "1"
rm -rf "$tmp"

# --- 6. README block carries the project's own facts -------------------------------
block=$(kit_readme_block "Acme Wallet" "sidecar" "| \`../acme-api\` | backend |" "1.2.0" "https://example.com/kit")
check readme_name   "$(printf '%s' "$block" | grep -c 'Acme Wallet')" "1"
check readme_layout "$(printf '%s' "$block" | grep -c 'sidecar')" "1"
check readme_repo   "$(printf '%s' "$block" | grep -c 'acme-api')" "1"
check readme_start  "$(printf '%s' "$block" | grep -c 'ONBOARDING.md')" "1"

echo "---"
[ "$fails" -eq 0 ] && echo "all kit-pointers tests passed" || echo "$fails test(s) failed"
exit "$fails"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `bash template/scripts/tests/test_kit_pointers.sh`
Expected: FAIL — `kit-pointers.sh: No such file or directory`.

- [ ] **Step 3: Write the library**

Create `template/scripts/lib/kit-pointers.sh`:

```bash
#!/usr/bin/env bash
# kit-pointers.sh — write per-tool and per-repo pointers to the canonical brief.
#
# AGENTS.md is canonical and is read natively by Codex, Cursor, Windsurf,
# Antigravity and Copilot on github.com — those tools need no pointer at all.
# Only Claude Code (reads CLAUDE.md) and Gemini CLI (defaults to GEMINI.md)
# need anything written. Source this file; do not run it. Requires kit-merge.sh.

# kit_write_tool_pointers <dir> <tools_csv>
kit_write_tool_pointers() {
  local dir=$1 tools=$2 t block action old_ifs
  old_ifs=$IFS; IFS=','
  for t in $tools; do
    IFS=$old_ifs
    case "$t" in
      claude)
        block=$(mktemp)
        {
          echo "@AGENTS.md"
          echo
          echo "\`AGENTS.md\` is the canonical brief for this project. This file only points at it."
        } > "$block"
        action=$(kit_merge_block "$dir/CLAUDE.md" "$block")
        rm -f "$block"
        echo "pointer claude $action"
        ;;
      gemini)
        mkdir -p "$dir/.gemini"
        python3 - "$dir/.gemini/settings.json" <<'PY'
import json, os, sys
path = sys.argv[1]
data = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        data = {}
ctx = data.setdefault("context", {})
names = ctx.get("fileName")
if isinstance(names, str):
    names = [names]
elif not isinstance(names, list):
    names = []
if "AGENTS.md" not in names:
    names.insert(0, "AGENTS.md")
if "GEMINI.md" not in names:
    names.append("GEMINI.md")
ctx["fileName"] = names
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
        echo "pointer gemini updated"
        ;;
      copilot)
        block=$(mktemp)
        {
          echo "Read [\`AGENTS.md\`](../AGENTS.md) at the repository root first — it is the canonical"
          echo "brief for this project. These instructions add nothing of their own."
        } > "$block"
        action=$(kit_merge_block "$dir/.github/copilot-instructions.md" "$block")
        rm -f "$block"
        echo "pointer copilot $action"
        ;;
      *)
        # Codex, Cursor, Windsurf, Antigravity: AGENTS.md is read natively.
        echo "pointer $t none"
        ;;
    esac
    old_ifs=$IFS; IFS=','
  done
  IFS=$old_ifs
}

# kit_write_repo_pointer <repo_dir> <rel_kit_path> <kit_url>
kit_write_repo_pointer() {
  local repo=$1 rel=$2 url=$3 block action
  block=$(mktemp)
  {
    echo "**This repository is governed by the AI-SDLC kit at \`$rel\`.**"
    echo
    echo "Read \`$rel/AGENTS.md\` first — it is the canonical brief (mission, constraints,"
    echo "trust tiers, MCP posture, seats). This file adds no rules of its own."
    echo
    echo "If \`$rel\` is not present, clone the kit beside this repository:"
    echo
    echo '```bash'
    echo "git clone $url $rel"
    echo '```'
  } > "$block"
  action=$(kit_merge_block "$repo/AGENTS.md" "$block")
  rm -f "$block"

  block=$(mktemp)
  {
    echo "@$rel/AGENTS.md"
    echo
    echo "The canonical brief lives in the AI-SDLC kit at \`$rel\`. See \`AGENTS.md\` in this"
    echo "repository for what to do when that path is missing."
  } > "$block"
  kit_merge_block "$repo/CLAUDE.md" "$block" >/dev/null
  rm -f "$block"
  echo "repo-pointer $repo $action"
}

# kit_readme_block <name> <layout> <repos_table> <kit_version> <kit_source>
kit_readme_block() {
  local name=$1 layout=$2 repos_table=$3 version=$4 source=$5
  echo "## $name — how we work with AI here"
  echo
  echo "This project is governed by the **AI-SDLC Bootstrap Kit** (\`$version\`, from $source),"
  echo "installed in the **\`$layout\`** layout."
  echo
  if [ -n "$repos_table" ]; then
    echo "| Repository | Role |"
    echo "|---|---|"
    printf '%s\n' "$repos_table"
    echo
  fi
  echo "### Start here"
  echo
  echo "1. Open your AI agent in this folder. It reads \`AGENTS.md\` — the canonical brief."
  echo "2. On your first run it follows \`ONBOARDING.md\`, which installs the tooling and"
  echo "   creates your personal \`USER.md\` (git-ignored). Onboarding runs once per person."
  echo "3. After that, \`USER.md\` is read each session and the brief governs the work."
  echo
  echo "### Day to day"
  echo
  echo "| Where | What |"
  echo "|---|---|"
  echo "| \`AGENTS.md\` | The brief every AI tool reads — mission, constraints, seats, MCP posture |"
  echo "| \`WORKING-AGREEMENT.md\` | How the team organises information, and the rules CI enforces |"
  echo "| \`.claude/skills/\` | Role playbooks — invoke your seat's skill to work in it |"
  echo "| \`docs/\` | The project's knowledge tree; \`FOLDER-INDEX.md\` says what goes where |"
  echo "| \`.ai-sdlc/kit.json\` | What was installed, in which layout, and at which version |"
}
```

- [ ] **Step 4: Run the test**

Run: `bash template/scripts/tests/test_kit_pointers.sh`
Expected: PASS — every case `ok`, `all kit-pointers tests passed`.

- [ ] **Step 5: Call the library from `bootstrap.sh`**

Source it next to the merge library:

```bash
# shellcheck source=/dev/null
. "$TEMPLATE_ROOT/scripts/lib/kit-pointers.sh"
```

and, after the manifest is written (Task 3, Step 6), add:

```bash
# --- README block with this project's own facts ------------------------------------
block=$(mktemp)
kit_readme_block "$name" "$layout" "$repos_table" "$kit_version" "$kit_source" > "$block"
kit_merge_block "$dir/README.md" "$block" >/dev/null
rm -f "$block"

# --- tool pointers -------------------------------------------------------------------
kit_write_tool_pointers "$dir" "$tools" | sed 's/^/[bootstrap] /'

# --- code-repo pointers (sidecar / parent layouts) ----------------------------------
if [ -n "$repos" ] && { [ "$layout" = "sidecar" ] || [ "$layout" = "parent" ]; }; then
  kit_rel=$(basename "$dir")
  old_ifs=$IFS; IFS=','
  for pair in $repos; do
    IFS=$old_ifs
    p=${pair%%=*}
    target="$dir/$p"
    [ -d "$target" ] || target="$p"
    if [ -d "$target" ]; then
      case "$layout" in
        sidecar) rel_to_kit="../$kit_rel" ;;
        parent)  rel_to_kit=".." ;;
      esac
      kit_write_repo_pointer "$target" "$rel_to_kit" "$kit_source" | sed 's/^/[bootstrap] /'
    else
      echo "[bootstrap] repo not found on disk, pointer skipped: $p"
    fi
    old_ifs=$IFS; IFS=','
  done
  IFS=$old_ifs
fi
```

- [ ] **Step 6: Add the bootstrap-level assertions**

Append to `template/scripts/tests/test_bootstrap.sh`, before its summary:

```bash
# --- 7. README block and pointers land in a real install ---------------------------
tmp=$(mktemp -d)
"$BOOT" --name "Acme Wallet" --slug acme-wallet --dir "$tmp/acme" --desc "d" --ticket ACME \
        --layout embedded --tools "claude,gemini" --non-interactive >/dev/null 2>&1
check readme_block  "$(grep -c 'how we work with AI here' "$tmp/acme/README.md")" "1"
check readme_layout "$(grep -c 'embedded' "$tmp/acme/README.md")" "1"
check claude_ptr    "$(grep -c '@AGENTS.md' "$tmp/acme/CLAUDE.md")" "1"
check gemini_ptr    "$([ -f "$tmp/acme/.gemini/settings.json" ] && echo yes)" "yes"
rm -rf "$tmp"
```

- [ ] **Step 7: Run both test files**

Run:
```bash
bash template/scripts/tests/test_kit_pointers.sh
bash template/scripts/tests/test_bootstrap.sh
```
Expected: both PASS.

- [ ] **Step 8: Wire the new test into both CI files**

`.github/workflows/ci.yml`:

```yaml
      - name: Pointer-writer unit tests
        run: bash template/scripts/tests/test_kit_pointers.sh
```

Mirror it in `.gitlab-ci.yml`.

- [ ] **Step 9: Commit**

```bash
git add template/scripts/lib/kit-pointers.sh template/scripts/tests/test_kit_pointers.sh \
        template/scripts/tests/test_bootstrap.sh template/scripts/bootstrap.sh \
        .github/workflows/ci.yml .gitlab-ci.yml
git commit -m "feat(bootstrap): project README block and per-tool/per-repo pointers

Writes a README section carrying the project's own layout, repos and start
path, a CLAUDE.md pointer, a Gemini settings entry, an optional Copilot
pointer, and pointers into code repos for the sidecar/parent layouts. Tools
that read AGENTS.md natively get nothing and say so.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Hook modes — `kit`, `repo`, `none`

`kit` and `none` already work from Task 3. This task implements `repo`: fold the kit's local hooks into a code repo's **existing** `.pre-commit-config.yaml`, with the script paths rewritten to reach the kit.

**Files:**
- Create: `template/scripts/merge-precommit.py`
- Create: `template/scripts/tests/test_merge_precommit.py`
- Modify: `template/scripts/bootstrap.sh`

**Interfaces:**
- Consumes: `$hooks`, `$dir`, `$layout` (Task 3).
- Produces:
  - `merge-precommit.py <target_config> <source_config> [--prefix <rel>] [--dry-run] [--backup <path>]` → exit 0 on success, 2 on a target that cannot be parsed. Prints one line per hook: `added <id>` / `present <id>`.
  - `bootstrap.sh --hooks-target <dir>` — required when `--hooks repo` is used.

> **Known limitation, stated in the install report and in `SKILL.md`:** PyYAML round-trips lose comments and formatting in the target file. The original is therefore copied to `.ai-sdlc/pre-commit-config.backup.yaml` before writing, and the report names that backup. `--dry-run` prints what would change without touching anything.

- [ ] **Step 1: Write the failing test**

Create `template/scripts/tests/test_merge_precommit.py`:

```python
#!/usr/bin/env python3
"""Unit tests for merge-precommit.py (hooks mode `repo`)."""
import importlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
merge = importlib.import_module("merge-precommit")

import yaml

SOURCE = """\
default_install_hook_types: [pre-commit, commit-msg]
repos:
  - repo: local
    hooks:
      - id: validate-skills
        name: Validate SKILL.md
        entry: python scripts/validate-skills.py
        language: python
        files: (^|/)SKILL\\.md$
      - id: commit-msg-ticket
        name: Commit message references an issue key
        entry: python scripts/git/commit_msg_ticket.py --mode warn
        language: python
        stages: [commit-msg]
"""

TARGET = """\
# our own hooks
repos:
  - repo: https://github.com/psf/black
    rev: 24.1.0
    hooks:
      - id: black
"""


class TestMergePreCommit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.src = self.d / "source.yaml"
        self.dst = self.d / "target.yaml"
        self.src.write_text(SOURCE, encoding="utf-8")
        self.dst.write_text(TARGET, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def load(self):
        return yaml.safe_load(self.dst.read_text(encoding="utf-8"))

    def hook_ids(self):
        return [h["id"] for r in self.load()["repos"] for h in r["hooks"]]

    def test_adds_kit_hooks_and_keeps_existing(self):
        merge.merge(self.dst, self.src, prefix="../acme-sdlc")
        ids = self.hook_ids()
        self.assertIn("black", ids)
        self.assertIn("validate-skills", ids)
        self.assertIn("commit-msg-ticket", ids)

    def test_rewrites_entry_paths_with_prefix(self):
        merge.merge(self.dst, self.src, prefix="../acme-sdlc")
        entries = [h.get("entry", "") for r in self.load()["repos"] for h in r["hooks"]]
        self.assertIn("python ../acme-sdlc/scripts/validate-skills.py", entries)

    def test_is_idempotent(self):
        merge.merge(self.dst, self.src, prefix="../acme-sdlc")
        first = self.hook_ids()
        merge.merge(self.dst, self.src, prefix="../acme-sdlc")
        self.assertEqual(first, self.hook_ids())

    def test_preserves_install_hook_types(self):
        merge.merge(self.dst, self.src, prefix="../acme-sdlc")
        self.assertEqual(
            self.load().get("default_install_hook_types"), ["pre-commit", "commit-msg"]
        )

    def test_dry_run_changes_nothing(self):
        before = self.dst.read_text(encoding="utf-8")
        merge.merge(self.dst, self.src, prefix="../acme-sdlc", dry_run=True)
        self.assertEqual(before, self.dst.read_text(encoding="utf-8"))

    def test_writes_backup(self):
        backup = self.d / "backup.yaml"
        merge.merge(self.dst, self.src, prefix="../acme-sdlc", backup=backup)
        self.assertEqual(backup.read_text(encoding="utf-8"), TARGET)

    def test_unparseable_target_exits_2(self):
        self.dst.write_text("repos: [unclosed\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(Path(merge.__file__)), str(self.dst), str(self.src)],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python3 template/scripts/tests/test_merge_precommit.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'merge-precommit'`.

- [ ] **Step 3: Write the merger**

Create `template/scripts/merge-precommit.py`:

```python
#!/usr/bin/env python3
"""Fold the kit's local pre-commit hooks into a project's existing config.

Used by `bootstrap.sh --hooks repo`, when the governance hooks must run in a code
repository that already has its own `.pre-commit-config.yaml`.

Existing hooks are never removed and never reordered. A kit hook whose `id` is
already present is left alone, so re-running changes nothing. Script paths in
`entry` are rewritten with `--prefix` so they resolve from the target repo to the
kit. NOTE: PyYAML does not preserve comments — pass `--backup` (bootstrap.sh does)
so the original file is recoverable.

Usage:
  merge-precommit.py <target_config> <source_config> [--prefix <rel>]
                     [--dry-run] [--backup <path>]

Exit code 0 on success, 2 if the target file cannot be parsed.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    sys.exit("error: PyYAML is required (pip install pyyaml)")


def _existing_ids(doc: dict) -> set[str]:
    ids: set[str] = set()
    for repo in doc.get("repos") or []:
        for hook in repo.get("hooks") or []:
            if isinstance(hook, dict) and "id" in hook:
                ids.add(hook["id"])
    return ids


def _reprefix(entry: str, prefix: str) -> str:
    """Rewrite `python scripts/x.py …` to `python <prefix>/scripts/x.py …`."""
    if not prefix:
        return entry
    parts = entry.split()
    return " ".join(
        f"{prefix}/{p}" if p.startswith("scripts/") else p for p in parts
    )


def merge(target: Path, source: Path, prefix: str = "", dry_run: bool = False,
          backup: Path | None = None) -> list[str]:
    """Merge source's local hooks into target. Returns the log lines."""
    try:
        target_doc = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"target is not valid YAML: {exc}") from exc
    if not isinstance(target_doc, dict):
        raise ValueError("target must be a YAML mapping")

    source_doc = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    present = _existing_ids(target_doc)
    log: list[str] = []
    new_hooks = []

    for repo in source_doc.get("repos") or []:
        if repo.get("repo") != "local":
            continue
        for hook in repo.get("hooks") or []:
            hid = hook.get("id")
            if hid in present:
                log.append(f"present {hid}")
                continue
            hook = dict(hook)
            if "entry" in hook:
                hook["entry"] = _reprefix(hook["entry"], prefix)
            new_hooks.append(hook)
            log.append(f"added {hid}")

    if not new_hooks:
        return log

    if dry_run:
        return log

    if backup is not None:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target, backup)

    repos = target_doc.setdefault("repos", [])
    local = next((r for r in repos if r.get("repo") == "local"), None)
    if local is None:
        local = {"repo": "local", "hooks": []}
        repos.append(local)
    local.setdefault("hooks", []).extend(new_hooks)

    src_types = source_doc.get("default_install_hook_types")
    if src_types and "default_install_hook_types" not in target_doc:
        target_doc["default_install_hook_types"] = src_types

    target.write_text(
        yaml.safe_dump(target_doc, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return log


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target")
    ap.add_argument("source")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup")
    args = ap.parse_args()

    try:
        log = merge(
            Path(args.target), Path(args.source), args.prefix, args.dry_run,
            Path(args.backup) if args.backup else None,
        )
    except (ValueError, OSError) as exc:
        print(f"merge-precommit: {exc}", file=sys.stderr)
        return 2
    for line in log:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test**

Run: `python3 template/scripts/tests/test_merge_precommit.py`
Expected: PASS — 7 tests, `OK`.

- [ ] **Step 5: Call it from `bootstrap.sh`**

Add `--hooks-target` to the flag block (default empty) and replace the `--hooks repo` placeholder from Task 3, Step 8:

```bash
elif [ "$hooks" = "repo" ]; then
  if [ -z "$hooks_target" ]; then
    echo "bootstrap: --hooks repo requires --hooks-target <dir>" >&2; exit 2
  fi
  if [ ! -f "$hooks_target/.pre-commit-config.yaml" ]; then
    echo "[bootstrap] no .pre-commit-config.yaml in $hooks_target — copying the kit's."
    cp "$dir/.pre-commit-config.yaml" "$hooks_target/.pre-commit-config.yaml"
  else
    mkdir -p "$dir/.ai-sdlc"
    python3 "$dir/scripts/merge-precommit.py" \
      "$hooks_target/.pre-commit-config.yaml" "$dir/.pre-commit-config.yaml" \
      --prefix "$(basename "$dir")" \
      --backup "$dir/.ai-sdlc/pre-commit-config.backup.yaml" | sed 's/^/[bootstrap] hook /'
    echo "[bootstrap] original config backed up to .ai-sdlc/pre-commit-config.backup.yaml (comments are not preserved by the merge)."
  fi
  if command -v pre-commit >/dev/null 2>&1; then
    ( cd "$hooks_target" && pre-commit install --hook-type pre-commit --hook-type commit-msg >/dev/null 2>&1 ) || true
    echo "[bootstrap] installed pre-commit hooks in $hooks_target (both stages)."
  fi
fi
```

The `--prefix` above assumes the code repo sits beside the kit (`sidecar`). For `parent`, pass `--prefix ".."`; compute it from `$layout` exactly as Task 4, Step 5 computes `rel_to_kit`, and reuse that variable.

- [ ] **Step 6: Add the bootstrap-level assertion**

Append to `template/scripts/tests/test_bootstrap.sh`, before its summary:

```bash
# --- 8. --hooks repo folds into an existing config without losing it ---------------
tmp=$(mktemp -d); mkdir -p "$tmp/acme-api"
printf 'repos:\n  - repo: local\n    hooks:\n      - id: mine\n        name: mine\n        entry: echo\n        language: system\n' \
  > "$tmp/acme-api/.pre-commit-config.yaml"
"$BOOT" --name "Acme" --slug acme --dir "$tmp/acme-sdlc" --desc "d" --ticket ACME \
        --layout sidecar --hooks repo --hooks-target "$tmp/acme-api" \
        --non-interactive >/dev/null 2>&1
check hooks_kept_mine  "$(grep -c 'id: mine' "$tmp/acme-api/.pre-commit-config.yaml")" "1"
check hooks_added_kit  "$(grep -c 'validate-skills' "$tmp/acme-api/.pre-commit-config.yaml")" "1"
check hooks_backup     "$([ -f "$tmp/acme-sdlc/.ai-sdlc/pre-commit-config.backup.yaml" ] && echo yes)" "yes"
check hooks_manifest   "$(jqp "$tmp/acme-sdlc/.ai-sdlc/kit.json" hooks)" '"repo"'
rm -rf "$tmp"
```

- [ ] **Step 7: Run both test files**

Run:
```bash
python3 template/scripts/tests/test_merge_precommit.py
bash template/scripts/tests/test_bootstrap.sh
```
Expected: both PASS.

- [ ] **Step 8: Wire the test into both CI files**

`.github/workflows/ci.yml`:

```yaml
      - name: Pre-commit merger unit tests
        run: python3 template/scripts/tests/test_merge_precommit.py
```

Mirror it in `.gitlab-ci.yml`.

- [ ] **Step 9: Commit**

```bash
git add template/scripts/merge-precommit.py template/scripts/tests/test_merge_precommit.py \
        template/scripts/tests/test_bootstrap.sh template/scripts/bootstrap.sh \
        .github/workflows/ci.yml .gitlab-ci.yml
git commit -m "feat(bootstrap): --hooks repo folds governance hooks into an existing config

Adds merge-precommit.py: idempotent by hook id, rewrites script paths to reach
the kit, keeps the project's own hooks, backs the original up first.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: The skill itself

The decision layer. Short, and it delegates: install work goes to `bootstrap.sh`, onboarding goes to the project's `ONBOARDING.md`.

**Files:**
- Create: `.claude/skills/install-ai-sdlc-kit/SKILL.md`
- Create: `.claude/skills/install-ai-sdlc-kit/references/layouts.md`
- Create: `.claude/skills/install-ai-sdlc-kit/references/pointer-blocks.md`

**Interfaces:**
- Consumes: `scripts/detect-situation.sh` (Task 1); every `bootstrap.sh` flag from Tasks 3–5.
- Produces: the skill invoked as `/ai-sdlc-kit:install-ai-sdlc-kit` once the plugin from Task 7 is installed, and auto-discovered as a project skill when the kit repo itself is open.

- [ ] **Step 1: Write `SKILL.md`**

Create `.claude/skills/install-ai-sdlc-kit/SKILL.md`:

````markdown
---
name: install-ai-sdlc-kit
description: Use when someone wants to install, set up, bootstrap or adopt the AI-SDLC Bootstrap Kit in a project, or when a project already has the kit and a person needs onboarding. Triggers on "install the kit", "set up AI-SDLC", "bootstrap this repo", "add AI governance to this project", "onboard me", and on finding AGENTS.md with no USER.md. Works out which of three situations applies — no kit, kit present but this person not onboarded, or fully set up — and does only what that situation needs. Not for authoring new skills (use skill-creator) and not for updating an installed kit to a newer version.
metadata:
  status: "approved"
  classification: "internal"
  ai-trust: "working"
  owner: "Architect"
---

# install-ai-sdlc-kit

Installs the [AI-SDLC Bootstrap Kit](https://github.com/georgiandinca/ai-sdlc-bootstrap-kit) into any project, in the layout that project needs, and hands over to the project's own onboarding.

## Step 1 — Check the situation first. Always.

Run the situation check before asking the user anything:

```bash
"$CLAUDE_PLUGIN_ROOT/.claude/skills/install-ai-sdlc-kit/scripts/detect-situation.sh"
```

(When the kit repo itself is open, the path is `.claude/skills/install-ai-sdlc-kit/scripts/detect-situation.sh`.)

It prints one JSON object and writes nothing. Read it, then take exactly one path:

| `kit.state` | `user_md` | Path |
|---|---|---|
| `absent` | — | **Setup** (Step 2), then **Onboarding** (Step 3) |
| `present-uncommitted` | — | Say the kit is installed but not committed; offer to commit it; then re-run this check |
| `present-committed` | `false` | **Onboarding** only (Step 3) |
| `present-committed` | `true` | **Status** (Step 4) |

Never install when `kit.state` is not `absent`. Never re-run onboarding when `USER.md` exists.

## Step 2 — Setup

Ask these, in this order, proposing the detected answer first so the common case is one confirmation:

1. **Layout** — propose from `layout_signals`, in this order: `embedded` (kit inside this repo) → `monorepo` (kit at the workspace root; `workspace_files` non-empty) → `sidecar` (kit beside the code repos; `sibling_repos` non-empty) → `parent` (kit above the code repos; `child_repos` non-empty). `references/layouts.md` describes what each one writes where, and their trade-offs.
2. **Project facts** — name, one-line description, ticket prefix, host (`github`/`gitlab`).
3. **Repos and roles** — for `monorepo`/`sidecar`/`parent`, e.g. `../acme-api=backend`.
4. **Hooks** — `kit` (governance hooks on the kit's own repo), `repo` (fold them into a code repo's existing `.pre-commit-config.yaml`; needs `--hooks-target`), or `none` (no versioning, or the team does not want them).
5. **AI tools** — which the team uses. Most read `AGENTS.md` natively and need nothing; see `references/pointer-blocks.md`.
6. **Pointers into code repos** — ask per repo, default yes.

Then clone the kit and install:

```bash
KIT=$(mktemp -d)
git clone --depth 1 https://github.com/georgiandinca/ai-sdlc-bootstrap-kit "$KIT"
"$KIT/template/scripts/bootstrap.sh" --name "<name>" --slug "<slug>" --dir "<target>" \
  --desc "<desc>" --ticket "<TICKET>" --host "<host>" --layout "<layout>" \
  --repos "<path=role,…>" --tools "<ids>" --hooks "<mode>" [--merge] [--hooks-target <dir>]
```

Use `--merge` whenever the target already has files. Without it, `bootstrap.sh` refuses a non-empty directory — that refusal is a safety feature, so never reach for `--force` to get past it.

### Rules for this step

- **Show the whole plan before writing anything** — every file to be created, every file to be appended to, every collision that will be skipped — and get an explicit yes.
- **Never overwrite a file the project owns.** `bootstrap.sh` handles this; do not work around it by hand.
- **If the target repo already has commits, work on a branch** (`chore/ai-sdlc-kit`) so the install can be reviewed.
- **If the working tree is dirty** (`git.dirty`), say so and let the user decide before touching anything.
- **Never commit without showing what will be committed.**
- After installing, read `.ai-sdlc/install-report.md` and tell the user what was created, what was merged, and what was skipped.

## Step 3 — Onboarding

Do not carry out the onboarding steps from memory and do not summarise them here. Read the installed project's `ONBOARDING.md` and follow it exactly — it is the single source of truth, it checks for `USER.md` itself, and it covers OS detection, tooling, identity, seat and git-comfort.

## Step 4 — Status

The kit is installed and this person is onboarded. Report, with a fix offered for each:

- **Version drift** — compare `kit.manifest.kit.version` with the latest tag of the public repo (`git ls-remote --tags`). Report the gap and what changed. **Do not update any files** — safe propagation is a separate piece of work.
- **Hooks not installed** (`hooks.config` true, `hooks.installed` false) — offer `pre-commit install`.
- **Repos missing from the manifest** — a sibling or child repo that appeared since install; offer to add it and write its pointer.
- **Unfilled placeholders** — `grep -roIn -- '<[A-Z_/]\{3,\}>' .` and list them.

## What this skill does not do

- **Update an installed kit.** Report drift, stop there.
- **Author skills.** That is `skill-creator`, inside the installed kit.
- **Onboard from memory.** Always via the project's `ONBOARDING.md`.

## Running without Claude Code

The situation check and `bootstrap.sh` are plain shell. Any agent can be pointed at this file and follow it, and a person can run the install directly:

```bash
git clone --depth 1 https://github.com/georgiandinca/ai-sdlc-bootstrap-kit /tmp/ai-sdlc-kit
/tmp/ai-sdlc-kit/template/scripts/bootstrap.sh --help
```
````

- [ ] **Step 2: Validate it**

Run: `python3 template/scripts/validate-skills.py .claude/skills/install-ai-sdlc-kit/SKILL.md`
Expected: `ok .claude/skills/install-ai-sdlc-kit/SKILL.md` and `1/1 SKILL.md files conform to agentskills.io.`

- [ ] **Step 3: Write `references/layouts.md`**

Create `.claude/skills/install-ai-sdlc-kit/references/layouts.md`:

```markdown
# The four layouts

Ask in this order. The first that fits is usually right.

## 1. `embedded` — the kit inside the repo

```
acme-api/
├── AGENTS.md  CLAUDE.md  ONBOARDING.md  WORKING-AGREEMENT.md
├── .claude/skills/   .github/workflows/   scripts/   docs/
├── .ai-sdlc/kit.json
└── src/                 ← the project's own code, untouched
```

One repo, one brief, hooks and CI protect the same repo the code lives in. Use `--merge`
when the repo already has files. **Best default.**

## 2. `monorepo` — the kit at the workspace root

Same file placement as `embedded`, at the root of a workspace that holds several packages.
`AGENTS.md` §2 lists each package and its role (`apps/web` = frontend, `services/api` = backend).
Signals: `pnpm-workspace.yaml`, `turbo.json`, `nx.json`, `lerna.json`, `go.work`, a Cargo `[workspace]`.

## 3. `sidecar` — the kit beside the code repos

```
acme/
├── acme-sdlc/     ← the kit, its own git repo
├── acme-api/      ← code repo + pointer block
└── acme-web/      ← code repo + pointer block
```

For several repos with different roles, or when the code repos cannot take the kit's files.
**Trade-off to state plainly:** the kit's hooks and CI protect `acme-sdlc` only. Use
`--hooks repo` to put the governance hooks into a code repo as well. Open the agent in
`acme-sdlc` and add the code repos with `--add-dir`, or rely on each repo's pointer.

## 4. `parent` — the kit above the code repos

```
acme/                  ← the kit lives here
├── AGENTS.md …
├── acme-api/          ← its own git repo
└── acme-web/          ← its own git repo
```

Same trade-offs as `sidecar`; the difference is that the parent folder may not be a git
repo at all. Use `--no-git` when it should not become one.

## Choosing when signals conflict

Signals propose; the user decides. State what you detected and why, then ask. A wrong
guess costs one keystroke — an unasked question costs a wrong install.
```

- [ ] **Step 4: Write `references/pointer-blocks.md`**

Create `.claude/skills/install-ai-sdlc-kit/references/pointer-blocks.md`:

```markdown
# Pointers — who needs one, and what gets written

`AGENTS.md` is canonical. Most agents read it with no configuration, so most need nothing.

| Tool | Reads `AGENTS.md` natively? | What the installer writes |
|---|---|---|
| OpenAI Codex (CLI + cloud) | yes | nothing |
| Cursor | yes (root + subdirectories) | nothing |
| Windsurf / Cascade | yes | nothing |
| Google Antigravity | yes (workspace root) | nothing |
| GitHub Copilot (github.com) | yes | nothing |
| GitHub Copilot (VS Code) | yes, behind a setting whose default is undocumented | optional `.github/copilot-instructions.md` pointer |
| **Claude Code** | **no — reads `CLAUDE.md`** | `CLAUDE.md` containing `@AGENTS.md` |
| **Gemini CLI** | **no — defaults to `GEMINI.md`** | `.gemini/settings.json` → `{"context":{"fileName":["AGENTS.md","GEMINI.md"]}}` |

Verified against official documentation on 2026-09-18. Re-check before adding a tool.

## The block

Every pointer written into a file the project owns goes inside markers, so a later run
updates it in place instead of appending a second copy:

```markdown
<!-- ai-sdlc-kit:begin -->
…pointer…
<!-- ai-sdlc-kit:end -->
```

Hash-comment files (`.gitignore`, YAML) use `# ai-sdlc-kit:begin` / `# ai-sdlc-kit:end`.
JSON files (Gemini settings) cannot carry comments — they are merged key-wise instead,
adding `AGENTS.md` only when it is not already listed.

## Pointers into code repos (`sidecar` / `parent`)

Each code repo gets both:

- `AGENTS.md` — names the kit's relative path **and** its clone URL, so a fresh clone that
  lacks the sibling folder knows how to get it.
- `CLAUDE.md` — `@<rel>/AGENTS.md`. An import outside the repo prompts the user for
  approval once; that is expected, and worth saying up front.
```

- [ ] **Step 5: Validate every skill again**

Run:
```bash
python3 template/scripts/validate-skills.py .claude/skills
python3 template/scripts/validate-skills.py
```
Expected: both report every file `ok`.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/install-ai-sdlc-kit
git commit -m "feat(installer): the install-ai-sdlc-kit skill and its references

Decision layer only: runs the situation check, picks setup / onboarding /
status, and delegates. Layout and pointer detail live in references/ so
SKILL.md stays short.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Plugin packaging and the kit's own documentation

Makes the skill installable in any project, and documents the routes for people who do not use Claude Code.

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`
- Modify: `README.md` (kit root)

**Interfaces:**
- Consumes: the skill from Task 6.
- Produces: `claude plugin marketplace add georgiandinca/ai-sdlc-bootstrap-kit` followed by installing the `ai-sdlc-kit` plugin, after which the skill is available in every project as `/ai-sdlc-kit:install-ai-sdlc-kit`.

> **Verified against the current plugin documentation (2026-09-18):** `.claude-plugin/` holds only JSON; plugin skills are discovered from the plugin's `skills` paths, **not** automatically from a repo's `.claude/skills/`. Because the plugin root here *is* the repo root, `"skills": ["./.claude/skills/"]` should resolve — Step 3 verifies that it actually does, and names the fallback if it does not.

- [ ] **Step 1: Write `plugin.json`**

Create `.claude-plugin/plugin.json`:

```json
{
  "name": "ai-sdlc-kit",
  "displayName": "AI-SDLC Bootstrap Kit",
  "description": "Install the AI-SDLC Bootstrap Kit into any project and onboard people to it.",
  "version": "0.1.0",
  "author": { "name": "Georgian Dinca" },
  "homepage": "https://github.com/georgiandinca/ai-sdlc-bootstrap-kit",
  "repository": "https://github.com/georgiandinca/ai-sdlc-bootstrap-kit",
  "license": "MIT",
  "keywords": ["sdlc", "governance", "bootstrap", "onboarding", "agents-md"],
  "skills": ["./.claude/skills/"]
}
```

- [ ] **Step 2: Write `marketplace.json`**

Create `.claude-plugin/marketplace.json`:

```json
{
  "name": "ai-sdlc-bootstrap-kit",
  "owner": { "name": "Georgian Dinca" },
  "description": "The AI-SDLC Bootstrap Kit and its installer.",
  "plugins": [
    {
      "name": "ai-sdlc-kit",
      "source": "./",
      "displayName": "AI-SDLC Bootstrap Kit",
      "description": "Install the kit into any project and onboard people to it.",
      "keywords": ["sdlc", "governance", "bootstrap", "onboarding"]
    }
  ]
}
```

- [ ] **Step 3: Verify the plugin loads and the skill is discovered**

Run, from any directory **other** than this repo:

```bash
claude plugin marketplace add /Users/georgiandinca/ps/AI/SDLC
claude plugin install ai-sdlc-kit@ai-sdlc-bootstrap-kit
claude plugin list
```

Expected: `ai-sdlc-kit` is listed as installed, and in a new session `/ai-sdlc-kit:install-ai-sdlc-kit` resolves.

**If the skill is not discovered**, the `skills` path is the cause. Fallback, in this order:
1. Change `"skills"` to `["./.claude/skills/install-ai-sdlc-kit"]` and retry.
2. If that also fails, move the skill directory to `skills/install-ai-sdlc-kit/` at the repo root, set `"skills": ["./skills/"]`, and update the two `detect-situation.sh` paths in `SKILL.md`, the CI validation path added in Task 1, and every path in this plan's Task 6.

Record which of the three worked in the commit message.

- [ ] **Step 4: End-to-end rehearsal in a throwaway project**

```bash
tmp=$(mktemp -d); mkdir -p "$tmp/acme-api/src"
printf '# Acme API\n' > "$tmp/acme-api/README.md"
printf 'console.log(1)\n' > "$tmp/acme-api/src/index.js"
( cd "$tmp/acme-api" && git init -q && git add -A && \
  git -c user.name=t -c user.email=t@t commit -qm init )
.claude/skills/install-ai-sdlc-kit/scripts/detect-situation.sh --dir "$tmp/acme-api"
template/scripts/bootstrap.sh --name "Acme API" --slug acme-api --dir "$tmp/acme-api" \
  --desc "api" --ticket ACME --layout embedded --merge --tools claude --non-interactive
head -1 "$tmp/acme-api/README.md"          # must still be "# Acme API"
cat "$tmp/acme-api/.ai-sdlc/install-report.md"
.claude/skills/install-ai-sdlc-kit/scripts/detect-situation.sh --dir "$tmp/acme-api"
rm -rf "$tmp"
```

Expected: the first check reports `absent`; the project's own README keeps its first line; the report lists what was created and skipped; the second check reports `present-uncommitted` with the manifest filled in.

- [ ] **Step 5: Document both routes in the kit README**

In `README.md`, replace the "Bootstrap a new project" section's opening with an install section covering: the plugin route (`claude plugin marketplace add georgiandinca/ai-sdlc-bootstrap-kit`, then install, then ask the agent to set up the kit); the other-agents route (clone, point the agent at `.claude/skills/install-ai-sdlc-kit/SKILL.md`); and the terminal route (the existing `bootstrap.sh` invocation, now with `--layout` and `--merge` documented). Keep the existing verification and design-principles sections as they are.

- [ ] **Step 6: Run the whole gate locally**

```bash
python3 template/scripts/validate-skills.py
python3 template/scripts/validate-skills.py .claude/skills
python3 template/scripts/validate-frontmatter.py
bash .claude/skills/install-ai-sdlc-kit/scripts/tests/test-detect-situation.sh
bash template/scripts/tests/test_kit_merge.sh
bash template/scripts/tests/test_kit_pointers.sh
bash template/scripts/tests/test_bootstrap.sh
python3 template/scripts/tests/test_merge_precommit.py
```
Expected: all pass.

- [ ] **Step 7: Commit and open the PR**

```bash
git add .claude-plugin README.md
git commit -m "feat(installer): package the installer as a Claude Code plugin

Adds the plugin and marketplace manifests so the skill installs into any
project, and documents the plugin, other-agent and terminal routes in the
kit README.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push -u origin feat/kit-installer-skill
```

Then open the PR with a body summarising: the new skill, the four layouts, merge-not-clobber, the manifest, the hook modes, and the CI gap this closes.

---

## Notes for the executor

- **Tasks are ordered by dependency.** Task 2 (merge engine) underpins 3, 4 and 5. Task 6 documents behaviour built in 1–5, so do not write `SKILL.md` before those work.
- **Every task ends green.** Run that task's tests before committing; do not carry a red test into the next task.
- **The kit repo has no ticket convention**, so commit messages carry no `Refs:` trailer.
- **`.gitlab-ci.yml` mirrors `.github/workflows/ci.yml`.** Every CI step added in this plan goes in both.
