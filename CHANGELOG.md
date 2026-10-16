# Changelog

What changed in the AI-SDLC Bootstrap Kit, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

Each release has a heading with its version and date, and matches a git tag
(`v0.1.0`). Changes waiting for a release go under "Unreleased".
`bootstrap.sh` records `git describe --tags` in an installed project's
`.ai-sdlc/kit.json`, so the tag is also the kit version an installed project
compares against.

An entry says what a project that installs or updates the kit will notice.
**Updating** notes say what an already-installed project has to do by hand.

## Unreleased

### Added

- **Frontmatter debt baseline** — `bootstrap.sh --merge` records docs that
  already lack frontmatter in `.ai-sdlc/frontmatter-baseline.txt`, and the
  install report says how many. `validate-frontmatter.py` reports them as
  debt instead of failing, still fails on any new violation, and lists
  baselined files that are fixed or deleted. `--write-baseline` writes the
  baseline once and after that only shrinks it; `--no-baseline` shows the
  full debt. Files that git ignores are no longer checked.
  `docs/governance/README.md` says how to pay the baseline down. Adapted from
  Emil Dan's fork. ([#17])

### Updating

- An installed project that already fails the frontmatter gate on inherited
  docs can adopt them once with
  `python3 scripts/validate-frontmatter.py --write-baseline`.

## [0.1.1] — 2026-10-14

The plugin is listed in the Claude plugin directory, and the installer skill
can be installed with `npx skills add`.

### Added

- **Superseded documents are ignored** — `AGENTS.md` §4.2 treats a file with
  `status: superseded` as Exploratory whatever its `ai-trust` says. Knowledge
  graph search and trace leave such documents out; `--include-superseded`, or
  `include_superseded` on `kg_query`, `kg_federated_query` and `kg_trace`,
  brings them back. `validate-frontmatter.py` warns when a superseded file's
  `ai-trust` is not `exploratory`. ([#8])
- **Issue ledger: dependencies** — an optional `depends_on` column gives one
  `depends-on` edge per key. ([#8])
- **Issue keys a project can define** — `key_pattern` on the `issues` namespace
  of `graph-manifest.json` (default `ABC-123`) is used by the graph, by commit
  linking and by the `commit-msg` hook. A bare key given to `--trace` or
  `kg_trace` resolves to its issue. ([#8])
- **Knowledge graph: `exclude`** — a `docs` or `code` namespace takes a list of
  paths or globs below its roots that the graph leaves out. ([#8])
- This changelog.
- **Install with the skills CLI** — `npx skills add
  georgiandinca/ai-sdlc-bootstrap-kit` puts the installer skill into a project
  for any agent the CLI supports. The README documents it.

- **Privacy policy** — `PRIVACY.md` covers what the plugin reads and what
  onboarding stores. The plugin manifests link to it as `privacyPolicyUrl`,
  and the README links to it from a new Privacy section.

### Changed

- **The plugin is now `ai-sdlc-bootstrap-kit`, in its own folder** — the
  installer skill, its manifests and a new listing icon moved to
  `plugins/ai-sdlc-bootstrap-kit/`. Before this, the whole repository was the
  plugin, so the plugin directory scanned `docs/` and `template/` as plugin
  code. The plugin was renamed from `ai-sdlc-kit` because that name was too
  close to an existing listing. `.claude/skills/install-ai-sdlc-kit` is now a
  symlink to the moved skill. ([#10])

### Fixed

- The plugin no longer ships the situation-check test. Its monorepo case
  creates a `pnpm-workspace.yaml`, which the plugin directory blocked as
  redirecting the package registry. The test moved to `tests/installer/`,
  and CI still runs it. ([#13])
- The frontmatter parser of the knowledge graph kept a trailing YAML comment
  as part of a value (`status: approved  # …`). ([#8])
- The `ai-governance` workflow shipped to projects did not run the three issue
  test files. ([#8])

### Updating

- When superseding a file, set `ai-trust: exploratory` as well as
  `status: superseded`. Rebuild the graph after updating
  (`python3 scripts/knowledge/ingest.py --build`).
- If you installed the plugin as `ai-sdlc-kit`, reinstall it under its new
  name: `claude plugin uninstall ai-sdlc-kit@ai-sdlc-bootstrap-kit`, then
  `claude plugin marketplace update ai-sdlc-bootstrap-kit` and
  `claude plugin install ai-sdlc-bootstrap-kit@ai-sdlc-bootstrap-kit`. The
  skill is now invoked as `/ai-sdlc-bootstrap-kit:install-ai-sdlc-kit`.

## [0.1.0] — 2026-10-13

The first tagged release: everything from the first commit to the Reviewer
seat, grouped by the date a change was merged to `main`.

### 2026-10-13

#### Added

- **Reviewer seat** — a sixth named seat that does an independent review of
  each change before its pull request is opened, with its playbook
  (`playbook-reviewer`) and a read-on-demand review guide.
  `WORKING-AGREEMENT.md` §5.5 makes the review a rule; `AGENTS.md` §0 lets an
  agent given a seat in its brief skip onboarding. ([#6])

#### Updating

- `bootstrap.sh --merge` into a project that already has the kit creates the
  Reviewer playbook but keeps the project's own `seat-profiles.json`,
  `validate-seat-profiles.py`, `WORKING-AGREEMENT.md` and `AGENTS.md`. Merge
  the Reviewer seat into those four by hand.

### 2026-10-12

#### Added

- **Knowledge graph: nested repositories and freshness** — a namespace root
  may be another git repository, under the kit or beside it. `kg_freshness`
  and `ingest.py --freshness` say whether the graph was built from the commits
  checked out now, and `--depth` bounds a trace. ([#5])
- **Knowledge graph: HTML view** — `export_html.py` writes one self-contained
  page to explore the graph. Relative Markdown links become `links` edges, and
  a root may be a single file. ([#3])
- **Installer: Codex and Antigravity** — the kit installs as a plugin for both,
  and the installer's situation check runs read-only. ([#4])

### 2026-09-18

#### Added

- **`install-ai-sdlc-kit` skill** — installs the kit into any project, in any
  layout, and onboards a person to a project that already has it. `bootstrap.sh`
  gains layouts, `--merge` and a committed manifest of what it installed. ([#1])

#### Fixed

- Both pre-commit stages are installed, so the governance gate runs on commit. ([#2])

### 2026-07-22

#### Added

- Published on GitHub under the MIT license, with a contributing guide, code of
  conduct, security policy, issue and pull-request templates, and Dependabot.

### 2026-07-16

#### Added

- **Team session ledger** — each person's sessions are exported to a committed
  per-user CSV at session end and merged on import; the dashboard's Utilization
  view gains a by-user breakdown.
- **Token economy and ROI** — the `token-economy` rule pack, per-seat model
  routing defaults, and dashboard views for spend, waste signals and ROI.

### 2026-07-15

#### Added

- **Issue ledger** — `export_jira.py` writes a Jira project (Cloud or Data
  Center) to an idempotent CSV ledger. The knowledge graph ingests it as an
  `issues` namespace and links commits to the issues they name.

### 2026-07-03

#### Added

- **Knowledge graph** — a local docs-and-code graph, one SQLite database per
  namespace, replaces the keyword stub: scoped and federated search, `trace`
  for the ADR ↔ code ↔ test ↔ story chain, and a stdio MCP server
  (`kg_query`, `kg_federated_query`, `kg_trace`).

### 2026-07-02

#### Added

- **Metrics dashboard** — a commit-attribution collector and dashboard tab on a
  shared schema.
- **Session hooks** — SessionEnd and Stop hooks, the `git-verbs` skill for
  people who do not use git directly, and git-comfort-aware sync at session
  start.
- **Seats and onboarding** — onboarding in two phases (global, then seat), a
  per-seat profile manifest, `switch-seat.sh`, and artefact-scoped rules under
  `.claude/rules/`.
- **Shared primitives** — the session lifecycle-moments manifest and its
  validator; git-comfort captured during onboarding.

### 2026-06-26

#### Added

- First version of the kit: the `template/` scaffold with `AGENTS.md`, the
  working agreement, onboarding, five role playbooks, the frontmatter and skill
  validators, the AI-governance CI gate and a utilization dashboard.

[#1]: https://github.com/georgiandinca/ai-sdlc-bootstrap-kit/pull/1
[#2]: https://github.com/georgiandinca/ai-sdlc-bootstrap-kit/pull/2
[#3]: https://github.com/georgiandinca/ai-sdlc-bootstrap-kit/pull/3
[#4]: https://github.com/georgiandinca/ai-sdlc-bootstrap-kit/pull/4
[#5]: https://github.com/georgiandinca/ai-sdlc-bootstrap-kit/pull/5
[#6]: https://github.com/georgiandinca/ai-sdlc-bootstrap-kit/pull/6
[#8]: https://github.com/georgiandinca/ai-sdlc-bootstrap-kit/pull/8
[#10]: https://github.com/georgiandinca/ai-sdlc-bootstrap-kit/issues/10
[#13]: https://github.com/georgiandinca/ai-sdlc-bootstrap-kit/issues/13
[#17]: https://github.com/georgiandinca/ai-sdlc-bootstrap-kit/issues/17
[0.1.1]: https://github.com/georgiandinca/ai-sdlc-bootstrap-kit/releases/tag/v0.1.1
[0.1.0]: https://github.com/georgiandinca/ai-sdlc-bootstrap-kit/releases/tag/v0.1.0
