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
#       [--repos "path=role[:nopointer],path=role"] [--tools "id,id"] \
#       [--hooks kit|repo|none] [--hooks-target <dir>] [--no-git] [--non-interactive] \
#       [--kit-version <v>] [--kit-commit <sha>]
#
# Flags:
#   --name              project name (required)
#   --slug              project slug (derived from --name if omitted)
#   --dir               where the new project should live (required)
#   --desc              one-line description
#   --ticket            ticket/issue key prefix
#   --host              git host (default: github) — recorded in the manifest
#                        as "host", for later tooling that needs to know
#   --force             overwrite a non-empty target
#   --layout            embedded|monorepo|sidecar|parent (default: embedded) —
#                        where the kit sits relative to the project's code
#   --merge             install into a non-empty target without clobbering
#                        existing files (marker-merge / copy-if-absent). The
#                        outcome per path is written to .ai-sdlc/install-report.md
#                        at the END of the run, so it reflects the final state.
#   --repos             "path=role[:nopointer],path=role,…" — other repos this
#                        kit governs. A ":nopointer" suffix on the role lists
#                        the repo in AGENTS.md §2 and the manifest but writes
#                        NO pointer block into it, and records "pointer": false.
#                        Example: --repos "../acme-api=backend,../acme-web=frontend:nopointer"
#   --tools             "id,id,…" AI tools in use (default: claude)
#   --hooks             kit|repo|none (default: kit) — which git hooks to install
#   --hooks-target      code-repo dir to fold hooks into — required when
#                        --hooks repo is used
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
layout="embedded"; merge=0; repos=""; tools="claude"; hooks="kit"; hooks_target=""; no_git=0; non_interactive=0
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
    --hooks-target) hooks_target=${2:?}; shift 2 ;;
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
# Validated up front, before any work (mkdir/tar/git init) happens: a bad
# --hooks-target used to fail deep into the run (a raw `cp` error after the
# initial commit), leaving a half-bootstrapped kit directory behind.
if [ "$hooks" = "repo" ]; then
  if [ -z "$hooks_target" ]; then
    echo "bootstrap: --hooks repo requires --hooks-target <dir>" >&2; exit 2
  fi
  if [ ! -d "$hooks_target" ]; then
    echo "bootstrap: --hooks-target '$hooks_target' does not exist" >&2; exit 2
  fi
fi

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
# The install report is written ONCE, at the very end of the run, from what
# actually happened — see "install report" below. Writing it here, before the
# marker merges run, reported every successfully merged file as a `collision`,
# and SKILL.md tells the agent to relay collisions as files "only the user can
# resolve by hand". $copy_results holds the copy step's verdict per path;
# $final_notes holds the later, final verdict for the paths that changed again.
copy_results=$(mktemp)
final_notes=$(mktemp)
trap 'rm -f "$copy_results" "$final_notes"' EXIT

if [ "$merge" -eq 1 ]; then
  staging=$(mktemp -d)
  ( cd "$TEMPLATE_ROOT" && \
    tar --exclude='.git' --exclude='node_modules' --exclude='.venv' \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='docs/knowledge/.index' \
        -cf - . ) | ( cd "$staging" && tar -xf - )
  kit_copy_merge "$staging" "$dir" > "$copy_results"
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

# --- install-report bookkeeping -----------------------------------------------------
# Every path this run touches after the copy step records its FINAL outcome
# here; the report is rendered from these two files at the end of the run.

# record_outcome <rel> <outcome> [reason]
record_outcome() {
  local rel=$1 outcome=$2 reason=${3:-}
  if [ -n "$reason" ]; then
    printf '%s %s (%s)\n' "$outcome" "$rel" "$reason" >> "$final_notes"
  else
    printf '%s %s\n' "$outcome" "$rel" >> "$final_notes"
  fi
}

# copy_outcome <rel> -> what the copy step said about this path (may be empty)
copy_outcome() { awk -v r="$1" '$2 == r { print $1; exit }' "$copy_results"; }

# record_merge <rel> <kit_merge_block action>
# Translates one merge-engine outcome into the report. A file the copy step
# already created needs no second line; a file the PROJECT owned that the kit
# then successfully merged into is a `merged`, not the `collision` the copy
# step saw. Every non-clobber outcome keeps its own name and a reason, so the
# skill can relay it verbatim.
record_merge() {
  local rel=$1 action=$2 prior
  prior=$(copy_outcome "$rel")
  case "$action" in
    created|appended|updated)
      if [ "$prior" = "created" ] || [ "$prior" = "identical" ]; then
        return 0
      fi
      if [ -z "$prior" ] && [ "$action" = "created" ]; then
        record_outcome "$rel" created
      else
        record_outcome "$rel" merged "$action"
      fi
      ;;
    malformed)  report_malformed "$rel" ;;
    unwritable) record_outcome "$rel" unwritable \
                  "read-only file, or a path the project owns as a regular file — left untouched, needs a human look" ;;
    escaped)    record_outcome "$rel" escaped \
                  "resolves outside the install target through a symlink — nothing was written" ;;
    *)          record_outcome "$rel" unknown \
                  "unrecognised merge outcome '$action' — nothing was written" ;;
  esac
}

# A malformed target (ambiguous kit markers, or — for the Gemini settings
# JSON — an unparseable/unsupported shape) leaves that file byte-identical —
# surface it in the install report alongside the copy-merge collisions
# rather than swallowing it. Defaults to the marker-based reason; callers on
# a non-marker path (e.g. JSON) pass their own.
report_malformed() {
  local rel=$1 reason=${2:-"ambiguous ai-sdlc-kit markers — left untouched, needs a human look"}
  record_outcome "$rel" malformed "$reason"
}

# --- repos "path=role[:nopointer],…" -----------------------------------------------
# The Markdown table for AGENTS.md §2 is built now; the JSON array is built
# after the pointer loop, from what each repo ACTUALLY got — spec §6 and the
# skill's status check both read `repos[].pointer`, so a hard-coded `false`
# reported a false positive on every installed project.
repo_paths=(); repo_roles=(); repo_wantptr=(); repo_ptrdone=()
repo_count=0; repos_table=""
if [ -n "$repos" ]; then
  old_ifs=$IFS; IFS=','
  for pair in $repos; do
    IFS=$old_ifs
    p=${pair%%=*}; r=${pair#*=}
    want=1
    # ":nopointer" honours spec decision 4's "ask per repo, default yes": the
    # repo is still listed in AGENTS.md §2 and the manifest, but no pointer
    # block is written into it.
    case "$r" in
      *:nopointer) r=${r%:nopointer}; want=0 ;;
    esac
    repo_paths[$repo_count]=$p
    repo_roles[$repo_count]=$r
    repo_wantptr[$repo_count]=$want
    repo_ptrdone[$repo_count]=0
    repos_table="$repos_table| \`$p\` | $r |
"
    repo_count=$((repo_count + 1))
    old_ifs=$IFS; IFS=','
  done
  IFS=$old_ifs
fi

tools_json=""; old_ifs=$IFS; IFS=','
for t in $tools; do
  [ -n "$tools_json" ] && tools_json="$tools_json,"
  tools_json="$tools_json\"$(json_escape "$t")\""
done
IFS=$old_ifs
tools_json="[$tools_json]"

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
  record_merge "AGENTS.md" "$(kit_merge_block "$dir/AGENTS.md" "$block" "$dir")"
  rm -f "$block"
fi

# --- README block with this project's own facts ------------------------------------
if [ -f "$dir/README.md" ]; then
  block=$(mktemp)
  kit_readme_block "$name" "$layout" "$repos_table" "$kit_version" "$kit_source" \
    "$(basename "$dir")" > "$block"
  record_merge "README.md" "$(kit_merge_block "$dir/README.md" "$block" "$dir")"
  rm -f "$block"
fi

# --- .gitignore: the kit's ignore lines, as a marked block --------------------------
# Spec §7 lists .gitignore among the known-mergeable files. A project with its
# own .gitignore used to get `- collision .gitignore` and nothing else, so the
# kit's USER.md / .env / .env.* lines never arrived and the per-person identity
# file created at onboarding was committable.
if [ "$merge" -eq 1 ] && [ "$(copy_outcome .gitignore)" = "collision" ]; then
  block=$(mktemp)
  {
    echo "# Added by the AI-SDLC Bootstrap Kit — keep these ignored."
    cat "$TEMPLATE_ROOT/.gitignore"
  } > "$block"
  record_merge ".gitignore" "$(kit_merge_block "$dir/.gitignore" "$block" "$dir")"
  rm -f "$block"
fi

# --- tool pointers -------------------------------------------------------------------
pointer_output=$(kit_write_tool_pointers "$dir" "$tools")
printf '%s\n' "$pointer_output" | sed 's/^/[bootstrap] /'
while IFS= read -r ptr_line; do
  ptr_action=${ptr_line##* }
  case "$ptr_line" in
    "pointer claude "*)  record_merge "CLAUDE.md" "$ptr_action" ;;
    "pointer copilot "*) record_merge ".github/copilot-instructions.md" "$ptr_action" ;;
    "pointer gemini "*)
      # JSON has no markers, so the merge-engine wording would be wrong here.
      if [ "$ptr_action" = "malformed" ]; then
        report_malformed ".gemini/settings.json" \
          "invalid or unsupported JSON — left untouched, needs a human look"
      else
        record_merge ".gemini/settings.json" "$ptr_action"
      fi
      ;;
  esac
done <<POINTERS
$pointer_output
POINTERS

# --- code-repo pointers (sidecar / parent layouts) ----------------------------------
if [ "$repo_count" -gt 0 ] && { [ "$layout" = "sidecar" ] || [ "$layout" = "parent" ]; }; then
  kit_rel=$(basename "$dir")
  i=0
  while [ "$i" -lt "$repo_count" ]; do
    p=${repo_paths[$i]}
    if [ "${repo_wantptr[$i]}" -eq 0 ]; then
      echo "[bootstrap] pointer declined (:nopointer), repo still listed in AGENTS.md §2: $p"
      i=$((i + 1)); continue
    fi
    target="$dir/$p"
    [ -d "$target" ] || target="$p"
    if [ -d "$target" ]; then
      case "$layout" in
        sidecar) rel_to_kit="../$kit_rel" ;;
        parent)  rel_to_kit=".." ;;
      esac
      repo_pointer_output=$(kit_write_repo_pointer "$target" "$rel_to_kit" "$kit_source")
      printf '%s\n' "$repo_pointer_output" | sed 's/^/[bootstrap] /'
      repo_agents_action=$(printf '%s\n' "$repo_pointer_output" \
        | awk -v k="repo-pointer" '$1 == k { print $NF }')
      repo_claude_action=$(printf '%s\n' "$repo_pointer_output" \
        | awk -v k="repo-pointer-claude" '$1 == k { print $NF }')
      record_merge "$p/AGENTS.md" "$repo_agents_action"
      record_merge "$p/CLAUDE.md" "$repo_claude_action"
      case "$repo_agents_action" in
        created|appended|updated) repo_ptrdone[$i]=1 ;;
      esac
    else
      echo "[bootstrap] repo not found on disk, pointer skipped: $p"
    fi
    i=$((i + 1))
  done
fi

# --- the manifest: what was actually installed --------------------------------------
repos_json="[]"
if [ "$repo_count" -gt 0 ]; then
  repos_json=""; i=0
  while [ "$i" -lt "$repo_count" ]; do
    [ -n "$repos_json" ] && repos_json="$repos_json,"
    if [ "${repo_ptrdone[$i]}" -eq 1 ]; then ptr_json=true; else ptr_json=false; fi
    repos_json="$repos_json{\"path\":\"$(json_escape "${repo_paths[$i]}")\",\"role\":\"$(json_escape "${repo_roles[$i]}")\",\"pointer\":$ptr_json}"
    i=$((i + 1))
  done
  repos_json="[$repos_json]"
fi

# The manifest is the one file bootstrap writes with an unguarded `>`. In
# --merge mode a `.ai-sdlc/kit.json` that is not the kit's own (no top-level
# "kit" key) belongs to the project: report it and write nothing.
manifest="$dir/.ai-sdlc/kit.json"
write_manifest=1
if [ "$merge" -eq 1 ] && { [ -e "$manifest" ] || [ -L "$manifest" ]; }; then
  if _kit_escapes_root "$manifest" "$dir"; then
    write_manifest=0
    record_merge ".ai-sdlc/kit.json" escaped
  elif ! grep -q '"kit"' "$manifest" 2>/dev/null; then
    write_manifest=0
    record_outcome ".ai-sdlc/kit.json" collision \
      "a file the project already owns — the kit's manifest was not written"
    echo "[bootstrap] .ai-sdlc/kit.json already exists and is not the kit's — left untouched; see install report."
  fi
fi
if [ "$write_manifest" -eq 1 ]; then
  mkdir -p "$dir/.ai-sdlc"
  cat > "$manifest" <<JSON
{
  "kit": {
    "version": "$(json_escape "$kit_version")",
    "commit": "$(json_escape "$kit_commit")",
    "source": "$(json_escape "$kit_source")",
    "installed": "$(date -u '+%Y-%m-%d')"
  },
  "layout": "$(json_escape "$layout")",
  "host": "$(json_escape "$host")",
  "project": { "name": "$(json_escape "$name")", "slug": "$(json_escape "$slug")" },
  "repos": $repos_json,
  "hooks": "$(json_escape "$hooks")",
  "tools": $tools_json
}
JSON
fi

# Initialise git. The initial COMMIT is deferred to the end of the run so the
# hooks wiring and the install report land inside it.
git_initialised=0
if [ "$no_git" -eq 0 ] && [ ! -d .git ]; then
  git init -q
  git_initialised=1
fi

if [ "$hooks" = "kit" ]; then
  if command -v pre-commit >/dev/null 2>&1; then
    # Plain `install` honours default_install_hook_types ([pre-commit, commit-msg]);
    # passing --hook-type would install only that stage and leave the validators ungated.
    pre-commit install >/dev/null 2>&1 || true
    echo "[bootstrap] installed pre-commit hooks."
  else
    echo "[bootstrap] pre-commit not found — run: pip install pre-commit && pre-commit install"
  fi
elif [ "$hooks" = "repo" ]; then
  # --hooks-target's presence and existence are already validated up front.
  # Prefix so a rewritten hook `entry` resolves from $hooks_target back to the
  # kit. sidecar/parent are cross-repo (mirrors Task 4's rel_to_kit); embedded/
  # monorepo run the hooks inside the kit's own repo, so no rewrite is needed.
  case "$layout" in
    sidecar)           hooks_prefix="../$(basename "$dir")" ;;
    parent)             hooks_prefix=".." ;;
    embedded|monorepo)  hooks_prefix="" ;;
  esac
  # ONE path, whether or not the code repo already has a config. Copying the
  # kit's file when the target is absent used to bypass the `entry:` rewriting
  # entirely: every hook kept `python scripts/…`, unresolvable from the code
  # repo, and the repo's next commit was blocked by commit-msg-ticket failing
  # to find its script. merge-precommit.py treats a missing target as an empty
  # config and creates it with the prefix applied.
  if [ ! -f "$hooks_target/.pre-commit-config.yaml" ]; then
    echo "[bootstrap] no .pre-commit-config.yaml in $hooks_target — creating it from the kit's (paths rewritten for this repo)."
  fi
  mkdir -p "$dir/.ai-sdlc"
  # Name the backup from $hooks_target's own absolute path (basename +
  # checksum), not a fixed per-kit-install name: two different code repos
  # folding hooks from the same kit install must get two different backup
  # files, or the second run would overwrite the first repo's only
  # pre-merge recovery copy.
  hooks_target_abs=$(cd "$hooks_target" && pwd)
  hooks_backup_slug="$(basename "$hooks_target_abs")-$(printf '%s' "$hooks_target_abs" | cksum | awk '{print $1}')"
  hooks_backup="$dir/.ai-sdlc/pre-commit-config.backup.${hooks_backup_slug}.yaml"
  hooks_backup_existed=0
  [ -f "$hooks_backup" ] && hooks_backup_existed=1
  merge_args=("$hooks_target/.pre-commit-config.yaml" "$dir/.pre-commit-config.yaml" \
              --backup "$hooks_backup")
  # Only pass --prefix when non-empty, so an embedded/monorepo layout never
  # sends a literal "" through to the merger.
  [ -n "$hooks_prefix" ] && merge_args+=(--prefix "$hooks_prefix")
  merge_rc=0
  merge_output=$(python3 "$dir/scripts/merge-precommit.py" "${merge_args[@]}" 2>&1) || merge_rc=$?
  printf '%s\n' "$merge_output" | sed 's/^/[bootstrap] hook /'
  if [ "$merge_rc" -eq 0 ]; then
    # merge-precommit.py never overwrites a backup that's already on disk,
    # so on a repeat run it still holds the ORIGINAL, pre-merge file even
    # though this run may have added more hooks on top of the first merge.
    # No backup is taken when the target did not exist — there is nothing to
    # recover to.
    if [ -f "$hooks_backup" ]; then
      if [ "$hooks_backup_existed" -eq 1 ]; then
        echo "[bootstrap] original config already backed up at .ai-sdlc/$(basename "$hooks_backup") (kept from the first merge; comments are not preserved by the merge)."
      else
        echo "[bootstrap] original config backed up to .ai-sdlc/$(basename "$hooks_backup") (comments are not preserved by the merge)."
      fi
    fi
  else
    # Refuse-rather-than-guess: the merger exits 2 when it cannot safely
    # parse the target, so the target is left untouched — surface that the
    # same way the other non-clobber outcomes are surfaced.
    report_malformed "$hooks_target/.pre-commit-config.yaml" \
      "could not be safely merged — left untouched, needs a human look"
    echo "[bootstrap] $hooks_target/.pre-commit-config.yaml left untouched (merge failed); see install report."
  fi
  if command -v pre-commit >/dev/null 2>&1; then
    if ( cd "$hooks_target" && pre-commit install --hook-type pre-commit --hook-type commit-msg >/dev/null 2>&1 ); then
      echo "[bootstrap] installed pre-commit hooks in $hooks_target (both stages)."
    else
      echo "[bootstrap] pre-commit hook install FAILED in $hooks_target (not a git repo? run it yourself: cd $hooks_target && pre-commit install --hook-type pre-commit --hook-type commit-msg)"
    fi
  fi
elif [ "$hooks" = "none" ]; then
  echo "[bootstrap] hooks skipped (--hooks none)."
fi

# --- the install report: the FINAL state of every path this run touched -------------
# A copy-step line is printed only when nothing later in the run changed that
# path's verdict, so a file that collided on copy and was then successfully
# marker-merged appears as `merged`, not as a `collision` the user must resolve.
if [ "$merge" -eq 1 ]; then
  mkdir -p "$dir/.ai-sdlc"
  {
    echo "# AI-SDLC kit install report"
    echo
    echo "Generated by \`bootstrap.sh --merge\` on $(date -u '+%Y-%m-%d %H:%M UTC')."
    echo
    echo "Outcomes: \`created\` / \`identical\` / \`merged\` — the kit's content is in place."
    echo "\`collision\` / \`malformed\` / \`unwritable\` / \`escaped\` — the file was left"
    echo "byte-identical and only a human can resolve it."
    echo
    {
      awk -v notes="$final_notes" '
        FILENAME == notes { seen[$2] = 1; next }
        !($2 in seen)     { print }
      ' "$final_notes" "$copy_results"
      cat "$final_notes"
    } | sort | sed 's/^/- /'
  } > "$dir/.ai-sdlc/install-report.md"
fi

# The initial commit runs last so the hooks wiring, the manifest and the
# install report are all inside it.
if [ "$git_initialised" -eq 1 ]; then
  git add -A
  git commit -qm "chore: bootstrap $name from AI-SDLC Bootstrap Kit

Refs: ${ticket}-0" 2>/dev/null || git commit -qm "chore: bootstrap $name from AI-SDLC Bootstrap Kit"
  echo "[bootstrap] initialised git repo with an initial commit."
fi

cat <<EOF

[bootstrap] Done. Next:
  1. cd $dir
  2. Open in Claude Code — it will run ONBOARDING.md (creates your USER.md).
  3. Fill the remaining <PLACEHOLDERS> listed above (start with AGENTS.md §1, §3, §4).
  4. (optional) add knowledge sources under docs/knowledge/sources/ and run
     python3 scripts/knowledge/ingest.py --build
EOF
