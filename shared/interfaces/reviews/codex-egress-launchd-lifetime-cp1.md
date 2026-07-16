# Fable 5 checkpoint — egress launchd lifetime

**Reviewer:** Claude Fable 5, read-only API review (`--bare`, all tools denied,
staged diff only, hard $5 cap)
**Date:** 2026-07-15
**Verdict:** REQUEST CHANGES

## Confirmed findings

### P1

1. `stop_proxy` reconciles only the mode selected for the current invocation.
   A child started before launchd was available could be orphaned when a later
   `auto` stop chose launchd; the inverse could kill a launchd worker and let
   KeepAlive respawn it. Stop/disable must reconcile both ownership forms.
2. Failed/refused teardown unconditionally deleted PID/ready/env markers. A
   second stop could then claim success despite the suspect process surviving.
   Failure evidence must remain until resolved.
3. The hook diff unintentionally added trailing globs to many unrelated
   germline entries. Restrict this amendment to the exact new plist path.

### P2

1. Validate the Captain-owned CONNECT-port set at the guard boundary and prove
   the backend parser contract.
2. Child-mode command attestation used substring matching and did not explicitly
   require a fixed configured port to equal the ready port. Compare exact argv
   fields and add the port-drift assertion.
3. Invalid launch mode was swallowed in teardown; it must fail loudly.
4. Document the user-GUI launchd domain/exit-code operational constraint.

### P3 / residuals

- Child-mode PID identity check has an unavoidable narrow PID-reuse TOCTOU.
- Avoid second-pass placeholder expansion in template substitution.
- The rendered user LaunchAgent is mutable outside the repository germline;
  runtime attestation detects drift, but pre-attestation login execution remains
  a same-UID residual and must be documented.
- Document nonzero `status` on invalid drift and transient read/apply races.
- KeepAlive can crash-loop on a persistently occupied fixed port; log-file mode
  needs explicit verification.

## Required verification additions

- Cross-mode stop in both directions, second-stop honesty after refused kill,
  absent launchd service, launchd disable, fixed-port drift, and explicit hook
  blocking for the new template.
- Confirm the ready parser accepts `READY <port> PID <pid>` and the backend
  validates CONNECT ports.
- Record the real Mac caller-exit, crash-restart, bootout/bootstrap, and
  no-respawn drill; run germline lockstep and HEAD-based egg export.

This checkpoint does not approve based on passing tests. Re-review is required
after the findings are fixed.

## Resolution submitted for CP2

- Stop/disable now reconcile launchd and exact-argv child ownership in either
  transition direction; refused/unknown stops preserve PID/ready/env evidence
  and a second stop remains nonzero.
- The accidental hook globs were reverted. Only the exact new plist was added,
  with Edit, Write, absolute-path, redirect, `sed -i`, `cp`, and near-neighbour
  regression probes. The hook harness now supplies its own reachable/empty
  Redis stub, so an active host kill switch cannot make BLOCK probes vacuous.
- CONNECT ports are strictly validated/canonicalised at the guard and rejected
  independently by the backend. Fixed-port and CONNECT-policy drift replace
  the owner only through a failed-attestation → stop → start sequence.
- Process checks compare argv fields; the ready marker requires exact
  `READY <port> PID <pid>` form and a fixed port must match Captain config.
- Invalid launch modes and unknown supervisor queries fail loudly. Template
  replacement is one-pass, rendered plist mode is exactly `0600`, and the log
  is a non-symlink user-owned regular file normalised to `0600` before launch.
- The runbook now records GUI-domain/exit-113 behavior, nonzero status and
  transition races, same-UID plist tampering, PID TOCTOU, and fixed-port crash
  loop/log-mode residuals. Real-Mac caller/crash/rebootstrap/no-respawn drills
  are recorded in the amendment; a final post-commit drill remains mandatory.

Verification before CP2: 46 egress tests, 387 germline/amendment tests, 72
Edit/Write hook probes, 96 Bash hook probes, shellcheck/bash syntax, plist
lint, Python compile, and diff whitespace checks are green.
