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

# A well-formed pointer line is "pointer gemini <action>" with a non-empty
# action — check this holds for every gemini case below, not just the
# specific expected value, so a regression can never silently echo an
# empty/garbled action (Finding 3, review round 2).
check_gemini_shape() {
  if printf '%s' "$1" | grep -qE '^pointer gemini (created|updated|malformed|escaped)$'; then
    echo "ok   $2"
  else
    echo "FAIL $2: '$1' does not match 'pointer gemini <action>'"
    fails=$((fails+1))
  fi
}

# --- 3. gemini settings: created, then merged without losing existing keys ---------
tmp=$(mktemp -d)
gemini_out=$(kit_write_tool_pointers "$tmp" "gemini")
check gemini_created_action "$gemini_out" "pointer gemini created"
check_gemini_shape "$gemini_out" gemini_created_shape_ok
check gemini_created "$(python3 -c 'import json,sys;print("AGENTS.md" in json.load(open(sys.argv[1]))["context"]["fileName"])' "$tmp/.gemini/settings.json")" "True"
mkdir -p "$tmp/g2/.gemini"; printf '{"theme":"dark","context":{"fileName":["GEMINI.md"]}}\n' > "$tmp/g2/.gemini/settings.json"
gemini_out2=$(kit_write_tool_pointers "$tmp/g2" "gemini")
check gemini_updated_action "$gemini_out2" "pointer gemini updated"
check_gemini_shape "$gemini_out2" gemini_updated_shape_ok
check gemini_kept_theme "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["theme"])' "$tmp/g2/.gemini/settings.json")" "dark"
check gemini_added "$(python3 -c 'import json,sys;print(",".join(json.load(open(sys.argv[1]))["context"]["fileName"]))' "$tmp/g2/.gemini/settings.json")" "AGENTS.md,GEMINI.md"
kit_write_tool_pointers "$tmp/g2" "gemini" >/dev/null  # idempotent, no duplicate entry
check gemini_no_dupe "$(python3 -c 'import json,sys;f=json.load(open(sys.argv[1]))["context"]["fileName"];print(len(f))' "$tmp/g2/.gemini/settings.json")" "2"
rm -rf "$tmp"

# --- 3b. malformed (invalid JSON) .gemini/settings.json is reported, never clobbered --
tmp=$(mktemp -d); mkdir -p "$tmp/.gemini"
printf '{"theme":"dark","custom_api_keys":["SECRET-123"], invalid syntax here' > "$tmp/.gemini/settings.json"
cp "$tmp/.gemini/settings.json" "$tmp/gemini-before"
gemini_out3=$(kit_write_tool_pointers "$tmp" "gemini")
check gemini_invalid_json_action    "$gemini_out3" "pointer gemini malformed"
check_gemini_shape "$gemini_out3" gemini_invalid_json_shape_ok
check gemini_invalid_json_unchanged "$(cmp -s "$tmp/gemini-before" "$tmp/.gemini/settings.json" && echo same)" "same"
rm -rf "$tmp"

# --- 3c. .gemini/settings.json whose "context" isn't a mapping is also malformed -----
tmp=$(mktemp -d); mkdir -p "$tmp/.gemini"
printf '{"context":"nope"}' > "$tmp/.gemini/settings.json"
cp "$tmp/.gemini/settings.json" "$tmp/gemini-before"
gemini_out4=$(kit_write_tool_pointers "$tmp" "gemini")
check gemini_bad_context_action    "$gemini_out4" "pointer gemini malformed"
check_gemini_shape "$gemini_out4" gemini_bad_context_shape_ok
check gemini_bad_context_unchanged "$(cmp -s "$tmp/gemini-before" "$tmp/.gemini/settings.json" && echo same)" "same"
rm -rf "$tmp"

# --- 3d. a syntactically valid but non-object top level is malformed too, and -------
# never crashes: array / number / string all reported malformed, byte-identical,
# exit 0, and no Python traceback on stderr (the review-round-2 regression: these
# shapes used to raise an uncaught AttributeError from data.get("context")).
for shape_case in "array [1,2,3]" "scalar 42" "string \"hello\""; do
  shape_label=${shape_case%% *}
  shape_json=${shape_case#* }
  tmp=$(mktemp -d); mkdir -p "$tmp/.gemini"
  printf '%s' "$shape_json" > "$tmp/.gemini/settings.json"
  cp "$tmp/.gemini/settings.json" "$tmp/gemini-before"
  gemini_out_shape=$(kit_write_tool_pointers "$tmp" "gemini" 2>"$tmp/stderr.log")
  shape_rc=$?
  check "gemini_${shape_label}_exit"        "$shape_rc" "0"
  check "gemini_${shape_label}_action"      "$gemini_out_shape" "pointer gemini malformed"
  check_gemini_shape "$gemini_out_shape" "gemini_${shape_label}_shape_ok"
  check "gemini_${shape_label}_unchanged"   "$(cmp -s "$tmp/gemini-before" "$tmp/.gemini/settings.json" && echo same)" "same"
  check "gemini_${shape_label}_no_traceback" "$(grep -c 'Traceback' "$tmp/stderr.log")" "0"
  rm -rf "$tmp"
done

# --- 4. a tool that needs nothing reports "none" ------------------------------------
tmp=$(mktemp -d)
check cursor_none "$(kit_write_tool_pointers "$tmp" "cursor")" "pointer cursor none"
check cursor_nofiles "$(ls -A "$tmp" | wc -l | tr -d ' ')" "0"
rm -rf "$tmp"

# --- 5. code-repo pointer names both the path and the clone URL --------------------
tmp=$(mktemp -d); mkdir -p "$tmp/acme-api"
repo_out=$(kit_write_repo_pointer "$tmp/acme-api" "../acme-sdlc" "https://example.com/acme-sdlc.git")
check repo_agents "$(grep -c '\.\./acme-sdlc/AGENTS.md' "$tmp/acme-api/AGENTS.md")" "1"
check repo_url    "$(grep -c 'example.com/acme-sdlc.git' "$tmp/acme-api/AGENTS.md")" "1"
check repo_claude "$(grep -c '@\.\./acme-sdlc/AGENTS.md' "$tmp/acme-api/CLAUDE.md")" "1"
check repo_agents_line "$(printf '%s\n' "$repo_out" | grep -c -- "^repo-pointer $tmp/acme-api created\$")" "1"
check repo_claude_line "$(printf '%s\n' "$repo_out" | grep -c -- "^repo-pointer-claude $tmp/acme-api created\$")" "1"
rm -rf "$tmp"

# --- 5b. a malformed CLAUDE.md in a code repo is reported, not swallowed -----------
# AGENTS.md still gets its pointer even though CLAUDE.md's marker layout is
# ambiguous (begin marker present, no end marker).
tmp=$(mktemp -d); mkdir -p "$tmp/acme-api2"
printf '<!-- ai-sdlc-kit:begin -->\nstray content, no end marker\n' > "$tmp/acme-api2/CLAUDE.md"
cp "$tmp/acme-api2/CLAUDE.md" "$tmp/claude-before"
repo_out2=$(kit_write_repo_pointer "$tmp/acme-api2" "../acme-sdlc" "https://example.com/acme-sdlc.git")
check repo_claude_malformed  "$(printf '%s\n' "$repo_out2" | grep -c -- "^repo-pointer-claude $tmp/acme-api2 malformed\$")" "1"
check repo_claude_unchanged  "$(cmp -s "$tmp/claude-before" "$tmp/acme-api2/CLAUDE.md" && echo same)" "same"
check repo_agents_still_written "$([ -f "$tmp/acme-api2/AGENTS.md" ] && echo yes)" "yes"
check repo_agents_action_ok  "$(printf '%s\n' "$repo_out2" | grep -c -- "^repo-pointer $tmp/acme-api2 created\$")" "1"
rm -rf "$tmp"

# --- 5c. fix-round 2, finding 4: pointers never write outside the target -----------
# A CLAUDE.md / .gemini that leaves the tree through a symlink is refused, not
# followed: the file outside the target stays byte-identical.
tmp=$(mktemp -d); mkdir -p "$tmp/outside" "$tmp/proj" "$tmp/outside/gemini"
printf 'their claude notes\n' > "$tmp/outside/CLAUDE.md"
ln -s ../outside/CLAUDE.md "$tmp/proj/CLAUDE.md"
ln -s ../outside/gemini    "$tmp/proj/.gemini"
outside_before=$(cat "$tmp/outside/CLAUDE.md")
esc_out=$(kit_write_tool_pointers "$tmp/proj" "claude,gemini")
check ptr_claude_escaped    "$(printf '%s\n' "$esc_out" | grep -c '^pointer claude escaped$')" "1"
check ptr_gemini_escaped    "$(printf '%s\n' "$esc_out" | grep -c '^pointer gemini escaped$')" "1"
check ptr_outside_untouched "$(cat "$tmp/outside/CLAUDE.md")" "$outside_before"
check ptr_outside_no_gemini "$([ -e "$tmp/outside/gemini/settings.json" ] && echo written || echo none)" "none"
check ptr_claude_still_link "$([ -L "$tmp/proj/CLAUDE.md" ] && echo link || echo file)" "link"
rm -rf "$tmp"

# A code-repo pointer is contained the same way, against the CODE REPO's root.
tmp=$(mktemp -d); mkdir -p "$tmp/outside" "$tmp/acme-api"
printf 'their agents brief\n' > "$tmp/outside/AGENTS.md"
ln -s ../outside/AGENTS.md "$tmp/acme-api/AGENTS.md"
agents_before=$(cat "$tmp/outside/AGENTS.md")
esc_repo=$(kit_write_repo_pointer "$tmp/acme-api" "../acme-sdlc" "https://example.com/kit.git")
check repo_ptr_escaped    "$(printf '%s\n' "$esc_repo" | grep -c -- "^repo-pointer $tmp/acme-api escaped\$")" "1"
check repo_ptr_untouched  "$(cat "$tmp/outside/AGENTS.md")" "$agents_before"
check repo_ptr_claude_ok  "$(printf '%s\n' "$esc_repo" | grep -c -- "^repo-pointer-claude $tmp/acme-api created\$")" "1"
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
