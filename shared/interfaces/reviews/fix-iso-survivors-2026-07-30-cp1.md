# fix/iso-survivors-2026-07-30 — checkpoint 1

Three defects an adversarial audit of the iso dynamics layer found, plus one it
did not, all landed in one unit because all four are the same class: a promise
in a docstring that the shipped world does not keep.

## 1. The vessel was pickable at the berth it had left (must-fix)

`drawIsoVoyage` re-seats the harbour's own boat sprite along its course, while
`scene.sprites` — the array the pick walks — keeps the composed berth
coordinates forever. Measured in a browser against the live org state with a
staged port call (7 days into a 14-day tacking window, hull 1,281 layout px from
its mooring): the drawn hull answered `ground` and a click on the EMPTY BERTH
answered `harbor_boat: packet_boat — metric 2`.

Fix: `PickWorld.isoMoved` — where a static ACTUALLY is this frame, by scene id,
handed over by the draw pass exactly as `isoFigures` and `isoSitePads` are.
`pickIsoSprite` takes the same map and tests the drawn position. Cleared before
every early return in `drawIsoVoyage`, like the cutaway's officer boxes, so a
frame that seats no vessel cannot leave a stale hit box on the water.

A moved sprite keeps its composed pick ORDER, which is exact at both ends of the
fold (the vessel is at its berth, the order the compositor sorted) and irrelevant
in between (open water, nothing else has a body). Re-sorting per click would be a
second depth answer free to disagree with the canvas.

## 2. A pending count ladder pegged its plot on a house that already stood (must-fix)

`pendingMarks` looked the element up among the DRAWN SPRITES first and fell back
to the lot rule — which is exactly the "naive find the structure for this
element" lookup `isoSitePad`'s own docstring names as the invisible error.
MEASURED on a composed hamlet (four dwellings, six residential lots): the mark
landed at (833, 818) — dwelling number one — while the free lot the fifth will be
raised on, (593, 762), showed nothing. The world said "this is about to change"
about a building that is not changing. Fabricated state is worse than absent.

Fix: the lot rule first (one rule, shared with the construction sites, so a
pending mark and the works that follow it cannot disagree), the drawn sprite only
for what has no lot — harbour kit (`berths`, `quay`, `harbor_boat`) and the lamp,
where `isoSitePad` returns null by construction and the sprite is the only honest
ground.

**Its own test pinned the defect.** An arm asserted the sprite's coordinates, so
putting the order right turned an arm RED. That is the finding, not the
reassurance: a mutation battery that only asks "can this fail?" scores an arm
aimed at a defect as healthy.

## 3. A left click on unmapped water did nothing (found while proving #1)

`onPrimary` opened `if (!target || target.kind === 'ground') return`, so the
honesty branch inside `openInspect` — commented "catch-all honesty: unmapped
pixels answer plainly (no dead clicks)" — was unreachable from the primary
channel. Measured: LEFT click on open water → nothing; RIGHT click on the same
pixel → "ground / water — carries no data". `pick.ts`'s reason for making
`ground` a PickKind member rather than a null was true of the type and false of
the product. The pan case was already handled by the drag guard one line up.

## 4. `faunaCard()` deleted — a card nothing could open (dead twin)

No production consumer in either kernel; its only callers were its own tests.
`PickKind` has no fauna member, so no click anywhere can name a creature. What a
click on a creature actually gets is the pick's `ground` card, which says
"carries no data" and is flagged decorative — the same promise
show-grammar §15.5 makes. Removed from the dead-export ratchet baseline
(shrink-only). When fauna is ported to iso the pick kind and the card land in the
same unit or neither lands.

## Evidence

- `npx vitest run`: 2872 passed, 1 skipped, 141 files. `npx tsc --noEmit` clean.
  `check-layer-separation.sh`: new=0.
- Mutation battery, every arm proven able to fail: sprite-first order (2 arms
  red) · lot fallback deleted (2 red) · handover ignored (2 red) · handover keyed
  by frame instead of scene id (2 red) · the dead click restored (1 red).
- Browser, real dev server against the live org state on a read-only overlay
  root, real mouse input, cards read back from the DOM: sailing hull →
  `harbor_boat: packet_boat (packet_boat) — metric 2`; empty berth → no vessel;
  open water, left AND right → `ground / water — carries no data`; the pending
  plot at the free residential lot, not on any of the four standing dwellings.
- What has NO unit sensor and is browser-proven only: the canvas→pick handover
  itself. `engine-canvas.tsx` is a PixiJS-bearing closure with no test harness in
  the tree, which is why the browser measurement is the primary evidence for #1
  and #3 and the grep ratchets are secondary.
