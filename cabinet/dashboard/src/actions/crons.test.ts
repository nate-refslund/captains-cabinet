/**
 * THE REAL HANDLERS, END TO END — no mock of the crontab plane at all.
 *
 * Every arm below calls the exported server action, which builds its own
 * `CrontabIO`, which `spawn`s `docker`, which execs `crontab`. Both programs are
 * real executables this file writes to a temp dir and puts on PATH, so the exit
 * codes, the pipe and the file are real. The only mocks are `next/cache` and the
 * auth guard — neither is part of the defect.
 *
 * WHY NOT A MOCKED IO. `lib/crontab.test.ts` already drives every transform and
 * every commit branch through an injected `CrontabIO`; that proves the
 * algorithm. It cannot prove the process boundary, and the process boundary is
 * where the whole defect lived: a shell pipeline whose exit status came from its
 * LAST stage. An arm that mocks the boundary would be a sensor pointed at a twin
 * of the thing it is supposed to watch — the dominant failure in this program.
 *
 * RED AGAINST PRE-CHANGE CODE. Every arm named "reports the failure" fails
 * against `origin/master`'s `actions/crons.ts`, which returned
 * `{ success: true }` from all five write sites. Measured, with the transcript
 * in the PR.
 */
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))

const { mockAuth } = vi.hoisted(() => ({ mockAuth: vi.fn<() => Promise<boolean>>() }))
vi.mock('@/lib/provisioning/guard', () => ({ requireDashboardAuth: mockAuth }))

// ---------------------------------------------------------------------------
// A real `crontab` and a real `docker`, written to disk and put on PATH.
// ---------------------------------------------------------------------------

const BIN = fs.mkdtempSync(path.join(os.tmpdir(), 'cron-bin-'))

/**
 * vixie-cron's contract, as far as this code depends on it:
 *   -l  prints the crontab; with none installed it prints "no crontab for
 *       <user>" on stderr and EXITS 1.
 *   -   installs stdin.
 * The flag files are how an arm injects a failure into a program that is
 * otherwise behaving exactly like the real one.
 */
fs.writeFileSync(
  path.join(BIN, 'crontab'),
  `#!/bin/sh
F="\${CRONTAB_FILE:?}"
case "$1" in
  -l)
    [ -f "$F.fail-list" ] && { echo "crontab: cannot open spool: Permission denied" >&2; exit 1; }
    [ -f "$F" ] || { echo "no crontab for cabinet" >&2; exit 1; }
    cat "$F" ;;
  -)
    [ -f "$F.drop-write" ] && { cat > /dev/null; exit 0; }
    [ -f "$F.reject-write" ] && { cat > /dev/null; echo "crontab: errors in crontab file, can't install" >&2; exit 1; }
    cat > "$F.tmp" && mv "$F.tmp" "$F" ;;
  *) echo "crontab: usage" >&2; exit 2 ;;
esac
`,
  { mode: 0o755 }
)

/** `docker exec [-i] <container> <argv...>` → run <argv...> here. */
fs.writeFileSync(
  path.join(BIN, 'docker'),
  `#!/bin/sh
[ "$1" = exec ] || { echo "docker: unsupported" >&2; exit 1; }
shift
while [ $# -gt 0 ]; do case "$1" in -i|-t|-it) shift ;; -u) shift 2 ;; *) break ;; esac; done
[ -f "$DOCKER_NO_CONTAINER" ] && { echo "Error response from daemon: No such container: $1" >&2; exit 1; }
shift
exec "$@"
`,
  { mode: 0o755 }
)

afterAll(() => fs.rmSync(BIN, { recursive: true, force: true }))

const SEED = [
  '# Health check',
  '*/5 * * * * /opt/watchdog/health-check.sh',
  '# Morning briefing',
  '0 6 * * * /opt/watchdog/morning-briefing.sh',
  '0 18 * * * /opt/watchdog/evening-briefing.sh',
  '',
].join('\n')

let ct: string
const read = () => (fs.existsSync(ct) ? fs.readFileSync(ct, 'utf8') : '<<ABSENT>>')
const jobCount = () =>
  read()
    .split('\n')
    .filter((l) => l.trim() && !l.trim().startsWith('#')).length
const flag = (name: string, on = true) => {
  const p = `${ct}.${name}`
  if (on) fs.writeFileSync(p, '')
  else fs.rmSync(p, { force: true })
}

const fd = (o: Record<string, string>) => {
  const f = new FormData()
  for (const [k, v] of Object.entries(o)) f.append(k, v)
  return f
}

beforeEach(() => {
  vi.resetModules()
  mockAuth.mockResolvedValue(true)
  ct = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'ct-')), 'crontab')
  fs.writeFileSync(ct, SEED)
  vi.stubEnv('CRONTAB_FILE', ct)
  vi.stubEnv('PATH', `${BIN}:${process.env.PATH}`)
  // live posture, docker runtime: the deployment the crontab path is for
  vi.stubEnv('REDIS_URL', 'redis://127.0.0.1:1')
  vi.stubEnv('MOCK_DATA', '')
  vi.stubEnv('CABINET_DEMO_DATA', '')
  vi.stubEnv('CABINET_RUNTIME_MODE', 'docker')
  vi.stubEnv('NODE_ENV', 'test')
})
afterEach(() => vi.unstubAllEnvs())

const load = () => import('./crons')

const update = (o: Record<string, string>) => load().then((m) => m.updateCronSchedule(null, fd(o)))
const add = (o: Record<string, string>) => load().then((m) => m.addCronJob(null, fd(o)))
const del = (o: Record<string, string>) => load().then((m) => m.deleteCronJob(null, fd(o)))

const MORNING = { originalSchedule: '0 6 * * *', command: '/opt/watchdog/morning-briefing.sh' }

describe('the writes that used to lie', () => {
  it('R1 the read fails → refusal, and the schedule is NOT destroyed', async () => {
    // PRE-CHANGE: `{success:true}`, crontab emptied — 3 jobs to 0, photographed.
    flag('fail-list')
    const res = await update({ ...MORNING, schedule: '0 7 * * *' })
    flag('fail-list', false)
    expect(res.success).toBeUndefined()
    expect(res.error).toMatch(/could not be read, so nothing was changed/)
    expect(read()).toBe(SEED)
    expect(jobCount()).toBe(3)
  })

  it('R1b the same, on add — the new job does not replace every existing one', async () => {
    flag('fail-list')
    const res = await add({ schedule: '*/30 * * * *', command: '/opt/watchdog/new.sh', description: 'New' })
    flag('fail-list', false)
    expect(res.error).toMatch(/could not be read/)
    expect(read()).toBe(SEED)
  })

  it('R1c the same, on delete', async () => {
    flag('fail-list')
    const res = await del({ schedule: '0 6 * * *', command: '/opt/watchdog/morning-briefing.sh' })
    flag('fail-list', false)
    expect(res.error).toMatch(/could not be read/)
    expect(read()).toBe(SEED)
  })

  it('R2 nothing matches → refusal naming the line it looked for', async () => {
    const res = await update({
      originalSchedule: '0 3 * * *',
      command: '/opt/watchdog/nothing.sh',
      schedule: '0 7 * * *',
    })
    expect(res.success).toBeUndefined()
    expect(res.error).toMatch(/no line in the crontab reads "0 3 \* \* \* \/opt\/watchdog\/nothing.sh"/)
    expect(read()).toBe(SEED)
  })

  it('R4 delete removes the named job ONLY — never every job sharing the minute', async () => {
    fs.appendFileSync(ct, '# Nightly backup\n0 6 * * * /opt/watchdog/backup.sh\n')
    const res = await del({ schedule: '0 6 * * *', command: '/opt/watchdog/morning-briefing.sh' })
    expect(res).toEqual({ success: true })
    expect(read()).toContain('/opt/watchdog/backup.sh')
    expect(read()).not.toContain('morning-briefing')
  })

  it('R5 deleting something that is not there → refusal', async () => {
    const res = await del({ schedule: '9 9 9 9 9', command: '/ghost.sh' })
    expect(res.success).toBeUndefined()
    expect(res.error).toMatch(/nothing was deleted/)
  })

  it('R6 the write is accepted and dropped → failure, and the pre-image is restored', async () => {
    flag('drop-write')
    const res = await add({ schedule: '*/30 * * * *', command: '/opt/watchdog/new.sh', description: '' })
    flag('drop-write', false)
    expect(res.success).toBeUndefined()
    expect(res.error).toMatch(/did not take/)
    expect(read()).toBe(SEED)
  })

  it('R6b the write is refused by cron → the refusal is reported verbatim', async () => {
    flag('reject-write')
    const res = await add({ schedule: '*/30 * * * *', command: '/opt/watchdog/new.sh' })
    flag('reject-write', false)
    expect(res.success).toBeUndefined()
    expect(res.error).toMatch(/errors in crontab file/)
    expect(read()).toBe(SEED)
  })

  it('R7 demo mode says so instead of reporting a bare save', async () => {
    vi.stubEnv('CABINET_DEMO_DATA', 'true')
    const res = await update({ ...MORNING, schedule: '0 7 * * *' })
    expect(res.success).toBe(true)
    expect(res.note).toMatch(/nothing was written to any schedule/)
    expect(read()).toBe(SEED)
  })

  /**
   * The assertion here is deliberately narrow, and the first version of it was
   * a FALSE GREEN caught by mutation: removing the refusal entirely still left
   * `/launchd/` matching, because the transform's own "no line in the crontab
   * reads \"launchd com.cabinet.officer.cos\"" refusal contains the word too.
   * The arm was measuring a different control from the one it names, which is
   * the exact defect class this whole change is about. It now matches a phrase
   * only the runtime refusal uses.
   */
  it('R8 a launchd deployment refuses instead of writing to a crontab nobody is looking at', async () => {
    vi.stubEnv('CABINET_RUNTIME_MODE', 'native')
    for (const call of [
      update({ originalSchedule: 'launchd', command: 'com.cabinet.officer.cos', schedule: '0 7 * * *' }),
      add({ schedule: '0 7 * * *', command: '/opt/watchdog/new.sh' }),
      del({ schedule: '*/5 * * * *', command: '/opt/watchdog/health-check.sh' }),
    ]) {
      const res = await call
      expect(res.success).toBeUndefined()
      expect(res.error).toMatch(/schedules with launchd, not cron/)
      expect(res.error).toMatch(/launchctl/)
    }
    expect(read()).toBe(SEED)
  })

  it('R9 no crontab binary / no container → an honest error, never a claim', async () => {
    vi.stubEnv('DOCKER_NO_CONTAINER', `${ct}`) // the file exists, so docker refuses
    const res = await add({ schedule: '0 1 * * *', command: '/a.sh' })
    expect(res.success).toBeUndefined()
    expect(res.error).toMatch(/No such container|could not be read/)
    expect(read()).toBe(SEED)
  })
})

describe('the inverse — a write that genuinely lands still reports success', () => {
  it('update', async () => {
    const res = await update({ ...MORNING, schedule: '0 7 * * *' })
    expect(res).toEqual({ success: true })
    expect(read()).toContain('0 7 * * * /opt/watchdog/morning-briefing.sh')
    expect(jobCount()).toBe(3)
  })

  it('add', async () => {
    const res = await add({ schedule: '*/30 * * * *', command: '/opt/watchdog/new.sh', description: 'New' })
    expect(res).toEqual({ success: true })
    expect(read()).toContain('# New')
    expect(jobCount()).toBe(4)
  })

  it('delete', async () => {
    const res = await del({ schedule: '0 18 * * *', command: '/opt/watchdog/evening-briefing.sh' })
    expect(res).toEqual({ success: true })
    expect(jobCount()).toBe(2)
  })

  it('the FIRST job, when no crontab is installed at all', async () => {
    fs.rmSync(ct)
    const res = await add({ schedule: '0 1 * * *', command: '/a.sh' })
    expect(res).toEqual({ success: true })
    expect(read()).toContain('0 1 * * * /a.sh')
  })
})

describe('auth', () => {
  it('unauthenticated → Unauthorized, and the schedule is never touched', async () => {
    mockAuth.mockResolvedValue(false)
    for (const call of [
      update({ ...MORNING, schedule: '0 7 * * *' }),
      add({ schedule: '0 1 * * *', command: '/a.sh' }),
      del({ schedule: '0 6 * * *', command: '/opt/watchdog/morning-briefing.sh' }),
    ]) {
      expect((await call).error).toBe('Unauthorized')
    }
    expect(read()).toBe(SEED)
  })

  it('the auth gate is checked BEFORE the demo short-circuit', async () => {
    mockAuth.mockResolvedValue(false)
    vi.stubEnv('CABINET_DEMO_DATA', 'true')
    expect((await update({ ...MORNING, schedule: '0 7 * * *' })).error).toBe('Unauthorized')
  })
})

// ---------------------------------------------------------------------------
// The officer-task timers. Store writes, so the crontab bins are irrelevant.
// ---------------------------------------------------------------------------

describe('officer task timers', () => {
  const setup = async (posture: 'live' | 'unconfigured') => {
    const store: Record<string, string> = {}
    if (posture === 'live') vi.stubEnv('REDIS_URL', 'redis://127.0.0.1:1')
    else vi.stubEnv('REDIS_URL', '')
    vi.doMock('@/lib/redis', () => ({
      default: {
        get: async (k: string) => store[k] ?? null,
        set: async (k: string, v: string) => {
          store[k] = v
          return 'OK'
        },
        del: async (k: string) => {
          delete store[k]
          return 1
        },
      },
      isMockRedis: posture !== 'live',
      storeReading: {
        posture,
        source: posture === 'live' ? 'the configured store' : 'no store is configured (REDIS_URL unset)',
        fabricated: false,
      },
    }))
    return { mod: await import('./crons'), store }
  }

  it('live: reset writes and proves it', async () => {
    const { mod, store } = await setup('live')
    expect(await mod.resetTaskTimer('cos', 'reflection')).toEqual({ success: true })
    expect(store['cabinet:schedule:last-run:cos:reflection']).toBeTruthy()
  })

  it('live: delete removes and proves the absence', async () => {
    const { mod, store } = await setup('live')
    store['cabinet:schedule:last-run:cos:reflection'] = 'x'
    expect(await mod.deleteTaskTimer('cos', 'reflection')).toEqual({ success: true })
    expect(store['cabinet:schedule:last-run:cos:reflection']).toBeUndefined()
  })

  it('live: a write the store does not keep is reported, not claimed', async () => {
    vi.stubEnv('REDIS_URL', 'redis://127.0.0.1:1')
    vi.doMock('@/lib/redis', () => ({
      default: { get: async () => null, set: async () => 'OK', del: async () => 1 },
      isMockRedis: false,
      storeReading: { posture: 'live', source: 'the configured store', fabricated: false },
    }))
    const mod = await import('./crons')
    const res = await mod.resetTaskTimer('cos', 'reflection')
    expect(res.success).toBeUndefined()
    expect(res.error).toMatch(/did not take/)
  })

  it('live: a delete the store does not honour is reported', async () => {
    vi.stubEnv('REDIS_URL', 'redis://127.0.0.1:1')
    vi.doMock('@/lib/redis', () => ({
      default: { get: async () => 'still-here', set: async () => 'OK', del: async () => 1 },
      isMockRedis: false,
      storeReading: { posture: 'live', source: 'the configured store', fabricated: false },
    }))
    const mod = await import('./crons')
    const res = await mod.deleteTaskTimer('cos', 'reflection')
    expect(res.success).toBeUndefined()
    expect(res.error).toMatch(/was not deleted/)
  })

  /**
   * THE ARM A READ-BACK ALONE CANNOT PASS.
   *
   * With no REDIS_URL, `lib/redis.ts` hands out an in-process object: `set`
   * then `get` returns exactly what was written, so a read-back-only fix
   * REPORTS SUCCESS about a cabinet this process has never contacted. Only the
   * posture check can tell the difference — which is why the killswitch's
   * pattern was copied WITH an addition rather than as-is.
   */
  it('unconfigured: refuses, even though a read-back would have passed', async () => {
    const { mod, store } = await setup('unconfigured')
    const res = await mod.resetTaskTimer('cos', 'reflection')
    expect(res.success).toBeUndefined()
    expect(res.error).toMatch(/not connected to a cabinet/)
    expect(Object.keys(store)).toHaveLength(0)
    // the in-process store WOULD have echoed the write back:
    expect(await mod.deleteTaskTimer('cos', 'reflection')).toMatchObject({ error: expect.any(String) })
    expect(
      (await mod.createTaskTimer(null, fd({ officer: 'cos', task: 'new-thing' }))).error
    ).toMatch(/not connected to a cabinet/)
  })

  it('a bad task or officer name is rejected before any store write', async () => {
    const { mod, store } = await setup('live')
    expect((await mod.createTaskTimer(null, fd({ officer: 'cos', task: 'Bad Name' }))).error).toMatch(/lowercase/)
    expect((await mod.createTaskTimer(null, fd({ officer: 'co:s', task: 'ok-name' }))).error).toMatch(/lowercase/)
    expect(Object.keys(store)).toHaveLength(0)
  })

  it('unauthenticated timers touch nothing', async () => {
    const { mod, store } = await setup('live')
    mockAuth.mockResolvedValue(false)
    expect(await mod.resetTaskTimer('cos', 'reflection')).toEqual({ error: 'Unauthorized' })
    expect(await mod.deleteTaskTimer('cos', 'reflection')).toEqual({ error: 'Unauthorized' })
    expect(Object.keys(store)).toHaveLength(0)
  })
})
