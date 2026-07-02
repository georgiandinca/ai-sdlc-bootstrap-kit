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
