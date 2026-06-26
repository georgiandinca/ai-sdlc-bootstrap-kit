# Knowledge source & chunk schema

The contract the ingester (`scripts/knowledge/ingest.py`) and any knowledge MCP server follow.

## Source document frontmatter

Every file under `sources/` should carry frontmatter so its provenance and trust tier travel with it into the index:

```yaml
---
title: "Human-readable title"
source: "<origin — URL, system, or 'authored'>"
ai-trust: authoritative | working | exploratory
classification: public | internal | restricted
last-reviewed: YYYY-MM-DD
---
```

`ai-trust` uses the project trust-tier vocabulary (`AGENTS.md` §4.2). The ingester reads it and stamps every chunk; the default is `working` when absent.

## Chunk record (what the index stores)

The stub writes JSONL to `.index/chunks.jsonl` (git-ignored). One object per chunk:

| Field | Type | Meaning |
|---|---|---|
| `source` | string | repo-relative path of the source file |
| `tier` | string | `ai-trust` tier inherited from the source |
| `chunk` | int | chunk ordinal within the source |
| `text` | string | the chunk text |

A production vector store adds at least an `embedding` (vector) field and an index over it; a knowledge graph adds `entities` and `relations`. Keep `source` + `tier` on every record so retrieved context can always be **cited with its trust tier**.

## Conventions

- **Markdown/text only** for the stub (`.md`, `.txt`). For PDFs/Docx, convert to Markdown first (e.g. `pandoc`) so the content diffs and stays inspectable.
- **One topic per source file** where practical — smaller sources retrieve more precisely.
- **No secrets, no real personal data.** Sources are git-tracked.
