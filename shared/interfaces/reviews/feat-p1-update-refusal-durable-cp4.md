# U5b — checkpoint 4: the currency of a refusal, and the class closed

Round 3 rejected on one must-fix and named the fix in four steps. This
checkpoint closes it and adds the sensor that makes the CLASS unrepeatable,
because the must-fix was the third defect three review rounds found in the same
two readers — each one an adjacent state, each one missed by arms aimed at the
state that already worked.

Base of this checkpoint: `888afb6b`.

## 1. The must-fix — a refusal that a later apply had overtaken kept speaking

`refusalToShow` returned the refusal unconditionally when `!status.latest`;
`_update_refusal_line` skipped both filters when `waiting_sha` was empty.
Neither asked whether anything had happened AFTER the refusal, and nothing ever
clears `last_refusal` — `CARRIED_STATE_FIELDS` carries it onto every later state
document on purpose, because a refusal is still TRUE after the next thing
happens. What it stops being is the NEWS.

| # | the step round 3 named | where it is closed |
|---|---|---|
| 1 | `updates.ts` `refusalToShow`: a currency check on the nothing-waiting branch | `if (!status.latest) return status.phase === 'refused' ? refusal : null` — a NARROWING; the sha scope on the something-waiting branch is untouched, and the arm that pins it is below |
| 2 | `run_briefing._update_refusal_line`: mirror it | the compound `if` is now three arms, one per rule: `if not bundle` / `if waiting_sha:` (rule 4, the sha scope) / `elif state.get("phase") != "refused":` (rule 3, currency). Four rules in one boolean is how the third one got written on one surface only |
| 3 | arms on both sides, RED against `888afb6b` | 5 pytest, 6 vitest — table below |
| 4 | a seventh parity case: `phase: applied`, nothing waiting, `last_refusal` on record, `agree.kind: applied` | `update_surface_parity.json` case 7, the literal end-state of the busy race, plus the count assertions in both suites (7 cases, `applied` × 2) |

## 2. The class-closer — one oracle, 240 rows, both surfaces

`framework/frontdoor/tests/update_surface_oracle.json` is the whole product of
the five axes these two readers branch on:

    phase          idle | refused | applying | applied | rolled_back      (5)
    waiting        none | same (the refused sha) | other                 (3)
    refusal        none | locked-paths | busy | digest-mismatch          (4)
    ledger_error   absent | set                                          (2)
    event_fallback false | true                                          (2)

5 × 3 × 4 × 2 × 2 = **240 rows, the whole product, nothing skipped.** (Round 3's
sweep counted 288 by splitting waiting-presence and same/other-sha into two
axes; here they fold into one 3-valued axis, since a refusal is always ABOUT the
refused sha and `same`/`other` is what scopes it.) Rows the updater cannot
produce — phase `idle` carrying a refusal, phase `refused` carrying none — are
KEPT and pinned rather than dropped: a state file can be truncated or
hand-edited, and what a reader does at the degenerate end is exactly what three
rounds of arms never asked.

Each row carries the literal `state` document written to `.updates/state.json`,
the inbox descriptor, the expected headline KIND for EACH surface
(`ready | refused | applying | applied | rolled_back | fault | quiet`) and
whether the refusal sub-surface speaks. The pytest half drives
`_update_notice` + `_update_refusal_line`; the vitest half drives
`updateHeadline` + `refusalToShow` over a status object derived field-for-field
as `cabinet-update.sh status --json` derives its report. Both read the SAME
file.

**Derived from the contract, not from the code.** The rules were written first,
from A5.13/A5.15/A5.16: (1) no refusal on record, nothing to say; (2) an apply
in flight outranks it; (3) nothing waiting, it speaks only while it is still the
last thing that happened; (4) something waiting, only about those bytes and only
when the reason is about the bundle. Ranking: the briefing has ONE line and
spends it refusal → fault → applying → ready → applied/rolled_back; the card
has a headline and a sub-line, so the fault does not displace its headline.

**The one per-surface difference, encoded rather than skipped.** 88 of the 240
rows have different headline kinds on the two surfaces, and all 88 are
ledger-fault rows: the briefing's one line goes to the fault, the card shows it
beside whatever it is saying. `refusal_speaks` is identical on all 240 rows,
because it is one property of one record.

**One row class where the code disagreed with the contract, so the code moved.**
A fault with an idle phase, nothing waiting and no refusal on record reached NO
web surface: the page renders the card only when `updateHeadline` is non-null.
Round 2 recorded that as "not a hole in practice"; the oracle says a fault is
named on every surface, so `updateHeadline` now has a LAST arm —
`Update records are not reaching the ledger` — which takes the headline only
where nothing else has one. Two arms pin both directions.

## 3. Every row the old code got wrong

40 of 240 on the card, 36 of 240 on the briefing, union 40 — measured by
swapping the sources back to `888afb6b` under the new tests.

| rows | phase | waiting | refusal | old answer | contract |
|---|---|---|---|---|---|
| 12 | `applied` | none | locked-paths / busy / digest-mismatch | `Update refused — …` | `Updated to cccccccc: 4 changes` |
| 12 | `rolled_back` | none | locked-paths / busy / digest-mismatch | `Update refused — …` | `An update was rolled back…` |
| 12 | `idle` | none | locked-paths / busy / digest-mismatch | `Update refused — …` | quiet, or the ledger fault when one is set |
| 4 (card only) | `idle` / `refused` | none | none, ledger fault set | no card at all | the fault names itself |

(× 2 ledger_error states × 2 event_fallback states in each of the first three
rows.) The 36/12 split is the same on both surfaces; the 4 card-only rows are
the fault-headline class above.

## 4. Sensors — RED on `888afb6b`, GREEN after

Method: the new tests kept, the two sources swapped to `888afb6b`,
`__pycache__` purged, `PYTHONDONTWRITEBYTECODE=1`.

| arm | RED rc | RED text (verbatim) | GREEN rc |
|---|---|---|---|
| `test_an_apply_since_the_refusal_overtakes_it_and_the_applied_line_wins` | 1 | `AssertionError: Update refused — busy (bbbbbbbb)` / `assert 'Update refus...sy (bbbbbbbb)' == 'Updated to c...cc: 4 changes'` | 0 |
| `test_a_rollback_since_the_refusal_overtakes_it_too` | 1 | `AssertionError: Update refused — busy (bbbbbbbb)` | 0 |
| `test_even_a_constitutional_refusal_is_overtaken_by_a_later_apply` | 1 | `AssertionError: Update refused — 1 constitutional file differs; needs the Captain (bbbbbbbb)` | 0 |
| `test_the_briefing_says_what_the_card_says_on_every_shared_state` (7th parity case) | 1 | `('applied, nothing waiting, and the refusal it overtook still on record', 'Update refused — busy (bbbbbbbb)')` | 0 |
| `test_the_briefing_answers_every_state_the_way_the_oracle_says` | 1 | `AssertionError: 36 of 240 states are not what the contract says:` + every row named | 0 |
| `updates.test.ts` · `is null once an apply has overtaken it and nothing is waiting` | 1 | `AssertionError: expected { …(5) } to be null` | 0 |
| `updates.test.ts` · `is null once a rollback has overtaken it…` | 1 | same | 0 |
| `updates.test.ts` · `the busy race ends in the applied sentence, not in its own refusal` | 1 | same | 0 |
| `updates.test.ts` · `a constitutional refusal overtaken by a later apply stops withdrawing Apply` | 1 | same | 0 |
| `updates.test.ts` · `a rollback since the refusal gives the rollback sentence back` | 1 | same | 0 |
| `updates.test.ts` · parity, 7th case | 1 | `expected [ …(3) ] to deeply equal [ …(3) ]` | 0 |
| `updates.test.ts` · `the card answers every state the way the oracle says` | 1 | `expected [ '40 of 240 wrong', …(20) ] to deeply equal [ '0 of 240 wrong' ]` | 0 |

**Green in both directions, declared rather than counted:**
`test_the_refusal_still_speaks_when_it_IS_the_last_thing_that_happened` and
`test_a_refusal_of_a_bundle_still_waiting_survives_a_later_apply_of_another`
(pytest), `still speaks for a refused bundle that is STILL waiting after another
apply` (vitest), and both oracle-completeness arms. They exist so the currency
check cannot become a mute button and so the sha scope is not narrowed with it.

## 5. The oracle is coupled to both suites — proved, not argued

- **A kind flipped in the JSON reds BOTH.** `applied/none/busy/noledger/nohold`
  flipped `applied → refused`: pytest `AssertionError: 1 of 240 states are not
  what the contract says: applied/none/busy/noledger/nohold: kind applied (want
  refused) … 'Updated to cccccccc: 4 changes'`; vitest `expected [ '1 of 240
  wrong', …(1) ] to deeply equal [ '0 of 240 wrong' ]`. Restored: 39 pytest / 39
  vitest pass.
- **A missing fixture FAILS, it does not skip.** File moved away: pytest
  `FileNotFoundError … update_surface_oracle.json` on both oracle arms; vitest
  `Error: ENOENT … update_surface_oracle.json`, `Tests no tests`, file FAIL.
- **A shrunk table is caught.** The completeness arm derives the expected id set
  from the DECLARED axes and compares sets, so it sees a removed row as well as
  a changed one, and it re-derives each row's id from that row's own axes so the
  index cannot come loose from what it indexes.
- **The code mutation is the RED-before measurement above:** the two sources at
  `888afb6b` are the code without this fix, and the sweep is red on both
  surfaces against them.

## 6. Battery (this tree, this session)

| cmd | rc |
|---|---|
| `pytest framework/ -q -rs -p no:cacheprovider` | 0 — 8552 passed, 31 skipped |
| `pytest cabinet/scripts/tests` chunk 1/4 (58 files) | 0 — 2179 passed, 5 skipped |
| chunk 2/4 | 0 — 1517 passed, 25 skipped |
| chunk 3/4 | 1 — **1 failed** `test_evidence_seam_bypass_replay.py::test_shipped_catalog_harness_still_green[evidence-access.sh]` (pre-existing), 1049 passed |
| chunk 4/4 | 0 — 754 passed, 2 skipped |
| `python3.12 cabinet/mcp-server/test_server.py` | 0 — 95 passed |
| `check-layer-separation.sh` | 0 — baseline=24 allowlist=19 current=43 **new=0** |
| `docs-track-code-sweep.sh` | 0 — files=66 findings=0 |
| `ledger-status-parity.sh` | 0 — ids=354 md_rows=354 findings=0 |
| `run-hook-regression.sh` | 1 — 11/19, the pre-existing 8 |
| `test-triggers.sh` | 0 — ALL PASSED |
| `test-mac-dry-run.sh` | 0 |
| `null-hatch.sh` | 0 — PROOF 1 PASS (run after the commit; it reads HEAD) |
| `state-persistence-preflight.py --repo .` | 0 — 97 candidates, 62 carried, 4 wildcard-linked, 29 declared disposable, **0 UNACCOUNTED**, 2 known deferred gaps |
| `cognitive-architecture-census.py --check` | **printed** `cognitive architecture census: PASS`, `framework_production_noncomment_lines 81411 <= 81411` (read, not inferred — it exits 0 on BLOCK) |
| `npx vitest run` (full dashboard) | 0 — 3915 passed, 1 skipped |
| `npx tsc --noEmit` | 0 |
| `drills/one-responsibility.sh --skip-update` | 0 |
| `drills/one-responsibility.sh` (full, P7) | 0 — *gate red rolled back, gate green applied, preserved path intact, locked bundle refused whole* |
| `cabinet/tests/start-officer/test-args.sh` | 1 — PASS=12 FAIL=7 (pre-existing) |
| `audit-framework-backlog-drift.sh` | 0 — THIN (`/opt/founders-cabinet/…` not on this host) |

**Failing set identical to the pre-existing set: YES** — the evidence-seam
replay arm, hook-regression 11/19 with the same eight (`captain-exceptions.sh,
evidence-access.sh, fw040-h6-v2.sh, fw040-hotfix5.sh, fw056-adversary.sh,
fw056-baseline.sh, fw057-notify-officer-argv.sh, fw076-pool-mode.sh`),
`test-args.sh` PASS=12 FAIL=7, backlog-drift THIN.

## 7. Budget, locked set, agnostic law

- **Budget:** `framework_production_noncomment_lines` **81407 → 81411 = +4**,
  measured with the census on this tree; the yml maximum moves **66669 → 66673 =
  +4**, with a dated paragraph naming the mass — the four lines of the
  nothing-waiting branch becoming its own arm. Everything else added under
  `framework/` is a test file or a JSON fixture and is outside the budget by
  construction (`_production_python_files` excludes any path with `tests` in it).
  `framework_production_modules` unchanged at 253. `observed == maximum`, zero
  headroom.
- **Locked set:** the changed paths ∩ the parsed locked set of this tree's
  `germline-lock.sh` = EMPTY, with the check proved able to fire.
- **Agnostic law:** layer separation `new=0`; nothing in the diff names a
  product, an industry, a role or a person; no guarded token added to a doc.
- **CI:** still executing zero steps on this repository (billing lock, the
  Captain's). This checkpoint's battery is the whole of the evidence.
