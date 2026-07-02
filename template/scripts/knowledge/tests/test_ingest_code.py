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
