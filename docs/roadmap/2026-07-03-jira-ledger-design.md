---
title: "JIRA → CSV Ledger → Knowledge Graph (design)"
status: draft
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-07-03
classification: internal
ai-trust: working
---

# JIRA → CSV Ledger → Knowledge Graph

**Goal.** A **repeatable, scripted** process that (1) pulls JIRA issues from either a
**Cloud** or a **Data Center (on-prem)** instance, (2) writes a **diff-friendly CSV
ledger** tracked in git, (3) ingests that ledger into the Phase-4 knowledge graph as a
new `issue` node kind, and (4) **auto-links** every issue to the docs, ADRs, stories,
commits, and code that already reference it — using JIRA keys that already flow through
the repo. Dependency-light: Python **stdlib only**, same posture as the Phase-3
collector and the Phase-4 ingesters.

**Non-negotiable framing.** This is a *template kit*. The feature ships a **real,
runnable reference**: a working exporter (both deployment backends), a committed sample
ledger, a real `issues` namespace in the graph manifest, and a genuine traceability
chain from an issue through a commit to code and a story. "Add another project / swap
Cloud↔DC" is a config edit, not a rewrite.

---

## 1. Decisions (resolved in brainstorming)

| # | Decision | Choice |
|---|---|---|
| 1 | Fetch architecture | **Single REST exporter + deployment adapter.** One `export_jira.py`; all Cloud-vs-DC differences hide behind a small adapter selected by one `deployment` field. |
| 2 | MCP posture | **Demoted to optional Cloud-only convenience.** The hosted Atlassian MCP (`mcp.atlassian.com`) is Cloud-only and has no DC equivalent, so it is *not* part of the contract — one documented shortcut, never the pipeline, never CI. |
| 3 | Separation of concerns | **Three isolated units**: Fetch (network, non-deterministic) → Ledger (committed CSV) → Ingest (pure, offline, testable). The graph build and CI never touch JIRA. |
| 4 | Ledger format & location | **`docs/product/jira/issues.csv`** — stable column order, rows sorted by key, `description` normalized + capped (≤500 chars). Minimal git diffs; reviewable in a PR. |
| 5 | Graph model | New node kind **`issue`** (id `issue:<KEY>`) in its own **`issues` namespace**; all edges auto-derived from existing signals, each citing its source. |
| 6 | Linking source | **Reuse existing JIRA-key flows**: commit trailers (`Refs: KEY`), frontmatter link fields, and CSV epic/parent fields. No new human convention required. |
| 7 | Secrets | **Env-only.** `config.json` (project, JQL, deployment) is tracked; tokens/passwords never are. |

---

## 2. Architecture

Three units, mirroring the existing collector/ingester split. Only the **Fetch** unit is
new-in-kind; **Ledger** is data; **Ingest** extends the Phase-4 graph.

| Unit | File | Purpose | Deterministic? |
|---|---|---|---|
| **Fetch** | `scripts/jira/export_jira.py` | Pull issues from JIRA (Cloud or DC) → write the CSV. The only network-facing, non-deterministic part. | No (network) |
| **Ledger** | `docs/product/jira/issues.csv` | The committed CSV ledger. Stable columns, sorted rows, normalized description. | — |
| **Ingest** | `scripts/knowledge/ingest_issues.py` | Pure `CSV → (nodes, edges)`, wired into `ingest.py` as the `issues` namespace. Fully unit-testable, no network. | Yes |

```
JIRA (Cloud | DC)
      │   export_jira.py  ── deployment adapter (base URL · auth · api version · pagination)
      ▼
docs/product/jira/issues.csv        ← committed, reviewed in PRs
      │   ingest_issues.py  (via ingest.py --build, "issues" namespace)
      ▼
.knowledge issue graph  ──edges──▶  commits ▶ code · stories · ADRs · docs
```

### 2.1 Fetch — one exporter, a deployment adapter

`export_jira.py` reads `docs/product/jira/config.json`, resolves auth from env, calls the
backend selected by `deployment`, normalizes the JSON to rows, and writes the CSV. All
Cloud-vs-DC variance reduces to **four knobs** behind a tiny adapter; nothing downstream
changes.

| Knob | JIRA Cloud | JIRA Data Center (on-prem) |
|---|---|---|
| **Base URL** | `https://<site>.atlassian.net` (from env) | `https://jira.company.com` (self-hosted, from env) |
| **Auth** | Basic: `email` + **API token** (`base64(email:token)`) | Bearer **Personal Access Token** (DC 8.14+); Basic `user:password` fallback |
| **API version** | v3 | v2 (no v3 on DC) |
| **Search + pagination** | enhanced JQL search endpoint, **cursor** (`nextPageToken`) | `/rest/api/2/search`, **offset** (`startAt`/`maxResults`) |

- **Adapter shape.** Two small profile objects (`CLOUD`, `DATACENTER`), each supplying:
  `auth_header(env)`, `search_path`, `paginate(fetch_page) -> issues`. The exporter body
  is backend-agnostic; adding a future backend = one profile.
- **Cloud search endpoint.** Atlassian has been migrating Cloud to the enhanced
  `/rest/api/3/search/jql` cursor endpoint (the older bulk `/search` GET was retired on
  Cloud). Because search+pagination is a single knob, this stays isolated — **confirm the
  exact current Cloud endpoint against live docs at implementation time**; DC's v2
  `/search` is stable.
- **Transport.** Stdlib `urllib.request` only. Timeouts, one bounded retry on 429/5xx,
  no third-party HTTP library.
- **Fields requested.** `key, issuetype, summary, status, assignee, reporter, labels,
  priority, resolution, created, updated, parent, description` + sprint & epic (see §3.2)
  + story points (configurable custom-field id, see §5).

### 2.2 Ingest — the `issues` namespace

`ingest_issues.py` exposes `ingest_root(csv_path, namespace, base) -> (nodes, edges)`,
matching the `ingest_docs` / `ingest_code` signature so `ingest.py` wires it with no
special-casing beyond a `kind: "issues"` branch. The manifest gains one entry:

```json
{
  "namespaces": {
    "docs":     { "kind": "docs", "db": "docs/.knowledge/graph.db", "roots": ["docs/"] },
    "kit-code": { "kind": "code", "db": ".knowledge/graph.db",       "roots": ["scripts/", "dashboard/"] },
    "issues":   { "kind": "issues", "db": "docs/product/jira/.knowledge/graph.db", "roots": ["docs/product/jira/issues.csv"] }
  },
  "overlay": "docs/knowledge/.knowledge/global.db"
}
```

The issue namespace's own edges are `part-of` (epic/parent, both endpoints are issues).
Cross-namespace edges (issue↔commit, doc↔issue) resolve into the **global overlay**,
exactly like today's cross-namespace edges — no new machinery in the orchestrator's
resolve pass.

---

## 3. The ledger

### 3.1 Columns (stable order)

```
key, type, title, status, assignee, reporter, labels, sprint,
epic, parent, priority, story_points, created, updated, resolution, url, description
```

- **One issue per row**, **rows sorted by key** (natural sort on the numeric suffix so
  `PROJ-2` precedes `PROJ-10`).
- Multi-values (`labels`) joined with `;`.
- **`description` normalized**: collapse whitespace, strip markup/ADF to plain text, cap
  at ≤500 chars. Full text stays in JIRA; the graph only needs enough to search + cite.
- Written with `csv.writer`, `\n` line terminator, UTF-8 — so re-exporting an unchanged
  board yields a **byte-identical** file (empty git diff).

### 3.2 JIRA field mapping

| CSV column | Cloud source | DC source |
|---|---|---|
| `key` | `key` | `key` |
| `type` | `fields.issuetype.name` | same |
| `title` | `fields.summary` | same |
| `status` | `fields.status.name` | same |
| `assignee` | `fields.assignee.displayName` (or `emailAddress`) | `fields.assignee.displayName`/`name` |
| `reporter` | `fields.reporter.displayName` | same |
| `labels` | `fields.labels[]` | same |
| `sprint` | sprint custom field (agile) → name of active/last sprint | same (custom-field id may differ) |
| `epic` | parent epic key (`fields.parent.key` on team-managed, or Epic-Link custom field) | Epic-Link custom field |
| `parent` | `fields.parent.key` | same |
| `priority` | `fields.priority.name` | same |
| `story_points` | configurable custom-field id | configurable custom-field id |
| `created` / `updated` | `fields.created` / `fields.updated` (ISO) | same |
| `resolution` | `fields.resolution.name` (or empty) | same |
| `url` | `<base>/browse/<key>` | `<base>/browse/<key>` |
| `description` | ADF → plain text | wiki/markup → plain text |

Custom-field ids (sprint, epic-link, story points) vary per instance → declared in
`config.json` (§5), never hard-coded.

---

## 4. Graph model & linking

### 4.1 Node

- **kind** `issue`, **id** `issue:<KEY>` (e.g. `issue:PROJ-123`).
- `name` = title; `path` = `docs/product/jira/issues.csv` (citation target);
  `text` = title + normalized description (feeds content search);
  `meta` = `{type, status, assignee, reporter, labels, sprint, epic, parent, priority, story_points, url, ...}`.
- `tier` left null (issues are tracker state, not a trust-tiered source document).

### 4.2 Edges — all auto-derived, each citing its source

| Edge | from → to | Derived from | Resolves via |
|---|---|---|---|
| `part-of` | issue → issue | CSV `epic` / `parent` columns | within `issues` namespace |
| `references` | commit → issue | `Refs: KEY` (and inline `KEY`) in `git log` messages | overlay (commit lives in `kit-code`) |
| `traces` / `implements` / `cites` | doc·adr·story → issue | frontmatter link field whose value matches the JIRA key pattern | overlay |

**The key that makes linking free.** `commit_msg_ticket.py` already enforces `Refs: KEY`
trailers and injects them from `feature/KEY-slug` branch names. Phase-3's optional layer
already draws `commit → code` (`touches`) edges. So once we add `commit → issue`
(`references`), a single `trace(issue:PROJ-123)` walks **issue → commit → code** with no
new human convention. Likewise, extending `normalize_ref()` so a bare `PROJ-123`
resolves to `issue:PROJ-123` means any existing frontmatter `traces:`/`implements:`/
`cites:` list that names a JIRA key links automatically.

**Two additions to existing code (small, additive):**

1. `graph_store.normalize_ref()` — add a JIRA-key branch: a token matching
   `^[A-Z][A-Z0-9]+-\d+$` (the same `KEY_RE` `commit_msg_ticket.py` uses) → `issue:<KEY>`.
   Guarded so it can't shadow the existing `ADR-`/`AS-` rules (those are matched first).
2. A **commit→issue linker** — reads commit messages (from the Phase-3 `commits` table
   when present, else `git log`) and emits `references` edges for each `KEY` found.
   Activates only when the `issues` namespace exists; a clean no-op otherwise, mirroring
   `link_commits.py`'s optional posture.

**Honesty preserved.** An issue named in a commit or frontmatter but absent from the
ledger stays `resolved=0` (dangling) — surfaced, never invented — exactly like today.

### 4.3 Worked example (ships as the reference)

Seed `PROJ-1` in the sample ledger; a commit `... \n\nRefs: PROJ-1` touching
`scripts/jira/export_jira.py`; and `docs/product/stories/AS-0001` gaining
`traces: [PROJ-1]`. Then `ingest.py --trace issue:PROJ-1` returns the issue, the commit,
the touched code file, and the story — a real cross-namespace chain.

---

## 5. Configuration & secrets

`docs/product/jira/config.json` (tracked, no secrets):

```json
{
  "deployment": "cloud",
  "base_url_env": "JIRA_BASE_URL",
  "project": "PROJ",
  "jql": "project = PROJ ORDER BY updated DESC",
  "fields": { "sprint": "customfield_10020", "epic_link": "customfield_10014", "story_points": "customfield_10016" },
  "description_max_chars": 500
}
```

Auth env vars, resolved by the adapter:

| Deployment | Base URL | Auth env |
|---|---|---|
| `cloud` | `JIRA_BASE_URL` = `https://<site>.atlassian.net` | `JIRA_EMAIL` + `JIRA_API_TOKEN` |
| `datacenter` | `JIRA_BASE_URL` = `https://jira.company.com` | `JIRA_PAT` (preferred) or `JIRA_USER` + `JIRA_PASSWORD` |

Missing/invalid auth → exit non-zero with a precise message; the existing CSV is **never
touched**, so the graph keeps building from the last committed ledger.

---

## 6. Process wiring

- **Manual / on demand:** `python3 scripts/jira/export_jira.py` then
  `python3 scripts/knowledge/ingest.py --build`. Documented in
  `docs/product/jira/README.md`.
- **Convenience:** a `--build` flag on the exporter that chains the graph rebuild after a
  successful export (opt-in).
- **CI:** the exporter is **not** run in CI (needs live JIRA + secrets). CI ingests the
  **committed** ledger and runs the new tests, alongside the existing knowledge-graph job
  in `.gitlab-ci.yml`.
- **MCP (optional, Cloud only):** one documented line — a Cloud team may have the agent
  pull issues via the `issue-tracker` MCP and hand them to a `--from-json` mode of the
  exporter. Not required, not CI, not on the DC path.

---

## 7. Error handling & idempotency

- **Network/auth failure:** clear stderr message, non-zero exit, CSV untouched.
- **Idempotent export:** same JIRA state → byte-identical CSV → empty diff.
- **Partial page failure:** bounded retry on 429/5xx; on give-up, fail without a partial
  overwrite (write to a temp file, atomic rename only on full success).
- **Rate limiting:** honour `Retry-After` where present.
- **Malformed / missing fields:** tolerant extraction (absent custom field → empty
  column), never a crash.
- **Ingest** is pure and total: a malformed row is skipped with a warning, not fatal.

---

## 8. Testing

- `ingest_issues.py` — unit tests on a fixture CSV → asserts `issue` nodes and `part-of`
  edges (pure, offline).
- `normalize_ref()` — JIRA-key resolution, and that `ADR-`/`AS-` precedence is intact.
- commit→issue linker — fixture repo with a `Refs: PROJ-1` commit → asserts a
  `references` edge; no-op when the `issues` namespace is absent.
- End-to-end — the §4.3 worked example: `trace(issue:PROJ-1)` returns commit + code +
  story across namespaces.
- `export_jira.py` — the **normalizer** (JSON → rows) unit-tested against captured Cloud
  **and** DC JSON fixtures (two shapes); the adapter's knob selection tested; the live
  network call is **not** exercised in CI.
- Wired into `.gitlab-ci.yml` next to the Phase-4 knowledge-graph tests.

---

## 9. Non-goals (YAGNI)

- No write-back to JIRA (read-only export).
- No incremental/delta sync in v1 — full re-export each run (idempotent, so cheap in git
  terms); a `updated >= last-run` optimization is a documented later step.
- No webhook / real-time listener.
- No attachment, comment, or worklog import.
- No hosted-DB or vector store — the ledger is the source of record, the graph is derived.
- No secret storage in the repo or any new secret manager.

---

## 10. Deliverables

1. `scripts/jira/export_jira.py` + deployment adapter (Cloud / DC).
2. `docs/product/jira/config.json` (sample) and `docs/product/jira/issues.csv` (seed
   ledger with `PROJ-1`).
3. `docs/product/jira/README.md` (how to configure, run, and the MCP shortcut).
4. `scripts/knowledge/ingest_issues.py` + one `issues` entry in `graph-manifest.json`.
5. `normalize_ref()` JIRA-key branch + commit→issue linker.
6. Tests for all of the above; CI wiring.
7. Schema/docs update: add the `issue` node and its edges to
   `docs/knowledge/schema.md`.
