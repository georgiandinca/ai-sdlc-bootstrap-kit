#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Issue ingester: the JIRA CSV ledger -> issue nodes + part-of and depends-on
edges. Stdlib `csv` only. One row per issue; the `epic`/`parent` columns become
`part-of` edges, and each key in the optional `depends_on` column (keys
separated by spaces or commas) becomes a `depends-on` edge. An edge is resolved
in-namespace when the referenced issue is in the same ledger, otherwise held
for the global overlay, where a key no ledger holds stays unresolved."""
from __future__ import annotations

import csv
from pathlib import Path

from graph_store import issue_id

META_COLS = ("type", "status", "assignee", "reporter", "labels", "sprint",
             "epic", "parent", "priority", "story_points", "created", "updated",
             "resolution", "url")


def ingest_root(root, namespace, base):
    root, base = Path(root), Path(base)
    nodes, edges = [], []
    if not root.exists():
        return nodes, edges
    rels = str(root.relative_to(base)).replace("\\", "/")
    with root.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            key = (row.get("key") or "").strip()
            if not key:
                continue
            nid = issue_id(key)
            title = (row.get("title") or "").strip()
            desc = (row.get("description") or "").strip()
            meta = {c: (row.get(c) or "").strip() for c in META_COLS}
            nodes.append({"id": nid, "kind": "issue",
                          "subtype": meta["type"] or None,
                          "name": title or key, "path": rels, "tier": None,
                          "text": " ".join((title + " " + desc).split())[:800],
                          "meta": meta, "namespace": namespace})
            for col in ("epic", "parent"):
                ref = (row.get(col) or "").strip()
                if ref and ref != key:
                    edges.append({"src": nid, "dst": issue_id(ref),
                                  "kind": "part-of", "source_file": rels,
                                  "line": None, "resolved": None,
                                  "namespace": namespace})
            depends = (row.get("depends_on") or "").strip()
            if depends:
                meta["depends_on"] = depends
            for ref in dict.fromkeys(depends.replace(",", " ").split()):
                if ref != key:
                    edges.append({"src": nid, "dst": issue_id(ref),
                                  "kind": "depends-on", "source_file": rels,
                                  "line": None, "resolved": None,
                                  "namespace": namespace})
    return nodes, edges
