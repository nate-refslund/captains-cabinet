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
 * The roof-off twin of a frame, or null when the pack ships none.
 *
 * RESOLVED FROM THE PACK, never from a hardcoded list of which buildings have
 * interiors. A list would be a claim the atlas has to keep up with; this is the
 * atlas answering for itself, so a building whose roof-off art has not been
 * generated yet simply does not open, and the interim fade is what it gets.
 */
export function openFrameOf(pack: IsoPack, frame: string): OpenFrame | null {
  const f = pack.frames[frame + OPEN_SUFFIX]
  if (!f) return null
  return { frame: frame + OPEN_SUFFIX, dw: f.dw, dh: f.dh }
}

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
