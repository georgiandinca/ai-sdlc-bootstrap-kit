#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Docs ingester: frontmatter + link convention -> nodes/edges, plus a `links`
edge per relative markdown link in the body. Stdlib only (no pyyaml): a small
frontmatter parser handles scalars, inline [a, b] lists, and block '- item'
lists."""
from __future__ import annotations

import posixpath
import re
from pathlib import Path
from urllib.parse import unquote

from graph_store import ISSUE_KEY, adr_id, story_id, doc_id, source_id, normalize_ref

LINK_FIELDS = ("implements", "traces", "cites", "supersedes", "covers")
_ADR_FILE_RE = re.compile(r"(ADR-\d{3,4})")
_STORY_FILE_RE = re.compile(r"(AS-\d+)", re.I)
# inline [text](target "title") / [text](<target>); images (![..]) are skipped
_MD_LINK_RE = re.compile(r"(?<!!)\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^)\s]+)(?:\s+[\"'][^\"'\n]*[\"'])?\s*\)")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
# link targets that can be graph nodes (docs + ingest_code.CODE_SUFFIXES)
LINKABLE_SUFFIXES = {".md", ".py", ".js", ".ts", ".sh", ".go", ".rb", ".java", ".rs"}


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


def body_links(body: str, rel_path: str, base: Path, line_offset: int = 0):
    """Yield (repo-relative target path, line) for each relative markdown link
    in `body` that points at a doc or code file. External URLs, bare #anchors,
    images, fenced code and targets outside the repo are skipped; a link to a
    directory resolves to its README.md when it has one. First occurrence per target wins."""
    here = posixpath.dirname(rel_path)
    seen = set()
    fenced = False
    for i, raw in enumerate(body.splitlines(), 1):
        if _FENCE_RE.match(raw):
            fenced = not fenced
            continue
        if fenced:
            continue
        for m in _MD_LINK_RE.finditer(raw):
            target = unquote(m.group(1).strip("<>").split("#", 1)[0].split("?", 1)[0])
            if not target or _SCHEME_RE.match(target) or target.startswith("//"):
                continue
            joined = target.lstrip("/") if target.startswith("/") else posixpath.join(here, target)
            path = posixpath.normpath(joined)
            if path.startswith("..") or path == ".":
                continue
            if (Path(base) / path).is_dir():
                path = posixpath.join(path, "README.md")
                if not (Path(base) / path).is_file():
                    continue  # a folder link with no README is not a broken link
            if posixpath.splitext(path)[1].lower() not in LINKABLE_SUFFIXES:
                continue
            if path == rel_path or path in seen:
                continue
            seen.add(path)
            yield path, line_offset + i


def ingest_root(root: Path, namespace: str, base: Path, issue_key: str = ISSUE_KEY):
    nodes, edges = [], []
    link_edges = []
    path_index = {}  # rels -> node id, to resolve in-root links in-pass
    root = Path(root)
    base = Path(base)
    # a root is a folder (walked) or a single file; a root named in the manifest
    # is honoured even when hidden, dot-directories below it are skipped
    files = [root] if root.is_file() else sorted(root.rglob("*.md"))
    for f in files:
        if f.suffix.lower() != ".md":
            continue
        rel = f.relative_to(base)
        if f != root and any(part.startswith(".") for part in f.relative_to(root).parts):
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
                edges.append({"src": nid, "dst": normalize_ref(str(ref), issue_key),
                              "kind": field, "source_file": rels, "line": None,
                              "resolved": None, "namespace": namespace})
        path_index[rels] = nid
        offset = text.count("\n", 0, len(text) - len(body))
        for target, line in body_links(body, rels, base, offset):
            link_edges.append({"src": nid, "dst": f"path:{target}", "kind": "links",
                               "source_file": rels, "line": line,
                               "resolved": None, "namespace": namespace})
    # in-root targets resolve here; the rest stay 'path:' for the orchestrator's overlay pass
    for e in link_edges:
        target = path_index.get(e["dst"][len("path:"):])
        edges.append({**e, "dst": target, "resolved": 1} if target else e)
    return nodes, edges
