#!/usr/bin/env python3
"""Flag cache-hostile churn on the canonical brief (token-economy rule 2).

Every AGENTS.md edit invalidates the prompt-cache prefix for every operator.
This gate counts commits touching the brief in a recent window: prints the
count, warns above --warn, fails (exit 1) above --max. Stdlib only.

Usage:  check-brief-churn.py [--path AGENTS.md] [--days 14] [--warn 3] [--max 10]
"""
from __future__ import annotations

import argparse
import subprocess


def churn_count(path="AGENTS.md", days=14, cwd=None):
    out = subprocess.run(
        ["git", "log", f"--since={days} days ago", "--oneline", "--", path],
        capture_output=True, text=True, check=True, cwd=cwd,
    ).stdout
    return len([line for line in out.splitlines() if line.strip()])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", default="AGENTS.md")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--warn", type=int, default=3)
    ap.add_argument("--max", type=int, default=10)
    ap.add_argument("--cwd", default=None, help="repo dir (default: cwd)")
    args = ap.parse_args(argv)

    n = churn_count(args.path, args.days, args.cwd)
    print(f"[brief-churn] {n} commit(s) touched {args.path} in the last {args.days} days")
    if n > args.max:
        print(f"[brief-churn] FAIL: > --max {args.max} — cache-hostile brief churn; "
              "batch brief edits between sprints (rules/token-economy.md §2)")
        return 1
    if n > args.warn:
        print(f"[brief-churn] WARN: > --warn {args.warn} — keep the brief byte-stable "
              "within a sprint (rules/token-economy.md §2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
