# Security Policy

## Reporting a Vulnerability

Please **do not report security vulnerabilities through public GitHub issues.**

Instead, report them privately using one of these channels:

- **GitHub Security Advisories** — use the
  ["Report a vulnerability"](https://github.com/georgiandinca/ai-sdlc-bootstrap-kit/security/advisories/new)
  button on the repository's Security tab (preferred).
- **Email** — send details to **geo@magnify.ro**.

Please include:

- A description of the issue and its potential impact
- Steps to reproduce (proof-of-concept if possible)
- Any suggested remediation

You can expect an acknowledgement within a few business days. We ask that you
give us a reasonable window to investigate and release a fix before any public
disclosure.

## Scope

This is a bootstrap **template kit**, not a hosted service. The most relevant
security concerns are:

- Accidental inclusion of secrets, tokens, or real personal data in the
  template or its sample data.
- Scripts or CI steps that could execute untrusted input.

Auth to external systems (JIRA, AI providers) is **environment-variable only** —
no credentials are ever stored in the repository. If you find committed secrets
or a pattern that encourages storing them in-tree, please report it.
