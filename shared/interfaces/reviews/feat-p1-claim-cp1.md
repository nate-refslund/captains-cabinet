# Checkpoint review — feat/p1-claim (phase-1 unit 2, the claim)

Reviewed-Scope-Digest: dedc15328131ea879309712c99cad089c5a738869966e98f5b94c41fcccbf268

Reviewer: the build session, on a fresh clone of origin/master @1d1aec53, after
the sensors were red on pre-change bytes and green after. This is an adversarial
pass over the staged diff — what I tried to break, what broke, and what is
knowingly left open. Where I found a defect I fixed it in the same staged bytes
and say so below rather than listing it as a residual.

## What the change is

`framework/missions/claims.py` (new) puts an atomic claim with a lease on the
REAL pull path. `get_next_task` claims by default, renews its own claim on every
tick and returns `None` rather than re-injecting a task it already holds. The
compiler's status overlay holds a node IN_PROGRESS only while its lease runs.
The router stops treating a held task as unassigned. `work-graph-complete.sh`
fences done/failed completions on the claim token and exits 4 instead of
emitting a second completion.

## Attacks run against the diff, and what they found

1. **Two claimers, real processes, one barrier.** 8 subprocesses park on a file
   barrier, then race. One winner, one `work_item_started`. A threads-only test
   would have passed on the GIL and proved nothing about the cross-process
   flock, so the sensor spawns processes and pins `CABINET_EVENT_LOG_DIR` in
   each child — without that pin every child resolves its own ledger and every
   child "wins".
   **Found and fixed while writing it:** the first barrier was a bare counting
   loop that finished before any child had started, so the race never happened.
   It is now a deadline-bounded poll with an assertion that every child parked.

2. **The fence, from the wrong side.** A token from a claim that has since
   EXPIRED is refused (`stale_claim`) even though nobody holds the task now.
   That is the lost-update case, and the naive "refuse only while a claim is
   live" spelling accepts it. The comparison is against the task's LATEST
   claim, liveness deliberately not consulted.

3. **The degenerate ends.** Zero events: `live_claims() == {}`, no crash. A
   started event with no `claim_id` (the locked subagent hook's own shape) is
   invisible to the claim plane and does not fence a completion. A completion
   with no token on a task nobody holds still lands — the compatibility path —
   and carries `claim_id: null` so a later reader can tell it apart.

4. **A stale renewal after a completion.** Replaying `started → completed →
   renewed` put the DONE node back IN_PROGRESS in the first draft of the
   overlay. **Fixed in these bytes:** a renewal now only moves an expiry that a
   started event opened, and the arm is pinned by
   `test_a_stale_renewal_cannot_resurrect_a_completed_node`.

5. **The count the overlay returns.** My first version changed
   `_apply_status_from_events` to a net-change count, which broke two existing
   tests that (correctly) read it as a transition count. **Reverted in these
   bytes**: the historical meaning is kept and the docstring now says what the
   number actually is. Changing an existing sensor's expectation to suit new
   code is the move this review exists to catch.

6. **Empty array under bash 3.2.** `work-graph-complete.sh` builds its optional
   args in an array. A bare `"${CLAIM_ARGS[@]}"` aborts under `set -u` on the
   /bin/bash every mac ships, which would have killed the compatibility path
   (no token, no evidence) on the one machine that matters. Written with the
   `[@]+` guard; `framework/tests/test_bash32_empty_array_ratchet.py` is green.

7. **The holder identity, through the real process shape.** Two sessions of one
   role with `CABINET_WORKER_ID` unset must not share a holder. The sensor runs
   session-shell → hook-shell → python twice and asserts the two derived holders
   DIFFER and exactly one claim exists. Asserting only "one claim" would have
   passed on the broken same-holder case too, since a shared holder returns its
   own claim rather than a second one.
   **Found while writing it:** the first version could not claim at all in the
   children, because `list_roles` is monkeypatched only inside the pytest
   process. The fixture now declares `owner_role`, so the arm measures holder
   derivation rather than a roster lookup.

8. **The 3.9 floor.** The locked hook runs the box's `python3` (3.9.6 on the
   reference machine) and swallows stderr, so a 3.10-only construct on the pull
   path would fail silently in production and green in CI. Two arms: an ast
   grammar check that never skips, and an execution arm on a real 3.9 that
   FAILS (not skips) when the host has none, plus a new CI job that installs 3.9
   and runs the hook's own command.
   **Found while writing it:** the union heuristic flagged `os.O_RDWR |
   os.O_CREAT` as a type union. Fixed, and the checker is now exercised against
   a synthetic offender on every run so it cannot go quietly vacuous.

9. **Layer separation.** The 3.9 fixture originally spelled out
   `instance/config`, which is a framework→instance coupling and reds
   `check-layer-separation.sh`. It now builds the path through
   `session_bridge._outcomes_path`, which also binds the fixture to the live
   resolver instead of a hardcoded layout.

10. **The locked set.** Every changed path checked against FILES and DIRS
    parsed out of `germline-lock.sh` itself: clean. The session hook's call and
    stdout contract are byte-identical, which is what makes the 3.9 floor a real
    constraint rather than a preference.

## Judgement calls, stated because the contract is silent on them

* `claim_id` is a uuid4 minted at the moment of the started event rather than
  the event's own `id`. `emit()` mints its id internally after the payload is
  composed, so literal identity is not available without changing the emitter's
  signature. The load-bearing property — unguessable, not a counter — holds.
* `complete()` accepts `holder=None`. A shell completion cannot derive the same
  session-scoped holder the pull derived, so asserting one would refuse honest
  completions. The token is the credential; a holder, when supplied, is checked
  as well.
* `--status verified` is outside the fence. A verification is another role's act
  and holds no claim; fencing it on the executor's token would refuse exactly
  the separation of duties the script already enforces.
* A tick that holds its own live claim returns `None` and does not take a
  second task. One holder, one task.

## Left open, named rather than covered

* The A2.2 sensor reproduces the hook's process SHAPE; it does not execute the
  locked hook file (schg). The CI job runs the same command under 3.9.
* Dashboard exec strings (`actions/gaps.ts`, `lib/capability-gaps.ts`) still
  call bare `python3`. Out of this unit's scope; they belong to the units that
  own those files.
* The compatibility path (completion with no token when nothing is claimed)
  stays open by contract until every pull carries a claim.

---

## cp2 — re-verification on current master (2026-09-07, later)

Master moved to `97164616` (PRs #367 and #369 landed) after cp1 was written
against `1d1aec53`. The branch was merged forward and the whole proof was re-run
on the new base, not carried over.

**Re-run from scratch on a pristine clone of `97164616`:** the RED probe (the
six pre-change behaviours), the sensor RED pass, the sensor GREEN pass, and the
full battery. The pre-existing failing set was re-measured on that clone
verdict-by-verdict rather than by count.

**One defect found in cp1's own sensors, and fixed here.**
`TestLeasedInProgress::test_renewal_keeps_it_in_progress_past_the_original_expiry`
passed on PRE-CHANGE bytes as well as after. It asserted only that a renewed
node is IN_PROGRESS past its original expiry — which the pre-change overlay
made true of *every* started node, because it never read an expiry at all. A
sensor green in both directions is a disabled sensor, and this one carried
amendment A2.6.

It now starts a second node with an identically expired lease and NO renewal,
and asserts that one is PENDING while the renewed one is IN_PROGRESS. Only an
overlay that reads the renewal's expiry can separate them; the pre-change
overlay holds both IN_PROGRESS. Verified red on master bytes
(`assert <NodeStatus.IN_PROGRESS> is <NodeStatus.PENDING>`), green after.

**One scope over-claim narrowed.** `test_the_script_pins_its_interpreter`
described itself as A0.3 in general while checking one file. Its docstring now
names the two dashboard exec strings it does NOT cover and says they are an open
residual — a checked file must not read as a claim about an unchecked one.

**Method note for the RED pass.** Three sensor modules import
`framework.missions.claims`, so on pristine bytes they abort at collection with
an ImportError, which proves nothing about the invariants they carry. The two
that are invariant-level (`test_session_bridge.py`, `test_compiler.py`) were
therefore run in a second red tree that keeps the new module and reverts ONLY
`session_bridge.py` and `compiler.py` to master bytes: 15 failures, each for the
invariant's own reason rather than for an absent import.
