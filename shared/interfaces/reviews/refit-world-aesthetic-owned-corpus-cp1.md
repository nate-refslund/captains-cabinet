# Checkpoint review — refit/world-aesthetic-owned-corpus cp1

Reviewed-Scope-Digest: bd7dd0db8f7837e7798e919a0aab0ed38ae6ff65794d818f87687a20924a7df3

**This is a SELF-review by the author, not an independent one.** No fresh-context
reviewer was dispatched — this session had no agent-dispatch tool. Recording that
plainly, because a review artifact that implies an independent pass it did not get is
worth less than no artifact. What follows is what was actually attacked and what the
attacks returned. Full argument and every number:
cabinet-meta `designs/world-aesthetic-corpus-refit-2026-07-28.md`.

## What the change is

The aesthetic-gate calibration corpus moves from LimeZu showcase scenes to owned
isometric art, per the Captain's "ALL OUT of LimeZu" direction. The old corpus is
preserved verbatim and runnable; the old derived calibration is preserved as TRACKED
files so pre-refit claims stay reproducible from a plain checkout. `palette_coherence`
gains the separation proof it never had.

3,657 staged lines, of which ~2,900 are regenerated JSON calibration/manifest data.
Hand-written change is ~750 lines across 12 files.

## The finding that justifies the shape of the change

Measured before touching anything: **the old `palette_coherence` passed 4 of its own 5
corpus negatives** (0.04%, 0.15%, 1.38%, 3.17% foreign against a 5% limit). It never
separated good composition from bad and structurally could not — the negatives are made
of the same LimeZu pixels as the positives. It is an ART-FAMILY gate. `clustering` is
the composition gate and tripped on all five.

Nothing had ever asked whether the palette arm could fail, because `calibrate.py prove`
only proved clustering. That gap is closed here (P1-P5).

## Attacks run against the re-fitted gate

| attack | result | caught by |
|---|---|---|
| channel rotation `(r,g,b)→(g,b,r)` on a positive | 98.94% RED | **palette only** — `flat_mass`/`dominant_share` byte-identical, clustering blind |
| hue rotation 140° | 88.43% RED | **palette only** |
| 60 LimeZu sprites composited into an owned frame | 21.72% RED | **palette only** |
| synthetic CSS rectangles | 93.26% RED | palette + clustering |
| all 16 archived LimeZu images | min 16.05% RED | palette |
| owned sprites on an empty field (deliberately bad frame) | palette 0.12% GREEN | **clustering only** (`CLUSTER_FLAT_VOID`) |

Both gates have an arm where they are the only thing that fires. Neither is decorative.
All six run through the real CLI: exit 1 on every attack, exit 0 on 13 held-out owned
frames that were never in the fit.

## Permissiveness — the "did you build a mirror" check

The re-fitted palette admits **9.01%** of the 5-bit colour cube; the LimeZu palette it
replaces admitted **16.47%**. `flat_max` tightens 0.4018 → 0.2433, `busy_cv_min`
0.4101 → 0.8238, `dominant_max` 0.3526 → 0.3503, map bounds unchanged. The gate is
strictly LESS permissive on every axis. `MAX_FOREIGN` and every margin constant are
untouched.

## Sensor work in this diff

- `prove_palette` calls `palette_coherence.check` rather than re-deriving the arithmetic
  (a proof that reimplements what it proves drifts silently).
- Mutation-tested: neutering P3/P4 turns `test_prove_palette_FAILS_a_dead_palette` red;
  restoring turns it green. A palette admitting the whole cube fails the proof.
- P3/P4 synthesize their own inputs, so the bite proof never depends on gitignored
  pixels. P5 prints `NOT RUN (not a pass)` after the verdict when the archive is absent.
- **Two existing sensors were found broken and fixed, not worked around.**
  `test_corpus_smoke` silently SKIPPED when the images it named vanished — it now
  asserts (a gitignored corpus being wholly absent is still a legitimate skip).
  `test_world_assets_and_node_modules_absent` enumerated banned dirs literally so an
  archived corpus was uncovered — it now globs.
- `.gitignore` uses a LITERAL per-archive rule, not `corpus-*`: the persistence
  preflight resolves a wildcard to its deepest wildcard-free prefix, so a glob collapsed
  to `cabinet/scripts/world-aesthetic` and reported an unaccounted durable path. The
  literal rule forces whoever archives a corpus to declare its persistence.

## Known limitations, stated not buried

1. **`palette_coherence` cannot see foreign art below ~5% of frame pixel mass.**
   Measured: one LimeZu 16×32 cell (0.048% of frame) → 0.24% foreign, green; ~800 cells
   covering ~39% of the frame are needed to cross the limit. **It therefore cannot
   detect the one iso-reachable LimeZu draw site** (officers at desks, ~1% of a frame).
   Per-sprite provenance is a manifest check, not this one. → BACKLOG.
2. **The renderer draws 0.00% exact master-palette colours** — a global tint/fog/
   downscale transform moves every pixel off the authored 49-colour lock (9,943 distinct
   colours in one frame). This is why the palette must be fitted from renders and cannot
   be anchored on `master_palette.png`. → BACKLOG.
3. **The palette is a function of the renderer, not only the art.** A legitimate
   renderer change can red the gate, and refit-by-refit is how a gate becomes a mirror.
   Rule recorded in the design doc: such a refit must re-run the BITE battery, not just
   the pass battery.
4. **v15-era frames (2026-07-21) now fail** — 14.89% foreign, `flat` RED. They predate
   the computed dithered ground. Deliberate scoping, not a regression; the frames were
   looked at before deciding.
5. The vision judge's positive pool changes with the corpus. Not separately re-validated
   here beyond confirming `--full` builds a 34-task bundle (it was blocked entirely
   while mechanical was red).

## Gates run

world-aesthetic pytest **96 passed, 0 skipped** (was 90 passed / 1 failed / 1 skipped) ·
`calibrate.py all` **PROVE OK** exit 0 · `build_corpus.py verify` 11/11 and archive
16/16 · egg export 59 passed / 1 skipped (pre-existing) · `check-layer-separation.sh` OK,
new 0 · `state-persistence-preflight.py` exit 0, 0 unaccounted. Clean clone of
origin/master, `__pycache__` purged, `PYTHONDONTWRITEBYTECODE=1`.
