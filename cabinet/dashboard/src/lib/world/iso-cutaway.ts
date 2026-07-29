/**
 * THE ROOF CUTAWAY IN ISOMETRIC — real roof-off art, and a candidate rule that
 * can actually fire.
 *
 * WHAT THIS REPLACES. The cutaway shipped as `sp.alpha` on the WHOLE building
 * sprite fading to 0.08, plus an axis-aligned TilingSprite floor and a
 * rectangular desk grid drawn in TILE space. Top-down that reads as a roof
 * lifting, because a top-down building IS its roof seen from above. In iso it is
 * a ghost of the entire structure with a rectangle punched through the world
 * behind it: the great house is 196x174 standing on a ground diamond of 165x96,
 * so officers packed into that lozenge sit under a building still towering over
 * them.
 *
 * THE FIX IS ART, not geometry — `cutawayStep`/`roofAlpha` in ./lod are pure
 * tick math and are used here unchanged. The pack now ships roof-off twins
 * (`<frame>_open`: the same building with its roof removed and its own interior
 * floor and inner wall faces visible) and an interior kit of EMPTY fixtures. A
 * cutaway is then a CROSS-FADE between two frames anchored at the same base
 * centre, not a fade to transparent.
 *
 * WHY THE FIXTURES ARE EMPTY, and this is a doctrine constraint rather than an
 * art preference: a work board with pins drawn on it, or a bookshelf drawn full,
 * bakes a MEASURED QUANTITY into static art. The number of desks is the number
 * of officers and the number of pinned cards is a real count — so the art is a
 * bare board and a bare shelf, and the compositor fills them from state. This
 * project already rejected an entire design for getting that backwards.
 *
 * PURE: no clocks, no RNG, no DOM, no PixiJS.
 */
import { ROOF_ALPHA_OPEN, roofAlpha, type CutawayState } from './lod'
import { groundDiamond } from './projection'
import type { IsoPack } from './iso-pack'

/** The suffix a roof-off twin carries in the pack. */
export const OPEN_SUFFIX = '_open'

/** A roof-off frame: the name and the size it draws at. */
export interface OpenFrame {
  frame: string
  dw: number
  dh: number
}

/**
 * A verdict passed on a frame's PIXELS, and the hash of the pixels it was
 * passed on.
 *
 * WHY THE HASH IS THE POINT. A deny list is an assertion, and an assertion
 * about art outlives the art: regenerate `library_open` correctly and a bare
 * name here goes on refusing it forever, while regenerate it WRONGER and a name
 * that was removed goes on admitting it. So every judgement below is bound to
 * the bytes it was made about — `iso-art.test.ts` recomputes `pixelHash` from
 * the shipped atlas and goes red the moment a judged frame's pixels change,
 * which forces the call to be made again against the picture that now exists
 * rather than inherited from one that does not.
 *
 * FNV-1a/32 over the frame's RGBA bytes in atlas order. Cheap, stable, and it
 * is a staleness detector rather than a security primitive.
 */
export interface ArtVerdict {
  /** Why, in the words a person regenerating the art needs to read. */
  reason: string
  /** FNV-1a/32 (hex) of the frame's RGBA bytes, as judged. */
  pixelHash: string
}

/**
 * Roof-off twins the atlas SHIPS and the world REFUSES to cross-fade to.
 *
 * THE DEFECT, seen with the eye on the shipped atlas 2026-07-28: `library` is a
 * half-timbered cottage — plaster infill, orange tile roof, brick chimney — and
 * `library_open` is a dressed-sandstone Roman arcade with round arches. They
 * are not the same building with its roof taken off; they are two buildings.
 * Cross-fading one into the other at a fixed base centre is a SCENE SWAP IN
 * PLACE, which is the one thing the world doctrine forbids outright ("one
 * continuous world; zoom is level-of-detail, never a scene swap"), and the
 * library is drawn on every hamlet island — so a camera centred on it at close
 * zoom morphs a cottage into a ruin in front of the Captain.
 *
 * NOTHING MECHANICAL CATCHES THIS, and that was measured before it was
 * asserted: the whole pack is drawn from one master palette, so colour overlap
 * between `library` and `library_open` is 1.000/0.822 — HIGHER than four twins
 * that are correct. A palette gate would have been a sensor pointed at
 * something other than the control. Identity of a building is an eye judgement;
 * what a machine can hold is whether that judgement is still about these bytes.
 *
 * A refused building is not broken — it keeps the interim behaviour every
 * building without roof-off art gets: the roof fades, nothing is drawn inside.
 */
export const OPEN_TWIN_REJECTED: ReadonlyMap<string, ArtVerdict> = new Map<string, ArtVerdict>([
  [
    'library_open',
    {
      reason:
        'a different building: the closed library is a half-timbered plaster cottage with an ' +
        'orange tile roof, the open twin is a dressed-sandstone arcade with round arches — ' +
        'cross-fading them is a scene swap in place',
      // Re-judged 2026-07-28 after the cutout fix re-cut every twin. The library's
      // DRAWN pixels did not change — it carried no baked lawn, so the lawn peel
      // removed nothing and only the transparent margin was cropped — and it is
      // still a sandstone arcade against a plaster cottage. The refusal stands
      // verbatim; only the bytes it is bound to moved.
      pixelHash: '6ea02fa6',
    },
  ],
])

/**
 * Why a roof-off twin may not be used, or null when it may.
 *
 * TWO RULES, and only one of them is a judgement.
 *
 * 1. THE JUDGED SET above — a twin that is not the same building.
 *
 * 2. IT MAY NOT BE BIGGER ON THE GROUND THAN WHAT IT REPLACES, and this rule is
 *    DERIVED rather than chosen. `iso-scene.footprintOf` composes the layout
 *    with the shipped pack's drawn size for the sprite that will actually be
 *    drawn — the CLOSED one — so every clearance, lot and neighbour on the
 *    island was placed against the closed frame's ground diamond. A twin with a
 *    wider or deeper diamond therefore overhangs ground the layout already
 *    promised to something else, and it does it at the exact moment the camera
 *    is closest to it. Measured on the shipped atlas: `officer_house_b_open`
 *    +4.2px half-width and +3.3px deep — the only twin still on that side.
 *
 *    RE-MEASURED 2026-07-28. `camp_log_cabin_open` (+4.2px) and `cottage_b_open`
 *    (+3.8px) used to be refused here and now are not. Neither twin was
 *    redrawn: both were carrying a baked exterior LAWN that the old base
 *    treatment could not lift, so their frames were oversized by the deck
 *    around the walls rather than by the walls. The lawn peel removed it and
 *    the buildings fell back inside their closed footprint. Both open now.
 *
 *    The rule is ONE-SIDED on purpose. A twin that is SMALLER is what a roof
 *    coming off actually looks like — the eaves overhang the walls, so the
 *    walls alone are narrower — and the nine correct twins are all on that
 *    side (great_house -11.7px, cottage_a -8.4px, officer_house_a -14.3px,
 *    workshop -0.4px). There is no defensible symmetric tolerance in this
 *    sample and inventing one would be a constant dressed as a measurement.
 *
 * 1px of slack absorbs the `min()` rounding in `groundDiamond`, nothing more.
 */
export function openTwinRefusal(pack: IsoPack, frame: string): string | null {
  const open = pack.frames[frame + OPEN_SUFFIX]
  if (!open) return null
  const judged = OPEN_TWIN_REJECTED.get(frame + OPEN_SUFFIX)
  if (judged) return judged.reason
  const closed = pack.frames[frame]
  if (!closed) return null
  const gc = groundDiamond(closed.dw, closed.dh)
  const go = groundDiamond(open.dw, open.dh)
  if (go.hw > gc.hw + 1) {
    return `roof-off twin is ${(go.hw - gc.hw).toFixed(1)}px wider on the ground than the building it replaces`
  }
  if (go.depth > gc.depth + 1) {
    return `roof-off twin is ${(go.depth - gc.depth).toFixed(1)}px deeper on the ground than the building it replaces`
  }
  return null
}

/**
 * The roof-off twin of a frame, or null when the pack ships none — or ships one
 * the world refuses (see `openTwinRefusal`).
 *
 * RESOLVED FROM THE PACK, never from a hardcoded list of which buildings have
 * interiors. A list would be a claim the atlas has to keep up with; this is the
 * atlas answering for itself, so a building whose roof-off art has not been
 * generated yet simply does not open, and the interim fade is what it gets.
 *
 * THE REFUSAL IS HERE rather than at the call sites because there are three of
 * them — `isoCutawayCandidate` and both halves of the canvas's cutaway draw —
 * and a refusal enforced in two of three is how a rejected building ends up
 * chosen as a candidate and then drawn as a roof fading to nothing over no
 * interior at all.
 */
export function openFrameOf(pack: IsoPack, frame: string): OpenFrame | null {
  const f = pack.frames[frame + OPEN_SUFFIX]
  if (!f) return null
  if (openTwinRefusal(pack, frame) !== null) return null
  return { frame: frame + OPEN_SUFFIX, dw: f.dw, dh: f.dh }
}

/**
 * THE INTERIOR KIT — which `int_*` frames may be placed in an open room, and
 * which the atlas ships that the world will not put on a floor.
 *
 * EVERY FIXTURE IS EMPTY ART FILLED FROM STATE. That is the doctrine this
 * module was written under, and it is not an art preference: the number of
 * desks is the number of officers and the number of pinned cards is a real
 * count, so a desk drawn with papers or a board drawn with pins bakes a
 * MEASURED QUANTITY into a static frame. This project rejected an entire design
 * for getting that backwards.
 *
 * WHAT THE ATLAS ACTUALLY SHIPPED, looked at rather than assumed 2026-07-28:
 * five of the eight fixtures honour it and three do not. They were harmless
 * only because the canvas happened to place exactly one of them — so the next
 * round that reaches for a stove or a table would have shipped the violation
 * with the suite green, which is why this is a table and not a comment.
 *
 * `iso-art.test.ts` requires every `int_*` frame in the pack to appear in
 * exactly one of these two maps, so a NEW fixture cannot arrive unjudged.
 */
export const INTERIOR_KIT: ReadonlyMap<string, string> = new Map<string, string>([
  ['int_desk', 'a bare desk — the compositor draws one per officer'],
  ['int_bookshelf', 'shelves drawn EMPTY; what stands on them is a count'],
  ['int_work_board', 'a bare board; every pin on it would be a measured card'],
  ['int_bunk', 'a made bed — one dwelling, one bed, no quantity to bake'],
  ['int_rug', 'floor covering; carries no state at all'],
])

/** Fixtures the atlas ships that may NOT be placed, bound to their pixels. */
export const INTERIOR_KIT_REJECTED: ReadonlyMap<string, ArtVerdict> = new Map<string, ArtVerdict>([
  [
    'int_stove',
    {
      reason:
        'bakes ANIMATE STATE into static art — a lit fire, a cooking pot and rising smoke assert ' +
        'a hearth is going that nothing measured; and it stands on its own mossy OUTDOOR ground ' +
        'plate, which is a lie about placement in a room with a plank floor',
      pixelHash: '2d4672ea',
    },
  ],
  [
    'int_table',
    {
      reason:
        'bakes a seat count — the chairs are drawn around it, so the art asserts how many people ' +
        'sit there while the compositor is the only thing that knows',
      pixelHash: '3a8d4201',
    },
  ],
  [
    'int_postbox',
    {
      reason:
        'is not the object it is named after: a roofed OUTDOOR shed on its own plinth, not a ' +
        'postbox, and not a fixture that can stand on an interior floor',
      pixelHash: 'aeee1de1',
    },
  ],
])

/** The minimum a sprite must expose for the cutaway to reason about it. */
export interface CutawaySprite {
  readonly id: string
  readonly frame: string
  /** Base centre in layout px. */
  readonly x: number
  readonly y: number
  readonly dw: number
  readonly dh: number
  /** The state object that justifies it — decoration never opens. */
  readonly role: string | null
}

/** Viewport size in screen px. */
export interface CutawayViewport {
  w: number
  h: number
}

/**
 * A candidate must be at least this tall on screen, as a fraction of viewport
 * height, before its roof comes off.
 *
 * MEASURED, not chosen (hamlet fixture, 1280x800 viewport, ISO_BASE = 1/3):
 * the great house draws 196x174 layout px, so at z=3 it is 174 screen px = 21.8%
 * of viewport height, and at the close tier's floor z=2.5 it is 145 px = 18.1%.
 * The smallest roof-off building, the camp log cabin at 128x120, is 15.0% at
 * z=3. A floor of 0.12 therefore admits every building the pack can open at
 * every zoom the close tier covers, and still refuses a 60px prop.
 */
export const ISO_CUTAWAY_MIN_H = 0.12

/**
 * The cutaway candidate under ISO: the FRONT-MOST openable building whose drawn
 * rect contains the viewport centre.
 *
 * IT IS NOT lod.cutawayCandidate's RULE, and the difference is measured rather
 * than preferred. That rule asks for ≥40% coverage of the viewport's central
 * third, which is calibrated to top-down buildings drawn at `tile * z` — a 6x5
 * tile great house is 288x240 px at z=3 against a 426x266 central third, i.e.
 * 61%, comfortably over. The ISO great house draws at its PACK size, 196x174,
 * and the iso scale re-bases by ISO_BASE = 1/3, so at z=3 (scale 1.0) it covers
 * 196*174 / (426*266) = 30% of that same box — under the floor. Ported verbatim,
 * the rule would mean NO building ever opens at any zoom, and every test of the
 * cutaway machine would stay green while the feature was dead.
 *
 * So the iso rule asks the question the product actually asks — "is the camera
 * looking AT this building" — which is scale-free and needs no coverage
 * constant: the viewport centre lands on its drawn rect, and it is big enough on
 * screen to be worth opening (ISO_CUTAWAY_MIN_H).
 *
 * FRONT-MOST rather than birth-order: `sprites` arrives depth-sorted back to
 * front, so scanning backwards returns the one the eye sees on top at the
 * centre of the screen — the same answer the pick gives for that pixel. The
 * top-down rule's birth-order tie-break exists because its bboxes do not
 * occlude; iso ones do.
 */
export function isoCutawayCandidate(
  sprites: readonly CutawaySprite[],
  pack: IsoPack,
  /**
   * The viewport centre in LAYOUT PX — `projection.project(cam.x, cam.y)`.
   * Taken already projected, and not as a camera plus a kernel, because the
   * camera speaks TILES and every sprite here speaks layout px: a function that
   * accepted both would be the sixth place in this tree that owns the transform.
   */
  centre: { x: number; y: number },
  vp: CutawayViewport,
  scale: number
): string | null {
  if (vp.w <= 0 || vp.h <= 0 || scale <= 0) return null
  const cx = centre.x
  const cy = centre.y
  const minH = vp.h * ISO_CUTAWAY_MIN_H
  for (let i = sprites.length - 1; i >= 0; i--) {
    const s = sprites[i]
    if (s.role === null) continue
    if (!openFrameOf(pack, s.frame)) continue
    if (s.dh * scale < minH) continue
    if (cx < s.x - s.dw / 2 || cx > s.x + s.dw / 2) continue
    if (cy < s.y - s.dh || cy > s.y) continue
    return s.id
  }
  return null
}

/**
 * The two alphas a cutaway building draws with this tick.
 *
 * ONE TIMING LAW. The ramp lives in lod.roofAlpha and nothing here re-derives
 * it: `t` is that ramp's own progress, recovered by inverting it, so a change to
 * CUTAWAY_FADE_MS moves both halves together and cannot desynchronise them.
 *
 * WITHOUT roof-off art (`hasOpen` false) this is exactly today's behaviour — the
 * whole sprite fades to ROOF_ALPHA_OPEN and nothing is drawn under it. WITH it,
 * the closed frame goes all the way to zero: a 0.08 ghost of the whole building
 * laid over its own open twin is a double exposure, not a lifted roof.
 */
export function cutawayMix(
  state: CutawayState,
  id: string,
  tick: number,
  hasOpen: boolean
): { closed: number; open: number } {
  const a = roofAlpha(state, id, tick)
  if (!hasOpen) return { closed: a, open: 0 }
  const t = (1 - a) / (1 - ROOF_ALPHA_OPEN)
  return { closed: 1 - t, open: t }
}

/**
 * The pack frame for a kit fixture — or null if the kit does not admit it.
 *
 * THE ONE WAY THE RENDERER MAY NAME A FIXTURE. `pack.frames.int_stove` type-checks
 * and draws; going through here means a rejected fixture cannot be placed by
 * reaching past the table, and a fixture that was never judged cannot be placed
 * at all. The canvas asks for `int_desk` and gets it; the day it asks for
 * `int_table` it gets null and draws nothing, loudly, instead of shipping a
 * baked seat count.
 */
export function kitFrame(pack: IsoPack, name: string): { dw: number; dh: number } | null {
  if (!INTERIOR_KIT.has(name)) return null
  const f = pack.frames[name]
  if (!f) return null
  return { dw: f.dw, dh: f.dh }
}

/** One placed interior fixture, at its base centre in layout px. */
export interface InteriorSlot {
  x: number
  y: number
}

/**
 * Interior fixture slots for an open room, on the ISO LATTICE.
 *
 * The room's floor is the OPEN frame's own ground diamond — the same
 * `groundDiamond` the pick, the clearance rules and checks/world_checks.py read,
 * so nothing here invents a fifth notion of where a sprite stands. Slots are
 * laid on the 2:1 lattice inside it (a step of +u runs down-right, +v
 * down-left), inset by `margin` so a desk's own width does not hang through a
 * wall, and returned BACK TO FRONT so the caller's depth sort places them
 * without a second sort.
 *
 * A RECTANGULAR GRID IS THE DEFECT THIS REPLACES: the old interior laid desks on
 * `col * (w-2)/2.5, row * 1.6` in tile space, which inside an isometric building
 * is a rectangle through the floor at the wrong angle.
 */
export function interiorSlots(
  open: OpenFrame,
  baseX: number,
  baseY: number,
  count: number,
  opts: { step?: number; margin?: number } = {}
): InteriorSlot[] {
  if (count <= 0) return []
  const g = groundDiamond(open.dw, open.dh)
  // 44px between fixtures: the great house's open room is a 105x58 inset
  // diamond, and at 34 five desks (28px wide) crowded into its middle third —
  // seen in the eye check. At 44 the same five reach x = ±44, which is the
  // room's own width. Measured on the render, not chosen.
  const step = opts.step ?? 44
  const margin = opts.margin ?? 0.34
  const hw = g.hw * (1 - margin)
  const hd = (g.depth / 2) * (1 - margin)
  if (hw <= 0 || hd <= 0) return []
  const cx = baseX
  const cy = baseY - g.depth / 2
  const out: InteriorSlot[] = []
  // Walk the lattice outward from the room's centre; keep what lands inside the
  // inset diamond. `r` bounds the walk by the widest the diamond can ever be.
  const r = Math.ceil(Math.max(hw / step, (hd * 2) / step)) + 1
  for (let u = -r; u <= r; u++) {
    for (let v = -r; v <= r; v++) {
      const x = cx + (u - v) * (step / 2)
      const y = cy + (u + v) * (step / 4)
      if (Math.abs(x - cx) / hw + Math.abs(y - cy) / hd > 1) continue
      out.push({ x, y })
    }
  }
  // CENTRE-OUT, then back to front. Taking the first `count` in depth order
  // instead packs every fixture against the back wall and leaves the front of
  // the room bare — visible in the first eye check of this change, where five
  // desks sat in the top 17px of a 58px-deep floor. Distance is measured in the
  // diamond's OWN units so a wide shallow room spreads sideways rather than
  // stacking, and the tie-break is total so the layout is replay-identical.
  const near = (p: InteriorSlot) =>
    Math.abs(p.x - cx) / hw + Math.abs(p.y - cy) / hd
  out.sort((a, b) => near(a) - near(b) || a.y - b.y || a.x - b.x)
  const kept = out.slice(0, count)
  kept.sort((a, b) => a.y - b.y || a.x - b.x)
  return kept
}

// ── the room's own child pool ───────────────────────────────────────────────

/**
 * The label the roof-off FLOOR sprite carries.
 *
 * It exists because the room container is a POOL: the draw pass re-uses the
 * same children across ticks and switches off the ones it no longer placed.
 * A pool needs to know which children it owns, and the floor is one of them.
 */
export const ROOM_FLOOR = 'floor'

/** The label prefixes the cutaway pass places and therefore owns. */
export const ROOM_MANAGED_PREFIXES: readonly string[] = ['desk:', 'off:']

/**
 * Is this room child STALE — placed by an earlier pass and not by this one?
 *
 * THE DEFECT THIS FUNCTION EXISTS FOR, measured in a browser on master
 * 2026-07-29: the roof-off room drew NOTHING. The sweep was written inline as
 * `const n = c.label; if (n && !want.has(n)) c.visible = false`, on the
 * assumption that a child nobody named has a falsy label. PixiJS 8.19 does not
 * work that way — `Sprite`'s constructor passes `label: "Sprite"` to
 * `Container` (node_modules/pixi.js/lib/scene/sprite/Sprite.mjs:18), so the
 * unnamed floor sprite arrived carrying a truthy label that was never in
 * `want`, and the tick after it was added the sweep hid it. The building faded
 * out on cue and the room behind it was never visible: officers and desks
 * standing on open grass inside the shadow of a house that had vanished.
 *
 * So the rule is inverted, and this is the invariant rather than a patch: a
 * sweep may only switch off a child it PLACED. Ownership is the label
 * namespace — the floor, and the `desk:`/`off:` slots that vary with how many
 * officers there are. Anything else is art some other code put in this
 * container, and hiding art you did not place is exactly the bug above.
 *
 * PURE: no PixiJS types, no DOM. It takes the label, so the test can hand it
 * the string a REAL `new PIXI.Sprite()` reports rather than one we imagine.
 */
export function roomChildStale(
  label: string | null | undefined,
  want: ReadonlySet<string>
): boolean {
  if (!label) return false
  if (want.has(label)) return false
  if (label === ROOM_FLOOR) return false
  return ROOM_MANAGED_PREFIXES.some((p) => label.startsWith(p))
}
