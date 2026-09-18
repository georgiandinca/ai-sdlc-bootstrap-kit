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

# --- 6. malformed file: begin marker without end marker -> returns malformed, file byte-identical
printf '# Start\n\n<!-- ai-sdlc-kit:begin -->\nold block\n## Our project section\n' > "$tmp/malformed.md"
malformed_before=$(cat "$tmp/malformed.md")
result=$(kit_merge_block "$tmp/malformed.md" "$tmp/block.txt")
check malformed "$(echo "$result")" "malformed"
check malformed_unchanged "$(cat "$tmp/malformed.md")" "$malformed_before"
check malformed_content_preserved "$(grep -c 'Our project section' "$tmp/malformed.md")" "1"

# --- 7. multiple updates maintain single block: idempotence test
printf 'first update content\n' > "$tmp/update1.txt"
printf 'second update content\n' > "$tmp/update2.txt"
kit_merge_block "$tmp/multi_update.md" "$tmp/update1.txt" >/dev/null
count_after_first=$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/multi_update.md")
kit_merge_block "$tmp/multi_update.md" "$tmp/update2.txt" >/dev/null
count_after_second=$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/multi_update.md")
check multi_update_consistent "$([ "$count_after_first" = "$count_after_second" ] && echo same || echo diff)" "same"
check multi_update_one_block "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/multi_update.md")" "1"

# --- 8. symlinks in source tree: copied as symlinks, reported with own line
mkdir -p "$tmp/symlink_src" "$tmp/symlink_dst"
printf 'regular file\n' > "$tmp/symlink_src/regular.txt"
ln -s regular.txt "$tmp/symlink_src/link_to_regular.txt"
symlink_report=$(kit_copy_merge "$tmp/symlink_src" "$tmp/symlink_dst")
check symlink_reported "$(printf '%s\n' "$symlink_report" | grep -c '^created link_to_regular.txt$')" "1"
check symlink_is_link "$([ -L "$tmp/symlink_dst/link_to_regular.txt" ] && echo yes || echo no)" "yes"
check symlink_regular_also_copied "$([ -f "$tmp/symlink_dst/regular.txt" ] && echo yes || echo no)" "yes"

# --- 9. content without trailing newline: end marker lands on own line, idempotent
printf 'no newline at end' > "$tmp/no_newline.txt"
kit_merge_block "$tmp/no_newline_target.md" "$tmp/no_newline.txt" >/dev/null
check no_newline_marker_on_own_line "$(tail -1 "$tmp/no_newline_target.md")" "<!-- ai-sdlc-kit:end -->"
# Second call with different content
printf 'changed content' > "$tmp/changed.txt"
result=$(kit_merge_block "$tmp/no_newline_target.md" "$tmp/changed.txt")
check no_newline_second_call "$(echo "$result")" "updated"
check no_newline_block_count "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/no_newline_target.md")" "1"

# --- 10. content with line equal to END marker: update with sanitisation
printf '# Project\n' > "$tmp/project.md"
printf 'initial content\n' > "$tmp/initial.txt"
kit_merge_block "$tmp/project.md" "$tmp/initial.txt" >/dev/null
# Now update with content containing a line equal to the end marker
printf 'block content\n<!-- ai-sdlc-kit:end -->\nmore block\n' > "$tmp/marker_lookalike.txt"
kit_merge_block "$tmp/project.md" "$tmp/marker_lookalike.txt" >/dev/null
count_begin=$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/project.md")
count_end=$(grep -c -- '<!-- ai-sdlc-kit:end -->' "$tmp/project.md")
check end_lookalike_one_begin "$(grep -cx -- '<!-- ai-sdlc-kit:begin -->' "$tmp/project.md")" "1"
check end_lookalike_one_end "$(grep -cx -- '<!-- ai-sdlc-kit:end -->' "$tmp/project.md")" "1"
check end_lookalike_project_preserved "$(grep -c '^# Project$' "$tmp/project.md")" "1"
check end_lookalike_content_present "$(grep -c 'block content' "$tmp/project.md")" "1"
# "more block" is content that should be preserved
check end_lookalike_more_block_present "$(grep -c '^more block$' "$tmp/project.md")" "1"
# The sanitised line should be present with trailing space
check end_lookalike_sanitised_present "$(grep -c '^<!-- ai-sdlc-kit:end --> $' "$tmp/project.md")" "1"

# --- 11. content with lines equal to BOTH markers: sanitisation preserves both
printf '# Project2\n' > "$tmp/project2.md"
printf 'first\n' > "$tmp/first.txt"
kit_merge_block "$tmp/project2.md" "$tmp/first.txt" >/dev/null
# Update with content containing both markers
printf '<!-- ai-sdlc-kit:begin -->\nmiddle content\n<!-- ai-sdlc-kit:end -->\nafter block\n' > "$tmp/both_markers.txt"
kit_merge_block "$tmp/project2.md" "$tmp/both_markers.txt" >/dev/null
count_begin2=$(grep -cx -- '<!-- ai-sdlc-kit:begin -->' "$tmp/project2.md")
count_end2=$(grep -cx -- '<!-- ai-sdlc-kit:end -->' "$tmp/project2.md")
check both_one_begin "$(echo "$count_begin2")" "1"
check both_one_end "$(echo "$count_end2")" "1"
check both_project_preserved "$(grep -c '^# Project2$' "$tmp/project2.md")" "1"
check both_marker_begin_sanitised "$(grep -c '^<!-- ai-sdlc-kit:begin --> $' "$tmp/project2.md")" "1"
check both_marker_end_sanitised "$(grep -c '^<!-- ai-sdlc-kit:end --> $' "$tmp/project2.md")" "1"

# --- 12. unsanitised marker lookalike in existing block: ambiguous layout -> malformed
printf '# Header\n<!-- ai-sdlc-kit:begin -->\nold content\n<!-- ai-sdlc-kit:end -->\n<!-- ai-sdlc-kit:end -->\n## Project footer\n' > "$tmp/ambig.md"
ambig_before=$(cat "$tmp/ambig.md")
result=$(kit_merge_block "$tmp/ambig.md" "$tmp/update1.txt")
check ambig_unsanitised_malformed "$(echo "$result")" "malformed"
check ambig_unsanitised_unchanged "$(cat "$tmp/ambig.md")" "$ambig_before"
check ambig_unsanitised_project_intact "$(grep -c '^## Project footer$' "$tmp/ambig.md")" "1"

# --- 13. file with two complete kit blocks: ambiguous -> malformed
printf '# Header\n<!-- ai-sdlc-kit:begin -->\nblock 1\n<!-- ai-sdlc-kit:end -->\n# Middle\n<!-- ai-sdlc-kit:begin -->\nblock 2\n<!-- ai-sdlc-kit:end -->\n# Footer\n' > "$tmp/two_blocks.md"
two_before=$(cat "$tmp/two_blocks.md")
result=$(kit_merge_block "$tmp/two_blocks.md" "$tmp/update1.txt")
check two_blocks_malformed "$(echo "$result")" "malformed"
check two_blocks_unchanged "$(cat "$tmp/two_blocks.md")" "$two_before"

# --- 14. file with end marker but no begin marker: ambiguous -> malformed
printf '# Header\nContent line\n<!-- ai-sdlc-kit:end -->\nFooter\n' > "$tmp/end_only.md"
end_before=$(cat "$tmp/end_only.md")
result=$(kit_merge_block "$tmp/end_only.md" "$tmp/update1.txt")
check end_only_malformed "$(echo "$result")" "malformed"
check end_only_unchanged "$(cat "$tmp/end_only.md")" "$end_before"

# --- 15. normal single-block update still works (idempotence check)
printf '# Test\n' > "$tmp/normal.md"
printf 'content\n' > "$tmp/c1.txt"
kit_merge_block "$tmp/normal.md" "$tmp/c1.txt" >/dev/null
result1=$(kit_merge_block "$tmp/normal.md" "$tmp/c1.txt")
check idempotent_update "$(echo "$result1")" "updated"
check idempotent_one_begin "$(grep -cx -- '<!-- ai-sdlc-kit:begin -->' "$tmp/normal.md")" "1"
check idempotent_one_end "$(grep -cx -- '<!-- ai-sdlc-kit:end -->' "$tmp/normal.md")" "1"

rm -rf "$tmp"
echo "---"
[ "$fails" -eq 0 ] && echo "all kit-merge tests passed" || echo "$fails test(s) failed"
exit "$fails"
