import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "commit_msg_ticket", HERE.parent / "git" / "commit_msg_ticket.py")
cmt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cmt)


def run(message, mode="block", pattern=None, branch="main"):
    """Run the hook on a message; return (exit code, the message afterwards)."""
    orig = (cmt.key_pattern, cmt.current_branch, sys.argv)
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "COMMIT_EDITMSG"
        path.write_text(message, encoding="utf-8")
        try:
            if pattern:
                cmt.key_pattern = lambda: pattern
            cmt.current_branch = lambda: branch
            sys.argv = ["commit_msg_ticket.py", "--mode", mode, str(path)]
            return cmt.main(), path.read_text(encoding="utf-8")
        finally:
            cmt.key_pattern, cmt.current_branch, sys.argv = orig


class KeyPatternTests(unittest.TestCase):
    def test_default_when_the_manifest_is_missing_or_sets_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(cmt.key_pattern(Path(d) / "none.json"), cmt.DEFAULT_KEY)
        self.assertEqual(cmt.key_pattern(), cmt.DEFAULT_KEY)  # the shipped manifest

    def test_read_from_the_issues_namespace(self):
        with tempfile.TemporaryDirectory() as d:
            mf = Path(d) / "graph-manifest.json"
            mf.write_text(json.dumps({"namespaces": {"issues": {
                "kind": "issues", "db": "x.db", "roots": [], "key_pattern": "E\\d+-S\\d+"}}}))
            self.assertEqual(cmt.key_pattern(mf), "E\\d+-S\\d+")

    def test_default_when_the_pattern_is_not_a_regular_expression(self):
        with tempfile.TemporaryDirectory() as d:
            mf = Path(d) / "graph-manifest.json"
            mf.write_text(json.dumps({"namespaces": {"issues": {
                "kind": "issues", "key_pattern": "E(\\d+"}}}))
            self.assertEqual(cmt.key_pattern(mf), cmt.DEFAULT_KEY)
            mf.write_text(json.dumps({"namespaces": {"issues": {
                "kind": "issues", "key_pattern": "(?i)e\\d+-s\\d+"}}}))
            self.assertEqual(cmt.key_pattern(mf), cmt.DEFAULT_KEY)


class HookTests(unittest.TestCase):
    def test_default_key(self):
        self.assertEqual(run("feat: x\n\nRefs: PROJ-12\n")[0], 0)
        self.assertEqual(run("feat: x\n")[0], 1)
        self.assertEqual(run("feat: x\n", mode="warn")[0], 0)
        self.assertEqual(run("chore: tidy [no-ticket]\n")[0], 0)

    def test_project_key(self):
        pattern = "E\\d+-S\\d+"
        self.assertEqual(run("feat: x (E03-S08)\n", pattern=pattern)[0], 0)
        self.assertEqual(run("feat: x (PROJ-12)\n", pattern=pattern)[0], 1)
        self.assertEqual(run("feat: x (XE03-S08)\n", pattern=pattern)[0], 1)  # inside a word
        self.assertEqual(run("fixes #12\n", pattern="#\\d+")[0], 0)  # starts with a non-word character
        self.assertEqual(run("fixes 12\n", pattern="#\\d+")[0], 1)

    def test_key_injected_from_the_branch_name(self):
        code, msg = run("feat: x\n", pattern="E\\d+-S\\d+", branch="feature/E03-S08-slug")
        self.assertEqual(code, 0)
        self.assertTrue(msg.endswith("Refs: E03-S08\n"))
        code, msg = run("feat: x\n", branch="feature/PROJ-7-slug")
        self.assertTrue(msg.endswith("Refs: PROJ-7\n"))


if __name__ == "__main__":
    unittest.main()
