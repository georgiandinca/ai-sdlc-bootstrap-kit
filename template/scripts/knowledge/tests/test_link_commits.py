import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sqlite3, subprocess, tempfile, unittest
import link_commits as lc


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


class LinkCommitsTests(unittest.TestCase):
    def test_absent_db_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            out = lc.link("kit", [], Path(d) / "nope.db", Path(d))
            self.assertEqual(out, ([], [], {}))

    def test_touches_and_attribution(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            _git(base, "init", "-q")
            _git(base, "config", "user.email", "a@b.c")
            _git(base, "config", "user.name", "T")
            (base / "foo.py").write_text("x = 1\n")
            _git(base, "add", "-A"); _git(base, "commit", "-q", "-m", "add foo")
            sha = _git(base, "rev-parse", "HEAD").stdout.strip()
            db = base / "dash.db"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE commits (sha TEXT, klass TEXT)")
            con.execute("INSERT INTO commits VALUES (?, 'ai')", (sha,))
            con.commit(); con.close()
            code_nodes = [{"id": "code:kit:foo.py", "path": "foo.py"}]
            nodes, edges, attrib = lc.link("kit", code_nodes, db, base)
            self.assertEqual(len(nodes), 1)
            self.assertEqual(nodes[0]["kind"], "commit")
            self.assertEqual(edges[0]["kind"], "touches")
            self.assertEqual(edges[0]["dst"], "code:kit:foo.py")
            self.assertEqual(attrib["code:kit:foo.py"]["ai_commits"], 1)


if __name__ == "__main__":
    unittest.main()
