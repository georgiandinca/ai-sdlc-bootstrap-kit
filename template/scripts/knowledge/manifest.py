#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Read the knowledge-graph manifest: namespace -> {kind, db, roots} + overlay.
All paths resolve against a base dir (default: the template repo root)."""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST = REPO_ROOT / "docs" / "knowledge" / "graph-manifest.json"
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


def overlay_db(data: dict, base=REPO_ROOT) -> Path:
    return Path(base) / data["overlay"]
