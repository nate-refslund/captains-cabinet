# Checkpoint review — adopt the orphaned exact-recovery drill rewrite

- Branch: `feat/rollback-drill-exact-adopted`
- Reviewed base: `aa56f43e00ec81ac5e7e653838e2cb5a391c2ba4` (origin/master)
- Source: `~/.codex/worktrees/rollback-drill-exact/captains-cabinet` — 4 dirty,
  never-committed, never-reviewed files copied out (source left untouched).
- Reviewer: Claude Fable 5, independent adversarial review
- Scope: `cabinet/scripts/test-recovery.sh` (137 → 401 lines, full rewrite),
  new hermetic suite `cabinet/scripts/tests/test_recovery_exact.py` (372
  lines), and two runbook updates (`cabinet/docs/mac-mini-deploy-runbook.md`,
  `docs/runbooks/observe-only-dogfood.md`).

## Why this rewrite exists

The prior `test-recovery.sh` was a minimum-count smoke test: it globbed
every `com.cabinet.*` plist for bootout/bootstrap (so a disabled or legacy
plist would get reactivated), accepted "≥5 loaded, Redis up" as PASS, never
checked observe-only/kill-switch/egress/posture, and only `warn`ed on
individual bootout/bootstrap failures instead of failing closed. That is
the "dishonest / misleading" complaint on record for this drill.

## First review — what was checked

Cross-referenced every claim the new script and docs make against the
actual current master-tip implementation of everything it shells out to
(not just read in isolation):

1. **Exact enabled-set reconciliation** — `rows = services.yml manifest +
   lib_roster.officer_service_rows(root)` matches `deploy-mac.sh --all`'s
   own documented contract ("reconcile to EXACTLY roster officers + every
   enabled services.yml row; disabled/legacy agents [pruned]"). Confirmed
   `services.yml` carries no hand-authored `kind: officer` rows (avoids
   double-counting against the synthesized roster rows).
2. **Egress boundary preserved** — `controlled_labels()` excludes
   `com.cabinet.egress-proxy` from the bootout/bootstrap/exact-match
   allowlist unless it is itself an enabled manifest row, matching
   `cabinet-doctor.sh`'s own "egress proxy is separately managed" contract.
3. **Posture + kill-switch attestation** — `capture_observe()` requires
   `observe-only.sh status` = `active`, `instance/config/posture-narrow` =
   `earn_up` (+ sha256 of the raw file), and `kill-switch.sh status` to
   match `^Kill switch: ACTIVE` verbatim — all three string/path contracts
   verified against the real scripts' current output shapes.
4. **Egress attestation** — `capture_egress()`'s `runtime-state` parsing
   (`ENFORCE\tENV_FILE`) matches `egress-guard.sh`'s `cmd_runtime_state`
   exactly; the drift-detection design relies on a textual diff of
   `status` output (not its exit code), which the test suite proves
   correct with a simulated drift case.
5. **Cabinet Doctor semantic diff** — `capture_doctor()` parses
   `CABINET_DOCTOR GREEN (...)` plus a per-line `(OK|WARN|WAIVED|SKIP|DEAD)\t<subject>`
   projection, and requires pre/post to match byte-for-byte — this is the
   "equal aggregate counts can't hide one check flipping while another
   improves" property the docs claim; the test suite has a dedicated case
   proving equal counts with swapped subject classifications still fails.
6. **tmux officer-session naming** — `officer-$OFFICER` in
   `start-officer-mac.sh` matches the `^officer-[A-Za-z0-9._-]+$` pattern
   the drill greps for.
7. **Restore-only-allowlist trap** — the `cleanup()` trap iterates
   `enabled.tsv` only, never a glob, and only bootstraps a label if
   `launchctl print` shows it currently absent.

Mechanical gates run against this worktree: `bash -n` + `shellcheck`
(default severity, 0 findings) on the script; `check-layer-separation.sh`
(new=0); `docs-track-code-sweep.sh` (findings=0); the new hermetic pytest
suite — all subprocess calls (`launchctl`, `tmux`, `redis-cli`, observe,
kill-switch, egress, doctor) point at tmpdir fakes under a fake
`CABINET_ROOT`/`HOME`, so no live Redis, launchd, or tmux state is ever
touched by the tests.

## Confirmed finding

1. **`--help` leaked 3 lines of executable source.** The `-h|--help`
   handler used `sed -n '2,38p' "$0"` to print the header comment, but the
   comment block ends at line 33 (line 34 is blank, lines 35-38 are
   `set -uo pipefail` / `SCRIPT_DIR=...` / `CABINET_ROOT=...`). Running
   `--help` printed those 3 code lines after the intended usage text.
   Verified by direct execution before the fix. This bug pre-dates the
   rewrite (the previous 137-line script had the identical off-by-several
   pattern, `sed -n '1,25p'` against a comment block ending at line 20) —
   not a regression introduced here, but a real, user-visible defect in the
   file being adopted, and squarely the class of bug this repo already
   tests against elsewhere (`test_boot_path_scripts.py`: "`--help` ... never
   leaks code lines").

## Fix applied

- `sed -n '2,38p'` → `sed -n '2,33p'` (matches the actual comment-block
  extent; verified by re-running `--help` — output now ends cleanly at the
  Usage block, no code lines).
- Added a regression test,
  `test_help_prints_only_the_header_comment_and_never_leaks_code`, that
  runs `--help` directly (safe — it exits before any live-system check, so
  no fakes are needed) and asserts none of `set -uo pipefail`,
  `SCRIPT_DIR=`, `CABINET_ROOT=`, `#!/bin/bash` appear in stdout.
- No other defects found. The exact-equality design, the fail-closed
  preconditions, the restore-only-allowlist trap, and the Doctor
  semantic-diff are all sound and independently verified against the
  scripts they depend on and against the hermetic test suite's own
  assertions — not just against their own comments.

## Verification at approval

- `python3.12 -m pytest cabinet/scripts/tests/test_recovery_exact.py -v` —
  15/15 passed (14 original + 1 new regression test).
- `shellcheck cabinet/scripts/test-recovery.sh` — 0 findings (default
  severity).
- `bash -n cabinet/scripts/test-recovery.sh` — syntax OK.
- `bash cabinet/scripts/check-layer-separation.sh` — new=0.
- `bash cabinet/scripts/docs-track-code-sweep.sh` — findings=0.
- Doc diffs (`mac-mini-deploy-runbook.md`, `observe-only-dogfood.md`) read
  against the fixed script's actual behavior — accurate, no stale claims.

The live repository, the live fleet, and Redis were not touched by this
review. The real script was only ever invoked directly for `--help`,
an unknown flag, and an invalid `--timeout` value — all three exit during
argument parsing, before any live-system check. Every exact-recovery
behavior (bootout/bootstrap, egress preservation, posture/kill-switch
attestation, Doctor semantic diff, trap-restore) was proved only through
the hermetic pytest suite against tmpdir fakes, never against the real
fleet.
