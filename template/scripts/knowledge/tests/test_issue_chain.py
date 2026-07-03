import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sqlite3, subprocess, tempfile, unittest
import ingest, query as q


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


class IssueChainTests(unittest.TestCase):
    def test_issue_links_to_commit_code_and_story(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "docs/product/stories").mkdir(parents=True)
            (base / "docs/product/stories/AS-0001-x.md").write_text(
                '---\ntitle: "Story"\ntraces: [PROJ-1]\n---\nAs a user.\n', encoding="utf-8")
            (base / "src").mkdir(parents=True)
            (base / "src/thing.py").write_text("def go():\n    return 1\n", encoding="utf-8")
            _git(base, "init", "-q")
            _git(base, "config", "user.email", "a@b.c")
            _git(base, "config", "user.name", "T")
            _git(base, "add", "-A")
            _git(base, "commit", "-q", "-m", "feat: thing\n\nRefs: PROJ-1")
            sha = _git(base, "rev-parse", "HEAD").stdout.strip()
            dash = base / "dashboard" / "utilization.db"
            dash.parent.mkdir(parents=True)
            con = sqlite3.connect(dash)
            con.execute("CREATE TABLE commits (sha TEXT, klass TEXT)")
            con.execute("INSERT INTO commits VALUES (?, 'ai')", (sha,))
            con.commit(); con.close()
            (base / "docs/product/jira").mkdir(parents=True)
            (base / "docs/product/jira/issues.csv").write_text(
                "key,type,title,status,assignee,reporter,labels,sprint,epic,parent,"
                "priority,story_points,created,updated,resolution,url,description\n"
                "PROJ-1,Story,Do the thing,In Progress,,,,,,,,,,,,,\n", encoding="utf-8")
            data = {"namespaces": {
                        "docs": {"kind": "docs", "db": "docs/.knowledge/graph.db", "roots": ["docs/"]},
                        "kit": {"kind": "code", "db": ".knowledge/graph.db", "roots": ["src/"]},
                        "issues": {"kind": "issues",
                                   "db": "docs/product/jira/.knowledge/graph.db",
                                   "roots": ["docs/product/jira/issues.csv"]}},
                    "overlay": "docs/knowledge/.knowledge/global.db"}
            orig = ingest.DASHBOARD_DB
            ingest.DASHBOARD_DB = dash
            try:
                ingest.build(data=data, base=base)
                kg = q.open_federated(data=data, base=base)
                res = q.trace(kg, "issue:PROJ-1")
            finally:
                ingest.DASHBOARD_DB = orig
            ids = {n["id"] for n in res["nodes"]}
            self.assertIn("issue:PROJ-1", ids)
            self.assertIn("story:AS-0001", ids)             # doc -> issue via traces
            self.assertIn("code:kit:src/thing.py", ids)     # issue -> commit -> code
            refs = [e for e in res["edges"]
                    if e["kind"] == "references" and e["dst"] == "issue:PROJ-1"]
            self.assertTrue(refs and refs[0]["resolved"] == 1)


if __name__ == "__main__":
    unittest.main()
