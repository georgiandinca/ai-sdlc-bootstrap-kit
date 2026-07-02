#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Optional layer: link commits to the code files they touched, using Phase 3's
dashboard `commits` table. Activates only when that DB + table are present;
otherwise a clean no-op (no hard dependency on Phase 3)."""
from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

from graph_store import commit_id

_KLASS_KEY = {"ai": "ai_commits", "ai-assisted": "ai_commits",
              "human": "human_commits", "mixed": "mixed_commits"}


def _has_commits_table(db_path: Path) -> bool:
    if not Path(db_path).exists():
        return False
    con = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    try:
        return con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='commits'"
        ).fetchone() is not None
    finally:
        con.close()


def _match(gitpath: str, by_path: dict):
    if gitpath in by_path:
        return by_path[gitpath]
    for npath, nid in by_path.items():
        if gitpath.endswith("/" + npath) or gitpath == npath:
            return nid
    return None


def link(namespace, code_nodes, dashboard_db, base):
    if not _has_commits_table(dashboard_db):
        return [], [], {}
    by_path = {n["path"]: n["id"] for n in code_nodes if n.get("path")}
    con = sqlite3.connect(f"file:{Path(dashboard_db)}?mode=ro", uri=True)
    try:
        commits = con.execute("SELECT sha, klass FROM commits").fetchall()
    finally:
        con.close()
    nodes, edges, attrib = [], [], {}
    for sha, klass in commits:
        out = subprocess.run(
            ["git", "-C", str(base), "show", "--numstat", "--format=", "-M", sha],
            capture_output=True, text=True).stdout
        cid = commit_id(namespace, sha)
        touched_any = False
        for ln in out.splitlines():
            parts = ln.split("\t")
            if len(parts) < 3:
                continue
            node_id = _match(parts[2], by_path)
            if not node_id:
                continue
            edges.append({"src": cid, "dst": node_id, "kind": "touches",
                          "source_file": None, "line": None, "resolved": 1,
                          "namespace": namespace})
            counts = attrib.setdefault(node_id, {"ai_commits": 0, "human_commits": 0,
                                                 "mixed_commits": 0})
            key = _KLASS_KEY.get(klass)
            if key:
                counts[key] += 1
            touched_any = True
        if touched_any:
            nodes.append({"id": cid, "kind": "commit", "subtype": None,
                          "name": sha[:10], "path": None, "tier": None, "text": None,
                          "meta": {"klass": klass, "sha": sha}, "namespace": namespace})
    return nodes, edges, attrib
