/**
 * THE WRITE-LIE SWEEP, DRIVEN — every action that shells out, with no store.
 *
 * WHY THIS FILE EXISTS. `lib/docker.ts` answered `{ stdout: 'mock: command
 * executed', stderr: '' }` for every command it declined to run, and 19 write
 * actions turned that resolved value into `{ success: true }`. Counted, then
 * photographed against the BUILT app in `NODE_ENV=production` with `REDIS_URL`
 * unset: `/officers/create` rendered "Officer Created · the officer is booting
 * and will announce on the warroom shortly" with `create-officer.sh` never
 * invoked, and `/integrations` closed its add-secret modal on success with
 * `cabinet/.env` byte-identical afterwards. Both underneath the app's own
 * banner, "NO STORE CONFIGURED — nothing here is a measurement".
 *
 * The fix is one rejection at the source, so this file is the sensor that says
 * the source is still the source: it drives the REAL action modules — no
 * `dockerExec` mock, no fixture stdout — and fails if any of them reports
 * success for work that did not happen.
 *
 * WHAT IT DELIBERATELY DOES NOT MOCK. `@/lib/docker` and `@/lib/store-posture`
 * are the code under test and are loaded for real; the posture is set the only
 * way production sets it, through the environment. Auth and `next/cache` ARE
 * mocked — they are the harness, not the subject.
 *
 * THE INVERSE ARM IS NOT OPTIONAL. A change that made everything fail would
 * satisfy every refusal arm here, so the last block runs a command that
 * genuinely succeeds, against a real temp checkout, and asserts BOTH the
 * reported success and the bytes on disk. It uses `echo >>` rather than
 * `sed -i` on purpose: BSD `sed -i` takes a mandatory suffix argument and would
 * make this arm pass on CI's GNU userland and fail on the Captain's Mac, which
 * is an environment lie rather than a measurement.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/provisioning/guard', () => ({
  requireDashboardAuth: async () => true,
  requireProvisioningAccess: async () => true,
}))
// The store CLIENT is stubbed so the sweep never opens a socket; the store
// POSTURE — the thing under test — is left to the environment.
vi.mock('@/lib/redis', () => ({
  default: {
    get: async () => null,
    set: async () => 'OK',
    del: async () => 1,
    keys: async () => [],
  },
  isMockRedis: false,
  storeReading: { posture: 'live', source: 'the configured store', fabricated: false },
}))

/**
 * EVERY env var that can steer a write OUT of the temp tree, saved and
 * overridden. `CABINET_ENV_PATH` is here because leaving it out was a real,
 * proven hazard rather than an oversight: `actions/env.ts` reads it at module
 * scope, `cabinet/scripts/start-dashboard.sh` exports it, and the inverse block
 * below runs a REAL `echo >> $ENV_PATH`. Reproduced during review —
 * `CABINET_ENV_PATH=victim.env npx vitest run` appended `SWEEP_INVERSE_KEY` and
 * `EXISTING_KEY=second-copy` to that file. On a configured box that file is
 * `cabinet/.env`: the Anthropic key, every Telegram bot token, the GitHub PAT.
 * A test that writes for real must own every input that decides WHERE.
 */
const saved = {
  REDIS_URL: process.env.REDIS_URL,
  MOCK_DATA: process.env.MOCK_DATA,
  CABINET_DEMO_DATA: process.env.CABINET_DEMO_DATA,
  CABINET_ROOT: process.env.CABINET_ROOT,
  CABINET_RUNTIME_MODE: process.env.CABINET_RUNTIME_MODE,
  CABINET_ENV_PATH: process.env.CABINET_ENV_PATH,
}

let root: string

/** A real checkout-shaped tree, so a LIVE command has something true to do. */
function makeRoot(): string {
  const dir = mkdtempSync(path.join(tmpdir(), 'cabinet-sweep-'))
  mkdirSync(path.join(dir, 'cabinet'), { recursive: true })
  mkdirSync(path.join(dir, 'instance', 'config', 'projects'), { recursive: true })
  writeFileSync(path.join(dir, 'cabinet', '.env'), 'EXISTING_KEY=already-here\n')
  writeFileSync(
    path.join(dir, 'instance', 'config', 'product.yml'),
    'product:\n  name: Before\n'
  )
  writeFileSync(path.join(dir, 'instance', 'config', 'active-project.txt'), 'demo\n')
  writeFileSync(path.join(dir, 'instance', 'config', 'projects', 'demo.yml'), 'product:\n  name: Demo\n')
  return dir
}

/** No store configured — the posture that is reachable on a production deploy. */
function unconfigured() {
  delete process.env.REDIS_URL
  delete process.env.MOCK_DATA
  delete process.env.CABINET_DEMO_DATA
  sandboxPaths()
}

/** Point every write target at the temp tree, then PROVE it points there. */
function sandboxPaths() {
  process.env.CABINET_ROOT = root
  process.env.CABINET_RUNTIME_MODE = 'native'
  process.env.CABINET_ENV_PATH = path.join(root, 'cabinet', '.env')
  // The assertion is the control. A future edit that adds another path-steering
  // variable, or reorders these, fails here rather than in somebody's secrets.
  if (!process.env.CABINET_ENV_PATH.startsWith(root)) {
    throw new Error('refusing to run: the env-file path is outside the temp tree')
  }
}

beforeEach(() => {
  vi.resetModules()
  root = makeRoot()
  unconfigured()
})

afterEach(() => {
  for (const [k, v] of Object.entries(saved)) {
    if (v === undefined) delete process.env[k]
    else process.env[k] = v
  }
  vi.resetModules()
  vi.unstubAllEnvs()
  try {
    rmSync(root, { recursive: true, force: true })
  } catch {
    /* the tmpdir is disposable; a failure to remove it is not a test result */
  }
})

const envFile = () => readFileSync(path.join(root, 'cabinet', '.env'), 'utf8')
const productFile = () =>
  readFileSync(path.join(root, 'instance', 'config', 'product.yml'), 'utf8')

/** Every result shape in the app: `{success}` for most, `{ok}` for gaps.ts. */
function claimedSuccess(res: unknown): boolean {
  const r = (res ?? {}) as { success?: unknown; ok?: unknown }
  return r.success === true || r.ok === true
}

/** The one sentence a refusal must carry: nothing happened, and why. */
function saysNothingHappened(res: unknown): boolean {
  const r = (res ?? {}) as { error?: unknown }
  return (
    typeof r.error === 'string' &&
    /nothing was run and nothing was changed|not connected to a cabinet|no store is configured|REDIS_URL/i.test(
      r.error
    )
  )
}

describe('no store configured: not one write action reports success', () => {
  it('config.ts — every YAML field editor refuses, and product.yml is untouched', async () => {
    const before = productFile()
    const m = await import('@/actions/config')
    const results = [
      await m.updateProductConfig('name', 'Renamed'),
      await m.updateGlobalVoiceConfig('enabled', 'true'),
      await m.updateImageGenConfig('enabled', 'true'),
      await m.updateEmbeddingsConfig('provider', 'voyage'),
      await m.updateOfficerVoiceConfig('cos', 'stability', '0.7'),
      await m.updateNotionConfig('enabled', 'true'),
      await m.updateLinearConfig('enabled', 'true'),
      await m.updateCaptainAvailability('full_time'),
    ]
    for (const r of results) {
      expect(claimedSuccess(r)).toBe(false)
      expect(saysNothingHappened(r)).toBe(true)
    }
    expect(productFile()).toBe(before)
  })

  it('env.ts — the secret editor refuses, and cabinet/.env is byte-identical', async () => {
    const before = envFile()
    const m = await import('@/actions/env')
    for (const r of [
      await m.addEnvVar('STRIPE_LIVE_SECRET', 'sk_live_repro'),
      await m.updateEnvVar('EXISTING_KEY', 'changed'),
      await m.deleteEnvVar('EXISTING_KEY'),
    ]) {
      expect(claimedSuccess(r)).toBe(false)
      expect(saysNothingHappened(r)).toBe(true)
    }
    expect(envFile()).toBe(before)
  })

  it('project-config.ts — refuses, and never builds a path out of the no-op answer', async () => {
    // The sentinel used to come back as the ACTIVE PROJECT SLUG, so config
    // edits were aimed at a file called "mock: command executed.yml".
    const m = await import('@/actions/project-config')
    const r = await m.updateProjectConfig('product', 'name', 'Renamed')
    expect(claimedSuccess(r)).toBe(false)
    expect(JSON.stringify(r)).not.toMatch(/mock: command executed/)
  })

  it('projects.ts — switching project refuses; the page never reloads on a switch that did not happen', async () => {
    const m = await import('@/actions/projects')
    expect(claimedSuccess(await m.switchProject('demo'))).toBe(false)
  })

  it('projects.ts — the active project is EMPTY, never the no-op answer rendered as a name', async () => {
    const m = await import('@/actions/projects')
    const active = await m.getActiveProject()
    expect(active).toBe('')
    expect(await m.getProjects()).toEqual([])
  })

  it("gaps.ts — the Captain's approval refuses; the install gate is never told it opened", async () => {
    const m = await import('@/actions/gaps')
    for (const r of [
      await m.approveGap('gap-0123abcd'),
      await m.declineGap('gap-0123abcd', 'no'),
    ]) {
      expect(claimedSuccess(r)).toBe(false)
      expect(saysNothingHappened(r)).toBe(true)
    }
  })

  it('officers.ts — createOfficer refuses; no "Officer Created" for one that does not exist', async () => {
    const m = await import('@/actions/officers')
    const fd = new FormData()
    fd.set('abbreviation', 'cfo')
    fd.set('title', 'Chief Financial Officer')
    fd.set('domain', 'money')
    fd.set('botUsername', 'repro_cfo_bot')
    fd.set('botToken', '7001234:AAErepro-token')
    const r = await m.createOfficer(null, fd)
    expect(claimedSuccess(r)).toBe(false)
    expect(saysNothingHappened(r)).toBe(true)
  })
})

describe('the degenerate ends of the environment', () => {
  it('REDIS_URL="" — present but empty is NOT a store, and still refuses', async () => {
    process.env.REDIS_URL = ''
    const { dockerExec } = await import('@/lib/docker')
    await expect(dockerExec('echo hi')).rejects.toThrow(/nothing was run/i)
  })

  it('REDIS_URL absent in PRODUCTION — refused, and named as a misconfiguration', async () => {
    // The exclusion `demo` always had and `unconfigured` never did. Outside
    // production this is somebody mid-setup; in production it is a broken
    // deploy, and the sentence has to say which.
    vi.stubEnv('NODE_ENV', 'production')
    const { dockerExec } = await import('@/lib/docker')
    await expect(dockerExec('echo hi')).rejects.toThrow(/misconfiguration/i)
    await expect(dockerExec('echo hi')).rejects.toThrow(/REDIS_URL/)
  })

  it('MOCK_DATA=true in PRODUCTION cannot buy the demo posture — it still refuses', async () => {
    vi.stubEnv('NODE_ENV', 'production')
    process.env.MOCK_DATA = 'true'
    const { dockerExec } = await import('@/lib/docker')
    await expect(dockerExec('echo hi')).rejects.toThrow(/misconfiguration/i)
  })

  it('the demo posture refuses too, and says demo rather than misconfigured', async () => {
    process.env.CABINET_DEMO_DATA = 'true'
    const { dockerExec } = await import('@/lib/docker')
    await expect(dockerExec('echo hi')).rejects.toThrow(/demo data/i)
    await expect(dockerExec('echo hi')).rejects.not.toThrow(/misconfiguration/i)
  })
})

describe('THE INVERSE — work that genuinely happens still reports success', () => {
  beforeEach(() => {
    process.env.REDIS_URL = 'redis://127.0.0.1:6379'
    sandboxPaths()
  })

  it('a live posture runs the command and returns its real stdout', async () => {
    const { dockerExec } = await import('@/lib/docker')
    const { stdout } = await dockerExec('printf hello-from-a-real-shell')
    expect(stdout).toBe('hello-from-a-real-shell')
  })

  it('a real command that FAILS is still a failure, and says so as a RUN command', async () => {
    // `rejects.toThrow()` alone passed whether the command ran and exited 7 or
    // was refused for the posture — it could not tell the two apart, which is
    // the distinction this whole file is about. The message shape is what
    // separates them.
    const { dockerExec } = await import('@/lib/docker')
    await expect(dockerExec('exit 7')).rejects.toThrow(/exit code 7|Command failed/i)
    await expect(dockerExec('exit 7')).rejects.not.toThrow(/nothing was run/i)
  })

  it('addEnvVar writes the key and reports success — proven from the file, not the return', async () => {
    const m = await import('@/actions/env')
    const r = await m.addEnvVar('SWEEP_INVERSE_KEY', 'landed')
    expect(r).toEqual({ success: true })
    expect(envFile()).toMatch(/^SWEEP_INVERSE_KEY=landed$/m)
  })

  it('addEnvVar still refuses a duplicate — the precondition read is real again', async () => {
    // `parseInt('mock: command executed')` was NaN, so `NaN > 0` was false and
    // the duplicate check silently passed for every key in the file.
    const m = await import('@/actions/env')
    const r = await m.addEnvVar('EXISTING_KEY', 'second-copy')
    expect(r.success).toBe(false)
    expect(r.error).toMatch(/already exists/)
    expect(envFile().match(/^EXISTING_KEY=/gm)).toHaveLength(1)
  })
})
