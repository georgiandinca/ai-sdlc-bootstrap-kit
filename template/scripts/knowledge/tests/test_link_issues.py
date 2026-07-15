import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import subprocess, tempfile, unittest
import link_issues as li


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


class LinkIssuesTests(unittest.TestCase):
    def test_no_commit_nodes_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(li.link("kit", [], Path(d)), [])

    def test_references_edge_from_commit_message(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            _git(base, "init", "-q")
            _git(base, "config", "user.email", "a@b.c")
            _git(base, "config", "user.name", "T")
            (base / "f.py").write_text("x = 1\n")
            _git(base, "add", "-A")
            _git(base, "commit", "-q", "-m", "feat: thing\n\nRefs: PROJ-1 PROJ-1 PROJ-2")
            sha = _git(base, "rev-parse", "HEAD").stdout.strip()
            commit_nodes = [{"id": f"commit:kit:{sha}", "meta": {"sha": sha}}]
            edges = li.link("kit", commit_nodes, base)
            pairs = {(e["src"], e["dst"], e["kind"]) for e in edges}
            self.assertIn((f"commit:kit:{sha}", "issue:PROJ-1", "references"), pairs)
            self.assertIn((f"commit:kit:{sha}", "issue:PROJ-2", "references"), pairs)
            self.assertEqual(len(edges), 2)  # PROJ-1 de-duplicated


if __name__ == "__main__":
    unittest.main()
