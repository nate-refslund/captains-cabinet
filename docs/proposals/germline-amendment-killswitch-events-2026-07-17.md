# Germline amendment — kill-switch flip-event audit trail (2026-07-17)

Prepared per the 2026-07-07 full-autonomy grant (staging only — application
to the schg-locked live file is Captain-ceremony-gated, below). Completes
Wave-1 item (e)'s second half from
`designs/captain-message-effect-2026-07-16.md` §2.3 (the first half — the
golden-eval redis sandbox, so tests can never touch the live switch — landed
@1cd84459).

## Incident / why

The emergency stop's history is not attributable. The Captain armed the kill
switch in the 2026-07-15 pre-flip lockdown; on 2026-07-16 it read INACTIVE.
No record can say which actor cleared it — at the time, every FW-025
pre-push golden-eval run both ARMED and CLEARED the live switch as a side
effect (fixed @1cd84459), and the sanctioned flip surface writes no ledger
row. An emergency control whose flips leave no trace cannot support the
"no arming decision may cite pre-fix telemetry" rule, incident forensics, or
the graduation evidence chain.

## Change (one germline file)

`cabinet/scripts/kill-switch.sh` — on each **verified** flip, emit the
already-registered org event (`framework/events/emitter.py` registry:
`kill_switch_activated` / `kill_switch_deactivated`, aggregate `system`,
ref `killswitch_id`):

- `emit_flip_event()` helper: `python3 framework/events/emitter.py <type>
  ${CABINET_OFFICER:-captain} '{"killswitch_id":"cabinet:killswitch",
  "via":"kill-switch.sh"}' >/dev/null 2>&1 || true`.
- Called ONLY in the verified-activate and verified-deactivate branches.
- Fail-quiet BY DESIGN: the ledger must never block, slow, or fail the
  emergency surface (mirrors on-subagent-stop.sh). An UNVERIFIED flip emits
  nothing — a false "activated" row is worse than none.
- Honest limit: a direct `redis-cli SET/DEL cabinet:killswitch` bypasses
  this by nature. The sanctioned surfaces (this script; the Chair path that
  shells to it) are covered; raw redis writes remain visible only through
  their effects. Officer-side raw writes are separately hook-blocked
  (EVAL-001b pins that `DEL cabinet:killswitch` in officer Bash is refused).

## Tests (land with this change, run pre- and post-ceremony)

`cabinet/scripts/tests/test_kill_switch_events.py` — 7 behavioral/source
tests against the REAL script + a disposable redis + a tmp event ledger:
verified flips emit exactly the two rows (with killswitch_id + actor);
`CABINET_OFFICER` attribution honored; unverified flip emits NOTHING;
a broken event ledger never blocks the flip; `status` never emits; the
event types stay registered; the emit helper stays fail-quiet.

## Ceremony (Captain sudo; ~2 minutes; batches with any other pending sync)

The live inode `/Users/nate/captains-cabinet/cabinet/scripts/kill-switch.sh`
is schg-locked; git-side the change lands on master first (CI-green), then:

1. Pre-check (orchestrator, no sudo): `git -C /Users/nate/captains-cabinet
   fetch origin master`, confirm the target blob:
   `git -C /Users/nate/captains-cabinet diff HEAD origin/master --stat --
   cabinet/scripts/kill-switch.sh` shows only this amendment.
2. Captain: `sudo bash /Users/nate/captains-cabinet/cabinet/scripts/germline-lock.sh unlock`
3. Orchestrator (same window):
   `git -C /Users/nate/captains-cabinet checkout origin/master -- cabinet/scripts/kill-switch.sh`
   then blob-verify:
   `git -C /Users/nate/captains-cabinet hash-object cabinet/scripts/kill-switch.sh`
   equals `git -C /Users/nate/captains-cabinet rev-parse origin/master:cabinet/scripts/kill-switch.sh`.
4. Captain: `sudo bash /Users/nate/captains-cabinet/cabinet/scripts/germline-lock.sh lock`
   then `germline-lock.sh status` + `verify` must pass (same-day relock rule).
5. Live acceptance (orchestrator, no sudo, ~30s): with a DISPOSABLE redis
   (`REDIS_URL=redis://127.0.0.1:<sandbox>`) and a tmp
   `CABINET_EVENT_LOG_DIR`, run the LIVE script `activate` then
   `deactivate`; assert the two rows land and read-back verified both flips.
   (Never against live redis — the live switch state must not change during
   the ceremony.)

## Rollback

Source rollback = revert the amendment commit on master + a new
unlock→checkout→relock ceremony for the same file. No state migration —
the change is emit-only; rows already written are ordinary ledger history
and stay (append-only surface). Operational rollback is not applicable: the
flip semantics (SET/DEL + read-back verification) are byte-unchanged.
