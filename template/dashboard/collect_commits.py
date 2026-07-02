#!/usr/bin/env python3
"""Collect commit attribution into the dashboard DB (commits table).

Classifies each commit AI / mixed / human by LOC using git-ai line-level notes
(refs/notes/ai, authorship/3.0.0) when present, falling back to the
Co-Authored-By trailer (human vs AI-assisted) otherwise. Reads notes with plain
`git notes` — the git-ai binary is NOT required on this machine.

Usage: collect_commits.py [--since <ref>] [--db <path>] [--repo <path>]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as dbmod  # noqa: E402

AI_MARKERS = re.compile(r"anthropic|claude|copilot|cursor|windsurf|\bbot\b", re.I)
TICKET_RE = re.compile(r"[A-Z][A-Z0-9]+-\d+")
SEAT_BRANCH_RE = re.compile(r"session/([a-z0-9-]+)/")


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _count_ranges(spec: str) -> int:
    total = 0
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            try:
                total += max(0, int(hi) - int(lo) + 1)
            except ValueError:
                pass
        elif part.isdigit():
            total += 1
    return total


def parse_note(note: str):
    """Return (ai_lines, human_lines, tool) from a git-ai authorship/3.0.0 note."""
    lines = note.splitlines()
    div = next((i for i, l in enumerate(lines) if l.strip() == "---"), None)
    attest = lines[:div] if div is not None else lines
    meta_str = "\n".join(lines[div + 1:]) if div is not None else ""
    ai = human = 0
    for line in attest:
        if not (line.startswith("  ") or line.startswith("\t")):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        # ranges are a single comma-separated token per authorship/3.0.0; join any
        # remaining whitespace-separated groups defensively so none are dropped.
        key, ranges = parts[0], ",".join(parts[1:])
        n = _count_ranges(ranges)
        if key.startswith("h_"):
            human += n
        else:
            ai += n
    tool = None
    if meta_str.strip():
        try:
            j = json.loads(meta_str)
            for s in (j.get("sessions") or {}).values():
                tool = (s.get("agent_id") or {}).get("tool")
                if tool:
                    break
        except (ValueError, TypeError):
            pass
    return ai, human, tool


def classify(ai, human, has_note, has_ai_trailer):
    if has_note:
        if ai > 0 and human > 0:
            return "mixed", "git-ai"
        if ai > 0:
            return "ai", "git-ai"
        return "human", "git-ai"
    if has_ai_trailer:
        return "ai-assisted", "trailer"
    return "human", "trailer"


def collect(repo=".", since=None, db_path=None):
    conn = dbmod.connect(db_path) if db_path is not None else dbmod.connect()
    rng = f"{since}..HEAD" if since else "HEAD"
    fmt = "%H%x1f%aI%x1f%an%x1f%ae%x1f%s%x1f%b%x1e"
    out = _git(repo, "log", "--no-merges", f"--pretty=format:{fmt}", rng).stdout
    rows = 0
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        fields = (rec.split("\x1f") + [""] * 6)[:6]
        sha, ts, an, ae, subj, body = fields
        # numstat
        ins = dels = files = 0
        for l in _git(repo, "show", "--numstat", "--format=", "-M", sha).stdout.splitlines():
            p = l.split("\t")
            if len(p) >= 3:
                files += 1
                if p[0].isdigit():
                    ins += int(p[0])
                if p[1].isdigit():
                    dels += int(p[1])
        # git-ai note
        note = _git(repo, "notes", "--ref=ai", "show", sha)
        has_note = note.returncode == 0 and note.stdout.strip() != ""
        ai_lines = human_lines = 0
        tool = None
        if has_note:
            ai_lines, human_lines, tool = parse_note(note.stdout)
        has_ai_trailer = any(
            l.lower().startswith("co-authored-by:") and AI_MARKERS.search(l)
            for l in body.splitlines()
        )
        klass, source = classify(ai_lines, human_lines, has_note, has_ai_trailer)
        if source == "trailer" and klass == "ai-assisted":
            # No line-level note: attribute the commit's insertions to AI as a
            # coarse (commit-level) estimate. Upgrade to git-ai for precision.
            ai_lines = ins
        m = TICKET_RE.search(subj) or TICKET_RE.search(body)
        ticket = m.group(0) if m else None
        seat = None
        bm = SEAT_BRANCH_RE.search(_git(repo, "branch", "--contains", sha, "--format=%(refname:short)").stdout)
        if bm:
            seat = bm.group(1)
        conn.execute(
            "INSERT OR REPLACE INTO commits (sha, ts, author_name, author_email, seat, klass, source, "
            "ai_lines, human_lines, insertions, deletions, files_changed, tool, subject, ticket) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sha, ts, an, ae, seat, klass, source, ai_lines, human_lines, ins, dels, files, tool, subj, ticket),
        )
        rows += 1
    conn.commit()
    summary = dict(conn.execute("SELECT klass, COUNT(*) FROM commits GROUP BY klass").fetchall())
    conn.close()
    return rows, summary


def main():
    ap = argparse.ArgumentParser(description="Collect commit attribution into the dashboard DB.")
    ap.add_argument("--since", help="collect commits since this ref (default: all)")
    ap.add_argument("--db", help="path to the SQLite DB (default: dashboard/utilization.db)")
    ap.add_argument("--repo", default=".", help="git repo to scan (default: cwd)")
    a = ap.parse_args()
    rows, summary = collect(repo=a.repo, since=a.since, db_path=a.db)
    print(f"collected {rows} commit(s): " + ", ".join(f"{k}={v}" for k, v in sorted(summary.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
