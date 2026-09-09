# Checkpoint review — U5b round 3: the one the round-2 review rejected on

Branch `feat/p1-update-refusal-durable`, PR #381. Round-2 head `7ba026148e15…`,
reviewed independently and **REJECTED** on exactly one thing, with all three
round-1 gaps and all four notes re-proved closed. This checkpoint is that one
fix. The sensor was made RED against **the round-2 PR bytes** — the baseline for
a defect the PR itself carried — and the failure text is recorded with it.

## The defect: a claim written on both sides and true on one

`lib/updates.refusalToShow` opens with `if (!status || status.phase ===
'applying') return null`. `run_briefing._update_refusal_line` had **no
`applying` guard at all**, and `_update_notice`'s own `applying` arm sat AFTER
the waiting-bundle arm, which a waiting bundle makes unreachable. So the two
surfaces the unit's own comments say cannot disagree, disagreed — on the third
of the three rules, and in the one place the Captain reads every day.

One state file, both readers, as the review drove it:

```
state.json = {phase: 'applying', to_sha: bbbb…, snapshot: '20260908T1-aaaa',
              last_refusal: {bundle: bbbb…, reason: 'failed per-file digest
                             verification', paths: []}}
inbox      = bbbb… (still waiting — the entry is not removed until the apply lands)

card     updateHeadline  >>> "Taking an update to bbbbbbbb — this page restarts…"
         refusalToShow   >>> null
briefing _update_notice  >>> "Update refused — failed per-file digest verification (bbbbbbbb)"

and with a locked-path refusal on record:
briefing _update_notice  >>> "Update refused — 1 constitutional file differs;
                              needs the Captain (bbbbbbbb)"
```

**Reachable through the flow this unit designs for, not through an exotic one.**
The card deliberately KEEPS Apply for a digest-mismatch, unreadable or busy
refusal, because a retry is a reasonable thing to do about all three. Tap it and
`phase` becomes `applying` with that same sha still in `last_refusal` (the state
write carries that field on purpose) and the bundle still in the inbox — so for
the whole of every designed retry the briefing told the Captain the bundle had
been refused while the card said it was being taken. And durable with it: a
killed apply leaves `phase: applying` plus its snapshot on disk **by design**,
because that pair is the only marker saying which snapshot puts the tree back.
Master's sentence in that state ("An update is ready to take") was wrong too,
but it at least routed to the Apply that resumes and restores; this one routes
nowhere.

**Why no arm caught it.** `test_an_apply_in_flight_says_it_is_happening_now` is
pre-existing, has no waiting bundle and no `last_refusal`, so the state it
asserts on cannot reach the code that was wrong. The TS side had `is null while
an apply is in flight`; the briefing side had no counterpart. Each side's
fixtures were authored on that side, so each side proved only itself — which is
the general lesson of this round and is why the fix ships a fixture set that is
neither side's.

## The fix

- `_update_refusal_line` opens with `if state.get("phase") == "applying":
  return ""` — rule 3, finally written where it was claimed to be.
- `_update_notice`'s `applying` arm is hoisted ahead of the waiting-bundle arm,
  so "An update is being taken right now" is reachable at all. It sat last,
  i.e. after the arm that fires whenever anything is in the inbox — and an apply
  is running BECAUSE something is in the inbox, so the only situation that
  sentence describes was the only one it could not be reached in. It stays
  BELOW the ledger-fault arm: this is a one-line surface and the fault is the
  sentence nobody goes back to look at, while the card has room to show the
  fault beside whatever its headline says.
- The `state = _update_state(base)` read is hoisted with it; the second read
  lower down is gone. No behaviour rides on that, it is one document read
  instead of two.

## The claim, which was the actual defect

Three places asserted parity that had never been measured: `updates.ts`, the
round-2 commit message, and cp2 §1. cp2 §1 now carries a dated **CORRECTION**
naming what was false and why. `updates.ts` and the runbook now say what is
true and point at the thing that checks it:

**`framework/frontdoor/tests/update_surface_parity.json`** — six states, one
file, driven through BOTH readers. `test_card_update_notice.py::
test_the_briefing_says_what_the_card_says_on_every_shared_state` drives them
through `_update_notice` + `_update_refusal_line`; `updates.test.ts >
surface parity with the briefing line` drives the same six through
`updateHeadline` + `refusalToShow`, deriving its status object from those same
fields exactly as `cabinet-update.sh status --json` derives its report. The six:
idle+waiting · refused-same-sha-locked · refused-same-sha-busy ·
refused-other-sha · applying+waiting+refusal-on-record · applied.

What is asserted is the KIND each sentence classifies to (the wording differs on
purpose — a card headline is not a briefing line), that no sentence names a
bundle other than the one the case is about, and any wording the two genuinely
share. Both classifiers are total: an unrecognised sentence is `unclassified`
and fails naming itself. Both sides also pin the sub-surface that is not the
headline — `refusalToShow` non-null exactly when `_update_refusal_line` speaks —
because that is what withdraws Apply and names the files. A missing fixture file
FAILS on both sides: parity that cannot be verified is drift, not a skip.

## Sensors — RED then GREEN

Method: the new tests kept, `framework/frontdoor/run_briefing.py` swapped back to
`7ba02614`, `__pycache__` purged, `PYTHONDONTWRITEBYTECODE=1`.

| arm | rc on 7ba02614 | failure text |
|---|---|---|
| `test_an_apply_in_flight_outranks_the_refusal_of_the_bundle_it_is_taking` | 1 | `AssertionError: Update refused — failed per-file digest verification (bbbbbbbb)` |
| `test_an_apply_in_flight_outranks_even_a_constitutional_refusal_on_record` | 1 | `AssertionError: Update refused — 1 constitutional file differs; needs the Captain (bbbbbbbb)` |
| `test_the_apply_in_flight_sentence_is_reachable_with_a_bundle_in_the_inbox` | 1 | `assert 'An update is…and tap Apply' == 'An update is…ken right now'` |
| `test_the_briefing_says_what_the_card_says_on_every_shared_state` | 1 | `('applying, the same bundle still waiting, its refusal still on record', 'Update refused — failed per-file digest verification (bbbbbbbb)')` / `assert 'refusal' == 'apply-in-flight'` |

`4 failed, 28 passed` on the PR bytes; **32 passed, rc 0** on the fix.

**The vitest half is GREEN in both directions on this tree, and is labelled as
such** — the card was already right, so a parity arm on it cannot be red for the
defect. It is not vacuous, and that was measured rather than argued: deleting
`status.phase === 'applying'` from `refusalToShow` in the working tree turns it
RED (`expected [ …(2) ] to deeply equal [ …(2) ] — false / true` on the
applying case, plus the pre-existing `is null while an apply is in flight`),
proving it is wired to the live artifact. Its standing job is the direction this
round's defect came from: the two suites now move together or one of them goes
red.

`test_a_refusal_still_speaks_once_the_apply_is_no_longer_in_flight` and
`test_the_parity_fixture_carries_every_state_the_two_surfaces_argue_about` are
also green in both directions, deliberately: the first makes the guard a
RANKING rather than a mute button, the second stops a fixture set quietly
shrinking and taking both suites with it. Declared, not counted as sensors.

## Budget

`framework_production_noncomment_lines` 81405 → 81407 (**+2**, measured with
`cognitive-architecture-census.py` on both trees this session); the yml maximum
moves `66667 → 66669` = +2, with a dated paragraph naming the mass. The mass is
the guard, exactly. Hoisting the `applying` arm is a MOVE and costs nothing; the
parity fixture and the arms are test files, outside the budget by construction.
`framework_production_modules` unchanged at 253. Census **prints** `cognitive
architecture census: PASS`, `81407 <= 81407` — read, not inferred from its exit
code, which is 0 on BLOCK.

## Notes carried, not actioned

N1 (a `_state_lock` that proceeds unlocked after 15 s is invisible), N2 (the
shell break-glass `write_state`) and the `owner: 'nate'` dashboard test fixture
are the round-2 reviewer's notes and were explicitly marked as needing no code.
N4 stands and is the Captain's: **CI has executed zero steps on this head** —
every job fails in ~3 s with "the job was not started because your account is
locked due to a billing issue", identically on `master`. This PR is therefore
not CI-verified; the battery in the PR comment is the whole of the evidence.
