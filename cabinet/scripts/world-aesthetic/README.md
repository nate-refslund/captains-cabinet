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

## Calibration corpus (why `corpus/` is gitignored)

Three classes, `corpus/{positive,negative,palette}/`:

* **positive** — finished OWNED isometric scenes the Captain has seen: two
  wide island states (hamlet, overgrown camp), one close zoom, one roof-off
  interior. Fits the palette AND the clustering image bounds, and is the
  vision judge's positive pool.
* **negative** — the three Captain-rejected build screenshots (accumulated
  taste, carried across every re-fit) plus three synthetic OWNED-art scenes:
  scatter at two densities and a building void. The owned negatives are what
  give the composition bounds ground truth that cannot be passed on
  art-family grounds.
* **palette** — palette-source art that is not a scene (the owned isometric
  atlas). Read by the palette fit ONLY: never the clustering bounds (a sprite
  sheet is not a composed scene) and never the judge (which would compare a
  candidate against a sprite sheet). Without it, a frame drawing sprites the
  corpus renders happen not to contain reads as foreign colour — measured
  6.52% vs 1.23%.

**Pixels are never committed** — `.gitignore` excludes `corpus/*` except
`corpus/manifest.json` (sha256 + provenance per image). Only code, the
manifests, and derived-number calibrations are tracked.

**So the test suite MATERIALISES what it can and VERIFIES what it finds**
(2026-07-30). Every REGISTRY row carries a `rebuild` field: `"synthetic"` and
`"copy:<tracked path>"` mean a plain checkout can reconstruct those bytes, and
`None` means the member is HELD — a live capture, or a Captain-rejected
screenshot carrying licensed art this tree may not redistribute. `build_corpus.py
materialise` puts every rebuildable member on disk (4 of 11), the fixture runs it
before the arms, and every member present is digest-checked — **a mismatch is a
hard failure naming the ids, never a skip and never a quiet pass**.

**Two digests, because a generated member and a transported one are not
verifiable the same way.** `sha256` is the FILE; `pixels_sha256` is the decoded
RGBA buffer. A rebuilt PNG is re-encoded by the local zlib, so the same picture
lands as different bytes on a different machine — measured the hard way, when a
correct corpus reddened 74 tests on the first ubuntu runner after three
byte-identical rebuilds on one laptop. Held members are judged by file bytes
(that is all anyone has of them); rebuildable ones by pixels. `tests/test_world_aesthetic_corpus_reach.py` pins the
held set BY ID so a member cannot join it silently.

Why that matters: the suite used to gate on "are there PNGs in
`corpus/positive/`?", which is a different question from "is this the corpus the
manifest declares". Measured on ONE commit — the manifest's corpus gave
**96 passed**, the archived pre-re-fit corpus dropped in the same place gave
**4 failed**, and a fresh CI checkout gave **5 skipped**. A fresh checkout now
runs 99 and skips 3, and the 3 name the held members.

**Re-fit 2026-07-28 (LimeZu → owned art).** The corpus was LimeZu showcase
scenes until the Captain's "ALL OUT of LimeZu" direction. A palette fitted to
LimeZu measured owned frames at 57-90% foreign against a 5% limit — the gate
was pointed at the art family we are deliberately leaving. The previous
corpus is preserved verbatim and still runnable at
`corpus/archive-limezu-2026-07-08/`, with its manifest and the calibration it
produced TRACKED at `calibration/archive/limezu-2026-07-08/`. The argument,
before/after numbers and bite proof are in cabinet-meta
`designs/world-aesthetic-corpus-refit-2026-07-28.md`. Reproduce any pre-refit
claim with `calibrate.py all --corpus corpus/archive-limezu-2026-07-08
--out-dir /tmp/old`.

An archive nests INSIDE `corpus/` rather than beside it, and that is
load-bearing: `cognitive-architecture-census.py` derives `durable_store_units`
from `.gitignore`'s wildcard-free prefixes, so a sibling `corpus-*/` needs its
own ignore rule and reads as a NEW organ of memory against a zero-headroom
budget. An archived corpus is not a new organ — it is this organ's own history.

* `build_corpus.py synthetic|materialise|manifest|verify [--corpus DIR] [--manifest PATH]` —
  regenerate the synthetic negatives (cut from the repo's own tracked owned
  atlas, so they rebuild from a plain checkout + Pillow), put every rebuildable
  member on disk and NAME the held ones, rebuild the manifest, verify bytes
  against it. Current corpus 11/11 OK; archive 16/16 OK.
* `calibrate.py palette|clustering|prove|all` — fit `calibration/*.json`
  from the corpus. Palette floor semantics: a quantized bin joins the
  palette when it reaches `min_bin_share` in **at least one** input
  (per-image floor — a merged-mass floor let big images starve a small
  positive's colors and broke self-consistency).

## The prove-it contract

`calibrate.py prove` proves BOTH gates, and they discriminate different
things. That split was measured, not assumed: against the pre-2026-07-28
corpus `palette_coherence` passed **3 of its own 5 negatives** (0.04%, 0.15%,
1.38% foreign). It never separated good scenes from bad and never could.
Clustering is the composition gate; palette is the ART-FAMILY gate.

1. **Clustering** — every corpus **negative** must trip an image bound, every
   **positive** must trip none; synthetic scatter maps must trip the map
   bounds while a held-out clustered layout passes.
2. **Palette** — P1 every positive under `max_foreign`; P2 every OWNED-art
   negative ALSO under it (a composition defect must never be reported as
   foreign colour); P3 a channel-rotated positive `(r,g,b)->(g,b,r)` must
   EXCEED it — composition-identical by construction, so `flat_mass` and
   `dominant_share` come out byte-identical and no other gate can see it;
   P4 a synthetic CSS-rectangle scene must exceed it; P5 every image in any
   archived corpus must exceed it. P3/P4 synthesize their own inputs, so the
   bite proof never depends on assembled pixels; P5 prints **NOT RUN** and is
   listed after the verdict when an archive is absent, never counted as a
   pass. Exit 1 on any violation.
3. `tests/test_world_aesthetic_{clustering,palette}.py` — the same
   separations as pytest against the **committed** calibrations, plus
   corpus-independent synthetic cases so a clean clone (no corpus) still
   proves the mechanism, plus a mutation arm: a palette broadened to admit
   the whole colour cube must FAIL the proof.

**What `palette_coherence` cannot see.** It is a bulk gate on pixel mass, so
foreign art below ~5% of a frame's opaque pixels is invisible by
construction. Measured on the owned island frame: one LimeZu 16x32 character
cell at 2x (0.048% of the frame) reads 0.24% foreign and passes; it takes
~800 such cells covering ~39% of the frame to cross the limit. Per-sprite
provenance is a manifest-level check, not this one.

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
