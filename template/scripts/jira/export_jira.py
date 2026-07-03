#!/usr/bin/env python3
"""Export JIRA issues (Cloud or Data Center) to the CSV ledger.

One exporter, two backends behind a deployment adapter (Task 6). Stdlib only.
Reads docs/product/jira/config.json, resolves auth from the environment, writes
docs/product/jira/issues.csv (sorted, idempotent). See docs/product/jira/README.md.
"""
from __future__ import annotations

import base64
import csv
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
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


FIELDS = ["issuetype", "summary", "status", "assignee", "reporter", "labels",
          "priority", "resolution", "created", "updated", "parent", "description"]


def load_config(path=CONFIG):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _env(name):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"export_jira: missing required env var {name}")
    return v


def _http_get(url, headers, timeout=30):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def cloud_headers():
    b = base64.b64encode(f"{_env('JIRA_EMAIL')}:{_env('JIRA_API_TOKEN')}".encode()).decode()
    return {"Authorization": f"Basic {b}", "Accept": "application/json"}


def datacenter_headers():
    pat = os.environ.get("JIRA_PAT")
    if pat:
        return {"Authorization": f"Bearer {pat}", "Accept": "application/json"}
    b = base64.b64encode(f"{_env('JIRA_USER')}:{_env('JIRA_PASSWORD')}".encode()).decode()
    return {"Authorization": f"Basic {b}", "Accept": "application/json"}


def paginate_offset(fetch, base_url, api, jql, fields, page_size=50):
    """DC / classic search: startAt + maxResults until total reached."""
    start, issues = 0, []
    while True:
        qs = urllib.parse.urlencode({"jql": jql, "startAt": start,
                                     "maxResults": page_size, "fields": ",".join(fields)})
        data = fetch(f"{base_url.rstrip('/')}/rest/api/{api}/search?{qs}")
        batch = data.get("issues", [])
        issues += batch
        start += len(batch)
        if not batch or start >= data.get("total", 0):
            return issues


def paginate_cursor(fetch, base_url, jql, fields, page_size=50):
    """Cloud enhanced search: nextPageToken cursor."""
    token, issues = None, []
    while True:
        params = {"jql": jql, "maxResults": page_size, "fields": ",".join(fields)}
        if token:
            params["nextPageToken"] = token
        data = fetch(f"{base_url.rstrip('/')}/rest/api/3/search/jql?"
                     f"{urllib.parse.urlencode(params)}")
        issues += data.get("issues", [])
        token = data.get("nextPageToken")
        if not token:
            return issues


BACKENDS = {
    "cloud": {"headers": cloud_headers, "paginate": "cursor"},
    "datacenter": {"headers": datacenter_headers, "paginate": "offset", "api": "2"},
}


def fetch_all(cfg):
    dep = cfg.get("deployment")
    if dep not in BACKENDS:
        sys.exit(f"export_jira: unknown deployment {dep!r} (expected cloud|datacenter)")
    backend = BACKENDS[dep]
    base_url = _env(cfg.get("base_url_env", "JIRA_BASE_URL"))
    headers = backend["headers"]()
    fields = FIELDS + [v for v in cfg.get("fields", {}).values() if v]
    jql = cfg.get("jql") or f"project = {cfg['project']} ORDER BY updated DESC"

    def fetch(url):
        return _http_get(url, headers)

    if backend["paginate"] == "cursor":
        raw = paginate_cursor(fetch, base_url, jql, fields)
    else:
        raw = paginate_offset(fetch, base_url, backend["api"], jql, fields)
    return base_url, raw


def main(argv=None, config=None, ledger=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    from_json = None
    do_build = False
    if "--from-json" in argv:
        i = argv.index("--from-json")
        from_json = argv[i + 1]
        del argv[i:i + 2]
    if "--build" in argv:
        do_build = True
        argv.remove("--build")
    cfg = config if config is not None else load_config()
    if from_json:
        loaded = json.loads(Path(from_json).read_text(encoding="utf-8"))
        raw = loaded.get("issues", loaded) if isinstance(loaded, dict) else loaded
        base_url = os.environ.get(cfg.get("base_url_env", "JIRA_BASE_URL"),
                                  cfg.get("base_url", ""))
    else:
        base_url, raw = fetch_all(cfg)
    rows = [normalize_issue(r, cfg, base_url) for r in raw]
    path = write_ledger(rows, ledger if ledger is not None else LEDGER)
    print(f"export_jira: wrote {len(rows)} issues -> {path}")
    if do_build:
        import subprocess
        subprocess.run([sys.executable,
                        str(REPO_ROOT / "scripts" / "knowledge" / "ingest.py"), "--build"],
                       check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
