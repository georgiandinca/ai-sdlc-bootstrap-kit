#!/usr/bin/env python3
"""Unit tests for validate-seat-profiles.py (stdlib unittest — no extra deps)."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent.parent / "validate-seat-profiles.py"
spec = importlib.util.spec_from_file_location("validate_seat_profiles", MODULE_PATH)
vsp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vsp)

PLAYBOOKS = {
    "Architect": "playbook-architect", "EM": "playbook-em", "Product": "playbook-product",
    "Developer": "playbook-dev", "QA": "playbook-qa",
}
DEFAULTS = {"Architect": "git-native", "EM": "git-native", "Product": "hidden",
            "Developer": "git-native", "QA": "guided"}


def full_manifest():
    return {"version": 1, "seats": [
        {"id": sid, "git_comfort_default": DEFAULTS[sid], "playbook": PLAYBOOKS[sid],
         "connectors": ["issue-tracker"], "first_task": "do a thing"}
        for sid in ["Architect", "EM", "Product", "Developer", "QA"]
    ]}


class ValidateSeatProfilesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        for pb in PLAYBOOKS.values():
            (self.base / ".claude" / "skills" / pb).mkdir(parents=True)
        (self.base / ".mcp.json").write_text(json.dumps(
            {"mcpServers": {"issue-tracker": {}, "docs-wiki": {}, "knowledge": {}, "context7": {}}}))

    def tearDown(self):
        self._tmp.cleanup()

    def test_valid_manifest_passes(self):
        self.assertEqual(vsp.validate_manifest(full_manifest(), self.base), [])

    def test_missing_required_field(self):
        m = full_manifest(); del m["seats"][0]["first_task"]
        self.assertTrue(any("first_task" in e for e in vsp.validate_manifest(m, self.base)))

    def test_bad_git_comfort_default(self):
        m = full_manifest(); m["seats"][0]["git_comfort_default"] = "expert"
        self.assertTrue(any("git_comfort_default" in e for e in vsp.validate_manifest(m, self.base)))

    def test_unknown_seat_id(self):
        m = full_manifest(); m["seats"][0]["id"] = "Wizard"
        self.assertTrue(any("known seats" in e for e in vsp.validate_manifest(m, self.base)))

    def test_missing_known_seat(self):
        m = full_manifest(); m["seats"].pop()  # drop QA
        self.assertTrue(any("missing seats" in e for e in vsp.validate_manifest(m, self.base)))

    def test_duplicate_id(self):
        m = full_manifest(); m["seats"][1]["id"] = "Architect"
        self.assertTrue(any("duplicate" in e for e in vsp.validate_manifest(m, self.base)))

    def test_playbook_dir_missing(self):
        m = full_manifest(); m["seats"][0]["playbook"] = "playbook-nope"
        self.assertTrue(any("playbook skill dir not found" in e for e in vsp.validate_manifest(m, self.base)))

    def test_connector_not_in_mcp(self):
        m = full_manifest(); m["seats"][0]["connectors"] = ["ghost-connector"]
        self.assertTrue(any("not declared in .mcp.json" in e for e in vsp.validate_manifest(m, self.base)))

    def test_empty_seats(self):
        self.assertTrue(any("empty" in e for e in vsp.validate_manifest({"seats": []}, self.base)))

    def test_root_not_object(self):
        self.assertTrue(any("root" in e for e in vsp.validate_manifest([], self.base)))


if __name__ == "__main__":
    unittest.main()
