/**
 * ISO-QUAY — the timber deck, ported from designs/world-mockup-v2/quay.py.
 *
 * THE DEFECT THIS EXISTS FOR (Captain, 2026-07-27): `/world?iso=1` painted the
 * wharf and the finger pier with the ground class the DIRT LANE uses. The
 * harbour therefore read as a wide tan track walking out into the water — "this
 * here doesn't look like the jetty or harbor it looks like the road?". The
 * offline still renderer never had the defect: `world-capture/raster.py` has
 * called `quay.deck_strip` / `quay.jetty` since it was written, so the approved
 * still shows timber and the live engine showed a road. This module closes that
 * divergence by giving the engine the SAME deck the mirror draws.
 *
 * WHY THE DECK IS DRAWN AND NOT A GROUND FIELD. Every other surface in the iso
 * ground is a world-anchored noise field masked to a shape (iso-terrain.ts), and
 * a deck cannot be one: its boards run ALONG THE WATERLINE, which wanders, so a
 * field banded in screen y would cut across the boards wherever the shore rises.
 * quay.py's own header records the older form of the same mistake — stamping a
 * deck sprite along the shore "piles overlapping slabs into a jumbled
 * staircase". So the deck is one continuous surface laid between the shore
 * polyline and `depth` px below it, and harbour.ts emits exactly that geometry
 * (a polyline and a depth) for this file to draw.
 *
 * WHAT MAKES IT READ AS TIMBER rather than as ground, in the reference's own
 * order: a PLANK palette that is DARKER ON AVERAGE than the dirt ramp (not
 * stop-for-stop — see the palette note below); a tone per BOARD and per run
 * along its length, so it is laid timber and not one smooth ramp; a JOINT line
 * under every board; butt joints between board ends; and a FASCIA lip below the
 * front edge, which is what gives the deck thickness above the water instead of
 * looking painted onto it.
 *
 * PURE: no PIXI, no DOM, no clock, no unseeded randomness. Returns a flat list
 * of axis-aligned rects for the renderer to fill, which is what makes the
 * material testable without a browser — and the material claim (deck ≠ lane) is
 * the arm that keeps this defect from coming back.
 */
import type { Point } from './iso-layout/space'

/**
 * quay.py:13-17, verbatim. These ARE the reference's tones: the still the
 * Captain approved was drawn with them, and a hue invented here would be a hue
 * no corpus fitted.
 *
 * THE PALETTES ARE NOT STOP-FOR-STOP DISJOINT and pretending otherwise would be
 * the lie: the lightest board, 0x9e764e, is 4.5 units from RAMPS.dirt's
 * 0x9c7a4e. What separates a deck from a road is measured rather than asserted
 * — the board faces average 55 RGB units from the lane's field and are darker
 * on every channel by 27 or more, and the joints and the fascia are 40+ from
 * every stop of the ramp (iso-quay.test.ts, "the deck material is NOT the lane
 * material"; the numbers are in the cp12 review artifact).
 */
export const PLANK: readonly number[] = [0x7a5838, 0x86623e, 0x926c46, 0x9e764e, 0xa88056]
/** The line under each board and between board ends. quay.py:14. */
export const JOINT = 0x5c422a
/** The front lip that gives the deck thickness above the water. quay.py:15. */
export const FASCIA = 0x684a2e
/** A piling's shaft, standing in the water under the deck. quay.py:17 POSTSID. */
export const POST_SIDE = 0x6c4e32
/** The lit cap on a piling's head. quay.py:16 POSTTOP. */
export const POST_TOP = 0x967048

/** quay.py:25 — board width, in layout px. */
export const PLANK_W = 13
/** quay.py:51 — butt joints every this many px along a wharf. */
export const BUTT_PITCH = 34
/** quay.py:59 — how far the fascia hangs below the deck's front edge. */
export const FASCIA_DROP = 9
/** quay.py:89 — a jetty's boards run ACROSS the pier, one joint every 9 steps. */
export const JETTY_BOARD = 9
/** quay.py:85 — the pier walks out with y squashed by the iso projection. */
export const JETTY_Y_SQUASH = 0.86

/**
 * THE PILINGS — quay.py:68 `posts` and :93-97, the half of the quay the engine
 * did not have.
 *
 * WHAT WAS MISSING (measured 2026-07-27 on a fresh hamlet capture): 3 wharf
 * pilings and 6 jetty pilings that `world-capture/raster.py:418` has drawn
 * since it was written and the live engine never did. The port took
 * `deck_strip` and `jetty` and stopped at the deck surface, so the wharf stood
 * on nothing — which is the same class of defect as the deck being painted with
 * the road's material, one layer down: a structure over water that does not
 * show what holds it up reads as pasted onto the sea.
 *
 * THEY ARE NOT PART OF THE DECK and are emitted by their own functions, so the
 * deck's own arms (a tone per board, a joint under each, a fascia below every
 * board in its column) keep measuring the deck and nothing else. A piling is
 * BELOW the fascia by construction — that is what makes the wharf stand up —
 * and folding it into `deckStripRects` would have put a POST_TOP pixel under
 * the front edge in half the columns and quietly weakened the fascia arm.
 */
/** quay.py:68 — one piling every this far along the wharf. */
export const POST_STEP = 64
/** quay.py:68 — the first piling sits this far in from the wharf's west end. */
export const POST_INSET = 18
/** quay.py:74 — the shaft's half width; PIL's rectangle is corner-inclusive. */
export const POST_HALF = 9
/** quay.py:75 — how far the shaft drops below the deck's front edge. */
export const POST_HEIGHT = 26
/** quay.py:73 — the shaft's head sits this far under the fascia's own top. */
export const POST_DROP = 8
/** quay.py:76 — the cap ellipse's half height. */
export const POST_CAP = 5
/** quay.py:94 — a jetty stands on a pair of pilings every this many steps. */
export const JETTY_POST_STEP = 46
/** quay.py:96 — the jetty piling's half width and drop. */
export const JETTY_POST_HALF = 6
export const JETTY_POST_HEIGHT = 30
/** quay.py:97 — the jetty cap ellipse's half height. */
export const JETTY_POST_CAP = 4

/** One axis-aligned fill. The whole deck is a list of these. */
export interface DeckRect {
  x: number
  y: number
  w: number
  h: number
  color: number
}

/**
 * quay.py:20 `_hash`, reproduced exactly.
 *
 * Python's ints are arbitrary precision and JavaScript's are doubles, so the
 * products are taken with Math.imul: only the low 16 bits survive the mask, and
 * bitwise ops depend only on the low bits of their operands, so the low 32 bits
 * Math.imul keeps are enough for the result to be identical to the reference's.
 * Every argument this file passes is non-negative, which is what makes the
 * floor-division match Python's `//`.
 */
export function quayHash(i: number, j: number, seed: number): number {
  return ((Math.imul(i, 73856093) ^ Math.imul(j, 19349663) ^ Math.imul(seed, 83492791)) >>> 0) & 0xffff
}

/**
 * The waterline's y in one column, by linear interpolation between samples.
 * quay.py:33 `top_at`, including its behaviour off the ends (clamp to the
 * nearest end point rather than extrapolate).
 */
function topAt(pts: readonly Point[], x: number): number {
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i]
    const b = pts[i + 1]
    if (a.x <= x && x <= b.x && b.x !== a.x) {
      return a.y + (b.y - a.y) * ((x - a.x) / (b.x - a.x))
    }
  }
  return x < pts[0].x ? pts[0].y : pts[pts.length - 1].y
}

/**
 * The wharf deck: boards running WITH the shore between `shore` and `depth`
 * px below it, plus the joints and the fascia lip. quay.py:24 `deck_strip`.
 *
 * The boards follow the waterline column by column rather than being laid on a
 * straight band, which is the whole reason harbour.ts emits a polyline: a deck
 * whose front edge is straight while the shore behind it wanders reads as a
 * slab dropped on the water.
 */
export function deckStripRects(
  shore: readonly Point[],
  depth: number,
  seed: number,
  plankW = PLANK_W
): DeckRect[] {
  const out: DeckRect[] = []
  if (shore.length < 2 || depth <= 0) return out
  const xs = shore.map((p) => p.x)
  const x0 = Math.ceil(Math.min(...xs))
  const x1 = Math.floor(Math.max(...xs))
  if (x1 <= x0) return out
  const n = Math.max(3, Math.floor(depth / plankW))

  // the boards, tone varying per board AND along its length
  for (let k = 0; k < n; k++) {
    const f0 = k / n
    const f1 = (k + 1) / n
    for (let x = x0; x < x1; x++) {
      const t = topAt(shore, x)
      const yTop = Math.round(t + depth * f0)
      const yEnd = Math.round(t + depth * f1) - 2 // last board row (inclusive)
      const color = PLANK[(quayHash(k, Math.floor(x / 26), seed) + k) % PLANK.length]
      if (yEnd >= yTop) out.push({ x, y: yTop, w: 1, h: yEnd - yTop + 1, color })
      // the line under the board — what separates one course from the next
      out.push({ x, y: yEnd + 1, w: 1, h: 1, color: JOINT })
    }
  }

  // butt joints between board ends
  for (let x = x0; x < x1; x += BUTT_PITCH) {
    const jx = x + (quayHash(Math.floor(x / BUTT_PITCH), 3, seed) % 12)
    if (jx >= x1) continue
    const t = topAt(shore, jx)
    out.push({ x: jx, y: Math.round(t + 2), w: 1, h: Math.max(1, Math.round(depth) - 3), color: JOINT })
  }

  // the fascia — a CONSTANT lip, never one that follows the shore drop:
  // quay.py:56 records that following it turned the lip into a wall at the
  // wharf's low end.
  for (let x = x0; x < x1; x++) {
    out.push({ x, y: Math.round(topAt(shore, x) + depth), w: 1, h: FASCIA_DROP, color: FASCIA })
  }

  // the deck's own upper edge, straight end to end (quay.py:60)
  const ya = topAt(shore, x0)
  const yb = topAt(shore, x1)
  for (let x = x0; x < x1; x++) {
    const t = ya + ((yb - ya) * (x - x0)) / (x1 - x0)
    out.push({ x, y: Math.round(t), w: 1, h: 1, color: JOINT })
  }
  return out
}

/**
 * The finger pier: boards running ACROSS the pier as it walks out into the
 * water at the iso angle. quay.py:80 `jetty`.
 *
 * The angle and the length are derived from the root and the seaward end the
 * SAME way world-capture/raster.py:421 derives them, so the engine and the
 * offline still renderer draw one pier rather than two that resemble each other.
 */
export function jettyDeckRects(
  at: Point,
  end: Point,
  width: number,
  seed: number
): DeckRect[] {
  const out: DeckRect[] = []
  const length = Math.round(Math.hypot(end.x - at.x, end.y - at.y))
  if (length <= 2 || width <= 0) return out
  const angle = Math.atan2(end.x - at.x, Math.max(1e-6, end.y - at.y))
  const dx = Math.sin(angle)
  const dy = Math.cos(angle)
  const half = Math.trunc(width / 2)

  for (let s = 0; s < length; s++) {
    const px = at.x + dx * s
    const py = Math.round(at.y + dy * s * JETTY_Y_SQUASH)
    // one row of boards, coalesced into runs of equal tone (the reference's
    // tone cell is 9 steps along the pier by 11 px across it)
    let runStart = -half
    let runColor = PLANK[quayHash(Math.floor(s / JETTY_BOARD), Math.floor((-half + 64) / 11), seed) % PLANK.length]
    for (let i = -half + 1; i <= half; i++) {
      const color =
        i < half
          ? PLANK[quayHash(Math.floor(s / JETTY_BOARD), Math.floor((i + 64) / 11), seed) % PLANK.length]
          : -1
      if (color !== runColor) {
        out.push({ x: Math.round(px + runStart), y: py, w: i - runStart, h: 1, color: runColor })
        runStart = i
        runColor = color
      }
    }
    // a joint across the whole pier at every board end, and the two side edges
    if (s % JETTY_BOARD === JETTY_BOARD - 1) {
      out.push({ x: Math.round(px - half), y: py, w: 2 * half, h: 1, color: JOINT })
    }
    out.push({ x: Math.round(px - half), y: py, w: 1, h: 1, color: JOINT })
    out.push({ x: Math.round(px + half), y: py, w: 1, h: 1, color: JOINT })
  }

  // the seaward end board
  const ex = at.x + dx * length
  const ey = Math.round(at.y + dy * length * JETTY_Y_SQUASH)
  out.push({ x: Math.round(ex - half), y: ey, w: 2 * half, h: 1, color: JOINT })

  // the side fascia — the pier has thickness over the water for the same
  // reason the wharf does
  for (let s = 0; s < length; s++) {
    const px = at.x + dx * s
    const py = Math.round(at.y + dy * s * JETTY_Y_SQUASH)
    out.push({ x: Math.round(px - half) - 1, y: py, w: 1, h: 2, color: FASCIA })
    out.push({ x: Math.round(px + half) + 1, y: py, w: 1, h: 2, color: FASCIA })
  }
  return out
}

/**
 * PIL's `ellipse` as scanline rects — the cap on a piling's head.
 *
 * The reference draws an ellipse and this renderer fills rects, so the cap is
 * emitted one row at a time with the ellipse's own half-width at that row. It
 * is the shape rather than an approximation of it: at 11 rows and 19px across,
 * a rect-per-row IS the rasterisation PIL would produce to within a pixel.
 */
function capRects(cx: number, cy: number, rx: number, ry: number, color: number): DeckRect[] {
  const out: DeckRect[] = []
  for (let dy = -ry; dy <= ry; dy++) {
    const half = Math.round(rx * Math.sqrt(Math.max(0, 1 - (dy / ry) ** 2)))
    if (half <= 0) continue
    out.push({ x: Math.round(cx - half), y: Math.round(cy + dy), w: 2 * half, h: 1, color })
  }
  return out
}

/**
 * The wharf's pilings — quay.py:68 `posts`, called by raster.py:418.
 *
 * They hang BELOW the deck's fascia, standing in the water, which is what makes
 * the wharf read as built over the sea rather than painted on it. Emitted
 * separately from `deckStripRects` so the deck's own arms keep measuring the
 * deck alone — see the PILINGS note above.
 */
export function wharfPostRects(
  shore: readonly Point[],
  depth: number,
  seed: number,
  step = POST_STEP
): DeckRect[] {
  const out: DeckRect[] = []
  if (shore.length < 2 || depth <= 0 || step <= 0) return out
  const xs = shore.map((p) => p.x)
  const x0 = Math.ceil(Math.min(...xs))
  const x1 = Math.floor(Math.max(...xs))
  // `seed` is accepted because the reference takes one and raster.py passes
  // `seed + 5`; the reference's own `posts` never reads it either. Named and
  // unread beats dropped from the signature, which would make the two
  // renderers' call sites diverge.
  void seed
  for (let x = x0 + POST_INSET; x < x1; x += step) {
    const y = Math.round(topAt(shore, x) + depth + POST_DROP)
    out.push({
      x: x - POST_HALF,
      y,
      w: 2 * POST_HALF + 1,
      h: POST_HEIGHT + 1,
      color: POST_SIDE,
    })
    out.push(...capRects(x, y, POST_HALF, POST_CAP, POST_TOP))
  }
  return out
}

/**
 * The finger pier's pilings — quay.py:93-97, the pairs that carry the jetty.
 *
 * One pair every JETTY_POST_STEP along the pier, at both side edges, so the
 * pier walks out on legs instead of floating.
 */
export function jettyPostRects(
  at: Point,
  end: Point,
  width: number,
  seed: number
): DeckRect[] {
  const out: DeckRect[] = []
  const length = Math.round(Math.hypot(end.x - at.x, end.y - at.y))
  if (length <= 2 || width <= 0) return out
  void seed
  const angle = Math.atan2(end.x - at.x, Math.max(1e-6, end.y - at.y))
  const dx = Math.sin(angle)
  const dy = Math.cos(angle)
  const half = width / 2
  for (let s = 0; s < length; s += JETTY_POST_STEP) {
    const px = at.x + dx * s
    const py = Math.round(at.y + dy * s * JETTY_Y_SQUASH)
    for (const sx of [-half, half]) {
      const cx = Math.round(px + sx)
      out.push({
        x: cx - JETTY_POST_HALF,
        y: py,
        w: 2 * JETTY_POST_HALF + 1,
        h: JETTY_POST_HEIGHT + 1,
        color: POST_SIDE,
      })
      out.push(...capRects(cx, py, JETTY_POST_HALF, JETTY_POST_CAP, POST_TOP))
    }
  }
  return out
}

/** Every colour a deck can be painted in — the material, as a set. */
export const DECK_COLOURS: readonly number[] = [...PLANK, JOINT, FASCIA]

/** The pilings' own two tones — timber below the deck, not deck surface. */
export const POST_COLOURS: readonly number[] = [POST_SIDE, POST_TOP]
