#!/usr/bin/env bash
# Commit changes and open a Pull Request (or print the PR-create URL).
# Implements the board's git workflow: Repo -> Edit -> Pull Request.
#
# Usage: wrapup.sh [--seat <seat>] [--target <branch>] [--ticket <KEY>] "<message>" [path ...]
#   --seat    confirmed operator seat; used to name the branch when starting from a
#             protected branch. Prompted if omitted and the terminal is interactive.
#   --target  PR target branch. Defaults to SESSION_PR_TARGET from scripts/session/config.
#   --ticket  issue key (e.g. PROJ-123). Names the branch feature/<KEY>-<slug> and adds a
#             "Refs: <KEY>" trailer if the message has none. Otherwise read from the branch.
#
# PR creation: uses the `gh` CLI if present (GitHub). Otherwise the branch is pushed and a
# compare/PR URL is printed for you to open by hand. AI never pushes a protected branch.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

config="scripts/session/config"
[ -f "$config" ] && . "$config" || true
personal="${SDLC_CONFIG_DIR:-$HOME/.config/ai-sdlc}/env"
# shellcheck disable=SC1090
[ -f "$personal" ] && { . "$personal" || true; }

seat=""; target=""; ticket=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --seat)   shift; seat=${1:-};   [ -n "$seat" ]   || { echo "[wrapup] --seat needs a value" >&2; exit 2; }; shift ;;
    --target) shift; target=${1:-}; [ -n "$target" ] || { echo "[wrapup] --target needs a value" >&2; exit 2; }; shift ;;
    --ticket) shift; ticket=${1:-}; [ -n "$ticket" ] || { echo "[wrapup] --ticket needs a value" >&2; exit 2; }; shift ;;
    --) shift; break ;;
    --*) echo "[wrapup] unknown flag: $1" >&2; exit 2 ;;
    *) break ;;
  esac
done

msg=${1:-}; [ -n "$msg" ] || { echo "[wrapup] commit message required" >&2; exit 2; }
shift || true
target=${target:-${SESSION_PR_TARGET:-main}}

branch=$(git branch --show-current)
if [ "$branch" = main ] || [ "$branch" = master ]; then
  [ -z "$seat" ] && seat=${SESSION_SEAT:-}
  if [ -z "$seat" ] && [ -t 0 ]; then
    printf '[wrapup] On %s. Enter your seat (Architect/EM/Product/Developer/QA): ' "$branch" >&2
    read -r seat
  fi
  [ -n "$seat" ] || { echo "[wrapup] on protected branch '$branch' — pass --seat <seat>" >&2; exit 2; }
  seat_slug=$(printf '%s' "$seat" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-')
  slug=$(printf '%s' "$msg" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-' | cut -c1-40)
  branch="session/${seat_slug}/${slug}"
  if [ -n "$ticket" ]; then
    branch="feature/${ticket}-${slug}"
    echo "[wrapup] ticket $ticket given — using branch $branch"
  fi
  git switch -c "$branch"
  echo "[wrapup] was on a protected branch — created $branch"
fi

if [ "$#" -gt 0 ]; then git add -- "$@"; else
  echo "[wrapup] no paths given; staging tracked modifications (git add -u) only"; git add -u
fi
git diff --cached --quiet && { echo "[wrapup] nothing staged — aborting." >&2; exit 3; }

# Append a Refs trailer if a ticket key is known and the message lacks one.
key="$ticket"
[ -z "$key" ] && key=$(printf '%s' "$branch" | grep -oE '[A-Z][A-Z0-9]+-[0-9]+' | head -n1 || true)
if [ -n "$key" ] && ! printf '%s' "$msg" | grep -qE '[A-Z][A-Z0-9]+-[0-9]+'; then
  msg="${msg}

Refs: ${key}"
fi
git commit -m "$msg"
git push -u origin "$branch"

if command -v gh >/dev/null 2>&1; then
  if gh pr create --base "$target" --head "$branch" --title "$msg" --body "Opened by scripts/session/wrapup.sh" 2>/dev/null; then
    echo "[wrapup] PR created via gh."
    exit 0
  fi
  echo "[wrapup] gh pr create failed — printing manual URL." >&2
fi

remote=$(git remote get-url origin)
host_path=${remote#*@}; host_path=${host_path#*://}
host=${host_path%%[:/]*}; path=${host_path#*[:/]}; path=${path%.git}
echo "[wrapup] Branch pushed. Open a PR:"
case "$host" in
  github.com)    echo "         https://github.com/${path}/compare/${target}...${branch}?expand=1" ;;
  gitlab.com)    echo "         https://gitlab.com/${path}/-/merge_requests/new?merge_request[source_branch]=${branch}&merge_request[target_branch]=${target}" ;;
  bitbucket.org) echo "         https://bitbucket.org/${path}/pull-requests/new?source=${branch}&dest=${target}" ;;
  *)             echo "         (push succeeded; open a PR for ${branch} -> ${target} on ${host})" ;;
esac
