# JIRA → CSV ledger → knowledge graph

A repeatable, scripted import of JIRA issues into a **git-tracked CSV ledger**
(`issues.csv`), then into the knowledge graph as `issue` nodes — auto-linked to
the commits, code, ADRs, and stories that already reference each key.

## One process, both deployments

`scripts/jira/export_jira.py` supports **JIRA Cloud** and **JIRA Data Center
(on-prem)** behind a deployment adapter. Pick the deployment in `config.json`;
everything downstream (ledger, ingest, linking) is identical.

| Deployment | `config.json` `deployment` | Base URL env | Auth env |
|---|---|---|---|
| Cloud | `cloud` | `JIRA_BASE_URL=https://<site>.atlassian.net` | `JIRA_EMAIL` + `JIRA_API_TOKEN` |
| Data Center | `datacenter` | `JIRA_BASE_URL=https://jira.company.com` | `JIRA_PAT` (preferred) or `JIRA_USER` + `JIRA_PASSWORD` |

Secrets come from the environment only — never commit them. `config.json`
(project, JQL, custom-field ids) is tracked.

## Run

```bash
# 1. configure
$EDITOR docs/product/jira/config.json          # deployment, project, JQL, field ids
export JIRA_BASE_URL=https://acme.atlassian.net
export JIRA_EMAIL=you@acme.com JIRA_API_TOKEN=…  # Cloud; or JIRA_PAT=… for Data Center

# 2. export + rebuild the graph
python3 scripts/jira/export_jira.py --build      # writes issues.csv, then ingest --build
#   (or: python3 scripts/jira/export_jira.py  &&  python3 scripts/knowledge/ingest.py --build)

# 3. trace an issue across docs/code/commits
python3 scripts/knowledge/ingest.py --federated --trace issue:PROJ-1
```

The export is idempotent: an unchanged board produces a byte-identical
`issues.csv` (empty git diff). A failed fetch never overwrites the ledger, so
the graph keeps building from the last committed version.

## Custom-field ids

Sprint, Epic-Link, and Story-Points are custom fields whose ids differ per
instance. Find them at `<base>/rest/api/2/field` (Data Center) or
`/rest/api/3/field` (Cloud) and set them under `fields` in `config.json`.

## Linking

- **issue → issue** (`part-of`) — from the `epic`/`parent` columns.
- **commit → issue** (`references`) — from any JIRA key (`ABC-123`) in a commit
  message; the `commit-msg` hook injects a `Refs: KEY` trailer from the branch
  name when none is present. Requires the Phase-3 commit layer (`dashboard/`) for
  the issue → commit → code chain; without it, issues still link to docs/stories.
- **doc/adr/story → issue** — put the JIRA key in a frontmatter link field
  (`traces:`, `implements:`, `cites:`), e.g. `traces: [PROJ-1]`.

Unresolved keys are reported honestly (`resolved=0`), never invented.

## MCP shortcut (Cloud only, optional)

Cloud teams can let the agent pull issues via the `issue-tracker` MCP instead of
a stored token, then hand the JSON to the exporter:

```bash
python3 scripts/jira/export_jira.py --from-json /path/to/issues.json --build
```

There is no hosted MCP for Data Center — DC uses the REST path above.
