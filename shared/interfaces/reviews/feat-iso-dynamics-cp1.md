# feat/iso-dynamics — checkpoint 1

## What this is

The iso world's DYNAMIC layer. Before this, `drawIsoDynamics` painted the
lighthouse lamp, the roof cutaway and (since PR #292) the product archipelago,
and nothing else — the world lost MOTION when it gained ownership of its art.
Two of the losses were not decoration: an officer could not be clicked anywhere
on the island, and a PENDING RUNG WAS INVISIBLE.

## The design decision, and why it is not a wiring job

`lifeStep` is ONE reducer for both kernels and stays that way. Its output splits
cleanly:

- **MEASURED, projection-independent** — a commuter's `progress` (0..1 along a
  road, engine-mapped by the reducer's own contract), the district they walk to,
  their verb bubble, a site's element/phase/witness, its CREW SIZE, each
  wright's action and swing frame, an apprentice's officer and spawn proof.
- **GEOMETRY, top-down by construction** — `roadPoint(t)`'s tile polyline, a
  site's `footprint` in TILES, a wright's perimeter tile, an apprentice's tile
  offset.

`lib/world/iso-life.ts` re-sites the first half on the second kernel's own
measured geometry: the commute walks the `main` lane the layout laid, the yard
is the great house's own lot frontage, a site sits on the first FREE lot of its
element's group (or wraps the standing building when every lot is taken), and
the pending mark stands at the sprite whose rung is moving. Nothing invents a
place the layout does not already know; anything unplaceable is REPORTED on the
issues channel rather than drawn somewhere arbitrary.

## Evidence

- 55 new arms in `iso-life.test.ts`, 7 in `pick.test.ts`, 1 in
  `projection.test.ts`. Whole suite: 2836 passed / 1 skipped, `tsc --noEmit`
  clean, `check-layer-separation.sh` new=0.
- **30 mutations, 30 red an arm.** Two came back GREEN first and both were real
  sensor holes, fixed rather than reported away:
  - `commuteRoad` taking `lanes[0]` instead of the lane keyed `main` — green
    because `LANE_SPECS` authors `main` first, so on every composed layout the
    two agree. The fixture decided the verdict, not the code. New arm drives a
    lane list in the other order.
  - the free-lot branch's ground squash — green because the aspect arm only
    ever drove `library`, which is the UPGRADE branch. An arm over one of two
    return paths is a sensor over half the function.
- **Browser-verified on a real dev server**, not asserted from a test:
  officer cards open from the island (`coo — officer`, `cto — officer` clicked
  directly under their own name chips); a commute walker clicked MID-WALK at
  23px/0.7s returned `cto — officer`; site cards read
  `library → wing — clearing (0%) · witness keyframe:census 2026-07-25` and
  `officer_dwellings → dwellings_5 — clearing (2%) · witness chronicle:iid:98596`
  — the second sited on a FREE residential lot, not on the four-year-old
  dwelling a naive lookup would have wrapped; pending plots measured at their
  two exact sanctioned hues (112 foam + 90 plank px in two clusters).

## Two defects found and fixed on the way

1. **The DOM name chips were placed with a TILE-space lift** (`y - 2.2`) under a
   kernel whose axes are coupled, so every chip landed 53px right and 26px up of
   its officer, and clicks aimed under a chip hit scenery. Measured, fixed, and
   the property it violated is now pinned in `projection.test.ts`.
2. **`districts` never reached the frame.** An officer walked the harbour road,
   arrived at the quay, and reappeared at the great house — the world animated
   the transition and discarded its result.

## Composition changes, both browser findings

- the cleared-earth pad covered 1.3%, then 6.2%, of its own ellipse and was
  invisible against speckled meadow. Density now scales with pad area
  (`PAD_DOT_AREA`), measured at 22.9% on the frame, and the coverage is pinned.
- eight fence panels round a 110px pad is not a fence. `hoardingPanels` follows
  the perimeter.
- the yard fan was purely hashed and clumped inside 50px, which made
  `layoutLabels` displace all five chips into an unreadable column. Spacing is
  by index now, with the same per-slug hash as the jitter.

## Deliberately NOT done

Fauna, chimney-smoke-beyond-the-great-house, and the voyage boat under iso.
Window glow and smoke ARE in. The live cabinet has NO `world-sites.jsonl` and
no `cabinet:world:presence`, so the construction and commute arms were proven
against an isolated runtime (its own redis on 6399, a scratch CABINET_ROOT that
shadows nothing live) carrying the REAL chronicle with synthesized presence.
That is stated rather than glossed.

Reviewed by the author against the world's own doctrine: every drawn thing
traces to a measurement; era styles, rung measures; an unmeasured value renders
as an honest absence; a check may never import what it tests.
