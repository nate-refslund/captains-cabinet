/**
 * Instance lane readers (Wave G) — parse laws + fail-honest fallbacks.
 * All fixtures are synthetic Testburg vocabulary in a tmpdir; lane names
 * are instance data, so no real lane may appear here. R164 (done): the
 * instance-test mark is read from instance_test_lanes in
 * instance/config/platform.yml (fail-honest to the empty set), so the
 * outcomes fixture exercises it with the same Testburg vocabulary as
 * every other lane here — 'orchard' is marked instance-test via the
 * platform.yml fixture below, no hardcoded module constant left to test.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { declaredLanes, outcomeLanes, probeWiredLanes } from './instance-lanes'

let root: string

async function write(rel: string, content: string): Promise<void> {
  const p = path.join(root, rel)
  await fs.mkdir(path.dirname(p), { recursive: true })
  await fs.writeFile(p, content, 'utf8')
}

beforeAll(async () => {
  root = await fs.mkdtemp(path.join(os.tmpdir(), 'testburg-instance-'))
  // contexts: the declared-lane universe
  await write(
    'instance/config/contexts/bakery.yml',
    '# a comment first\nslug: bakery\nname: Bakery\nactive: false\n'
  )
  await write(
    'instance/config/contexts/newsletter.yml',
    'slug: "Newsletter"\nname: Newsletter\n' // quoted + uppercase → lowercased
  )
  await write(
    'instance/config/contexts/orchard.yml',
    'slug: ""orchard""\nname: Orchard\n' // quote RUNS strip (python strip('"'))
  )
  await write(
    'instance/config/contexts/_default.yml',
    'name: defaults only — no slug here\n' // slug-less file contributes nothing
  )
  await write(
    'instance/config/contexts/broken.yml',
    "slug: ''\nslug: late-second-slug\n" // first slug line wins AND ends the scan
  )
  await write('instance/config/contexts/notes.txt', 'slug: not-a-yml\n')
  // platform.yml: instance_test_lanes marks 'orchard' as instance-test
  await write(
    'instance/config/platform.yml',
    'instance_test_lanes:\n  - orchard\n'
  )
  // outcomes: the birth-order ledger
  await write(
    'instance/config/outcomes.yml',
    [
      'outcomes:',
      '  - id: outcome-bakery-001',
      '    status: active',
      '  - id: outcome-bakery-002',
      '    status: achieved',
      '  - id: outcome-newsletter-001',
      '    status: retired',
      '  - id: outcome-oddly-shaped-id-001', // regex fallback → pseudo-lane
      '    status: active',
      '  - id: outcome-anything-007',
      '    lane: newsletter', // explicit lane: wins over the id regex
      '    status: active',
      '  - id: outcome-drafts-001',
      '    status: draft', // never ratified — not "ever"
      '  - id: outcome-orchard-001', // platform.yml marks orchard instance-test
      '    status: active',
    ].join('\n') + '\n'
  )
  // probes + projects: the probe-wired join
  await write(
    'instance/config/probes.yml',
    [
      'github:',
      '  - repo: Testburg-Org/bakery-site',
      '    checkout: /opt/testburg-cabinet/bakery-site',
      'vercel:',
      '  - app: gazette-web',
      '    checkout: /opt/testburg-cabinet/gazette-web',
    ].join('\n') + '\n'
  )
  await write(
    'instance/config/projects/bakery.yml',
    'product:\n  name: Bakery\n  repo: https://github.com/Testburg-Org/bakery-site\n'
  )
  await write(
    'instance/config/projects/gazette.yml',
    'product:\n  name: Gazette\n  repo: git@github.com:Testburg-Org/gazette-web.git\n'
  )
  await write(
    'instance/config/projects/newsletter.yml',
    'product:\n  name: Newsletter\n  repo: https://github.com/Testburg-Org/newsletter\n'
  )
  await write(
    'instance/config/projects/_template.yml',
    'product:\n  name: Template\n  repo: https://github.com/Testburg-Org/bakery-site\n'
  )
})

afterAll(async () => {
  await fs.rm(root, { recursive: true, force: true })
})

describe('declaredLanes — the context slug universe', () => {
  it('parses the first slug: scalar per contexts/*.yml (quote runs stripped, lowercased)', () => {
    // orchard rides in as ""orchard"" — run-strip parity with
    // _context_slugs / env.lanes() / cabinet_lanes (strip('"') eats the RUN,
    // where a single-char strip would leave '"orchard"')
    expect(declaredLanes(root)).toEqual(['bakery', 'newsletter', 'orchard'])
  })
  it('unreadable dir ⇒ [] (honest absence, never a default)', () => {
    expect(declaredLanes(path.join(root, 'no-such-root'))).toEqual([])
  })
})

describe('outcomeLanes — the birth-order ledger fold', () => {
  it('folds records in first-ratified order; draft rows never count', () => {
    const out = outcomeLanes(root)
    // key order IS birth order — the berth fold depends on this
    expect(Object.keys(out.lanes)).toEqual([
      'bakery',
      'newsletter',
      'oddly-shaped-id',
      'orchard',
    ])
    expect(out.lanes.bakery).toMatchObject({ ever: 2, active: 1, achieved: 1, retired: 0 })
    // explicit lane: field beats the id regex (row 5 lands on newsletter)
    expect(out.lanes.newsletter).toMatchObject({ ever: 2, active: 1, retired: 1 })
    expect(out.lanes.orchard.instanceTest).toBe(true)
    expect(out.lanes.bakery.instanceTest).toBe(false)
  })
  it('missing file ⇒ empty fold', () => {
    expect(outcomeLanes(path.join(root, 'no-such-root')).lanes).toEqual({})
  })
})

describe('probeWiredLanes — the probes.yml ⋈ projects join', () => {
  it('joins github repo slugs and vercel apps against product.repo', () => {
    // bakery via github row; gazette via vercel app; newsletter has no row
    expect(probeWiredLanes(root)).toEqual(['bakery', 'gazette'])
  })
  it('missing probes.yml ⇒ [] (every isle honestly unverified)', () => {
    expect(probeWiredLanes(path.join(root, 'no-such-root'))).toEqual([])
  })
})
