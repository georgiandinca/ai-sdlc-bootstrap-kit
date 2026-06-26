#!/usr/bin/env bash
# Session-start status for the current repo. Read-only. Always exits 0.
set -uo pipefail

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "[session-start] not inside a git repo — skipping sync check."; exit 0; }
cd "$repo_root"

config="scripts/session/config"
[ -f "$config" ] && . "$config" || true

origin=$(git remote get-url origin 2>/dev/null || true)
repo=$(basename -s .git "${origin:-$repo_root}")
branch=$(git branch --show-current)
git fetch --quiet 2>/dev/null || true

behind=0; ahead=0; upstream=none
if u=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null); then
  upstream=$u
  read -r behind ahead < <(git rev-list --left-right --count "$u"...HEAD 2>/dev/null || echo "0 0")
fi
dirty=clean; [ -n "$(git status --porcelain)" ] && dirty=dirty

personal="${SDLC_CONFIG_DIR:-$HOME/.config/ai-sdlc}/env"
seat_status="unset"; token_status="no"
if [ -f "$personal" ]; then
  # shellcheck disable=SC1090
  . "$personal" || true
  [ -n "${SESSION_SEAT:-}" ] && seat_status="$SESSION_SEAT (confirm or change)"
  [ -n "${GIT_HOST_TOKEN:-}" ] && token_status="yes"
fi

echo "[session-start] repo=$repo branch=$branch upstream=$upstream behind=$behind ahead=$ahead tree=$dirty seat=$seat_status token=$token_status"
cat <<'EOF'
[session ritual] Before creating artefacts and during this session:
1. Confirm the operator's SEAT (Architect/EM/Product/Developer/QA). If a saved seat is
   shown above, confirm or change it; otherwise ask. Use it as the default `owner:` in new
   frontmatter; set `author:` from `git config user.name`/`user.email`; `created:` = today.
2. If this branch is BEHIND upstream AND the tree is CLEAN, OFFER a sync
   (scripts/session/sync.sh). Run it ONLY after the operator agrees.
3. When the operator signals they are wrapping up, OFFER to commit + raise a PR
   (scripts/session/wrapup.sh "<message>" <paths...>). Confirm files + message first.
EOF
