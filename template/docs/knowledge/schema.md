# Knowledge schema — nodes, edges, and the link convention

The contract the ingesters (`scripts/knowledge/`) and the `knowledge` MCP server
follow. The knowledge layer is a **graph** over docs *and* code, isolated per
namespace and queryable scoped or federated. (This replaces the earlier
chunk/keyword schema; source-document frontmatter is unchanged.)

## Namespaces & the manifest

`docs/knowledge/graph-manifest.json` registers each namespace:

```json
{
  "namespaces": {
    "docs":     { "kind": "docs", "db": "docs/.knowledge/graph.db", "roots": ["docs/"] },
    "kit-code": { "kind": "code", "db": ".knowledge/graph.db",       "roots": ["scripts/", "dashboard/"] }
  },
  "overlay": "docs/knowledge/.knowledge/global.db"
}
```

Each namespace ingests into its own **git-ignored** `.knowledge/graph.db`. A
shared **`global` overlay** holds edges whose endpoints live in different
namespaces (e.g. code that implements a docs ADR) plus unresolved (dangling)
links. Add a repo by adding a namespace entry — no code change.

## Nodes

| kind | id form | source |
|---|---|---|
| `adr` | `adr:ADR-NNNN` | `docs/architecture/decisions/` |
| `story` | `story:AS-N` | `docs/product/stories/` |
| `doc` | `doc:<ns>:<path>` | any other tracked `.md` |
| `source` | `source:<ns>:<path>` | `docs/knowledge/sources/` |
| `code-file` | `code:<ns>:<path>` | tracked code (non-test) |
| `symbol` | `sym:<ns>:<path>:<name>` | `ast`/regex def/class |
| `test` | `test:<ns>:<path>` | `test_*.py` / `*_test.py` |
| `commit` | `commit:<ns>:<sha>` | optional Phase-3 commit layer |
| `issue` | `issue:<KEY>` | JIRA CSV ledger (`docs/product/jira/issues.csv`) |

Every node carries `namespace`, `path`, and (for docs) a `tier` from `ai-trust`,
so retrieved context is always citable with its trust tier (`AGENTS.md §4.2`).

## Edges

| kind | from → to | derived from |
|---|---|---|
| `implements` | code/symbol → adr | `# ADR-NNNN` marker; frontmatter `implements:` |
| `covers` | test → code | `test_x ↔ x` naming; frontmatter `covers:` |
| `traces` | story → adr | frontmatter `traces:` |
| `cites` | doc → source | frontmatter `cites:` |
| `supersedes` | adr → adr | frontmatter `supersedes:` |
| `imports` | code → code | `ast`/regex (intra-namespace only) |
| `contains` | code → symbol | `ast`/regex |
| `touches` | commit → code | git numstat (optional) |
| `part-of` | issue → issue | ledger `epic`/`parent` columns |
| `references` | commit → issue | `Refs: KEY` in commit messages (optional commit layer) |

Every edge stores `source_file` + `line` (its citation) and `resolved`
(`0` = the target node was not found — surfaced honestly, never invented).

## The link convention

- **Doc frontmatter** (optional lists): `implements:`, `covers:`, `traces:`,
  `cites:`, `supersedes:`. Values are ids (`ADR-0001`, `AS-0001`) or paths.
- **Code marker:** a comment containing `ADR-NNNN` → an `implements` edge (file
  level, plus symbol level when the marker is inside a def).
- **Naming:** `tests/test_x.py` → `covers` the same-namespace `x.py`.
- **JIRA keys:** a frontmatter link value matching `ABC-123` resolves to
  `issue:<KEY>`, linking docs/stories/ADRs to imported issues.

## Source-document frontmatter (unchanged)

Files under `sources/` still carry `title`, `source`, `ai-trust`,
`classification`, `last-reviewed` (see below). The ingester stamps `ai-trust`
onto the `source` node's `tier`.

```yaml
---
title: "Human-readable title"
source: "<origin — URL, system, or 'authored'>"
ai-trust: authoritative | working | exploratory
classification: public | internal | restricted
last-reviewed: YYYY-MM-DD
---
```

## Conventions

- **No secrets, no real personal data.** Sources and the manifest are tracked; the DBs are derived and git-ignored.
- **One topic per source file** where practical.
- This file (`schema.md`) is exempt from the frontmatter contract; source docs still carry it.
