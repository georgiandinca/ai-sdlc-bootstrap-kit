#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Knowledge-graph orchestrator + CLI. Replaces the keyword stub: builds a
per-namespace docs+code graph (+ a global overlay) and answers scoped or
federated queries/traces, each grounded on a source citation.

  ingest.py --build                       # (re)build every namespace + overlay
  ingest.py --stats
  ingest.py --freshness                   # built from the commits checked out now?
  ingest.py --query "text" [--scope NS | --federated]
  ingest.py --trace ADR-0001 [--scope NS | --federated] [--depth N]
  ingest.py ... --base DIR                # read and keep the graph under DIR
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import graph_store as gs          # noqa: E402
import manifest as manifest_mod   # noqa: E402
import ingest_docs                # noqa: E402
import ingest_code                # noqa: E402
import ingest_issues              # noqa: E402
import link_issues                # noqa: E402
import link_commits               # noqa: E402
import freshness                  # noqa: E402
import query as query_mod         # noqa: E402

DASHBOARD_DB = Path("dashboard") / "utilization.db"   # under the base


def _drop_ignored(nodes, edges, base, tree=None):
    """Drop nodes (and their edges) whose file is git-ignored: vendored or
    generated trees (node_modules/, out/) are not project knowledge. Outside a
    git work tree nothing is dropped. `tree` is the work tree that decides
    (default: the base); node paths stay relative to the base, and may start
    with `../` for a root beside it."""
    base = Path(base).resolve()
    tree = Path(tree).resolve() if tree else base
    in_tree = {}  # path as the deciding work tree sees it -> path as the node holds it
    for nd in nodes:
        if nd.get("path"):
            try:
                full = Path(os.path.normpath(base / nd["path"]))
                in_tree[str(full.relative_to(tree)).replace("\\", "/")] = nd["path"]
            except ValueError:
                continue
    if not in_tree:
        return nodes, edges
    try:
        r = subprocess.run(["git", "check-ignore", "-z", "--stdin"], cwd=str(tree),
                           input="\0".join(sorted(in_tree)), capture_output=True, text=True)
    except OSError:
        return nodes, edges
    if r.returncode != 0:  # 1 = none ignored, 128 = not a git work tree
        return nodes, edges
    ignored = {in_tree[p] for p in r.stdout.split("\0") if p in in_tree}
    gone = {nd["id"] for nd in nodes if nd.get("path") in ignored}
    return ([nd for nd in nodes if nd["id"] not in gone],
            [e for e in edges if e["src"] not in gone and e["dst"] not in gone])


def build(data=None, base=None):
    data = data or manifest_mod.load()
    base = base or manifest_mod.REPO_ROOT
    all_ids: set[str] = set()
    all_paths: dict[str, str] = {}
    held: list[dict] = []
    issues_present = any(spec.get("kind") == "issues"
                         for spec in data.get("namespaces", {}).values())
    freshness.forget(data, base)

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
            elif kind == "issues":
                n, e = ingest_issues.ingest_root(root, name, base)
            else:
                n, e = ingest_docs.ingest_root(root, name, base)
            n, e = _drop_ignored(n, e, base, freshness.work_tree(root, base))
            ns_nodes += n
            ns_edges += e
        # commits are recorded for the base repository; a namespace read from
        # another repository has none to link, and the search is slow
        own = all(freshness.work_tree(r, base) == Path(base).resolve() for r in roots)
        if kind == "code" and own:
            cn, ce, attrib = link_commits.link(name, ns_nodes, Path(base) / DASHBOARD_DB, base)
            ns_nodes += cn
            ns_edges += ce
            if issues_present:
                ns_edges += link_issues.link(name, cn, base)
            for nd in ns_nodes:
                if nd["id"] in attrib:
                    nd["meta"] = {**(nd.get("meta") or {}), **attrib[nd["id"]]}
        ns_ids = {nd["id"] for nd in ns_nodes}
        # path refs to a file in this namespace (possibly under another root) resolve here
        ns_paths = {nd["path"]: nd["id"] for nd in ns_nodes
                    if nd.get("path") and nd["kind"] != "symbol"}
        ns_edges = [{**e, "dst": ns_paths.get(e["dst"][len("path:"):], e["dst"])}
                    if isinstance(e["dst"], str) and e["dst"].startswith("path:") else e
                    for e in ns_edges]
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
    freshness.record(data, base)
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


def _kg(scope, base=None):
    return (query_mod.open_scoped(scope, base=base) if scope
            else query_mod.open_federated(base=base))


def main():
    ap = argparse.ArgumentParser(description="Docs+code knowledge graph.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--build", action="store_true", help="(re)build all namespaces + overlay")
    g.add_argument("--stats", action="store_true", help="show node/edge counts")
    g.add_argument("--freshness", action="store_true",
                   help="is the graph built from the commits checked out now? exit 1 if not")
    g.add_argument("--query", metavar="TEXT", help="content search")
    g.add_argument("--trace", metavar="ID", help="trace a node id's chain")
    ap.add_argument("--scope", metavar="NS", help="restrict to one namespace")
    ap.add_argument("--federated", action="store_true", help="query across all namespaces (default)")
    ap.add_argument("--depth", type=int, default=4, metavar="N",
                    help="how many edges --trace follows from the id (default 4; "
                         "1 = only what is tied to it directly)")
    ap.add_argument("--base", metavar="DIR", type=Path,
                    help="read the files, and keep the graph, under DIR in place of this "
                         "checkout; this checkout's scripts and manifest are still used. "
                         "From a git worktree, name the main checkout to get the "
                         "product repositories cloned under it")
    a = ap.parse_args()
    if a.base and not a.base.is_dir():
        ap.error(f"--base {a.base} is not a directory")
    base = a.base.resolve() if a.base else manifest_mod.REPO_ROOT

    if a.build:
        stats = build(base=base)
        for name, nn, ne in stats["namespaces"]:
            print(f"  {name:<10} {nn:>5} nodes  {ne:>5} edges")
        print(f"  {'overlay':<10} {'':>5}        {stats['overlay_edges']:>5} edges")
        print("Built docs+code knowledge graph. See docs/knowledge/README.md.")
        return 0
    if a.stats:
        print(json.dumps(_stats(manifest_mod.load(), base), indent=2))
        return 0
    if a.freshness:
        state = freshness.check(base=base)
        print(json.dumps(state, indent=2))
        return 0 if state["state"] == "fresh" else 1
    scope = a.scope if not a.federated else None
    kg = _kg(scope, base)
    if not kg.aliases:
        print(query_mod.EMPTY_HINT)
        return 1
    if a.query:
        print(json.dumps(query_mod.search(kg, a.query), indent=2))
    else:
        print(json.dumps(query_mod.trace(kg, a.trace, max_depth=max(1, a.depth)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
