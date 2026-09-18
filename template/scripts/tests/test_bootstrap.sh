#!/usr/bin/env bash
# Functional test for bootstrap.sh (no framework). Exits non-zero on any failure.
set -uo pipefail
SRC_ROOT=$(cd "$(dirname "$0")/../.." && pwd)     # …/template
BOOT="$SRC_ROOT/scripts/bootstrap.sh"
fails=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got '$2' want '$3'"; fails=$((fails+1)); fi; }
jqp() { python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."):
    d = d[k] if isinstance(d, dict) else None
print(json.dumps(d))' "$1" "$2"; }

export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

# --- 1. fresh embedded install -----------------------------------------------------
tmp=$(mktemp -d)
"$BOOT" --name "Acme Wallet" --slug acme-wallet --dir "$tmp/acme" --desc "wallet" \
        --ticket ACME --layout embedded --kit-version 1.2.0 --kit-commit abc1234 \
        --non-interactive >/dev/null 2>&1
check fresh_agents   "$([ -f "$tmp/acme/AGENTS.md" ] && echo yes)" "yes"
check fresh_manifest "$([ -f "$tmp/acme/.ai-sdlc/kit.json" ] && echo yes)" "yes"
check fresh_layout   "$(jqp "$tmp/acme/.ai-sdlc/kit.json" layout)"        '"embedded"'
check fresh_version  "$(jqp "$tmp/acme/.ai-sdlc/kit.json" kit.version)"   '"1.2.0"'
check fresh_name     "$(jqp "$tmp/acme/.ai-sdlc/kit.json" project.name)"  '"Acme Wallet"'
check fresh_hooks    "$(jqp "$tmp/acme/.ai-sdlc/kit.json" hooks)"         '"kit"'
rm -rf "$tmp"

# --- 2. merge into a populated project ---------------------------------------------
tmp=$(mktemp -d); proj="$tmp/api"; mkdir -p "$proj/src"
printf '# Acme API\n\nOur own readme.\n' > "$proj/README.md"
printf 'dist/\n' > "$proj/.gitignore"
printf 'console.log(1)\n' > "$proj/src/index.js"
( cd "$proj" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Acme API" --slug acme-api --dir "$proj" --desc "api" --ticket ACME \
        --layout embedded --merge --non-interactive >/dev/null 2>&1
check merge_kept_readme "$(head -1 "$proj/README.md")" "# Acme API"
check merge_block_once  "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$proj/README.md")" "1"
check merge_kept_ignore "$(head -1 "$proj/.gitignore")" "dist/"
check merge_kept_src    "$(cat "$proj/src/index.js")" "console.log(1)"
check merge_added_kit   "$([ -f "$proj/AGENTS.md" ] && echo yes)" "yes"
check merge_report      "$([ -f "$proj/.ai-sdlc/install-report.md" ] && echo yes)" "yes"

# --- 3. idempotence: a second run changes nothing structurally ----------------------
sum_before=$(cat "$proj/README.md" | wc -l | tr -d ' ')
"$BOOT" --name "Acme API" --slug acme-api --dir "$proj" --desc "api" --ticket ACME \
        --layout embedded --merge --non-interactive >/dev/null 2>&1
idem_rc=$?
check idem_exit_zero "$idem_rc" "0"
check idem_block_once "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$proj/README.md")" "1"
check idem_same_lines "$(cat "$proj/README.md" | wc -l | tr -d ' ')" "$sum_before"
rm -rf "$tmp"

# --- 3b. a full --merge install run twice end to end reaches completion ------------
# Regression guard: bootstrap.sh must not abort partway through a repeat
# --merge run (see substitute()'s "no placeholders left to replace" case) —
# it must reach the manifest, README block, pointers and install report both
# times, with README.md still carrying exactly one kit block.
tmp=$(mktemp -d); proj2="$tmp/api2"; mkdir -p "$proj2/src"
printf '# Acme API 2\n\nOur own readme.\n' > "$proj2/README.md"
printf 'dist/\n' > "$proj2/.gitignore"
( cd "$proj2" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Acme API 2" --slug acme-api-2 --dir "$proj2" --desc "api" --ticket ACME \
        --layout embedded --tools "claude,gemini" --merge --non-interactive >/dev/null 2>&1
check e2e_run1_exit "$?" "0"
"$BOOT" --name "Acme API 2" --slug acme-api-2 --dir "$proj2" --desc "api" --ticket ACME \
        --layout embedded --tools "claude,gemini" --merge --non-interactive >/dev/null 2>&1
check e2e_run2_exit "$?" "0"
check e2e_manifest         "$([ -f "$proj2/.ai-sdlc/kit.json" ] && echo yes)" "yes"
check e2e_report           "$([ -f "$proj2/.ai-sdlc/install-report.md" ] && echo yes)" "yes"
check e2e_readme_block     "$(grep -c 'how we work with AI here' "$proj2/README.md")" "1"
check e2e_readme_one_block "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$proj2/README.md")" "1"
check e2e_claude_ptr       "$(grep -c '@AGENTS.md' "$proj2/CLAUDE.md")" "1"
check e2e_gemini_ptr       "$([ -f "$proj2/.gemini/settings.json" ] && echo yes)" "yes"
rm -rf "$tmp"

# --- 4. repos + layout are recorded ------------------------------------------------
tmp=$(mktemp -d)
"$BOOT" --name "Acme" --slug acme --dir "$tmp/sdlc" --desc "d" --ticket ACME \
        --layout sidecar --repos "../acme-api=backend,../acme-web=frontend" \
        --tools "claude,copilot" --non-interactive >/dev/null 2>&1
check repos_layout "$(jqp "$tmp/sdlc/.ai-sdlc/kit.json" layout)" '"sidecar"'
check repos_count  "$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))["repos"]))' "$tmp/sdlc/.ai-sdlc/kit.json")" "2"
check repos_role   "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["repos"][0]["role"])' "$tmp/sdlc/.ai-sdlc/kit.json")" "backend"
check repos_tools  "$(python3 -c 'import json,sys;print(",".join(json.load(open(sys.argv[1]))["tools"]))' "$tmp/sdlc/.ai-sdlc/kit.json")" "claude,copilot"
check agents_table "$(grep -c 'acme-api' "$tmp/sdlc/AGENTS.md")" "1"
rm -rf "$tmp"

# --- 5. --no-git and --hooks none ---------------------------------------------------
tmp=$(mktemp -d)
"$BOOT" --name "NoGit" --slug nogit --dir "$tmp/ng" --desc "d" --ticket NG \
        --no-git --hooks none --non-interactive >/dev/null 2>&1
check nogit_no_repo "$([ -d "$tmp/ng/.git" ] && echo yes || echo no)" "no"
check nogit_hooks   "$(jqp "$tmp/ng/.ai-sdlc/kit.json" hooks)" '"none"'
rm -rf "$tmp"

# --- 5b. every layout installs and is recorded -------------------------------------
for lay in embedded monorepo sidecar parent; do
  tmp=$(mktemp -d)
  "$BOOT" --name "L $lay" --slug "l-$lay" --dir "$tmp/k" --desc "d" --ticket L \
          --layout "$lay" --non-interactive >/dev/null 2>&1
  check "layout_${lay}_agents"   "$([ -f "$tmp/k/AGENTS.md" ] && echo yes)" "yes"
  check "layout_${lay}_manifest" "$(jqp "$tmp/k/.ai-sdlc/kit.json" layout)" "\"$lay\""
  rm -rf "$tmp"
done

# --- 6. --non-interactive with a missing required value fails loudly ----------------
tmp=$(mktemp -d)
"$BOOT" --slug x --dir "$tmp/x" --non-interactive >/dev/null 2>&1
check ni_exit "$?" "2"
rm -rf "$tmp"

# --- 7. README block and pointers land in a real install ---------------------------
tmp=$(mktemp -d)
"$BOOT" --name "Acme Wallet" --slug acme-wallet --dir "$tmp/acme" --desc "d" --ticket ACME \
        --layout embedded --tools "claude,gemini" --non-interactive >/dev/null 2>&1
check readme_block  "$(grep -c 'how we work with AI here' "$tmp/acme/README.md")" "1"
check readme_layout "$(grep -c 'embedded' "$tmp/acme/README.md")" "1"
check readme_one_block  "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/acme/README.md")" "1"
check readme_no_placeholder "$(grep -c 'Installed by the' "$tmp/acme/README.md")" "0"
check claude_ptr    "$(grep -c '@AGENTS.md' "$tmp/acme/CLAUDE.md")" "1"
check gemini_ptr    "$([ -f "$tmp/acme/.gemini/settings.json" ] && echo yes)" "yes"
rm -rf "$tmp"

# --- 8. malformed pointer targets are reported, never silently accepted ------------
# Root CLAUDE.md with an ambiguous marker layout (begin, no end): the run
# must still exit 0, the file must stay byte-identical, and the install
# report must name it.
tmp=$(mktemp -d); proj="$tmp/mal"; mkdir -p "$proj"
printf '<!-- ai-sdlc-kit:begin -->\nstray CLAUDE content, no end marker\n' > "$proj/CLAUDE.md"
( cd "$proj" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Malformed Proj" --slug malformed-proj --dir "$proj" --desc "d" --ticket ACME \
        --layout embedded --tools "claude" --merge --non-interactive >/dev/null 2>&1
mal_claude_rc=$?
check mal_claude_exit      "$mal_claude_rc" "0"
check mal_claude_unchanged "$(grep -c 'stray CLAUDE content' "$proj/CLAUDE.md")" "1"
check mal_claude_reported  "$(grep -c 'malformed CLAUDE.md' "$proj/.ai-sdlc/install-report.md")" "1"
rm -rf "$tmp"

# Root .github/copilot-instructions.md, same shape.
tmp=$(mktemp -d); proj="$tmp/malc"; mkdir -p "$proj/.github"
printf '<!-- ai-sdlc-kit:begin -->\nstray copilot content, no end marker\n' > "$proj/.github/copilot-instructions.md"
( cd "$proj" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Malformed Copilot" --slug malformed-copilot --dir "$proj" --desc "d" --ticket ACME \
        --layout embedded --tools "copilot" --merge --non-interactive >/dev/null 2>&1
mal_copilot_rc=$?
check mal_copilot_exit      "$mal_copilot_rc" "0"
check mal_copilot_unchanged "$(grep -c 'stray copilot content' "$proj/.github/copilot-instructions.md")" "1"
check mal_copilot_reported  "$(grep -c 'malformed .github/copilot-instructions.md' "$proj/.ai-sdlc/install-report.md")" "1"
rm -rf "$tmp"

# .gemini/settings.json with invalid JSON: never clobbered, reported instead
# of silently rewritten (the Critical fix — was previously destroyed and
# reported as a success).
tmp=$(mktemp -d); proj="$tmp/malg"; mkdir -p "$proj/.gemini"
printf '{"theme":"dark","custom_api_keys":["SECRET-123"], invalid syntax here' > "$proj/.gemini/settings.json"
cp "$proj/.gemini/settings.json" "$tmp/gemini-before"
( cd "$proj" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Malformed Gemini" --slug malformed-gemini --dir "$proj" --desc "d" --ticket ACME \
        --layout embedded --tools "gemini" --merge --non-interactive >/dev/null 2>&1
mal_gemini_rc=$?
check mal_gemini_exit      "$mal_gemini_rc" "0"
check mal_gemini_unchanged "$(cmp -s "$tmp/gemini-before" "$proj/.gemini/settings.json" && echo same)" "same"
check mal_gemini_reported  "$(grep -c 'malformed .gemini/settings.json' "$proj/.ai-sdlc/install-report.md")" "1"
rm -rf "$tmp"

echo "---"
[ "$fails" -eq 0 ] && echo "all bootstrap tests passed" || echo "$fails test(s) failed"
exit "$fails"
