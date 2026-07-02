---
paths:
  - "docs/knowledge/**"
  - "docs/architecture/decisions/**"
  - "docs/product/stories/**"
---
# Knowledge graph & sources

The knowledge layer is a local **docs+code graph** (pillar 5) — see
`docs/knowledge/schema.md` and `README.md`.

- After adding/changing docs, code, or sources, rebuild: `python3 scripts/knowledge/ingest.py --build`.
- **Link convention** (how edges are drawn): frontmatter `implements:`/`covers:`/`traces:`/`cites:`/`supersedes:` (lists of ids/paths); a `# ADR-NNNN` comment in code; `test_x ↔ x` naming. Each edge cites its source line.
- Ground answers on the graph and **cite the source file + trust tier** (`AGENTS.md §4.2`); do not paraphrase Authoritative sources from memory — quote and cite.
- Unresolved links are reported honestly (`resolved=0`); fix the reference or add the missing node rather than inventing one.
- `docs/knowledge/schema.md` is exempt from the frontmatter contract; source docs still carry it.
