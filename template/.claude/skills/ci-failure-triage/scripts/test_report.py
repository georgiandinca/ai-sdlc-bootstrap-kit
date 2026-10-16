#!/usr/bin/env python3
"""Stats and failure categories from local test reports, read-only and redacted.

  python3 test_report.py <path, folder or glob>... [--format auto|junit|go-json|jest-json|tap]
                         [--compare <path, folder or glob>...] [--json]

Formats live in PARSERS, one row each: a name, a detector and a parser. The format is
auto-detected from the content unless --format names it. Adding a format is one
parser function, one row and one fixture.
- junit      JUnit XML: JVM runners (Surefire, Gradle), pytest --junitxml, .NET and
             JS loggers and many more. Surefire's rerun elements (flakyFailure,
             flakyError) are read. A file with a DOCTYPE or ENTITY is refused.
- go-json    `go test -json` output.
- jest-json  Jest `--json` and Vitest `--reporter=json` output.
- tap        TAP 12/13/14, with YAML diagnostics and indented subtests (node --test,
             prove, bats, ...). A parent whose subtests are listed is not counted.
A folder means the REPORT_SUFFIXES files directly in it; `-` reads stdin.

Each failure gets one category from RULES, in order, first match wins, on its type
and the first MATCH_CHARS characters of its text: infra, network, timeout, build,
config, assertion, else other. Add a row to RULES to teach it a new pattern.

"Flaky candidate" is a tag with a reason, never a verdict: a rerun that failed then
passed in the same run, or a --compare report where the same test passed. One report
alone never makes a test a flaky candidate.

Messages are redacted by the kit's shared redactor (scripts/lib/redact.py) and clipped
to MESSAGE_CHARS; without the redactor the script stops and shows nothing. Bounds: at
most MAX_FILES files of MAX_FILE_BYTES each; TEXT_KEEP characters kept per failure.
Stdlib only, Python 3.9+. It reads and prints; it never writes a file, never uses the
network and never runs a program.

Adapted from Emil Dan's fork of this kit (MIT).
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, NamedTuple

sys.dont_write_bytecode = True        # no __pycache__ next to the installed skill


def _load_redactor():
    """The kit's one redactor: the nearest scripts/lib/redact.py above this file."""
    for base in Path(__file__).resolve().parents:
        lib = base / "scripts" / "lib"
        if (lib / "redact.py").is_file():
            sys.path.insert(0, str(lib))
            import redact
            return redact
    sys.stderr.write("test_report.py: cannot find scripts/lib/redact.py above this skill; "
                     "nothing is shown unredacted.\n")
    sys.exit(2)


redact = _load_redactor()

MAX_FILES = 2000
MAX_FILE_BYTES = 50 * 1024 * 1024
MESSAGE_CHARS = 300
MATCH_CHARS = 4000
TEXT_KEEP = 8000
SLOWEST = 10
SKIPPED_MAX = 100        # skipped test ids listed at most (the count is in stats)
REPORT_SUFFIXES = (".xml", ".json", ".jsonl", ".ndjson", ".tap")
CATEGORIES = ("infra", "network", "timeout", "build", "config", "assertion", "other")


def _rule(name, category, pattern):
    return name, category, re.compile(pattern, re.I | re.M)


# (rule name, category, pattern): checked in this order; the first match wins.
RULES = [
    _rule("out-of-memory", "infra", r"OutOfMemoryError|\bOOMKilled\b|\bMemoryError\b|"
                                    r"JavaScript heap out of memory|runtime: out of memory"),
    _rule("disk-full", "infra", r"No space left on device|\bENOSPC\b"),
    _rule("container-daemon", "infra", r"Cannot connect to the Docker daemon"),
    _rule("killed", "infra", r"exit (?:code|status):? 137|signal: killed|\bSIGKILL\b"),
    _rule("open-files", "infra", r"Too many open files|\bEMFILE\b"),
    _rule("refused", "network", r"ConnectException|ConnectionRefusedError|\bECONNREFUSED\b|"
                                r"Connection refused|\bdial tcp\b"),
    _rule("dns", "network", r"UnknownHostException|\bENOTFOUND\b|\bEAI_AGAIN\b|no such host|"
                            r"Name or service not known|Temporary failure in name resolution"),
    _rule("socket-timeout", "network", r"SocketTimeoutException|\bETIMEDOUT\b"),
    _rule("tls", "network", r"SSLHandshakeException|PKIX path building failed|"
                            r"CERTIFICATE_VERIFY_FAILED|x509: certificate"),
    _rule("reset", "network", r"\bECONNRESET\b|Connection reset|ConnectionResetError|Broken pipe"),
    _rule("timeout-type", "timeout", r"TimeoutException|TimeoutError"),
    _rule("timed-out", "timeout", r"timed out"),
    _rule("deadline", "timeout", r"context deadline exceeded|DeadlineExceeded"),
    _rule("test-timeout", "timeout", r"Exceeded timeout|There was a timeout in the fork"),
    _rule("go-build", "build", r"\[(?:build|setup) failed\]"),
    _rule("typescript", "build", r"\berror TS\d+"),
    _rule("rust", "build", r"\berror\[E\d+\]"),
    _rule("compile", "build", r"COMPILATION ERROR|compilation failed|cannot find symbol|"
                              r"\bSyntaxError\b"),
    _rule("module-missing", "config", r"ModuleNotFoundError|ImportError|Cannot find module|"
                                      r"ClassNotFoundException|NoClassDefFoundError|"
                                      r"cannot find package|no required module provides"),
    _rule("app-context", "config", r"Failed to load ApplicationContext|BeanCreationException|"
                                   r"NoSuchBeanDefinitionException"),
    _rule("missing-setting", "config", r"Could not resolve placeholder|environment variable "
                                       r"\S+ (?:is )?(?:not set|missing|undefined|required)|"
                                       r"missing (?:required )?(?:property|configuration|"
                                       r"setting)"),
    _rule("assertion-type", "assertion", r"AssertionError|AssertionFailedError|"
                                         r"ComparisonFailure|ERR_ASSERTION"),
    _rule("expected-actual", "assertion", r"\bExpected: |\bReceived: |\bExpecting\b|"
                                          r"expected:\s*<.*>\s*but was:\s*<"),
    _rule("assert-statement", "assertion", r"^(?:E\s+)?assert\s"),
    _rule("testify", "assertion", r"Error Trace:"),
    _rule("got-expected", "assertion", r"\bgot:\s.*\n\s*expected:\s"),
]

# Where the failing test is: (pattern) with groups file and line, tried in order.
LOCATIONS = [
    re.compile(r"at [\w.$<>]+\(([\w$]+(?:Test|Tests|IT|Spec|TestCase)\.(?:java|kt|groovy|"
               r"scala)):(\d+)\)"),                                         # JVM
    re.compile(r"\b(\w+_test\.go):(\d+)"),                                  # Go
    re.compile(r"([\w.-]+\.(?:test|spec)\.[cm]?[jt]sx?):(\d+)"),            # JS / TS
    re.compile(r"((?:[\w.-]+/){0,8}(?:test_\w+|\w+_test)\.py):(\d+)"),      # Python
    re.compile(r"in \S*?([\w.]+Tests?\.cs):line (\d+)"),                    # .NET
]


class Refused(Exception):
    """A plain reason to stop (exit 2)."""


def categorize(kind, message):
    """(category, rule name) for a failure's type and text; ("other", None) when no
    rule matches."""
    text = f"{kind or ''}\n{(message or '')[:MATCH_CHARS]}"
    for name, category, pattern in RULES:
        if pattern.search(text):
            return category, name
    return "other", None


def location(text):
    for pattern in LOCATIONS:
        m = pattern.search(text or "")
        if m:
            return f"{m.group(1)}:{m.group(2)}"
    return None


# --- parsers: each returns a list of test records -----------------------------------
# A record: {group, name, status (passed|failed|error|skipped|passed_on_rerun),
#            duration (s), kind, text, flaky_why}

def _rec(group, name, status, duration=0.0, kind="", text="", why=None):
    try:
        duration = float(duration or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return {"group": group or "", "name": name or "", "status": status, "duration": duration,
            "kind": kind or "", "text": (text or "")[:TEXT_KEEP], "flaky_why": why}


def parse_junit(raw, data, label):
    if "<!DOCTYPE" in raw or "<!ENTITY" in raw:
        raise Refused(f"{label}: refused: a DOCTYPE or ENTITY declaration (not read, for safety)")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise Refused(f"{label}: not valid XML ({exc})") from None
    out = []
    for case in root.iter("testcase"):
        group = case.get("classname") or case.get("class") or ""
        name, dur = case.get("name"), case.get("time")

        def first(*tags):
            for tag in tags:
                el = case.find(tag)
                if el is not None:
                    return el
            return None

        failure, error, skipped = first("failure"), first("error"), first("skipped")
        flaky = first("flakyFailure", "flakyError")
        bad = failure if failure is not None else error
        if bad is not None:
            status = "failed" if failure is not None else "error"
            text = "\n".join(x for x in (bad.get("message"), bad.text) if x)
            out.append(_rec(group, name, status, dur, bad.get("type"), text))
        elif skipped is not None:
            out.append(_rec(group, name, "skipped", dur))
        elif flaky is not None:
            text = "\n".join(x for x in (flaky.get("message"), flaky.text) if x)
            out.append(_rec(group, name, "passed_on_rerun", dur, flaky.get("type"), text,
                            f"failed, then passed on a rerun in the same run ({flaky.tag})"))
        else:
            out.append(_rec(group, name, "passed", dur))
    return out


_GO_NOISE = re.compile(r"^\s*(=== (RUN|PAUSE|CONT|NAME)|--- (PASS|FAIL|SKIP))")


def parse_go(raw, data, label):
    tests, packages, order = {}, {}, []
    for i, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            raise Refused(f"{label}: line {i} is not go test -json output") from None
        if not isinstance(ev, dict):
            raise Refused(f"{label}: line {i} is not go test -json output")
        pkg, test, action = ev.get("Package") or "", ev.get("Test"), ev.get("Action")
        key = (pkg, test)
        store = tests if test else packages
        if test and key not in tests:
            order.append(key)
        st = store.setdefault(key, {"status": None, "out": "", "elapsed": 0.0})
        if action == "output":
            out = ev.get("Output") or ""
            if len(st["out"]) < TEXT_KEEP and not _GO_NOISE.match(out):
                st["out"] += out
        elif action in ("pass", "fail", "skip"):
            st["status"] = action
            st["elapsed"] = ev.get("Elapsed") or 0.0
    out = []
    failed_pkgs = {k[0] for k, v in tests.items() if v["status"] == "fail"}
    mapping = {"pass": "passed", "skip": "skipped", "fail": "failed"}
    for pkg, test in order:
        st = tests[(pkg, test)]
        status = st["status"]
        if status is None and packages.get((pkg, None), {}).get("status") == "fail":
            status = "fail"                      # still running when the package failed
        if status in mapping:
            out.append(_rec(pkg, test, mapping[status], st["elapsed"], "", st["out"]))
    for (pkg, _), st in packages.items():
        if st["status"] == "fail" and pkg not in failed_pkgs:   # a build or setup failure,
            out.append(_rec(pkg, "(package)", "error", st["elapsed"], "", st["out"]))  # or a crash
    return out


def parse_jest(raw, data, label):
    out = []
    for suite in data.get("testResults") or []:
        group = suite.get("name") or suite.get("testFilePath") or ""
        results = suite.get("assertionResults") or suite.get("testResults") or []
        if suite.get("status") == "failed" and not results:
            out.append(_rec(group, "(suite)", "error", 0, "", suite.get("message")
                            or suite.get("failureMessage") or ""))
            continue
        for a in results:
            name = a.get("fullName") or " ".join([*(a.get("ancestorTitles") or []),
                                                  a.get("title") or ""]).strip()
            status = {"passed": "passed", "failed": "failed", "pending": "skipped",
                      "skipped": "skipped", "todo": "skipped",
                      "disabled": "skipped"}.get(a.get("status"), "passed")
            text = "\n".join(a.get("failureMessages") or [])
            dur = (a.get("duration") or 0) / 1000.0
            out.append(_rec(group, name, status, dur, "", text))
    return out


_TAP_TEST = re.compile(r"^(?P<ind>\s*)(?P<not>not )?ok\b(?:\s+\d+)?(?:\s*-)?\s*"
                       r"(?P<desc>[^#]*?)\s*(?:#\s*(?P<dir>\w+)\b\s*(?P<why>.*))?$")
_TAP_SUBTEST = re.compile(r"^(?P<ind>\s*)# Subtest: (?P<name>.*)$")
_TAP_BAIL = re.compile(r"^\s*Bail out!\s*(?P<why>.*)$")
_TAP_YAML_START = re.compile(r"^\s*---\s*$")
_TAP_YAML_END = re.compile(r"^\s*\.\.\.\s*$")
_TAP_COMMENT = re.compile(r"^\s*#\s?(?P<text>.*)$")
_YAML_KEY = re.compile(r"^(?P<key>[\w-]+):\s*(?P<value>.*)$")
TAP_TEXT_KEYS = ("error", "message", "stack", "at", "expected", "actual", "got", "wanted",
                 "found")


def _tap_yaml(lines):
    """Top-level keys of a TAP YAML block as strings (block scalars joined)."""
    body = [l for l in lines if l.strip()]
    if not body:
        return {}
    base = min(len(l) - len(l.lstrip()) for l in body)
    fields, key = {}, None
    for line in lines:
        indent = len(line) - len(line.lstrip())
        m = _YAML_KEY.match(line[base:]) if indent == base else None
        if m:
            key, value = m.group("key"), m.group("value").strip()
            fields[key] = "" if value[:1] in ("|", ">") else value.strip("'\"")
        elif key is not None:
            fields[key] = (fields[key] + "\n" + line[base:].strip()).strip("\n")
    return fields


def parse_tap(raw, data, label):
    out, names = [], {}
    last, prev_depth, diag_open, yaml = None, None, False, None
    for line in raw.splitlines():
        if yaml is not None:
            if _TAP_YAML_END.match(line):
                if last is not None:
                    _apply_yaml(last, _tap_yaml(yaml))
                yaml = None
            elif len(yaml) < 400:
                yaml.append(line)
            continue
        if _TAP_YAML_START.match(line) and last is not None:
            yaml, diag_open = [], False
            continue
        m = _TAP_SUBTEST.match(line)
        if m:
            depth = len(m.group("ind"))
            names = {d: n for d, n in names.items() if d < depth}
            names[depth] = m.group("name").strip()
            diag_open = False
            continue
        m = _TAP_BAIL.match(line)
        if m:
            out.append(_rec("", "(bail out)", "error", 0, "", m.group("why")))
            last, diag_open = None, False
            continue
        m = _TAP_TEST.match(line)
        if m:
            depth = len(m.group("ind"))
            parent = prev_depth is not None and prev_depth > depth
            prev_depth = depth
            directive = (m.group("dir") or "").upper()
            failed = bool(m.group("not"))
            if directive.startswith("SKIP") or (failed and directive == "TODO"):
                status = "skipped"
            else:
                status = "failed" if failed else "passed"
            group = " > ".join(n for d, n in sorted(names.items()) if d < depth)
            rec = _rec(group, m.group("desc").strip(), status)
            last = None if parent else rec        # a parent with listed subtests: not a test
            if last is not None:
                out.append(rec)
            diag_open = status == "failed" and last is not None
            continue
        m = _TAP_COMMENT.match(line)
        if m and diag_open:
            last["text"] = (last["text"] + "\n" + m.group("text").strip()).strip()[:TEXT_KEEP]
            continue
        diag_open = False
    return out


def _apply_yaml(rec, fields):
    try:
        rec["duration"] = float(fields.get("duration_ms") or 0) / 1000.0
    except ValueError:
        pass
    rec["kind"] = rec["kind"] or fields.get("name", "")
    text = "\n".join(fields[k] for k in TAP_TEXT_KEYS if fields.get(k))
    rec["text"] = "\n".join(x for x in (rec["text"], text) if x)[:TEXT_KEEP]


def _first_line(raw):
    return next((l.strip() for l in raw.splitlines()[:50] if l.strip()), "")


def _detect_go(raw, data):
    try:
        ev = json.loads(_first_line(raw))
    except ValueError:
        return False
    return isinstance(ev, dict) and "Action" in ev


_TAP_HEAD = re.compile(r"^(?:TAP version \d+|\d+\.\.\d+|(?:not )?ok\b)")


def _detect_tap(raw, data):
    return data is None and bool(_TAP_HEAD.match(_first_line(raw)))


class Parser(NamedTuple):
    name: str
    detect: Callable          # (raw text, parsed JSON or None) -> bool
    parse: Callable           # (raw text, parsed JSON or None, label) -> [record]
    wants_object: bool        # parse needs one JSON object


# The registry, in detection order. Add a format here.
PARSERS = [
    Parser("junit", lambda raw, data: raw.lstrip().startswith("<"), parse_junit, False),
    Parser("jest-json", lambda raw, data: isinstance(data, dict) and "testResults" in data,
           parse_jest, True),
    Parser("go-json", _detect_go, parse_go, False),
    Parser("tap", _detect_tap, parse_tap, False),
]
FORMATS = ("auto", *(p.name for p in PARSERS))


# --- inputs ------------------------------------------------------------------------

def expand(patterns):
    """[(label, Path or None for stdin)] for paths, folders, globs and '-'."""
    found = []
    for pat in patterns:
        if pat == "-":
            found.append(("-", None))
            continue
        p = Path(pat)
        if p.is_dir():
            files = sorted(f for f in p.iterdir()
                           if f.is_file() and f.suffix.lower() in REPORT_SUFFIXES)
        elif p.is_file():
            files = [p]
        else:
            files = sorted(Path(x) for x in glob.glob(pat, recursive=True) if Path(x).is_file())
        if not files:
            raise Refused(f"No file matches {pat}.")
        found += [(str(f), f) for f in files]
        if len(found) > MAX_FILES:
            raise Refused(f"Too many report files: more than {MAX_FILES} files. Give a "
                          "narrower path or glob.")
    return found


def read_input(label, path, stdin):
    too_big = Refused(f"{label}: larger than {MAX_FILE_BYTES} bytes; not read.")
    if path is None:
        raw = stdin.read(MAX_FILE_BYTES + 1)
    else:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise too_big
        raw = path.read_bytes().decode("utf-8", "replace")
    if len(raw) > MAX_FILE_BYTES:
        raise too_big
    return raw


def load(patterns, fmt, stdin):
    """(inputs, records)."""
    by_name = {p.name: p for p in PARSERS}
    inputs, records = [], []
    for label, path in expand(patterns):
        raw = read_input(label, path, stdin)
        data = None
        if raw.lstrip()[:1] in ("{", "["):
            try:
                data = json.loads(raw)
            except ValueError:
                data = None
        if fmt == "auto":
            chosen = next((p for p in PARSERS if p.detect(raw, data)), None)
            if chosen is None:
                raise Refused(f"{label}: unknown report format; give --format "
                              f"({', '.join(FORMATS[1:])}).")
        else:
            chosen = by_name[fmt]
        if chosen.wants_object and not isinstance(data, dict):
            raise Refused(f"{label}: not {chosen.name} (expected one JSON object).")
        recs = chosen.parse(raw, data, label)
        for r in recs:
            r["report"] = label
        records += recs
        inputs.append({"path": label, "format": chosen.name})
    return inputs, records


# --- the report --------------------------------------------------------------------

def test_id(r):
    return f"{r['group']}#{r['name']}" if r["group"] else r["name"]


def report(inputs, records, compare):
    redactions = {}

    def clean(text):
        first_line = next((l.strip() for l in (text or "").splitlines() if l.strip()), "")
        red, counts = redact.redact_text(first_line)
        for k, v in counts.items():
            redactions[k] = redactions.get(k, 0) + v
        return red if len(red) <= MESSAGE_CHARS else red[:MESSAGE_CHARS - 1] + "…"

    key = {"passed": "passed", "failed": "failed", "error": "errors", "skipped": "skipped",
           "passed_on_rerun": "rerun_passed"}
    stats = {"total": len(records), **{v: 0 for v in key.values()}, "duration_s": 0.0}
    for r in records:
        stats[key[r["status"]]] += 1
        stats["duration_s"] += r["duration"]
    stats["duration_s"] = round(stats["duration_s"], 3)

    passed_elsewhere = {}
    for r in compare:
        if r["status"] in ("passed", "passed_on_rerun"):
            passed_elsewhere.setdefault(test_id(r), r["report"])

    failures, groups = [], {}
    for r in records:
        if r["status"] not in ("failed", "error", "passed_on_rerun"):
            continue
        tid = test_id(r)
        category, matched = categorize(r["kind"], r["text"])
        why = r["flaky_why"]
        if why is None and tid in passed_elsewhere:
            why = f"passed in {passed_elsewhere[tid]}"
        failures.append({"id": tid, "status": r["status"], "category": category,
                         "matched": matched, "message": clean(r["text"] or r["kind"]),
                         "location": location(r["text"]), "report": r["report"],
                         "flaky_candidate": why is not None, "why": why})
        if r["status"] != "passed_on_rerun":
            groups[r["group"]] = groups.get(r["group"], 0) + 1
    by_group = [{"group": g, "failed": n}                # most failures first, then as read
                for g, n in sorted(groups.items(), key=lambda kv: -kv[1])]
    slowest = [{"id": test_id(r), "duration_s": round(r["duration"], 3)}
               for r in sorted(records, key=lambda r: -r["duration"])[:SLOWEST]
               if r["duration"] > 0]
    skipped = [test_id(r) for r in records if r["status"] == "skipped"][:SKIPPED_MAX]
    return {"inputs": inputs, "stats": stats, "by_group": by_group, "slowest": slowest,
            "failures": failures, "skipped": skipped,
            "redactions": {k: redactions[k] for k in redact.KINDS if redactions.get(k)}}


def render(doc) -> list:
    s = doc["stats"]
    out = [f"{len(doc['inputs'])} report(s): " + ", ".join(i["path"] for i in doc["inputs"][:5])
           + (", …" if len(doc["inputs"]) > 5 else ""),
           f"{s['total']} tests: {s['passed']} passed, {s['failed']} failed, {s['errors']} "
           f"errors, {s['skipped']} skipped, {s['rerun_passed']} passed on rerun "
           f"({s['duration_s']} s)"]
    if doc["by_group"]:
        out.append("Failures per suite or package: "
                   + ", ".join(f"{g['group'] or '?'} {g['failed']}" for g in doc["by_group"]))
    for f in doc["failures"]:
        line = f"- {f['status']} {f['id']} [{f['category']}]"
        if f["location"]:
            line += f" at {f['location']}"
        if f["message"]:
            line += f": {f['message']}"
        out.append(line)
        if f["flaky_candidate"]:
            out.append(f"    flaky candidate: {f['why']}")
    if doc["skipped"]:
        more = s["skipped"] - len(doc["skipped"])
        out.append("Skipped: " + ", ".join(doc["skipped"])
                   + (f" (and {more} more)" if more > 0 else ""))
    if doc["slowest"]:
        out.append("Slowest: " + ", ".join(f"{x['id']} {x['duration_s']} s"
                                           for x in doc["slowest"][:5]))
    if doc["redactions"]:
        out.append("Redacted (values never shown): "
                   + ", ".join(f"{k} {v}" for k, v in doc["redactions"].items()) + ".")
    return out


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="test_report.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="report files, folders or globs; - for stdin")
    ap.add_argument("--format", choices=FORMATS, default="auto", help="the report format")
    ap.add_argument("--compare", nargs="+", metavar="PATH",
                    help="an earlier or later run of the same tests")
    ap.add_argument("--json", action="store_true", help="structured output")
    return ap


def main(argv=None, stdin=None) -> int:
    stdin = stdin or sys.stdin
    args = parser().parse_args(argv)
    try:
        inputs, records = load(args.paths, args.format, stdin)
        compare = load(args.compare, args.format, stdin)[1] if args.compare else []
    except Refused as exc:
        print(f"test_report.py: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"test_report.py: cannot read a report ({type(exc).__name__}: "
              f"{getattr(exc, 'filename', '') or ''})", file=sys.stderr)
        return 2
    doc = report(inputs, records, compare)
    if args.json:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
    else:
        print("\n".join(render(doc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
