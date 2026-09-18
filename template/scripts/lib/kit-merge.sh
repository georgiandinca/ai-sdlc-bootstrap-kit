#!/usr/bin/env bash
# kit-merge.sh — marker-based merge helpers for the AI-SDLC kit installer.
#
# The kit never overwrites a file a project already owns. It either creates the
# file, or maintains its own block between markers inside it, or reports a
# collision and leaves the file byte-identical. Source this file; do not run it.
#
#   kit_merge_block <target> <content_file> [root]
#       -> created | updated | appended | malformed | unwritable | escaped
#   kit_copy_merge  <src_dir> <dst_dir>
#       -> "created|identical|collision|unwritable|escaped <rel>" lines
#
# Outcomes for kit_merge_block:
#   created    — file did not exist, created with block and markers
#   appended   — file exists without begin marker, block appended at end
#   updated    — file has exactly one begin marker, exactly one end marker (in order),
#                and no begin marker exists (or a single clean block), replaced in-place
#   malformed  — file has ambiguous marker layout (no end marker, multiple markers,
#                end before begin, or more than one complete block) file left unchanged
#   unwritable — the target could not be written: a read-only file, a path
#                component that exists as a regular file, or any other write
#                failure. Nothing is written; the target stays byte-identical.
#                Without this outcome the caller's result variable came back
#                EMPTY and the failure was reported as a success.
#   escaped    — the target, or a directory component of it, is a symlink that
#                resolves outside <root>. Nothing is written. Only checked when
#                a <root> is passed; spec §4 forbids writing outside the
#                confirmed target paths.
#
# An existing symlink inside <root> is written *through*, never replaced: the
# link survives the merge instead of forking into a regular file.
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

# _kit_physical_dir <path>
# Print the physical directory a write to <path> would actually land in.
# Symlinks on the final component are followed (up to 32 hops, so a link cycle
# terminates), then the nearest existing ancestor directory is resolved with
# `cd -P` — which also resolves any symlinked directory component, such as a
# project's `docs -> ../elsewhere/docs`. Prints nothing and returns 1 when no
# ancestor can be resolved. No `readlink -f`/`realpath`: neither is portable to
# the macOS bash 3.2 floor.
_kit_physical_dir() {
  local path=$1 hops=0 link dir
  while [ -L "$path" ] && [ "$hops" -lt 32 ]; do
    link=$(readlink "$path") || return 1
    case "$link" in
      /*) path=$link ;;
      *)  path="$(dirname "$path")/$link" ;;
    esac
    hops=$((hops + 1))
  done
  dir=$(dirname "$path")
  while [ ! -d "$dir" ]; do
    case "$dir" in /|.|"") return 1 ;; esac
    dir=$(dirname "$dir")
  done
  ( cd "$dir" 2>/dev/null && pwd -P )
}

# _kit_escapes_root <path> <root>
# True (exit 0) when a write to <path> would land outside <root> — because the
# path itself is a symlink leaving the tree, or because a parent directory
# component is. An empty <root> disables the check.
_kit_escapes_root() {
  local path=$1 root=$2 root_abs phys
  [ -n "$root" ] || return 1
  root_abs=$(cd "$root" 2>/dev/null && pwd -P) || return 1
  phys=$(_kit_physical_dir "$path") || return 1
  [ -n "$phys" ] || return 1
  case "$phys/" in
    "$root_abs"/*) return 1 ;;
    *) return 0 ;;
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

# kit_merge_block <target> <content_file> [root]
# Uses positional state machine: locates first begin marker and first end marker
# after it. Only that range is the block; lines inside are replaced by position,
# not re-matched. If begin exists without matching end, file is malformed.
# Block content is sanitised to prevent marker lookalikes.
# When <root> is given, a target that resolves outside it through a symlink is
# refused (`escaped`) instead of written.
kit_merge_block() {
  local target=$1 content=$2 root=${3:-}
  local begin end tmp marker_line end_line
  local norm_content
  begin=$(kit_begin_marker "$target")
  end=$(kit_end_marker "$target")

  if _kit_escapes_root "$target" "$root"; then
    echo escaped
    return 0
  fi

  # A target we cannot write is a non-clobber outcome, not a silent failure:
  # the redirects below would otherwise fail, skip the `echo`, and hand the
  # caller an empty result while the run went on reporting success.
  if [ -e "$target" ] && [ ! -w "$target" ]; then
    echo unwritable
    return 0
  fi

  # Normalize and sanitise content: ensure trailing newline, escape marker lookalikes
  norm_content=$(mktemp)
  {
    _sanitise_content "$content" "$begin" "$end"
    [ -z "$(tail -c 1 "$content")" ] || printf '\n'
  } >> "$norm_content"

  if [ ! -f "$target" ]; then
    if ! mkdir -p "$(dirname "$target")" 2>/dev/null; then
      rm -f "$norm_content"
      echo unwritable
      return 0
    fi
    if ! ( { printf '%s\n' "$begin"; cat "$norm_content"; printf '%s\n' "$end"; } > "$target" ) 2>/dev/null; then
      rm -f "$norm_content"
      echo unwritable
      return 0
    fi
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
    ' "$target" > "$tmp"

    # Write *through* an existing symlink rather than replacing it: `mv` would
    # swap the link for a regular file, destroying the link and forking the
    # content away from whatever else points at it.
    if [ -L "$target" ]; then
      if ! ( cat "$tmp" > "$target" ) 2>/dev/null; then
        rm -f "$norm_content" "$tmp"
        echo unwritable
        return 0
      fi
      rm -f "$tmp"
    elif ! mv "$tmp" "$target" 2>/dev/null; then
      rm -f "$norm_content" "$tmp"
      echo unwritable
      return 0
    fi

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

  if ! ( { printf '\n%s\n' "$begin"; cat "$norm_content"; printf '%s\n' "$end"; } >> "$target" ) 2>/dev/null; then
    rm -f "$norm_content"
    echo unwritable
    return 0
  fi
  rm -f "$norm_content"
  echo appended
}

# kit_copy_merge <src_dir> <dst_dir>
# Copies tree without overwriting. Handles both files and symlinks.
# Echoes one line per entry: created|identical|collision|unwritable|escaped <rel>
#   escaped    — the destination path leaves <dst_dir> through a symlink (its
#                own, or a parent directory's, e.g. `docs -> ../elsewhere/docs`)
#   unwritable — a path component the kit needs as a directory exists as a
#                regular file, or the copy itself failed. One file is skipped
#                and reported; the install carries on.
kit_copy_merge() {
  local src=$1 dst=$2 rel abs_src abs_dst
  ( cd "$src" && find . \( -type f -o -type l \) -print ) | sed 's|^\./||' | sort | while read -r rel; do
    abs_src="$src/$rel"; abs_dst="$dst/$rel"
    if _kit_escapes_root "$abs_dst" "$dst"; then
      # Writing here would land outside the confirmed target (spec §4).
      echo "escaped $rel"
      continue
    fi
    if [ ! -e "$abs_dst" ] && [ ! -L "$abs_dst" ]; then
      # Destination doesn't exist
      if ! mkdir -p "$(dirname "$abs_dst")" 2>/dev/null; then
        # A component the kit needs as a directory is a regular file the
        # project owns. Skip this file, keep theirs, keep installing — an
        # abort here used to kill the run mid-tree via `set -e`.
        echo "unwritable $rel"
        continue
      fi
      if [ -L "$abs_src" ]; then
        # Copy symlink as symlink (don't dereference)
        cp -P "$abs_src" "$abs_dst" 2>/dev/null || { echo "unwritable $rel"; continue; }
      else
        # Copy regular file
        cp -p "$abs_src" "$abs_dst" 2>/dev/null || { echo "unwritable $rel"; continue; }
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
