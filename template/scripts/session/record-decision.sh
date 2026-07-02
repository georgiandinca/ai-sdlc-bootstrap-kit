#!/usr/bin/env bash
# Record an ADR: write docs/architecture/decisions/ADR-<NNNN>-<slug>.md and commit.
# Never commits to a protected branch. Usage: record-decision.sh "<title>"
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
. "$here/lib.sh"
root=$(sdlc_repo_root) || { echo "[decision] not in a git repo" >&2; exit 1; }
cd "$root"

title="${1:-}"; [ -n "$title" ] || { echo "[decision] usage: record-decision.sh \"<title>\"" >&2; exit 2; }

dir="docs/architecture/decisions"; mkdir -p "$dir"
n=0
for f in "$dir"/ADR-*.md; do
  [ -e "$f" ] || continue
  num=$(basename "$f" | sed -E 's/^ADR-0*([0-9]+)-.*/\1/')
  case "$num" in ''|*[!0-9]*) continue ;; esac
  [ "$num" -gt "$n" ] && n="$num"
done
next=$(printf '%04d' $((n + 1)))
slug=$(printf '%s' "$title" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-' | cut -c1-50)
[ -z "$slug" ] && slug="decision"
file="$dir/ADR-${next}-${slug}.md"
today=$(date +%Y-%m-%d)
seat=$(sdlc_seat); [ -z "$seat" ] && seat="Architect"

cat > "$file" <<EOF
---
title: "ADR-${next}: ${title}"
status: draft
owner: Architect
author: ${seat}
created: ${today}
classification: internal
last-reviewed: ${today}
ai-trust: working
---

# ADR-${next}: ${title}

## Context

<Why is this decision needed? What forces are at play?>

## Decision

We will <state the decision as a completed choice>.

## Consequences

<Trade-offs, follow-ups, and what this enables or constrains.>
EOF

branch=$(sdlc_ensure_feature_branch "$seat" adr) || { echo "[decision] refusing to commit on a protected branch" >&2; exit 1; }
git add "$file"
git commit -q -m "docs: ADR-${next} ${title}"
echo "[decision] wrote $file and committed on $branch."
