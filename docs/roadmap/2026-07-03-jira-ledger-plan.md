# JIRA → CSV Ledger → Knowledge Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repeatable, scripted process that exports JIRA issues (Cloud *or* Data Center) to a git-tracked CSV ledger, ingests it into the Phase-4 knowledge graph as a new `issue` node kind, and auto-links each issue to the commits, code, docs, ADRs, and stories that already reference it.

**Architecture:** Three isolated units — **Fetch** (`scripts/jira/export_jira.py`, the only network unit, with a Cloud/DC deployment adapter) → **Ledger** (`docs/product/jira/issues.csv`, committed) → **Ingest** (`scripts/knowledge/ingest_issues.py`, pure). Linking reuses existing JIRA-key flows: `Refs: KEY` commit trailers (via a new `link_issues.py`, mirroring `link_commits.py`) and frontmatter link fields (via a small `normalize_ref()` extension). Cross-namespace edges resolve in the existing global overlay — no orchestrator changes beyond one `kind` branch.

**Tech Stack:** Python 3.12 **stdlib only** (`csv`, `urllib`, `sqlite3`, `ast`, `unittest`) — no third-party runtime deps. SQLite graph store. GitLab CI governance gate.

## Global Constraints

- **Stdlib only.** No new runtime dependencies (matches `scripts/knowledge/` and the Phase-3 collector). `urllib.request` for HTTP, `csv` for the ledger.
- **All work lives under `template/`.** Paths below are relative to `template/` (the kit root the scripts resolve via `Path(__file__).parents[…]`). The plan/spec docs live at repo-root `docs/roadmap/`.
- **No secrets in git.** Auth via env vars only; `config.json` (project/JQL/deployment) is tracked, tokens are not.
- **Idempotent ledger.** Re-exporting unchanged JIRA state yields a byte-identical CSV (stable columns, rows sorted by natural key, `\n` line terminator, UTF-8).
- **Honesty preserved.** Unresolved links stay `resolved=0` (dangling, surfaced) — never invented. Same posture as the existing ingesters.
- **Derived DBs are git-ignored.** `template/.gitignore` already ignores `**/.knowledge/`, so `docs/product/jira/.knowledge/graph.db` needs no gitignore change.
- **Commit trailer.** End every commit message with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Branch.** All work on `feat/jira-ledger` (already created; the design spec is committed there).
- **CSV columns (canonical order), used verbatim everywhere:**
  `key, type, title, status, assignee, reporter, labels, sprint, epic, parent, priority, story_points, created, updated, resolution, url, description`

---

## File Structure

**Create:**
- `template/scripts/jira/export_jira.py` — exporter + Cloud/DC adapter (network).
- `template/scripts/jira/tests/test_export_jira.py` — normalizer/adapter/pagination unit tests (no network).
- `template/scripts/knowledge/ingest_issues.py` — pure `CSV → (nodes, edges)`.
- `template/scripts/knowledge/link_issues.py` — commit→issue `references` edges.
- `template/scripts/knowledge/tests/test_ingest_issues.py`
- `template/scripts/knowledge/tests/test_link_issues.py`
- `template/scripts/knowledge/tests/test_issue_chain.py` — end-to-end cross-namespace trace.
- `template/docs/product/jira/config.json` — sample config (tracked).
- `template/docs/product/jira/issues.csv` — seed ledger (live demo: `PROJ-1`, `PROJ-2`).
- `template/docs/product/jira/README.md` — how to configure/run + the MCP shortcut.

**Modify:**
- `template/scripts/knowledge/graph_store.py` — add `issue_id()` + JIRA-key branch in `normalize_ref()`.
- `template/scripts/knowledge/tests/test_graph_store.py` — assertions for the above.
- `template/scripts/knowledge/ingest.py` — `elif kind == "issues"` branch; wire `link_issues` (gated).
- `template/docs/knowledge/graph-manifest.json` — add the `issues` namespace.
- `template/docs/knowledge/schema.md` — document the `issue` node + `part-of`/`references` edges.
- `.gitlab-ci.yml` (repo root) — run the three new test files + an issue-trace smoke assert.

---

## Task 1: `normalize_ref` JIRA-key resolution + `issue_id` helper

**Files:**
- Modify: `template/scripts/knowledge/graph_store.py`
- Test: `template/scripts/knowledge/tests/test_graph_store.py`

**Interfaces:**
- Produces: `issue_id(key: str) -> str` returning `f"issue:{key}"`; `normalize_ref("PROJ-123") -> "issue:PROJ-123"` while `ADR-*`/`AS-*` precedence is unchanged.

- [ ] **Step 1: Add the failing assertions** to `test_id_helpers_and_normalize` in `template/scripts/knowledge/tests/test_graph_store.py` (append inside the existing method, after the last `assertEqual`):

```python
        self.assertEqual(gs.issue_id("PROJ-123"), "issue:PROJ-123")
        self.assertEqual(gs.normalize_ref("PROJ-123"), "issue:PROJ-123")
        self.assertEqual(gs.normalize_ref("AS-2"), "story:AS-2")      # story wins over issue
        self.assertEqual(gs.normalize_ref("ADR-0003"), "adr:ADR-0003")  # adr wins over issue
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/knowledge/tests/test_graph_store.py`
Expected: FAIL — `AttributeError: module 'graph_store' has no attribute 'issue_id'`

- [ ] **Step 3: Implement in `graph_store.py`.** Add the `issue_id` helper next to the other id helpers (after the `commit_id` line ~82):

```python
def issue_id(key: str) -> str: return f"issue:{key}"
```

Add the issue regex next to `_STORY_RE` (~line 84):

```python
_ISSUE_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
```

In `normalize_ref`, insert the issue branch **after** the story branch and **before** the path branch:

```python
    if _STORY_RE.match(ref):
        return story_id(ref.upper())
    if _ISSUE_RE.match(ref):
        return issue_id(ref)
    if "/" in ref or "." in ref:
        return f"path:{ref}"
```

(Order matters: `ADR-*` and `AS-*` are matched first, so they never fall through to the generic issue-key rule.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/scripts/knowledge/tests/test_graph_store.py`
Expected: PASS (`OK`)

- [ ] **Step 5: Commit**

```bash
git add template/scripts/knowledge/graph_store.py template/scripts/knowledge/tests/test_graph_store.py
git commit -m "feat: normalize_ref resolves JIRA keys to issue:<KEY> (+ issue_id helper)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `ingest_issues.py` — CSV ledger → issue nodes + `part-of` edges

**Files:**
- Create: `template/scripts/knowledge/ingest_issues.py`
- Test: `template/scripts/knowledge/tests/test_ingest_issues.py`

**Interfaces:**
- Consumes: `graph_store.issue_id` (Task 1).
- Produces: `ingest_root(root, namespace, base) -> (nodes, edges)` — same signature as `ingest_docs.ingest_root` / `ingest_code.ingest_root`. `root` is the CSV file path. Nodes have `kind="issue"`, `id=issue:<KEY>`, `path=<csv rels>`; `epic`/`parent` columns emit `part-of` edges (`src=issue:<KEY>`, `dst=issue:<ref>`, `resolved=None`).

- [ ] **Step 1: Write the failing test** — create `template/scripts/knowledge/tests/test_ingest_issues.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tempfile, unittest
import ingest_issues

HEADER = ("key,type,title,status,assignee,reporter,labels,sprint,epic,parent,"
          "priority,story_points,created,updated,resolution,url,description\n")


class IngestIssuesTests(unittest.TestCase):
    def _write(self, base, body):
        d = base / "docs/product/jira"
        d.mkdir(parents=True)
        (d / "issues.csv").write_text(HEADER + body, encoding="utf-8")
        return d / "issues.csv"

    def test_nodes_and_part_of(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            csv_path = self._write(
                base,
                "PROJ-1,Epic,Ledger epic,In Progress,Ada,Grace,plat;kg,S3,,,High,,,,,,An epic.\n"
                "PROJ-2,Story,Child story,To Do,Ada,Grace,kg,S3,PROJ-1,PROJ-1,Medium,3,,,,,Child.\n")
            nodes, edges = ingest_issues.ingest_root(csv_path, "issues", base)
            byid = {n["id"]: n for n in nodes}
            self.assertEqual(byid["issue:PROJ-1"]["kind"], "issue")
            self.assertEqual(byid["issue:PROJ-1"]["name"], "Ledger epic")
            self.assertEqual(byid["issue:PROJ-1"]["path"], "docs/product/jira/issues.csv")
            self.assertEqual(byid["issue:PROJ-2"]["meta"]["labels"], "kg")
            self.assertEqual(byid["issue:PROJ-2"]["subtype"], "Story")
            po = [e for e in edges if e["kind"] == "part-of"]
            self.assertIn(("issue:PROJ-2", "issue:PROJ-1"),
                          {(e["src"], e["dst"]) for e in po})
            self.assertEqual(po[0]["source_file"], "docs/product/jira/issues.csv")

    def test_blank_key_skipped_and_missing_file(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            csv_path = self._write(base, ",Story,No key,To Do,,,,,,,,,,,,,\n")
            nodes, edges = ingest_issues.ingest_root(csv_path, "issues", base)
            self.assertEqual(nodes, [])
            missing = base / "docs/product/jira/none.csv"
            self.assertEqual(ingest_issues.ingest_root(missing, "issues", base), ([], []))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/knowledge/tests/test_ingest_issues.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingest_issues'`

- [ ] **Step 3: Write the implementation** — create `template/scripts/knowledge/ingest_issues.py`:

```python
#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Issue ingester: the JIRA CSV ledger -> issue nodes + part-of edges. Stdlib
`csv` only. One row per issue; the `epic`/`parent` columns become `part-of`
edges (resolved in-namespace when the referenced issue is in the same ledger,
otherwise held for the global overlay)."""
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
    return nodes, edges
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 template/scripts/knowledge/tests/test_ingest_issues.py`
Expected: PASS (`OK`) — note `part-of` appears for both `epic` and `parent`; the test asserts the pair is present, so duplicates are fine.

- [ ] **Step 5: Commit**

```bash
git add template/scripts/knowledge/ingest_issues.py template/scripts/knowledge/tests/test_ingest_issues.py
git commit -m "feat: issue ingester (JIRA CSV ledger -> issue nodes + part-of edges)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Wire the `issues` namespace (manifest + orchestrator + seed ledger)

**Files:**
- Modify: `template/docs/knowledge/graph-manifest.json`
- Modify: `template/scripts/knowledge/ingest.py`
- Create: `template/docs/product/jira/issues.csv` (seed)
- Test: `template/scripts/knowledge/tests/test_ingest_issues.py` (add a build-level test)

**Interfaces:**
- Consumes: `ingest_issues.ingest_root` (Task 2).
- Produces: `ingest.build(data, base)` handles `kind == "issues"`; a `issues_present` flag is computed for Task 4's gating.

- [ ] **Step 1: Write the failing build-level test** — append to `template/scripts/knowledge/tests/test_ingest_issues.py` (add `import ingest` at the top, and this method to the class):

```python
    def test_build_registers_issue_namespace(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            self._write(
                base,
                "PROJ-1,Epic,Root,In Progress,,,,,,,,,,,,,\n"
                "PROJ-2,Story,Child,To Do,,,,,PROJ-1,,,,,,,,\n")
            data = {"namespaces": {
                        "issues": {"kind": "issues",
                                   "db": "docs/product/jira/.knowledge/graph.db",
                                   "roots": ["docs/product/jira/issues.csv"]}},
                    "overlay": "docs/knowledge/.knowledge/global.db"}
            stats = ingest.build(data=data, base=base)
            names = [n for n, *_ in stats["namespaces"]]
            self.assertIn("issues", names)
            counts = {n: nn for n, nn, ne in stats["namespaces"]}
            self.assertEqual(counts["issues"], 2)
```

(Remember to add `import ingest` beside `import ingest_issues` at the top of the file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/knowledge/tests/test_ingest_issues.py`
Expected: FAIL — the `issues` namespace ingests via the `else` (docs) branch, so `.md`-globbing finds nothing and `counts["issues"]` is `0` (KeyError/assert failure).

- [ ] **Step 3a: Add the manifest entry** — `template/docs/knowledge/graph-manifest.json` becomes:

```json
{
  "namespaces": {
    "docs":     { "kind": "docs", "db": "docs/.knowledge/graph.db", "roots": ["docs/"] },
    "kit-code": { "kind": "code", "db": ".knowledge/graph.db",       "roots": ["scripts/", "dashboard/"] },
    "issues":   { "kind": "issues", "db": "docs/product/jira/.knowledge/graph.db", "roots": ["docs/product/jira/issues.csv"] }
  },
  "overlay": "docs/knowledge/.knowledge/global.db"
}
```

- [ ] **Step 3b: Add imports and the branch** in `template/scripts/knowledge/ingest.py`. After `import ingest_code` (~line 23) add:

```python
import ingest_issues              # noqa: E402
import link_issues                # noqa: E402
```

Inside `build()`, right after `held: list[dict] = []` add the gating flag:

```python
    issues_present = any(spec.get("kind") == "issues"
                         for spec in data.get("namespaces", {}).values())
```

Replace the ingest dispatch (`if kind == "code": ... else: ingest_docs...`) with:

```python
            if kind == "code":
                n, e = ingest_code.ingest_root(root, name, base)
            elif kind == "issues":
                n, e = ingest_issues.ingest_root(root, name, base)
            else:
                n, e = ingest_docs.ingest_root(root, name, base)
```

(Leave the `link_commits` block as-is for this task — Task 4 adds the `link_issues` call. `link_issues` is imported now so the module exists; Task 4 creates it. To keep this task's tests green on its own, create a one-line stub `template/scripts/knowledge/link_issues.py` now containing `def link(namespace, commit_nodes, base): return []` — Task 4 replaces it test-first.)

- [ ] **Step 3c: Create the seed ledger** — `template/docs/product/jira/issues.csv` (the live in-kit demo: a two-issue `part-of` chain). Exact bytes:

```csv
key,type,title,status,assignee,reporter,labels,sprint,epic,parent,priority,story_points,created,updated,resolution,url,description
PROJ-1,Epic,Adopt the JIRA ledger,In Progress,,,knowledge,Sprint 1,,,High,,2026-07-03,2026-07-03,,https://example.atlassian.net/browse/PROJ-1,Seed epic demonstrating the issue namespace in the knowledge graph.
PROJ-2,Story,Ingest issues into the graph,To Do,,,knowledge,Sprint 1,PROJ-1,PROJ-1,Medium,3,2026-07-03,2026-07-03,,https://example.atlassian.net/browse/PROJ-2,Seed story that is part-of PROJ-1; shows a resolved part-of edge.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 template/scripts/knowledge/tests/test_ingest_issues.py`
Expected: PASS.

Run the real build smoke: `cd template && python3 scripts/knowledge/ingest.py --build && cd ..`
Expected: output includes an `issues   2 nodes   1 edges` line (the `PROJ-2 → PROJ-1` `part-of`), and the build still prints the docs/kit-code lines.

- [ ] **Step 5: Commit**

```bash
git add template/docs/knowledge/graph-manifest.json template/scripts/knowledge/ingest.py \
        template/scripts/knowledge/link_issues.py template/docs/product/jira/issues.csv \
        template/scripts/knowledge/tests/test_ingest_issues.py
git commit -m "feat: register issues namespace + seed ledger; wire ingest orchestrator

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `link_issues.py` — commit→issue `references` edges + orchestrator wiring

**Files:**
- Modify: `template/scripts/knowledge/link_issues.py` (replace the Task-3 stub)
- Modify: `template/scripts/knowledge/ingest.py` (call `link_issues` in the code branch)
- Test: `template/scripts/knowledge/tests/test_link_issues.py`
- Test: `template/scripts/knowledge/tests/test_issue_chain.py` (end-to-end)

**Interfaces:**
- Consumes: `graph_store.issue_id` (Task 1); the commit nodes returned by `link_commits.link` (each `{"id": "commit:<ns>:<sha>", "meta": {"sha": ...}}`).
- Produces: `link(namespace, commit_nodes, base) -> list[edge]` — one `references` edge (`src=commit id`, `dst=issue:<KEY>`, `resolved=None`) per distinct JIRA key found in each commit's message. Empty list when `commit_nodes` is empty.

- [ ] **Step 1: Write the failing unit test** — create `template/scripts/knowledge/tests/test_link_issues.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import subprocess, tempfile, unittest
import link_issues as li


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


class LinkIssuesTests(unittest.TestCase):
    def test_no_commit_nodes_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(li.link("kit", [], Path(d)), [])

    def test_references_edge_from_commit_message(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            _git(base, "init", "-q")
            _git(base, "config", "user.email", "a@b.c")
            _git(base, "config", "user.name", "T")
            (base / "f.py").write_text("x = 1\n")
            _git(base, "add", "-A")
            _git(base, "commit", "-q", "-m", "feat: thing\n\nRefs: PROJ-1 PROJ-1 PROJ-2")
            sha = _git(base, "rev-parse", "HEAD").stdout.strip()
            commit_nodes = [{"id": f"commit:kit:{sha}", "meta": {"sha": sha}}]
            edges = li.link("kit", commit_nodes, base)
            pairs = {(e["src"], e["dst"], e["kind"]) for e in edges}
            self.assertIn((f"commit:kit:{sha}", "issue:PROJ-1", "references"), pairs)
            self.assertIn((f"commit:kit:{sha}", "issue:PROJ-2", "references"), pairs)
            self.assertEqual(len(edges), 2)  # PROJ-1 de-duplicated


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 template/scripts/knowledge/tests/test_link_issues.py`
Expected: FAIL — the Task-3 stub returns `[]`, so the `assertIn` checks fail.

- [ ] **Step 3: Replace the stub** — `template/scripts/knowledge/link_issues.py`:

```python
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
```

- [ ] **Step 4a: Run the unit test to verify it passes**

Run: `python3 template/scripts/knowledge/tests/test_link_issues.py`
Expected: PASS (`OK`).

- [ ] **Step 4b: Wire it into the orchestrator.** In `template/scripts/knowledge/ingest.py`, inside `build()`'s `if kind == "code":` block, right after `ns_edges += ce` (the `link_commits` results), add:

```python
            if issues_present:
                ns_edges += link_issues.link(name, cn, base)
```

- [ ] **Step 4c: Write the end-to-end test** — create `template/scripts/knowledge/tests/test_issue_chain.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sqlite3, subprocess, tempfile, unittest
import ingest, query as q


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


class IssueChainTests(unittest.TestCase):
    def test_issue_links_to_commit_code_and_story(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "docs/product/stories").mkdir(parents=True)
            (base / "docs/product/stories/AS-0001-x.md").write_text(
                '---\ntitle: "Story"\ntraces: [PROJ-1]\n---\nAs a user.\n', encoding="utf-8")
            (base / "src").mkdir(parents=True)
            (base / "src/thing.py").write_text("def go():\n    return 1\n", encoding="utf-8")
            _git(base, "init", "-q")
            _git(base, "config", "user.email", "a@b.c")
            _git(base, "config", "user.name", "T")
            _git(base, "add", "-A")
            _git(base, "commit", "-q", "-m", "feat: thing\n\nRefs: PROJ-1")
            sha = _git(base, "rev-parse", "HEAD").stdout.strip()
            dash = base / "dashboard" / "utilization.db"
            dash.parent.mkdir(parents=True)
            con = sqlite3.connect(dash)
            con.execute("CREATE TABLE commits (sha TEXT, klass TEXT)")
            con.execute("INSERT INTO commits VALUES (?, 'ai')", (sha,))
            con.commit(); con.close()
            (base / "docs/product/jira").mkdir(parents=True)
            (base / "docs/product/jira/issues.csv").write_text(
                "key,type,title,status,assignee,reporter,labels,sprint,epic,parent,"
                "priority,story_points,created,updated,resolution,url,description\n"
                "PROJ-1,Story,Do the thing,In Progress,,,,,,,,,,,,,\n", encoding="utf-8")
            data = {"namespaces": {
                        "docs": {"kind": "docs", "db": "docs/.knowledge/graph.db", "roots": ["docs/"]},
                        "kit": {"kind": "code", "db": ".knowledge/graph.db", "roots": ["src/"]},
                        "issues": {"kind": "issues",
                                   "db": "docs/product/jira/.knowledge/graph.db",
                                   "roots": ["docs/product/jira/issues.csv"]}},
                    "overlay": "docs/knowledge/.knowledge/global.db"}
            orig = ingest.DASHBOARD_DB
            ingest.DASHBOARD_DB = dash
            try:
                ingest.build(data=data, base=base)
                kg = q.open_federated(data=data, base=base)
                res = q.trace(kg, "issue:PROJ-1")
            finally:
                ingest.DASHBOARD_DB = orig
            ids = {n["id"] for n in res["nodes"]}
            self.assertIn("issue:PROJ-1", ids)
            self.assertIn("story:AS-0001", ids)             # doc -> issue via traces
            self.assertIn("code:kit:src/thing.py", ids)     # issue -> commit -> code
            refs = [e for e in res["edges"]
                    if e["kind"] == "references" and e["dst"] == "issue:PROJ-1"]
            self.assertTrue(refs and refs[0]["resolved"] == 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4d: Run the end-to-end test**

Run: `python3 template/scripts/knowledge/tests/test_issue_chain.py`
Expected: PASS (`OK`) — the trace assembles issue → story (traces), and issue → commit → code (references + touches) across three namespaces via the overlay.

- [ ] **Step 5: Commit**

```bash
git add template/scripts/knowledge/link_issues.py template/scripts/knowledge/ingest.py \
        template/scripts/knowledge/tests/test_link_issues.py \
        template/scripts/knowledge/tests/test_issue_chain.py
git commit -m "feat: link commits to issues (references edges) + end-to-end trace

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `export_jira.py` — config, normalizer, ledger writer (pure core)

**Files:**
- Create: `template/scripts/jira/export_jira.py` (core functions this task; adapter/main in Task 6)
- Test: `template/scripts/jira/tests/test_export_jira.py`

**Interfaces:**
- Produces:
  - `COLUMNS: list[str]` — the canonical column order (Global Constraints).
  - `adf_to_text(node) -> str` — flatten Atlassian Document Format (Cloud) to text.
  - `normalize_description(desc, max_chars) -> str` — ADF/str → collapsed, capped text.
  - `normalize_issue(raw: dict, cfg: dict, base_url: str) -> dict` — one raw JIRA issue → a row dict keyed by `COLUMNS`.
  - `natural_key(key: str) -> tuple` — `("PROJ", 2)` so `PROJ-2 < PROJ-10`.
  - `write_ledger(rows: list[dict], path) -> Path` — atomic, sorted, idempotent write.

- [ ] **Step 1: Write the failing tests** — create `template/scripts/jira/tests/test_export_jira.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tempfile, unittest
import export_jira as ej

CFG = {"deployment": "cloud", "project": "PROJ",
       "fields": {"sprint": "customfield_10020", "epic_link": "customfield_10014",
                  "story_points": "customfield_10016"},
       "description_max_chars": 30}

CLOUD_RAW = {
    "key": "PROJ-2",
    "fields": {
        "issuetype": {"name": "Story"}, "summary": "Ingest issues",
        "status": {"name": "To Do"}, "assignee": {"displayName": "Ada"},
        "reporter": {"displayName": "Grace"}, "labels": ["kg", "plat"],
        "priority": {"name": "Medium"}, "resolution": None,
        "created": "2026-07-03T10:00:00.000+0000", "updated": "2026-07-03T11:00:00.000+0000",
        "parent": {"key": "PROJ-1"},
        "customfield_10020": [{"name": "Sprint 1"}],
        "customfield_10016": 3.0,
        "description": {"type": "doc", "content": [
            {"type": "paragraph", "content": [
                {"type": "text", "text": "A long description that exceeds the cap for sure."}]}]},
    }}

DC_RAW = {
    "key": "PROJ-3",
    "fields": {
        "issuetype": {"name": "Bug"}, "summary": "Fix it",
        "status": {"name": "Done"}, "assignee": {"name": "ada"},
        "reporter": {"name": "grace"}, "labels": [],
        "priority": {"name": "High"}, "resolution": {"name": "Fixed"},
        "created": "2026-07-01T09:00:00.000+0000", "updated": "2026-07-02T09:00:00.000+0000",
        "customfield_10016": 5,
        "description": "Plain   wiki   text.",
    }}


class NormalizeTests(unittest.TestCase):
    def test_cloud_issue(self):
        r = ej.normalize_issue(CLOUD_RAW, CFG, "https://x.atlassian.net")
        self.assertEqual(r["key"], "PROJ-2")
        self.assertEqual(r["type"], "Story")
        self.assertEqual(r["assignee"], "Ada")
        self.assertEqual(r["labels"], "kg;plat")
        self.assertEqual(r["sprint"], "Sprint 1")
        self.assertEqual(r["parent"], "PROJ-1")
        self.assertEqual(r["epic"], "PROJ-1")     # falls back to parent
        self.assertEqual(r["story_points"], "3")  # 3.0 -> "3"
        self.assertEqual(r["url"], "https://x.atlassian.net/browse/PROJ-2")
        self.assertEqual(len(r["description"]), 30)  # capped
        self.assertNotIn("\n", r["description"])

    def test_datacenter_issue(self):
        r = ej.normalize_issue(DC_RAW, CFG, "https://jira.co/")
        self.assertEqual(r["type"], "Bug")
        self.assertEqual(r["assignee"], "ada")
        self.assertEqual(r["resolution"], "Fixed")
        self.assertEqual(r["story_points"], "5")
        self.assertEqual(r["description"], "Plain wiki text.")
        self.assertEqual(r["url"], "https://jira.co/browse/PROJ-3")

    def test_natural_key_sorts_numerically(self):
        self.assertEqual(ej.natural_key("PROJ-2"), ("PROJ", 2))
        self.assertTrue(ej.natural_key("PROJ-2") < ej.natural_key("PROJ-10"))

    def test_write_ledger_is_idempotent(self):
        rows = [ej.normalize_issue(DC_RAW, CFG, "https://jira.co"),
                ej.normalize_issue(CLOUD_RAW, CFG, "https://x.atlassian.net")]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "issues.csv"
            ej.write_ledger(rows, p)
            first = p.read_bytes()
            ej.write_ledger(list(reversed(rows)), p)  # order must not matter
            self.assertEqual(first, p.read_bytes())
            text = first.decode("utf-8")
            self.assertTrue(text.startswith(",".join(ej.COLUMNS)))
            self.assertLess(text.index("PROJ-2"), text.index("PROJ-3"))  # sorted


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 template/scripts/jira/tests/test_export_jira.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'export_jira'`.

- [ ] **Step 3: Write the core** — create `template/scripts/jira/export_jira.py` (core only; Task 6 appends the adapter + `main`):

```python
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


def adf_to_text(node):
    """Flatten an Atlassian Document Format node (Cloud) to plain text."""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    parts = [adf_to_text(c) for c in node.get("content", []) or []]
    sep = "\n" if node.get("type") in {"paragraph", "heading"} else ""
    return sep.join(p for p in parts if p)


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 template/scripts/jira/tests/test_export_jira.py`
Expected: PASS (`OK`).

- [ ] **Step 5: Commit**

```bash
git add template/scripts/jira/export_jira.py template/scripts/jira/tests/test_export_jira.py
git commit -m "feat: JIRA exporter core (normalizer + idempotent CSV ledger writer)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `export_jira.py` — deployment adapter, pagination, `main`

**Files:**
- Modify: `template/scripts/jira/export_jira.py` (append adapter + `main`)
- Test: `template/scripts/jira/tests/test_export_jira.py` (add adapter/pagination tests)

**Interfaces:**
- Consumes: Task-5 core (`normalize_issue`, `write_ledger`, `COLUMNS`).
- Produces:
  - `cloud_headers() -> dict` / `datacenter_headers() -> dict` — auth headers from env.
  - `paginate_offset(fetch, base_url, api, jql, fields, page_size=50) -> list` (DC).
  - `paginate_cursor(fetch, base_url, jql, fields, page_size=50) -> list` (Cloud).
  - `BACKENDS: dict` — deployment → `{headers, paginate, [api]}`.
  - `main(argv=None) -> int` — supports `--build` and `--from-json <path>`.

- [ ] **Step 1: Write the failing tests** — append to `template/scripts/jira/tests/test_export_jira.py` (add `import os` at top):

```python
class AdapterTests(unittest.TestCase):
    def _fake(self, pages):
        it = iter(pages)
        return lambda url: next(it)

    def test_offset_pagination_stops_at_total(self):
        pages = [{"issues": [{"key": "A"}, {"key": "B"}], "total": 3},
                 {"issues": [{"key": "C"}], "total": 3}]
        got = ej.paginate_offset(self._fake(pages), "https://j", "2",
                                 "project=P", ["summary"], page_size=2)
        self.assertEqual([i["key"] for i in got], ["A", "B", "C"])

    def test_cursor_pagination_follows_token(self):
        pages = [{"issues": [{"key": "A"}], "nextPageToken": "t1"},
                 {"issues": [{"key": "B"}], "nextPageToken": None}]
        got = ej.paginate_cursor(self._fake(pages), "https://x", "project=P", ["summary"])
        self.assertEqual([i["key"] for i in got], ["A", "B"])

    def test_cloud_headers_basic(self):
        os.environ["JIRA_EMAIL"] = "a@b.c"
        os.environ["JIRA_API_TOKEN"] = "tok"
        h = ej.cloud_headers()
        self.assertTrue(h["Authorization"].startswith("Basic "))

    def test_datacenter_headers_bearer(self):
        os.environ.pop("JIRA_USER", None)
        os.environ.pop("JIRA_PASSWORD", None)
        os.environ["JIRA_PAT"] = "pat123"
        h = ej.datacenter_headers()
        self.assertEqual(h["Authorization"], "Bearer pat123")

    def test_main_from_json_writes_ledger(self):
        payload = ('{"issues": [' + str(CLOUD_RAW).replace("'", '"').replace("None", "null") + ']}')
        with tempfile.TemporaryDirectory() as d:
            jf = Path(d) / "in.json"
            jf.write_text(payload, encoding="utf-8")
            out = Path(d) / "issues.csv"
            os.environ["JIRA_BASE_URL"] = "https://x.atlassian.net"
            rc = ej.main(["--from-json", str(jf)], config=CFG, ledger=out)
            self.assertEqual(rc, 0)
            self.assertIn("PROJ-2", out.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 template/scripts/jira/tests/test_export_jira.py`
Expected: FAIL — `AttributeError: module 'export_jira' has no attribute 'paginate_offset'`.

- [ ] **Step 3: Append the adapter + `main`** to `template/scripts/jira/export_jira.py`. Add these imports to the existing import block at the top: `import base64`, `import json`, `import sys`, `import urllib.error`, `import urllib.parse`, `import urllib.request`. Then append:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 template/scripts/jira/tests/test_export_jira.py`
Expected: PASS (`OK`) — all normalizer, pagination, header, and `--from-json` tests green. (No live network is exercised.)

- [ ] **Step 5: Commit**

```bash
git add template/scripts/jira/export_jira.py template/scripts/jira/tests/test_export_jira.py
git commit -m "feat: JIRA exporter Cloud/DC adapter + pagination + main (--from-json/--build)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Config sample, docs, schema, and CI wiring

**Files:**
- Create: `template/docs/product/jira/config.json`
- Create: `template/docs/product/jira/README.md`
- Modify: `template/docs/knowledge/schema.md`
- Modify: `.gitlab-ci.yml` (repo root)

**Interfaces:** none (docs + CI only). This task makes the feature adoptable and gated.

- [ ] **Step 1: Create the sample config** — `template/docs/product/jira/config.json`:

```json
{
  "deployment": "cloud",
  "base_url_env": "JIRA_BASE_URL",
  "project": "PROJ",
  "jql": "project = PROJ ORDER BY updated DESC",
  "fields": {
    "sprint": "customfield_10020",
    "epic_link": "customfield_10014",
    "story_points": "customfield_10016"
  },
  "description_max_chars": 500
}
```

- [ ] **Step 2: Create the README** — `template/docs/product/jira/README.md` (`README.md` is exempt from the frontmatter contract, so no frontmatter needed):

````markdown
# JIRA → CSV ledger → knowledge graph

A repeatable, scripted import of JIRA issues into a **git-tracked CSV ledger**
(`issues.csv`), then into the knowledge graph as `issue` nodes — auto-linked to
the commits, code, ADRs, and stories that already reference each key.

## One process, both deployments

`scripts/jira/export_jira.py` supports **JIRA Cloud** and **JIRA Data Center
(on-prem)** behind a deployment adapter. Pick the deployment in `config.json`;
everything downstream (ledger, ingest, linking) is identical.

| Deployment | `config.json` `deployment` | Base URL env | Auth env |
|---|---|---|---|
| Cloud | `cloud` | `JIRA_BASE_URL=https://<site>.atlassian.net` | `JIRA_EMAIL` + `JIRA_API_TOKEN` |
| Data Center | `datacenter` | `JIRA_BASE_URL=https://jira.company.com` | `JIRA_PAT` (preferred) or `JIRA_USER` + `JIRA_PASSWORD` |

Secrets come from the environment only — never commit them. `config.json`
(project, JQL, custom-field ids) is tracked.

## Run

```bash
# 1. configure
$EDITOR docs/product/jira/config.json          # deployment, project, JQL, field ids
export JIRA_BASE_URL=https://acme.atlassian.net
export JIRA_EMAIL=you@acme.com JIRA_API_TOKEN=…  # Cloud; or JIRA_PAT=… for Data Center

# 2. export + rebuild the graph
python3 scripts/jira/export_jira.py --build      # writes issues.csv, then ingest --build
#   (or: python3 scripts/jira/export_jira.py  &&  python3 scripts/knowledge/ingest.py --build)

# 3. trace an issue across docs/code/commits
python3 scripts/knowledge/ingest.py --federated --trace issue:PROJ-1
```

The export is idempotent: an unchanged board produces a byte-identical
`issues.csv` (empty git diff). A failed fetch never overwrites the ledger, so
the graph keeps building from the last committed version.

## Custom-field ids

Sprint, Epic-Link, and Story-Points are custom fields whose ids differ per
instance. Find them at `<base>/rest/api/2/field` (Data Center) or
`/rest/api/3/field` (Cloud) and set them under `fields` in `config.json`.

## Linking

- **issue → issue** (`part-of`) — from the `epic`/`parent` columns.
- **commit → issue** (`references`) — from `Refs: KEY` trailers (enforced by the
  `commit-msg` hook). Requires the Phase-3 commit layer (`dashboard/`) for the
  issue → commit → code chain; without it, issues still link to docs/stories.
- **doc/adr/story → issue** — put the JIRA key in a frontmatter link field
  (`traces:`, `implements:`, `cites:`), e.g. `traces: [PROJ-1]`.

Unresolved keys are reported honestly (`resolved=0`), never invented.

## MCP shortcut (Cloud only, optional)

Cloud teams can let the agent pull issues via the `issue-tracker` MCP instead of
a stored token, then hand the JSON to the exporter:

```bash
python3 scripts/jira/export_jira.py --from-json /path/to/issues.json --build
```

There is no hosted MCP for Data Center — DC uses the REST path above.
````

- [ ] **Step 3: Document the node/edges in the schema** — in `template/docs/knowledge/schema.md`, add a row to the **Nodes** table (after the `commit` row):

```markdown
| `issue` | `issue:<KEY>` | JIRA CSV ledger (`docs/product/jira/issues.csv`) |
```

and add rows to the **Edges** table (after the `touches` row):

```markdown
| `part-of` | issue → issue | ledger `epic`/`parent` columns |
| `references` | commit → issue | `Refs: KEY` in commit messages (optional commit layer) |
```

Also extend the `traces`/`implements`/`cites` note under "The link convention" — append one bullet:

```markdown
- **JIRA keys:** a frontmatter link value matching `ABC-123` resolves to
  `issue:<KEY>`, linking docs/stories/ADRs to imported issues.
```

- [ ] **Step 4: Wire the tests + smoke into CI** — in `.gitlab-ci.yml`, in the `ai-governance` job, after the `test_end_to_end.py` line (currently ~line 54) add:

```yaml
  - python3 template/scripts/knowledge/tests/test_ingest_issues.py
  - python3 template/scripts/knowledge/tests/test_link_issues.py
  - python3 template/scripts/knowledge/tests/test_issue_chain.py
  - python3 template/scripts/jira/tests/test_export_jira.py
```

and after the existing ADR trace-smoke line (`--trace ADR-0001 | …`) add an issue-trace smoke:

```yaml
  - python3 template/scripts/knowledge/ingest.py --federated --trace issue:PROJ-1 | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('nodes'), 'empty issue trace'; print('issue trace OK:', len(d['nodes']), 'nodes')"
```

- [ ] **Step 5: Run the full governance sequence locally to verify green**

Run:
```bash
cd template
python3 scripts/validate-frontmatter.py
python3 scripts/knowledge/tests/test_graph_store.py
python3 scripts/knowledge/tests/test_ingest_issues.py
python3 scripts/knowledge/tests/test_link_issues.py
python3 scripts/knowledge/tests/test_issue_chain.py
python3 scripts/jira/tests/test_export_jira.py
python3 scripts/knowledge/ingest.py --build
python3 scripts/knowledge/ingest.py --federated --trace issue:PROJ-1 | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('nodes'); print('issue trace OK:', len(d['nodes']), 'nodes')"
cd ..
```
Expected: every test prints `OK`; the build prints an `issues` line; the trace smoke prints `issue trace OK: N nodes` (N ≥ 2 — `PROJ-1` + `PROJ-2` via `part-of`). `validate-frontmatter.py` still passes (README is exempt).

- [ ] **Step 6: Commit**

```bash
git add template/docs/product/jira/config.json template/docs/product/jira/README.md \
        template/docs/knowledge/schema.md .gitlab-ci.yml
git commit -m "docs+ci: JIRA ledger config/README, schema nodes+edges, CI wiring

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage** (design §→ task):
- §2 three-unit architecture → Tasks 2/3 (ingest), 5/6 (fetch), 3 (ledger). ✓
- §2.1 Cloud/DC adapter (4 knobs) → Task 6 (`BACKENDS`, headers, pagination, api version). ✓
- §2.2 `issues` namespace + one `kind` branch → Task 3. ✓
- §3.1 ledger columns / sort / idempotence → Task 5 (`COLUMNS`, `natural_key`, `write_ledger`). ✓
- §3.2 field mapping (Cloud ADF vs DC markup; custom fields via config) → Tasks 5/6. ✓
- §4.1 `issue` node → Task 2. ✓
- §4.2 edges `part-of` / `references` / frontmatter `traces` → Tasks 2, 4, 1. ✓
- §4.3 worked example → Task 4 end-to-end test (fabricated commit lives in the fixture, not the repo; live kit graph ships the seed `part-of` demo — deliberate refinement). ✓
- §5 config + env auth (no secrets) → Tasks 6/7. ✓
- §6 process wiring (manual, `--build`, CI ingests committed ledger, MCP shortcut) → Tasks 6/7. ✓
- §7 error handling / idempotency (atomic write, non-zero on auth fail, tolerant fields) → Tasks 5/6. ✓
- §8 testing (pure ingest, normalizer on both shapes, pagination, end-to-end) → Tasks 2/4/5/6, CI in 7. ✓
- §9 non-goals — nothing in the plan violates them (read-only, full re-export, no webhooks). ✓
- §10 deliverables 1–7 → all mapped. ✓

**Placeholder scan:** none — every step has concrete code/commands/expected output.

**Type consistency:** `ingest_root(root, namespace, base)` signature matches the other ingesters and the `elif` call site; `link(namespace, commit_nodes, base)` matches Task 3's stub and Task 4's real impl and the wiring call `link_issues.link(name, cn, base)`; `normalize_issue(raw, cfg, base_url)` and `write_ledger(rows, path)` used consistently across Tasks 5/6 and the tests; commit node shape `{"id","meta":{"sha"}}` matches `link_commits.py`. ✓

One ordering note honored: `link_issues.py` is imported in Task 3 (as a stub) so `ingest.py` imports resolve, then replaced test-first in Task 4.
