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


class BodyLinkTests(unittest.TestCase):
    def _repo(self, d):
        base = Path(d)
        (base / "docs/guide/sub").mkdir(parents=True)
        (base / "src").mkdir()
        (base / "docs/guide/sub/README.md").write_text("Sub.\n", encoding="utf-8")
        (base / "docs/guide/b.md").write_text("B.\n", encoding="utf-8")
        (base / "docs/top.md").write_text("Top.\n", encoding="utf-8")
        (base / "src/tool.py").write_text("x = 1\n", encoding="utf-8")
        return base

    def test_relative_links_resolve_to_repo_paths_with_lines(self):
        with tempfile.TemporaryDirectory() as d:
            base = self._repo(d)
            body = ("See [b](b.md#part) and [b again](./b.md).\n"
                    "Up: [top](../top.md \"Top\"), dir: [sub](sub/), code: [tool](/src/tool.py)\n"
                    "Spaces: [x](<my%20file.md>)\n")
            got = list(idoc.body_links(body, "docs/guide/a.md", base, line_offset=4))
            self.assertEqual(got, [("docs/guide/b.md", 5), ("docs/top.md", 6),
                                   ("docs/guide/sub/README.md", 6), ("src/tool.py", 6),
                                   ("docs/guide/my file.md", 7)])

    def test_non_graph_targets_are_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            base = self._repo(d)
            body = ("[web](https://example.com/x.md) [mail](mailto:a@b.co) [anchor](#here)\n"
                    "![img](b.md) [pic](shot.png) [self](a.md) [out](../../../etc/x.md)\n"
                    "[folder without a README](../../src/)\n"
                    "```\n[in fence](b.md)\n```\n")
            self.assertEqual(list(idoc.body_links(body, "docs/guide/a.md", base)), [])

    def test_ingest_root_emits_links_edges(self):
        with tempfile.TemporaryDirectory() as d:
            base = self._repo(d)
            (base / "docs/guide/a.md").write_text(
                "---\ntitle: A\n---\n\nSee [b](b.md), [tool](../../src/tool.py), [gone](gone.md).\n",
                encoding="utf-8")
            _nodes, edges = idoc.ingest_root(base / "docs", "docs", base)
            links = {e["dst"]: e for e in edges if e["kind"] == "links"}
            inroot = links["doc:docs:docs/guide/b.md"]
            self.assertEqual((inroot["resolved"], inroot["source_file"], inroot["line"]),
                             (1, "docs/guide/a.md", 5))
            # outside this root (or missing): left as path: for the overlay pass
            self.assertIsNone(links["path:src/tool.py"]["resolved"])
            self.assertIsNone(links["path:docs/guide/gone.md"]["resolved"])


class RootKindTests(unittest.TestCase):
    def test_a_single_file_can_be_a_root(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "docs").mkdir()
            (base / "docs/a.md").write_text("A.\n", encoding="utf-8")
            (base / "AGENTS.md").write_text("See [a](docs/a.md).\n", encoding="utf-8")
            (base / "notes.txt").write_text("not markdown\n", encoding="utf-8")
            nodes, edges = idoc.ingest_root(base / "AGENTS.md", "briefs", base)
            self.assertEqual([n["id"] for n in nodes], ["doc:briefs:AGENTS.md"])
            self.assertEqual([(e["kind"], e["dst"]) for e in edges], [("links", "path:docs/a.md")])
            self.assertEqual(idoc.ingest_root(base / "notes.txt", "briefs", base), ([], []))

    def test_an_explicit_hidden_root_is_walked_but_hidden_dirs_below_are_not(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / ".claude/skills/qa").mkdir(parents=True)
            (base / ".claude/skills/qa/SKILL.md").write_text("Skill.\n", encoding="utf-8")
            (base / ".claude/skills/.cache").mkdir()
            (base / ".claude/skills/.cache/x.md").write_text("Derived.\n", encoding="utf-8")
            (base / "docs/.knowledge").mkdir(parents=True)
            (base / "docs/.knowledge/x.md").write_text("Derived.\n", encoding="utf-8")
            nodes, _ = idoc.ingest_root(base / ".claude/skills", "briefs", base)
            self.assertEqual([n["path"] for n in nodes], [".claude/skills/qa/SKILL.md"])
            self.assertEqual(idoc.ingest_root(base / "docs", "docs", base)[0], [])


if __name__ == "__main__":
    unittest.main()
