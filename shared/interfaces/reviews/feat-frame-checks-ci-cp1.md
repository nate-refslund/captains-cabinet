# Checkpoint review — feat/frame-checks-ci cp1

Reviewed-Scope-Digest: 54518d878e78cd34963d52badb603496bda54d93f00bac017f09bade70b09dfc

**PROVENANCE, first, because it is the weakest part of this artifact.** This is an
AUTHOR self-review, not an independent lens. No reviewer subagent was available in this
session, and saying so beats a review that reads independent and is not. The evidence
below is measured rather than asserted, and the mutation arms are the part that does not
depend on my judgment — every claim about an arm going red is a test in the tree, run.

## What the change is

Twelve world invariants judge a frame `raster.py` draws from `composeLayout`'s blueprint:
no clock, no day bucket, no render stage. Every screen-space pass the browser composites
— ambience, weather, the killswitch wash, the glow — was therefore outside all of them at
every zoom. This adds a second, ADDITIVE path: capture the real composited browser frame
across the clock and the zoom, and judge what the blueprint cannot see. The blueprint path
is untouched and keeps every check it has.

## Evidence, all run this session on this tree

| what | command | result |
|---|---|---|
| judge over 16 real frames | `frame-judge.py /tmp/wf-final` | GREEN 38/38 |
| judge self-arms | `pytest cabinet/scripts/world-capture/tests/test_frame_judge.py -q` | 19 passed |
| whole world-capture dir | `pytest cabinet/scripts/world-capture/tests -q` | 81 passed |
| dashboard suite | `npm test` | 140 files, 2891 passed, 1 skipped |
| typecheck | `npx tsc --noEmit` | clean |
| mirror guard | `sync-checks.py --check` | 4/4 identical |
| layer separation | `check-layer-separation.sh` | no new violations |
| docs sweep | `docs-track-code-sweep.sh` | GREEN (64 files, 0 findings) |
| capture syntax | `node --check frame-harness/shoot.mjs` | OK |

## Where I attacked it

**"Does each arm fail against the defect it names?"** Every arm has a mutation test that
turns exactly it red: the filter never applied · the wrong bucket for the hour · the real
2026-07-29 16% dither · a pixel permutation · a washed-out frame · water above the derived
cap · a wash that stopped drawing · one pixel of non-determinism in each channel
separately. The permutation arm is the one that matters most — it leaves the histogram
bit-identical, so if `grain` did not catch it, `grain` would be decoration.

**"What does it do at the degenerate end?"** Found and fixed three, all by asking:
* a flat day twin raised `ZeroDivisionError` building the grain ratio before testing the
  denominator. Now UNJUDGED, and the arm that found it asks for zero rather than small.
* the determinism arm compared the difference image converted to `'L'`, whose ITU-601
  weights round a one-unit RED difference to **zero** — proven: two frames differing by
  `(1,0,0)` counted 0 differing pixels. Every day-vs-bucket arm was standing on that
  fail-open. Now a per-channel max; the test is parameterised per channel and only the red
  case catches it.
* a sweep whose frames all carry the wash printed NO water arm at all, which reads as "not
  applicable" rather than "not looked at". Now UNJUDGED.

**"Is the sensor wired to the live artifact?"** Yes, and this is the crux of the change:
the harness imports the shipped `EngineCanvas`, its PixiJS boot and its GLSL ambience
filter. Only the DATA is stubbed, from the same `states/*.json` the blueprint path reads.

**"What does the test environment guarantee that production does not?"** Two answers, both
uncomfortable and both handled. (1) The harness supplies `position:absolute; inset:0` in
CSS because the product supplies them as Tailwind classes — without them PixiJS sized
itself 1200x600 in a 1200x800 stage and every capture had a black band the arms would have
judged as a third of the world. The driver now ASSERTS the canvas size and refuses a
mismatch. (2) A runner with no GPU gets WebGL from SwiftShader; if it did not, the filter
would be null and every night frame would be daylight. That is caught twice — the renderer
raises it on the issues channel and the driver refuses, and independently the `ambience`
arm would go red by ~50 luminance.

## What I am NOT claiming

* **Six of the twelve did not transfer** and are blocked on a renderer capture door that
  does not exist. `README.frame.md` says which, why, and what building it costs. Nothing
  here should be read as "the twelve now run on the frame".
* **`ambience` and `grain` judge the sun / killswitch-off sweep.** Both overlays draw above
  the filter and are not remapped; measured drift +0.8 mean under rain, +3.9 under fog. So
  their COMPOSITION with ambience has no sensor. Stated in the judge's header, the README
  and the code.
* **The weather layer has no arm of its own** — only its exclusion.
* **One state** (`hamlet`) and one canvas size are in the CI sweep.
* The `ambience` tolerances ARE constants (1.5 L / 2.5 sd / 0.015 sat / 8 span). They are a
  measured noise floor for the nearest-native snap disagreeing with the GPU on a tie —
  worst observed agreement is 0.1 / 0.6 / 0.001 / 3 — not a quality dial. `grain` has no
  constant at all; its bound is the day frame's own energy.

## Risk I would watch

CI flake on capture readiness. Mitigated by three independent waits plus a
capture-until-two-agree loop that ERRORS rather than returning a best effort, and the
renderer measured bit-exact (0 of 960000 px across two full page loads), re-proven every
run by the `determinism` arm. If it does flake, the failure is a red arm with the frames
uploaded as an artifact, not a silent pass.
