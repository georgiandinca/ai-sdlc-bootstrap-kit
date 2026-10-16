# Contributing to the AI-SDLC Bootstrap Kit

First off — thanks for taking the time to contribute! This project is a
bootstrap skeleton for AI-augmented software projects, and it gets better with
real-world use. Bug reports, docs fixes, new role playbooks, and validator
improvements are all welcome.

By participating in this project you agree to abide by our
[Code of Conduct](./CODE_OF_CONDUCT.md).

## Ways to contribute

- **Report a bug** — open an issue describing what you did, what you expected,
  and what actually happened. Include your OS, Python version, and the exact
  command output.
- **Suggest a feature** — open an issue explaining the problem you're trying to
  solve first, then your proposed solution. Discussion before code saves
  everyone time.
- **Improve the docs** — typos, unclear steps, missing examples. Small PRs are
  perfectly welcome.
- **Submit code** — see the workflow below.

## Development setup

The kit is intentionally low-dependency: Python 3.12 (stdlib + `pyyaml`) and
Node (only for regenerating the pitch deck).

```bash
git clone https://github.com/georgiandinca/ai-sdlc-bootstrap-kit.git
cd ai-sdlc-bootstrap-kit
python3 -m pip install "pyyaml>=6"
```

## Running the checks locally

CI runs a governance gate (see `.github/workflows/ci.yml`). Run the same
validators and tests before you push:

```bash
# Validators
python3 template/scripts/validate-skills.py
python3 template/scripts/validate-frontmatter.py
python3 template/scripts/validate-moments.py
python3 template/scripts/validate-seat-profiles.py
python3 template/scripts/check-context-budget.py

# Unit tests (knowledge graph, dashboard, spend/ROI, validators)
python3 template/scripts/tests/test_validate_frontmatter.py
python3 template/scripts/tests/test_validate_moments.py
python3 template/scripts/tests/test_validate_seat_profiles.py
python3 template/scripts/tests/test_check_context_budget.py
python3 template/scripts/tests/test_redact.py
python3 template/scripts/tests/test_ci_triage_log_slice.py
python3 template/scripts/tests/test_ci_triage_test_report.py
python3 template/dashboard/tests/test_schema.py
python3 template/dashboard/tests/test_roi.py
bash tests/installer/test-detect-situation.sh   # the plugin's situation check
# …see .github/workflows/ci.yml for the full list

# Knowledge-graph build + traceability smoke test
python3 template/scripts/knowledge/ingest.py --build
```

A green local run is the bar for a PR.

## Pull request workflow

1. **Fork** the repo and create a topic branch from `main`:
   `git checkout -b feat/short-description` (or `fix/…`, `docs/…`).
2. **Make focused changes.** One logical change per PR — it reviews faster and
   reverts cleanly.
3. **Add or update tests** for any behavior change. The kit's whole premise is
   "rules as scripts," so new rules should ship with a validator or test.
4. **Run the checks** above and make sure they pass.
5. **Write clear commits.** We use [Conventional Commits](https://www.conventionalcommits.org/):
   `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `ci:`, `refactor:`.
   Example: `fix(dashboard): guard against empty spend table`.
6. **Add a changelog entry** under "Unreleased" in [`CHANGELOG.md`](./CHANGELOG.md)
   for anything a project that installs or updates the kit will notice. Say
   what an already-installed project has to do by hand, if anything.
7. **Open the PR** against `main`. Describe *what* changed and *why*, and link
   any related issue (`Closes #123`).
8. **Keep the discussion going** — address review comments by pushing follow-up
   commits to the same branch.

## Coding conventions

- **Python**: standard library first; avoid adding dependencies. Match the
  surrounding style (4-space indent, type hints where the file already uses
  them). Keep scripts runnable with a bare `python3 script.py`.
- **Docs**: Markdown, wrapped around ~80 columns where practical. Preserve the
  frontmatter contract enforced by `validate-frontmatter.py`.
- **No secrets, no real personal data.** Sample data uses placeholders
  (`Acme`, `PROJ-1`, `example.atlassian.net`). Never commit tokens, API keys,
  or real customer/employee data — CI secret-scanning aside, treat it as a
  hard rule.

## Reporting security issues

Please **do not** open a public issue for security vulnerabilities. See
[SECURITY.md](./SECURITY.md) for private reporting instructions.

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](./LICENSE) that covers this project.
