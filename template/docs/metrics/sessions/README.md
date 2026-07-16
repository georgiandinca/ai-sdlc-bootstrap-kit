# Per-user session ledgers

One CSV per developer — `<user>.csv`, where `<user>` is the local part of
their `git config user.email` (sanitized) — regenerated on every SessionEnd
by `scripts/session/collect-usage.sh` → `scripts/spend/export_sessions.py`
from that developer's **local** dashboard DB. The files land with normal
PRs; that is the whole transport: no server, no shared DB.

Merge everyone's ledgers into the dashboard on any machine:

    python3 scripts/spend/import_sessions.py

Re-running is a no-op (upsert by `session_id`; the larger token total wins,
so a fresher local parse is never overwritten by an older committed CSV).

**Privacy.** Rows carry `ticket` and `task`, visible to everyone with repo
access. For sensitive client work leave `task` empty (the collector defaults
it to empty) and/or keep ticket keys out of branch names. Data arrives with
commit latency — this ledger feeds retros and ROI reviews, not real-time
monitoring.
