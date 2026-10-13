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


def _adr(base, num, title, extra, body):
    d = base / "docs/architecture/decisions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"ADR-{num}-x.md").write_text(
        f"---\ntitle: \"{title}\"\nai-trust: working\n{extra}---\n\n{body}\n", encoding="utf-8")


def _build_superseded(base):
    """ADR-0001 is superseded by ADR-0002; a guide links to both; a story
    traces to the old decision only."""
    import ingest
    # written as the ADR template writes it, with a comment after the value
    _adr(base, "0001", "Queue on a cron", "status: superseded   # replaced by ADR-0002\n",
         "The pigeon queue runs on a cron.")
    _adr(base, "0002", "Queue on events", "status: approved\nsupersedes: [ADR-0001]\n",
         "The pigeon queue runs on events.")
    (base / "docs/guide.md").write_text(
        "---\ntitle: Guide\nstatus: approved\n---\n\n"
        "See [old](architecture/decisions/ADR-0001-x.md) and "
        "[new](architecture/decisions/ADR-0002-x.md).\n", encoding="utf-8")
    s = base / "docs/product/stories"
    s.mkdir(parents=True)
    (s / "AS-0001.md").write_text(
        "---\ntitle: Story\nstatus: approved\ntraces: [ADR-0001]\n---\n\nbody\n", encoding="utf-8")
    data = {"namespaces": {"docs": {"kind": "docs", "db": "docs/.knowledge/graph.db",
                                    "roots": ["docs/"]}},
            "overlay": "docs/knowledge/.knowledge/global.db"}
    ingest.build(data=data, base=base)
    return data


class SupersededTests(unittest.TestCase):
    def test_search_leaves_superseded_out_unless_asked(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _build_superseded(base)
            fed = q.open_federated(data=data, base=base)
            ids = {h["id"] for h in q.search(fed, "pigeon queue")}
            self.assertEqual(ids, {"adr:ADR-0002"})
            ids = {h["id"] for h in q.search(fed, "pigeon queue", include_superseded=True)}
            self.assertEqual(ids, {"adr:ADR-0001", "adr:ADR-0002"})

    def test_trace_keeps_only_the_supersedes_edge_to_a_superseded_document(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _build_superseded(base)
            fed = q.open_federated(data=data, base=base)
            res = q.trace(fed, "ADR-0002")
            ids = {n["id"] for n in res["nodes"]}
            self.assertNotIn("adr:ADR-0001", ids)
            self.assertNotIn("story:AS-0001", ids)  # reachable only through the old ADR
            self.assertIn("doc:docs:docs/guide.md", ids)
            touching = {(e["src"], e["kind"]) for e in res["edges"] if e["dst"] == "adr:ADR-0001"}
            self.assertEqual(touching, {("adr:ADR-0002", "supersedes")})
            self.assertEqual(res["superseded"], ["adr:ADR-0001"])

    def test_trace_with_include_superseded_is_the_whole_chain(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _build_superseded(base)
            fed = q.open_federated(data=data, base=base)
            res = q.trace(fed, "ADR-0002", include_superseded=True)
            ids = {n["id"] for n in res["nodes"]}
            self.assertLessEqual({"adr:ADR-0001", "story:AS-0001"}, ids)
            self.assertNotIn("superseded", res)

    def test_a_superseded_document_named_as_the_root_is_traced(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); data = _build_superseded(base)
            fed = q.open_federated(data=data, base=base)
            res = q.trace(fed, "ADR-0001", max_depth=1)
            ids = {n["id"] for n in res["nodes"]}
            self.assertLessEqual({"adr:ADR-0001", "adr:ADR-0002", "story:AS-0001"}, ids)
            self.assertNotIn("superseded", res)

    def test_an_issue_with_that_status_is_not_a_superseded_document(self):
        self.assertFalse(q.is_superseded({"kind": "issue", "meta": {"status": "superseded"}}))
        self.assertTrue(q.is_superseded({"kind": "doc", "meta": {"status": "Superseded "}}))


if __name__ == "__main__":
    unittest.main()
