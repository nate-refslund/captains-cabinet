# U5b checkpoint 6 — A5.17: the current refusal of a bundle

Round 5 REJECTED on one must-fix, and it was a regression this branch
introduced while closing round 4: **the resolver's refusal currency was
GLOBAL, not per bundle.** It took the newest `cabinet_update_refused` receipt
in the window and, when that record named another bundle or no bundle at all,
threw the rest of the channel away. `refuse_busy` writes exactly such a record
on every lock contention — `record_refusal "" busy` when a rollback loses the
lock, `record_refusal <other> busy` when an apply does — so a constitutional
verdict on the bundle sitting in the inbox was blanked by a note about a
moment, and BOTH surfaces then said *"an update is ready to take — tap Apply"*
over bytes this box had already turned down. Round 4 was card-wrong and
briefing-right; round 5 was both wrong, in agreement, which is worse.

The rule was then RULED, by a blind two-model gate (arm A Fable 5.1, arm B
Opus 5; adjudication in `designs/employee-phase1-2026-09-07/
a517-gate-2026-09-09/`), as contract amendment **A5.17**. This commit builds
exactly that. Where this branch's code disagreed with A5.17, the code was the
defect — including two arms that pinned A5.15's letter, which A5.17 supersedes.

## The rules, and where each one lives

| A5.17 | what it says | where |
|---|---|---|
| 1 | two classes: a VERDICT about the bundle's bytes, a TIMING NOTE (`busy`, or any empty sha) about a moment | `update_bundle.is_verdict`, `run_briefing._is_verdict` |
| 2 | a verdict writes its MARKER first (`.updates/refusals/<sha>.json`), then the receipt, then `state.json` with `last_refusal` as a legacy mirror; a timing note writes its receipt and `last_busy` only; apply/rollback delete the markers of every sha they name; never pruned while in the inbox; a failed write is named `state_error` | `update_bundle.record_refusal` / `write_refusal_marker` / `drop_refusal_markers`, `cabinet-update.sh drop_refusal_markers` |
| 3 | time is the record's OWN — one payload field, `recorded_at`, on all three event types; never the ledger's insertion time; position is not an input | `update_bundle.record_event` (stamps it), `record_time`, `run_briefing._record_time` |
| 4 | "about B" = `to_sha` is B, or a ROLLBACK whose `from_sha` is B | `_receipt_is_about`, `_state_event_is_about` and their twins |
| 5 | current(B): candidates are verdicts about B on either channel (legacy admitted only where no marker store exists); superseded only by a STRICTLY newer apply/rollback about B on either channel, or by a newer verdict; ties keep the refusal; ties on channel go to `state` | `update_bundle.current_refusal`, `run_briefing._resolve_refusal` |
| 6 | `status --json` reports current(W), or — nothing waiting — the newest verdict newer than every applied/rolled_back record; plus `last_refusal_source`, `last_busy`, `state_error`; it never writes | `update_bundle.resolve_update_surface`, `cabinet-update.sh cmd_status` |
| 7 | the ladder, IDENTICAL on both surfaces, including the rollback-FROM-W sentence with Apply kept | `run_briefing._update_notice` / `_rollback_line`, `lib/updates.updateHeadline` / `applyTarget` |
| 8 | the 5250-row oracle | `framework/frontdoor/tests/update_surface_oracle.json` |
| 9 | the sensors | `test_card_update_notice.py`, `test_cabinet_update.py`, `lib/updates.test.ts`, `update-card.test.tsx` |

## What the round-5 review asked for, item by item

1. **Per-bundle currency.** Both resolvers now take the waiting sha and ask
   about that bundle. A record naming no bundle is a timing note and is not a
   candidate anywhere; a record about another bundle is not an answer to a
   question about this one.
2. **A written decision about a state-file refusal of X versus a ledger refusal
   of the WAITING Y.** A5.17.5 settles it and this commit implements it: they
   are not compared at all, because they are answers to different questions.
   Within ONE bundle the newest wins and ties go to `state`.
3. **An oracle that can hold a ledger of depth two.** The ledger about B is now
   an axis of seven time-ordered SEQUENCES, and what the ledger says about
   anything else is an axis of five. 5250 rows.
4. **Arms red against `c0a92731` on both surfaces.** e1 and e2 drive the real
   updater, the real recorder, the real `status --json` and the real briefing.

Also from the review's notes: the card's real resolver is now driven against
the table (`test_cabinet_update.py::test_the_resolver_answers_every_state_the_
way_the_oracle_says`, all 5250 rows), the rollback-from-W per-surface
difference is retired, and `docs/proposals/update-path-event-expansion-2026-09-07.md`
no longer says `_update_receipt_for` is the second channel — that helper is
retired, along with every direct read of a refusal receipt by a surface.

## The oracle

`5 phase × 3 waiting × 5 state-about-B × 7 ledger-about-B sequences ×
5 newest-not-about-B × 2 ledger_error = 5250 rows`, the whole product, nothing
skipped or xfailed. Each row carries the exact SENTENCE for both surfaces,
`refusal_speaks`, `apply_live` and `last_refusal_source`, and what both
resolvers must produce. Seeds are hoisted per axis value; every seeded event
carries its own `recorded_at`.

Three readers consume it: the briefing (pytest), the resolver `status --json`
reports (pytest, in the cabinet suite), and the card (vitest). Four inputs are
held OUTSIDE the product as INVARIANCE arms over ≥ 50 sampled rows each — a
marker about another bundle, `last_busy` in any value, `event_fallback` either
way, and the ledger's record ORDER.

**One of those four is not invariant, and the arm says so rather than
excluding it.** A5.17.5 admits the legacy state record only where there is no
marker store, so the first marker this updater ever writes — about ANY bundle —
switches that compatibility read off. Measured on four sampled rows. Those rows
are held to the answer their `state: none` twin gives, which states exactly
what the marker costs them.

## Rows `c0a92731` gets wrong

Measured, not derived, on the new table with the production sources checked out
at `c0a92731` and `__pycache__` purged:

| surface | wrong |
|---|---|
| briefing (`_update_notice`) | **1702 of 5250** |
| card (old resolver → old `updateHeadline`/`refusalToShow`/Apply gate) | **1786 of 5250** — 1786 sentences, 1468 `refusal_speaks`, 592 Apply |

e1 (`idle/same/legacy-busy/V/busy-empty/noledger`), e2
(`idle/same/legacy-busy/V/busy-other/noledger`), the round-5-blessed row
(`idle/same/legacy-busy/V/none/noledger`) and the double tap
(`idle/same/none/V-busy/none/noledger`) are in BOTH wrong sets.

## Mutations

| mutation | briefing | resolver | card |
|---|---|---|---|
| flip `refusal_speaks` on the double-tap row | rc 1 — `1 of 5250 states are not what the contract says` | (does not consume it) | rc 1 — `expected [ '1 of 5250 wrong', …] to deeply equal [ '0 of 5250 wrong' ]` |
| flip `resolved.source` on the e1 row | rc 1 — `1 of 5250 states…` | rc 1 — `1 of 5250 resolutions…` | (does not consume it) |
| fixture moved away | rc 1 — `FileNotFoundError`, **no skip** | rc 1 — `FileNotFoundError`, no skip | rc 1 — `ENOENT`, `Tests no tests`, the file FAILS |

## Arms whose expectation this commit CHANGED, and why

Eight arms pinned behaviour A5.17 supersedes. None was deleted; each was
re-aimed and says what moved:

* `test_a_busy_refusal_is_recorded_and_never_erases_an_interrupted_apply` and
  `test_a_losing_updaters_state_write_cannot_revert_the_winners[record_refusal]`
  — a timing note lands in `last_busy` and nowhere else (A5.17.1 reverses
  A5.15's letter). Both now also assert no verdict marker was written.
* `test_the_refusal_record_outlives_the_next_state_write` — the durable record
  is the marker; `status --json` is silent because nothing waits and an apply
  has happened since, and the arm asserts the verdict still stands on that
  bundle if it is ever offered again.
* `test_a_refusal_that_reached_only_the_ledger_…`, `test_an_unreadable_state_
  file_…`, `test_a_receipt_refusal_an_apply_overtook_…` — deleting `state.json`
  no longer produces a ledger-only refusal, because the marker survives, which
  is the point of it. They now drop the whole state channel. The overtaking
  apply is given an explicit `recorded_at` rather than racing the clock: the
  updater stamps whole seconds and a tie keeps the refusal.
* `test_the_refusal_still_speaks_when_it_IS_the_last_thing_that_happened` and
  the two `_overtaken_refusal` arms — they carried `busy` as the refusal, which
  since A5.17 is not a candidate at all, so they would have passed without the
  currency rule ever running. They carry a verdict now, and the busy case is
  pinned by its own arm.
* The card's scoping arms in `lib/updates.test.ts` and
  `update-card.test.tsx` — the sha test, the `busy` filter and the currency
  check moved to the resolver, so these are fed what the resolver actually
  produces in each state and each names where the rule now lives.

## Two arms added that the contract does not list

* `test_an_apply_with_no_time_of_its_own_cannot_overtake_anything` — the
  degenerate end of "strictly newer". Every `write_state` on both paths stamps
  `finished_at`, so this shape comes only from a truncated file, and the answer
  it gets is the safe one.
* `test_the_resolver_never_writes` — A5.17.6's last sentence, checked by
  comparing every byte under `.updates/` around three resolutions.

## What the second half of round 6 added (and what it found)

The commit above was cut mid-unit. Everything below was built after it, and
every claim in this file was re-measured rather than inherited: the 1702 and
the 1786 were reproduced from scratch on this tree, at `c0a92731` production
bytes with `__pycache__` purged, by driving the OLD briefing and the OLD
resolver over all 5250 rows and the OLD card over the documents that resolver
produced. Both numbers came back identical.

* **The weld.** `test_the_races_land_on_the_oracle_row_the_card_is_held_to`
  (three params: e1, e2, the double tap). The chain had a seam: the resolver is
  pinned to the table, the table is pinned to the card, and nothing said the
  REAL races land on the row the other two are arguing about — a table can be
  right about a state nobody is ever in. This arm takes the document the real
  updater leaves behind, checks every axis of the row it claims to be against
  the install itself (phase from `state.json`, the marker file and its paths,
  the receipts about B, the newest record not about B, the ledger fault), and
  then asserts that row's expectations are the refused sentence with Apply
  withdrawn — the row `lib/updates.test.ts` renders the card from. RED at
  `c0a92731`: `FileNotFoundError: …/.updates/refusals/bbbb….json`, because the
  durable store the table describes did not exist there.
* **The races, rendered.** `update-card.test.tsx` now renders `<UpdateCard/>`
  on the shape both races leave — a constitutional verdict standing on the
  waiting bundle with a timing note beside it, about no bundle (e1) and about
  another (e2). **GREEN at `c0a92731` too, and the arm says so**: at those bytes
  the card was handed the wrong DOCUMENT, not handed the right one and rendered
  wrong. The red for that is the resolver's, and it is recorded there.
* **The rollback-classify arm is relabelled**, per the round-5 note. It is
  green against every production tree and always will be — `_classify_kind` is
  a helper in the test file — so it is now labelled a sensor on the parity
  sweep's own eyesight rather than counted among the arms that red on
  production bytes.
* **`docs/proposals/update-path-event-expansion-2026-09-07.md:74`** said in the
  present tense that the briefing reads the three types through
  `_update_receipt_for`. That helper is retired; the line now names
  `_update_receipts` and dates the old spelling. (Line 89-91, the residual the
  round-5 review named, was already fixed in the commit above.)

## Budget, locked set, agnostic law

* **Budget:** `framework_production_noncomment_lines` **81466 → 81577 = +111**;
  the yml maximum moves **66728 → 66839 = +111**, with a dated round-6
  paragraph naming the mass, the timestamp field (`recorded_at`) and all six
  axes. `observed == maximum`, zero headroom, modules unchanged. The +111 is
  NET of two retired helpers (`_update_receipt_for`, `_update_receipt_refusal`).
  The card's resolver lives in `cabinet/`, outside this budget; the oracle and
  every arm are test files, outside it by construction.
* **Locked set:** no changed path is in the germline set.
* **Agnostic law:** layer separation `new=0`; no product, industry, role or
  person literal in the production diff; no guarded token added to a doc.
* **Docs track code in this commit:** the runbook's whole refusal section, the
  proposal's stale `_update_receipt_for` line, the contract yml's three
  expansion-row consumers, and the drill's P7 check, which now requires the
  durable marker as well as the mirror.
