# feat/p1-update-refusal-durable — checkpoint 5

Round-5 targeted follow-up. One must-fix from the round-4 review: **the briefing
had a SECOND refusal channel — the ledger receipt — that spoke outside the four
rules and that the card could not see at all**, and the branch asserted in
production source that the two surfaces could not disagree.

## 1. What was wrong, measured

| state (reachable) | briefing at `9b426cc4` | card at `9b426cc4` | Apply |
|---|---|---|---|
| `busy` refusal of the bundle still in the inbox | `An update is waiting but was REFUSED: busy (bbbbbbbb)` | `Update ready — 7 files changed` | live |
| locked-path refusal that reached only the LEDGER | `An update is waiting but was REFUSED: bundle changes locked constitutional paths` | `Update ready — 7 files changed` | **live** |

`refuse_busy` fires on every lock contention and writes both channels. The
ledger-only rows arise whenever `state.json` is absent or unreadable while the
ledger is not — and `update_bundle.record_refusal` could reach exactly that
state, because a failed state write RAISED out of the CLI (rc 1) after the
receipt had already landed.

## 2. The shape of the fix — one resolved record, one predicate

`status --json` is now the single reader of both channels. It resolves ONE
`last_refusal` — the state file's record if it has one, else the ledger's
CURRENT refusal — and tags it `last_refusal_source: state | receipt | ""`.
Both surfaces consume only that resolved value:

- **the card** already did, and its production code is unchanged apart from the
  new optional field on `UpdateStatus`. Proved: the non-comment diff of
  `updates.ts` against `9b426cc4` is one line, `last_refusal_source?: string`.
  What changed is its INPUT.
- **the briefing** resolves the same two channels the same way
  (`_update_resolved_refusal`), a deliberate twin of
  `update_bundle.resolve_last_refusal` rather than an import, because a briefing
  may not shell out and `framework/` does not import from `cabinet/`. The two
  resolvers are held to the SAME declaration by the oracle (`resolved` per row),
  so they cannot drift without a row going red.
- the briefing's `_update_receipt_for` refusal arm is **retired**. It keeps the
  channel for `applied` and `rolled_back` receipts only — those are not refusals
  and cannot contradict a live Apply button.
- **one predicate**, `_refusal_speaks`, carries A5.15's four rules and runs once,
  on that one record, whichever channel produced it. `refusalToShow` is its TS
  twin.

Currency on the receipt channel is the receipt spelling of `phase: refused`:
the newest `cabinet_update_refused` receipt speaks only while nothing has
happened to that bundle since. A receipt naming no bundle is not resolvable.

Two smaller items in the same family:

- `record_refusal` no longer raises when the state write fails: it returns
  `state_error` (as `record_event` does), the updater logs `STATE WRITE FAILED`,
  and the refusal is then resolved from the receipt and tagged `receipt`. The
  missing half says it is missing.
- `_state_refusal` reads the state document's record in either of the two forms
  it takes (`last_refusal`, or the top-level copy a `refused` document carries),
  which deletes round-4 note **N2** at the resolution step instead of in either
  reader.
- the shared classifier now names the receipt-channel rollback sentence
  (round-4 note **N1**); it was `unclassified`, inert only because every sweep
  row ran on an empty ledger.
- the stale docstring of `test_a_refused_bundle_does_not_read_as_ready_to_take`
  is rewritten (round-4 note **N4**).

## 3. The oracle — the ledger is the sixth axis

`update_surface_oracle.json`: **1440 rows** = 5 phase × 3 waiting × 4 refusal ×
2 ledger_error × 2 event_fallback × **6 receipt** (`none | refused-same-sha |
refused-other-sha | refused-busy | applied | rolled_back`). Each row carries the
seeds to emit, what the resolution must produce, and the expected kind per
surface.

Generated from a classifier written out of the contract (A5.13/A5.15/A5.16 and
the round-1..4 adjudications), never from either implementation. **The
generator reproduces the reviewed 240-row table exactly on all 240 empty-ledger
rows** — two independent statements of the same rules landing on the same table.

Reachable subset, stated in `_what_this_is`: every row where the two channels
agree (both written by one call), and every row where the ledger has a record
the state file does not (failed/truncated/removed state write, or an install
carrying refusals recorded before this branch). Not writer-reachable: a state
file carrying refusal X while the ledger's current refusal is about a different
bundle Y. Kept and pinned for the same reason the degenerate `phase` rows are.

Two deliberate per-surface SHAPE differences, both written per surface rather
than skipped: the ledger fault (as before) and a `rolled_back` receipt about the
waiting bundle — the briefing spends its one line on it, the card says `Update
ready` and keeps Apply, because a rollback is not a refusal. `refusal_speaks`,
which is what withdraws Apply, is identical on every one of the 1440 rows.

## 4. Rows the old code got wrong

Measured, not derived: **52 of 1440 on the briefing** (production sources at
`9b426cc4`, new tests and fixture kept, `__pycache__` purged) and **28 of 1440
on the card** (the real `updateHeadline`/`refusalToShow` fed the OLD
state-file-only resolution). Union **52**; the card's 28 are exactly the rows
where the receipt channel resolves a refusal that speaks, and they are a subset.

## 5. Mutation proof

- Kind flipped in the JSON (`idle/same/none/noledger/nohold/refused-same-sha`,
  `refused → ready`) reds BOTH: pytest `1 of 1440 states are not what the
  contract says`; vitest `expected [ '1 of 1440 wrong', …(1) ] to deeply equal
  [ '0 of 1440 wrong' ]`. Restored: green both.
- Fixture moved away: pytest 3 failed with `FileNotFoundError`, **no skip**;
  vitest `Error: ENOENT`, `Tests no tests`, the file FAILS.
- The completeness arm derives the id set from the DECLARED axes (so a REMOVED
  row fails, not only a changed one), re-derives each row's id from its own
  axes, and now also asserts every declared receipt value has seeds behind it —
  an axis with nothing behind it is an axis held constant under a name, which is
  exactly what the ledger was.

## 6. Sensors — RED at `9b426cc4`, GREEN after

| arm | RED rc | RED text (verbatim) | GREEN rc |
|---|---|---|---|
| `test_a_busy_receipt_does_not_turn_the_waiting_bundle_into_a_refusal` | 1 | `AssertionError: An update is waiting but was REFUSED: busy (bbbbbbbb)` | 0 |
| `test_a_ledger_only_refusal_speaks_through_the_same_helper_as_the_state_file` | 1 | `AssertionError: An update is waiting but was REFUSED: bundle changes locked constitutional paths (bbbbbbbb)` | 0 |
| `test_a_rolled_back_receipt_is_still_classified_as_a_rollback` | 1 | `assert 'unclassified' == 'rolled_back'` | 0 |
| `test_a_refused_bundle_does_not_read_as_ready_to_take` | 1 | `AssertionError: An update is waiting but was REFUSED: it changes locked constitutional paths (bbbbbbbb)` | 0 |
| `test_the_briefing_answers_every_state_the_way_the_oracle_says` | 1 | `AssertionError: 52 of 1440 states are not what the contract says:` + every offending row | 0 |
| `test_the_briefing_resolves_the_refusal_the_table_says_it_must` | 1 | `AttributeError: module 'framework.frontdoor.run_briefing' has no attribute '_update_resolved_refusal'` | 0 |
| `test_a_refusal_that_reached_only_the_ledger_is_still_the_last_refusal` | 1 | `KeyError: 'last_refusal_source'` (and `last_refusal` is `None`) | 0 |
| `test_an_unreadable_state_file_does_not_lose_the_refusal_either` | 1 | `KeyError: 'last_refusal_source'` | 0 |
| `test_the_state_file_is_the_source_whenever_it_has_a_refusal` | 1 | `KeyError: 'last_refusal_source'` | 0 |
| `test_a_receipt_refusal_an_apply_overtook_is_not_resolved` | 1 | `assert None` (`last_refusal` already null, `last_refusal_source` absent) | 0 |
| `test_a_state_write_that_fails_is_named_rather_than_swallowed` | 1 | `record-refusal` exits 1 with `IsADirectoryError` traceback | 0 |
| the card sweep, fed the OLD resolution | 1 | `expected [ '28 of 1440 wrong', …(20) ] to deeply equal [ '0 of 1440 wrong' ]` | 0 |

**Declared guards — green in BOTH directions, and labelled as such.** The card's
own source did not change, so the two new vitest arms (`withdraws Apply exactly
as one the state file carried would`, `is still filtered by rule 4 when the
reason is only timing`) pass at `9b426cc4` too: they pin that a receipt-sourced
record is treated exactly like a state-sourced one, which is what makes moving
the resolution upstream safe. Likewise
`test_a_refusal_receipt_an_apply_receipt_has_overtaken_is_not_the_news` and
`test_the_state_file_outranks_the_ledger_when_both_carry_a_refusal`, which pin
the two directions the fallback must NOT widen into.

## 7. Budget, locked set, agnostic law

- **Budget:** `framework_production_noncomment_lines` **81411 → 81466 = +55**;
  the yml maximum moves **66673 → 66728 = +55**, with a dated paragraph naming
  the mass (the five resolution/predicate helpers in `run_briefing.py`). Census
  printed `cognitive architecture census: PASS`, `81466 <= 81466`, modules
  `253 <= 253`. `observed == maximum`, zero headroom. The oracle and the arms
  are test files, outside the budget by construction; `status --json`'s resolver
  is in `cabinet/`, likewise outside it.
- **Locked set:** no changed path is in the germline set (checked against this
  tree's `germline-lock.sh`).
- **Agnostic law:** no product, industry, role or person literal in the
  production diff; layer separation `new=0`.
- **Docs track code:** the runbook's refusal section names both channels, the
  resolution, `last_refusal_source`, the `state_error` log line, the sixth axis
  and the two per-surface shape differences. `DOCS_SWEEP GREEN (files=66
  findings=0)`.
