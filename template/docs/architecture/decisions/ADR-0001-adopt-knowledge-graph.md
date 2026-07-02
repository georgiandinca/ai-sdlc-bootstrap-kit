---
title: "ADR-0001 — Adopt a local docs+code knowledge graph"
status: approved
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-07-02
classification: internal
last-reviewed: 2026-07-02
ai-trust: working
---

# ADR-0001 — Adopt a local docs+code knowledge graph

## Status

Accepted — 2026-07-02.

## Context

The kit shipped a keyword stub (`scripts/knowledge/ingest.py`) that chunked
`docs/knowledge/sources/` and did keyword search — docs-only, no structure, no
traceability. Grounding (`AGENTS.md §4.4`) and the QA/Architect traceability
duty need more: a graph over **docs and code**, isolated per repo, queryable
across the whole project, that answers "what implements this ADR, and what
tests cover it?".

## Decision

Adopt a **local, dependency-light knowledge graph**: per-namespace SQLite DBs
(`nodes` + `edges`) plus a shared `global` overlay, federated via `ATTACH`.
Stdlib ingesters read docs (frontmatter) and code (`ast`). Traceability edges
(ADR→code→test→story) come from explicit links — frontmatter fields, `# ADR-NNNN`
code markers, and `test_x ↔ x` naming — each edge citing its source line. A thin
stdlib MCP server exposes scoped/federated query + trace on the `knowledge` slot.
Embeddings, tree-sitter, and hosted stores remain documented upgrade paths.

## Consequences

- Agents ground answers on a structured, citable graph, not a flat keyword index.
- Every AI-authored knowledge module is attributable to this ADR (dogfooded via
  `# ADR-0001` markers), so `trace ADR-0001` returns its own implementation.
- The graph is derived and git-ignored; only sources + the manifest are tracked.
