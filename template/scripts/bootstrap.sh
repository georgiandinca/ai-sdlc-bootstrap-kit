#!/usr/bin/env bash
# bootstrap.sh — initialise a new AI-augmented SDLC project from this template.
#
# Copies the template into a target directory, substitutes the <PLACEHOLDERS>,
# initialises git, and installs the hooks. Idempotent-ish: refuses to clobber a
# non-empty target unless --force is given.
#
# Usage:
#   scripts/bootstrap.sh --name "My Project" --slug my-project --dir ../my-project \
#       [--desc "one line"] [--ticket PROJ] [--host github] [--force]
#
# Run it from the template root (the folder containing AGENTS.md). When invoked
# from the kit, point --dir at where the new project should live.
set -euo pipefail

TEMPLATE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

name=""; slug=""; dir=""; desc="<ONE_LINE_DESCRIPTION>"; ticket="<TICKET>"; host="github"; force=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --name)   name=${2:?}; shift 2 ;;
    --slug)   slug=${2:?}; shift 2 ;;
    --dir)    dir=${2:?}; shift 2 ;;
    --desc)   desc=${2:?}; shift 2 ;;
    --ticket) ticket=${2:?}; shift 2 ;;
    --host)   host=${2:?}; shift 2 ;;
    --force)  force=1; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "bootstrap: unknown arg: $1" >&2; exit 2 ;;
  esac
done

[ -n "$name" ] || { echo "bootstrap: --name is required" >&2; exit 2; }
[ -n "$dir" ]  || { echo "bootstrap: --dir is required"  >&2; exit 2; }
[ -n "$slug" ] || slug=$(printf '%s' "$name" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-')

if [ -d "$dir" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ] && [ "$force" -ne 1 ]; then
  echo "bootstrap: target '$dir' exists and is not empty (use --force to override)" >&2
  exit 1
fi

echo "[bootstrap] project=$name slug=$slug host=$host -> $dir"
mkdir -p "$dir"

# Copy everything except VCS noise and local artifacts.
( cd "$TEMPLATE_ROOT" && \
  tar --exclude='.git' --exclude='node_modules' --exclude='.venv' \
      --exclude='__pycache__' --exclude='*.pyc' --exclude='docs/knowledge/.index' \
      -cf - . ) | ( cd "$dir" && tar -xf - )

cd "$dir"

# Per-user example -> not the real file; the real USER.md is created at onboarding.
[ -f USER.md.example ] && echo "[bootstrap] kept USER.md.example (real USER.md is created at onboarding)"

# Placeholder substitution across text files (skip binaries / vcs / deps).
substitute() {
  local find_str="$1" repl="$2"
  grep -rlI --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv \
       --exclude-dir=__pycache__ -- "$find_str" . 2>/dev/null | while read -r f; do
    # portable in-place sed (BSD/GNU)
    sed -i.bak "s|${find_str}|${repl}|g" "$f" && rm -f "$f.bak"
  done
}
substitute "<PROJECT_NAME>" "$name"
substitute "<ONE_LINE_DESCRIPTION>" "$desc"
substitute "<TICKET>" "$ticket"

echo "[bootstrap] substituted <PROJECT_NAME>, <ONE_LINE_DESCRIPTION>, <TICKET>."
echo "[bootstrap] remaining placeholders to fill by hand:"
grep -roIn --exclude-dir=.git -- '<[A-Z_/]\{3,\}>' . 2>/dev/null | sort -u | sed 's/^/           /' || true

# Initialise git + hooks.
if [ ! -d .git ]; then
  git init -q
  git add -A
  git commit -qm "chore: bootstrap $name from AI-SDLC Bootstrap Kit

Refs: ${ticket}-0" 2>/dev/null || git commit -qm "chore: bootstrap $name from AI-SDLC Bootstrap Kit"
  echo "[bootstrap] initialised git repo with an initial commit."
fi

if command -v pre-commit >/dev/null 2>&1; then
  pre-commit install --hook-type commit-msg >/dev/null 2>&1 || true
  echo "[bootstrap] installed pre-commit hooks."
else
  echo "[bootstrap] pre-commit not found — run: pip install pre-commit && pre-commit install --hook-type commit-msg"
fi

cat <<EOF

[bootstrap] Done. Next:
  1. cd $dir
  2. Open in Claude Code — it will run ONBOARDING.md (creates your USER.md).
  3. Fill the remaining <PLACEHOLDERS> listed above (start with AGENTS.md §1, §3, §4).
  4. (optional) add knowledge sources under docs/knowledge/sources/ and run
     python3 scripts/knowledge/ingest.py --build
EOF
