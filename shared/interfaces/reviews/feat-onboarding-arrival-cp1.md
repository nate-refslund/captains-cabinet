# FW-019 checkpoint review — feat/onboarding-arrival cp1

**Unit:** PR1 of the adjudicated onboarding UX direction
(`LAUNCH-DIRECTION-ONBOARDING-UX-2026-08-14.md`): the ending alone — a real
`complete` stage, the arrival screen, the post-completion management view, and a
four-stop monotonic rail. No vocabulary changes, no screen router (PR2/PR3).

**Scope:** 23 files, +2080 / -130. Core: `framework/onboarding/journey.py`.
Surface: five new dashboard modules, four modified. Four screenshots.

---

## What the defect actually was

Measured live, the Captain's own instance: stage `orientation_offered`, Charter
RATIFIED, first dividend DELIVERED — objectively finished — rendering a card
headed "Deeper Orientation has not started" over a menu of more onboarding. His
words: *"i believe i've answered everything and am now stuck and can't continue
again?"* The stage machine had no terminal success state, so a finished operator
and a stuck one were the same screen. Separately, the six-stop rail mapped
`orientation_offered` back to stop three while `dividend_ready` sat at stop
five — the operator's last act moved the rail two stops BACKWARD.

## What changed

| Piece | Mechanism |
|---|---|
| `complete` stage | `continue` from `dividend_ready`/`paused`/either complete stage lands on `COMPLETE_STAGE`, guarded by `journey_has_arrived`. |
| `orientation_offered` ≡ `complete` | `COMPLETE_STAGES` frozenset; both render the same `kind: "arrival"` card and route the same way. **Stored state files are never rewritten.** |
| Arrival card | Title "Your Cabinet is ready.", `status: "complete"`, carries the dividend's citations + egress disposition, summary assembled from recorded answers. |
| Deeper orientation | Demoted from stage title to offer, with BOTH disclosures verbatim. |
| `journey.STAGES` | Declared stage list, pinned in both directions (Python: every stage has a live card branch; TS: every stage has exactly one rail stop). |
| Rail | Four stops (You · Access · First look · Done) in a new `flow-rail.ts`, with a monotonic law. |
| Arrival screen | New `components/onboarding/arrival.tsx` — replaces the card entirely; no new hooks. |
| Management view | Same screen: what I may read / what I found / connected tools / stop or delete. |
| Completion predicate | One law, two runtimes, one shared fixture table. |

## Class-11: the four cheap questions

**1. Does each arm FAIL against pre-change code, both directions, cache purged?**

Yes, measured. `git stash push framework/onboarding/journey.py`, `__pycache__`
purged, `PYTHONDONTWRITEBYTECODE=1`:

```
8 failed, 152 deselected
  test_continue_moves_dividend_to_the_arrival
  test_arrival_is_assembled_from_recorded_answers_and_invents_nothing
  test_a_legacy_orientation_offered_journey_renders_the_arrival_untouched
  test_a_complete_stage_without_the_facts_cannot_render_an_arrival
  test_every_declared_stage_renders_its_own_card
  test_completion_parity_table
  test_the_arrival_is_not_terminal
  test_pause_still_accepts_an_arrived_journey
```

Three TS sensors carry their own inverted arm permanently, in-suite, so they
cannot rot into always-green:

- `flow-rail.test.ts` — "THE SENSOR FIRES": runs the monotonic checker over
  `LEGACY_PHASE_INDEX` (the exact pre-change mapping, frozen with its
  provenance) and asserts it FAILS at `dividend_ready`(5) → `orientation_offered`(3).
- `arrival.test.ts` — "THE SENSOR FIRES": feeds the no-invention arm a clause
  table with one fabricated word, and a clause with a dead path; both must throw.
- `completion.test.ts` — "THE SENSOR FIRES": the client-safe check is asserted to
  FAIL against `completion-state-file.ts`, which deliberately imports Node.

**2. What does each check do at the degenerate end — zero, empty, absent, null?**

- `arrivalClauses(null | undefined)` → `[]`. A blank seed (`"   "`) drops its
  clause. An empty sweep drops the tools clause. A journey with only the window
  and the finding yields exactly those two clauses — asserted, not assumed.
- `journeyIsComplete` on `{}` → false; on a null charter, an absent dividend, a
  `proposed` charter → false. The parity table carries all of them, and asserts
  it has ≥10 cases and at least one of each verdict, so an emptied table cannot
  pass vacuously.
- `stopIndex` on an unknown stage → `-1` and the rail HIDES rather than lying.
- The core's `STAGES` parser throws on an empty tuple, an unreadable line, or a
  constant it cannot resolve — it never silently returns a partial set.

**3. What does the test environment guarantee that production does not?**

**This one bit, and it is the most important line in this review.** `tsc
--noEmit` was clean and 3577 vitest tests passed with a defect that made
`/onboarding` return **500 for every operator**: the arrival is a CLIENT
component, it gated on the completion predicate, and that predicate lived beside
`import { readFile } from 'node:fs/promises'`. Both gates run in Node, where
that import is legal; the browser bundler is the only thing that could see it.
It was caught by opening the page in a real browser.

Fixed by splitting `completion.ts` (pure, client-safe) from
`completion-state-file.ts` (server, disk), and turned into a permanent cheap
sensor: `completion.test.ts` asserts every module the client component imports
is free of Node built-ins, with the server half as the proof it can fire.

**4. Is the sensor wired to the LIVE artifact?**

- `flow-rail.test.ts` parses `journey.STAGES` out of the real
  `framework/onboarding/journey.py` (five-levels-up path resolution, same
  technique as the existing `parity.test.ts`), and resolves `COMPLETE_STAGE` to
  its actual value rather than assuming the string.
- `STAGES` itself is proven to match the card builder's live branches by
  `test_every_declared_stage_renders_its_own_card` — so the TS registry is
  pinned to a control, not to a comment.
- `arrival.test.ts` resolves each clause's declared path against a real state
  object and asserts the value appears in `JSON.stringify(state)`.
- The completion parity table is read from disk by BOTH suites; neither embeds a
  copy.
- `test_continue_moves_dividend_to_the_arrival` compares the arrival's evidence
  against the **actual dividend card returned by `ratify_charter`**, not against
  a second read of the arrival.

## Adversarial pass

**Can the arrival render on a false complete?** No, at three independent layers.
(a) The transition refuses: `continue` checks `journey_has_arrived` even though
every current source stage implies it — because "implies" is an argument about a
graph that changes. (b) The card refuses: the `_card` branch is
`stage in COMPLETE_STAGES and journey_has_arrived(state)`; without the facts it
falls to the generic status card, pinned by
`test_a_complete_stage_without_the_facts_cannot_render_an_arrival` which
hand-edits the state file exactly as an attacker or a bad restore would. (c) The
surface refuses: `card.kind === 'arrival' && journeyIsComplete(state)`, pinned
per-field in `journey-card.test.ts`.

**Can the wizard be reached post-completion by URL tricks?** No, structurally.
Every welcome question and the folder branch are gated on `stage === 'welcome'`;
a finished journey's stage is `complete` or `orientation_offered`. Pinned by
iterating ALL FIVE client steps against an arrived journey and asserting none of
the four question headings render. `?more=1` opens the full orientation surface
(so the residual questions this screen does not draw a form for stay answerable
— removing a way to answer a question would be a worse defect than the one being
fixed) and it cannot reach the wizard for the same structural reason.

**Does the migration rule mis-treat a paused journey as complete?** No. `paused`
is its own stage with its own card kind; it is not in `COMPLETE_STAGES`. A
journey paused BEFORE the read carries no ratified Charter, so the predicate is
false too — that case is row `paused_before_the_read` in the parity table. The
arms iterate `welcome / charter_pending / dividend_ready / paused / revoked /
purged` and assert none renders the arrival.

**A revoked journey reads as complete by the predicate — is that a hole?** It is
a deliberate answer and it is documented in the table row and both docstrings.
Revoke stops future reads; it does not erase the Charter that was approved or
the result that was given, so an operator who exercises a control is not shoved
back into the wizard. The arrival SCREEN is still blocked there, by the card
kind. The previous docstring claimed revoked carries no ratified charter, which
was simply false about the code — corrected.

**Was any honesty deleted?** No, and it is asserted rather than asserted-about.
The two deeper-orientation disclosures are byte-identical strings, still
asserted by the same Python arm that guarded them before. The dividend's
citations and egress disposition block now travel onto the arrival card (they
did not, in my first cut — caught by looking at the live page, fixed, and pinned
against the real dividend card). The full finding text, the coverage shortfall,
the withheld-excerpt note, the read-only badge and the Charter fingerprint all
render in the management sections; the summary shows the headline only, with the
rest on the same screen. The four-clause cap can only drop clauses that have
their own section below — asserted.

**Did any capability disappear?** `pause` is no longer OFFERED on the arrival
(nothing is running to pause) but the ACTION still accepts an arrived journey,
so a card printed by an older build keeps working — pinned by
`test_pause_still_accepts_an_arrived_journey`. Question-shaped offers are not
rendered as buttons this screen cannot carry the answer for; they are named and
linked to the surface that can.

## Live verification (real browser, real core, real folder)

Dev server on a scratch `CABINET_ROOT`, fixture folder with three markdown
files. Drove the whole flow by hand:

1. Fresh journey → wizard as today, rail at "step 1 of 4" (You).
2. Three questions → rail STAYS at stop 1 (three questions, one subject).
3. Folder + ownership + authority → rail "step 2 of 4" (Access), stop 1 ✓.
4. Charter approved → rail "step 3 of 4" (First look), finding cited.
5. "See the locked next step" → **the arrival**: four settled green pips, "Your
   Cabinet is ready.", three clauses each beside the act that recorded it
   (you told me / you approved / I found), Go to your Cabinet · Read the full
   briefing · Give me more to read, then the four management sections.
6. "Go to your Cabinet" → home renders, no bounce back.
7. Revisit `/onboarding` → the arrival + management, never the wizard.
8. `?more=1` → full surface with the residual question forms, zero wizard
   headings.
9. State hand-edited to `stage: "orientation_offered"` (the Captain's live case)
   → API returns `kind: "arrival"`, page renders "Your Cabinet is ready.", and
   the stage on disk is STILL `orientation_offered`.
10. Journey removed → wizard returns; `/` redirects to `/onboarding`.

Screenshots: `docs/plans/onboarding-stepped-flow-screens/25..28`.

## Gates

| Gate | Result |
|---|---|
| `python3.12 -m pytest framework/onboarding/tests -q` | 954 passed, 1 skipped |
| `npx tsc --noEmit` | clean |
| `npx vitest run` | 171 files, 3577 passed, 1 skipped |
| `check-layer-separation.sh` | OK — new=0 |
| `null-hatch.sh` | pass |
| action-vocabulary parity (`parity.test.ts`) | green — no action surface changed |

## Judgment

The unit is the smallest cut that closes the live defect, and every ceiling it
adds is set where the pre-change build fails it. The one thing I would flag to a
later session: the arrival and the management view are the SAME screen rather
than two, because PR1 must not build the screen router. A revisit therefore
sees "Your Cabinet is ready." above the management sections — true on a revisit,
but PR2 should decide whether the ending deserves to be shown once.

Reviewed by the author against the class-11 discipline; the bundle-boundary
defect above is the honest evidence that the mechanical gates alone were not
sufficient here.

---

## Addendum — four more defects, none of them caught by a gate

Written after the artifact above, and kept as a separate section because the
pattern is the finding: every one of these was green under `tsc --noEmit` and
the full vitest suite, and every one was found by *looking at the thing* or by
asking who else touches it.

1. **The bundle boundary** (in the body above). `/onboarding` returned 500 for
   every operator. Found by opening the page. Now a permanent sensor.
2. **Two voices for one row.** The arrival's "Connected tools" rendered
   `row.reason` directly — the raw `credential_absent` the rest of the product
   translates — and a different sentence from the journey card for a tool that
   *did* answer. `plainReason`/`sweepLine`/`dayOf` extracted to
   `lib/onboarding/sweep-line.ts`; both surfaces call them. Verified live.
3. **The World overlay.** This same component renders as a fixed panel over the
   pixel map. The dashboard arrival deliberately drops the card chrome; the same
   early return left loose text on the map with no panel and no collapse
   control. Found by asking who else renders the component. The World branch
   keeps its shell, its "−" button and a one-column layout; the arm was proven
   to fail against the shell-less version.
4. **A query string that is a camera.** The full-surface link was a bare
   `?more=1`, which replaces the whole query — on the World that is `z/x/y/iso`,
   so answering a question would have thrown away the operator's view of their
   own map. `fullSurfaceHref()` keeps what it finds.

Plus one merge defect, after `feat/wake-the-crew` (#359) landed: their new
`crew.ts` imports `isOnboardingComplete` from the module this branch split. The
merge was textually clean and every test passed; only `tsc` saw it. Both the
import and the test's `vi.mock` are repointed — and the mock is the half that
mattered, because a mock aimed at a module the action no longer imports leaves
the real disk read live behind a green pass.

**The honest conclusion for this unit:** the mechanical gates were necessary and
were nowhere near sufficient. Four of the five defects above are invisible to
every gate this repo runs, and the one class-11 question that earned its keep
was "what does the test environment guarantee that production does not?".

Gates re-run green on the merged tree: `pytest framework/onboarding/tests` 954
passed · `tsc --noEmit` clean · `vitest` 3685 passed · layer-sep new=0 · census
PASS · COG-4 binding OK · null-hatch PASS.
