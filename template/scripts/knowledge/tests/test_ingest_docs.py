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
