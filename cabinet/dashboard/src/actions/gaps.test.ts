/**
 * A0.3 on the /gaps WRITE path — the Captain's Approve and Decline.
 *
 * A0.3 names three unlocked exec strings: work-graph-complete.sh, the reader
 * in lib/capability-gaps.ts, and THIS module's two. The reader's pin was
 * asserted (lib/capability-gaps.test.ts); these two were pinned in source and
 * asserted nowhere, so reverting them to a bare `python3` left `tsc --noEmit`
 * at rc=0 and every vitest file green — a pin with no sensor, which is the
 * same thing as no pin the first time someone reformats this file.
 *
 * `python3` on the deployment box is 3.9.6 with python3.12 installed beside
 * it, so an unpinned token here does not name an interpreter: it names
 * whatever PATH answers with inside the container this shells into.
 *
 * The command string is asserted as a STRING, not by "dockerExec was called":
 * `expect(mockDockerExec).toHaveBeenCalled()` is true of every possible
 * command, including the wrong one, which is why the hole survived a review
 * pass with a green suite.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mockVerify, mockDockerExec } = vi.hoisted(() => ({
  mockVerify: vi.fn<() => Promise<boolean>>(),
  mockDockerExec: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ verifySession: mockVerify }))
vi.mock('@/lib/docker', () => ({ dockerExec: mockDockerExec }))

import { approveGap, declineGap } from './gaps'

const PIN = '${CABINET_PYTHON:-python3.12}'
// A bare interpreter token: `python3` with no version suffix. Mirrors
// framework/tests/test_interpreter_pin.py's regex, which scans this file's
// source repo-wide; this arm watches the string actually handed to the shell.
const BARE = /(?<![\w.])python3(?![\w.-])/

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubEnv('MOCK_DATA', '')
  vi.stubEnv('NODE_ENV', 'test')
  mockVerify.mockResolvedValue(true)
  mockDockerExec.mockResolvedValue({ stdout: '', stderr: '' })
})

afterEach(() => vi.unstubAllEnvs())

describe('the /gaps write path pins the interpreter it shells into', () => {
  it('approveGap', async () => {
    expect(await approveGap('gap-0000abcd')).toEqual({ ok: true })

    const cmd: string = mockDockerExec.mock.calls[0][0]
    expect(cmd).toContain(PIN)
    expect(cmd).not.toMatch(BARE)
    // The pin is on the COMMAND, not merely present in the file: it leads.
    expect(cmd.startsWith(PIN + ' ')).toBe(true)
    expect(cmd).toContain('org-runtime.py gaps approve')
  })

  it('declineGap', async () => {
    expect(await declineGap('gap-0000abcd', 'not now')).toEqual({ ok: true })

    const cmd: string = mockDockerExec.mock.calls[0][0]
    expect(cmd).toContain(PIN)
    expect(cmd).not.toMatch(BARE)
    expect(cmd.startsWith(PIN + ' ')).toBe(true)
    expect(cmd).toContain('org-runtime.py gaps decline')
  })

  it('every command this module can send is pinned — both, in one pass', async () => {
    await approveGap('gap-0000abcd')
    await declineGap('gap-0000abcd', "it's declined")

    const sent = mockDockerExec.mock.calls.map((c) => String(c[0]))
    expect(sent).toHaveLength(2)
    for (const cmd of sent) {
      expect(cmd).toContain(PIN)
      expect(cmd).not.toMatch(BARE)
    }
  })
})

describe('the guard still stands in front of the pinned command', () => {
  it('an unauthenticated caller never reaches the shell', async () => {
    mockVerify.mockResolvedValue(false)

    expect(await approveGap('gap-0000abcd')).toEqual({ ok: false, error: 'unauthorized' })
    expect(await declineGap('gap-0000abcd', 'x')).toEqual({ ok: false, error: 'unauthorized' })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })

  it('a malformed id never reaches the shell', async () => {
    expect(await approveGap("gap-0000abcd'; rm -rf /")).toEqual({
      ok: false,
      error: 'invalid gap id',
    })
    expect(mockDockerExec).not.toHaveBeenCalled()
  })
})
