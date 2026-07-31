/**
 * THE FIFTEEN CONFIG WRITES, DRIVEN FOR REAL, ON THE MACHINE THAT RUNS THEM.
 *
 * WHAT THIS FILE IS THE SENSOR FOR. `actions/config.ts` (×8), `actions/env.ts`
 * (×2), `actions/project-config.ts` (×2) and `deleteOfficer` (×3) edited the
 * cabinet's YAML and `.env` with `sed -i '<script>' <file>`. BSD `sed` takes the
 * in-place suffix as a MANDATORY argument, so on the Captain's Mac — the only
 * deployment that exists — every one of them exited 1 and changed nothing.
 * Measured directly, all four shapes the app used:
 *
 *     sed -i 's|^FOO=.*|FOO=new|' env1
 *       exit 1 · sed: 1: "env1\n": invalid command code e · file unchanged
 *     sed -i '/^FOO=/d' env2                                    · unchanged
 *     sed -i '/^product:/,/^[a-z]/{s/^  name: .*​/  name: NEW/}' · unchanged
 *     sed -i '/^voice:/,…{/^  officers:/,…{/^    cos: /d}}'     · unchanged
 *
 * WHY THE EXISTING SWEEP COULD NOT SEE IT. `lib/unexecuted-command.test.ts`
 * proves every one of these actions REFUSES with no store. Refusal is the arm it
 * needs and refusal is what BSD sed produces too — via a different route, with a
 * different sentence, but `success: false` either way. Its own inverse arm says
 * so out loud: it uses `echo >>` "on purpose" because `sed -i` "would make this
 * arm pass on CI's GNU userland and fail on the Captain's Mac". So the suite was
 * green on both platforms while the feature worked on neither.
 *
 * THIS FILE IS THAT MISSING INVERSE. Every arm asserts the BYTES ON DISK after a
 * real action call in a live posture — never the returned flag alone. Run
 * against the pre-change tree on this Mac, all of them fail; on GNU they would
 * have passed, which is why the assertion had to be the file rather than the
 * exit status.
 *
 * SANDBOX. Every path-steering variable is owned and restored, and the
 * destinations are ASSERTED to be inside the temp tree before anything is
 * written — `cabinet/.env` on a configured box holds the Anthropic key, every
 * Telegram bot token and the GitHub PAT, and a previous pass proved that a sweep
 * overriding CABINET_ROOT but not CABINET_ENV_PATH appends to it for real.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import yaml from 'js-yaml'

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/provisioning/guard', () => ({
  requireDashboardAuth: async () => true,
  requireProvisioningAccess: async () => true,
}))
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

const saved = {
  REDIS_URL: process.env.REDIS_URL,
  MOCK_DATA: process.env.MOCK_DATA,
  CABINET_DEMO_DATA: process.env.CABINET_DEMO_DATA,
  CABINET_ROOT: process.env.CABINET_ROOT,
  CABINET_RUNTIME_MODE: process.env.CABINET_RUNTIME_MODE,
  CABINET_ENV_PATH: process.env.CABINET_ENV_PATH,
  CABINET_PREFIX: process.env.CABINET_PREFIX,
}

let root: string

const PRODUCT_YML = `product:
  name: Before
  description: An unchanged description
  repo: owner/repo
voice:
  enabled: false
  provider: elevenlabs
  voices:
    cos: voice-cos
    cto: voice-cto
  stability:
    cos: 0.5
image_generation:
  enabled: false
  provider: none
embeddings:
  provider: voyage
  dimensions: 1024
  models:
    storage: voyage-3
    query: voyage-3
notion:
  enabled: false
linear:
  enabled: false
telegram:
  officers:
    cos: cos_bot
    cto: cto_bot
`

function makeRoot(): string {
  const dir = mkdtempSync(path.join(tmpdir(), 'cabinet-cfgwrite-'))
  mkdirSync(path.join(dir, 'cabinet'), { recursive: true })
  mkdirSync(path.join(dir, 'instance', 'config', 'projects'), { recursive: true })
  mkdirSync(path.join(dir, '.claude', 'agents'), { recursive: true })
  mkdirSync(path.join(dir, 'cabinet', 'loop-prompts'), { recursive: true })
  writeFileSync(
    path.join(dir, 'cabinet', '.env'),
    'EXISTING_KEY=already-here\nTELEGRAM_CTO_TOKEN=7001:AAEtoken\n'
  )
  writeFileSync(path.join(dir, 'instance', 'config', 'product.yml'), PRODUCT_YML)
  writeFileSync(path.join(dir, 'instance', 'config', 'active-project.txt'), 'demo\n')
  writeFileSync(
    path.join(dir, 'instance', 'config', 'projects', 'demo.yml'),
    'product:\n  name: Demo\nnotion:\n  dashboard:\n    page_id: old-page\n'
  )
  // assemble-config.sh is invoked by project-config.ts after the edit. A stub
  // inside the temp tree keeps the action's own success path real without
  // running the checkout's script against the checkout's config.
  mkdirSync(path.join(dir, 'cabinet', 'scripts'), { recursive: true })
  writeFileSync(path.join(dir, 'cabinet', 'scripts', 'assemble-config.sh'), 'exit 0\n')
  return dir
}

/**
 * Point every write target at the temp tree, then PROVE each one lands there.
 *
 * The assertion is the control, and it enumerates the destinations the way the
 * modules compute them rather than trusting that setting CABINET_ROOT covers
 * everything: `actions/env.ts` reads CABINET_ENV_PATH, and a sweep that set the
 * root but not that variable is precisely how a previous pass appended a test
 * secret to a live `cabinet/.env`.
 */
function sandboxPaths() {
  process.env.CABINET_ROOT = root
  process.env.CABINET_RUNTIME_MODE = 'native'
  process.env.CABINET_ENV_PATH = path.join(root, 'cabinet', '.env')
  process.env.CABINET_PREFIX = 'cabinet-test-sandbox'
  const destinations = [
    process.env.CABINET_ENV_PATH,
    path.join(process.env.CABINET_ROOT, 'instance', 'config', 'product.yml'),
    path.join(process.env.CABINET_ROOT, 'instance', 'config', 'projects', 'demo.yml'),
  ]
  for (const d of destinations) {
    if (!d.startsWith(root + path.sep)) {
      throw new Error(`refusing to run: ${d} is outside the temp tree`)
    }
  }
}

/** A live store — the posture in which these actions are allowed to write. */
function live() {
  delete process.env.MOCK_DATA
  delete process.env.CABINET_DEMO_DATA
  process.env.REDIS_URL = 'redis://127.0.0.1:6379'
  sandboxPaths()
}

beforeEach(() => {
  vi.resetModules()
  root = makeRoot()
  live()
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
    /* the tmpdir is disposable */
  }
})

const envFile = () => readFileSync(path.join(root, 'cabinet', '.env'), 'utf8')
const productFile = () =>
  readFileSync(path.join(root, 'instance', 'config', 'product.yml'), 'utf8')
const projectFile = () =>
  readFileSync(path.join(root, 'instance', 'config', 'projects', 'demo.yml'), 'utf8')
const productDoc = () => yaml.load(productFile()) as Record<string, never>

describe('the config editors change the file — proven from the bytes, not the flag', () => {
  it('updateProductConfig writes the product field', async () => {
    const m = await import('@/actions/config')
    expect(await m.updateProductConfig('name', 'After')).toEqual({ success: true })
    expect(productDoc().product['name']).toBe('After')
    // Untouched neighbours stay untouched — a line edit, not a re-serialisation.
    expect(productDoc().product['description']).toBe('An unchanged description')
    expect(productFile()).toContain('  repo: owner/repo')
  })

  it('updateGlobalVoiceConfig writes into the voice block, not the first match anywhere', async () => {
    const m = await import('@/actions/config')
    expect(await m.updateGlobalVoiceConfig('enabled', 'true')).toEqual({ success: true })
    expect(productDoc().voice['enabled']).toBe(true)
    // `image_generation.enabled` has the same key name one block down.
    expect(productDoc().image_generation['enabled']).toBe(false)
  })

  it('updateImageGenConfig writes its own block', async () => {
    const m = await import('@/actions/config')
    expect(await m.updateImageGenConfig('provider', 'openai')).toEqual({ success: true })
    expect(productDoc().image_generation['provider']).toBe('openai')
    expect(productDoc().voice['provider']).toBe('elevenlabs')
  })

  it('updateEmbeddingsConfig writes both the flat field and the nested models field', async () => {
    const m = await import('@/actions/config')
    expect(await m.updateEmbeddingsConfig('provider', 'openai')).toEqual({ success: true })
    expect(await m.updateEmbeddingsConfig('models.storage', 'voyage-3-large')).toEqual({
      success: true,
    })
    expect(productDoc().embeddings['provider']).toBe('openai')
    expect(productDoc().embeddings['models']['storage']).toBe('voyage-3-large')
    expect(productDoc().embeddings['models']['query']).toBe('voyage-3')
  })

  it('updateOfficerVoiceConfig writes voice.<field>.<role>', async () => {
    const m = await import('@/actions/config')
    expect(await m.updateOfficerVoiceConfig('cos', 'voices', 'new-voice-id')).toEqual({
      success: true,
    })
    expect(productDoc().voice['voices']['cos']).toBe('new-voice-id')
    expect(productDoc().voice['voices']['cto']).toBe('voice-cto')
  })

  it('updateNotionConfig and updateLinearConfig write their blocks', async () => {
    const m = await import('@/actions/config')
    expect(await m.updateNotionConfig('enabled', 'true')).toEqual({ success: true })
    expect(await m.updateLinearConfig('enabled', 'true')).toEqual({ success: true })
    expect(productDoc().notion['enabled']).toBe(true)
    expect(productDoc().linear['enabled']).toBe(true)
  })

  it('updateProjectConfig writes the project YAML at both depths', async () => {
    const m = await import('@/actions/project-config')
    expect(await m.updateProjectConfig('product', 'name', 'Renamed')).toEqual({ success: true })
    expect(await m.updateProjectConfig('notion', 'dashboard.page_id', 'new-page')).toEqual({
      success: true,
    })
    const doc = yaml.load(projectFile()) as Record<string, never>
    expect(doc.product['name']).toBe('Renamed')
    expect(doc.notion['dashboard']['page_id']).toBe('new-page')
  })

  it('updateEnvVar rewrites an existing secret in place', async () => {
    const m = await import('@/actions/env')
    expect(await m.updateEnvVar('EXISTING_KEY', 'rotated')).toEqual({ success: true })
    expect(envFile()).toMatch(/^EXISTING_KEY=rotated$/m)
    expect(envFile().match(/^EXISTING_KEY=/gm)).toHaveLength(1)
  })

  it('deleteEnvVar removes the line', async () => {
    const m = await import('@/actions/env')
    expect(await m.deleteEnvVar('EXISTING_KEY')).toEqual({ success: true })
    expect(envFile()).not.toMatch(/^EXISTING_KEY=/m)
    expect(envFile()).toMatch(/^TELEGRAM_CTO_TOKEN=/m)
  })

  it('deleteOfficer strips the officer from product.yml AND drops his bot token', async () => {
    const m = await import('@/actions/officers')
    expect(await m.deleteOfficer('cto')).toEqual({ success: true })
    const doc = productDoc()
    expect(doc.voice['voices']).not.toHaveProperty('cto')
    expect(doc.voice['voices']).toHaveProperty('cos')
    expect(doc.telegram['officers']).not.toHaveProperty('cto')
    expect(envFile()).not.toMatch(/^TELEGRAM_CTO_TOKEN=/m)
    // He had no `voice.stability` entry. Deleting an absent key is the goal,
    // not a failure — an officer must not survive because he was half-configured.
    expect(doc.voice['stability']).toHaveProperty('cos')
  })
})

describe('what the write refuses, and proves it refused', () => {
  it('a field that is not in the file is an ERROR, not a green tick', async () => {
    // GNU `sed` exits 0 when its pattern matches nothing, so this reported
    // success and changed nothing on the platform where `sed -i` did run. It is
    // the same write-lie with no shell dialect involved.
    const before = productFile()
    const m = await import('@/actions/config')
    const r = await m.updateProductConfig('mount_path', '/srv/thing')
    expect(r.success).toBe(false)
    expect(r.error).toMatch(/no product\.mount_path field|nothing was changed/i)
    expect(productFile()).toBe(before)
  })

  it('a value that would break the YAML is refused and the file is byte-identical', async () => {
    const before = productFile()
    const m = await import('@/actions/config')
    const r = await m.updateProductConfig('name', 'oops: "unbalanced')
    // Either it is quoted safely or it is refused; what is NOT allowed is a
    // product.yml the cabinet can no longer read.
    expect(() => yaml.load(productFile())).not.toThrow()
    if (r.success === false) expect(productFile()).toBe(before)
  })

  it('a newline in a secret cannot inject a second line into cabinet/.env', async () => {
    // `echo 'K=v' >> .env` with a newline in `v` wrote an attacker-chosen extra
    // line into the file holding every credential the cabinet has.
    const m = await import('@/actions/env')
    const r = await m.addEnvVar('INJECTED', 'a\nSUPERUSER=yes')
    expect(r.success).toBe(false)
    expect(envFile()).not.toMatch(/^SUPERUSER=/m)
  })

  it('a shell metacharacter in a value is data, not a command', async () => {
    // The old shape interpolated this into `sed -i '…' file` through /bin/bash.
    const m = await import('@/actions/config')
    const marker = path.join(root, 'PWNED')
    const r = await m.updateProductConfig('name', `x'; touch ${marker}; echo '`)
    expect(r.success === true || r.success === false).toBe(true)
    expect(() => readFileSync(marker)).toThrow()
    expect(() => yaml.load(productFile())).not.toThrow()
  })

  it('setting a field to the value it already has is a success and not a write', async () => {
    const before = productFile()
    const m = await import('@/actions/config')
    expect(await m.updateProductConfig('name', 'Before')).toEqual({ success: true })
    expect(productFile()).toBe(before)
  })
})

describe('THE INVERSE OF THE INVERSE — with no store, none of it happens', () => {
  beforeEach(() => {
    delete process.env.REDIS_URL
    delete process.env.MOCK_DATA
    delete process.env.CABINET_DEMO_DATA
    sandboxPaths()
  })

  it('every editor refuses and every file is byte-identical', async () => {
    const beforeProduct = productFile()
    const beforeEnv = envFile()
    const cfg = await import('@/actions/config')
    const env = await import('@/actions/env')
    const officers = await import('@/actions/officers')
    const results = [
      await cfg.updateProductConfig('name', 'After'),
      await cfg.updateOfficerVoiceConfig('cos', 'voices', 'x'),
      await env.updateEnvVar('EXISTING_KEY', 'rotated'),
      await env.deleteEnvVar('EXISTING_KEY'),
      await officers.deleteOfficer('cto'),
    ]
    for (const r of results) expect(r.success).toBe(false)
    expect(productFile()).toBe(beforeProduct)
    expect(envFile()).toBe(beforeEnv)
  })
})
