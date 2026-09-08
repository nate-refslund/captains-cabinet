# Checkpoint review — U5b, the update-path tail (A5.15 + A5.16)

Reviewed-Scope-Digest: a4ba9aa955aa448e055d43b0b12401346c14c0a2afabebad3e108c724557bb53

Branch `feat/p1-update-refusal-durable`, one commit, 12 paths. Base: master
113b52c4. Contract of record: `phase1-contracts-v2-2026-09-07` §5 and its
amendments; this unit is round 4 (A5.15, A5.16, the U5b paragraph). Motivating
evidence: the first apply on the installed Cabinet, 2026-09-08.

## What was measured, and what it cost

The bundle cut at 113b52c4 was published into the real install's inbox and
applied. It refused, correctly, on one differing constitutional path, and left
**nothing any surface could read**: `status --json` answered `phase: idle,
last: null`, so the home card would have gone on offering "Update ready" for
that bundle for ever, behind an Apply button that fails identically every time.
The one record on the box was a line in `.updates/update.log`.

The receipt that should have been the second channel did not exist either: the
INSTALLED emitter predated the update path and raised `ValueError: Unknown
event type: cabinet_update_refused`. That is not a property of one box. The
emitter that knows `cabinet_update_applied` **arrives with the update that
event announces**, so the first apply on any install cut before this leg
existed is unannounced by construction.

Two independent channels, silent on the same event, and nothing in the fixture
suite could see either — both defects live in the gap between the fixture
install (which symlinks the repo's current emitter) and a real one.

## The change

| Where | What |
|---|---|
| `lib/update_bundle.py` | the state writer (`write_state` carries `last_refusal` forward), `record_event`, `record_refusal`, `ingest_deferred_events`, and four CLI subcommands |
| `cabinet-update.sh` | every event routed through the recorder; `refuse` and `refuse_busy` write the durable refusal; `status --json` gains `last_refusal` + `event_fallback`; `apply` replays held records after the new tree lands |
| `dashboard/src/lib/updates.ts` | `UpdateRefusal`, `refusalToShow`, `refusalHeadline`; the refusal outranks the waiting bundle in `updateHeadline` |
| `components/updates/update-card.tsx` | names the files, withdraws Apply for a constitutional refusal, says when a record is held |
| `framework/frontdoor/run_briefing.py` | `_update_refusal_line`, read ahead of the waiting-bundle arm |
| docs | the runbook's refusal + held-record sections; the event-expansion proposal's "a refusal writes no state file at all" claim corrected |

## The three judgment calls a reviewer should attack

1. **A busy refusal never takes `phase` from an interrupted apply.** `phase:
   applying` + a snapshot name is the only marker saying a tree is half-written
   and which snapshot puts it back. A durable refusal that stamped over it
   would eat a durability feature to add one. The refusal is still recorded, in
   `last_refusal`. Arm: `test_a_busy_refusal_is_recorded_and_never_erases_an_
   interrupted_apply`, which also proves the resume still completes.
2. **`busy` does not stick to a bundle.** It is a fact about timing, not about
   those bytes, so once the phase has moved on the card offers the bundle
   normally again. Arms on both surfaces.
3. **The replay runs BEFORE the health gate.** A rollback undoes the bytes and
   must not also undo the record that they were there.

## Sensors — RED before, GREEN after

25 arms, all RED on this branch's base (recorded verbatim in the PR body); 10
in `test_cabinet_update.py`, 11 in the two dashboard suites, 4 in
`test_card_update_notice.py`. One of them is the inverted arm
(`test_without_the_refusal_record_the_status_is_silent`): a mutated updater
with the record call stripped puts `status --json` back to `phase: idle,
last_refusal: null` — the measured defect, reproduced on demand, so the other
arms are known to fail when the property is absent. A 26th arm
(`test_a_refusal_of_some_other_bundle_never_silences_the_waiting_one`) passes
in both directions by design: it is a guard against over-reach, not a new
property, and is labelled as such rather than counted as a sensor.

**CORRECTED 2026-09-09 (independent review, round 1 → cp2).** That count was
wrong in the direction that matters: **four** of the 29 arms pass unchanged on
master bytes, not one. Re-measured here, master sources swapped in under the
PR's tests, the four are
`test_a_refusal_of_some_other_bundle_never_silences_the_waiting_one`
(briefing — the one named above), and in `updates.test.ts`
`a refusal of some OTHER bundle never silences the one that is waiting`,
`busy is about timing, not about the bundle, so it does not stick to it`, and
`an apply in flight still leads — it is the live state`.

The middle two were not guards, they were **sensors aimed away from the
control**: both were written on the `phase: 'applied'` branch, which already
worked, while the property they name was broken on the `phase: 'refused'`
branch — where it bricked the card for every bundle published after a
constitutional refusal. Round 2 re-aims them over both phases (see cp2). An
arm counted as a sensor is an arm nobody re-reads; that is what this
correction is for.

## Budget

`framework_production_noncomment_lines` 66638 → 66660 (+22, measured, effective
81376 → 81398), raised visibly with a dated paragraph in the row. The whole +22
is `_update_refusal_line` plus its three wiring lines and two docstring lines;
every other framework/ line the change adds is a `#` comment. No new modules,
no new event types, no baseline-sets edit (A0.9).

## Not touched

No locked path (`git diff --name-only base..HEAD` ∩ the locked set is empty —
`test_phase1_touches_no_locked_path` and
`test_the_guard_is_not_exempted_on_this_branch` both run over this commit). No
new event type. No change to the health gate, the lock, the re-exec, the
preserve set, the deletion set or the snapshot/restore path.
