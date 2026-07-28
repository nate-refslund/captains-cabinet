# Checkpoint review — iso-layout cp2: the three land/exclusion defects

Branch `iso-port-composition`, on top of `1954df5d`. Diff ~1115 LOC across
7 files, all under `cabinet/dashboard/src/lib/world/iso-layout/`.

## What this checkpoint is

Two independent adversarial reviews of the layout port (`/tmp/isoframe/
refute_correctness.md`, `refute_fidelity.md`) each measured the same three
defects and blocked. This lands the fixes plus the sensors that would have
caught them.

1. **Nothing stands on open water** — `place()`'s walk-inland (compose.py:530-539)
   and `snap()` (compose.py:870-883) were not ported. Ported into
   `clearance.ts` as `walkInland` / `snapInland`; `placeOnGround` now bookends
   the settle with the land test and returns null rather than a point in the
   sea; lots are snapped after relaxation; district anchors are snapped;
   `auditLayout` grew an `inWater` arm.
2. **The keep-out discs were declared and never enforced** — `free()` had only
   the lane term. It now carries the disc and water terms as compose.py:1213
   does, and so does the verge predicate.
3. **No painted mask was clipped to land except the pond, and the pond only at
   its blob centre** — lanes are cut into on-land runs (`Lane.runs` replaces
   `Lane.path`), and plaza / field / pond blobs are shrunk-to-fit or dropped.

Plus the dead sensor the brief named, and three others of the same shape found
while looking: the camp field-plot arm (passed on a fixture that omitted the
count), the "camp has one lane" arm (never looked at the coastline), and the
first version of the offline bridge below (painted whatever it declared, so it
could not see water under a lane).

## Self-review — what I attacked in my own change

- **Every new arm was proven able to fail.** Ten mutations, each disabling one
  rule, each recorded with the arms that went red, in the commit message. Two
  mutations came back GREEN and both are reported rather than buried: the
  `in_water` term is redundant with the pond's own keep-out disc (kept, with an
  arm pinning the dependency), and a land guard I had added to the lot
  relaxation guarded nothing measurable (removed rather than left as untestable
  protection).
- **The seed set was too weak and I changed it.** With the land rules deleted,
  four of five named seeds still passed — the compass anchors happen to be
  inland on the reference ellipse. The arm now shrinks the island through the
  public `coastline.radii` option, which strands the anchors on every seed
  (at hw<=360 the civic anchors are themselves offshore, which is the case that
  proves the walk inside `placeOnGround` is load-bearing).
- **The extent sensor does not co-design with the clip.** The clip probes a
  ~5px lattice; the test probes 90 rim angles plus a 7x7 interior grid, and a
  permanent arm asserts the extent sensor is strictly stronger than the centre
  sensor it replaces.

## Known-open, stated rather than hidden

- The layout still emits no region EXTENTS (`plaza [x,y,rx,ry]`, `fields
  [x,y,w,h]`), which `check_terrain` and `check_on_road` read. The offline
  bridge derives them from the blobs.
- The officer row fronts `LOT_LANES.west`, which is not the painted `west`
  carriageway — inherited from the reference, which paints those drives anyway.
  The era gate stops the camp case; the geometric case is a direction call.
- The forest enclosure ring, harbour, lighthouse and the rest of the unported
  stages are unchanged by this checkpoint. Planting is now much sparser than
  the stills, because the reference fills the rim with the ring and this port
  has no ring yet.

## Batteries, re-run for this checkpoint

- `npx tsc --noEmit` → exit 0.
- `npx vitest run src/lib/world/iso-layout/iso-layout.test.ts` → 74 passed.
- `npx vitest run` (whole dashboard) → 122 files, 2279 passed, 1 skipped.
- `cabinet/scripts/check-layer-separation.sh` → new=0.
- `checks/world_checks.py:check_terrain` through the offline bridge, 8 seeds:
  2 FAIL before / 8 PASS after.
