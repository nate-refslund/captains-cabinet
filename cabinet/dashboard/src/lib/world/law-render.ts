/**
 * WHAT THE WORLD ACTUALLY DRAWS OF ITS OWN LAW — per kernel, per law row.
 *
 * THE DEFECT THIS FILE EXISTS FOR, measured in a browser on 2026-07-29 with
 * the iso default simulated locally: the Legend Law panel's gauge read
 * `codex coverage 100%` and the panel listed every ratified row in
 * `cabinet/world/morphology.yml`, while SEVEN of those rows had nothing on
 * screen at all. Four had lost their renderer with the legacy three-scene
 * shell earlier the same day; three had never had an isometric form.
 *
 * The gauge was not wrong about what it measures. It measures whether a
 * morphology entry carries a `codex:` block — DOCUMENTATION completeness — and
 * every entry does. It has no term for whether anything paints the row, so it
 * could not have gone amber when the renderers were deleted, and it will not go
 * amber the next time either. That is the failure class this programme keeps
 * paying for: the sensor is green because it is pointed at something other than
 * the control. A world that reports 100% coverage of law it cannot draw is
 * making a claim on the reader's behalf that nobody measured.
 *
 * So this module is the SECOND term. Every ratified morphology id is classified
 * here exactly once, as either
 *
 *   - `renders`  — the surfaces that paint it, per kernel; or
 *   - `unrendered` — with the reason, in the open.
 *
 * and the Legend shows BOTH numbers, with the unrendered rows named. An honest
 * amber gauge is worth more than a green one that means nothing.
 *
 * WHAT MAKES THIS DIFFERENT FROM A HAND-KEPT LIST (which is the same defect one
 * level up). `law-render.test.ts` gives it three sets of teeth, all against
 * LIVE artifacts rather than against this file's own opinion:
 *
 *   1. SET EQUALITY with `cabinet/world/morphology.yml`. Ratifying a new law
 *      row fails the suite until it is classified here; deleting one fails
 *      until the row goes. Neither direction can drift quietly.
 *   2. EVERY NAMED LAYOUT SURFACE MUST APPEAR IN A COMPOSED LAYOUT. The test
 *      runs the real `composeLayout` and collects what it actually placed —
 *      structure roles, dressing kinds, harbour item kinds, scatter, ring, the
 *      emitted regions, the lighthouse tower and lamp. Claiming a surface the
 *      layout does not place is red. This is what turns "the renderer was
 *      deleted" from a silent 100% into a failing test.
 *   3. EVERY NAMED CODE SURFACE MUST RESOLVE to a symbol that exists. A card,
 *      a room fixture or a HUD chip is named by its module and export, and the
 *      test imports it.
 *
 * PROJECTION IS PART OF THE ANSWER, which is why this lives in TypeScript next
 * to the renderers rather than in `world-legend.py`. `street_hq_floors` was
 * drawn by the top-down street and is drawn by nothing now; `harbor_boat_voyage`
 * is drawn by the top-down dynamics layer and has no isometric form yet. A
 * coverage number that could not say "under which kernel" would have to pick
 * one and be wrong about the other.
 *
 * PURE: no DOM, no clock, no RNG. It is data plus two selectors.
 */
import type { ProjectionKind } from './projection'

/**
 * Where a law row is painted.
 *
 * `layout` surfaces are produced by `composeLayout` and are checked against a
 * real composition. `code` surfaces are everything the layout does not emit —
 * a card, an interior fixture, a HUD chip — named as `module#export` so the
 * test can resolve them.
 */
export type LawSurface =
  | { readonly at: 'structure'; readonly object: string }
  | { readonly at: 'dressing'; readonly object: string }
  | { readonly at: 'harbour'; readonly object: string }
  | { readonly at: 'region'; readonly object: 'fields' | 'plaza' | 'quay' | 'moorings' }
  | { readonly at: 'coast' }
  | { readonly at: 'lighthouse'; readonly object: 'tower' | 'lamp' }
  /** The composition itself changes with era / rung state (vocabulary law). */
  | { readonly at: 'composition' }
  | { readonly at: 'code'; readonly module: string; readonly symbol: string }

/** Which kernels paint a row. */
export type LawKernels = 'both' | 'iso' | 'topdown'

export interface LawRendered {
  readonly rendered: true
  readonly kernels: LawKernels
  readonly surfaces: readonly LawSurface[]
  /** Why these surfaces ARE this law — the traceability the codex asks for. */
  readonly note: string
}

export interface LawUnrendered {
  readonly rendered: false
  /** Plain, checkable reason. Never "TODO" — say what is missing. */
  readonly reason: string
}

export type LawBinding = LawRendered | LawUnrendered

/**
 * THE MAP. One row per ratified morphology id, in `morphology.yml` order so a
 * reviewer can read the two files side by side.
 */
export const LAW_RENDER: ReadonlyMap<string, LawBinding> = new Map<string, LawBinding>([
  // ── v1: the org-global growth surfaces ────────────────────────────────────
  [
    'memory_store',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'structure', object: 'library' }],
      note: 'memory_rows_total drives the library ladder; the library building is placed at its rung.',
    },
  ],
  [
    'evolved_skills',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'structure', object: 'workshop' }],
      note: 'evolved_skills drives the workshop ladder; the workshop is placed at its rung.',
    },
  ],
  [
    'consequence_ledger',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'dressing', object: 'consequence_ledger' }],
      note: 'ledger lines render as the ledger stone in the civic dressing.',
    },
  ],
  [
    'commits',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [
        { at: 'structure', object: 'outbuildings' },
        { at: 'region', object: 'quay' },
      ],
      note: 'commits_since_genesis drives both the outbuildings ladder and the quay deck.',
    },
  ],
  [
    'captain_rules',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [
        { at: 'dressing', object: 'law_plot' },
        { at: 'dressing', object: 'law_post' },
      ],
      note: 'ratified rules render as the law plot and its posts.',
    },
  ],
  [
    'work_completed',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'harbour', object: 'cargo_stacks' }],
      note: 'ev_work_item_completed drives the cargo_stacks ladder, stacked on the wharf.',
    },
  ],
  [
    'subagents_lifetime',
    {
      rendered: false,
      reason:
        'no ladder binds it and no surface paints it in either kernel — the count reaches the ' +
        'census and the codex, and stops there. Rendering it needs a ratified surface first.',
    },
  ],
  [
    'tier2_reflections',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'dressing', object: 'journal_desk' }],
      note: 'tier2_note_files drives the journal_desk ladder; the desk is placed in the civic dressing.',
    },
  ],
  [
    'golden_evals_delta',
    {
      rendered: false,
      reason:
        'no ladder binds golden_evals_delta_vs_seed and no surface paints it in either kernel; ' +
        'it is census + codex only.',
    },
  ],
  [
    'packs_inherited',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'harbour', object: 'crate_single' }],
      note: 'packs_dirs render as dock crates on the wharf (the Z0 face of island_harbor_crates).',
    },
  ],
  [
    'cells_graduated',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [
        { at: 'lighthouse', object: 'lamp' },
        { at: 'dressing', object: 'lamp_lantern' },
      ],
      note: 'graduated cells light the beacon lamp and the lit lantern posts; zero renders dark.',
    },
  ],
  [
    'hats_earned',
    {
      rendered: false,
      reason:
        'scope is DARK by ratification — per-officer census does not exist, so there is nothing ' +
        'measured to draw. Not a gap in the renderer; a gap in the measurement, declared.',
    },
  ],
  [
    'org_posture',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'dressing', object: 'flagpole' }],
      note: 'the posture enum flies on the flagpole — display, never a control (forge-vector doctrine).',
    },
  ],

  // ── v2: street (Z1) + island (Z0) + wardroom growth surfaces ──────────────
  [
    'street_hq_floors',
    {
      rendered: false,
      reason:
        'its only renderer was the top-down Z1 street scene, deleted with the legacy shell on ' +
        '2026-07-29. The island draws commits as outbuildings and the quay (see `commits`); the ' +
        'stacked-floor HQ facade has no isometric form.',
    },
  ],
  [
    'island_land_radius',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'coast' }],
      note: 'org_events_total folds the shoreline radius; the coastline IS this law.',
    },
  ],
  [
    'island_officer_houses',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [
        { at: 'structure', object: 'officer_dwelling' },
        { at: 'structure', object: 'harbormaster_hut' },
      ],
      note: 'ev_role_defined mints one cottage per role at its birth-order slot.',
    },
  ],
  [
    'island_fields',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'region', object: 'fields' }],
      note: 'ratified outcomes set the plot count; the tilled plots are emitted regions.',
    },
  ],
  [
    'island_harbor_beacon',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [
        { at: 'lighthouse', object: 'tower' },
        { at: 'lighthouse', object: 'lamp' },
      ],
      note: 'the banded tower stands from day zero with an UNLIT lamp; graduation lights it.',
    },
  ],
  [
    'island_harbor_crates',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'harbour', object: 'crate_single' }],
      note: 'one crate on the wharf per pack directory.',
    },
  ],
  [
    'island_services_mill_row',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [
        { at: 'dressing', object: 'watermill_kiln' },
        { at: 'dressing', object: 'windmill' },
        { at: 'dressing', object: 'composter' },
        { at: 'dressing', object: 'pens' },
      ],
      note: 'service rows render as the Works-ridge mill/kiln row; disabled rows render stopped.',
    },
  ],
  [
    'wardroom_bookshelf_fill',
    {
      rendered: false,
      reason:
        'its renderer was the top-down Wardroom bookshelf, deleted with the legacy shell on ' +
        '2026-07-29. `tier2_note_files` still paints the island journal_desk (see ' +
        '`tier2_reflections`), but the SHELF-BY-SHELF fill it names has no isometric surface: ' +
        'the roof-off room places desks and officers only, and tier2_note_files is not on the ' +
        '/api/world/engine payload the client receives.',
    },
  ],
  [
    'wardroom_noticeboard_pins',
    {
      rendered: false,
      reason:
        'the noticeboard object IS placed in the island dressing, but its PINS are the law and ' +
        'nothing binds them: `events_today` is not on the /api/world/engine payload, so the ' +
        'board is drawn bare. Bare is the honest render of an unmeasured count — this row says ' +
        'so rather than claiming the board covers the law.',
    },
  ],
  [
    'street_liveliness',
    {
      rendered: false,
      reason:
        'its only renderer was the top-down street set-dressing unlock band, deleted with the ' +
        'legacy shell on 2026-07-29. The island dresses itself by ERA, not by org age, so no ' +
        'isometric surface reads the first-keyframe date.',
    },
  ],

  // ── v3: the living island ────────────────────────────────────────────────
  [
    'era_vocabulary',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'composition' }],
      note: 'era selects the sprite vocabulary for every rung — the composition itself is the render.',
    },
  ],
  [
    'ladder_rungs',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'composition' }],
      note: 'rungs decide what is built and how far along; the composition differs by state.',
    },
  ],
  [
    'lighthouse_staged',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [
        { at: 'lighthouse', object: 'tower' },
        { at: 'structure', object: 'lighthouse' },
      ],
      note: 'cells_accumulating stages the tower through its rungs, dual-view with the lamp.',
    },
  ],
  [
    'lane_reef_buoys',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'code', module: 'iso-lanes', symbol: 'isoLaneSites' }],
      note:
        'a lane with no ratified outcome — including an instance-test or retired one — renders ' +
        'as a reef buoy at its berth slot, and the buoy opens the lane card that quotes the ' +
        'why-string. Bound in BOTH kernels since 2026-07-29: the landing dressing still carries ' +
        'authored water furniture, which is decoration, but the LAW is read off buildWorldGeo ' +
        'laneSites and drawn by the iso dynamics layer.',
    },
  ],
  [
    'mailbox_pending',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [
        { at: 'dressing', object: 'mailbox' },
        { at: 'code', module: 'iso-scene', symbol: 'NO_STATE_KINDS' },
      ],
      note: 'pending_captain_items raises the mailbox flag; the crossroads mailbox is pickable in both kernels.',
    },
  ],
  [
    'manor_chart_table',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [
        { at: 'dressing', object: 'chart_table' },
        { at: 'code', module: 'course', symbol: 'buildChartTableCard' },
      ],
      note: 'the chart table stands in the dressing and opens the direction card in both kernels.',
    },
  ],
  [
    'harbor_port_calls',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'region', object: 'moorings' }],
      note: 'port calls berth at the moorings the harbour emits.',
    },
  ],
  [
    'lane_course_state',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'code', module: 'course', symbol: 'laneCourseState' }],
      note: 'per-lane course states are rows on the chart table card, reachable in both kernels.',
    },
  ],
  [
    'harbor_boat_voyage',
    {
      rendered: true,
      kernels: 'both',
      surfaces: [{ at: 'code', module: 'iso-lanes', symbol: 'isoVoyageBoat' }],
      note:
        'the boat is moored at the harbour mouth until a lane is TACKING, then sails the ' +
        'out-and-back fold to that lane berth — position is a pure fold of the newest port ' +
        'call (voyageRender), never a clock. Bound in BOTH kernels since 2026-07-29: the ' +
        'top-down path cuts the LimeZu rowboat, the iso path draws an owned hull on the ' +
        'ground plane with the sail set only under way, so the state is dual-coded by shape ' +
        'as well as by position. Its course DRIFT LINES are drawn in both kernels too, and ' +
        'the underlying state stays readable on the chart table card (lane_course_state).',
    },
  ],
])

export interface RenderCoverage {
  /** Rows painted under this kernel. */
  rendered: number
  /** Rows classified in total. */
  total: number
  /** 0..1, or null when nothing is classified (never silently 1). */
  fraction: number | null
  /** The rows this kernel does NOT paint, in declaration order. */
  unrendered: readonly string[]
}

/**
 * How much of the ratified law this kernel actually paints.
 *
 * A row bound to the other kernel counts as unrendered HERE, which is the whole
 * point: the number is per-kernel or it is a fiction.
 */
export function renderCoverage(projection: ProjectionKind): RenderCoverage {
  const unrendered: string[] = []
  let rendered = 0
  for (const [id, b] of LAW_RENDER) {
    const paints = b.rendered && (b.kernels === 'both' || b.kernels === projection)
    if (paints) rendered += 1
    else unrendered.push(id)
  }
  const total = LAW_RENDER.size
  return { rendered, total, fraction: total ? rendered / total : null, unrendered }
}

/** Why a row is not painted — the string the Legend shows next to its id. */
export function unrenderedReason(id: string, projection: ProjectionKind): string | null {
  const b = LAW_RENDER.get(id)
  if (!b) return null
  if (!b.rendered) return b.reason
  if (b.kernels === 'both' || b.kernels === projection) return null
  return `painted only by the ${b.kernels} kernel`
}
