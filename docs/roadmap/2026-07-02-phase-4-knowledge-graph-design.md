---
title: "Phase 4 — Docs + Code Knowledge Graph (design)"
status: draft
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-07-02
classification: internal
ai-trust: working
---

# Phase 4 — Docs + Code Knowledge Graph

**Goal.** Replace the keyword stub (`scripts/knowledge/ingest.py`, chunk + keyword search over `docs/knowledge/sources/`) with a local, per-repo-isolated **graph over docs *and* code**, carrying **traceability edges** (ADR → code → test → story), queryable **scoped** (one repo/docs-tree) or **federated** (whole project), and exposed via the already-declared `knowledge` MCP slot. Dependency-light: Python **stdlib only**, same posture as the stub and the Phase 3 collector.

**Non-negotiable framing.** This is a *template kit*. Phase 4 ships a **real, runnable reference** that ingests the kit's own docs+code, builds a genuine traceability chain, and answers scoped + federated queries — while the namespace/manifest design makes "add another repo" a config edit, not a rewrite. This mirrors how the stub is "real and runnable from day one, not the final implementation."

---

## 1. Decisions (resolved in brainstorming)

| # | Decision | Choice |
|---|---|---|
| 1 | Store & isolation | **Per-namespace DB file + committed manifest**; federation via SQLite `ATTACH`; a shared **`global` overlay** DB for cross-namespace edges. |
| 2 | Code ingestion | **stdlib-first**: Python `ast` for `.py`, light regex for other languages. tree-sitter is a documented upgrade path, not built. |
| 3 | MCP exposure | **Thin stdlib stdio JSON-RPC server** (no SDK) wired to the `knowledge` slot, exposing scoped/federated query + trace. |
| 4 | Traceability source | **Explicit links + conventions**: frontmatter link fields + `ADR-NNNN` code markers + `test_x ↔ x` naming. Every edge cites its source line. |
| 5 | Commit linkage | **Included as an optional layer** that activates only if `dashboard/utilization.db` (Phase 3) with a `commits` table is present; otherwise silently skipped. No hard dependency on Phase 3. |

---

## 2. Architecture

### 2.1 Store — per-namespace SQLite, shared overlay

One SQLite DB **per namespace** (a repo or a docs-tree), each a **derived, git-ignored** artefact (default `<root>/.knowledge/graph.db`, path declared explicitly in the manifest). A committed **manifest** at `docs/knowledge/graph-manifest.json` registers them — reusing the knowledge layer's existing home, so Phase 4 adds **no new top-level folder**. A single **`global` overlay** DB (`docs/knowledge/.knowledge/global.db`) holds edges whose endpoints live in *different* namespaces (e.g. kit-code that `implements` a docs-tree ADR) plus dangling edges. This is the roadmap's "shared global overlay."

The manifest for the kit itself:

```json
{
  "namespaces": {
    "docs":     { "kind": "docs", "db": "docs/.knowledge/graph.db", "roots": ["docs/"] },
    "kit-code": { "kind": "code", "db": ".knowledge/graph.db",       "roots": ["scripts/", "dashboard/"] }
  },
  "overlay": "docs/knowledge/.knowledge/global.db"
}
```

- **Scoped query** — open one namespace DB read-only, plus the overlay for edges touching that namespace.
- **Federated query** — `ATTACH` every manifest DB + the overlay read-only; `UNION ALL` across them.
- **Isolation** — each namespace DB is self-contained; a repo's subgraph never carries another repo's internal nodes. The overlay is the only connective tissue.

For the kit itself we register **two real namespaces** — `docs` (the `docs/` tree) and `kit-code` (`scripts/`, `dashboard/`) — so scoped-vs-federated and the overlay are exercised for real.

### 2.2 Schema (identical DDL in every namespace DB and the overlay)

```sql
CREATE TABLE IF NOT EXISTS nodes (
  id         TEXT PRIMARY KEY,   -- see id scheme (§2.3)
  kind       TEXT NOT NULL,      -- adr|story|doc|source|code-file|symbol|test|commit
  subtype    TEXT,               -- e.g. function|class for symbol
  name       TEXT,               -- title / label
  path       TEXT,               -- repo-relative source path (nullable)
  tier       TEXT,               -- ai-trust tier for docs (nullable)
  text       TEXT,               -- short content snippet for grounding search (nullable)
  meta       TEXT,               -- JSON: frontmatter + extras
  namespace  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edges (
  src         TEXT NOT NULL,     -- node id
  dst         TEXT NOT NULL,     -- node id
  kind        TEXT NOT NULL,     -- implements|covers|traces|cites|supersedes|imports|contains|touches
  source_file TEXT,              -- citation: file the edge was derived from
  line        INTEGER,           -- citation: line (nullable)
  resolved    INTEGER NOT NULL DEFAULT 1,  -- 0 = target node not found at build/resolve time
  namespace   TEXT NOT NULL,     -- owning namespace ('global' in the overlay)
  PRIMARY KEY (src, dst, kind)
);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_edges_src  ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst  ON edges(dst);
```

Schema creation is idempotent (`IF NOT EXISTS`); writes are `INSERT OR REPLACE`, so re-running `--build` reproduces the same graph.

### 2.3 Node id scheme (makes federation resolvable)

Shared, canonical entities use **bare ids** so any repo can reference them and federation resolves; repo-local entities are **namespace-prefixed** for global uniqueness.

| Kind | Id form | Example |
|---|---|---|
| adr | `adr:ADR-NNNN` | `adr:ADR-0001` |
| story | `story:AS-N` | `story:AS-0001` |
| doc | `doc:<ns>:<path>` | `doc:docs:docs/methodology/framework.md` |
| source | `source:<ns>:<path>` | `source:docs:docs/knowledge/sources/example-coding-standards.md` |
| code-file | `code:<ns>:<path>` | `code:kit-code:scripts/knowledge/query.py` |
| symbol | `sym:<ns>:<path>:<name>` | `sym:kit-code:scripts/knowledge/query.py:trace` |
| test | `test:<ns>:<path>` | `test:kit-code:scripts/knowledge/tests/test_query.py` |
| commit | `commit:<ns>:<sha>` | `commit:kit-code:fae44c5…` |

`adr:` and `story:` ids are the shared vocabulary that links a code repo's subgraph to the docs-tree subgraph through the overlay.

### 2.4 Ontology — node & edge kinds

**Nodes:** `adr`, `story`, `doc`, `source`, `code-file`, `symbol`, `test`, `commit`.

**Edges** (directed; `trace` walks both directions):

| kind | from → to | Derived from |
|---|---|---|
| `implements` | code-file/symbol → adr | `# ADR-NNNN` code marker; frontmatter `implements:` |
| `covers` | test → code-file | `test_x ↔ x` naming; test importing a module; frontmatter `covers:` |
| `traces` | story → adr | frontmatter `traces:` |
| `cites` | doc → source | frontmatter `cites:` |
| `supersedes` | adr → adr | frontmatter `supersedes:` |
| `imports` | code-file → code-file | `ast` / regex import extraction |
| `contains` | code-file → symbol | `ast` / regex definition extraction |
| `touches` | commit → code-file | git numstat (optional commit layer) |

### 2.5 Link convention (the one new authoring convention)

Documented in `docs/knowledge/schema.md` and enforced-by-habit via the `knowledge-sources` rule.

- **Doc frontmatter** (all optional; lists of ids): `implements:`, `covers:`, `traces:`, `cites:`, `supersedes:`. Values are node ids in short form (`ADR-0001`, `AS-0001`) or repo-relative paths. The ingester normalizes them to full node ids (§2.3).
- **Code marker:** a comment containing `ADR-NNNN` (regex `ADR-\d{3,4}`) anywhere in a file → a file-level `implements` edge to `adr:ADR-NNNN`; if the marker's line falls inside a def/class the `ast` pass also emits a symbol-level `implements`. The edge stores the marker's `source_file` + `line`.
- **Naming:** `tests/test_<x>.py` / `<x>_test.py` → `covers` the same-namespace `code:<ns>:…/<x>.py` node when it exists.
- **Honesty:** a link whose target node is not found anywhere (after the resolve pass, §3.1) is kept as a **dangling edge** (`resolved=0`) in the overlay, so `trace` reports "ADR-0003 referenced but not found" instead of inventing — matching `AGENTS.md §4.4` ("say so rather than inventing").

---

## 3. Components (all under `scripts/knowledge/`, stdlib only)

| File | Responsibility |
|---|---|
| `graph_store.py` | SQLite connection + idempotent schema; typed `add_node`/`add_edge` helpers; read helpers. Namespace-agnostic (the caller passes the DB path). |
| `manifest.py` | Read/write `docs/knowledge/graph-manifest.json` (`namespace → {db, roots, kind}` + `overlay`); resolve a root to its namespace DB path; iterate registered namespaces. |
| `ingest_docs.py` | Walk a docs root (skipping dot-directories), parse frontmatter (reusing the stub's lightweight parser), emit `adr`/`story`/`doc`/`source` nodes + link-convention edges + `ADR-NNNN` mentions. Stamps `tier` from `ai-trust`. |
| `ingest_code.py` | Python `ast` for `.py` (module/`code-file`, `symbol` with subtype, `imports`, `contains`); light regex for other languages (shallow def-like + import-like lines); `# ADR-NNNN` markers → `implements`; `test_x ↔ x` naming → `covers`. Files matching the test pattern (`test_*.py` / `*_test.py`) become `test` nodes; other code files become `code-file` nodes (both still get `contains`/`imports`). |
| `link_commits.py` | **Optional.** If `dashboard/utilization.db` with a `commits` table exists, add `commit` nodes + `touches` edges (from `git show --numstat`) and stamp each `code-file` node's `meta` with `{ai_commits, human_commits, mixed_commits}` counts. Skipped silently otherwise. |
| `query.py` | The engine: `open_scoped(ns)`, `open_federated()`, `search(conn,q,k)`, `get_node`, `neighbors`, `trace(id,max_depth)`. Every result carries `namespace, path, source_file, line, tier`. |
| `ingest.py` | **Rewritten** orchestrator/CLI: `--build`, `--query`, `--stats`, `--scope <ns>`, `--federated`, `--trace <id>`. Muscle-memory (`ingest.py --build`) preserved. |
| `mcp_server.py` | Thin stdlib stdio JSON-RPC 2.0 server: `initialize`, `tools/list`, `tools/call` for `kg_query`, `kg_federated_query`, `kg_trace`. Reads via `query.py`. |

### 3.1 Data flow — `ingest.py --build`

1. Read manifest.
2. **Per namespace:** run docs and/or code ingesters over its roots (skipping dot-directories, so derived `.knowledge/` DBs are never re-ingested) → write nodes + **intra-namespace** edges to the namespace's DB; collect edges whose other endpoint is a foreign/unknown id → hold for the overlay.
3. **Optional commit layer** per code namespace (§3, `link_commits.py`) if the dashboard DB is present.
4. **Resolve pass:** open every namespace DB read-only; write the held cross-namespace edges to the overlay, setting `resolved=1` when both endpoints exist somewhere, else `resolved=0`.
5. Print stats (nodes/edges per namespace + overlay).

### 3.2 Query & trace

- **Scoped** (`--scope kit-code`): open that DB + overlay (ro); search/trace within.
- **Federated** (`--federated`): `ATTACH` all namespace DBs + overlay (ro, `PRAGMA query_only`); `UNION ALL` node/edge views; search/trace across the whole project.
- **`trace(id)`**: bounded BFS over edges in both directions (default depth 4) assembling the ADR↔code↔test↔story chain; each hop annotated with its citation.
- **`search(q)`**: term-scored match over node `name` + `text` (the first ~800 chars of a doc/source body, or a symbol's signature line, stored on the node). Preserves the stub's grounding-by-content — the agent finds the cited file, then reads it. No re-chunking, no vector store.

### 3.3 MCP server

stdlib stdio, **newline-delimited JSON-RPC 2.0** (the MCP stdio framing). Handles `initialize` (returns protocol version + `serverInfo` + `capabilities.tools`), `notifications/initialized` (no-op), `tools/list` (three tools with JSON schemas), `tools/call` (dispatch to `query.py`, return JSON-encoded results-with-citations as text content). Unknown method → JSON-RPC error `-32601`; the read loop never crashes on a bad message (logs to stderr, continues). Degrades gracefully when the graph is unbuilt: returns an empty result plus a hint to run `ingest.py --build`.

`.mcp.json` `knowledge` slot is wired to `python3 scripts/knowledge/mcp_server.py` and **enabled** (it is the only fully-local, no-URL/no-secret server; can be disabled like any other).

---

## 4. Dogfood chain + acceptance

Phase 4 seeds a **complete, real traceability chain in the kit itself**, so the acceptance query is not hypothetical:

- **`ADR-0001`** — a new ADR "Adopt a local docs+code knowledge graph" (`docs/architecture/decisions/`). Node `adr:ADR-0001`.
- **Phase 4 code** carries `# ADR-0001` markers → `implements` edges (`code:kit-code:scripts/knowledge/*.py → adr:ADR-0001`).
- **Phase 4 tests** cover that code by naming → `covers` edges.
- **`AS-0001`** — a seed example story (`docs/product/stories/AS-0001-adopt-knowledge-graph.md`, frontmatter `traces: [ADR-0001]`) → `traces` edge (`story:AS-0001 → adr:ADR-0001`). (`docs/product/` is a demand-driven subfolder, like the other role homes — not a new top-level folder.)

**Acceptance signals** (mirroring the roadmap):

1. **Scoped:** `ingest.py --scope kit-code --trace ADR-0001` returns the implementing modules and their covering tests, each with a source citation.
2. **Federated:** `ingest.py --federated --trace ADR-0001` resolves across `docs` + `kit-code` + overlay → the full **ADR → code → test → story** chain, every hop grounded on a source line.
3. **MCP:** the `knowledge` server answers `kg_trace(ADR-0001)` and `kg_federated_query("knowledge graph")` over stdio.

---

## 5. Error handling

- **No manifest / empty roots** → helpful "nothing to ingest" (mirrors the stub).
- **Malformed frontmatter** → skip that node's frontmatter, warn to stderr, never crash.
- **Unbuilt / empty DB** on query → "Graph is empty. Run: ingest.py --build" (mirrors the stub).
- **Dangling links** → kept as `resolved=0` edges; surfaced honestly by `trace`.
- **MCP bad message / unknown method** → JSON-RPC error, loop continues.
- **Missing dashboard DB** (commit layer) → skipped silently, `--build` still succeeds.

---

## 6. Testing

Per-module `unittest`, mirroring `dashboard/tests/`:

- `test_graph_store.py` — schema idempotency, add/replace node & edge, indexes.
- `test_manifest.py` — read/write/round-trip, root→namespace resolution.
- `test_ingest_docs.py` — frontmatter link fields → correct edges; `ADR-NNNN` mention; tier stamping; malformed frontmatter tolerated.
- `test_ingest_code.py` — `ast` module/class/function nodes + imports/contains; `# ADR` marker → implements (file + symbol); `test_x ↔ x` covers; non-`.py` regex path.
- `test_link_commits.py` — with a **fixture** dashboard DB (temp): `touches` edges + attribution counts; absent DB → no-op.
- `test_query.py` — scoped vs federated node/edge visibility; `trace` assembles the chain both directions; dangling edge surfaced; citations present.
- `test_mcp_server.py` — protocol smoke over an in-process pipe: `initialize` → `tools/list` → `tools/call(kg_trace)`; unknown method → error, loop survives.
- `test_end_to_end.py` — build a temp fixture repo (ADR + code-with-marker + test + story), run `--build`, assert scoped + federated `trace` return the full chain with citations.

**CI:** wire into the governance gate (`.gitlab-ci.yml`, mirrored in `.github/workflows/` if present) — the knowledge test suite + an `ingest.py --build` smoke on the kit + `py_compile`.

---

## 7. Files created / modified

**New (code):** `scripts/knowledge/{graph_store,manifest,ingest_docs,ingest_code,link_commits,query,mcp_server}.py` + `scripts/knowledge/tests/{test_graph_store,test_manifest,test_ingest_docs,test_ingest_code,test_link_commits,test_query,test_mcp_server,test_end_to_end}.py`.
**New (data/docs):** `docs/knowledge/graph-manifest.json`; `docs/architecture/decisions/ADR-0001-adopt-knowledge-graph.md`; `docs/product/stories/AS-0001-adopt-knowledge-graph.md`.
**Rewritten:** `scripts/knowledge/ingest.py`.
**Updated:** `docs/knowledge/schema.md` (graph schema + convention + manifest + isolation), `docs/knowledge/README.md` (graph quick-start), `.claude/rules/knowledge-sources.md` (rebuild + convention), `.mcp.json` (knowledge slot → local server, enabled), `AGENTS.md §4.4` (grounding → scoped/federated/trace), template `.gitignore` (ignore `**/.knowledge/`).
**Untouched:** `CLAUDE.md` stays a pure pointer.

---

## 8. Global constraints (bind every task)

- **Python stdlib only** — no new pip dependencies. **Python 3.9+** (as the existing scripts assume), `from __future__ import annotations` style.
- **Derived DBs are git-ignored** (`**/.knowledge/` covers every namespace DB and the overlay at `docs/knowledge/.knowledge/global.db`); the **manifest `docs/knowledge/graph-manifest.json` is committed**.
- **Idempotent** ingest — `--build` is repeatable; `INSERT OR REPLACE`; schema `IF NOT EXISTS`.
- **Every query result is citable** — `namespace`, `path`/`source_file`, `line`, `tier`. **No fabricated edges**: unresolved links are `resolved=0`, never dropped or invented.
- **No hard dependency on Phase 3** — the commit layer activates only when `dashboard/utilization.db` with a `commits` table exists.
- **MCP server degrades gracefully** when the graph is unbuilt.
- **Docs invariants:** `AGENTS.md` is canonical; `CLAUDE.md` stays a pure pointer; no secrets; sources/nodes carry no real personal data.
- **Commit trailer** on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## 9. Out of scope (documented upgrade paths, not built)

- **Embeddings / vector search** — content search stays term-scored over node text; documented as the upgrade (local model or provider via the AI Gateway + `sqlite-vec`/DuckDB-VSS/LanceDB/pgvector).
- **tree-sitter multi-language AST** — the code ingester is `ast` + shallow regex; tree-sitter is the documented depth upgrade.
- **Defect-tracker linkage** — `touches` gives commit→code; wiring *which defect* fixed which code (issue-tracker MCP → commit) is a later increment.
- **Hosted knowledge MCP** — the slot can instead point at a managed KG/vector DB; the local server is the reference.
