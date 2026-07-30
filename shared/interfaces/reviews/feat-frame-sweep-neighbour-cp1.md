# feat/frame-sweep-neighbour — checkpoint 1

**This is an AUTHOR SELF-REVIEW.** No second reviewer was available for this
lane. Everything below is a measurement I ran myself in this session, on real
composited browser frames, with `__pycache__` purged; nothing is inherited from
the brief that started the work — and two of that brief's three premises did not
survive the measurement (see *Premises that failed*).

## What landed

**1. `surface` — the neighbour arm in `frame-judge.py`.**

The programme's top open item was that a membership test cannot catch a
legitimate colour in an illegitimate place: `PALETTE_FOREIGN_MASS` asks whether
a pixel is a corpus colour and never whether it is a plausible neighbour of the
surface it sits on, so the 2026-07-29 dusk veil satisfied it *by construction*.

The law: **every screen-space pass in this renderer is a decision per COLOUR, so
over any patch of the frame it may MERGE a surface's tones and may never ADD
one.** Measured per 16×16 tile (the world's own `tile_size`) against a twin
differing only in the pass under test.

Why that is the neighbour question made mechanical: the "place" is the tile, and
the plausibility criterion is that surface's own tone count. A global grade
cannot raise it. A hue sprayed into a surface always does.

| | tiles gaining a tone |
|---|---|
| honest pair, `ambience_py.remap` applied per colour (fixture) | **0.00%** — the law is exact |
| shipped renderer, 30 legitimate cells (3 zooms × 3 lit buckets × {sun,rain,fog,storm} × killswitch on/off) | 0.37% – **5.49%** |
| the 2026-07-29 dusk veil at its shipped 16% coverage | **77.55%** |
| the same veil at 0.05% coverage | 10.45% |

The 0.4–5.5% legitimate floor is attributed, not assumed: the shipped GLSL
filter and `ambience_py`'s nearest-native snap **disagree on ~14% of pixels**
(85.94% of a night z2 frame is exactly `remap(day)`, and the differences are
small and spread evenly rather than clustered on any object). `SURFACE_EXCESS =
0.12` sits 2.2× above the worst legitimate cell and 6.5× under the shipped
defect. There is nothing here to relax when a frame goes red.

**It sees what the existing arms cannot.** A luminance-matched chroma veil moves
no edge energy and almost no histogram. Measured on the real dusk z1 frame:

| coverage | `ambience` | `grain` | `surface` |
|---|---|---|---|
| 1.0% | RED | pass | RED (74%) |
| 0.4% | pass | pass | **RED (51%)** |
| 0.1% | pass | pass | **RED (18%)** |

So the arm's unique territory is any veil at or below ~1% coverage and any
luminance-matched veil at any coverage — roughly **1/100th of the mass
`PALETTE_FOREIGN_MASS` needs before it can see anything at all**, whose
detection floor equals its own 5% threshold.

**It also closes a gap the file itself declared open.** `README.frame.md` said
"ambience-under-weather has a sensor for the OVERLAY and none for their
COMPOSITION". An overlay is a per-colour pass too, so `surface` judges it as
long as the twin carries the same weather: night-under-fog vs a fogged day twin
reads 0.37%, identical to sun, and the killswitch wash reads exactly 0.0000.
Judged against a `sun` twin instead, fog reads 13.2% — which is the measurement
that says the twin must match, and it is why `pair_up_surface` keys on
(zoom, weather, killswitch) rather than reusing `pair_up`.

**2. The corpus arms can now be seen by CI.**

Five arms of `world-aesthetic/tests` read a gitignored corpus and every one of
them skipped when it was absent — always, on a fresh checkout. The corpus is now
**materialised from tracked inputs** before the arms run (`build_corpus.py
materialise`), **sha256-verified against the tracked manifest** with a mismatch
as a hard failure by id, and the members that genuinely cannot be reconstructed
are **declared and pinned**.

    fresh checkout, before:  91 passed,  5 skipped
    fresh checkout, after:   99 passed,  3 skipped

Four of eleven members rebuild from the repo's own tracked owned pack (3
seeded synthetic negatives; 1 palette member, a byte-copy of
`originals/iso/atlas-0.png`).

**PIXEL-identically, not byte-identically — and that correction cost a red CI
run.** I proved byte-equality three times on this laptop and wrote it down as a
property. The first ubuntu runner produced the same PICTURES as different FILES
(PNG encoding runs through whatever zlib the local Pillow was built against) and
the verifier called a perfectly correct corpus a mismatch, reddening 74 tests.
So the manifest now carries BOTH digests and each governs what it can: the file
hash for a member that is TRANSPORTED (the held ones — those bytes are all
anyone has), the pixel hash for a member that is GENERATED. A reproducibility
claim measured at one operating point is a hypothesis; this one is now measured
at two, and `test_a_mere_RE_ENCODE_of_a_rebuilt_member_is_not_a_mismatch` keeps
it that way. The other seven are HELD:
four live renderer captures, and three Captain-rejected screenshots carrying
licensed LimeZu art that this tree may not redistribute now it is headed for a
public export. `test_world_aesthetic_corpus_reach.py` pins the held set BY ID,
so a member cannot join it silently — which would be the "partial fix that
relabels the rest as covered" move this programme has paid for before.

**A second fail-open, caught in my own first draft of this change.** The
`ImportError` branch (Pillow builds the synthetic negatives) originally reported
every member as held and carried on — which quietly restores the exact skip this
change removes. It now FAILS, naming the rebuildable members it could not build,
but only when their absence actually costs coverage: with them already on disk a
missing Pillow is harmless, because the gates themselves are stdlib-only, and
failing there would be an invented blocker. Both directions are pinned. The test
also had to catch `pytest.fail.Exception` rather than `Exception` — `Failed`
derives from `BaseException`, so `pytest.raises(Exception)` walks straight past
it and the test reports the guard's failure as its own red.

Two skips that could never legitimately fire were removed outright: `_bounds`
skipped on a missing `calibration/clustering_bounds.json`, which is **tracked**;
and `test_corpus_smoke` named a live capture and a LimeZu screenshot for its two
PNG colour types, both re-pointed onto rebuildable members carrying the same two
types (ct2 `neg-owned-void`, ct6 `pal-owned-atlas`) so the arm now runs in CI.

## Premises that failed

Recorded because a review that only confirms is not a review.

* **"Three corpus tests FAIL once the corpus is assembled on disk"** — refuted.
  With the corpus master's manifest declares, master is **96 passed, 0 failed,
  0 skipped**. The 4 failures reproduce only when the **archived pre-re-fit
  LimeZu corpus** is dropped into `corpus/` instead. The real defect is one
  level up and worse: `has_corpus` asked "are there PNGs here?" and never "is
  this the corpus the manifest declares", so **one commit produced three
  verdicts** — 96 green, 4 red, 5 skipped — and nothing in the suite could tell
  them apart. That is what the verifier fixes.
* **"`CLUSTER_FLAT_VOID` fails on the night frame"** — true but far too narrow.
  It fails on **13 of 16 frames in the sun sweep, including DAY**, and on 20 of
  24 weather frames. Cause measured: the dominant colour of every failing frame
  is a colour from the renderer's own **sea ramp**, and sea mass is 76–94% at
  z0.5/z1 against 12% at z2, where every frame passes. The gate is measuring how
  much ocean is in shot. Not fixed here — see *Not fixed*.

## Every new arm proven able to fail

Each mutation was applied to the source, the named test re-run with
`__pycache__` purged, and the source restored byte-identically.

| mutation | expected red | result |
|---|---|---|
| `arm_surface` always passes | the 2 red-arm tests | 2 failed |
| `arm_surface` always reds | merge-green + honest baseline | 2 failed |
| drop the twin-size guard | different-size twin | 1 failed |
| drop the zero-tile guard | sub-tile frame | 1 failed |
| delete `if not pairs:` | daylight-only sweep | 1 failed |
| delete `if not spairs:` | daylight-only sweep | 1 failed |
| a rebuild recipe becomes HELD | 2 corpus-reach arms | 2 failed |
| the missing-Pillow guard stops firing | the Pillow arm | 1 failed |
| the verifier goes back to file bytes only | the re-encode arm | 1 failed |
| the pixel comparison always agrees | the mismatch arm | 1 failed |
| an undeclared member joins the registry | the declaration arm | 1 failed |
| the sha256 mismatch stops being recorded | the mismatch arm | 1 failed |

**A fail-open found this way, in my own first draft.** Deleting the
`if not spairs:` branch did NOT redden its test: dropping the day frame leaves
the lit frame *orphaned*, and the orphan branch answers first, so the no-pairs
branch had no test that reached it. The input that reaches it is a sweep with
**no lit frame at all** (`shoot.mjs --hours 13`), which no test contained.
`test_a_daylight_only_sweep_is_unjudged_by_both_pair_arms` supplies it — and the
**pre-existing `ambience` branch had shipped in exactly that state**, proven by
defeating it and watching its own test still pass. Both branches are now covered
by that one test.

## Not fixed, and why

* **The mechanical aesthetic gate reds on 37 of 40 real composited frames.**
  `CLUSTER_FLAT_VOID` on the wide camera (dominant colour is the sea ramp),
  `PALETTE_FOREIGN_MASS` on every code-drawn overlay (fog 11.05%, dominated by
  two fog-lightened sea teals never present in the atlas the palette was fit
  from; killswitch 20–94%). Both are the gate being asked a question outside its
  calibration domain: its image bounds were fitted on close captures of the
  island, and its palette is a membership test that no code-drawn hue can
  satisfy. It is invoked by `world-preview.py` and `world-asset-intake.py`, and
  by no CI job — feeding it a browser frame is a NEW use. Fixing it needs a
  notion of "a legitimately flat surface" and "a legitimately synthesised hue",
  which is a design, not a threshold, and widening either bound is forbidden.
  Recorded in cabinet-meta `BACKLOG.md` with every number.
* **`water` is UNJUDGED on all 8 rain and storm frames** (both repaint the sea,
  so the probe finds no sea-ramp window) and **`grade` reds on `day/storm`**
  (mean L 94 against a floor of 95 — daylight bounds meeting a darkened sky).
  Neither reaches CI, whose sweep is sun-only. Recorded, not silenced.
* **Three corpus arms still skip**, naming the seven held members. Making them
  run would mean committing live captures and licensed screenshots to a tree
  headed for public export.

## Gates run in this worktree

`world-capture/tests` 89 passed · `world-aesthetic/tests` 102 passed (full
corpus) / 99 passed + 3 skipped (fresh-checkout simulation, corpus removed,
and again with the synthetics re-encoded to the cross-machine byte difference) ·
`sync-checks.py --check` 4/4 identical · `docs-track-code-sweep.sh` GREEN
(files=64 findings=0) · `check-layer-separation.sh` new=0 · `frame-judge.py`
GREEN 50/50 on the 16-frame sun sweep, and the arm costs 1.4s of the judge's
1m40.
