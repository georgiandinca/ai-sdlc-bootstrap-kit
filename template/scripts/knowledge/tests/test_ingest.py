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


if __name__ == "__main__":
    unittest.main()
