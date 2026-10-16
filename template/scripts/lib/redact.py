#!/usr/bin/env python3
"""Redact secrets from text before it is logged, persisted or shown: one rule per kind.

Each match is replaced by `<redacted:KIND>`. `Redactor.counts` counts matches per kind;
it never holds a value, a part of one or its length. Emails, IP addresses and host
names are left alone. Redaction is best effort: whoever shows the output still quotes
only the lines they need.

Kinds, in the order they are applied:

- own_secret       the caller's own secrets (each at least MIN_SECRET characters), anywhere.
- auth_header      the value of `Authorization:` / `Proxy-Authorization:` (after an optional
                   scheme word such as Bearer, Basic or token, which is kept); a lone
                   `Bearer <x>` or `Basic <x>` when <x> looks like a token (8 or more token
                   characters, not only lower-case letters).
- jwt              three base64url parts, the first starting `eyJ`.
- cookie           the value of `Cookie:` and `Set-Cookie:`; a bare session cookie
                   (SESSION_COOKIES, e.g. `JSESSIONID=<x>`); an anti-forgery header
                   (CSRF_HEADERS, `Name: <x>`) or field (CSRF_FIELDS, `"name": "<x>"` or
                   `name=<x>`).
- url_credentials  `scheme://user:password@host` -> `scheme://<redacted:url_credentials>@host`.
- key_value        the value after a name that ENDS with a secret word (SECRET_WORDS),
                   then `=`, or `:` followed by a space (or after a quoted name, as in
                   JSON); also in `-Dname=value`. The name is kept. `Test.badPassword:42`
                   (a test summary line) is kept. The name must end with the word:
                   `passwordPolicy=strict` and `tokens_total=3` are kept; `dbPassword=x`
                   and `GIT_TOKEN=x` are not.
- env_dump         ENV_RUN or more lines in a row shaped `NAME=value` with an upper-case
                   NAME (the output of `env`, `printenv` or `set`): every value in the run.
                   A shorter run is not a dump; its secret-named lines are caught by
                   key_value.
- private_key      a `-----BEGIN … PRIVATE KEY-----` block up to its END line becomes one
                   line `<redacted:private_key>`. A block with no END line ends at the first
                   line that is not key text, or after PEM_MAX_LINES lines.
- token_shape      well-known public token formats (TOKEN_SHAPES).

Stack-specific names live in the data tables below; add a row, not a rule.

Library (scripts import this one copy; never copy the file):

    sys.path.insert(0, "<scripts>/lib"); import redact
    text, counts = redact.redact_text(text, secrets=[own_token])
    value, counts = redact.redact_value(row_or_json)    # strings inside dicts/lists
    r = redact.Redactor(); r.feed(line) ...; r.flush()   # streaming, line by line

Command line (stdin or FILE -> stdout; own secrets by env var NAME, never on argv):

    python3 scripts/lib/redact.py [--secret-env NAME]... [--counts] [FILE]

`--counts` prints the counts per kind to stderr as JSON. Stdlib only.

Ported from Emil Dan's fork of this kit (MIT).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Dict, Iterable, List, Tuple

KINDS = ("own_secret", "auth_header", "jwt", "cookie", "url_credentials",
         "key_value", "env_dump", "private_key", "token_shape")

ENV_RUN = 5               # lines in a row that make an environment dump
PEM_MAX_LINES = 400       # key lines hidden at most when a block has no END line
MIN_SECRET = 4            # shorter own secrets are not replaced (too many false hits)

SECRET_WORDS = ("password", "passwd", "pwd", "passphrase", "secret", "token", "apikey",
                "api_key", "api-key", "access_key", "private_key", "client_secret",
                "secret_key", "credentials")

# Session cookies that show up bare (`NAME=value`) in URLs and logs; one row per web stack.
SESSION_COOKIES = ("JSESSIONID", "PHPSESSID", "ASP.NET_SessionId", "connect.sid",
                   "laravel_session", "_session_id")
# Anti-forgery tokens: headers (`Name: value`) and form/JSON fields (`"name": "value"`,
# `name=value`).
CSRF_HEADERS = ("Jenkins-Crumb", "X-CSRF-Token", "X-XSRF-Token", "X-CSRFToken")
CSRF_FIELDS = ("crumb", "csrfmiddlewaretoken", "csrf_token", "authenticity_token", "_csrf")

# (name, pattern): a whole match is replaced. Public token formats; add a row for a new one.
TOKEN_SHAPES = [
    ("cloud access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("git hosting token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("git hosting fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("git hosting token (lab)", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}")),
    ("chat token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("issue tracker API token", re.compile(r"\bATATT[A-Za-z0-9_=-]{20,}")),
    ("cloud API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("package registry token (js)", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("package registry token (python)", re.compile(r"\bpypi-AgE[A-Za-z0-9_-]{50,}")),
    ("LLM API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("payments API key", re.compile(r"\b[rs]k_live_[A-Za-z0-9]{20,}")),
]


def _alt(names: Iterable[str]) -> str:
    return "|".join(map(re.escape, names))


_NOT_MARKER = r"(?!<redacted:)"
_AUTH = re.compile(r"(?i)\b((?:proxy-)?authorization\s*[:=]\s*)"
                   r"((?:bearer|basic|token|digest|negotiate|ntlm)\s+)?" + _NOT_MARKER
                   + r"([^\s\"',;]+)")
_LONE_SCHEME = re.compile(r"\b(Bearer|Basic)(\s+)" + _NOT_MARKER + r"([A-Za-z0-9._~+/=-]{8,})")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}")
_COOKIE_HEADER = re.compile(r"(?i)\b((?:set-)?cookie\s*:\s*)" + _NOT_MARKER + r"([^\"'\r\n]+)")
_SESSION_COOKIE = re.compile(r"(?i)(?<![A-Za-z0-9_.-])((?:" + _alt(SESSION_COOKIES) + r")=)"
                             + _NOT_MARKER + r"([^;\s\"'&]+)")
_CSRF_HEADER = re.compile(r"(?i)(?<![A-Za-z0-9_-])((?:" + _alt(CSRF_HEADERS) + r")\s*[:=]\s*)"
                          + _NOT_MARKER + r"([^\s\"',;]+)")
_CSRF_FIELD = re.compile(r"(?i)((?<![A-Za-z0-9_])[\"'](?:" + _alt(CSRF_FIELDS)
                         + r")[\"']\s*:\s*[\"']|(?<![A-Za-z0-9_])(?:" + _alt(CSRF_FIELDS)
                         + r")=)" + _NOT_MARKER + r"([^\s\"'&,;]+)")
_URL_CRED = re.compile(r"\b([A-Za-z][A-Za-z0-9+.-]*://)([^/\s:@]+):([^/\s@]+)@")
_KEY_VALUE = re.compile(
    r"(?i)(?<![A-Za-z0-9_])([\"']?)([A-Za-z0-9_.-]*?(?:" + _alt(SECRET_WORDS)
    + r"))\1(\s*=\s*|\s*:\s+|(?<=[\"'])\s*:\s*)([\"']?)" + _NOT_MARKER
    + r"([^\s\"'&,;]+)")
_ENV = re.compile(r"^(\[[^\]]*\]\s*)?([A-Z_][A-Z0-9_]*)=(.*)$")
_PEM_BEGIN = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
_PEM_END = re.compile(r"-----END [A-Z0-9 ]*PRIVATE KEY-----")
_PEM_BODY = re.compile(r"^(?:\[[^\]]*\]\s*)?(?:([A-Za-z0-9+/=]+)|(?:Proc-Type|DEK-Info): .*)?\s*$")


def _pem_body(line) -> bool:
    """Key text: base64 (not a plain word), a PEM header line, or an empty line."""
    m = _PEM_BODY.match(line)
    if not m:
        return False
    word = m.group(1)
    return not (word and word.isalpha() and (word.islower() or word.isupper()))


def marker(kind: str) -> str:
    return f"<redacted:{kind}>"


class Redactor:
    """Feed lines one at a time; get 0..n redacted lines back. An environment dump needs
    a look-ahead of up to ENV_RUN lines, so lines can come out later than they went in;
    `flush()` returns the rest at the end. `feed_numbered` / `flush_numbered` give each
    line out the number of the line it came from (a private key block keeps the number
    of its BEGIN line), counting from 1. One Redactor may serve many texts; its counts
    add up across them."""

    def __init__(self, secrets=()) -> None:
        self._secrets = sorted({s for s in secrets if s and len(s) >= MIN_SECRET},
                               key=len, reverse=True)
        self.counts: Dict[str, int] = {}
        self._n = 0
        self._env: List[Tuple[int, str]] = []    # candidate dump lines, not yet out
        self._in_dump = False
        self._in_pem = False
        self._pem_lines = 0

    # -- public --
    def feed(self, line: str) -> List[str]:
        return [text for _, text in self.feed_numbered(line)]

    def flush(self) -> List[str]:
        return [text for _, text in self.flush_numbered()]

    def feed_numbered(self, line: str) -> List[Tuple[int, str]]:
        self._n += 1
        n = self._n
        if self._in_pem:
            if _PEM_END.search(line):
                self._in_pem = False
                return []
            if self._pem_lines < PEM_MAX_LINES and _pem_body(line):
                self._pem_lines += 1
                return []
            self._in_pem = False
        if _PEM_BEGIN.search(line):
            return self._release() + [(n, self._begin_pem(line))]
        if _ENV.match(line):
            if self._in_dump:
                return [(n, self._env_line(line))]
            self._env.append((n, line))
            if len(self._env) >= ENV_RUN:
                out = [(i, self._env_line(text)) for i, text in self._env]
                self._env = []
                self._in_dump = True
                return out
            return []
        return self._release() + [(n, self._line(line))]

    def flush_numbered(self) -> List[Tuple[int, str]]:
        self._in_pem = False
        return self._release()

    def text(self, text: str) -> str:
        """One whole text, redacted line by line; the stream state is reset after it."""
        out: List[str] = []
        for line in str(text).split("\n"):
            out += self.feed(line)
        out += self.flush()
        return "\n".join(out)

    # -- inside --
    def _count(self, kind, k=1):
        if k:
            self.counts[kind] = self.counts.get(kind, 0) + k

    def _release(self) -> List[Tuple[int, str]]:
        """The buffered lines were not a dump: out, each redacted on its own."""
        self._in_dump = False
        out = [(i, self._line(text)) for i, text in self._env]
        self._env = []
        return out

    def _env_line(self, line) -> str:
        m = _ENV.match(line)
        if not m.group(3):
            return line
        self._count("env_dump")
        return f"{m.group(1) or ''}{m.group(2)}={marker('env_dump')}"

    def _begin_pem(self, line) -> str:
        self._count("private_key")
        start = _PEM_BEGIN.search(line)
        end = _PEM_END.search(line, start.end())
        before = self._line(line[:start.start()]) if start.start() else ""
        if end:
            after = line[end.end():]
            return before + marker("private_key") + (self._line(after) if after else "")
        self._in_pem, self._pem_lines = True, 0
        return before + marker("private_key")

    def _sub(self, kind, pattern, repl, text) -> str:
        new, k = pattern.subn(repl, text)
        self._count(kind, k)
        return new

    def _line(self, text) -> str:
        if not text:
            return text
        for secret in self._secrets:
            if secret in text:
                self._count("own_secret", text.count(secret))
                text = text.replace(secret, marker("own_secret"))
        text = self._sub("auth_header", _AUTH,
                         lambda m: m.group(1) + (m.group(2) or "") + marker("auth_header"), text)
        text = self._lone_scheme(text)
        text = self._sub("jwt", _JWT, marker("jwt"), text)
        for pattern in (_COOKIE_HEADER, _SESSION_COOKIE, _CSRF_HEADER, _CSRF_FIELD):
            text = self._sub("cookie", pattern, lambda m: m.group(1) + marker("cookie"), text)
        text = self._sub("url_credentials", _URL_CRED,
                         lambda m: m.group(1) + marker("url_credentials") + "@", text)
        text = self._sub("key_value", _KEY_VALUE,
                         lambda m: m.group(1) + m.group(2) + m.group(1) + m.group(3) + m.group(4)
                         + marker("key_value"), text)
        for _name, pattern in TOKEN_SHAPES:
            text = self._sub("token_shape", pattern, marker("token_shape"), text)
        return text

    def _lone_scheme(self, text) -> str:
        def repl(m):
            value = m.group(3)
            if value.isalpha() and value.islower():
                return m.group(0)                 # a word ("Basic authentication"), not a token
            self._count("auth_header")
            return m.group(1) + m.group(2) + marker("auth_header")
        return _LONE_SCHEME.sub(repl, text)


def redact_text(text, secrets=()) -> Tuple[str, Dict[str, int]]:
    """The whole `text`, redacted line by line, and the counts per kind."""
    r = Redactor(secrets=secrets)
    return r.text(text), dict(r.counts)


def redact_value(value, secrets=()):
    """`value` with every string inside it redacted (dicts, lists and tuples are walked;
    dict keys and non-strings are kept), and the counts per kind. The input is not
    changed. For JSON documents, database rows and connector output."""
    r = Redactor(secrets=secrets)

    def walk(v):
        if isinstance(v, str):
            return r.text(v)
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, tuple):
            return tuple(walk(x) for x in v)
        return v

    return walk(value), dict(r.counts)


def format_counts(counts: Dict[str, int]) -> str:
    """`kind=n, …` in KINDS order, for a log or a notes field; "" when nothing was found."""
    return ", ".join(f"{k}={counts[k]}" for k in KINDS if counts.get(k))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Redact secrets from a text stream (stdin or FILE) to stdout.")
    ap.add_argument("file", nargs="?", help="read this file instead of stdin")
    ap.add_argument("--secret-env", action="append", default=[], metavar="NAME",
                    help="also redact the value of this environment variable (repeatable)")
    ap.add_argument("--counts", action="store_true",
                    help="print the counts per kind to stderr as JSON")
    args = ap.parse_args(argv)

    secrets = [os.environ.get(name, "") for name in args.secret_env]
    try:
        src = (open(args.file, encoding="utf-8", errors="replace", newline="")
               if args.file else sys.stdin)
    except OSError as exc:
        print(f"redact: cannot read {args.file}: {exc.strerror}", file=sys.stderr)
        return 2
    r = Redactor(secrets=secrets)
    held: List[str] = []          # the last line out, written once we know what follows

    def emit(lines):
        for out in lines:
            if held:
                sys.stdout.write(held.pop() + "\n")
            held.append(out)

    last = ""
    with src:
        for raw in src:
            last = raw
            emit(r.feed(raw.rstrip("\r\n")))
    emit(r.flush())
    if held:                      # keep the input's final newline, or its lack of one
        sys.stdout.write(held.pop() + ("\n" if last.endswith("\n") else ""))
    if args.counts:
        print(json.dumps(r.counts, sort_keys=True), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
