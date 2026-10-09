#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Export the built knowledge graph to one self-contained HTML page (no network,
no dependencies) for visual exploration. Reads every namespace DB + the overlay
read-only; run `ingest.py --build` first.

  export_html.py                 # -> docs/knowledge/.knowledge/graph.html
  export_html.py --out PATH --open

Unresolved edges are kept and drawn against a `missing` placeholder node, so
dangling links stay visible instead of being silently dropped. The output embeds
doc titles, paths and short text snippets: it is a derived, git-ignored file.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import graph_store as gs          # noqa: E402
import manifest as manifest_mod   # noqa: E402

TEMPLATE = Path(__file__).resolve().parent / "graph_view.html"
DEFAULT_OUT = "docs/knowledge/.knowledge/graph.html"
DATA_MARKER = "/*__GRAPH_DATA__*/"
SNIPPET_KINDS = {"adr", "story", "doc", "source", "issue"}
SNIPPET_LEN = 280


def collect(data=None, base=None) -> dict:
    """Read all namespace DBs + the overlay into one {nodes, edges} payload."""
    data = data or manifest_mod.load()
    base = base or manifest_mod.REPO_ROOT
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    namespaces: list[str] = []
    built = 0.0
    dbs = [(name, db) for name, _kind, db, _roots in manifest_mod.namespaces(data, base=base)]
    dbs.append(("global", manifest_mod.overlay_db(data, base=base)))
    for name, db in dbs:
        if not Path(db).exists():
            continue
        built = max(built, Path(db).stat().st_mtime)
        conn = gs.connect_ro(db)
        for nid, kind, subtype, nm, path, tier, text, ns in conn.execute(
                "SELECT id,kind,subtype,name,path,tier,text,namespace FROM nodes"):
            node = {"id": nid, "kind": kind, "name": nm or nid, "ns": ns}
            if subtype:
                node["subtype"] = subtype
            if path:
                node["path"] = path
            if tier:
                node["tier"] = tier
            if text and kind in SNIPPET_KINDS:
                node["text"] = text[:SNIPPET_LEN]
            nodes.setdefault(nid, node)  # first namespace wins, as in ingest.build
        for src, dst, kind, source_file, line, resolved, ns in conn.execute(
                "SELECT src,dst,kind,source_file,line,resolved,namespace FROM edges"):
            edges.append({"src": src, "dst": dst, "kind": kind, "file": source_file,
                          "line": line, "resolved": int(resolved), "ns": ns})
        conn.close()
        if name != "global":
            namespaces.append(name)
    for e in edges:
        for end in (e["src"], e["dst"]):
            if end not in nodes:
                nodes[end] = {"id": end, "kind": "missing", "name": end, "ns": "global"}
    return {"nodes": list(nodes.values()), "edges": edges, "namespaces": namespaces,
            "built": time.strftime("%Y-%m-%d %H:%M", time.localtime(built)) if built else None}


def render(payload: dict, template: str | None = None) -> str:
    template = template if template is not None else TEMPLATE.read_text(encoding="utf-8")
    if DATA_MARKER not in template:
        raise ValueError(f"template has no {DATA_MARKER} marker")
    # "</" must not appear inside an inline <script>; "<\/" is the same JSON string.
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return template.replace(DATA_MARKER, blob, 1)


def main():
    ap = argparse.ArgumentParser(description="Export the knowledge graph to a self-contained HTML page.")
    ap.add_argument("--out", metavar="PATH", default=None,
                    help=f"output file (default: {DEFAULT_OUT})")
    ap.add_argument("--open", action="store_true", help="open the page in the default browser")
    a = ap.parse_args()

    payload = collect()
    if not payload["nodes"]:
        print("Graph is empty. Run: ingest.py --build")
        return 1
    out = Path(a.out) if a.out else manifest_mod.REPO_ROOT / DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(payload), encoding="utf-8")
    unresolved = sum(1 for e in payload["edges"] if not e["resolved"])
    print(f"  {len(payload['nodes'])} nodes  {len(payload['edges'])} edges  "
          f"{unresolved} unresolved  ->  {out}")
    if a.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
