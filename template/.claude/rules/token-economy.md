# Token economy

Enforced defaults for AI token spend (design: docs/roadmap token-roi theme).
Each rule has a metric proxy on the dashboard's **Waste signals** tab; a rule
that shows no measurable effect after two sprints is a deletion candidate at
retro (anti-bloat). Techniques 1 (model routing) and 5 (plan-before-code)
live in the seat profiles and playbooks; this file holds the agent-behavior
rules.

## 2 — Prompt-cache hygiene
Keep the briefs byte-stable within a sprint: no mid-session edits to
`AGENTS.md`, `CLAUDE.md`, or rule files. Cache reads cost ~10× less than
fresh input; every brief edit invalidates the prefix cache for everyone.
Batch brief changes and land them between sprints. CI warns when AGENTS.md
churns (scripts/check-brief-churn.py).
*Proxy: cache-hit ratio per seat.*

## 3 — Context hygiene
One ticket per session; `/clear` between tickets. Read the files you need
with targeted ranges instead of dumping whole files or directories into
context. Don't re-read files you already read this session.
*Proxy: tokens-per-session distribution (long tail flagged).*

## 6 — Subagent scoping
Exploration (broad searches, many-file reads, log scans) goes to a scoped
subagent whose raw output never enters the main context — bring back the
conclusion, not the file dumps. Keep the main session for decisions and
edits.
*Proxy: tokens-in per accepted outcome.*

## 7 — Batch / off-peak
Non-interactive jobs (bulk doc generation, triage sweeps, dataset
processing) go through the Batch API at 50% of standard price — see
scripts/spend/README.md.
*Proxy: share of API spend at batch rate.*

## Grounding (pointer)
Answer from the knowledge layer (pillar 5) instead of pasting documents into
the prompt — see `.claude/rules/knowledge-sources.md`.
*Proxy: grounded vs ungrounded cost.*
