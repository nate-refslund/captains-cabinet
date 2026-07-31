/**
 * THE NO-STORE SWEEP, DRIVEN — every reader, with REDIS_URL unset.
 *
 * WHY THIS FILE EXISTS. The census fix (#328) was defeated on every consumer in
 * its first adversarial round because the only guards were substring greps, and
 * a grep tests a spelling. `store-posture.test.ts` is the pure decision;
 * THIS file is the one that fails if any reader still invents.
 *
 * It is the sensor the ruling asked for: boot with no store, and fail if a
 * dollar figure or a "running" officer comes out. Every arm below FAILS against
 * pre-change `lib/redis.ts` — where `!REDIS_URL` seeded five heartbeats, an
 * all-`active` roster and a randomised 30-day cost history — which is the only
 * property that makes it a sensor rather than a fixture. (Proven by reverting
 * `IS_MOCK = !process.env.REDIS_URL || MOCK_DATA === 'true'` and re-running;
 * the mutation log is in the PR.)
 *
 * HONEST LIMIT, stated rather than hidden: vitest runs `environment: 'node'`
 * with no DOM renderer, so the React surfaces cannot be mounted here. Their
 * decisions were therefore moved into pure modules — `lib/liveness.ts`
 * (`livenessWord` can never return "Active" for an unread heartbeat) and
 * `lib/store-posture.ts` — which ARE driven, by their own suites. What is
 * untested here is JSX layout, not the invent/absent decision; the pixels are
 * covered by the before/after browser capture in the PR, taken against a
 * running app with no REDIS_URL.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const saved = {
  REDIS_URL: process.env.REDIS_URL,
  MOCK_DATA: process.env.MOCK_DATA,
  CABINET_DEMO_DATA: process.env.CABINET_DEMO_DATA,
}

/** The posture this whole file is about: nothing configured, nothing asked for. */
function noStore() {
  delete process.env.REDIS_URL
  delete process.env.MOCK_DATA
  delete process.env.CABINET_DEMO_DATA
}

beforeEach(() => {
  vi.resetModules()
  noStore()
})

afterEach(() => {
  for (const [k, v] of Object.entries(saved)) {
    if (v === undefined) delete process.env[k]
    else process.env[k] = v
  }
  vi.resetModules()
})

describe('the store itself invents nothing', () => {
  it('holds NO officer heartbeats', async () => {
    const { default: redis } = await import('./redis')
    expect(await redis.keys('cabinet:heartbeat:*')).toEqual([])
    for (const role of ['cos', 'cto', 'cpo', 'cro', 'coo']) {
      expect(await redis.get(`cabinet:heartbeat:${role}`)).toBeNull()
    }
  })

  it('holds NO officer roster and no expectations', async () => {
    const { default: redis } = await import('./redis')
    expect(await redis.keys('cabinet:officer:expected:*')).toEqual([])
  })

  it('holds NO cost data at all — not one key, not one field', async () => {
    const { default: redis } = await import('./redis')
    expect(await redis.keys('cabinet:cost:')).toEqual([])
    const today = new Date().toISOString().split('T')[0]
    expect(await redis.hgetall(`cabinet:cost:tokens:daily:${today}`)).toBeNull()
  })

  it('holds NO schedule history and no tool-call counters', async () => {
    const { default: redis } = await import('./redis')
    expect(await redis.keys('cabinet:schedule:last-run:')).toEqual([])
    expect(await redis.get('cabinet:toolcalls:cos')).toBeNull()
  })

  it('reports the posture, and reports it as NOT fabricated', async () => {
    const mod = await import('./redis')
    expect(mod.storeReading.posture).toBe('unconfigured')
    expect(mod.storeReading.fabricated).toBe(false)
    // Not-live is still true: an empty store is not a reading.
    expect(mod.isMockRedis).toBe(true)
  })
})

describe('money: no reading, and never a measured zero', () => {
  it('every day of cost history is null, not 0', async () => {
    const { getCostHistory } = await import('./redis')
    const history = await getCostHistory(30)
    expect(history).toHaveLength(30)
    for (const day of history) {
      expect(day.total).toBeNull()
      expect(day.officers).toEqual({})
      expect(day.unmeasuredReason).toBeTruthy()
    }
    // The shape that used to render "$65.61" and a 30-day per-officer table.
    expect(history.some((d) => typeof d.total === 'number')).toBe(false)
  })

  it('token cost history carries null totals', async () => {
    const { getTokenCostHistory } = await import('./redis')
    const history = await getTokenCostHistory(7)
    expect(history).toHaveLength(7)
    for (const day of history) {
      expect(day.totalCostMicro).toBeNull()
      expect(day.officers).toEqual({})
    }
  })

  it('schedule last-runs are empty', async () => {
    const { getScheduleLastRuns } = await import('./redis')
    expect(await getScheduleLastRuns()).toEqual({})
  })
})

describe('a present-but-corrupt cost field is unknown, not zero', () => {
  // The other half of the money row: `parseInt(value || '0', 10) || 0`
  // swallowed a non-numeric field into a MEASURED zero, silently shrinking the
  // total the Captain reads as his spend. `sumDailyCost` is pure and exported
  // exactly so these ends can be driven without standing up a store.
  const ROLES = ['cos', 'cto']

  it('a non-numeric cost field makes the DAY unmeasured and says which field', async () => {
    const { sumDailyCost } = await import('./redis')
    const r = sumDailyCost({ cos_cost_micro: 'NOT-A-NUMBER', cto_cost_micro: '900000' }, ROLES)
    expect(r.total).toBeNull()
    expect(r.officers).toEqual({})
    expect(r.unmeasuredReason).toMatch(/not a number/i)
    expect(r.unmeasuredReason).toMatch(/cos_cost_micro/)
  })

  it('an EMPTY string field is not a zero either', async () => {
    const { sumDailyCost } = await import('./redis')
    expect(sumDailyCost({ cos_cost_micro: '' }, ROLES).total).toBeNull()
  })

  it('an ABSENT hash and an EMPTY hash are both unmeasured', async () => {
    const { sumDailyCost } = await import('./redis')
    for (const h of [null, undefined, {}]) {
      const r = sumDailyCost(h, ROLES)
      expect(r.total).toBeNull()
      expect(r.unmeasuredReason).toBeTruthy()
    }
  })

  it('a genuinely ZERO cost field is a MEASURED zero, not unknown', async () => {
    // The inverse arm. A "fix" that turns every reading into unknown passes
    // every arm above and is exactly as useless as the one that turned every
    // reading into a number.
    const { sumDailyCost } = await import('./redis')
    const r = sumDailyCost({ cos_cost_micro: '0', cto_cost_micro: '0' }, ROLES)
    expect(r.total).toBe(0)
    expect(r.unmeasuredReason).toBeNull()
    expect(r.officers).toEqual({ cos: 0, cto: 0 })
  })

  it('a real total still totals — including pool-mode per-project fields', async () => {
    const { sumDailyCost } = await import('./redis')
    const r = sumDailyCost(
      { cos_alpha_cost_micro: '10000', cos_beta_cost_micro: '20000', cto_cost_micro: '30000' },
      ROLES
    )
    expect(r.total).toBe(6) // 60000 micro = 6 cents
    expect(r.unmeasuredReason).toBeNull()
  })
})

describe('the runtime probes invent no officers', () => {
  it('getTmuxWindows returns NO officers — this is what said "4/5 running"', async () => {
    const { getTmuxWindows } = await import('./docker')
    expect(await getTmuxWindows()).toEqual([])
  })

  it('isClaudeAlive is false for every role', async () => {
    const { isClaudeAlive } = await import('./docker')
    for (const role of ['cos', 'cto', 'cpo', 'cro', 'coo']) {
      expect(await isClaudeAlive(role)).toBe(false)
    }
  })

  it('isTelegramConnected is false for every role', async () => {
    const { isTelegramConnected } = await import('./docker')
    for (const role of ['cos', 'cto', 'cpo', 'cro', 'coo']) {
      expect(await isTelegramConnected(role)).toBe(false)
    }
  })

  it('getCronSchedule returns nothing — and never the no-op sentinel as a job', async () => {
    // CABINET_RUNTIME_MODE=native is REQUIRED here, and finding that out is
    // why this arm exists in its current form: without it `RUNTIME_MODE`
    // resolves to 'docker', whose branch never calls `dockerExec` at all — so
    // the first version of this test passed against a deliberately
    // re-introduced defect, because the mutated line was unreachable. A fence
    // that cannot reach the code it names is a disabled sensor.
    process.env.CABINET_RUNTIME_MODE = 'native'
    try {
      const { getCronSchedule, MOCK_EXEC_SENTINEL } = await import('./docker')
      const jobs = await getCronSchedule()
      expect(jobs).toEqual([])
      expect(jobs.some((j) => j.command.includes(MOCK_EXEC_SENTINEL))).toBe(false)
    } finally {
      delete process.env.CABINET_RUNTIME_MODE
    }
  })

  it('getEnvVars invents no credential names', async () => {
    const { getEnvVars } = await import('./docker')
    expect(await getEnvVars()).toEqual({})
  })
})

describe('the emergency stop stays UNKNOWN with no store', () => {
  it('is never a verified "clear" from an empty store answering null', async () => {
    // The regression this guards: the empty `unconfigured` store answers null,
    // and `readingFromKey(null, contacted: true)` is a MEASURED "not engaged".
    // Only `isMockRedis` covering BOTH not-live postures stops that.
    const { readKillswitch } = await import('./killswitch-state')
    const r = await readKillswitch()
    expect(r.engaged).toBeNull()
    expect(r.unknownReason).toBeTruthy()
  })
})

describe('the DEMO posture still fabricates — and still says so', () => {
  it('MOCK_DATA=true outside production restores the seeded store', async () => {
    process.env.MOCK_DATA = 'true'
    // NODE_ENV is typed read-only; vitest already runs it as 'test', which is
    // the non-production side of the gate this arm exercises.
    expect(process.env.NODE_ENV).not.toBe('production')
    const mod = await import('./redis')
    expect(mod.storeReading.fabricated).toBe(true)
    expect(await mod.default.keys('cabinet:heartbeat:*')).not.toEqual([])
    const history = await mod.getCostHistory(1)
    expect(typeof history[0].total).toBe('number')
  })

  it('CABINET_DEMO_DATA=true does the same WITHOUT touching MOCK_DATA', async () => {
    // demo-dashboard.sh needs fabricated data AND its login page; MOCK_DATA
    // also waives auth in middleware, so the store-only opt-in exists.
    process.env.CABINET_DEMO_DATA = 'true'
    const mod = await import('./redis')
    expect(mod.storeReading.fabricated).toBe(true)
    expect(process.env.MOCK_DATA).toBeUndefined()
  })

  it('the emergency stop is UNKNOWN in demo too — a seeded value is not a reading', async () => {
    process.env.MOCK_DATA = 'true'
    const { readKillswitch } = await import('./killswitch-state')
    expect((await readKillswitch()).engaged).toBeNull()
  })
})
