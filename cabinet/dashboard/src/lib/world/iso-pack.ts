/**
 * ISO-PACK — the shipped isometric sprite pack, parsed and resolved.
 *
 * The pack (public/world-assets/originals/iso/world-pack.json + atlas-0.png) is
 * GENERATED from designs/world-mockup-v2/vocab.py by export_pack.py, and it is
 * the SAME artifact the offline compositor draws the approved stills from. That
 * is the whole reason the engine reads it rather than carrying its own table: a
 * second (object, era, rung) -> sprite map is a second place for the world to
 * disagree with the picture the Captain approved.
 *
 * WHAT THIS MODULE IS RESPONSIBLE FOR
 *   - parsing the pack STRICTLY, so a truncated or wrong-schema file is a loud
 *     error at boot rather than a world that quietly draws nothing (the
 *     2026-07-08 silent-black contract);
 *   - answering frameFor(object, era, rung) exactly as the pack's own resolve
 *     table does, including its '*' fallback;
 *   - answering isEmptyRung() from THE PACK'S list, so honest zero has one
 *     table in the render path instead of three;
 *   - handing the layout the pack's own DRAWN sizes, because the layout's
 *     spacing rules are only as true as the footprints they measure.
 *
 * PURE: no fetch, no DOM, no clock. The component fetches the bytes and hands
 * them here; that keeps the world-tree determinism ratchet satisfied and makes
 * every rule below testable without a browser.
 */

/** One atlas frame, as the pack states it. */
export interface PackFrame {
  /** Atlas sub-rectangle, in NATIVE (unscaled) atlas pixels. */
  x: number
  y: number
  w: number
  h: number
  /**
   * The size the sprite is DRAWN at. NEVER recompute this from `scale`: 28 of
   * the 163 frames have dw !== w/scale because the generator floors an odd
   * pixel (bay_archive_bureau is w=111 scale=2 dw=55), and a sprite drawn at
   * 55.5 leaves the pixel grid the whole pack exists to keep.
   */
  dw: number
  dh: number
  /** Integer fraction of native the frame is drawn at. Informational. */
  scale: number
  /** Which atlas image the frame lives in. */
  atlas: number
  /** Base centre in DRAWN pixels — always (dw/2, dh); pinned by the tests. */
  anchor: readonly [number, number]
}

/** A resolve-table hit: which frame, and whether it is real art. */
export interface PackHit {
  frame: string
  /**
   * False = a placeholder standing in for art that was never generated. The
   * pack ships zero of these today; the field is carried rather than dropped
   * so the count can be REPORTED instead of assumed (an assumed zero is how a
   * placeholder ends up in front of the Captain as if it were the world).
   */
  trueArt: boolean
}

export interface IsoPack {
  schema: string
  /** The pack's own declaration of its geometry, e.g. 'isometric 2:1'. */
  projection: string
  /** The verbatim ground-footprint contract; projection.ts is pinned to it. */
  note: string
  atlasSize: number
  atlases: readonly string[]
  frames: Readonly<Record<string, PackFrame>>
  /** THE honest-zero table — rung names that mean "nothing is built here". */
  emptyRungs: ReadonlySet<string>
  /** object -> era -> rung ('*' = any) -> hit. */
  resolve: Readonly<Record<string, Readonly<Record<string, Readonly<Record<string, PackHit>>>>>>
}

const SCHEMA = 'cabinet.world.iso-pack/v1'

function fail(what: string): never {
  throw new Error(`iso-pack: ${what}`)
}

function num(v: unknown, where: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v)) fail(`${where} is not a finite number`)
  return v as number
}

/**
 * Parse the shipped pack, or THROW.
 *
 * Strict on purpose. Every tolerated defect here becomes a sprite drawn at the
 * wrong size or in the wrong place, and the failure mode of a lenient parser is
 * a world that looks nearly right — which is worse than one that refuses to
 * boot and says why.
 */
export function parsePack(raw: unknown): IsoPack {
  if (typeof raw !== 'object' || raw === null) fail('pack is not an object')
  const p = raw as Record<string, unknown>
  if (p.schema !== SCHEMA) fail(`unexpected schema ${String(p.schema)} (want ${SCHEMA})`)
  const atlasSize = num(p.atlas_size, 'atlas_size')
  const atlases = p.atlases
  if (!Array.isArray(atlases) || atlases.length === 0) fail('atlases is empty')
  for (const a of atlases) if (typeof a !== 'string') fail('atlases holds a non-string')
  if (typeof p.note !== 'string' || p.note.length === 0) fail('note is missing')
  if (typeof p.projection !== 'string') fail('projection is missing')

  const framesRaw = p.frames
  if (typeof framesRaw !== 'object' || framesRaw === null) fail('frames is not an object')
  const frames: Record<string, PackFrame> = {}
  for (const [name, v] of Object.entries(framesRaw as Record<string, unknown>)) {
    if (typeof v !== 'object' || v === null) fail(`frame ${name} is not an object`)
    const f = v as Record<string, unknown>
    const anchor = f.anchor
    if (!Array.isArray(anchor) || anchor.length !== 2) fail(`frame ${name} has no anchor pair`)
    const fr: PackFrame = {
      x: num(f.x, `frame ${name}.x`),
      y: num(f.y, `frame ${name}.y`),
      w: num(f.w, `frame ${name}.w`),
      h: num(f.h, `frame ${name}.h`),
      dw: num(f.dw, `frame ${name}.dw`),
      dh: num(f.dh, `frame ${name}.dh`),
      scale: num(f.scale, `frame ${name}.scale`),
      atlas: num(f.atlas, `frame ${name}.atlas`),
      anchor: [num(anchor[0], `frame ${name}.anchor[0]`), num(anchor[1], `frame ${name}.anchor[1]`)],
    }
    if (fr.w <= 0 || fr.h <= 0 || fr.dw <= 0 || fr.dh <= 0) fail(`frame ${name} has a non-positive size`)
    if (fr.x < 0 || fr.y < 0 || fr.x + fr.w > atlasSize || fr.y + fr.h > atlasSize) {
      fail(`frame ${name} falls outside the ${atlasSize}px atlas`)
    }
    if (fr.atlas < 0 || fr.atlas >= atlases.length) fail(`frame ${name} cites atlas ${fr.atlas}`)
    frames[name] = fr
  }
  if (Object.keys(frames).length === 0) fail('pack ships no frames')

  const emptyRaw = p.empty_rungs
  if (!Array.isArray(emptyRaw)) fail('empty_rungs is not an array')
  const emptyRungs = new Set<string>()
  for (const r of emptyRaw) {
    if (typeof r !== 'string') fail('empty_rungs holds a non-string')
    emptyRungs.add(r)
  }

  const resolveRaw = p.resolve
  if (typeof resolveRaw !== 'object' || resolveRaw === null) fail('resolve is not an object')
  const resolve: Record<string, Record<string, Record<string, PackHit>>> = {}
  for (const [obj, byEraRaw] of Object.entries(resolveRaw as Record<string, unknown>)) {
    if (typeof byEraRaw !== 'object' || byEraRaw === null) fail(`resolve.${obj} is not an object`)
    const byEra: Record<string, Record<string, PackHit>> = {}
    for (const [era, byRungRaw] of Object.entries(byEraRaw as Record<string, unknown>)) {
      if (typeof byRungRaw !== 'object' || byRungRaw === null) {
        fail(`resolve.${obj}.${era} is not an object`)
      }
      const byRung: Record<string, PackHit> = {}
      for (const [rung, hitRaw] of Object.entries(byRungRaw as Record<string, unknown>)) {
        if (typeof hitRaw !== 'object' || hitRaw === null) {
          fail(`resolve.${obj}.${era}.${rung} is not an object`)
        }
        const hit = hitRaw as Record<string, unknown>
        if (typeof hit.frame !== 'string') fail(`resolve.${obj}.${era}.${rung} has no frame`)
        // A resolve row naming a frame the atlas does not carry draws NOTHING
        // and reports nothing — the exact silent hole this parser exists to
        // refuse. The pack ships zero of these; the check is what keeps it so.
        if (!(hit.frame in frames)) {
          fail(`resolve.${obj}.${era}.${rung} names absent frame ${hit.frame}`)
        }
        byRung[rung] = { frame: hit.frame, trueArt: hit.true_art !== false }
      }
      byEra[era] = byRung
    }
    resolve[obj] = byEra
  }

  return {
    schema: SCHEMA,
    projection: p.projection as string,
    note: p.note as string,
    atlasSize,
    atlases: atlases as string[],
    frames,
    emptyRungs,
    resolve,
  }
}

/**
 * Does this rung name mean "nothing is built here"?
 *
 * THE pack's table, and the only honest-zero predicate the iso render path may
 * ask. An ABSENT rung answers true as well: an object whose ladder the state
 * never mentions has not been measured, and drawing the first rung of an
 * unmeasured ladder invents a measurement.
 */
export function isEmptyRung(pack: IsoPack, rung: string | null | undefined): boolean {
  if (rung === null || rung === undefined || rung === '') return true
  return pack.emptyRungs.has(rung)
}

/**
 * The pack's own answer to "what art does this object wear at this era and
 * rung?" — resolve[object][era][rung] falling back to the era's '*' row.
 *
 * Returns null when the pack has no opinion, which is a real answer for the
 * five ladders it deliberately does not cover (quay, road, lane_isles,
 * lighthouse_lamp, posts_lit — all drawn procedurally). A null must never be
 * silently swallowed by the caller; see iso-scene.ts, which reports it.
 */
export function frameFor(
  pack: IsoPack,
  object: string,
  era: string,
  rung: string | null | undefined
): PackHit | null {
  const byEra = pack.resolve[object]
  if (!byEra) return null
  const byRung = byEra[era]
  if (!byRung) return null
  if (rung !== null && rung !== undefined && rung in byRung) return byRung[rung]
  return byRung['*'] ?? null
}

/**
 * The ERA a frame's art belongs to, read off the generator's own naming.
 *
 * export_pack.py prefixes era-specific art (`camp_`, `town_`, `bay_`) and
 * leaves the hamlet vocabulary bare. That prefix is what lets a caller ask
 * whether a sprite the LAYOUT chose is legal at the era the STATE is in —
 * which is how the per-lot dwelling variety survives without letting a
 * hamlet cottage stand in a town (see iso-scene.resolveKind).
 *
 * It is a naming convention, so it is pinned by a test against the shipped
 * pack rather than trusted: every frame named by a `camp`/`town`/`beyond_bay`
 * resolve row must carry the matching prefix.
 */
export function eraOfFrame(frame: string): 'camp' | 'hamlet' | 'town' | 'beyond_bay' {
  if (frame.startsWith('camp_')) return 'camp'
  if (frame.startsWith('town_')) return 'town'
  if (frame.startsWith('bay_')) return 'beyond_bay'
  return 'hamlet'
}

/** The drawn size of a frame, or null when the pack has no such frame. */
export function drawSize(pack: IsoPack, frame: string): { w: number; h: number } | null {
  const f = pack.frames[frame]
  return f ? { w: f.dw, h: f.dh } : null
}

/**
 * A `footprintOf` for composeLayout, backed by the SHIPPED pack.
 *
 * The layout's DEFAULT_FOOTPRINTS are a fallback measured off the generator's
 * manifest; the pack is what actually draws. Handing the layout the pack's
 * sizes is what keeps every spacing rule it enforces — belt separation, ground
 * overlap, lane clearance — measured against the sprite that appears.
 */
export function packFootprints(pack: IsoPack): (kind: string) => { w: number; h: number } | undefined {
  return (kind) => {
    const f = pack.frames[kind]
    return f ? { w: f.dw, h: f.dh } : undefined
  }
}
