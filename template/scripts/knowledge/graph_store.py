#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""SQLite graph store: nodes + edges, one DB per namespace (+ a global overlay).

Stdlib only. Idempotent schema; INSERT OR REPLACE writes. Records are plain
dicts produced by the ingesters; this module owns the DDL and the id scheme so
every producer stays consistent.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, subtype TEXT, name TEXT,
  path TEXT, tier TEXT, text TEXT, meta TEXT, namespace TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edges (
  src TEXT NOT NULL, dst TEXT NOT NULL, kind TEXT NOT NULL,
  source_file TEXT, line INTEGER, resolved INTEGER NOT NULL DEFAULT 1,
  namespace TEXT NOT NULL, PRIMARY KEY (src, dst, kind)
);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
"""

NODE_FIELDS = ("id", "kind", "subtype", "name", "path", "tier", "text", "meta", "namespace")
EDGE_FIELDS = ("src", "dst", "kind", "source_file", "line", "resolved", "namespace")


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def connect(db_path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    return conn


def connect_ro(db_path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)


def add_node(conn: sqlite3.Connection, node: dict) -> None:
    vals = []
    for k in NODE_FIELDS:
        v = node.get(k)
        if k == "meta":
            v = json.dumps(v or {}, sort_keys=True)
        vals.append(v)
    conn.execute(
        f"INSERT OR REPLACE INTO nodes ({','.join(NODE_FIELDS)}) "
        f"VALUES ({','.join('?' * len(NODE_FIELDS))})", vals)


def add_edge(conn: sqlite3.Connection, edge: dict) -> None:
    e = dict(edge)
    if e.get("resolved") is None:
        e["resolved"] = 1
    conn.execute(
        f"INSERT OR REPLACE INTO edges ({','.join(EDGE_FIELDS)}) "
        f"VALUES ({','.join('?' * len(EDGE_FIELDS))})",
        [e.get(k) for k in EDGE_FIELDS])


def adr_id(num: str) -> str: return f"adr:{num}"
def story_id(sid: str) -> str: return f"story:{sid}"
def code_id(ns: str, path: str) -> str: return f"code:{ns}:{path}"
def doc_id(ns: str, path: str) -> str: return f"doc:{ns}:{path}"
def source_id(ns: str, path: str) -> str: return f"source:{ns}:{path}"
def symbol_id(ns: str, path: str, name: str) -> str: return f"sym:{ns}:{path}:{name}"
def test_id(ns: str, path: str) -> str: return f"test:{ns}:{path}"
def commit_id(ns: str, sha: str) -> str: return f"commit:{ns}:{sha}"
def issue_id(key: str) -> str: return f"issue:{key}"

_ADR_RE = re.compile(r"^ADR-\d{3,4}$")
_STORY_RE = re.compile(r"^AS-\d+$", re.I)
_ISSUE_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


def normalize_ref(ref: str) -> str:
    """Frontmatter ref -> node id. ADR/story -> canonical id; a path -> a
    provisional 'path:<p>' id resolved later; anything else stays literal."""
    ref = ref.strip()
    if _ADR_RE.match(ref):
        return adr_id(ref)
    if _STORY_RE.match(ref):
        return story_id(ref.upper())
    if _ISSUE_RE.match(ref):
        return issue_id(ref)
    if "/" in ref or "." in ref:
        return f"path:{ref}"
    return ref
