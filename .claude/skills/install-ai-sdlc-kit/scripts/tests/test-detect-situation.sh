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

echo "---"
[ "$fails" -eq 0 ] && echo "all detect-situation tests passed" || echo "$fails test(s) failed"
exit "$fails"
