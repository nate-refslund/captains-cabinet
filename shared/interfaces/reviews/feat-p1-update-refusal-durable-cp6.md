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

---

# Round-6 evidence, measured this session on this tree

Method for every RED below: the PR's tests and fixtures kept, the FIVE
production sources checked out at `c0a92731` (`cabinet-update.sh`,
`lib/update_bundle.py`, `run_briefing.py`, `lib/updates.ts`,
`update-card.tsx`), every `__pycache__` purged, `PYTHONDONTWRITEBYTECODE=1`.
Restored to HEAD afterwards and the oracle verified byte-identical
(`git diff --quiet` on the fixture).

## The rows `c0a92731` gets wrong — re-measured, not inherited

Driven over the whole 5250 by a throwaway harness (deleted; it reused
`_drive_oracle_row` and the OLD `update_bundle.resolve_last_refusal`, then fed
the OLD `updateHeadline`/`refusalToShow` and the OLD inline Apply gate the
documents that resolver produced):

| reader at `c0a92731` | wrong |
|---|---|
| briefing `_update_notice` | **1702 of 5250** |
| card (old resolver → old headline/refusal/Apply) | **1786 of 5250** |

Both numbers equal the ones the commit above claimed. In BOTH wrong sets:
`idle/same/legacy-busy/V/busy-empty/noledger` (e1 as the old bytes produced
it), `idle/same/legacy-busy/V/busy-other/noledger` (e2),
`idle/same/legacy-busy/V/none/noledger` (the round-5-blessed row),
`idle/same/none/V-busy/none/noledger` (the double tap) — and also the three
rows the REAL races land on today, which is what the new weld arm names:
`refused/same/marker-locked/V/busy-empty/noledger`,
`refused/same/marker-locked/V/busy-other/noledger` and
`refused/same/marker-locked/V-busy/none/noledger`.

## Every A5.17.9 sensor: RED at `c0a92731`, GREEN at HEAD

| arm | RED text at `c0a92731` | GREEN |
|---|---|---|
| `test_e1_a_rollback_that_lost_the_lock_does_not_blank_the_verdict` | `AssertionError` on `report["last_refusal"]` — the whole report, `last_refusal: null` | rc 0 |
| `test_e2_an_apply_of_another_bundle_that_lost_the_lock_does_not_blank_it` | `AssertionError: {'bundle': 'eeee…', 'reason': 'busy', …}` | rc 0 |
| `test_the_double_tap_on_one_bundle_keeps_its_verdict` | `AssertionError: {'bundle': 'bbbb…', 'paths': [], 'reason': 'busy', …}` | rc 0 |
| `test_the_races_land_on_the_oracle_row_the_card_is_held_to` ×3 | `FileNotFoundError: …/.updates/refusals/bbbb….json` | rc 0 |
| `test_a_marker_survives_a_whole_document_state_replace` | `AssertionError: assert False` (no marker file after the refusal) | rc 0 |
| `test_the_legacy_state_record_is_read_where_there_is_no_marker_store` | `AssertionError: {'bundle': 'bbbb…', 'paths': ['cabinet/scripts/start-officer-mac.sh'], …}` | rc 0 |
| `test_two_verdicts_on_one_bundle_leave_the_newest_speaking` | `AttributeError: module 'update_bundle' has no attribute 'read_refusal_marker'` | rc 0 |
| `test_an_apply_in_the_same_second_does_not_supersede_the_verdict` | `TypeError: resolve_last_refusal() got an unexpected keyword argument 'waiting_sha'` | rc 0 |
| `test_an_apply_and_a_rollback_drop_the_markers_of_the_shas_they_name` | `AttributeError: … no attribute 'read_refusal_marker'` | rc 0 |
| `test_the_marker_store_is_bounded_but_never_evicts_a_waiting_bundle` | `AttributeError: … no attribute 'write_refusal_marker'` | rc 0 |
| `test_a_failed_marker_write_is_named_rather_than_swallowed` | `KeyError: 'state_error'` | rc 0 |
| `test_the_resolver_answers_every_state_the_way_the_oracle_says` | `AttributeError: … no attribute 'resolve_update_surface'` | rc 0 |
| `test_the_resolver_never_writes` | same `AttributeError` | rc 0 |
| `test_an_apply_with_no_time_of_its_own_cannot_overtake_anything` | `AssertionError: an untimed apply silenced a verdict it cannot be shown to postdate` | rc 0 |
| `test_a_timing_note_is_never_a_candidate_even_when_it_is_the_last_record` | `AssertionError: assert 'Update refus...sy (bbbbbbbb)' == ''` | rc 0 |
| `test_the_briefing_answers_every_state_the_way_the_oracle_says` | `TypeError: _update_resolved_refusal() takes 1 positional argument but 2 were given` | rc 0 |
| INVARIANCE `test_a_marker_about_another_bundle_never_moves_the_answer` | `AssertionError: 49 of 103 moved` | rc 0 |
| INVARIANCE `test_last_busy_in_any_value_never_moves_the_answer` | `AssertionError: 35 of 87 moved` | rc 0 |
| INVARIANCE `test_event_fallback_on_or_off_never_moves_the_answer` | `AssertionError: 34 of 89 moved` | rc 0 |
| INVARIANCE `test_the_position_of_a_record_in_the_ledger_is_not_an_input` | `AssertionError: 45 of 107 moved` | rc 0 |
| vitest `the card answers every state the way the oracle says` | `TypeError: applyTarget is not a function` | rc 0 |
| vitest `a held record and a busy note never move the headline` | `AssertionError: expected [ '14 of 87 moved', …(10) ] to deeply equal [ '0 of 87 moved' ]` | rc 0 |
| vitest `a bundle this box rolled back is neither refused nor untried` | `expected 'Update ready — 12 files changed (bbbb…' to be 'Update rolled back — the health gate …'` | rc 0 |
| vitest `says a bundle was rolled back and still keeps Apply` (rendered card) | `expected '<div class="rounded-lg border border-…' to contain 'Update rolled back — the health gate …'` | rc 0 |
| vitest `takes the resolved record as final — it does not re-scope it` | `AssertionError: expected null to deeply equal { …(5) }` | rc 0 |
| vitest `keeps Apply for a receipt-sourced verdict a retry can re-test` | `TypeError: applyTarget is not a function` | rc 0 |

**Two arms are green at `c0a92731` and say so** rather than being counted:
the rendered-card race arm (the card was handed the wrong DOCUMENT there, not
handed the right one and rendered wrong) and
`test_a_rolled_back_receipt_is_still_classified_as_a_rollback` (its subject is
a helper in the test file). The parity sweep
`test_the_briefing_says_what_the_card_says_on_every_shared_state` also passes
at `c0a92731`: its seven argued cases do not discriminate this change — the
5250-row product is what does.

## Mutations, run this session

| mutation | briefing (pytest) | resolver (pytest) | card (vitest) |
|---|---|---|---|
| flip `expect.refusal_speaks` on the double-tap row | rc 1 — `1 of 5250 states are not what the contract says` | (does not consume it) | rc 1 — `expected [ '1 of 5250 wrong', …(1) ] to deeply equal [ '0 of 5250 wrong' ]` |
| flip `resolved.source` on the e1 row | rc 1 — `1 of 5250 states…` | rc 1 — `1 of 5250 resolutions are not what the contract says` | (does not consume it) |
| fixture moved away | **6 failed, 44 passed**, `FileNotFoundError`, no skip | **5 failed**, same error | the file FAILS — `Error: ENOENT`, the other file's 12 still run |

Oracle restored byte-identical after each.

## Battery — every command and its exit code, this tree, this session

| cmd | rc |
|---|---|
| `pytest framework/ -q -rs -p no:cacheprovider` | 0 — 8563 passed, 31 skipped, 2 subtests |
| `pytest cabinet/scripts/tests` chunk 1/8 (incl. `test_cabinet_update.py`) | 0 — 1548 passed |
| chunk 2/8 | 0 — 651 passed, 5 skipped |
| chunk 3/8 | 0 — 786 passed, 6 skipped |
| chunk 4/8 | 0 — 731 passed, 19 skipped |
| chunk 5/8 | 1 — **1 failed** `test_evidence_seam_bypass_replay.py::test_shipped_catalog_harness_still_green[evidence-access.sh]` (pre-existing), 616 passed |
| chunk 6/8 | 0 — 433 passed, 2 skipped |
| chunk 7/8 | 0 — 284 passed, 1 skipped |
| chunk 8/8 | 0 — 470 passed, 1 skipped |
| `python3.12 cabinet/mcp-server/test_server.py` | 0 — 95 passed |
| `check-layer-separation.sh` | 0 — baseline=24 allowlist=19 current=43 **new=0** |
| `docs-track-code-sweep.sh` | 0 — `DOCS_SWEEP GREEN (files=66 findings=0)` |
| `ledger-status-parity.sh` | 0 — `ids=354 md_rows=354 findings=0` |
| `run-hook-regression.sh` | 1 — 11/19, the pre-existing eight |
| `test-triggers.sh` | 0 — `PASS: 55 FAIL: 0` |
| `test-mac-dry-run.sh` | 0 |
| `null-hatch.sh` | 0 — `PROOF 1 — NULL HATCH: PASS` |
| `state-persistence-preflight.py --repo .` | 0 — 97 candidates, **0 UNACCOUNTED**, 2 known deferred gaps |
| `cognitive-architecture-census.py --check` | **printed** `cognitive architecture census: PASS`, `framework_production_noncomment_lines: 81577 <= 81577`, modules `253 <= 253` |
| `npx vitest run` | 0 — 186 files, 3920 passed, 1 skipped |
| `npx tsc --noEmit` | 0 |
| `drills/one-responsibility.sh --skip-update` | 0 |
| `drills/one-responsibility.sh` (full) | 0 — `PASS [P7] gate red rolled back, gate green applied, preserved path intact, locked bundle refused whole` |
| `cabinet/tests/start-officer/test-args.sh` | 1 — PASS=12 FAIL=7 (pre-existing) |
| `audit-framework-backlog-drift.sh` | 0 — THIN (`/opt/founders-cabinet/…` not on this host) |

**Failing set identical to the pre-existing set at `95e47ba2`: YES** —
`test_evidence_seam_bypass_replay[evidence-access.sh]`, run-hook-regression
11/19, `test-args.sh` 12/7, `audit-framework-backlog-drift` THIN. The known
`test_cog1_outbox_capture` p95 wall-clock flake did not trip this run.

## Locked set

21 changed paths (`git diff --name-only 95e47ba2...HEAD`) ∩ this tree's parsed
germline set (**73 files, 7 dirs**, asserted non-empty) = **EMPTY**. The first
parse of `DIRS` silently swallowed the trailing comments and would have matched
nothing — caught before it became a claim; the fixed check is proved able to
fire on `.claude/settings.json`, `cabinet/scripts/hooks/pre-tool-use.sh` and
`memory/golden-evals/EVAL-024.md`, and correctly does not fire on
`cabinet/scripts/cabinet-update.sh`.

## Residuals

* CI still executes zero steps on this repository (billing lock), so this PR is
  not CI-verified and the battery above is the whole of the evidence.
* The `bin/Cabinet Companion.app` and world-aesthetic goldens preflight gaps are
  pre-existing and dated (deferred to 2026-10-31); neither is touched here.
