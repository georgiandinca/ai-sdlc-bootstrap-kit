#!/usr/bin/env python3
"""Fold the kit's local pre-commit hooks into a project's existing config.

Used by `bootstrap.sh --hooks repo`, when the governance hooks must run in a code
repository that already has its own `.pre-commit-config.yaml`.

Existing hooks are never removed and never reordered. A kit hook whose `id` is
already present is left alone, so re-running changes nothing. Script paths in
`entry` are rewritten with `--prefix` so they resolve from the target repo to the
kit. NOTE: PyYAML does not preserve comments — pass `--backup` (bootstrap.sh does)
so the original file is recoverable.

Usage:
  merge-precommit.py <target_config> <source_config> [--prefix <rel>]
                     [--dry-run] [--backup <path>]

Exit code 0 on success, 2 if the target file cannot be parsed (invalid YAML,
not a mapping, or a `repos`/`hooks` shape we can't safely merge into).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    sys.exit("error: PyYAML is required (pip install pyyaml)")


def _validate_shape(doc: dict, label: str) -> None:
    """Raise ValueError if `repos`/`hooks` don't have a shape we can safely
    merge into. Called on the target before anything is read from it or
    written to it, so a malformed target is refused rather than guessed at
    (and never raises an uncaught AttributeError/TypeError out of `merge`)."""
    repos = doc.get("repos")
    if repos is None:
        return
    if not isinstance(repos, list):
        raise ValueError(f"{label} 'repos' must be a list")
    for repo in repos:
        if not isinstance(repo, dict):
            raise ValueError(f"{label} 'repos' entries must be mappings")
        hooks = repo.get("hooks")
        if hooks is None:
            continue
        if not isinstance(hooks, list):
            raise ValueError(f"{label} repo 'hooks' must be a list")
        for hook in hooks:
            if not isinstance(hook, dict):
                raise ValueError(f"{label} hook entries must be mappings")


def _existing_ids(doc: dict) -> set[str]:
    ids: set[str] = set()
    for repo in doc.get("repos") or []:
        for hook in repo.get("hooks") or []:
            if isinstance(hook, dict) and "id" in hook:
                ids.add(hook["id"])
    return ids


def _reprefix(entry: str, prefix: str) -> str:
    """Rewrite `python scripts/x.py …` to `python <prefix>/scripts/x.py …`."""
    if not prefix:
        return entry
    parts = entry.split()
    return " ".join(
        f"{prefix}/{p}" if p.startswith("scripts/") else p for p in parts
    )


def merge(target: Path, source: Path, prefix: str = "", dry_run: bool = False,
          backup: Path | None = None) -> list[str]:
    """Merge source's local hooks into target. Returns the log lines."""
    try:
        target_doc = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"target is not valid YAML: {exc}") from exc
    if not isinstance(target_doc, dict):
        raise ValueError("target must be a YAML mapping")
    _validate_shape(target_doc, "target")

    source_doc = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    present = _existing_ids(target_doc)
    log: list[str] = []
    new_hooks = []

    for repo in source_doc.get("repos") or []:
        if repo.get("repo") != "local":
            continue
        for hook in repo.get("hooks") or []:
            hid = hook.get("id")
            if hid in present:
                log.append(f"present {hid}")
                continue
            hook = dict(hook)
            if "entry" in hook:
                hook["entry"] = _reprefix(hook["entry"], prefix)
            new_hooks.append(hook)
            log.append(f"added {hid}")

    if not new_hooks:
        return log

    if dry_run:
        return log

    if backup is not None:
        backup.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite an existing backup: it holds the state from BEFORE
        # the first merge ever ran against this target. A later run (e.g. the
        # kit gained a new hook) must not replace that recovery copy with an
        # already-merged file, which would make the backup worthless.
        if not backup.exists():
            shutil.copyfile(target, backup)

    repos = target_doc.setdefault("repos", [])
    local = next((r for r in repos if r.get("repo") == "local"), None)
    if local is None:
        local = {"repo": "local", "hooks": []}
        repos.append(local)
    local.setdefault("hooks", []).extend(new_hooks)

    src_types = source_doc.get("default_install_hook_types")
    if src_types and "default_install_hook_types" not in target_doc:
        target_doc["default_install_hook_types"] = src_types

    target.write_text(
        yaml.safe_dump(target_doc, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return log


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target")
    ap.add_argument("source")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup")
    args = ap.parse_args()

    try:
        log = merge(
            Path(args.target), Path(args.source), args.prefix, args.dry_run,
            Path(args.backup) if args.backup else None,
        )
    except (ValueError, OSError) as exc:
        print(f"merge-precommit: {exc}", file=sys.stderr)
        return 2
    for line in log:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
