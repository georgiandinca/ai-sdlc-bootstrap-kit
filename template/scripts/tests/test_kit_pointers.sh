#!/usr/bin/env bash
# Functional test for kit-pointers.sh (no framework). Exits non-zero on any failure.
set -uo pipefail
SRC_ROOT=$(cd "$(dirname "$0")/../.." && pwd)     # …/template
fails=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got '$2' want '$3'"; fails=$((fails+1)); fi; }
# shellcheck source=/dev/null
. "$SRC_ROOT/scripts/lib/kit-merge.sh"
# shellcheck source=/dev/null
. "$SRC_ROOT/scripts/lib/kit-pointers.sh"

# --- 1. claude pointer is created when absent --------------------------------------
tmp=$(mktemp -d)
kit_write_tool_pointers "$tmp" "claude" >/dev/null
check claude_created "$(grep -c '@AGENTS.md' "$tmp/CLAUDE.md")" "1"
rm -rf "$tmp"

# --- 2. existing CLAUDE.md keeps its content, gains one block ----------------------
tmp=$(mktemp -d); printf '# CLAUDE.md\n\nProject notes.\n' > "$tmp/CLAUDE.md"
kit_write_tool_pointers "$tmp" "claude" >/dev/null
check claude_kept  "$(head -1 "$tmp/CLAUDE.md")" "# CLAUDE.md"
check claude_block "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/CLAUDE.md")" "1"
kit_write_tool_pointers "$tmp" "claude" >/dev/null     # idempotent
check claude_block_once "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/CLAUDE.md")" "1"
rm -rf "$tmp"

# --- 3. gemini settings: created, then merged without losing existing keys ---------
tmp=$(mktemp -d)
kit_write_tool_pointers "$tmp" "gemini" >/dev/null
check gemini_created "$(python3 -c 'import json,sys;print("AGENTS.md" in json.load(open(sys.argv[1]))["context"]["fileName"])' "$tmp/.gemini/settings.json")" "True"
mkdir -p "$tmp/g2/.gemini"; printf '{"theme":"dark","context":{"fileName":["GEMINI.md"]}}\n' > "$tmp/g2/.gemini/settings.json"
kit_write_tool_pointers "$tmp/g2" "gemini" >/dev/null
check gemini_kept_theme "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["theme"])' "$tmp/g2/.gemini/settings.json")" "dark"
check gemini_added "$(python3 -c 'import json,sys;print(",".join(json.load(open(sys.argv[1]))["context"]["fileName"]))' "$tmp/g2/.gemini/settings.json")" "AGENTS.md,GEMINI.md"
kit_write_tool_pointers "$tmp/g2" "gemini" >/dev/null  # idempotent, no duplicate entry
check gemini_no_dupe "$(python3 -c 'import json,sys;f=json.load(open(sys.argv[1]))["context"]["fileName"];print(len(f))' "$tmp/g2/.gemini/settings.json")" "2"
rm -rf "$tmp"

# --- 4. a tool that needs nothing reports "none" ------------------------------------
tmp=$(mktemp -d)
check cursor_none "$(kit_write_tool_pointers "$tmp" "cursor")" "pointer cursor none"
check cursor_nofiles "$(ls -A "$tmp" | wc -l | tr -d ' ')" "0"
rm -rf "$tmp"

# --- 5. code-repo pointer names both the path and the clone URL --------------------
tmp=$(mktemp -d); mkdir -p "$tmp/acme-api"
kit_write_repo_pointer "$tmp/acme-api" "../acme-sdlc" "https://example.com/acme-sdlc.git" >/dev/null
check repo_agents "$(grep -c '\.\./acme-sdlc/AGENTS.md' "$tmp/acme-api/AGENTS.md")" "1"
check repo_url    "$(grep -c 'example.com/acme-sdlc.git' "$tmp/acme-api/AGENTS.md")" "1"
check repo_claude "$(grep -c '@\.\./acme-sdlc/AGENTS.md' "$tmp/acme-api/CLAUDE.md")" "1"
rm -rf "$tmp"

# --- 6. README block carries the project's own facts -------------------------------
block=$(kit_readme_block "Acme Wallet" "sidecar" "| \`../acme-api\` | backend |" "1.2.0" "https://example.com/kit")
check readme_name   "$(printf '%s' "$block" | grep -c 'Acme Wallet')" "1"
check readme_layout "$(printf '%s' "$block" | grep -c 'sidecar')" "1"
check readme_repo   "$(printf '%s' "$block" | grep -c 'acme-api')" "1"
check readme_start  "$(printf '%s' "$block" | grep -c 'ONBOARDING.md')" "1"

echo "---"
[ "$fails" -eq 0 ] && echo "all kit-pointers tests passed" || echo "$fails test(s) failed"
exit "$fails"
