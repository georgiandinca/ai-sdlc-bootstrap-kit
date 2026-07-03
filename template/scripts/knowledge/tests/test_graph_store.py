import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sqlite3, tempfile, unittest
import graph_store as gs


class GraphStoreTests(unittest.TestCase):
    def test_schema_idempotent(self):
        conn = sqlite3.connect(":memory:")
        gs.ensure_schema(conn)
        gs.ensure_schema(conn)  # second call must not raise
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("nodes", names)
        self.assertIn("edges", names)

    def test_add_and_replace_node(self):
        conn = sqlite3.connect(":memory:"); gs.ensure_schema(conn)
        gs.add_node(conn, {"id": "adr:ADR-0001", "kind": "adr", "name": "x",
                           "namespace": "docs", "meta": {"a": 1}})
        gs.add_node(conn, {"id": "adr:ADR-0001", "kind": "adr", "name": "y",
                           "namespace": "docs"})  # replace
        rows = conn.execute("SELECT name, meta FROM nodes WHERE id=?",
                            ("adr:ADR-0001",)).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "y")
        self.assertEqual(rows[0][1], "{}")  # meta defaults to {} json

    def test_add_edge_defaults_resolved(self):
        conn = sqlite3.connect(":memory:"); gs.ensure_schema(conn)
        gs.add_edge(conn, {"src": "a", "dst": "b", "kind": "implements",
                           "namespace": "global"})
        r = conn.execute("SELECT resolved FROM edges").fetchone()
        self.assertEqual(r[0], 1)

    def test_id_helpers_and_normalize(self):
        self.assertEqual(gs.adr_id("ADR-0001"), "adr:ADR-0001")
        self.assertEqual(gs.code_id("kit", "a/b.py"), "code:kit:a/b.py")
        self.assertEqual(gs.symbol_id("kit", "a.py", "f"), "sym:kit:a.py:f")
        self.assertEqual(gs.normalize_ref("ADR-0003"), "adr:ADR-0003")
        self.assertEqual(gs.normalize_ref("AS-2"), "story:AS-2")
        self.assertEqual(gs.normalize_ref("scripts/x.py"), "path:scripts/x.py")
        self.assertEqual(gs.issue_id("PROJ-123"), "issue:PROJ-123")
        self.assertEqual(gs.normalize_ref("PROJ-123"), "issue:PROJ-123")
        self.assertEqual(gs.normalize_ref("AS-2"), "story:AS-2")      # story wins over issue
        self.assertEqual(gs.normalize_ref("ADR-0003"), "adr:ADR-0003")  # adr wins over issue


if __name__ == "__main__":
    unittest.main()
