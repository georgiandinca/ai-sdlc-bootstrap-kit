#!/usr/bin/env python3
"""Export JIRA issues (Cloud or Data Center) to the CSV ledger.

One exporter, two backends behind a deployment adapter (Task 6). Stdlib only.
Reads docs/product/jira/config.json, resolves auth from the environment, writes
docs/product/jira/issues.csv (sorted, idempotent). See docs/product/jira/README.md.
"""
from __future__ import annotations

import csv
import os
import re
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = REPO_ROOT / "docs" / "product" / "jira" / "config.json"
LEDGER = REPO_ROOT / "docs" / "product" / "jira" / "issues.csv"

COLUMNS = ["key", "type", "title", "status", "assignee", "reporter", "labels",
           "sprint", "epic", "parent", "priority", "story_points", "created",
           "updated", "resolution", "url", "description"]


def _name(obj):
    if isinstance(obj, dict):
        return obj.get("displayName") or obj.get("name") or ""
    return obj or ""


def _num(v):
    if v in (None, ""):
        return ""
    try:
        fv = float(v)
        return str(int(fv)) if fv.is_integer() else str(fv)
    except (TypeError, ValueError):
        return str(v)


# ADF block-level nodes: separate these so sibling blocks don't run together.
# (Inline runs like `text` concatenate directly; downstream whitespace-collapsing
#  turns the inserted "\n" into a single space.)
_ADF_BLOCKS = {"paragraph", "heading", "blockquote", "codeBlock", "panel",
               "listItem", "bulletList", "orderedList", "rule", "tableRow"}


def adf_to_text(node):
    """Flatten an Atlassian Document Format node (Cloud) to plain text."""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    parts = []
    for child in node.get("content", []) or []:
        text = adf_to_text(child)
        if not text:
            continue
        if parts and isinstance(child, dict) and child.get("type") in _ADF_BLOCKS:
            parts.append("\n")
        parts.append(text)
    return "".join(parts)


def normalize_description(desc, max_chars):
    if isinstance(desc, dict):
        text = adf_to_text(desc)
    elif desc is None:
        text = ""
    else:
        text = str(desc)
    return " ".join(text.split())[:max_chars]


def _sprint(fields, cfg):
    raw = fields.get(cfg.get("fields", {}).get("sprint", ""))
    if isinstance(raw, list) and raw:
        last = raw[-1]
        if isinstance(last, dict):
            return last.get("name", "")
        m = re.search(r"name=([^,\]]+)", str(last))  # DC greenhopper string form
        return m.group(1) if m else str(last)
    return ""


def normalize_issue(raw, cfg, base_url):
    f = raw.get("fields", {}) or {}
    fmap = cfg.get("fields", {})
    parent_key = (f.get("parent") or {}).get("key", "")
    epic_key = f.get(fmap.get("epic_link", ""), "") or parent_key
    return {
        "key": raw.get("key", ""),
        "type": _name(f.get("issuetype")),
        "title": f.get("summary", "") or "",
        "status": _name(f.get("status")),
        "assignee": _name(f.get("assignee")),
        "reporter": _name(f.get("reporter")),
        "labels": ";".join(f.get("labels") or []),
        "sprint": _sprint(f, cfg),
        "epic": epic_key,
        "parent": parent_key,
        "priority": _name(f.get("priority")),
        "story_points": _num(f.get(fmap.get("story_points", ""))),
        "created": f.get("created", "") or "",
        "updated": f.get("updated", "") or "",
        "resolution": _name(f.get("resolution")),
        "url": f"{base_url.rstrip('/')}/browse/{raw.get('key', '')}",
        "description": normalize_description(
            f.get("description"), cfg.get("description_max_chars", 500)),
    }


def natural_key(key):
    m = re.match(r"^([A-Za-z]+)-(\d+)$", key or "")
    return (m.group(1), int(m.group(2))) if m else (key or "", 0)


def write_ledger(rows, path=LEDGER):
    rows = sorted(rows, key=lambda r: natural_key(r.get("key", "")))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".csv")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n",
                               extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in COLUMNS})
        os.replace(tmp, path)  # atomic; original untouched unless we fully succeed
    except Exception:
        os.unlink(tmp)
        raise
    return path
