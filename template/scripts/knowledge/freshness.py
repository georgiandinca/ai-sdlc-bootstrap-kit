#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Is the built graph still the graph of what is checked out?

A build records the commit of every git work tree it read: the base, and each
repository cloned under it that a namespace names as a root (the product
repositories in the parent layout), together with the manifest it was built
from. `check` compares that record with what is there now, and also names the
namespaces that have no sources on disk, which is the case for the product
namespaces in a git worktree and in CI.

It sees commits only: an edit that is not committed does not make the graph
stale here, so rebuild after editing too. A repository cloned somewhere below
a root, and not named as a root itself, is not tracked."""
from __future__ import annotations

import functools
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import manifest as manifest_mod

STAMP = "built.json"


def work_tree(root, base) -> Path:
    """The git work tree that owns a root. A repository cloned under the base
    is git-ignored by the base and answers for its own files; any other root
    belongs to the base."""
    root, base = Path(root).resolve(), Path(base).resolve()
    folder = root if root.is_dir() else root.parent
    # only a folder between the root and the base that holds .git can be another
    # work tree; without one the answer is the base, and no git call is needed
    between = [folder, *folder.parents]
    if base not in between:
        return base
    if not any((p / ".git").exists() for p in between[:between.index(base)]):
        return base
    top = _toplevel(str(folder))
    return top if top and top != base and base in top.parents else base


@functools.lru_cache(maxsize=None)
def _toplevel(folder: str):
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=folder,
                           capture_output=True, text=True)
    except OSError:
        return None
    return Path(r.stdout.strip()).resolve() if r.returncode == 0 and r.stdout.strip() else None


def _head(tree: Path):
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(tree),
                           capture_output=True, text=True)
    except OSError:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def heads(data, base) -> dict:
    """{work tree, relative to the base ('.' for the base): commit or None}."""
    base = Path(base).resolve()
    trees = {base}
    for _name, _kind, _db, roots in manifest_mod.namespaces(data, base=base):
        trees |= {work_tree(root, base) for root in roots if Path(root).exists()}
    return {("." if t == base else str(t.relative_to(base)).replace("\\", "/")): _head(t)
            for t in sorted(trees)}


def _stamp(data, base) -> Path:
    return Path(manifest_mod.overlay_db(data, base=base)).parent / STAMP


def _manifest_digest(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def without_sources(data, base) -> list:
    """Namespaces none of whose roots exist under the base: nothing was read
    for them, so their part of the graph is empty whatever `state` says."""
    return [name for name, _kind, _db, roots in manifest_mod.namespaces(data, base=base)
            if not any(Path(root).exists() for root in roots)]


def forget(data, base) -> None:
    """Called when a build starts, so a build that fails leaves no record."""
    _stamp(data, base).unlink(missing_ok=True)


def record(data, base) -> dict:
    stamp = {"built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "manifest": _manifest_digest(data),
             "heads": heads(data, base)}
    path = _stamp(data, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    return stamp


def check(data=None, base=None) -> dict:
    """{'state': 'fresh' | 'stale' | 'unbuilt', 'built_at', 'changed', 'without_sources'}.
    `changed` lists each work tree whose commit differs from the one built, each
    one cloned or removed since, and the manifest when it was edited.
    `without_sources` lists the namespaces that are empty because their roots
    are not on disk here."""
    data = data or manifest_mod.load()
    base = base or manifest_mod.REPO_ROOT
    missing = without_sources(data, base)
    unbuilt = {"state": "unbuilt", "built_at": None, "changed": [], "without_sources": missing,
               "fix": "python3 scripts/knowledge/ingest.py --build"}
    path = _stamp(data, base)
    if not path.exists():
        return unbuilt
    try:
        stamp = json.loads(path.read_text(encoding="utf-8"))
        built = dict(stamp["heads"])
    except (ValueError, KeyError, TypeError):
        return unbuilt
    if not all(Path(db).exists() for _n, _k, db, _r in manifest_mod.namespaces(data, base=base)):
        return unbuilt
    now = heads(data, base)
    changed = [{"tree": t, "built": built.get(t), "now": now.get(t)}
               for t in sorted(set(built) | set(now)) if built.get(t) != now.get(t)]
    if stamp.get("manifest") != _manifest_digest(data):
        changed.append({"tree": "graph-manifest.json", "built": stamp.get("manifest"),
                        "now": _manifest_digest(data)})
    out = {"state": "stale" if changed else "fresh", "built_at": stamp.get("built_at"),
           "changed": changed, "without_sources": missing}
    if changed:
        out["fix"] = "python3 scripts/knowledge/ingest.py --build"
    return out
