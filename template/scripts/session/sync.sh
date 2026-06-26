#!/usr/bin/env bash
# Fast-forward sync of the current repo. Refuses on a dirty tree.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
if [ -n "$(git status --porcelain)" ]; then
  echo "[sync] working tree is dirty — refusing to pull. Commit or stash first." >&2
  exit 1
fi
git pull --ff-only
echo "[sync] up to date."
