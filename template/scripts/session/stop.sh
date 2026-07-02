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

state=$(git rev-parse --git-path .sdlc-stop-state 2>/dev/null) || state="$root/.git/.sdlc-stop-state"
now=$(date +%s); last=0
[ -f "$state" ] && last=$(cat "$state" 2>/dev/null || echo 0)
case "$last" in ''|*[!0-9]*) last=0 ;; esac
[ $((now - last)) -lt 600 ] && exit 0
printf '%s' "$now" > "$state" 2>/dev/null || true

echo '{"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":"You have unsaved work. Say: save my work — and I will checkpoint it (scripts/session/checkpoint.sh)."}}'
exit 0
