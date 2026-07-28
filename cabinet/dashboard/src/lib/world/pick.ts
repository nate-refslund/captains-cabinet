/**
 * PICK — THE hit test. One function, both kernels, outside the PixiJS closure.
 *
 * WHY IT IS A FILE. Until 2026-07-28 the entire clickability of the world was a
 * 75-line closure inside `engine-canvas.tsx`'s boot `useEffect`, with no test
 * file and no PixiJS interaction graph behind it — `eventMode` and `hitArea`
 * appear zero times in the tree, because the canvas takes one DOM `click` and
 * does all the geometry itself. A closure cannot be driven by a test, so every
 * inspect card, every deep link, the mailbox, the chart table and the Library
 * entrance were guarded by nothing at all. The port's own premise check named
 * this the silent failure: under iso every tolerance in it is wrong and the
 * whole suite stays green while the world stops answering.
 *
 * WHAT IT PRESERVES, because all of it is product law:
 *   - the priority order: officers -> commute walkers (which resolve to their
 *     officer) -> LIFE sites -> mailbox -> chart table -> buildings -> lane
 *     sites -> ground;
 *   - the LOD gate that suppresses officers, walkers and sites below the tier
 *     that draws them — a click may not name what the frame does not show;
 *   - the `{kind:'ground'}` fallback, so there are NEVER dead clicks: an
 *     unmapped pixel says "carries no data" rather than nothing at all.
 *
 * The top-down arithmetic below is the shipped arithmetic, moved verbatim.
 * `pick.test.ts` pins each branch on hand-computed fixtures AND sweeps 4,000
 * seeded screen points against an oracle transcribed from the pre-move source,
 * which is what makes "top-down behaviour did not change" a measurement rather
 * than a claim.
 *
 * WHAT IT DOES NOT CONTAIN, and must not: the killswitch lever. The world's one
 * actuator is a DOM overlay at z-[60] with its own two-tap ceremony and a
 * server-verified session, and it has no world coordinate and no path through
 * this file. `PickKind` has no actuator member; pick.test.ts pins that the
 * returned kind is always one of the seven read-only ones and that no sweep of
 * the whole canvas, in either kernel, can produce anything else.
 *
 * PURE: no DOM, no clock, no RNG (determinism ratchet #4). The caller turns a
 * MouseEvent into a screen point and hands over state it already holds.
 */
import { fnv1a } from './hash'
import {
  elementForRole,
  PICKS_MEASURED,
  pickIsoSprite,
  type IsoScene,
  type IsoSprite,
} from './iso-scene'
import { LOD_RULES, lodTier, type EngineCamera } from './lod'
import { projectionFor, screenToWorld, type ProjectionKind, type ViewportPx } from './projection'
import { CHART_TABLE_LOCAL, roadPoint, toWorld, type WorldGeo } from './world-geo'
import type { LifeOut } from './life/life'
import type { WorldBuilding } from './world-buildings'

/**
 * Every kind of thing in the world a pointer can name. READ-ONLY, all seven.
 *
 * `ground` is a member rather than a null because the honesty contract has a
 * card for it ("ground / water — carries no data"), and a pick that returned
 * nothing would be indistinguishable from a pick that broke.
 */
export type PickKind =
  | 'officer'
  | 'building'
  | 'lane'
  | 'mailbox'
  | 'chart_table'
  | 'site'
  | 'ground'

export interface PickTarget {
  kind: PickKind
  id: string
}

const GROUND: PickTarget = { kind: 'ground', id: 'ground' }

/**
 * The two world objects that are their own card while no ladder entitles them.
 *
 * THE BUG THIS EXISTS FOR, measured on a composed hamlet scene 2026-07-28:
 * under iso BOTH WERE UNREACHABLE, and the code that looked like it handled
 * them could never run. `iso-layout/dressing.ts` emits the crossroads mailbox
 * and the chart table in the `village_life` class — entitled by an ERA rather
 * than by a ladder — which is not a pack resolve object, so `buildIsoScene`
 * gives them `role: null`. The pick then skipped every `role === null` sprite
 * BEFORE the frame was ever compared, and two branches reading
 * `s.frame === 'mailbox'` and `s.frame === 'chart_table'` sat in
 * engine-canvas.tsx as dead code with the suite green over them.
 *
 * So they are a THIRD class, not an exception inside the second: `role !== null`
 * means a ladder measured it, `STATIONS` means the world binds a card to it
 * anyway, and everything else is decoration the pointer passes straight through.
 * pick.test.ts asserts every frame named here exists in the SHIPPED pack and
 * appears in a composed scene, so a renamed or dropped frame goes red instead of
 * quietly returning the world to "carries no data".
 */
export const STATIONS: ReadonlyMap<string, PickTarget> = new Map<string, PickTarget>([
  ['mailbox', { kind: 'mailbox', id: 'mailbox' }],
  ['chart_table', { kind: 'chart_table', id: 'chart-table' }],
])

/** The world state a pick reads — exactly what the canvas already holds. */
export interface PickWorld {
  projection: ProjectionKind
  camera: EngineCamera
  /** Viewport in RENDERER px (the canvas converts once, at the DOM edge). */
  viewport: ViewportPx
  geo: WorldGeo
  buildings: WorldBuilding[]
  /** Officers present this frame — only the KEYS are read. */
  officers: Record<string, unknown>
  life: LifeOut | null
  /** Directions exist on this deployment — the chart table's own gate. */
  chartTable: boolean
  /**
   * The building whose roof is currently OFF (`CutawayState.openId`), or null.
   *
   * IT IS A PICK INPUT BECAUSE IT MOVES THE OFFICERS. `officerSlots` places
   * them in the yard when the great house is shut and at desks INSIDE it when
   * the roof is off, and the canvas draws from that same call — so a pick that
   * cannot see this state tests the wrong six squares whenever the cutaway is
   * open, which at close zoom over the great house is exactly when a person is
   * clicking an officer. Measured 2026-07-28: with the roof off, a click on a
   * drawn officer returned `building:great_house` and a click on empty yard
   * returned an officer who was not there.
   */
  cutawayOpenId: string | null
  /**
   * The composed iso scene, or null. Null is the honest state when the pack
   * failed to load: the canvas draws ground and no sprites, and the pick must
   * answer the world it drew rather than one it imagines.
   */
  scene: Pick<IsoScene, 'sprites'> | null
}

/**
 * Where the officers stand — ONE definition, shared with the label layer.
 *
 * It was two, a copy-paste apart: `engine-canvas.tsx` `officerPositions` placed
 * the drawn sprite and `engine-client.tsx` `officerLabels` placed the DOM name
 * chip over it, each re-deriving the same seeded slot from the same hash.
 * Nothing held them equal, so one edit would have put the name beside the
 * officer and the click on neither. The port collapsed five copies of the
 * world->screen transform for exactly this reason; this is the sixth copy.
 *
 * NO GREAT HOUSE MEANS NO OFFICERS ANYWHERE, and that is the honest answer
 * rather than a gap: the yard IS the great house's, so a cabinet that has not
 * built one has nowhere for them to stand and the pick must not invent a spot.
 */
export function officerSlots(
  greatHouse: { x: number; y: number; w: number; h: number } | null | undefined,
  slugs: string[],
  open: boolean
): Array<{ slug: string; x: number; y: number; inside: boolean }> {
  const gh = greatHouse
  if (!gh) return []
  return slugs.map((slug, i) => {
    const h = fnv1a(`officer:${slug}`)
    if (open) {
      const col = i % 3
      const row = Math.floor(i / 3)
      return {
        slug,
        x: gh.x + 1 + col * ((gh.w - 2) / 2.5),
        y: gh.y + 1.6 + row * 1.6,
        inside: true,
      }
    }
    return {
      slug,
      x: gh.x + 0.5 + ((h >>> 4) % (gh.w * 2)) / 2,
      y: gh.y + gh.h + 1 + (i % 2),
      inside: false,
    }
  })
}

/**
 * Which sprites the iso pick may answer with, for THIS world.
 *
 * The chart table is gated on `chartTable` exactly as the top-down path gates
 * DRAWING it: with no directions on the deployment there is no card to open, so
 * the sprite becomes decoration the pointer passes through rather than a station
 * that answers with an empty chart. (Under iso the layout draws it either way —
 * a separate honesty gap, recorded in BACKLOG.md, not papered over here.)
 */
export function isoWants(chartTable: boolean): IsoWants {
  return (s) => {
    if (s.frame === 'chart_table') return chartTable
    return PICKS_MEASURED(s) || STATIONS.has(s.frame)
  }
}

type IsoWants = (s: IsoSprite) => boolean

/**
 * The iso pick: the scene's own sprites, front to back, on the shared solid.
 *
 * WHY IT CANNOT REUSE THE TOP-DOWN TESTS BELOW. Under iso a sprite's position is
 * a layout PIXEL, not a tile: `buildIsoSprites` does `sp.position.set(s.x, s.y)`
 * straight from composeLayout. `screenToWorld` returns TILES, because that is
 * what the camera and the top-down world speak — so the one conversion here is
 * `proj.project(tx, ty)`, the same kernel the camera projects with, run forward.
 * project() is linear, so project(tile) is the absolute layout px of that tile
 * and no camera term enters twice.
 *
 * Every tolerance below this function is a tile-space tolerance against TOP-DOWN
 * geometry — building bboxes, the crossroads mailbox, lane-site circles, the
 * road walk. Running them against an iso pointer would open the inspect card for
 * whatever top-down building happened to occupy that coordinate, which is a card
 * asserting something false about the org.
 *
 * A LADDER ROLE BECOMES A BUILDING ROW BY ITS `element`, never by its id: the
 * engine's building ids are its own, the ladder object is the name both sides
 * already agree on, so the card that opens is about the same measurement the
 * sprite drew. A measured role the building table has no row for is real but has
 * no card yet, and answers `ground` rather than opening a neighbour's.
 *
 * THROUGH `elementForRole`, NOT `===`. The layout spells one role differently
 * from the ladder that entitles it (`officer_dwelling` vs `officer_dwellings`),
 * and iso-scene has carried the alias since it was written — for the PACK
 * lookup. A raw `===` here meant every officer dwelling a hamlet island draws
 * answered `ground`: four sprites, the most numerous card-bearing structure
 * after the anchors, silently un-clickable while the suite stayed green.
 * Measured 2026-07-28 on a composed hamlet scene, base/mid/upper: 0/4 at every
 * height. This is the same table iso-scene resolves the pack with — never a
 * second copy, and never a fuzzy singular/plural match.
 */
function pickIso(world: PickWorld, tx: number, ty: number): PickTarget {
  const scene = world.scene
  if (!scene) return GROUND
  const px = projectionFor('iso').project(tx, ty)
  const s = pickIsoSprite(scene, px.x, px.y, { wants: isoWants(world.chartTable) })
  if (!s) return GROUND
  const station = STATIONS.get(s.frame)
  if (station) return station
  const element = elementForRole(s.role)
  const b = element === null ? undefined : world.buildings.find((bb) => bb.element === element)
  if (b) return { kind: 'building', id: b.id }
  return GROUND
}

/**
 * THE hit test.
 *
 * `screen` is in the same renderer px as `viewport`: the canvas subtracts its
 * bounding rect once, at the DOM edge, and nothing downstream touches a
 * MouseEvent.
 */
export function pickTarget(world: PickWorld, screen: { x: number; y: number }): PickTarget {
  const proj = projectionFor(world.projection)
  // THE one inverse — the same kernel the camera projects with, so a click can
  // never land where the eye did not.
  const w = screenToWorld(proj, screen.x, screen.y, world.camera, world.viewport)
  const wx = w.x
  const wy = w.y
  if (proj.kind === 'iso') return pickIso(world, wx, wy)

  const p = world
  // officers first (small, on top)
  if (LOD_RULES[lodTier(p.camera.z)].officers) {
    const gh = p.buildings.find((b) => b.element === 'great_house')
    // THE SAME CALL THE CANVAS DRAWS FROM, including the open/closed argument.
    // `false` here was the extraction's one behavioural change and it is the
    // whole point of collapsing the two copies: a pick that assumes the yard
    // while the renderer draws desks is two definitions again, wearing one name.
    for (const o of officerSlots(gh, Object.keys(p.officers).sort(), p.cutawayOpenId === gh?.id)) {
      if (Math.abs(wx - o.x) < 0.8 && Math.abs(wy - o.y + 0.3) < 1) {
        return { kind: 'officer', id: o.slug }
      }
    }
    // commute walkers inspect as their officer (the walk is presence animation
    // of a real verb shift — the card cites the mechanism)
    if (p.life) {
      for (const cm of p.life.commuters) {
        const t = cm.walk.to === 'quay' ? cm.progress : 1 - cm.progress
        const pos = roadPoint(t)
        if (Math.abs(wx - (pos.x + 0.5)) < 0.9 && Math.abs(wy - (pos.y + 1) + 0.5) < 1.2) {
          return { kind: 'officer', id: cm.slug }
        }
      }
      for (const st of p.life.sites) {
        const f = st.site.footprint
        if (wx >= f.x - 1 && wx <= f.x + f.w + 1 && wy >= f.y - 1 && wy <= f.y + f.h + 1) {
          return { kind: 'site', id: st.site.id }
        }
      }
    }
  }
  // the mailbox (crossroads)
  if (
    Math.abs(wx - (p.geo.crossroads.x + 1.2)) < 1.2 &&
    Math.abs(wy - p.geo.crossroads.y) < 1.6
  ) {
    return { kind: 'mailbox', id: 'mailbox' }
  }
  // the chart table (direction surface — read-only card, never an actuator;
  // the killswitch lever stays THE one actuator, D2)
  if (p.chartTable) {
    const ctw = toWorld(CHART_TABLE_LOCAL.x, CHART_TABLE_LOCAL.y)
    if (Math.abs(wx - (ctw.x + 0.5)) < 1.1 && Math.abs(wy - (ctw.y + 0.5)) < 1.2) {
      return { kind: 'chart_table', id: 'chart-table' }
    }
  }
  // buildings by bbox (footprints hit the same boxes at far LOD)
  for (const b of p.buildings) {
    if (wx >= b.x - 0.3 && wx <= b.x + b.w + 0.3 && wy >= b.y - 1 && wy <= b.y + b.h + 0.3) {
      return { kind: 'building', id: b.id }
    }
  }
  // lane sites (buoys / isles / mist)
  for (const site of p.geo.laneSites) {
    const r = site.render === 'isle' ? 12 : 4
    if (Math.hypot(wx - site.cx, wy - site.cy) <= r) {
      return { kind: 'lane', id: `lane:${site.slot}` }
    }
  }
  return GROUND
}
