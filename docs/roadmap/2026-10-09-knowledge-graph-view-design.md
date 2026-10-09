---
title: "Knowledge graph view — HTML export, markdown-link edges, file roots (design)"
status: implemented
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-10-09
classification: internal
ai-trust: working
---

# Knowledge graph view

**Goal.** Make the Phase-4 knowledge graph something a person can look at. Until
now the graph was reachable only through the CLI and the `knowledge` MCP server,
so nobody could see its shape, its gaps, or its dangling links. This feature
adds a one-command export to a single HTML page, and the two ingest changes
without which that page shows mostly unconnected dots. Dependency-light, like
the rest of the knowledge layer: Python **stdlib only**, no JavaScript library,
no network.

**Origin.** Built and used on a client engagement repo that carries the kit,
then ported here unchanged in substance. Nothing project-specific ships.

## 1. Decisions

| # | Decision | Why |
|---|---|---|
| 1 | A generated HTML page, not an Obsidian vault | Obsidian draws only untyped links between `.md` files. An export to a vault would lose the edge kind, the citation (file + line), the trust tier and the `resolved=0` flag, which are the point of this graph. |
| 2 | One self-contained file, no CDN | Opens offline and can be handed to a colleague. The layout is a small force simulation on a canvas, written inline. |
| 3 | The page is derived output under `docs/knowledge/.knowledge/` | Already git-ignored; it embeds doc titles, paths and short text snippets, so it should not be tracked. |
| 4 | Unresolved edges are drawn, against a `missing` placeholder node | Keeps the kit's rule that dangling links are surfaced honestly, never dropped or invented. |
| 5 | Symbols are hidden by default | They are most of the nodes and turn the picture into a hairball; one checkbox turns them on. |
| 6 | Markdown links become a new `links` edge kind | Frontmatter links (`traces:`, `cites:`) are rare in real docs; relative `[text](path)` links are how authors already connect documents. |
| 7 | Git-ignored files are not ingested | The ingesters walk roots with `rglob`, so `node_modules/` and generated `out/` trees were entering the graph as project knowledge. |
| 8 | A manifest root may be a single file; a named hidden root is honoured | Docs link to `AGENTS.md`, `README.md` and `.claude/skills/`, which sit outside every folder root. Without this, valid links showed as unresolved. |

## 2. What ships

- **`scripts/knowledge/export_html.py`** + **`graph_view.html`** (the template).
  `export_html.py [--out PATH] [--open]` reads every namespace DB and the
  overlay read-only and writes `docs/knowledge/.knowledge/graph.html`.
  The page offers filters by namespace, node kind and edge kind, a search box,
  an "only unresolved links" view, and a detail panel listing each link of the
  selected node with the file and line it was drawn from. Graph content is
  embedded as JSON and rendered with `textContent` only.
- **`links` edges** (`ingest_docs.py`, `schema.md`). A relative markdown link in
  a doc body to a `.md` or code file. External URLs, `#anchors`, images and
  fenced code are ignored; a folder link resolves to its `README.md` when it
  has one.
- **Git-ignore filter** (`ingest.py`). Nodes whose file is git-ignored are
  dropped with their edges. Outside a git work tree nothing is dropped.
- **File roots and the `briefs` namespace** (`ingest_docs.py`, `ingest_code.py`,
  `graph-manifest.json`). The template manifest gains a `briefs` namespace for
  the top-level briefs, the skills and the READMEs that live outside `docs/`.
  Path references between two roots of one namespace resolve in that
  namespace's DB instead of the overlay.
- **CI.** The new test file and an export smoke step run in `ci.yml`,
  `.gitlab-ci.yml` and the template's `ai-governance.yml`.

## 3. Acceptance signal

After `ingest.py --build`, `export_html.py` writes a page that loads with no
console errors, and the template's own graph has **no unresolved `links`
edge**. The remaining unresolved edges predate this feature: `implements`
markers in the knowledge tests' own fixtures, which name ADRs the template does
not contain, and one commit `Refs:` trailer that names an ADR and is read as an
issue key.

## 4. Known limits

- Only inline links are read; reference-style links (`[id]: path`) are not.
- The layout is O(n²) per tick. It is comfortable to a few thousand nodes; a
  larger graph needs a spatial index or a pre-computed layout.
- A project that adds its own top-level documents must list them in the
  `briefs` roots, or links to them will show as unresolved.
- No automated browser test ships. The Python side is unit-tested; the page was
  checked in headless Chrome during development.
