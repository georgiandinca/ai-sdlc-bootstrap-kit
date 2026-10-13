import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tempfile, unittest
import ingest_issues
import ingest

HEADER = ("key,type,title,status,assignee,reporter,labels,sprint,epic,parent,"
          "priority,story_points,created,updated,resolution,url,description\n")


class IngestIssuesTests(unittest.TestCase):
    def _write(self, base, body):
        d = base / "docs/product/jira"
        d.mkdir(parents=True)
        (d / "issues.csv").write_text(HEADER + body, encoding="utf-8")
        return d / "issues.csv"

    def test_nodes_and_part_of(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            csv_path = self._write(
                base,
                "PROJ-1,Epic,Ledger epic,In Progress,Ada,Grace,plat;kg,S3,,,High,,,,,,An epic.\n"
                "PROJ-2,Story,Child story,To Do,Ada,Grace,kg,S3,PROJ-1,PROJ-1,Medium,3,,,,,Child.\n")
            nodes, edges = ingest_issues.ingest_root(csv_path, "issues", base)
            byid = {n["id"]: n for n in nodes}
            self.assertEqual(byid["issue:PROJ-1"]["kind"], "issue")
            self.assertEqual(byid["issue:PROJ-1"]["name"], "Ledger epic")
            self.assertEqual(byid["issue:PROJ-1"]["path"], "docs/product/jira/issues.csv")
            self.assertEqual(byid["issue:PROJ-2"]["meta"]["labels"], "kg")
            self.assertEqual(byid["issue:PROJ-2"]["subtype"], "Story")
            po = [e for e in edges if e["kind"] == "part-of"]
            self.assertIn(("issue:PROJ-2", "issue:PROJ-1"),
                          {(e["src"], e["dst"]) for e in po})
            self.assertEqual(po[0]["source_file"], "docs/product/jira/issues.csv")

    def test_depends_on_column_gives_one_edge_per_key(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            d = base / "docs/product/jira"
            d.mkdir(parents=True)
            (d / "issues.csv").write_text(
                "key,title,depends_on\n"
                "PROJ-1,First,\n"
                "PROJ-2,Second,PROJ-1\n"
                "PROJ-3,Third,PROJ-1  PROJ-2 PROJ-2 PROJ-3 PROJ-99\n", encoding="utf-8")
            nodes, edges = ingest_issues.ingest_root(d / "issues.csv", "issues", base)
            deps = [(e["src"], e["dst"]) for e in edges if e["kind"] == "depends-on"]
            self.assertEqual(deps, [("issue:PROJ-2", "issue:PROJ-1"),
                                    ("issue:PROJ-3", "issue:PROJ-1"),
                                    ("issue:PROJ-3", "issue:PROJ-2"),
                                    ("issue:PROJ-3", "issue:PROJ-99")])  # no repeat, no self
            self.assertEqual({n["id"]: n for n in nodes}["issue:PROJ-3"]["meta"]["depends_on"],
                             "PROJ-1  PROJ-2 PROJ-2 PROJ-3 PROJ-99")

    def test_a_ledger_without_the_column_has_no_depends_on_edges(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            csv_path = self._write(base, "PROJ-2,Story,Child,To Do,,,,,PROJ-1,,,,,,,,\n")
            nodes, edges = ingest_issues.ingest_root(csv_path, "issues", base)
            self.assertEqual({e["kind"] for e in edges}, {"part-of"})
            self.assertEqual(nodes[0]["meta"]["depends_on"], "")

    def test_build_resolves_a_dependency_in_the_ledger_and_reports_one_that_is_not(self):
        import query
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            d = base / "docs/product/jira"
            d.mkdir(parents=True)
            (d / "issues.csv").write_text(
                "key,title,depends_on\nPROJ-1,First,\nPROJ-2,Second,PROJ-1 PROJ-99\n",
                encoding="utf-8")
            data = {"namespaces": {
                        "issues": {"kind": "issues",
                                   "db": "docs/product/jira/.knowledge/graph.db",
                                   "roots": ["docs/product/jira/issues.csv"]}},
                    "overlay": "docs/knowledge/.knowledge/global.db"}
            ingest.build(data=data, base=base)
            res = query.trace(query.open_federated(data=data, base=base), "issue:PROJ-2", max_depth=1)
            got = {(e["dst"], e["resolved"]) for e in res["edges"] if e["kind"] == "depends-on"}
            self.assertEqual(got, {("issue:PROJ-1", 1), ("issue:PROJ-99", 0)})

    def test_blank_key_skipped_and_missing_file(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            csv_path = self._write(base, ",Story,No key,To Do,,,,,,,,,,,,,\n")
            nodes, edges = ingest_issues.ingest_root(csv_path, "issues", base)
            self.assertEqual(nodes, [])
            missing = base / "docs/product/jira/none.csv"
            self.assertEqual(ingest_issues.ingest_root(missing, "issues", base), ([], []))

    def test_build_registers_issue_namespace(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            self._write(
                base,
                "PROJ-1,Epic,Root,In Progress,,,,,,,,,,,,,\n"
                "PROJ-2,Story,Child,To Do,,,,,PROJ-1,,,,,,,,\n")
            data = {"namespaces": {
                        "issues": {"kind": "issues",
                                   "db": "docs/product/jira/.knowledge/graph.db",
                                   "roots": ["docs/product/jira/issues.csv"]}},
                    "overlay": "docs/knowledge/.knowledge/global.db"}
            stats = ingest.build(data=data, base=base)
            names = [n for n, *_ in stats["namespaces"]]
            self.assertIn("issues", names)
            counts = {n: nn for n, nn, ne in stats["namespaces"]}
            self.assertEqual(counts["issues"], 2)


class ProjectKeyPatternTests(unittest.TestCase):
    def _build(self, base, key_pattern=None):
        d = base / "docs/product/jira"
        d.mkdir(parents=True)
        (d / "issues.csv").write_text("key,title\nE03-S08,Story eight\nstory42,Odd key\n",
                                      encoding="utf-8")
        (base / "docs/note.md").write_text(
            "---\ntitle: Note\ntraces: [E03-S08]\n---\n\nbody\n", encoding="utf-8")
        issues = {"kind": "issues", "db": "docs/product/jira/.knowledge/graph.db",
                  "roots": ["docs/product/jira/issues.csv"]}
        if key_pattern:
            issues["key_pattern"] = key_pattern
        data = {"namespaces": {
                    "docs": {"kind": "docs", "db": "docs/.knowledge/graph.db", "roots": ["docs/"]},
                    "issues": issues},
                "overlay": "docs/knowledge/.knowledge/global.db"}
        ingest.build(data=data, base=base)
        import query
        return query.open_federated(data=data, base=base)

    def test_a_frontmatter_ref_in_the_project_pattern_links_to_the_issue(self):
        import query
        with tempfile.TemporaryDirectory() as t:
            kg = self._build(Path(t), r"E\d+-S\d+")
            res = query.trace(kg, "E03-S08", max_depth=1)  # a bare key
            self.assertEqual(res["root"], "issue:E03-S08")
            self.assertIn(("doc:docs:docs/note.md", "issue:E03-S08", "traces", 1),
                          {(e["src"], e["dst"], e["kind"], e["resolved"]) for e in res["edges"]})

    def test_without_the_pattern_the_ref_stays_a_literal(self):
        import query
        with tempfile.TemporaryDirectory() as t:
            kg = self._build(Path(t))
            res = query.trace(kg, "issue:E03-S08", max_depth=1)
            self.assertEqual(res["edges"], [])

    def test_a_bare_key_in_the_ledger_is_traced_whatever_the_pattern(self):
        import query
        with tempfile.TemporaryDirectory() as t:
            kg = self._build(Path(t))
            self.assertEqual(query.trace(kg, "story42")["root"], "issue:story42")
            self.assertEqual(query.trace(kg, "E03-S08")["root"], "issue:E03-S08")
            self.assertEqual(query.trace(kg, "nothing")["root"], "nothing")


if __name__ == "__main__":
    unittest.main()
