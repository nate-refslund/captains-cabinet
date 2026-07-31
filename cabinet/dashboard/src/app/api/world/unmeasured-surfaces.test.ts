/**
 * THE REMAINING UNMEASURED-VS-VALUE ROWS, DRIVEN — not grepped.
 *
 * Sibling of `killswitch-surfaces.test.ts`, and for the same reason it exists:
 * the census fix was defeated on every CONSUMER in its first adversarial round
 * because the only guards were substring greps, and a grep tests a spelling.
 * So these arms CALL the handlers — `GET /api/world/rail` and
 * `GET /api/world/engine` — and assert what comes out on the wire.
 *
 * Two rows are covered here because both live inside a route rather than in a
 * pure module:
 *
 *   rail/route.ts    `(micro ?? 0) + (parseInt(value || '0', 10) || 0)` turned
 *                    a corrupt cost field into a MEASURED $0.00 for that
 *                    officer, while an ABSENT field correctly stayed null.
 *   engine/route.ts  `num(latestKf, 'org_events_total') ?? 0` folded a PRESENT
 *                    keyframe that is MISSING that one field into a day-zero
 *                    island (`landRadius(0)` is the smallest world there is) —
 *                    and the "census unavailable" badge could not fire, because
 *                    it only watches for a NULL eval, never a per-field hole in
 *                    a keyframe that arrived.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const COOKIE = 'test-session-value'

vi.mock('next/headers', () => ({
  cookies: async () => ({ get: () => ({ value: COOKIE }) }),
}))

const store: { values: Record<string, string>; hashes: Record<string, Record<string, string>> } = {
  values: {},
  hashes: {},
}

vi.mock('ioredis', () => ({
  default: class {
    async get(k: string): Promise<string | null> {
      return store.values[k] ?? null
    }
    async keys(pattern: string): Promise<string[]> {
      const prefix = pattern.replace('*', '')
      return Object.keys(store.values).filter((k) => k.startsWith(prefix))
    }
    async hgetall(k: string): Promise<Record<string, string>> {
      return store.hashes[k] ?? {}
    }
    async xrevrange(): Promise<Array<[string, string[]]>> {
      return []
    }
    async xlen(): Promise<number> {
      return 0
    }
    async quit() {}
    disconnect() {}
  },
}))

const savedRedisUrl = process.env.REDIS_URL
const savedRoot = process.env.CABINET_ROOT
let tmpRoot: string | null = null

beforeEach(() => {
  store.values = {}
  store.hashes = {}
  process.env.REDIS_URL = 'redis://127.0.0.1:6379'
})

afterEach(() => {
  if (savedRedisUrl === undefined) delete process.env.REDIS_URL
  else process.env.REDIS_URL = savedRedisUrl
  if (savedRoot === undefined) delete process.env.CABINET_ROOT
  else process.env.CABINET_ROOT = savedRoot
  if (tmpRoot) {
    fs.rmSync(tmpRoot, { recursive: true, force: true })
    tmpRoot = null
  }
  vi.resetModules()
})

const TODAY = new Date().toISOString().split('T')[0]
const COST_KEY = `cabinet:cost:tokens:daily:${TODAY}`

interface RailBody {
  slots: Array<{ slug: string; costMicro: number | null; ring: string; freshS: number | null }>
  dayMaxMicro: number | null
}

async function rail(): Promise<RailBody> {
  const { GET } = await import('./rail/route')
  const res = await GET({} as never)
  return (await res.json()) as RailBody
}

describe('GET /api/world/rail — a corrupt cost field is not $0.00', () => {
  it('ABSENT cost stays null (the rail already renders the honest em-dash)', async () => {
    store.values['cabinet:officer:expected:cos'] = 'active'
    const body = await rail()
    expect(body.slots[0].slug).toBe('cos')
    expect(body.slots[0].costMicro).toBeNull()
  })

  it('THE DEFECT: a non-numeric cost field must be null, never a measured zero', async () => {
    store.values['cabinet:officer:expected:cos'] = 'active'
    store.hashes[COST_KEY] = { cos_cost_micro: 'NOT-A-NUMBER' }
    const body = await rail()
    expect(body.slots[0].costMicro).toBeNull()
  })

  it('one corrupt project field poisons only that officer, not the roster', async () => {
    store.values['cabinet:officer:expected:cos'] = 'active'
    store.values['cabinet:officer:expected:cto'] = 'active'
    store.hashes[COST_KEY] = {
      cos_alpha_cost_micro: 'x',
      cos_beta_cost_micro: '5000',
      cto_cost_micro: '7000',
    }
    const body = await rail()
    const bySlug = Object.fromEntries(body.slots.map((s) => [s.slug, s.costMicro]))
    expect(bySlug.cos).toBeNull()
    expect(bySlug.cto).toBe(7000)
  })

  it('a real cost still totals, and a MEASURED zero is still zero', async () => {
    // The inverse arm: a fix that nulls everything passes every arm above.
    store.values['cabinet:officer:expected:cos'] = 'active'
    store.values['cabinet:officer:expected:cto'] = 'active'
    store.hashes[COST_KEY] = { cos_cost_micro: '12345', cto_cost_micro: '0' }
    const body = await rail()
    const bySlug = Object.fromEntries(body.slots.map((s) => [s.slug, s.costMicro]))
    expect(bySlug.cos).toBe(12345)
    expect(bySlug.cto).toBe(0)
  })

  it('a FUTURE-DATED activity stamp is not a green ring', async () => {
    store.values['cabinet:officer:expected:cos'] = 'active'
    store.values['cabinet:officer:activity:cos'] = JSON.stringify({
      verb: 'building',
      object: 'nothing',
      since: '2030-01-01T00:00:00Z',
    })
    const body = await rail()
    expect(body.slots[0].freshS).toBeNull()
    expect(body.slots[0].ring).not.toBe('green')
  })

  it('a genuinely fresh activity stamp IS a green ring', async () => {
    store.values['cabinet:officer:expected:cos'] = 'active'
    store.values['cabinet:officer:activity:cos'] = JSON.stringify({
      verb: 'building',
      object: 'something',
      since: new Date(Date.now() - 60_000).toISOString(),
    })
    const body = await rail()
    expect(body.slots[0].ring).toBe('green')
  })
})

// ── engine: org_events_total ────────────────────────────────────────────────

function seedChronicle(rows: Array<Record<string, unknown>>): void {
  tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'cabinet-engine-'))
  const dir = path.join(tmpRoot, 'shared', 'interfaces')
  fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(
    path.join(dir, 'world-chronicle.jsonl'),
    rows.map((r) => JSON.stringify(r)).join('\n') + '\n'
  )
  process.env.CABINET_ROOT = tmpRoot
}

interface EngineBody {
  eval: unknown
  orgEventsTotal: number | null
}

async function engine(): Promise<EngineBody> {
  const { GET } = await import('./engine/route')
  const res = await GET({} as never)
  return (await res.json()) as EngineBody
}

const KEYFRAME = {
  date: '2026-07-30',
  org_events_total: 168917,
  lanes: {},
}

describe('GET /api/world/engine — a keyframe missing one field is not a day-zero org', () => {
  it('a complete keyframe reports its event total', async () => {
    seedChronicle([KEYFRAME])
    const body = await engine()
    expect(body.orgEventsTotal).toBe(168917)
  })

  it('THE DEFECT: a PRESENT keyframe with no org_events_total is null, not 0', async () => {
    // `?? 0` made this render the smallest island there is, silently, while
    // the census badge stayed quiet because `eval` was not null.
    const { org_events_total: _drop, ...withoutField } = KEYFRAME
    seedChronicle([withoutField])
    const body = await engine()
    expect(body.eval).not.toBeNull() // the keyframe DID arrive
    expect(body.orgEventsTotal).toBeNull() // ...but this field did not
  })

  it('a NON-NUMERIC org_events_total is null too', async () => {
    seedChronicle([{ ...KEYFRAME, org_events_total: 'lots' }])
    const body = await engine()
    expect(body.orgEventsTotal).toBeNull()
  })

  it('a genuine ZERO is still reported as zero, not swallowed into unknown', async () => {
    // The inverse arm: a day-zero org really does have zero events, and that
    // is a measurement.
    seedChronicle([{ ...KEYFRAME, org_events_total: 0 }])
    const body = await engine()
    expect(body.orgEventsTotal).toBe(0)
  })
})
