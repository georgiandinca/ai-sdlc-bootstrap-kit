# Governance

Project governance artefacts (pillar 3) that aren't ADRs: the RACI / decision-rights map, rollout plans, working-agreement sign-offs, and any internal rules specific to this project.

| Artefact | What it is | Status |
|---|---|---|
| RACI / decision rights | Who is Responsible / Accountable / Consulted / Informed per decision type. The seat playbooks (`.claude/skills/playbook-*`) carry per-seat cheat sheets; a consolidated matrix can live here. | _(add when needed)_ |
| Rollout plan | How this project is introduced to the team / stakeholders. | _(add when needed)_ |
| Working-agreement sign-off | Record of the seats that ratified `WORKING-AGREEMENT.md`. | _(add when needed)_ |

The canonical rules live in [`../../AGENTS.md`](../../AGENTS.md) and [`../../WORKING-AGREEMENT.md`](../../WORKING-AGREEMENT.md); this folder holds the supporting, project-specific governance documents. Each carries the frontmatter contract (`AGENTS.md` §4.2).

## Paying down the frontmatter baseline

When the kit is installed into an existing repo (`bootstrap.sh --merge`), docs written before the frontmatter contract existed are recorded once in `.ai-sdlc/frontmatter-baseline.txt`, next to the kit manifest. `scripts/validate-frontmatter.py` reports those files as `debt` instead of failing, so the gate is green on day one. Every doc that is not in the baseline must comply. Files that git ignores, such as session transcripts, are not checked.

The baseline only shrinks. To pay it down:

1. Pick a file from the baseline and add the frontmatter block (`AGENTS.md` §4.2). Set `ai-trust` honestly; an old doc nobody has reviewed is `exploratory` or `working`, not `authoritative`.
2. Run `python3 scripts/validate-frontmatter.py`. It lists the file under "remove from baseline".
3. Run `python3 scripts/validate-frontmatter.py --write-baseline`. It drops fixed and deleted files and never adds a new violation. Commit the shorter baseline with the fix.

The baseline lists paths, so renaming or moving a baselined doc (`git mv`) turns the new path into a new violation; add the frontmatter as part of the move, or delete the baseline and re-adopt deliberately. A doc that should not be governed belongs in `docs/drafts/` or `docs/received/`, not in the baseline. To adopt a further batch of inherited docs, for example after merging another repo in, delete the baseline file and run `--write-baseline` again; review that diff like any other change to a gate. `--no-baseline` shows the full debt.

## The context budget

Every session loads `AGENTS.md`, `CLAUDE.md`, the `.claude/rules/` files and the description of every skill in `.claude/skills/`. `scripts/check-context-budget.py` measures that text in characters and checks it against `scripts/context-budget.json`; pre-commit and CI run it. Each skill description is capped at `description_max` (500), which `scripts/validate-skills.py` enforces too.

- **Over a limit:** the check fails and says how many characters to cut. Cut first. Raise a limit only together with the text that needs it, and say why in the CHANGELOG.
- **Slack limit:** a limit more than `warn_slack_pct` (15%) above the real size warns and says what to lower it to, so freed space is not quietly refilled.
- **Resizing:** `python3 scripts/check-context-budget.py --write-limits` sets every limit to today's size plus `headroom_pct` (6%) and marks the file `"sized_for": "project"`. It never raises `description_max`. Review that diff like any other change to a gate.
- **First sizing:** the file ships with the kit's starting limits (`"sized_for": "kit"`), which fit an unfilled `AGENTS.md`. Once the placeholders are filled in, run `--write-limits` once and commit the result. Until then an overflow still fails, and the message says so.
- **Where warnings show:** pre-commit hides the output of hooks that pass, so the slack warnings are in practice seen only in the CI log, or when you run the script yourself.
