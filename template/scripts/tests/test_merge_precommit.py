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

    # --- fix-round 1, finding 1: a target with a valid-YAML but wrong shape
    # (not the AttributeError-then-traceback it used to raise) --------------
    def _assert_malformed_shape_exits_2(self, target_text):
        before = target_text
        self.dst.write_text(target_text, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(Path(merge.__file__)), str(self.dst), str(self.src)],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(self.dst.read_text(encoding="utf-8"), before)
        return proc

    def test_repos_as_string_exits_2(self):
        self._assert_malformed_shape_exits_2("repos: not-a-list\n")

    def test_repos_as_mapping_exits_2(self):
        self._assert_malformed_shape_exits_2("repos:\n  foo: bar\n")

    def test_hooks_not_a_list_exits_2(self):
        self._assert_malformed_shape_exits_2(
            "repos:\n  - repo: local\n    hooks: not-a-list\n"
        )

    def test_hook_entry_not_a_mapping_exits_2(self):
        self._assert_malformed_shape_exits_2(
            "repos:\n  - repo: local\n    hooks:\n      - just-a-string\n"
        )

    # --- fix-round 1, finding 2: a backup already on disk holds the
    # pre-merge original and must never be replaced by a later merge --------
    def test_second_merge_does_not_overwrite_existing_backup(self):
        backup = self.d / "backup.yaml"
        merge.merge(self.dst, self.src, prefix="../acme-sdlc", backup=backup)
        first_backup_content = backup.read_text(encoding="utf-8")
        self.assertEqual(first_backup_content, TARGET)

        # Simulate the kit gaining a brand-new hook after the first merge —
        # this run has something new to add, so it would try to back up
        # again if the guard were missing.
        extra_source = self.d / "source2.yaml"
        extra_source.write_text(
            SOURCE + "      - id: brand-new-hook\n        entry: python scripts/new.py\n"
                     "        language: python\n",
            encoding="utf-8",
        )
        merge.merge(self.dst, extra_source, prefix="../acme-sdlc", backup=backup)
        self.assertEqual(backup.read_text(encoding="utf-8"), first_backup_content)
        self.assertNotEqual(backup.read_text(encoding="utf-8"),
                             self.dst.read_text(encoding="utf-8"))


    # --- fix-round 2, finding 1: a target that does not exist yet is created
    # BY THE MERGE, so its entries get the same --prefix rewriting the merge
    # path applies. Copying the kit's file instead left every `entry:` as
    # `python scripts/…`, unresolvable from the code repo. ------------------
    def test_absent_target_is_created_with_prefix(self):
        absent = self.d / "nope" / "new-config.yaml"
        self.assertFalse(absent.exists())
        log = merge.merge(absent, self.src, prefix="../acme-sdlc")
        self.assertIn("added validate-skills", log)
        doc = yaml.safe_load(absent.read_text(encoding="utf-8"))
        entries = [h.get("entry", "") for r in doc["repos"] for h in r["hooks"]]
        self.assertIn("python ../acme-sdlc/scripts/validate-skills.py", entries)
        self.assertIn("python ../acme-sdlc/scripts/git/commit_msg_ticket.py --mode warn",
                      entries)
        self.assertNotIn("python scripts/validate-skills.py", entries)
        self.assertEqual(doc.get("default_install_hook_types"),
                         ["pre-commit", "commit-msg"])

    def test_absent_target_writes_no_backup(self):
        absent = self.d / "new-config.yaml"
        backup = self.d / "backup.yaml"
        merge.merge(absent, self.src, prefix="../acme-sdlc", backup=backup)
        self.assertTrue(absent.exists())
        self.assertFalse(backup.exists())

    def test_absent_target_second_run_is_idempotent(self):
        absent = self.d / "new-config.yaml"
        merge.merge(absent, self.src, prefix="../acme-sdlc")
        first = absent.read_text(encoding="utf-8")
        log = merge.merge(absent, self.src, prefix="../acme-sdlc")
        self.assertEqual(first, absent.read_text(encoding="utf-8"))
        self.assertTrue(all(line.startswith("present ") for line in log), log)


if __name__ == "__main__":
    unittest.main()
