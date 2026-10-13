---
title: "Reviewer — review guide (read-on-demand)"
status: draft
owner: Architect
author: AI-SDLC Bootstrap Kit
created: 2026-10-12
classification: internal
last-reviewed: 2026-10-12
ai-trust: working
---

# Reviewer — how a review is run, and what it looks for first

A **read-on-demand** guide (not an auto-invoked skill). Pair it with the invokable [`playbook-reviewer`](../../../../.claude/skills/playbook-reviewer/SKILL.md) role contract. Read "The brief" and "Every change", then the section for each part the change touches.

The lists are not complete, and passing them is not a verdict. They are a starting point: the author of a change adds an item when a review finds a class of defect that the list would have caught, so the next review starts from it. The Architect owns this file.

## The brief

The author of the change writes the brief. A reviewer that is missing one of these asks for it or lists it under "not checked".

- **The change** — the checkout and the commits: committed, with no pull request opened yet.
- **The requirement** — the story and its acceptance criteria, or the decision. For a change with no story, the requirement in the author's words.
- **The author's model**, so the reviewer can be run on one at least as capable (`WORKING-AGREEMENT.md` §5).
- **Where the knowledge graph is** — which checkout holds a graph that includes the code under review, and whether the change exists only in a git worktree.
- **A scratch directory** for copies and experiments. Never the checkout, and never a shared temporary directory.
- **What may not be touched** — for example containers or ports another checkout is using.
- **Not in the brief** — the author's reasoning, test results or conclusions.

## Ground on the knowledge graph first

The graph ties decisions to code and tests. What it holds, what it leaves out and how it is kept current are in [`docs/knowledge/README.md`](../../../knowledge/README.md). Use the `knowledge` MCP server. Where it is not connected, has no `kg_freshness`, or its `kg_trace` takes no `depth`, the same answers come from `python3 scripts/knowledge/ingest.py`. After a build with `--base`, use that command with the same `--base` for every step: the MCP server of the session still answers from its own graph.

1. **`kg_freshness`** (`--freshness`). Read all three parts of the answer: `state`, `changed` and `without_sources`. A graph can be "fresh" and still hold no code, when it was built where the code repositories are not on disk. If the graph is stale, unbuilt or missing the namespaces the change touches, rebuild it, or list it under "not checked".
2. **`kg_trace` with `depth: 1`** (`--trace ADR-0001 --depth 1`) on each ADR or story the change cites. The answer is the code and tests that name the decision. Code that names the decision and that the change should have touched and did not is a finding. Without `depth: 1` a trace of an ADR can return most of the graph.
3. **`kg_federated_query`** (`--query`) for the names the change introduces or removes. It finds definitions and documents, not usages; use `grep` for usages.
4. **Cite** what the graph returned with its file and trust tier. An ADR is quoted from the file, not from memory (`AGENTS.md` §4.2).

The graph finds links that are written down: an `ADR-NNNN` marker, a test named after its code, a markdown link. Code with no marker is not in a trace, so an empty trace is not proof that nothing implements a decision.

A fix commit that changes behaviour gets a review of its own, scoped to the findings it claims to close and to what it may have broken.

## Every change

- **A gate must fail when it should.** For each check the change adds or relies on, build the input that should fail and run it. A check that only matches text (a `grep`, a line-based `awk`, a name-based lint selector) is tried with the same content written another way.
- **Claims are tested, not read.** A README, a pull request description or an ADR that says what a tool does is checked against the tool, at the version the project locks.
- **CI is the reference.** Results are checked on the versions CI uses, not only the local ones.
- **No fabricated facts** (`AGENTS.md` §3): a date, version, identifier or citation with no source is a finding.

## Your code repositories

Add one section per repository or component, naming what a review looks for first there. Keep each item to a rule a reviewer can test. For example:

- **Data access** — every query goes through `<the one package that holds SQL>`; try the routes around the check that enforces it.
- **Dependencies** — the lock file holds only packages from `<the index>` with a hash for each file; an install with a changed hash fails.
- **Secrets** — none in the repository, in logs or in plan output.

## Kit scripts, CI and briefs (this repository)

- **Seats and playbooks are listed in many files.** A change to the seats is checked by a search for the other seat names: the brief, the working agreement, ADR-0000, the seat profiles and their validator and tests, the session scripts, onboarding, `USER.md.example`, the framework document and the folder index.
- **Validators and their tests** — run `scripts/validate-*.py` and `python3 -m unittest discover -s scripts/tests`; check which of them CI runs.
- **Brief churn** — a change to `AGENTS.md` or a rule file is counted by `scripts/check-brief-churn.py` (`.claude/rules/token-economy.md` §2).
- **Session scripts** — a rule written in the working agreement is checked against what `scripts/session/` does.

## Decisions and documents (this repository)

- **ADR claims** — every factual sentence of an ADR or an amendment is verified; limits are stated next to the claim they limit.
- **Decided or proposed** — text does not state as decided what a named seat has not decided.
- **Frontmatter and links** — the frontmatter contract holds and cross-references resolve.
