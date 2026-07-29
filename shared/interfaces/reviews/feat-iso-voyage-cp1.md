# feat/iso-voyage — checkpoint 1

**The law row this closes.** `harbor_boat_voyage` was the last row `law-render.ts`
recorded as unrendered for a reason that was about the RENDERER rather than the data:
"the VOYAGE BOAT is drawn by the top-down dynamics layer only … under iso there is no
vessel under way." Its course drift lines landed under iso in PR #292; the vessel did
not, and half a law painted is not the law.

## What changed

`lib/world/iso-lanes.ts` (pure): `isoBoatBerth(layout)` reads the berth the LAYOUT
already measured for `harbor_boat`, and `isoVoyageBoat(voyage, berth, sites)` folds the
server's own `voyageRender` progress into a position on the run out to the tacking
lane's berth. `BERTH_STANDOFF` and `VOYAGE_REACH` are the two numbers.

`engine-canvas.tsx`: `drawIsoVoyage` MOVES the harbour's own boat sprite. It draws no
hull.

## Three decisions worth reviewing

**1. It moves the pack's boat; it does not draw one.** The first version of this change
drew an owned hull from primitives — a ground-plane polygon, a mast, a sail — on the
reasoning that the top-down boat is a LimeZu crop and `/world` references zero LimeZu
files. That reasoning was right about the crop and wrong about the conclusion: the iso
layout ALREADY berths `harbor_boat` (`iso-layout/harbour.ts`, "the ONE craft with a
ladder behind it"), and `iso-pack.json` resolves it at every rung — `rowboat →
boat_rowing`, `packet_boat → boat_packet`, `steam_packet → bay_steam_packet`. A drawn
hull would have put TWO vessels in one harbour and invented pixels for the one thing the
pack does draw. The hand-drawn version was deleted.

**2. The mooring is the layout's measurement, not a derived offset.** The first version
also derived a mooring as a fixed seaward offset from the quay mouth. `harbour.ts`
already records why that shape is wrong — the reference's own authored offset "put the
hull on the wharf on 2 of 1600 (seed x era x rung) and it could never have done better
than luck, because a fixed offset from a pier whose length is a state reading cannot
know where the water is." It is now the berth that harbour's `inOpenWater` search
found. **No berth means no boat and no voyage**, which is the layout's own rule.

**3. The stand-off is measured, and the browser is why.** `drawDynamics` stops the boat
at 0.9 of the run. Ported verbatim, that put the hull INSIDE the berth's own ellipse on
the live cabinet — measured on a real dev server: the polads run is 2062 ground-px and
the isle's own ground is ~332, so a tenth of the run left the boat under the isle's
jetty and warehouse block, painted over. The voyage was correct in the data and
invisible on the screen. It now stops `BERTH_STANDOFF × site.hw` short — measured
against the thing it has to clear — with `VOYAGE_REACH` kept as a ceiling for a berth
close enough that the stand-off would not bite.

## Two renderer details

- **The vessel's shadow moved to the per-frame buffer.** Its ground diamond is skipped
  in `buildIsoSprites` and re-cast in `drawIsoVoyage`. The static shadow buffer is not
  rebuilt for a payload change under iso, so a boat that sailed would have towed a black
  ellipse left behind at the berth.
- **`drawIsoVoyage` is called from `drawIsoDynamics`, not from `drawIsoLanes`**, which
  returns early on an empty fan. The vessel belongs to the harbour; an org with no
  ratified product lane still berths a boat, and that pass now also casts its shadow.

## Evidence

- 49 arms in `iso-lanes.test.ts` (13 new). Mutations proven to red their arm: stand-off
  dropped · stand-off made a constant · run measured in screen space · reach ceiling
  removed · stand-off multiplier zeroed · negative clamp removed · join by first entry ·
  triangle fold removed · reach 0.9→1.0 and 0.9→0.0 · no-berth invents a berth ·
  no-berth invents a boat at the origin · flip never set · flip inverted ·
  `isoBoatBerth` by position instead of by kind.
- **Three mutations came back GREEN and the arms were fixed, not the mutations
  reported away.** (a) `isoBoatBerth` reading `items[0]` passed everything: a hamlet
  harbour emits exactly ONE item, so key-lookup and position-lookup are the same answer
  in the only fixture — a synthetic three-item harbour now separates them. (b) measuring
  the run in screen space passed every east-west fixture; the arm now includes a purely
  north-south run and asserts the EXACT gap. (c) removing the negative clamp was
  invisible until a berth closer than its own stand-off was added.
- Browser, real dev server, live cabinet payload with a staged port call putting polads
  in the tacking window: berth `(1234.6, 1385.9)` → polads berth `(3037.8, 1885.6)`,
  boat `(2674.7, 1785.0)`, ground gap to the berth centre 415px = `1.25 × 332`. A/B
  screenshots at the same camera show the vessel AT its berth when moored and GONE from
  the berth when tacking, and present in open water off polads.
- `npx tsc --noEmit` clean; `npx vitest run` 2851 passed / 1 skipped over 139 files;
  `check-layer-separation.sh` new=0.

## Not done here

The boat is not a pick target — parity with the top-down kernel, which does not make it
one either. Its state is readable on the chart table card (`lane_course_state`) and at
the lane berth it is sailing to.
