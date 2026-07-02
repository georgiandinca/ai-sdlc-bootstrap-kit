---
paths:
  - "docs/knowledge/**"
---
# Knowledge sources

Files under `docs/knowledge/sources/` are ingestable inputs for the knowledge layer (pillar 5).
- Treat them per their trust tier (`AGENTS.md` §4.2); cite the source file when grounding an answer.
- After adding or changing sources, rebuild the index: `python3 scripts/knowledge/ingest.py --build`.
- `docs/knowledge/schema.md` is exempt from the frontmatter contract; source docs still carry it.
- Do not paraphrase Authoritative sources from memory — quote and cite.
