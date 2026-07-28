/**
 * iso-art.test.ts — THE GATE THAT LOOKS AT THE ART.
 *
 * WHY IT EXISTS. On 2026-07-28 nineteen new frames entered the shipped atlas —
 * ten roof-off building twins and an eight-piece interior kit — and NOTHING
 * looked at them. The twelve world checks judge a capture, and neither judged
 * capture draws a single one of the new frames (no roof is open in either), so
 * `12/12 green` covered exactly zero of the new art. The pack tests read the
 * pack's JSON. The cutaway tests read `dw`/`dh`. Not one line in the tree had
 * ever read a pixel of the atlas, which is why an `_open` twin that is a
 * DIFFERENT BUILDING and a "postbox" that is an outdoor shed both shipped green.
 *
 * So this file decodes `atlas-0.png` — the shipped bytes, not a fixture — and
 * sweeps EVERY frame the pack declares. A frame cannot enter the atlas without
 * passing through here, and a judgement passed on a frame's pixels cannot
 * outlive those pixels.
 *
 * THE DECODER IS FORTY LINES OF `node:zlib` on purpose: a dependency to read a
 * PNG is a dependency the egg has to carry, and the atlas is 8-bit RGBA,
 * non-interlaced, which is the one PNG shape worth hand-decoding.
 */
import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { inflateSync } from 'node:zlib'
import {
  INTERIOR_KIT,
  INTERIOR_KIT_REJECTED,
  OPEN_SUFFIX,
  OPEN_TWIN_REJECTED,
  kitFrame,
  openFrameOf,
  openTwinRefusal,
} from './iso-cutaway'
import { groundDiamond } from './projection'
import { buildIsoScene } from './iso-scene'
import type { LayoutState } from './iso-layout'
import type { IsoPack } from './iso-pack'

const ISO_DIR = join(process.cwd(), 'public', 'world-assets', 'originals', 'iso')
/**
 * The pack as it is ON DISK — snake_case, exactly as the exporter wrote it.
 * `iso-pack.ts` is what turns this into an `IsoPack`; reading the raw file here
 * is deliberate, because the subject of this file is the SHIPPED artifact and a
 * parser is one more thing that could be making the bytes look fine.
 */
const RAW: {
  atlas_size: number
  counts: { frames: number; atlases: number; objects: number }
  frames: Record<string, { x: number; y: number; w: number; h: number; dw: number; dh: number }>
  resolve: Record<string, Record<string, Record<string, { frame: string }>>>
} = JSON.parse(readFileSync(join(ISO_DIR, 'world-pack.json'), 'utf8'))
/** The same object, in the shape the module under test consumes. */
const PACK = RAW as unknown as IsoPack

// ---------------------------------------------------------------------------
// PNG -> RGBA. 8-bit truecolour+alpha, non-interlaced; anything else throws
// rather than returning plausible garbage.
// ---------------------------------------------------------------------------

interface Raster {
  w: number
  h: number
  /** RGBA, row-major, 4 bytes per pixel. */
  data: Uint8Array
}

function decodePng(buf: Buffer): Raster {
  if (buf.readUInt32BE(0) !== 0x89504e47) throw new Error('not a PNG')
  let p = 8
  let w = 0
  let h = 0
  const idat: Buffer[] = []
  while (p < buf.length) {
    const len = buf.readUInt32BE(p)
    const type = buf.toString('ascii', p + 4, p + 8)
    const body = buf.subarray(p + 8, p + 8 + len)
    if (type === 'IHDR') {
      w = body.readUInt32BE(0)
      h = body.readUInt32BE(4)
      const depth = body[8]
      const colour = body[9]
      const interlace = body[12]
      if (depth !== 8 || colour !== 6 || interlace !== 0) {
        throw new Error(`unsupported PNG: depth=${depth} colour=${colour} interlace=${interlace}`)
      }
    } else if (type === 'IDAT') {
      idat.push(Buffer.from(body))
    } else if (type === 'IEND') {
      break
    }
    p += 12 + len
  }
  const raw = inflateSync(Buffer.concat(idat))
  const bpp = 4
  const stride = w * bpp
  const out = new Uint8Array(w * h * bpp)
  let q = 0
  for (let y = 0; y < h; y++) {
    const filter = raw[q++]
    const row = y * stride
    const prev = row - stride
    for (let x = 0; x < stride; x++) {
      const rawByte = raw[q + x]
      const a = x >= bpp ? out[row + x - bpp] : 0
      const b = y > 0 ? out[prev + x] : 0
      const c = x >= bpp && y > 0 ? out[prev + x - bpp] : 0
      let v: number
      switch (filter) {
        case 0:
          v = rawByte
          break
        case 1:
          v = rawByte + a
          break
        case 2:
          v = rawByte + b
          break
        case 3:
          v = rawByte + ((a + b) >> 1)
          break
        case 4: {
          const pp = a + b - c
          const pa = Math.abs(pp - a)
          const pb = Math.abs(pp - b)
          const pc = Math.abs(pp - c)
          v = rawByte + (pa <= pb && pa <= pc ? a : pb <= pc ? b : c)
          break
        }
        default:
          throw new Error(`bad PNG filter ${filter} on row ${y}`)
      }
      out[row + x] = v & 0xff
    }
    q += stride
  }
  return { w, h, data: out }
}

const ATLAS = decodePng(readFileSync(join(ISO_DIR, 'atlas-0.png')))

/** The frame's own RGBA bytes, in atlas order. */
function frameBytes(name: string): Uint8Array {
  const f = PACK.frames[name]
  if (!f) throw new Error(`no such frame ${name}`)
  const out = new Uint8Array(f.w * f.h * 4)
  for (let y = 0; y < f.h; y++) {
    const src = ((f.y + y) * ATLAS.w + f.x) * 4
    out.set(ATLAS.data.subarray(src, src + f.w * 4), y * f.w * 4)
  }
  return out
}

/** FNV-1a/32 over bytes — the same walk `ArtVerdict.pixelHash` records. */
function fnv1aBytes(b: Uint8Array): string {
  let h = 0x811c9dc5
  for (let i = 0; i < b.length; i++) {
    h ^= b[i]
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return h.toString(16).padStart(8, '0')
}

interface Shape {
  opaque: number
  minX: number
  maxX: number
  /** Lowest SOLID row — where the art's mass ends. */
  maxY: number
  /** Lowest row with any ink at all, shadows included — where the art ends. */
  maxYInk: number
}

function shapeOf(name: string): Shape {
  const f = PACK.frames[name]
  const px = frameBytes(name)
  let opaque = 0
  let minX = f.w
  let maxX = -1
  let maxY = -1
  let maxYInk = -1
  for (let y = 0; y < f.h; y++) {
    for (let x = 0; x < f.w; x++) {
      const a = px[(y * f.w + x) * 4 + 3]
      if (a > 0 && y > maxYInk) maxYInk = y
      if (a < 200) continue
      opaque++
      if (x < minX) minX = x
      if (x > maxX) maxX = x
      if (y > maxY) maxY = y
    }
  }
  return { opaque, minX, maxX, maxY, maxYInk }
}

const ALL = Object.keys(PACK.frames).sort()

/** A pack with only the frames a case needs — no fixture inherits the atlas. */
function packOf(frames: Record<string, { dw: number; dh: number }>): IsoPack {
  const f: Record<string, unknown> = {}
  for (const [n, s] of Object.entries(frames)) {
    f[n] = {
      atlas: 0, x: 0, y: 0, w: s.dw, h: s.dh,
      dw: s.dw, dh: s.dh, scale: 1, anchor: [s.dw / 2, s.dh],
    }
  }
  return { ...PACK, frames: f as IsoPack['frames'] }
}

// ---------------------------------------------------------------------------

describe('the decoder itself, before anything is measured with it', () => {
  // A decoder that silently returned zeros would make every sweep below pass
  // vacuously — the exact class of defect this round is repairing elsewhere.
  it('decodes the shipped atlas to its declared size, and it is not blank', () => {
    expect(ATLAS.w).toBe(RAW.atlas_size)
    expect(ATLAS.h).toBe(RAW.atlas_size)
    expect(ATLAS.data.length).toBe(RAW.atlas_size * RAW.atlas_size * 4)
    const nonZero = ATLAS.data.some((v) => v !== 0)
    expect(nonZero, 'the whole atlas decoded to zeroes').toBe(true)
  })

  it('the hash separates two frames that differ, and repeats on the same frame', () => {
    expect(fnv1aBytes(frameBytes('great_house'))).toBe(fnv1aBytes(frameBytes('great_house')))
    expect(fnv1aBytes(frameBytes('great_house'))).not.toBe(fnv1aBytes(frameBytes('library')))
    // and it is sensitive to ONE byte, which is what makes a stale judgement
    // detectable at all
    const a = frameBytes('int_desk')
    const b = Uint8Array.from(a)
    b[0] = b[0] ^ 0xff
    expect(fnv1aBytes(a)).not.toBe(fnv1aBytes(b))
  })
})

describe('EVERY frame the atlas ships — the sweep that did not exist', () => {
  it('sweeps all of them, including every frame added on 2026-07-28', () => {
    // The count is the point: a sweep that quietly covered 12 of 182 would look
    // exactly like this one in the log.
    expect(ALL.length).toBe(RAW.counts.frames)
    expect(ALL.length).toBeGreaterThanOrEqual(182)
    const nu = ALL.filter((k) => k.endsWith(OPEN_SUFFIX) || k.startsWith('int_'))
    expect(nu.length, 'the roof-off + interior art is not in the swept set').toBe(18)
  })

  it('no frame is blank, and none is a rect packed over empty atlas', () => {
    const thin: string[] = []
    for (const k of ALL) {
      const f = PACK.frames[k]
      const s = shapeOf(k)
      if (s.opaque < f.w * f.h * 0.02) thin.push(`${k} ${s.opaque}/${f.w * f.h}`)
    }
    expect(thin, 'frames with almost nothing drawn in them').toEqual([])
  })

  it('every PLACEABLE frame is drawn around its OWN anchor — centred, on its base', () => {
    // `anchor` is (dw/2, dh): the base centre. If the art drifts off that point
    // the sprite is placed by a coordinate it is not actually standing on, and
    // every rule downstream — clearance, the pick solid, the cutaway's base
    // centre — is about the wrong spot.
    //
    // ONE frame in the shipped atlas fails it, and the sweep found it: int_stove
    // sits 8px right of its own anchor in a 36px frame. It is already refused
    // for other reasons, which is what this arm asserts — a drifted frame must
    // be art the world will not place. A PLACEABLE frame that drifts is red.
    const drifted: string[] = []
    const floating: string[] = []
    for (const k of ALL) {
      const f = PACK.frames[k]
      const s = shapeOf(k)
      const cx = (s.minX + s.maxX) / 2
      if (Math.abs(cx - f.w / 2) > f.w * 0.1) drifted.push(k)
      // INK, not solid mass. A building's contact shadow is 30-60px of
      // semi-transparent pixels below its walls and it is still the sprite; the
      // first cut of this arm read alpha>=200 and reported four correct frames
      // as floating, `workshop_open` by 57px. What matters for a cross-fade at
      // a fixed base centre is where the art ENDS, shadow included.
      if (f.h - 1 - s.maxYInk > 16) floating.push(`${k} ${f.h - 1 - s.maxYInk}px above its base`)
    }
    const placeableDrift = drifted.filter(
      (k) => !INTERIOR_KIT_REJECTED.has(k) && !OPEN_TWIN_REJECTED.has(k)
    )
    expect(placeableDrift, 'placed art whose mass is not over its own base centre').toEqual([])
    expect(drifted, 'the drifted set moved — re-measure before updating this').toEqual(['int_stove'])
    expect(floating, 'art that hangs above the point it is anchored at').toEqual([])
  })

  it('every frame the pack declares is INSIDE the atlas it declares', () => {
    const out: string[] = []
    for (const k of ALL) {
      const f = PACK.frames[k]
      if (f.x < 0 || f.y < 0 || f.x + f.w > ATLAS.w || f.y + f.h > ATLAS.h) out.push(k)
    }
    expect(out, 'frame rects that run off the atlas').toEqual([])
  })
})

describe('roof-off twins — judged, and the judgement bound to the pixels', () => {
  const twins = ALL.filter((k) => k.endsWith(OPEN_SUFFIX))

  it('the atlas ships the twins this round looked at', () => {
    expect(twins.length).toBe(10)
  })

  it('every REJECTED twin is a frame that exists, and its pixels are the ones judged', () => {
    for (const [frame, verdict] of OPEN_TWIN_REJECTED) {
      expect(PACK.frames[frame], `${frame} is rejected but the atlas has no such frame`).toBeDefined()
      expect(
        fnv1aBytes(frameBytes(frame)),
        `${frame} HAS BEEN REGENERATED. The refusal on record was passed on different pixels ` +
          `and does not carry over — look at the new art and judge it again. Reason on file: ` +
          verdict.reason
      ).toBe(verdict.pixelHash)
    }
  })

  it('the library does NOT open, and the world says why', () => {
    // The eye judgement, pinned: a half-timbered cottage may not cross-fade
    // into a sandstone arcade at a fixed base centre.
    expect(openFrameOf(PACK, 'library')).toBeNull()
    expect(openTwinRefusal(PACK, 'library')).toMatch(/scene swap/)
    // …and it is refused for THAT reason, not by accident of geometry: the
    // mechanical rule below admits it, so removing the judged entry would let
    // the scene swap ship. Asserted as "would be admitted" rather than
    // "footprint identical" — until 2026-07-28 the twin was byte-for-byte the
    // closed frame's size because the old base treatment returned it uncropped,
    // and pinning that equality was pinning an artefact of that bug.
    const gc = groundDiamond(PACK.frames.library.dw, PACK.frames.library.dh)
    const go = groundDiamond(PACK.frames.library_open.dw, PACK.frames.library_open.dh)
    expect(go.hw).toBeLessThanOrEqual(gc.hw + 1)
    expect(go.depth).toBeLessThanOrEqual(gc.depth + 1)
  })

  it('the footprint rule is measured against the SHIPPED atlas, both ways', () => {
    // Derived, not chosen: the layout composed every clearance from the CLOSED
    // frame's ground diamond, so a wider twin overhangs ground already promised
    // to a neighbour. One-sided on purpose — a narrower twin is what a roof
    // coming off looks like.
    const wider: string[] = []
    const narrower: string[] = []
    for (const t of twins) {
      const base = t.slice(0, -OPEN_SUFFIX.length)
      const cf = PACK.frames[base]
      if (!cf) continue
      const gc = groundDiamond(cf.dw, cf.dh)
      const go = groundDiamond(PACK.frames[t].dw, PACK.frames[t].dh)
      const refused = openTwinRefusal(PACK, base)
      if (go.hw > gc.hw + 1 || go.depth > gc.depth + 1) {
        wider.push(base)
        expect(refused, `${base} grows on the ground and was admitted anyway`).not.toBeNull()
        expect(openFrameOf(PACK, base), `${base} grows and still opens`).toBeNull()
      } else {
        narrower.push(base)
      }
    }
    // The measurement itself, so a regenerated atlas that flips a building from
    // one side to the other cannot do it silently. It flipped two on
    // 2026-07-28 and this arm is how that was noticed: `camp_log_cabin_open`
    // and `cottage_b_open` were oversized by a baked exterior lawn, not by
    // their walls, and the lawn peel put them back inside the closed footprint.
    expect(wider.sort()).toEqual(['officer_house_b'])
    expect(narrower.length).toBe(9)
  })

  it('the DEPTH half of the footprint rule fires on its own', () => {
    // A MUTATION SURVIVED THIS FILE AND THIS ARM IS THE ANSWER. Deleting the
    // depth branch entirely left every arm above green, because on the shipped
    // atlas every twin that is too deep is ALSO too wide — the width branch
    // decides all three, and a rule that never decides anything is a rule
    // nobody is testing.
    //
    // The fixture has to be built with `groundDiamond`'s own arithmetic in mind:
    // depth is `min(dh, dw) * 0.55`, so at equal `dw` the depth can never
    // exceed — the first version of this arm asserted 55 > 55 and said so. The
    // case that reaches the branch is a LOW WIDE building (dh < dw, so depth is
    // set by dh) whose twin is taller: same footprint width, and it grows
    // toward the viewer.
    const p = packOf({ hall: { dw: 100, dh: 50 }, hall_open: { dw: 100, dh: 200 } })
    expect(groundDiamond(100, 200).hw).toBe(groundDiamond(100, 50).hw)
    expect(groundDiamond(100, 200).depth).toBeGreaterThan(groundDiamond(100, 50).depth + 1)
    expect(openTwinRefusal(p, 'hall')).toMatch(/deeper on the ground/)
    expect(openFrameOf(p, 'hall')).toBeNull()
    // and the same shapes the other way round open, so the arm is not just
    // asserting that this function refuses things
    const q = packOf({ hall: { dw: 100, dh: 200 }, hall_open: { dw: 100, dh: 50 } })
    expect(openTwinRefusal(q, 'hall')).toBeNull()
    expect(openFrameOf(q, 'hall')?.frame).toBe('hall_open')
  })

  it('a twin that is neither judged nor oversized DOES open', () => {
    // The inverted arm. Without it every assertion above is satisfied by a
    // function that refuses everything, which is the failure mode of a gate.
    const open = openFrameOf(PACK, 'great_house')
    expect(open).not.toBeNull()
    expect(open?.frame).toBe('great_house_open')
    expect(openTwinRefusal(PACK, 'great_house')).toBeNull()
    expect(openFrameOf(PACK, 'workshop')?.frame).toBe('workshop_open')
  })

  it('the refusal reaches the CANDIDATE, not only the draw', () => {
    // A refusal enforced at one of three call sites leaves the building chosen,
    // its roof faded to nothing, and no interior under it. One of each kind, so
    // the arm covers both branches of openTwinRefusal: `library` is the JUDGED
    // refusal, `officer_house_b` the geometric one. It used to name
    // `camp_log_cabin`, which stopped being refused on 2026-07-28 when the lawn
    // peel took the baked deck off its frame and it fell back inside its closed
    // footprint — the refusal was about a lawn, not about the building.
    expect(openFrameOf(PACK, 'library')).toBeNull()
    expect(openFrameOf(PACK, 'officer_house_b')).toBeNull()
  })
})

describe('the interior kit — no fixture enters unjudged', () => {
  const ints = ALL.filter((k) => k.startsWith('int_'))

  it('every int_ frame in the atlas is admitted or rejected, and never both', () => {
    const unjudged = ints.filter((k) => !INTERIOR_KIT.has(k) && !INTERIOR_KIT_REJECTED.has(k))
    expect(unjudged, 'interior art nobody has looked at').toEqual([])
    const both = ints.filter((k) => INTERIOR_KIT.has(k) && INTERIOR_KIT_REJECTED.has(k))
    expect(both).toEqual([])
    // and neither table names a frame the atlas does not have
    for (const k of INTERIOR_KIT.keys()) expect(PACK.frames[k], `${k} admitted, not in atlas`).toBeDefined()
    for (const k of INTERIOR_KIT_REJECTED.keys()) expect(PACK.frames[k], `${k} rejected, not in atlas`).toBeDefined()
  })

  it('every rejection is still about the pixels it was passed on', () => {
    for (const [frame, verdict] of INTERIOR_KIT_REJECTED) {
      expect(
        fnv1aBytes(frameBytes(frame)),
        `${frame} HAS BEEN REGENERATED — re-judge it. Reason on file: ${verdict.reason}`
      ).toBe(verdict.pixelHash)
    }
  })

  it('the renderer can reach an admitted fixture and cannot reach a rejected one', () => {
    expect(kitFrame(PACK, 'int_desk')).toEqual({
      dw: PACK.frames.int_desk.dw,
      dh: PACK.frames.int_desk.dh,
    })
    for (const k of INTERIOR_KIT_REJECTED.keys()) {
      expect(kitFrame(PACK, k), `${k} is rejected and still placeable`).toBeNull()
    }
    expect(kitFrame(PACK, 'int_nonesuch')).toBeNull()
  })

  it('int_stove really does stand on outdoor ground, which is the measurable half', () => {
    // BE HONEST ABOUT WHAT A MACHINE CAN SEE HERE. The stove's worst faults —
    // a lit fire, a cooking pot, rising smoke — are an eye judgement, and the
    // pixel hash above is what holds them. What IS measurable is the ground it
    // stands on: it is the only fixture in the kit, the rug aside, with any
    // green under it at all, and a fixture meant for a plank floor carrying
    // moss and grass is a lie about where it is.
    const greenIn = (name: string): { green: number; seen: number } => {
      const f = PACK.frames[name]
      const px = frameBytes(name)
      let green = 0
      let seen = 0
      for (let y = Math.floor(f.h * 0.7); y < f.h; y++) {
        for (let x = 0; x < f.w; x++) {
          const i = (y * f.w + x) * 4
          if (px[i + 3] < 200) continue
          seen++
          if (px[i + 1] > px[i] + 12 && px[i + 1] > px[i + 2] + 12) green++
        }
      }
      return { green, seen }
    }
    const stove = greenIn('int_stove')
    expect(stove.seen).toBeGreaterThan(100)
    expect(stove.green, 'the outdoor plate under int_stove has gone').toBeGreaterThan(10)
    // …and the fixtures the world DOES place carry not one such pixel, so this
    // is a discriminator and not a property of every sprite in the pack. (The
    // rug is excluded by construction: a green rug is a rug.)
    for (const k of ['int_desk', 'int_work_board', 'int_bookshelf', 'int_bunk']) {
      expect(greenIn(k).green, `${k} stands on grass too`).toBe(0)
    }
  })
})

describe('the renderer cannot reach around the kit — a grep, because a canvas has no test', () => {
  /**
   * THE SECOND MUTATION THAT SURVIVED. Putting `pack.frames.int_desk` back in
   * `engine-canvas.tsx` left every arm in this file green, and it always will:
   * `drawIsoCutaway` lives inside a PixiJS `useEffect` closure and nothing in
   * the tree can drive it. A rule whose only enforcement is a function nobody is
   * obliged to call is a convention, not a gate.
   *
   * So this is mechanical and it reads the shipped source: no file under the
   * world trees may name an `int_*` frame as a property of `pack.frames` or as a
   * string literal outside iso-cutaway.ts, which is where the kit lives.
   */
  const WORLD_TREES = [
    join(process.cwd(), 'src', 'lib', 'world'),
    join(process.cwd(), 'src', 'components', 'world'),
  ]
  function collect(dir: string): string[] {
    if (!existsSync(dir)) return []
    const out: string[] = []
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, e.name)
      if (e.isDirectory()) out.push(...collect(p))
      else if (/\.(ts|tsx)$/.test(e.name) && !e.name.endsWith('.test.ts')) out.push(p)
    }
    return out
  }
  const sources = WORLD_TREES.flatMap(collect)

  it('there are world sources to grep at all', () => {
    expect(sources.length).toBeGreaterThan(10)
    expect(sources.some((p) => p.endsWith('engine-canvas.tsx'))).toBe(true)
  })

  it('only iso-cutaway.ts names an interior fixture; everything else goes through kitFrame', () => {
    const offenders: string[] = []
    for (const p of sources) {
      if (p.endsWith('iso-cutaway.ts')) continue
      const src = readFileSync(p, 'utf8')
      // `pack.frames.int_desk`, `pack.frames['int_desk']`, `frames.int_stove`…
      if (/\bframes\s*(\.\s*int_|\[\s*['"]int_)/.test(src)) {
        offenders.push(`${p.split('/').pop()}: indexes pack.frames by an int_ name`)
      }
    }
    expect(offenders, 'the interior kit is being reached around').toEqual([])
    // and the canvas DOES go through the kit, so this is not vacuous on a file
    // that simply stopped drawing interiors
    const canvas = readFileSync(
      sources.find((p) => p.endsWith('engine-canvas.tsx'))!,
      'utf8'
    )
    expect(canvas).toMatch(/kitFrame\(pack, 'int_desk'\)/)
  })
})

describe('what this round did NOT fix, declared so it cannot be forgotten', () => {
  it('two roof-off twins are art no composed island draws — latent, not shipped', () => {
    // ASKED OF THE COMPOSED SCENES, not of the resolve table. The first cut of
    // this arm walked `resolve` and concluded that `officer_house_b` and
    // `officer_house_c` were unreachable — and the suite immediately proved it
    // wrong, because `resolveFrame` REFINES per lot by `kind`, so a hamlet
    // island draws both. A claim about what the world draws has to be made
    // against a drawn world.
    //
    // What survives that test: `cottage_c_open` (stone-block walls under a
    // straw-roofed timber cottage) and `camp_log_cabin_open` (+4.2px wider on
    // the ground) belong to closed frames that neither shipped island fixture
    // draws, so their defects are latent. If either starts being drawn this
    // goes red and the art gets judged before it is seen.
    const drawn = new Set<string>()
    for (const which of ['hamlet', 'camp']) {
      const st = JSON.parse(
        readFileSync(join(process.cwd(), '..', 'scripts', 'world-capture', 'states', `${which}.json`), 'utf8')
      ) as { seed: string; state: LayoutState }
      for (const s of buildIsoScene(PACK, st.state, st.seed).sprites) drawn.add(s.frame)
    }
    expect(drawn.size, 'neither island composed anything').toBeGreaterThan(50)
    for (const u of ['cottage_c', 'camp_log_cabin']) {
      expect(PACK.frames[`${u}${OPEN_SUFFIX}`], `${u}_open left the atlas`).toBeDefined()
      expect(drawn.has(u), `${u} is now DRAWN — judge its roof-off twin before it ships`).toBe(false)
    }
    // and the ones that ARE drawn have all been through the gate above
    for (const f of ['library', 'cottage_b', 'officer_house_b', 'officer_house_c']) {
      expect(drawn.has(f), `${f} stopped being drawn — this arm is now about nothing`).toBe(true)
    }
  })

  it('great_house_open ships a built-in stove — declared art debt', () => {
    // The one open twin kept despite a doctrine smell, RE-JUDGED 2026-07-28 on
    // new pixels. The debt changed shape rather than clearing: the old frame's
    // back walls carried glazed casework with objects drawn inside them, and
    // that is gone — the walls are now plain arched windows and a plank door.
    // What replaced it is a small stone stove standing in the corner, which is
    // still a fixture drawn into art the compositor is supposed to fill (the
    // kit ships `int_stove` for exactly this). It is strictly the lesser debt,
    // because a stove bakes in no MEASURED QUANTITY the way a shelf drawn full
    // or a board drawn with pins does, and it is clear of all five desk slots.
    // Kept because this is the ONLY interior officers are ever drawn in; still
    // pinned, so a regeneration is noticed and the debt is never confused with
    // a clean bill.
    expect(fnv1aBytes(frameBytes('great_house_open'))).toBe('cc15ead9')
    expect(openFrameOf(PACK, 'great_house')).not.toBeNull()
  })
})
