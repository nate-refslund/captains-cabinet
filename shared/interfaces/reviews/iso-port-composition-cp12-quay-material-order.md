# cp12 — the wharf was painted as a road, and the road was painted over the square

Two defects the Captain found BY EYE in `/world?iso=1`, screenshot kept at
`cabinet-meta/designs/defect-wharf-painted-as-dirt-2026-07-27.png`. His words,
verbatim: *"the road - can you put it beneath the centre concrete? and this here
doesn't look like the jetty or harbor it looks like the road?"*

Both were the SAME class of defect: the live engine had diverged from the
offline still renderer that mirrors it. `world-capture/raster.py` was right on
both counts and has been since it was written; `engine-canvas.tsx` was the only
one of the three implementations (compose.py, raster.py, the engine) that got
them wrong. That is why the approved still shows a timber wharf and the browser
showed a dirt track.

## Root cause

| # | defect | root cause | file:line (at HEAD 9e08b6df) |
|---|---|---|---|
| 1 | wharf + finger pier read as the dirt lane | both painted with `paintClass(…, 'dirt', …)` — literally the lane's ground class | `cabinet/dashboard/src/components/world/engine-canvas.tsx:1399` (wharf) and `:1407` (jetty) |
| 2 | the road stops dead at the paved square | the plaza was painted at step 5 and the lanes at step 7, so the dirt band was laid ON TOP of the paving | `engine-canvas.tsx:1360-1369` (plaza) vs `:1381-1389` (lanes) |

For (1) the reference solution already existed and was never ported:
`designs/world-mockup-v2/quay.py` `deck_strip()` / `jetty()`, which
`raster.py:417-425` calls. `designs/iso-engine-port-plan-2026-07-27.md:149`
even names the work — *"QUAY: port quay.py's drawn timber wharf along the real
waterline"* — and step 8 shipped without it.

For (2) the order in `compose.py:351` (lanes) → `:362` (plaza) → `:376`
(fields) is deliberate and `raster.py:388` → `:391` → `:402` mirrors it. The
engine had plaza → pond → lanes.

## The change

- NEW `cabinet/dashboard/src/lib/world/iso-quay.ts` — the port of `quay.py`.
  Pure (no PIXI, no DOM, no clock): emits a flat list of axis-aligned rects.
  PLANK palette verbatim from `quay.py:13-17`, a tone per board and per run
  along its length, a JOINT line under every board, butt joints between board
  ends, a FASCIA lip below the front edge, and `quayHash` reproducing the
  reference's `_hash` exactly (Math.imul, because Python ints are arbitrary
  precision and only the low 16 bits survive the mask).
- `engine-canvas.tsx` — three edits, kept as small as possible because another
  wave is live in this file: one import line; the wharf/jetty block now walks
  the deck rects instead of calling `paintClass(…, 'dirt')`; and the
  plaza/tillage block moved BELOW the lanes so the ground order is now exactly
  `raster.py`'s (sand, grass, meadow, mottle, pond, lanes, paving+tillage,
  deck). The `buildIsoTerrain` docstring, which stated the old order, was
  corrected in the same commit.
- NEW `iso-quay.test.ts` — 8 arms.

## Evidence

Captured from the REAL engine in a real browser (Chromium via playwright)
against a dev server serving a scratch tree of HEAD with `CABINET_ROOT` pointed
at the live checkout, so this is the live world state (`era=hamlet @ 0.439`,
`quay=stone_quay_5`, 7 berths), not a fixture. Same URL, same camera, before
and after; the only difference is the two changed files hot-reloaded into the
running tree.

| image | camera |
|---|---|
| `cabinet-meta/designs/defect1-wharf-BEFORE-2026-07-27.png` | `?iso=1&z=3.00&x=83.3&y=33.3` |
| `cabinet-meta/designs/defect1-wharf-AFTER-2026-07-27.png` | same |
| `cabinet-meta/designs/defect2-road-under-plaza-BEFORE-2026-07-27.png` | `?iso=1&z=3.00&x=68.2&y=16.8` |
| `cabinet-meta/designs/defect2-road-under-plaza-AFTER-2026-07-27.png` | same |

Numbers behind the material claim, measured this session against the lane's own
`groundField('dirt')` over the same box:

| surface | mean RGB | distance from the lane | darker by |
|---|---|---|---|
| whole deck | 130.2, 95.6, 61.6 | 71.9 | 45.1, 45.1, 33.3 |
| board faces only | 142.2, 105.1, 68.2 | 55.4 | 33.1, 35.5, 26.7 |
| the lane | 175.3, 140.7, 94.9 | — | — |

Test floors are 30 (whole deck) and 25 (faces), with 12 per channel on both.

## Mutations — each applied, run, seen RED, restored

| # | mutation | arm that went red | result |
|---|---|---|---|
| 1 | wharf repainted with `paintClass(c, 'dirt', …)` in `engine-canvas.tsx` | *the wharf and the pier are drawn with the deck material, not a ground class* | RED — `expected '…' to contain 'deckStripRects('` |
| 2 | `PLANK := RAMPS.dirt` (exact) | *the deck material is NOT the lane material* | RED — `deck colour 8a6a42 IS a lane tone` |
| 2b | `PLANK := RAMPS.dirt + 1 per channel` (no exact match) | same arm | **first attempt GREEN** — see below |
| 3 | plaza/tillage block moved back above the lanes | *the lanes are laid BENEATH the paving, not over it* | RED — `expected 60077 to be less than 58943` |

**Mutation 2b is the finding worth recording.** The first version of the
material arm measured only the WHOLE-DECK mean, and the whole-deck mean is held
down by the joints (12.3% of painted pixels) and the fascia (15.2%) — both
dark. A plank palette repainted in near-lane tones therefore still cleared the
threshold: distance 40, darker by 17-27 per channel, all green, with every
board face the colour of a dirt road. The arm was measuring a surface that
included the very structure that was not being attacked. It now measures the
board faces SEPARATELY as well, and under that arm mutation 2b fails at
distance 10.7 against a floor of 25.

## Verified

- `npx vitest run src/lib/world src/components/world` on a scratch tree of HEAD
  + only this change: **47 files, 721 tests, all passing** (35s). Run on the
  isolated tree on purpose — three other waves are live in this worktree and a
  suite run here would not attribute cleanly.
- `npx tsc --noEmit` on the same tree: exit 0.
- `capture.test.ts` (the twelve world invariants over both fixtures + its six
  mutations) is inside that suite and is green.

## Not verified / still open

- **The aesthetic gate does not cover the iso path.**
  `world-aesthetic-gate.py --mechanical` fires `PALETTE_FOREIGN_MASS` on ALL
  FOUR images — including the two rendered from unmodified HEAD (29.4% before /
  29.3% after on the harbour; 34.1% / 35.4% on the square). Its palette
  calibration is fitted to the top-down mockup corpus, so it is a sensor
  pointed at a different artifact rather than a verdict on this change. The
  change does not move it materially. Flagged, not fixed.
- **The tillage now buries a lane.** Matching `raster.py`'s order means the
  ploughed/crop plots paint over the lanes, and in the live state a lane runs
  through the SE plot and now disappears under it. Confirmed this is
  PARITY, not a new defect: the offline still renderer buries the same lane
  (`/tmp` live capture, `frame.ground.png` at the field region). The real
  problem is a LAYOUT overlap — fields placed across a lane — and it belongs to
  the layout stage, not the paint order.
- **No painted posts.** `quay.posts()` and the jetty's side posts are in the
  reference and in `raster.py`; the engine gets its mooring posts from pack
  sprites instead. Not ported, so the engine and the still differ on posts.
  Deliberate: the Captain's complaint was the deck material, and adding painted
  posts under existing post sprites would double them.
- **Pixel identity with the mirror is not claimed.** Same algorithm, same
  palette, same seed offsets (+3 wharf, +11 jetty), but the engine's base seed
  is `layout.seed` and the rasteriser's is a CLI `--seed`, so the two decks are
  the same deck and not the same pixels. `iso-terrain.ts`'s own header already
  states this for the ground.
- **The order arms are source scans**, in the established pattern of
  `ratchets.test.ts`. They will go red if the paint sequence changes, and they
  will need re-pointing if the surrounding code is restructured; both arms
  carry an assertion message saying so.
