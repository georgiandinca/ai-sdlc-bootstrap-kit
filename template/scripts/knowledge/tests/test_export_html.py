import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json, tempfile, unittest
import export_html, ingest
from test_ingest import _fixture_repo, _fixture_repo_with_ghost


def _payload_from_html(html):
    start = html.index('<script id="graph-data" type="application/json">') + len(
        '<script id="graph-data" type="application/json">')
    return json.loads(html[start:html.index("</script>", start)])


class ExportHtmlTests(unittest.TestCase):
    def test_collect_merges_namespaces_and_overlay(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _fixture_repo(base)
            ingest.build(data=data, base=base)
            p = export_html.collect(data=data, base=base)
            ids = {n["id"] for n in p["nodes"]}
            self.assertLessEqual({"adr:ADR-0001", "story:AS-0001", "code:kit:src/thing.py"}, ids)
            self.assertEqual(p["namespaces"], ["docs", "kit"])
            impl = [e for e in p["edges"] if e["kind"] == "implements"
                    and e["src"] == "code:kit:src/thing.py"]
            self.assertEqual(impl[0]["resolved"], 1)          # cross-namespace edge from the overlay
            self.assertEqual((impl[0]["file"], impl[0]["line"]), ("src/thing.py", 1))
            adr = next(n for n in p["nodes"] if n["id"] == "adr:ADR-0001")
            self.assertEqual(adr["tier"], "working")
            self.assertNotIn("missing", {n["kind"] for n in p["nodes"]})

    def test_unresolved_edge_gets_a_missing_placeholder(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _fixture_repo_with_ghost(base)
            ingest.build(data=data, base=base)
            p = export_html.collect(data=data, base=base)
            ghost = [n for n in p["nodes"] if n["id"] == "adr:ADR-0099"]
            self.assertEqual([n["kind"] for n in ghost], ["missing"])
            dangling = [e for e in p["edges"] if e["dst"] == "adr:ADR-0099"]
            self.assertTrue(dangling)
            self.assertTrue(all(e["resolved"] == 0 for e in dangling))

    def test_render_embeds_payload_without_breaking_out_of_the_script(self):
        payload = {"nodes": [{"id": "doc:x", "kind": "doc", "ns": "docs",
                              "name": "</script><script>alert(1)</script>"}],
                   "edges": [], "namespaces": ["docs"], "built": None}
        html = export_html.render(payload)
        self.assertNotIn("</script><script>alert(1)", html)
        self.assertEqual(_payload_from_html(html), payload)   # round-trips unchanged

    def test_render_rejects_a_template_without_the_marker(self):
        with self.assertRaises(ValueError):
            export_html.render({"nodes": []}, template="<html></html>")


if __name__ == "__main__":
    unittest.main()
