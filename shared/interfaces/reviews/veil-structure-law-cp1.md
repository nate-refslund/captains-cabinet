# Review — veil-structure-law cp1 (FW-019)

Day/night ambience replaced: opaque screen-space dither → position-independent
palette remap. Branch `veil-structure-law`, off origin/master `d9cc1494`.

## The defect, measured on live frames

`/world` captured at 1:1, z=1.60, at four pinned clocks (the clock is pinned
through `instance/config/platform.yml captain_timezone`, and every capture's
bucket is verified from the HUD clock chip, not assumed). The day bucket applies
no ambience at all, so it IS the baseline. Same crops in every frame; `grain` =
mean |Δluminance| between horizontally adjacent pixels; `fid r` = per-pixel
luminance correlation with the baseline over the whole canvas.

### Shipped — opaque dither (origin/master d9cc1494)

| bucket | sea dst | lum | grain | grass dst | lum | grain | roof dst | lum | grain | fid r |
|---|---|---|---|---|---|---|---|---|---|---|
| day (baseline) | 10 | 112 | 5.48 | 205 | 101 | 5.39 | 5 | 113 | 6.73 | 1.000 |
| dawn | 14 | 115 | 9.22 | 204 | 105 | 11.79 | 6 | 117 | 11.33 | 0.932 |
| dusk | 16 | 112 | 6.18 | 203 | 103 | 7.46 | 8 | 113 | 7.51 | 0.935 |
| night | 16 | 86 | **31.75** | 177 | 80 | **25.28** | 7 | 88 | **28.30** | **0.525** |

### Landed — position-independent remap

| bucket | sea dst | lum | grain | grass dst | lum | grain | roof dst | lum | grain | fid r |
|---|---|---|---|---|---|---|---|---|---|---|
| day (baseline) | 10 | 112 | 5.48 | 205 | 101 | 5.39 | 5 | 113 | 6.73 | 1.000 |
| dawn | 10 | 103 | 4.72 | 9 | 89 | 4.94 | 5 | 101 | 5.53 | 0.903 |
| dusk | 10 | 94 | 4.70 | 12 | 81 | 4.25 | 5 | 96 | 5.93 | 0.902 |
| night | 10 | 60 | 2.06 | 5 | 51 | 1.57 | 3 | 48 | 1.36 | 0.769 |

Night was 4.2–5.8× the art's own grain and threw away half the frame's per-pixel
luminance. It is now BELOW the art's own grain on every surface and twice as dark
as the dither managed (−52 luminance against its −26).

## Two premises corrected

The dispatch said grass went "from a handful of dither tones to 334 distinct
colours". Measured on the same frame and the same crop, the grass patch carries
**205 distinct colours with no ambience at all** — it is dense multi-tone art
under a non-integer zoom — and the night dither **lowered** the count to 177,
because a replace-dither deletes tones as well as adding three. The 334-vs-4
comparison was sea-crop-in-one-file against grass-crop-in-another. The defect is
real; the stated cause was not, and the arm it implies (`distinct count must not
grow`) passes the broken code.

The other obvious arm — "must not invert the luminance order of the ramps it
covers" — also passes: a uniform replace at coverage c composites to
`(1−c)·source + c·veil`, an affine map with positive slope. Both near-misses are
recorded in `ambience.test.ts`'s header so they are not re-proposed as the fix.

## The law

**Ambience is a function of the PIXEL, never of its POSITION.**

For a replace-dither the light removed and the grain added are the same quantity:
mean darkening is `c·|L_art − L_veil|` and injected edge energy is
`≈ 2c(1−c)·|L_art − L_veil|`, so `added grain ≈ 2(1−c) × darkening`. The art's own
grain is 5–7, so a dither can buy 5–7 luminance of darkening before its grain
outweighs the art's. Night needs ~50. The mechanism was arithmetically incapable;
no coverage value was ever going to be the fix.

Parameters, all derived (`ambience.ts` header carries the tables):

1. **hue direction** — `WINDOW_SKY[bucket] / WINDOW_SKY.day` per channel, the
   art's own statement of that hour's light.
2. **depth** — the sky ratio, floored at the art's own deepest shade `RAMP_SHADE²`
   (0.439). Two ramps and not three because three blanks a ramp to a single tone
   (measured: 1 ramp 52/52 steps, 2 ramps 45/52, 3 ramps 31/52 with a 1-tone ramp).
3. **chroma** — a tint may not make a surface more colourful than a neutral
   darkening of the same depth already does. This pulls dusk from the raw sky
   ratio (which turned open water olive; a grey cobble tone became a 54-chroma
   orange, 6.4×) back to a near-neutral drain, independently reproducing the
   ratified 2026-07-29 call that "warmth at dusk is the LAMPS, not a tint over the
   whole sea".
4. **output set** — the palette gate's own native set (342 corpus bins widened by
   its `neighbor_radius`, 2952 bins). Bin centres alone collapse the sea ramp 5→2;
   the native set keeps all five, ordered. Every emittable colour is one the gate
   calls native, so the two old veil hue laws hold by construction.

## The arm, red then green

`ambience.test.ts` — 23 cases. Two new arms:

- **flat neighbours** — where two adjacent pixels were the same colour, ambience
  cannot have made them different. Zero tolerance.
- **grain does not grow** — aggregate over the eleven shipped ramps, bounded by
  the art's own grain measured in the same test. Aggregate because a colour map
  cannot create an edge but can steepen one (dawn/dirtWorn, +1.4%), and a
  per-ramp bound would need a picked tolerance.

Proved red against the shipped mechanism with `node_modules/.vite` purged, then
kept as a permanent inverted arm (the dither is inlined as a fixture, since a
live export whose only reader is a test is dead code with a green light on it):

| bucket | coverage | flat pairs split | grain vs the art |
|---|---|---|---|
| dawn | 0.08 | 1805 / 12793 (14%) | 1.47× |
| dusk | 0.16 | 3448 / 12793 (27%) | 2.00× |
| night | 0.42 | 7815 / 12793 (61%) | 6.89× |

Dawn and dusk matter there: their hues were fixed the day before, and the
mechanism was still adding half again and double the art's grain underneath,
where no hue law could see it.

## Two other defects found on the same path

**`☀ sun` at 01:39.** Neither the bucket nor the veil label was wrong — the frame
carried the night veil's navies, so `night` resolved correctly. The chip is the
WEATHER badge (`data-world-weather`), and `sun` means doctor GREEN + probes
passing (`lib/world/weather.ts`). Its glyph was time-blind. The word stays (it is
the weather state); the glyph now comes from the same bucket function the frame is
lit by, so the HUD cannot contradict the clock beside it.

**Two bucket implementations, and the law-driven one was dead.** `lighting.ts`
`bucketForHour` takes its ranges from the parsed grammar `night.buckets`; it sat
on ratchet 11's dead-export baseline because nothing called it. The renderer
called `sprites-outdoor.ts` `bucketOf`, with the four ranges as literals. The
grammar's day/night law was configuring a function no frame ever ran. Twin
deleted, one implementation now; `DEFAULT_BUCKETS` is byte-identical to the
literals, so behaviour is unchanged today. Threading the grammar's actual ranges
through needs the grammar payload on `EngineCanvasProps` — recorded, not silently
closed.

## WebGL

The remap is a GLSL filter with no WGSL twin, and `app.init` now pins
`preference: 'webgl'` (Pixi's own priority is webgl-first, so nothing changes
today). A shader is only ever verified by looking at a browser capture; a second
one nothing runs cannot be. On any other renderer `ambienceFilter` returns null
and the canvas raises a HUD render issue rather than drawing daylight at midnight.

## Gates

- `npx tsc --noEmit` clean
- dashboard vitest **2881 passed / 1 skipped, 140 files**
- `cabinet/scripts/check-layer-separation.sh` — new=0
- `python3.12 -m pytest cabinet/scripts/world-aesthetic/tests -q` — 91 passed, 5 skipped
- A13 parity — OK, 353 rows
- ratchet 11 baseline SHRANK by two entries (`terrain-pattern.ts -> NIGHT_VEIL`,
  `lighting.ts -> bucketForHour`), never extended

## Known, named rather than discovered later

Dawn (0.88) and dusk (0.82) are shallow because the art's own sky table says they
are, so at a glance they read close to day. Both are still strictly more of a
dawn and a dusk than what shipped, which had dawn *brighter* than noon (115 vs
112) and dusk identical to it. Whether the day cycle should be more stylized than
the art's sky table states is an aesthetic direction call, not a bug fix, and it
needs the Captain's eye.
