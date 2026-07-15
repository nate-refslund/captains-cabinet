# Fable 5 checkpoint — egress launchd lifetime CP2

**Reviewer:** Claude Fable 5, read-only API review (`--bare`, all tools denied,
complete staged diff, hard $8 cap)
**Date:** 2026-07-15
**Verdict:** APPROVE

## Release-blocking findings

- P0: none.
- P1: none.
- P2: none.

The reviewer verified from the diff—not from claimed test results—that every
CP1 item is fixed: both ownership modes are reconciled; failed-stop markers
survive; hook scope is exact and its Redis fixture prevents vacuous passes;
CONNECT ports are strict at both boundaries; argv and fixed-port attestation
are field-exact; invalid modes fail loudly; GUI/113 behavior and residuals are
documented; template substitution is one-pass; and the germline/egg lists are
lockstep. It found no new fail-open path: the env is published only after full
post-start attestation, while all unknown/tampered states remain nonzero.

## Accepted P3 residuals / notes

1. The final drill must explicitly record green `runtime-state` **after**
   germline relock, because any future ceremony that changed file ownership
   (rather than only flags) would fail template ownership attestation closed.
2. Exit 113 is a documented macOS service-absence assumption; drift fails
   closed.
3. The Bash hook regex over-blocks `.plist.example` neighbours, matching the
   pre-existing gate-apply precedent; Edit/Write scope is exact.
4. A child that remains alive at startup timeout before publishing its PID is
   an availability/orphan residual, never an env-publication fail-open.
5. Marker read→unlink has a narrow restart race; loss fails attestation closed.
6. HOME-unset `/tmp` fallback is guarded by parent ownership/symlink checks.
7. `/usr/bin/false` and inherited `PYTHONPATH` are test-only portability nits.
8. Plist `Umask` decimal 63 equals documented octal 0077; an inline comment is
   suggested for future clarity.
9. Officer execution of the pre-existing `egress-guard.sh stop` is a future
   exec-deny review item; boot re-applies policy, status goes red, and running
   Mac sessions retain Seatbelt.

## Condition of approval

Before the dogfood clock starts, the post-commit real-Mac drill must record:

- strict installed plist, PID, ready, env, and log modes; and
- green `runtime-state` after the repository germline is relocked.

No code changes were requested by CP2.
