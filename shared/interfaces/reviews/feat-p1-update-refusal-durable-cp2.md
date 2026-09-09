# Checkpoint review — U5b round 2: the three the independent review rejected on

Branch `feat/p1-update-refusal-durable`, PR #381. Round-1 head `def54478`,
reviewed and **REJECTED** on one blocking defect and two must-fixes, plus four
notes. This checkpoint is the fix pass. Every sensor below was made RED against
**the round-1 PR bytes** — not against master, which is the wrong baseline for a
defect the PR itself introduced — and the failure text is recorded with it.

## 1. BLOCKING — the refusal was sticky globally, not per bundle sha (A5.15)

`refusalToShow` returned early on `phase === 'refused'`, in front of its own
sha-scope and busy filters. Nothing moves that phase except a later apply, so
after ONE constitutional refusal the card showed that refusal's headline and
files over **every** bundle published afterwards and withdrew Apply with them —
and Apply is the only no-terminal way to take the update that would have
cleared the phase. The door this whole unit exists to open, bricked by the
record of one refusal. It was not hypothetical: the install measured on
2026-09-08 is sitting in exactly that state, and the next step of the program
is the Captain's ceremony followed by a new bundle.

`run_briefing._update_refusal_line` got the sha half right and the `busy` half
wrong in the same way — it filtered `busy` only once the phase had moved on,
which is never, for the whole window after a refusal. So the two surfaces the
unit's own comments say cannot disagree, disagreed.

**Fixed** in both, as the same three rules written twice on purpose:

- nothing waiting → the refusal is the last thing that happened, and it speaks;
- something waiting → it speaks only for the same sha, and only when it is a
  verdict on those bytes (`busy` is timing, never a verdict);
- an apply in flight outranks both.

The runbook now states the rule and names both readers.

**CORRECTION, 2026-09-09 (round 3).** The third bullet was TRUE OF THE CARD AND
FALSE OF THE BRIEFING when this checkpoint was written, and the round-2
independent review proved it: `refusalToShow` opened with `phase === 'applying'
-> null`; `_update_refusal_line` had no `applying` guard at all, and
`_update_notice`'s own `applying` arm sat after the waiting-bundle arm, which a
waiting bundle makes unreachable. So on the retry this card is deliberately
built for — it keeps Apply for a digest-mismatch, unreadable or busy refusal —
the card said "Taking an update to bbbbbbbb" while the briefing said "Update
refused", and with a locked-path refusal on record, "needs the Captain" over a
running apply. An interrupted apply leaves `phase: applying` on disk by design,
so the wrong sentence was durable with it. Closed in cp3: the guard is in
`_update_refusal_line`, the `applying` arm is hoisted ahead of the waiting one,
and the claim is no longer a claim — the six states are one checked-in fixture
driven through BOTH readers. Recorded here rather than rewritten, because the
lesson is that a parity claim written on the strength of "I wrote the same
three rules on both sides" is an assertion, not a measurement.

## 2. MUST-FIX — a busy refusal could revert a concurrent apply's state

`record_refusal` and `record_event → update_state` did an unlocked
read-modify-write of `state.json`, and `refuse_busy` runs *by definition* while
the updater it lost to holds `.updates/.lock` and writes that same file. The
`phase != "applying"` guard was check-then-act. Driven interleaving: winner
`{applying, snapshot}` → loser reads → winner `{applied}` → loser writes its
stale copy back → `{phase: applying, snapshot: …, last_refusal: busy}`, which
the next apply or rollback restores from, undoing an apply that succeeded.

**Fixed** with `.updates/.state.lock` — a lock of its own, because the caller
that needs it most is the one that could not take the updater lock; a refusal
that had to hold `.updates/.lock` to write itself down could never be written
at all. `write_state`, `update_state` and `record_refusal` (guard included) all
run their read-modify-write under it. Bounded and fail-open: 15 s, then it
proceeds unlocked, because a state file that never got written is how an
interrupted apply becomes unrecoverable.

## 3. MUST-FIX — a real ledger fault read as benign version skew

The widened `except Exception` is right — nothing may cost the record — but
`why` was computed and dropped, and all four surfaces said the same reassuring
thing about a full disk that they said about an emitter one version behind:
"the ledger does not know the event kind yet, and the next update files it". No
update files a full disk.

**Fixed** with one classifier, `_is_version_skew` — an unknown-type
`ValueError` or an `ImportError`, and nothing else — feeding `ledger_error` in
`state.json`. The log line, `status`, `status --json` and the card all read
that one field, so no surface can classify it differently, and the `why`
travels on every held record including the skew ones. The field is a fact about
the last attempt, not a sticky alarm: a ledger that starts working clears it.

## 4. Notes taken (N1, N2, N3), and the one recorded as-is

- **N1 — the ingest window.** The replay drained `events.jsonl` in place and
  renamed it at the end, so a record held *during* the drain was retired
  unreplayed into a file nothing reads again. The batch is now renamed to
  `events.draining-<ts>-<pid>.jsonl` **before** a row is read; a concurrent
  hold opens a fresh sidecar, and a drain that could not finish keeps that name
  for the next ingest instead of being stranded. `event_fallback` is now
  measured after the drain rather than set to `false`.
- **N2 — exactly-once.** Chosen, not glossed: the marker stays **after** the
  emit, so this is at-least-once at the crash boundary. Marking first would
  turn the same crash into a record that never reaches the ledger and can no
  longer be found, and no record being lost is the one guarantee this path
  makes. A duplicate is visible and deduplicable by `deferred_record_id`; a
  hole is neither. Stated in the module docstring, the section comment and the
  runbook.
- **N3 — the drill.** P7's refusal leg asserted only the ledger delta. It now
  also reads `state.json` and requires `phase: refused`, `last_refusal.bundle`
  equal to the bundle it just published, and a non-empty `paths` — so the
  acceptance drill can see A5.15 regress. The arm was checked against four
  wrong states (idle phase, other bundle, empty paths, absent file) and only
  the real one passes.
- **N5** (the briefing gives counts, never paths) stays deliberate and
  documented. **N6** (CI has executed no steps on any recent run of this repo,
  on master or on any phase-1 branch) is infrastructure, not this PR.

## 5. N4 — the vacuous arms, corrected

The reviewer measured four arms passing unchanged on master bytes where cp1
claimed one. Re-measured here (master sources swapped under the PR's tests):
the four are the briefing's
`test_a_refusal_of_some_other_bundle_never_silences_the_waiting_one`, and in
`updates.test.ts` `a refusal of some OTHER bundle …`, `busy is about timing …`
and `an apply in flight still leads`. cp1 has been corrected in place.

The middle two were the ones that would have caught §1, and they were written
on `phase: 'applied'` — the branch that already worked. They are now
parametrised over `['applied', 'refused']`; the `refused` half was RED on the
round-1 bytes.

One round-1 card arm was **re-aimed rather than kept**: `keeps Apply when the
refusal was timing rather than content` demanded the words "Update refused"
over a bundle whose only refusal was `busy`. That is the same defect as §1 one
surface further along — the retry that is the right thing to do about `busy` is
exactly what the card was talking the operator out of — so it now asserts the
opposite, and is RED on the round-1 bytes.

## Sensors — RED on the round-1 PR bytes, GREEN after

| Arm | RED rc | RED reason | GREEN rc |
|---|---|---|---|
| `updates.test.ts` · other-bundle refusal (phase `refused`) | 1 | `expected 'Update refused — 1 constitutional file differs; needs the Captain (eeeeeeee)' to be 'Update ready — 12 files changed (bbbbbbbb)'` | 0 |
| `updates.test.ts` · busy does not stick (phase `refused`) | 1 | `expected 'Update refused — busy (bbbbbbbb)' to be 'Update ready — 12 files changed (bbbbbbbb)'` | 0 |
| `updates.test.ts` · `refusalToShow` null for a bundle it is not about | 1 | `expected { …(5) } to be null` (returned the `ffff…` refusal) | 0 |
| `update-card.test.tsx` · a busy refusal neither withdraws Apply nor speaks | 1 | `expected html not to contain 'Update refused'` — headline was `Update refused — busy (bbbbbbbb)` | 0 |
| `update-card.test.tsx` · offers the NEXT bundle while phase says refused | 1 | `expected html to contain 'Update ready — 7 files changed (ffffffff)'`; got the old refusal's headline and files, no Apply | 0 |
| `test_card_update_notice.py` · busy refusal of the waiting bundle | 1 | `'Update refused — busy (bbbbbbbb)'.startswith('An update is ready to take')` | 0 |
| `test_cabinet_update.py` · loser's write cannot revert the winner's `[record_refusal]` | 1 | `the loser wrote its stale copy back over the winner: {…'phase': 'applying', 'snapshot': '20260908T195800Z-aaaaaaaa'…}` | 0 |
| … same, `[record_event]` | 1 | same, with `event_fallback` merged onto the stale document | 0 |
| `test_cabinet_update.py` · a broken ledger is named as a fault | 1 | `assert 'No space left on device' in ((None or ''))` — `state.json` carried no discriminator | 0 |
| `test_cabinet_update.py` · version skew is still version skew | 1 | `assert 'Unknown event type' in "…does not know the event kind yet; the next update replays it"` — the `why` was dropped | 0 |
| `test_cabinet_update.py` · a working ledger clears the fault | 1 | `assert 'No space left on device' in ((None or ''))` | 0 |
| `test_cabinet_update.py` · a record appended during the ingest | 1 | `the mid-ingest record was swept into the retired file, unreplayed — assert [] == ['held-late']` | 0 |
| `test_card_update_notice.py` · a ledger fault is named | 1 | `assert 'ledger fault' in 'An update is ready to take (bbbbbbbb, 3 files) — open the home page and tap Apply'` | 0 |
| drill P7 · `state.json` refusal assertion | — | checked against four wrong states, each rejected with its own sentence; only the real one prints `ok` | 0 |

Two arms are guards rather than sensors and are labelled as such, not counted
above: `test_a_held_record_with_no_fault_does_not_raise_an_alarm` and the card's
benign-sentence half — they exist so the §3 fix cannot become a blanket
relabel.

## Budget

`framework_production_noncomment_lines` 66660 → 66667 (+7 measured, effective
81398 → 81405), raised with a dated paragraph in the row: four lines are the
ledger-fault arm, two are `_update_state` (one reader for the state file where
there were three parse sites), one is the `busy` filter's second clause. Census
printed verdict: PASS, `observed == maximum`.

## Not touched

No locked path. No new event type. No change to the health gate, the updater
lock, the re-exec, the preserve set, the deletion set or the snapshot/restore
path. The state lock is a new file under `.updates/` and is never content.
