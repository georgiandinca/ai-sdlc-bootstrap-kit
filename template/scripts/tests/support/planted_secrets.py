#!/usr/bin/env python3
"""Planted secrets for tests: known fake values that must never reach any output.

A test feeds `carrier()` (or single values from `PLANTED`) into a script, then checks
stdout, stderr and every file the script wrote with `leaks()` / `leaks_in_files()`, or
with `PlantedSecretsMixin.assertNoPlantedSecrets`:

    sys.path.insert(0, "<scripts>/tests/support"); import planted_secrets as ps
    proc = run_script(input=ps.carrier())
    self.assertNoPlantedSecrets(proc.stdout, proc.stderr, files=[out_dir])

- `PLANTED`     one value per redaction kind of scripts/lib/redact.py (but own_secret).
- `OWN_SECRET`  a value with no known shape: only redacted when the caller passes it as
                its own secret (`redact_text(..., secrets=[...])`, `--secret-env`).
- `SECRETS`     all of the above.
- `carrier()`   text that holds each planted value where its redaction rule finds it.

Every value is made at import time from a fresh random part, so none is written in any
file beforehand (a file scan cannot match the test's own source) and no secret scanner
mistakes one for a real token. Values use only letters, digits, `-` and `.`, so URL or
JSON quoting cannot hide a leak; their base64 forms (as in a Basic auth header) count as
leaks too. Failure messages name the kind and the file, never the value. Stdlib only.
"""
from __future__ import annotations

import base64
import json
import os
import secrets as _random
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

NONCE = _random.token_hex(4)        # 8 hex characters, new on every run


def _b64url(obj) -> str:
    raw = json.dumps(obj, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _value(tag: str) -> str:
    return f"Pl4nted{tag}{NONCE}"


# In redact.KINDS order. Each value is the part a rule must hide, not its context.
PLANTED: Dict[str, str] = {
    "auth_header": _value("Bearer"),
    "jwt": ".".join([_b64url({"alg": "HS256", "typ": "JWT"}),
                     _b64url({"sub": "planted-" + NONCE}), _value("JwtSig")]),
    "cookie": _value("Session"),
    "url_credentials": _value("UrlPw"),
    "key_value": _value("DbPw"),
    "env_dump": _value("Env"),
    "private_key": _value("PemBody") + "AAAA",
    # A public token format, assembled here so no literal token sits in the source.
    "token_shape": "gh" + "p_" + _value("Token").ljust(36, "x"),
}
OWN_SECRET = "own-" + _value("Secret")
SECRETS: Tuple[str, ...] = (*PLANTED.values(), OWN_SECRET)


def named_secrets(extra: Optional[Dict[str, str]] = None) -> List[Tuple[str, str]]:
    """(name, value) for every planted value, then `extra`, in a fixed order."""
    pairs = [*PLANTED.items(), ("own_secret", OWN_SECRET)]
    pairs += list((extra or {}).items())
    return pairs


def _carrier_lines(kind: str) -> List[str]:
    v = PLANTED[kind]
    return {
        "auth_header": [f"curl -H 'Authorization: Bearer {v}' https://ci.example.test/api"],
        "jwt": [f"using id token {v} for the deploy step"],
        "cookie": [f"Set-Cookie: JSESSIONID={v}; Path=/"],
        "url_credentials": [f"git clone https://builder:{v}@git.example.test/app.git"],
        "key_value": [f"connect db_password={v} host=db.example.test"],
        "env_dump": ["HOME=/home/build", "PATH=/usr/bin:/bin", "LANG=C.UTF-8",
                     "WORKSPACE=/ws/app", f"DEPLOY_HINT={v}", "CI=true"],
        "private_key": ["-----BEGIN RSA PRIVATE KEY-----", v, "MorePemBody" + NONCE,
                        "-----END RSA PRIVATE KEY-----"],
        "token_shape": [f"configured access with {v} for the registry"],
    }[kind]


def carrier(kinds: Optional[Iterable[str]] = None, own: bool = False) -> str:
    """Lines holding each planted value (all kinds, or `kinds`) in a context its rule
    catches, separated by ordinary lines; `own=True` adds a line with OWN_SECRET. Ends
    with a newline. An unknown kind raises KeyError."""
    lines: List[str] = ["build started"]
    for kind in (PLANTED if kinds is None else kinds):
        if kind not in PLANTED:
            raise KeyError(kind)
        lines += _carrier_lines(kind)
        lines.append("step done")
    if own:
        lines.append(f"release note mentions {OWN_SECRET}")
    return "\n".join(lines) + "\n"


def _forms(value: str) -> List[bytes]:
    """The value's bytes and the parts of its base64 forms that do not depend on what
    surrounds it (one per alignment, standard and URL-safe alphabets)."""
    raw = value.encode()
    forms = [raw]
    for pad in range(3):
        total = pad + len(raw)
        start, end = -(-8 * pad // 6), 8 * total // 6
        for enc in (base64.b64encode, base64.urlsafe_b64encode):
            forms.append(enc(b"\0" * pad + raw)[start:end])
    return forms


def leaks(*texts, extra: Optional[Dict[str, str]] = None) -> List[str]:
    """Names of the planted values (and `extra` {name: value}) found in any of `texts`
    (str, bytes or None), each once, in `named_secrets()` order."""
    blobs = [t.encode("utf-8", "surrogateescape") if isinstance(t, str) else t
             for t in texts if t]
    return [name for name, value in named_secrets(extra)
            if any(form in blob for blob in blobs for form in _forms(value))]


def leaks_in_files(*paths, extra: Optional[Dict[str, str]] = None) -> List[Tuple[str, str]]:
    """(relative path, name) for each planted value found in a file under `paths` (files
    or folders, walked without following symlinks), sorted by path. A path that does not
    exist raises FileNotFoundError, so a script that wrote nothing cannot pass by mistake."""
    found: List[Tuple[str, str]] = []
    for top in map(Path, paths):
        if not top.exists() and not top.is_symlink():
            raise FileNotFoundError(str(top))
        if top.is_file() and not top.is_symlink():
            files = [(top.name, top)]
        else:
            files = []
            for folder, dirs, names in os.walk(top):
                dirs.sort()
                for name in names:
                    path = Path(folder) / name
                    if path.is_file() and not path.is_symlink():
                        files.append((path.relative_to(top).as_posix(), path))
        for rel, path in sorted(files):
            found += [(rel, name) for name in leaks(path.read_bytes(), extra=extra)]
    return found


class PlantedSecretsMixin:
    """For unittest.TestCase subclasses: `assertNoPlantedSecrets`."""

    def assertNoPlantedSecrets(self, *texts, files: Iterable = (), what: str = "output",
                               extra: Optional[Dict[str, str]] = None):
        bad = [f"text: {name}" for name in leaks(*texts, extra=extra)]
        bad += [f"{rel}: {name}" for rel, name in leaks_in_files(*files, extra=extra)]
        if bad:
            raise self.failureException(
                f"planted secrets leaked into {what}: " + "; ".join(bad))
