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


def _fixture_repo_with_ghost(base):
    """Same as _fixture_repo but adds src/ghost.py referencing a missing ADR-0099."""
    data = _fixture_repo(base)
    (base / "src/ghost.py").write_text("# ADR-0099\ndef ghost(): pass\n", encoding="utf-8")
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


class DanglingLinkTests(unittest.TestCase):
    def test_dangling_link_honesty_and_scoped_isolation(self):
        """Covers Finding 2 + 3: dangling edges kept with resolved=0 and scoped
        overlay filtering prevents cross-namespace leakage."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            data = _fixture_repo_with_ghost(base)
            ingest.build(data=data, base=base)

            # (a) Federated: dangling link preserved with resolved=0 and source_file set.
            fed = q.open_federated(data=data, base=base)
            res = q.trace(fed, "adr:ADR-0099")
            dangling = [e for e in res["edges"]
                        if e["dst"] == "adr:ADR-0099" and e["kind"] == "implements"]
            self.assertTrue(dangling, "dangling edge must be surfaced, not dropped")
            self.assertEqual(dangling[0]["resolved"], 0, "dangling edge must have resolved=0")
            self.assertIsNotNone(dangling[0]["source_file"],
                                 "dangling edge must carry its source_file citation")

            # (b) Scoped to 'docs': neither endpoint is a docs node — edge must not leak.
            docs_kg = q.open_scoped("docs", data=data, base=base)
            docs_res = q.trace(docs_kg, "adr:ADR-0099")
            docs_dangling = [e for e in docs_res["edges"]
                             if e["dst"] == "adr:ADR-0099" and e["kind"] == "implements"]
            self.assertEqual(docs_dangling, [],
                             "docs scope must not see a kit-only dangling overlay edge")

            # (c) Scoped to 'kit': source node is a kit node — edge IS visible.
            kit_kg = q.open_scoped("kit", data=data, base=base)
            kit_res = q.trace(kit_kg, "adr:ADR-0099")
            kit_dangling = [e for e in kit_res["edges"]
                            if e["dst"] == "adr:ADR-0099" and e["kind"] == "implements"]
            self.assertTrue(kit_dangling,
                            "kit scope must see the kit-only dangling overlay edge")

    def test_git_ignored_files_are_not_ingested(self):
        import shutil, subprocess
        if not shutil.which("git"):
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _fixture_repo(base)
            subprocess.run(["git", "init", "-q"], cwd=d, check=True)
            (base / ".gitignore").write_text("node_modules/\nout/\n", encoding="utf-8")
            (base / "docs/node_modules/pkg").mkdir(parents=True)
            (base / "docs/node_modules/pkg/README.md").write_text("vendored\n", encoding="utf-8")
            (base / "src/out").mkdir()
            (base / "src/out/gen.py").write_text("def gen(): pass\n", encoding="utf-8")
            ingest.build(data=data, base=base)
            fed = q.open_federated(data=data, base=base)
            paths = {r[0] for r in fed.conn.execute(
                f"SELECT path FROM ({fed.nodes_sql()})")}
            self.assertIn("src/thing.py", paths)
            self.assertFalse([p for p in paths if "node_modules" in p or "/out/" in p], paths)


    def test_a_repository_cloned_under_the_base_is_ingested_by_its_own_ignore_rules(self):
        """Parent layout: the product repository is git-ignored by the kit, and still ingested."""
        import shutil, subprocess
        if not shutil.which("git"):
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _fixture_repo(base)
            subprocess.run(["git", "init", "-q"], cwd=d, check=True)
            (base / ".gitignore").write_text("product/\n", encoding="utf-8")
            product = base / "product"
            (product / "pkg").mkdir(parents=True)
            (product / "dist").mkdir()
            subprocess.run(["git", "init", "-q"], cwd=str(product), check=True)
            (product / ".gitignore").write_text("dist/\n", encoding="utf-8")
            (product / "pkg/app.py").write_text("# ADR-0001\ndef run(): pass\n", encoding="utf-8")
            (product / "dist/built.py").write_text("def built(): pass\n", encoding="utf-8")
            data["namespaces"]["product"] = {"kind": "code", "db": ".knowledge/product.db",
                                             "roots": ["product/"]}
            ingest.build(data=data, base=base)
            fed = q.open_federated(data=data, base=base)
            paths = {r[0] for r in fed.conn.execute(f"SELECT path FROM ({fed.nodes_sql()})")}
            self.assertIn("product/pkg/app.py", paths)
            self.assertNotIn("product/dist/built.py", paths)

    def test_a_namespace_whose_repository_is_not_cloned_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _fixture_repo(base)
            data["namespaces"]["absent"] = {"kind": "code", "db": ".knowledge/absent.db",
                                            "roots": ["not-cloned/"]}
            stats = ingest.build(data=data, base=base)
            self.assertIn(["absent", 0, 0], [list(row) for row in stats["namespaces"]])

    def test_the_base_option_must_name_a_directory(self):
        import subprocess
        script = Path(ingest.__file__)
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, str(script), "--stats", "--base", f"{d}/missing"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)
            self.assertIn("is not a directory", r.stderr)
            self.assertFalse((Path(d) / "missing").exists())

    def test_markdown_link_across_namespaces_resolves_in_overlay(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _fixture_repo(base)
            (base / "docs/guide.md").write_text(
                "See [the code](../src/thing.py) and [nothing](missing.md).\n", encoding="utf-8")
            ingest.build(data=data, base=base)
            fed = q.open_federated(data=data, base=base)
            rows = {r[0]: r[1] for r in fed.conn.execute(
                f"SELECT dst, resolved FROM ({fed.edges_sql()}) WHERE kind='links'")}
            self.assertEqual(rows, {"code:kit:src/thing.py": 1, "path:docs/missing.md": 0})


    def test_link_between_two_roots_of_one_namespace_stays_in_that_namespace(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _fixture_repo(base)
            (base / "AGENTS.md").write_text("Start at the [readme](README.md).\n", encoding="utf-8")
            (base / "README.md").write_text("Readme.\n", encoding="utf-8")
            data["namespaces"]["briefs"] = {"kind": "docs", "db": ".knowledge/briefs.db",
                                            "roots": ["AGENTS.md", "README.md"]}
            ingest.build(data=data, base=base)
            scoped = q.open_scoped("briefs", data=data, base=base)
            rows = scoped.conn.execute(
                "SELECT src, dst, resolved FROM ns_briefs.edges WHERE kind='links'").fetchall()
            self.assertEqual(rows, [("doc:briefs:AGENTS.md", "doc:briefs:README.md", 1)])


class ExcludeTests(unittest.TestCase):
    def _paths(self, base, data, ns):
        import query
        kg = query.open_scoped(ns, data=data, base=base)
        return {r[0] for r in kg.conn.execute(f"SELECT path FROM ({kg.nodes_sql()})")}

    def _tree(self, base, files):
        for rel, text in files.items():
            f = base / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8")

    def test_matching(self):
        ex = ingest._excluded
        self.assertTrue(ex("backlog/old/a.md", ["backlog"]))        # a folder above it
        self.assertTrue(ex("backlog/old/a.md", ["backlog/old"]))
        self.assertTrue(ex("backlog/old/a.md", ["backlog/old/a.md"]))  # the file
        self.assertTrue(ex("backlog/old/a.md", ["*.md"]))           # * crosses /
        self.assertTrue(ex("x/archive/a.md", ["*/archive"]))
        self.assertFalse(ex("backlog-new/a.md", ["backlog"]))        # not a prefix of a name
        self.assertFalse(ex("a/backlog/b.md", ["backlog"]))          # below the root, not anywhere
        self.assertFalse(ex("keep.md", ["backlog", "*.txt"]))

    def test_a_docs_namespace_leaves_out_what_its_exclude_list_names(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            self._tree(base, {
                "docs/keep.md": "# keep\n\n[old](backlog/old.md)\n",
                "docs/backlog/old.md": "# old\n",
                "docs/backlog/deep/older.md": "# older\n",
                "docs/notes/a.draft.md": "# draft\n",
                "docs/notes/b.md": "# b\n",
                "other/backlog/kept.md": "# a second root\n"})
            data = {"namespaces": {"docs": {
                        "kind": "docs", "db": "docs/.knowledge/graph.db",
                        "roots": ["docs/", "other/"],
                        "exclude": ["backlog/", "*.draft.md"]}},
                    "overlay": "docs/knowledge/.knowledge/global.db"}
            ingest.build(data=data, base=base)
            self.assertEqual(self._paths(base, data, "docs"),
                             {"docs/keep.md", "docs/notes/b.md"})

    def test_exclude_is_below_each_root_and_a_file_root_is_kept(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            self._tree(base, {"docs/a.md": "# a\n", "docs/sub/a.md": "# sub a\n",
                              "README.md": "# readme\n"})
            data = {"namespaces": {"docs": {
                        "kind": "docs", "db": "docs/.knowledge/graph.db",
                        "roots": ["docs/", "README.md"],
                        "exclude": ["a.md", "README.md", "docs"]}},
                    "overlay": "docs/knowledge/.knowledge/global.db"}
            ingest.build(data=data, base=base)
            self.assertEqual(self._paths(base, data, "docs"), {"docs/sub/a.md", "README.md"})

    def test_a_code_namespace_drops_the_file_and_its_symbols(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            self._tree(base, {"src/app.py": "def run():\n    pass\n",
                              "src/vendor/lib.py": "def helper():\n    pass\n"})
            data = {"namespaces": {"code": {
                        "kind": "code", "db": ".knowledge/graph.db",
                        "roots": ["src/"], "exclude": ["vendor"]}},
                    "overlay": "docs/knowledge/.knowledge/global.db"}
            ingest.build(data=data, base=base)
            self.assertEqual(self._paths(base, data, "code"), {"src/app.py"})

    def test_no_exclude_list_changes_nothing(self):
        nodes, edges = [{"id": "doc:d:docs/a.md", "path": "docs/a.md"}], []
        with tempfile.TemporaryDirectory() as t:
            for patterns in (None, [], ["", "/"]):
                self.assertEqual(ingest._drop_excluded(nodes, edges, Path(t) / "docs", t, patterns),
                                 (nodes, edges))


if __name__ == "__main__":
    unittest.main()
