#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Read the knowledge-graph manifest: namespace -> {kind, db, roots} + overlay.
All paths resolve against a base dir (default: the template repo root)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from graph_store import ISSUE_KEY

_HERE = Path(__file__).resolve().parent.parent.parent
# The manifest is always this checkout's. KG_BASE moves where the files are read
# and the graph is kept, for the CLI, the MCP server and the HTML export alike:
# from a git worktree, set it to the main checkout to get the repositories
# cloned under it. `ingest.py --base` does the same for one command.
REPO_ROOT = Path(os.environ["KG_BASE"]).resolve() if os.environ.get("KG_BASE") else _HERE
MANIFEST = _HERE / "docs" / "knowledge" / "graph-manifest.json"
DEFAULT_OVERLAY = "docs/knowledge/.knowledge/global.db"


def load(path=MANIFEST) -> dict:
    p = Path(path)
    if not p.exists():
        return {"namespaces": {}, "overlay": DEFAULT_OVERLAY}
    data = json.loads(p.read_text(encoding="utf-8"))
    data.setdefault("namespaces", {})
    data.setdefault("overlay", DEFAULT_OVERLAY)
    return data


def namespaces(data: dict, base=REPO_ROOT):
    base = Path(base)
    for name, spec in data["namespaces"].items():
        db = base / spec["db"]
        roots = [base / r for r in spec.get("roots", [])]
        yield name, spec.get("kind", "docs"), db, roots


def issue_key_pattern(data: dict) -> str:
    """The regular expression an issue key matches in this project: `key_pattern`
    on each `issues` namespace (default ABC-123), joined when they differ. It is
    matched against a whole frontmatter ref, and searched for in commit messages
    and branch names."""
    patterns = []
    for name, spec in data.get("namespaces", {}).items():
        if spec.get("kind") != "issues":
            continue
        pattern = spec.get("key_pattern") or ISSUE_KEY
        try:
            re.compile(pattern)
        except re.error as ex:
            raise ValueError(f"graph-manifest.json: namespace '{name}': key_pattern "
                             f"{pattern!r} is not a regular expression: {ex}") from ex
        if pattern not in patterns:
            patterns.append(pattern)
    if len(patterns) < 2:
        return patterns[0] if patterns else ISSUE_KEY
    return "|".join(f"(?:{p})" for p in patterns)


def overlay_db(data: dict, base=REPO_ROOT) -> Path:
    return Path(base) / data["overlay"]
