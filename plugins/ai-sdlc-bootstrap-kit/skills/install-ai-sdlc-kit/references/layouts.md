# The four layouts

Ask in this order. The first that fits is usually right.

## 1. `embedded` — the kit inside the repo

```
acme-api/
├── AGENTS.md  CLAUDE.md  ONBOARDING.md  WORKING-AGREEMENT.md
├── .claude/skills/   .github/workflows/   scripts/   docs/
├── .ai-sdlc/kit.json
└── src/                 ← the project's own code, untouched
```

One repo, one brief, hooks and CI protect the same repo the code lives in. Use `--merge`
when the repo already has files. **Best default.**

## 2. `monorepo` — the kit at the workspace root

Same file placement as `embedded`, at the root of a workspace that holds several packages.
`AGENTS.md` §2 lists each package and its role (`apps/web` = frontend, `services/api` = backend).
Signals: `pnpm-workspace.yaml`, `turbo.json`, `nx.json`, `lerna.json`, `go.work`, a Cargo `[workspace]`.

## 3. `sidecar` — the kit beside the code repos

```
acme/
├── acme-sdlc/     ← the kit, its own git repo
├── acme-api/      ← code repo + pointer block
└── acme-web/      ← code repo + pointer block
```

For several repos with different roles, or when the code repos cannot take the kit's files.
**Trade-off to state plainly:** the kit's hooks and CI protect `acme-sdlc` only. Use
`--hooks repo` to put the governance hooks into a code repo as well. Open the agent in
`acme-sdlc` and add the code repos with `--add-dir`, or rely on each repo's pointer.

## 4. `parent` — the kit above the code repos

```
acme/                  ← the kit lives here
├── AGENTS.md …
├── acme-api/          ← its own git repo
└── acme-web/          ← its own git repo
```

Same trade-offs as `sidecar`; the difference is that the parent folder may not be a git
repo at all. Use `--no-git` when it should not become one.

## Choosing when signals conflict

Signals propose; the user decides. State what you detected and why, then ask. A wrong
guess costs one keystroke — an unasked question costs a wrong install.
