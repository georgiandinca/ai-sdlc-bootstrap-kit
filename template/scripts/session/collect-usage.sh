#!/usr/bin/env bash
# SessionEnd hook: record the ended Claude Code session's token usage into
# the dashboard DB (token-roi design §4). Reads the hook payload JSON from
# stdin (session_id, transcript_path). Telemetry may be lost; a session
# ritual must never break: every path exits 0, failures append to
# scripts/session/.usage-errors.log.
set -u

root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
# In the kit repo the workspace root is the kit, not template/ — resolve to
# the directory that actually holds scripts/session (template/ in the kit,
# repo root in a generated project).
[ -d "$root/scripts/session" ] || root="$root/template"
[ -d "$root/scripts/session" ] || exit 0
cd "$root" || exit 0
errlog="scripts/session/.usage-errors.log"
log_err() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >> "$errlog" 2>/dev/null; }

payload=$(cat 2>/dev/null || true)
read_field() {
  printf '%s' "$payload" | python3 -c \
    'import json,sys;print(json.load(sys.stdin).get(sys.argv[1],""))' "$1" 2>/dev/null || true
}
transcript=$(read_field transcript_path)
session_id=$(read_field session_id)

if [ -z "$transcript" ] || [ ! -f "$transcript" ]; then
  log_err "no usable transcript in hook payload (transcript='$transcript')"
  exit 0
fi
[ -n "$session_id" ] || session_id=$(basename "$transcript" .jsonl)

seat="unknown"
if [ -f scripts/session/lib.sh ]; then
  # shellcheck disable=SC1091
  . scripts/session/lib.sh 2>/dev/null || true
  s=$(sdlc_seat 2>/dev/null || true); [ -n "$s" ] && seat="$s"
fi
branch=$(git branch --show-current 2>/dev/null || true)
ticket=$(printf '%s' "$branch" | grep -oE '[A-Z][A-Z0-9]+-[0-9]+' | head -n1 || true)

user=$(python3 -c 'import sys; sys.path.insert(0, "scripts/spend"); from export_sessions import resolve_user; print(resolve_user() or "")' 2>/dev/null || true)

db="${SDLC_USAGE_DB:-dashboard/utilization.db}"
if python3 scripts/spend/parse_transcript.py \
     --transcript "$transcript" --session-id "$session_id" \
     --seat "$seat" ${ticket:+--ticket "$ticket"} ${user:+--user "$user"} \
     --db "$db" 2>>"$errlog"; then
  # Team ledger (design §5): regenerate this user's committed CSV. Failure
  # is telemetry loss, never a broken session — log and keep exit 0.
  ledger_dir="${SDLC_SESSIONS_DIR:-docs/metrics/sessions}"
  if ! python3 scripts/spend/export_sessions.py \
       --db "$db" --out-dir "$ledger_dir" ${user:+--user "$user"} 2>>"$errlog"; then
    log_err "export_sessions failed for $session_id"
  fi
else
  log_err "parse_transcript failed for $transcript"
fi
exit 0
