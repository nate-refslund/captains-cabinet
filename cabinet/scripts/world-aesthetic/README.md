# world-aesthetic — the Cabinet World aesthetic gate

The harness that stops another Captain-rejected build from shipping. Three
pillars, in order of authority:

1. **Mechanical-first.** Six deterministic, stdlib-only (python3.12, no
   Pillow/numpy) gates catch the *recorded* failure classes mechanically —
   no LLM in the loop, red in CI exactly like a broken test. Anything a
   ratchet can catch, a ratchet MUST catch; the judge is never spent on
   frames below the mechanical floor.
2. **Pairwise-calibrated judges.** The judgment half — "does this frame read
   like a finished, warm, professional pixel-game scene?" — is the **vision
   judge** (`judge/`): protocol in code, judgment via agents at call time,
   and NO verdict counts unless the judge first passes a hidden calibration
   set (every Captain-rejected frame ranked below every approved frame,
   accuracy >= 0.90, else the run is VOID).
3. **Taste accumulation.** Every Captain approve/reject permanently sharpens
   the bar: rejections join `corpus/negative/` (the calibration set + the
   pairwise floor), approvals join `corpus/positive/` and can pin as goldens
   (`judge/goldens.py`) with SSIM regression thresholds. The harness gets
   *harder to fool over time*, never softer.

## One entrypoint — `world-aesthetic-gate.py`

```
# per-change ratchet gate (CI-fast, deterministic; committed calibrations
# are wired in automatically — override with --palette/--bounds):
python3.12 cabinet/scripts/world-aesthetic/world-aesthetic-gate.py \
    --mechanical --map world.map.json --render out.png --labels out.labels.json

# ratchets + blinded vision-judge run-bundle emission (mechanical must pass
# first; hand the printed tasks.json to a judge agent, then `judge_protocol.py
# ingest` computes calibrated verdicts):
python3.12 cabinet/scripts/world-aesthetic/world-aesthetic-gate.py \
    --full --render out.png --map world.map.json

# refit calibration/*.json from the (gitignored) corpus + separation proof:
python3.12 cabinet/scripts/world-aesthetic/world-aesthetic-gate.py --calibrate
```

This gate runs **per-change** (renderer commits, mockup reviews, CI) — never
on cron; see the doc note beside the Cabinet World rows in
`cabinet/services.yml`.

**Integration contract.** Every world-reimagine mockup and every future
renderer build MUST pass `--mechanical` before it is shown to the Captain,
and SHOULD carry a calibrated judge verdict (`promote`/`iterate`) from
`--full` when the change is aesthetic (new scene, new dressing pass, new
zoom). A frame that fails `--mechanical` is not "awaiting taste" — it is
rejected, mechanically, for reproducing a recorded failure class. Historical
proof (self-test, 2026-07-08): all 5 reconstructions of the rejected build
fail hard (`CLUSTER_FLAT_VOID` on every one; `PALETTE_FOREIGN_MASS` on the
street-void frame), all 9 approved showcase scenes pass, and a real
agent-as-judge calibration run scored 45/45 (1.000) on the hidden set while
rejecting a scatter candidate 0/5 vs negatives.

**Captain feedback loop.** When the Captain rejects a frame: screenshot →
`corpus/negative/` + a `why` row in `corpus/manifest.json`
(`build_corpus.py manifest` regenerates hashes) → `--calibrate` refits the
bounds and proves separation. When the Captain approves one:
`corpus/positive/` the same way, and optionally
`judge/goldens.py record --verdict approve` to pin it as a regression
golden. Both directions land in the next judge run's hidden calibration set.

The underlying runner remains directly invokable:

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

## The vision judge (`judge/`)

The gates catch *known* failure classes; the judge scores *overall look*
against the corpus, pairwise. Protocol in code, judgment via agents at call
time — `judge_protocol.py build` emits a task-list JSON for an LLM runner,
`ingest` computes verdicts from the filled results:

```
python3.12 cabinet/scripts/world-aesthetic/judge/judge_protocol.py \
    build --candidate out.png            # -> judge/runs/<run_id>/tasks.json
# hand tasks.json + images/ to a judge agent; it writes results.json
python3.12 cabinet/scripts/world-aesthetic/judge/judge_protocol.py \
    ingest --run judge/runs/<run_id> --results .../results.json
```

* **Pairwise, blinded, position-bias-killed.** Candidate vs sampled corpus
  positives and negatives; every pair asks *"Which reads more like a
  finished, warm, professional pixel-game scene — LEFT or RIGHT, and why in
  one line?"* (rubric: `judge/rubric.md` — three lenses: composition
  mechanics / mood + warmth + lighting / game-feel). Left/right is
  seeded-randomized per pair; staged image names are opaque; `tasks.json`
  carries no ground truth (the answer key lives in `key.json`, which the
  runner must never read).
* **Calibration gate (the D5 move).** Every run hides the full
  positive x negative cross product among the candidate pairs. `ingest`
  scores it first: pairwise accuracy `>= 0.90` (every corpus negative below
  every positive) or the whole run is **VOID** — stamped
  `void_uncalibrated`, exit 1, no candidate verdict leaks out. Calibration
  results are stamped into `verdicts.json` on every outcome.
* **Aggregation.** Win-rate vs negatives is the sanity floor (default 1.0 —
  one loss to a Captain-rejected frame disqualifies); win-rate vs positives
  is the real signal. `reject` below the floor, `promote` at `>= 0.5` vs
  positives, `iterate` between; every one-line "why" from the losses is
  collected per candidate as actionable feedback.
* **Goldens + taste accumulation** (`judge/goldens.py`). Captain-approved
  frames pin under `goldens/` (gitignored; tracked `goldens/manifest.json`
  carries sha256 + per-region `min_ssim`/`max_pixel_frac` thresholds);
  `compare` runs stdlib SSIM + exact pixel-diff per region as a regression
  gate. `record --verdict approve|reject` appends the frame + WHY to the
  calibration corpus, so every Captain ruling permanently sharpens both the
  hidden calibration set and the pairwise bar (`build_corpus.py manifest`
  carries these recorded entries across rebuilds).

Run bundles (`judge/runs/`) and golden PNGs are gitignored like the corpus —
licensed pixels never enter git; sha256 manifests are the tracked record.

## Tests

```
python3.12 -m pytest cabinet/scripts/world-aesthetic/tests -q   # 92 tests
```

## Import contract

`cabinet/scripts/gates` is a pre-existing top-level package. This dir's
`gates/` package is therefore **never** imported as `gates` — everything
(runner, calibrate, tests) loads it via `_loader.load_gates()` under the
unique module name `world_aesthetic_gates`. The judge package follows the
same contract via `_loader.load_judge()` (`world_aesthetic_judge`); its CLI
modules self-anchor onto that name when executed directly (PEP 366). No
`sys.path` mutation anywhere.
