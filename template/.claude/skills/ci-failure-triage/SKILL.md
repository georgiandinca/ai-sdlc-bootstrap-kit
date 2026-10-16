---
name: ci-failure-triage
description: Find why a build or test run failed, from a pasted CI log, a log file or test reports. Read-only, with evidence and a fix plan; never edits code. Use on "why did CI fail", "tests failed".
metadata:
  status: "approved"
  classification: "internal"
  ai-trust: "working"
  owner: "Architect"
---

# ci-failure-triage

Answer "why did it fail?" from evidence. Two habits make this go wrong: reading a whole
log into the conversation (it wastes context and can expose secrets), and jumping
straight to a code change. This skill avoids both. It reads through two helpers that
redact secrets and cap their output, and it ends with a plan, not an edit.

## Rules

- **Read-only.** Do not edit code, configuration or the pipeline, and do not re-run
  anything that writes, publishes or deploys. If the person wants the fix, that is a
  new task after this answer, through the normal change and review path.
- **Never print a whole log.** Use the helpers below. Quote only the lines that carry
  the evidence, with their line numbers.
- **Secrets stay hidden.** The helpers redact before they print and report only counts.
  If a log was pasted into the chat, save it to a scratch file and read it through
  `log_slice.py`. Do not repeat raw lines from the paste.
- **No CI product is assumed.** Work from the files and text the person gives you.

## Pick the mode

| What you have | Mode | Start with |
|---|---|---|
| A CI log pasted in the chat, or a link to one | **Pasted log** | Save the paste to a scratch file, or ask for the raw log as a file. Then continue as **Log file**. |
| A local log file (`.log`, `.txt`, `.gz`) | **Log file** | `log_slice.py FILE --first-error`, then `--traces` |
| Test reports (JUnit XML, `go test -json`, Jest or Vitest JSON, TAP) | **Test reports** | `test_report.py PATH` (a file, a folder or a glob) |
| Both a log and reports | Both | Reports first (they name the failing tests), then the log around that time |

The helpers live in `.claude/skills/ci-failure-triage/scripts/`. Both run on Python 3.9+
with the standard library only, and both import the kit's redactor
(`scripts/lib/redact.py`). If they cannot find it, they stop and print nothing.

## Steps

1. **Find the first failure, not the loudest one.** Later errors are often knock-on
   effects. `log_slice.py --first-error` gives the first line at ERROR or above, or the
   first failure marker, with context around it.
2. **See what repeats.** `log_slice.py --traces` groups repeated stack traces (JVM, .NET,
   Python, Node, Go) by exception and top frames. `test_report.py` gives the counts,
   failures per suite or package, and one category per failure: `infra`, `network`,
   `timeout`, `build`, `config`, `assertion` or `other`.
3. **Narrow down.** Use `--since`/`--until` for a time window, `--level WARN`,
   `--grep RE`, `--from-line N` or `--tail N`. Output is capped by `--max-bytes`. If it
   is cut, narrow the slice instead of raising the cap.
4. **Flaky or real?** Call a test a flaky candidate only with a reason: it failed and
   then passed on a rerun in the same run, or it passed in another run you compared
   (`test_report.py PATH --compare OTHER_PATH`). One run alone proves nothing either way.
5. **Answer in the shape below.**

## Answer shape

Use these headings, in this order:

1. **First failure**: what failed first and where (test id, `file:line`, or log line number).
2. **Pattern**: its category, and how often it happens (trace groups, failures per suite).
3. **Evidence**: the few redacted lines that show it, each with its line number or report.
4. **Evidence suggests**: the likely cause, with a confidence (high, medium or low) and
   the reason for that confidence.
5. **Not shown**: what this evidence does not cover, such as lines cut by a cap, stages
   or reports you were not given, or the environment.
6. **Next checks**: read-only commands or files that would confirm or rule out the cause.
7. **Fix plan**: the steps a developer would take. No code change is made here.

## Helper reference

```bash
S=.claude/skills/ci-failure-triage/scripts
python3 $S/log_slice.py build.log --first-error --before 10 --after 30
python3 $S/log_slice.py build.log.gz --traces
python3 $S/log_slice.py build.log --since 10:00 --until 10:05 --level WARN
python3 $S/log_slice.py build.log --grep 'FAIL|Error' --tail 100 --json
python3 $S/test_report.py target/surefire-reports/       # a folder of reports
python3 $S/test_report.py 'reports/**/*.xml' --compare previous/ --json
```

Teaching the helpers something new means adding a row to a table, not writing new
logic: `TRACE_SHAPES`, `LEVEL_PREFIXES` or `FAILURE_MARKERS` in `log_slice.py`, and
`PARSERS`, `RULES` or `LOCATIONS` in `test_report.py`. Add a test fixture for each one.
Where the ideas come from: [PROVENANCE.md](PROVENANCE.md).
