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

# --- 16. fix-round 2, finding 4: never write outside the destination root -----------
# A project whose `docs/` is a symlink to somewhere else used to receive the
# whole kit `docs/` tree into that other place, and a symlinked README.md used
# to get the kit block appended to a file outside the project.
tmp2=$(mktemp -d)
mkdir -p "$tmp2/outside/docs" "$tmp2/proj" "$tmp2/src/docs"
printf 'their file\n' > "$tmp2/outside/README.md"
printf 'kit guide\n'  > "$tmp2/src/docs/guide.md"
printf 'kit readme\n' > "$tmp2/src/README.md"
ln -s ../outside/docs      "$tmp2/proj/docs"
ln -s ../outside/README.md "$tmp2/proj/README.md"
outside_before=$(cat "$tmp2/outside/README.md")
esc_report=$(kit_copy_merge "$tmp2/src" "$tmp2/proj")
check escape_dir_reported   "$(printf '%s\n' "$esc_report" | grep -c '^escaped docs/guide.md$')" "1"
check escape_dir_not_written "$([ -e "$tmp2/outside/docs/guide.md" ] && echo written || echo none)" "none"
check escape_file_reported  "$(printf '%s\n' "$esc_report" | grep -c '^escaped README.md$')" "1"
check escape_file_untouched "$(cat "$tmp2/outside/README.md")" "$outside_before"
# kit_merge_block must refuse the same symlinked target …
printf 'kit block\n' > "$tmp2/blk.txt"
check escape_block_result  "$(kit_merge_block "$tmp2/proj/README.md" "$tmp2/blk.txt" "$tmp2/proj")" "escaped"
check escape_block_untouched "$(cat "$tmp2/outside/README.md")" "$outside_before"
check escape_block_still_link "$([ -L "$tmp2/proj/README.md" ] && echo link || echo file)" "link"
# … and a symlinked path under a symlinked directory component too.
check escape_nested_result "$(kit_merge_block "$tmp2/proj/docs/NOTES.md" "$tmp2/blk.txt" "$tmp2/proj")" "escaped"
check escape_nested_none   "$([ -e "$tmp2/outside/docs/NOTES.md" ] && echo written || echo none)" "none"
# With no root given the check is off — the old two-argument callers still work.
check escape_no_root_ok "$(kit_merge_block "$tmp2/proj/plain.md" "$tmp2/blk.txt")" "created"
rm -rf "$tmp2"

# --- 17. fix-round 2, finding 4 (part 3): an in-tree symlink is written THROUGH -----
# A second run used to `mv` a regular file over the symlink, destroying the link
# and forking the content away from whatever else pointed at it.
tmp2=$(mktemp -d)
printf '# Real\n' > "$tmp2/real.md"
ln -s real.md "$tmp2/link.md"
printf 'v1\n' > "$tmp2/v1.txt"
printf 'v2\n' > "$tmp2/v2.txt"
check inlink_append "$(kit_merge_block "$tmp2/link.md" "$tmp2/v1.txt" "$tmp2")" "appended"
check inlink_update "$(kit_merge_block "$tmp2/link.md" "$tmp2/v2.txt" "$tmp2")" "updated"
check inlink_still_link "$([ -L "$tmp2/link.md" ] && echo link || echo file)" "link"
check inlink_target_got_it "$(grep -c '^v2$' "$tmp2/real.md")" "1"
check inlink_one_block "$(grep -cx -- '<!-- ai-sdlc-kit:begin -->' "$tmp2/real.md")" "1"
rm -rf "$tmp2"

# --- 18. fix-round 2, finding 5: a read-only mergeable file is a known outcome ------
# The append used to fail the redirect, skip the `echo`, and hand the caller an
# EMPTY result while two "Permission denied" lines went to stderr and the run
# exited 0 saying "Done."
if [ "$(id -u)" != "0" ]; then
  tmp2=$(mktemp -d)
  printf '# Theirs\n' > "$tmp2/ro.md"
  ro_before=$(cat "$tmp2/ro.md")
  chmod 444 "$tmp2/ro.md"
  printf 'kit block\n' > "$tmp2/blk.txt"
  ro_result=$(kit_merge_block "$tmp2/ro.md" "$tmp2/blk.txt" "$tmp2" 2>"$tmp2/stderr.log")
  check readonly_result     "$ro_result" "unwritable"
  check readonly_not_empty  "$([ -n "$ro_result" ] && echo nonempty || echo EMPTY)" "nonempty"
  check readonly_unchanged  "$(cat "$tmp2/ro.md")" "$ro_before"
  check readonly_silent     "$(grep -c 'Permission denied' "$tmp2/stderr.log")" "0"
  # …and on the update path too (an existing block in a now read-only file).
  printf '# Theirs2\n' > "$tmp2/ro2.md"
  kit_merge_block "$tmp2/ro2.md" "$tmp2/blk.txt" "$tmp2" >/dev/null
  ro2_before=$(cat "$tmp2/ro2.md")
  chmod 444 "$tmp2/ro2.md"
  printf 'changed\n' > "$tmp2/blk2.txt"
  check readonly_update_result    "$(kit_merge_block "$tmp2/ro2.md" "$tmp2/blk2.txt" "$tmp2" 2>/dev/null)" "unwritable"
  check readonly_update_unchanged "$(cat "$tmp2/ro2.md")" "$ro2_before"
  chmod 644 "$tmp2/ro.md" "$tmp2/ro2.md"
  rm -rf "$tmp2"
else
  echo "skip readonly_* (running as root: mode 0444 is still writable)"
fi

# --- 19. fix-round 2, finding 6: a needed directory that exists as a file -----------
# `mkdir -p` failed and `set -e` killed bootstrap mid-install. It is now a
# per-file outcome: skip that file, report it, keep copying the rest.
tmp2=$(mktemp -d)
mkdir -p "$tmp2/src/docs" "$tmp2/dst"
printf 'kit guide\n' > "$tmp2/src/docs/guide.md"
printf 'kit top\n'   > "$tmp2/src/TOP.md"
printf 'their notes, not a directory\n' > "$tmp2/dst/docs"
docs_before=$(cat "$tmp2/dst/docs")
blocked_report=$(kit_copy_merge "$tmp2/src" "$tmp2/dst")
blocked_rc=$?
check blocked_rc_zero     "$blocked_rc" "0"
check blocked_reported    "$(printf '%s\n' "$blocked_report" | grep -c '^unwritable docs/guide.md$')" "1"
check blocked_theirs_kept "$(cat "$tmp2/dst/docs")" "$docs_before"
check blocked_kept_going  "$(printf '%s\n' "$blocked_report" | grep -c '^created TOP.md$')" "1"
check blocked_other_file  "$([ -f "$tmp2/dst/TOP.md" ] && echo yes || echo no)" "yes"
# kit_merge_block reports the same condition rather than aborting.
printf 'kit block\n' > "$tmp2/blk.txt"
check blocked_merge_result "$(kit_merge_block "$tmp2/dst/docs/NEW.md" "$tmp2/blk.txt" "$tmp2/dst" 2>/dev/null)" "unwritable"
check blocked_merge_kept   "$(cat "$tmp2/dst/docs")" "$docs_before"
rm -rf "$tmp2"

rm -rf "$tmp"
echo "---"
[ "$fails" -eq 0 ] && echo "all kit-merge tests passed" || echo "$fails test(s) failed"
exit "$fails"
