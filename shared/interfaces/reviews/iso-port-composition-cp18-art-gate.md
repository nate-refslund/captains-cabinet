# iso-port-composition · cp18 — the gate that looks at the art

Repair round on top of `b31c14a1`, answering the two-agent adversarial attack of
2026-07-28. That attack fixed the two reachability defects itself (`90e72c56`,
`b31c14a1`); what it left standing were four art findings, one record-damage
finding and one systemic hole. This is the systemic hole and the art.

## The hole

**Nineteen frames entered the shipped atlas and nothing looked at them.** Ten
roof-off building twins and an eight-piece interior kit. The twelve world checks
judge a capture, and neither judged capture draws a single new frame — no roof
is open in either — so `12/12 GREEN` covered exactly zero of the new art. The
pack tests read the pack's JSON; the cutaway tests read `dw`/`dh`. Not one line
in the tree had ever read a pixel of `atlas-0.png`.

That is why an `_open` twin that is a **different building** and a "postbox"
that is an outdoor shed both shipped green.

## What landed

### 1. `iso-art.test.ts` — a shipped gate that decodes the atlas

Forty lines of `node:zlib` (8-bit RGBA, non-interlaced; anything else throws)
and a sweep of **every one of the 182 frames**, including all 18 new ones:

| arm | what it would catch |
|---|---|
| decoder self-check | a decoder returning zeroes, which would make every sweep below pass vacuously |
| hash discriminates | a staleness detector that cannot detect |
| swept-set count | a sweep quietly covering 12 frames of 182 |
| no blank frame | a rect packed over empty atlas |
| anchor centring / base contact | art placed by a coordinate it is not standing on |
| rect inside atlas | a frame declared off the edge |

### 2. `openTwinRefusal` — a building may refuse to open, and say why

Two rules, one of them a judgement.

**`library_open` is a different building.** Closed: half-timbered plaster
cottage, orange tile roof, brick chimney. Open: dressed-sandstone Roman arcade
with round arches. Cross-fading them at one base centre is a scene swap in
place, which world doctrine forbids outright — and the library is drawn on every
hamlet island, so a close-zoom camera on it morphs a cottage into a ruin.

**Nothing mechanical catches that, and it was measured before it was asserted.**
The pack is drawn from one master palette: colour overlap between `library` and
`library_open` is 1.000/0.822 — *higher* than four twins that are correct. A
palette gate would have been a sensor pointed at something other than the
control. So identity is an eye judgement, and what the machine holds is whether
the judgement is still about these bytes: every verdict carries an FNV-1a/32 of
the frame's RGBA, recomputed from the shipped atlas each run. Regenerate the art
and the verdict goes red and must be passed again.

**The footprint rule is DERIVED, not chosen.** `iso-scene.footprintOf` composes
the layout from the shipped pack's drawn size for the sprite that will actually
be drawn — the closed one — so every clearance and neighbour on the island was
placed against the closed frame's ground diamond. A twin that is *bigger* on the
ground overhangs land the layout already promised, at the exact moment the
camera is closest. One-sided on purpose: a *narrower* twin is what a roof coming
off looks like (the eaves overhang the walls), and all seven correct twins are on
that side. Measured on the shipped atlas — `camp_log_cabin_open` +4.2px
half-width, `cottage_b_open` +3.8px, `officer_house_b_open` +4.2px / +3.3px deep.

Net on a real hamlet island: **four of seven still open** (`great_house`,
`workshop`, `cottage_a`, `officer_house_c`), three keep the interim roof-fade.

### 3. `INTERIOR_KIT` — no fixture enters unjudged

Five of the eight `int_*` frames honour the doctrine the module was written
under; three do not, and they were harmless only because the canvas happened to
place exactly one of them:

- `int_stove` — bakes animate state (lit fire, cooking pot, rising smoke) and
  stands on its own mossy **outdoor** ground plate. The green plate is measured
  in the arm; the fire is the eye's, held by the hash.
- `int_table` — bakes a seat count; the chairs are drawn around it.
- `int_postbox` — is not a postbox. A roofed outdoor shed on its own plinth.

`kitFrame()` is now the only way the renderer may name a fixture, and the canvas
goes through it. `pack.frames.int_stove` type-checks and draws; that is exactly
how the next round would have shipped a baked count with the suite green.

### 4. The arm that was about "has roof-off art" now splits its answer

"Has no twin" and "has a twin the world refuses" were one bucket in
`iso-cutaway.test.ts`. Split, with the refused set pinned by name — so the day a
building silently stops opening it cannot join a list nobody reads.

## Mutations — 9 run

`openFrameOf` ignores the refusal · the judged set emptied · the footprint rule
made symmetric · the slack widened to 999 · the depth rule deleted · `kitFrame`
stops consulting the kit · a rejected fixture promoted into the kit · a judged
frame's pixel hash gone stale · the canvas reaching past the kit into
`pack.frames`. Harness and result in the round's report.

## One arm was WRONG on its first run, and the suite said so

The first cut of the "latent art" arm walked the `resolve` table and concluded
`officer_house_b` and `officer_house_c` were unreachable. They are not:
`resolveFrame` refines per lot by `kind`, so a hamlet island draws both. The
claim is now made against a **composed scene**, which is the only place a claim
about what the world draws can be made. Recorded because the same shape of error
— reasoning about a table instead of the artifact — is what put nineteen
unjudged frames in the atlas.

## Record damage repaired

`136de037` overwrote `iso-port-composition-cp3.md`, destroying the 164-line
adversarial re-review written by `1379c62b` (51 insertions, 164 deletions). cp3
is restored from history; the cutaway round's review is now cp17; this is cp18.

## What this round did NOT fix, and why

- **`great_house_open` ships built-in cabinets with contents.** Kept, declared as
  art debt, pinned by hash. It is the only interior officers are ever drawn in,
  the casework reads as architecture rather than a fixture the compositor fills,
  and refusing it would leave the cutaway with nothing worth opening. **Captain's
  eye.**
- **`cottage_c_open` / `camp_log_cabin_open`** — defects are latent: no composed
  island draws their closed frames. Pinned, so it goes red if that changes.
- **Four measured structures still have no inspect card** (`flagpole`,
  `noticeboard`, `lantern_posts`, `composter`). Adding rows to
  `world-buildings.ts` would add top-down bboxes and change the top-down pick,
  which this round is required to leave byte-identical. Declared, not invented.
