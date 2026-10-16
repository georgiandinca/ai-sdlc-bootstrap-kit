#!/usr/bin/env python3
"""A read-only, redacted slice of a local log file (plain text or .gz).

  python3 log_slice.py <file> [--since T] [--until T] [--level LEVEL] [--first-error]
                       [--before N] [--after N] [--traces] [--grep RE] [--from-line N]
                       [--tail N] [--max-bytes N] [--json]

Every line is redacted first by the kit's shared redactor (scripts/lib/redact.py):
secrets become <redacted:KIND> and are only counted. Without the redactor the script
stops and shows nothing. Lines keep their number in the whole file, so they can be
cited and used with --from-line. Terminal colour codes are removed as lines are read.

- --since / --until: a time window. ISO-8601 (2026-10-12T10:00:00; a Z or +02:00
  offset is turned into UTC), "2026-10-12 10:00:00", or a bare "10:00" (the date of
  the first time stamp in the file). A stamp is read at the start of a line, bare or
  in square brackets, with - or / between the date parts; level words, markers and
  stack traces are read after it. In a log with stamps, a
  line without one (a stack-trace line) belongs to the line before it.
- --level WARN: WARN and above (LEVEL_WORDS ranks the words; LEVEL_PREFIXES ranks
  lines such as "npm ERR!", "panic:" or a Python "Traceback").
- --first-error: the first line at ERROR or above, or a FAILURE_MARKERS line, with
  --before (10) and --after (30) lines.
- --traces: repeated stack traces grouped by exception and its top SIG_FRAMES frames,
  line numbers stripped. TRACE_SHAPES holds one row per trace shape (JVM, .NET,
  Python, Node, Go); add a row to teach it another.
- --grep, --from-line, --tail, --max-bytes: applied in that order. With no selector
  at all (and no --first-error or --traces) the last DEFAULT_TAIL lines.

Bounds: one pass over the file, a line is read up to LINE_READ_MAX characters (the
rest of it is skipped) and shown up to LINE_CHARS; at most MAX_GROUPS trace groups.
Stdlib only, Python 3.9+. It reads the file and prints; it never writes a file,
never uses the network and never runs a program.

Adapted from Emil Dan's fork of this kit (MIT).
"""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import re
import sys
import zlib
from collections import deque
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True        # no __pycache__ next to the installed skill


REDACTOR_API = ("KINDS", "Redactor", "redact_text", "redact_value")


def _load_redactor():
    """The kit's one redactor: the nearest scripts/lib/redact.py above this file, used
    only if it has the kit redactor's API. Anything else stops the script."""
    for base in Path(__file__).resolve().parents:
        path = base / "scripts" / "lib" / "redact.py"
        if path.is_file():
            try:
                spec = importlib.util.spec_from_file_location("redact", path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            except Exception:         # noqa: BLE001  any failure means: not trusted
                break
            if all(hasattr(module, name) for name in REDACTOR_API):
                return module
            break
    sys.stderr.write("log_slice.py: cannot load the kit's scripts/lib/redact.py above this "
                     "skill; nothing is shown unredacted.\n")
    sys.exit(2)


redact = _load_redactor()

DEFAULT_TAIL, TAIL_MAX = 200, 5000
MAX_BYTES, MAX_BYTES_CEIL = 65_536, 1_048_576
LINE_READ_MAX, LINE_CHARS = 65_536, 2000
GREP_MAX, AROUND_MAX = 200, 200
SAMPLE_LINES, MAX_STARTS, SIG_FRAMES, MAX_GROUPS = 40, 20, 3, 50

# --- data tables -----------------------------------------------------------------

# Level words, searched in the first 120 characters of a line; the first one wins.
LEVEL_WORDS = {"TRACE": 0, "DEBUG": 1, "INFO": 2, "NOTICE": 2, "WARN": 3, "WARNING": 3,
               "ERR": 4, "ERROR": 4, "CRITICAL": 5, "FATAL": 5, "SEVERE": 5}
ERROR_RANK = LEVEL_WORDS["ERROR"]


def _re(pattern):
    return re.compile(pattern)


# (pattern at the start of a line, level): lines that carry their level in another shape.
LEVEL_PREFIXES = [
    (_re(r"^npm ERR!"), "ERROR"),                                # npm
    (_re(r"^Traceback \(most recent call last\):"), "ERROR"),    # Python
    (_re(r"^(?:panic|fatal error): "), "FATAL"),                 # Go runtime
    (_re(r"^error(?:\[E\d+\])?: "), "ERROR"),                    # compilers (rustc, gcc, ...)
]

# A line that marks a failure even without a level word.
FAILURE_MARKERS = [
    _re(r"BUILD FAILURE|BUILD FAILED"),                 # Maven, Gradle, Ant
    _re(r"^--- FAIL:|^FAIL\b"),                         # go test, Jest
    _re(r"\bFAILED\b"),                                 # pytest, generic
    _re(r"^panic: |^fatal error: "),                    # Go runtime
    _re(r"Exception in thread |^Unhandled exception\."),    # JVM, .NET
    _re(r"^Traceback \(most recent call last\):"),      # Python
    _re(r"^npm ERR!"),                                  # npm
]

_AT_FRAME = r"^\s+at (?P<sig>\S.*)$"                    # JVM, .NET and Node frames
_JVM_MORE = r"^\s*(?:Caused by: |Suppressed: |\.\.\. \d+ (?:more|common frames omitted)|--- End of )"

# One row per stack-trace shape, tried in this order on a line that is not indented.
#   start:  the first line; groups cls and msg name the exception (fixed `cls` otherwise)
#   lead:   lines allowed between start and the first frame
#   frame:  a frame; group sig, or groups file and fn, give its signature part
#   cont:   other lines that belong to the trace (source lines, "Caused by", file lines)
#   end:    the last line, which names the exception (Python)
#   innermost: "first" or "last" - where the frames nearest the failure are
TRACE_SHAPES = [
    {"name": "python",
     "start": _re(r"^Traceback \(most recent call last\):$"), "cls": "Traceback",
     "frame": _re(r'^\s+File "(?P<file>[^"]+)", line \d+, in (?P<fn>\S+)'),
     "cont": _re(r"^\s{4,}\S"),
     "end": _re(r"^(?P<cls>[A-Za-z_][\w.]*)(?::\s*(?P<msg>.*))?$"),
     "innermost": "last"},
    {"name": "jvm",            # also .NET: dotted exception names with `at` frames
     "start": _re(r'^(?:Caused by: |Exception in thread "[^"]*" |Unhandled exception\. )?'
                  r"(?P<cls>(?:[A-Za-z_$][\w$]*\.)+[A-Za-z_$][\w$]*"
                  r"(?:Exception|Error|Throwable|Failure))(?::\s*(?P<msg>.*))?$"),
     "frame": _re(_AT_FRAME), "cont": _re(_JVM_MORE), "innermost": "first"},
    {"name": "node",
     "start": _re(r"^(?:Uncaught )?(?P<cls>[A-Z][\w$]*(?:Error|Exception))"
                  r"(?: \[[\w-]+\])?(?::\s*(?P<msg>.*))?$"),
     "frame": _re(_AT_FRAME), "innermost": "first"},
    {"name": "go",
     "start": _re(r"^(?P<cls>panic|fatal error): (?P<msg>.*)$"),
     "lead": _re(r"^$|^goroutine \d+ \[[^\]]*\]:$|^\s+panic: |^\[signal "),
     "frame": _re(r"^(?P<sig>[\w.*/\[\]()-]+)\([^()]*\)$"),
     "cont": _re(r"^\t\S+:\d+|^created by "),
     "innermost": "first"},
]

_LINE_NO = re.compile(r":line \d+|:\d+(?::\d+)?|\s\+0x[0-9a-f]+")
_STAMP = re.compile(r"^\s*\[?(\d{4})[-/](\d{2})[-/](\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?"
                    r"(?:[.,](\d+))?\s*(Z|[+-]\d{2}:?\d{2})?")
# A leading time stamp, bare or in square brackets, and one space after it.
_STAMP_PREFIX = re.compile(r"^\[?\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:[.,]\d+)?"
                           r"(?:\s?(?:Z|[+-]\d{2}:?\d{2}))?\]?[ \t]?")
_CSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")              # terminal colour codes
_BARE_TIME = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
_LEVEL_WORD = re.compile(r"\b(" + "|".join(sorted(LEVEL_WORDS, key=len, reverse=True))
                         + r")\b")


# --- arguments -------------------------------------------------------------------

def _bounded(lo, hi, what):
    def parse(value):
        try:
            n = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{what} must be a whole number") from None
        if not lo <= n <= hi:
            raise argparse.ArgumentTypeError(f"{what} must be from {lo} to {hi}")
        return n
    return parse


def _regex(value):
    if len(value) > GREP_MAX:
        raise argparse.ArgumentTypeError(f"--grep is at most {GREP_MAX} characters")
    try:
        return re.compile(value)
    except re.error as exc:
        raise argparse.ArgumentTypeError(f"--grep is not a valid regular expression: {exc}") \
            from None


def _stamp_value(m) -> datetime:
    y, mo, d, h, mi, s, frac, off = m.groups()
    micro = int((frac or "0")[:6].ljust(6, "0"))
    dt = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0), micro)
    if off:
        if off == "Z":
            delta = timedelta(0)
        else:
            sign = 1 if off[0] == "+" else -1
            digits = off[1:].replace(":", "")
            delta = sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
        dt = dt.replace(tzinfo=timezone(delta)).astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _when(value):
    """A --since/--until value: a datetime, or a bare time (resolved against the file)."""
    text = value.strip()
    m = _BARE_TIME.match(text)
    if m:
        h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        if h < 24 and mi < 60 and s < 60:
            return time(h, mi, s)
    m = _STAMP.match(text)
    if m and m.end() == len(text):
        try:
            return _stamp_value(m)
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(
        f"not a time: {value!r} (use 2026-10-12T10:00:00, \"2026-10-12 10:00:00\" or 10:00)")


def _level(value):
    key = value.strip().upper()
    if key not in LEVEL_WORDS:
        raise argparse.ArgumentTypeError(
            f"not a level: {value} (one of {', '.join(LEVEL_WORDS)})")
    return LEVEL_WORDS[key]


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="log_slice.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="a local log file (text or .gz)")
    ap.add_argument("--since", type=_when, metavar="T", help="only lines at or after T")
    ap.add_argument("--until", type=_when, metavar="T", help="only lines at or before T")
    ap.add_argument("--level", type=_level, metavar="LEVEL", help="this level and above")
    ap.add_argument("--first-error", action="store_true", help="the first error with context")
    ap.add_argument("--before", type=_bounded(0, AROUND_MAX, "--before"), default=10,
                    metavar="N", help="lines before the first error (default 10)")
    ap.add_argument("--after", type=_bounded(0, AROUND_MAX, "--after"), default=30,
                    metavar="N", help="lines after the first error (default 30)")
    ap.add_argument("--traces", action="store_true", help="repeated stack traces, grouped")
    ap.add_argument("--grep", type=_regex, metavar="RE",
                    help="only lines matching this regular expression (on the redacted text)")
    ap.add_argument("--from-line", type=_bounded(1, 10 ** 12, "--from-line"), metavar="N",
                    help="start at line N")
    ap.add_argument("--tail", type=_bounded(1, TAIL_MAX, "--tail"), metavar="N",
                    help=f"the last N lines (at most {TAIL_MAX})")
    ap.add_argument("--max-bytes", type=_bounded(1, MAX_BYTES_CEIL, "--max-bytes"),
                    default=MAX_BYTES, metavar="N",
                    help=f"cap on the lines shown, in bytes (default {MAX_BYTES})")
    ap.add_argument("--json", action="store_true", help="structured output")
    return ap


# --- reading ---------------------------------------------------------------------

def read_lines(path):
    """Each line without its line break, cut at LINE_READ_MAX characters."""
    with open(path, "rb") as fh:
        gz = fh.read(2) == b"\x1f\x8b"
    opener = gzip.open if gz else open
    with opener(path, "rt", encoding="utf-8", errors="replace", newline="") as fh:
        while True:
            line = fh.readline(LINE_READ_MAX)
            if not line:
                return
            if not line.endswith(("\n", "\r")):
                rest = line
                while rest and not rest.endswith(("\n", "\r")):    # skip the overlong rest
                    rest = fh.readline(LINE_READ_MAX)
            yield _CSI.sub("", line.rstrip("\r\n"))


def clip(text_, limit=LINE_CHARS) -> str:
    return text_ if len(text_) <= limit else text_[:limit - 1] + "…"


def body_of(text_) -> str:
    """The line without a leading time stamp (bare or bracketed)."""
    return _STAMP_PREFIX.sub("", text_, count=1)


def level_of(text_):
    body = body_of(text_)
    for pattern, name in LEVEL_PREFIXES:
        if pattern.match(body):
            return LEVEL_WORDS[name]
    m = _LEVEL_WORD.search(text_[:120])
    return LEVEL_WORDS[m.group(1)] if m else None


def is_marker(text_) -> bool:
    body = body_of(text_)
    return any(p.search(body) for p in FAILURE_MARKERS)


# --- first error and traces ------------------------------------------------------

class FirstError:
    def __init__(self, before, after):
        self.buf = deque(maxlen=before) if before else None
        self.after_n = after
        self.left = 0
        self.hit = None

    def feed(self, n, text_, level):
        if self.hit is None:
            if (level is not None and level >= ERROR_RANK) or is_marker(text_):
                self.hit = {"n": n, "text": text_,
                            "before": [{"n": i, "text": t} for i, t in (self.buf or [])],
                            "after": []}
                self.left = self.after_n
            elif self.buf is not None:
                self.buf.append((n, text_))
        elif self.left > 0:
            self.hit["after"].append({"n": n, "text": text_})
            self.left -= 1


class Traces:
    """Stack traces grouped by shape, exception and top frames; one pass, bounded."""

    def __init__(self):
        self.groups = {}
        self.dropped = 0
        self.cand = None

    def feed(self, n, text_):
        body = body_of(text_)
        c = self.cand
        if c is not None:
            if self._inside(c, body):
                return
            self.finish()
        self._start(n, body)

    def _inside(self, c, body) -> bool:
        """True when the line belongs to the open trace (and was taken)."""
        shape = c["shape"]
        fm = shape["frame"].match(body)
        if fm:
            g = fm.groupdict()
            part = g.get("sig") or f"{g.get('file')} in {g.get('fn')}"
            c["sig"].append(_LINE_NO.sub("", part.strip()))
            c["frames"] += 1
            self._keep(c, body)
            return True
        lead = shape.get("lead")
        if not c["frames"] and lead is not None and lead.match(body):
            self._keep(c, body)
            return True
        cont = shape.get("cont")
        if cont is not None and cont.match(body) and (c["frames"] or lead is None):
            self._keep(c, body)
            return True
        end = shape.get("end")
        if end is not None and c["frames"]:
            em = end.match(body)
            if em:
                c["cls"], c["msg"] = em.group("cls"), (em.group("msg") or "").strip()
                self._keep(c, body)
                self.finish()
                return True
        return False

    @staticmethod
    def _keep(c, body):
        if len(c["lines"]) < SAMPLE_LINES:
            c["lines"].append(body)

    def _start(self, n, body):
        if body[:1] in (" ", "\t"):
            return
        for shape in TRACE_SHAPES:
            m = shape["start"].match(body)
            if m:
                g = m.groupdict()
                keep = SIG_FRAMES if shape.get("innermost") == "last" else None
                self.cand = {"n": n, "shape": shape, "cls": g.get("cls") or shape.get("cls"),
                             "msg": (g.get("msg") or "").strip(), "lines": [body],
                             "sig": deque(maxlen=keep) if keep else _Capped(SIG_FRAMES),
                             "frames": 0}
                return

    def finish(self):
        c, self.cand = self.cand, None
        if not c or not c["frames"]:
            return
        frames = list(c["sig"])
        if c["shape"].get("innermost") == "last":
            frames.reverse()
        sig = " | ".join([c["cls"], *frames[:SIG_FRAMES]])
        key = (c["shape"]["name"], sig)
        g = self.groups.get(key)
        if g is None:
            if len(self.groups) >= MAX_GROUPS:
                self.dropped += 1
                return
            self.groups[key] = {"signature": sig, "shape": c["shape"]["name"], "count": 1,
                                "first_n": c["n"], "last_n": c["n"], "starts": [c["n"]],
                                "message": c["msg"], "sample": c["lines"]}
            return
        g["count"] += 1
        g["last_n"] = c["n"]
        if len(g["starts"]) < MAX_STARTS:
            g["starts"].append(c["n"])

    def result(self):
        self.finish()
        return sorted(self.groups.values(), key=lambda g: (-g["count"], g["first_n"]))


class _Capped(list):
    """A list that keeps only its first `cap` items."""

    def __init__(self, cap):
        super().__init__()
        self.cap = cap

    def append(self, item):
        if len(self) < self.cap:
            super().append(item)


# --- selection -------------------------------------------------------------------

def _size(text_) -> int:
    return len(text_.encode("utf-8")) + 1


def select(lines, *, from_line, grep, tail, max_bytes):
    """(kept, truncated, omitted): --from-line, then --grep, then --tail, then --max-bytes
    (the end is kept with --tail, else the start)."""
    picked = ((n, t) for n, t in lines if from_line is None or n >= from_line)
    if grep is not None:
        picked = ((n, t) for n, t in picked if grep.search(t))
    if tail is not None:
        window = deque(picked, maxlen=tail)
        kept, size = [], 0
        for n, t in reversed(window):
            if size + _size(t) > max_bytes:
                break
            kept.append((n, t))
            size += _size(t)
        kept.reverse()
        omitted = len(window) - len(kept)
        return kept, omitted > 0, omitted
    kept, size, omitted = [], 0, 0
    for n, t in picked:
        if omitted or size + _size(t) > max_bytes:
            omitted += 1
            continue
        kept.append((n, t))
        size += _size(t)
    return kept, omitted > 0, omitted


# --- the run ---------------------------------------------------------------------

def slice_log(args):
    path = Path(args.file)
    redactor = redact.Redactor()
    first = FirstError(args.before, args.after) if args.first_error else None
    traces = Traces() if args.traces else None
    state = {"read": 0, "stamped": False, "time": None, "level": None, "day": None}

    def resolve(value):
        if isinstance(value, time):
            return datetime.combine(state["day"], value) if state["day"] else None
        return value

    def redacted():
        for raw in read_lines(path):
            state["read"] += 1
            for n, t in redactor.feed_numbered(raw):
                yield n, clip(t)
        for n, t in redactor.flush_numbered():
            yield n, clip(t)

    def records():
        for n, t in redacted():
            m = _STAMP.match(t)
            own = level_of(t)
            stamp = None
            if m:
                try:
                    stamp = _stamp_value(m)
                except ValueError:
                    stamp = None
            if stamp is not None:
                state["stamped"], state["time"], state["level"] = True, stamp, own
                if state["day"] is None:
                    state["day"] = stamp.date()
                level = own
            elif own is None and (state["stamped"] or body_of(t)[:1] in (" ", "\t")):
                level = state["level"]                 # a continuation line
            else:
                level = own
                if not state["stamped"]:
                    state["level"] = own
            if args.since is not None or args.until is not None:
                since, until = resolve(args.since), resolve(args.until)
                cur = state["time"] if state["stamped"] else None
                if cur is None or (since and cur < since) or (until and cur > until):
                    if traces:
                        traces.finish()
                    continue
            if first:
                first.feed(n, t, level)
            if traces:
                traces.feed(n, t)
            if args.level is None or (level is not None and level >= args.level):
                yield n, t

    line_selector = any(v is not None for v in (args.since, args.until, args.level, args.grep,
                                                args.from_line, args.tail))
    tail = args.tail
    if not line_selector and not (args.first_error or args.traces):
        tail = DEFAULT_TAIL
    if line_selector or tail is not None:
        kept, truncated, omitted = select(records(), from_line=args.from_line, grep=args.grep,
                                          tail=tail, max_bytes=args.max_bytes)
    else:
        for _ in records():
            pass
        kept, truncated, omitted = [], False, 0

    counts = {k: redactor.counts[k] for k in redact.KINDS if redactor.counts.get(k)}
    groups = traces.result() if traces else []
    return {
        "file": str(path),
        "lines_read": state["read"],
        "window": {"since": _shown(resolve(args.since), args.since),
                   "until": _shown(resolve(args.until), args.until)},
        "lines": [{"n": n, "text": t} for n, t in kept],
        "first_error": first.hit if first else None,
        "traces": groups,
        "traces_dropped": traces.dropped if traces else 0,
        "truncated": truncated,
        "omitted_lines": omitted,
        "redactions": counts,
    }


def _shown(resolved, raw):
    if raw is None:
        return None
    if isinstance(resolved, datetime):
        return resolved.isoformat(timespec="seconds")
    return raw.isoformat(timespec="seconds")


def render(doc, args) -> list:
    w = doc["window"]
    head = f"{doc['file']}: {doc['lines_read']} lines read"
    if w["since"] or w["until"]:
        head += f" (window {w['since'] or '…'} to {w['until'] or '…'})"
    out = [head]
    if args.first_error:
        fe = doc["first_error"]
        if fe is None:
            out.append("First error: none found.")
        else:
            out.append(f"First error: line {fe['n']}")
            out += [f"  #{l['n']}  {l['text']}" for l in fe["before"]]
            out.append(f"> #{fe['n']}  {fe['text']}")
            out += [f"  #{l['n']}  {l['text']}" for l in fe["after"]]
    if args.traces:
        if not doc["traces"]:
            out.append("Stack traces: none found.")
        else:
            out.append("Stack traces (grouped by exception and top frames):")
            for g in doc["traces"]:
                starts = ", ".join(map(str, g["starts"]))
                more = "" if len(g["starts"]) == g["count"] else ", …"
                msg = f": {g['message']}" if g["message"] else ""
                out.append(f"- {g['count']}x {g['signature'].split(' | ')[0]}{msg} "
                           f"[{g['shape']}] (lines {starts}{more})")
                out += [f"    {f}" for f in g["signature"].split(" | ")[1:]]
            if doc["traces_dropped"]:
                out.append(f"  ({doc['traces_dropped']} more trace(s) in groups past "
                           f"the first {MAX_GROUPS} not shown)")
    if doc["lines"]:
        out += [f"#{l['n']}  {l['text']}" for l in doc["lines"]]
    if doc["truncated"]:
        out.append(f"Cut at --max-bytes {args.max_bytes}: {doc['omitted_lines']} more "
                   "selected line(s) not shown. Narrow it with --grep, --from-line or --tail.")
    if doc["redactions"]:
        out.append("Redacted (values never shown): "
                   + ", ".join(f"{k} {v}" for k, v in doc["redactions"].items()) + ".")
    return out


def main(argv=None) -> int:
    ap = parser()
    args = ap.parse_args(argv)
    if not Path(args.file).is_file():
        ap.error(f"cannot read {args.file}: no such file")
    try:
        doc = slice_log(args)
    except (OSError, EOFError, zlib.error) as exc:      # also a corrupt or cut-off .gz
        print(f"log_slice.py: cannot read {args.file} ({type(exc).__name__})", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
    else:
        print("\n".join(render(doc, args)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
