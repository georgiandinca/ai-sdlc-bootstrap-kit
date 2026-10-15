#!/usr/bin/env python3
"""Tests for check-context-budget.py and the description cap in validate-skills.py
(stdlib unittest — no extra deps).

Each test builds a throwaway project (`<repo>/scripts/` holds the scripts and
the limits file), the same shape as an installed project, and runs the script
as pre-commit and CI do.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
TEMPLATE = SCRIPTS.parent
CHECK = SCRIPTS / "check-context-budget.py"
SKILLS = SCRIPTS / "validate-skills.py"
LIMITS_REL = "scripts/context-budget.json"


def skill_md(name: str, desc: str) -> str:
    return f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n\nBody.\n"


class Repo:
    def __init__(self, root: Path):
        self.root = root
        (root / "scripts").mkdir(parents=True)
        shutil.copy(CHECK, root / "scripts" / CHECK.name)
        shutil.copy(SKILLS, root / "scripts" / SKILLS.name)
        self.write("AGENTS.md", "a" * 1000)
        self.write("CLAUDE.md", "c" * 200)
        self.write(".claude/rules/one.md", "r" * 300)
        self.write(".claude/rules/two.md", "r" * 100)
        self.skill("playbook-dev", "d" * 100)
        self.skill("helper", "h" * 50)
        self.write("scripts/session/seat-profiles.json", json.dumps(
            {"seats": [{"id": "Developer", "playbook": "playbook-dev"}]}))
        self.limits({"AGENTS.md": 1060, "CLAUDE.md": 210, ".claude/rules": 420,
                     "skill-descriptions": 160, "total": 1850})

    def write(self, rel: str, text: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def skill(self, name: str, desc: str) -> Path:
        return self.write(f".claude/skills/{name}/SKILL.md", skill_md(name, desc))

    def limits(self, limits: dict, **extra) -> None:
        data = {"version": 1, "description_max": 500, "warn_slack_pct": 15,
                "headroom_pct": 6, "limits": limits}
        data.update(extra)
        self.write(LIMITS_REL, json.dumps(data, indent=2))

    def read_limits(self) -> dict:
        return json.loads((self.root / LIMITS_REL).read_text(encoding="utf-8"))

    def run(self, *args: str, script: str = CHECK.name):
        return subprocess.run(
            [sys.executable, str(self.root / "scripts" / script), *args],
            cwd=self.root, capture_output=True, text=True)


class TestCheckContextBudget(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Repo(Path(self._tmp.name) / "proj")

    def tearDown(self):
        self._tmp.cleanup()

    def test_within_budget_passes_and_reports_every_item(self):
        r = self.repo.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for item in ("AGENTS.md", "CLAUDE.md", ".claude/rules/one.md",
                     ".claude/rules/two.md", "playbook-dev", "helper"):
            self.assertIn(item, r.stdout)
        self.assertIn("1000 / 1060", r.stdout)            # AGENTS.md against its limit
        self.assertIn("400 / 420", r.stdout)              # rules group
        self.assertIn("150 / 160", r.stdout)              # descriptions group
        self.assertIn("1750 / 1850", r.stdout)            # total
        self.assertIn("tokens", r.stdout)                 # approximate token count
        self.assertNotIn("warn", r.stdout)

    def test_file_over_its_limit_fails_with_the_cut(self):
        self.repo.write("AGENTS.md", "a" * 1100)
        r = self.repo.run()
        self.assertEqual(r.returncode, 1)
        self.assertIn("AGENTS.md", r.stdout)
        self.assertIn("cut 40", r.stdout)

    def test_rules_group_over_its_limit_fails(self):
        self.repo.write(".claude/rules/three.md", "r" * 50)
        r = self.repo.run()
        self.assertEqual(r.returncode, 1)
        self.assertIn("cut 30", r.stdout)

    def test_total_over_its_limit_fails(self):
        self.repo.limits({"AGENTS.md": 1060, "CLAUDE.md": 210, ".claude/rules": 420,
                          "skill-descriptions": 160, "total": 1700})
        r = self.repo.run()
        self.assertEqual(r.returncode, 1)
        self.assertIn("total", r.stdout)
        self.assertIn("cut 50", r.stdout)

    def test_long_description_fails_with_the_cut(self):
        self.repo.skill("helper", "h" * 501)
        self.repo.limits({"AGENTS.md": 1060, "CLAUDE.md": 210, ".claude/rules": 420,
                          "skill-descriptions": 650, "total": 2300})
        r = self.repo.run()
        self.assertEqual(r.returncode, 1)
        self.assertIn("helper", r.stdout)
        self.assertIn("501 / 500", r.stdout)
        self.assertIn("cut 1", r.stdout)

    def test_slack_limit_warns_but_passes(self):
        self.repo.limits({"AGENTS.md": 1200, "CLAUDE.md": 210, ".claude/rules": 420,
                          "skill-descriptions": 160, "total": 2050})
        r = self.repo.run()
        self.assertEqual(r.returncode, 0, r.stdout)
        warns = [l for l in r.stdout.splitlines() if l.lstrip().startswith("warn")]
        self.assertEqual(len(warns), 2, r.stdout)        # AGENTS.md and total
        self.assertTrue(any("AGENTS.md" in l for l in warns))
        self.assertTrue(any("lower it to 1060" in l for l in warns), warns)

    def test_seats_report_their_playbook_description(self):
        r = self.repo.run()
        line = next(l for l in r.stdout.splitlines() if "Developer" in l)
        self.assertIn("playbook-dev", line)
        self.assertIn("100 / 500", line)

    def test_missing_seat_manifest_is_fine(self):
        (self.repo.root / "scripts/session/seat-profiles.json").unlink()
        r = self.repo.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_limits_file_is_a_usage_error(self):
        (self.repo.root / LIMITS_REL).unlink()
        r = self.repo.run()
        self.assertEqual(r.returncode, 2)
        self.assertIn("--write-limits", r.stdout + r.stderr)

    def test_malformed_limits_file_is_a_usage_error(self):
        self.repo.write(LIMITS_REL, "{ not json")
        r = self.repo.run()
        self.assertEqual(r.returncode, 2)

    def test_limit_missing_for_an_item_is_a_usage_error(self):
        self.repo.limits({"AGENTS.md": 1060})
        r = self.repo.run()
        self.assertEqual(r.returncode, 2)
        self.assertIn("CLAUDE.md", r.stdout + r.stderr)

    def test_write_limits_sets_current_size_plus_headroom(self):
        self.repo.write("AGENTS.md", "a" * 5000)
        self.repo.write(LIMITS_REL, json.dumps({"version": 1, "description_max": 400,
                                                "keep": "me"}))
        r = self.repo.run("--write-limits")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = self.repo.read_limits()
        self.assertEqual(data["keep"], "me")             # other keys survive
        self.assertEqual(data["description_max"], 400)
        self.assertEqual(data["limits"]["AGENTS.md"], 5300)   # 5000 + 6 %
        self.assertEqual(data["limits"]["CLAUDE.md"], 220)    # 212, rounded up to 10
        r = self.repo.run()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("warn", r.stdout)

    def test_write_limits_creates_a_missing_file(self):
        (self.repo.root / LIMITS_REL).unlink()
        r = self.repo.run("--write-limits")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = self.repo.read_limits()
        self.assertEqual(data["description_max"], 500)
        self.assertEqual(set(data["limits"]), {"AGENTS.md", "CLAUDE.md", ".claude/rules",
                                               "skill-descriptions", "total"})

    def test_kit_limits_over_budget_say_to_resize_once(self):
        self.repo.limits({"AGENTS.md": 1060, "CLAUDE.md": 210, ".claude/rules": 420,
                          "skill-descriptions": 160, "total": 1850}, sized_for="kit")
        self.repo.write("AGENTS.md", "a" * 1100)       # placeholders filled in
        r = self.repo.run()
        self.assertEqual(r.returncode, 1)              # still fails
        self.assertIn("kit's starting limits", r.stdout)
        self.assertIn("--write-limits", r.stdout)

    def test_project_limits_over_budget_do_not_suggest_resizing(self):
        self.repo.limits({"AGENTS.md": 1060, "CLAUDE.md": 210, ".claude/rules": 420,
                          "skill-descriptions": 160, "total": 1850}, sized_for="project")
        self.repo.write("AGENTS.md", "a" * 1100)
        r = self.repo.run()
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("kit's starting limits", r.stdout)

    def test_write_limits_marks_the_file_sized_for_the_project(self):
        self.repo.limits({"AGENTS.md": 1060, "CLAUDE.md": 210, ".claude/rules": 420,
                          "skill-descriptions": 160, "total": 1850}, sized_for="kit")
        self.repo.write("AGENTS.md", "a" * 1100)
        self.assertEqual(self.repo.run("--write-limits").returncode, 0)
        self.assertEqual(self.repo.read_limits()["sized_for"], "project")
        self.assertEqual(self.repo.run().returncode, 0)

    def test_non_utf8_file_is_a_usage_error(self):
        (self.repo.root / "AGENTS.md").write_bytes(b"\xff\xfe broken")
        r = self.repo.run()
        self.assertEqual(r.returncode, 2)
        self.assertIn("AGENTS.md is not UTF-8", r.stderr)

    def test_non_utf8_skill_is_a_usage_error(self):
        (self.repo.root / ".claude/skills/helper/SKILL.md").write_bytes(b"---\n\xff\n---\n")
        r = self.repo.run()
        self.assertEqual(r.returncode, 2)
        self.assertIn("helper/SKILL.md is not UTF-8", r.stderr)

    def test_nested_skill_files_are_not_counted(self):
        self.repo.write(".claude/skills/helper/examples/helper/SKILL.md",
                        skill_md("helper", "n" * 400))
        r = self.repo.run()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("150 / 160", r.stdout)           # descriptions group unchanged
        self.assertNotIn("examples", r.stdout)

    def test_non_integer_settings_are_usage_errors(self):
        base = {"AGENTS.md": 1060, "CLAUDE.md": 210, ".claude/rules": 420,
                "skill-descriptions": 160, "total": 1850}
        for limits, extra in (({**base, "total": True}, {}),
                              ({**base, "CLAUDE.md": -1}, {}),
                              (base, {"description_max": "500"}),
                              (base, {"warn_slack_pct": 1.5}),
                              (base, {"headroom_pct": None})):
            with self.subTest(limits=limits, extra=extra):
                self.repo.limits(limits, **extra)
                r = self.repo.run()
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertNotIn("Traceback", r.stderr)

    def test_write_limits_never_raises_the_description_cap(self):
        self.repo.skill("helper", "h" * 600)
        r = self.repo.run("--write-limits")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("helper", r.stdout)
        self.assertEqual(self.repo.read_limits()["description_max"], 500)


class TestValidateSkillsDescriptionCap(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Repo(Path(self._tmp.name) / "proj")

    def tearDown(self):
        self._tmp.cleanup()

    def test_description_over_the_budget_fails(self):
        self.repo.skill("helper", "h" * 501)
        r = self.repo.run(script=SKILLS.name)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("cut 1", r.stdout)

    def test_description_at_the_budget_passes(self):
        self.repo.skill("helper", "h" * 500)
        r = self.repo.run(script=SKILLS.name)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_cap_comes_from_the_limits_file(self):
        self.repo.limits({}, description_max=40)
        r = self.repo.run(script=SKILLS.name)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("helper", r.stdout)               # 50 > 40

    def test_default_cap_without_a_limits_file(self):
        (self.repo.root / LIMITS_REL).unlink()
        self.repo.skill("helper", "h" * 501)
        r = self.repo.run(script=SKILLS.name)
        self.assertEqual(r.returncode, 1, r.stdout)


class TestKitTemplateBudget(unittest.TestCase):
    """The kit's own template is within its budget, and the limits are not slack."""

    def test_template_passes_without_warnings(self):
        r = subprocess.run([sys.executable, str(CHECK)], cwd=TEMPLATE,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("warn", r.stdout)

    def test_limits_have_five_to_eight_percent_headroom_over_a_fresh_install(self):
        """Sized from what an install holds: bootstrap adds a pointer block to CLAUDE.md."""
        limits = json.loads((TEMPLATE / LIMITS_REL).read_text(encoding="utf-8"))
        self.assertEqual(limits["description_max"], 500)
        self.assertEqual(limits["sized_for"], "kit")
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "fresh"
            b = subprocess.run(["bash", str(SCRIPTS / "bootstrap.sh"), "--name", "Fresh",
                                "--slug", "fresh", "--dir", str(proj), "--desc", "d",
                                "--ticket", "F", "--hooks", "none", "--no-git",
                                "--non-interactive"], capture_output=True, text=True)
            self.assertEqual(b.returncode, 0, b.stdout + b.stderr)
            r = subprocess.run([sys.executable, str(proj / "scripts" / CHECK.name), "--json"],
                               capture_output=True, text=True)
        sizes = json.loads(r.stdout)["sizes"]
        for key, cap in limits["limits"].items():
            with self.subTest(key=key):
                self.assertGreaterEqual(cap, sizes[key] * 1.04, f"{key}: too tight")
                self.assertLessEqual(cap, sizes[key] * 1.09, f"{key}: too slack")


if __name__ == "__main__":
    unittest.main()
