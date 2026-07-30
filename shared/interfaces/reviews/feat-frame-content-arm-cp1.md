# Checkpoint review — feat/frame-content-arm cp1

**Diff**: 11 files, 839 changed lines, staged off `origin/master` @ `4fd9b2b4`.
**Provenance of this artifact, stated first because it is the weakest part of it**:
this is a SELF-review. The session that wrote the code wrote this. It is not a
fresh-context panel and must not be read as one — this session is a subagent with no
agent-dispatch tool available, so the independent lens the doctrine prefers was not
reachable here. What follows is therefore evidence and attack, not a second opinion.
The independent lens is the CI run on the PR and whatever review the parent session
commissions.

## What the change is

The 2026-07-30 attack review proved a hole: **every arm in `frame-judge.py` compares a
lit frame with its DAY TWIN, and a twin carries a CONTENT defect exactly as the frame
does.** Corpus sand sprayed over land at 16.7% coverage passed all six arms, and
`PALETTE_FOREIGN_MASS` returned no finding either. This adds the non-differential arm
that shape of defect needs, plus the renderer capture door it requires.

1. `EngineCanvas` gets `groundOnly` (default off, nothing in `src/app` passes it): at
   boot it sets `visible = false` on `staticShadowG`, `dynShadowG`, `propLayer`,
   `placeholderG`, `dynG`, `fxG`, `weatherG`. Container visibility rather than a branch
   inside `draw()`, so every draw call, transform and filter stays where it was.
2. `frame-harness/main.tsx` takes it off `?ground=1`; `shoot.mjs` captures one ground
   twin per plain cell as `<stem>.ground.png` (the name `check_terrain` already looks
   for) through the SAME readiness path as the composite, extracted into `shoot()`.
3. `ambience.test.ts` emits `ramps_day` into `ambience-derived.json`; `ambience_py`
   grows `ramps(bucket)`. The alternative was a Python regex over `iso-terrain.ts` —
   a fourth copy of a colour table.
4. `frame-judge.arm_soil`: on the ground frame, over 16px tiles that are not entirely
   sea, the share of tiles where >15% of adjacent pairs step further than the widest
   rung inside any shipped ground ladder must be ≤ 45%.

## Evidence, every number run this session

| claim | command | result |
|---|---|---|
| the hole is real in the REAL renderer | mod-6 corpus sand injected into `terrainField` (land only), full re-capture, judge | determinism / ambience / grain / surface / grade / water / killswitch **all PASS** |
| `soil` catches it | same run | **RED** at day/dawn/dusk z1 and z2 — 59.7–90.0% against the 45% limit |
| `soil` is green on the shipped renderer | `frame-judge.py /tmp/wf-ground` | `GREEN · 62/62 arms pass`, exit 0; worst cell 23.92% |
| the injection was reverted exactly | `git status --porcelain -- src/lib/world/iso-terrain.ts` | 0 changes |
| every new arm can FAIL | 6 mutations, `__pycache__` purged, `PYTHONDONTWRITEBYTECODE=1`, restored | all 6 red the suite |
| suites | `pytest cabinet/scripts/world-capture/tests -q` | 98 passed |
| | `npx vitest run src/lib/world` | 49 files, 973 tests passed |
| | `npx tsc --noEmit` | exit 0 |
| | `check-layer-separation.sh` | new=0 |

The six mutations: `frame-judge.py` imports `raster` · a judge dropped from the
no-import list · the soil verdict always passes · soil UNJUDGED becomes a pass · the
min-tile guard removed · the ladder bound replaced by a constant.

## What I attacked in my own work, and what I found

* **Is the sensor wired to the live artifact?** `soil` reads the frame the SHIPPED
  `EngineCanvas` renders, from the same `settled()` path as the composite. It is not a
  re-derivation. Verified by injecting the defect into the renderer rather than into
  the PNG.
* **The degenerate end.** A frame with no ground → `judged < SOIL_MIN_TILES` →
  UNJUDGED, non-zero exit, with a test. A manifest with no `ground` key → UNJUDGED,
  with a test. Neither is a silent pass. Measured minimum on the shipped renderer is
  248 tiles against a floor of 100.
* **Is the floor honest?** Worst lawful cell 23.92%, weakest catch 59.7%. That is
  **2.5x either side of the 45% limit and it is the thinnest margin in this file** —
  `SURFACE_EXCESS` claims a factor of 14. Stated rather than dressed up. It is the
  margin the world's own dressing density allows: at day z0.5 most judged tiles hold a
  coastline or a dressing sprite.
* **Two measured holes, both in the docstring and the README**: night is uncovered (the
  shipped night grass ladder steps 40/channel by itself, so the derived bound has no
  purchase — the same defect reads 0.3-0.4%), and z0.5 is unproven in either direction
  (the injection reached 0.27% of that frame, so the cell tested nothing).
* **Did I move a threshold to make something pass?** No threshold in this file was
  changed. `SURFACE_EXCESS` stays 0.12.

## Findings from the attack review that this commit also closes

* **A false claim on the claim surface.** `frame-judge.py` cited the `surface` arm
  staying "over 10% down to 0.05% coverage" as detection evidence — but the limit is
  12%, so 10% is a PASS. Re-measured on this file's own chroma-veil fixture: RED at
  0.20% (12.3%), PASS at 0.18% (11.3%), 3.7% at 0.05%. The real floor is ~0.19% and the
  docstring now says so.
* **The no-import law had a sensor on one of its four subjects.** It covered
  `mirror/checks/world_checks.py` only; `frame-judge.py` and `live-frame-probe.py` were
  uncovered. Now parametrised over all four, plus a discovery test so a fifth judge
  cannot arrive without a row.
* **A comment leaning on an inert guard.** `frame-judge.py` said `sync-checks.py
  --check` guards the mirror. It does — on a laptop that has the private source. In CI
  it prints SKIPPED-NO-SOURCE and exits 0 without diffing. The comment now says that.

## What this does NOT do

* Does not wire `check_terrain` / `check_on_road` / `check_paint_fidelity` onto the new
  ground layer. The door is open; they are not through it. `check_terrain`'s
  `_is_water`/`_is_sand` are absolute-colour predicates fitted on daylight (night sea
  fails `b > 80`), so it would have to run day-only like `grade` — real work, not a
  wiring change.
* Does not touch the two id buffers, so `check_depth_order` and `check_shadows` stay
  blocked.
* Does not pin the branch-protection context set (the open P1 from the same review).

**Verdict: approve to land, with the two `soil` holes and the thin margin recorded in
BACKLOG.md and in README.frame.md rather than smoothed over.**
