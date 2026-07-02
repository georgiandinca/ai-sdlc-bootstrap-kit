#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Knowledge-graph orchestrator + CLI. Replaces the keyword stub: builds a
per-namespace docs+code graph (+ a global overlay) and answers scoped or
federated queries/traces, each grounded on a source citation.

  ingest.py --build                       # (re)build every namespace + overlay
  ingest.py --stats
  ingest.py --query "text" [--scope NS | --federated]
  ingest.py --trace ADR-0001 [--scope NS | --federated]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import graph_store as gs          # noqa: E402
import manifest as manifest_mod   # noqa: E402
import ingest_docs                # noqa: E402
import ingest_code                # noqa: E402
import link_commits               # noqa: E402
import query as query_mod         # noqa: E402

DASHBOARD_DB = manifest_mod.REPO_ROOT / "dashboard" / "utilization.db"


def build(data=None, base=None):
    data = data or manifest_mod.load()
    base = base or manifest_mod.REPO_ROOT
    all_ids: set[str] = set()
    all_paths: dict[str, str] = {}
    held: list[dict] = []

    for name, kind, db, roots in manifest_mod.namespaces(data, base=base):
        conn = gs.connect(db)
        conn.execute("DELETE FROM edges")
        conn.execute("DELETE FROM nodes")
        ns_nodes, ns_edges = [], []
        for root in roots:
            if not Path(root).exists():
                continue
            if kind == "code":
                n, e = ingest_code.ingest_root(root, name, base)
            else:
                n, e = ingest_docs.ingest_root(root, name, base)
            ns_nodes += n
            ns_edges += e
        if kind == "code":
            cn, ce, attrib = link_commits.link(name, ns_nodes, DASHBOARD_DB, base)
            ns_nodes += cn
            ns_edges += ce
            for nd in ns_nodes:
                if nd["id"] in attrib:
                    nd["meta"] = {**(nd.get("meta") or {}), **attrib[nd["id"]]}
        ns_ids = {nd["id"] for nd in ns_nodes}
        for nd in ns_nodes:
            gs.add_node(conn, nd)
            if nd.get("path") and nd["kind"] != "symbol":
                all_paths.setdefault(nd["path"], nd["id"])  # first namespace wins on cross-namespace path collisions
        all_ids |= ns_ids
        for e in ns_edges:
            if e["src"] in ns_ids and e["dst"] in ns_ids:
                e = {**e, "resolved": 1}
                gs.add_edge(conn, e)
            else:
                held.append(e)
        conn.commit()
        conn.close()

    ov = manifest_mod.overlay_db(data, base=base)
    oconn = gs.connect(ov)
    oconn.execute("DELETE FROM edges")
    oconn.execute("DELETE FROM nodes")
    for e in held:
        dst = e["dst"]
        if isinstance(dst, str) and dst.startswith("path:"):
            p = dst[len("path:"):]
            dst = all_paths.get(p, dst)
        row = {**e, "dst": dst, "namespace": "global"}
        row["resolved"] = 1 if (e["src"] in all_ids and dst in all_ids) else 0
        gs.add_edge(oconn, row)
    oconn.commit()
    oconn.close()
    return _stats(data, base)


def _stats(data, base):
    ns_stats = []
    for name, kind, db, roots in manifest_mod.namespaces(data, base=base):
        if Path(db).exists():
            c = gs.connect_ro(db)
            nn = c.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            ne = c.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            c.close()
            ns_stats.append([name, nn, ne])
    ov = manifest_mod.overlay_db(data, base=base)
    ove = 0
    if Path(ov).exists():
        c = gs.connect_ro(ov)
        ove = c.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        c.close()
    return {"namespaces": ns_stats, "overlay_edges": ove}


def _kg(scope):
    return query_mod.open_scoped(scope) if scope else query_mod.open_federated()


def main():
    ap = argparse.ArgumentParser(description="Docs+code knowledge graph.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--build", action="store_true", help="(re)build all namespaces + overlay")
    g.add_argument("--stats", action="store_true", help="show node/edge counts")
    g.add_argument("--query", metavar="TEXT", help="content search")
    g.add_argument("--trace", metavar="ID", help="trace a node id's chain")
    ap.add_argument("--scope", metavar="NS", help="restrict to one namespace")
    ap.add_argument("--federated", action="store_true", help="query across all namespaces (default)")
    a = ap.parse_args()

    if a.build:
        stats = build()
        for name, nn, ne in stats["namespaces"]:
            print(f"  {name:<10} {nn:>5} nodes  {ne:>5} edges")
        print(f"  {'overlay':<10} {'':>5}        {stats['overlay_edges']:>5} edges")
        print("Built docs+code knowledge graph. See docs/knowledge/README.md.")
        return 0
    if a.stats:
        print(json.dumps(_stats(manifest_mod.load(), manifest_mod.REPO_ROOT), indent=2))
        return 0
    scope = a.scope if not a.federated else None
    kg = _kg(scope)
    if not kg.aliases:
        print(query_mod.EMPTY_HINT)
        return 1
    if a.query:
        print(json.dumps(query_mod.search(kg, a.query), indent=2))
    else:
        print(json.dumps(query_mod.trace(kg, a.trace), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
