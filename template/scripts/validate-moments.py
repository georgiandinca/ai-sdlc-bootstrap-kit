#!/usr/bin/env python3
"""Validate the session lifecycle-moments manifest (scripts/session/moments.json).

The manifest binds each conversational "moment" in a working session to a handler
script, a Claude Code hook, and a per-git-comfort behaviour. Phases 2-3 import it;
this validator keeps it honest, the same way validate-skills.py and
validate-frontmatter.py guard their contracts.

Checks:
  - valid JSON with a top-level "moments" list (non-empty)
  - each moment has: id, trigger, handler, hook, status, behavior_by_comfort
  - status in {active, planned}
  - behavior_by_comfort keys == {git-native, guided, hidden}; values in {auto, offer, skip}
  - ids are unique
  - handler file exists when status == "active"

Usage:  validate-moments.py           # validate scripts/session/moments.json
Exit 0 if valid, 1 otherwise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_FIELDS = ["id", "trigger", "handler", "hook", "status", "behavior_by_comfort"]
STATUSES = {"active", "planned"}
COMFORT_KEYS = {"git-native", "guided", "hidden"}
BEHAVIORS = {"auto", "offer", "skip"}
MANIFEST_REL = "scripts/session/moments.json"


def validate_manifest(data, base_dir: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest root must be a JSON object"]
    moments = data.get("moments")
    if not isinstance(moments, list):
        return ["manifest must have a 'moments' list"]
    if not moments:
        errors.append("'moments' list is empty")

    seen_ids: set = set()
    for i, m in enumerate(moments):
        if not isinstance(m, dict):
            errors.append(f"moments[{i}]: must be a JSON object")
            continue
        mid = m.get("id", f"<index {i}>")
        for field in REQUIRED_FIELDS:
            if field not in m:
                errors.append(f"{mid}: missing required field '{field}'")
        if "id" in m:
            if m["id"] in seen_ids:
                errors.append(f"{mid}: duplicate id")
            seen_ids.add(m["id"])
        status = m.get("status")
        if status is not None and status not in STATUSES:
            errors.append(f"{mid}: status={status!r} not in {sorted(STATUSES)}")
        bbc = m.get("behavior_by_comfort")
        if isinstance(bbc, dict):
            if set(bbc.keys()) != COMFORT_KEYS:
                errors.append(f"{mid}: behavior_by_comfort keys must be exactly {sorted(COMFORT_KEYS)}")
            for k, v in bbc.items():
                if v not in BEHAVIORS:
                    errors.append(f"{mid}: behavior_by_comfort[{k}]={v!r} not in {sorted(BEHAVIORS)}")
        elif bbc is not None:
            errors.append(f"{mid}: behavior_by_comfort must be an object")
        handler = m.get("handler")
        if status == "active" and isinstance(handler, str):
            if not (base_dir / handler).exists():
                errors.append(f"{mid}: active handler not found: {handler}")
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
    print(f"ok    {MANIFEST_REL} ({len(data.get('moments', []))} moments)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
