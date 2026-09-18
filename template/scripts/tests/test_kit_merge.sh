#!/usr/bin/env bash
# Functional test for kit-merge.sh (no framework). Exits non-zero on any failure.
set -uo pipefail
SRC_ROOT=$(cd "$(dirname "$0")/../.." && pwd)     # …/template
LIB="$SRC_ROOT/scripts/lib/kit-merge.sh"
fails=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got '$2' want '$3'"; fails=$((fails+1)); fi; }

# shellcheck source=/dev/null
. "$LIB"

tmp=$(mktemp -d)
printf 'kit line one\nkit line two\n' > "$tmp/block.txt"

# --- 1. target absent -> created, with markers -------------------------------------
check created "$(kit_merge_block "$tmp/NEW.md" "$tmp/block.txt")" "created"
check created_has_begin "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/NEW.md")" "1"
check created_has_body  "$(grep -c 'kit line one' "$tmp/NEW.md")" "1"

# --- 2. project-owned file -> appended, original content untouched ------------------
printf '# Acme API\n\nOur own readme.\n' > "$tmp/README.md"
before=$(head -3 "$tmp/README.md")
check appended "$(kit_merge_block "$tmp/README.md" "$tmp/block.txt")" "appended"
check appended_kept_original "$(head -3 "$tmp/README.md")" "$before"
check appended_one_block "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/README.md")" "1"

# --- 3. second run with new content -> updated in place, still ONE block ------------
printf 'kit line CHANGED\n' > "$tmp/block2.txt"
check updated "$(kit_merge_block "$tmp/README.md" "$tmp/block2.txt")" "updated"
check updated_one_block "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/README.md")" "1"
check updated_new_body  "$(grep -c 'kit line CHANGED' "$tmp/README.md")" "1"
check updated_old_gone  "$(grep -c 'kit line one' "$tmp/README.md")" "0"
check updated_kept_original "$(head -3 "$tmp/README.md")" "$before"

# --- 4. hash-comment file gets hash markers ----------------------------------------
printf 'node_modules/\n' > "$tmp/.gitignore"
kit_merge_block "$tmp/.gitignore" "$tmp/block.txt" >/dev/null
check hash_marker "$(grep -c '^# ai-sdlc-kit:begin$' "$tmp/.gitignore")" "1"
check hash_no_html "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/.gitignore")" "0"

# --- 5. kit_copy_merge: create missing, keep existing, report collisions ------------
mkdir -p "$tmp/src/docs" "$tmp/dst"
printf 'kit version\n'    > "$tmp/src/AGENTS.md"
printf 'kit doc\n'        > "$tmp/src/docs/guide.md"
printf 'kit identical\n'  > "$tmp/src/SAME.md"
printf 'project version\n' > "$tmp/dst/AGENTS.md"
printf 'kit identical\n'   > "$tmp/dst/SAME.md"
report=$(kit_copy_merge "$tmp/src" "$tmp/dst")
check copy_created   "$(printf '%s\n' "$report" | grep -c '^created docs/guide.md$')" "1"
check copy_collision "$(printf '%s\n' "$report" | grep -c '^collision AGENTS.md$')"   "1"
check copy_identical "$(printf '%s\n' "$report" | grep -c '^identical SAME.md$')"     "1"
check copy_untouched "$(cat "$tmp/dst/AGENTS.md")" "project version"

rm -rf "$tmp"
echo "---"
[ "$fails" -eq 0 ] && echo "all kit-merge tests passed" || echo "$fails test(s) failed"
exit "$fails"
