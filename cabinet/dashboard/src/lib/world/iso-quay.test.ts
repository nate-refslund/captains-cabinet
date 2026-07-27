/**
 * The harbour must not read as a road.
 *
 * Captain, 2026-07-27, looking at `/world?iso=1`: "this here doesn't look like
 * the jetty or harbor it looks like the road?" — the wharf and the finger pier
 * were painted with `groundField('dirt')`, the SAME material as the dirt lane
 * running down to them, so the harbour was a tan strip walking into the water.
 * The second half of the same message, "the road — can you put it beneath the
 * centre concrete?", is the paint ORDER: the lanes were laid after the plaza,
 * so the road crossed the paved square instead of running under it.
 *
 * Both arms below are written to go RED if either is undone. The material arm
 * samples the two surfaces and requires a real colour separation, so repainting
 * the deck in the lane's ground class fails on pixels rather than on a name;
 * the order arm reads the engine's own paint sequence. Both were proven by
 * mutation — three of them, applied, run red, and restored; the run log is in
 * shared/interfaces/reviews/iso-port-composition-cp12-quay-material-order.md.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import {
  DECK_COLOURS,
  FASCIA,
  JETTY_POST_STEP,
  JOINT,
  PLANK,
  PLANK_W,
  POST_COLOURS,
  POST_SIDE,
  POST_STEP,
  POST_TOP,
  deckStripRects,
  jettyDeckRects,
  jettyPostRects,
  quayHash,
  wharfPostRects,
  type DeckRect,
} from './iso-quay'
import { RAMPS, groundField } from './iso-terrain'

const ENGINE = path.resolve(__dirname, '..', '..', 'components', 'world', 'engine-canvas.tsx')
const RASTER = path.resolve(
  __dirname, '..', '..', '..', '..', 'scripts', 'world-capture', 'raster.py'
)

/** A wharf of the shape harbour.ts emits: a wandering waterline, 12px samples. */
const SHORE = Array.from({ length: 18 }, (_, i) => ({
  x: 1092 + i * 12,
  y: 1269 - Math.round(18 * Math.sin((i / 17) * Math.PI)),
}))
const DEPTH = 30

const rgb = (c: number) => [(c >> 16) & 0xff, (c >> 8) & 0xff, c & 0xff]
const dist = (a: number[], b: number[]) =>
  Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])

/** Paint a rect list into a colour grid; -1 is unpainted. */
function paint(rects: DeckRect[]): {
  grid: Int32Array
  x0: number
  y0: number
  w: number
  h: number
} {
  const x0 = Math.min(...rects.map((r) => r.x))
  const y0 = Math.min(...rects.map((r) => r.y))
  const x1 = Math.max(...rects.map((r) => r.x + r.w))
  const y1 = Math.max(...rects.map((r) => r.y + r.h))
  const w = x1 - x0
  const h = y1 - y0
  const grid = new Int32Array(w * h).fill(-1)
  for (const r of rects) {
    for (let y = r.y; y < r.y + r.h; y++) {
      for (let x = r.x; x < r.x + r.w; x++) grid[(y - y0) * w + (x - x0)] = r.color
    }
  }
  return { grid, x0, y0, w, h }
}

/** The mean colour of every painted pixel. */
function meanOf(grid: Int32Array): number[] {
  let n = 0
  const s = [0, 0, 0]
  for (const c of grid) {
    if (c < 0) continue
    const p = rgb(c)
    s[0] += p[0]
    s[1] += p[1]
    s[2] += p[2]
    n++
  }
  expect(n).toBeGreaterThan(0)
  return [s[0] / n, s[1] / n, s[2] / n]
}

const wharf = deckStripRects(SHORE, DEPTH, 3)
const jetty = jettyDeckRects({ x: 1304, y: 1265 }, { x: 1328, y: 1392 }, 44, 11)
const wharfPosts = wharfPostRects(SHORE, DEPTH, 5)
const jettyPosts = jettyPostRects({ x: 1304, y: 1265 }, { x: 1328, y: 1392 }, 44, 11)

describe('the quay is timber, not the road', () => {
  it('a wharf and a pier are actually drawn (the arms below are not vacuous)', () => {
    expect(wharf.length).toBeGreaterThan(500)
    expect(jetty.length).toBeGreaterThan(200)
    // degenerate ends: no shore, no depth, no pier => nothing, never a stub
    expect(deckStripRects([], DEPTH, 3)).toHaveLength(0)
    expect(deckStripRects(SHORE, 0, 3)).toHaveLength(0)
    expect(jettyDeckRects({ x: 10, y: 10 }, { x: 10, y: 11 }, 44, 11)).toHaveLength(0)
    expect(jettyDeckRects({ x: 10, y: 10 }, { x: 10, y: 200 }, 0, 11)).toHaveLength(0)
  })

  it('the deck material is NOT the lane material', () => {
    // The lane's material is whatever the engine paints lanes with — read out
    // of the engine rather than assumed, so this comparison cannot go stale.
    const src = fs.readFileSync(ENGINE, 'utf8')
    const laneCall = src.match(/paintClass\(lanes, '([a-z_]+)'/)
    expect(laneCall, 'the engine no longer paints lanes through paintClass').toBeTruthy()
    const laneClass = laneCall![1] as 'dirt'
    expect(laneClass).toBe('dirt')

    // 1. no deck tone IS a lane tone, and the two structural colours — the
    //    joints and the fascia, which are most of what the eye reads as
    //    carpentry — are nowhere near the ramp.
    //
    //    Note what is NOT claimed: the reference's PLANK palette is not
    //    disjoint from the dirt ramp stop by stop (its lightest board, 9e764e,
    //    sits 4.5 units from the ramp's 9c7a4e). It is ported verbatim anyway,
    //    because the still the Captain approved was drawn with it and the
    //    separation that makes a deck read as a deck is the one measured
    //    below — a darker surface broken by joints — not a novel hue.
    const laneRamp = RAMPS[laneClass].map(rgb)
    for (const c of DECK_COLOURS) {
      expect(RAMPS[laneClass], `deck colour ${c.toString(16)} IS a lane tone`).not.toContain(c)
    }
    for (const c of [JOINT, FASCIA]) {
      for (const l of laneRamp) expect(dist(rgb(c), l)).toBeGreaterThan(40)
    }

    // 2. the two surfaces, as painted, are a real distance apart — measured
    //    TWICE, because measuring only once hides half the surface. The joints
    //    and the fascia are dark, and they drag the whole-deck mean down far
    //    enough that a plank palette repainted in lane tones still clears a
    //    whole-deck threshold: that mutation was run and it went GREEN against
    //    the whole-deck arm alone. So the BOARD FACES are measured on their
    //    own as well, and they are the arm that actually holds.
    const painted = paint([...wharf, ...jetty]).grid
    const faces = painted.map((c) => (PLANK.includes(c) ? c : -1))
    const deckMean = meanOf(painted)
    const faceMean = meanOf(faces)
    const field = groundField(laneClass, 240, 120, 0, 1092, 1269)
    let n = 0
    const lane = [0, 0, 0]
    for (let i = 0; i < field.w * field.h; i++) {
      lane[0] += field.rgba[i * 4]
      lane[1] += field.rgba[i * 4 + 1]
      lane[2] += field.rgba[i * 4 + 2]
      n++
    }
    const laneMean = [lane[0] / n, lane[1] / n, lane[2] / n]
    expect(dist(deckMean, laneMean), 'the deck as a whole is the lane').toBeGreaterThan(30)
    expect(dist(faceMean, laneMean), 'the BOARDS are the lane').toBeGreaterThan(25)

    // 3. and the separation has a DIRECTION: weathered timber sits below a
    // sunlit dirt track on every channel, which is what stops the deck from
    // reading as more road.
    for (let ch = 0; ch < 3; ch++) {
      expect(deckMean[ch]).toBeLessThan(laneMean[ch] - 12)
      expect(faceMean[ch], 'a board face is as light as the lane').toBeLessThan(laneMean[ch] - 12)
    }
  })

  it('the deck reads as laid boards — a tone per board, and a joint under each', () => {
    const { grid, w, h, y0 } = paint(wharf)
    // every plank tone is used; no board is a flat repeat of its neighbour
    const used = new Set<number>()
    for (const c of grid) if (c >= 0 && PLANK.includes(c)) used.add(c)
    expect(used.size).toBeGreaterThanOrEqual(3)

    // A joint under EVERY board. Counted per column, not per screen row: the
    // boards follow the waterline, so a joint course is a wandering diagonal
    // and a row-wise count would report one course for a deck that has three.
    const boards = Math.max(3, Math.floor(DEPTH / PLANK_W))
    let columnsJointed = 0
    let columnsPainted = 0
    for (let x = 0; x < w; x++) {
      let joints = 0
      let painted = 0
      for (let y = 0; y < h; y++) {
        const c = grid[y * w + x]
        if (c < 0) continue
        painted++
        if (c === JOINT) joints++
      }
      if (painted < DEPTH) continue
      columnsPainted++
      if (joints >= boards) columnsJointed++
    }
    expect(columnsPainted).toBeGreaterThan(100)
    expect(
      columnsJointed / columnsPainted,
      'the boards have no joint between them — the deck is one smooth surface'
    ).toBeGreaterThan(0.9)

    // butt joints: JOINT pixels standing in a column INSIDE a board, which is
    // what breaks the boards into lengths rather than one 200px plank
    const buttColumns = new Set<number>()
    for (let x = 0; x < w; x++) {
      let run = 0
      for (let y = 0; y < h; y++) {
        if (grid[y * w + x] === JOINT) run++
        else {
          if (run >= 4) buttColumns.add(x)
          run = 0
        }
      }
      if (run >= 4) buttColumns.add(x)
    }
    expect(buttColumns.size, 'no butt joints between board ends').toBeGreaterThanOrEqual(4)
    expect(y0).toBeLessThan(1270)
  })

  /**
   * THE PILINGS — the half of the quay the engine did not have.
   *
   * `world-capture/raster.py:418` has called `quay.posts` since it was written,
   * so the approved offline still shows a wharf standing on legs; the engine
   * drew only the deck surface. Measured on a fresh hamlet capture, 3 wharf and
   * 6 jetty pilings were missing. These arms measure the pilings' geometry
   * against the deck's, so a piling that stopped hanging below the deck — the
   * one thing that makes the wharf read as built over water — fails.
   */
  it('the wharf stands on pilings, and they hang BELOW the deck', () => {
    // not vacuous: the wharf here is 204px of shore at a 64px step
    const heads = wharfPosts.filter((r) => r.color === POST_SIDE)
    expect(heads.length).toBeGreaterThanOrEqual(3)
    expect(wharfPosts.some((r) => r.color === POST_TOP)).toBe(true)
    // degenerate ends: nothing, never a stub
    expect(wharfPostRects([], DEPTH, 5)).toHaveLength(0)
    expect(wharfPostRects(SHORE, 0, 5)).toHaveLength(0)
    expect(wharfPostRects(SHORE, DEPTH, 5, 0)).toHaveLength(0)
    // one piling per step along the wharf, and no two on the same column
    const xs = heads.map((r) => r.x).sort((a, b) => a - b)
    for (let i = 1; i < xs.length; i++) expect(xs[i] - xs[i - 1]).toBe(POST_STEP)
    // EVERY shaft starts below the deck's own fascia in its column — that is
    // what "the wharf stands on them" means, and painting them level with the
    // deck would make them planks.
    const deckBottom = new Map<number, number>()
    for (const r of wharf) {
      const b = r.y + r.h
      for (let x = r.x; x < r.x + r.w; x++) {
        deckBottom.set(x, Math.max(deckBottom.get(x) ?? -Infinity, b))
      }
    }
    let checked = 0
    for (const h of heads) {
      const under = deckBottom.get(h.x + Math.floor(h.w / 2))
      if (under === undefined) continue
      checked++
      expect(h.y + h.h).toBeGreaterThan(under)
    }
    expect(checked).toBeGreaterThanOrEqual(3)
  })

  it('the finger pier walks out on pairs of pilings', () => {
    const shafts = jettyPosts.filter((r) => r.color === POST_SIDE)
    // 129px of pier at a 46px step = 3 stations, two legs each
    expect(shafts.length).toBe(6)
    expect(shafts.length % 2).toBe(0)
    expect(jettyPosts.some((r) => r.color === POST_TOP)).toBe(true)
    expect(jettyPostRects({ x: 10, y: 10 }, { x: 10, y: 11 }, 44, 11)).toHaveLength(0)
    expect(jettyPostRects({ x: 10, y: 10 }, { x: 10, y: 200 }, 0, 11)).toHaveLength(0)
    // the legs stand at the pier's two side EDGES, never under its middle
    const deckX: { lo: number; hi: number }[] = []
    for (const r of jetty) deckX.push({ lo: r.x, hi: r.x + r.w })
    for (const s of shafts) {
      const cx = s.x + Math.floor(s.w / 2)
      const rowMid = jetty.filter((r) => Math.abs(r.y - s.y) <= 1)
      if (rowMid.length === 0) continue
      const lo = Math.min(...rowMid.map((r) => r.x))
      const hi = Math.max(...rowMid.map((r) => r.x + r.w))
      const mid = (lo + hi) / 2
      expect(Math.abs(cx - mid)).toBeGreaterThan((hi - lo) / 4)
    }
    // and they step along the pier at the reference's own pitch
    const ys = [...new Set(shafts.map((r) => r.y))].sort((a, b) => a - b)
    expect(ys.length).toBe(3)
    for (let i = 1; i < ys.length; i++) {
      expect(ys[i] - ys[i - 1]).toBeGreaterThan(JETTY_POST_STEP * 0.5)
    }
  })

  it('a piling is not a plank and not the lane', () => {
    // the two post tones are their own material: neither is a deck tone, and
    // neither is a stop of the ground ramp the lanes are painted with
    for (const c of POST_COLOURS) {
      expect(DECK_COLOURS, `post colour ${c.toString(16)} IS a deck tone`).not.toContain(c)
      expect(RAMPS.dirt, `post colour ${c.toString(16)} IS a lane tone`).not.toContain(c)
    }
  })

  it('the engine draws the pilings the offline still already drew', () => {
    const src = fs.readFileSync(ENGINE, 'utf8')
    const start = src.indexOf('const hb = layout.harbour')
    const end = src.indexOf('const rt = PIXI.RenderTexture.create', start)
    const block = src.slice(start, end)
    expect(block).toContain('wharfPostRects(')
    expect(block).toContain('jettyPostRects(')
    // AFTER the deck, so a post head sits under the front edge rather than on
    // top of the boards
    expect(block.indexOf('deckStripRects(')).toBeLessThan(block.indexOf('wharfPostRects('))
    // and the mirror has been drawing them all along — if it ever stops, this
    // port is alone again
    const r = fs.readFileSync(RASTER, 'utf8')
    expect(r).toContain('quay.posts(')
  })

  it('the deck stands ABOVE the water — a fascia lip under the front edge', () => {
    const { grid, w, h } = paint(wharf)
    let columnsWithLip = 0
    for (let x = 0; x < w; x++) {
      let lastPlank = -1
      let lip = 0
      for (let y = 0; y < h; y++) {
        const c = grid[y * w + x]
        if (c >= 0 && PLANK.includes(c)) lastPlank = y
        if (c === FASCIA) lip++
      }
      // the lip is below every board in its own column, and it has thickness
      if (lip >= 3 && lastPlank >= 0) {
        let below = true
        for (let y = 0; y <= lastPlank; y++) if (grid[y * w + x] === FASCIA) below = false
        if (below) columnsWithLip++
      }
    }
    expect(columnsWithLip, 'the deck has no fascia — it is painted on the water').toBeGreaterThan(
      w * 0.5
    )
  })

  it("quayHash reproduces the reference's own board hash", () => {
    // quay.py _hash(3, 7, 11) in Python: (3*73856093 ^ 7*19349663 ^ 11*83492791) & 0xFFFF
    const py = (3 * 73856093) ^ (7 * 19349663) ^ (11 * 83492791)
    expect(quayHash(3, 7, 11)).toBe(py & 0xffff)
    expect(quayHash(0, 0, 0)).toBe(0)
  })
})

describe('the engine paints the harbour and the square in the right order', () => {
  const src = fs.readFileSync(ENGINE, 'utf8')

  it('the wharf and the pier are drawn with the deck material, not a ground class', () => {
    const start = src.indexOf('const hb = layout.harbour')
    expect(start, 'the iso terrain no longer reads layout.harbour').toBeGreaterThan(0)
    const end = src.indexOf('const rt = PIXI.RenderTexture.create', start)
    expect(end).toBeGreaterThan(start)
    const block = src.slice(start, end)
    expect(block).toContain('deckStripRects(')
    expect(block).toContain('jettyDeckRects(')
    // the regression itself: the deck painted with the lane's ground class
    expect(block).not.toMatch(/paintClass\([^)]*'dirt'/)
    expect(block).not.toMatch(/paintClass\(/)
  })

  it('the lanes are laid BENEATH the paving, not over it', () => {
    const lane = src.indexOf("paintClass(lanes, 'dirt'")
    const plaza = src.indexOf("['plaza', 'cobble']")
    expect(lane, 'the lane paint call moved — re-point this arm').toBeGreaterThan(0)
    expect(plaza, 'the plaza paint loop moved — re-point this arm').toBeGreaterThan(0)
    expect(lane, 'the paving is painted before the lanes: the road stops at the square').toBeLessThan(
      plaza
    )
    // and both still sit inside the one baked ground, before it is rendered out
    const bake = src.indexOf('const rt = PIXI.RenderTexture.create', plaza)
    expect(bake).toBeGreaterThan(plaza)
  })

  it('the offline still renderer draws the SAME deck (no second wharf)', () => {
    // raster.py has drawn timber since it was written; the engine was the one
    // that diverged. If the mirror ever stops using quay.py, this port is
    // alone again and the two renderers can drift apart unnoticed.
    const r = fs.readFileSync(RASTER, 'utf8')
    expect(r).toContain('quay.deck_strip(')
    expect(r).toContain('quay.jetty(')
    // and the mirror's own order is the one the engine now matches
    expect(r.indexOf('canvas.paste(ground.dirt')).toBeLessThan(r.indexOf('by_kind.get("plaza"'))
  })
})
