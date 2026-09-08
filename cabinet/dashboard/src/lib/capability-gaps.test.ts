/**
 * The /gaps read path over the widened kind vocabulary (contract §3 + A0.3).
 *
 * Three properties, each red on the pre-change tree for its own reason:
 *
 *  1. TYPE — `skill | authority | information` are assignable to `GapKind`.
 *     tsconfig includes every `**\/*.ts`, so `npx tsc --noEmit` IS this
 *     sensor: against the three-kind union the annotation below is an error,
 *     which is the failure a widened ledger + a narrow reader produces in the
 *     one place a reader can still catch it.
 *  2. INTERPRETER (A0.3) — the exec string this unlocked module hands the
 *     shell pins `${CABINET_PYTHON:-python3.12}`. Bare `python3` on the
 *     deployment box is 3.9, and this string is read by whatever is first on
 *     PATH, not by the interpreter the suite ran under.
 *  3. GENERIC HANDLING — the pure helpers sort and count a row whose kind
 *     nobody wrote a branch for. That is the whole behaviour promised for the
 *     structural kinds ("rendered generically, zero new UI"), so it is
 *     asserted rather than assumed.
 */
import { describe, expect, it, vi } from 'vitest'

const { mockDockerExec } = vi.hoisted(() => ({ mockDockerExec: vi.fn() }))
vi.mock('@/lib/docker', () => ({ dockerExec: mockDockerExec }))

import { countGaps, listCapabilityGaps, sortGaps } from './capability-gaps'
import type { CapabilityGap, GapKind } from './capability-gaps'

// The annotation is the sensor — a narrower `GapKind` fails to compile here.
const STRUCTURAL_KINDS: readonly GapKind[] = ['skill', 'authority', 'information']

function gap(kind: GapKind, over: Partial<CapabilityGap> = {}): CapabilityGap {
  return {
    gap_id: `gap-0000000${kind.length % 10}`,
    need: `no holder for a ${kind} need`,
    kind,
    status: 'open',
    hit_count: 1,
    evidence: '',
    first_seen: '2026-09-07T00:00:00Z',
    last_seen: '2026-09-07T00:00:00Z',
    recorded_by: 'supervisor',
    resolution: null,
    ...over,
  }
}

describe('GapKind', () => {
  it('carries the three structural kinds alongside the actionable ones', () => {
    expect([...STRUCTURAL_KINDS]).toEqual(['skill', 'authority', 'information'])
  })
})

describe('listCapabilityGaps', () => {
  it('pins the interpreter in the command it hands the shell', async () => {
    mockDockerExec.mockReset()
    mockDockerExec.mockResolvedValue({ stdout: '[]' })

    await listCapabilityGaps()

    const cmd: string = mockDockerExec.mock.calls[0][0]
    expect(cmd).toContain('${CABINET_PYTHON:-python3.12}')
    // ...and nowhere an unpinned one that PATH would resolve for us.
    expect(cmd).not.toMatch(/(^|[\s;|&])python3(\s|$)/)
  })

  it('returns a structural-kind row unchanged', async () => {
    mockDockerExec.mockReset()
    mockDockerExec.mockResolvedValue({ stdout: JSON.stringify([gap('skill')]) })

    const rows = await listCapabilityGaps()

    expect(rows).toHaveLength(1)
    expect(rows[0].kind).toBe('skill')
  })
})

describe('the pure helpers over a kind they were never written for', () => {
  it('sorts and counts every structural kind like any other open gap', () => {
    const rows = STRUCTURAL_KINDS.map((k) => gap(k))

    expect(sortGaps(rows).map((g) => g.kind)).toEqual([...STRUCTURAL_KINDS])
    expect(countGaps(rows)).toEqual({
      open: 3,
      skilled: 0,
      pendingCaptain: 0,
      resolved: 0,
    })
  })
})
