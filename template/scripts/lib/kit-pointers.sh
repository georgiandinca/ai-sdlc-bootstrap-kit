#!/usr/bin/env bash
# kit-pointers.sh — write per-tool and per-repo pointers to the canonical brief.
#
# AGENTS.md is canonical and is read natively by Codex, Cursor, Windsurf,
# Antigravity and Copilot on github.com — those tools need no pointer at all.
# Only Claude Code (reads CLAUDE.md) and Gemini CLI (defaults to GEMINI.md)
# need anything written. Source this file; do not run it. Requires kit-merge.sh.

# kit_write_tool_pointers <dir> <tools_csv>
kit_write_tool_pointers() {
  local dir=$1 tools=$2 t block action old_ifs
  old_ifs=$IFS; IFS=','
  for t in $tools; do
    IFS=$old_ifs
    case "$t" in
      claude)
        block=$(mktemp)
        {
          echo "@AGENTS.md"
          echo
          echo "\`AGENTS.md\` is the canonical brief for this project. This file only points at it."
        } > "$block"
        action=$(kit_merge_block "$dir/CLAUDE.md" "$block")
        rm -f "$block"
        echo "pointer claude $action"
        ;;
      gemini)
        mkdir -p "$dir/.gemini"
        python3 - "$dir/.gemini/settings.json" <<'PY'
import json, os, sys
path = sys.argv[1]
data = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        data = {}
ctx = data.setdefault("context", {})
names = ctx.get("fileName")
if isinstance(names, str):
    names = [names]
elif not isinstance(names, list):
    names = []
if "AGENTS.md" not in names:
    names.insert(0, "AGENTS.md")
if "GEMINI.md" not in names:
    names.append("GEMINI.md")
ctx["fileName"] = names
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
        echo "pointer gemini updated"
        ;;
      copilot)
        block=$(mktemp)
        {
          echo "Read [\`AGENTS.md\`](../AGENTS.md) at the repository root first — it is the canonical"
          echo "brief for this project. These instructions add nothing of their own."
        } > "$block"
        action=$(kit_merge_block "$dir/.github/copilot-instructions.md" "$block")
        rm -f "$block"
        echo "pointer copilot $action"
        ;;
      *)
        # Codex, Cursor, Windsurf, Antigravity: AGENTS.md is read natively.
        echo "pointer $t none"
        ;;
    esac
    old_ifs=$IFS; IFS=','
  done
  IFS=$old_ifs
}

# kit_write_repo_pointer <repo_dir> <rel_kit_path> <kit_url>
kit_write_repo_pointer() {
  local repo=$1 rel=$2 url=$3 block action
  block=$(mktemp)
  {
    echo "**This repository is governed by the AI-SDLC kit at \`$rel\`.**"
    echo
    echo "Read \`$rel/AGENTS.md\` first — it is the canonical brief (mission, constraints,"
    echo "trust tiers, MCP posture, seats). This file adds no rules of its own."
    echo
    echo "If \`$rel\` is not present, clone the kit beside this repository:"
    echo
    echo '```bash'
    echo "git clone $url $rel"
    echo '```'
  } > "$block"
  action=$(kit_merge_block "$repo/AGENTS.md" "$block")
  rm -f "$block"

  block=$(mktemp)
  {
    echo "@$rel/AGENTS.md"
    echo
    echo "The canonical brief lives in the AI-SDLC kit at \`$rel\`. See \`AGENTS.md\` in this"
    echo "repository for what to do when that path is missing."
  } > "$block"
  kit_merge_block "$repo/CLAUDE.md" "$block" >/dev/null
  rm -f "$block"
  echo "repo-pointer $repo $action"
}

# kit_readme_block <name> <layout> <repos_table> <kit_version> <kit_source>
kit_readme_block() {
  local name=$1 layout=$2 repos_table=$3 version=$4 source=$5
  echo "## $name — how we work with AI here"
  echo
  echo "This project is governed by the **AI-SDLC Bootstrap Kit** (\`$version\`, from $source),"
  echo "installed in the **\`$layout\`** layout."
  echo
  if [ -n "$repos_table" ]; then
    echo "| Repository | Role |"
    echo "|---|---|"
    printf '%s\n' "$repos_table"
    echo
  fi
  echo "### Start here"
  echo
  echo "1. Open your AI agent in this folder. It reads \`AGENTS.md\` — the canonical brief."
  echo "2. On your first run it follows \`ONBOARDING.md\`, which installs the tooling and"
  echo "   creates your personal \`USER.md\` (git-ignored). Onboarding runs once per person."
  echo "3. After that, \`USER.md\` is read each session and the brief governs the work."
  echo
  echo "### Day to day"
  echo
  echo "| Where | What |"
  echo "|---|---|"
  echo "| \`AGENTS.md\` | The brief every AI tool reads — mission, constraints, seats, MCP posture |"
  echo "| \`WORKING-AGREEMENT.md\` | How the team organises information, and the rules CI enforces |"
  echo "| \`.claude/skills/\` | Role playbooks — invoke your seat's skill to work in it |"
  echo "| \`docs/\` | The project's knowledge tree; \`FOLDER-INDEX.md\` says what goes where |"
  echo "| \`.ai-sdlc/kit.json\` | What was installed, in which layout, and at which version |"
}
