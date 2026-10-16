#!/usr/bin/env bash
# SessionEnd hook: record the ended Claude Code session's token usage into
# the dashboard DB (token-roi design §4). Reads the hook payload JSON from
# stdin (session_id, transcript_path). Telemetry may be lost; a session
# ritual must never break: every path exits 0, failures append to
# scripts/session/.usage-errors.log, redacted by scripts/lib/redact.py.
set -u

root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
# In the kit repo the workspace root is the kit, not template/ — resolve to
# the directory that actually holds scripts/session (template/ in the kit,
# repo root in a generated project).
[ -d "$root/scripts/session" ] || root="$root/template"
[ -d "$root/scripts/session" ] || exit 0
cd "$root" || exit 0
errlog="scripts/session/.usage-errors.log"
# Everything bound for the log passes the shared redactor; if it cannot run,
# the text is dropped, never logged raw.
redact_to_log() {
  python3 scripts/lib/redact.py >> "$errlog" 2>/dev/null \
    || printf '%s redaction failed; error text dropped\n' "$(date -u +%FT%TZ)" >> "$errlog" 2>/dev/null
}
log_err() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" | redact_to_log; }
# Run "$@"; its stderr reaches the log redacted. Returns the command's status.
# The raw stderr file is removed on any exit, even a killed run.
raw_err=""
trap 'rm -f "$raw_err"' EXIT
run_logged() {
  local rc
  raw_err=$(mktemp "${TMPDIR:-/tmp}/collect-usage.XXXXXX" 2>/dev/null) || { "$@" 2>/dev/null; return; }
  "$@" 2>"$raw_err"; rc=$?
  [ -s "$raw_err" ] && redact_to_log < "$raw_err"
  rm -f "$raw_err"; raw_err=""
  return "$rc"
}

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
if run_logged python3 scripts/spend/parse_transcript.py \
     --transcript "$transcript" --session-id "$session_id" \
     --seat "$seat" ${ticket:+--ticket "$ticket"} ${user:+--user "$user"} \
     --db "$db"; then
  # Team ledger (design §5): regenerate this user's committed CSV. Failure
  # is telemetry loss, never a broken session — log and keep exit 0.
  ledger_dir="${SDLC_SESSIONS_DIR:-docs/metrics/sessions}"
  if ! run_logged python3 scripts/spend/export_sessions.py \
       --db "$db" --out-dir "$ledger_dir" ${user:+--user "$user"}; then
    log_err "export_sessions failed for $session_id"
  fi
else
  log_err "parse_transcript failed for $transcript"
fi
exit 0
