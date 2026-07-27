# Checkpoint 16 — the vessel on the pier (iso-port-composition)

Captain, 2026-07-27, on a rendered hamlet frame: *"is it on purpose that the
ship is ON the ground and not water?"*

## What was actually wrong

The sprite in the Captain's screenshot is `boat_fishing` — the single-masted
craft with cargo crates — and it comes from **`dressLanding`
(iso-layout/dressing.ts)**, not from the harbour stage. `dressLanding` puts it
at the reference's own offset `cove.x + 122` (compose.py:1158, "east of the
pier head"). In this port the pier is rooted at `cove.x + 104` and is 44 to
58px wide, so that column is **on the planks**, and the boat was drawn lying
along them.

The premise I was handed — that the defect is the org's vessel at
`harbour.ts:537` — is **wrong on the measurement**, and the measurement is
below. That vessel's contact patch was in open water on 1591 of 1600 cases. It
still carried `overWater: true` as a hard-coded claim with no sensor on it, and
it is fixed here too, but it is not what the Captain saw.

## Measured, 80 seeds x 4 eras x 5 quay rungs = 1600 layouts

Contact patch = ../projection's ground diamond, probed the way
clearance.footprintOnLane probes it. Land = `coast.landAt`. The probe
cross-checks every verdict against the module's own `inOpenWater` (0
disagreements across the after run), so it is not a fourth predicate.

| emitter | before (deck / pier / land / water) | after |
|---|---|---|
| `dressing:boat_fishing` | 618 / 982 / 0 / 0 — **1600 beached** | 0 / 0 / 0 / 1600 |
| `dressing:buoy` (n=3200) | 741 / 0 / 11 / 2448 | 0 / 0 / 0 / 3200 |
| `dressing:boat_rowing` | 30 / 0 / 0 / 1570 | 0 / 0 / 0 / 1600 |
| `harbour:harbor_boat` | 0 / 0 / 9 / 1591 | 0 / 0 / 0 / 1600 |
| `harbour:mooring_post` (n=6400) | 111 / 0 / 0 / 6289 | 0 / 0 / 0 / 6400 |

Nothing was dropped to get there: every craft still draws on all 1600 cases.
The dock kit (crates, barrels, nets, crab pots) is unchanged and still stands
on the deck, which is what a working dock looks like.

## The fix

1. **`overWater` is measured, never declared.** It means one thing — "does not
   stand on the island's ground" — and every emitter now computes it from
   `coast.landAt` at emit time. The vessel's hard-coded `true` is gone.
2. **A second flag, `afloat`**, on `HarbourItem` and `DressItem`: "must lie in
   OPEN water". `inOpenWater(coast, timber, at, size)` decides it on the ground
   diamond — clear of land AND of the wharf deck and the finger pier's planks
   (`onWharfDeck`, `onFingerPier`, from quay.py's own geometry, fascia
   included). The dock kit is deliberately NOT afloat.
3. **The vessel is berthed by search, not by offset.** `BERTH_STATIONS` along
   the pier's run x `BERTH_SIDES`, offset laterally by
   `width/2 + beam + BERTH_GAP`, then `ANCHOR_DEPTHS` when there is no pier;
   the first candidate inside the harbour extent AND in open water wins; none
   passes → no vessel, the same rule the jetty root already follows. The extent
   moved above the items for this, and its value is unchanged (it reads only
   inputs).
4. **The landing drifts.** Each craft walks away from the cove's centre
   (LANDING_DRIFT_X/Y, smallest move first), resampling its own column's
   waterline, until `openWater` passes; none passes → not drawn.
5. **Mooring posts resolve their own column's waterline.** Both rows were laid
   off the pier column's `waterBase` across a shore that falls up to 250px over
   the 152px between them — the same defect the jetty root and the wharf
   material were fixed for earlier today.

## Two new audit arms (auditLayout)

- `waterClaim` — `overWater === !coast.landAt(base)` on every emitter carrying
  the flag. Deliberately the weak arm: it passes for a crate on the deck, and
  it passed for the beached boat, which is exactly why the second one exists.
- `beached` — everything `afloat`, plus every mooring post, must satisfy
  `inOpenWater`. Runs whether or not a harbour was built.

Both ride in `capture.test.ts`'s capture harness and print from `emit.ts`.

## Mutations run (scratch copy of the tree, one at a time)

| mutation | result |
|---|---|
| MH31 `vessel-fixed-offset` — restore `jEnd.x - 132` + hard-coded `overWater` | RED: open-water arm, drop arm, `beached` |
| MH32 `moorings-shared-waterline` | RED: mooring arm, `beached`, negative twin |
| MH33 `kit-flag-inverted` | RED: `waterClaim`, per-column waterline arm |
| `landing-unchecked` — authored offset, no `openWater` test | RED: drift arm, drop arm, both audit arms |
| `landing-nodrop` — emit the last candidate rather than nothing | RED: drop arm |

MH32's first run left my own mooring arm GREEN — it asserted the consequence
(no post on the deck) on seeds where the old rule happened not to produce one.
It now asserts the RULE (each post's y = its own column's waterline + 116 +
row*52) with a non-vacuity count, and fails.

Hard-CODING the kit's `overWater` to `true` is green, and correctly so: no kit
item's base lands on land on any measured seed, so that edit tells no lie.

## One thing I could not fix here — check_shadows is fail-open

`--mutate no-shadows` deletes every shadow in the frame and `check_shadows`
still returns PASS on the hamlet fixture. It scores a sprite as casting when
the ground at its foot is darker than a ring `max(70, w*1.5)` out, so it cannot
tell a shadow from a MATERIAL change — anything standing on water, soil or
timber beside bright grass scores as shadowed. Its noise floor has reached its
own 55% floor:

| tree | mutated score |
|---|---|
| 40eff57e | 33/71 = 46% (red, nine points of margin) |
| 2669f2fc (concurrent lane/smoke wave) | 35/65 = 54% (red by ONE sprite) |
| this change (two boats stop standing on the pier) | 36/65 = 55% — **GREEN** |

The world change is right and was verified by eye; the CHECK is what is broken,
and its fix reaches `checks/world_checks.py` and its byte-identical mirror,
which this branch does not own. So: the `no-shadows` row moved to the `camp`
fixture, where it is red with a nine-point margin, and a **pinned-defect arm**
now asserts the hamlet fail-open with these numbers, so the hole lives in the
suite rather than in a report nobody re-reads. That arm goes RED when the check
is fixed, which is its purpose.

## Verification

- `tsc --noEmit` clean.
- `vitest run src/lib/world` — 737 passed, 45 files.
- `pytest cabinet/scripts/world-capture/tests` — 13 passed (includes
  `sync-checks --check`; the mirror is untouched).
- `capture.py --state hamlet` GREEN 12/12; `audit: … waterClaim 0, beached 0`.
- The meta `checks/verify.py --render` on the after frame: GREEN 12/12.
- Eye: `designs/harbour-vessel-{BEFORE,AFTER}-2026-07-27.png` in the meta
  workspace, plus `-captainzoom` crops of the Captain's own frame region.

## Shared files touched

`iso-layout/dressing.ts` (DressItem, DressCtx, dressLanding only),
`iso-layout/index.ts` (harbour import, the landing's `openWater` closure,
auditLayout), `world-capture/emit.ts` (prints the two new arms),
`capture.test.ts` (harness assertions + the shadow arms). The concurrent wave
committed as 2669f2fc before I landed, so none of these were dirty at edit
time.
