---
paths:
  - "docs/architecture/decisions/**"
---
# ADR conventions

When creating or editing an Architecture Decision Record:
- Name it `ADR-<NNNN>-<kebab-topic>.md` with a zero-padded number.
- Carry the frontmatter contract (title, status, owner, classification, ai-trust).
- Structure: **Context** → **Decision** → **Consequences**. State the decision as a completed choice ("We will …"), not a proposal.
- `status: approved` only after the accountable seat signs off; until then `draft` / `under-review`.
- Supersede rather than delete: set the old ADR `status: superseded` and link the replacement.
