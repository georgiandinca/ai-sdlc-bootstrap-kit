# scripts/knowledge/tests/test_end_to_end.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json, tempfile, unittest
import ingest, query as q
import mcp_server


def _fixture(base):
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
    return {"namespaces": {
                "docs": {"kind": "docs", "db": "docs/.knowledge/graph.db", "roots": ["docs/"]},
                "kit":  {"kind": "code", "db": ".knowledge/graph.db", "roots": ["src/"]}},
            "overlay": "docs/knowledge/.knowledge/global.db"}


class EndToEndTests(unittest.TestCase):
    def test_build_query_via_mcp_tool_call(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            data = _fixture(base)
            ingest.build(data=data, base=base)
            # route the MCP server's federated open at our fixture graph
            orig = mcp_server.query_mod.open_federated
            mcp_server.query_mod.open_federated = (
                lambda data=None, base=None: orig(data=_DATA, base=_BASE))
            global _DATA, _BASE
            _DATA, _BASE = data, base
            try:
                req = {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                       "params": {"name": "kg_trace", "arguments": {"id": "adr:ADR-0001"}}}
                resp = mcp_server.handle(req)
                payload = json.loads(resp["result"]["content"][0]["text"])
            finally:
                mcp_server.query_mod.open_federated = orig
            ids = {n["id"] for n in payload["nodes"]}
            self.assertIn("code:kit:src/thing.py", ids)
            self.assertIn("test:kit:src/tests/test_thing.py", ids)
            self.assertIn("story:AS-0001", ids)
            impl = [e for e in payload["edges"]
                    if e["kind"] == "implements" and e["dst"] == "adr:ADR-0001"]
            self.assertTrue(impl and impl[0]["resolved"] == 1)
            self.assertEqual(impl[0]["source_file"], "src/thing.py")  # citation present


if __name__ == "__main__":
    unittest.main()
