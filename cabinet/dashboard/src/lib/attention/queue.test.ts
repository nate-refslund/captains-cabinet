/**
 * attention/queue lib — census parsing, staleness, fallback shaping, and the
 * READ-ONLY ratchet over the new attention route (sister of the mailbox
 * GET-only pin: the queue API is a projection, never a door).
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {
  CENSUS_MAX_AGE_MS,
  EMPTY_QUEUE,
  fallbackFromCards,
  parseCensus,
} from './queue'

const NOW = Date.parse('2026-07-10T09:00:00Z')

function census(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    v: 1,
    generated_at: '2026-07-10T08:55:00Z',
    pending_captain_items: 2,
    pending_total: 3,
    by_class: { 'action-proposal': 2, need: 1 },
    overflow: 0,
    cap: 7,
    admission_enforced: false,
    decisions: [
      {
        id: 'sit-aaaa', kind: 'action-proposal', state: 'pending',
        class: 'action-card', urgency: 'batch',
        deadline_iso: '2026-07-11T09:00:00Z', harm_class: 'external_deadline',
        age_h: 20.5, blast: { class: 'ceiling', reach: 'external' },
        decay_stage: 'ping-now', admission: 'decisions',
        pid: 'cos|action-card|subj|2026-07-09T12:00:00Z', h: 'qabc123',
        what: 'reply to TV2 DPA counsel',
        why_now: { cost_of_delay: 'blocking', decay: 'waiting 20h' },
        refs: ['cmt-aaaaaaaaaaaa'], one_tap: { approve: 'per-item-approval' },
        blast_worst_case: 'a message reaches a human outside the machine',
        filed_by: 'officer:cos', lane: 'polads',
      },
    ],
    directions: [
      {
        id: 'need-ab12cd34', kind: 'need', state: 'pending',
        what: 'standing grant for plausible', refs: [], age_h: 40,
      },
    ],
    ...overrides,
  })
}

describe('parseCensus', () => {
  it('parses the private census into the queue payload', () => {
    const q = parseCensus(census(), NOW)
    expect(q).not.toBeNull()
    expect(q!.pendingCaptainItems).toBe(2)
    expect(q!.decisions[0].what).toBe('reply to TV2 DPA counsel')
    expect(q!.decisions[0].pid).toContain('action-card')
    expect(q!.decisions[0].blast).toEqual({ class: 'ceiling', reach: 'external' })
    expect(q!.directions[0].kind).toBe('need')
    expect(q!.source).toBe('census')
  })

  it('rejects a stale census (falls back rather than lying)', () => {
    const old = census({ generated_at: '2026-07-10T06:00:00Z' })
    expect(NOW - Date.parse('2026-07-10T06:00:00Z')).toBeGreaterThan(
      CENSUS_MAX_AGE_MS
    )
    expect(parseCensus(old, NOW)).toBeNull()
  })

  it('rejects garbage without throwing', () => {
    expect(parseCensus('not json', NOW)).toBeNull()
    expect(parseCensus('[1,2,3]', NOW)).toBeNull()
  })

  it('tolerates missing optional fields (honest nulls, never invented)', () => {
    const q = parseCensus(
      JSON.stringify({
        generated_at: '2026-07-10T08:59:00Z',
        decisions: [{ id: 'x', kind: 'need' }],
      }),
      NOW
    )
    expect(q!.decisions[0].deadline_iso).toBeNull()
    expect(q!.decisions[0].age_h).toBeNull()
    expect(q!.pendingCaptainItems).toBe(0)
  })
})

describe('fallbackFromCards', () => {
  it('shapes live binder cards as an honest degraded queue', () => {
    const q = fallbackFromCards([
      {
        cid: 'c1', subject: 's1', lane: 'polads', urgency: 'batch',
        confidence: 0.7, evidenceCount: 2, ts: '2026-07-09T10:00:00Z',
      },
    ])
    expect(q.source).toBe('redis-fallback')
    expect(q.pendingCaptainItems).toBe(1)
    expect(q.decisions[0].what).toBe('s1')
    // no invented clocks on the degraded path
    expect(q.decisions[0].deadline_iso).toBeNull()
  })

  it('EMPTY_QUEUE is the honest zero', () => {
    expect(EMPTY_QUEUE.pendingCaptainItems).toBe(0)
    expect(EMPTY_QUEUE.source).toBe('empty')
  })
})

describe('read-only ratchet — attention routes never grow a write path', () => {
  const roots = path.resolve(__dirname, '..', '..')
  const files = [
    path.join(roots, 'app', 'api', 'attention', 'queue', 'route.ts'),
    path.join(roots, 'lib', 'attention', 'queue.ts'),
  ]
  it('queue route exports GET only, auth-gated, no Redis writes', () => {
    const route = fs.readFileSync(files[0], 'utf8')
    expect(route).toMatch(/export\s+async\s+function\s+GET/)
    expect(route).not.toMatch(
      /export\s+(async\s+)?function\s+(POST|PUT|PATCH|DELETE)/
    )
    expect(route).toMatch(/cabinet_session/)
    expect(route).toMatch(/401/)
  })
  it('no write/expiry verbs anywhere in the attention lib or route', () => {
    for (const f of files) {
      const text = fs.readFileSync(f, 'utf8')
      expect(text, f).not.toMatch(
        /\.(set|del|hset|hdel|xadd|xdel|lpush|rpush|sadd|incr|decr|expire|persist)\(/i
      )
    }
  })
  it('no approve/veto verbs — the binder stays the one door', () => {
    for (const f of files) {
      const text = fs.readFileSync(f, 'utf8')
      expect(text, f).not.toMatch(/approveAction|submitVerdict|use server/)
    }
  })
})
