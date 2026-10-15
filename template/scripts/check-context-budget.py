#!/usr/bin/env python3
"""Check the size of the always-loaded instructions against a budget.

Every session loads AGENTS.md, CLAUDE.md, the .claude/rules/ files and the
description of every skill under .claude/skills/. That text only grows; this
script keeps it inside the limits in scripts/context-budget.json, like
validate-skills.py / validate-frontmatter.py keep their own contracts.

Measured in characters (stdlib only, the same result on every machine), with
an approximate token count (characters / 4). Path-scoped rules are counted
too: they load whenever a matching file is touched.

Checks:
  - AGENTS.md, CLAUDE.md, the .claude/rules group, the skill-descriptions
    group and the total, each against its limit; an overflow fails and says
    how many characters to cut
  - every skill description against description_max (also enforced by
    validate-skills.py, which reads the same file)
  - a limit more than warn_slack_pct above the actual size warns, so limits
    cannot go slack; the warning says what to lower it to
Each seat in scripts/session/seat-profiles.json is listed with its playbook's
description.

Raise a limit only together with the text that needs it, and say why in the
project's CHANGELOG.

Usage:
  check-context-budget.py                 # report and check
  check-context-budget.py --json          # sizes and limits as JSON
  check-context-budget.py --write-limits  # set every group limit to today's
                                          # size plus headroom_pct (never
                                          # touches description_max)
Exit 0 if within budget (warnings allowed), 1 over budget, 2 on bad usage or
a missing / malformed limits file.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("error: PyYAML is required (pip install pyyaml)")

LIMITS_REL = "scripts/context-budget.json"
SEATS_REL = "scripts/session/seat-profiles.json"
FILES = ["AGENTS.md", "CLAUDE.md"]
RULES = ".claude/rules"
SKILLS = ".claude/skills"
DESCRIPTIONS = "skill-descriptions"
TOTAL = "total"
KEYS = FILES + [RULES, DESCRIPTIONS, TOTAL]
DEFAULTS = {"description_max": 500, "warn_slack_pct": 15, "headroom_pct": 6}
CHARS_PER_TOKEN = 4


def description(skill_md: Path) -> str:
    """The frontmatter description of a SKILL.md ('' when it has none)."""
    text = skill_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                fm = yaml.safe_load("\n".join(lines[1:i]))
            except yaml.YAMLError:
                return ""
            desc = fm.get("description") if isinstance(fm, dict) else None
            return desc if isinstance(desc, str) else ""
    return ""


def measure(root: Path) -> dict:
    """Sizes of everything always loaded, by file, rule, skill and group."""
    files = {f: (len((root / f).read_text(encoding="utf-8")) if (root / f).is_file() else 0)
             for f in FILES}
    rules = {p.relative_to(root).as_posix(): len(p.read_text(encoding="utf-8"))
             for p in sorted((root / RULES).rglob("*.md"))} if (root / RULES).is_dir() else {}
    skills = {p.parent.name: len(description(p))
              for p in sorted((root / SKILLS).rglob("SKILL.md"))} if (root / SKILLS).is_dir() else {}
    sizes = dict(files)
    sizes[RULES] = sum(rules.values())
    sizes[DESCRIPTIONS] = sum(skills.values())
    sizes[TOTAL] = sum(files.values()) + sizes[RULES] + sizes[DESCRIPTIONS]
    return {"sizes": sizes, "rules": rules, "skills": skills}


def seats(root: Path) -> list[tuple[str, str]]:
    """(seat id, playbook) pairs from the seat manifest; [] if it is absent or unreadable."""
    try:
        data = json.loads((root / SEATS_REL).read_text(encoding="utf-8"))
        return [(s["id"], s["playbook"]) for s in data["seats"]
                if isinstance(s, dict) and isinstance(s.get("id"), str)
                and isinstance(s.get("playbook"), str)]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def with_headroom(n: int, pct: float) -> int:
    """n plus pct %, rounded up to a multiple of 10."""
    return int(math.ceil(n * (1 + pct / 100) / 10) * 10)


def load_limits(path: Path) -> tuple[dict | None, str]:
    if not path.is_file():
        return None, (f"{LIMITS_REL} not found; create it with "
                      "`python3 scripts/check-context-budget.py --write-limits`")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return None, f"{LIMITS_REL} is not valid JSON: {exc}"
    if not isinstance(data, dict) or not isinstance(data.get("limits"), dict):
        return None, f"{LIMITS_REL} must be an object with a 'limits' object"
    missing = [k for k in KEYS if not isinstance(data["limits"].get(k), int)]
    if missing:
        return None, f"{LIMITS_REL}: no integer limit for {', '.join(missing)}"
    for k, v in DEFAULTS.items():
        data.setdefault(k, v)
    return data, ""


def write_limits(path: Path, m: dict) -> dict:
    data = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("version", 1)
    for k, v in DEFAULTS.items():
        data.setdefault(k, v)
    data["limits"] = {k: with_headroom(m["sizes"][k], data["headroom_pct"]) for k in KEYS}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def report(m: dict, cfg: dict, root: Path) -> int:
    """Print every item against its limit; return the number of overflows."""
    sizes, limits = m["sizes"], cfg["limits"]
    dmax, slack, head = cfg["description_max"], cfg["warn_slack_pct"], cfg["headroom_pct"]
    over = 0

    def line(label: str, n: int, cap: int, indent: str = "", warn_slack: bool = True) -> None:
        nonlocal over
        if n > cap:
            over += 1
            status, note = "OVER", f"  cut {n - cap}"
        elif warn_slack and cap > n * (1 + slack / 100):
            status = "warn"
            note = (f"  limit is {round(100 * cap / n - 100) if n else 'inf'}% above actual; "
                    f"lower it to {with_headroom(n, head)}")
        else:
            status, note = "ok", ""
        print(f"{indent}{status:<5} {label:<44} {n:>6} / {cap}{note}")

    print("Context budget (characters; ~tokens = characters / 4)")
    for f in FILES:
        line(f, sizes[f], limits[f])
    line(f"{RULES} ({len(m['rules'])} files)", sizes[RULES], limits[RULES])
    for rel, n in m["rules"].items():
        print(f"        {rel:<44} {n:>6}")
    line(f"{DESCRIPTIONS} ({len(m['skills'])} skills)", sizes[DESCRIPTIONS], limits[DESCRIPTIONS])
    for name, n in m["skills"].items():
        line(name, n, dmax, indent="  ", warn_slack=False)
    line(TOTAL, sizes[TOTAL], limits[TOTAL])

    seat_rows = seats(root)
    if seat_rows:
        print("\nSeats (each seat's playbook description):")
        for sid, playbook in seat_rows:
            n = m["skills"].get(playbook)
            if n is None:
                print(f"  {sid:<10} {playbook:<24} not installed")
            else:
                print(f"  {sid:<10} {playbook:<24} {n:>6} / {dmax}")

    t = sizes[TOTAL]
    print(f"\nalways loaded: {t} characters (~{t // CHARS_PER_TOKEN} tokens) "
          f"of {limits[TOTAL]} ({LIMITS_REL})")
    return over


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    args = set(argv)
    if args - {"--json", "--write-limits"}:
        print(__doc__, file=sys.stderr)
        return 2
    m = measure(root)
    path = root / LIMITS_REL

    if "--write-limits" in args:
        data = write_limits(path, m)
        print(f"limits written: {LIMITS_REL} (current size + {data['headroom_pct']}%)")
    if "--json" in args:
        print(json.dumps(m, indent=2))
        return 0

    cfg, err = load_limits(path)
    if cfg is None:
        print(f"error: {err}", file=sys.stderr)
        return 2
    over = report(m, cfg, root)
    if over:
        print(f"{over} item(s) over budget. Cut the text, or raise the limit in "
              f"{LIMITS_REL} with the reason in the CHANGELOG.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
