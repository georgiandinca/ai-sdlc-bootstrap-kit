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

# Scope to one namespace
python3 scripts/knowledge/ingest.py --scope kit-code --trace ADR-0001

# Content search + stats
python3 scripts/knowledge/ingest.py --federated --query "knowledge graph"
python3 scripts/knowledge/ingest.py --stats
```

Agents can also reach it over MCP: the `knowledge` server (`.mcp.json`) exposes
`kg_query`, `kg_federated_query`, and `kg_trace`.

## Adding a repo

Add a namespace to `graph-manifest.json` (`kind: code|docs`, its `db` path, and
`roots`), then rebuild. Scoped queries stay isolated to that namespace; federated
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
