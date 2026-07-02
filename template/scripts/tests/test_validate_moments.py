#!/usr/bin/env python3
"""Unit tests for validate-moments.py (stdlib unittest — no extra deps)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent.parent / "validate-moments.py"
spec = importlib.util.spec_from_file_location("validate_moments", MODULE_PATH)
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)

NOWHERE = Path("/nonexistent-base-dir")


def good_moment(**over):
    m = {
        "id": "session-start",
        "trigger": "A new working session begins.",
        "handler": "scripts/session/start.sh",
        "hook": "SessionStart",
        "status": "planned",  # planned → handler need not exist on disk
        "behavior_by_comfort": {"git-native": "offer", "guided": "offer", "hidden": "auto"},
    }
    m.update(over)
    return m


class ValidateManifestTests(unittest.TestCase):
    def test_valid_manifest_passes(self):
        self.assertEqual(vm.validate_manifest({"version": 1, "moments": [good_moment()]}, NOWHERE), [])

    def test_missing_required_field(self):
        m = good_moment()
        del m["trigger"]
        errs = vm.validate_manifest({"moments": [m]}, NOWHERE)
        self.assertTrue(any("trigger" in e for e in errs))

    def test_bad_status(self):
        errs = vm.validate_manifest({"moments": [good_moment(status="live")]}, NOWHERE)
        self.assertTrue(any("status" in e for e in errs))

    def test_bad_behavior_value(self):
        m = good_moment(behavior_by_comfort={"git-native": "maybe", "guided": "offer", "hidden": "auto"})
        errs = vm.validate_manifest({"moments": [m]}, NOWHERE)
        self.assertTrue(any("behavior_by_comfort" in e for e in errs))

    def test_bad_comfort_keys(self):
        errs = vm.validate_manifest({"moments": [good_moment(behavior_by_comfort={"native": "offer"})]}, NOWHERE)
        self.assertTrue(any("keys" in e for e in errs))

    def test_duplicate_ids(self):
        errs = vm.validate_manifest({"moments": [good_moment(), good_moment()]}, NOWHERE)
        self.assertTrue(any("duplicate" in e for e in errs))

    def test_active_handler_missing(self):
        errs = vm.validate_manifest({"moments": [good_moment(status="active", handler="scripts/session/nope.sh")]}, NOWHERE)
        self.assertTrue(any("handler not found" in e for e in errs))

    def test_active_handler_present(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "scripts" / "session").mkdir(parents=True)
            (base / "scripts" / "session" / "start.sh").write_text("#!/usr/bin/env bash\n")
            m = good_moment(status="active", handler="scripts/session/start.sh")
            self.assertEqual(vm.validate_manifest({"moments": [m]}, base), [])

    def test_empty_moments(self):
        errs = vm.validate_manifest({"moments": []}, NOWHERE)
        self.assertTrue(any("empty" in e for e in errs))

    def test_root_not_object(self):
        errs = vm.validate_manifest([], NOWHERE)
        self.assertTrue(any("root" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
