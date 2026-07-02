#!/usr/bin/env bash
# Switch the operator's seat: re-runs "Phase B" of onboarding without touching
# identity or environment. Updates USER.md's Seat + Git comfort from
# seat-profiles.json. Portable across macOS (BSD) and Linux (GNU) sed.
set -uo pipefail

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "not inside a git repo"; exit 1; }
cd "$repo_root"
[ -f USER.md ] || { echo "no USER.md — run onboarding first (see ONBOARDING.md)"; exit 1; }
[ -f scripts/session/seat-profiles.json ] || { echo "no seat-profiles.json"; exit 1; }

new_seat="${1:-}"
if [ -z "$new_seat" ]; then
  echo "Usage: scripts/session/switch-seat.sh <Architect|EM|Product|Developer|QA>"
  exit 2
fi

# Resolve canonical id, git-comfort default, and playbook for the requested seat.
resolved=$(python3 - "$new_seat" <<'PY'
import json, sys
from pathlib import Path
seat = sys.argv[1]
try:
    data = json.loads(Path("scripts/session/seat-profiles.json").read_text())
except Exception:
    sys.exit(1)
for s in data.get("seats", []):
    if str(s.get("id", "")).lower() == seat.lower():
        print(f"{s['id']}|{s.get('git_comfort_default','')}|{s.get('playbook','')}")
        sys.exit(0)
sys.exit(1)
PY
) || { echo "unknown seat: ${new_seat} (must be one of Architect/EM/Product/Developer/QA)"; exit 2; }

canonical="${resolved%%|*}"; rest="${resolved#*|}"
comfort="${rest%%|*}"; playbook="${rest#*|}"

# Update USER.md in place (exact-case markers; portable -i.bak, remove backup per call).
if grep -qE '^- \*\*Seat:\*\*' USER.md; then
  sed -i.bak -E "s|^- \*\*Seat:\*\*.*|- **Seat:** ${canonical}|" USER.md && rm -f USER.md.bak
else
  printf -- '- **Seat:** %s\n' "${canonical}" >> USER.md
fi
if grep -qE '^- \*\*Git comfort:\*\*' USER.md; then
  sed -i.bak -E "s|^- \*\*Git comfort:\*\*.*|- **Git comfort:** ${comfort}|" USER.md && rm -f USER.md.bak
else
  printf -- '- **Git comfort:** %s\n' "${comfort}" >> USER.md
fi
rm -f USER.md.bak

echo "[switch-seat] seat -> ${canonical} (git-comfort ${comfort})."
echo "[switch-seat] load the ${playbook} skill for this seat. Change git-comfort in USER.md if it doesn't fit."
