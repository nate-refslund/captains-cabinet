import {
  isNotLiveStore,
  resolveStorePosture,
  unreachableReading,
  type StoreReading,
} from './store-posture'
import {
  guardCommands,
  LIVE_CLIENT_OPTIONS,
  StoreBreaker,
  StoreUnreachableError,
} from './store-reachability'

/**
 * What produced everything this module hands out. See `lib/store-posture.ts`
 * for the ruling; the short version is that `!REDIS_URL` used to be a licence
 * to INVENT five officers and a randomised 30-day cost history, and is now an
 * EMPTY store instead.
 */
export const storeReading: StoreReading = resolveStorePosture(process.env)

/** Only an explicit, non-production opt-in reaches the seeded data below. */
const IS_FABRICATED = storeReading.fabricated

// Generate date strings for last N days
function daysAgo(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().split('T')[0]
}

// Mock data for local development
const today = new Date().toISOString().split('T')[0]
const officers = ['cos', 'cto', 'cpo', 'cro', 'coo']
const dailyCosts = [4250, 3800, 5100, 4700, 3200, 4900, 4450, 3600, 5200, 4100, 3900, 4600, 5000, 3700, 4300, 4800, 3500, 5300, 4000, 3100, 4400, 4950, 3850, 5050, 4150, 3650, 4550, 4750, 3350, 5150]
const officerWeights: Record<string, number> = { cos: 0.30, cto: 0.25, cpo: 0.20, cro: 0.15, coo: 0.10 }

/**
 * The seeded demo store. Reachable ONLY from the explicit non-production
 * opt-in — `IS_FABRICATED` gates whether it is ever installed as the client.
 * In the `unconfigured` posture the store is a structurally EMPTY twin of this
 * object, so every consumer takes its absent branch instead of reading a lie.
 */
const mockStore: Record<string, string> = {
  'cabinet:heartbeat:cos': new Date().toISOString(),
  'cabinet:heartbeat:cto': new Date(Date.now() - 120000).toISOString(),
  'cabinet:heartbeat:cpo': new Date(Date.now() - 300000).toISOString(),
  'cabinet:heartbeat:cro': new Date(Date.now() - 60000).toISOString(),
  'cabinet:heartbeat:coo': new Date(Date.now() - 900000).toISOString(),
  'cabinet:officer:expected:cos': 'active',
  'cabinet:officer:expected:cto': 'active',
  'cabinet:officer:expected:cpo': 'active',
  'cabinet:officer:expected:cro': 'active',
  'cabinet:officer:expected:coo': 'active',
  'cabinet:killswitch': '',
  // Health mock data — last-toolcall and daily tool call counts
  'cabinet:last-toolcall:cos': new Date(Date.now() - 45000).toISOString(),
  'cabinet:last-toolcall:cto': new Date(Date.now() - 180000).toISOString(),
  'cabinet:last-toolcall:cpo': new Date(Date.now() - 420000).toISOString(),
  'cabinet:last-toolcall:cro': new Date(Date.now() - 90000).toISOString(),
  'cabinet:last-toolcall:coo': new Date(Date.now() - 960000).toISOString(),
  'cabinet:toolcalls:cos': '312',
  'cabinet:toolcalls:cto': '487',
  'cabinet:toolcalls:cpo': '156',
  'cabinet:toolcalls:cro': '203',
  'cabinet:toolcalls:coo': '89',
  // Schedule last-run mock data
  'cabinet:schedule:last-run:cos:reflection': new Date(Date.now() - 3 * 3600000).toISOString(),
  'cabinet:schedule:last-run:cos:briefing': new Date(Date.now() - 7 * 3600000).toISOString(),
  'cabinet:schedule:last-run:cro:research-sweep': new Date(Date.now() - 2 * 3600000).toISOString(),
  'cabinet:schedule:last-run:cpo:backlog-refinement': new Date(Date.now() - 10 * 3600000).toISOString(),
  'cabinet:schedule:last-run:cos:retro': new Date(Date.now() - 20 * 3600000).toISOString(),
}

// FW-016: legacy cabinet:cost:daily:* + cabinet:cost:officer:*:* keys were
// removed; tokens:daily HSET is the single source of truth. getCostHistory
// now reads from HSET and converts microdollars → cents.

// Mock hash store for HGETALL support
const mockHashStore: Record<string, Record<string, string>> = {}

// Populate mock token cost data — 30 days for getCostHistory backfill.
// Gated: in the `unconfigured` posture these keys are never written, so there
// is no fabricated dollar figure in this process for anything to reach. The
// gate is at the WRITE, not at the read, on purpose — a value that was never
// created cannot be surfaced by a future consumer that forgets to check.
for (let i = 0; IS_FABRICATED && i < 30; i++) {
  const dateStr = daysAgo(i)
  const hash: Record<string, string> = {}
  for (const role of officers) {
    const weight = officerWeights[role]
    const base = 500000 + Math.round(Math.random() * 200000) // ~500K-700K output tokens
    hash[`${role}_input`] = String(Math.round(base * 0.01))
    hash[`${role}_output`] = String(Math.round(base * weight))
    hash[`${role}_cache_write`] = String(Math.round(base * weight * 2.5))
    hash[`${role}_cache_read`] = String(Math.round(base * weight * 50))
    // Opus cost in microdollars: in*15 + out*75 + cw*3.75 + cr*0.30
    const inp = Math.round(base * 0.01)
    const out = Math.round(base * weight)
    const cw = Math.round(base * weight * 2.5)
    const cr = Math.round(base * weight * 50)
    hash[`${role}_cost_micro`] = String(inp * 15 + out * 75 + Math.round(cw * 3.75) + Math.round(cr * 0.3))
  }
  mockHashStore[`cabinet:cost:tokens:daily:${dateStr}`] = hash
}

// Mock context window data per officer (for health page)
const mockContextPcts: Record<string, number> = { cos: 38.2, cto: 67.5, cpo: 22.1, cro: 45.8, coo: 81.4 }
for (const role of IS_FABRICATED ? officers : []) {
  const pct = mockContextPcts[role]
  mockHashStore[`cabinet:cost:tokens:${role}`] = {
    last_context_pct: String(pct),
    last_context_tokens: String(Math.round((pct / 100) * 1000000)),
    last_updated: new Date(Date.now() - Math.round(Math.random() * 300000)).toISOString(),
  }
}

const mockRedis = {
  get: async (key: string) => mockStore[key] || null,
  set: async (key: string, value: string) => { mockStore[key] = value; return 'OK' },
  del: async (key: string) => { delete mockStore[key]; return 1 },
  keys: async (pattern: string) => {
    const prefix = pattern.replace('*', '')
    return [
      ...Object.keys(mockStore).filter(k => k.startsWith(prefix)),
      ...Object.keys(mockHashStore).filter(k => k.startsWith(prefix)),
    ]
  },
  hgetall: async (key: string): Promise<Record<string, string> | null> =>
    mockHashStore[key] || null,
  // The reachability probe (`currentStoreReading`) issues this. It never runs
  // against the in-process stores — they return early — but the shape has to
  // exist or the default export's type loses the method the live client needs.
  ping: async (): Promise<string> => 'PONG',
}

/**
 * The `unconfigured` client: the same shape, holding nothing.
 *
 * NOT a real ioredis client pointed at a default endpoint — an ioredis client
 * with nothing behind it QUEUES commands rather than failing, which would swap
 * a lie for a hang on every page. An empty store answers `null` / `[]`
 * immediately, so every consumer takes the branch it already has for absence.
 *
 * Writes are accepted and kept in-process for the life of the request handler,
 * because refusing them would turn a disclosed no-store dashboard into a pile
 * of 500s; nothing here is persisted, and `storeReading` is what tells the
 * surface not to believe any of it.
 */
const emptyStore: Record<string, string> = {}
const unconfiguredRedis = {
  get: async (key: string) => emptyStore[key] ?? null,
  set: async (key: string, value: string) => {
    emptyStore[key] = value
    return 'OK'
  },
  del: async (key: string) => {
    delete emptyStore[key]
    return 1
  },
  keys: async (pattern: string) => {
    const prefix = pattern.replace('*', '')
    return Object.keys(emptyStore).filter((k) => k.startsWith(prefix))
  },
  hgetall: async (_key: string): Promise<Record<string, string> | null> => null,
  ping: async (): Promise<string> => 'PONG',
}

/**
 * Every command the dashboard issues on the default export.
 *
 * An explicit list rather than a Proxy: a Proxy over an ioredis client has to
 * guess which properties are commands and which are internals it must not
 * rebind, and a guess that is wrong in the permissive direction leaves an
 * UNGUARDED path — which is the hang, back again, on whichever call nobody
 * listed. `xrevrange` is here because `api/world/stream/route.ts` casts past the
 * declared type to reach it; a command that is reachable is a command that can
 * hang.
 */
const GUARDED_COMMANDS = [
  'get',
  'set',
  'del',
  'keys',
  'hgetall',
  'xrevrange',
  'ping',
] as const

/**
 * The live store's reachability, for the life of this process.
 *
 * Module-scoped on purpose: the whole point is that ONE failed call spares the
 * next thirty from paying their own timeout, and a per-request breaker cannot do
 * that. It closes itself the moment any call succeeds.
 */
const liveBreaker = new StoreBreaker()

/**
 * The bounds the LIVE client is actually carrying, or null when there is no live
 * client. Read off the constructed object, not off the constant.
 *
 * This exists because the first version of the fence was a FALSE GREEN, caught
 * by mutation rather than by review: reverting `new Redis(url, LIVE_CLIENT_OPTIONS)`
 * back to `new Redis(url)` — the exact original defect — left the end-to-end arm
 * PASSING, because `guardCommands`' own deadline caught the hang either way. The
 * arm named "the options" was measuring the wrapper. Two independent controls
 * cannot be tested through one of them; this is the door to the other.
 */
export function liveClientBounds(): Record<string, unknown> | null {
  return liveBounds
}
let liveBounds: Record<string, unknown> | null = null

let redis: typeof mockRedis

if (IS_FABRICATED) {
  console.log(
    '[dashboard] DEMO DATA: every officer, heartbeat and dollar figure is invented (MOCK_DATA / CABINET_DEMO_DATA is set, and this is not production)'
  )
  redis = mockRedis
} else if (storeReading.posture === 'unconfigured') {
  console.log(
    '[dashboard] NO STORE: REDIS_URL is unset — every reading renders as an honest unknown. Nothing is invented.'
  )
  redis = unconfiguredRedis
} else {
  const Redis = require('ioredis')
  // The options are the fix for the SET-but-unreachable hang; the reasons and
  // the measurements behind each number are in `lib/store-reachability.ts`.
  // Unbounded, two of the three unreachable shapes never settled at all.
  const realRedis = new Redis(process.env.REDIS_URL, LIVE_CLIENT_OPTIONS)
  const o = realRedis.options as Record<string, unknown>
  liveBounds = {
    connectTimeout: o.connectTimeout,
    commandTimeout: o.commandTimeout,
    maxRetriesPerRequest: o.maxRetriesPerRequest,
    enableOfflineQueue: o.enableOfflineQueue,
  }
  // ioredis prints "[ioredis] Unhandled error event" on every reconnect attempt
  // when nothing is listening — once per attempt, forever, for a dead store.
  // The command promises carry the error we act on; this only stops the log
  // flood from burying whatever else the server is saying.
  realRedis.on('error', () => {})
  redis = guardCommands(
    realRedis,
    GUARDED_COMMANDS as unknown as readonly (keyof typeof realRedis & string)[],
    liveBreaker
  ) as typeof mockRedis
}

/**
 * TRUE when this process is NOT talking to the fleet's store — `demo` OR
 * `unconfigured`.
 *
 * Exported (2026-07-31) because the killswitch readers must be able to say so:
 * with `REDIS_URL` unset, `get('cabinet:killswitch')` used to return the seeded
 * `''`, which `=== 'active'` turned into a confident "the emergency stop is not
 * engaged" — an invented reading about the org's emergency stop, from a store
 * that does not exist.
 *
 * It still covers BOTH not-live postures after the seeded store was gated
 * behind an explicit opt-in, and that is deliberate: the empty `unconfigured`
 * store answers `null`, and `readingFromKey(null, contacted: true)` is a
 * MEASURED "clear". An empty store is not a measurement, so it must never earn
 * `contacted`.
 */
export const isMockRedis = isNotLiveStore(storeReading)

/**
 * The posture AS OF NOW — the configured one, unless the store has stopped
 * answering.
 *
 * `storeReading` is decided from the environment at import time and cannot know
 * whether the host it names is alive. This asks. On a configured store it costs
 * one `PING` (measured p50 0.057ms, p99 0.122ms against the cabinet's own
 * store); on a dead one it costs one timeout, and the breaker makes every later
 * call in the next few seconds free.
 *
 * It is a PROBE rather than a read of whatever the page happened to do first,
 * because a banner whose accuracy depends on some other component having run
 * before it is a sensor wired to render order. `/display` and the authenticated
 * layout both mount the banner from this.
 */
export async function currentStoreReading(): Promise<StoreReading> {
  if (storeReading.posture !== 'live') return storeReading
  try {
    await redis.ping()
    return storeReading
  } catch (err) {
    return unreachableReading(
      err instanceof StoreUnreachableError
        ? err.reason
        : err instanceof Error
          ? err.message
          : 'unknown error'
    )
  }
}

export default redis

export interface DailyCostEntry {
  date: string
  /**
   * NULL = no cost record exists for this date, or one exists and cannot be
   * totalled. A MEASURED zero is `0`.
   *
   * This was `number` and every failure produced `0`, which the surfaces then
   * printed as `$0.00` — a confident claim about money, from a store that had
   * answered nothing. The type is the enforcement: `formatCents(total)` no
   * longer compiles, so a consumer cannot forget the case the way `|| 0` let
   * it.
   */
  total: number | null
  /** Per-officer cents. EMPTY when `total` is null — never a zeroed roster. */
  officers: Record<string, number>
  /** Plain words for why nothing was measured. Null on a measured reading. */
  unmeasuredReason: string | null
}

/**
 * Total ONE day's cost hash — pure, exported, and driven directly.
 *
 * Lifted out of `getCostHistory` (2026-07-31) for the same reason
 * `lib/world/killswitch.ts` holds `readingFromKey`: the degenerate ends of a
 * money reading — absent hash, empty hash, a field that is not a number — are
 * where the defect lived, and they must be testable without standing up a
 * store. A test that can only reach this logic through a live client is a test
 * that will not be written for the ends that matter.
 */
export function sumDailyCost(
  hash: Record<string, string> | null | undefined,
  officers: string[]
): Omit<DailyCostEntry, 'date'> {
  // No record for this date is NOT a day that cost nothing. It is a day nobody
  // wrote down.
  if (!hash || Object.keys(hash).length === 0) {
    return {
      total: null,
      officers: {},
      unmeasuredReason: 'no cost record was written for this date',
    }
  }
  const officerCosts: Record<string, number> = {}
  let total = 0
  let malformedField: string | null = null

  // FW-072 / S3 (Pool Phase 1A): the cost field shape is either legacy
  // `<officer>_cost_micro` (pre-pool) OR per-project
  // `<officer>_<project>_cost_micro` (pool mode). Sum both shapes per officer.
  for (const role of officers) {
    let micro = 0
    for (const [field, value] of Object.entries(hash)) {
      if (
        field === `${role}_cost_micro` ||
        (field.startsWith(`${role}_`) && field.endsWith('_cost_micro'))
      ) {
        // `parseInt(value || '0', 10) || 0` swallowed a non-numeric field into
        // a MEASURED zero, so a corrupt row silently shrank the total the
        // Captain reads as his spend. A total missing one of its parts is a
        // wrong number, and about money a wrong number is worse than none.
        const n = Number.parseInt(value ?? '', 10)
        if (!Number.isFinite(n)) {
          malformedField = malformedField ?? field
          continue
        }
        micro += n
      }
    }
    const cents = Math.round(micro / 10000)
    officerCosts[role] = cents
    total += cents
  }

  if (malformedField) {
    return {
      total: null,
      officers: {},
      unmeasuredReason: `the cost record for this date holds a value that is not a number (${malformedField}), so it cannot be totalled`,
    }
  }
  return { total, officers: officerCosts, unmeasuredReason: null }
}

/**
 * Plain words for a store that did not answer — deliberately DIFFERENT from
 * "no cost record was written for this date".
 *
 * The two are not the same claim and the difference is the whole point of this
 * change: one says the cabinet spent nothing worth recording, the other says
 * nobody asked it. Reusing the absence sentence for an unreachable store would
 * put a false statement in the slot built to hold the true one.
 */
function storeFailureReason(err: unknown): string {
  if (err instanceof StoreUnreachableError) {
    return `this figure was never read: ${err.reason}`
  }
  return `this figure was never read: the store failed (${
    err instanceof Error ? err.message : 'unknown error'
  })`
}

/** N days of "nobody asked", each carrying the same reason. */
function unreadCostHistory(days: number, reason: string): DailyCostEntry[] {
  const entries: DailyCostEntry[] = []
  for (let i = 0; i < days; i++) {
    const d = new Date()
    d.setDate(d.getDate() - i)
    entries.push({
      date: d.toISOString().split('T')[0],
      total: null,
      officers: {},
      unmeasuredReason: reason,
    })
  }
  return entries
}

export async function getCostHistory(days: number): Promise<DailyCostEntry[]> {
  // FW-016: read cabinet:cost:tokens:daily:<date> HSET; sum *_cost_micro
  // per officer and convert microdollars → cents (1 cent = 10000 micro).
  // Legacy cabinet:cost:daily:* and cabinet:cost:officer:*:* keys are gone.
  let officers: string[]
  try {
    const officerKeys = await redis.keys('cabinet:officer:expected:*')
    officers = officerKeys
      .map(k => k.replace('cabinet:officer:expected:', ''))
      .filter(k => !k.includes(':'))
  } catch (err) {
    // Losing the roster loses the whole window: without officers there is
    // nothing to sum, and returning an empty history would render 30 days of
    // silence as 30 days of nothing spent.
    return unreadCostHistory(days, storeFailureReason(err))
  }
  if (officers.length === 0) officers.push('cos', 'cto', 'cpo', 'cro', 'coo')

  const entries: DailyCostEntry[] = []

  for (let i = 0; i < days; i++) {
    const d = new Date()
    d.setDate(d.getDate() - i)
    const dateStr = d.toISOString().split('T')[0]

    try {
      const hash = await redis.hgetall(`cabinet:cost:tokens:daily:${dateStr}`)
      entries.push({ date: dateStr, ...sumDailyCost(hash, officers) })
    } catch (err) {
      entries.push({
        date: dateStr,
        total: null,
        officers: {},
        unmeasuredReason: storeFailureReason(err),
      })
    }
  }

  return entries
}

export interface TokenCostEntry {
  date: string
  officers: Record<string, {
    input: number
    output: number
    cacheWrite: number
    cacheRead: number
    costMicro: number
  }>
  /** NULL = no token record for this date. A measured zero is `0`. */
  totalCostMicro: number | null
}

/** N days of "nobody asked", in the token shape. `null` total, empty officers. */
function unreadTokenHistory(days: number): TokenCostEntry[] {
  const entries: TokenCostEntry[] = []
  for (let i = 0; i < days; i++) {
    const d = new Date()
    d.setDate(d.getDate() - i)
    entries.push({
      date: d.toISOString().split('T')[0],
      officers: {},
      totalCostMicro: null,
    })
  }
  return entries
}

export async function getTokenCostHistory(days: number): Promise<TokenCostEntry[]> {
  let officers: string[]
  try {
    const officerKeys = await redis.keys('cabinet:officer:expected:*')
    officers = officerKeys
      .map(k => k.replace('cabinet:officer:expected:', ''))
      .filter(k => !k.includes(':'))
  } catch {
    return unreadTokenHistory(days)
  }
  if (officers.length === 0) officers.push('cos', 'cto', 'cpo', 'cro', 'coo')

  const entries: TokenCostEntry[] = []

  for (let i = 0; i < days; i++) {
    const d = new Date()
    d.setDate(d.getDate() - i)
    const dateStr = d.toISOString().split('T')[0]

    let hash: Record<string, string> | null
    try {
      hash = await redis.hgetall(`cabinet:cost:tokens:daily:${dateStr}`)
    } catch {
      // Same rule as `getCostHistory`: a day nobody could ask about is null,
      // never a zeroed roster that plots as a real bar of height zero.
      entries.push({ date: dateStr, officers: {}, totalCostMicro: null })
      continue
    }
    if (!hash || Object.keys(hash).length === 0) {
      entries.push({ date: dateStr, officers: {}, totalCostMicro: null })
      continue
    }
    const officerData: TokenCostEntry['officers'] = {}
    let totalCostMicro = 0

    // FW-072 / S3 (Pool Phase 1A): cost field shape is now either legacy
    // `<officer>_<dim>` (pre-pool) OR per-project `<officer>_<project>_<dim>`
    // (pool mode). Sum both shapes per officer per dimension.
    for (const role of officers) {
      const dims = ['input', 'output', 'cache_write', 'cache_read', 'cost_micro']
      const sums: Record<string, number> = { input: 0, output: 0, cache_write: 0, cache_read: 0, cost_micro: 0 }
      for (const [field, value] of Object.entries(hash)) {
        // Match `<role>_<dim>` (legacy) or `<role>_<projslug>_<dim>` (pool).
        for (const dim of dims) {
          if (field === `${role}_${dim}` || (field.startsWith(`${role}_`) && field.endsWith(`_${dim}`))) {
            sums[dim] += parseInt(value || '0', 10) || 0
            break
          }
        }
      }
      officerData[role] = {
        input: sums.input,
        output: sums.output,
        cacheWrite: sums.cache_write,
        cacheRead: sums.cache_read,
        costMicro: sums.cost_micro,
      }
      totalCostMicro += sums.cost_micro
    }

    entries.push({ date: dateStr, officers: officerData, totalCostMicro })
  }

  return entries
}

export async function getScheduleLastRuns(): Promise<Record<string, string>> {
  let keys: string[]
  try {
    keys = await redis.keys('cabinet:schedule:last-run:*')
  } catch {
    // An empty map renders every job's last run as absent, which the cron table
    // already draws honestly; the page-level banner says why. Letting the throw
    // out would 500 the whole page — there are no error boundaries in this app,
    // so an uncaught throw in a server component is a blank screen, not a
    // disclosure.
    return {}
  }
  const result: Record<string, string> = {}
  for (const key of keys) {
    try {
      const val = await redis.get(key)
      if (val) {
        const shortKey = key.replace('cabinet:schedule:last-run:', '')
        result[shortKey] = val
      }
    } catch {
      // One unreadable key must not lose the ones that DID answer.
      continue
    }
  }
  return result
}
