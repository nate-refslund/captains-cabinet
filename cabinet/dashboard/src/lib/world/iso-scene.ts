/**
 * ISO-SCENE — the bridge from the engine's resolved world state to a drawable
 * isometric scene.
 *
 * THIS IS THE DELIVERY PATH THE LAYOUT PORT WAS MISSING. composeLayout has been
 * measured by three adversarial rounds and had no caller: nothing turned a
 * `Layout` into pixels, so every measurement it passed was a measurement of
 * something nobody could see. This module is the one place where the layout,
 * the shipped sprite pack and the engine's era/rung resolution meet, and it is
 * pure so that meeting is testable without a browser.
 *
 * THE ONE RULE THAT MATTERS HERE: the pack's (object, era, rung) table decides
 * what art a state wears. The layout's `kind` may REFINE within the era the
 * table resolved to — that is how one house per lot survives — and may never
 * cross an era. Concretely, without this rule the world draws a full lighthouse
 * tower on a camp island whose lighthouse rung is `dark_cairn`, and dresses a
 * town in hamlet cottages, because the layout emits a role-shaped `kind` and
 * `dwellingKind` only gates at camp. Both are era lies of exactly the kind
 * check_era exists to catch.
 *
 * SPACE. composeLayout works in the compositor's own screen pixels (2400x1760,
 * island centre 1200,760): the isometric projection is BAKED INTO those
 * coordinates, which is why nothing here re-projects a structure. The camera
 * still speaks tiles, so the two helpers at the bottom convert once, through
 * the projection kernel, and nowhere else.
 *
 * PURE: no fetch, no DOM, no clock, no unseeded randomness.
 */
import {
  composeLayout,
  CAMP_DWELLING,
  HOUSE_KINDS,
  LANE_SQUASH,
  LAYOUT_SPACE,
  type Era,
  type Layout,
  type LayoutSpace,
  type LayoutState,
  type RoadRung,
} from './iso-layout'
import { eraOfFrame, frameFor, isEmptyRung, type IsoPack, type PackFrame } from './iso-pack'
import { projectionFor, type ProjectionKind } from './projection'
import type { WorldResolution } from './era-engine'

const ERAS: readonly Era[] = ['camp', 'hamlet', 'town', 'beyond_bay']
const ROAD_RUNGS: readonly RoadRung[] = ['dirt_path', 'dirt_worn', 'gravel_road', 'cobbled_road']

/**
 * A layout `role` that is spelled differently in the pack's resolve table.
 *
 * ONE entry today, and it is here rather than papered over with a fuzzy match
 * because a fuzzy match would silently pair the wrong object the first time two
 * names nearly agreed. `iso-scene.test.ts` asserts every role a composed layout
 * emits either lands in the resolve table or is on the documented no-state list.
 */
const ROLE_ALIAS: Readonly<Record<string, string>> = {
  officer_dwelling: 'officer_dwellings',
}

/**
 * Layout kinds the LAYOUT varies per lot, and the object whose rung governs
 * them. Derived from iso-layout's own exports, never re-typed: `dwellingKind`
 * picks one of HOUSE_KINDS (or CAMP_DWELLING) per lot, and every one of them
 * must be sized and drawn as the dwelling ladder says.
 */
const DWELLING_KINDS: ReadonlySet<string> = new Set<string>([...HOUSE_KINDS, CAMP_DWELLING])

/**
 * Roles a composed layout emits that the pack deliberately has NO state entry
 * for — decoration and harbour kit whose existence is decided by the layout,
 * not by a ladder. Listed rather than defaulted so a role that QUIETLY stops
 * resolving shows up as an issue instead of joining this set by accident.
 */
export const NO_STATE_KINDS: ReadonlySet<string> = new Set([
  'market_stall',
  'cargo_barrels',
  'crate_single',
  'rope_coil',
  'crab_pots',
  'fish_barrel',
  'fishing_net',
  'fish_drying_rack',
  'anchor',
  'barrel_single',
  'mooring_post',
  'harbor_crane',
])

/**
 * The vertical squash of a lane's PAINTED band — iso-layout's own constant.
 *
 * A circle on the ground projects flattened on a 2:1 screen, so the occupancy
 * field tests each lane sample as an ellipse with y-radius `half * SQUASH`, not
 * a disc. The thing that PAINTS the road has to paint that same shape: a plain
 * round stroke is 1/0.72 = 39% taller in y than the corridor the clearance
 * rules reserved, so every structure those rules cleared against the ellipse
 * can end up standing on painted road — a defect that only appears once
 * something finally renders the layout.
 *
 * RE-EXPORTED, never re-typed, and pinned BEHAVIOURALLY on top of that:
 * iso-scene.test.ts measures the field's real x and y reaches through
 * buildLaneField and requires this number to reproduce them. An import alone
 * would survive the constant changing meaning; a measurement would not.
 */
export const LANE_PAINT_SQUASH = LANE_SQUASH

/** One sprite the renderer draws, at its base centre in layout px. */
export interface IsoSprite {
  /** Stable within a scene — pooling and debug overlays key off it. */
  id: string
  frame: string
  /** Base centre (the ground diamond's front vertex), in layout px. */
  x: number
  y: number
  /** DRAWN size, from the pack. */
  dw: number
  dh: number
  flip: boolean
  /** Paint order key — the projected base y, exactly what compose.py sorts on. */
  depth: number
  /**
   * The state object that justifies this sprite, or null when nothing measured
   * it (nature, harbour kit). This is check_state_traceable's question, carried
   * to the renderer rather than reconstructed from a sprite name.
   */
  role: string | null
  trueArt: boolean
}

export interface IsoScene {
  layout: Layout
  space: LayoutSpace
  /** Depth-sorted, back to front. */
  sprites: IsoSprite[]
  /** Where the lighthouse glow goes, or null when the lamp is not lit. */
  lamp: { x: number; y: number } | null
  /**
   * Everything the scene could not resolve, in the loud-failure format the
   * canvas already badges. A silently dropped sprite is the failure this
   * whole module exists to make impossible.
   */
  issues: string[]
}

function asEra(v: string | null | undefined): Era {
  return (ERAS as readonly string[]).includes(v ?? '') ? (v as Era) : 'camp'
}

function asRoadRung(v: string | null | undefined): RoadRung {
  return (ROAD_RUNGS as readonly string[]).includes(v ?? '') ? (v as RoadRung) : 'dirt_path'
}

/**
 * The engine's resolved world as the layout's own state shape.
 *
 * COUNTS ARE THE VISIBLE RUNG INDEX, which is what compose.py's WS.count()
 * returns and what the ladders encode: `officer_dwellings` runs
 * none/dwelling_1/dwellings_2/... so its rung index IS the number of houses.
 * It is NOT a raw metric — reading the metric would draw eleven cottages for
 * eleven role definitions. Any ladder whose rungs are not a counting sequence
 * therefore yields a TIER index here, and the layout treats it as "how much",
 * which is the same reading the reference takes.
 */
export function layoutStateFrom(resolution: WorldResolution | null): LayoutState {
  const stages: Record<string, string> = {}
  const counts: Record<string, number> = {}
  for (const [name, el] of Object.entries(resolution?.elements ?? {})) {
    stages[name] = el.rungName
    counts[name] = Math.max(0, Math.trunc(el.rung))
  }
  return {
    era: asEra(resolution?.era),
    road: asRoadRung(resolution?.elements?.road?.rungName),
    stages,
    counts,
  }
}

export interface ResolvedFrame {
  frame: string
  trueArt: boolean
  /** True when the layout's own kind refined the table's answer. */
  refined: boolean
}

/**
 * Which frame a thing wears — THE resolution, used by the renderer AND by the
 * footprint the layout is composed with, so the sprite that is spaced for is
 * the sprite that is drawn.
 *
 * Order, and why:
 *   1. the pack's table for (object, era, rung). The state decides.
 *   2. the layout's `kind`, but ONLY when it is real art in the SAME era family
 *      the table just resolved to. This is the per-lot dwelling variety, and
 *      the era guard is what stops a hamlet cottage standing in a town.
 *   3. no table entry at all -> the kind itself, if the pack draws it. That is
 *      the honest answer for nature and harbour kit: nothing measured them.
 *   4. otherwise null, which the caller MUST report.
 */
export function resolveFrame(
  pack: IsoPack,
  object: string | null,
  kind: string,
  era: Era,
  rung: string | null | undefined
): ResolvedFrame | null {
  const packObject = object === null ? null : (ROLE_ALIAS[object] ?? object)
  if (packObject !== null) {
    const hit = frameFor(pack, packObject, era, rung)
    if (hit) {
      if (kind !== packObject && kind !== object && pack.frames[kind]) {
        if (eraOfFrame(kind) === eraOfFrame(hit.frame)) {
          return { frame: kind, trueArt: hit.trueArt, refined: true }
        }
      }
      return { frame: hit.frame, trueArt: hit.trueArt, refined: false }
    }
  }
  if (pack.frames[kind]) return { frame: kind, trueArt: true, refined: false }
  return null
}

/** The object whose rung governs a layout `kind`, when one does. */
function objectForKind(kind: string): string | null {
  if (DWELLING_KINDS.has(kind)) return 'officer_dwellings'
  return kind
}

/**
 * The `footprintOf` composeLayout is composed with: the SHIPPED pack's drawn
 * size for the sprite that will actually be drawn.
 *
 * The layout's DEFAULT_FOOTPRINTS are a fallback measured off the generator's
 * manifest, and they are era-blind — `great_house` is 200x200 there while the
 * camp era draws a 128x120 log cabin. Every spacing rule the layout enforces
 * (belt separation, ground overlap, lane clearance, keep-out discs) is computed
 * against this size, so a size that is not the drawn one is a rule enforcing
 * the wrong distance and reporting that it did.
 */
export function packFootprintOf(
  pack: IsoPack,
  state: LayoutState
): (kind: string) => { w: number; h: number } | undefined {
  const era = state.era
  return (kind) => {
    const obj = objectForKind(kind)
    const rung = obj === null ? undefined : state.stages?.[obj]
    const r = resolveFrame(pack, obj, kind, era, rung)
    if (!r) return undefined
    const f = pack.frames[r.frame]
    return f ? { w: f.dw, h: f.dh } : undefined
  }
}

interface SpriteInput {
  id: string
  object: string | null
  kind: string
  x: number
  y: number
  flip: boolean
}

function pushSprite(
  out: IsoSprite[],
  issues: string[],
  pack: IsoPack,
  era: Era,
  state: LayoutState,
  s: SpriteInput
): void {
  const rung = s.object === null ? undefined : state.stages?.[ROLE_ALIAS[s.object] ?? s.object]
  const r = resolveFrame(pack, s.object, s.kind, era, rung)
  if (!r) {
    issues.push(
      `iso pack: nothing resolves for ${s.object ?? '(no object)'}/${s.kind} at ${era}` +
        (rung ? `/${rung}` : '')
    )
    return
  }
  const f: PackFrame | undefined = pack.frames[r.frame]
  if (!f) {
    issues.push(`iso pack: frame ${r.frame} is absent from the atlas`)
    return
  }
  out.push({
    id: s.id,
    frame: r.frame,
    x: s.x,
    y: s.y,
    dw: f.dw,
    dh: f.dh,
    flip: s.flip,
    depth: s.y,
    role: s.object,
    trueArt: r.trueArt,
  })
}

export interface IsoSceneOptions {
  space?: LayoutSpace
  /** Reuse an already-composed layout instead of composing again. */
  layout?: Layout
}

/**
 * Compose the world and dress it in the shipped pack.
 *
 * `seed` keys every seeded decision in the layout — the same org therefore
 * always gets the same island, which is what makes a computed lot centre as
 * trustworthy as an authored one.
 */
export function buildIsoScene(
  pack: IsoPack,
  state: LayoutState,
  seed: string | number,
  opts: IsoSceneOptions = {}
): IsoScene {
  const space = opts.space ?? LAYOUT_SPACE
  const layout =
    opts.layout ??
    composeLayout(state, seed, { space, footprintOf: packFootprintOf(pack, state) })
  const era = state.era
  const issues: string[] = []
  const sprites: IsoSprite[] = []

  // ---- structures: the measured world ------------------------------------
  layout.structures.forEach((st, i) => {
    // The pack's honest-zero table gates the STATE objects. A structure the
    // layout emitted for an object whose rung has built nothing draws nothing —
    // except the handful whose empty rung IS the drawing, which iso-layout
    // already decided by emitting them at all (ALWAYS_DRAWN); the pack answers
    // those with their own empty-rung art (a camp cairn, a bare plinth).
    pushSprite(sprites, issues, pack, era, state, {
      id: `st:${i}:${st.role}`,
      object: st.role,
      kind: st.kind,
      x: st.at.x,
      y: st.at.y,
      flip: st.flip,
    })
  })

  // ---- the harbour: kit, moorings, cranes, the boat -----------------------
  const h = layout.harbour
  if (h) {
    h.items.forEach((it, i) => {
      pushSprite(sprites, issues, pack, era, state, {
        id: `hb:${i}:${it.kind}`,
        object: pack.resolve[it.kind] ? it.kind : null,
        kind: it.kind,
        x: it.at.x,
        y: it.at.y,
        flip: it.flip,
      })
    })
    h.moorings.forEach((m, i) => {
      pushSprite(sprites, issues, pack, era, state, {
        id: `mo:${i}`,
        object: 'berths',
        kind: 'mooring_post',
        x: m.x,
        y: m.y,
        flip: false,
      })
    })
    h.cranes.forEach((c, i) => {
      pushSprite(sprites, issues, pack, era, state, {
        id: `cr:${i}`,
        object: null,
        kind: 'harbor_crane',
        x: c.x,
        y: c.y,
        flip: false,
      })
    })
  }

  // ---- planting: the forest belt, then the meadow scatter ------------------
  // Nature has no state object and says so: `role: null` is what keeps
  // check_state_traceable honest instead of inventing a ladder for a tree.
  layout.ring.forEach((r, i) => {
    pushSprite(sprites, issues, pack, era, state, {
      id: `ring:${r.layer}:${i}`,
      object: null,
      kind: r.kind,
      x: r.at.x,
      y: r.at.y,
      flip: r.flip,
    })
  })
  layout.scatter.forEach((s, i) => {
    pushSprite(sprites, issues, pack, era, state, {
      id: `sc:${i}`,
      object: null,
      kind: s.kind,
      x: s.at.x,
      y: s.at.y,
      flip: s.flip,
    })
  })

  // ONE depth key, the projected base y — the same sort compose.py does and the
  // same value the engine's sortableChildren layer already consumes. A stable
  // tie-break keeps two sprites at one y from swapping between frames.
  sprites.sort((a, b) => a.depth - b.depth || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))

  const lamp = layout.lighthouse?.lamp
  return {
    layout,
    space,
    sprites,
    lamp: lamp?.lit && lamp.at ? { x: lamp.at.x, y: lamp.at.y } : null,
    issues,
  }
}

/** True when this object's rung means nothing is built — re-exported so the
 * render path has exactly one honest-zero predicate to reach for. */
export function objectIsEmpty(pack: IsoPack, state: LayoutState, object: string): boolean {
  return isEmptyRung(pack, state.stages?.[object])
}

// ── the camera: tiles in, layout pixels out, once ──────────────────────────

/**
 * The camera position (in TILES) that centres the island.
 *
 * The camera contract stays tile-space in both kernels, so the pan inverse, the
 * pointer inverse and the deep link all keep one shape. Under iso the tiles a
 * camera names are the ISO tiles the kernel projects, so the island centre is
 * simply the inverse projection of the layout's own centre — derived, never a
 * second literal.
 *
 * A DEEP LINK'S ?x/?y THEREFORE MEANS A DIFFERENT PLACE IN THE TWO KERNELS.
 * That is a real limitation of this round and it is stated rather than
 * discovered: the two worlds are not the same size or shape, and pretending one
 * tile coordinate names the same ground in both would be the lie. Re-basing the
 * deep-link contract is the zoom step's work.
 */
export function cameraHome(
  kind: ProjectionKind,
  space: LayoutSpace = LAYOUT_SPACE
): { x: number; y: number } {
  if (kind !== 'iso') return TOPDOWN_HOME
  const t = projectionFor('iso').unproject(space.cx, space.cy)
  return { x: t.tx, y: t.ty }
}

/** The top-down world's landing camera — the whole island in frame. Unchanged
 * from the literal that used to sit in two places in engine-client. */
const TOPDOWN_HOME = { x: 120, y: 32 } as const

export interface CameraBounds {
  x0: number
  y0: number
  x1: number
  y1: number
}

/**
 * The camera clamp box in TILES — one world, one clamp, per kernel.
 *
 * Top-down clamps to the archipelago canvas plus a sea margin, exactly as it
 * always has. Iso clamps to the tile-space AABB of the LAYOUT rect, derived
 * from all four PROJECTED corners: under iso the world's tile extent is a
 * diamond, and a box fitted to two corners would refuse to pan to the other
 * two — which is where the harbour is.
 */
export function cameraClamp(
  kind: ProjectionKind,
  canvas: { w: number; h: number },
  margin = 24,
  space: LayoutSpace = LAYOUT_SPACE
): CameraBounds {
  if (kind !== 'iso') {
    return { x0: -margin, y0: -margin, x1: canvas.w + margin, y1: canvas.h + margin }
  }
  const proj = projectionFor('iso')
  const corners = [
    proj.unproject(0, 0),
    proj.unproject(space.w, 0),
    proj.unproject(0, space.h),
    proj.unproject(space.w, space.h),
  ]
  const xs = corners.map((c) => c.tx)
  const ys = corners.map((c) => c.ty)
  return {
    x0: Math.min(...xs) - margin,
    y0: Math.min(...ys) - margin,
    x1: Math.max(...xs) + margin,
    y1: Math.max(...ys) + margin,
  }
}
