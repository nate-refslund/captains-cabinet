/**
 * "WE KNOW NOTHING" MUST NOT LOOK LIKE "YOU HAVE NOTHING".
 *
 * THE DEFECT (Captain, 2026-07-27): `/world?iso=1` rendered a CAMP island while
 * the org is a hamlet at index 0.44 — four officers, seven berths, a cobbled
 * road, three lamp posts with one lit, the lighthouse lamp burning. Measured the
 * same day, the feed had two silent ways to vanish:
 *
 *   1. `/api/world/engine` 401s without the `cabinet_session` cookie, and
 *      engine-client swallows it with `if (!r.ok) return`, so `resolution`
 *      stays null. A logged-out browser renders a hatch.
 *   2. the route reads `shared/interfaces/world-chronicle.jsonl` under
 *      CABINET_ROOT. That file is a gitignored RUNTIME artifact, so a dev
 *      server started in a worktree or a fresh clone has no keyframes and
 *      `eval` is undefined — the resolution is null again.
 *
 * THE BASELINE IS NOT THE BUG. An unmeasured metric renders its baseline, so
 * with no feed the island SHOULD be the hatch. The bug is that it said nothing:
 * the unfed renderer and a genuine day-zero cabinet paint the same pixels, and a
 * dashboard whose "no data" and whose "no progress" are one picture is not
 * reporting. These arms pin the indistinguishability (so nobody later "fixes"
 * it by inventing state) and pin the announcement that makes it readable.
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { layoutStateFrom, UNMEASURED_STATE_ISSUE } from './iso-scene'
import type { WorldResolution } from './era-engine'

const CANVAS = path.resolve(
  __dirname,
  '..',
  '..',
  'components',
  'world',
  'engine-canvas.tsx'
)

describe('an unfed iso renderer says so', () => {
  it('a null resolution composes the HATCH BASELINE, not an invented state', () => {
    const st = layoutStateFrom(null)
    expect({
      era: st.era,
      road: st.road,
      stages: Object.keys(st.stages ?? {}).length,
      counts: Object.keys(st.counts ?? {}).length,
    }).toEqual({ era: 'camp', road: 'dirt_path', stages: 0, counts: 0 })
  })

  it('that baseline is IDENTICAL to a real day-zero cabinet — which is the problem', () => {
    // The positive control for the arm below: if these two ever diverged the
    // announcement would be unnecessary, and this test would be telling us so.
    const hatched: WorldResolution = {
      era: 'camp',
      eraIndex: 0,
      eraUnmeasured: [],
      elements: {},
    } as unknown as WorldResolution
    expect(layoutStateFrom(hatched)).toEqual(layoutStateFrom(null))
  })

  it('the issue names the baseline AND both ways the feed goes missing', () => {
    const t = UNMEASURED_STATE_ISSUE
    expect({
      saysBaseline: /baseline/i.test(t),
      refusesTheClaim: /not a claim/i.test(t),
      namesAuth: /unauthenticated|session/i.test(t),
      namesChronicle: /world-chronicle\.jsonl/.test(t),
      namesRoot: /CABINET_ROOT/.test(t),
    }).toEqual({
      saysBaseline: true,
      refusesTheClaim: true,
      namesAuth: true,
      namesChronicle: true,
      namesRoot: true,
    })
  })

  it('the canvas RAISES it on the issues channel when the resolution is null', () => {
    // A source ratchet, in the shape ratchets.test.ts already uses for the
    // other loud-failure surfaces: the wiring lives inside a PixiJS closure
    // that no unit test can enter, and a silent renderer is precisely the
    // regression class this exists to stop.
    const src = fs.readFileSync(CANVAS, 'utf8')
    const block = src.slice(src.indexOf('function rebuildIsoStatics'))
    const guard = block.indexOf('if (!p.resolution)')
    expect(guard).toBeGreaterThan(-1)
    const body = block.slice(guard, guard + 800)
    expect({
      badges: body.includes('onIssues?.([UNMEASURED_STATE_ISSUE])'),
      logs: body.includes('console.error'),
      // and it happens BEFORE the scene is composed, so the frame the reader
      // sees is never announced as measured
      beforeCompose: guard < block.indexOf('buildIsoScene('),
    }).toEqual({ badges: true, logs: true, beforeCompose: true })
  })
})
