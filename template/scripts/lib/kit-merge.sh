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
#   appended  — file exists without begin marker, block appended at end
#   updated   — file has exactly one begin marker, exactly one end marker (in order),
#               and no begin marker exists (or a single clean block), replaced in-place
#   malformed — file has ambiguous marker layout (no end marker, multiple markers,
#               end before begin, or more than one complete block) file left unchanged
#
# Content sanitisation: lines in the block that are exactly equal to a marker
# are written with a trailing space appended, preventing false marker detection
# on future reads. The trailing space is invisible in rendered Markdown/HTML;
# markers themselves are byte-exact.

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

# Sanitise content: append trailing space to any line that equals a marker.
# This prevents those lines from being mistaken for the actual markers on
# future reads. Reads from a file, writes to stdout with sanitised content.
_sanitise_content() {
  local content=$1 begin=$2 end=$3
  awk -v b="$begin" -v e="$end" '{
    if ($0 == b || $0 == e) {
      print $0 " "
    } else {
      print
    }
  }' "$content"
}

# kit_merge_block <target> <content_file>
# Uses positional state machine: locates first begin marker and first end marker
# after it. Only that range is the block; lines inside are replaced by position,
# not re-matched. If begin exists without matching end, file is malformed.
# Block content is sanitised to prevent marker lookalikes.
kit_merge_block() {
  local target=$1 content=$2
  local begin end tmp marker_line end_line
  local norm_content
  begin=$(kit_begin_marker "$target")
  end=$(kit_end_marker "$target")

  # Normalize and sanitise content: ensure trailing newline, escape marker lookalikes
  norm_content=$(mktemp)
  {
    _sanitise_content "$content" "$begin" "$end"
    [ -z "$(tail -c 1 "$content")" ] || printf '\n'
  } >> "$norm_content"

  if [ ! -f "$target" ]; then
    mkdir -p "$(dirname "$target")"
    { printf '%s\n' "$begin"; cat "$norm_content"; printf '%s\n' "$end"; } > "$target"
    rm -f "$norm_content"
    echo created
    return 0
  fi

  if grep -qFx -- "$begin" "$target"; then
    # Ambiguity check: count markers to ensure unambiguous layout
    begin_count=$(grep -cFx -- "$begin" "$target")
    end_count=$(grep -cFx -- "$end" "$target")

    # Require exactly one of each marker
    if [ "$begin_count" != "1" ] || [ "$end_count" != "1" ]; then
      rm -f "$norm_content"
      echo malformed
      return 0
    fi

    # Find line numbers of the markers (exact line match)
    marker_line=$(grep -nFx -- "$begin" "$target" | cut -d: -f1)
    end_line=$(grep -nFx -- "$end" "$target" | cut -d: -f1)

    # Require end marker to come after begin marker
    if [ "$end_line" -le "$marker_line" ]; then
      rm -f "$norm_content"
      echo malformed
      return 0
    fi

    # Rebuild the file using line numbers
    tmp=$(mktemp)
    awk -v begin_line="$marker_line" -v end_line="$end_line" -v b="$begin" -v e="$end" -v f="$norm_content" '
      NR < begin_line { print; next }
      NR == begin_line {
        print b
        while ((getline line < f) > 0) print line
        close(f)
        print e
        next
      }
      NR > end_line { print; next }
    ' "$target" > "$tmp" && mv "$tmp" "$target"

    rm -f "$norm_content" "$tmp"
    echo updated
    return 0
  fi

  # No begin marker found. Check if there's an orphaned end marker (malformed)
  if grep -qFx -- "$end" "$target"; then
    rm -f "$norm_content"
    echo malformed
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
