---
name: git-verbs
description: Translate plain-language version-control intents into the project's session scripts for operators who don't work in raw git. Invoke whenever the operator says or means "save my work", "get the latest", "send for review", or otherwise wants to commit/pull/share without touching git directly — especially for guided or hidden git-comfort seats (typically Product/PM and some QA). git-native operators use raw git themselves.
metadata:
  status: "approved"
  classification: "internal"
  ai-trust: "working"
  owner: "EM"
---

# git-verbs

Hide git behind intent for operators whose **git-comfort** (in `USER.md`) is `guided` or `hidden`. Map what they *mean* to a session script; never make them think in branches, commits, or PRs. `git-native` operators drive git themselves — do not use the verbs for them.

## The verbs

| The operator says… | Run | What it does |
|---|---|---|
| "get the latest" / "update my copy" | `scripts/session/sync.sh` | fast-forward pull (refuses on a dirty tree) |
| "save my work" / "I'm done with this" | `scripts/session/checkpoint.sh "<short summary>"` | commit + push to a safe personal branch — **no** review requested |
| "send for review" / "share this" | `scripts/session/wrapup.sh "<message>"` | commit + push + open a merge request |

## Rules

- **Never commit to a protected branch.** `checkpoint.sh` and `wrapup.sh` move to a personal branch automatically — trust them.
- `guided`: say what you're doing in one line ("Saving your work — that's a commit and push."). `hidden`: just do it and confirm ("Saved.").
- Prefer `checkpoint.sh` (save) over `wrapup.sh` (review) unless the operator explicitly wants review — opening a merge request is a deliberate act.
- These verbs realise the lifecycle moments in `scripts/session/moments.json` (`checkpoint`, `session-end`).
