/**
 * BLUEPRINT — the verification bridge: composeLayout's output, in the exact
 * shapes checks/world_checks.py reads.
 *
 * WHY THIS FILE EXISTS. The layout stage has survived three adversarial rounds
 * and nothing had ever LOOKED at it: composeLayout had no caller outside its
 * own tests, and the twelve invariants in checks/world_checks.py had never seen
 * a composed island because nothing emitted a blueprint. Every measurement
 * already taken was worth nothing until a frame could be judged. This module is
 * the missing half — it turns a Layout into (a) the blueprint JSON the checks
 * read and (b) an ordered DRAW LIST a renderer can paint from, so the offline
 * still and the live engine can be held to one description.
 *
 * THE ONE RULE THAT MAKES IT WORTH ANYTHING (checks/world_checks.py's own law,
 * inverted): the checks may not import what they test, so this file may not
 * make their job easy. Two consequences, both deliberate:
 *
 *   `justified` IS NOT DERIVED FROM WHAT WAS DRAWN. compose.py builds its
 *   JUSTIFIED set by adding a name in the same breath as it places the sprite,
 *   which makes check_state_traceable a tautology — `drawn - justified` is
 *   empty by construction and the arm can never fire. Here `justified` is
 *   derived from STATE ALONE (justifiedFromState below): which objects have a
 *   rung or a count that entitles them, resolved through the pack's own
 *   (object, era, rung) table. A layout that emits a warehouse while the
 *   warehouse count is 0 therefore shows up as an orphan, which is the whole
 *   point of that check.
 *
 *   `layers` IS NOT EMITTED HERE. The id buffers describe PAINT order including
 *   shadows, and only the thing that actually paints knows that. Emitting a
 *   guess would be a sensor wired to the wrong artifact. The rasteriser fills
 *   it in from what it really painted (see cabinet/scripts/world-capture).
 *
 * ERA VOCABULARY COMES FROM THE PACK, NOT FROM composeLayout. composeLayout
 * emits a ROLE ('library') and a hamlet-vocabulary kind ('library'); the art
 * for an era and a rung is resolve[object][era][rung]. The ONE exception is the
 * officer dwellings, where composeLayout already era-gates (dwellingKind
 * returns camp_tent at camp and one of six houses above it) and the per-lot
 * variety is a real product property the pack's single '*' entry would flatten.
 * That exception is named in KIND_IS_ERA_AWARE and nowhere else.
 *
 * PURE: no clock, no RNG, no IO, no DOM — same law as ./iso-layout.
 */
import {
  auditLayout,
  CAMP_DWELLING,
  LANE_SQUASH,
  composeLayout,
  countOf,
  eraAtLeast,
  HOUSE_KINDS,
  PAINT_FEATHER,
  presentRung,
  type ComposeOptions,
  type Footprint,
  type Layout,
  type LayoutState,
  type Point,
} from './iso-layout'
import { LANDING_FRAMES, VILLAGE_LIFE_FRAMES } from './iso-layout/dressing'

// ── the shipped pack, as much of it as the bridge reads ────────────────────

export interface PackFrame {
  x: number
  y: number
  w: number
  h: number
  dw: number
  dh: number
  anchor: [number, number]
  atlas: number
  scale: number
}

export interface PackResolveEntry {
  frame: string
  true_art: boolean
}

export interface WorldPack {
  frames: Record<string, PackFrame>
  resolve: Record<string, Record<string, Record<string, PackResolveEntry>>>
  empty_rungs: string[]
  atlases: string[]
  atlas_size: number
  note: string
}

/**
 * composeLayout's kind -> the pack OBJECT whose ladder decides its art.
 *
 * Anything absent draws itself: nature, harbour clutter and the market stall
 * have no ladder in the pack's resolve table, so their kind IS their frame.
 */
const OBJECT_OF_KIND: Readonly<Record<string, string>> = {
  great_house: 'great_house',
  well: 'well',
  firepit: 'firepit',
  library: 'library',
  workshop: 'workshop',
  outbuildings: 'outbuildings',
  warehouse: 'warehouse',
  harbormaster_hut: 'harbormaster_hut',
  lighthouse: 'lighthouse',
  cargo_stacks: 'cargo_stacks',
  harbor_boat: 'harbor_boat',
  mooring_post: 'berths',
  // The dressing's LADDER items (iso-layout/dressing.ts). Each is emitted under
  // its OBJECT name precisely so the pack's (object, era, rung) table picks the
  // art — a hamlet law plot is a fence run, a camp one is a carved post, and a
  // layout that chose between them would be a second vocabulary table.
  law_plot: 'law_plot',
  pens: 'pens',
  water_store: 'water_store',
  composter: 'composter',
  noticeboard: 'noticeboard',
  flagpole: 'flagpole',
  veto_plinth: 'veto_plinth',
  observatory: 'observatory',
  journal_desk: 'journal_desk',
  lantern_posts: 'lantern_posts',
}

/**
 * The kinds composeLayout already chose an ERA-CORRECT art for. See the header:
 * the dwelling row varies per lot on purpose, and routing it through the pack's
 * single '*' entry would put six identical roofs in a line — which is exactly
 * what dwellingKind exists to prevent.
 */
const KIND_IS_ERA_AWARE: ReadonlySet<string> = new Set([...HOUSE_KINDS, CAMP_DWELLING])

/** resolve[object][era][rung] ?? resolve[object][era]['*'] — the pack's own rule. */
export function resolveFrame(
  pack: WorldPack,
  object: string,
  era: string,
  rung: string | null | undefined
): string | null {
  const byEra = pack.resolve?.[object]?.[era]
  if (!byEra) return null
  const hit = (rung != null && byEra[rung]) || byEra['*']
  return hit ? hit.frame : null
}

/**
 * The ART a composeLayout kind draws as, for this state.
 *
 * ONE definition, used twice on purpose: once to SIZE the layout (through
 * ComposeOptions.footprintOf, so the ground diamonds the placement rules used
 * are the diamonds the drawn sprite really has) and once to NAME the sprite in
 * the blueprint. Two definitions here would put the rules and the render on
 * different sprites, which is the defect DEFAULT_FOOTPRINTS' own docstring
 * warns about one level down.
 */
export function frameOfKind(
  pack: WorldPack,
  state: LayoutState,
  kind: string
): string {
  if (KIND_IS_ERA_AWARE.has(kind)) return kind
  const object = OBJECT_OF_KIND[kind]
  if (object) {
    const f = resolveFrame(pack, object, state.era, state.stages?.[object])
    if (f) return f
  }
  return kind
}

/** The pack's drawn size for a frame, or null when the pack has no such frame. */
export function drawSizeOf(pack: WorldPack, frame: string): Footprint | null {
  const f = pack.frames[frame]
  return f ? { w: f.dw, h: f.dh } : null
}

/**
 * ComposeOptions.footprintOf for a state and a pack — the shipped sizes, so the
 * clearance rules measure the sprite that will actually be drawn.
 */
export function packFootprints(
  pack: WorldPack,
  state: LayoutState
): (kind: string) => Footprint | undefined {
  return (kind: string) => drawSizeOf(pack, frameOfKind(pack, state, kind)) ?? undefined
}

// ── what state entitles this frame to draw ─────────────────────────────────

/**
 * Every sprite name a STATE RULE entitles this frame to draw — computed from
 * `state` and the pack alone, never from the placed sprites.
 *
 * This is the sensor check_state_traceable actually needs. Reading it off the
 * emitted sprites (compose.py's JUSTIFIED) makes `drawn - justified` empty by
 * construction: a check that restates the emitter cannot catch the emitter
 * being wrong. Nature is deliberately NOT here — an island has a treeline
 * whether or not anyone has landed on it, so it goes through verify.py's
 * --allow-ambient list, which is a static reviewable file that fires when the
 * planting stages grow a new species.
 */
export function justifiedFromState(pack: WorldPack, state: LayoutState): string[] {
  const out = new Set<string>()
  const era = state.era
  const add = (object: string, rungKey = object) => {
    const f = resolveFrame(pack, object, era, state.stages?.[rungKey])
    if (f) out.add(f)
  }

  // Always drawn, because the empty rung IS the drawing (iso-layout ALWAYS_DRAWN).
  add('lighthouse')
  add('firepit')

  if (presentRung(state, 'great_house')) add('great_house')
  if (presentRung(state, 'well')) add('well')
  if (presentRung(state, 'library')) add('library')
  if (presentRung(state, 'workshop')) add('workshop')
  if (presentRung(state, 'outbuildings')) add('outbuildings')

  // ---- the district dressing (iso-layout/dressing.ts) ---------------------
  // THE LADDER CLASS: each on its own rung, exactly like a building. Note this
  // is `presentRung`, not `isBuilt` — an unmeasured ladder entitles nothing,
  // and the always-drawn override belongs to the four objects above.
  for (const object of [
    'law_plot',
    'pens',
    'water_store',
    'composter',
    'noticeboard',
    'flagpole',
    'veto_plinth',
    'observatory',
    'journal_desk',
    'lantern_posts',
  ]) {
    if (presentRung(state, object)) add(object)
  }
  // A LIT POST is the `posts_lit` count, and it has no resolve entry of its own
  // (the pack has no `posts_lit` object): the art is the lantern, and the count
  // is what entitles it. Nothing lights without a post to light.
  if (countOf(state, 'posts_lit') > 0 && countOf(state, 'lantern_posts') > 0) {
    out.add('lamp_lantern')
  }
  // THE COUNT-GATED BUILDINGS: a windmill says the fleet runs services, a kiln
  // says more than one does, a coop says more than one outbuilding.
  if (eraAtLeast(era, 'hamlet')) {
    if (countOf(state, 'pens') >= 1) out.add('windmill')
    if (countOf(state, 'pens') >= 2) out.add('watermill_kiln')
    if (countOf(state, 'outbuildings') >= 2) out.add('chicken_coop')
  }
  // THE VILLAGE-LIFE CLASS: entitled by the ERA and nothing finer, which is the
  // reference's own rule (compose.py:523 — "A camp is a camp: no benches, no
  // flowerbeds, no street lamps, no market goods"). At camp this set is EMPTY,
  // so any one of these names on a camp frame is an orphan and
  // check_state_traceable goes red. That is the arm the `camp-bench` mutation
  // proves, and it is the reason the list is a closed constant in dressing.ts
  // rather than something derived from what the dressing pass happened to place.
  if (eraAtLeast(era, 'hamlet')) for (const k of VILLAGE_LIFE_FRAMES) out.add(k)
  // THE LANDING: at every era, camp included. A cabinet exists because somebody
  // arrived, so the craft that brought them is as true on day zero as the
  // treeline — see dressLanding in iso-layout/dressing.ts.
  for (const k of LANDING_FRAMES) out.add(k)

  // The dwelling row: every art the era's variety pool may put on a lot. The
  // COUNT is what entitles them, so an org with no officers justifies none.
  if (countOf(state, 'officer_dwellings') > 0) {
    if (eraAtLeast(era, 'hamlet')) for (const k of HOUSE_KINDS) out.add(k)
    else out.add(CAMP_DWELLING)
  }

  // The harbour, object by object, each on its own count.
  for (let i = 0; i < countOf(state, 'warehouse'); i++) add('warehouse')
  if (presentRung(state, 'harbormaster_hut')) add('harbormaster_hut')
  if (countOf(state, 'berths') > 0) add('berths')
  if (presentRung(state, 'harbor_boat')) add('harbor_boat')
  if (countOf(state, 'packs_inherited') > 0) out.add('harbor_crane')
  if (countOf(state, 'cargo_stacks') > 0) {
    // buildHarbour lays DOCK_KIT[0 .. cargo*3); the kit is dressing in
    // proportion to how much passes over the dock, so the whole reachable
    // prefix is entitled. cargo_stacks itself resolves through the pack.
    add('cargo_stacks')
    for (const k of DOCK_KIT_FRAMES) out.add(k)
  }
  return [...out].sort()
}

/**
 * The dock kit's frames, in DOCK_KIT order minus the one with a ladder.
 *
 * Duplicated from harbour.ts's DOCK_KIT deliberately: this list answers "what
 * is ENTITLED", and deriving it from the table that decides "what is PLACED"
 * would make the entitlement follow the placement, which is the tautology this
 * whole function exists to avoid. blueprint.test.ts pins the two against each
 * other so the copy cannot silently fall behind.
 */
export const DOCK_KIT_FRAMES: readonly string[] = [
  'cargo_barrels',
  'crate_single',
  'rope_coil',
  'crab_pots',
  'fish_barrel',
  'fishing_net',
  'fish_drying_rack',
  'anchor',
  'barrel_single',
]

// ── the emitted shapes ─────────────────────────────────────────────────────

export type Ellipse4 = [number, number, number, number]
export type Rect4 = [number, number, number, number]

/** One sprite, in check_on_road / check_stacking's own contract. */
export interface BlueprintSprite {
  /** The ART name — the file in the assets dir the checks read. */
  n: string
  /** BASE CENTRE x, layout px. */
  x: number
  /** BASE CENTRE y (the bottom vertex of the ground diamond), layout px. */
  y: number
  /** DRAWN width. */
  w: number
  /** DRAWN height. */
  h: number
}

export interface BlueprintState {
  date: string
  era: string
  index: number
  ladders: Record<string, { stage: string | null; n: number; measured: boolean }>
  justified: string[]
  gaps: { object: string; era: string; stage: string | null; drawn: string }[]
}

export interface Blueprint {
  canvas: [number, number]
  island_centre: [number, number]
  cove: [number, number, number] | null
  plaza: Ellipse4 | null
  fields: Ellipse4[]
  quay: Rect4 | null
  lanes: Record<string, [number, number][]>
  driveways: [[number, number], [number, number]][]
  lots: Record<string, { c: [number, number]; road: [number, number]; face: [number, number] }[]>
  districts: [number, number, number][]
  sprites: BlueprintSprite[]
  /** Filled by whatever PAINTS — see the header. Empty here, never guessed. */
  layers: unknown[]
  state: BlueprintState
}

/** A sprite as the rasteriser needs it: the blueprint row plus how to paint it. */
export interface DrawSprite extends BlueprintSprite {
  flip: boolean
  /**
   * Does this sprite cast a ground shadow? False for anything standing on
   * water — a moored boat has no shadow on the sea, and compose.py passes
   * shadow=False for exactly that set.
   */
  shadow: boolean
}

export interface DrawBlob {
  x: number
  y: number
  rx: number
  ry: number
  /** Blend strength 0..1; absent means solid. */
  w?: number
}

export interface DrawPaint {
  kind: string
  tone?: number
  blobs: DrawBlob[]
}

export interface DrawLane {
  key: string
  kind: string
  /** How much its destination is used (iso-layout/lanes.ts LANE_WIDTH_RUNGS). */
  width: number
  /**
   * What it is PAVED with — the org-wide road ladder's rung name.
   *
   * SHIPPED because the renderer has to PAINT it. Since 2026-07-27 the road
   * rung no longer sets any lane's width (that is the destination's own
   * traffic), so if the rasteriser kept painting every lane as bare dirt the
   * road ladder would stop reaching the frame entirely and a real rung change
   * would move nothing — the defect this whole library exists to make
   * impossible.
   */
  surface: string
  runs: [number, number][][]
}

/**
 * Everything a renderer needs that is NOT in the blueprint: the coastline
 * raster, the ground regions, the lane surfaces, the wharf and the lamp.
 *
 * THE COASTLINE IS SHIPPED, NOT RE-DERIVED. A rasteriser that rebuilt the
 * island from the same formula would be a second definition of where the land
 * is, and the first thing a second definition does is disagree — with the
 * placement rules that already ran against the first one.
 */
export interface DrawList {
  canvas: [number, number]
  island_centre: [number, number]
  coast: {
    step: number
    mw: number
    mh: number
    /** base64 of mw*mh bytes: bit0 = land, bit1 = beach. */
    mask: string
  }
  paint: DrawPaint[]
  lanes: DrawLane[]
  /**
   * The vertical squash of a lane's occupancy disc (lanes.ts LANE_SQUASH).
   *
   * SHIPPED so the painted road is the reserved road. A renderer that drew a
   * round stroke would paint tarmac over ground the clearance rules never
   * reserved, and every sprite standing on that surplus would be a real
   * on-road defect that no rule could have prevented.
   */
  lane_squash: number
  /**
   * How far a painted region's edge is feathered, in layout px, by kind
   * (iso-layout/paint.ts PAINT_FEATHER). Absent kinds have a hard edge.
   *
   * SHIPPED for the same reason `lane_squash` is: two renderers paint this
   * list, and a feather each of them held privately would be two different
   * grounds. The Captain's 2026-07-27 frame is what this is for — the meadow
   * shading read as hard dark ellipses because the reference's 26px mask blur
   * (compose.py:149) had no home on the data side of the bridge.
   */
  paint_feather: Record<string, number>
  wharf: { shore: [number, number][]; depth: number } | null
  jetty: { at: [number, number]; end: [number, number]; width: number } | null
  /** compose.py LAMP_AT — the glow's centre, or null when the lamp is dark. */
  lamp_at: [number, number] | null
  /** What is alight, at its flue: [x, y, puffs, scale]. See SMOKE_FLUES. */
  smokes: [number, number, number, number][]
  sprites: DrawSprite[]
}

export interface EmittedFrame {
  blueprint: Blueprint
  draw: DrawList
  /** auditLayout's four arms — reported, so a capture never hides them. */
  audit: ReturnType<typeof auditLayout>
}

/**
 * WHAT BURNS — the frames that may emit smoke, and where their flue is.
 *
 * SMOKE COMES FROM THE FIRE, NOT THE TENT (Captain, 2026-07-27). The camp
 * frame put a plume over the canvas tent: `smokesOf` emitted for the ROLE
 * `officer_dwelling` at every era, and at camp that role's art is `camp_tent`.
 * A tent has no chimney. The campfire three tiles away has no flue either and
 * was the only thing on the island actually alight.
 *
 * SO THE GATE IS THE ART, NOT THE ROLE. A role is era-agnostic — one
 * `officer_dwelling` is a tent at camp, a chimneyed hut at hamlet, a cottage in
 * town — so a role-keyed table cannot answer "does this thing have a flue?"
 * without re-deriving the era, which is the pack's job. The frame is what is
 * DRAWN, and whether the drawn sprite has a chimney is a fact about that
 * sprite. Keying on it means the era gate comes free and correct.
 *
 * ALLOWLIST, and absence is the hard default: a frame not named here emits
 * nothing. The alternative (a smokeless list) is open at the wrong end — every
 * new shed the pack ships would smoke until someone remembered to add it.
 *
 * EVERY ENTRY WAS READ OFF THE SHIPPED ATLAS, 2026-07-27, by cropping the frame
 * and looking at it. The offsets are the top band's own centroid in the
 * sprite's box: `fx` from the box CENTRE as a fraction of width, `fy` up from
 * the base as a fraction of height (a sprite is drawn bottom-centre at its
 * point, so the flue is at `x + w*fx, y - h*fy`). Frames deliberately NOT here,
 * with the reason, because the omissions are the whole point:
 *   camp_tent, camp_leanto, camp_toolbox, camp_book_crate, camp_tarp_cache,
 *   camp_signal_post — canvas, open sheds and posts; no flue in the art.
 *   camp_log_cabin — a plain ridge, no chimney drawn on it.
 *   cottage_a, town_hall, bay_wings, well_house — the topmost feature is a
 *   roof ridge, a finial or a cupola, and none of them is a chimney.
 *   barn, town_barn, bay_great_barn, chicken_coop, warehouse, town_warehouse,
 *   bay_warehouse_row, harbormaster_hut, well, town_stone_well — no flue.
 *   bay_workshop_hall — it HAS a stack, and the art already draws its own smoke
 *   coming out of it; a second plume would be the same fire counted twice.
 */
export const SMOKE_FLUES: Readonly<
  Record<string, { fx: number; fy: number; puffs: number; scale: number }>
> = {
  // OPEN FIRES — the flame IS the source, so the plume starts at the sprite's
  // own top. These are the hearth ladder's four era arts.
  camp_campfire: { fx: 0.01, fy: 1.0, puffs: 7, scale: 0.62 },
  firepit: { fx: 0.044, fy: 1.0, puffs: 7, scale: 0.72 },
  town_brazier: { fx: -0.02, fy: 1.0, puffs: 7, scale: 0.68 },
  bay_plaza_hearth: { fx: -0.054, fy: 1.0, puffs: 8, scale: 0.85 },
  // CHIMNEYS — dwellings, the great house, the forge, the library, the kiln.
  officer_house_a: { fx: 0.097, fy: 1.0, puffs: 7, scale: 0.72 },
  officer_house_b: { fx: -0.175, fy: 1.0, puffs: 7, scale: 0.72 },
  officer_house_c: { fx: -0.14, fy: 1.0, puffs: 7, scale: 0.72 },
  cottage_b: { fx: -0.16, fy: 1.0, puffs: 7, scale: 0.72 },
  cottage_c: { fx: 0.184, fy: 1.0, puffs: 7, scale: 0.72 },
  great_house: { fx: -0.122, fy: 1.0, puffs: 8, scale: 0.85 },
  workshop: { fx: 0.138, fy: 1.0, puffs: 8, scale: 0.8 },
  library: { fx: 0.14, fy: 0.926, puffs: 6, scale: 0.7 },
  // The kiln is a FIRE with a stack, and it rides in the dressing rather than
  // in `structures` — which is a fact about which list it lands in, not about
  // what it is. smokesOf sweeps both for exactly this reason.
  watermill_kiln: { fx: -0.013, fy: 0.953, puffs: 8, scale: 0.8 },
  town_cottage: { fx: -0.198, fy: 1.0, puffs: 7, scale: 0.72 },
  town_manor: { fx: 0.193, fy: 1.0, puffs: 8, scale: 0.85 },
  town_workshop_hut: { fx: 0.223, fy: 1.0, puffs: 8, scale: 0.8 },
  town_harbor_office: { fx: -0.273, fy: 1.0, puffs: 6, scale: 0.7 },
  bay_townhouse: { fx: -0.226, fy: 1.0, puffs: 7, scale: 0.72 },
  // Two chimneys in the art; the RIGHT one, because draw_smoke drifts +x and a
  // plume off the left stack would blow back across its own roof.
  bay_manor_estate: { fx: 0.242, fy: 1.0, puffs: 8, scale: 0.85 },
}

/** Sprites that stand on water and therefore cast nothing onto the ground. */
const NO_SHADOW: ReadonlySet<string> = new Set([
  'mooring_post',
  'lilypads',
  'boat_rowing',
  'boat_packet',
  'boat_fishing',
  'bay_steam_packet',
  'buoy',
  'duck',
])

const r1 = (v: number) => Math.round(v * 10) / 10
const i = (v: number) => Math.round(v)
const pt = (p: Point): [number, number] => [i(p.x), i(p.y)]

/**
 * Compose a state and emit both halves of the bridge.
 *
 * `meta.date` and `meta.index` are carried through untouched: they are facts
 * about the org's replayed history, and inventing either here would be the
 * "drawn ahead of its measurement" defect one layer up from where the checks
 * look for it.
 */
export function composeFrame(
  pack: WorldPack,
  state: LayoutState,
  seed: string | number,
  meta: { date: string; index: number },
  opts: ComposeOptions = {}
): EmittedFrame {
  const layout = composeLayout(state, seed, {
    ...opts,
    footprintOf: opts.footprintOf ?? packFootprints(pack, state),
  })
  return emitFrame(pack, layout, meta)
}

/** The emitter proper, for a Layout that has already been composed. */
export function emitFrame(
  pack: WorldPack,
  layout: Layout,
  meta: { date: string; index: number }
): EmittedFrame {
  const state = layout.state
  const sprites: DrawSprite[] = []

  const push = (kind: string, at: Point, flip: boolean, size: Footprint) => {
    const n = frameOfKind(pack, state, kind)
    const drawn = drawSizeOf(pack, n) ?? size
    sprites.push({
      n,
      x: i(at.x),
      y: i(at.y),
      w: i(drawn.w),
      h: i(drawn.h),
      flip,
      shadow: !NO_SHADOW.has(n),
    })
  }

  // PLACEMENT ORDER, exactly as composeLayout emitted it. It is NOT paint
  // order — check_paint_fidelity says so in its own docstring, and the
  // rasteriser sorts a copy by base y. Re-ordering here would quietly make the
  // blueprint a claim about depth that nothing verified.
  for (const s of layout.structures) push(s.kind, s.at, s.flip, s.size)
  // The dressing rides here, between the buildings and the harbour, because
  // that is where composeLayout emits it. `overWater` decides the SHADOW and
  // nothing else — a buoy casts nothing onto the sea, and the NO_SHADOW name
  // list cannot answer that for a crate that happens to sit on a deck.
  for (const d of layout.dressing) {
    const n = frameOfKind(pack, state, d.kind)
    const drawn = drawSizeOf(pack, n) ?? d.size
    sprites.push({
      n,
      x: i(d.at.x),
      y: i(d.at.y),
      w: i(drawn.w),
      h: i(drawn.h),
      flip: d.flip,
      shadow: !d.overWater && !NO_SHADOW.has(n),
    })
  }
  const h = layout.harbour
  if (h) {
    for (const item of h.items) push(item.kind, item.at, item.flip, item.size)
    for (const m of h.moorings) {
      push('mooring_post', m, false, drawSizeOf(pack, 'mooring_post') ?? { w: 24, h: 28 })
    }
    for (const c of h.cranes) {
      push('harbor_crane', c, false, drawSizeOf(pack, 'harbor_crane') ?? { w: 75, h: 95 })
    }
  }
  for (const r of layout.ring) push(r.kind, r.at, r.flip, r.size)
  for (const s of layout.scatter) push(s.kind, s.at, s.flip, s.size)

  const regions = layout.regions
  const blueprint: Blueprint = {
    canvas: [i(layout.space.w), i(layout.space.h)],
    island_centre: [i(layout.space.cx), i(layout.space.cy)],
    cove: layout.coast.cove
      ? [i(layout.coast.cove.x), i(layout.coast.cove.y), i(layout.coast.cove.r)]
      : null,
    plaza: regions.plaza ? (regions.plaza.map(i) as Ellipse4) : null,
    fields: regions.fields.map((f) => f.map(i) as Ellipse4),
    quay: regions.quay ? (regions.quay.map(i) as Rect4) : null,
    lanes: Object.fromEntries(
      layout.lanes.flatMap((l) =>
        l.runs.map(
          (run, k) =>
            [l.runs.length > 1 ? `${l.key}#${k}` : l.key, run.map(pt)] as [
              string,
              [number, number][],
            ]
        )
      )
    ),
    driveways: layout.driveways.map((d) => [pt(d.door), pt(d.road)]),
    lots: Object.fromEntries(
      Object.entries(layout.lots).map(([k, v]) => [
        k,
        v.map((l) => ({ c: pt(l.c), road: pt(l.road), face: [r1(l.face.x), r1(l.face.y)] as [number, number] })),
      ])
    ),
    districts: layout.districts.map((d) => [i(d.at.x), i(d.at.y), i(d.r)]),
    sprites: sprites.map(({ n, x, y, w, h: sh }) => ({ n, x, y, w, h: sh })),
    layers: [],
    state: {
      date: meta.date,
      era: state.era,
      index: meta.index,
      ladders: laddersOf(state),
      justified: justifiedFromState(pack, state),
      gaps: gapsOf(pack, state),
    },
  }

  const mask = new Uint8Array(layout.coast.mw * layout.coast.mh)
  for (let k = 0; k < mask.length; k++) {
    mask[k] = (layout.coast.land[k] ? 1 : 0) | (layout.coast.beach[k] ? 2 : 0)
  }

  const draw: DrawList = {
    canvas: blueprint.canvas,
    island_centre: blueprint.island_centre,
    coast: {
      step: layout.coast.step,
      mw: layout.coast.mw,
      mh: layout.coast.mh,
      mask: base64(mask),
    },
    paint: layout.paint.map((r) => ({
      kind: r.kind,
      ...(r.tone === undefined ? {} : { tone: r.tone }),
      blobs: r.blobs.map((b) => ({
        x: r1(b.c.x),
        y: r1(b.c.y),
        rx: r1(b.rx),
        ry: r1(b.ry),
        ...(b.w === undefined ? {} : { w: r1(b.w) }),
      })),
    })),
    lanes: layout.lanes.map((l) => ({
      key: l.key,
      kind: l.kind,
      width: l.width,
      surface: l.surface,
      runs: l.runs.map((run) => run.map(pt)),
    })),
    lane_squash: LANE_SQUASH,
    paint_feather: { ...PAINT_FEATHER } as Record<string, number>,
    wharf: h?.wharf ? { shore: h.wharf.shore.map(pt), depth: h.wharf.depth } : null,
    jetty: h?.jetty
      ? { at: pt(h.jetty.at), end: pt(h.jetty.end), width: h.jetty.width }
      : null,
    lamp_at: layout.lighthouse?.lamp.at ? pt(layout.lighthouse.lamp.at) : null,
    smokes: smokesOf(pack, layout),
    sprites,
  }

  return { blueprint, draw, audit: auditLayout(layout) }
}

/**
 * Every ladder the state carries, in check_era's contract.
 *
 * ABSENT IS UNMEASURED, never zero. A ladder the state never mentions is one
 * nothing has measured, and `measured: false` is what stops the rung arm
 * reading an absence as a rung.
 */
function laddersOf(state: LayoutState): BlueprintState['ladders'] {
  const keys = new Set([
    ...Object.keys(state.stages ?? {}),
    ...Object.keys(state.counts ?? {}),
  ])
  const out: BlueprintState['ladders'] = {}
  for (const k of [...keys].sort()) {
    const stage = state.stages?.[k]
    out[k] = {
      stage: stage === undefined ? null : stage,
      n: countOf(state, k),
      measured: (state.stages && k in state.stages) || (state.counts && k in state.counts) ? true : false,
    }
  }
  return out
}

/**
 * ART GAPS — an object whose (era, rung) has no true art and is drawn with a
 * stand-in. compose.py reports these; the pack marks them with true_art:false.
 *
 * Reported rather than hidden: a stand-in is a fidelity gap, and a gap nobody
 * names is discovered in a screenshot.
 */
function gapsOf(pack: WorldPack, state: LayoutState): BlueprintState['gaps'] {
  const out: BlueprintState['gaps'] = []
  for (const object of Object.keys(pack.resolve ?? {}).sort()) {
    const rung = state.stages?.[object]
    const byEra = pack.resolve[object]?.[state.era]
    if (!byEra) continue
    const hit = (rung != null && byEra[rung]) || byEra['*']
    if (hit && hit.true_art === false) {
      out.push({ object, era: state.era, stage: rung ?? null, drawn: hit.frame })
    }
  }
  return out
}

/**
 * Smoke, hung off the things that are actually alight.
 *
 * A CONSEQUENCE OF SOMETHING BURNING, so it is emitted for the FRAME that was
 * really drawn and for nothing else — smoke over an empty lot is the same class
 * of lie as a driveway to unbuilt grass, and smoke over a tent is that lie one
 * level finer: the building is real, the fire is not.
 *
 * IT SWEEPS THE DRESSING TOO. The kiln is a fire with a stack that happens to
 * ride in `layout.dressing` because of how it is placed, not because of what it
 * is; a sweep that only read `structures` would have to know that.
 *
 * The plume's own size travels with the flue: a campfire is not a manor's
 * chimney, and one shared constant made every fire on the island the same fire.
 */
function smokesOf(pack: WorldPack, layout: Layout): [number, number, number, number][] {
  const out: [number, number, number, number][] = []
  const burn = (kind: string, at: Point, size: Footprint) => {
    const flue = SMOKE_FLUES[frameOfKind(pack, layout.state, kind)]
    if (!flue) return
    const drawn = drawSizeOf(pack, frameOfKind(pack, layout.state, kind)) ?? size
    out.push([
      i(at.x + drawn.w * flue.fx),
      i(at.y - drawn.h * flue.fy),
      flue.puffs,
      flue.scale,
    ])
  }
  for (const s of layout.structures) burn(s.kind, s.at, s.size)
  for (const d of layout.dressing) burn(d.kind, d.at, d.size)
  return out
}

/**
 * base64 without Buffer — this module is imported by the browser bundle too,
 * and `Buffer` is not a thing there. btoa cannot take a Uint8Array directly and
 * chunking keeps String.fromCharCode off its argument-count ceiling.
 */
function base64(bytes: Uint8Array): string {
  let s = ''
  const CHUNK = 0x8000
  for (let k = 0; k < bytes.length; k += CHUNK) {
    s += String.fromCharCode(...bytes.subarray(k, k + CHUNK))
  }
  // eslint-disable-next-line no-undef
  return typeof btoa === 'function'
    ? btoa(s)
    : // Node before btoa was global; the capture script runs there.
      (globalThis as { Buffer?: { from(v: string, e: string): { toString(e: string): string } } })
        .Buffer!.from(s, 'binary')
        .toString('base64')
}
