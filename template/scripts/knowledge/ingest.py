#!/usr/bin/env python3
"""Knowledge-layer ingestion — STUB (board pillar 5: Sources -> KG / RAG / VectorDB).

This is a deliberately minimal, dependency-light reference implementation. It walks
the tracked source documents under docs/knowledge/sources/, chunks them, and writes a
local index that an agent (or an MCP knowledge server) can query to *ground* answers
instead of guessing (AGENTS.md §4.4).

What it does today (no external services, no embeddings):
  - discover sources (.md / .txt) under docs/knowledge/sources/
  - read each source's trust tier from its frontmatter (defaults to 'working')
  - split into overlapping character chunks
  - write a JSONL index to docs/knowledge/.index/chunks.jsonl  (git-ignored)
  - keyword search over that index (a placeholder for vector search)

How to grow it into production (documented, not built here — see docs/knowledge/README.md):
  - swap the keyword search for embeddings (e.g. a local model or a provider via the
    Vercel AI Gateway) + a vector store (DuckDB-VSS, sqlite-vec, LanceDB, pgvector, …)
  - or point .mcp.json's `knowledge` server at a hosted vector DB / knowledge graph and
    let the agent ingest/query over MCP instead of this script.

Usage:
  ingest.py --build                 # (re)build the index from sources
  ingest.py --query "some text"     # keyword search the index (top 5)
  ingest.py --stats                 # show what's indexed
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCES = REPO_ROOT / "docs" / "knowledge" / "sources"
INDEX_DIR = REPO_ROOT / "docs" / "knowledge" / ".index"
INDEX_FILE = INDEX_DIR / "chunks.jsonl"
CHUNK_CHARS = 1200
OVERLAP = 200
SUFFIXES = {".md", ".txt"}


def read_trust_tier(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            m = re.search(r"^ai-trust:\s*(\S+)", fm, re.MULTILINE)
            if m:
                return m.group(1)
    return "working"


def chunk(text: str) -> list[str]:
    text = text.strip()
    if len(text) <= CHUNK_CHARS:
        return [text] if text else []
    out, start = [], 0
    while start < len(text):
        out.append(text[start : start + CHUNK_CHARS])
        start += CHUNK_CHARS - OVERLAP
    return out


def build() -> int:
    if not SOURCES.exists():
        print(f"No sources directory at {SOURCES.relative_to(REPO_ROOT)} — nothing to ingest.")
        return 0
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    n_src = n_chunk = 0
    with INDEX_FILE.open("w", encoding="utf-8") as out:
        for src in sorted(SOURCES.rglob("*")):
            if src.suffix.lower() not in SUFFIXES or not src.is_file():
                continue
            text = src.read_text(encoding="utf-8", errors="replace")
            tier = read_trust_tier(text)
            rel = str(src.relative_to(REPO_ROOT))
            n_src += 1
            for i, ch in enumerate(chunk(text)):
                out.write(json.dumps({"source": rel, "tier": tier, "chunk": i, "text": ch}) + "\n")
                n_chunk += 1
    print(f"Indexed {n_chunk} chunks from {n_src} source(s) -> {INDEX_FILE.relative_to(REPO_ROOT)}")
    print("Note: keyword index only. See docs/knowledge/README.md to add embeddings + a vector store.")
    return 0


def load_index() -> list[dict]:
    if not INDEX_FILE.exists():
        return []
    return [json.loads(line) for line in INDEX_FILE.read_text(encoding="utf-8").splitlines() if line]


def query(q: str, k: int = 5) -> int:
    rows = load_index()
    if not rows:
        print("Index is empty. Run: ingest.py --build")
        return 1
    terms = [t for t in re.findall(r"\w+", q.lower()) if len(t) > 2]
    scored = []
    for r in rows:
        low = r["text"].lower()
        score = sum(low.count(t) for t in terms)
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        print("No matches.")
        return 0
    for score, r in scored[:k]:
        snippet = " ".join(r["text"].split())[:200]
        print(f"[{score:>3}] {r['source']} (tier={r['tier']}, chunk={r['chunk']})\n      {snippet}…\n")
    return 0


def stats() -> int:
    rows = load_index()
    if not rows:
        print("Index is empty. Run: ingest.py --build")
        return 0
    by_src: dict[str, int] = {}
    for r in rows:
        by_src[r["source"]] = by_src.get(r["source"], 0) + 1
    print(f"{len(rows)} chunks across {len(by_src)} source(s):")
    for src, n in sorted(by_src.items()):
        print(f"  {n:>4}  {src}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Knowledge-layer ingestion stub.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--build", action="store_true", help="(re)build the index from sources")
    g.add_argument("--query", metavar="TEXT", help="keyword search the index")
    g.add_argument("--stats", action="store_true", help="show what's indexed")
    args = ap.parse_args()
    if args.build:
        return build()
    if args.query:
        return query(args.query)
    return stats()


if __name__ == "__main__":
    raise SystemExit(main())
