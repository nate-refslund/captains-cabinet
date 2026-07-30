# world-cycle-ruling — checkpoint 1

**What.** The Captain's cycle ruling of 2026-07-30: dawn and dusk deepen and take a
split tone (cool shadow / warm light). Night is untouched. `cabinet/dashboard/src/lib/world/ambience.ts`
+ its test, the emitted artifact, and the Python twin that reads it.

**Why it is not the sky table any more.** Measured on live /world frames at a pinned
clock: dawn 89% and dusk 82% of noon — indistinguishable from day. Both were a strict
function of `WINDOW_SKY[bucket] / WINDOW_SKY.day`. The Captain was shown that, told the
shallowness came from the art's own numbers, and ruled the cycle stylized beyond them.
`CYCLE_SHADE` / `CYCLE_TONE` / `CYCLE_CURVE` carry that ruling, named and dated in place
so a later session does not "fix" them back.

## Measured, live frames, 928x852 at z=1.60 (same island, same seed, same zoom)

| bucket | mean L before | after | grain vs art before | after | fidelity r before | after |
|---|---|---|---|---|---|---|
| day (baseline) | 100% | 100% | 1.00x | 1.00x | 1.000 | 1.000 |
| dawn | 89% | **68%** | 0.91x | 0.65x | 0.885 | 0.879 |
| dusk | 82% | **56%** | 0.83x | 0.52x | 0.880 | 0.856 |
| night | 48% | 48% | 0.35x | 0.35x | 0.815 | 0.815 |

Warmth (mean CIE Lab a*, red axis, against the same frame with no ambience), split by
the baseline pixel's own luminance:

| bucket | lit half before | after | shadow half before | after |
|---|---|---|---|---|
| dawn | +1.8 | **+9.1** | +2.2 | +8.8 (b* -4.3 → **-9.7**, cooler) |
| dusk | +0.6 | **+17.6** | +1.4 | +16.2 (b* -1.0 → **-16.1**, cooler) |

Night's PNG is byte-identical before and after (`cmp` clean), which is the whole of the
"night is unchanged" claim.

## Bounds

Kept, unchanged: the depth floor at RAMP_SHADE² (one ramp deeper blanks a shipped ramp);
the output set is the palette gate's own native set; no ramp blanks or inverts; grain may
not exceed the art's own; nothing brighter than open water; the adrift signal hue is
never emitted; ambience is a function of the pixel and never of its position.

**Replaced, with the finding stated in the module:** the chroma clause. Its reference was
a colourless darkening of the same depth, so any illuminant colour registered as painting
— at the ruled depths it admits t = 0.03-0.05, a grey cobble coming out #545454, exactly
neutral. It is not a tight bound on warmth, it is a statement that ambience must be
colourless, which the ruling contradicts. What it was DERIVED from is stated directly
instead: open water stays water — every sea tone keeps at least one palette bin more blue
than red, measured on the shipping path. Plus the clause it carried implicitly: a light
may only remove light, no channel factor above 1. Both are threshold-free and both bite
(arms: the raw dusk sky ratio fails, a flat warm multiply fails).

## Arms

24 -> 28 in ambience.test.ts. New: the ruling is not the sky table (both halves); night is
untouched, re-derived from WINDOW_SKY rather than pinned to a copied constant; the floor
clamps at a depth no bucket ships; open water holds and the two mechanisms that broke it
still break it; the warmth arrives and only on the lit half, with night's lit half going
the other way; the split changes hue and never depth; the LUT and the clamp measure the
same table. The inverted dither arms (flat-pairs-split, grain-vs-art) are untouched and
still fire on all three buckets.

## Pre-existing, NOT caused by this change, reported not fixed

- `CLUSTER_FLAT_VOID` fails the mechanical aesthetic gate on the NIGHT frame, flat_mass
  0.2633 > 0.2433 — identical value on master's night frame, which is byte-identical.
- Three `cabinet/scripts/world-aesthetic/tests` corpus tests fail once the gitignored
  corpus is actually assembled on disk. CI never sees them: it skips them for want of the
  corpus. Same result on master with the change stashed.
- The red "1 Issue" pill in every captured frame is the Next.js DEV overlay, not the app:
  `Console Error: eval() is not supported in this environment`. React's dev build wants
  eval and `/world` ships a deliberately eval-free CSP (next.config.ts, pinned by ratchet
  8). Production is unaffected. Not a defect and not to be "fixed" by widening the CSP.
