# iso-port-composition · cp3 — the roof cutaway gets real art

## What landed

**19 new pack frames** (163 -> 182, still ONE 2048 atlas): ten roof-off building
twins (`great_house_open`, `library_open`, `workshop_open`, `camp_log_cabin_open`,
`officer_house_a_open` and the five dwelling refinements a hamlet island really
draws — `cottage_a/b/c_open`, `officer_house_b/c_open`), an eight-piece interior
kit (`int_desk`, `int_work_board`, `int_bookshelf`, `int_table`, `int_bunk`,
`int_postbox`, `int_stove`, `int_rug`), and `lighthouse_lit`, since the pack's
`lighthouse` is authored with a DARK lantern room.

**`src/lib/world/iso-cutaway.ts`** — pure: `openFrameOf` (the ATLAS decides what
opens, not a list), `isoCutawayCandidate`, `cutawayMix`, `interiorSlots`.

**`engine-canvas.tsx`** — the iso cutaway is drawn: the closed frame fades out
while its `_open` twin fades in at the same base centre, with desks and officers
inside a nested room container.

## Verification

- `iso-cutaway.test.ts`: 25 arms. **16/16 source mutations turn an arm red, none
  green** (harness + list in the round report). One HOLE was found and fixed that
  way: the "2:1 lattice" arm passed against a rectangular grid, because
  whole-step gaps are a property both shapes have.
- `npx vitest run` (dashboard): **2702 passed, 1 skipped** (the skip is a
  pre-existing `skipIf`, not this change).
- `capture.test.ts` run explicitly: **12/12 world invariants pass** on real
  rasterized camp and hamlet frames with the new pack.
- `npx tsc --noEmit`: clean.
- Repack proven to be a pure re-shelf: **0 of the 163 existing frames changed
  drawn geometry, and 0 changed a pixel** — only their x/y in the atlas moved.

## Two rules this round is built on

1. **Every fixture is generated EMPTY.** A board with pins or a shelf drawn full
   bakes a measured quantity into static art. The number of desks is the number
   of officers and it is composited, never drawn.
2. **The candidate rule had to be recalibrated, not ported.** `lod.cutawayCandidate`
   asks for 40% of the viewport's central third; on real iso numbers the great
   house covers 30% at maximum zoom, so a verbatim port would have shipped a
   cutaway that can never fire with every existing lod test still green. That is
   pinned by its own arm.

## Known and stated, not hidden

- The iso cutaway machine is stepped in the canvas, not the shell: the shell's
  candidate is computed from top-down building boxes in tile space and its ids
  cannot name an iso scene sprite. Same reducer, different candidate.
- Officers are 16x32 LimeZu frames in a 176x160 room — the character pack and
  the building pack were authored at different scales.
