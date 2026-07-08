# VISION JUDGE rubric — Cabinet World frames

This rubric is what a judge agent holds in mind while answering the pairwise
question the protocol asks for every image pair:

> **Which reads more like a finished, warm, professional pixel-game scene —
> LEFT or RIGHT, and why in one line?**

Every criterion below is phrased as a **pairwise-decidable question**: it can
be answered by looking at two frames side by side and picking one, without a
numeric scale. Judge the pair on overall gestalt across all three lenses; the
one-line "why" should name the deciding criterion (e.g. "RIGHT — LEFT's props
float on an untextured green void").

No ties. If genuinely close, pick the frame a Stardew player would rather see
in a shipped game's screenshot gallery.

The lenses are grounded in the recorded Cabinet-World failure classes
(corpus negatives: flat-green prop scatter, black-void streets, the grey
unfurnished wardroom, garbled road tiling) and in what the LimeZu showcase
positives consistently do right.

---

## Lens 1 — Composition mechanics

Structural correctness of the scene as a piece of tile art.

1. **Grounding.** In which frame do buildings and props sit *on* the terrain
   — base transitions, contact shadows, paths meeting doorways — rather than
   floating on an untextured field?
2. **Terrain variation.** Which frame varies its ground purposefully (grass /
   dirt / paving / shore transitions) instead of one flat color fill from
   edge to edge?
3. **Path logic.** In which frame do paths and roads actually connect
   entrances to destinations and lead somewhere, rather than starting or
   ending nowhere?
4. **Seam integrity.** Which frame has clean tile transitions — no garbled or
   misaligned autotiles, no abrupt cuts into void or black backdrop?
5. **Purposeful placement.** In which frame do props form meaningful clusters
   that tell a small story (bench + lamp + path; table + set chairs; crates
   by a door) instead of a uniform sprinkle of unrelated objects?
6. **Frame completeness.** Which frame is composed all the way to its edges —
   no dead voids, no unfinished bands, no lone furniture strip in an empty
   room?

## Lens 2 — Mood, warmth, lighting

Whether the scene feels warm and finished rather than technical and flat.

1. **Palette warmth.** Which frame's palette reads warm and harmonized (hues
   that belong together) rather than cold, flat, or clashing?
2. **Light consistency.** Which frame shows a consistent light direction —
   shadows falling the same way, shading agreeing across objects?
3. **Contrast hierarchy.** Which frame guides the eye to focal points
   (doorway, square, hearth) instead of presenting uniform visual noise or
   uniform emptiness?
4. **Inhabited cues.** Which frame feels lived-in — lit windows, plants,
   food, laundry, animals, people mid-task — rather than staged or vacant?
5. **Color-mass balance.** Which frame avoids a single dominant untextured
   color mass (flat green field, grey floor plain, black void) swallowing
   the composition?

## Lens 3 — Game-feel ("would a Stardew player nod?")

Whether the frame would pass as a screenshot from a real, shipped game.

1. **The nod test.** Which frame would a Stardew Valley / LimeZu-showcase
   player accept as a screenshot from a finished game, not a work-in-progress
   asset test?
2. **Readability.** In which frame can you instantly tell where a character
   can walk and what blocks them?
3. **Place-ness.** Which frame reads as a *place with a job* — a farm, a
   street, an office you could name — rather than a scene assembled to
   display assets?
4. **Fiction breaks.** Which frame has fewer immersion breaks — floating
   props, cut-off structures, garbled tiles, objects at the wrong pixel
   scale for the world?
5. **Explorability pull.** Which frame makes you want to walk around the
   next corner — implied continuation and detail density beyond the visible
   frame?

---

## Protocol contract (for the judge agent)

- Answer **every** task in the run's `tasks.json`, one answer per task:
  `{"task_id": "...", "choice": "LEFT" | "RIGHT", "why": "one line"}`.
- Look at both images before answering. Never answer from filenames — they
  are deliberately opaque.
- Never read `key.json`, `run.json`, or anything outside `tasks.json` and the
  `images/` directory: the task list contains hidden calibration pairs, and a
  judge that peeks is void.
- The aggregate verdict is computed by `judge_protocol.py ingest`, never by
  the judge agent itself. A run whose hidden calibration pairs are ranked
  below the accuracy floor is **VOID** regardless of how the candidate pairs
  were answered.
