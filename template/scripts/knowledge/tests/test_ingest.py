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
