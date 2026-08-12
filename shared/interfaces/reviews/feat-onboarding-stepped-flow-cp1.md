# Checkpoint review — feat/onboarding-stepped-flow (cp1)

Reviewed-Scope-Digest: d58e616586342717150ac4b390535994d9fdaec9046ee9b03f1e93a4c4b16800

## What this lands

The `/onboarding` first run becomes a **stepped, plain, modern flow**, and the
one seed question splits into **three**.

**Core** (`framework/onboarding/journey.py::answer_seed`): now carries, on the
seams the tree already reads —
- `seed` → the operator's **role** (what they do), the journey seed genesis reads;
- `purpose` → the **dream**, stored under `mission.purpose` (the block
  `genesis._mission_fields` quotes on every proposal card) — composed, not forked;
- `start_preference` (`point` | `decide`) → the one genuinely new field.

Discovery now reads role AND dream (both the operator's own words). A role-only
answer writes no `mission` block and no `start_preference` — an empty mission
would be a claim the operator never made.

**Surface** (`cabinet/dashboard`): `journey-card.tsx` rewritten as a guided
wizard over the welcome front — one question per step, a "window-pane" progress
rail (`role → dream → start → window → charter → result`), Back/Next, a calm
dark visual system, `min-h-11` targets, `aria-current`/labelled controls. The
stepping logic is extracted into a pure, framework-free `lib/onboarding/wizard.ts`
so Back/Next-preserves-values and the payload composition are tested without a
DOM. The charter → scan → dividend → briefing back half, and every honesty
section (identity picker, ranked salience, off-target refusal, withheld
citations, purge, feedback), are preserved.

**The `decide` branch is honest.** Self-exploration needs a connected source.
Where the core offers `gather_connectors`, the branch wires to it; where nothing
is connected (the egg's default), it says so plainly and routes to the folder as
the concrete start. See the gap below.

## Class-11 four questions (does the sensor test the control?)

1. **Does the new arm FAIL against pre-change code, both directions?**
   - The 3-question round-trip test asserts the POST body carries `seed`,
     `purpose` AND `start_preference`. Against the old single-`seed`
     `answer_seed`, `purpose`/`start_preference` were never persisted — the
     Python arms (`test_answer_seed_splits_into_role_dream_and_start_preference`,
     `..._drops_an_unrecognised_start_preference`) fail on the old handler.
   - `test_cards_condition_on_role_and_dream_seams` asserts the dream ADDS a
     subject (`ryokan`) that is ABSENT in the role-only probes — it fails if the
     mission seam is dropped.
   - `wizard.test.ts` pins that `seedRequest` OMITS `purpose` on a blank dream
     and is `null` until role+preference exist — it fails on a version that
     always sends `purpose` or accepts an empty role.
2. **Degenerate end?** Role empty/whitespace → `canAdvance('role')` false and
   `seedRequest` null (tested); unknown `start_preference` → dropped by the core,
   not stored (tested); blank dream → no mission block, `purpose` omitted from
   the wire (tested both layers); `decide` with nothing connected → honest panel,
   no fabricated `gather` button (rendered arm asserts `not.toContain`).
3. **What does the test env guarantee that prod does not?** The dashboard tests
   run in vitest `node` (no DOM), so stepping is proven as pure logic in
   `wizard.test.ts` and render output via `react-dom/server`; the true
   click-through is the Playwright run in the PR. The Python arms are hermetic
   (`tmp_path`, no net). The census/digest chain was measured on the committed
   tree, not asserted from memory.
4. **Is the sensor wired to the LIVE artifact?** `parity.test.ts` still compares
   the LIVE bridge `ACTIONS` set and `ONBOARDING_ACTIONS` against the core's
   `_act_core` dispatch — no new action was added (I extended `answer_seed`), so
   the vocabulary is unchanged and the parity sensor is intact. The
   hook-scripted render tests assert the component's REAL useState order with
   `Object.is`, so a hook drift fails loudly.

## Gates paid

- Census: `framework_production_noncomment_lines` 62861 → 62872 (+11 measured
  via `cognitive-architecture-census.py`; journey.py only, modules unchanged).
- COG-4 digest: re-bound in this same commit (the contract edit is in-scope; the
  onboarding modules are not).
- Layer-separation: 0 new violations. No product/person/score/killswitch tokens
  in the diff. `null-hatch` clean.
- `python3.12 -m pytest framework/onboarding/tests` → 854 passed, 1 skipped.
  Dashboard `vitest` → full suite green (incl. 54 journey-card + 12 wizard arms).
  `tsc --noEmit` clean.

## Named gap (a fork for the Captain)

There is **no onboarding-integrated connect-a-source UX**. `/integrations`
exists (Notion/Linear/API keys) but is not wired into onboarding
self-exploration, and `gather_connectors` has no dashboard trigger except when
`connectors.yml` pre-declares a source. The `decide` branch is therefore honest
rather than fake, and the connect-a-source flow is its own unit of work.
