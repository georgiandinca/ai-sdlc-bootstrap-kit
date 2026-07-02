#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Docs ingester: frontmatter + link convention -> nodes/edges. Stdlib only
(no pyyaml): a small frontmatter parser handles scalars, inline [a, b] lists,
and block '- item' lists."""
from __future__ import annotations

import re
from pathlib import Path

from graph_store import adr_id, story_id, doc_id, source_id, normalize_ref

LINK_FIELDS = ("implements", "traces", "cites", "supersedes", "covers")
_ADR_FILE_RE = re.compile(r"(ADR-\d{3,4})")
_STORY_FILE_RE = re.compile(r"(AS-\d+)", re.I)


def parse_frontmatter(text: str):
    """Return (meta, body). Tolerant: no/again-unterminated frontmatter -> ({}, text)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = text[3:end].strip("\n")
    body = text[end + 4:]
    meta: dict = {}
    key = None
    for raw in fm.splitlines():
        if not raw.strip():
            continue
        if raw.lstrip().startswith("- ") and key is not None:
            meta.setdefault(key, [])
            if isinstance(meta[key], list):
                meta[key].append(raw.lstrip()[2:].strip().strip('"\''))
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", raw)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val == "":
            meta[key] = []  # a block list may follow
        elif val.startswith("[") and val.endswith("]"):
            meta[key] = [x.strip().strip('"\'') for x in val[1:-1].split(",") if x.strip()]
        else:
            meta[key] = val.strip('"\'')
    return meta, body


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def classify(rel_path: str, meta: dict):
    """Return (kind, ident). ident is the ADR/story id string, else None."""
    name = Path(rel_path).name
    rp = rel_path.replace("\\", "/")
    if "architecture/decisions/" in rp:
        m = _ADR_FILE_RE.search(name)
        if m:
            return "adr", m.group(1)
    if "product/stories/" in rp or _STORY_FILE_RE.match(name):
        m = _STORY_FILE_RE.search(name)
        if m:
            return "story", m.group(1).upper()
    if "knowledge/sources/" in rp:
        return "source", None
    return "doc", None


def ingest_root(root: Path, namespace: str, base: Path):
    nodes, edges = [], []
    root = Path(root)
    base = Path(base)
    for f in sorted(root.rglob("*.md")):
        rel = f.relative_to(base)
        if any(part.startswith(".") for part in rel.parts):
            continue  # skip dot-directories (derived .knowledge/, etc.)
        rels = str(rel).replace("\\", "/")
        text = f.read_text(encoding="utf-8", errors="replace")
        try:
            meta, body = parse_frontmatter(text)
        except Exception:
            meta, body = {}, text
        kind, ident = classify(rels, meta)
        if kind == "adr":
            nid = adr_id(ident)
        elif kind == "story":
            nid = story_id(ident)
        elif kind == "source":
            nid = source_id(namespace, rels)
        else:
            nid = doc_id(namespace, rels)
        nodes.append({"id": nid, "kind": kind, "subtype": None,
                      "name": meta.get("title") or f.name, "path": rels,
                      "tier": meta.get("ai-trust"),
                      "text": " ".join(body.split())[:800],
                      "meta": meta, "namespace": namespace})
        for field in LINK_FIELDS:
            for ref in _as_list(meta.get(field)):
                edges.append({"src": nid, "dst": normalize_ref(str(ref)),
                              "kind": field, "source_file": rels, "line": None,
                              "resolved": None, "namespace": namespace})
    return nodes, edges
