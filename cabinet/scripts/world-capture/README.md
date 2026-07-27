# world-capture — the verification bridge

Compose a world state with the real `composeLayout`, draw a real frame, and run
the twelve invariants in `checks/world_checks.py` over its pixels.

```
python3.12 cabinet/scripts/world-capture/capture.py --state hamlet
python3.12 cabinet/scripts/world-capture/capture.py --state camp
```

To judge the state the org is actually in, rather than one of the two authored
fixtures — the question that had no offline answer until 2026-07-27, and whose
first run turned `check_on_road` red on two sprites both fixtures leave green:

```
curl -s -H "Cookie: cabinet_session=$TOKEN" \
     http://localhost:3100/api/world/engine > /tmp/engine.json
cd cabinet/scripts/world-capture
node --import ./resolve-ts.mjs live-state.ts --engine /tmp/engine.json --out states/live.json
python3.12 capture.py --state states/live.json
```

`states/live.json` is a SNAPSHOT — true the day it is taken and a lie a week
later — so regenerate it rather than committing one. Serve the route with
`CABINET_ROOT` pointed at a checkout that has `shared/interfaces/world-chronicle.jsonl`
(it is a gitignored runtime artifact); without it, or without the session
cookie, `eval` is undefined and every consumer sees a day-zero cabinet.

Writes to `/tmp/world-capture/<state>/`: `frame.png`, `frame.ground.png`
(sprites-free), `frame.ids.png` and `frame.idsrev.png` (forward/reverse paint
order), `frame.blueprint.json`, `assets/` (one PNG per frame the capture drew),
and `frame.verify.json`. Exit code is `verify.py`'s.

## Why it exists

The layout stage survived three adversarial rounds and nothing had ever *looked*
at it. `composeLayout` had no caller outside its own tests; "does the belt read
as framing" was answered by a density histogram; the twelve invariants had never
seen a composed island, because nothing emitted a blueprint. Every measurement
already taken was worth nothing until a frame could be judged.

It found a real defect on first contact: the harbourmaster's hut standing in a
ploughed plot (28 of 40 village seeds). Structures knew about lanes, water and
each other; nothing told them about the plough.

## The pieces

| file | what it is |
|---|---|
| `../../dashboard/src/lib/world/blueprint.ts` | Layout → the blueprint the checks read + an ordered draw list. Pure, no browser. |
| `emit.ts` + `resolve-ts.mjs` | node CLI around it (node ≥ 22 strips the TypeScript itself). |
| `live-state.ts` | `/api/world/engine` payload → a state fixture, through the SAME `engineStep` + `layoutStateFrom` the browser runs. Refuses an empty feed rather than emitting a hatch that looks measured. |
| `ground.py` | the procedural ground: `terrain.py`'s ramps, Bayer dither, furrows, flagstone — with a dependency-free noise source. Two ramps are NOT `terrain.py`'s and say so in place: `RAMP_DIRT_WORN` and `RAMP_GRAVEL`, the road ladder's middle rungs, which had no material until lane WIDTH stopped following that rung (2026-07-27). |
| `raster.py` | draws the frame, the ground layer and both id buffers; `--mutate` breaks one rule on purpose. |
| `capture.py` | the one command: emit → raster → verify. |
| `states/*.json` | world-state fixtures. Every rung is a real rung of that ladder in `cabinet/world/growth-ladders.yml`. |
| `ambient-nature.txt` | morphology that no rung entitles — trees, reeds, rocks. Hand-held on purpose. |
| `mirror/` | byte-identical copies of the checks and the offline wharf; `sync-checks.py --check` guards them. |

## The rules it is built to

- **A check may never import what it tests.** `raster.py` and `ground.py` are on
  the tested side of that line and are never imported by anything in `mirror/`.
- **`justified` is derived from STATE, never from what was drawn.** The offline
  compositor adds a name to its justified set in the same breath as it places the
  sprite, which makes `check_state_traceable` a tautology. Here, removing a count
  removes the entitlement — so an unentitled sprite really does show up as an
  orphan.
- **`layers` is filled by whatever paints.** Paint order includes shadows and only
  the rasteriser knows it; a guess would be a sensor wired to the wrong artifact.
- **Every arm is proven to fail.** Six mutations, each breaking one rule, each
  asserted to turn exactly one check red — `orphan-sprite`, `sprite-on-lane`,
  `no-shadows`, `reverse-depth`, `unpaved-square`, `ghost-sprite`.
- **Judge at scale 1.0.** `--scale` is for eyeballing. `world_checks.py` carries
  absolute-pixel constants, so a shrunk frame is measured at a different relative
  resolution: at `--scale 0.45`, a frame that is green at 1.0 invents an on-road
  sprite, and `shadows` finds too few sample pixels per foot to judge — 2% of
  camp's large sprites, which trips its judged-fraction floor and goes red rather
  than reporting a verdict it cannot support.

## In CI

- `cabinet/dashboard/src/lib/world/capture.test.ts` — composes both fixtures,
  renders, runs all twelve invariants, then the six mutations. It **fails rather
  than skips** without python + Pillow; a skipped world check is a disabled sensor.
- `cabinet/dashboard/src/lib/world/blueprint.test.ts` — the blueprint contract,
  the era-vocabulary resolution, and a 40-seed sweep asserting no structure
  stands in a tilled plot.
- `tests/test_ground.py` — the ground port's own claims, and the mirror's identity.
- `tests/test_meadow_feather.py` — the meadow shading has a feather, both renderers
  read the SAME one out of the draw list, and the blur is applied to the union
  rather than per blob. Its own negative twin runs in the same file: without the
  feather the mask steps 204/255 in one pixel, with it 3/255.

## Not here yet

`?iso=1` in the engine. This round builds the bridge and judges the layout; the
engine still renders the top-down path. `designs/iso-engine-port-plan-2026-07-27.md`
steps 3–4 are the wiring, and the blueprint emitter is what will hold the engine
and this still renderer to one description when they land.
