# Pointers — who needs one, and what gets written

`AGENTS.md` is canonical. Most agents read it with no configuration, so most need nothing.

| Tool | Reads `AGENTS.md` natively? | What the installer writes |
|---|---|---|
| OpenAI Codex (CLI + cloud) | yes | nothing |
| Cursor | yes (root + subdirectories) | nothing |
| Windsurf / Cascade | yes | nothing |
| Google Antigravity | yes (workspace root) | nothing |
| GitHub Copilot (github.com) | yes | nothing |
| GitHub Copilot (VS Code) | yes, behind a setting whose default is undocumented | optional `.github/copilot-instructions.md` pointer |
| **Claude Code** | **no — reads `CLAUDE.md`** | `CLAUDE.md` containing `@AGENTS.md` |
| **Gemini CLI** | **no — defaults to `GEMINI.md`** | `.gemini/settings.json` → `{"context":{"fileName":["AGENTS.md","GEMINI.md"]}}` |

Verified against official documentation on 2026-09-18. Re-check before adding a tool.

## The block

Every pointer written into a file the project owns goes inside markers, so a later run
updates it in place instead of appending a second copy:

```markdown
<!-- ai-sdlc-kit:begin -->
…pointer…
<!-- ai-sdlc-kit:end -->
```

Hash-comment files (`.gitignore`, YAML) use `# ai-sdlc-kit:begin` / `# ai-sdlc-kit:end`.
JSON files (Gemini settings) cannot carry comments — they are merged key-wise instead,
adding `AGENTS.md` only when it is not already listed. A `.gemini/settings.json` that
exists but is not a plain JSON object — or whose `context`/`context.fileName` isn't a
shape the merger understands — is left byte-identical and reported `malformed` in the
install report rather than guessed at or overwritten.

A target that leaves the project through a symlink — its own, or a parent directory's —
is never followed: nothing is written and the install report says `escaped`. A target that
cannot be written (read-only, or a path the project owns as a regular file where the kit
needs a directory) is reported `unwritable`. Both leave the file byte-identical, like
`collision` and `malformed`. An existing symlink *inside* the project is written through,
so the link survives instead of being replaced by a regular file.

## Pointers into code repos (`sidecar` / `parent`)

Ask per repo; the default is yes. A "no" is expressed as a `:nopointer` suffix on that
repo's role in `--repos` (`../acme-web=frontend:nopointer`) — the repo stays in
`AGENTS.md` §2 and in the manifest, nothing is written into it, and the manifest records
`"pointer": false`. Dropping the repo from `--repos` instead would also drop it from §2.

Each code repo that gets a pointer gets both:

- `AGENTS.md` — names the kit's relative path **and** its clone URL, so a fresh clone that
  lacks the sibling folder knows how to get it.
- `CLAUDE.md` — `@<rel>/AGENTS.md`. An import outside the repo prompts the user for
  approval once; that is expected, and worth saying up front.
