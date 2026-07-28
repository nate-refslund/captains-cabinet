# FW-019 checkpoint review — feat/onboarding-ordering-inversion cp3

Reviewed-Scope-Digest: ece1bddb38fadedfeda3d621c9199b6b94df249bf56313df46a162055637c6a8

Altitude → preset mapping CORRECTED after the sibling personal-preset landing
(`docs/plans/personal-preset-live-2026-07-27.md`) reached master.

## Why this is a correction, not a preference change

While this branch was in flight, `contributor`/`project` resolved to
`developer`. That was the closest FIT under a stated gap: every shipped preset
stood up a C-suite for a company the operator may not run, and
`presets/personal/` was a placeholder whose own README **forbade** activating
it. The generator printed that gap rather than hiding it.

The sibling landing activated `presets/personal` — no C-suite, Navigator /
Librarian / Reviewer, and its README opens *"someone who owns a project, not a
company. A developer inside a large organisation."* That is verbatim the rung
`contributor`/`project` names. With the gap closed, "closest fit" became the
**wrong** fit: `developer` is a flat copy of `work` and ships the C-suite this
altitude does not have — the exact defect the personal preset landed to remove.

## What changed

| Surface | Was | Is |
|---|---|---|
| `resolve_preset` | contributor/project → `developer` | → `personal` |
| printed next step | "no shipped preset is shaped for a low-altitude operator … presets/personal/ is empty" | "the personal preset is the one shipped kit with NO C-suite" |
| `test_altitude_selection_names_the_honest_gap` | asserted `developer` + the gap line | renamed `test_low_altitude_selects_the_no_c_suite_preset`; asserts `personal`, `NO C-suite`, and that `presets/personal/preset.yml` EXISTS |
| `hatch.sh do_set_preset` | single resolution via `--print-preset` | same, PLUS that landing's existence guard on the resolved slug |

Both statements the old assertion made are now literally false, so the test was
inverted rather than deleted, and it gained the arm that would have caught the
mapping pointing at an unpopulated preset in the first place.

## Merge resolution, stated

`cabinet/scripts/hatch.sh` conflicted three ways because master fixed the SAME
drift (hatch ignoring `cabinet.preset`) by extending the duplicated mapping.
Resolved by keeping the single resolution — which subsumes theirs, since
`resolve_preset` already honours `cabinet.preset` — and **adopting their
existence guard**, which mine lacked. Strictly better than either side.
`cabinet/config/cognitive-architecture-contract.yml` kept all three expansion
rows (ownership.py, local.py, estate.py).

## Evidence

* `pytest cabinet/scripts/tests/test_generate_instance.py` — 128 passed.
* census PASS at `247 <= 247` / `71411 <= 71411`; layer-separation OK;
  docs-track-code sweep GREEN.
* Two clean-room hatches of the committed tree re-run after this change: the
  `contributor` arm now activates `personal` end to end (`load-preset.sh`
  included), which is the integration proof the mapping points somewhere real.
