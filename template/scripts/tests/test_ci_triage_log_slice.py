#!/usr/bin/env python3
"""Tests for .claude/skills/ci-failure-triage/scripts/log_slice.py (stdlib unittest).

Fixtures in fixtures/ci-failure-triage/ hold neutral, made-up logs for five
stack-trace shapes: JVM, Python, Node, Go and .NET. Every secret-looking value in
this file is synthetic and built from parts at runtime, so no secret scanner
mistakes this file for a leak.
"""
import contextlib
import gzip
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.dont_write_bytecode = True        # no __pycache__ inside the skill folder
ROOT = Path(__file__).resolve().parent.parent.parent       # template/
SCRIPT = ROOT / ".claude" / "skills" / "ci-failure-triage" / "scripts" / "log_slice.py"
FIX = Path(__file__).resolve().parent / "fixtures" / "ci-failure-triage"

spec = importlib.util.spec_from_file_location("log_slice", SCRIPT)
log_slice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(log_slice)

# synthetic values, built from parts
GIT_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0" + "k1L2m3N4o5P6q7R8"
DB_SECRET = "s3cr" + "et-Value-" + "0123"


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = log_slice.main([str(a) for a in argv])
    return code, out.getvalue()


def run_json(*argv):
    code, text = run(*argv, "--json")
    assert code == 0, text
    return json.loads(text)


def groups_by_class(doc):
    return {g["signature"].split(" | ")[0]: g for g in doc["traces"]}


class TestFirstError(unittest.TestCase):
    def test_first_error_line_and_context(self):
        doc = run_json(FIX / "jvm.log", "--first-error", "--before", "2", "--after", "3")
        fe = doc["first_error"]
        self.assertEqual(fe["n"], 3)
        self.assertIn("order failed", fe["text"])
        self.assertEqual([l["n"] for l in fe["before"]], [1, 2])
        self.assertEqual([l["n"] for l in fe["after"]], [4, 5, 6])

    def test_marker_without_levels_go(self):
        doc = run_json(FIX / "go.log", "--first-error")
        self.assertTrue(doc["first_error"]["text"].startswith("panic:"))
        self.assertEqual(doc["first_error"]["n"], 4)

    def test_python_traceback_is_an_error_without_a_level(self):
        path = Path(self.tmp) / "plain.log"
        path.write_text("collecting\nTraceback (most recent call last):\n"
                        '  File "a.py", line 1, in <module>\nKeyError: \'x\'\n')
        doc = run_json(path, "--first-error")
        self.assertEqual(doc["first_error"]["n"], 2)

    def test_npm_err_is_an_error(self):
        doc = run_json(FIX / "node.log", "--first-error", "--level", "ERROR")
        self.assertEqual([l["text"][:8] for l in doc["lines"]], ["npm ERR!", "npm ERR!"])

    def test_no_error(self):
        path = Path(self.tmp) / "ok.log"
        path.write_text("all good\nstill good\n")
        code, text = run(path, "--first-error")
        self.assertEqual(code, 0)
        self.assertIn("First error: none found.", text)

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)


class TestTraces(unittest.TestCase):
    def test_jvm_grouped_without_line_numbers(self):
        doc = run_json(FIX / "jvm.log", "--traces")
        g = groups_by_class(doc)["java.lang.IllegalStateException"]
        self.assertEqual(g["count"], 2)
        self.assertEqual(g["starts"], [4, 14])
        self.assertEqual(g["shape"], "jvm")
        self.assertIn("com.example.orders.OrderService.place(OrderService.java)",
                      g["signature"])

    def test_python_grouped_on_innermost_frames(self):
        doc = run_json(FIX / "python.log", "--traces")
        self.assertEqual(len(doc["traces"]), 1)
        g = doc["traces"][0]
        self.assertEqual(g["count"], 2)                 # worker.py line differs: same group
        self.assertEqual(g["shape"], "python")
        self.assertTrue(g["signature"].startswith("ValueError | "))
        self.assertIn("/srv/app/parse.py in parse", g["signature"])
        self.assertEqual(g["message"], "bad payload")

    def test_node(self):
        doc = run_json(FIX / "node.log", "--traces")
        g = groups_by_class(doc)["TypeError"]
        self.assertEqual(g["shape"], "node")
        self.assertIn("loadConfig (/srv/app/config.js)", g["signature"])

    def test_go_panic(self):
        doc = run_json(FIX / "go.log", "--traces")
        g = groups_by_class(doc)["panic"]
        self.assertEqual(g["shape"], "go")
        self.assertIn("runtime error: index out of range", g["message"])
        self.assertIn("example.com/shop/cart.(*Cart).Item", g["signature"])

    def test_dotnet_with_bracketed_stamps(self):
        doc = run_json(FIX / "dotnet.log", "--traces")
        g = groups_by_class(doc)["System.InvalidOperationException"]
        self.assertEqual(g["count"], 1)
        self.assertIn("Shop.Billing.Invoice.First() in /src/Billing/Invoice.cs", g["signature"])
        self.assertNotIn("line 27", g["signature"])

    def test_text_render(self):
        code, text = run(FIX / "jvm.log", "--traces")
        self.assertEqual(code, 0)
        self.assertIn("2x java.lang.IllegalStateException", text)

    def test_every_shape_is_data(self):
        names = [s["name"] for s in log_slice.TRACE_SHAPES]
        for name in ("jvm", "python", "node", "go"):
            self.assertIn(name, names)
        for s in log_slice.TRACE_SHAPES:
            self.assertTrue({"name", "start", "frame"} <= set(s), s["name"])

    def test_group_count_is_capped(self):
        tmp = tempfile.mkdtemp()
        try:
            path = Path(tmp) / "many.log"
            with open(path, "w") as fh:
                for i in range(log_slice.MAX_GROUPS + 30):
                    fh.write(f"java.lang.IllegalStateException: x\n\tat a.B.m{i}(B.java:1)\n")
            doc = run_json(path, "--traces")
            self.assertEqual(len(doc["traces"]), log_slice.MAX_GROUPS)
            self.assertEqual(doc["traces_dropped"], 30)
        finally:
            shutil.rmtree(tmp)


class TestSelection(unittest.TestCase):
    def test_level_keeps_continuation_lines(self):
        doc = run_json(FIX / "jvm.log", "--level", "WARN")
        ns = [l["n"] for l in doc["lines"]]
        self.assertEqual(ns, [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18])

    def test_time_window_bare_time(self):
        doc = run_json(FIX / "jvm.log", "--since", "10:00:02", "--until", "10:00:03")
        ns = [l["n"] for l in doc["lines"]]
        self.assertEqual(ns, list(range(3, 13)))
        self.assertEqual(doc["window"]["since"], "2026-10-12T10:00:02")

    def test_time_window_with_offset(self):
        doc = run_json(FIX / "python.log", "--since", "2026-10-12T12:00:03+02:00")
        self.assertEqual(doc["lines"][0]["n"], 12)

    def test_default_tail(self):
        tmp = tempfile.mkdtemp()
        try:
            path = Path(tmp) / "long.log"
            path.write_text("".join(f"line {i}\n" for i in range(1, 501)))
            doc = run_json(path)
            self.assertEqual(len(doc["lines"]), log_slice.DEFAULT_TAIL)
            self.assertEqual(doc["lines"][-1]["n"], 500)
            self.assertEqual(doc["lines_read"], 500)
        finally:
            shutil.rmtree(tmp)

    def test_grep_from_line_tail(self):
        doc = run_json(FIX / "jvm.log", "--grep", "order failed", "--from-line", "5")
        self.assertEqual([l["n"] for l in doc["lines"]], [13])
        doc = run_json(FIX / "jvm.log", "--tail", "2")
        self.assertEqual([l["n"] for l in doc["lines"]], [18, 19])

    def test_max_bytes(self):
        doc = run_json(FIX / "jvm.log", "--from-line", "1", "--max-bytes", "200")
        self.assertTrue(doc["truncated"])
        self.assertGreater(doc["omitted_lines"], 0)
        self.assertLessEqual(sum(len(l["text"].encode()) + 1 for l in doc["lines"]), 200)
        code, text = run(FIX / "jvm.log", "--from-line", "1", "--max-bytes", "200")
        self.assertIn("Cut at --max-bytes 200", text)

    def test_gzip(self):
        tmp = tempfile.mkdtemp()
        try:
            path = Path(tmp) / "jvm.log.gz"
            with gzip.open(path, "wb") as fh:
                fh.write((FIX / "jvm.log").read_bytes())
            doc = run_json(path, "--first-error")
            self.assertEqual(doc["first_error"]["n"], 3)
        finally:
            shutil.rmtree(tmp)

    def test_bad_arguments(self):
        with contextlib.redirect_stderr(io.StringIO()):
            for argv in (["--grep", "("], ["--level", "LOUD"], ["--since", "noon"],
                         ["--tail", "0"]):
                with self.assertRaises(SystemExit):
                    log_slice.main([str(FIX / "jvm.log"), *argv])
            with self.assertRaises(SystemExit):
                log_slice.main([str(FIX / "missing.log")])


class TestRedactionAndBounds(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_secrets_redacted_in_every_output(self):
        path = self.tmp / "s.log"
        path.write_text(f"INFO cloning with {GIT_TOKEN}\n"
                        f"ERROR connect failed db_password={DB_SECRET}\n")
        for argv in ([], ["--first-error"], ["--grep", "connect"]):
            for extra in ([], ["--json"]):
                code, text = run(path, *argv, *extra)
                self.assertEqual(code, 0)
                self.assertNotIn(GIT_TOKEN, text)
                self.assertNotIn(DB_SECRET, text)
        doc = run_json(path)
        self.assertEqual(doc["redactions"], {"key_value": 1, "token_shape": 1})
        self.assertIn("<redacted:token_shape>", doc["lines"][0]["text"])

    def test_grep_runs_on_redacted_text(self):
        path = self.tmp / "s.log"
        path.write_text(f"token {GIT_TOKEN}\n")
        doc = run_json(path, "--grep", "ghp_")
        self.assertEqual(doc["lines"], [])

    def test_long_line_is_bounded(self):
        path = self.tmp / "wide.log"
        path.write_text(f"ERROR password={DB_SECRET} " + "x" * 300_000 + "\nnext\n")
        doc = run_json(path, "--first-error")
        fe = doc["first_error"]
        self.assertLessEqual(len(fe["text"]), log_slice.LINE_CHARS)
        self.assertNotIn(DB_SECRET, json.dumps(doc))
        self.assertEqual(fe["after"][0], {"n": 2, "text": "next"})

    def test_pathological_lines_are_fast(self):
        path = self.tmp / "slow.log"
        with open(path, "w") as fh:
            for _ in range(200):
                fh.write("(" * 5000 + "\n")
                fh.write("a." * 2500 + "\n")
                fh.write("\tat " + "(" * 5000 + "\n")
        start = time.monotonic()
        run_json(path, "--traces", "--first-error", "--level", "INFO")
        self.assertLess(time.monotonic() - start, 10)

    def test_fails_closed_without_the_shared_redactor(self):
        alone = self.tmp / "skill" / "scripts"
        alone.mkdir(parents=True)
        shutil.copy(SCRIPT, alone / "log_slice.py")
        proc = subprocess.run([sys.executable, str(alone / "log_slice.py"),
                               str(FIX / "jvm.log")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("redact.py", proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_cli_runs_as_a_script(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), str(FIX / "go.log"), "--traces"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("panic", proc.stdout)


class TestHardening(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_bare_iso_stamp_prefix(self):
        doc = run_json(FIX / "runner-iso.log", "--traces", "--first-error")
        g = groups_by_class(doc)["java.lang.IllegalStateException"]
        self.assertEqual((g["shape"], g["first_n"]), ("jvm", 2))
        self.assertIn("com.example.stock.Ledger.take(Ledger.java)", g["signature"])
        self.assertEqual(doc["first_error"]["n"], 5)            # the --- FAIL marker

    def test_ansi_colour_codes(self):
        path = self.tmp / "ansi.log"
        path.write_text("ok\n\x1b[31mERROR\x1b[0m something broke\n"
                        "\x1b[1mBUILD FAILURE\x1b[0m\n")
        doc = run_json(path, "--level", "ERROR")
        self.assertEqual([l["text"] for l in doc["lines"]], ["ERROR something broke"])
        path.write_text("ok\n\x1b[1mBUILD FAILURE\x1b[0m\n")
        self.assertEqual(run_json(path, "--first-error")["first_error"]["n"], 2)

    def test_corrupt_and_truncated_gzip(self):
        whole = gzip.compress((FIX / "jvm.log").read_bytes())
        for name, data in (("bad.gz", b"\x1f\x8b" + b"junkjunk"), ("cut.log.gz", whole[:40])):
            path = self.tmp / name
            path.write_bytes(data)
            proc = subprocess.run([sys.executable, str(SCRIPT), str(path), "--first-error"],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2, name)
            self.assertNotIn("Traceback", proc.stderr, name)
            self.assertIn("cannot read", proc.stderr, name)
            self.assertEqual(proc.stdout, "", name)

    def test_a_look_alike_redactor_is_not_trusted(self):
        proj = self.tmp / "proj"
        (proj / "scripts" / "lib").mkdir(parents=True)
        (proj / "scripts" / "lib" / "redact.py").write_text("KINDS = ()\n")
        skill = proj / ".claude" / "skills" / "ci-failure-triage" / "scripts"
        skill.mkdir(parents=True)
        shutil.copy(SCRIPT, skill / "log_slice.py")
        proc = subprocess.run([sys.executable, str(skill / "log_slice.py"),
                               str(FIX / "jvm.log")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("redact.py", proc.stderr)
        self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
