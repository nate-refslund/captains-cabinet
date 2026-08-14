# feat/first-mate-speaks-short — checkpoint 1 self-review

Seven units (U1–U7) from the Captain driving the full connected onboarding on
his own instance, 2026-08-14. Reviewed against the shipping code in this branch,
with every battery re-run here rather than trusted from a build log.

## What was measured, and with what

| Gate | Command | Result |
|---|---|---|
| onboarding core | `python3.12 -m pytest framework/onboarding/tests -q` | 995 passed, 1 skipped |
| whole framework | `python3.12 -m pytest framework -q` | 8167 passed, 30 skipped, 2 failed — see "pre-existing" below |
| dashboard | `npm ci && npx vitest run` | 3548 passed, 1 skipped, 170 files |
| types + parity union | `npx tsc --noEmit` | clean |
| layer separation | `cabinet/scripts/check-layer-separation.sh` | new=0 |
| census | `cabinet/scripts/cognitive-architecture-census.py` | PASS after the contract raise below |
| null hatch | `cabinet/scripts/null-hatch.sh` | exit 0, PROOF 1 PASS |
| live drive | dashboard dev server + a mock estate over TLS on localhost | all seven units exercised, screens 25–36 |

**Pre-existing, not this branch:** `framework/fidelity/tests/test_retro_shim.py::
test_reexports_constants` fails identically on a clean checkout of master on this
machine (verified by stashing every change and re-running). It asserts a model id
re-exported from a locally-installed retro pipe that is outside the repo, so it is
an environment artifact of running on a machine that has that pipe. Per-job CI is
the authority and is checked before merge.

## The census raise

`framework_production_noncomment_lines` 63700 → 64244 (+544, measured, observed ==
maximum, zero headroom). Raised VISIBLY rather than paid by a temporary allowance,
for the reason every row above it gives: these are permanent organs and an
allowance would promise a deletion gate that never fires. Zero new production
modules — every organ lives in a file the tree already carried.

## Class-11: does each new sensor test the control?

1. **Does the arm FAIL against pre-change code?**
   `test_the_body_is_exactly_the_join_of_the_sections` would pass trivially if
   `details` were empty, so `test_dropping_one_section_breaks_the_join` removes a
   section and asserts the join no longer equals the body — the sensor is shown to
   be able to fail. `test_a_guess_is_never_recorded_without_the_operator_s_tap`
   fails the moment any writer stores a guess. The dashboard's
   `sends NOTHING until the operator taps` fails if a render posts.
   `test_no_act_surface_is_a_dead_end` fails on the pre-change
   `orientation_offered` card, which carried no completion block.
2. **What does it do at the degenerate end?** Explicitly armed: no sweep
   (`test_a_card_with_no_sweep_still_leads_with_its_opening_move`), no name
   (`test_no_name_no_guess_and_the_open_ask_is_unchanged`), two lookalikes
   (`test_two_lookalikes_refuse_to_guess_and_say_why`), no seed
   (`test_a_journey_with_no_seed_never_re_fires`), an incomplete journey
   (`test_an_incomplete_journey_is_never_congratulated` plus the four-way
   predicate table), and an ordinary folder carrying no breadth caveat.
3. **What does the test environment guarantee that production does not?** The
   Python arms write their own sweep onto state rather than opening a socket, so
   they do not prove the sweep. That is deliberate — `test_search_probes.py` and
   `test_connector_read_lane.py` own the wire — and the live drive closes it: a
   real sweep over a real TLS socket, a real `declare_connector`, and a real scan.
4. **Is the sensor wired to the live artifact?** `journey-card.test.ts` imports
   `officerTitle`/`COORDINATOR_ROLE` and `journeyIsComplete` as LIVE objects, and
   `parity.test.ts` already parses the core's dispatch chain. The completion arm
   asserts `journeyIsComplete(state) === card.completion.complete` across the
   process boundary rather than re-stating either side.

## Adversarial pass — the three the brief named, plus two I added

**Can the identity guess auto-claim without a tap?** No, measured three ways.
`identity_question` only ATTACHES a guess; nothing in `research.py` or
`journey.py` writes `operator_identity` outside the `record_operator_identity`
action. `test_a_guess_is_never_recorded_without_the_operator_s_tap` asserts the
state carries no `operator_identity` and `who_and_when.operator.handles` is `{}`
after a guess has been rendered. The dashboard arm asserts a render posts nothing.
Live: after the sweep, `attribution` read `unresolved` for both connectors until a
chip was tapped, and then for exactly the one tapped.

**Does layering hide a caveat an arm pinned?** No: `card.body` is the JOIN of
`card.details` by construction, so the blob every non-folding surface renders is
byte-identical to what it was. Two arms hold it, one of which proves the join can
fail. The dashboard renders the headline PLUS the full fold, so headline ∪ fold ⊇
body. The one honest residual: the card has always printed the first TWO
cannot-know statements and carried the rest structurally on `entry.cannot_know`;
layering did not change that, and the arm says so rather than implying the printed
set is the whole set.

**Can a broad window bypass a sensitivity skip?** No, measured.
`window_breadth`/`window_refusal` decide only whether a ROOT is admissible;
`_scan_source` applies `_is_sensitive` to every relative path regardless of root.
`test_a_broad_window_cannot_bypass_one_sensitivity_skip` ratifies a whole-home
window and asserts the manifest opened `readme.md` and refused `salaries.csv` and
`.env`. Live on a sandbox home: 5 files opened, `compensation: 1` refused, the
dotfile excluded as hidden.

**(mine) Can the guess match the wrong person?** The three rules are stated and
exact-word — no prefix, no edit distance, no similarity — and
`test_a_look_alike_that_is_not_the_name_is_not_a_match` pins four near misses
(`hanako.tanako`, `h.tanaka`, `tanaka-corp`, `nakata`). Where two accounts match,
there is NO guess and the card says why. The residual, stated: a colleague who
genuinely shares the operator's name would be proposed — and the operator is the
one who answers, which is the same protection the picker always had.

**(mine) Can the auto re-fire send the operator's words out repeatedly?** No: the
re-fire is gated on three conditions together — the declared connector is the
SEARCH lane, the journey has a seed, and the last run stopped specifically for
`NO_SEARCH_TOOL`. An inventory connector declared afterwards sends nothing
(`test_an_inventory_connector_does_not_re_send_the_same_refusal`), and a closed
egress ceiling produces a different reason so it does not re-trigger.

## What I changed my mind about while building

* **The pre-fill nearly put a filler word in the operator's mouth.** The first
  live drive offered "actually" as the name of a thing to open, out of "the onsen
  rota is what actually hurts". Fixed at the right layer — discourse adverbs are
  stopwords by the same rule the list already applies, and they were polluting the
  search QUERIES too. I deliberately did NOT add the verbs from that one sentence:
  a stopword list fitted to one fixture is worse than a pre-fill the operator
  edits, and the field says "change it if it is wrong".
* **The name write nearly could not refuse a two-line paste.** The first version
  collapsed whitespace and THEN checked for control characters, so the check ran
  on a string the collapse had just repaired — a rule that could never fire. Strip,
  check, then collapse.
* **`completion.ts` must not reach the client.** It reads `node:fs/promises`, so
  importing it into the card would break the client bundle (observed as exactly
  that failure in a sibling clone's dev server). The shared predicate therefore
  lives in `wizard.ts` — framework-free — and `completion.ts` consumes it.

## What is NOT in this branch, stated rather than implied

* Telegram renders `card.body`, which is unchanged — so the layering is a
  dashboard affordance today and Telegram keeps the full blob. That is the correct
  fallback, not an oversight, but Telegram gains no headline.
* The World skin renders the same component and therefore gets all of this; it was
  exercised only by the surface-parity test, not by a live World drive.
* `record_operator_identity` still has no Telegram branch (the existing named
  exemption in `parity.test.ts` — a picker cannot fit in 64 bytes of callback
  data). The confirm chip does not change that: a Telegram identity confirm is its
  own unit.
* The completion handoff names two destinations by CONCEPT; only the dashboard
  maps them to routes. Telegram and the World do not yet.
