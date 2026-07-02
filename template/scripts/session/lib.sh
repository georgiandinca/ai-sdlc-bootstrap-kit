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
    with open(path) as f:
        data = json.load(f)
except Exception:
    sys.exit(0)
for m in data.get("moments", []):
    if m.get("id") == mid:
        print(m.get("behavior_by_comfort", {}).get(comfort, ""))
        break
PY
}

# If on a protected branch, switch to a personal feature branch. Echo the branch.
# Returns non-zero if still on a protected branch after the switch attempt.
sdlc_ensure_feature_branch() {
  local seat="${1:-}" purpose="${2:-work}" branch slug pslug
  branch=$(git branch --show-current)
  if [ "$branch" = main ] || [ "$branch" = master ]; then
    slug=$(printf '%s' "${seat:-work}" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-'); [ -z "$slug" ] && slug=work
    pslug=$(printf '%s' "$purpose" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-'); [ -z "$pslug" ] && pslug=work
    git switch -c "session/${slug}/${pslug}" 2>/dev/null || git switch "session/${slug}/${pslug}" 2>/dev/null || true
  fi
  branch=$(git branch --show-current)
  printf '%s\n' "$branch"
  case "$branch" in ''|main|master) return 1 ;; esac
  return 0
}
