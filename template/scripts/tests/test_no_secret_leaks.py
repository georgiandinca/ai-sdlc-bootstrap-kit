#!/usr/bin/env python3
"""Planted-secret sweep: every script that writes text taken from logs, transcripts or
the team ledger is run end to end with the planted secrets (support/planted_secrets.py)
in its input, and none may reach its stdout, stderr or any file it writes.

One test per output surface; add one when a new script logs, persists or shows text
it did not write itself. The secrets are synthetic and made fresh on every run. A
failure names the kind and the place, never the value, and never prints a whole output.
"""
import csv
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parents[1]
SCRIPTS = TEMPLATE / "scripts"
SPEND = SCRIPTS / "spend"
TRIAGE = TEMPLATE / ".claude" / "skills" / "ci-failure-triage" / "scripts"
sys.path.insert(0, str(HERE / "support"))
sys.path.insert(0, str(SPEND))
sys.path.insert(0, str(SCRIPTS / "lib"))
import planted_secrets as ps  # noqa: E402
import redact  # noqa: E402
from export_sessions import HEADER  # noqa: E402

CARRIER = ps.carrier()


def run(argv, cwd=None, env_extra=None, stdin=None):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1", **(env_extra or {})}
    return subprocess.run(argv, input=stdin, text=True, capture_output=True, cwd=cwd,
                          env=env, timeout=120)


def transcript_lines():
    """A transcript whose user turn, assistant turn and model name carry the secrets."""
    return [
        {"type": "user", "message": {"role": "user", "content": CARRIER}},
        {"type": "assistant", "message": {
            "role": "assistant", "model": f"model-{ps.PLANTED['token_shape']}",
            "content": [{"type": "text", "text": CARRIER}],
            "usage": {"input_tokens": 10, "output_tokens": 2}}},
    ]


def write_transcript(path):
    path.write_text("\n".join(json.dumps(r) for r in transcript_lines()) + "\n",
                    encoding="utf-8")
    return path


def ledger_row(session_id, user, text):
    d = {k: "" for k in HEADER}
    d.update(session_id=session_id, ts="2026-07-01T10:00:00", user=user, seat="Developer",
             tool="agent", task=text, model="model-x", tokens_in="1", tokens_out="1",
             cache_read_tokens="0", cost_usd="0", outcome="unknown", grounded="0", notes=text)
    return [d[k] for k in HEADER]


class Sweep(ps.PlantedSecretsMixin, unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def assertClean(self, proc, *files, what):
        self.assertNoPlantedSecrets(proc.stdout, proc.stderr, files=files, what=what)

    def assertRan(self, proc, code=0):
        """The exit code; on a mismatch, a summary that cannot carry a planted value."""
        if (proc.returncode == code) if code is not None else proc.returncode != 0:
            return
        found = ps.leaks(proc.stdout, proc.stderr)
        tail = ("(withheld: planted secrets in the streams)" if found
                else redact.redact_text(proc.stderr[-800:])[0])
        self.fail(f"exit {proc.returncode}, want {'non-zero' if code is None else code}; "
                  f"leaks in streams: {found or 'none'}; stderr tail: {tail}")


class TestRedactorFilter(Sweep):
    def test_filter_with_own_secret(self):
        proc = run([sys.executable, str(SCRIPTS / "lib" / "redact.py"),
                    "--secret-env", "PLANTED_OWN", "--counts"],
                   stdin=ps.carrier(own=True), env_extra={"PLANTED_OWN": ps.OWN_SECRET})
        self.assertRan(proc)
        self.assertClean(proc, what="redact.py")
        self.assertEqual(set(json.loads(proc.stderr)), set(ps.PLANTED) | {"own_secret"})


class TestTranscriptParser(Sweep):
    def test_db_and_streams(self):
        db = self.tmp / "out" / "u.db"
        db.parent.mkdir()
        proc = run([sys.executable, str(SPEND / "parse_transcript.py"),
                    "--transcript", str(write_transcript(self.tmp / "t.jsonl")),
                    "--session-id", "planted-1", "--task", CARRIER, "--db", str(db)])
        self.assertRan(proc)
        self.assertClean(proc, db.parent, what="parse_transcript.py")
        with sqlite3.connect(db) as conn:
            dump = "\n".join(conn.iterdump())
        self.assertNoPlantedSecrets(dump, what="the usage DB")
        self.assertTrue("planted-1" in dump, "the session row is missing")


class TestLedgerExport(Sweep):
    def test_csv_and_streams(self):
        # Rows written before redaction existed: raw secrets already in the DB.
        sys.path.insert(0, str(TEMPLATE / "dashboard"))
        import db as dbmod
        db = self.tmp / "u.db"
        conn = dbmod.connect(db)
        conn.execute("INSERT INTO sessions (ts, seat, session_id, user, tokens_in, tokens_out,"
                     " task, model, notes) VALUES (?,?,?,?,?,?,?,?,?)",
                     ("2026-07-01T10:00:00", "QA", "s1", "dev1", 1, 1, CARRIER,
                      f"model-{ps.PLANTED['token_shape']}", CARRIER))
        conn.commit()
        conn.close()
        out = self.tmp / "ledger"
        proc = run([sys.executable, str(SPEND / "export_sessions.py"), "--db", str(db),
                    "--out-dir", str(out), "--user", "dev1"])
        self.assertRan(proc)
        self.assertClean(proc, out, what="export_sessions.py")
        self.assertTrue((out / "dev1.csv").is_file())


class TestLedgerImport(Sweep):
    def test_db_and_streams(self):
        ledger = self.tmp / "ledger"
        ledger.mkdir()
        with open(ledger / "dev2.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(HEADER)
            w.writerow(ledger_row("s1", "dev2", CARRIER))
            # A user cell that disagrees with the file name is echoed into notes.
            w.writerow(ledger_row("s2", "x-" + ps.PLANTED["token_shape"], "ok"))
        out = self.tmp / "out"
        out.mkdir()
        proc = run([sys.executable, str(SPEND / "import_sessions.py"), "--dir", str(ledger),
                    "--db", str(out / "u.db")])
        self.assertRan(proc)
        self.assertClean(proc, out, what="import_sessions.py")
        with sqlite3.connect(out / "u.db") as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM sessions WHERE user='dev2'")
                             .fetchone()[0], 2)

    def test_a_rejected_file_names_no_secret(self):
        # The error quotes the header, redacted. A bare value with no shape and no name
        # is a documented limit of the redactor, so the header holds shaped values only.
        ledger = self.tmp / "ledger"
        ledger.mkdir()
        (ledger / "dev2.csv").write_text(
            f"session_id,{ps.PLANTED['token_shape']},{ps.PLANTED['jwt']}\n"
            f"x,{ps.PLANTED['key_value']},y\n", encoding="utf-8")
        proc = run([sys.executable, str(SPEND / "import_sessions.py"), "--dir", str(ledger),
                    "--db", str(self.tmp / "u.db")])
        self.assertRan(proc, code=None)
        self.assertClean(proc, what="import_sessions.py on a bad file")


class TestSessionCollectorHook(Sweep):
    """collect-usage.sh in a throwaway copy of the kit's scripts: DB, ledger CSV, error
    log and the hook's own streams. Secrets come in through the transcript (turns and
    model name) and the seat (SESSION_SEAT reaches --seat). The ticket is cut from the
    branch name by a pattern no secret matches, and the user is folded to lower case
    and `[a-z0-9._-]`, so neither can carry a planted value as planted."""

    def setUp(self):
        super().setUp()
        self.root = self.tmp / "proj"
        skip = shutil.ignore_patterns("tests", "__pycache__", "*.db")
        for rel in ("scripts/session", "scripts/spend", "scripts/lib", "dashboard"):
            shutil.copytree(TEMPLATE / rel, self.root / rel, ignore=skip)
        run(["git", "init", "-q", str(self.root)])
        self.env = {"HOME": str(self.tmp), "GIT_CONFIG_NOSYSTEM": "1", "USER": "dev1",
                    "SESSION_SEAT": f"QA {ps.PLANTED['token_shape']} "
                                    f"password={ps.PLANTED['key_value']}",
                    "SDLC_USAGE_DB": str(self.tmp / "out" / "u.db"),
                    "SDLC_SESSIONS_DIR": str(self.tmp / "out" / "ledger")}
        (self.tmp / "out").mkdir()

    def hook(self, payload):
        proc = run(["bash", "scripts/session/collect-usage.sh"], cwd=self.root,
                   env_extra=self.env, stdin=json.dumps(payload))
        self.assertRan(proc)
        return proc

    def test_recorded_session(self):
        transcript = write_transcript(self.tmp / "t.jsonl")
        proc = self.hook({"session_id": "planted-hook", "transcript_path": str(transcript)})
        self.assertClean(proc, self.tmp / "out", self.root / "scripts" / "session",
                         what="collect-usage.sh")
        csv_text = (self.tmp / "out" / "ledger" / "dev1.csv").read_text(encoding="utf-8")
        # The seat went through, redacted: proof the planted field reached the output.
        self.assertTrue("QA <redacted:token_shape> password=<redacted:key_value>" in csv_text,
                        "the planted seat did not reach the ledger")

    def test_error_log(self):
        proc = self.hook({"session_id": "x",
                          "transcript_path": f"/does/not/exist?password={ps.PLANTED['key_value']}"
                                             f"&t={ps.PLANTED['token_shape']}"})
        errlog = self.root / "scripts" / "session" / ".usage-errors.log"
        self.assertTrue(errlog.is_file())
        self.assertClean(proc, errlog, what="collect-usage.sh error log")


class TestCiFailureTriage(Sweep):
    def test_log_slice_every_mode(self):
        log = self.tmp / "build.log"
        log.write_text("INFO start\n" + CARRIER + "ERROR deploy failed\n" + CARRIER,
                       encoding="utf-8")
        for flags in ([], ["--first-error"], ["--tail", "50"], ["--grep", "Pl4nted|token"],
                      ["--traces"], ["--json"], ["--first-error", "--json"]):
            with self.subTest(flags=flags):
                proc = run([sys.executable, str(TRIAGE / "log_slice.py"), str(log), *flags])
                self.assertRan(proc)
                self.assertClean(proc, what=f"log_slice.py {' '.join(flags)}")

    def test_test_report_junit(self):
        proc = run([sys.executable, str(TRIAGE / "test_report.py"),
                    str(junit_report(self.tmp)), "--json"])
        self.assertRan(proc)
        self.assertClean(proc, what="test_report.py --json")
        self.assertEqual(json.loads(proc.stdout)["stats"]["failed"], len(JUNIT_KINDS))
        proc = run([sys.executable, str(TRIAGE / "test_report.py"), str(junit_report(self.tmp))])
        self.assertRan(proc)
        self.assertClean(proc, what="test_report.py")

    def test_test_report_junit_catches_each_kind_the_redactor_misses(self):
        # The test above is only worth something if every planted value reaches the
        # output when its rule is off: run against a redactor with one kind disabled.
        report = junit_report(self.tmp)
        for kind in JUNIT_KINDS:
            with self.subTest(kind=kind):
                skill = project_without(self.tmp / kind, kind)
                proc = run([sys.executable, str(skill / "test_report.py"), str(report),
                            "--json"])
                self.assertRan(proc)
                self.assertEqual(ps.leaks(proc.stdout), [kind])


# test_report shows a failure's message by its first line only, and the id (group and
# name). So each kind gets its own failing test with its carrier line first. env_dump
# and private_key are multi-line, their value never on a first line: no field of this
# report can carry them, and they are left out here.
JUNIT_KINDS = [k for k in ps.PLANTED if k not in ("env_dump", "private_key")]


def junit_report(folder):
    from xml.sax.saxutils import escape, quoteattr
    cases = [f'<testcase classname="app.Login" name="case_{kind}">'
             f'<failure message={quoteattr(ps.carrier_lines(kind)[0])}>{escape(CARRIER)}'
             '</failure></testcase>' for kind in JUNIT_KINDS]
    path = Path(folder) / "TEST-planted.xml"
    path.write_text(f'<testsuite name="suite" tests="{len(cases)}" failures="{len(cases)}">'
                    + "".join(cases) + "</testsuite>", encoding="utf-8")
    return path


def project_without(root, kind):
    """A throwaway project holding the ci-failure-triage helpers and a copy of the
    shared redactor whose `kind` rule is switched off; the helpers' folder."""
    skill = root / ".claude" / "skills" / "ci-failure-triage" / "scripts"
    shutil.copytree(TRIAGE, skill, ignore=shutil.ignore_patterns("__pycache__"))
    lib = root / "scripts" / "lib"
    lib.mkdir(parents=True)
    (lib / "redact.py").write_text(
        (SCRIPTS / "lib" / "redact.py").read_text(encoding="utf-8") + f"""

_DISABLED = {kind!r}
_orig_sub = Redactor._sub


def _sub(self, kind, pattern, repl, text):
    return text if kind == _DISABLED else _orig_sub(self, kind, pattern, repl, text)


Redactor._sub = _sub
if _DISABLED == "auth_header":
    Redactor._lone_scheme = lambda self, text: text
""", encoding="utf-8")
    return skill

if __name__ == "__main__":
    unittest.main()
