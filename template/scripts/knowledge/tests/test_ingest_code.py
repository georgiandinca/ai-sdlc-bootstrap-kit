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

    def test_non_python_symbol_line_ignores_blank_lines_above(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self._write(base / "s/a.js", "import x\n\n\nfunction foo() {}\n")
            nodes, edges = icode.ingest_root(base / "s", "kit", base)
            foo = next(n for n in nodes if n["kind"] == "symbol" and n["name"] == "foo")
            self.assertEqual(foo["meta"]["lineno"], 4)  # not 2, the first blank line
            self.assertEqual([e["line"] for e in edges if e["dst"] == foo["id"]], [4])

    def test_import_resolution_boundary(self):
        """Regression test: ensure import resolution requires path-separator boundary.

        Fixture: s2/util.py (empty), s2/myutil.py (empty), s2/app.py (imports util).
        Verify: imports edge targets s2/util.py, NOT s2/myutil.py (no bare-suffix match).
        """
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self._write(base / "s2/util.py", "def helper():\n    return 1\n")
            self._write(base / "s2/myutil.py", "def myhelper():\n    return 2\n")
            self._write(base / "s2/app.py", "import util\n\ndef main():\n    return 3\n")
            nodes, edges = icode.ingest_root(base / "s2", "kit", base)
            ids = {n["id"] for n in nodes}
            self.assertIn("code:kit:s2/util.py", ids)
            self.assertIn("code:kit:s2/myutil.py", ids)
            self.assertIn("code:kit:s2/app.py", ids)
            # imports edges from app.py should target util.py, not myutil.py
            imports = [e for e in edges if e["kind"] == "imports"
                       and e["src"] == "code:kit:s2/app.py"]
            self.assertTrue(any(e["dst"] == "code:kit:s2/util.py" for e in imports),
                            "Should resolve 'import util' to s2/util.py")
            self.assertFalse(any(e["dst"] == "code:kit:s2/myutil.py" for e in imports),
                             "Should NOT match s2/myutil.py via bare-suffix match")


class FileRootTests(unittest.TestCase):
    def test_a_single_file_can_be_a_root(self):
        import tempfile
        from pathlib import Path as P
        import ingest_code
        with tempfile.TemporaryDirectory() as d:
            base = P(d)
            (base / "tools").mkdir()
            (base / "tools/run.py").write_text("def go():\n    return 1\n", encoding="utf-8")
            (base / "tools/other.py").write_text("def no():\n    return 0\n", encoding="utf-8")
            nodes, _ = ingest_code.ingest_root(base / "tools/run.py", "kit", base)
            self.assertEqual(sorted(n["id"] for n in nodes),
                             ["code:kit:tools/run.py", "sym:kit:tools/run.py:go"])


class MoreLanguagesTests(unittest.TestCase):
    def _write(self, p, text):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    # The markers below use numbers no project has: this file is ingested with a
    # project's scripts, and a real number would put it in that decision's trace.
    def test_tsx_sql_and_tf_files_are_ingested(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self._write(base / "app/src/App.tsx",
                        "// ADR-9994\nexport function App() {\n  return null;\n}\n"
                        "export default async function load() {}\n")
            self._write(base / "app/db/001_init.sql", "-- ADR-9993\nCREATE TABLE t (id int);\n")
            self._write(base / "app/main.tf", "# ADR-9997\n")
            self._write(base / "app/tests/posture.tftest.hcl", "# ADR-9997\n")
            nodes, edges = icode.ingest_root(base / "app", "console", base)
            ids = {n["id"] for n in nodes}
            self.assertIn("code:console:app/src/App.tsx", ids)
            self.assertIn("sym:console:app/src/App.tsx:App", ids)
            self.assertIn("sym:console:app/src/App.tsx:load", ids)
            self.assertIn("code:console:app/db/001_init.sql", ids)
            self.assertIn("code:console:app/main.tf", ids)
            self.assertIn("code:console:app/tests/posture.tftest.hcl", ids)
            implements = {(e["src"], e["dst"]) for e in edges if e["kind"] == "implements"}
            self.assertIn(("code:console:app/db/001_init.sql", "adr:ADR-9993"), implements)

    def test_a_typescript_test_covers_the_file_it_is_named_after(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self._write(base / "app/src/App.tsx", "export function App() {}\n")
            self._write(base / "app/src/App.test.tsx", "test('x', () => {});\n")
            self._write(base / "app/src/util.ts", "export const a = 1;\n")
            self._write(base / "app/src/util.spec.ts", "test('y', () => {});\n")
            nodes, edges = icode.ingest_root(base / "app", "console", base)
            kinds = {n["id"]: n["kind"] for n in nodes}
            self.assertEqual(kinds["test:console:app/src/App.test.tsx"], "test")
            covers = {(e["src"], e["dst"]) for e in edges if e["kind"] == "covers"}
            self.assertIn(("test:console:app/src/App.test.tsx", "code:console:app/src/App.tsx"), covers)
            self.assertIn(("test:console:app/src/util.spec.ts", "code:console:app/src/util.ts"), covers)


if __name__ == "__main__":
    unittest.main()
