import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json, tempfile, unittest
import graph_store as gs
import query as q


def _build_fixture(base):
    """Two namespace DBs (docs, kit) + an overlay with the cross-ns implements edge."""
    data = {"namespaces": {
                "docs": {"kind": "docs", "db": "docs/.knowledge/graph.db", "roots": ["docs/"]},
                "kit":  {"kind": "code", "db": ".knowledge/graph.db", "roots": ["src/"]}},
            "overlay": "docs/knowledge/.knowledge/global.db"}
    docs_db = base / "docs/.knowledge/graph.db"
    kit_db = base / ".knowledge/graph.db"
    ov_db = base / "docs/knowledge/.knowledge/global.db"
    dc = gs.connect(docs_db)
    gs.add_node(dc, {"id": "adr:ADR-0001", "kind": "adr", "name": "Adopt graph",
                     "path": "docs/architecture/decisions/ADR-0001.md",
                     "text": "knowledge graph decision", "namespace": "docs"})
    gs.add_node(dc, {"id": "story:AS-0001", "kind": "story", "name": "Story",
                     "path": "docs/product/stories/AS-0001.md", "namespace": "docs"})
    gs.add_edge(dc, {"src": "story:AS-0001", "dst": "adr:ADR-0001", "kind": "traces",
                     "source_file": "docs/product/stories/AS-0001.md", "namespace": "docs"})
    dc.commit(); dc.close()
    kc = gs.connect(kit_db)
    gs.add_node(kc, {"id": "code:kit:src/graph_store.py", "kind": "code-file",
                     "name": "graph_store.py", "path": "src/graph_store.py", "namespace": "kit"})
    gs.add_node(kc, {"id": "test:kit:src/test_graph_store.py", "kind": "test",
                     "name": "test_graph_store.py", "path": "src/test_graph_store.py",
                     "namespace": "kit"})
    gs.add_edge(kc, {"src": "test:kit:src/test_graph_store.py",
                     "dst": "code:kit:src/graph_store.py", "kind": "covers",
                     "source_file": "src/test_graph_store.py", "namespace": "kit"})
    kc.commit(); kc.close()
    oc = gs.connect(ov_db)
    gs.add_edge(oc, {"src": "code:kit:src/graph_store.py", "dst": "adr:ADR-0001",
                     "kind": "implements", "source_file": "src/graph_store.py",
                     "line": 2, "resolved": 1, "namespace": "global"})
    oc.commit(); oc.close()
    return data


class QueryTests(unittest.TestCase):
    def test_scoped_vs_federated_visibility(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _build_fixture(base)
            kg = q.open_scoped("kit", data=data, base=base)
            self.assertIsNone(q.get_node(kg, "adr:ADR-0001"))  # docs ns not attached
            self.assertIsNotNone(q.get_node(kg, "code:kit:src/graph_store.py"))
            fed = q.open_federated(data=data, base=base)
            self.assertIsNotNone(q.get_node(fed, "adr:ADR-0001"))

    def test_search_matches_text(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _build_fixture(base)
            fed = q.open_federated(data=data, base=base)
            hits = q.search(fed, "knowledge graph decision")
            self.assertTrue(any(h["id"] == "adr:ADR-0001" for h in hits))

    def test_trace_assembles_chain_with_citations(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _build_fixture(base)
            fed = q.open_federated(data=data, base=base)
            res = q.trace(fed, "adr:ADR-0001")
            node_ids = {n["id"] for n in res["nodes"]}
            self.assertIn("code:kit:src/graph_store.py", node_ids)   # implements
            self.assertIn("test:kit:src/test_graph_store.py", node_ids)  # covers
            self.assertIn("story:AS-0001", node_ids)                 # traces
            impl = [e for e in res["edges"] if e["kind"] == "implements"][0]
            self.assertEqual(impl["source_file"], "src/graph_store.py")
            self.assertEqual(impl["line"], 2)

    def test_trace_accepts_shorthand_ids(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _build_fixture(base)
            fed = q.open_federated(data=data, base=base)
            # Trace using shorthand ref
            res_shorthand = q.trace(fed, "ADR-0001")
            # Trace using full node id
            res_full = q.trace(fed, "adr:ADR-0001")
            # Both should return the same nodes
            node_ids_shorthand = {n["id"] for n in res_shorthand["nodes"]}
            node_ids_full = {n["id"] for n in res_full["nodes"]}
            self.assertEqual(node_ids_shorthand, node_ids_full)
            # And both should be non-empty (contain at least the root)
            self.assertTrue(len(node_ids_shorthand) > 0)
            self.assertIn("adr:ADR-0001", node_ids_shorthand)


if __name__ == "__main__":
    unittest.main()
