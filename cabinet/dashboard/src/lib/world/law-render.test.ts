/**
 * THE TEETH FOR `law-render.ts`.
 *
 * A hand-kept map of "what draws what" is worth nothing on its own — it is the
 * same disabled sensor one level up, and this repo has found that shape ten
 * ways in two days. So every claim in that file is checked against a LIVE
 * artifact here:
 *
 *   - the id set against `cabinet/world/morphology.yml` on disk, both
 *     directions, so ratifying or retiring law fails until it is classified;
 *   - every layout surface against what `composeLayout` actually places;
 *   - every code surface against the real module export;
 *   - the `composition` surfaces against two states producing two islands;
 *   - and the coverage arithmetic itself, including the case that matters:
 *     a kernel that paints less must REPORT less.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'
import yaml from 'js-yaml'
import {
  LAW_RENDER,
  renderCoverage,
  unrenderedReason,
  type LawSurface,
} from './law-render'
import { composeLayout, type Layout, type LayoutState } from './iso-layout/index'
import { NO_STATE_KINDS } from './iso-scene'
import { isoLaneSites } from './iso-lanes'
import { buildChartTableCard, laneCourseState } from './course'

/** The repo root, from `cabinet/dashboard/src/lib/world`. */
const REPO = join(__dirname, '..', '..', '..', '..', '..')
const MORPHOLOGY = join(REPO, 'cabinet', 'world', 'morphology.yml')

/** A state with every ladder well up its rungs — the widest surface set. */
const MATURE: LayoutState = {
  era: 'beyond_bay',
  road: 'cobbled_road',
  stages: {
    great_house: 'great_hall', well: 'stone_well', library: 'stone_hall',
    workshop: 'forge', outbuildings: 'barn', firepit: 'firepit',
    lighthouse: 'lit_tower', warehouse: 'warehouse', harbor_boat: 'packet',
    harbormaster_hut: 'hut', observatory: 'observatory', quay: 'stone_quay',
    journal_desk: 'desk', noticeboard: 'board', flagpole: 'pole',
    law_plot: 'plot', veto_plinth: 'plinth', pens: 'pens',
    water_store: 'store', composter: 'composter', lantern_posts: 'posts',
    lighthouse_lamp: 'lit', berths: 'berths', cargo_stacks: 'stacks',
    field_plots: 'grown', lane_isles: 'isles', posts_lit: 'lit',
  },
  counts: {
    officer_dwellings: 6, field_plots: 4, great_house: 4, library: 4,
    workshop: 4, outbuildings: 3, well: 3, lighthouse: 3, warehouse: 2,
    harbor_boat: 2, harbormaster_hut: 1, observatory: 2, quay: 3,
    journal_desk: 2, noticeboard: 2, flagpole: 1, law_plot: 2,
    veto_plinth: 1, pens: 2, water_store: 2, composter: 2,
    lantern_posts: 4, lighthouse_lamp: 2, berths: 4, cargo_stacks: 5,
    lane_isles: 3, posts_lit: 3,
  },
}

const CAMP: LayoutState = { era: 'camp', road: 'dirt_path', stages: {}, counts: {} }

/**
 * Compose across several seeds and UNION what was placed.
 *
 * One seed is not the island: the harbour bites a different shore each time and
 * a droppable dressing item can lose its spot to a tree. The manifest's claim is
 * "the layout places this surface for this law", so the union over seeds is the
 * honest set to check it against — and a surface that no seed ever places is
 * genuinely unbound, which is exactly what should go red.
 */
const SEEDS = ['acme-corp', 'harbour', 'lantern', 'captains-cabinet', 'zeta']
const FAST = { fast: true } as never

const layouts: Layout[] = SEEDS.map((s) => composeLayout(MATURE, s, FAST))

function unionOf(pick: (l: Layout) => Iterable<string>): Set<string> {
  const out = new Set<string>()
  for (const l of layouts) for (const v of pick(l)) out.add(v)
  return out
}

const STRUCTURES = unionOf((l) => l.structures.map((s) => s.role))
const DRESSING = unionOf((l) => (l.dressing ?? []).map((d) => d.kind))
const HARBOUR = unionOf((l) => (l.harbour?.items ?? []).map((i) => i.kind))

/** Does the composed world contain this surface? One answer, live. */
function placed(s: LawSurface): boolean {
  switch (s.at) {
    case 'structure':
      return STRUCTURES.has(s.object)
    case 'dressing':
      return DRESSING.has(s.object)
    case 'harbour':
      return HARBOUR.has(s.object)
    case 'coast':
      return layouts.every((l) => !!l.coast && l.coast.land.length > 0)
    case 'lighthouse':
      return layouts.some((l) => !!l.lighthouse && !!l.lighthouse[s.object])
    case 'region':
      if (s.object === 'fields') return layouts.some((l) => l.regions.fields.length > 0)
      if (s.object === 'plaza') return layouts.some((l) => !!l.regions.plaza)
      if (s.object === 'quay') return layouts.some((l) => !!l.regions.quay)
      return layouts.some((l) => (l.harbour?.moorings ?? []).length > 0)
    case 'composition':
      return true // checked separately, behaviourally
    case 'code':
      return CODE_SURFACES.has(`${s.module}#${s.symbol}`)
  }
}

/**
 * The code surfaces, RESOLVED — imported at the top of this file so a deleted
 * or renamed export is a module-resolution failure rather than a string that
 * still matches itself.
 */
const CODE_SURFACES = new Map<string, unknown>([
  ['iso-scene#NO_STATE_KINDS', NO_STATE_KINDS],
  ['iso-lanes#isoLaneSites', isoLaneSites],
  ['course#buildChartTableCard', buildChartTableCard],
  ['course#laneCourseState', laneCourseState],
])

describe('law-render — the second coverage term', () => {
  it('classifies exactly the ratified morphology ids, both directions', () => {
    const doc = yaml.load(readFileSync(MORPHOLOGY, 'utf8')) as {
      entries?: { id?: string }[]
    }
    const ratified = (doc.entries ?? []).map((e) => e.id).filter((x): x is string => !!x)
    expect(ratified.length).toBeGreaterThan(20) // the file was read, not empty
    expect([...ratified].sort()).toEqual([...LAW_RENDER.keys()].sort())
  })

  it('every claimed layout surface is one the layout actually places', () => {
    const missing: string[] = []
    for (const [id, b] of LAW_RENDER) {
      if (!b.rendered) continue
      for (const s of b.surfaces) {
        if (!placed(s)) missing.push(`${id} -> ${JSON.stringify(s)}`)
      }
    }
    expect(missing).toEqual([])
  })

  it('the surface check can FAIL — a surface nothing places is not accepted', () => {
    expect(placed({ at: 'structure', object: 'cathedral' })).toBe(false)
    expect(placed({ at: 'dressing', object: 'street_lamp_row' })).toBe(false)
    expect(placed({ at: 'harbour', object: 'submarine' })).toBe(false)
    expect(placed({ at: 'code', module: 'gone', symbol: 'alsoGone' })).toBe(false)
  })

  it('every code surface resolves to a live export', () => {
    for (const [, b] of LAW_RENDER) {
      if (!b.rendered) continue
      for (const s of b.surfaces) {
        if (s.at !== 'code') continue
        expect(CODE_SURFACES.get(`${s.module}#${s.symbol}`)).toBeDefined()
      }
    }
  })

  it('composition surfaces are real: two states compose two different islands', () => {
    const a = composeLayout(MATURE, 'acme-corp', FAST)
    const b = composeLayout(CAMP, 'acme-corp', FAST)
    expect(a.structures.map((s) => s.role).sort()).not.toEqual(
      b.structures.map((s) => s.role).sort()
    )
    expect(a.state.era).not.toBe(b.state.era)
  })

  it('an unrendered row states a reason, and a rendered row does not pretend to', () => {
    for (const [id, b] of LAW_RENDER) {
      if (b.rendered) {
        expect(b.note.length, id).toBeGreaterThan(20)
        expect(b.surfaces.length, id).toBeGreaterThan(0)
      } else {
        expect(b.reason.length, id).toBeGreaterThan(40)
        expect(b.reason, id).not.toMatch(/TODO|later|soon/i)
      }
    }
  })

  it('coverage is HONEST under iso — the eight unpainted rows are named', () => {
    const c = renderCoverage('iso')
    expect(c.total).toBe(LAW_RENDER.size)
    expect(c.rendered).toBeLessThan(c.total) // the whole point: never a free 100%
    expect(c.fraction).not.toBeNull()
    expect(c.unrendered).toEqual([
      'subagents_lifetime',
      'golden_evals_delta',
      'hats_earned',
      'street_hq_floors',
      'wardroom_bookshelf_fill',
      'wardroom_noticeboard_pins',
      'street_liveliness',
      'harbor_boat_voyage',
    ])
    expect(c.rendered + c.unrendered.length).toBe(c.total)
  })

  it('every unrendered row can say why, and every rendered one stays quiet', () => {
    for (const id of renderCoverage('iso').unrendered) {
      expect(unrenderedReason(id, 'iso'), id).toBeTruthy()
    }
    expect(unrenderedReason('memory_store', 'iso')).toBeNull()
    expect(unrenderedReason('no-such-law', 'iso')).toBeNull()
  })

  it('coverage is per-kernel arithmetic, not a constant', () => {
    // Nothing is topdown-only or iso-only today, so the two agree — but the
    // arithmetic must be the reason they agree, not a hardcoded number. A row
    // bound to one kernel counts against the other.
    const iso = renderCoverage('iso')
    const top = renderCoverage('topdown')
    expect(iso.total).toBe(top.total)
    for (const [id, b] of LAW_RENDER) {
      if (!b.rendered) continue
      if (b.kernels === 'iso') expect(top.unrendered).toContain(id)
      if (b.kernels === 'topdown') expect(iso.unrendered).toContain(id)
    }
  })
})
