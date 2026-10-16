#!/usr/bin/env python3
"""Tests for support/planted_secrets.py: the planted values, the text that carries them
and the leak checks. The values are synthetic and made at runtime; none is in a file."""
import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "support"))
sys.path.insert(0, str(HERE.parent / "lib"))
import planted_secrets as ps  # noqa: E402
import redact  # noqa: E402


class TestValues(unittest.TestCase):
    def test_one_planted_value_per_redaction_kind_but_own_secret(self):
        self.assertEqual(set(ps.PLANTED), set(redact.KINDS) - {"own_secret"})

    def test_secrets_holds_every_planted_value_and_the_own_secret(self):
        self.assertEqual(set(ps.SECRETS), set(ps.PLANTED.values()) | {ps.OWN_SECRET})
        self.assertEqual(len(set(ps.SECRETS)), len(ps.SECRETS))

    def test_values_are_fresh_per_run_and_not_in_any_source_file(self):
        for path in HERE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for name, value in ps.named_secrets():
                self.assertNotIn(value, text, f"{name} is written in {path.name}")

    def test_own_secret_has_no_shape_the_rules_know(self):
        out, counts = redact.redact_text(f"note {ps.OWN_SECRET} end")
        self.assertIn(ps.OWN_SECRET, out)
        self.assertEqual(counts, {})

    def test_values_survive_url_and_json_quoting_unchanged(self):
        # So a leak cannot hide behind percent- or JSON-escaping.
        import json
        import urllib.parse
        for name, value in ps.named_secrets():
            self.assertEqual(urllib.parse.quote(value, safe=""), value, name)
            self.assertEqual(json.dumps(value)[1:-1], value, name)


class TestCarrier(unittest.TestCase):
    def test_redactor_catches_every_planted_value_in_the_carrier(self):
        text = ps.carrier()
        for value in ps.PLANTED.values():
            self.assertIn(value, text)
        out, counts = redact.redact_text(text)
        self.assertEqual(ps.leaks(out), [])
        self.assertEqual(set(counts), set(ps.PLANTED))

    def test_own_secret_line_is_caught_only_when_passed(self):
        text = ps.carrier(own=True)
        self.assertEqual(ps.leaks(redact.redact_text(text)[0]), ["own_secret"])
        out, counts = redact.redact_text(text, secrets=[ps.OWN_SECRET])
        self.assertEqual(ps.leaks(out), [])
        self.assertEqual(counts["own_secret"], 1)

    def test_carrier_for_some_kinds(self):
        text = ps.carrier(kinds=["jwt", "cookie"])
        self.assertEqual(sorted(ps.leaks(text)), ["cookie", "jwt"])

    def test_unknown_kind_is_an_error(self):
        with self.assertRaises(KeyError):
            ps.carrier(kinds=["nope"])

    def test_each_kind_is_caught_by_its_own_rule(self):
        # Alone, each line is caught by the rule it is planted for, not by a neighbour.
        for kind in ps.PLANTED:
            with self.subTest(kind=kind):
                out, counts = redact.redact_text(ps.carrier(kinds=[kind]))
                self.assertEqual(ps.leaks(out), [])
                self.assertIn(kind, counts)


class TestLeaks(unittest.TestCase):
    def test_names_each_leaked_value_once_in_kind_order(self):
        v = ps.PLANTED
        found = ps.leaks(f"a {v['token_shape']}", b"b " + v["jwt"].encode(), v["token_shape"])
        self.assertEqual(found, ["jwt", "token_shape"])

    def test_clean_text_and_none_are_fine(self):
        self.assertEqual(ps.leaks("nothing here", None, b"", ""), [])

    def test_base64_of_a_value_counts_as_a_leak(self):
        # A Basic auth header or an encoded blob still carries the secret.
        blob = base64.b64encode(f"user:{ps.OWN_SECRET}".encode()).decode()
        self.assertEqual(ps.leaks(f"Authorization: Basic {blob}"), ["own_secret"])

    def test_extra_secrets_are_checked_too(self):
        self.assertEqual(ps.leaks("x my-own-value y", extra={"cli_token": "my-own-value"}),
                         ["cli_token"])

    def test_leaks_in_files_walks_a_tree_and_reads_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a" / "b").mkdir(parents=True)
            (root / "clean.txt").write_text("ok")
            (root / "a" / "b" / "data.db").write_bytes(b"\x00\xff" + ps.PLANTED["cookie"].encode())
            (root / "a" / "log.txt").write_text(ps.PLANTED["jwt"] + "\n" + ps.PLANTED["cookie"])
            found = ps.leaks_in_files(root)
            self.assertEqual(found, [("a/b/data.db", "cookie"), ("a/log.txt", "jwt"),
                                     ("a/log.txt", "cookie")])
            self.assertEqual(ps.leaks_in_files(root / "clean.txt"), [])
            self.assertEqual(ps.leaks_in_files(root / "a" / "log.txt"),
                             [("log.txt", "jwt"), ("log.txt", "cookie")])

    @unittest.skipIf(os.name == "nt", "symlinks")
    def test_leaks_in_files_does_not_follow_symlinks_out_of_the_tree(self):
        with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as tmp:
            (Path(out) / "s.txt").write_text(ps.OWN_SECRET)
            (Path(tmp) / "link.txt").symlink_to(Path(out) / "s.txt")
            self.assertEqual(ps.leaks_in_files(tmp), [])


class TestMixin(ps.PlantedSecretsMixin, unittest.TestCase):
    def test_passes_on_clean_text_and_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "f").write_text("clean")
            self.assertNoPlantedSecrets("clean", b"clean", files=[tmp])

    def test_failure_names_kinds_and_files_never_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "out.csv").write_text(ps.PLANTED["key_value"])
            with self.assertRaises(AssertionError) as cm:
                self.assertNoPlantedSecrets("x " + ps.PLANTED["jwt"], files=[tmp], what="export")
        msg = str(cm.exception)
        self.assertIn("export", msg)
        self.assertIn("jwt", msg)
        self.assertIn("out.csv: key_value", msg)
        for value in ps.SECRETS:
            self.assertNotIn(value, msg)

    def test_a_missing_file_is_an_error_not_a_pass(self):
        with self.assertRaises(FileNotFoundError):
            self.assertNoPlantedSecrets(files=["/does/not/exist/anywhere"])


if __name__ == "__main__":
    unittest.main()
