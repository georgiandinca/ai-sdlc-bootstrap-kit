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
(`docs/drafts/`, `docs/received/`) where the contract is relaxed.

Usage:
  validate-frontmatter.py                 # scan governed docs
  validate-frontmatter.py FILE [more...]  # specific files (pre-commit passes these)

Exit 0 if all valid, 1 otherwise.
"""
from __future__ import annotations

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


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    targets = collect_targets(sys.argv[1:], repo_root)
    if not targets:
        print("No governed Markdown files to validate.")
        return 0

    failed = 0
    for path in targets:
        try:
            rel = path.resolve().relative_to(repo_root)
        except ValueError:
            rel = path
        errs = validate_file(path)
        if errs:
            failed += 1
            print(f"FAIL  {rel}")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"ok    {rel}")

    total = len(targets)
    print(f"\n{total - failed}/{total} files satisfy the frontmatter contract.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
