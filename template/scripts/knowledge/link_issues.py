#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Optional layer: link commits to the JIRA issues they reference, by scanning
each commit message for issue keys (ABC-123). Operates on the commit nodes that
`link_commits` produced (Phase-3 commit layer); a clean no-op when there are
none. commit -> issue is cross-namespace, so the edges resolve in the global
overlay against the ingested issue nodes (dangling -> resolved=0, surfaced)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from graph_store import issue_id

KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


def _message(base, sha):
    out = subprocess.run(
        ["git", "-C", str(base), "log", "-1", "--format=%B", sha],
        capture_output=True, text=True)
    return out.stdout


def link(namespace, commit_nodes, base):
    base = Path(base)
    edges = []
    for cn in commit_nodes:
        sha = (cn.get("meta") or {}).get("sha") or cn["id"].rsplit(":", 1)[-1]
        seen = set()
        for m in KEY_RE.finditer(_message(base, sha)):
            key = m.group(0)
            if key in seen:
                continue
            seen.add(key)
            edges.append({"src": cn["id"], "dst": issue_id(key),
                          "kind": "references", "source_file": None,
                          "line": None, "resolved": None, "namespace": namespace})
    return edges
