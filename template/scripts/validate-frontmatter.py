#!/usr/bin/env python3
"""Validate the YAML-frontmatter contract on long-lived Markdown deliverables.

Enforces AGENTS.md §4.2: every governed Markdown file carries a frontmatter block
with the required maturity/trust fields. This is the machine half of the
governance pillar — the rule expressed as a script (board pillar 3/4).

Required fields:  title, status, owner, classification, ai-trust
Recommended:      author, created, last-reviewed
Vocabularies:
  status:         draft | under-review | approved | superseded
  classification: public | internal | restricted
  ai-trust:       authoritative | working | exploratory

By default scans `docs/` but skips the exploratory/immutable areas
(`docs/drafts/`, `docs/received/`) where the contract is relaxed. Files git
ignores (session transcripts, scratch) are not deliverables and are skipped.

Adopting the kit into an existing repo means inheriting docs written before the
contract existed. A gate that is red on day one gets switched off, so those
are recorded once in a **baseline** (`.ai-sdlc/frontmatter-baseline.txt`, next
to the kit manifest) and reported as debt instead of failing; anything new must
comply. The baseline only shrinks: rewriting it drops fixed and deleted files
but never adds a new violation.

Usage:
  validate-frontmatter.py                    # scan governed docs
  validate-frontmatter.py FILE [more...]     # specific files (pre-commit passes these)
  validate-frontmatter.py --write-baseline   # record today's violations as debt
  validate-frontmatter.py --no-baseline      # ignore the baseline; fail on everything

Exit 0 if all valid (baselined debt excepted), 1 otherwise, 2 on bad usage.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("error: PyYAML is required (pip install pyyaml)")

REQUIRED = ["title", "status", "owner", "classification", "ai-trust"]
RECOMMENDED = ["author", "created", "last-reviewed"]
ENUMS = {
    "status": {"draft", "under-review", "approved", "superseded"},
    "classification": {"public", "internal", "restricted"},
    "ai-trust": {"authoritative", "working", "exploratory"},
}

SCAN_ROOT = "docs"
SKIP_DIRS = {"drafts", "received", "knowledge"}  # relaxed / immutable areas
# Files exempt from the contract even inside the scan root.
EXEMPT_NAMES = {"README.md", "schema.md"}
# Inherited debt, next to the kit manifest (.ai-sdlc/kit.json).
BASELINE_REL = ".ai-sdlc/frontmatter-baseline.txt"
BASELINE_HEADER = """\
# Frontmatter debt inherited when this repo adopted the AI-SDLC kit.
# These files are reported as debt, not failed. The list only shrinks:
# fix a file, then run `scripts/validate-frontmatter.py --write-baseline`
# (or delete its line). A rewrite never adds a new violation.
# See docs/governance/README.md, "Paying down the frontmatter baseline".
"""


def split_frontmatter(text: str):
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i])
    return None


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return [f"could not read file: {exc}"]

    fm_str = split_frontmatter(text)
    if fm_str is None:
        return ["missing YAML frontmatter (see AGENTS.md §4.2)"]
    try:
        fm = yaml.safe_load(fm_str) or {}
    except yaml.YAMLError as exc:
        return [f"frontmatter is not valid YAML: {exc}"]
    if not isinstance(fm, dict):
        return ["frontmatter must be a YAML mapping"]

    for field in REQUIRED:
        if field not in fm or fm[field] in (None, ""):
            errors.append(f"missing required field: {field}")
    for field, allowed in ENUMS.items():
        val = fm.get(field)
        if val is not None and str(val) not in allowed:
            errors.append(f"{field}={val!r} not in {sorted(allowed)}")
    for field in RECOMMENDED:
        if field not in fm:
            print(f"  warning: recommended field missing: {field}")
    if str(fm.get("status")) == "superseded" and str(fm.get("ai-trust")) != "exploratory":
        print("  warning: status is superseded and ai-trust is not exploratory "
              "(AGENTS.md §4.2)")
    return errors


def collect_targets(args: list[str], repo_root: Path) -> list[Path]:
    if args:
        out = []
        for a in args:
            p = Path(a)
            if not p.is_absolute():
                p = Path.cwd() / p
            if p.suffix == ".md" and p.name not in EXEMPT_NAMES:
                out.append(p)
        return out
    base = repo_root / SCAN_ROOT
    targets = []
    for p in sorted(base.rglob("*.md")):
        rel_parts = set(p.relative_to(base).parts)
        if rel_parts & SKIP_DIRS or p.name in EXEMPT_NAMES:
            continue
        targets.append(p)
    return targets


def load_baseline(repo_root: Path) -> set[str] | None:
    """The baselined paths, or None when the repo has no baseline."""
    path = repo_root / BASELINE_REL
    if not path.is_file():
        return None
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")}


def write_baseline(repo_root: Path, rels) -> Path:
    path = repo_root / BASELINE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{r}\n" for r in sorted(rels))
    path.write_text(BASELINE_HEADER + body, encoding="utf-8")
    return path


def git_ignored(repo_root: Path, paths: list[Path]) -> set[Path]:
    """The subset of `paths` git ignores. Empty outside a git work tree."""
    if not paths:
        return set()
    # -z: NUL-separated and unquoted, so non-ASCII paths (which core.quotePath
    # would otherwise C-quote) come back exactly as given.
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "check-ignore", "-z", "--stdin"],
            input=b"\0".join(os.fsencode(p) for p in paths),
            capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return set()
    # Exit 1 means "nothing ignored"; 128 means "not a git repo".
    if out.returncode not in (0, 1):
        return set()
    return {Path(os.fsdecode(p)) for p in out.stdout.split(b"\0") if p}


def rel_of(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", help="files to check (default: scan docs/)")
    ap.add_argument("--write-baseline", action="store_true",
                    help=f"record current violations in {BASELINE_REL} (shrink-only "
                         "once it exists)")
    ap.add_argument("--no-baseline", action="store_true",
                    help="ignore the baseline and fail on every violation")
    args = ap.parse_args(argv)
    if args.write_baseline and args.paths:
        ap.error("--write-baseline scans every governed doc; do not pass files")

    repo_root = Path(__file__).resolve().parent.parent
    targets = collect_targets(args.paths, repo_root)
    ignored = git_ignored(repo_root, targets)
    targets = [p for p in targets if p not in ignored]
    full_scan = not args.paths

    baseline = None if args.no_baseline else load_baseline(repo_root)
    known = baseline or set()

    if not targets and not (full_scan and known):
        print("No governed Markdown files to validate.")
        if args.write_baseline and baseline is None:
            path = write_baseline(repo_root, [])
            print(f"baseline written: {rel_of(path, repo_root)} (0 file(s) recorded as debt)")
        return 0

    violations: list[str] = []
    failed: list[str] = []
    debt: list[str] = []
    fixed: list[str] = []
    for path in targets:
        rel = rel_of(path, repo_root)
        errs = validate_file(path)
        if not errs:
            print(f"ok    {rel}")
            if rel in known:
                fixed.append(rel)
            continue
        violations.append(rel)
        if rel in known:
            debt.append(rel)
            print(f"debt  {rel}  (baselined)")
            continue
        if args.write_baseline and baseline is None:
            print(f"debt  {rel}  (adopting into the baseline)")
            continue
        failed.append(rel)
        print(f"FAIL  {rel}")
        for e in errs:
            print(f"  - {e}")

    # A baselined file the full scan no longer covers (deleted, moved, renamed
    # to an exempt name, now git-ignored) is debt that is gone.
    scanned = {rel_of(p, repo_root) for p in targets}
    stale = sorted(known - scanned) if full_scan else []

    if args.write_baseline:
        if baseline is None:
            keep = violations  # first adoption: everything inherited is debt
        else:
            keep = [r for r in violations if r in baseline]
        path = write_baseline(repo_root, keep)
        print(f"\nbaseline written: {rel_of(path, repo_root)} "
              f"({len(keep)} file(s) recorded as debt)")
        if baseline is not None:
            print(f"{len(baseline) - len(keep)} file(s) dropped from the baseline.")
        if failed and baseline is not None:
            print(f"{len(failed)} new violation(s) NOT baselined — the baseline only "
                  f"shrinks; fix them: {', '.join(failed)}")
            return 1
        return 0

    total = len(targets)
    print(f"\n{total - len(failed) - len(debt)}/{total} files satisfy the frontmatter contract.")
    if debt:
        print(f"{len(debt)} baselined file(s) still owe frontmatter — see {BASELINE_REL}")
    if fixed or stale:
        print(f"{len(fixed) + len(stale)} baselined file(s) are fixed or gone; remove from "
              f"baseline (run --write-baseline): {', '.join(fixed + stale)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
