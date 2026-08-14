/**
 * THE SECOND SIGNAL, TAKEN FOR REAL — and the store readings around it.
 *
 * `crew.ts` decides; this module MEASURES, and a decision fed a wrong
 * measurement is wrong quietly. So these arms drive the real filesystem (a
 * temp LaunchAgents directory) rather than a mock of it: the thing that would
 * actually break this is a path or an errno, and neither survives being
 * stubbed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const { mockKeys, mockGet } = vi.hoisted(() => ({
  mockKeys: vi.fn(),
  mockGet: vi.fn(),
}))

vi.mock('@/lib/redis', () => ({ default: { keys: mockKeys, get: mockGet } }))
vi.mock('./redis', () => ({ default: { keys: mockKeys, get: mockGet } }))

import {
  launchAgentsDir,
  officerLabel,
  readCrew,
  readInstall,
  STOP_REQUESTED_KEY,
} from './crew-state'

let dir: string
let instance: string

const NOW = Date.parse('2026-08-14T12:00:00Z')

beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'crew-state-la-'))
  instance = fs.mkdtempSync(path.join(os.tmpdir(), 'crew-state-inst-'))
  fs.mkdirSync(path.join(instance, 'contexts'))
  process.env.CABINET_LAUNCHD_DIR = dir
  process.env.CABINET_ROSTER_PATH = path.join(instance, 'roster.yml')
  process.env.CABINET_CONTEXTS_DIR = path.join(instance, 'contexts')
  mockKeys.mockResolvedValue([])
  mockGet.mockResolvedValue(null)
})

afterEach(() => {
  delete process.env.CABINET_LAUNCHD_DIR
  delete process.env.CABINET_ROSTER_PATH
  delete process.env.CABINET_CONTEXTS_DIR
  fs.rmSync(dir, { recursive: true, force: true })
  fs.rmSync(instance, { recursive: true, force: true })
  vi.clearAllMocks()
})

const DARWIN = process.platform === 'darwin'
const onDarwin = DARWIN ? it : it.skip

describe('readInstall — the signal that separates never-started from died', () => {
  onDarwin('an installed helper reads as installed', () => {
    fs.writeFileSync(path.join(dir, `${officerLabel('cos')}.plist`), '<plist/>')
    expect(readInstall('cos')).toEqual({ state: 'installed' })
  })

  onDarwin('a directory that exists with no plist is a MEASURED absence', () => {
    expect(readInstall('cos')).toEqual({ state: 'absent' })
  })

  onDarwin('a machine with NO LaunchAgents directory at all is also a measured absence', () => {
    // The common shape of a brand-new Mac, and precisely the case that has to
    // render calmly rather than as "we could not tell".
    fs.rmSync(dir, { recursive: true, force: true })
    expect(readInstall('cos')).toEqual({ state: 'absent' })
  })

  it('a platform with no launchd is UNKNOWN, never a measured absence', () => {
    // Asserted from whichever platform this runs on: on darwin the arm is
    // proven by the ones above; elsewhere the reading must refuse to claim.
    if (DARWIN) return
    const r = readInstall('cos')
    expect(r.state).toBe('unknown')
  })

  it('the directory defaults to the user\'s LaunchAgents when nothing overrides it', () => {
    delete process.env.CABINET_LAUNCHD_DIR
    expect(launchAgentsDir().endsWith(path.join('Library', 'LaunchAgents'))).toBe(true)
  })

  it('the label is the one deploy-mac.sh renders and stops', () => {
    expect(officerLabel('cos')).toBe('com.cabinet.officer.cos')
  })
})

describe('readCrew — the roster is the spine', () => {
  beforeEach(() => {
    fs.writeFileSync(
      path.join(instance, 'roster.yml'),
      'roster:\n  cos:\n    title: Chair\n    type: fulltime\n' +
        '  first-lane-ceo:\n    title: First Lane CEO\n    type: consultant\n'
    )
  })

  onDarwin('a hired officer appears with NO store keys at all — that is what makes "not awake yet" renderable', async () => {
    const crew = await readCrew(NOW)
    const cos = crew.members.find((m) => m.slug === 'cos')
    expect(cos?.state).toBe('not-awake-yet')
    expect(cos?.name).toBe('First Mate')
    expect(crew.neverWoken).toBe(true)
    expect(crew.anyAwake).toBe(false)
  })

  onDarwin('the placeholder lane CEO is named after its lane and folded away', async () => {
    const crew = await readCrew(NOW)
    const lane = crew.members.find((m) => m.slug === 'first-lane-ceo')
    expect(lane?.name).toBe('First Lane CEO')
    expect(lane?.folded).toBe(true)
    expect(crew.wakeable).toEqual(['cos'])
  })

  onDarwin('an installed helper with no heartbeat is the alarm, and neverWoken drops', async () => {
    fs.writeFileSync(path.join(dir, `${officerLabel('cos')}.plist`), '<plist/>')
    const crew = await readCrew(NOW)
    expect(crew.members.find((m) => m.slug === 'cos')?.state).toBe('quiet')
    expect(crew.neverWoken).toBe(false)
  })

  onDarwin('a fresh heartbeat makes it awake', async () => {
    mockKeys.mockImplementation(async (pattern: string) =>
      pattern.startsWith('cabinet:heartbeat') ? ['cabinet:heartbeat:cos'] : []
    )
    mockGet.mockImplementation(async (key: string) =>
      key === 'cabinet:heartbeat:cos' ? new Date(NOW - 1000).toISOString() : null
    )
    const crew = await readCrew(NOW)
    expect(crew.members.find((m) => m.slug === 'cos')?.state).toBe('awake')
    expect(crew.anyAwake).toBe(true)
  })

  it('a store that did not answer yields NO rows and says it is unreadable', async () => {
    mockKeys.mockRejectedValue(new Error('ECONNREFUSED'))
    const crew = await readCrew(NOW)
    expect(crew.members).toEqual([])
    expect(crew.unreadable).toBe(true)
    // Never a roster rendered as "nobody has started these": that would be a
    // claim about a machine this process just failed to ask about.
    expect(crew.neverWoken).toBe(false)
  })

  onDarwin('a liveness-plane key never becomes a crew member', async () => {
    mockKeys.mockImplementation(async (pattern: string) =>
      pattern.startsWith('cabinet:heartbeat')
        ? ['cabinet:heartbeat:liveness:cos', 'cabinet:heartbeat:cos']
        : []
    )
    const crew = await readCrew(NOW)
    expect(crew.members.map((m) => m.slug).sort()).toEqual(['cos', 'first-lane-ceo'])
  })

  onDarwin('a leftover heartbeat under a stop marker reads as asleep, not as working', async () => {
    // The 900s TTL outlives the stop, so this is the state the card is in for
    // the first quarter-hour after the sleep button.
    mockKeys.mockImplementation(async (pattern: string) =>
      pattern.startsWith('cabinet:heartbeat') ? ['cabinet:heartbeat:cos'] : []
    )
    mockGet.mockImplementation(async (key: string) => {
      if (key === 'cabinet:heartbeat:cos') return new Date(NOW - 120_000).toISOString()
      if (key === 'cabinet:officer:expected:cos') return 'stopped'
      if (key === STOP_REQUESTED_KEY('cos')) return new Date(NOW - 60_000).toISOString()
      return null
    })
    const crew = await readCrew(NOW)
    expect(crew.members.find((m) => m.slug === 'cos')?.state).toBe('resting')
    expect(crew.anyAwake).toBe(false)
  })

  onDarwin('a heartbeat NEWER than the stop surfaces as the stop having failed', async () => {
    mockKeys.mockImplementation(async (pattern: string) =>
      pattern.startsWith('cabinet:heartbeat') ? ['cabinet:heartbeat:cos'] : []
    )
    mockGet.mockImplementation(async (key: string) => {
      if (key === 'cabinet:heartbeat:cos') return new Date(NOW - 5_000).toISOString()
      if (key === 'cabinet:officer:expected:cos') return 'stopped'
      if (key === STOP_REQUESTED_KEY('cos')) return new Date(NOW - 60_000).toISOString()
      return null
    })
    const crew = await readCrew(NOW)
    expect(crew.members.find((m) => m.slug === 'cos')?.state).toBe('stop-failed')
  })

  onDarwin('an UNPARSEABLE stop time is treated as no stop time, never as NaN', async () => {
    mockKeys.mockImplementation(async (pattern: string) =>
      pattern.startsWith('cabinet:heartbeat') ? ['cabinet:heartbeat:cos'] : []
    )
    mockGet.mockImplementation(async (key: string) => {
      if (key === 'cabinet:heartbeat:cos') return new Date(NOW - 5_000).toISOString()
      if (key === 'cabinet:officer:expected:cos') return 'stopped'
      if (key === STOP_REQUESTED_KEY('cos')) return 'not a date'
      return null
    })
    // `NOW - age > NaN` is false, so a NaN would silently take the resting
    // arm — the reassuring one. It must take the conservative arm instead.
    const crew = await readCrew(NOW)
    expect(crew.members.find((m) => m.slug === 'cos')?.state).toBe('stop-failed')
  })

  onDarwin('an officer known only to the store arrives un-hired, and folded', async () => {
    mockKeys.mockImplementation(async (pattern: string) =>
      pattern.startsWith('cabinet:officer:expected')
        ? ['cabinet:officer:expected:stray-ceo']
        : []
    )
    const crew = await readCrew(NOW)
    const stray = crew.members.find((m) => m.slug === 'stray-ceo')
    expect(stray?.hired).toBe(false)
    expect(stray?.folded).toBe(true)
  })
})
