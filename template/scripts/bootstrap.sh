#!/usr/bin/env bash
# bootstrap.sh — initialise a new AI-augmented SDLC project from this template.
#
# Copies the template into a target directory, substitutes the <PLACEHOLDERS>,
# initialises git, and installs the hooks. Idempotent-ish: refuses to clobber a
# non-empty target unless --force or --merge is given.
#
# Usage:
#   scripts/bootstrap.sh --name "My Project" --slug my-project --dir ../my-project \
#       [--desc "one line"] [--ticket PROJ] [--host github] [--force] \
#       [--layout embedded|monorepo|sidecar|parent] [--merge] \
#       [--repos "path=role,path=role"] [--tools "id,id"] \
#       [--hooks kit|repo|none] [--no-git] [--non-interactive] \
#       [--kit-version <v>] [--kit-commit <sha>]
#
# Flags:
#   --name              project name (required)
#   --slug              project slug (derived from --name if omitted)
#   --dir               where the new project should live (required)
#   --desc              one-line description
#   --ticket            ticket/issue key prefix
#   --host              git host (default: github)
#   --force             overwrite a non-empty target
#   --layout            embedded|monorepo|sidecar|parent (default: embedded) —
#                        where the kit sits relative to the project's code
#   --merge             install into a non-empty target without clobbering
#                        existing files (marker-merge / copy-if-absent)
#   --repos             "path=role,path=role,…" — other repos this kit governs
#   --tools             "id,id,…" AI tools in use (default: claude)
#   --hooks             kit|repo|none (default: kit) — which git hooks to install
#   --no-git            skip git init / initial commit
#   --non-interactive   fail loudly (exit 2) instead of prompting when a
#                        required value is missing
#   --kit-version       kit version to record in the manifest (else derived
#                        from the kit's own git tags)
#   --kit-commit        kit commit to record in the manifest (else derived
#                        from the kit's own git HEAD)
#
# Run it from the template root (the folder containing AGENTS.md). When invoked
# from the kit, point --dir at where the new project should live.
set -euo pipefail

TEMPLATE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# shellcheck source=/dev/null
. "$TEMPLATE_ROOT/scripts/lib/kit-merge.sh"
# shellcheck source=/dev/null
. "$TEMPLATE_ROOT/scripts/lib/kit-pointers.sh"

name=""; slug=""; dir=""; desc="<ONE_LINE_DESCRIPTION>"; ticket="<TICKET>"; host="github"; force=0
layout="embedded"; merge=0; repos=""; tools="claude"; hooks="kit"; no_git=0; non_interactive=0
kit_version=""; kit_commit=""
kit_source="https://github.com/georgiandinca/ai-sdlc-bootstrap-kit"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --name)   name=${2:?}; shift 2 ;;
    --slug)   slug=${2:?}; shift 2 ;;
    --dir)    dir=${2:?}; shift 2 ;;
    --desc)   desc=${2:?}; shift 2 ;;
    --ticket) ticket=${2:?}; shift 2 ;;
    --host)   host=${2:?}; shift 2 ;;
    --force)  force=1; shift ;;
    --layout) layout=${2:?}; shift 2 ;;
    --merge)  merge=1; shift ;;
    --repos)  repos=${2:?}; shift 2 ;;
    --tools)  tools=${2:?}; shift 2 ;;
    --hooks)  hooks=${2:?}; shift 2 ;;
    --no-git) no_git=1; shift ;;
    --non-interactive) non_interactive=1; shift ;;
    --kit-version) kit_version=${2:?}; shift 2 ;;
    --kit-commit)  kit_commit=${2:?}; shift 2 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "bootstrap: unknown arg: $1" >&2; exit 2 ;;
  esac
done

case "$layout" in
  embedded|monorepo|sidecar|parent) ;;
  *) echo "bootstrap: --layout must be embedded|monorepo|sidecar|parent (got '$layout')" >&2; exit 2 ;;
esac
case "$hooks" in
  kit|repo|none) ;;
  *) echo "bootstrap: --hooks must be kit|repo|none (got '$hooks')" >&2; exit 2 ;;
esac

missing=""
[ -n "$name" ] || missing="$missing --name"
[ -n "$dir" ]  || missing="$missing --dir"
if [ -n "$missing" ]; then
  echo "bootstrap: missing required flag(s):$missing" >&2
  exit 2
fi
[ -n "$slug" ] || slug=$(printf '%s' "$name" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-')

if [ -d "$dir" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ] && [ "$force" -ne 1 ] && [ "$merge" -ne 1 ]; then
  echo "bootstrap: target '$dir' exists and is not empty (use --merge to install alongside, or --force to overwrite)" >&2
  exit 1
fi

echo "[bootstrap] project=$name slug=$slug host=$host layout=$layout -> $dir"
mkdir -p "$dir"

# Copy everything except VCS noise and local artifacts. In --merge mode, copy
# into a staging dir first and merge file-by-file / block-by-block so nothing
# the project already owns is overwritten.
if [ "$merge" -eq 1 ]; then
  staging=$(mktemp -d)
  ( cd "$TEMPLATE_ROOT" && \
    tar --exclude='.git' --exclude='node_modules' --exclude='.venv' \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='docs/knowledge/.index' \
        -cf - . ) | ( cd "$staging" && tar -xf - )
  mkdir -p "$dir/.ai-sdlc"
  {
    echo "# AI-SDLC kit install report"
    echo
    echo "Generated by \`bootstrap.sh --merge\` on $(date -u '+%Y-%m-%d %H:%M UTC')."
    echo
    kit_copy_merge "$staging" "$dir" | sed 's/^/- /'
  } > "$dir/.ai-sdlc/install-report.md"
  rm -rf "$staging"
else
  ( cd "$TEMPLATE_ROOT" && \
    tar --exclude='.git' --exclude='node_modules' --exclude='.venv' \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='docs/knowledge/.index' \
        -cf - . ) | ( cd "$dir" && tar -xf - )
fi

cd "$dir"

# Per-user example -> not the real file; the real USER.md is created at onboarding.
[ -f USER.md.example ] && echo "[bootstrap] kept USER.md.example (real USER.md is created at onboarding)"

# Placeholder substitution across text files (skip binaries / vcs / deps).
# grep exits 1 when a placeholder isn't found anywhere — expected and benign
# on a repeat --merge run once an earlier run has already replaced it, so
# that alone must not trip `set -e`/`pipefail`. Only a real grep failure
# (bad pattern, unreadable path, exit > 1) is treated as an error. The grep
# call sits inside an `if` (not piped into the loop) specifically so its
# non-zero status never reaches `set -e` or `pipefail`.
substitute() {
  local find_str="$1" repl="$2" matches grep_rc=0
  if matches=$(grep -rlI --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv \
       --exclude-dir=__pycache__ -- "$find_str" . 2>/dev/null); then
    :
  else
    grep_rc=$?
  fi
  if [ "$grep_rc" -gt 1 ]; then
    echo "bootstrap: grep failed while scanning for '$find_str' (exit $grep_rc)" >&2
    return "$grep_rc"
  fi
  [ -z "$matches" ] && return 0
  while IFS= read -r f; do
    # portable in-place sed (BSD/GNU)
    sed -i.bak "s|${find_str}|${repl}|g" "$f" && rm -f "$f.bak"
  done <<EOF
$matches
EOF
}
substitute "<PROJECT_NAME>" "$name"
substitute "<ONE_LINE_DESCRIPTION>" "$desc"
substitute "<TICKET>" "$ticket"

echo "[bootstrap] substituted <PROJECT_NAME>, <ONE_LINE_DESCRIPTION>, <TICKET>."
echo "[bootstrap] remaining placeholders to fill by hand:"
grep -roIn --exclude-dir=.git -- '<[A-Z_/]\{3,\}>' . 2>/dev/null | sort -u | sed 's/^/           /' || true

# --- kit version/commit: explicit flags win, else read the kit's own git metadata ---
KIT_ROOT="$(cd "$TEMPLATE_ROOT/.." && pwd)"
[ -n "$kit_version" ] || kit_version=$(git -C "$KIT_ROOT" describe --tags --always 2>/dev/null || echo "unknown")
[ -n "$kit_commit" ]  || kit_commit=$(git -C "$KIT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")

json_escape() { printf '%s' "${1-}" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }

# repos "path=role,path=role" -> JSON array; also a Markdown table for AGENTS.md §2
repos_json="[]"; repos_table=""
if [ -n "$repos" ]; then
  repos_json=""; old_ifs=$IFS; IFS=','
  for pair in $repos; do
    p=${pair%%=*}; r=${pair#*=}
    [ -n "$repos_json" ] && repos_json="$repos_json,"
    repos_json="$repos_json{\"path\":\"$(json_escape "$p")\",\"role\":\"$(json_escape "$r")\",\"pointer\":false}"
    repos_table="$repos_table| \`$p\` | $r |
"
  done
  IFS=$old_ifs
  repos_json="[$repos_json]"
fi

tools_json=""; old_ifs=$IFS; IFS=','
for t in $tools; do
  [ -n "$tools_json" ] && tools_json="$tools_json,"
  tools_json="$tools_json\"$(json_escape "$t")\""
done
IFS=$old_ifs
tools_json="[$tools_json]"

mkdir -p "$dir/.ai-sdlc"
cat > "$dir/.ai-sdlc/kit.json" <<JSON
{
  "kit": {
    "version": "$(json_escape "$kit_version")",
    "commit": "$(json_escape "$kit_commit")",
    "source": "$(json_escape "$kit_source")",
    "installed": "$(date -u '+%Y-%m-%d')"
  },
  "layout": "$(json_escape "$layout")",
  "project": { "name": "$(json_escape "$name")", "slug": "$(json_escape "$slug")" },
  "repos": $repos_json,
  "hooks": "$(json_escape "$hooks")",
  "tools": $tools_json
}
JSON

# A malformed target (ambiguous kit markers, or — for the Gemini settings
# JSON — an unparseable/unsupported shape) leaves that file byte-identical —
# surface it in the install report alongside the copy-merge collisions
# rather than swallowing it. Defaults to the marker-based reason; callers on
# a non-marker path (e.g. JSON) pass their own.
report_malformed() {
  local rel=$1 reason=${2:-"ambiguous ai-sdlc-kit markers — left untouched, needs a human look"}
  [ -f "$dir/.ai-sdlc/install-report.md" ] || return 0
  echo "- malformed $rel ($reason)" >> "$dir/.ai-sdlc/install-report.md"
}

# AGENTS.md §2 — the repo table, inside the kit's marked block
if [ -f "$dir/AGENTS.md" ]; then
  block=$(mktemp)
  {
    echo "**Layout:** \`$layout\` — this kit governs the repositories below."
    if [ -n "$repos_table" ]; then
      echo
      echo "| Repository | Role |"
      echo "|---|---|"
      printf '%s' "$repos_table"
    fi
  } > "$block"
  agents_merge_result=$(kit_merge_block "$dir/AGENTS.md" "$block")
  [ "$agents_merge_result" = "malformed" ] && report_malformed "AGENTS.md"
  rm -f "$block"
fi

# --- README block with this project's own facts ------------------------------------
if [ -f "$dir/README.md" ]; then
  block=$(mktemp)
  kit_readme_block "$name" "$layout" "$repos_table" "$kit_version" "$kit_source" > "$block"
  readme_merge_result=$(kit_merge_block "$dir/README.md" "$block")
  [ "$readme_merge_result" = "malformed" ] && report_malformed "README.md"
  rm -f "$block"
fi

# --- tool pointers -------------------------------------------------------------------
pointer_output=$(kit_write_tool_pointers "$dir" "$tools")
printf '%s\n' "$pointer_output" | sed 's/^/[bootstrap] /'
case "$pointer_output" in
  *"pointer claude malformed"*)  report_malformed "CLAUDE.md" ;;
esac
case "$pointer_output" in
  *"pointer copilot malformed"*) report_malformed ".github/copilot-instructions.md" ;;
esac
case "$pointer_output" in
  *"pointer gemini malformed"*)
    report_malformed ".gemini/settings.json" \
      "invalid or unsupported JSON — left untouched, needs a human look"
    ;;
esac

# --- code-repo pointers (sidecar / parent layouts) ----------------------------------
if [ -n "$repos" ] && { [ "$layout" = "sidecar" ] || [ "$layout" = "parent" ]; }; then
  kit_rel=$(basename "$dir")
  old_ifs=$IFS; IFS=','
  for pair in $repos; do
    IFS=$old_ifs
    p=${pair%%=*}
    target="$dir/$p"
    [ -d "$target" ] || target="$p"
    if [ -d "$target" ]; then
      case "$layout" in
        sidecar) rel_to_kit="../$kit_rel" ;;
        parent)  rel_to_kit=".." ;;
      esac
      repo_pointer_output=$(kit_write_repo_pointer "$target" "$rel_to_kit" "$kit_source")
      printf '%s\n' "$repo_pointer_output" | sed 's/^/[bootstrap] /'
      case "$repo_pointer_output" in
        *"repo-pointer $target malformed"*) report_malformed "$p/AGENTS.md" ;;
      esac
      case "$repo_pointer_output" in
        *"repo-pointer-claude $target malformed"*) report_malformed "$p/CLAUDE.md" ;;
      esac
    else
      echo "[bootstrap] repo not found on disk, pointer skipped: $p"
    fi
    old_ifs=$IFS; IFS=','
  done
  IFS=$old_ifs
fi

# Initialise git + hooks.
if [ "$no_git" -eq 0 ] && [ ! -d .git ]; then
  git init -q
  git add -A
  git commit -qm "chore: bootstrap $name from AI-SDLC Bootstrap Kit

Refs: ${ticket}-0" 2>/dev/null || git commit -qm "chore: bootstrap $name from AI-SDLC Bootstrap Kit"
  echo "[bootstrap] initialised git repo with an initial commit."
fi

if [ "$hooks" = "kit" ] && command -v pre-commit >/dev/null 2>&1; then
  pre-commit install >/dev/null 2>&1 || true
  echo "[bootstrap] installed pre-commit hooks."
elif [ "$hooks" = "repo" ]; then
  # TODO(Task 5): --hooks repo will point at a project-owned hook config via
  # --hooks-target. For now it is a placeholder and behaves like "none".
  echo "[bootstrap] --hooks repo handled separately"
elif [ "$hooks" = "none" ]; then
  echo "[bootstrap] hooks skipped (--hooks none)."
fi

cat <<EOF

[bootstrap] Done. Next:
  1. cd $dir
  2. Open in Claude Code — it will run ONBOARDING.md (creates your USER.md).
  3. Fill the remaining <PLACEHOLDERS> listed above (start with AGENTS.md §1, §3, §4).
  4. (optional) add knowledge sources under docs/knowledge/sources/ and run
     python3 scripts/knowledge/ingest.py --build
EOF
