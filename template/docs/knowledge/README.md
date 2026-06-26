# Knowledge layer (pillar 5) — Sources → KG / RAG / vector store

This is where the project's **own knowledge** lives so agents can **ground** answers on it instead of guessing (`AGENTS.md` §4.4). It is the board's top row: *Sources → ingest → Knowledge Graph / RAG / VectorDB.*

```
docs/knowledge/
├── README.md        # this file
├── schema.md        # the record/metadata schema for sources + chunks
├── sources/         # the ingestable source documents (tracked in git)
└── .index/          # built index — GIT-IGNORED (a derived artefact)
```

## Quick start

```bash
# 1. Add sources (Markdown/text) under sources/ — give each one frontmatter (see schema.md)
# 2. Build the index
python3 ../../scripts/knowledge/ingest.py --build
# 3. Query it
python3 ../../scripts/knowledge/ingest.py --query "how do we handle X"
python3 ../../scripts/knowledge/ingest.py --stats
```

The shipped ingester ([`../../scripts/knowledge/ingest.py`](../../scripts/knowledge/ingest.py)) is a **dependency-light stub**: it chunks sources and does keyword search. It exists so the layer is real and runnable from day one — not to be the final implementation.

## Growing it into production

Pick one of two paths (they can coexist):

**A. Local/embedded vector store** — keep ingestion in-repo, swap keyword search for embeddings:
- Embeddings: a local model, or a provider via the **Vercel AI Gateway** (`provider/model` strings) — see the AI SDK.
- Vector store: `sqlite-vec`, DuckDB-VSS, LanceDB, or `pgvector` if you already run Postgres.
- Add a knowledge-graph layer (entities + relations) if your domain benefits from structured traversal, not just similarity.

**B. Hosted knowledge MCP server** — point the `knowledge` server in [`../../.mcp.json`](../../.mcp.json) at a managed vector DB / KG and let agents **ingest and query over MCP**. Then this folder holds the *source of truth documents*; the store is external.

## Trust & curation

- Every source carries a frontmatter `ai-trust` tier (`schema.md`); the ingester records it per chunk so answers can be cited with their tier (`AGENTS.md` §4.2).
- **Curation is human** (pillar 7): what enters the layer, and what gets pruned, is a deliberate act — not an automatic crawl.
- Never ingest secrets or real personal data. Sources are git-tracked and visible.
