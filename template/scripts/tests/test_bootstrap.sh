#!/usr/bin/env bash
# Functional test for bootstrap.sh (no framework). Exits non-zero on any failure.
set -uo pipefail
SRC_ROOT=$(cd "$(dirname "$0")/../.." && pwd)     # …/template
BOOT="$SRC_ROOT/scripts/bootstrap.sh"
fails=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got '$2' want '$3'"; fails=$((fails+1)); fi; }
jqp() { python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."):
    d = d[k] if isinstance(d, dict) else None
print(json.dumps(d))' "$1" "$2"; }

export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

# --- 1. fresh embedded install -----------------------------------------------------
tmp=$(mktemp -d)
"$BOOT" --name "Acme Wallet" --slug acme-wallet --dir "$tmp/acme" --desc "wallet" \
        --ticket ACME --layout embedded --kit-version 1.2.0 --kit-commit abc1234 \
        --non-interactive >/dev/null 2>&1
check fresh_agents   "$([ -f "$tmp/acme/AGENTS.md" ] && echo yes)" "yes"
check fresh_manifest "$([ -f "$tmp/acme/.ai-sdlc/kit.json" ] && echo yes)" "yes"
check fresh_layout   "$(jqp "$tmp/acme/.ai-sdlc/kit.json" layout)"        '"embedded"'
check fresh_version  "$(jqp "$tmp/acme/.ai-sdlc/kit.json" kit.version)"   '"1.2.0"'
check fresh_name     "$(jqp "$tmp/acme/.ai-sdlc/kit.json" project.name)"  '"Acme Wallet"'
check fresh_hooks    "$(jqp "$tmp/acme/.ai-sdlc/kit.json" hooks)"         '"kit"'
rm -rf "$tmp"

# --- 2. merge into a populated project ---------------------------------------------
tmp=$(mktemp -d); proj="$tmp/api"; mkdir -p "$proj/src"
printf '# Acme API\n\nOur own readme.\n' > "$proj/README.md"
printf 'dist/\n' > "$proj/.gitignore"
printf 'console.log(1)\n' > "$proj/src/index.js"
( cd "$proj" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Acme API" --slug acme-api --dir "$proj" --desc "api" --ticket ACME \
        --layout embedded --merge --non-interactive >/dev/null 2>&1
check merge_kept_readme "$(head -1 "$proj/README.md")" "# Acme API"
check merge_block_once  "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$proj/README.md")" "1"
check merge_kept_ignore "$(head -1 "$proj/.gitignore")" "dist/"
check merge_kept_src    "$(cat "$proj/src/index.js")" "console.log(1)"
check merge_added_kit   "$([ -f "$proj/AGENTS.md" ] && echo yes)" "yes"
check merge_report      "$([ -f "$proj/.ai-sdlc/install-report.md" ] && echo yes)" "yes"

# --- 3. idempotence: a second run changes nothing structurally ----------------------
sum_before=$(cat "$proj/README.md" | wc -l | tr -d ' ')
"$BOOT" --name "Acme API" --slug acme-api --dir "$proj" --desc "api" --ticket ACME \
        --layout embedded --merge --non-interactive >/dev/null 2>&1
idem_rc=$?
check idem_exit_zero "$idem_rc" "0"
check idem_block_once "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$proj/README.md")" "1"
check idem_same_lines "$(cat "$proj/README.md" | wc -l | tr -d ' ')" "$sum_before"
rm -rf "$tmp"

# --- 3b. a full --merge install run twice end to end reaches completion ------------
# Regression guard: bootstrap.sh must not abort partway through a repeat
# --merge run (see substitute()'s "no placeholders left to replace" case) —
# it must reach the manifest, README block, pointers and install report both
# times, with README.md still carrying exactly one kit block.
tmp=$(mktemp -d); proj2="$tmp/api2"; mkdir -p "$proj2/src"
printf '# Acme API 2\n\nOur own readme.\n' > "$proj2/README.md"
printf 'dist/\n' > "$proj2/.gitignore"
( cd "$proj2" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Acme API 2" --slug acme-api-2 --dir "$proj2" --desc "api" --ticket ACME \
        --layout embedded --tools "claude,gemini" --merge --non-interactive >/dev/null 2>&1
check e2e_run1_exit "$?" "0"
"$BOOT" --name "Acme API 2" --slug acme-api-2 --dir "$proj2" --desc "api" --ticket ACME \
        --layout embedded --tools "claude,gemini" --merge --non-interactive >/dev/null 2>&1
check e2e_run2_exit "$?" "0"
check e2e_manifest         "$([ -f "$proj2/.ai-sdlc/kit.json" ] && echo yes)" "yes"
check e2e_report           "$([ -f "$proj2/.ai-sdlc/install-report.md" ] && echo yes)" "yes"
check e2e_readme_block     "$(grep -c 'how we work with AI here' "$proj2/README.md")" "1"
check e2e_readme_one_block "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$proj2/README.md")" "1"
check e2e_claude_ptr       "$(grep -c '@AGENTS.md' "$proj2/CLAUDE.md")" "1"
check e2e_gemini_ptr       "$([ -f "$proj2/.gemini/settings.json" ] && echo yes)" "yes"
rm -rf "$tmp"

# --- 4. repos + layout are recorded ------------------------------------------------
tmp=$(mktemp -d)
"$BOOT" --name "Acme" --slug acme --dir "$tmp/sdlc" --desc "d" --ticket ACME \
        --layout sidecar --repos "../acme-api=backend,../acme-web=frontend" \
        --tools "claude,copilot" --non-interactive >/dev/null 2>&1
check repos_layout "$(jqp "$tmp/sdlc/.ai-sdlc/kit.json" layout)" '"sidecar"'
check repos_count  "$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))["repos"]))' "$tmp/sdlc/.ai-sdlc/kit.json")" "2"
check repos_role   "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["repos"][0]["role"])' "$tmp/sdlc/.ai-sdlc/kit.json")" "backend"
check repos_tools  "$(python3 -c 'import json,sys;print(",".join(json.load(open(sys.argv[1]))["tools"]))' "$tmp/sdlc/.ai-sdlc/kit.json")" "claude,copilot"
check agents_table "$(grep -c 'acme-api' "$tmp/sdlc/AGENTS.md")" "1"
rm -rf "$tmp"

# --- 5. --no-git and --hooks none ---------------------------------------------------
tmp=$(mktemp -d)
"$BOOT" --name "NoGit" --slug nogit --dir "$tmp/ng" --desc "d" --ticket NG \
        --no-git --hooks none --non-interactive >/dev/null 2>&1
check nogit_no_repo "$([ -d "$tmp/ng/.git" ] && echo yes || echo no)" "no"
check nogit_hooks   "$(jqp "$tmp/ng/.ai-sdlc/kit.json" hooks)" '"none"'
rm -rf "$tmp"

# --- 5b. every layout installs and is recorded -------------------------------------
for lay in embedded monorepo sidecar parent; do
  tmp=$(mktemp -d)
  "$BOOT" --name "L $lay" --slug "l-$lay" --dir "$tmp/k" --desc "d" --ticket L \
          --layout "$lay" --non-interactive >/dev/null 2>&1
  check "layout_${lay}_agents"   "$([ -f "$tmp/k/AGENTS.md" ] && echo yes)" "yes"
  check "layout_${lay}_manifest" "$(jqp "$tmp/k/.ai-sdlc/kit.json" layout)" "\"$lay\""
  rm -rf "$tmp"
done

# --- 6. --non-interactive with a missing required value fails loudly ----------------
tmp=$(mktemp -d)
"$BOOT" --slug x --dir "$tmp/x" --non-interactive >/dev/null 2>&1
check ni_exit "$?" "2"
rm -rf "$tmp"

# --- 7. README block and pointers land in a real install ---------------------------
tmp=$(mktemp -d)
"$BOOT" --name "Acme Wallet" --slug acme-wallet --dir "$tmp/acme" --desc "d" --ticket ACME \
        --layout embedded --tools "claude,gemini" --non-interactive >/dev/null 2>&1
check readme_block  "$(grep -c 'how we work with AI here' "$tmp/acme/README.md")" "1"
check readme_layout "$(grep -c 'embedded' "$tmp/acme/README.md")" "1"
check readme_one_block  "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$tmp/acme/README.md")" "1"
check readme_no_placeholder "$(grep -c 'Installed by the' "$tmp/acme/README.md")" "0"
check claude_ptr    "$(grep -c '@AGENTS.md' "$tmp/acme/CLAUDE.md")" "1"
check gemini_ptr    "$([ -f "$tmp/acme/.gemini/settings.json" ] && echo yes)" "yes"
rm -rf "$tmp"

# --- 8. malformed pointer targets are reported, never silently accepted ------------
# Root CLAUDE.md with an ambiguous marker layout (begin, no end): the run
# must still exit 0, the file must stay byte-identical, and the install
# report must name it.
tmp=$(mktemp -d); proj="$tmp/mal"; mkdir -p "$proj"
printf '<!-- ai-sdlc-kit:begin -->\nstray CLAUDE content, no end marker\n' > "$proj/CLAUDE.md"
( cd "$proj" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Malformed Proj" --slug malformed-proj --dir "$proj" --desc "d" --ticket ACME \
        --layout embedded --tools "claude" --merge --non-interactive >/dev/null 2>&1
mal_claude_rc=$?
check mal_claude_exit      "$mal_claude_rc" "0"
check mal_claude_unchanged "$(grep -c 'stray CLAUDE content' "$proj/CLAUDE.md")" "1"
check mal_claude_reported  "$(grep -c 'malformed CLAUDE.md' "$proj/.ai-sdlc/install-report.md")" "1"
check mal_claude_reason    "$(grep -c 'ambiguous ai-sdlc-kit markers' "$proj/.ai-sdlc/install-report.md")" "1"
rm -rf "$tmp"

# Root .github/copilot-instructions.md, same shape.
tmp=$(mktemp -d); proj="$tmp/malc"; mkdir -p "$proj/.github"
printf '<!-- ai-sdlc-kit:begin -->\nstray copilot content, no end marker\n' > "$proj/.github/copilot-instructions.md"
( cd "$proj" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Malformed Copilot" --slug malformed-copilot --dir "$proj" --desc "d" --ticket ACME \
        --layout embedded --tools "copilot" --merge --non-interactive >/dev/null 2>&1
mal_copilot_rc=$?
check mal_copilot_exit      "$mal_copilot_rc" "0"
check mal_copilot_unchanged "$(grep -c 'stray copilot content' "$proj/.github/copilot-instructions.md")" "1"
check mal_copilot_reported  "$(grep -c 'malformed .github/copilot-instructions.md' "$proj/.ai-sdlc/install-report.md")" "1"
rm -rf "$tmp"

# .gemini/settings.json with invalid JSON: never clobbered, reported instead
# of silently rewritten (the Critical fix — was previously destroyed and
# reported as a success).
tmp=$(mktemp -d); proj="$tmp/malg"; mkdir -p "$proj/.gemini"
printf '{"theme":"dark","custom_api_keys":["SECRET-123"], invalid syntax here' > "$proj/.gemini/settings.json"
cp "$proj/.gemini/settings.json" "$tmp/gemini-before"
( cd "$proj" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Malformed Gemini" --slug malformed-gemini --dir "$proj" --desc "d" --ticket ACME \
        --layout embedded --tools "gemini" --merge --non-interactive >/dev/null 2>&1
mal_gemini_rc=$?
check mal_gemini_exit      "$mal_gemini_rc" "0"
check mal_gemini_unchanged "$(cmp -s "$tmp/gemini-before" "$proj/.gemini/settings.json" && echo same)" "same"
check mal_gemini_reported  "$(grep -c 'malformed .gemini/settings.json' "$proj/.ai-sdlc/install-report.md")" "1"
# Cosmetic fix (review round 2): the JSON path's reported reason must not
# claim ambiguous markers — JSON has no markers.
check mal_gemini_reason_ok  "$(grep 'malformed .gemini/settings.json' "$proj/.ai-sdlc/install-report.md" | grep -c 'invalid or unsupported JSON')" "1"
check mal_gemini_no_marker_text "$(grep 'malformed .gemini/settings.json' "$proj/.ai-sdlc/install-report.md" | grep -c 'ambiguous ai-sdlc-kit markers')" "0"
rm -rf "$tmp"

# A syntactically valid but non-object .gemini/settings.json (the review-
# round-2 regression: used to crash with an uncaught AttributeError,
# corrupting the pointer line and never reaching the install report).
tmp=$(mktemp -d); proj="$tmp/malg2"; mkdir -p "$proj/.gemini"
printf '[1,2,3]' > "$proj/.gemini/settings.json"
cp "$proj/.gemini/settings.json" "$tmp/gemini-before"
( cd "$proj" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Malformed Gemini Array" --slug malformed-gemini-array --dir "$proj" --desc "d" --ticket ACME \
        --layout embedded --tools "gemini" --merge --non-interactive >"$tmp/boot.log" 2>&1
mal_gemini_array_rc=$?
check mal_gemini_array_exit       "$mal_gemini_array_rc" "0"
check mal_gemini_array_unchanged  "$(cmp -s "$tmp/gemini-before" "$proj/.gemini/settings.json" && echo same)" "same"
check mal_gemini_array_reported   "$(grep -c 'malformed .gemini/settings.json' "$proj/.ai-sdlc/install-report.md")" "1"
rm -rf "$tmp"

# --- 8. --hooks repo folds into an existing config without losing it ---------------
tmp=$(mktemp -d); mkdir -p "$tmp/acme-api"
printf 'repos:\n  - repo: local\n    hooks:\n      - id: mine\n        name: mine\n        entry: echo\n        language: system\n' \
  > "$tmp/acme-api/.pre-commit-config.yaml"
"$BOOT" --name "Acme" --slug acme --dir "$tmp/acme-sdlc" --desc "d" --ticket ACME \
        --layout sidecar --hooks repo --hooks-target "$tmp/acme-api" \
        --non-interactive >/dev/null 2>&1
check hooks_kept_mine  "$(grep -c 'id: mine' "$tmp/acme-api/.pre-commit-config.yaml")" "1"
# grep for the `id:` line specifically — the real kit config also mentions
# validate-skills in its `entry:` line (script path), so a bare substring
# count would over-count.
check hooks_added_kit  "$(grep -c '^[[:space:]]*- id: validate-skills$' "$tmp/acme-api/.pre-commit-config.yaml")" "1"
# fix-round 1, finding 2: the backup filename is now derived from
# $hooks_target (basename + checksum of its absolute path), not a fixed
# per-kit-install name — match it with a glob instead of an exact name.
hooks_backup_glob="$tmp/acme-sdlc/.ai-sdlc/pre-commit-config.backup.acme-api-"*".yaml"
check hooks_backup      "$(ls $hooks_backup_glob 2>/dev/null | wc -l | tr -d ' ')" "1"
check hooks_backup_orig "$(grep -c 'id: mine' $hooks_backup_glob 2>/dev/null)" "1"
check hooks_manifest    "$(jqp "$tmp/acme-sdlc/.ai-sdlc/kit.json" hooks)" '"repo"'
rm -rf "$tmp"

# --- 8b. fix-round 2, finding 1: --hooks repo against a repo with NO existing
#         config still rewrites the entry paths -----------------------------------
# The copy branch used to bypass the prefix rewriting entirely: every `entry:`
# stayed `python scripts/validate-skills.py`, unresolvable from the code repo,
# and the repo's next commit was blocked by commit-msg-ticket.
tmp=$(mktemp -d); mkdir -p "$tmp/acme-api"
"$BOOT" --name "Acme" --slug acme --dir "$tmp/acme-sdlc" --desc "d" --ticket ACME \
        --layout sidecar --hooks repo --hooks-target "$tmp/acme-api" \
        --non-interactive >/dev/null 2>&1
check hooks_new_config_made    "$([ -f "$tmp/acme-api/.pre-commit-config.yaml" ] && echo yes)" "yes"
check hooks_new_config_prefix  "$(grep -c 'entry: python ../acme-sdlc/scripts/validate-skills.py' "$tmp/acme-api/.pre-commit-config.yaml")" "1"
check hooks_new_config_ticket  "$(grep -c 'entry: python ../acme-sdlc/scripts/git/commit_msg_ticket.py --mode warn' "$tmp/acme-api/.pre-commit-config.yaml")" "1"
check hooks_new_config_unprefixed "$(grep -c 'entry: python scripts/' "$tmp/acme-api/.pre-commit-config.yaml")" "0"
# The rewritten path actually resolves from the code repo back to the kit.
check hooks_new_config_resolves "$([ -f "$tmp/acme-api/../acme-sdlc/scripts/validate-skills.py" ] && echo yes || echo no)" "yes"
check hooks_new_config_stages  "$(grep -c 'default_install_hook_types' "$tmp/acme-api/.pre-commit-config.yaml")" "1"
# Nothing to recover to, so no backup is written for a config that did not exist.
check hooks_new_config_nobackup "$(ls "$tmp/acme-sdlc/.ai-sdlc/pre-commit-config.backup."*.yaml 2>/dev/null | wc -l | tr -d ' ')" "0"
# An embedded layout needs no prefix and must not gain one.
mkdir -p "$tmp/emb-code"
"$BOOT" --name "Emb" --slug emb --dir "$tmp/emb" --desc "d" --ticket E \
        --layout embedded --hooks repo --hooks-target "$tmp/emb-code" \
        --non-interactive >/dev/null 2>&1
check hooks_embedded_no_prefix "$(grep -c 'entry: python scripts/validate-skills.py' "$tmp/emb-code/.pre-commit-config.yaml")" "1"
rm -rf "$tmp"

# --- 9. fix-round 1 findings: shape-safety, per-target backups, early
#        --hooks-target validation, truthful pre-commit-install reporting ---

# finding 3: a --hooks-target that does not exist is rejected up front, with
# no partial work (the kit --dir itself is never created).
tmp=$(mktemp -d)
"$BOOT" --name "Acme" --slug acme --dir "$tmp/acme-sdlc" --desc "d" --ticket ACME \
        --layout sidecar --hooks repo --hooks-target "$tmp/does-not-exist" \
        --non-interactive >"$tmp/log.txt" 2>&1
missing_target_rc=$?
check hooks_missing_target_exit   "$missing_target_rc" "2"
check hooks_missing_target_msg    "$(grep -c -- '--hooks-target .* does not exist' "$tmp/log.txt")" "1"
check hooks_missing_target_no_dir "$([ -d "$tmp/acme-sdlc" ] && echo made || echo none)" "none"
rm -rf "$tmp"

# finding 2 (bootstrap-level): two different --hooks-target repos folded from
# the SAME kit install get two distinct, non-colliding backups, each holding
# its own repo's original content.
tmp=$(mktemp -d); mkdir -p "$tmp/repo-a" "$tmp/repo-b"
printf 'repos:\n  - repo: local\n    hooks:\n      - id: a-own\n        name: a\n        entry: echo\n        language: system\n' \
  > "$tmp/repo-a/.pre-commit-config.yaml"
printf 'repos:\n  - repo: local\n    hooks:\n      - id: b-own\n        name: b\n        entry: echo\n        language: system\n' \
  > "$tmp/repo-b/.pre-commit-config.yaml"
"$BOOT" --name "Acme" --slug acme --dir "$tmp/acme-sdlc" --desc "d" --ticket ACME \
        --layout sidecar --hooks repo --hooks-target "$tmp/repo-a" \
        --non-interactive >/dev/null 2>&1
"$BOOT" --name "Acme" --slug acme --dir "$tmp/acme-sdlc" --desc "d" --ticket ACME \
        --layout sidecar --merge --hooks repo --hooks-target "$tmp/repo-b" \
        --non-interactive >/dev/null 2>&1
backup_a_glob="$tmp/acme-sdlc/.ai-sdlc/pre-commit-config.backup.repo-a-"*".yaml"
backup_b_glob="$tmp/acme-sdlc/.ai-sdlc/pre-commit-config.backup.repo-b-"*".yaml"
check hooks_two_targets_backup_a       "$(ls $backup_a_glob 2>/dev/null | wc -l | tr -d ' ')" "1"
check hooks_two_targets_backup_b       "$(ls $backup_b_glob 2>/dev/null | wc -l | tr -d ' ')" "1"
check hooks_two_targets_backup_a_owns  "$(grep -c 'id: a-own' $backup_a_glob 2>/dev/null)" "1"
check hooks_two_targets_backup_b_owns  "$(grep -c 'id: b-own' $backup_b_glob 2>/dev/null)" "1"
rm -rf "$tmp"

# finding 2 (repeat-run): a second run against the SAME target (the kit
# gained new hooks in between, simulated by re-running against its own
# already-merged config having more ids present than the first pass) must
# not replace the backup with post-merge content — it still holds the
# original "mine"-only file from before the first merge ever ran.
tmp=$(mktemp -d); mkdir -p "$tmp/acme-api"
printf 'repos:\n  - repo: local\n    hooks:\n      - id: mine\n        name: mine\n        entry: echo\n        language: system\n' \
  > "$tmp/acme-api/.pre-commit-config.yaml"
"$BOOT" --name "Acme" --slug acme --dir "$tmp/acme-sdlc" --desc "d" --ticket ACME \
        --layout sidecar --hooks repo --hooks-target "$tmp/acme-api" \
        --non-interactive >/dev/null 2>&1
"$BOOT" --name "Acme" --slug acme --dir "$tmp/acme-sdlc" --desc "d" --ticket ACME \
        --layout sidecar --merge --hooks repo --hooks-target "$tmp/acme-api" \
        --non-interactive >/dev/null 2>&1
repeat_backup_glob="$tmp/acme-sdlc/.ai-sdlc/pre-commit-config.backup.acme-api-"*".yaml"
check hooks_repeat_backup_still_orig     "$(grep -c 'id: mine' $repeat_backup_glob 2>/dev/null)" "1"
check hooks_repeat_backup_no_kit_hooks   "$(grep -c '^[[:space:]]*- id: validate-skills$' $repeat_backup_glob 2>/dev/null)" "0"
check hooks_repeat_target_has_kit_hooks  "$(grep -c '^[[:space:]]*- id: validate-skills$' "$tmp/acme-api/.pre-commit-config.yaml")" "1"
rm -rf "$tmp"

# finding 4: a --hooks-target that exists but is not a git repo — bootstrap
# completes (non-fatal), and the message reports the failed install rather
# than a false "installed" claim.
if command -v pre-commit >/dev/null 2>&1; then
  tmp=$(mktemp -d); mkdir -p "$tmp/not-a-git-repo"
  printf 'repos:\n  - repo: local\n    hooks: []\n' > "$tmp/not-a-git-repo/.pre-commit-config.yaml"
  "$BOOT" --name "Acme" --slug acme --dir "$tmp/acme-sdlc" --desc "d" --ticket ACME \
          --layout sidecar --hooks repo --hooks-target "$tmp/not-a-git-repo" \
          --non-interactive >"$tmp/log.txt" 2>&1
  notgit_rc=$?
  check hooks_notgit_exit        "$notgit_rc" "0"
  check hooks_notgit_failed_msg  "$(grep -c 'pre-commit hook install FAILED' "$tmp/log.txt")" "1"
  check hooks_notgit_no_false_ok "$(grep -c 'installed pre-commit hooks in' "$tmp/log.txt")" "0"
  rm -rf "$tmp"
else
  echo "skip hooks_notgit_* (pre-commit not installed)"
fi

# --- 10. fix-round 2, finding 3: the install report reflects the FINAL state -------
# It used to be written BEFORE the marker merges ran, so every file that was
# successfully merged was reported as a `collision` — which SKILL.md tells the
# agent to relay as a file "only the user can resolve by hand".
tmp=$(mktemp -d); proj="$tmp/api"; mkdir -p "$proj"
printf '# Acme API\n\nOurs.\n' > "$proj/README.md"
printf '# ours\n'              > "$proj/CLAUDE.md"
printf 'keepme\n'              > "$proj/AGENTS.md"
printf 'dist/\n'               > "$proj/.gitignore"
( cd "$proj" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Acme API" --slug acme-api --dir "$proj" --desc "d" --ticket ACME \
        --layout embedded --tools "claude" --merge --non-interactive >/dev/null 2>&1
rep="$proj/.ai-sdlc/install-report.md"
check report_readme_merged     "$(grep -c '^- merged README.md' "$rep")" "1"
check report_readme_no_coll    "$(grep -c '^- collision README.md$' "$rep")" "0"
check report_claude_merged     "$(grep -c '^- merged CLAUDE.md' "$rep")" "1"
check report_claude_no_coll    "$(grep -c '^- collision CLAUDE.md$' "$rep")" "0"
check report_agents_merged     "$(grep -c '^- merged AGENTS.md' "$rep")" "1"
check report_gitignore_merged  "$(grep -c '^- merged .gitignore' "$rep")" "1"
# The project's own content survived every one of those merges.
check report_readme_kept       "$(head -1 "$proj/README.md")" "# Acme API"
check report_agents_kept       "$(head -1 "$proj/AGENTS.md")" "keepme"
# The report is committed with the rest of the install (it is written before
# the initial commit, not after it).
rm -rf "$tmp"

tmp=$(mktemp -d)
"$BOOT" --name "Fresh" --slug fresh --dir "$tmp/f" --desc "d" --ticket F \
        --layout embedded --merge --non-interactive >/dev/null 2>&1
check report_committed "$(cd "$tmp/f" && git ls-files .ai-sdlc/install-report.md)" ".ai-sdlc/install-report.md"
check manifest_committed "$(cd "$tmp/f" && git ls-files .ai-sdlc/kit.json)" ".ai-sdlc/kit.json"
rm -rf "$tmp"

# --- 11. fix-round 2, finding 2: .gitignore is marker-merged ------------------------
# A project with its own .gitignore used to get `- collision .gitignore` and
# nothing else, so USER.md / .env / .env.* were never ignored and the identity
# file created at onboarding was committable.
tmp=$(mktemp -d); proj="$tmp/api"; mkdir -p "$proj"
printf 'dist/\nbuild/\n' > "$proj/.gitignore"
( cd "$proj" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Acme" --slug acme --dir "$proj" --desc "d" --ticket ACME \
        --layout embedded --merge --non-interactive >/dev/null 2>&1
check gi_kept_theirs   "$(head -1 "$proj/.gitignore")" "dist/"
check gi_kept_theirs2  "$(grep -c '^build/$' "$proj/.gitignore")" "1"
check gi_hash_marker   "$(grep -cx '# ai-sdlc-kit:begin' "$proj/.gitignore")" "1"
check gi_no_html       "$(grep -c -- '<!-- ai-sdlc-kit:begin -->' "$proj/.gitignore")" "0"
check gi_user_md       "$(grep -cx 'USER.md' "$proj/.gitignore")" "1"
check gi_env           "$(grep -cx '\.env' "$proj/.gitignore")" "1"
check gi_env_star      "$(grep -cx '\.env\.\*' "$proj/.gitignore")" "1"
# git itself now ignores the per-person identity file.
printf 'me\n' > "$proj/USER.md"
check gi_git_ignores   "$(cd "$proj" && git status --porcelain USER.md | wc -l | tr -d ' ')" "0"
# Idempotent: a second run updates the block in place, no second copy.
"$BOOT" --name "Acme" --slug acme --dir "$proj" --desc "d" --ticket ACME \
        --layout embedded --merge --non-interactive >/dev/null 2>&1
check gi_one_block     "$(grep -cx '# ai-sdlc-kit:begin' "$proj/.gitignore")" "1"
check gi_user_md_once  "$(grep -cx 'USER.md' "$proj/.gitignore")" "1"
rm -rf "$tmp"

# A project with NO .gitignore gets the kit's file whole — and no second,
# block-wrapped copy of the same lines inside it.
tmp=$(mktemp -d); proj="$tmp/bare"; mkdir -p "$proj"
printf 'x\n' > "$proj/keep.txt"
( cd "$proj" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Bare" --slug bare --dir "$proj" --desc "d" --ticket B \
        --layout embedded --merge --non-interactive >/dev/null 2>&1
check gi_fresh_no_block "$(grep -cx '# ai-sdlc-kit:begin' "$proj/.gitignore")" "0"
check gi_fresh_user_md  "$(grep -cx 'USER.md' "$proj/.gitignore")" "1"
rm -rf "$tmp"

# --- 12. fix-round 2, finding 7: the manifest records the REAL pointer outcome -----
# `"pointer":false` was hard-coded even when pointers were written, so spec §6's
# "a code repo without a pointer block" status check was a false positive on
# every installed project. `:nopointer` makes a user's "no" expressible.
tmp=$(mktemp -d); mkdir -p "$tmp/acme-api" "$tmp/acme-web"
"$BOOT" --name "Acme" --slug acme --dir "$tmp/acme-sdlc" --desc "d" --ticket ACME \
        --layout sidecar --repos "../acme-api=backend,../acme-web=frontend:nopointer" \
        --non-interactive >"$tmp/log.txt" 2>&1
man="$tmp/acme-sdlc/.ai-sdlc/kit.json"
ptr() { python3 -c 'import json,sys;print(json.dumps(json.load(open(sys.argv[1]))["repos"][int(sys.argv[2])][sys.argv[3]]))' "$man" "$1" "$2"; }
check ptr_true_recorded  "$(ptr 0 pointer)" "true"
check ptr_false_recorded "$(ptr 1 pointer)" "false"
check ptr_role_clean     "$(ptr 1 role)"    '"frontend"'
check ptr_written        "$([ -f "$tmp/acme-api/AGENTS.md" ] && echo yes || echo no)" "yes"
check ptr_declined       "$([ -f "$tmp/acme-web/AGENTS.md" ] && echo yes || echo no)" "no"
check ptr_declined_said  "$(grep -c 'pointer declined (:nopointer)' "$tmp/log.txt")" "1"
# The declined repo is still listed in AGENTS.md §2 — decision 4 lists it, it
# just carries no pointer.
check ptr_declined_listed "$(grep -c 'acme-web' "$tmp/acme-sdlc/AGENTS.md")" "1"
# A repo named in --repos that is not on disk stays "pointer": false.
mkdir -p "$tmp/two"
"$BOOT" --name "Acme2" --slug acme2 --dir "$tmp/two/sdlc" --desc "d" --ticket A \
        --layout sidecar --repos "../ghost=backend" --non-interactive >/dev/null 2>&1
check ptr_missing_repo "$(python3 -c 'import json,sys;print(json.dumps(json.load(open(sys.argv[1]))["repos"][0]["pointer"]))' "$tmp/two/sdlc/.ai-sdlc/kit.json")" "false"
# --help documents the syntax.
check ptr_help_documented "$([ "$("$BOOT" --help | grep -c ':nopointer')" -gt 0 ] && echo yes || echo no)" "yes"
rm -rf "$tmp"

# --- 13. fix-round 2, finding 8: .ai-sdlc/kit.json is not clobbered -----------------
# The manifest was the only unguarded `>` in --merge mode.
tmp=$(mktemp -d); proj="$tmp/api"; mkdir -p "$proj/.ai-sdlc"
printf '{"ourOwnTool": {"secret": "keep-me"}}\n' > "$proj/.ai-sdlc/kit.json"
cp "$proj/.ai-sdlc/kit.json" "$tmp/before.json"
( cd "$proj" && git init -q && git add -A && git commit -qm init )
"$BOOT" --name "Acme" --slug acme --dir "$proj" --desc "d" --ticket ACME \
        --layout embedded --merge --non-interactive >"$tmp/log.txt" 2>&1
check manifest_guard_exit      "$?" "0"
check manifest_guard_unchanged "$(cmp -s "$tmp/before.json" "$proj/.ai-sdlc/kit.json" && echo same)" "same"
check manifest_guard_reported  "$(grep -c '^- collision .ai-sdlc/kit.json' "$proj/.ai-sdlc/install-report.md")" "1"
check manifest_guard_said      "$(grep -c 'kit.json already exists and is not the kit' "$tmp/log.txt")" "1"
rm -rf "$tmp"

# The kit's OWN manifest is still rewritten on a repeat run (it carries a
# top-level "kit" object), so version/commit stay current.
tmp=$(mktemp -d); proj="$tmp/api"; mkdir -p "$proj"; printf 'x\n' > "$proj/keep.txt"
"$BOOT" --name "Acme" --slug acme --dir "$proj" --desc "d" --ticket ACME --layout embedded \
        --merge --kit-version 1.0.0 --non-interactive >/dev/null 2>&1
"$BOOT" --name "Acme" --slug acme --dir "$proj" --desc "d" --ticket ACME --layout embedded \
        --merge --kit-version 2.0.0 --non-interactive >/dev/null 2>&1
check manifest_own_updated "$(jqp "$proj/.ai-sdlc/kit.json" kit.version)" '"2.0.0"'
rm -rf "$tmp"

# --- 14. fix-round 2, finding 9: --host is recorded in the manifest ------------------
# It used to be parsed, echoed once and discarded, while SKILL.md asked for it.
tmp=$(mktemp -d)
"$BOOT" --name "Acme" --slug acme --dir "$tmp/k" --desc "d" --ticket A \
        --host gitlab --layout embedded --non-interactive >/dev/null 2>&1
check host_recorded "$(jqp "$tmp/k/.ai-sdlc/kit.json" host)" '"gitlab"'
"$BOOT" --name "Acme" --slug acme --dir "$tmp/k2" --desc "d" --ticket A \
        --layout embedded --non-interactive >/dev/null 2>&1
check host_default  "$(jqp "$tmp/k2/.ai-sdlc/kit.json" host)" '"github"'
rm -rf "$tmp"

# --- 15. fix-round 2, finding 10: the generated README carries a layout diagram -----
tmp=$(mktemp -d); mkdir -p "$tmp/acme-api"
"$BOOT" --name "Acme" --slug acme --dir "$tmp/acme-sdlc" --desc "d" --ticket A \
        --layout sidecar --repos "../acme-api=backend" --non-interactive >/dev/null 2>&1
check diagram_present "$(grep -c 'the folder that holds them all' "$tmp/acme-sdlc/README.md")" "1"
check diagram_kit_dir "$(grep -c '├── acme-sdlc/   ← the kit' "$tmp/acme-sdlc/README.md")" "1"
check diagram_repo    "$(grep -c '├── acme-api/   ← backend repo' "$tmp/acme-sdlc/README.md")" "1"
rm -rf "$tmp"
tmp=$(mktemp -d)
"$BOOT" --name "Acme" --slug acme --dir "$tmp/emb" --desc "d" --ticket A \
        --layout embedded --non-interactive >/dev/null 2>&1
check diagram_embedded "$(grep -c "project's own code, untouched" "$tmp/emb/README.md")" "1"
rm -rf "$tmp"

echo "---"
[ "$fails" -eq 0 ] && echo "all bootstrap tests passed" || echo "$fails test(s) failed"
exit "$fails"
