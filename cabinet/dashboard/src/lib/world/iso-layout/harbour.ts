/**
 * HARBOUR + LIGHTHOUSE — the two places the world tells its most important
 * state, as pure seeded geometry.
 *
 * PORTED FROM compose.py:885-897 (the lighthouse site walk) and :1118-1208
 * (section 7, "the Lantern Quay").
 *
 * WHY THESE TWO ARE ONE MODULE. They are the same geometric problem — a thing
 * pinned to the REAL waterline rather than to an authored coordinate — and the
 * reference solves both with the same primitive, shore_y(): the lowest land row
 * in a column. The wharf sits on it along the cove; the lighthouse walks it east
 * of the cove looking for the most seaward point. Splitting them would give that
 * primitive two callers in two files and, sooner or later, two definitions.
 *
 * NOTHING FLOATS. The reference records the defect this section exists to
 * prevent (compose.py:1119-1120): "the Captain's note on v12 was that the dock
 * sat out in open sea." Every x here resolves its own y through shoreAt(), and
 * the populations that can afford to lose a member DROP one whose column has no
 * land in the cove window rather than inventing a waterline for it: shoreLine()
 * returns a short polyline on a seed whose cove ate the south shore, and the
 * dock kit and the cranes skip the column.
 *
 * THERE ARE NO GUESSED WATERLINES LEFT. Three anchors used to fall back to one
 * — the jetty root (`?? cove.y - 140`) and the warehouse and harbourmaster
 * columns (`?? cove.y - 160`) — because each is a single anchor the harbour is
 * defined by rather than one of many, and dropping it would drop the thing. They
 * now fall back to `nearestShoreY()`, the MEASURED waterline of the nearest
 * sampled column, which is a real shore 12px away rather than an invented one.
 * The jetty is stricter still: a guessed root was emitted as geometry, so it now
 * refuses to exist at all when its own column has no land (see below).
 *
 * THE PIER IS ATTACHED TO THE SHORE, and that sentence is the whole of the fix
 * the Captain's 2026-07-27 frame forced. The reference roots the finger pier 52px
 * BELOW its column's waterline — out on the water — and gets away with it only
 * where a deck happens to cover the gap. Measured across 80 seeds before the fix:
 * 480 of 480 (era x rung x seed) put the root 52px out with no deck under it,
 * which is a pier connected to nothing. The root is now its own column's
 * waterline lifted onto the LAND side by SHORE_LIFT, so the pier starts exactly
 * where the deck's upper edge does and walks out from there.
 *
 * AND NOTHING IS BEACHED EITHER, which is the same sentence read the other way
 * and the fix the Captain's second 2026-07-27 frame forced. A boat drawn flat
 * along the planks reads as a boat parked on a pier, and `overWater: true` on
 * the vessel was a DECLARATION that nothing measured: it was hard-coded, the
 * flag's own meaning ("does not stand on the island's ground") was true of a
 * crate on the deck as well as of a hull in the water, and the only sensor
 * anywhere asked about the BASE POINT, which sat 82px clear of a deck the
 * sprite was drawn straight across. So: `overWater` is now measured at emit
 * time and never asserted; craft carry a second flag, `afloat`, meaning "must
 * lie in open water"; and `inOpenWater()` decides it on the sprite's own
 * contact patch — clear of land AND clear of every plank this module laid.
 * Emitters check before emitting and the audit re-measures afterwards.
 *
 * THE DECK IS DRAWN, NOT STAMPED. quay.py exists because stamping a deck sprite
 * along the shore "piles overlapping slabs into a jumbled staircase". So this
 * module emits the deck's GEOMETRY — the shore polyline and a depth — and the
 * renderer draws one continuous surface along it. Emitting a list of deck-tile
 * positions would re-create precisely the defect quay.py was written to fix.
 *
 * ERA GATES CONTENT, RUNG MEASURES IT, and the two are kept visibly separate:
 *   - the WHARF is a built surface, so a camp does not have one (quayDepth()
 *     returns 0 at camp whatever the rung says);
 *   - the JETTY's length still follows the rung at every era, so the
 *     measurement is never hidden — a camp that has shipped for a year has a
 *     longer finger pier over the water, and no deck;
 *   - but NEITHER is built from a rung that does not exist. An org whose `quay`
 *     ladder is unmeasured, or on an empty rung, gets no deck AND no pier
 *     (`jetty` is null), where the reference's `WS.stage("quay") or
 *     "rowboat_jetty"` builds the first rung out of the absence. That is a
 *     porting DIVERGENCE and it is the same one the cargo block makes: era may
 *     never hide a count, and no count may be invented from a missing one.
 *   - the MOORINGS, the CARGO, the WAREHOUSES and the CRANES are counts. They
 *     are not era-gated at all: a count is a fact about the org and era may
 *     never hide one. What era does to them is choose the sprite, which is the
 *     renderer's job (vocab.py), not this one's.
 *
 * SPELLING, deliberately inconsistent in exactly one direction: TypeScript
 * identifiers here read `harbour`, and every STATE KEY and emitted sprite kind
 * reads `harbor`/`harbormaster` because those are the literal ids in
 * cabinet/world/growth-ladders.yml and designs/world-mockup-v2/vocab.py. A
 * "tidier" rename would silently stop matching a ladder.
 *
 * PURE: no clocks, no unseeded randomness, no IO, no DOM.
 */
import { groundDiamond } from '../projection'
import type { Footprint } from './clearance'
import type { Coastline } from './coastline'
import { clamp, emptyRung, hypot, type Era, type LayoutSpace, type Point } from './space'

// ── region extents, in the shapes the offline checks read ──────────────────

/**
 * An axis-aligned extent, [x0,y0,x1,y1] — checks/world_checks.py reads the
 * blueprint's `quay` in exactly this shape (check_on_road's exemption and
 * check_terrain's "a harbour approach may leave the shore" clause).
 */
export type Rect = [number, number, number, number]

/**
 * An ellipse extent, [cx,cy,rx,ry] — the shape of the blueprint's `plaza` and
 * of each entry in `fields`. Both checks test `((x-cx)/rx)^2 + ((y-cy)/ry)^2 <= 1`.
 */
export type Ellipse = [number, number, number, number]

export function rectContains(r: Rect, p: Point): boolean {
  return p.x >= r[0] && p.x <= r[2] && p.y >= r[1] && p.y <= r[3]
}

// ── the cove ───────────────────────────────────────────────────────────────

export interface Cove {
  x: number
  y: number
  r: number
}

/** compose.py:1129 — the wharf is looked for 360px either side of the cove. */
export const SHORE_HALF_SPAN = 360
/** compose.py:1129 — one shore sample every 12px. */
export const SHORE_STEP = 12
/** compose.py:1131 — the deck's upper edge sits 4px above the waterline row. */
export const SHORE_LIFT = 4

/**
 * compose.py:1124 shore_at() — the waterline row in one column, searched only
 * across the cove's own vertical window.
 *
 * The window matters: searching the whole canvas would find the island's south
 * shore far from the cove and hang the wharf off it. Returns null when the
 * column has no land in the window at all, and every caller here treats null as
 * "there is nothing to build on in this column" rather than substituting a y.
 */
export function shoreAt(coast: Coastline, cove: Cove, x: number): number | null {
  return coast.shoreY(x, cove.y - cove.r * 1.3, cove.y + cove.r * 1.25)
}

/**
 * compose.py:1128-1131 — the waterline polyline the deck is laid along.
 *
 * Sampled west to east so the renderer can walk it in one direction, and lifted
 * by SHORE_LIFT so the deck's upper edge is on the land side of the waterline
 * rather than straddling it.
 */
export function shoreLine(
  coast: Coastline,
  cove: Cove,
  halfSpan: number = SHORE_HALF_SPAN,
  step: number = SHORE_STEP
): Point[] {
  const out: Point[] = []
  for (let x = cove.x - halfSpan; x <= cove.x + halfSpan; x += step) {
    const sy = shoreAt(coast, cove, x)
    if (sy !== null) out.push({ x, y: sy - SHORE_LIFT })
  }
  return out
}

/**
 * The waterline of the nearest column that HAS one — the only fallback in this
 * module, and a measured one.
 *
 * It exists for the anchors that cannot be dropped (the moorings' base row, the
 * two quayside columns): where those used to substitute an authored offset from
 * the cove's centre, they now take a real shore reading from up to half a sample
 * step away. Takes the shore polyline, whose points are already lifted by
 * SHORE_LIFT, and undoes the lift so callers get a WATERLINE and not a deck edge.
 *
 * Callers must have a non-empty polyline — buildHarbour has already returned
 * null below four columns, so an empty one here is a caller bug, not a seed.
 */
export function nearestShoreY(shore: Point[], x: number): number {
  let best = shore[0]
  for (const p of shore) if (Math.abs(p.x - x) < Math.abs(best.x - x)) best = p
  return best.y + SHORE_LIFT
}

// ── the quay ladder ────────────────────────────────────────────────────────

/**
 * compose.py:1135-1136 — deck depth per quay rung, in layout px.
 *
 * `rowboat_jetty` is 0 ON PURPOSE and is not a missing entry: the first rung of
 * the quay ladder is a couple of planks over the water, which is a jetty and not
 * a deck. A rung ABOVE the table (a ladder that grows a sixth stone rung) gets
 * the deepest wharf rather than none — an unknown rung is more quay, never less.
 *
 * "UNKNOWN" AND "EMPTY" ARE NOT THE SAME UNKNOWN, and reading them as one was a
 * defect measured 2026-07-27: `bare_ground` is not in this table either, and the
 * more-quay-never-less rule handed an UNBUILT quay the deepest stone wharf in
 * the ladder. An empty rung is now answered before the table is consulted (see
 * quayDepth), so the rule keeps its meaning — a rung past the top is more quay —
 * without applying it to a rung below the bottom.
 */
export const QUAY_DEPTH: Readonly<Record<string, number>> = {
  rowboat_jetty: 0,
  timber_jetty: 30,
  stone_quay_2: 40,
  stone_quay_3: 46,
  stone_quay_4: 50,
  stone_quay_5: 54,
}
const QUAY_DEPTH_MAX = 54

/** compose.py:1138 — a timber jetty decks only the middle 30% of the cove. */
export const QUAY_SPAN: Readonly<Record<string, number>> = { timber_jetty: 0.3 }

/** compose.py:1147 — the finger pier's length per rung. */
export const JETTY_LENGTH: Readonly<Record<string, number>> = {
  rowboat_jetty: 96,
  timber_jetty: 150,
}
const JETTY_LENGTH_MAX = 230

/** compose.py:1148 — the pier walks out at the isometric angle, not straight down. */
export const JETTY_ANGLE = 0.16

/**
 * The deck depth an (era, rung) actually builds.
 *
 * NO RUNG, NO QUAY. compose.py:1134 reads `WS.stage("quay") or "rowboat_jetty"`,
 * which turns an unmeasured quay ladder into the ladder's first rung and builds
 * from it. This port does not follow that line, on the same ground it already
 * refused compose.py:1188's `max(1, 1 + cargo*3)` (see the cargo block below):
 * an object with no rule over `state` behind it is exactly what
 * check_state_traceable exists to catch, and "the ladder was never measured" is
 * not a rule that builds anything. It is the difference between no data and
 * zero, and only one of the two may be drawn.
 *
 * A CAMP HAS NO WHARF either. That is a content gate, the same kind as "a camp
 * has no paved square": a deck is a built surface and a camp is the era before
 * the org builds surfaces. It is NOT era hiding a measurement — the rung goes on
 * driving jettyLength() at every era, so a camp that has shipped for a long time
 * shows it as a longer pier over the water. Deleting this gate is mutation MH1.
 */
export function quayDepth(era: Era, rung: string | null | undefined): number {
  if (emptyRung(rung)) return 0
  if (era === 'camp') return 0
  return QUAY_DEPTH[rung as string] ?? QUAY_DEPTH_MAX
}

/**
 * compose.py:1147 — rung only, at every era. See quayDepth's note.
 *
 * 0 MEANS THERE IS NO PIER, and buildHarbour emits no Jetty at all rather than a
 * zero-length one: a pier of length 0 is not a shorter pier, it is a thing that
 * does not exist, and handing the renderer a degenerate object to interpret is
 * how the degenerate value gets drawn.
 */
export function jettyLength(rung: string | null | undefined): number {
  if (emptyRung(rung)) return 0
  return JETTY_LENGTH[rung as string] ?? JETTY_LENGTH_MAX
}

// ── what the harbour emits ─────────────────────────────────────────────────

export interface Wharf {
  /**
   * The waterline polyline the deck is DRAWN along — the kept span, west to
   * east. The renderer lays one continuous surface between this line and
   * `depth` px below it (quay.py deck_strip), and stands a post every ~76px
   * (quay.py posts).
   */
  shore: Point[]
  /** Deck depth below the waterline. Always > 0 — a 0-depth wharf is not one. */
  depth: number
  /**
   * The quay extent the checks read.
   *
   * DERIVED FROM THE KEPT SPAN, which diverges from compose.py:1376 — the
   * reference takes the FULL shore polyline even when it decked only 30% of it,
   * so its exemption zone covers bare shore where no deck was drawn. An
   * exemption wider than the surface it exempts is a check turned down: every
   * sprite standing on that bare shore stops being judged for standing in the
   * road. This rect spans the deck that exists, and no more of the shore.
   *
   * IT IS NOT THE DECK EXACTLY, and the difference is deliberate rather than
   * sloppy: it is the deck's x span, but vertically it runs from 20px ABOVE the
   * highest waterline in that span to 60px below the deck's own depth. The
   * apron is what makes the exemption usable — a crate at the deck's landward
   * edge, or a bollard at its seaward one, is on the wharf in every sense a
   * viewer cares about. What that costs is measured rather than assumed: across
   * 80 village islands the apron holds the 223 QUAYSIDE BUILDINGS (2 warehouses
   * and a harbourmaster's hut per island) that stand on land above the deck, so
   * those are exempt from check_on_road. That exemption cannot mask a defect
   * this layout can produce — every one of them was placed by placeOnGround,
   * which refuses a lane outright — but it is wider than the planks, and a
   * reader is owed that rather than the word "deck".
   */
  rect: Rect
}

export interface Jetty {
  /**
   * Root — where the pier leaves the LAND. Its own column's waterline, lifted
   * onto the land side by SHORE_LIFT, so `coast.landAt(at)` is true on every
   * pier this module emits and the planks meet the beach instead of starting
   * out in the water. A pier that fails that is not emitted at all.
   */
  at: Point
  length: number
  width: number
  angle: number
  /**
   * Seaward end. compose.py:1153 JETTY_END.
   *
   * It is the pier's own geometry and no longer an anchor anything else is
   * pinned to: the vessel used to sit at a fixed offset from it, which is how
   * it came to be drawn on the planks. Berths are searched along the run now
   * (BERTH_STATIONS), so this end is where the pier stops and nothing more.
   */
  end: Point
}

// ── timber over water, and open water ──────────────────────────────────────
//
// THE HARBOUR BUILDS SURFACES OVER THE SEA, so "is this over water?" stopped
// being the same question as "is this floating?" the moment the deck existed.
// A crate on the wharf is over water and standing on planks; a boat on the
// wharf is over water and BEACHED. Everything below exists to keep those two
// apart, because the frame the Captain returned on 2026-07-27 — a packet with
// its hull drawn flat along the finger pier — passed every arm the layout had:
// its base point was in open water, 82px clear of the deck, and the sprite it
// anchored was drawn standing on the planks all the same.

/**
 * quay.py deck_strip's fascia — the constant lip drawn BELOW the deck's own
 * depth so the surface has thickness above the water. It is part of the drawn
 * deck, so anything asking "am I on the deck" has to include it or it will
 * clear the planks by 6px and land on the front board.
 */
export const DECK_FASCIA = 8

/**
 * The deck's upper edge in one column, interpolated between shore samples —
 * quay.py deck_strip's own `top_at()`, which is what the renderer draws from.
 *
 * Returns null OUTSIDE the kept span rather than clamping to its ends, which
 * is the one thing quay.py does differently and deliberately so: quay.py only
 * ever asks about x it is already drawing, while this is asked about moorings
 * and craft that are routinely beyond the deck. Clamping there would invent a
 * deck along bare shore and push things off a surface that is not built.
 */
export function deckEdgeAt(shore: readonly Point[], x: number): number | null {
  for (let i = 0; i < shore.length - 1; i++) {
    const a = shore[i]
    const b = shore[i + 1]
    if (a.x <= x && x <= b.x && b.x !== a.x) return a.y + ((b.y - a.y) * (x - a.x)) / (b.x - a.x)
  }
  return null
}

/** Is this point on the wharf's drawn planks (surface + fascia)? */
export function onWharfDeck(wharf: Wharf | null | undefined, p: Point): boolean {
  if (!wharf) return false
  const top = deckEdgeAt(wharf.shore, p.x)
  return top !== null && p.y >= top && p.y <= top + wharf.depth + DECK_FASCIA
}

/**
 * Is this point on the finger pier's planks? quay.py jetty() walks the run in
 * 1px steps and lays a `width`-wide row at each, so the pier is that swept
 * band — sampled here every 2px, which is finer than any craft is small.
 */
export function onFingerPier(jetty: Jetty | null | undefined, p: Point): boolean {
  if (!jetty) return false
  const dx = Math.sin(jetty.angle)
  const dy = Math.cos(jetty.angle)
  const half = jetty.width / 2
  for (let s = 0; s <= jetty.length; s += 2) {
    if (
      Math.abs(p.x - (jetty.at.x + dx * s)) <= half &&
      Math.abs(p.y - (jetty.at.y + dy * s * 0.86)) <= 4
    ) {
      return true
    }
  }
  return false
}

/** Everything the harbour has BUILT over the water. */
export interface HarbourTimber {
  wharf: Wharf | null
  jetty: Jetty | null
}

export function onHarbourTimber(timber: HarbourTimber, p: Point): boolean {
  return onWharfDeck(timber.wharf, p) || onFingerPier(timber.jetty, p)
}

/**
 * The sprite's ground diamond, probed the way ./clearance's footprintOnLane
 * probes it — four depths, the span narrowing toward the far vertex.
 *
 * The half-width and depth come from ../projection's groundDiamond, which is
 * the ONE definition of a contact patch in this world (checks/world_checks.py
 * ground_box mirrors it). Sampling the base point alone is what let the defect
 * through: the vessel's base was 82px below the deck's front board and its
 * hull was drawn across it anyway.
 */
function contactPatch(at: Point, size: Footprint): Point[] {
  const g = groundDiamond(size.w, size.h)
  const half = Math.max(4, g.hw)
  const out: Point[] = []
  for (const fy of [0, 0.35, 0.7, 1]) {
    const y = at.y - g.depth * fy
    const span = half * (1 - 0.45 * fy)
    for (const fx of [-1, -0.55, 0, 0.55, 1]) out.push({ x: at.x + span * fx, y })
  }
  return out
}

/**
 * Would a craft of this size, based here, lie in OPEN water — clear of the
 * island and clear of every plank the harbour has laid?
 *
 * This is the predicate `afloat` means, and the only one: an emitter that sets
 * the flag has to pass this at emit time, and auditLayout re-measures it with
 * this same function afterwards. Land is asked with `coast.landAt`, the
 * layout's own water predicate — there is no fourth notion of water here.
 */
export function inOpenWater(
  coast: Coastline,
  timber: HarbourTimber,
  at: Point,
  size: Footprint
): boolean {
  for (const p of contactPatch(at, size)) {
    if (coast.landAt(p.x, p.y)) return false
    if (onHarbourTimber(timber, p)) return false
  }
  return true
}

/**
 * One dockside thing standing on the deck or in the harbour water.
 *
 * These are NOT structures. A structure is guaranteed to stand on land
 * (placeOnGround returns null rather than put one in the sea) and auditLayout
 * re-measures that; a mooring post is in the water BY CONSTRUCTION and a crate
 * stands on a deck that is over water. Running them through the structure rules
 * would either delete every one of them or force the water arm to grow an
 * exemption — and an exemption is how a real defect gets waved through later.
 * They carry their own invariant instead: everything here is inside the
 * harbour's own extent, and auditLayout measures that.
 */
export interface HarbourItem {
  kind: string
  at: Point
  flip: boolean
  size: Footprint
  /**
   * True = this does not stand on the island's ground — it is on the deck, on
   * the pier, or in the water. It decides the SHADOW and nothing else.
   *
   * MEASURED, NEVER DECLARED (2026-07-27). It is `!coast.landAt(at)` at emit
   * time on every item here, and auditLayout re-measures it; the vessel used to
   * hard-code `true`, which made it a claim with no sensor on it. A hard-coded
   * `true` on this field is the defect, not a shortcut.
   */
  overWater: boolean
  /**
   * True = this thing FLOATS, so it must lie in open water: clear of land AND
   * clear of the harbour's own timber (`inOpenWater`). False for the dock kit,
   * whose whole point is that it stands on the planks.
   *
   * The two flags are not the same question and were conflated until the
   * Captain's beached-vessel frame: a crate on the wharf is `overWater` and
   * must NOT be `afloat`, and reading one as the other either deletes the cargo
   * from the deck or lets a boat be drawn on it.
   */
  afloat: boolean
}

export interface Harbour {
  cove: Cove
  /** The whole shore polyline the harbour was measured against. */
  shore: Point[]
  /** null at an era or a rung that has built no deck. */
  wharf: Wharf | null
  /**
   * null when the `quay` ladder is unmeasured or on an empty rung — and also
   * when the pier's own column has no land to root in, because a pier that
   * reaches no shore is a lie about the island and a missing one is not.
   */
  jetty: Jetty | null
  /** compose.py:1149-1152 — one per open outcome window (the `berths` count). */
  moorings: Point[]
  /**
   * The drawn size of a mooring post, carried so the audit can measure the
   * posts' contact patches with the size the LAYOUT used. Without it the audit
   * has to guess a footprint, and a sensor holding a different size than the
   * renderer is measuring a different world (blueprint.ts resolves the same
   * post through the pack).
   */
  mooringSize: Footprint
  /** Cargo and working clutter; its extent follows completed work items. */
  items: HarbourItem[]
  /** compose.py:1181 — one per inherited extension pack, as many as fit. */
  cranes: Point[]
  /** What the pack count asked for. cranes.length is lower on a short wharf. */
  cranesRequested: number
  /** Quayside building anchors, on LAND above the wharf. */
  warehouseSites: Point[]
  harbourmasterSite: Point | null
  /**
   * The harbour's working envelope, computed from the COVE AND THE SHORE ONLY —
   * never from the items inside it. A box fitted around the items would be a
   * dead sensor: it could not fail, because it is defined by what it checks.
   */
  extent: Rect
}

/** compose.py:1184-1187 — the dock kit, in the reference's own order. */
export const DOCK_KIT: readonly { kind: string; dx: number; dy: number }[] = [
  { kind: 'cargo_stacks', dx: -238, dy: 6 },
  { kind: 'cargo_barrels', dx: -60, dy: 12 },
  { kind: 'crate_single', dx: -186, dy: 34 },
  { kind: 'rope_coil', dx: 30, dy: 30 },
  { kind: 'crab_pots', dx: 152, dy: 16 },
  { kind: 'fish_barrel', dx: 214, dy: 26 },
  { kind: 'fishing_net', dx: -292, dy: 40 },
  { kind: 'fish_drying_rack', dx: 250, dy: -12 },
  { kind: 'anchor', dx: 96, dy: 40 },
  { kind: 'barrel_single', dx: -108, dy: 40 },
]

/** compose.py:1166,1172 — the quayside buildings' columns, either side of the cove. */
export const WAREHOUSE_DX = -330
export const WAREHOUSE_STRIDE = { x: 118, y: -14 }
export const HARBOURMASTER_DX = 300

// ── where the org's vessel ties up ─────────────────────────────────────────
//
// compose.py:1156-1157 moors it at a FIXED offset from the pier head
// (`JETTY_END + (-132, -6)`), which is an authored spot on the reference's own
// island and nothing more. Ported literally it beached the boat, so the offset
// is replaced by a berth SEARCH: the stations below are tried in order and the
// first one that is genuinely in open water wins.

/** Fractions along the pier's run where the vessel is offered a berth. */
export const BERTH_STATIONS: readonly number[] = [0.66, 0.82, 0.5, 0.94, 0.34]
/** Which side of the pier, west first — the side the reference moored on. */
export const BERTH_SIDES: readonly number[] = [-1, 1]
/** Daylight between the hull's contact patch and the pier's planks. */
export const BERTH_GAP = 10
/**
 * With no pier to tie to, the vessel lies at anchor these distances below its
 * column's waterline. They are absolute because there is no pier length to
 * scale off — the shortest is already clear of the deepest wharf in the ladder
 * (54px + fascia) and of the shore band the landing dresses.
 */
export const ANCHOR_DEPTHS: readonly number[] = [96, 132, 168]

/** Cranes need working room between them; below this they are one heap. */
export const CRANE_SPACING = 150
/** compose.py:1182 — the crane stands 42px out from the waterline, on the deck. */
export const CRANE_DEPTH = 42

/** How far past the shore box the harbour's working envelope reaches. */
const HARBOUR_MARGIN = 60

export interface HarbourInputs {
  era: Era
  /** The `quay` ladder's rung. */
  quay?: string | null
  /** `berths` — open outcome windows. */
  berths?: number
  /** `cargo_stacks` — completed work items, as a tier count. */
  cargo?: number
  /** `warehouse` — outcomes achieved. */
  warehouses?: number
  /** `harbormaster_hut` — a flag ladder: is the hut built? */
  harbourmaster?: boolean
  /** `packs_inherited` — extension packs present; one crane each. */
  packs?: number
  /** `harbor_boat` — is the org's own vessel a thing yet? */
  boat?: boolean
  /** The drawn size of a sprite kind, from the shipped pack. */
  sizeOf: (kind: string) => Footprint
}

const count = (v: number | undefined, hi: number) =>
  v === undefined || !Number.isFinite(v) ? 0 : clamp(Math.trunc(v), 0, hi)

/**
 * The whole harbour for one state, or null when this island has no cove shore
 * to build on at all (a seed whose cove ate the south of the island). Null is
 * the honest answer there: the alternative is a wharf hanging in open sea,
 * which is the exact defect compose.py:1119 names.
 */
export function buildHarbour(
  coast: Coastline,
  cove: Cove,
  input: HarbourInputs
): Harbour | null {
  const shore = shoreLine(coast, cove)
  // compose.py:1139 requires more than three columns before it decks anything;
  // below that there is no waterline to follow, only isolated pixels.
  if (shore.length <= 3) return null

  const depth = quayDepth(input.era, input.quay)
  const span = QUAY_SPAN[input.quay ?? 'rowboat_jetty'] ?? 1

  // ---- the wharf ---------------------------------------------------------
  let wharf: Wharf | null = null
  if (depth > 0) {
    const lo = Math.trunc(shore.length * (0.5 - span / 2))
    const hi = Math.trunc(shore.length * (0.5 + span / 2))
    const kept = span >= 1 ? shore : shore.slice(lo, hi)
    if (kept.length > 1) {
      const xs = kept.map((p) => p.x)
      const ys = kept.map((p) => p.y)
      wharf = {
        shore: kept,
        depth,
        rect: [
          Math.min(...xs),
          Math.min(...ys) - 20,
          Math.max(...xs),
          Math.max(...ys) + depth + 60,
        ],
      }
    }
  }

  // ---- the finger jetty --------------------------------------------------
  // compose.py:1145-1148, WITHOUT the reference's +52 root offset. The root's y
  // comes from the waterline in the jetty's OWN column, not from the wharf's —
  // the two are 104px apart and the cove shore falls away between them — and it
  // sits on the LAND side of that waterline, by the same SHORE_LIFT the deck's
  // upper edge uses. A pier is a thing you can walk onto.
  //
  // The reference's `js + 52` put the root 52px out on the water. On the offline
  // island a stone wharf covered the gap; at a rung or an era that decks nothing
  // it is the v12 defect verbatim — a pier with a strip of sea between it and
  // the beach — and that is what the Captain saw in the first rendered frame
  // from this module. Restoring the offset here is mutation MH28; MH30 is the
  // on-land refusal below, which is the sensor rather than the null check.
  const jx = cove.x + 104
  const jShore = shoreAt(coast, cove, jx)
  const jLen = jettyLength(input.quay)
  const jRoot: Point | null = jShore === null ? null : { x: jx, y: jShore - SHORE_LIFT }
  /**
   * The waterline the harbour's FLOATING furniture is measured from: the jetty
   * column's own where that column has land, and the nearest measured shore
   * otherwise. The moorings and the org's vessel are counts and facts about the
   * org, so they may not be deleted by a geometric accident in one column — but
   * neither may they be hung off an invented y.
   */
  const waterBase = jShore ?? nearestShoreY(shore, jx)
  /**
   * The seaward mooring point — the pier's end, or the anchorage when there is
   * no pier. Computed here rather than on the Jetty so the things moored off it
   * do not vanish with it: a boat with no pier lies at anchor in the cove, which
   * is what a length of 0 puts it at.
   */
  const jEnd: Point = {
    x: jx + Math.sin(JETTY_ANGLE) * jLen,
    y: waterBase - SHORE_LIFT + Math.cos(JETTY_ANGLE) * jLen * 0.86,
  }
  /**
   * NO SHORE, NO PIER. A column with no land in the cove window cannot root one,
   * and the honest output there is nothing at all: a missing pier says the
   * harbour has none, while a floating pier says something false about the org
   * AND about the island. `landAt` is asked rather than assumed because the root
   * is the one anchor here that is emitted as drawn geometry — shoreAt's
   * contract makes it land, and a rule this module states is a rule this module
   * checks.
   */
  const jetty: Jetty | null =
    jLen > 0 && jRoot !== null && coast.landAt(jRoot.x, jRoot.y)
      ? {
          at: jRoot,
          length: jLen,
          width: jLen < 200 ? 44 : 58,
          angle: JETTY_ANGLE,
          end: jEnd,
        }
      : null

  /** Every plank this harbour has laid — what a floating thing must clear. */
  const timber: HarbourTimber = { wharf, jetty }

  const berths = count(input.berths, 64)

  // ---- the working envelope ---------------------------------------------
  //
  // COMPUTED BEFORE THE THINGS IT CONTAINS, since 2026-07-27, because the
  // vessel now has to be placed INSIDE it: a berth search that could not ask
  // the envelope would moor the boat somewhere auditLayout's outsideHarbour arm
  // then reported. Nothing here reads an emitted position, so moving it up
  // changes no value — it only makes the "derived from inputs, never from the
  // items" rule mechanical rather than a promise.
  //
  // THE DEEPEST THING IN A HARBOUR IS NOT ALWAYS THE PIER. The reach was the
  // jetty's alone until 2026-07-27, and the mooring rows walk 52px further out
  // per PAIR of open outcome windows, so a well-used harbour out-reaches its own
  // finger pier: measured over 20 seeds at the top quay rung, `berths: 16` put 6
  // mooring posts outside the envelope the harbour declares for itself and
  // `berths: 24` put 150 — auditLayout's outsideHarbour arm reporting a defect
  // that was the ENVELOPE's, not the moorings'. It went unseen because every
  // fixture in the suite stopped at 6 berths, which is the value the state
  // happened to carry; `count()` admits up to 64.
  //
  // EVERY TERM IS COMPUTED FROM INPUTS — the quay rung, the berth count, the
  // kit table, whether the org has a vessel — and not from the emitted
  // positions. That distinction is the whole point of the envelope: a box
  // fitted around the items it contains is a sensor that cannot fail, while a
  // box derived from the inputs still catches a row indexed off the wrong base
  // or a kit computed from the wrong origin.
  const xs = shore.map((p) => p.x)
  const ys = shore.map((p) => p.y)
  // The pier now leaves the shore ON the shore line rather than 52px out on the
  // water, so its reach below the shore box is its run and nothing more. The
  // constant that used to lead this term was the root offset; it went with it.
  const pierReach = jLen * 0.86
  // The mooring row's own depth below the shore box, in the same terms: the
  // last row sits 116 + floor((berths-1)/2)*52 below its column's waterline,
  // that column can be the lowest in the box (+4 for SHORE_LIFT), and the box
  // already adds `depth` below the shore before `reach` is applied.
  const mooringReach =
    berths > 0 ? Math.max(0, 120 + Math.floor((berths - 1) / 2) * 52 - depth) : 0
  // The dock kit's own depth, which the old pier constant was quietly covering:
  // its deepest member sits 14+dy below its column's waterline, and that column
  // is not one of the sampled ones, so the shore box alone does not contain it.
  // Read off the KIT TABLE, never off the emitted items — same rule as above.
  const kitReach = Math.max(0, 14 + Math.max(...DOCK_KIT.map((k) => k.dy)) + SHORE_LIFT - depth)
  // A vessel with no pier lies at anchor, which is the one berth that reaches
  // past everything above. Only claimed when there is no pier, because that is
  // the only case the anchorage is used — an envelope widened for a berth the
  // harbour cannot take is a looser bound for no reason.
  const anchorReach =
    input.boat && jetty === null
      ? Math.max(0, ANCHOR_DEPTHS[ANCHOR_DEPTHS.length - 1] + SHORE_LIFT - depth)
      : 0
  const reach = Math.max(pierReach, mooringReach, kitReach, anchorReach)
  const extent: Rect = [
    Math.min(...xs) - HARBOUR_MARGIN,
    Math.min(...ys) - HARBOUR_MARGIN,
    Math.max(...xs) + HARBOUR_MARGIN,
    Math.max(...ys) + depth + reach + HARBOUR_MARGIN,
  ]

  // ---- the moorings: ONE PER OPEN OUTCOME WINDOW -------------------------
  // compose.py:1149-1152. A real count, in two rows either side of the pier.
  // Not era-gated: "there are no moorings without open outcome windows" is a
  // statement about the count, and a camp with an open window has a mooring.
  //
  // EACH POST RESOLVES ITS OWN COLUMN'S WATERLINE, which is the law the rest of
  // this module already follows and the mooring rows were the last thing here
  // to break. They were laid off the JETTY column's waterline for both rows,
  // 152px apart, across a cove shore that falls away by up to 250px over that
  // span — so the east row was measured against the wrong sea. Measured over 80
  // seeds x 4 eras x 5 quay rungs before the fix: 111 of 6400 posts drawn
  // standing on the wharf deck, and the audit's new float arm found posts on
  // the BEACH as well. A post may never be dropped for it (it is a count), and
  // it no longer has to be: 116px below its own waterline is open water by the
  // same argument the deck's own edge is, since the deepest wharf in the ladder
  // reaches 54 + fascia below that line. The envelope above already contains
  // the deepest row this can produce (see mooringReach).
  const mooringSize = input.sizeOf('mooring_post')
  const moorings: Point[] = []
  for (let b = 0; b < berths; b++) {
    const x = jx - 66 + (b % 2) * 152
    const s = shoreAt(coast, cove, x) ?? nearestShoreY(shore, x)
    moorings.push({ x, y: s + 116 + Math.floor(b / 2) * 52 })
  }

  // ---- cargo and working clutter ----------------------------------------
  // compose.py:1188 reads `max(1, min(len, 1 + cargo*3))`, so it lays a crate on
  // the wharf of an org that has completed NOTHING. That is a sprite with no
  // rule behind it — check_state_traceable's whole subject — so this port drops
  // the `1 +` and the `max(1, ...)`: no completed work, no cargo. The kit's
  // fishing gear scales with the same number for the reference's own reason,
  // that a working dock is dressed in proportion to how much passes over it.
  const cargo = count(input.cargo, 999)
  const kitN = clamp(cargo * 3, 0, DOCK_KIT.length)
  const items: HarbourItem[] = []
  for (let i = 0; i < kitN; i++) {
    const kit = DOCK_KIT[i]
    const x = cove.x + kit.dx
    const s = shoreAt(coast, cove, x)
    if (s === null) continue
    const at = { x, y: s + 14 + kit.dy }
    items.push({
      kind: kit.kind,
      at,
      flip: false,
      size: input.sizeOf(kit.kind),
      overWater: !coast.landAt(at.x, at.y),
      // THE KIT IS CARGO AND WORKING GEAR: crates, barrels, nets and crab pots
      // stand ON the planks, which is what a working dock looks like. Marking
      // them afloat would either delete them from the deck or force the float
      // arm to grow an exemption, and an exemption is how a beached boat gets
      // waved through next time.
      afloat: false,
    })
  }

  // ---- the org's own vessel, moored ALONGSIDE the pier --------------------
  // compose.py:1156-1157. This is the ONE craft with a ladder behind it
  // (`harbor_boat`, outcomes achieved), and it is the only one ported.
  //
  // The reference also draws a fishing boat, a rowboat, two buoys and two
  // ducks. Every one of those is a sprite with no rule over `state` behind it,
  // which is exactly what check_state_traceable is for — so they belong to the
  // renderer's ambient set (era-permitted dressing) if anywhere, not to a stage
  // that claims everything it emits is measured.
  //
  // THE OFFSET WAS A CLAIM, NOT A PLACEMENT. `JETTY_END + (-132, -6)` is an
  // authored spot on the reference's own island; ported here it carried
  // `overWater: true` as a hard-coded declaration and nothing measured it. It
  // put the hull on the wharf on 2 of 1600 (seed x era x rung) and it could
  // never have done better than luck, because a fixed offset from a pier whose
  // length is a state reading cannot know where the water is. It is now a berth
  // SEARCH against `inOpenWater` — the same predicate auditLayout re-measures —
  // and a seed with no open water beside its pier gets NO VESSEL, which is the
  // rule the jetty root already follows: a missing boat says the harbour could
  // not berth one, a beached boat says something false about the island.
  if (input.boat) {
    const boatSize = input.sizeOf('harbor_boat')
    const beam = Math.max(4, groundDiamond(boatSize.w, boatSize.h).hw)
    const berths: Point[] = []
    if (jetty) {
      // Beam-on to the planks, bow up-shore: near the head first, because that
      // is where a working boat ties up and where the water is deepest.
      const off = jetty.width / 2 + beam + BERTH_GAP
      for (const f of BERTH_STATIONS) {
        const px = jetty.at.x + Math.sin(jetty.angle) * jetty.length * f
        const py = jetty.at.y + Math.cos(jetty.angle) * jetty.length * f * 0.86
        for (const side of BERTH_SIDES) berths.push({ x: px + side * off, y: py })
      }
    }
    // At anchor when there is no pier to lie against — the jetty is null on an
    // unmeasured quay ladder and on a column with no land to root in, and a
    // boat is a fact about the org either way.
    for (const d of ANCHOR_DEPTHS) {
      for (const side of BERTH_SIDES) berths.push({ x: jx + side * (beam + 24), y: waterBase + d })
    }
    const berth = berths.find(
      (p) => rectContains(extent, p) && inOpenWater(coast, timber, p, boatSize)
    )
    if (berth) {
      items.push({
        kind: 'harbor_boat',
        at: berth,
        flip: false,
        size: boatSize,
        // MEASURED like every other item here, not asserted. inOpenWater has
        // already proved the whole contact patch is off the land, so this reads
        // true — which is the point: the flag now reports a measurement instead
        // of repeating the emitter's intention.
        overWater: !coast.landAt(berth.x, berth.y),
        afloat: true,
      })
    }
  }

  // ---- the cranes: one per inherited extension pack ----------------------
  // compose.py:1180-1182 says "one dockside crane per inherited extension pack"
  // and then places exactly one, unconditionally. The comment is the rule and
  // the code is the bug: packs_inherited is a census count (morphology.yml:178,
  // "Harbor cranes — extension packs present"), and a count that renders as 1
  // whatever it says is era-hiding-a-count by another route.
  //
  // They are spread across the deck rather than stacked on one spot, and the
  // number that does not fit is REPORTED (cranesRequested) rather than lost —
  // a silently truncated count is the same defect one level down.
  const cranesRequested = count(input.packs, 999)
  const cranes: Point[] = []
  if (wharf && input.era !== 'camp' && cranesRequested > 0) {
    const x0 = wharf.rect[0]
    const x1 = wharf.rect[2]
    const capacity = Math.max(0, Math.floor((x1 - x0) / CRANE_SPACING))
    const n = Math.min(cranesRequested, capacity)
    for (let i = 0; i < n; i++) {
      const x = x0 + ((x1 - x0) * (i + 0.5)) / n
      const s = shoreAt(coast, cove, x)
      if (s === null) continue
      cranes.push({ x, y: s + CRANE_DEPTH })
    }
  }

  // ---- quayside buildings, on LAND above the wharf -----------------------
  // compose.py:1165-1176. These are ANCHORS: the caller runs them through the
  // structure rules, which walk them inland and drop them when there is no
  // ground — so this module never decides that a building stands in the sea.
  const warehouses = count(input.warehouses, 16)
  const warehouseSites: Point[] = []
  const whX = cove.x + WAREHOUSE_DX
  const whS = shoreAt(coast, cove, whX) ?? nearestShoreY(shore, whX)
  for (let i = 0; i < warehouses; i++) {
    warehouseSites.push({
      x: whX + i * WAREHOUSE_STRIDE.x,
      y: whS - 6 + i * WAREHOUSE_STRIDE.y,
    })
  }
  const hmX = cove.x + HARBOURMASTER_DX
  const hmS = shoreAt(coast, cove, hmX) ?? nearestShoreY(shore, hmX)
  const harbourmasterSite = input.harbourmaster ? { x: hmX, y: hmS - 8 } : null

  return {
    cove,
    shore,
    wharf,
    jetty,
    moorings,
    mooringSize,
    items,
    cranes,
    cranesRequested,
    warehouseSites,
    harbourmasterSite,
    extent,
  }
}

// ── the lighthouse ─────────────────────────────────────────────────────────

/**
 * compose.py:905 — the forest ring is kept off the tower so it is not swallowed.
 * The reference reserves 200 flat; this port shrinks the clearing when the rung
 * has built no tower, because a 200px bald ring around a knee-high cairn is a
 * mown circle around nothing — the same argument that era-gates the district
 * discs in index.ts.
 */
export const LIGHTHOUSE_CLEARING = 200
export const CAIRN_CLEARING = 90

/**
 * compose.py:891-897 — the island's most seaward south-east point, found by
 * WALKING THE COAST rather than by a hardcoded angle.
 *
 * It scans every column east of the cove, takes that column's waterline, and
 * keeps the one maximising x + y: furthest east AND furthest south, which on a
 * south-east-facing shore is the point that reaches furthest into open water.
 * A hardcoded bearing cannot do this — the coastline is a function of the org
 * seed, so the compass direction of "the point" moves island to island, and an
 * authored angle would put the tower inland on half of them.
 *
 * Returns null when no column east of the cove has any land: an island that
 * does not reach that far has no south-east point, and inventing one would put
 * the keystone structure in the sea.
 *
 * `cove` may be null (an island built with no harbour bite). The cove is only a
 * SEARCH ORIGIN here — it says where the south-east shore starts and how far up
 * the column to look — so without one the search starts at the island centre and
 * sweeps the southern half. The lighthouse is the keystone and is drawn at every
 * era, so it may not be deleted merely because this island has no harbour.
 */
export function lighthouseSite(
  coast: Coastline,
  space: LayoutSpace,
  cove: Cove | null
): Point | null {
  const fromX = (cove ? cove.x : space.cx) + 380
  const yTop = cove ? cove.y - cove.r * 1.5 : space.cy
  let best: { score: number; x: number; y: number } | null = null
  for (let x = fromX; x < space.w - 60; x += 6) {
    const sy = coast.shoreY(x, yTop, space.h - 40)
    if (sy === null) continue
    const score = x + sy
    if (!best || score > best.score) best = { score, x, y: sy }
  }
  // compose.py:897 lifts the tower 18px off the waterline row so it stands on
  // the point rather than in the surf.
  return best ? { x: best.x, y: best.y - 18 } : null
}

/**
 * THE LAMP — "the biggest visual event in the world's life" (morphology.yml:189,
 * cells_graduated: "the beam lighting is the biggest visual event of the world's
 * life"). The tower grows as trust cells accumulate; the lamp stays dark until
 * the first cell GRADUATES.
 *
 * `rungLit` is what state says and `lit` is what is drawn, and they are kept as
 * two fields on purpose. They differ in exactly one case: a lit rung over a
 * lighthouse that is still a dark cairn, which the reference would draw as a
 * lamp floating above a pile of stones (compose.py:1203 gates only on the
 * sprite existing, and the cairn is a sprite). A LAMP NEEDS A TOWER TO SIT IN.
 * Reporting both is what keeps that from being a hidden measurement: the count
 * survives in `rungLit` even on the frame that cannot draw it.
 */
export interface LighthouseLamp {
  /** What the `lighthouse_lamp` rung says. */
  rungLit: boolean
  /** Drawn lit: rungLit AND there is a tower to hold the lamp. */
  lit: boolean
  /** compose.py:1205 LAMP_AT — where the renderer puts the glow. */
  at: Point | null
}

export interface Lighthouse {
  /** Base centre of the tower, after the structure rules placed it. */
  at: Point
  size: Footprint
  /** The forest-ring keep-out around it. */
  clearing: number
  lamp: LighthouseLamp
  /** False = the rung has built no tower yet, so this is the unlit cairn. */
  tower: boolean
}

/**
 * compose.py:1203-1205 — the lamp sits 86% of the sprite's height above its
 * base, on the base's own column.
 */
export function lampPosition(at: Point, size: Footprint): Point {
  return { x: at.x, y: at.y - size.h * 0.86 }
}

/** Distance in the reference's squashed metric — exported for the tests' sake. */
export function harbourDistance(a: Point, b: Point): number {
  return hypot(a.x - b.x, a.y - b.y)
}
