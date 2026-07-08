# world-aesthetic — mechanical aesthetic ratchets for Cabinet World

Six deterministic, stdlib-only (python3.12, no Pillow/numpy) gates that catch
the recorded Cabinet-World failure classes *mechanically* — no LLM judge in
the loop. A renderer change that reintroduces a rejected look goes red in CI,
exactly like a broken test.

```
python3.12 cabinet/scripts/world-aesthetic/aesthetic_gates.py \
    --map world.map.json --render out.png --labels out.labels.json \
    --palette cabinet/scripts/world-aesthetic/calibration/palette.json \
    --bounds  cabinet/scripts/world-aesthetic/calibration/clustering_bounds.json
```

Exit codes: `0` pass (warnings allowed unless `--strict`), `1` at least one
error finding, `2` unusable invocation. Findings JSON
(`cabinet.world.aesthetic-findings/v1`) goes to stdout and `--out`.
Calibration files are passed **explicitly** — a ratchet must never change
verdicts because a file appeared next to it. A gate whose input is missing is
*skipped with an info finding*, never silently dropped; a gate that crashes
emits `GATE_CRASH` (error) without taking the others down.

## The gates

| Gate | Input | Error codes | Failure class caught |
|---|---|---|---|
| `edge_continuity` | map | `EDGE_MISMATCH` | terrain seam breaks — autotile edge tiles placed incompatibly |
| `connectivity` | map | `CONNECT_DOOR_UNREACHABLE`, `CONNECT_ANCHOR_UNWALKABLE`, `CONNECT_NO_WALKABLE`, `CONNECT_NO_ANCHOR` | building doors unreachable from the map anchor |
| `scale_lint` | map | `SCALE_MISALIGNED`, `SCALE_48PX_SOURCE`, `SCALE_NON16_SOURCE`, `SCALE_ENTITY_BAND` | off-16px-grid regions; the giant-barn class (48px-scale LimeZu variants in a 16px world); mis-scaled actors outside the 16..32px charset band |
| `label_overlap` | labels (+render) | `LABEL_OVERLAP`, `LABEL_SPAM` | label spam — colliding boxes / area blankets per zoom (`chrome: true` boxes are sanctioned HUD) |
| `palette_coherence` | render + palette calibration | `PALETTE_FOREIGN_MASS` | foreign-color mass vs the positive-corpus palette (UI chrome rects excluded via `--ui-rects`) |
| `clustering` | map and/or render + bounds calibration | `CLUSTER_SCATTER`, `CLUSTER_NO_CLEARING`, `CLUSTER_FLAT_VOID` | the scattered-props class — props uniformly sprinkled on an untextured field (Clark-Evans R / open-space ratio on map data; flat-block & dominant-color mass on renders) |

## Schemas (defined here first; the renderer conforms to these)

* **Map** `cabinet.world.map/v1` — full spec in `gates/_common.py`. Minimal
  shape: `tile_size`, `width`/`height` (cells), `anchor` `[x,y]`,
  `sheets` (per-sheet native `grid` px + optional `autotile` blocks), and
  `layers: [{name, kind, tiles: [{sheet, region: [x,y,w,h] px, x, y}]}]`.
  Layer `kind` drives walkability/blocking defaults (`terrain`/`path`/`door`
  walk-positive; `building`/`prop`/`collision` blocking by footprint;
  explicit `walkable` on tile or layer overrides; doors punch through).
* **Autotile conventions** `gates/data/autotile_conventions.json` — the
  LimeZu blob/wang sheet-layout convention **encoded as data**: each block
  cell is a 3×3 primary/secondary subgrid from which the four side
  signatures derive; adjacent tiles must present equal facing signatures.
  Unknown regions degrade to wildcard + info finding, never false errors.
* **Labels** `cabinet.world.labels/v1` — see `gates/label_overlap.py`:
  `{render: {width, height}, labels: [{id, text, zoom, rect, chrome}]}`.
* **Palette** `cabinet.world.palette/v1`, **bounds**
  `cabinet.world.clustering-bounds/v1` — derived-numbers-only calibration
  files under `calibration/` (committed).

## Calibration corpus & licensing (why `corpus/` is gitignored)

`corpus/positive/` holds official LimeZu showcase scenes (licensed art) and
`corpus/negative/` the Captain-rejected build screenshots + two synthetic
scatter renders. **Licensed pixels are never committed** — `.gitignore`
excludes `corpus/*` except `corpus/manifest.json` (sha256 + provenance for
every image). Only code, the manifest, and derived-number calibrations are
tracked.

* `build_corpus.py synthetic|manifest|verify` — regenerate the synthetic
  negatives, rebuild the manifest, verify corpus bytes against it
  (currently 14/14 OK).
* `calibrate.py palette|clustering|prove|all` — fit `calibration/*.json`
  from the corpus. Palette floor semantics: a quantized bin joins the
  palette when it reaches `min_bin_share` in **at least one** positive
  (per-image floor — a merged-mass floor let big images starve a small
  positive's colors and broke self-consistency).

## The prove-it contract (clustering)

Enforced twice, mechanically:

1. `calibrate.py prove` — every corpus **negative** must trip an image
   bound, every **positive** must trip none; synthetic scatter maps (seeds
   mirroring the corpus scatter renders) must trip the map bounds while a
   held-out clustered layout passes. Exit 1 on any violation.
2. `tests/test_world_aesthetic_clustering.py` — the same separation as
   pytest against the **committed** calibrations, plus corpus-independent
   synthetic cases so a clean clone (no corpus) still proves the mechanism.

## Tests

```
python3.12 -m pytest cabinet/scripts/world-aesthetic/tests -q   # 58 tests
```

## Import contract

`cabinet/scripts/gates` is a pre-existing top-level package. This dir's
`gates/` package is therefore **never** imported as `gates` — everything
(runner, calibrate, tests) loads it via `_loader.load_gates()` under the
unique module name `world_aesthetic_gates`. No `sys.path` mutation anywhere.
