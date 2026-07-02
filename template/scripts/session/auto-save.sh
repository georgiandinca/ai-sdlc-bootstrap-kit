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

branch=$(sdlc_ensure_feature_branch "$(sdlc_seat)" autosave) || exit 0
git add -A
git diff --cached --quiet && exit 0
git commit -q -m "auto-save: session end" || exit 0
git push -u origin "$branch" >/dev/null 2>&1 || true
exit 0
