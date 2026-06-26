#!/usr/bin/env python3
"""Validate SKILL.md files against the agentskills.io specification.

Spec: https://agentskills.io/specification

Checks each SKILL.md for:
  - YAML frontmatter present, followed by a non-empty Markdown body
  - name        (required): 1-64 chars, lowercase a-z/0-9/hyphen, no leading,
                trailing, or consecutive hyphens, equal to the parent dir name
  - description (required): 1-1024 chars, non-empty
  - compatibility (optional): 1-500 chars
  - license     (optional): string
  - metadata    (optional): mapping of string -> string
  - allowed-tools (optional): string
Unknown top-level frontmatter fields produce a warning, not a failure.

Usage:
  validate-skills.py                                 # scan default skill roots
  validate-skills.py path/to/SKILL.md [more ...]     # validate specific files
                                                     # (dir paths are scanned)

Exit code 0 if all valid, 1 otherwise. Zero network dependency for CI.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("error: PyYAML is required (pip install pyyaml)")

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
KNOWN_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}

# Default locations searched when no explicit paths are given. Relative to the
# repo root (the parent of this script's `scripts/` directory).
DEFAULT_ROOTS = [".claude/skills", "docs/ai-context/skills"]


def split_frontmatter(text: str):
    """Return (frontmatter_str, body_str) or (None, reason) on failure."""
    if not text.startswith("---"):
        return None, "file does not start with '---' YAML frontmatter"
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return None, "first line must be exactly '---'"
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return None, "unterminated frontmatter (missing closing '---')"


def validate_file(path: Path) -> list[str]:
    """Return a list of error strings ([] means valid). Warnings print inline."""
    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return [f"could not read file: {exc}"]

    fm_str, body = split_frontmatter(text)
    if fm_str is None:
        return [body]  # body holds the reason here

    if not body.strip():
        errors.append("Markdown body after frontmatter is empty")

    try:
        fm = yaml.safe_load(fm_str)
    except yaml.YAMLError as exc:
        return [f"frontmatter is not valid YAML: {exc}"]
    if not isinstance(fm, dict):
        return ["frontmatter must be a YAML mapping"]

    name = fm.get("name")
    if name is None:
        errors.append("missing required field: name")
    elif not isinstance(name, str):
        errors.append("name must be a string")
    else:
        if not (1 <= len(name) <= 64):
            errors.append(f"name must be 1-64 chars (got {len(name)})")
        if not NAME_RE.match(name):
            errors.append(
                "name must be lowercase a-z/0-9/hyphen with no leading, "
                f"trailing, or consecutive hyphens (got {name!r})"
            )
        if name != path.parent.name:
            errors.append(f"name {name!r} must match parent directory name {path.parent.name!r}")

    desc = fm.get("description")
    if desc is None:
        errors.append("missing required field: description")
    elif not isinstance(desc, str):
        errors.append("description must be a string")
    elif not (1 <= len(desc) <= 1024):
        errors.append(f"description must be 1-1024 chars (got {len(desc)})")
    elif not desc.strip():
        errors.append("description must be non-empty")

    compat = fm.get("compatibility")
    if compat is not None and (not isinstance(compat, str) or not (1 <= len(compat) <= 500)):
        errors.append("compatibility must be a string of 1-500 chars")

    lic = fm.get("license")
    if lic is not None and not isinstance(lic, str):
        errors.append("license must be a string")

    meta = fm.get("metadata")
    if meta is not None:
        if not isinstance(meta, dict):
            errors.append("metadata must be a mapping")
        else:
            for k, v in meta.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    errors.append(f"metadata entries must be string->string (offending key: {k!r})")
                    break

    tools = fm.get("allowed-tools")
    if tools is not None and not isinstance(tools, str):
        errors.append("allowed-tools must be a space-separated string")

    for field in fm:
        if field not in KNOWN_FIELDS:
            print(f"  warning: unknown frontmatter field {field!r} (not in agentskills.io spec)")

    return errors


def collect_targets(args: list[str], repo_root: Path) -> list[Path]:
    targets: list[Path] = []
    if args:
        for arg in args:
            p = Path(arg)
            if not p.is_absolute():
                p = Path.cwd() / p
            if p.is_dir():
                targets.extend(sorted(p.rglob("SKILL.md")))
            elif p.name == "SKILL.md":
                targets.append(p)
    else:
        for root in DEFAULT_ROOTS:
            base = repo_root / root
            if base.exists():
                targets.extend(sorted(base.rglob("SKILL.md")))
    seen, unique = set(), []
    for t in targets:
        rp = t.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(t)
    return unique


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    targets = collect_targets(sys.argv[1:], repo_root)
    if not targets:
        print("No SKILL.md files found to validate.")
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
    print(f"\n{total - failed}/{total} SKILL.md files conform to agentskills.io.")
    if failed:
        print(f"{failed} file(s) failed validation.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
