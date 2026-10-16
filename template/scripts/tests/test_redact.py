#!/usr/bin/env python3
"""Tests for scripts/lib/redact.py (stdlib unittest — no extra deps).

Every kind has a positive test (the value is replaced by <redacted:KIND>,
counted, and gone from the output) and a negative test (look-alike text is
kept and nothing is counted).

Every secret-looking value in this file is synthetic and built from parts at
runtime, so no secret scanner mistakes this file for a leak.
"""
import ast
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "lib"
sys.path.insert(0, str(LIB))
import redact  # noqa: E402

# synthetic values, built from parts
JWT = "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiJ1MSJ9" + "." + "c2lnbmF0dXJlLXg"
CLOUD_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"
GIT_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0" + "k1L2m3N4o5P6q7R8"
GIT_PAT = "github_pat_" + "11ABCDEFG0123456789_" + "abcdefghijklmnop"
LAB_TOKEN = "glpat-" + "AbCdEfGhIj" + "KlMnOpQrSt"
CHAT_TOKEN = "xoxb-" + "1234567890-" + "abcdefghij"
TRACKER_TOKEN = "ATATT" + "3xFfGF0abcdefgh" + "ijklmnopqrstu"
GOOGLE_KEY = "AIza" + "SyA-abcdefghijklmnop" + "qrstuvwxyz01234"
NPM_TOKEN = "npm_" + "abcdefghijklmnopqr" + "stuvwxyz0123456789"
PYPI_TOKEN = "pypi-" + "AgEIcHlwaS5vcmc" + "x" * 50
LLM_KEY = "sk-" + "ant-" + "api03-" + "fakeFAKEfake" + "0123456789abcdef"
PAY_KEY = "sk_" + "live_" + "FAKEfake0123" + "456789abcdef"
LLM_KEY_GENERIC = "sk-" + "proj-" + "Fake0fake1FAKE2" + "fake3fake4fake5fake6"
CHAT_HOOK = ("https://hooks." + "chat.example.com/services/" + "T0FAKE01/"
             + "B0FAKE02/" + "fakeWebhookSecret0123")
# PEM armour lines, split so no scanner reads this file as holding a key.
BEGIN, END, PRIV = "-----" + "BEGIN ", "-----" + "END ", "PRIVATE " + "KEY-----"

ALL_TOKENS = (CLOUD_KEY, GIT_TOKEN, GIT_PAT, LAB_TOKEN, CHAT_TOKEN, TRACKER_TOKEN,
              GOOGLE_KEY, NPM_TOKEN, PYPI_TOKEN, LLM_KEY, PAY_KEY, LLM_KEY_GENERIC,
              CHAT_HOOK)


def run(lines, secrets=()):
    r = redact.Redactor(secrets=secrets)
    out = []
    for line in lines:
        out += r.feed(line)
    out += r.flush()
    return out, r.counts


class Case(unittest.TestCase):
    def assert_redacted(self, line, kind, value, *, count=1, secrets=()):
        out, counts = run([line], secrets)
        text = "\n".join(out)
        self.assertNotIn(value, text)
        self.assertIn(f"<redacted:{kind}>", text)
        self.assertEqual(counts.get(kind), count, counts)
        return text

    def assert_kept(self, line, secrets=()):
        out, counts = run([line], secrets)
        self.assertEqual(out, [line])
        self.assertEqual(counts, {})


class TestKinds(unittest.TestCase):
    def test_kinds_in_application_order(self):
        self.assertEqual(redact.KINDS, ("own_secret", "auth_header", "jwt", "cookie",
                                        "url_credentials", "key_value", "env_dump",
                                        "private_key", "token_shape"))

    def test_marker(self):
        self.assertEqual(redact.marker("jwt"), "<redacted:jwt>")


class TestOwnSecret(Case):
    def test_saved_secret_anywhere(self):
        text = self.assert_redacted("curl x?q=s3cr3t-tok&y=1 done", "own_secret", "s3cr3t-tok",
                                    secrets=["s3cr3t-tok"])
        self.assertIn("done", text)

    def test_longest_secret_first(self):
        out, counts = run(["abcd-efgh"], secrets=["abcd", "abcd-efgh"])
        self.assertEqual(out, ["<redacted:own_secret>"])
        self.assertEqual(counts, {"own_secret": 1})

    def test_short_secrets_are_ignored(self):
        self.assert_kept("abc is fine", secrets=["abc"])

    def test_other_text_kept(self):
        self.assert_kept("nothing to see", secrets=["s3cr3t-tok"])


class TestAuthHeader(Case):
    def test_bearer(self):
        text = self.assert_redacted("Authorization: Bearer abc.def", "auth_header", "abc.def")
        self.assertIn("Authorization: Bearer <redacted:auth_header>", text)

    def test_proxy_basic(self):
        self.assert_redacted("Proxy-Authorization: Basic dXNlcjpw", "auth_header", "dXNlcjpw")

    def test_token_in_curl(self):
        text = self.assert_redacted('curl -H "Authorization: token ghx" https://x', "auth_header",
                                    "ghx")
        self.assertIn('token <redacted:auth_header>" https://x', text)

    def test_bearer_alone(self):
        self.assert_redacted("sent Bearer Zm9vYmFyYmF6MTIz to the API", "auth_header",
                             "Zm9vYmFyYmF6MTIz")

    def test_lower_case_scheme_alone(self):
        self.assert_redacted("curl -H 'x: bearer Zm9vYmFyYmF6MTIz'", "auth_header",
                             "Zm9vYmFyYmF6MTIz")
        self.assert_redacted("BASIC dXNlcjpwYXNz1", "auth_header", "dXNlcjpwYXNz1")

    def test_words_kept(self):
        self.assert_kept("Basic authentication is enabled for the Bearer of the badge")
        self.assert_kept("Authorization failed for user u1")
        self.assert_kept("basic authentication, bearer tokens and more")


class TestJwt(Case):
    def test_in_a_sentence(self):
        text = self.assert_redacted(f"got {JWT} back", "jwt", JWT)
        self.assertEqual(text, "got <redacted:jwt> back")

    def test_prefix_alone_kept(self):
        self.assert_kept("eyJ alone is not a token")
        self.assert_kept("eyJabc.def is two parts")


class TestCookie(Case):
    def test_set_cookie(self):
        self.assert_redacted("Set-Cookie: JSESSIONID=1A2B; Path=/", "cookie", "1A2B")

    def test_cookie(self):
        text = self.assert_redacted("Cookie: a=b; c=d", "cookie", "a=b")
        self.assertNotIn("c=d", text)

    def test_session_cookie_names_from_two_stacks(self):
        # The names come from a data table, one row per web stack.
        self.assert_redacted("url;JSESSIONID=9F8E7D6C5B", "cookie", "9F8E7D6C5B")
        self.assert_redacted("GET /?PHPSESSID=q1w2e3r4t5", "cookie", "q1w2e3r4t5")
        self.assert_redacted("ASP.NET_SessionId=zx81zx81zx81", "cookie", "zx81zx81zx81")

    def test_anti_forgery_headers_and_fields(self):
        self.assert_redacted("Jenkins-Crumb: 9f0e1d2c3b4a", "cookie", "9f0e1d2c3b4a")
        self.assert_redacted("X-CSRF-Token: 77aa88bb99cc", "cookie", "77aa88bb99cc")
        self.assert_redacted('{"crumb": "5e5e5e5e5e5e"}', "cookie", "5e5e5e5e5e5e")
        self.assert_redacted("csrfmiddlewaretoken=6d6d6d6d6d", "cookie", "6d6d6d6d6d")

    def test_kept(self):
        self.assert_kept("cookies are tasty")
        self.assert_kept("a bread crumb: tasty")
        self.assert_kept("the session id is logged elsewhere")


class TestUrlCredentials(Case):
    def test_user_and_password(self):
        text = self.assert_redacted("clone https://u1:pw@git.example.com/x.git",
                                    "url_credentials", "u1:pw")
        self.assertIn("https://<redacted:url_credentials>@git.example.com/x.git", text)

    def test_other_schemes(self):
        self.assert_redacted("db postgres://app:pa55@db.example.com:5432/x",
                             "url_credentials", "pa55")

    def test_scheme_with_plus(self):
        self.assert_redacted("git+ssh://u1:pw77@git.example.com/x", "url_credentials", "pw77")

    def test_password_holding_an_at_sign(self):
        text = self.assert_redacted("https://u1:p@ss77@git.example.com/x", "url_credentials",
                                    "ss77")
        self.assertIn("https://<redacted:url_credentials>@git.example.com/x", text)

    def test_no_credentials_kept(self):
        self.assert_kept("see https://git.example.com")
        self.assert_kept("git@host.example.com:repo")
        self.assert_kept("mail user@example.com")


class TestKeyValue(Case):
    def test_shapes(self):
        for line, value, name in (("password=hunter2", "hunter2", "password="),
                                  ("-Ddb.password=x9y8", "x9y8", "-Ddb.password="),
                                  ('"apiKey": "k7k7k7"', "k7k7k7", '"apiKey": "'),
                                  ("client_secret: s3s3s3", "s3s3s3", "client_secret:"),
                                  ("TOKEN=abc123", "abc123", "TOKEN="),
                                  ("url?access_key=zz11&x=1", "zz11", "access_key="),
                                  ("credentials = c0c0c0", "c0c0c0", "credentials"),
                                  ("passphrase: p4p4p4", "p4p4p4", "passphrase:")):
            with self.subTest(line=line):
                text = self.assert_redacted(line, "key_value", value)
                self.assertIn(name, text)          # the name is kept

    def test_rest_of_line_kept(self):
        out, _ = run(["login password=hunter2 user=u1"])
        self.assertEqual(out, ["login password=<redacted:key_value> user=u1"])

    def test_name_must_end_with_the_secret_word(self):
        self.assert_kept("tokens_total=3")
        self.assert_kept("passwordPolicy=strict")
        self.assert_kept("secretary=someone")

    def test_colon_needs_a_quote_or_a_space(self):
        # A test-report summary line ("Class.testPassword:42") is not a secret;
        # with ":" the name must be quoted or the value must follow a space.
        self.assert_kept("[ERROR]   LoginTest.badPassword:42 expected: <401> but was: <200>")
        self.assert_redacted("password: hunter2", "key_value", "hunter2")
        self.assert_redacted("'password':'hunter2'", "key_value", "hunter2")

    def test_camel_and_prefixed_names(self):
        self.assert_redacted("dbPassword=pp99", "key_value", "pp99")
        self.assert_redacted("GIT_TOKEN=tt88", "key_value", "tt88")

    def test_empty_value_kept(self):
        self.assert_kept("password=")
        self.assert_kept("Enter password:")
        self.assert_kept('password=""')

    def test_quoted_value_is_taken_whole(self):
        for line, value in (('{"password": "my secret pass Zq8"}', "secret pass Zq8"),
                            ('password="ab,cd"', ",cd"),
                            ("password='a&b'", "&b"),
                            ('{"token": "a\\"b c"}', "b c")):
            with self.subTest(line=line):
                text = self.assert_redacted(line, "key_value", value)
                self.assertTrue(text.endswith(('<redacted:key_value>"}', "<redacted:key_value>'",
                                               '<redacted:key_value>"')), text)

    def test_unclosed_quote_still_redacts_the_first_word(self):
        self.assert_redacted('password="abc def', "key_value", "abc")

    def test_more_name_shapes(self):
        for line, value in (("-Dfoo.password=v1v1", "v1v1"), ("app.db-password=v2v2", "v2v2"),
                            ('"x.token": "v3v3"', "v3v3"), ("--api-key=v4v4", "v4v4"),
                            ("form password%3Dv5v5", "v5v5")):
            with self.subTest(line=line):
                self.assert_redacted(line, "key_value", value)

    def test_space_separated_cli_flag(self):
        text = self.assert_redacted("tool login --password v6v6 --user u1", "key_value", "v6v6")
        self.assertEqual(text, "tool login --password <redacted:key_value> --user u1")
        self.assert_redacted("tool --api-token v7v7", "key_value", "v7v7")

    def test_cli_flag_lookalikes_kept(self):
        self.assert_kept("tool --password-file pw.txt")
        self.assert_kept("tool --no-password --verbose")
        self.assert_kept("bypass=true compass: north primary_key=id")


class TestEnvDump(Case):
    ENV = ["HOME=/home/u1", "PATH=/usr/bin", "LANG=C.UTF-8", "SHELL=/bin/sh",
           "BUILD_ID=412", "WORKSPACE=/ws/app"]

    def test_six_lines_all_values(self):
        out, counts = run(["start"] + self.ENV + ["end"])
        self.assertEqual(out[0], "start")
        self.assertEqual(out[-1], "end")
        for line, original in zip(out[1:-1], self.ENV):
            name = original.split("=", 1)[0]
            self.assertEqual(line, f"{name}=<redacted:env_dump>")
        self.assertEqual(counts["env_dump"], 6)
        for original in self.ENV:
            self.assertNotIn(original.split("=", 1)[1], "\n".join(out))

    def test_four_lines_are_not_a_dump(self):
        lines = ["HOME=/home/u1", "PATH=/usr/bin", "API_TOKEN=tok5tok5", "LANG=C"]
        out, counts = run(lines)
        self.assertEqual(out, ["HOME=/home/u1", "PATH=/usr/bin",
                               "API_TOKEN=<redacted:key_value>", "LANG=C"])
        self.assertNotIn("env_dump", counts)

    def test_timestamp_prefix(self):
        lines = [f"[2026-10-12T10:00:0{i}.000Z] {l}" for i, l in enumerate(self.ENV)]
        out, counts = run(lines)
        self.assertEqual(counts["env_dump"], 6)
        self.assertTrue(out[0].startswith("[2026-10-12T10:00:00.000Z] HOME=<redacted:env_dump>"))


class TestPrivateKey(Case):
    PEM = [BEGIN + "RSA " + PRIV, "MIIEowIBAAKCAQEAsynthetic1",
           "c3ludGhldGljMg", "c3ludGhldGljMw", END + "RSA " + PRIV]

    def test_block_is_one_line(self):
        out, counts = run(["before"] + self.PEM + ["after"])
        self.assertEqual(out, ["before", "<redacted:private_key>", "after"])
        self.assertEqual(counts, {"private_key": 1})

    def test_openssh_key(self):
        pem = [BEGIN + "OPENSSH " + PRIV, "b3BlbnNzaC1rZXktdjEAsynthetic",
               END + "OPENSSH " + PRIV]
        out, counts = run(pem)
        self.assertEqual(out, ["<redacted:private_key>"])

    def test_numbered_keeps_the_begin_line_number(self):
        r = redact.Redactor()
        got = []
        for line in ["before"] + self.PEM + ["after"]:
            got += r.feed_numbered(line)
        got += r.flush_numbered()
        self.assertEqual(got, [(1, "before"), (2, "<redacted:private_key>"), (7, "after")])

    def test_public_certificate_kept(self):
        cert = [BEGIN + "CERTIFICATE-----", "MIIBszCCAVmgAwIBAgIU", END + "CERTIFICATE-----"]
        out, counts = run(cert)
        self.assertEqual(out, cert)
        self.assertEqual(counts, {})

    def test_unterminated_block_ends_at_the_first_line_that_is_not_key_text(self):
        lines = [BEGIN + PRIV] + ["c3ludGhldGlj"] * 30 + ["later"]
        out, counts = run(lines)
        self.assertEqual(out, ["<redacted:private_key>", "later"])
        self.assertEqual(counts, {"private_key": 1})

    def test_unterminated_block_stops_hiding_at_the_cap(self):
        lines = [BEGIN + PRIV] + ["c3ludGhldGlj"] * redact.PEM_MAX_LINES + ["x y"]
        out, _ = run(lines)
        self.assertEqual(out, ["<redacted:private_key>", "x y"])
        out, _ = run(lines[:-1] + ["c3ludGhldGlj", "x y"])
        self.assertEqual(out[-1], "x y")          # past the cap, lines are shown again
        self.assertEqual(len(out), 3)

    def test_one_line_key_in_json(self):
        line = ('"key": "' + BEGIN + PRIV + '\\nMIIEsynthetic\\n'
                + END + PRIV + '\\n", "x": 1')
        out, counts = run([line])
        self.assertEqual(out, ['"key": "<redacted:private_key>\\n", "x": 1'])
        self.assertEqual(counts, {"private_key": 1})

    def test_timestamped_block(self):
        pem = [f"[2026-10-12T10:00:00.000Z] {l}" for l in self.PEM]
        out, counts = run(pem + ["[2026-10-12T10:00:01.000Z] next"])
        self.assertEqual(out, ["[2026-10-12T10:00:00.000Z] <redacted:private_key>",
                               "[2026-10-12T10:00:01.000Z] next"])


class TestTokenShape(Case):
    def test_each_shape(self):
        for token in ALL_TOKENS:
            with self.subTest(token=token[:6]):
                self.assert_redacted(f"using {token} now", "token_shape", token)

    def test_every_row_has_a_test_token(self):
        for name, pattern in redact.TOKEN_SHAPES:
            with self.subTest(shape=name):
                self.assertTrue(any(pattern.search(t) for t in ALL_TOKENS), name)

    def test_table_rows_are_name_and_pattern(self):
        self.assertTrue(all(len(row) == 2 for row in redact.TOKEN_SHAPES))

    def test_prefixes_and_short_lookalikes_kept(self):
        for line in ("AKIA is a prefix only", "ghp_short", "glpat-short",
                     "xoxb-1", "npm_install", "pypi-package", "sk-ant-x",
                     "sk_live_x", "AIza too short",
                     "sk-learn-is-a-short-name", "sk-" + "a-very-long-kebab-case-name-without-any-digit",
                     "https://hooks.example.com/services/health"):
            with self.subTest(line=line):
                self.assert_kept(line)


class TestRedactText(unittest.TestCase):
    def test_whole_text(self):
        text, counts = redact.redact_text(f"a\npassword=hunter2\n{JWT}", secrets=["zzzz-secret"])
        self.assertEqual(text, "a\npassword=<redacted:key_value>\n<redacted:jwt>")
        self.assertEqual(counts, {"key_value": 1, "jwt": 1})

    def test_empty(self):
        self.assertEqual(redact.redact_text(""), ("", {}))

    def test_clean_text_unchanged(self):
        text = "user@example.com from 10.0.0.1 via build.example.com"
        self.assertEqual(redact.redact_text(text), (text, {}))


class TestRedactValue(unittest.TestCase):
    def test_nested_structure(self):
        value = {"title": f"rotate {GIT_TOKEN}", "n": 3, "ok": True, "none": None,
                 "items": ["fine", "password=hunter2", ("tuple", JWT)],
                 "password": "kept-key-names"}
        out, counts = redact.redact_value(value)
        self.assertEqual(out["title"], "rotate <redacted:token_shape>")
        self.assertEqual(out["items"][1], "password=<redacted:key_value>")
        self.assertEqual(out["items"][2], ("tuple", "<redacted:jwt>"))
        self.assertEqual((out["n"], out["ok"], out["none"]), (3, True, None))
        self.assertIn("password", out)            # keys are never rewritten
        self.assertEqual(counts, {"token_shape": 1, "key_value": 1, "jwt": 1})
        self.assertIn(GIT_TOKEN, value["title"])  # the input is not mutated

    def test_own_secret(self):
        out, counts = redact.redact_value(["x my-own-secret y"], secrets=["my-own-secret"])
        self.assertEqual(out, ["x <redacted:own_secret> y"])
        self.assertEqual(counts, {"own_secret": 1})


class TestFormatCounts(unittest.TestCase):
    def test_kind_order_and_empty(self):
        self.assertEqual(redact.format_counts({"token_shape": 2, "jwt": 1}),
                         "1 jwt, 2 token_shape")
        self.assertEqual(redact.format_counts({}), "")

    def test_formatted_counts_survive_redaction(self):
        note = "redacted: " + redact.format_counts({k: 1 for k in redact.KINDS})
        self.assertEqual(redact.redact_text(note), (note, {}))


class TestStream(unittest.TestCase):
    def test_order_and_count_over_10000_lines(self):
        lines = [f"line {i}" for i in range(10_000)]
        lines[5000:5000] = TestPrivateKey.PEM          # 5 lines in, one line out
        out, counts = run(lines)
        self.assertEqual(len(out), 10_001)
        self.assertEqual(out[:3], ["line 0", "line 1", "line 2"])
        self.assertEqual(out[5000], "<redacted:private_key>")
        self.assertEqual(out[-1], "line 9999")
        self.assertEqual(counts, {"private_key": 1})

    def test_buffer_never_holds_more_than_a_run(self):
        r = redact.Redactor()
        held = 0
        for line in TestEnvDump.ENV * 3:
            r.feed(line)
            held = max(held, len(r._env))
        self.assertLessEqual(held, redact.ENV_RUN)

    def test_counts_never_hold_values(self):
        _, counts = run(["password=hunter2", JWT])
        self.assertEqual(set(counts.values()), {1})
        self.assertTrue(set(counts) <= set(redact.KINDS))


class TestLongLines(unittest.TestCase):
    """No rule may take quadratic time on a long line without separators."""

    def test_100_kb_lines_finish_fast(self):
        import time
        n = 100_000
        for line in ("-" * n, "a." * (n // 2), "ab-cd." * (n // 6), "a+" * (n // 2),
                     "x" * n, "a:" * (n // 2), "--password" * (n // 10),
                     'password="' * (n // 10), "Bearer " * (n // 7)):
            with self.subTest(line=line[:12]):
                start = time.perf_counter()
                redact.redact_text(line)
                self.assertLess(time.perf_counter() - start, 1.0)


class TestCli(unittest.TestCase):
    SCRIPT = LIB / "redact.py"

    def cli(self, *args, stdin="", env=None):
        return subprocess.run([sys.executable, str(self.SCRIPT), *args], input=stdin,
                              capture_output=True, text=True, timeout=60,
                              env={**os.environ, **(env or {})})

    def test_stdin_to_stdout_quiet_by_default(self):
        proc = self.cli(stdin=f"a\npassword=hunter2\nusing {GIT_TOKEN}\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout,
                         "a\npassword=<redacted:key_value>\nusing <redacted:token_shape>\n")
        self.assertEqual(proc.stderr, "")

    def test_counts_on_stderr_as_json(self):
        proc = self.cli("--counts", stdin="password=hunter2\n")
        self.assertEqual(json.loads(proc.stderr), {"key_value": 1})
        self.assertNotIn("hunter2", proc.stderr)

    def test_own_secrets_come_from_named_env_vars(self):
        own = "own-" + "s3cr3t-value"
        proc = self.cli("--secret-env", "KIT_TEST_SECRET", "--counts",
                        stdin=f"echo {own}\n", env={"KIT_TEST_SECRET": own})
        self.assertEqual(proc.stdout, "echo <redacted:own_secret>\n")
        self.assertEqual(json.loads(proc.stderr), {"own_secret": 1})

    def test_file_argument_and_no_trailing_newline(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log.txt"
            path.write_text(f"x {JWT}", encoding="utf-8")
            proc = self.cli(str(path))
        self.assertEqual(proc.stdout, "x <redacted:jwt>")

    def test_invalid_utf8_on_stdin_is_replaced_not_fatal(self):
        proc = subprocess.run([sys.executable, str(self.SCRIPT)],
                              input=b"\xff\xfe x\npassword=hunter2\n",
                              capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.decode("utf-8"),
                         "\ufffd\ufffd x\npassword=<redacted:key_value>\n")

    def test_missing_file_fails(self):
        proc = self.cli("/does/not/exist.log")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")


class TestStdlibOnly(unittest.TestCase):
    def test_imports_stdlib_only_and_no_relative_imports(self):
        tree = ast.parse((LIB / "redact.py").read_text(encoding="utf-8"))
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "no relative imports")
                mods.add(node.module.split(".")[0])
        self.assertLessEqual(mods, {"re", "typing", "__future__", "argparse", "json",
                                    "os", "sys"})


if __name__ == "__main__":
    unittest.main()
