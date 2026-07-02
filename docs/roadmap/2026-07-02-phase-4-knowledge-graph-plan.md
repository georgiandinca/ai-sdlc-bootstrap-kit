# Phase 4 — Docs + Code Knowledge Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the keyword stub with a local, per-repo-isolated SQLite graph over docs *and* code, carrying ADR→code→test→story traceability, queryable scoped or federated, exposed via a stdlib MCP server on the `knowledge` slot.

**Architecture:** One SQLite DB per namespace (`nodes` + `edges`, identical DDL) plus a shared `global` overlay DB for cross-namespace edges; federation via `ATTACH` + `UNION ALL`. Stdlib ingesters (frontmatter for docs, `ast`+regex for code) return plain dict records; an orchestrator writes them, holds cross-namespace edges, runs an optional commit-linkage layer, then a resolve pass materializes the overlay. A read-only query engine backs both the CLI and a newline-delimited JSON-RPC MCP server.

**Tech Stack:** Python 3.9+ stdlib only (`sqlite3`, `ast`, `json`, `re`, `subprocess`, `argparse`, `unittest`). No pip dependencies.

## Global Constraints

- **Python stdlib only** — no new pip dependencies. Python 3.9+, `from __future__ import annotations`.
- **Every new module starts with the marker comment `# ADR-0001 — local docs+code knowledge graph`** (second line, after the shebang) — this is the dogfood `implements` signal. Test files do NOT carry the marker.
- **Derived DBs are git-ignored** via `**/.knowledge/` (every namespace DB + the overlay at `docs/knowledge/.knowledge/global.db`); the manifest `docs/knowledge/graph-manifest.json` is committed.
- **Idempotent** — schema uses `CREATE TABLE IF NOT EXISTS`; writes use `INSERT OR REPLACE`; `--build` clears each DB's rows first so re-runs reproduce the same graph.
- **Every query result is citable** — carries `namespace`, `path`/`source_file`, `line`, `tier`. No fabricated edges: unresolved links are kept with `resolved=0`, never dropped or invented.
- **No hard dependency on Phase 3** — the commit layer no-ops unless `dashboard/utilization.db` with a `commits` table exists.
- **MCP server degrades gracefully** when the graph is unbuilt.
- `AGENTS.md` is canonical; `CLAUDE.md` stays a pure pointer (untouched); no secrets; no real personal data.
- **Commit trailer** on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- All modules live in `template/scripts/knowledge/`; tests in `template/scripts/knowledge/tests/`. Paths below are relative to `template/` unless prefixed with `template/`.
- Each test file begins with `import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` so `import graph_store` etc. resolve.

## File Structure

| File | Responsibility |
|---|---|
| `scripts/knowledge/graph_store.py` | SQLite schema + `connect`/`connect_ro`/`ensure_schema`; `add_node`/`add_edge` (dict records); id-scheme helpers; `normalize_ref`. |
| `scripts/knowledge/manifest.py` | Load `docs/knowledge/graph-manifest.json`; iterate namespaces (name, kind, db, roots); overlay path. All resolved against a `base` dir. |
| `scripts/knowledge/ingest_docs.py` | `parse_frontmatter` + `ingest_root(root, ns, base)` → nodes/edges from frontmatter link fields. |
| `scripts/knowledge/ingest_code.py` | `ingest_root(root, ns, base)` → code-file/test/symbol nodes, `contains`/`imports` (intra-ns resolved), `implements` (ADR markers), `covers` (naming). |
| `scripts/knowledge/link_commits.py` | Optional `link(ns, code_nodes, dashboard_db, base)` → commit nodes + `touches` edges + attribution map. No-op without the dashboard DB. |
| `scripts/knowledge/query.py` | `open_scoped`/`open_federated` (ATTACH, `query_only`); `KG` wrapper; `get_node`/`search`/`neighbors`/`trace`. |
| `scripts/knowledge/ingest.py` | Rewritten orchestrator + CLI: `--build`, `--stats`, `--query`, `--trace`, `--scope`, `--federated`. |
| `scripts/knowledge/mcp_server.py` | Newline-delimited JSON-RPC stdio server: `initialize`/`tools/list`/`tools/call` for `kg_query`/`kg_federated_query`/`kg_trace`. |
| `docs/knowledge/graph-manifest.json` | Namespace registry (committed). |
| `docs/architecture/decisions/ADR-0001-adopt-knowledge-graph.md` | Dogfood ADR node. |
| `docs/product/stories/AS-0001-adopt-knowledge-graph.md` | Seed story (`traces: [ADR-0001]`). |
| `docs/knowledge/schema.md`, `docs/knowledge/README.md`, `.claude/rules/knowledge-sources.md`, `.mcp.json`, `AGENTS.md`, `.gitignore` | Updated (see Tasks 9). |
| CI: root `.gitlab-ci.yml`, `template/.github/workflows/ai-governance.yml` | Add knowledge test suite + trace smoke (Task 10). |

**Namespace id scheme:** `adr:ADR-NNNN`, `story:AS-N` (bare/canonical); `code:<ns>:<path>`, `doc:<ns>:<path>`, `source:<ns>:<path>`, `sym:<ns>:<path>:<name>`, `test:<ns>:<path>`, `commit:<ns>:<sha>` (namespace-prefixed).

---

### Task 1: graph_store.py — schema, writers, id scheme

**Files:**
- Create: `scripts/knowledge/graph_store.py`
- Test: `scripts/knowledge/tests/test_graph_store.py`

**Interfaces:**
- Produces: `ensure_schema(conn)`, `connect(db_path)->Connection`, `connect_ro(db_path)->Connection`, `add_node(conn, node:dict)`, `add_edge(conn, edge:dict)`, id helpers `adr_id/story_id/code_id/doc_id/source_id/symbol_id/test_id/commit_id`, `normalize_ref(ref:str)->str`. `NODE_FIELDS`, `EDGE_FIELDS` tuples.

- [ ] **Step 1: Write the failing test**

```python
# scripts/knowledge/tests/test_graph_store.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sqlite3, tempfile, unittest
import graph_store as gs


class GraphStoreTests(unittest.TestCase):
    def test_schema_idempotent(self):
        conn = sqlite3.connect(":memory:")
        gs.ensure_schema(conn)
        gs.ensure_schema(conn)  # second call must not raise
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("nodes", names)
        self.assertIn("edges", names)

    def test_add_and_replace_node(self):
        conn = sqlite3.connect(":memory:"); gs.ensure_schema(conn)
        gs.add_node(conn, {"id": "adr:ADR-0001", "kind": "adr", "name": "x",
                           "namespace": "docs", "meta": {"a": 1}})
        gs.add_node(conn, {"id": "adr:ADR-0001", "kind": "adr", "name": "y",
                           "namespace": "docs"})  # replace
        rows = conn.execute("SELECT name, meta FROM nodes WHERE id=?",
                            ("adr:ADR-0001",)).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "y")
        self.assertEqual(rows[0][1], "{}")  # meta defaults to {} json

    def test_add_edge_defaults_resolved(self):
        conn = sqlite3.connect(":memory:"); gs.ensure_schema(conn)
        gs.add_edge(conn, {"src": "a", "dst": "b", "kind": "implements",
                           "namespace": "global"})
        r = conn.execute("SELECT resolved FROM edges").fetchone()
        self.assertEqual(r[0], 1)

    def test_id_helpers_and_normalize(self):
        self.assertEqual(gs.adr_id("ADR-0001"), "adr:ADR-0001")
        self.assertEqual(gs.code_id("kit", "a/b.py"), "code:kit:a/b.py")
        self.assertEqual(gs.symbol_id("kit", "a.py", "f"), "sym:kit:a.py:f")
        self.assertEqual(gs.normalize_ref("ADR-0003"), "adr:ADR-0003")
        self.assertEqual(gs.normalize_ref("AS-2"), "story:AS-2")
        self.assertEqual(gs.normalize_ref("scripts/x.py"), "path:scripts/x.py")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/knowledge/tests/test_graph_store.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'graph_store'`.

- [ ] **Step 3: Write the module**

```python
# scripts/knowledge/graph_store.py
#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""SQLite graph store: nodes + edges, one DB per namespace (+ a global overlay).

Stdlib only. Idempotent schema; INSERT OR REPLACE writes. Records are plain
dicts produced by the ingesters; this module owns the DDL and the id scheme so
every producer stays consistent.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, subtype TEXT, name TEXT,
  path TEXT, tier TEXT, text TEXT, meta TEXT, namespace TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edges (
  src TEXT NOT NULL, dst TEXT NOT NULL, kind TEXT NOT NULL,
  source_file TEXT, line INTEGER, resolved INTEGER NOT NULL DEFAULT 1,
  namespace TEXT NOT NULL, PRIMARY KEY (src, dst, kind)
);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
"""

NODE_FIELDS = ("id", "kind", "subtype", "name", "path", "tier", "text", "meta", "namespace")
EDGE_FIELDS = ("src", "dst", "kind", "source_file", "line", "resolved", "namespace")


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def connect(db_path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    ensure_schema(conn)
    return conn


def connect_ro(db_path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)


def add_node(conn: sqlite3.Connection, node: dict) -> None:
    vals = []
    for k in NODE_FIELDS:
        v = node.get(k)
        if k == "meta":
            v = json.dumps(v or {}, sort_keys=True)
        vals.append(v)
    conn.execute(
        f"INSERT OR REPLACE INTO nodes ({','.join(NODE_FIELDS)}) "
        f"VALUES ({','.join('?' * len(NODE_FIELDS))})", vals)


def add_edge(conn: sqlite3.Connection, edge: dict) -> None:
    e = dict(edge)
    if e.get("resolved") is None:
        e["resolved"] = 1
    conn.execute(
        f"INSERT OR REPLACE INTO edges ({','.join(EDGE_FIELDS)}) "
        f"VALUES ({','.join('?' * len(EDGE_FIELDS))})",
        [e.get(k) for k in EDGE_FIELDS])


def adr_id(num: str) -> str: return f"adr:{num}"
def story_id(sid: str) -> str: return f"story:{sid}"
def code_id(ns: str, path: str) -> str: return f"code:{ns}:{path}"
def doc_id(ns: str, path: str) -> str: return f"doc:{ns}:{path}"
def source_id(ns: str, path: str) -> str: return f"source:{ns}:{path}"
def symbol_id(ns: str, path: str, name: str) -> str: return f"sym:{ns}:{path}:{name}"
def test_id(ns: str, path: str) -> str: return f"test:{ns}:{path}"
def commit_id(ns: str, sha: str) -> str: return f"commit:{ns}:{sha}"

_ADR_RE = re.compile(r"^ADR-\d{3,4}$")
_STORY_RE = re.compile(r"^AS-\d+$", re.I)


def normalize_ref(ref: str) -> str:
    """Frontmatter ref -> node id. ADR/story -> canonical id; a path -> a
    provisional 'path:<p>' id resolved later; anything else stays literal."""
    ref = ref.strip()
    if _ADR_RE.match(ref):
        return adr_id(ref)
    if _STORY_RE.match(ref):
        return story_id(ref.upper())
    if "/" in ref or "." in ref:
        return f"path:{ref}"
    return ref
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/scripts/knowledge/tests/test_graph_store.py`
Expected: `OK` (4 tests).

- [ ] **Step 5: Commit**

```bash
git add template/scripts/knowledge/graph_store.py template/scripts/knowledge/tests/test_graph_store.py
git commit -m "feat: knowledge graph store (schema, writers, id scheme)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: manifest.py + graph-manifest.json + .gitignore

**Files:**
- Create: `scripts/knowledge/manifest.py`, `docs/knowledge/graph-manifest.json`
- Modify: `.gitignore`
- Test: `scripts/knowledge/tests/test_manifest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `REPO_ROOT` (Path = `template/`), `load(path=MANIFEST)->dict`, `namespaces(data, base=REPO_ROOT)` → yields `(name, kind, db:Path, roots:list[Path])`, `overlay_db(data, base=REPO_ROOT)->Path`.

- [ ] **Step 1: Write the failing test**

```python
# scripts/knowledge/tests/test_manifest.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json, tempfile, unittest
import manifest as m


class ManifestTests(unittest.TestCase):
    def test_load_missing_returns_defaults(self):
        data = m.load(Path(tempfile.gettempdir()) / "no-such-manifest-xyz.json")
        self.assertEqual(data["namespaces"], {})
        self.assertIn("overlay", data)

    def test_roundtrip_and_resolution(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            data = {"namespaces": {
                        "docs": {"kind": "docs", "db": "docs/.knowledge/graph.db",
                                 "roots": ["docs/"]}},
                    "overlay": "docs/knowledge/.knowledge/global.db"}
            (base / "mf.json").write_text(json.dumps(data), encoding="utf-8")
            loaded = m.load(base / "mf.json")
            got = list(m.namespaces(loaded, base=base))
            self.assertEqual(len(got), 1)
            name, kind, db, roots = got[0]
            self.assertEqual(name, "docs")
            self.assertEqual(kind, "docs")
            self.assertEqual(db, base / "docs/.knowledge/graph.db")
            self.assertEqual(roots, [base / "docs/"])
            self.assertEqual(m.overlay_db(loaded, base=base),
                             base / "docs/knowledge/.knowledge/global.db")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/knowledge/tests/test_manifest.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'manifest'`.

- [ ] **Step 3: Write the module + the manifest + .gitignore entry**

```python
# scripts/knowledge/manifest.py
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
```

```json
// docs/knowledge/graph-manifest.json
{
  "namespaces": {
    "docs":     { "kind": "docs", "db": "docs/.knowledge/graph.db", "roots": ["docs/"] },
    "kit-code": { "kind": "code", "db": ".knowledge/graph.db",       "roots": ["scripts/", "dashboard/"] }
  },
  "overlay": "docs/knowledge/.knowledge/global.db"
}
```

(Write the JSON WITHOUT the `//` comment line — JSON has no comments.)

In `.gitignore`, replace the three knowledge-layer lines (`docs/knowledge/.index/`, `docs/knowledge/*.duckdb`, `docs/knowledge/*.sqlite`) with:

```gitignore
# Knowledge layer — local vector store / graph build artifacts (sources + manifest stay tracked)
docs/knowledge/.index/
docs/knowledge/*.duckdb
docs/knowledge/*.sqlite
# Derived per-namespace graph DBs + the global overlay (Phase 4)
**/.knowledge/
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/scripts/knowledge/tests/test_manifest.py`
Expected: `OK` (2 tests).

Also confirm the committed manifest is NOT ignored: `git -C template check-ignore docs/knowledge/graph-manifest.json; echo rc=$?` → Expected `rc=1` (not ignored). And `git -C template check-ignore docs/knowledge/.knowledge/global.db; echo rc=$?` → Expected `rc=0` (ignored).

- [ ] **Step 5: Commit**

```bash
git add template/scripts/knowledge/manifest.py template/docs/knowledge/graph-manifest.json template/.gitignore template/scripts/knowledge/tests/test_manifest.py
git commit -m "feat: knowledge-graph manifest + ignore derived .knowledge DBs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: ingest_docs.py — frontmatter + link-field edges

**Files:**
- Create: `scripts/knowledge/ingest_docs.py`
- Test: `scripts/knowledge/tests/test_ingest_docs.py`

**Interfaces:**
- Consumes: `graph_store` id helpers + `normalize_ref`.
- Produces: `parse_frontmatter(text)->(meta:dict, body:str)`, `classify(rel_path, meta)->(kind, ident)`, `ingest_root(root:Path, namespace:str, base:Path)->(nodes:list[dict], edges:list[dict])`. Edge kinds emitted: `implements`, `traces`, `cites`, `supersedes`, `covers` (from frontmatter link fields only — no freeform body scanning; code markers are the code-side signal in Task 4).

- [ ] **Step 1: Write the failing test**

```python
# scripts/knowledge/tests/test_ingest_docs.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tempfile, unittest
import ingest_docs as idoc


class ParseFrontmatterTests(unittest.TestCase):
    def test_scalar_inline_and_block_lists(self):
        text = ('---\n'
                'title: "Hello"\n'
                'ai-trust: working\n'
                'traces: [ADR-0001, ADR-0002]\n'
                'cites:\n'
                '  - docs/knowledge/sources/a.md\n'
                '  - docs/knowledge/sources/b.md\n'
                '---\n'
                'Body text here.\n')
        meta, body = idoc.parse_frontmatter(text)
        self.assertEqual(meta["title"], "Hello")
        self.assertEqual(meta["ai-trust"], "working")
        self.assertEqual(meta["traces"], ["ADR-0001", "ADR-0002"])
        self.assertEqual(meta["cites"], ["docs/knowledge/sources/a.md",
                                         "docs/knowledge/sources/b.md"])
        self.assertEqual(body.strip(), "Body text here.")

    def test_no_frontmatter(self):
        meta, body = idoc.parse_frontmatter("# Just a heading\n")
        self.assertEqual(meta, {})
        self.assertTrue(body.startswith("# Just"))

    def test_malformed_frontmatter_tolerated(self):
        meta, body = idoc.parse_frontmatter("---\nthis is not: : valid\n")  # no closing ---
        self.assertIsInstance(meta, dict)  # must not raise


class IngestRootTests(unittest.TestCase):
    def _write(self, p, text):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def test_adr_story_source_and_edges(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self._write(base / "docs/architecture/decisions/ADR-0001-x.md",
                        "---\ntitle: \"ADR-0001\"\nai-trust: working\n---\nDecision body.\n")
            self._write(base / "docs/product/stories/AS-0001-x.md",
                        "---\ntitle: \"Story\"\ntraces: [ADR-0001]\n---\nAs a user.\n")
            self._write(base / "docs/knowledge/sources/a.md",
                        "---\ntitle: \"Src\"\nai-trust: authoritative\n---\nSource text.\n")
            nodes, edges = idoc.ingest_root(base / "docs", "docs", base)
            by_id = {n["id"]: n for n in nodes}
            self.assertIn("adr:ADR-0001", by_id)
            self.assertEqual(by_id["adr:ADR-0001"]["kind"], "adr")
            self.assertIn("story:AS-0001", by_id)
            self.assertEqual(by_id["story:AS-0001"]["kind"], "story")
            src = [n for n in nodes if n["kind"] == "source"][0]
            self.assertEqual(src["tier"], "authoritative")
            trace_edges = [e for e in edges if e["kind"] == "traces"]
            self.assertEqual(len(trace_edges), 1)
            self.assertEqual(trace_edges[0]["src"], "story:AS-0001")
            self.assertEqual(trace_edges[0]["dst"], "adr:ADR-0001")
            self.assertEqual(trace_edges[0]["source_file"],
                             "docs/product/stories/AS-0001-x.md")

    def test_skips_dot_directories(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self._write(base / "docs/.knowledge/graph.db.md", "---\ntitle: x\n---\n")
            self._write(base / "docs/real.md", "---\ntitle: real\n---\nbody\n")
            nodes, _ = idoc.ingest_root(base / "docs", "docs", base)
            paths = {n["path"] for n in nodes}
            self.assertIn("docs/real.md", paths)
            self.assertNotIn("docs/.knowledge/graph.db.md", paths)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/knowledge/tests/test_ingest_docs.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingest_docs'`.

- [ ] **Step 3: Write the module**

```python
# scripts/knowledge/ingest_docs.py
#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Docs ingester: frontmatter + link convention -> nodes/edges. Stdlib only
(no pyyaml): a small frontmatter parser handles scalars, inline [a, b] lists,
and block '- item' lists."""
from __future__ import annotations

import re
from pathlib import Path

from graph_store import adr_id, story_id, doc_id, source_id, normalize_ref

LINK_FIELDS = ("implements", "traces", "cites", "supersedes", "covers")
_ADR_FILE_RE = re.compile(r"(ADR-\d{3,4})")
_STORY_FILE_RE = re.compile(r"(AS-\d+)", re.I)


def parse_frontmatter(text: str):
    """Return (meta, body). Tolerant: no/again-unterminated frontmatter -> ({}, text)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = text[3:end].strip("\n")
    body = text[end + 4:]
    meta: dict = {}
    key = None
    for raw in fm.splitlines():
        if not raw.strip():
            continue
        if raw.lstrip().startswith("- ") and key is not None:
            meta.setdefault(key, [])
            if isinstance(meta[key], list):
                meta[key].append(raw.lstrip()[2:].strip().strip('"\''))
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", raw)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val == "":
            meta[key] = []  # a block list may follow
        elif val.startswith("[") and val.endswith("]"):
            meta[key] = [x.strip().strip('"\'') for x in val[1:-1].split(",") if x.strip()]
        else:
            meta[key] = val.strip('"\'')
    return meta, body


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def classify(rel_path: str, meta: dict):
    """Return (kind, ident). ident is the ADR/story id string, else None."""
    name = Path(rel_path).name
    rp = rel_path.replace("\\", "/")
    if "architecture/decisions/" in rp:
        m = _ADR_FILE_RE.search(name)
        if m:
            return "adr", m.group(1)
    if "product/stories/" in rp or _STORY_FILE_RE.match(name):
        m = _STORY_FILE_RE.search(name)
        if m:
            return "story", m.group(1).upper()
    if "knowledge/sources/" in rp:
        return "source", None
    return "doc", None


def ingest_root(root: Path, namespace: str, base: Path):
    nodes, edges = [], []
    root = Path(root)
    base = Path(base)
    for f in sorted(root.rglob("*.md")):
        rel = f.relative_to(base)
        if any(part.startswith(".") for part in rel.parts):
            continue  # skip dot-directories (derived .knowledge/, etc.)
        rels = str(rel).replace("\\", "/")
        text = f.read_text(encoding="utf-8", errors="replace")
        try:
            meta, body = parse_frontmatter(text)
        except Exception:
            meta, body = {}, text
        kind, ident = classify(rels, meta)
        if kind == "adr":
            nid = adr_id(ident)
        elif kind == "story":
            nid = story_id(ident)
        elif kind == "source":
            nid = source_id(namespace, rels)
        else:
            nid = doc_id(namespace, rels)
        nodes.append({"id": nid, "kind": kind, "subtype": None,
                      "name": meta.get("title") or f.name, "path": rels,
                      "tier": meta.get("ai-trust"),
                      "text": " ".join(body.split())[:800],
                      "meta": meta, "namespace": namespace})
        for field in LINK_FIELDS:
            for ref in _as_list(meta.get(field)):
                edges.append({"src": nid, "dst": normalize_ref(str(ref)),
                              "kind": field, "source_file": rels, "line": None,
                              "resolved": None, "namespace": namespace})
    return nodes, edges
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/scripts/knowledge/tests/test_ingest_docs.py`
Expected: `OK` (5 tests).

- [ ] **Step 5: Commit**

```bash
git add template/scripts/knowledge/ingest_docs.py template/scripts/knowledge/tests/test_ingest_docs.py
git commit -m "feat: docs ingester (frontmatter -> traceability edges)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: ingest_code.py — ast/regex nodes, markers, covers

**Files:**
- Create: `scripts/knowledge/ingest_code.py`
- Test: `scripts/knowledge/tests/test_ingest_code.py`

**Interfaces:**
- Consumes: `graph_store` id helpers.
- Produces: `ingest_root(root:Path, namespace:str, base:Path)->(nodes, edges)`. Emits `code-file`/`test`/`symbol` nodes; `contains` (file→symbol, resolved=1); `imports` (code→code, resolved=1, intra-namespace only — external/stdlib imports dropped); `implements` (file→adr and symbol→adr from `# ADR-NNNN` markers, resolved left None for the resolve pass); `covers` (test→code by naming, resolved=1, only when the target file exists).

- [ ] **Step 1: Write the failing test**

```python
# scripts/knowledge/tests/test_ingest_code.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tempfile, unittest
import ingest_code as icode


class IngestCodeTests(unittest.TestCase):
    def _write(self, p, text):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def test_ast_symbols_imports_marker(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self._write(base / "src/foo.py",
                        "# ADR-0001\nimport src.util\n\n"
                        "class Foo:\n    def bar(self):\n        return 1\n")
            self._write(base / "src/util.py", "def helper():\n    return 2\n")
            nodes, edges = icode.ingest_root(base / "src", "kit", base)
            ids = {n["id"] for n in nodes}
            self.assertIn("code:kit:src/foo.py", ids)
            self.assertIn("sym:kit:src/foo.py:Foo", ids)
            self.assertIn("sym:kit:src/foo.py:bar", ids)
            kinds = {(e["src"], e["dst"]): e["kind"] for e in edges}
            self.assertEqual(kinds[("code:kit:src/foo.py", "sym:kit:src/foo.py:Foo")],
                             "contains")
            # marker -> file-level implements to ADR
            impl = [e for e in edges if e["kind"] == "implements"
                    and e["src"] == "code:kit:src/foo.py"]
            self.assertTrue(any(e["dst"] == "adr:ADR-0001" for e in impl))
            self.assertTrue(all(e["line"] for e in impl))  # carries a citation line
            # intra-namespace import resolved to the util file
            imports = [e for e in edges if e["kind"] == "imports"]
            self.assertTrue(any(e["dst"] == "code:kit:src/util.py" for e in imports))

    def test_test_naming_covers(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self._write(base / "pkg/thing.py", "def go():\n    return 1\n")
            self._write(base / "pkg/tests/test_thing.py", "def test_go():\n    assert True\n")
            nodes, edges = icode.ingest_root(base / "pkg", "kit", base)
            test_nodes = [n for n in nodes if n["kind"] == "test"]
            self.assertEqual(test_nodes[0]["id"], "test:kit:pkg/tests/test_thing.py")
            covers = [e for e in edges if e["kind"] == "covers"]
            self.assertEqual(covers[0]["src"], "test:kit:pkg/tests/test_thing.py")
            self.assertEqual(covers[0]["dst"], "code:kit:pkg/thing.py")

    def test_non_python_regex_and_skips(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self._write(base / "s/run.sh", "#!/bin/sh\n# ADR-0002\nrun() { echo hi; }\n")
            self._write(base / "s/__pycache__/x.py", "def ghost():\n    return 0\n")
            nodes, edges = icode.ingest_root(base / "s", "kit", base)
            ids = {n["id"] for n in nodes}
            self.assertIn("code:kit:s/run.sh", ids)
            self.assertNotIn("code:kit:s/__pycache__/x.py", ids)  # skipped
            self.assertTrue(any(e["kind"] == "implements" and e["dst"] == "adr:ADR-0002"
                                for e in edges))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/knowledge/tests/test_ingest_code.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingest_code'`.

- [ ] **Step 3: Write the module**

```python
# scripts/knowledge/ingest_code.py
#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Code ingester: Python `ast` (+ shallow regex for other languages), `# ADR-NNNN`
markers, and test<->code naming. Returns (nodes, edges) with intra-namespace
imports/covers resolved in-pass; implements edges (to ADRs) are left for the
orchestrator's resolve pass."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from graph_store import adr_id, code_id, symbol_id, test_id

CODE_SUFFIXES = {".py", ".js", ".ts", ".sh", ".go", ".rb", ".java", ".rs"}
SKIP_DIRS = {"__pycache__", "node_modules", ".git"}
_ADR_MARKER_RE = re.compile(r"ADR-\d{3,4}")
_TEST_NAME_RE = re.compile(r"^(?:test_(.+)|(.+)_test)\.py$")
_DEF_RE = re.compile(
    r"^\s*(?:def|class|func|function|public|private|protected|const|let|var)\s+([A-Za-z_]\w*)")


def _is_test(name: str) -> bool:
    return bool(_TEST_NAME_RE.match(name))


def _markers(text: str):
    """Yield (adr_str, line_number) for each ADR marker occurrence."""
    for m in _ADR_MARKER_RE.finditer(text):
        yield m.group(0), text.count("\n", 0, m.start()) + 1


def _py_symbols(text: str):
    """Yield (name, subtype, lineno, end_lineno) for top-level+nested defs/classes."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield n.name, "function", n.lineno, getattr(n, "end_lineno", n.lineno)
        elif isinstance(n, ast.ClassDef):
            yield n.name, "class", n.lineno, getattr(n, "end_lineno", n.lineno)


def _py_import_modules(text: str):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                yield a.name, n.lineno
        elif isinstance(n, ast.ImportFrom) and n.module:
            yield n.module, n.lineno


def ingest_root(root: Path, namespace: str, base: Path):
    root, base = Path(root), Path(base)
    nodes, edges = [], []
    file_index = {}          # rels -> node_id (code-file/test) for import + covers resolution
    raw_imports = []         # (src_id, module, line)
    covers_pending = []      # (test_id, stem, parent_rels)

    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in CODE_SUFFIXES:
            continue
        rel = f.relative_to(base)
        if any(p.startswith(".") or p in SKIP_DIRS for p in rel.parts):
            continue
        rels = str(rel).replace("\\", "/")
        text = f.read_text(encoding="utf-8", errors="replace")
        is_test = _is_test(f.name)
        nid = test_id(namespace, rels) if is_test else code_id(namespace, rels)
        file_index[rels] = nid
        nodes.append({"id": nid, "kind": "test" if is_test else "code-file",
                      "subtype": None, "name": f.name, "path": rels, "tier": None,
                      "text": None, "meta": {}, "namespace": namespace})

        symbol_ranges = []
        if f.suffix.lower() == ".py":
            for name, sub, lineno, end in _py_symbols(text):
                sid = symbol_id(namespace, rels, name)
                nodes.append({"id": sid, "kind": "symbol", "subtype": sub,
                              "name": name, "path": rels, "tier": None, "text": None,
                              "meta": {"lineno": lineno}, "namespace": namespace})
                edges.append({"src": nid, "dst": sid, "kind": "contains",
                              "source_file": rels, "line": lineno, "resolved": 1,
                              "namespace": namespace})
                symbol_ranges.append((sid, lineno, end))
            for mod, line in _py_import_modules(text):
                raw_imports.append((nid, mod, line))
        else:
            for m in _DEF_RE.finditer(text):
                # shallow: record a symbol per def-like line
                name = m.group(1)
                line = text.count("\n", 0, m.start()) + 1
                sid = symbol_id(namespace, rels, name)
                nodes.append({"id": sid, "kind": "symbol", "subtype": "function",
                              "name": name, "path": rels, "tier": None, "text": None,
                              "meta": {"lineno": line}, "namespace": namespace})
                edges.append({"src": nid, "dst": sid, "kind": "contains",
                              "source_file": rels, "line": line, "resolved": 1,
                              "namespace": namespace})

        # ADR markers -> file-level implements (+ symbol-level when in range)
        for adr, line in _markers(text):
            edges.append({"src": nid, "dst": adr_id(adr), "kind": "implements",
                          "source_file": rels, "line": line, "resolved": None,
                          "namespace": namespace})
            for sid, lo, hi in symbol_ranges:
                if lo <= line <= hi:
                    edges.append({"src": sid, "dst": adr_id(adr), "kind": "implements",
                                  "source_file": rels, "line": line, "resolved": None,
                                  "namespace": namespace})

        if is_test:
            m = _TEST_NAME_RE.match(f.name)
            stem = m.group(1) or m.group(2)
            covers_pending.append((nid, stem, rel.parent))

    # resolve intra-namespace imports (dotted module -> a file in this root)
    for src_id, mod, line in raw_imports:
        target = mod.replace(".", "/") + ".py"
        match = next((rid for rp, rid in file_index.items() if rp.endswith(target)), None)
        if match and match != src_id:
            edges.append({"src": src_id, "dst": match, "kind": "imports",
                          "source_file": src_id.split(":", 2)[-1], "line": line,
                          "resolved": 1, "namespace": namespace})

    # resolve covers by naming (test_x.py -> x.py near the test)
    for tid, stem, parent in covers_pending:
        cands = [str((parent / f"{stem}.py")).replace("\\", "/"),
                 str((parent.parent / f"{stem}.py")).replace("\\", "/")]
        # parent/parent.parent are relative to base already? they are relative to base
        cands = [c[len(str(base)) + 1:] if c.startswith(str(base)) else c for c in cands]
        target = next((file_index[c] for c in cands if c in file_index), None)
        if target:
            edges.append({"src": tid, "dst": target, "kind": "covers",
                          "source_file": tid.split(":", 2)[-1], "line": None,
                          "resolved": 1, "namespace": namespace})
    return nodes, edges
```

Note on `covers_pending`: `rel.parent` is already relative to `base` (since `rel = f.relative_to(base)`), so the candidate strings are namespace-relative paths that match `file_index` keys directly; the `startswith(str(base))` guard is a no-op safety net. Verify the `test_test_naming_covers` test passes — if the candidate path math is off, print `file_index` keys and `cands` to debug.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/scripts/knowledge/tests/test_ingest_code.py`
Expected: `OK` (3 tests).

- [ ] **Step 5: Commit**

```bash
git add template/scripts/knowledge/ingest_code.py template/scripts/knowledge/tests/test_ingest_code.py
git commit -m "feat: code ingester (ast/regex, ADR markers, test-covers)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: link_commits.py — optional commit→code attribution

**Files:**
- Create: `scripts/knowledge/link_commits.py`
- Test: `scripts/knowledge/tests/test_link_commits.py`

**Interfaces:**
- Consumes: `graph_store.commit_id`; Phase 3's `commits` table (columns `sha`, `klass`); `git show --numstat`.
- Produces: `link(namespace:str, code_nodes:list[dict], dashboard_db, base)->(nodes, edges, attribution:dict)`. Returns `([], [], {})` when the DB or the `commits` table is absent. `attribution` maps a code-file node id → `{"ai_commits","human_commits","mixed_commits"}` counts (`ai` and `ai-assisted` both count as ai). Edges are `touches` (commit→code-file, resolved=1).

- [ ] **Step 1: Write the failing test**

```python
# scripts/knowledge/tests/test_link_commits.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sqlite3, subprocess, tempfile, unittest
import link_commits as lc


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


class LinkCommitsTests(unittest.TestCase):
    def test_absent_db_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            out = lc.link("kit", [], Path(d) / "nope.db", Path(d))
            self.assertEqual(out, ([], [], {}))

    def test_touches_and_attribution(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            _git(base, "init", "-q")
            _git(base, "config", "user.email", "a@b.c")
            _git(base, "config", "user.name", "T")
            (base / "foo.py").write_text("x = 1\n")
            _git(base, "add", "-A"); _git(base, "commit", "-q", "-m", "add foo")
            sha = _git(base, "rev-parse", "HEAD").stdout.strip()
            db = base / "dash.db"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE commits (sha TEXT, klass TEXT)")
            con.execute("INSERT INTO commits VALUES (?, 'ai')", (sha,))
            con.commit(); con.close()
            code_nodes = [{"id": "code:kit:foo.py", "path": "foo.py"}]
            nodes, edges, attrib = lc.link("kit", code_nodes, db, base)
            self.assertEqual(len(nodes), 1)
            self.assertEqual(nodes[0]["kind"], "commit")
            self.assertEqual(edges[0]["kind"], "touches")
            self.assertEqual(edges[0]["dst"], "code:kit:foo.py")
            self.assertEqual(attrib["code:kit:foo.py"]["ai_commits"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/knowledge/tests/test_link_commits.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'link_commits'`.

- [ ] **Step 3: Write the module**

```python
# scripts/knowledge/link_commits.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/scripts/knowledge/tests/test_link_commits.py`
Expected: `OK` (2 tests).

- [ ] **Step 5: Commit**

```bash
git add template/scripts/knowledge/link_commits.py template/scripts/knowledge/tests/test_link_commits.py
git commit -m "feat: optional commit->code linkage (activates on Phase 3 DB)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: query.py — scoped/federated reads, search, trace

**Files:**
- Create: `scripts/knowledge/query.py`
- Test: `scripts/knowledge/tests/test_query.py`

**Interfaces:**
- Consumes: `manifest`, `graph_store` (fixtures build DBs directly).
- Produces: `class KG` (holds `conn`, `aliases`; `.nodes_sql()`, `.edges_sql()`), `open_scoped(namespace, data=None, base=None)->KG`, `open_federated(data=None, base=None)->KG`, `get_node(kg, id)->dict|None`, `search(kg, q, k=5)->list[dict]`, `neighbors(kg, id)->list[dict]`, `trace(kg, id, max_depth=4)->{"root","nodes","edges"}`. Node/edge dicts include `namespace`, `path`/`source_file`, `line`, `tier` for citation.

- [ ] **Step 1: Write the failing test**

```python
# scripts/knowledge/tests/test_query.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json, tempfile, unittest
import graph_store as gs
import query as q


def _build_fixture(base):
    """Two namespace DBs (docs, kit) + an overlay with the cross-ns implements edge."""
    data = {"namespaces": {
                "docs": {"kind": "docs", "db": "docs/.knowledge/graph.db", "roots": ["docs/"]},
                "kit":  {"kind": "code", "db": ".knowledge/graph.db", "roots": ["src/"]}},
            "overlay": "docs/knowledge/.knowledge/global.db"}
    docs_db = base / "docs/.knowledge/graph.db"
    kit_db = base / ".knowledge/graph.db"
    ov_db = base / "docs/knowledge/.knowledge/global.db"
    dc = gs.connect(docs_db)
    gs.add_node(dc, {"id": "adr:ADR-0001", "kind": "adr", "name": "Adopt graph",
                     "path": "docs/architecture/decisions/ADR-0001.md",
                     "text": "knowledge graph decision", "namespace": "docs"})
    gs.add_node(dc, {"id": "story:AS-0001", "kind": "story", "name": "Story",
                     "path": "docs/product/stories/AS-0001.md", "namespace": "docs"})
    gs.add_edge(dc, {"src": "story:AS-0001", "dst": "adr:ADR-0001", "kind": "traces",
                     "source_file": "docs/product/stories/AS-0001.md", "namespace": "docs"})
    dc.commit(); dc.close()
    kc = gs.connect(kit_db)
    gs.add_node(kc, {"id": "code:kit:src/graph_store.py", "kind": "code-file",
                     "name": "graph_store.py", "path": "src/graph_store.py", "namespace": "kit"})
    gs.add_node(kc, {"id": "test:kit:src/test_graph_store.py", "kind": "test",
                     "name": "test_graph_store.py", "path": "src/test_graph_store.py",
                     "namespace": "kit"})
    gs.add_edge(kc, {"src": "test:kit:src/test_graph_store.py",
                     "dst": "code:kit:src/graph_store.py", "kind": "covers",
                     "source_file": "src/test_graph_store.py", "namespace": "kit"})
    kc.commit(); kc.close()
    oc = gs.connect(ov_db)
    gs.add_edge(oc, {"src": "code:kit:src/graph_store.py", "dst": "adr:ADR-0001",
                     "kind": "implements", "source_file": "src/graph_store.py",
                     "line": 2, "resolved": 1, "namespace": "global"})
    oc.commit(); oc.close()
    return data


class QueryTests(unittest.TestCase):
    def test_scoped_vs_federated_visibility(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _build_fixture(base)
            kg = q.open_scoped("kit", data=data, base=base)
            self.assertIsNone(q.get_node(kg, "adr:ADR-0001"))  # docs ns not attached
            self.assertIsNotNone(q.get_node(kg, "code:kit:src/graph_store.py"))
            fed = q.open_federated(data=data, base=base)
            self.assertIsNotNone(q.get_node(fed, "adr:ADR-0001"))

    def test_search_matches_text(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _build_fixture(base)
            fed = q.open_federated(data=data, base=base)
            hits = q.search(fed, "knowledge graph decision")
            self.assertTrue(any(h["id"] == "adr:ADR-0001" for h in hits))

    def test_trace_assembles_chain_with_citations(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _build_fixture(base)
            fed = q.open_federated(data=data, base=base)
            res = q.trace(fed, "adr:ADR-0001")
            node_ids = {n["id"] for n in res["nodes"]}
            self.assertIn("code:kit:src/graph_store.py", node_ids)   # implements
            self.assertIn("test:kit:src/test_graph_store.py", node_ids)  # covers
            self.assertIn("story:AS-0001", node_ids)                 # traces
            impl = [e for e in res["edges"] if e["kind"] == "implements"][0]
            self.assertEqual(impl["source_file"], "src/graph_store.py")
            self.assertEqual(impl["line"], 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/knowledge/tests/test_query.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'query'`.

- [ ] **Step 3: Write the module**

```python
# scripts/knowledge/query.py
#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Read-only query engine: scoped (one namespace) or federated (ATTACH all),
content search, and trace() to assemble the ADR<->code<->test<->story chain."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import manifest as manifest_mod

_NODE_COLS = "id,kind,subtype,name,path,tier,text,meta,namespace"
_EDGE_COLS = "src,dst,kind,source_file,line,resolved,namespace"


class KG:
    def __init__(self, conn, aliases):
        self.conn = conn
        self.aliases = aliases

    def nodes_sql(self):
        return " UNION ALL ".join(f"SELECT {_NODE_COLS} FROM {a}.nodes" for a in self.aliases)

    def edges_sql(self):
        return " UNION ALL ".join(f"SELECT {_EDGE_COLS} FROM {a}.edges" for a in self.aliases)


def _alias(name):
    return "ns_" + re.sub(r"\W", "_", name)


def _open(pairs):
    """pairs: list of (alias, db_path). Returns a KG over attached DBs (ro)."""
    conn = sqlite3.connect(":memory:")
    aliases = []
    for alias, db in pairs:
        if Path(db).exists():
            conn.execute(f"ATTACH DATABASE ? AS {alias}", (str(db),))
            aliases.append(alias)
    conn.execute("PRAGMA query_only=ON")
    return KG(conn, aliases)


def open_scoped(namespace, data=None, base=None):
    data = data or manifest_mod.load()
    base = base or manifest_mod.REPO_ROOT
    pairs = []
    for name, kind, db, roots in manifest_mod.namespaces(data, base=base):
        if name == namespace:
            pairs.append((_alias(name), db))
    pairs.append(("overlay", manifest_mod.overlay_db(data, base=base)))
    return _open(pairs)


def open_federated(data=None, base=None):
    data = data or manifest_mod.load()
    base = base or manifest_mod.REPO_ROOT
    pairs = [(_alias(name), db)
             for name, kind, db, roots in manifest_mod.namespaces(data, base=base)]
    pairs.append(("overlay", manifest_mod.overlay_db(data, base=base)))
    return _open(pairs)


def _node(row):
    d = dict(zip(_NODE_COLS.split(","), row))
    try:
        d["meta"] = json.loads(d["meta"]) if d["meta"] else {}
    except (ValueError, TypeError):
        d["meta"] = {}
    return d


def _edge(row):
    return dict(zip(_EDGE_COLS.split(","), row))


def get_node(kg, node_id):
    if not kg.aliases:
        return None
    row = kg.conn.execute(
        f"SELECT {_NODE_COLS} FROM ({kg.nodes_sql()}) WHERE id=? LIMIT 1",
        (node_id,)).fetchone()
    return _node(row) if row else None


def search(kg, q, k=5):
    if not kg.aliases:
        return []
    terms = [t for t in re.findall(r"\w+", q.lower()) if len(t) > 2]
    scored = []
    for row in kg.conn.execute(f"SELECT {_NODE_COLS} FROM ({kg.nodes_sql()})"):
        n = _node(row)
        hay = ((n["name"] or "") + " " + (n["text"] or "")).lower()
        score = sum(hay.count(t) for t in terms)
        if score:
            scored.append((score, n))
    scored.sort(key=lambda x: -x[0])
    return [n for _, n in scored[:k]]


def neighbors(kg, node_id):
    if not kg.aliases:
        return []
    rows = kg.conn.execute(
        f"SELECT {_EDGE_COLS} FROM ({kg.edges_sql()}) WHERE src=? OR dst=?",
        (node_id, node_id)).fetchall()
    return [_edge(r) for r in rows]


def trace(kg, node_id, max_depth=4):
    seen = {node_id}
    frontier = [node_id]
    chain, chain_keys = [], set()
    depth = 0
    while frontier and depth < max_depth and kg.aliases:
        ph = ",".join("?" * len(frontier))
        rows = kg.conn.execute(
            f"SELECT {_EDGE_COLS} FROM ({kg.edges_sql()}) "
            f"WHERE src IN ({ph}) OR dst IN ({ph})", frontier * 2).fetchall()
        nxt = []
        for r in rows:
            e = _edge(r)
            key = (e["src"], e["dst"], e["kind"])
            if key in chain_keys:
                continue
            chain_keys.add(key)
            chain.append(e)
            for endpoint in (e["src"], e["dst"]):
                if endpoint not in seen:
                    seen.add(endpoint)
                    nxt.append(endpoint)
        frontier = nxt
        depth += 1
    nodes = [n for n in (get_node(kg, nid) for nid in seen) if n]
    return {"root": node_id, "nodes": nodes, "edges": chain}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/scripts/knowledge/tests/test_query.py`
Expected: `OK` (3 tests).

- [ ] **Step 5: Commit**

```bash
git add template/scripts/knowledge/query.py template/scripts/knowledge/tests/test_query.py
git commit -m "feat: knowledge-graph query engine (scoped/federated/trace)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: ingest.py — rewritten orchestrator + CLI

**Files:**
- Modify (full rewrite): `scripts/knowledge/ingest.py`
- Test: `scripts/knowledge/tests/test_ingest.py`

**Interfaces:**
- Consumes: `manifest`, `graph_store`, `ingest_docs`, `ingest_code`, `link_commits`, `query`.
- Produces: `build(data=None, base=None)->dict` (stats), `main()`. CLI: `--build`, `--stats`, `--query TEXT`, `--trace ID`, `--scope NS`, `--federated`.
- Build algorithm: for each namespace, clear its DB, run the kind's ingester over its roots, run the optional commit layer (code namespaces), merge attribution into code-file node meta, write nodes; write intra-namespace edges (both endpoints local) to the namespace DB with `resolved=1`, hold the rest; then a **resolve pass** writes held edges to the overlay — rewriting `path:<p>` targets to a node with a matching path and setting `resolved` = 1 iff both endpoints exist across all namespaces.

- [ ] **Step 1: Write the failing test**

```python
# scripts/knowledge/tests/test_ingest.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json, tempfile, unittest
import ingest, query as q


def _fixture_repo(base):
    (base / "docs/architecture/decisions").mkdir(parents=True)
    (base / "docs/product/stories").mkdir(parents=True)
    (base / "src/tests").mkdir(parents=True)
    (base / "docs/architecture/decisions/ADR-0001-x.md").write_text(
        '---\ntitle: "ADR-0001"\nai-trust: working\n---\nDecision.\n', encoding="utf-8")
    (base / "docs/product/stories/AS-0001-x.md").write_text(
        '---\ntitle: "Story"\ntraces: [ADR-0001]\n---\nAs a user.\n', encoding="utf-8")
    (base / "src/thing.py").write_text("# ADR-0001\ndef go():\n    return 1\n", encoding="utf-8")
    (base / "src/tests/test_thing.py").write_text(
        "def test_go():\n    assert True\n", encoding="utf-8")
    data = {"namespaces": {
                "docs": {"kind": "docs", "db": "docs/.knowledge/graph.db", "roots": ["docs/"]},
                "kit":  {"kind": "code", "db": ".knowledge/graph.db", "roots": ["src/"]}},
            "overlay": "docs/knowledge/.knowledge/global.db"}
    return data


class IngestBuildTests(unittest.TestCase):
    def test_build_and_federated_trace(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _fixture_repo(base)
            stats = ingest.build(data=data, base=base)
            self.assertTrue(stats["namespaces"])
            fed = q.open_federated(data=data, base=base)
            res = q.trace(fed, "adr:ADR-0001")
            ids = {n["id"] for n in res["nodes"]}
            self.assertIn("code:kit:src/thing.py", ids)          # implements (overlay)
            self.assertIn("test:kit:src/tests/test_thing.py", ids)  # covers
            self.assertIn("story:AS-0001", ids)                  # traces
            impl = [e for e in res["edges"]
                    if e["kind"] == "implements" and e["dst"] == "adr:ADR-0001"]
            self.assertTrue(impl and impl[0]["resolved"] == 1)

    def test_build_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _fixture_repo(base)
            s1 = ingest.build(data=data, base=base)
            s2 = ingest.build(data=data, base=base)
            self.assertEqual(s1, s2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/knowledge/tests/test_ingest.py`
Expected: FAIL — `AttributeError: module 'ingest' has no attribute 'build'` (the old stub has no `build(data=...)`).

- [ ] **Step 3: Rewrite the module**

```python
# scripts/knowledge/ingest.py
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
                all_paths.setdefault(nd["path"], nd["id"])
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
    if a.query:
        print(json.dumps(query_mod.search(kg, a.query), indent=2))
    else:
        print(json.dumps(query_mod.trace(kg, a.trace), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/scripts/knowledge/tests/test_ingest.py`
Expected: `OK` (2 tests).

- [ ] **Step 5: Commit**

```bash
git add template/scripts/knowledge/ingest.py template/scripts/knowledge/tests/test_ingest.py
git commit -m "feat: knowledge-graph orchestrator + CLI (replaces keyword stub)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: mcp_server.py — stdlib stdio JSON-RPC

**Files:**
- Create: `scripts/knowledge/mcp_server.py`
- Test: `scripts/knowledge/tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `query`.
- Produces: `handle(msg:dict)->dict|None`, `call_tool(name, args)->dict`, `serve(stdin, stdout)`, constants `PROTOCOL_VERSION`, `TOOLS`. Newline-delimited JSON-RPC 2.0. `initialize` → protocolVersion + serverInfo + `capabilities.tools`; `notifications/initialized` → None (no reply); `tools/list` → the three tools; `tools/call` → dispatch; unknown method → JSON-RPC error `-32601`. Tools: `kg_query{scope,query,k?}`, `kg_federated_query{query,k?}`, `kg_trace{id,scope?}`.

- [ ] **Step 1: Write the failing test**

```python
# scripts/knowledge/tests/test_mcp_server.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import io, json, unittest
import mcp_server as srv


class McpProtocolTests(unittest.TestCase):
    def test_initialize(self):
        r = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(r["result"]["protocolVersion"], srv.PROTOCOL_VERSION)
        self.assertIn("tools", r["result"]["capabilities"])
        self.assertIn("serverInfo", r["result"])

    def test_tools_list_has_three(self):
        r = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in r["result"]["tools"]}
        self.assertEqual(names, {"kg_query", "kg_federated_query", "kg_trace"})

    def test_notification_no_reply(self):
        self.assertIsNone(srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_unknown_method_errors(self):
        r = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "no/such"})
        self.assertEqual(r["error"]["code"], -32601)

    def test_serve_survives_bad_json_and_replies(self):
        stdin = io.StringIO("not json\n"
                            + json.dumps({"jsonrpc": "2.0", "id": 9, "method": "tools/list"}) + "\n")
        stdout = io.StringIO()
        srv.serve(stdin=stdin, stdout=stdout)
        lines = [l for l in stdout.getvalue().splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)  # bad line skipped, one valid reply
        self.assertEqual(json.loads(lines[0])["id"], 9)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/knowledge/tests/test_mcp_server.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_server'`.

- [ ] **Step 3: Write the module**

```python
# scripts/knowledge/mcp_server.py
#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Thin stdlib stdio MCP server exposing the knowledge graph (no SDK).

Newline-delimited JSON-RPC 2.0. Tools: kg_query (scoped), kg_federated_query,
kg_trace. Degrades gracefully when the graph is unbuilt (empty results)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import query as query_mod  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
TOOLS = [
    {"name": "kg_query",
     "description": "Scoped content search within one namespace.",
     "inputSchema": {"type": "object",
                     "properties": {"scope": {"type": "string"},
                                    "query": {"type": "string"},
                                    "k": {"type": "integer"}},
                     "required": ["scope", "query"]}},
    {"name": "kg_federated_query",
     "description": "Content search across all namespaces.",
     "inputSchema": {"type": "object",
                     "properties": {"query": {"type": "string"},
                                    "k": {"type": "integer"}},
                     "required": ["query"]}},
    {"name": "kg_trace",
     "description": "Trace the ADR<->code<->test<->story chain for a node id.",
     "inputSchema": {"type": "object",
                     "properties": {"id": {"type": "string"},
                                    "scope": {"type": "string"}},
                     "required": ["id"]}},
]


def _text(obj):
    return {"content": [{"type": "text", "text": json.dumps(obj, indent=2)}]}


def call_tool(name, args):
    if name == "kg_query":
        kg = query_mod.open_scoped(args["scope"])
        return _text(query_mod.search(kg, args["query"], args.get("k", 5)))
    if name == "kg_federated_query":
        kg = query_mod.open_federated()
        return _text(query_mod.search(kg, args["query"], args.get("k", 5)))
    if name == "kg_trace":
        kg = query_mod.open_scoped(args["scope"]) if args.get("scope") else query_mod.open_federated()
        return _text(query_mod.trace(kg, args["id"]))
    raise KeyError(name)


def handle(msg):
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ai-sdlc-knowledge", "version": "1.0.0"}}}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        try:
            res = call_tool(params.get("name"), params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": mid, "result": res}
        except Exception as ex:  # never crash the loop; surface as tool error
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": f"error: {ex}"}], "isError": True}}
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(msg)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()


if __name__ == "__main__":
    serve()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/scripts/knowledge/tests/test_mcp_server.py`
Expected: `OK` (5 tests).

- [ ] **Step 5: Commit**

```bash
git add template/scripts/knowledge/mcp_server.py template/scripts/knowledge/tests/test_mcp_server.py
git commit -m "feat: stdlib stdio MCP server for the knowledge graph

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: docs, ADR, seed story, MCP slot, AGENTS.md

This task carries no unit test; its deliverable is verified by a real build+trace of the kit's own dogfood chain plus the frontmatter validator. Do all edits, then run the verification block.

**Files:**
- Create: `docs/architecture/decisions/ADR-0001-adopt-knowledge-graph.md`, `docs/product/stories/AS-0001-adopt-knowledge-graph.md`
- Modify (rewrite): `docs/knowledge/schema.md`, `docs/knowledge/README.md`, `.claude/rules/knowledge-sources.md`
- Modify (edit): `.mcp.json`, `AGENTS.md`

- [ ] **Step 1: Create ADR-0001** (match ADR-0000's frontmatter field set)

```markdown
---
title: "ADR-0001 — Adopt a local docs+code knowledge graph"
status: approved
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-07-02
classification: internal
last-reviewed: 2026-07-02
ai-trust: working
---

# ADR-0001 — Adopt a local docs+code knowledge graph

## Status

Accepted — 2026-07-02.

## Context

The kit shipped a keyword stub (`scripts/knowledge/ingest.py`) that chunked
`docs/knowledge/sources/` and did keyword search — docs-only, no structure, no
traceability. Grounding (`AGENTS.md §4.4`) and the QA/Architect traceability
duty need more: a graph over **docs and code**, isolated per repo, queryable
across the whole project, that answers "what implements this ADR, and what
tests cover it?".

## Decision

Adopt a **local, dependency-light knowledge graph**: per-namespace SQLite DBs
(`nodes` + `edges`) plus a shared `global` overlay, federated via `ATTACH`.
Stdlib ingesters read docs (frontmatter) and code (`ast`). Traceability edges
(ADR→code→test→story) come from explicit links — frontmatter fields, `# ADR-NNNN`
code markers, and `test_x ↔ x` naming — each edge citing its source line. A thin
stdlib MCP server exposes scoped/federated query + trace on the `knowledge` slot.
Embeddings, tree-sitter, and hosted stores remain documented upgrade paths.

## Consequences

- Agents ground answers on a structured, citable graph, not a flat keyword index.
- Every AI-authored knowledge module is attributable to this ADR (dogfooded via
  `# ADR-0001` markers), so `trace ADR-0001` returns its own implementation.
- The graph is derived and git-ignored; only sources + the manifest are tracked.
```

- [ ] **Step 2: Create the seed story AS-0001**

```markdown
---
title: "AS-0001 — Ground answers on a project knowledge graph"
status: done
owner: Product
author: AI-SDLC Bootstrap Kit
created: 2026-07-02
classification: internal
ai-trust: working
traces: [ADR-0001]
---

# AS-0001 — Ground answers on a project knowledge graph

**As a** team running the AI-SDLC kit,
**I want** agents to answer from a graph over our docs and code,
**so that** every answer is traceable (ADR→code→test→story) and cited, not guessed.

This is the **seed story** every project gets — it demonstrates the `traces:`
link convention (it traces to `ADR-0001`) and completes the reference
traceability chain. Copy its shape for real stories under `docs/product/stories/`.

## Acceptance

- `ingest.py --federated --trace ADR-0001` returns the implementing code, its
  tests, and this story, each grounded on a source citation.
```

- [ ] **Step 3: Rewrite `docs/knowledge/schema.md`**

```markdown
# Knowledge schema — nodes, edges, and the link convention

The contract the ingesters (`scripts/knowledge/`) and the `knowledge` MCP server
follow. The knowledge layer is a **graph** over docs *and* code, isolated per
namespace and queryable scoped or federated. (This replaces the earlier
chunk/keyword schema; source-document frontmatter is unchanged.)

## Namespaces & the manifest

`docs/knowledge/graph-manifest.json` registers each namespace:

```json
{
  "namespaces": {
    "docs":     { "kind": "docs", "db": "docs/.knowledge/graph.db", "roots": ["docs/"] },
    "kit-code": { "kind": "code", "db": ".knowledge/graph.db",       "roots": ["scripts/", "dashboard/"] }
  },
  "overlay": "docs/knowledge/.knowledge/global.db"
}
```

Each namespace ingests into its own **git-ignored** `.knowledge/graph.db`. A
shared **`global` overlay** holds edges whose endpoints live in different
namespaces (e.g. code that implements a docs ADR) plus unresolved (dangling)
links. Add a repo by adding a namespace entry — no code change.

## Nodes

| kind | id form | source |
|---|---|---|
| `adr` | `adr:ADR-NNNN` | `docs/architecture/decisions/` |
| `story` | `story:AS-N` | `docs/product/stories/` |
| `doc` | `doc:<ns>:<path>` | any other tracked `.md` |
| `source` | `source:<ns>:<path>` | `docs/knowledge/sources/` |
| `code-file` | `code:<ns>:<path>` | tracked code (non-test) |
| `symbol` | `sym:<ns>:<path>:<name>` | `ast`/regex def/class |
| `test` | `test:<ns>:<path>` | `test_*.py` / `*_test.py` |
| `commit` | `commit:<ns>:<sha>` | optional Phase-3 commit layer |

Every node carries `namespace`, `path`, and (for docs) a `tier` from `ai-trust`,
so retrieved context is always citable with its trust tier (`AGENTS.md §4.2`).

## Edges

| kind | from → to | derived from |
|---|---|---|
| `implements` | code/symbol → adr | `# ADR-NNNN` marker; frontmatter `implements:` |
| `covers` | test → code | `test_x ↔ x` naming; frontmatter `covers:` |
| `traces` | story → adr | frontmatter `traces:` |
| `cites` | doc → source | frontmatter `cites:` |
| `supersedes` | adr → adr | frontmatter `supersedes:` |
| `imports` | code → code | `ast`/regex (intra-namespace only) |
| `contains` | code → symbol | `ast`/regex |
| `touches` | commit → code | git numstat (optional) |

Every edge stores `source_file` + `line` (its citation) and `resolved`
(`0` = the target node was not found — surfaced honestly, never invented).

## The link convention

- **Doc frontmatter** (optional lists): `implements:`, `covers:`, `traces:`,
  `cites:`, `supersedes:`. Values are ids (`ADR-0001`, `AS-0001`) or paths.
- **Code marker:** a comment containing `ADR-NNNN` → an `implements` edge (file
  level, plus symbol level when the marker is inside a def).
- **Naming:** `tests/test_x.py` → `covers` the same-namespace `x.py`.

## Source-document frontmatter (unchanged)

Files under `sources/` still carry `title`, `source`, `ai-trust`,
`classification`, `last-reviewed` (see below). The ingester stamps `ai-trust`
onto the `source` node's `tier`.

```yaml
---
title: "Human-readable title"
source: "<origin — URL, system, or 'authored'>"
ai-trust: authoritative | working | exploratory
classification: public | internal | restricted
last-reviewed: YYYY-MM-DD
---
```

## Conventions

- **No secrets, no real personal data.** Sources and the manifest are tracked; the DBs are derived and git-ignored.
- **One topic per source file** where practical.
- This file (`schema.md`) is exempt from the frontmatter contract; source docs still carry it.
```

- [ ] **Step 4: Rewrite `docs/knowledge/README.md`**

```markdown
# Knowledge layer (pillar 5) — a local docs+code graph

The project's **own knowledge** as a graph, so agents **ground** answers on it
instead of guessing (`AGENTS.md §4.4`). It spans **docs and code**, is isolated
per namespace, and answers **traceability** (ADR→code→test→story) as well as
content search.

```
docs/knowledge/
├── README.md              # this file
├── schema.md              # node/edge/link schema
├── graph-manifest.json    # namespace registry (TRACKED)
├── sources/               # ingestable source documents (TRACKED)
└── .knowledge/            # global overlay DB — GIT-IGNORED (derived)
<each namespace root>/.knowledge/graph.db   # per-namespace DB — GIT-IGNORED
```

## Quick start

```bash
# Build every namespace + the overlay
python3 scripts/knowledge/ingest.py --build

# Trace an ADR's chain (federated across docs + code)
python3 scripts/knowledge/ingest.py --federated --trace ADR-0001

# Scope to one namespace
python3 scripts/knowledge/ingest.py --scope kit-code --trace ADR-0001

# Content search + stats
python3 scripts/knowledge/ingest.py --federated --query "knowledge graph"
python3 scripts/knowledge/ingest.py --stats
```

Agents can also reach it over MCP: the `knowledge` server (`.mcp.json`) exposes
`kg_query`, `kg_federated_query`, and `kg_trace`.

## Adding a repo

Add a namespace to `graph-manifest.json` (`kind: code|docs`, its `db` path, and
`roots`), then rebuild. Scoped queries stay isolated to that namespace; federated
queries and the overlay tie repos together through shared `adr:`/`story:` ids.

## Growing it into production (documented, not built)

- **Embeddings / vector search** — swap term-scored `search` for embeddings
  (local model or a provider via the Vercel AI Gateway) + `sqlite-vec`/DuckDB-VSS/LanceDB/pgvector.
- **tree-sitter** — richer multi-language ASTs in `ingest_code.py`.
- **Hosted KG MCP** — point the `knowledge` slot at a managed graph/vector DB;
  this local server is the reference.

## Trust & curation

- Sources carry a frontmatter `ai-trust` tier (`schema.md`); it rides onto every
  `source` node so answers cite their tier (`AGENTS.md §4.2`).
- **Curation is human** (pillar 7). Never ingest secrets or real personal data.
```

- [ ] **Step 5: Rewrite `.claude/rules/knowledge-sources.md`**

```markdown
---
paths:
  - "docs/knowledge/**"
  - "docs/architecture/decisions/**"
  - "docs/product/stories/**"
---
# Knowledge graph & sources

The knowledge layer is a local **docs+code graph** (pillar 5) — see
`docs/knowledge/schema.md` and `README.md`.

- After adding/changing docs, code, or sources, rebuild: `python3 scripts/knowledge/ingest.py --build`.
- **Link convention** (how edges are drawn): frontmatter `implements:`/`covers:`/`traces:`/`cites:`/`supersedes:` (lists of ids/paths); a `# ADR-NNNN` comment in code; `test_x ↔ x` naming. Each edge cites its source line.
- Ground answers on the graph and **cite the source file + trust tier** (`AGENTS.md §4.2`); do not paraphrase Authoritative sources from memory — quote and cite.
- Unresolved links are reported honestly (`resolved=0`); fix the reference or add the missing node rather than inventing one.
- `docs/knowledge/schema.md` is exempt from the frontmatter contract; source docs still carry it.
```

- [ ] **Step 6: Edit `.mcp.json`** — replace the `knowledge` server block:

Old:
```json
    "knowledge": {
      "$note": "Used by: all seats (ingest & query the KG/RAG/vector store — pillar 5). Point at your vector-DB / KG MCP server.",
      "command": "<KNOWLEDGE_MCP_COMMAND>",
      "args": [],
      "$disabled": true
    },
```
New:
```json
    "knowledge": {
      "$note": "Used by: all seats. Local docs+code knowledge graph (pillar 5). Build it: `python3 scripts/knowledge/ingest.py --build`. This server answers scoped/federated queries + traceability (kg_query, kg_federated_query, kg_trace). Fully local — no URL or secret. Swap for a hosted KG/vector-DB MCP if you outgrow it.",
      "command": "python3",
      "args": ["scripts/knowledge/mcp_server.py"]
    },
```

- [ ] **Step 7: Edit `AGENTS.md §4.4`** — replace the section body:

Old:
```
When a question can be answered from the project's own knowledge, **ground on it instead of guessing.** The ingestion stub and schema live under `docs/knowledge/` and `scripts/knowledge/ingest.py`. Cite the source file and its trust tier (§4.2). If the knowledge store is empty or stale, say so rather than inventing an answer.
```
New:
```
When a question can be answered from the project's own knowledge, **ground on it instead of guessing.** A local **docs+code knowledge graph** lives under `docs/knowledge/` and `scripts/knowledge/`: build it with `python3 scripts/knowledge/ingest.py --build`, then query it **scoped** (one repo/docs-tree) or **federated** (whole project) — `ingest.py --trace ADR-0001`, `ingest.py --query "…"`, or the `knowledge` MCP server (`kg_query`/`kg_federated_query`/`kg_trace`). It answers traceability (ADR→code→test→story) and content search, each result **cited** with its source file, line, and trust tier (§4.2). If the graph is empty or stale, say so — unresolved links are reported honestly, never invented.
```

- [ ] **Step 8: Verify the dogfood chain + frontmatter**

```bash
python3 template/scripts/knowledge/ingest.py --build
python3 template/scripts/knowledge/ingest.py --federated --trace ADR-0001
python3 template/scripts/validate-frontmatter.py
```
Expected: `--build` prints per-namespace counts; `--trace ADR-0001` emits JSON whose `nodes` include a `code:kit-code:scripts/knowledge/...` node, a `test:kit-code:...` node, and `story:AS-0001`, with an `implements` edge `resolved: 1`; `validate-frontmatter.py` prints its PASS line. If the validator flags the new ADR/story, add exactly the fields it names (match ADR-0000's field set) and re-run.

- [ ] **Step 9: Commit**

```bash
git add template/docs/knowledge/schema.md template/docs/knowledge/README.md \
  template/docs/architecture/decisions/ADR-0001-adopt-knowledge-graph.md \
  template/docs/product/stories/AS-0001-adopt-knowledge-graph.md \
  template/.claude/rules/knowledge-sources.md template/.mcp.json template/AGENTS.md
git commit -m "docs: graph schema/README, ADR-0001 + seed story, enable knowledge MCP

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: end-to-end test + CI gate wiring

**Files:**
- Create: `scripts/knowledge/tests/test_end_to_end.py`
- Modify: `.gitlab-ci.yml` (repo root), `template/.github/workflows/ai-governance.yml`

**Interfaces:**
- Consumes: `ingest`, `query`, `mcp_server`.
- Produces: a full-stack test (build fixture → graph → MCP `tools/call` → JSON chain).

- [ ] **Step 1: Write the end-to-end test**

```python
# scripts/knowledge/tests/test_end_to_end.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json, tempfile, unittest
import ingest, query as q
import mcp_server


def _fixture(base):
    (base / "docs/architecture/decisions").mkdir(parents=True)
    (base / "docs/product/stories").mkdir(parents=True)
    (base / "src/tests").mkdir(parents=True)
    (base / "docs/architecture/decisions/ADR-0001-x.md").write_text(
        '---\ntitle: "ADR-0001"\nai-trust: working\n---\nDecision.\n', encoding="utf-8")
    (base / "docs/product/stories/AS-0001-x.md").write_text(
        '---\ntitle: "Story"\ntraces: [ADR-0001]\n---\nAs a user.\n', encoding="utf-8")
    (base / "src/thing.py").write_text("# ADR-0001\ndef go():\n    return 1\n", encoding="utf-8")
    (base / "src/tests/test_thing.py").write_text(
        "def test_go():\n    assert True\n", encoding="utf-8")
    return {"namespaces": {
                "docs": {"kind": "docs", "db": "docs/.knowledge/graph.db", "roots": ["docs/"]},
                "kit":  {"kind": "code", "db": ".knowledge/graph.db", "roots": ["src/"]}},
            "overlay": "docs/knowledge/.knowledge/global.db"}


class EndToEndTests(unittest.TestCase):
    def test_build_query_via_mcp_tool_call(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            data = _fixture(base)
            ingest.build(data=data, base=base)
            # route the MCP server's federated open at our fixture graph
            orig = mcp_server.query_mod.open_federated
            mcp_server.query_mod.open_federated = (
                lambda data=None, base=None: q.open_federated(data=_DATA, base=_BASE))
            global _DATA, _BASE
            _DATA, _BASE = data, base
            try:
                req = {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                       "params": {"name": "kg_trace", "arguments": {"id": "adr:ADR-0001"}}}
                resp = mcp_server.handle(req)
                payload = json.loads(resp["result"]["content"][0]["text"])
            finally:
                mcp_server.query_mod.open_federated = orig
            ids = {n["id"] for n in payload["nodes"]}
            self.assertIn("code:kit:src/thing.py", ids)
            self.assertIn("test:kit:src/tests/test_thing.py", ids)
            self.assertIn("story:AS-0001", ids)
            impl = [e for e in payload["edges"]
                    if e["kind"] == "implements" and e["dst"] == "adr:ADR-0001"]
            self.assertTrue(impl and impl[0]["resolved"] == 1)
            self.assertEqual(impl[0]["source_file"], "src/thing.py")  # citation present


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to verify it passes**

Run: `python3 template/scripts/knowledge/tests/test_end_to_end.py`
Expected: `OK` (1 test). (If it fails on node ids, the earlier tasks' resolve/covers wiring is the cause — fix there, not here.)

- [ ] **Step 3: Wire the knowledge suite into `.gitlab-ci.yml`**

In the root `.gitlab-ci.yml`, add `git` to `before_script` (the `python:3.12-slim` image lacks it, and `test_link_commits`/`test_end_to_end` fixtures need it), and replace the two-line ingest smoke (the `echo "Knowledge ingest smoke test…"` + `ingest.py --build` lines) with the block below:

`before_script` becomes:
```yaml
  before_script:
  - apt-get update -qq && apt-get install -y -qq --no-install-recommends git
  - pip install --quiet "pyyaml>=6"
```
Replacement `script` tail:
```yaml
  - echo "Running knowledge-graph unit tests…"
  - python3 template/scripts/knowledge/tests/test_graph_store.py
  - python3 template/scripts/knowledge/tests/test_manifest.py
  - python3 template/scripts/knowledge/tests/test_ingest_docs.py
  - python3 template/scripts/knowledge/tests/test_ingest_code.py
  - python3 template/scripts/knowledge/tests/test_link_commits.py
  - python3 template/scripts/knowledge/tests/test_query.py
  - python3 template/scripts/knowledge/tests/test_ingest.py
  - python3 template/scripts/knowledge/tests/test_mcp_server.py
  - python3 template/scripts/knowledge/tests/test_end_to_end.py
  - echo "Knowledge graph build + traceability smoke…"
  - python3 template/scripts/knowledge/ingest.py --build
  - python3 template/scripts/knowledge/ingest.py --federated --trace ADR-0001
```

- [ ] **Step 4: Mirror into the shipped template workflow**

Open `template/.github/workflows/ai-governance.yml`. It already runs `scripts/knowledge/ingest.py --build` with template-root-relative paths. Add the same knowledge unit-test lines and the `--federated --trace ADR-0001` smoke there, using **that file's existing path prefix** (match the prefix already on its `ingest.py --build` line), and ensure `git` is available (add a `git` install/step only if the workflow doesn't already run on an image that includes it — GitHub's `ubuntu-latest` includes git, so no install is needed there).

- [ ] **Step 5: Verify the full governance gate locally (mirrors CI)**

```bash
python3 template/scripts/validate-skills.py
python3 template/scripts/validate-frontmatter.py
python3 template/scripts/validate-moments.py
python3 template/scripts/tests/test_validate_moments.py
python3 template/scripts/validate-seat-profiles.py
python3 template/scripts/tests/test_validate_seat_profiles.py
for t in template/scripts/knowledge/tests/test_*.py; do python3 "$t" || break; done
python3 template/scripts/knowledge/ingest.py --build
python3 template/scripts/knowledge/ingest.py --federated --trace ADR-0001
```
Expected: every validator prints its PASS line; every knowledge test prints `OK`; build prints counts; trace prints the resolved chain JSON.

- [ ] **Step 6: Commit**

```bash
git add template/scripts/knowledge/tests/test_end_to_end.py .gitlab-ci.yml template/.github/workflows/ai-governance.yml
git commit -m "ci: wire knowledge-graph tests + traceability smoke into the gate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Plan Self-Review

**Spec coverage** — every design section maps to a task:
- Store & isolation (per-namespace DB + manifest + overlay) → Tasks 1, 2, 7.
- Node/edge ontology + id scheme → Task 1 (+ producers 3, 4, 5).
- Docs ingester + link convention → Task 3.
- Code ingester (ast/regex, markers, covers, imports) → Task 4.
- Commit-linkage optional layer → Task 5.
- Query engine (scoped/federated/search/trace, citations) → Task 6.
- Orchestrator + CLI + resolve pass → Task 7.
- MCP server → Task 8.
- Dogfood chain (ADR-0001 + markers + tests + AS-0001) → markers in Tasks 1–8, nodes in Task 9, verified in 9 + 10.
- Docs (schema/README/rule/AGENTS §4.4), `.mcp.json` enabled → Task 9.
- Tests + CI gate + `.gitignore` → Tasks 1–10 (gitignore in 2, CI in 10).
- Error handling (dangling `resolved=0`, unbuilt-graph degrade, malformed frontmatter, absent dashboard DB) → Tasks 3 (malformed), 5 (absent DB), 6 (empty aliases), 7 (resolve pass), 8 (tool errors).

**Type/name consistency** — id helpers, `NODE_FIELDS`/`EDGE_FIELDS`, `ingest_root(root, ns, base)` (both ingesters), `link(ns, code_nodes, db, base)`, `build(data, base)`, `open_scoped`/`open_federated`/`KG`/`trace` names are used identically across Tasks 1–10.

**Placeholder scan** — no TBD/TODO; every code step ships complete, runnable code; every run step has an exact command + expected output.

**Known follow-through for the executor:** the two heuristic spots (Task 4 `covers` candidate-path math; Task 5 git-path suffix matching) carry inline debug notes — if their tests fail, fix in-module, don't paper over in the test.

---

## Execution Handoff

**Plan complete and saved to `docs/roadmap/2026-07-02-phase-4-knowledge-graph-plan.md`.** Two execution options:

**1. Subagent-Driven (recommended)** — fresh implementer subagent per task, spec+quality review after each, whole-branch review at the end.

**2. Inline Execution** — batch execution in this session with checkpoints.

Which approach?
