# Security Policy

## Status: pre-release

Captain's Cabinet is **pre-release**. This repository is private today; the
public artifact is produced by a fresh-cut export (live instance values never
ship in it) and publication is gated on governance approval. There are no
published releases yet.

## Supported versions

None yet. Until a first public release exists, only the tip of `master` is
maintained; no backported security fixes are promised.

| Version | Supported |
|---|---|
| `master` tip (pre-release) | best effort |
| anything else | no |

## Reporting a vulnerability

- **Preferred:** GitHub Security Advisories on this repository — the
  **Security** tab → **Report a vulnerability**. That opens a private thread
  with the maintainers.
- **Fallback:** if the advisory flow is unavailable to you, open a plain issue
  saying only "security report — requesting a private channel" (no details in
  the issue), and a maintainer will arrange one. The contact-placeholder
  pattern used across this repo is `<role>@cabinet.example.com` — a
  `security@cabinet.example.com` mailbox is a placeholder until publication,
  not a live address.

Please keep details private until a fix or a coordinated disclosure date is
agreed. Acknowledgment is best-effort while pre-release — there is no security
team or SLA yet, and it would be dishonest to promise one.

## Scope

Captain's Cabinet is a **self-hosted runtime**: the officer fleet runs as
launchd/tmux sessions on the operator's own Mac. There is no hosted service
and no project-operated cloud endpoint, so classic service-side categories
mostly don't apply. What does apply:

- **Authority-boundary bypasses** — anything letting an officer act above its
  earned autonomy: authority-matrix or hard-ceiling evasion, posture/grant
  forgery, graduation-math manipulation.
- **Germline bypasses** — writing (or laundering a write to) the schg-locked
  enforcer/judge plane without a Captain unlock window
  (`cabinet/scripts/germline-lock.sh`).
- **Hook / gate evasion** — command or tool-call patterns that slip
  consequential actions past the pre-tool-use enforcement, the kill switch, or
  the git hooks.
- **Secret handling** — anything that moves values out of `cabinet/.env` / the
  keychain into tracked files, logs, or outbound surfaces (the rule is: names
  in files, values in env/keychain).
- **Operator dashboard** — designed for local, single-operator use; reports
  that defeat its auth or expose it beyond the operator's machine are in
  scope.

Out of scope: your own instance-layer modifications, and vulnerabilities in
the upstream stack (Claude Code, Homebrew, Redis, macOS) — report those
upstream.

## Good faith

Testing against **your own** deployment is encouraged — the clean-room hatch
and the synthetic Testburg fixtures exist for exactly that. Never test against
someone else's running cabinet without permission.
