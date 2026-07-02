---
title: "AS-0001 — Ground answers on a project knowledge graph"
status: approved
owner: Product
author: AI-SDLC Bootstrap Kit
created: 2026-07-02
classification: internal
last-reviewed: 2026-07-02
ai-trust: working
traces: [ADR-0001]
---

# AS-0001 — Ground answers on a project knowledge graph

**As a** team running the AI-SDLC kit,
**I want** agents to answer from a graph over our docs and code,
**so that** every answer is traceable (ADR→code→test→story) and cited, not guessed.

This is the **seed story** every project gets — it demonstrates the `traces:`
link convention (it traces to `ADR-0001`) and completes the reference
traceability chain. Copy its shape for real stories under `docs/product/stories/`.

## Acceptance

- `ingest.py --federated --trace ADR-0001` returns the implementing code, its
  tests, and this story, each grounded on a source citation.
