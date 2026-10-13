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

    def test_issue_key_pattern(self):
        ns = lambda **kw: {"kind": "issues", "db": "x.db", "roots": ["i.csv"], **kw}
        self.assertEqual(m.issue_key_pattern({"namespaces": {}}), m.ISSUE_KEY)
        self.assertEqual(m.issue_key_pattern({"namespaces": {"issues": ns()}}), m.ISSUE_KEY)
        custom = r"E\d+-S\d+"
        self.assertEqual(m.issue_key_pattern({"namespaces": {"issues": ns(key_pattern=custom)}}),
                         custom)
        # a key_pattern on a namespace that is not a ledger is not read
        self.assertEqual(m.issue_key_pattern(
            {"namespaces": {"docs": {"kind": "docs", "key_pattern": custom}}}), m.ISSUE_KEY)
        both = m.issue_key_pattern({"namespaces": {"a": ns(), "b": ns(key_pattern=custom)}})
        import re
        self.assertTrue(re.fullmatch(both, "PROJ-1") and re.fullmatch(both, "E03-S08"))
        self.assertIsNone(re.fullmatch(both, "E03-S08-extra"))

    def test_a_key_pattern_that_is_not_a_regular_expression_is_an_error(self):
        with self.assertRaises(ValueError) as ctx:
            m.issue_key_pattern({"namespaces": {"issues": {"kind": "issues", "key_pattern": "E(\\d+"}}})
        self.assertIn("issues", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
