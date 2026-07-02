#!/usr/bin/env python3
"""Validate the per-seat profiles manifest (scripts/session/seat-profiles.json).

seat-profiles.json is the single source of per-seat data — git-comfort default,
role playbook, MCP connectors, and the onboarding first task. Phase 1 onboarding,
the SessionStart hook, and switch-seat.sh read it; this validator keeps it honest,
like validate-skills.py / validate-frontmatter.py / validate-moments.py.

Checks:
  - valid JSON with a non-empty "seats" list
  - each seat has: id, git_comfort_default, playbook, connectors, first_task
  - id in the known seat set; all known seats present; ids unique
  - git_comfort_default in {git-native, guided, hidden}
  - playbook skill dir exists at .claude/skills/<playbook>/
  - every connector is a key in .mcp.json's mcpServers (skipped if .mcp.json absent)

Usage:  validate-seat-profiles.py
Exit 0 if valid, 1 otherwise.
"""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED_FIELDS = ["id", "git_comfort_default", "playbook", "connectors", "first_task"]
KNOWN_SEATS = {"Architect", "EM", "Product", "Developer", "QA"}
COMFORTS = {"git-native", "guided", "hidden"}
MANIFEST_REL = "scripts/session/seat-profiles.json"
MCP_REL = ".mcp.json"


def _mcp_server_keys(base_dir: Path) -> tuple[set, str]:
    """Return (keys, status) where status is 'absent', 'malformed', or 'ok'."""
    mcp_path = base_dir / MCP_REL
    if not mcp_path.exists():
        return set(), "absent"
    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set(), "malformed"
    servers = data.get("mcpServers")
    return (set(servers.keys()) if isinstance(servers, dict) else set()), "ok"


def validate_manifest(data: dict, base_dir: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest root must be a JSON object"]
    seats = data.get("seats")
    if not isinstance(seats, list):
        return ["manifest must have a 'seats' list"]
    if not seats:
        errors.append("'seats' list is empty")
        return errors

    connector_keys, mcp_status = _mcp_server_keys(base_dir)
    seen_ids: set = set()
    for i, s in enumerate(seats):
        if not isinstance(s, dict):
            errors.append(f"seats[{i}]: must be a JSON object")
            continue
        sid = s.get("id", f"<index {i}>")
        for field in REQUIRED_FIELDS:
            if field not in s or s[field] in (None, "", []):
                errors.append(f"{sid}: missing required field '{field}'")
        if "id" in s:
            if s["id"] in seen_ids:
                errors.append(f"{sid}: duplicate id")
            seen_ids.add(s["id"])
            if s["id"] not in KNOWN_SEATS:
                errors.append(f"{sid}: id not in known seats {sorted(KNOWN_SEATS)}")
        gcd = s.get("git_comfort_default")
        if gcd is not None and gcd not in COMFORTS:
            errors.append(f"{sid}: git_comfort_default={gcd!r} not in {sorted(COMFORTS)}")
        playbook = s.get("playbook")
        if isinstance(playbook, str) and playbook:
            if not (base_dir / ".claude" / "skills" / playbook).is_dir():
                errors.append(f"{sid}: playbook skill dir not found: .claude/skills/{playbook}/")
        connectors = s.get("connectors")
        if isinstance(connectors, list):
            if mcp_status == "absent":
                pass  # skip connector validation when .mcp.json is absent
            elif mcp_status == "malformed":
                errors.append(f"{sid}: cannot validate connectors — .mcp.json is not valid JSON")
            else:
                for c in connectors:
                    if c not in connector_keys:
                        errors.append(f"{sid}: connector {c!r} not declared in .mcp.json mcpServers")
    missing = KNOWN_SEATS - seen_ids
    if missing:
        errors.append(f"missing seats: {sorted(missing)}")
    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    manifest_path = repo_root / MANIFEST_REL
    if not manifest_path.exists():
        print(f"FAIL  {MANIFEST_REL}\n  - manifest file not found")
        return 1
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL  {MANIFEST_REL}\n  - invalid JSON: {exc}")
        return 1
    errors = validate_manifest(data, repo_root)
    if errors:
        print(f"FAIL  {MANIFEST_REL}")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"ok    {MANIFEST_REL} ({len(data.get('seats', []))} seats)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
