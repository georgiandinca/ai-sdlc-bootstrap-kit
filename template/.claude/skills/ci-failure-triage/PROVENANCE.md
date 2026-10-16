# Provenance: ci-failure-triage

- **Helpers** (`scripts/log_slice.py`, `scripts/test_report.py`): adapted from Emil
  Dan's fork of this kit (MIT, used with his permission). This version imports the
  kit's shared redactor (`scripts/lib/redact.py`) instead of carrying a copy. It moves
  report formats, trace shapes, log levels and failure categories into data tables,
  adds TAP and Python and .NET traces, and drops the CI-server input.
- **Skill text** (`SKILL.md`): written for this kit from the specification in issue
  #21. No text was copied from any source.
- **Ideas credited** (both MIT):
  - [`warpdotdev/common-skills`](https://github.com/warpdotdev/common-skills),
    *diagnose-ci-failures* (at commit `1b811f3c051d`): the flow of starting from the
    first failure and answering in a fixed shape.
  - [`patricio0312rev/skills`](https://github.com/patricio0312rev/skills),
    *test-reporting-triage-skill* (at commit `63451c75e50f`): sorting
    failures into categories.
