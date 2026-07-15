#!/usr/bin/env python3
"""Unit tests for the AGENTS.md churn check (token-economy technique 2)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import importlib
churn = importlib.import_module("check-brief-churn")


def make_repo(tmp, commits):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp, check=True, capture_output=True,
                       env={"PATH": "/usr/bin:/bin:/usr/local/bin",
                            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                            "HOME": tmp})
    git("init", "-q")
    for i in range(commits):
        Path(tmp, "AGENTS.md").write_text(f"v{i}\n", encoding="utf-8")
        git("add", "AGENTS.md")
        git("commit", "-q", "-m", f"edit {i}")


class TestChurn(unittest.TestCase):
    def test_counts_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp, 4)
            self.assertEqual(churn.churn_count("AGENTS.md", days=14, cwd=tmp), 4)

    def test_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp, 4)
            self.assertEqual(churn.main(["--days", "14", "--warn", "3",
                                         "--max", "10", "--cwd", tmp]), 0)   # warn only
            self.assertEqual(churn.main(["--days", "14", "--warn", "1",
                                         "--max", "2", "--cwd", tmp]), 1)    # over max


if __name__ == "__main__":
    unittest.main()
