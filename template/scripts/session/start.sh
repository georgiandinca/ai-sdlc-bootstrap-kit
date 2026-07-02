#!/usr/bin/env bash
# Session-start status for the current repo. Read-only. Always exits 0.
set -uo pipefail

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "[session-start] not inside a git repo — skipping sync check."; exit 0; }
cd "$repo_root"
# shellcheck source=/dev/null
[ -f scripts/session/lib.sh ] && . scripts/session/lib.sh || true

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
