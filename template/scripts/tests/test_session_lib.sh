#!/usr/bin/env bash
# Functional test for lib.sh (no framework). Exits non-zero on any failure.
set -uo pipefail
SRC_ROOT=$(cd "$(dirname "$0")/../../.." && pwd)   # repo root (…/template)
LIB="$SRC_ROOT/template/scripts/session/lib.sh"
[ -f "$LIB" ] || LIB="$SRC_ROOT/scripts/session/lib.sh"   # when run from inside template/
fails=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got '$2' want '$3'"; fails=$((fails+1)); fi; }

tmp=$(mktemp -d); ( cd "$tmp"
  git init -q; mkdir -p scripts/session
  cp "$LIB" scripts/session/lib.sh
  cat > scripts/session/moments.json <<'JSON'
{ "version": 1, "moments": [
  { "id": "session-start", "trigger": "x", "handler": "scripts/session/start.sh", "hook": "SessionStart", "status": "active",
    "behavior_by_comfort": { "git-native": "offer", "guided": "offer", "hidden": "auto" } } ] }
JSON
  printf -- '- **Seat:** Product\n- **Git comfort:** hidden\n' > USER.md
  # shellcheck source=/dev/null
  . scripts/session/lib.sh
  check comfort   "$(sdlc_git_comfort)"                       "hidden"
  check seat      "$(sdlc_seat)"                              "Product"
  check behavior  "$(sdlc_moment_behavior session-start hidden)" "auto"
  check behavior2 "$(sdlc_moment_behavior session-start git-native)" "offer"
  git checkout -q -b main 2>/dev/null || git branch -m main
  br=$(sdlc_ensure_feature_branch Product save); check branch "$br" "session/product/save"
  # git-comfort env fallback: USER.md has no git-comfort line, env var takes over
  printf -- '- **Seat:** Product\n' > USER.md
  check comfort_env "$(SESSION_GIT_COMFORT=guided sdlc_git_comfort)" "guided"
  # git-comfort unset sentinel: no git-comfort line, env var not set
  check comfort_unset "$(unset SESSION_GIT_COMFORT; sdlc_git_comfort)" "unset"
  exit $fails
)
rc=$?
rm -rf "$tmp"
exit $rc
