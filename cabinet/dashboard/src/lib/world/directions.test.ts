/**
 * Direction-layer readers — fail-honest degradations (instance-lanes law):
 * missing file / missing org: block / malformed YAML → uncharted, never an
 * invented apex; port-calls artifact absent/malformed → null, never an
 * invented voyage.
 */
import { afterEach, describe, expect, it } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { readDirections, readPortCalls } from './directions'

const roots: string[] = []

function tmpRoot(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'world-directions-'))
  roots.push(root)
  return root
}

function writeDirections(root: string, text: string): void {
  const dir = path.join(root, 'instance', 'config')
  fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(path.join(dir, 'directions.yml'), text)
}

function writePortCalls(root: string, text: string): void {
  const dir = path.join(root, 'shared', 'interfaces', 'world')
  fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(path.join(dir, 'port-calls.json'), text)
}

afterEach(() => {
  while (roots.length > 0) {
    fs.rmSync(roots.pop() as string, { recursive: true, force: true })
  }
})

describe('readDirections', () => {
  it('reads apex + lane directions', () => {
    const root = tmpRoot()
    writeDirections(
      root,
      [
        'directions:',
        '  alpha:',
        '    mission: >',
        '      Ship the thing.',
        '    instruments: [a_rate, b_rate]',
        'org:',
        '  apex:',
        '    mission: Prove the org.',
        '    instruments:',
        '      - escalation_rate',
      ].join('\n')
    )
    const d = readDirections(root)
    expect(d.apex).toEqual({
      mission: 'Prove the org.',
      instruments: ['escalation_rate'],
    })
    expect(Object.keys(d.lanes)).toEqual(['alpha'])
    expect(d.lanes.alpha.mission).toBe('Ship the thing.')
    expect(d.lanes.alpha.instruments).toEqual(['a_rate', 'b_rate'])
  })

  it('missing file → uncharted (apex null, lanes empty)', () => {
    expect(readDirections(tmpRoot())).toEqual({ apex: null, lanes: {} })
  })

  it('missing org: block → apex null, lanes kept (pre-apex deployments)', () => {
    const root = tmpRoot()
    writeDirections(root, 'directions:\n  alpha:\n    mission: m\n')
    const d = readDirections(root)
    expect(d.apex).toBeNull()
    expect(d.lanes.alpha.mission).toBe('m')
  })

  it('malformed YAML → uncharted, never a throw', () => {
    const root = tmpRoot()
    writeDirections(root, 'directions: [unclosed\n  ::::')
    expect(readDirections(root)).toEqual({ apex: null, lanes: {} })
  })

  it('malformed rows are skipped, not guessed', () => {
    const root = tmpRoot()
    writeDirections(
      root,
      [
        'directions:',
        '  good:',
        '    mission: m',
        '  missionless:',
        '    instruments: [x]',
        '  scalar: 4',
        'org:',
        '  apex: not-a-mapping',
      ].join('\n')
    )
    const d = readDirections(root)
    expect(Object.keys(d.lanes)).toEqual(['good'])
    expect(d.apex).toBeNull()
  })

  it('reads the REAL tracked directions.yml (apex block, ratified 2026-07-17)', () => {
    // repo root = <dashboard>/../.. — the tracked instance config carries the
    // real generic apex text (ratified choice; PR notes it).
    const repoRoot = path.resolve(__dirname, '..', '..', '..', '..', '..')
    if (!fs.existsSync(path.join(repoRoot, 'instance', 'config', 'directions.yml'))) {
      return // egg/clean checkout: instance directions pruned (only .example ships)
    }
    const d = readDirections(repoRoot)
    expect(d.apex).not.toBeNull()
    expect(d.apex?.mission).toContain('one founder plus an AI org')
    expect(d.apex?.instruments).toContain('verified_outcomes_per_captain_minute')
    // the framework's own key is untouched: lane directions still fold.
    expect(Object.keys(d.lanes).length).toBeGreaterThan(0)
  })
})

describe('readPortCalls', () => {
  it('absent artifact → null (honest absence)', () => {
    expect(readPortCalls(tmpRoot())).toBeNull()
  })

  it('reads a valid artifact; malformed rows skipped', () => {
    const root = tmpRoot()
    writePortCalls(
      root,
      JSON.stringify({
        schema: 'cabinet.world.port-calls/v1',
        generated_at: '2026-07-17T09:00:00+00:00',
        source_git_head: 'dab34876',
        port_calls_total: 2,
        last_port_call_date: '2026-07-02',
        lanes: {
          alpha: [
            { date: '2026-07-02', outcome_id: 'outcome-alpha-001' },
            { date: 'not-a-date', outcome_id: 'junk' },
            'garbage',
          ],
        },
      })
    )
    const a = readPortCalls(root)
    expect(a?.lanes.alpha).toEqual([
      { date: '2026-07-02', outcome_id: 'outcome-alpha-001' },
    ])
    expect(a?.last_port_call_date).toBe('2026-07-02')
    expect(a?.source_git_head).toBe('dab34876')
  })

  it('wrong schema or unparseable JSON → null', () => {
    const root = tmpRoot()
    writePortCalls(root, JSON.stringify({ schema: 'nope/v9', lanes: {} }))
    expect(readPortCalls(root)).toBeNull()
    writePortCalls(root, '{not json')
    expect(readPortCalls(root)).toBeNull()
  })
})
