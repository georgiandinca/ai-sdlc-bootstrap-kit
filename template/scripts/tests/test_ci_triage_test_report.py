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
GIT_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0" + "k1L2m3N4o5P6q7R8"
CLOUD_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"
LAB_TOKEN = "glpat-" + "AbCdEfGhIj" + "KlMnOpQrSt"


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


class TestHardening(unittest.TestCase):
    """Malformed, hostile or unusual input: no traceback, no secret, no lost failure."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, name, text, encoding="utf-8"):
        p = self.tmp / name
        p.write_bytes(text.encode(encoding))
        return p

    def test_secrets_in_test_names_groups_and_skips(self):
        tap = self.write("n.tap", "TAP version 13\n1..2\n"
                         f"not ok 1 - login with token {GIT_TOKEN} works\n"
                         f"ok 2 - skip {CLOUD_KEY} # SKIP no creds\n")
        xml = self.write("n.xml", '<testsuite><testcase classname="a.B" '
                         f'name="test_login[password={DB_SECRET}]" time="1">'
                         '<failure message="x">boom</failure></testcase>'
                         f'<testcase classname="{LAB_TOKEN}" name="t2"><skipped/></testcase>'
                         '</testsuite>')
        for path in (tap, xml):
            for extra in ([], ["--json"]):
                code, text, err = run(path, *extra)
                self.assertEqual(code, 0, err)
                for secret in (GIT_TOKEN, CLOUD_KEY, LAB_TOKEN, DB_SECRET):
                    self.assertNotIn(secret, text)
        self.assertEqual(run_json(tap)["redactions"], {"token_shape": 2})
        doc = run_json(xml)
        self.assertEqual(doc["redactions"], {"key_value": 2, "token_shape": 1})  # id, slowest
        self.assertIn("a.B#test_login[password=<redacted:key_value>", by_id(doc))
        self.assertEqual(doc["skipped"], ["<redacted:token_shape>#t2"])

    def test_malformed_json_is_refused_without_a_traceback(self):
        cases = {
            "go1.json": '{"Action":"run","Package":"p","Test":"T"}\n'
                        '{"Action":"output","Package":"p","Test":"T","Output":5}\n',
            "go2.json": '{"Action":"run","Package":["p"],"Test":"T"}\n',
            "j1.json": '{"testResults":[1]}',
            "j2.json": '{"testResults":"x"}',
        }
        for name, text in cases.items():
            code, _, err = run(self.write(name, text))
            self.assertEqual(code, 2, name)
            self.assertIn("not valid", err, name)
            self.assertNotIn("Traceback", err, name)

    def test_odd_jest_values_are_tolerated(self):
        p = self.write("j.json", '{"testResults":[{"name":"a","assertionResults":['
                       '{"status":"failed","duration":"12","title":"x",'
                       '"failureMessages":[{"m":1}]}]}]}')
        doc = run_json(p)
        self.assertEqual(doc["stats"]["failed"], 1)
        self.assertEqual(doc["stats"]["duration_s"], 0.012)

    def test_unterminated_tap_yaml_does_not_swallow_tests(self):
        p = self.write("y.tap", "TAP version 13\n1..3\nnot ok 1 - first\n  ---\n"
                       "  message: 'boom'\nok 2 - second\nnot ok 3 - third\n")
        doc = run_json(p)
        self.assertEqual((doc["stats"]["total"], doc["stats"]["failed"]), (3, 2))
        self.assertEqual(by_id(doc)["first"]["message"], "boom")
        self.assertIn("third", by_id(doc))

    def test_byte_order_marks(self):
        xml = '<?xml version="1.0" encoding="utf-8"?><testsuite><testcase classname="A" ' \
              'name="x"><failure message="m"/></testcase></testsuite>'
        self.assertEqual(run_json(self.write("bom.xml", "﻿" + xml))["stats"]["failed"], 1)
        js = '{"testResults":[]}'
        self.assertEqual(run_json(self.write("bom.json", "﻿" + js))["inputs"][0]["format"],
                         "jest-json")
        u16 = xml.replace("utf-8", "utf-16")
        self.assertEqual(run_json(self.write("u16.xml", u16, "utf-16"))["stats"]["failed"], 1)
        code, text, err = run("-", stdin=io.StringIO("﻿1..1\nnot ok 1 - a\n"))
        self.assertEqual(code, 0, err)
        self.assertIn("1 failed", text)

    def test_doctype_inside_cdata_is_text(self):
        p = self.write("html.xml", '<testsuite><testcase classname="ui.Page" name="renders">'
                       '<failure message="snapshot mismatch"><![CDATA[expected <!DOCTYPE '
                       'html><html>...]]></failure></testcase></testsuite>')
        self.assertEqual(run_json(p)["stats"]["failed"], 1)

    def test_entities_and_dtds_still_refused(self):
        laughs = ('<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa">'
                  '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
                  '<testsuite><testcase name="&b;"/></testsuite>')
        xxe = ('<?xml version="1.0"?><!DOCTYPE t [<!ENTITY x SYSTEM "file:///etc/hosts">]>'
               '<testsuite><testcase name="&x;"/></testsuite>')
        for name, text in (("laughs.xml", laughs), ("xxe.xml", xxe)):
            code, out, err = run(self.write(name, text))
            self.assertEqual(code, 2, name)
            self.assertIn("DOCTYPE", err)
            self.assertNotIn("localhost", out)
        code, _, err = run(self.write("u7.xml", '<?xml version="1.0" encoding="UTF-7"?>'
                                      '+ADw-!DOCTYPE x+AD4-<testsuite/>'))
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)

    def test_go_json_after_build_output(self):
        p = self.write("gobuild.json", "# example.com/foo\n"
                       "foo_test.go:3:2: undefined: bar\n"
                       '{"Action":"start","Package":"example.com/foo"}\n'
                       '{"Action":"fail","Package":"example.com/foo","Elapsed":0}\n')
        doc = run_json(p)
        self.assertEqual(doc["inputs"][0]["format"], "go-json")
        f = by_id(doc)["example.com/foo#(package)"]
        self.assertEqual((f["status"], f["category"]), ("error", "build"))

    def test_go_parent_with_failed_subtests_is_not_counted(self):
        lines = [
            {"Action": "run", "Package": "p", "Test": "TestA"},
            {"Action": "run", "Package": "p", "Test": "TestA/sub1"},
            {"Action": "output", "Package": "p", "Test": "TestA/sub1",
             "Output": "    a_test.go:9: got 1 want 2\n"},
            {"Action": "fail", "Package": "p", "Test": "TestA/sub1", "Elapsed": 0},
            {"Action": "run", "Package": "p", "Test": "TestA/sub2"},
            {"Action": "pass", "Package": "p", "Test": "TestA/sub2", "Elapsed": 0},
            {"Action": "fail", "Package": "p", "Test": "TestA", "Elapsed": 0},
            {"Action": "run", "Package": "p", "Test": "TestB"},
            {"Action": "run", "Package": "p", "Test": "TestB/ok"},
            {"Action": "pass", "Package": "p", "Test": "TestB/ok", "Elapsed": 0},
            {"Action": "output", "Package": "p", "Test": "TestB",
             "Output": "    b_test.go:20: cleanup failed\n"},
            {"Action": "fail", "Package": "p", "Test": "TestB", "Elapsed": 0},
            {"Action": "fail", "Package": "p", "Elapsed": 0},
        ]
        p = self.write("g.json", "".join(json.dumps(l) + "\n" for l in lines))
        doc = run_json(p)
        self.assertEqual(sorted(by_id(doc)), ["p#TestA/sub1", "p#TestB"])
        self.assertEqual(doc["stats"]["total"], 4)       # sub1, sub2, TestB/ok, TestB

    def test_a_long_secret_is_redacted_before_the_message_is_clipped(self):
        payload = "eyJ" + "a" * 1500
        jwt = "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + payload + "." + "c2lnbmF0dXJlLXg"
        p = self.write("cut.json", json.dumps({"testResults": [{"name": "a", "assertionResults": [
            {"status": "failed", "title": "x", "failureMessages": ["boom jwt " + jwt]}]}]}))
        for extra in ([], ["--json"]):
            code, text, _ = run(p, *extra)
            self.assertEqual(code, 0)
            self.assertNotIn("a" * 40, text)
        doc = run_json(p)
        self.assertEqual(doc["redactions"], {"jwt": 1})
        self.assertEqual(doc["failures"][0]["message"], "boom jwt <redacted:jwt>")

    def test_deeply_nested_json_is_refused(self):
        for name, text in (("deep.json", "[" * 100000 + "]" * 100000),
                           ("deep.jsonl", '{"a":' * 100000 + "1" + "}" * 100000 + "\n")):
            code, _, err = run(self.write(name, text))
            self.assertEqual(code, 2, name)
            self.assertNotIn("Traceback", err, name)
            self.assertIn("unknown report format", err, name)

    def test_failures_and_groups_are_capped(self):
        cases = "".join(f'<testcase classname="g{i}" name="t{i}"><failure message="f"/></testcase>'
                        for i in range(250))
        cases += "".join(f'<testcase classname="e" name="e{i}"><error message="e"/></testcase>'
                         for i in range(3))
        cases += ('<testcase classname="r" name="r1"><flakyFailure message="x"/></testcase>')
        p = self.write("many.xml", f"<testsuite>{cases}</testsuite>")
        doc = run_json(p)
        self.assertEqual(len(doc["failures"]), test_report.FAILURES_MAX)
        self.assertEqual(doc["failures_omitted"], 254 - test_report.FAILURES_MAX)
        self.assertEqual({f["status"] for f in doc["failures"]}, {"failed"})
        self.assertEqual(len(doc["by_group"]), test_report.GROUPS_MAX)
        self.assertEqual(doc["groups_omitted"], 251 - test_report.GROUPS_MAX)
        self.assertEqual(doc["stats"]["failed"], 250)
        code, text, _ = run(p)
        self.assertIn(f"{254 - test_report.FAILURES_MAX} more failure(s) not shown", text)
        self.assertLess(len(text.splitlines()), test_report.FAILURES_MAX + 20)
        small = run_json(FIX / "junit-surefire.xml")
        self.assertEqual((small["failures_omitted"], small["groups_omitted"]), (0, 0))
        self.assertEqual([f["status"] for f in small["failures"]],
                         ["failed", "error", "passed_on_rerun"])      # failures first

    def test_tap_yaml_at_column_zero_ends_at_the_next_test(self):
        p = self.write("y0.tap", "1..3\nnot ok 1 - first\n---\nmessage: 'boom'\nok: 1\n"
                       "ok 2 - second\n# Subtest: s\nnot ok 3 - third\n")
        doc = run_json(p)
        self.assertEqual((doc["stats"]["total"], doc["stats"]["failed"]), (3, 2))
        self.assertEqual(by_id(doc)["first"]["message"], "boom")
        self.assertIn("third", by_id(doc))
        p = self.write("y1.tap", "1..2\nnot ok 1 - first\n---\nmessage: 'boom'\n"
                       "Bail out! gone\n")
        self.assertIn("(bail out)", by_id(run_json(p)))


    def test_a_look_alike_redactor_is_not_trusted(self):
        fake = self.tmp / "proj"
        (fake / "scripts" / "lib").mkdir(parents=True)
        (fake / "scripts" / "lib" / "redact.py").write_text("def redact_text(t):\n    return t, {}\n")
        skill = fake / ".claude" / "skills" / "ci-failure-triage" / "scripts"
        skill.mkdir(parents=True)
        shutil.copy(SCRIPT, skill / "test_report.py")
        proc = subprocess.run([sys.executable, str(skill / "test_report.py"),
                               str(FIX / "classic.tap")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("redact.py", proc.stderr)
        self.assertEqual(proc.stdout, "")


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
