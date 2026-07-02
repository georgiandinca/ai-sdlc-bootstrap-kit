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
