#!/usr/bin/env python3
"""Tests for validate-frontmatter.py's debt baseline (stdlib unittest — no extra deps).

Each test copies the validator into a throwaway repo (`<repo>/scripts/`), the
same shape as an installed project, and runs it as pre-commit and CI do.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "validate-frontmatter.py"
BASELINE = ".ai-sdlc/frontmatter-baseline.txt"

GOOD = """---
title: Good doc
status: draft
owner: Product
classification: internal
ai-trust: working
author: someone
created: 2026-01-01
last-reviewed: 2026-01-01
---

# Good doc
"""
BARE = "# A doc written before the contract existed\n"

GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


class Repo:
    def __init__(self, root: Path, git: bool = True):
        self.root = root
        (root / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, root / "scripts" / "validate-frontmatter.py")
        (root / "docs").mkdir()
        if git:
            subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=GIT_ENV)

    def doc(self, rel: str, text: str = BARE) -> Path:
        p = self.root / "docs" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def run(self, *args: str):
        return subprocess.run(
            [sys.executable, str(self.root / "scripts" / "validate-frontmatter.py"), *args],
            cwd=self.root, capture_output=True, text=True, env=GIT_ENV)

    def baseline(self) -> list[str]:
        text = (self.root / BASELINE).read_text(encoding="utf-8")
        return [l for l in text.splitlines() if l.strip() and not l.startswith("#")]


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Repo(Path(self._tmp.name) / "proj")

    def tearDown(self):
        self._tmp.cleanup()

    def adopt_ten(self):
        for i in range(10):
            self.repo.doc(f"area{i % 3}/legacy-{i}.md")
        self.repo.doc("ok.md", GOOD)
        return self.repo.run("--write-baseline")

    def test_without_baseline_a_bare_doc_fails(self):
        self.repo.doc("legacy.md")
        r = self.repo.run()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("FAIL  docs/legacy.md", r.stdout)

    def test_write_baseline_records_every_violation(self):
        r = self.adopt_ten()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("10 file(s) recorded", r.stdout)
        entries = self.repo.baseline()
        self.assertEqual(len(entries), 10)
        self.assertIn("docs/area0/legacy-0.md", entries)
        self.assertNotIn("docs/ok.md", entries)

    def test_baselined_docs_pass_the_gate_as_debt(self):
        self.adopt_ten()
        r = self.repo.run()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("debt  docs/area1/legacy-1.md", r.stdout)
        self.assertIn("10 baselined file(s)", r.stdout)

    def test_new_doc_without_frontmatter_still_fails(self):
        self.adopt_ten()
        self.repo.doc("new.md")
        r = self.repo.run()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("FAIL  docs/new.md", r.stdout)

    def test_baseline_applies_to_files_passed_by_pre_commit(self):
        self.adopt_ten()
        new = self.repo.doc("new.md")
        r = self.repo.run("docs/area0/legacy-0.md")
        self.assertEqual(r.returncode, 0, r.stdout)
        r = self.repo.run("docs/area0/legacy-0.md", str(new))
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_fixed_doc_prints_remove_notice_and_rewrite_shrinks(self):
        self.adopt_ten()
        self.repo.doc("area1/legacy-1.md", GOOD)
        r = self.repo.run()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("remove from baseline", r.stdout)
        self.assertIn("docs/area1/legacy-1.md", r.stdout)
        r = self.repo.run("--write-baseline")
        self.assertEqual(r.returncode, 0, r.stdout)
        entries = self.repo.baseline()
        self.assertEqual(len(entries), 9)
        self.assertNotIn("docs/area1/legacy-1.md", entries)

    def test_rewrite_never_adds_a_new_violation(self):
        self.adopt_ten()
        self.repo.doc("new.md")
        r = self.repo.run("--write-baseline")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("docs/new.md", r.stdout)
        self.assertNotIn("docs/new.md", self.repo.baseline())
        self.assertEqual(len(self.repo.baseline()), 10)

    def test_deleted_baselined_doc_is_reported_stale(self):
        self.adopt_ten()
        (self.repo.root / "docs/area2/legacy-2.md").unlink()
        r = self.repo.run()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("remove from baseline", r.stdout)
        self.assertIn("docs/area2/legacy-2.md", r.stdout)
        self.repo.run("--write-baseline")
        self.assertNotIn("docs/area2/legacy-2.md", self.repo.baseline())

    def test_no_baseline_flag_fails_on_debt(self):
        self.adopt_ten()
        r = self.repo.run("--no-baseline")
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_write_baseline_refuses_file_arguments(self):
        self.repo.doc("legacy.md")
        r = self.repo.run("--write-baseline", "docs/legacy.md")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertFalse((self.repo.root / BASELINE).exists())

    def test_empty_adoption_still_writes_a_baseline(self):
        self.repo.doc("ok.md", GOOD)
        r = self.repo.run("--write-baseline")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.repo.baseline(), [])
        # An existing (empty) baseline means a later rewrite cannot adopt new debt.
        self.repo.doc("new.md")
        self.assertEqual(self.repo.run("--write-baseline").returncode, 1)
        self.assertEqual(self.repo.baseline(), [])


class GitIgnoredTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_git_ignored_docs_are_skipped(self):
        repo = Repo(Path(self._tmp.name) / "proj")
        (repo.root / ".gitignore").write_text("docs/transcripts/\n", encoding="utf-8")
        ignored = repo.doc("transcripts/session-1.md")
        repo.doc("ok.md", GOOD)
        r = repo.run()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("transcripts", r.stdout)
        r = repo.run(str(ignored))
        self.assertEqual(r.returncode, 0, r.stdout)
        repo.run("--write-baseline")
        self.assertEqual(repo.baseline(), [])

    def test_works_outside_a_git_repo(self):
        repo = Repo(Path(self._tmp.name) / "proj", git=False)
        repo.doc("legacy.md")
        r = repo.run()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("FAIL  docs/legacy.md", r.stdout)


if __name__ == "__main__":
    unittest.main()
