# Privacy Policy

This policy covers the AI-SDLC Bootstrap Kit: the `ai-sdlc-bootstrap-kit`
plugin, its `install-ai-sdlc-kit` skill, and the project template it installs.

**In short:** the kit runs on your machine and has no server. It collects
nothing, sends nothing to its author, and contains no telemetry.

## What the plugin reads

- **Your project directory.** The situation check
  (`detect-situation.sh`) reads git state (repository root, `origin` URL,
  branch, whether there are uncommitted changes), whether the kit's manifest
  and `USER.md` exist, and the names of neighbouring folders that are git
  repositories. It writes nothing and makes no network calls. Its report
  stays in your agent session.
- **The kit itself.** Installing clones the public repository
  `github.com/georgiandinca/ai-sdlc-bootstrap-kit`. This is a download. The
  kit sends no data about you or your project.

## What it stores, and where

After the install, the agent follows the installed project's `ONBOARDING.md`.
Onboarding asks for your **full name and email address**, as well as your
communication preferences, role and git experience. It writes them to
`USER.md` at the root of your project.

`USER.md` is listed in the project's `.gitignore`, so it is never committed
and stays on your machine. You can edit or delete it at any time. Deleting it
makes onboarding run again the next time the agent starts.

The installed project can also keep per-user session metrics under
`docs/metrics/sessions/`. That folder is git-ignored too.

## What leaves your machine

The kit sends nothing. Two things outside the kit can send data:

- **Your AI agent** (for example Claude Code, Codex or Antigravity) processes
  your conversation, including anything onboarding asks you. Its provider's
  privacy policy applies.
- **Optional integrations in the installed project.** These include the
  Jira export and the Anthropic usage import. They run only if you configure
  them, and they use credentials you supply. They talk only to the service
  they are named for.

## Retention

The kit has no service, so it retains nothing. Data stays in your project's
files for as long as you keep them.

## Children

The kit is a tool for software teams and is not intended for anyone under 18.

## Contact

Questions about this policy: **geo@magnify.ro**, or open an issue on
[GitHub](https://github.com/georgiandinca/ai-sdlc-bootstrap-kit/issues).

_Last updated: 2026-10-14._
