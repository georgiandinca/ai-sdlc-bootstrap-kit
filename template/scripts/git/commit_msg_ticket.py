#!/usr/bin/env python3
"""commit-msg hook: ensure the commit message references an issue/ticket key.

Implements the commit<->issue linking rule (WORKING-AGREEMENT.md §5.5). The key
lets the git host link commits/branches/PRs to the tracker item.

Modes:
  --mode warn   (default) print a reminder but never block      [advisory]
  --mode block  fail the commit if no key is present            [enforced]

A key looks like ABC-123 (uppercase letters/digits, hyphen, digits), unless the
`issues` namespace of docs/knowledge/graph-manifest.json sets `key_pattern`. If the
current branch is named feature/ABC-123-slug, the key is injected automatically
when the message has none. Exempt: merges, reverts, and messages containing
[no-ticket].

Usage (wired via .pre-commit-config.yaml, stage commit-msg):
  commit_msg_ticket.py --mode warn  <path-to-COMMIT_EDITMSG>
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DEFAULT_KEY = r"[A-Z][A-Z0-9]+-\d+"
EXEMPT_RE = re.compile(r"^(Merge |Revert )|\[no-ticket\]", re.IGNORECASE | re.MULTILINE)


def key_pattern(manifest_path=None) -> str:
    """The project's issue-key pattern, from the knowledge-graph manifest; the
    default when the manifest or its reader is missing or cannot be read."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "knowledge"))
        import manifest
        data = manifest.load(manifest_path) if manifest_path else manifest.load()
        return manifest.issue_key_pattern(data)
    except Exception:  # noqa: BLE001
        return DEFAULT_KEY


def current_branch() -> str:
    try:
        return subprocess.check_output(
            ["git", "branch", "--show-current"], text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


def main() -> int:
    args = sys.argv[1:]
    mode = "warn"
    if "--mode" in args:
        i = args.index("--mode")
        mode = args[i + 1] if i + 1 < len(args) else "warn"
        del args[i : i + 2]
    if not args:
        return 0  # no message file passed; nothing to do
    path = args[0]

    try:
        with open(path, "r", encoding="utf-8") as fh:
            msg = fh.read()
    except OSError:
        return 0

    pattern = key_pattern()
    if EXEMPT_RE.search(msg) or re.search(rf"(?<!\w)(?:{pattern})(?!\w)", msg):
        return 0

    # Try to recover the key from the branch name and inject a trailer.
    m = re.search(pattern, current_branch())
    if m:
        key = m.group(0)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(msg.rstrip("\n") + f"\n\nRefs: {key}\n")
        print(f"[commit-msg] injected issue key {key} from branch name.")
        return 0

    note = (
        "[commit-msg] no issue key (e.g. ABC-123) found in the commit message.\n"
        "             Add one so the host links this commit to the tracker, or use "
        "[no-ticket] for genuine non-ticket commits."
    )
    if mode == "block":
        print(note, file=sys.stderr)
        return 1
    print(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
