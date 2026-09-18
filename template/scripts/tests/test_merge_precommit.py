#!/usr/bin/env python3
"""Unit tests for merge-precommit.py (hooks mode `repo`)."""
import importlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
merge = importlib.import_module("merge-precommit")

import yaml

SOURCE = """\
default_install_hook_types: [pre-commit, commit-msg]
repos:
  - repo: local
    hooks:
      - id: validate-skills
        name: Validate SKILL.md
        entry: python scripts/validate-skills.py
        language: python
        files: (^|/)SKILL\\.md$
      - id: commit-msg-ticket
        name: Commit message references an issue key
        entry: python scripts/git/commit_msg_ticket.py --mode warn
        language: python
        stages: [commit-msg]
"""

TARGET = """\
# our own hooks
repos:
  - repo: https://github.com/psf/black
    rev: 24.1.0
    hooks:
      - id: black
"""


class TestMergePreCommit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.src = self.d / "source.yaml"
        self.dst = self.d / "target.yaml"
        self.src.write_text(SOURCE, encoding="utf-8")
        self.dst.write_text(TARGET, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def load(self):
        return yaml.safe_load(self.dst.read_text(encoding="utf-8"))

    def hook_ids(self):
        return [h["id"] for r in self.load()["repos"] for h in r["hooks"]]

    def test_adds_kit_hooks_and_keeps_existing(self):
        merge.merge(self.dst, self.src, prefix="../acme-sdlc")
        ids = self.hook_ids()
        self.assertIn("black", ids)
        self.assertIn("validate-skills", ids)
        self.assertIn("commit-msg-ticket", ids)

    def test_rewrites_entry_paths_with_prefix(self):
        merge.merge(self.dst, self.src, prefix="../acme-sdlc")
        entries = [h.get("entry", "") for r in self.load()["repos"] for h in r["hooks"]]
        self.assertIn("python ../acme-sdlc/scripts/validate-skills.py", entries)

    def test_is_idempotent(self):
        merge.merge(self.dst, self.src, prefix="../acme-sdlc")
        first = self.hook_ids()
        merge.merge(self.dst, self.src, prefix="../acme-sdlc")
        self.assertEqual(first, self.hook_ids())

    def test_preserves_install_hook_types(self):
        merge.merge(self.dst, self.src, prefix="../acme-sdlc")
        self.assertEqual(
            self.load().get("default_install_hook_types"), ["pre-commit", "commit-msg"]
        )

    def test_dry_run_changes_nothing(self):
        before = self.dst.read_text(encoding="utf-8")
        merge.merge(self.dst, self.src, prefix="../acme-sdlc", dry_run=True)
        self.assertEqual(before, self.dst.read_text(encoding="utf-8"))

    def test_writes_backup(self):
        backup = self.d / "backup.yaml"
        merge.merge(self.dst, self.src, prefix="../acme-sdlc", backup=backup)
        self.assertEqual(backup.read_text(encoding="utf-8"), TARGET)

    def test_unparseable_target_exits_2(self):
        self.dst.write_text("repos: [unclosed\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(Path(merge.__file__)), str(self.dst), str(self.src)],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
