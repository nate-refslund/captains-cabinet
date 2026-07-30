# Pointing the checks at what ships

`capture.py` runs the twelve world invariants over a frame **`raster.py` draws from
`composeLayout`'s blueprint**. That pipeline has no clock, no day bucket and no PIXI stage —
`grep -r 'veil\|clockHour\|bucket'` across this directory returned nothing before this file
existed. So the ambience remap, the weather layer, the killswitch wash and the glow layer sat
outside all twelve checks, at every zoom.

It was not theoretical. A dusk veil replaced **15.6% of every pixel in the frame** with one
apricot hue, on grass and water alike, three hours a day, at every zoom — and every arm stayed
green. The night ambience destroyed half the frame's structure (luminance fidelity 0.525,
grain 31.75 against the art's own 5.48) and no check saw it. Both were found by a person
looking at a picture.

**A check that judges a re-derivation of the render is testing the model, not the product.**

## What runs now

    # capture — 16 real composited browser frames + 12 sprites-free GROUND twins
    # (~1m15 local, ~2m50 on a runner)
    cd cabinet/dashboard && node frame-harness/shoot.mjs --out /tmp/world-frames --killswitch 1

    # judge (~1m40 local, 4m10 on a runner)
    python3.12 cabinet/scripts/world-capture/frame-judge.py /tmp/world-frames

`frame-harness/` mounts the **shipped `EngineCanvas`** — its PixiJS boot, its GLSL ambience
filter, its shipped atlases — under vite, with the clock, the zoom, the weather and the
killswitch pinned on the query string. It is not a route: `/world` is an authenticated Next
page behind redis and a live snapshot, and the one input that has to be forced here (the hour)
is server-stamped data in the product on purpose. Nothing under `src/` imports it, so it never
enters `next build`.

Two axes were blind and both are now swept: **the clock** (one hour from each of dawn / day /
dusk / night, pinned as an input rather than read off the wall clock) and **the zoom** (0.5,
1.0, 2.0, crossing three `lodTier` boundaries — `capture.py`'s own docstring says CAPTURE AT
SCALE 1.0 TO JUDGE).

The renderer is **bit-exact**: two captures of one URL differ in 0 of 960000 pixels, measured,
and re-proven every run. Every arm that compares a lit frame with its day twin rests on that.

**And it is bit-exact ACROSS MACHINES too**, which was not the expectation and changes what
these frames are worth. The arms were built statistical rather than golden-image on the
assumption that a GitHub runner's SwiftShader would disagree with an Apple GPU somewhere in
the low bits. It does not: the first CI run printed the same numbers to the decimal as the
laptop — ambience `mean 86.2/86.2`, grain `4.58` against `6.82`, killswitch saturation
`0.416 -> 0.236`. Pixi with `scaleMode: 'nearest'`, no antialias and integer-snapped sprites
leaves the two rasterisers nothing to disagree about. So **a frame captured in CI is portable
evidence**, and there is no cross-machine variance here that any tolerance should be widened
for.

## The twelve, per check

`✔ frame` = now runs on the real composited frame · `▢ blueprint` = stays where it is, and
that is correct · `✖ blocked` = would run on the frame, and cannot yet.

| # | check | verdict | why |
|---|---|---|---|
| 1 | `check_on_road` | ▢ blueprint + ✖ blocked | Needs the lane polylines (a declaration) **and** `frame.ground.png`, the sprites-free ground layer, to tell road from prop. The declaration half is blueprint-shaped forever. The pixel half is blocked on the capture door. |
| 2 | `check_stacking` | ▢ blueprint | Rect overlap between declared sprites. It reads geometry, not pixels; a frame adds nothing. |
| 3 | `check_sprite_opacity` | ▢ blueprint | Reads the ART FILES, never the frame. **Stated gap:** it therefore cannot see a sprite the renderer tints or fades at draw time. |
| 4 | `check_sprite_cutoff` | ▢ blueprint | Same — the asset, not the composite. |
| 5 | `check_palette` | ▢ blueprint + **`surface` on the frame** | Asset-level membership, and membership is the wrong question for a frame: `PALETTE_FOREIGN_MASS` asks whether a pixel is a corpus colour, never whether it is a plausible NEIGHBOUR of the surface it landed on. The dusk veil satisfied it **by construction** — every apricot pixel was a legitimate corpus sand tone, sprayed across open water. The frame-side answer is the `surface` arm, which asks the second half of the question by counting tones per tile, plus `ambience` + `grain` + `water`. |
| 6 | `check_state_traceable` | ▢ blueprint | Declared-vs-measured. No pixels at all; the declaration IS the subject. |
| 7 | `check_paint_fidelity` | ▢ blueprint + ✖ blocked | "A declared sprite that left no mark" needs the declaration. Its pixel half needs `ground.png` to fit this frame's own grade. |
| 8 | `check_era` | ▢ blueprint | Vocabulary vs era. Pure data. |
| 9 | `check_light` — **grade** | **✔ frame** | Runs on every real DAY frame, cropped to the island (see below). The first time any of the twelve has been put in front of a browser frame. |
| 9 | `check_light` — **lamp** | ▢ blueprint | "Lit iff the rung says lit" needs the rung. Correctly UNJUDGED on the frame path, and it does not claim the surface. |
| 10 | `check_terrain` | ✖ blocked, **door now open** | Wants `frame.ground.png` and refuses to fall back to the composite — which is right. The browser now EMITS that layer (`groundOnly`, `?ground=1`), and `soil` is the first arm to read it; wiring `check_terrain`'s own rim/island/coast sweeps onto it is the next step and is not done here, because its `_is_water`/`_is_sand` predicates are absolute-colour and were fitted on daylight (night sea fails `b > 80`), so it would have to run day-only like `grade`. Its water half is covered meanwhile by `water`. |
| 11 | `check_depth_order` | ✖ blocked | Needs `frame.ids.png` **and** `frame.idsrev.png`. Draw order cannot be recovered from a finished frame; it can be recovered from a forward/reverse pair, and only the renderer can emit them. |
| 12 | `check_shadows` | ✖ blocked | Needs `ids.png` + `ground.png` to find bare ground under each foot. |

Plus five arms that exist **only** on the frame path, because there is nothing in a blueprint
to point them at:

| arm | law | proven red against |
|---|---|---|
| `determinism` | two captures of one URL are identical | one pixel, in each channel separately |
| `surface` | **the neighbour law** — a screen-space pass may MERGE a surface's tones, never add one | the 2026-07-29 dither · a luminance-matched chroma veil at 0.4% that `ambience` and `grain` both pass |
| `ambience` | the shipped grade **is** the grade `ambience.ts` predicts for that hour | filter never applied · wrong bucket for the hour · the real 2026-07-29 dither |
| `grain` | ambience may not add structure the art did not draw | the dither · a pixel permutation (histogram unchanged) |
| `water` | ambience may darken water, never brighten or saturate it | sea repainted above the derived cap |
| `killswitch` | the red wash draws | the wash not drawing |
| `soil` | **the content law** — the ground may not step further between two adjacent pixels than its own shipped ladder does | the 2026-07-29 dither injected into `terrainField` and re-captured, which every arm above passed |

## The hole `soil` was built for, and what it closed

**Every arm above compares a lit frame with its DAY TWIN, and a twin carries a CONTENT
defect exactly as the frame does.** Proven 2026-07-30, in the real renderer rather than
synthetically: corpus sand `(212,156,84)` on a mod-6 diagonal, injected into
`terrainField` on land only, and the whole sweep re-captured. `determinism`, `ambience`,
`grain`, `surface`, `grade`, `water` and `killswitch` **all stayed green**, and
`PALETTE_FOREIGN_MASS` returns no finding on it either — every injected pixel is a
legitimate corpus tone, which is the same reason the original veil satisfied it by
construction. This is the 2026-07-29 defect class moved one layer down, from the
screen-space filter into the world.

`soil` reads the **sprites-free ground layer** — the shipped canvas's own `groundOnly`
pass, `?ground=1` on the harness, one extra capture per plain cell — and asks a question
with no second frame in it. `terrainField` quantizes a smooth noise field onto ONE
shipped `RAMPS` ladder, so two adjacent ground pixels can differ by at most that ladder's
own widest rung (23/channel at day, 48 dawn, 40 dusk, 40 night — read from the artifact
`ambience.ts` emits, so a re-lit world moves the bound with it). A tile where more than
15% of adjacent pairs step further than that is dithered; more than 45% of judged tiles
dithered is red.

| | worst lawful cell | the injected defect |
|---|---|---|
| day | 23.9% (z0.5) · 7.2% (z1) · 2.9% (z2) | — · **90.0%** · **88.8%** |
| dawn | 10.7% · 2.6% · 0.5% | — · **63.2%** · **59.7%** |
| dusk | 11.1% · 2.5% · 0.6% | — · **65.1%** · **61.1%** |
| night | 0.0% · 0.0% · 0.0% | — · 0.3% · 0.4% |

**Its two holes, measured in the same run and not deduced:**

* **Night is uncovered.** The shipped night grass ladder itself steps 40 per channel —
  `(60,52,36) → (52,60,76)`, the split-tone light plus the native snap taking the
  mid-tones blue while the dark end stays brown — so the derived bound is wide enough
  that the same defect reads 0.3–0.4%. Not fixable by moving a number: it needs a
  PER-LADDER bound, which needs the ground classified per pixel, which needs the id
  buffer the engine does not emit.
* **z = 0.5 is unproven, in neither direction.** The injection reached only 0.27% of that
  frame's pixels (against 5.5% at z1 and 19.9% at z2), so the ground at the widest shot is
  substantially not `terrainField` output and that cell tested nothing. It is not
  evidence that the arm is blind there; it is the absence of evidence either way.

## Where the numbers come from

**`ambience` has no tuned constant that decides anything.** It remaps the day twin's colours
through `ambience_py` — the port pinned to `ambience-derived.json`, which `lib/world/
ambience.ts` emits and `ambience.test.ts` pins to itself — and compares the two histograms.
Measured over 3 zooms × 3 lit buckets on the shipped renderer, worst cell of each column:

| | mean L | contrast | saturation | span |
|---|---|---|---|---|
| agreement | 0.1 | 0.6 | 0.001 | 3 |
| bound | 1.5 | 2.5 | 0.015 | 8 |

The bounds are a noise floor for the nearest-native snap disagreeing with the GPU on a tie,
not a quality dial. A filter that fails to apply moves mean by ~50.

**`grain` has no constant at all.** The bound is the day frame's own adjacent-pixel energy.
Measured: the shipped remap runs 0.30–0.68× it; the dither it replaced ran **4.0×** (sea 5.5 →
31.8). `ambience` reads the histogram and `grain` reads the structure — a pixel permutation
moves only the second, and there is an arm pinning exactly that so neither can become
decoration.

**`grade` is cropped to the island, and that is a composition fix rather than a widened
bound.** `check_light`'s bounds were fitted on `raster.py` frames where the island fills the
canvas. A browser frame is a camera: at z=0.5 the same island sits in a corner of open ocean
and the whole frame measures contrast 13.1 / span 58 against 19.8 / 145 at z=1.0. Same world,
judged as flat because most of the frame is sea. The box is derived from the shipped sea ramp,
never from a hand-picked rectangle.

## What this does NOT cover — said here rather than discovered later

* **`ambience` and `grain` judge the sun / killswitch-off sweep.** Both overlays draw ABOVE the
  ambience filter, so they are not remapped and the prediction drifts by their own mass —
  measured +0.8 mean under rain, +3.9 under fog. Judging them together would mean loosening the
  tolerance that makes the arm worth having. So the overlays have a sensor for the LAYER and
  none for its COMPOSITION with ambience.
* **`grade` and `water` skip killswitch frames.** The wash drains saturation 0.42 → 0.24 by
  design, which is the drained-of-colour failure `grade` exists to catch, and it repaints the
  sea so the water probe reports the frame unjudgeable. Both exclusions are coverage
  statements, not conveniences.
* **The weather layer is judged by `surface` and by nothing else.** It has no arm reading the
  overlay's own mass, and `ambience`/`grain` still hold it out; what `surface` adds is the
  COMPOSITION — an overlay is a per-colour pass too, so night-under-fog against a fogged day
  twin obeys the same law (measured 0.4%, identical to sun) and the killswitch wash measures
  exactly 0.0%. The twin has to carry the same weather: judged against a `sun` twin, fog reads
  13.2% and the law does not apply, because fog is not a per-colour map of the sun frame.
* **`surface` runs on the sun sweep only in CI**, because that is the sweep the job captures.
  Run `shoot.mjs --weather rain,fog,storm --killswitch 1` and it judges those too — measured
  green on all 18 of those cells. Two things go red on that sweep and are recorded rather than
  fixed here: `water` reports UNJUDGED on every rain and storm frame (both repaint the sea, so
  the probe finds no sea-ramp window), and `grade` reds on `day/storm` at mean L 94 against its
  floor of 95, which is daylight bounds meeting a deliberately darkened sky.
* **The DOM half of `/world`** — chips, cards, the HUD — is not on this canvas at all.
* **Six of the twelve are blocked on a capture door** (next section).
* **One state.** The sweep runs `hamlet`; `camp` and every future fixture are one `--state`
  away and are not in the CI sweep's budget yet.

## What the blocked six would cost

`raster.py` emits four artifacts beside the frame: `frame.ground.png` (sprites-free, pre-grade),
`frame.ids.png` (every layer as a flat colour in paint order), `frame.idsrev.png` (the same in
reverse), and the blueprint with `layers` filled in. Six checks read one or more of them, and
the browser emits none.

The engine's container tree makes the first cheap and the others real work:

* **`ground.png`** — **BUILT 2026-07-30.** `groundOnly` on `EngineCanvas` hides
  `propLayer`, the two shadow graphics, `placeholderG`, `dynG`, `fxG` and `weatherG` at
  boot and changes nothing else; the harness takes it off `?ground=1` and `shoot.mjs`
  captures one per plain cell as `<stem>.ground.png`, which is the name `check_terrain`
  already looks for. Expressed as container visibility rather than as a branch inside
  `draw()` on purpose: every draw call, transform and filter stays exactly where it was,
  so the ground pass is the SAME code the product runs. `soil` reads it. The pixel halves
  of `check_terrain`, `check_on_road` and `check_paint_fidelity` are now unblocked but
  not yet wired — see the `check_terrain` row above for what that costs.
* **the two id buffers** — every sprite would have to be drawn as a unique flat colour in the
  same pass, in the same order, twice. Pixi `tint` multiplies a texture rather than replacing
  it, so this means swapping textures, not tinting. That is the expensive half, and it unblocks
  `check_depth_order` and `check_shadows`.
* **screen-space blueprint geometry** — the checks measure declared rects against pixels, and
  under a camera those rects are in layout space. The engine already knows where each sprite
  actually landed (`PickWorld.isoMoved` carries exactly that, handed over by the draw pass).
  Emitting it is a readout, not a re-derivation — and re-deriving the camera transform in the
  judge instead would be the same defect this whole file is about, one level down.

`engine-canvas.tsx` is a ~3,000-line PixiJS-bearing closure with no test harness in the tree,
which is its own open backlog row. A capture door belongs in the same piece of work.
