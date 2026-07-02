#!/usr/bin/env python3
"""Functional test for collect_commits.py: classifies human / ai-assisted / mixed."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

MOD = Path(__file__).resolve().parent.parent / "collect_commits.py"
spec = importlib.util.spec_from_file_location("collect_commits", MOD)
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

NOTE = """foo.py
  s_aaaaaaaaaaaaaa::t_bbbbbbbbbbbbbb 1-10
  h_cccccccccccccc 11-14
---
{"schema_version":"authorship/3.0.0","base_commit_sha":"x","prompts":{},"sessions":{"s_aaaaaaaaaaaaaa":{"agent_id":{"tool":"claude","id":"c","model":"m"},"human_author":"d@e.com"}},"humans":{"h_cccccccccccccc":{"author":"D <d@e.com>"}}}"""


def git(repo, *args, **kw):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, **kw)


class CollectTests(unittest.TestCase):
    def test_parse_note_counts_ai_and_human(self):
        ai, human, tool = cc.parse_note(NOTE)
        self.assertEqual(ai, 10)      # s_ key range 1-10
        self.assertEqual(human, 4)    # h_ key range 11-14
        self.assertEqual(tool, "claude")

    def test_classify(self):
        self.assertEqual(cc.classify(10, 0, True, False)[0], "ai")
        self.assertEqual(cc.classify(10, 4, True, False)[0], "mixed")
        self.assertEqual(cc.classify(0, 0, False, True)[0], "ai-assisted")
        self.assertEqual(cc.classify(0, 0, False, False)[0], "human")

    def test_end_to_end_three_commits(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"; repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "h@e.com"); git(repo, "config", "user.name", "Human")
            # 1) human commit (no trailer)
            (repo / "a.py").write_text("x = 1\n")
            git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "plain human change")
            # 2) AI-trailer commit
            (repo / "b.py").write_text("y = 2\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "add b\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
            # 3) commit with a synthetic git-ai note
            (repo / "foo.py").write_text("\n".join(f"L{i}" for i in range(1, 15)) + "\n")
            git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "add foo")
            sha3 = git(repo, "rev-parse", "HEAD").stdout.strip()
            git(repo, "notes", "--ref=ai", "add", "-m", NOTE, sha3)
            dbp = Path(d) / "u.db"
            rows, summary = cc.collect(repo=str(repo), since=None, db_path=dbp)
            self.assertEqual(rows, 3)
            import sqlite3
            con = sqlite3.connect(dbp)
            by = dict(con.execute("SELECT subject, klass FROM commits").fetchall())
            self.assertEqual(by["plain human change"], "human")
            self.assertEqual(by["add b"], "ai-assisted")
            self.assertEqual(by["add foo"], "mixed")   # ai 10 + human 4
            ai_lines = con.execute("SELECT ai_lines FROM commits WHERE subject='add foo'").fetchone()[0]
            self.assertEqual(ai_lines, 10)
            con.close()


if __name__ == "__main__":
    unittest.main()
