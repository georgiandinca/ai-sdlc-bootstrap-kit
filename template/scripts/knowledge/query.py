#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Read-only query engine: scoped (one namespace) or federated (ATTACH all),
content search, and trace() to assemble the ADR<->code<->test<->story chain."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import manifest as manifest_mod
from graph_store import normalize_ref

_NODE_COLS = "id,kind,subtype,name,path,tier,text,meta,namespace"
_EDGE_COLS = "src,dst,kind,source_file,line,resolved,namespace"

EMPTY_HINT = "Graph is empty. Run: ingest.py --build"


class KG:
    def __init__(self, conn, aliases, scope_alias=None):
        self.conn = conn
        self.aliases = aliases
        self.scope_alias = scope_alias

    def nodes_sql(self):
        return " UNION ALL ".join(f"SELECT {_NODE_COLS} FROM {a}.nodes" for a in self.aliases)

    def edges_sql(self):
        parts = []
        for a in self.aliases:
            if a == "overlay" and self.scope_alias:
                # Spec §2.1: scoped view includes only overlay edges touching this namespace.
                parts.append(
                    f"SELECT {_EDGE_COLS} FROM overlay.edges "
                    f"WHERE src IN (SELECT id FROM {self.scope_alias}.nodes) "
                    f"OR dst IN (SELECT id FROM {self.scope_alias}.nodes)"
                )
            else:
                parts.append(f"SELECT {_EDGE_COLS} FROM {a}.edges")
        return " UNION ALL ".join(parts)


def _alias(name):
    return "ns_" + re.sub(r"\W", "_", name)


def _open(pairs, scope_alias=None):
    """pairs: list of (alias, db_path). Returns a KG over attached DBs (ro)."""
    conn = sqlite3.connect(":memory:")
    aliases = []
    for alias, db in pairs:
        if Path(db).exists():
            conn.execute(f"ATTACH DATABASE ? AS {alias}", (str(db),))
            aliases.append(alias)
    conn.execute("PRAGMA query_only=ON")
    # Only honour scope_alias if the namespace DB was actually attached.
    effective_scope = scope_alias if (scope_alias and scope_alias in aliases) else None
    return KG(conn, aliases, scope_alias=effective_scope)


def open_scoped(namespace, data=None, base=None):
    data = data or manifest_mod.load()
    base = base or manifest_mod.REPO_ROOT
    pairs = []
    ns_alias = None
    for name, kind, db, roots in manifest_mod.namespaces(data, base=base):
        if name == namespace:
            ns_alias = _alias(name)
            pairs.append((ns_alias, db))
    pairs.append(("overlay", manifest_mod.overlay_db(data, base=base)))
    return _open(pairs, scope_alias=ns_alias)


def open_federated(data=None, base=None):
    data = data or manifest_mod.load()
    base = base or manifest_mod.REPO_ROOT
    pairs = [(_alias(name), db)
             for name, kind, db, roots in manifest_mod.namespaces(data, base=base)]
    pairs.append(("overlay", manifest_mod.overlay_db(data, base=base)))
    return _open(pairs)


def _node(row):
    d = dict(zip(_NODE_COLS.split(","), row))
    try:
        d["meta"] = json.loads(d["meta"]) if d["meta"] else {}
    except (ValueError, TypeError):
        d["meta"] = {}
    return d


def _edge(row):
    return dict(zip(_EDGE_COLS.split(","), row))


def get_node(kg, node_id):
    if not kg.aliases:
        return None
    row = kg.conn.execute(
        f"SELECT {_NODE_COLS} FROM ({kg.nodes_sql()}) WHERE id=? LIMIT 1",
        (node_id,)).fetchone()
    return _node(row) if row else None


def search(kg, q, k=5):
    if not kg.aliases:
        return []
    terms = [t for t in re.findall(r"\w+", q.lower()) if len(t) > 2]
    scored = []
    for row in kg.conn.execute(f"SELECT {_NODE_COLS} FROM ({kg.nodes_sql()})"):
        n = _node(row)
        hay = ((n["name"] or "") + " " + (n["text"] or "")).lower()
        score = sum(hay.count(t) for t in terms)
        if score:
            scored.append((score, n))
    scored.sort(key=lambda x: -x[0])
    return [n for _, n in scored[:k]]


def neighbors(kg, node_id):
    if not kg.aliases:
        return []
    rows = kg.conn.execute(
        f"SELECT {_EDGE_COLS} FROM ({kg.edges_sql()}) WHERE src=? OR dst=?",
        (node_id, node_id)).fetchall()
    return [_edge(r) for r in rows]


def trace(kg, node_id, max_depth=4):
    if ":" not in node_id:
        node_id = normalize_ref(node_id)  # 'ADR-0001' -> 'adr:ADR-0001', 'AS-1' -> 'story:AS-1'
    seen = {node_id}
    frontier = [node_id]
    chain, chain_keys = [], set()
    depth = 0
    while frontier and depth < max_depth and kg.aliases:
        ph = ",".join("?" * len(frontier))
        rows = kg.conn.execute(
            f"SELECT {_EDGE_COLS} FROM ({kg.edges_sql()}) "
            f"WHERE src IN ({ph}) OR dst IN ({ph})", frontier * 2).fetchall()
        nxt = []
        for r in rows:
            e = _edge(r)
            key = (e["src"], e["dst"], e["kind"])
            if key in chain_keys:
                continue
            chain_keys.add(key)
            chain.append(e)
            for endpoint in (e["src"], e["dst"]):
                if endpoint not in seen:
                    seen.add(endpoint)
                    nxt.append(endpoint)
        frontier = nxt
        depth += 1
    nodes = [n for n in (get_node(kg, nid) for nid in seen) if n]
    return {"root": node_id, "nodes": nodes, "edges": chain}
