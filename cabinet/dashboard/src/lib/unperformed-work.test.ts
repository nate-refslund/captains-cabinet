/**
 * THREE PLACES THAT REPORTED WORK THAT DID NOT HAPPEN, EACH WITH ITS INVERSE.
 *
 * Every arm here was RED against the pre-change tree and is GREEN after it; the
 * matching inverse arm is the control, because a change that made everything
 * fail would satisfy every honesty assertion in the file and mean nothing.
 *
 *   1. `lib/attention/verdict.ts` — the bridge's EXIT CODE was never read. Its
 *      only failure branch was `if (err && !stdout)`, so a bridge that printed
 *      `{"ok": true, "plain_result": "Approved — done."}` and then died —
 *      having submitted nothing through the binder wire — resolved as success
 *      and the Captain's queue card showed a completed act. Its two sibling
 *      transports already read it (`lib/onboarding/bridge.ts` rejects
 *      `core_exit`; `lib/evidence/read.ts` refuses any exit outside {0,3,4}).
 *
 *   2. `lib/provisioning/worker.ts:transitionState` — a GUARDED update whose
 *      `rowCount` was discarded (`await query(...)`, and `lib/db.ts` returns
 *      `result.rows`), so a transition that matched ZERO rows left the database
 *      untouched and still wrote a permanent audit row saying it happened.
 *
 *   3. `app/api/cabinets/[id]/archive` — two `console.info` stubs, then an
 *      audit row asserting `peers_yml_atomic: true`. An audit trail recording
 *      an atomicity guarantee for an operation that did not happen is worse
 *      than no audit trail.
 *
 * The suspend/resume routes have the same shape (`{ok:true,state:'suspended'}`
 * committed with `// TODO (PR 4): docker compose stop`) and are deliberately
 * NOT touched here: making them honest needs either a real container transport
 * or a changed status code, and half-landing that would convert a silent hole
 * into a green one.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const saved = {
  CABINET_ROOT: process.env.CABINET_ROOT,
  CABINET_ENV_PATH: process.env.CABINET_ENV_PATH,
  CABINET_RUNTIME_MODE: process.env.CABINET_RUNTIME_MODE,
  CABINET_PREFIX: process.env.CABINET_PREFIX,
  CABINET_PYTHON: process.env.CABINET_PYTHON,
  CABINET_ATTENTION_DIR: process.env.CABINET_ATTENTION_DIR,
  REDIS_URL: process.env.REDIS_URL,
  MOCK_DATA: process.env.MOCK_DATA,
  CABINET_DEMO_DATA: process.env.CABINET_DEMO_DATA,
  DATABASE_URL: process.env.DATABASE_URL,
  NEON_CONNECTION_STRING: process.env.NEON_CONNECTION_STRING,
  PATH: process.env.PATH,
}

let root: string

/** Every write and every spawn is proven to land inside the temp tree first. */
function sandbox(): void {
  root = mkdtempSync(path.join(tmpdir(), 'unperformed-'))
  mkdirSync(path.join(root, 'bin'), { recursive: true })
  mkdirSync(path.join(root, 'cabinet'), { recursive: true })
  process.env.CABINET_ROOT = root
  process.env.CABINET_RUNTIME_MODE = 'native'
  process.env.CABINET_ENV_PATH = path.join(root, 'cabinet', '.env')
  process.env.CABINET_ATTENTION_DIR = path.join(root, 'attention')
  process.env.CABINET_PREFIX = 'unperformed-test'
  delete process.env.REDIS_URL
  delete process.env.MOCK_DATA
  delete process.env.CABINET_DEMO_DATA
  delete process.env.CABINET_PYTHON
  // Unusable on purpose: nothing here may open a socket even if a stub failed.
  process.env.DATABASE_URL = 'postgres://t:t@invalid.invalid:1/t'
  process.env.NEON_CONNECTION_STRING = process.env.DATABASE_URL
  // Only the shim dir is on PATH, so `python3.12` can only be ours.
  process.env.PATH = path.join(root, 'bin')
  for (const [k, v] of Object.entries(process.env)) {
    if (k.startsWith('CABINET_') && typeof v === 'string' && path.isAbsolute(v)) {
      if (!v.startsWith(root)) throw new Error(`refusing to run: ${k}=${v} is outside the temp tree`)
    }
  }
  if (!process.env.PATH.startsWith(root)) {
    throw new Error('refusing to run: PATH is not the temp shim dir')
  }
}

function shim(name: string, body: string): void {
  const p = path.join(root, 'bin', name)
  if (!p.startsWith(root + path.sep)) throw new Error('refusing to write outside the temp tree')
  writeFileSync(p, body)
  chmodSync(p, 0o755)
}

/** The pg calls the provisioning plane made, in order. */
const sql: Array<{ text: string; values?: unknown[] }> = []
const table: Record<string, { state: string }> = {}
let sweepRows: Array<{ cabinet_id: string; state: string }> = []
let lastUpdateRowCount: number | null = null

function applyGuardedUpdate(text: string, values?: unknown[]): number {
  const [to, cabinet_id, from] = (values ?? []) as string[]
  const row = table[cabinet_id]
  if (/UPDATE cabinets\s+SET state = \$1/i.test(text) && row && row.state === from) {
    row.state = to
    return 1
  }
  return 0
}

vi.mock('@/lib/db', () => ({
  query: async (text: string, values?: unknown[]) => {
    sql.push({ text, values })
    if (/SELECT cabinet_id, state FROM cabinets/i.test(text)) return sweepRows
    if (/UPDATE cabinets SET state = 'archived'/i.test(text)) return []
    return []
  },
  getDbPool: () => ({
    query: async (text: string, values?: unknown[]) => {
      sql.push({ text, values })
      const rowCount = applyGuardedUpdate(text, values)
      lastUpdateRowCount = rowCount
      return { rows: [], rowCount }
    },
    connect: async () => ({
      query: async () => ({ rows: [], rowCount: 0 }),
      release: () => {},
    }),
  }),
}))

vi.mock('@/lib/redis', () => ({
  default: { get: async () => null, set: async () => 'OK', del: async () => 1, publish: async () => 0 },
  isMockRedis: false,
  storeReading: { posture: 'live', source: 'the configured store', fabricated: false },
}))

interface AuditRow {
  cabinet_id: string
  state_before: string | null
  state_after: string | null
  payload: Record<string, unknown>
}
function auditRows(): AuditRow[] {
  return sql
    .filter((c) => /INSERT INTO cabinet_provisioning_events/i.test(c.text))
    .map((c) => {
      const v = (c.values ?? []) as unknown[]
      return {
        cabinet_id: v[0] as string,
        state_before: v[4] as string | null,
        state_after: v[5] as string | null,
        payload: JSON.parse((v[6] as string) || '{}'),
      }
    })
}

beforeEach(() => {
  vi.resetModules()
  sql.length = 0
  for (const k of Object.keys(table)) delete table[k]
  sweepRows = []
  lastUpdateRowCount = null
  sandbox()
})

afterEach(() => {
  for (const [k, v] of Object.entries(saved)) {
    if (v === undefined) delete process.env[k]
    else process.env[k] = v as string
  }
  try {
    rmSync(root, { recursive: true, force: true })
  } catch {
    /* disposable */
  }
  vi.resetModules()
})

// ---------------------------------------------------------------------------
// 1. The verdict bridge's exit code.
// ---------------------------------------------------------------------------

/** Prints a well-formed success, then dies. Nothing reached the binder wire. */
const CRASHES_AFTER_PRINTING = [
  '#!/bin/sh',
  // `while read` is a BUILTIN. PATH is clamped to the temp shim dir, so `cat`
  // is not on it — the shim used to exit instantly, and whether the parent's
  // stdin write lost the race was a property of the machine. It raised an
  // unhandled EPIPE on the CI runner and not on this Mac.
  'while read -r _line; do :; done',
  `printf '%s\\n' '{"ok": true, "plain_result": "Approved — done.", "receipt_seq": 42}'`,
  'exit 1',
  '',
].join('\n')

/** The same success, and a clean exit. */
const SUCCEEDS = [
  '#!/bin/sh',
  // `while read` is a BUILTIN. PATH is clamped to the temp shim dir, so `cat`
  // is not on it — the shim used to exit instantly, and whether the parent's
  // stdin write lost the race was a property of the machine. It raised an
  // unhandled EPIPE on the CI runner and not on this Mac.
  'while read -r _line; do :; done',
  `printf '%s\\n' '{"ok": true, "plain_result": "Approved — done.", "receipt_seq": 42}'`,
  'exit 0',
  '',
].join('\n')

describe("the Captain's verdict is not confirmed by a bridge that died", () => {
  it('a bridge that is GONE before the request is written fails, and does not crash us', async () => {
    // The degenerate end of the same race, made deterministic: the child exits
    // before reading a byte, so `child.stdin.end()` writes to a dead pipe.
    // Unhandled, that EPIPE is fatal to the whole Node process — the dashboard,
    // not just this request.
    // DETERMINISTIC ON BOTH PLATFORMS, and it took three tries to get there.
    // A bare `exit 3` reproduced on the Linux runner and NOT on this Mac: the
    // parent usually finished its small write before the child's shell had even
    // started, so the arm passed with the guard removed — a fence that cannot
    // fail on the machine you are running it on is not a fence. `exec 0<&-` did
    // not fix that, for the same reason. What does is a request LARGER than the
    // pipe buffer: the write cannot complete in one go, so it is still in
    // flight when the child exits, and the dead pipe is reached on any platform.
    shim('python3.12', ['#!/bin/sh', 'exit 3', ''].join('\n'))
    const { spawnBridge } = await import('@/lib/attention/verdict')
    const r = await spawnBridge({
      op: 'fire',
      pid: 'p1',
      verb: 'approve',
      revision: 'r1',
      // 2 MiB — comfortably past the 64 KiB pipe buffer on macOS and Linux.
      _pad: 'x'.repeat(2 * 1024 * 1024),
    })
    expect(r.ok).toBe(false)
    expect(r.code).toBe('bridge_fail')
  })

  it('a bridge that exits non-zero is a failure, however well-formed its stdout', async () => {
    shim('python3.12', CRASHES_AFTER_PRINTING)
    const { spawnBridge } = await import('@/lib/attention/verdict')
    const r = await spawnBridge({ op: 'fire', pid: 'p1', verb: 'approve', revision: 'r1' })
    expect(r.ok).toBe(false)
    expect(r.code).toBe('bridge_fail')
  })

  it('THE INVERSE — a bridge that exits 0 is still reported as the success it is', async () => {
    shim('python3.12', SUCCEEDS)
    const { spawnBridge } = await import('@/lib/attention/verdict')
    const r = await spawnBridge({ op: 'fire', pid: 'p1', verb: 'approve', revision: 'r1' })
    expect(r.ok).toBe(true)
    expect(r.plain_result).toBe('Approved — done.')
    expect(r.receipt_seq).toBe(42)
  })
})

// ---------------------------------------------------------------------------
// 2. The guarded UPDATE's rowCount.
// ---------------------------------------------------------------------------

describe('a state transition the database refused is not recorded as one', () => {
  it('zero matched rows: nothing is audited, and the caller is told', async () => {
    // The sweep read `creating`; by write time a concurrent writer has moved
    // the row, so `AND state = 'creating'` matches nothing.
    table['cab_race'] = { state: 'adopting-bots' }
    sweepRows = [{ cabinet_id: 'cab_race', state: 'creating' }]
    const { runBootSweep } = await import('@/lib/provisioning/worker')
    await runBootSweep()

    expect(lastUpdateRowCount).toBe(0)
    expect(table['cab_race'].state).toBe('adopting-bots')
    expect(auditRows().filter((r) => r.state_after === 'failed')).toHaveLength(0)
  })

  it('THE INVERSE — a transition that DOES apply still moves the row and audits it', async () => {
    table['cab_ok'] = { state: 'creating' }
    sweepRows = [{ cabinet_id: 'cab_ok', state: 'creating' }]
    const { runBootSweep } = await import('@/lib/provisioning/worker')
    await runBootSweep()

    expect(lastUpdateRowCount).toBe(1)
    expect(table['cab_ok'].state).toBe('failed')
    expect(auditRows().map((r) => r.state_after)).toContain('failed')
  })

  it('the guard is still IN the SQL — this is not a fix that dropped the WHERE clause', async () => {
    table['cab_ok2'] = { state: 'creating' }
    sweepRows = [{ cabinet_id: 'cab_ok2', state: 'creating' }]
    const { runBootSweep } = await import('@/lib/provisioning/worker')
    await runBootSweep()
    const update = sql.find((c) => /UPDATE cabinets\s+SET state = \$1/i.test(c.text))
    expect(update?.text).toMatch(/WHERE cabinet_id = \$2 AND state = \$3/)
  })
})

// ---------------------------------------------------------------------------
// 3. The archive audit row.
// ---------------------------------------------------------------------------

describe('the archive audit row does not certify work nothing performed', () => {
  it('no peers_yml_atomic, and the unperformed steps are named in the row', async () => {
    const { runArchivalSteps } = await import('@/app/api/cabinets/[id]/archive/route')
    await runArchivalSteps('cab_archive', 'captain')

    const row = auditRows().find((r) => r.state_after === 'archived')
    expect(row, 'the row still moves to archived — that part the Captain asked for').toBeDefined()
    expect(row!.payload).not.toHaveProperty('peers_yml_atomic')
    // The honest replacement is not merely the ABSENCE of the false claim: a
    // reader of this row has to learn what is still outstanding.
    expect(Array.isArray(row!.payload.unperformed)).toBe(true)
    expect((row!.payload.unperformed as string[]).join(' ')).toMatch(/peers\.yml/)
    expect((row!.payload.unperformed as string[]).join(' ')).toMatch(/containers/)
  })

  it('THE INVERSE — the state transition itself still happens', async () => {
    const { runArchivalSteps } = await import('@/app/api/cabinets/[id]/archive/route')
    await runArchivalSteps('cab_archive2', 'captain')
    expect(sql.some((c) => /UPDATE cabinets SET state = 'archived'/i.test(c.text))).toBe(true)
  })
})
