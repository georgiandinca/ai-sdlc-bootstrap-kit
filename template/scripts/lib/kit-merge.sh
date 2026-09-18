#!/usr/bin/env bash
# kit-merge.sh — marker-based merge helpers for the AI-SDLC kit installer.
#
# The kit never overwrites a file a project already owns. It either creates the
# file, or maintains its own block between markers inside it, or reports a
# collision and leaves the file byte-identical. Source this file; do not run it.
#
#   kit_merge_block <target> <content_file>   -> created | updated | appended | malformed
#   kit_copy_merge  <src_dir> <dst_dir>       -> "created|identical|collision <rel>" lines
#
# Outcomes for kit_merge_block:
#   created   — file did not exist, created with block and markers
#   appended  — file exists without markers, block appended at end
#   updated   — file has begin and end markers, block replaced in-place
#   malformed — file has begin marker but no matching end marker, file left unchanged

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
# Uses positional state machine: locates first begin marker and first end marker
# after it. Only that range is the block; lines inside are replaced by position,
# not re-matched. If begin exists without matching end, file is malformed.
kit_merge_block() {
  local target=$1 content=$2
  local begin end tmp marker_line end_line
  local norm_content
  begin=$(kit_begin_marker "$target")
  end=$(kit_end_marker "$target")

  # Normalize content: add trailing newline if missing.
  # Use a temp file to handle this safely.
  norm_content=$(mktemp)
  cat "$content" >> "$norm_content"
  [ -s "$norm_content" ] && [ -z "$(tail -c 1 "$norm_content")" ] || printf '\n' >> "$norm_content"

  if [ ! -f "$target" ]; then
    mkdir -p "$(dirname "$target")"
    { printf '%s\n' "$begin"; cat "$norm_content"; printf '%s\n' "$end"; } > "$target"
    rm -f "$norm_content"
    echo created
    return 0
  fi

  if grep -qF -- "$begin" "$target"; then
    # Find line numbers of first begin and first end marker after it
    marker_line=$(grep -nF -- "$begin" "$target" | head -1 | cut -d: -f1)
    if [ -z "$marker_line" ]; then
      rm -f "$norm_content"
      echo appended
      return 0
    fi

    # Find first end marker after the begin marker
    end_line=$(tail -n +"$marker_line" "$target" | grep -nF -- "$end" | head -1 | cut -d: -f1)
    if [ -z "$end_line" ]; then
      # Begin marker exists but no end marker found
      rm -f "$norm_content"
      echo malformed
      return 0
    fi

    # Convert end_line to absolute line number
    end_line=$((marker_line + end_line - 1))

    # Rebuild the file using line numbers
    tmp=$(mktemp)
    awk -v begin_line="$marker_line" -v end_line="$end_line" -v b="$begin" -v e="$end" -v f="$norm_content" '
      NR < begin_line { print; next }
      NR == begin_line {
        print b
        system("cat " f)
        print e
        next
      }
      NR > end_line { print; next }
    ' "$target" > "$tmp" && mv "$tmp" "$target"

    rm -f "$norm_content"
    echo updated
    return 0
  fi

  { printf '\n%s\n' "$begin"; cat "$norm_content"; printf '%s\n' "$end"; } >> "$target"
  rm -f "$norm_content"
  echo appended
}

# kit_copy_merge <src_dir> <dst_dir>
# Copies tree without overwriting. Handles both files and symlinks.
# Echoes one line per entry: created|identical|collision <rel>
kit_copy_merge() {
  local src=$1 dst=$2 rel abs_src abs_dst
  ( cd "$src" && find . \( -type f -o -type l \) -print ) | sed 's|^\./||' | sort | while read -r rel; do
    abs_src="$src/$rel"; abs_dst="$dst/$rel"
    if [ ! -e "$abs_dst" ] && [ ! -L "$abs_dst" ]; then
      # Destination doesn't exist
      mkdir -p "$(dirname "$abs_dst")"
      if [ -L "$abs_src" ]; then
        # Copy symlink as symlink (don't dereference)
        cp -P "$abs_src" "$abs_dst"
      else
        # Copy regular file
        cp -p "$abs_src" "$abs_dst"
      fi
      echo "created $rel"
    elif [ -L "$abs_src" ] && [ -L "$abs_dst" ]; then
      # Both are symlinks: check if they point to the same target
      if cmp -s "$abs_src" "$abs_dst"; then
        echo "identical $rel"
      else
        echo "collision $rel"
      fi
    elif [ ! -L "$abs_src" ] && [ ! -L "$abs_dst" ]; then
      # Both are regular files: compare content
      if cmp -s "$abs_src" "$abs_dst"; then
        echo "identical $rel"
      else
        echo "collision $rel"
      fi
    else
      # One is symlink, one is not: collision
      echo "collision $rel"
    fi
  done
}
