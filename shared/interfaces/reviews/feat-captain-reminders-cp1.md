# Checkpoint review — feat/captain-reminders cp1 (FW-019)

**Batch:** integration of the two captain-reminders lanes (tick-live +
captain-arm) onto one clean worktree off origin/master @1cd84459.
**Reviewer:** integrator session (Fable), building on the two lanes' own
completed adversarial reviews — this checkpoint reviews the INTEGRATION
DELTAS, not a re-litigation of the already-reviewed lane content.

## What the batch contains

1. **tick-live lane (applied verbatim, 3way-clean except the tick):**
   `cabinet/services.yml` gains the `due-at-reminder-tick` cron row
   (interval_s 300, ONE command — exec-wrapper chain lesson);
   `cabinet/scripts/due-at-reminder-tick.sh` becomes portable
   (SCRIPT_DIR/CABINET_ROOT resolution, `cabinet/.env` sourcing for direct
   runs, Mac-native Redis defaults, loud no-conn degrade, quiet-tick
   heartbeat); new `cabinet/scripts/tests/test_due_at_reminder_tick.py`.
   Root finding: Spec 041's worker was SCHEDULED NOWHERE and sourced
   lib/triggers.sh from a dead convergence-era /opt path — trigger_send
   undefined, every fire a silent dead limb.
2. **captain-arm lane (applied verbatim, 3way-clean except the tick):**
   new `cabinet/scripts/captain-reminder-arm.py` (parse-when / owner-slug /
   file-card / reconcile), new `cabinet/scripts/remind-captain.sh` (create
   path), `cabinet/sql/042-tasks-reminder-kind.sql` (+ registration in
   load-preset.sh and cabinet-bootstrap.sh apply lists after 039),
   `framework/env.py captain_slug()` + tests, tick routing (captain rows →
   needs-ledger one-tap card; officer rows → unchanged 041 trigger),
   reconcile phase, P2 fix (claim RETURNING = machine fields only; title
   re-read by id), runbook `docs/runbooks/captain-reminders.md`, cos.md
   Chair instruction.

## Integration deltas reviewed (the new material in this checkpoint)

* **Merged tick** (`cabinet/scripts/due-at-reminder-tick.sh`): verified by
  double-diff against BOTH lanes' final copies — the merge is exactly the
  union; no functional hunk from either lane dropped. Two deliberate
  integration decisions, both documented in-file:
  - triggers lib sourced SCRIPT-relative (`$SCRIPT_DIR/lib/triggers.sh`)
    rather than tick-live's `$CABINET_ROOT/...` form: a CABINET_ROOT
    override is the test harnesses' RUNTIME-root isolation lever (tmp needs
    ledger, tmp instance config); code must stay beside code or the
    captain-arm e2e (which overrides CABINET_ROOT to a tmp root and runs
    the shipped tick) would lose trigger_send — the exact dead-limb failure
    mode this batch fixes. tick-live's structural pin updated to match.
  - the quiet-tick early-exit is gone: the reconcile phase must run EVERY
    tick, so the heartbeat is now the single unconditional summary line
    (`fired= carded= snooze_bumped= fail= elapsed_at=`); the watchdog
    freshness-floor rationale comment moved with it. tick-live's heartbeat
    assertion updated from the `(no due reminders)` wording to the merged
    line; services.yml `expected` updated to the real format.
* **tick-live psql stub upgraded** to the merged claim shape: required-guard
  list now pins `returning id, officer_slug, due_at, type` (the P2
  machine-fields-only stream); rows emit 4 fields; no-`-c` calls (the by-id
  title re-read and the snooze bump, which bind `:'var'` and therefore
  arrive on STDIN) are dispatched on the STDIN body — the injection test's
  title now flows through the same re-read path the live tick uses.
* **Prose honesty edits:** services.yml notes/expected now describe the
  captain-card routing + reconcile; the runbook's "tick is scheduled"
  prerequisite now points at the services.yml row + generate-plists +
  deploy path instead of the deleted crontab suggestion (all referenced
  paths tracked — docs sweep green).
* **Ledger:** CAPTAIN-REMINDERS-1 appended (done, 2026-07-16) + plan-doc
  §37 parity row; A13 gate, ledger-status-parity.sh and id-uniqueness all
  exit 0 on the edited pair.

## Risks checked

* schg guard: `ls -lO` on every touched path + parent dirs on the live box —
  no immutable flags anywhere in this batch's surface; nothing dropped.
* No live-fleet mutation: plists rendered to a scratch dir for verification
  only; no launchctl, no install (rides deploy-mac.sh / bootstrap).
* Secrets discipline: `.env` values sourced, never echoed; conn strings
  env-only; untrusted titles transit STDIN/psql -v binds/jq --arg only.
* Semantic-conflict sweep: the only cross-lane semantic coupling found was
  the tick-live stub/assertions vs the captain-arm claim shape — resolved
  above and proven by the merged tree's green runs.

## Evidence

* `python3.12 -m pytest cabinet/scripts/tests/test_due_at_reminder_tick.py -q` — 7 passed
* `python3.12 -m pytest cabinet/scripts/tests/test_captain_reminder_arm.py -q` — 56 passed
  (includes the live ephemeral-Postgres class: claim predicate, bump guard,
  REAL 041 re-arm, no-forgery RETURNING, each with a mutate-the-SQL negative
  control, plus the e2e of the SHIPPED merged tick filing a real-title card)
* `python3.12 -m pytest framework/tests/test_env.py -q` — 77 passed
* `python3.12 -m pytest cabinet/scripts/tests -q` — 1123 passed, 4 skipped
  (the pre-existing environment skips only)
* `bash -n` clean on all four touched .sh
* generate-plists render: `com.cabinet.due-at-reminder-tick.plist` lint OK,
  StartInterval 300, wrapper ends in the single exec'd command
* docs-track-code-sweep GREEN (files=40 findings=0);
  check-layer-separation new=0; A13 parity 317 ids; LEDGER_STATUS GREEN.

**Verdict:** integration deltas sound; batch cleared for commit.
