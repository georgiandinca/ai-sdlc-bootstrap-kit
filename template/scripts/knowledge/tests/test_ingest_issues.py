import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tempfile, unittest
import ingest_issues

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

    def test_blank_key_skipped_and_missing_file(self):
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            csv_path = self._write(base, ",Story,No key,To Do,,,,,,,,,,,,,\n")
            nodes, edges = ingest_issues.ingest_root(csv_path, "issues", base)
            self.assertEqual(nodes, [])
            missing = base / "docs/product/jira/none.csv"
            self.assertEqual(ingest_issues.ingest_root(missing, "issues", base), ([], []))


if __name__ == "__main__":
    unittest.main()
