/**
 * The dashboard's availability write path — `updateCaptainAvailability`
 * (actions/config.ts), added 2026-07-27 so the dial is adjustable without a
 * phone.
 *
 * Every arm pins a property the Captain depends on, not an implementation
 * detail:
 *
 *   * an unauthenticated caller cannot move the dial AND cannot cause a shell
 *     command to run at all (a Server Action is a global action-ID POST
 *     endpoint; middleware never covers action dispatch);
 *   * the write goes to the store's OWN recorder — never a `sed`, never
 *     platform.yml, which is a marker-managed generator output with one writer;
 *   * only a canonical token reaches the command line, so a value the dial
 *     cannot hold is refused with NO exec rather than repaired, rounded, or
 *     smuggled into a shell;
 *   * `away` / `0` are real rulings, not absences — the degenerate end has to
 *     pass, or the control cannot express "leave me alone";
 *   * success is claimed only against the writer's receipt — an output-shape
 *     control that is INDEPENDENT of the store posture, and stays that way on
 *     purpose. `lib/docker.ts` no longer answers "mock: command executed" for a
 *     command it declined to run (it rejects), but a real writer that runs and
 *     prints something else is a different failure, and this is its sensor.
 *
 * The real requireDashboardAuth runs — only verifySession is mocked — with the
 * enforcing posture pinned (MOCK_DATA unset, NODE_ENV=test), the same harness
 * shape as actions-auth.test.ts.
 *
 * The other half of this contract — that the command really does write a valid
 * adjustment row, and that the resolver every consumer reads then serves it —
 * is pinned in python, against the command string extracted from this very
 * file: cabinet/scripts/lib/tests/test_captain_availability_dashboard.py.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mockVerify, mockDockerExec, mockRevalidate } = vi.hoisted(() => ({
  mockVerify: vi.fn<() => Promise<boolean>>(),
  mockDockerExec: vi.fn(),
  mockRevalidate: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: mockRevalidate }))
vi.mock('next/navigation', () => ({ redirect: vi.fn() }))
vi.mock('@/lib/auth', () => ({
  verifySession: mockVerify,
  checkPassword: vi.fn(),
  createSession: vi.fn(),
  destroySession: vi.fn(),
}))
vi.mock('@/lib/docker', () => ({ dockerExec: mockDockerExec, getEnvVars: vi.fn() }))

import { updateCaptainAvailability } from './config'

/** What the recorder actually prints on a successful append. */
const RECEIPT =
  'recorded 30 min/day (part_time) -> /srv/cabinet/instance/config/captain-availability.yml'

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubEnv('MOCK_DATA', '')
  vi.stubEnv('NODE_ENV', 'test')
  mockDockerExec.mockResolvedValue({ stdout: RECEIPT, stderr: '' })
})

afterEach(() => vi.unstubAllEnvs())

function lastCommand(): string {
  expect(mockDockerExec).toHaveBeenCalledTimes(1)
  return mockDockerExec.mock.calls[0][0] as string
}

describe('the unauthenticated caller cannot move the dial', () => {
  beforeEach(() => mockVerify.mockResolvedValue(false))

  it('refuses and runs no command at all', async () => {
    expect(await updateCaptainAvailability('part_time')).toEqual({
      success: false,
      error: 'Unauthorized',
    })
    expect(mockDockerExec).not.toHaveBeenCalled()
    expect(mockRevalidate).not.toHaveBeenCalled()
  })

  it('is refused BEFORE validation, so even a valid value execs nothing', async () => {
    expect(await updateCaptainAvailability('90')).toEqual({
      success: false,
      error: 'Unauthorized',
    })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })
})

describe('the authenticated caller writes through the store owner', () => {
  beforeEach(() => mockVerify.mockResolvedValue(true))

  it('runs the recorder with dashboard provenance — not a platform.yml sed', async () => {
    expect(await updateCaptainAvailability('part_time')).toEqual({ success: true })
    const cmd = lastCommand()
    expect(cmd).toContain('cabinet/scripts/lib/captain_availability.py')
    expect(cmd).toContain(' set part_time ')
    expect(cmd).toContain('--source dashboard')
    // The two things this action must never be.
    expect(cmd).not.toMatch(/\bsed\b/)
    expect(cmd).not.toContain('platform.yml')
    expect(mockRevalidate).toHaveBeenCalledWith('/settings')
  })

  it('accepts whole minutes and passes the integer, not the typed string', async () => {
    expect(await updateCaptainAvailability(' 090 ')).toEqual({ success: true })
    expect(lastCommand()).toContain(' set 90 ')
  })

  it('normalises the hyphen/case forms the phone also tolerates', async () => {
    expect(await updateCaptainAvailability('PART-TIME')).toEqual({ success: true })
    expect(lastCommand()).toContain(' set part_time ')
  })

  // Degenerate end. "away" and 0 are the whole point of the dial for a Captain
  // who is 90% elsewhere; a control that cannot express them is not the control.
  it.each([
    ['away', 'away'],
    ['0', '0'],
    ['full_time', 'full_time'],
    ['1440', '1440'],
  ])('records %s as a real ruling', async (input, token) => {
    expect(await updateCaptainAvailability(input)).toEqual({ success: true })
    expect(lastCommand()).toContain(` set ${token} `)
  })
})

describe('a value the dial cannot hold is refused, never repaired', () => {
  beforeEach(() => mockVerify.mockResolvedValue(true))

  it.each([
    ['90.5', 'a fractional minute — refuse, do not round'],
    ['1.5', 'a fraction below one minute'],
    ['0.0', 'an integer wearing a decimal point is still not the token'],
    ['1441', 'above the day'],
    ['-1', 'below zero'],
    ['-0', 'a signed zero is not the way to say away'],
    ['', 'empty'],
    ['   ', 'whitespace'],
    ['vacation', 'not a mode in the table'],
    ['part', 'a prefix of a mode is not a mode'],
    ['0x10', 'not a decimal integer'],
    ['3e2', 'not a decimal integer'],
    ['1_440', 'not a decimal integer'],
    ['20m', 'a phone form the dashboard deliberately does not accept'],
    ['2h', 'a phone form the dashboard deliberately does not accept'],
  ])('refuses %s (%s) and runs nothing', async (value) => {
    const res = await updateCaptainAvailability(value)
    expect(res.success).toBe(false)
    expect(res.error).toContain('not a budget the dial can hold')
    expect(mockDockerExec).not.toHaveBeenCalled()
    expect(mockRevalidate).not.toHaveBeenCalled()
  })

  // Nothing hostile can reach a shell, because the token that gets
  // interpolated is re-derived from the table, never the caller's string.
  it.each([
    'away; touch /tmp/pwned',
    "away' ; touch /tmp/pwned ; '",
    'part_time && rm -rf /',
    '30; echo hi',
    '$(whoami)',
    '`whoami`',
    'away\nminimal',
  ])('refuses the injection attempt %j and runs nothing', async (value) => {
    expect((await updateCaptainAvailability(value)).success).toBe(false)
    expect(mockDockerExec).not.toHaveBeenCalled()
  })
})

describe('success is claimed only against the writer receipt', () => {
  beforeEach(() => mockVerify.mockResolvedValue(true))

  it('output that is not the receipt cannot report a save', async () => {
    // Historically this stood in for `dockerExec`'s no-op sentinel. That
    // sentinel is gone (an unrun command rejects — see the arm below), so what
    // this now pins is the independent half: a writer that RAN and said
    // something other than the receipt is not a save either.
    mockDockerExec.mockResolvedValue({ stdout: 'wrote something, probably', stderr: '' })
    const res = await updateCaptainAvailability('part_time')
    expect(res.success).toBe(false)
    expect(res.error).toContain('nothing was recorded')
    expect(mockRevalidate).not.toHaveBeenCalled()
  })

  it('a command that was never run surfaces its own reason, not "nothing was recorded"', async () => {
    // The refusal from `lib/docker.ts` has to reach the Captain intact: "the
    // cabinet did not confirm the change" would send him looking at the writer
    // when the problem is that this dashboard has no cabinet.
    //
    // HONEST LIMIT: this arm does NOT go red against pre-change code. `dockerExec`
    // is mocked here and `config.ts`'s catch already returned `err.message`, so
    // it pins a property that was already true rather than sensing the change.
    // The sensor for the change is `lib/unexecuted-command.test.ts`, which drives
    // the real module. Kept because the property is worth pinning; labelled
    // because an arm that cannot fail must not be counted as coverage.
    mockDockerExec.mockRejectedValue(
      new Error('nothing was run and nothing was changed — no store is configured (REDIS_URL unset)')
    )
    const res = await updateCaptainAvailability('part_time')
    expect(res.success).toBe(false)
    expect(res.error).toMatch(/nothing was run and nothing was changed/)
    expect(mockRevalidate).not.toHaveBeenCalled()
  })

  it('silence from the runtime is not success', async () => {
    mockDockerExec.mockResolvedValue({ stdout: '', stderr: '' })
    expect((await updateCaptainAvailability('part_time')).success).toBe(false)
    expect(mockRevalidate).not.toHaveBeenCalled()
  })

  it('a failing command surfaces the failure instead of swallowing it', async () => {
    mockDockerExec.mockRejectedValue(new Error('container is down'))
    const res = await updateCaptainAvailability('part_time')
    expect(res).toEqual({ success: false, error: 'container is down' })
    expect(mockRevalidate).not.toHaveBeenCalled()
  })
})
