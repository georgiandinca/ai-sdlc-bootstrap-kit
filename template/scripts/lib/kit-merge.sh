#!/usr/bin/env bash
# kit-merge.sh — marker-based merge helpers for the AI-SDLC kit installer.
#
# The kit never overwrites a file a project already owns. It either creates the
# file, or maintains its own block between markers inside it, or reports a
# collision and leaves the file byte-identical. Source this file; do not run it.
#
#   kit_merge_block <target> <content_file>   -> created | updated | appended
#   kit_copy_merge  <src_dir> <dst_dir>       -> "created|identical|collision <rel>" lines

kit_begin_marker() {
  case "$1" in
    *.md|*.markdown|*.html) printf '<!-- ai-sdlc-kit:begin -->' ;;
    *) printf '# ai-sdlc-kit:begin' ;;
  esac
}

kit_end_marker() {
  case "$1" in
    *.md|*.markdown|*.html) printf '<!-- ai-sdlc-kit:end -->' ;;
    *) printf '# ai-sdlc-kit:end' ;;
  esac
}

# kit_merge_block <target> <content_file>
kit_merge_block() {
  local target=$1 content=$2
  local begin end tmp
  begin=$(kit_begin_marker "$target")
  end=$(kit_end_marker "$target")

  if [ ! -f "$target" ]; then
    mkdir -p "$(dirname "$target")"
    { printf '%s\n' "$begin"; cat "$content"; printf '%s\n' "$end"; } > "$target"
    echo created
    return 0
  fi

  if grep -qF -- "$begin" "$target"; then
    tmp=$(mktemp)
    awk -v b="$begin" -v e="$end" -v f="$content" '
      BEGIN { while ((getline line < f) > 0) blk = blk line "\n" }
      $0 == b { print b; printf "%s", blk; print e; skip = 1; next }
      $0 == e { skip = 0; next }
      !skip   { print }
    ' "$target" > "$tmp" && mv "$tmp" "$target"
    echo updated
    return 0
  fi

  { printf '\n%s\n' "$begin"; cat "$content"; printf '%s\n' "$end"; } >> "$target"
  echo appended
}

# kit_copy_merge <src_dir> <dst_dir>
kit_copy_merge() {
  local src=$1 dst=$2 rel abs_src abs_dst
  ( cd "$src" && find . -type f -print ) | sed 's|^\./||' | sort | while read -r rel; do
    abs_src="$src/$rel"; abs_dst="$dst/$rel"
    if [ ! -e "$abs_dst" ]; then
      mkdir -p "$(dirname "$abs_dst")"
      cp -p "$abs_src" "$abs_dst"
      echo "created $rel"
    elif cmp -s "$abs_src" "$abs_dst"; then
      echo "identical $rel"
    else
      echo "collision $rel"
    fi
  done
}
