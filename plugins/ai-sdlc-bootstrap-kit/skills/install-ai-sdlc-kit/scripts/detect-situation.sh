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

dir=$(pwd)
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dir) dir=${2:?}; shift 2 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "detect-situation: unknown arg: $1" >&2; exit 2 ;;
  esac
done
cd "$dir" 2>/dev/null || { echo "detect-situation: no such directory: $dir" >&2; exit 2; }
dir=$(pwd)

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
kit_state="absent"; kit_root=""; manifest="null"; manifest_valid=0
if [ -f "$dir/.ai-sdlc/kit.json" ]; then
  kit_root="$dir"
  manifest_content=$(cat "$dir/.ai-sdlc/kit.json")

  # Validate manifest JSON. Try python3 first; fall back to shell check.
  if command -v python3 >/dev/null 2>&1; then
    if printf '%s' "$manifest_content" | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
      manifest="$manifest_content"
      manifest_valid=1
    fi
  else
    # Minimal shell check: first non-whitespace is {, last is }
    trimmed=$(printf '%s' "$manifest_content" | sed -e 's/^[[:space:]]*//;s/[[:space:]]*$//')
    if [ "${trimmed#\{}" != "$trimmed" ] && [ "${trimmed%\}}" != "$trimmed" ]; then
      manifest="$manifest_content"
      manifest_valid=1
    fi
  fi

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

# Emitted with printf, not a here-document: bash backs a here-document with a temp
# file, which fails in a read-only sandbox (as Codex and other agents run this check).
printf '{\n'
printf '  "cwd": %s,\n' "$(json_str "$dir")"
printf '  "git": {\n'
printf '    "is_repo": %s,\n' "$(json_bool "$is_repo")"
printf '    "root": %s,\n' "$(json_str "$git_root")"
printf '    "remote": %s,\n' "$(json_str "$remote")"
printf '    "branch": %s,\n' "$(json_str "$branch")"
printf '    "dirty": %s,\n' "$(json_bool "$dirty")"
printf '    "has_commits": %s\n' "$(json_bool "$has_commits")"
printf '  },\n'
printf '  "kit": {\n'
printf '    "state": %s,\n' "$(json_str "$kit_state")"
printf '    "root": %s,\n' "$(json_str "$kit_root")"
printf '    "manifest": %s,\n' "$manifest"
printf '    "manifest_valid": %s\n' "$(json_bool "$manifest_valid")"
printf '  },\n'
printf '  "user_md": %s,\n' "$(json_bool "$user_md")"
printf '  "hooks": {\n'
printf '    "config": %s,\n' "$(json_bool "$hooks_config")"
printf '    "installed": %s,\n' "$(json_bool "$hooks_installed")"
printf '    "pre_commit_available": %s\n' "$(json_bool "$pre_commit_available")"
printf '  },\n'
printf '  "layout_signals": {\n'
printf '    "workspace_files": %s,\n' "$(json_array ${workspace+"${workspace[@]}"})"
printf '    "child_repos": %s,\n' "$(json_array ${children+"${children[@]}"})"
printf '    "sibling_repos": %s\n' "$(json_array ${siblings+"${siblings[@]}"})"
printf '  },\n'
printf '  "tooling": {\n'
printf '    "git": %s,\n' "$(json_str "$v_git")"
printf '    "python3": %s,\n' "$(json_str "$v_py")"
printf '    "pyyaml": %s\n' "$(json_bool "$pyyaml")"
printf '  }\n'
printf '}\n'
