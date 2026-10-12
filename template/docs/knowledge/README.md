# Knowledge layer (pillar 5) — a local docs+code graph

The project's **own knowledge** as a graph, so agents **ground** answers on it
instead of guessing (`AGENTS.md §4.4`). It spans **docs and code**, is isolated
per namespace, and answers **traceability** (ADR→code→test→story) as well as
content search.

```
docs/knowledge/
├── README.md              # this file
├── schema.md              # node/edge/link schema
├── graph-manifest.json    # namespace registry (TRACKED)
├── sources/               # ingestable source documents (TRACKED)
└── .knowledge/            # global overlay DB — GIT-IGNORED (derived)
<each namespace root>/.knowledge/graph.db   # per-namespace DB — GIT-IGNORED
```

## Quick start

```bash
# Build every namespace + the overlay
python3 scripts/knowledge/ingest.py --build

# Trace an ADR's chain (federated across docs + code)
python3 scripts/knowledge/ingest.py --federated --trace ADR-0001

# Only what names the ADR directly: the code and tests that carry its marker
python3 scripts/knowledge/ingest.py --trace ADR-0001 --depth 1

# Scope to one namespace
python3 scripts/knowledge/ingest.py --scope kit-code --trace ADR-0001

# Content search + stats
python3 scripts/knowledge/ingest.py --federated --query "knowledge graph"
python3 scripts/knowledge/ingest.py --stats

# Explore it visually: one self-contained HTML page (git-ignored, no network)
python3 scripts/knowledge/export_html.py --open
```

Agents can also reach it over MCP: the `knowledge` server (`.mcp.json`) exposes
`kg_query`, `kg_federated_query`, `kg_trace`, and `kg_freshness`.

## What is in it

`graph-manifest.json` ships with four namespaces: `docs` (`docs/`), `briefs`
(the briefs at the root and the skills), `kit-code` (`scripts/`, `dashboard/`)
and `issues` (the tracker export). A project adds a `code` namespace for each
of its code repositories (see "Adding a repo").

A root may be another git repository: one cloned under this one (the kit's
**parent layout**, where it is usually git-ignored here) or one beside it
(the **sidecar layout**, with a root such as `../acme-api/`). The build reads
such a repository by its own ignore rules, so its tracked files are ingested
and its `node_modules/` or `dist/` are not. A repository that is not cloned gives an empty namespace, not an
error, which is what happens in CI.

What the graph knows about code, and what it does not:

- **A code file is tied to a decision by an `ADR-NNNN` marker in a comment.**
  This is the link that carries most of the traceability. Code with no marker
  is in the graph as a file, tied to nothing.
- **A test is tied to its code by its name** (`test_x.py`, `x.test.tsx`), only
  when the code file sits in the test's folder or the one above. Tests
  that are not named after one file get no link this way.
- **Symbols.** Python is parsed. In other languages a line that starts with a
  definition keyword gives a symbol. That finds TypeScript and JavaScript
  definitions, and also some local variables and a few lines in shell
  scripts. SQL and OpenTofu files get no symbols.
- **Not ingested:** YAML, TOML and JSON files (CI workflows, `compose.yaml`,
  `pyproject.toml`, `package.json`), and the text of code files. A content
  search finds names and documents, not usages inside code; use `grep` for
  those.
- **Commit attribution** is linked for code in this repository, and not for
  a namespace read from another repository.

## Keeping it up to date

The graph is **derived and git-ignored**. Each person, and each agent session,
has the graph of what is checked out on that machine. Nothing is shared, and
nothing is committed.

1. **Get the sources current.** The graph describes the files on disk, so pull
   first: this repository, and each code repository cloned under it.
   ```bash
   git pull --ff-only
   for r in <repo-a> <repo-b>; do git -C "$r" pull --ff-only; done
   ```
2. **Rebuild.** It replaces every namespace. For a few thousand nodes it takes
   seconds.
   ```bash
   python3 scripts/knowledge/ingest.py --build
   ```
3. **Check.** `--freshness` compares the commit each repository was built from
   with the commit checked out now, and the manifest with the one built from.
   It exits 1 when they differ or nothing is built. `without_sources` in its
   answer names the namespaces that are empty because their folders are not on
   disk here.
   ```bash
   python3 scripts/knowledge/ingest.py --freshness
   ```

**When it happens by itself.** The session-start hook (`scripts/session/start.sh`)
runs the check and rebuilds when the graph is stale or unbuilt, and says which
namespaces have no sources. It does not pull the code repositories, and it
does not run again during a session. A session started inside another
repository does not run it: the script lives in this repository only.

**When to do it by hand.**

- After pulling or switching branch mid-session, in this repository or in any
  code repository the manifest names.
- After editing files you want to query before committing them: the check sees
  commits only, so it still says "fresh".
- After adding a namespace or a root to `graph-manifest.json`.
- In a git worktree of this repository (parent layout): the code repositories
  are cloned under the main checkout only, so a build inside a worktree has
  empty namespaces for them, and `without_sources` lists them. To get them, point the
  worktree's scripts at the main checkout. This reads the kit's files from the
  main checkout too, and replaces the graph kept there:
  ```bash
  python3 scripts/knowledge/ingest.py --build --base /path/to/main/checkout
  python3 scripts/knowledge/ingest.py --trace ADR-0001 --depth 1 --base /path/to/main/checkout
  ```
  Every later command needs the same `--base`. The MCP server and
  `export_html.py` take no such option: they follow the `KG_BASE` environment
  variable, which does the same thing, and the server already running in a
  session keeps answering from the graph it was started with.
  No single graph holds both a change to this repository that exists only in
  a worktree and the code of the other repositories.

**What the check does not see.** An edit that is not committed, and a
repository cloned below a root without being named as a root itself.

**Adding knowledge, as opposed to refreshing it.**

- A document: put it under `docs/` with the frontmatter contract, link it with
  `implements:` / `covers:` / `traces:` / `cites:` or a relative markdown link
  (`schema.md`), and rebuild.
- An external source (a standard, a client document): add it under
  `docs/knowledge/sources/` with its `ai-trust` tier. Curation is human.
- Code: write the `ADR-NNNN` it implements in a comment, and name its test
  after it.

An agent that grounds on the graph calls `kg_freshness` first and says so when
the graph is stale or empty (`AGENTS.md` §4.4).

## Adding a repo

Add a namespace to `graph-manifest.json` (`kind: code|docs`, its `db` path, and
`roots`), then rebuild. For a repository cloned under this one, keep the `db`
under `.knowledge/` here, so nothing is written into the other repository. A root is a folder (walked recursively) or a single
file; the `briefs` namespace uses file roots to bring the top-level briefs and
the skills into the graph, so links to them resolve. Scoped queries stay isolated to that namespace; federated
queries and the overlay tie repos together through shared `adr:`/`story:` ids.

## Growing it into production (documented, not built)

- **Embeddings / vector search** — swap term-scored `search` for embeddings
  (local model or a provider via the Vercel AI Gateway) + `sqlite-vec`/DuckDB-VSS/LanceDB/pgvector.
- **tree-sitter** — richer multi-language ASTs in `ingest_code.py`.
- **Hosted KG MCP** — point the `knowledge` slot at a managed graph/vector DB;
  this local server is the reference.

## Trust & curation

- Sources carry a frontmatter `ai-trust` tier (`schema.md`); it rides onto every
  `source` node so answers cite their tier (`AGENTS.md §4.2`).
- **Curation is human** (pillar 7). Never ingest secrets or real personal data.
