#!/usr/bin/env python3
"""Tests for .claude/skills/ci-failure-triage/scripts/test_report.py (stdlib unittest).

Fixtures in fixtures/ci-failure-triage/ are neutral, made-up reports in each shipped
format: JUnit XML (a JVM runner and pytest), `go test -json`, Jest and Vitest JSON,
and TAP (node:test and a classic producer). Every secret-looking value in this file
is synthetic and built from parts at runtime.
"""
import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True        # no __pycache__ inside the skill folder
ROOT = Path(__file__).resolve().parent.parent.parent       # template/
SCRIPT = ROOT / ".claude" / "skills" / "ci-failure-triage" / "scripts" / "test_report.py"
FIX = Path(__file__).resolve().parent / "fixtures" / "ci-failure-triage"

spec = importlib.util.spec_from_file_location("test_report", SCRIPT)
test_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_report)

DB_SECRET = "s3cr" + "et-Value-" + "0123"


def run(*argv, stdin=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = test_report.main([str(a) for a in argv], stdin=stdin)
    return code, out.getvalue(), err.getvalue()


def run_json(*argv):
    code, text, err = run(*argv, "--json")
    assert code == 0, err
    return json.loads(text)


def by_id(doc):
    return {f["id"]: f for f in doc["failures"]}


class TestRegistry(unittest.TestCase):
    def test_shipped_formats(self):
        names = [p.name for p in test_report.PARSERS]
        for name in ("junit", "go-json", "jest-json", "tap"):
            self.assertIn(name, names)
        self.assertEqual(test_report.FORMATS, ("auto", *names))

    def test_auto_detects_each_fixture(self):
        expected = {"junit-surefire.xml": "junit", "junit-pytest.xml": "junit",
                    "go-test.json": "go-json", "jest.json": "jest-json",
                    "vitest.json": "jest-json", "node-test.tap": "tap",
                    "classic.tap": "tap"}
        for name, fmt in expected.items():
            doc = run_json(FIX / name)
            self.assertEqual(doc["inputs"], [{"path": str(FIX / name), "format": fmt}], name)

    def test_unknown_format(self):
        code, _, err = run(FIX / "jvm.log")
        self.assertEqual(code, 2)
        self.assertIn("unknown report format", err)

    def test_forced_format_that_does_not_fit(self):
        code, _, err = run(FIX / "classic.tap", "--format", "jest-json")
        self.assertEqual(code, 2)
        self.assertIn("not jest-json", err)


class TestJUnit(unittest.TestCase):
    def test_surefire_stats_categories_and_rerun(self):
        doc = run_json(FIX / "junit-surefire.xml")
        self.assertEqual(doc["stats"], {"total": 5, "passed": 1, "failed": 1, "errors": 1,
                                        "skipped": 1, "rerun_passed": 1, "duration_s": 2.37})
        f = by_id(doc)
        cls = "com.example.orders.OrderServiceTest#"
        self.assertEqual(f[cls + "rejectsEmptyOrder"]["category"], "assertion")
        self.assertEqual(f[cls + "rejectsEmptyOrder"]["location"], "OrderServiceTest.java:57")
        self.assertEqual(f[cls + "callsInventory"]["category"], "network")
        rerun = f[cls + "cachesPrices"]
        self.assertEqual((rerun["status"], rerun["category"]), ("passed_on_rerun", "timeout"))
        self.assertTrue(rerun["flaky_candidate"])
        self.assertIn("rerun", rerun["why"])
        self.assertFalse(f[cls + "callsInventory"]["flaky_candidate"])
        self.assertEqual(doc["by_group"], [{"group": "com.example.orders.OrderServiceTest",
                                            "failed": 2}])

    def test_pytest(self):
        doc = run_json(FIX / "junit-pytest.xml")
        self.assertEqual((doc["stats"]["total"], doc["stats"]["failed"],
                          doc["stats"]["skipped"]), (4, 2, 1))
        f = by_id(doc)
        self.assertEqual(f["tests.test_cart#test_discount"]["category"], "assertion")
        self.assertEqual(f["tests.test_cart#test_discount"]["location"], "tests/test_cart.py:14")
        self.assertEqual(f["tests.test_plugins#test_loads_plugin"]["category"], "config")
        self.assertEqual(doc["skipped"], ["tests.test_cart#test_tax"])

    def test_doctype_refused(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            p = tmp / "bad.xml"
            p.write_text('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]>'
                         '<testsuite><testcase name="t"/></testsuite>')
            code, _, err = run(p)
            self.assertEqual(code, 2)
            self.assertIn("DOCTYPE", err)
        finally:
            shutil.rmtree(tmp)


class TestGo(unittest.TestCase):
    def test_go_json(self):
        doc = run_json(FIX / "go-test.json")
        s = doc["stats"]
        self.assertEqual((s["total"], s["passed"], s["failed"], s["errors"], s["skipped"]),
                         (5, 1, 2, 1, 1))
        f = by_id(doc)
        self.assertEqual(f["example.com/shop/cart#TestDiscount"]["category"], "assertion")
        self.assertEqual(f["example.com/shop/cart#TestDiscount"]["location"], "cart_test.go:21")
        self.assertEqual(f["example.com/shop/cart#TestFetch"]["category"], "network")
        build = f["example.com/shop/api#(package)"]
        self.assertEqual((build["status"], build["category"]), ("error", "build"))


class TestJest(unittest.TestCase):
    def test_jest(self):
        doc = run_json(FIX / "jest.json")
        s = doc["stats"]
        self.assertEqual((s["total"], s["passed"], s["failed"], s["errors"], s["skipped"]),
                         (5, 1, 2, 1, 1))
        f = by_id(doc)
        rounds = f["/src/app/src/price.test.js#price rounds"]
        self.assertEqual(rounds["category"], "assertion")
        self.assertEqual(rounds["location"], "price.test.js:14")
        self.assertEqual(f["/src/app/src/price.test.js#price slow path"]["category"], "timeout")
        self.assertEqual(f["/src/app/src/cart.test.ts#(suite)"]["category"], "build")
        self.assertEqual(doc["slowest"][0]["id"], "/src/app/src/price.test.js#price slow path")

    def test_vitest(self):
        doc = run_json(FIX / "vitest.json")
        f = by_id(doc)
        self.assertEqual(f["/src/web/src/format.spec.ts#format rounds money"]["category"],
                         "assertion")
        self.assertEqual(f["/src/web/src/format.spec.ts#format rounds money"]["location"],
                         "format.spec.ts:11")


class TestTap(unittest.TestCase):
    def test_node_test_subtests(self):
        doc = run_json(FIX / "node-test.tap")
        s = doc["stats"]
        self.assertEqual((s["total"], s["passed"], s["failed"], s["skipped"]), (3, 1, 1, 1))
        f = by_id(doc)
        bad = f["parser#rejects bad input"]
        self.assertEqual(bad["category"], "assertion")
        self.assertEqual(bad["message"], "Expected values to be strictly equal:")
        self.assertEqual(bad["location"], "parser.test.js:22")
        self.assertNotIn("parser", f)                     # the parent is not a test
        self.assertEqual(doc["skipped"], ["config loads"])

    def test_classic_tap(self):
        doc = run_json(FIX / "classic.tap")
        s = doc["stats"]
        self.assertEqual((s["total"], s["passed"], s["failed"], s["errors"], s["skipped"]),
                         (6, 1, 2, 1, 2))
        f = by_id(doc)
        self.assertEqual(f["logout clears session"]["category"], "assertion")
        self.assertEqual(f["sync remote"]["category"], "timeout")
        self.assertEqual(f["(bail out)"]["message"], "database unavailable")
        self.assertIn("upload big file", doc["skipped"])


class TestReport(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_compare_marks_flaky_candidates_with_a_reason(self):
        later = self.tmp / "later.xml"
        later.write_text('<testsuite><testcase classname="com.example.orders.OrderServiceTest"'
                         ' name="callsInventory" time="0.1"/></testsuite>')
        doc = run_json(FIX / "junit-surefire.xml", "--compare", later)
        f = by_id(doc)["com.example.orders.OrderServiceTest#callsInventory"]
        self.assertTrue(f["flaky_candidate"])
        self.assertEqual(f["why"], f"passed in {later}")
        self.assertFalse(by_id(doc)["com.example.orders.OrderServiceTest#rejectsEmptyOrder"]
                         ["flaky_candidate"])

    def test_one_report_alone_never_makes_a_flaky_candidate(self):
        for name in ("go-test.json", "jest.json", "classic.tap", "junit-pytest.xml"):
            doc = run_json(FIX / name)
            self.assertFalse(any(f["flaky_candidate"] for f in doc["failures"]), name)

    def test_messages_redacted_and_clipped(self):
        p = self.tmp / "s.xml"
        p.write_text('<testsuite><testcase classname="c" name="t">'
                     f'<failure message="login failed password={DB_SECRET} {"y" * 900}"/>'
                     '</testcase></testsuite>')
        for extra in ([], ["--json"]):
            code, text, _ = run(p, *extra)
            self.assertEqual(code, 0)
            self.assertNotIn(DB_SECRET, text)
        doc = run_json(p)
        self.assertEqual(doc["redactions"], {"key_value": 1})
        self.assertLessEqual(len(doc["failures"][0]["message"]), test_report.MESSAGE_CHARS)

    def test_folder_and_glob(self):
        doc = run_json(FIX)
        formats = sorted({i["format"] for i in doc["inputs"]})
        self.assertEqual(formats, ["go-json", "jest-json", "junit", "tap"])
        self.assertNotIn(str(FIX / "jvm.log"), [i["path"] for i in doc["inputs"]])
        doc = run_json(str(FIX / "*.tap"))
        self.assertEqual(len(doc["inputs"]), 2)

    def test_missing_input(self):
        code, _, err = run(self.tmp / "nothing-*.xml")
        self.assertEqual(code, 2)
        self.assertIn("No file matches", err)

    def test_size_cap(self):
        old = test_report.MAX_FILE_BYTES
        test_report.MAX_FILE_BYTES = 100
        try:
            code, _, err = run(FIX / "junit-surefire.xml")
        finally:
            test_report.MAX_FILE_BYTES = old
        self.assertEqual(code, 2)
        self.assertIn("larger than", err)

    def test_stdin(self):
        code, text, err = run("-", stdin=io.StringIO((FIX / "classic.tap").read_text()))
        self.assertEqual(code, 0, err)
        self.assertIn("6 tests", text)

    def test_text_render(self):
        code, text, _ = run(FIX / "junit-surefire.xml")
        self.assertEqual(code, 0)
        self.assertIn("5 tests: 1 passed, 1 failed, 1 errors, 1 skipped, 1 passed on rerun",
                      text)
        self.assertIn("flaky candidate:", text)

    def test_cli_runs_as_a_script(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), str(FIX / "go-test.json")],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[build]", proc.stdout)


class TestCategories(unittest.TestCase):
    def test_rules_by_ecosystem(self):
        cases = {
            ("", "java.lang.OutOfMemoryError: Java heap space"): "infra",
            ("", "No space left on device"): "infra",
            ("", "ConnectionRefusedError: [Errno 111] Connection refused"): "network",
            ("", "getaddrinfo ENOTFOUND db.example.com"): "network",
            ("", "context deadline exceeded"): "timeout",
            ("", "TimeoutError: waited 5 s"): "timeout",
            ("", "ModuleNotFoundError: No module named 'x'"): "config",
            ("", "Error: Cannot find module 'left-pad'"): "config",
            ("", "error[E0425]: cannot find value `x` in this scope"): "build",
            ("", "AssertionError: 1 != 2"): "assertion",
            ("", "assert 90 == 100"): "assertion",
            ("", "something odd"): "other",
        }
        for (kind, text), expected in cases.items():
            self.assertEqual(test_report.categorize(kind, text)[0], expected, text)

    def test_rules_are_data(self):
        for name, category, pattern in test_report.RULES:
            self.assertIn(category, test_report.CATEGORIES, name)
            self.assertTrue(hasattr(pattern, "search"), name)


if __name__ == "__main__":
    unittest.main()
