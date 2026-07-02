import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json, tempfile, unittest
import manifest as m


class ManifestTests(unittest.TestCase):
    def test_load_missing_returns_defaults(self):
        data = m.load(Path(tempfile.gettempdir()) / "no-such-manifest-xyz.json")
        self.assertEqual(data["namespaces"], {})
        self.assertIn("overlay", data)

    def test_roundtrip_and_resolution(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            data = {"namespaces": {
                        "docs": {"kind": "docs", "db": "docs/.knowledge/graph.db",
                                 "roots": ["docs/"]}},
                    "overlay": "docs/knowledge/.knowledge/global.db"}
            (base / "mf.json").write_text(json.dumps(data), encoding="utf-8")
            loaded = m.load(base / "mf.json")
            got = list(m.namespaces(loaded, base=base))
            self.assertEqual(len(got), 1)
            name, kind, db, roots = got[0]
            self.assertEqual(name, "docs")
            self.assertEqual(kind, "docs")
            self.assertEqual(db, base / "docs/.knowledge/graph.db")
            self.assertEqual(roots, [base / "docs/"])
            self.assertEqual(m.overlay_db(loaded, base=base),
                             base / "docs/knowledge/.knowledge/global.db")


if __name__ == "__main__":
    unittest.main()
