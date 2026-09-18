---
name: install-ai-sdlc-kit
description: Use when someone wants to install, set up, bootstrap or adopt the AI-SDLC Bootstrap Kit in a project, or when a project already has the kit and a person needs onboarding. Triggers on "install the kit", "set up AI-SDLC", "bootstrap this repo", "add AI governance to this project", "onboard me", and on finding AGENTS.md with no USER.md. Works out which of three situations applies — no kit, kit present but this person not onboarded, or fully set up — and does only what that situation needs. Not for authoring new skills (use skill-creator) and not for updating an installed kit to a newer version.
metadata:
  status: "approved"
  classification: "internal"
  ai-trust: "working"
  owner: "Architect"
---

# install-ai-sdlc-kit

Installs the [AI-SDLC Bootstrap Kit](https://github.com/georgiandinca/ai-sdlc-bootstrap-kit) into any project, in the layout that project needs, and hands over to the project's own onboarding.

## Step 1 — Check the situation first. Always.

Run the situation check before asking the user anything:

```bash
"$CLAUDE_PLUGIN_ROOT/.claude/skills/install-ai-sdlc-kit/scripts/detect-situation.sh"
```

(When the kit repo itself is open, the path is `.claude/skills/install-ai-sdlc-kit/scripts/detect-situation.sh`.)

It prints one JSON object and writes nothing. Read it, then take exactly one path:

| `kit.state` | `user_md` | Path |
|---|---|---|
| `absent` | — | **Setup** (Step 2), then **Onboarding** (Step 3) |
| `present-uncommitted` | — | Say the kit is installed but not committed; offer to commit it; then re-run this check |
| `present-committed` | `false` | **Onboarding** only (Step 3) |
| `present-committed` | `true` | **Status** (Step 4) |

Never install when `kit.state` is not `absent`. Never re-run onboarding when `USER.md` exists.

`kit.manifest` is only trustworthy when `kit.manifest_valid` is `true`. It is `false` when
`.ai-sdlc/kit.json` is absent or fails to parse as JSON — in that case treat `kit.manifest`
as unknown rather than reading fields out of it (Step 4's version-drift check needs a valid
manifest; if it isn't valid, say so and stop there instead of comparing against `null`).

## Step 2 — Setup

Ask these, in this order, proposing the detected answer first so the common case is one confirmation:

1. **Layout** — propose from `layout_signals`, in this order: `embedded` (kit inside this repo) → `monorepo` (kit at the workspace root; `workspace_files` non-empty) → `sidecar` (kit beside the code repos; `sibling_repos` non-empty) → `parent` (kit above the code repos; `child_repos` non-empty). `references/layouts.md` describes what each one writes where, and their trade-offs.
2. **Project facts** — name, one-line description, ticket prefix, host (`github`/`gitlab`).
3. **Repos and roles** — for `monorepo`/`sidecar`/`parent`, e.g. `../acme-api=backend`.
4. **Hooks** — `kit` (governance hooks on the kit's own repo), `repo` (fold them into a code repo's existing `.pre-commit-config.yaml`; requires `--hooks-target <dir>` pointing at that repo), or `none` (no versioning, or the team does not want them). If `repo`, warn up front: the merge is done with PyYAML, which does not preserve comments in the target's `.pre-commit-config.yaml`. The pre-merge original is backed up automatically under the kit's own `.ai-sdlc/` directory (a filename derived from the target repo's path), so it can always be recovered, but the live file in the code repo loses its comments.
5. **AI tools** — which the team uses. Most read `AGENTS.md` natively and need nothing; see `references/pointer-blocks.md`.
6. **Pointers into code repos** — ask per repo, default yes.

Then clone the kit and install:

```bash
KIT=$(mktemp -d)
git clone --depth 1 https://github.com/georgiandinca/ai-sdlc-bootstrap-kit "$KIT"
"$KIT/template/scripts/bootstrap.sh" --name "<name>" --slug "<slug>" --dir "<target>" \
  --desc "<desc>" --ticket "<TICKET>" --host "<host>" --layout "<layout>" \
  --repos "<path=role,…>" --tools "<ids>" --hooks "<mode>" [--merge] \
  [--hooks-target <dir>] [--kit-version <v>] [--kit-commit <sha>]
```

`--hooks-target <dir>` is required whenever `--hooks repo` is used — it names the code
repo whose `.pre-commit-config.yaml` gets the governance hooks folded in; omitting it is a
hard failure, checked before anything is written. `--kit-version`/`--kit-commit` are
optional overrides for the manifest; left out, `bootstrap.sh` derives them from the kit's
own git tags/HEAD.

Use `--merge` whenever the target already has files. Without it, `bootstrap.sh` refuses a non-empty directory — that refusal is a safety feature, so never reach for `--force` to get past it.

### Rules for this step

- **Show the whole plan before writing anything** — every file to be created, every file to be appended to, every collision that will be skipped — and get an explicit yes.
- **Never overwrite a file the project owns.** `bootstrap.sh` handles this; do not work around it by hand.
- **If the target repo already has commits, work on a branch** (`chore/ai-sdlc-kit`) so the install can be reviewed.
- **If the working tree is dirty** (`git.dirty`), say so and let the user decide before touching anything.
- **Never commit without showing what will be committed.**
- After installing, read `.ai-sdlc/install-report.md` (written whenever `--merge` was used) and tell the user what was created, what was merged, and what was skipped. Relay **every** `collision` and `malformed` line in it by name — those are the files the installer left byte-identical (an ambiguous marker layout, or, for `.gemini/settings.json`, a file that isn't a plain JSON object) and that only the user can resolve by hand. Do not summarise them away as "some files were skipped."

## Step 3 — Onboarding

Do not carry out the onboarding steps from memory and do not summarise them here. Read the installed project's `ONBOARDING.md` and follow it exactly — it is the single source of truth, it checks for `USER.md` itself, and it covers OS detection, tooling, identity, seat and git-comfort.

## Step 4 — Status

The kit is installed and this person is onboarded. Report, with a fix offered for each:

- **Version drift** — only when `kit.manifest_valid` is `true`: compare `kit.manifest.kit.version` with the latest tag of the public repo (`git ls-remote --tags`). Report the gap and what changed. **Do not update any files** — safe propagation is a separate piece of work. When `kit.manifest_valid` is `false`, report the manifest itself as malformed (absent or unparsable `.ai-sdlc/kit.json`) instead of guessing at a version.
- **Hooks not installed** (`hooks.config` true, `hooks.installed` false) — offer `pre-commit install`.
- **Repos missing from the manifest** — a sibling or child repo that appeared since install; offer to add it and write its pointer.
- **Unfilled placeholders** — `grep -roIn -- '<[A-Z_/]\{3,\}>' .` and list them.

## What this skill does not do

- **Update an installed kit.** Report drift, stop there.
- **Author skills.** That is `skill-creator`, inside the installed kit.
- **Onboard from memory.** Always via the project's `ONBOARDING.md`.

## Running without Claude Code

The situation check and `bootstrap.sh` are plain shell. Any agent can be pointed at this file and follow it, and a person can run the install directly:

```bash
git clone --depth 1 https://github.com/georgiandinca/ai-sdlc-bootstrap-kit /tmp/ai-sdlc-kit
/tmp/ai-sdlc-kit/template/scripts/bootstrap.sh --help
```
