/**
 * attention/queue lib — census parsing, staleness, fallback shaping, and the
 * READ-ONLY ratchet over the new attention route (sister of the mailbox
 * GET-only pin: the queue API is a projection, never a door).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {
  CENSUS_MAX_AGE_MS,
  UNMEASURED_GLYPH,
  attentionGlance,
  badgeState,
  censusCountOrNull,
  censusRejectionReason,
  fallbackFromCards,
  mastheadCount,
  parseCensus,
  readCensus,
  readQueue,
  unknownQueue,
  type QueuePayload,
} from './queue'

// A fake ioredis so the degraded leg can be exercised at BOTH ends: reachable
// and holding nothing (the live 2026-07-30 shape — Redis up, zero cards) and
// unreachable. `[]` used to mean both, which is half of the defect under test.
const redisState: { cards: Record<string, string>; throws: boolean } = {
  cards: {},
  throws: false,
}
vi.mock('ioredis', () => ({
  default: class {
    constructor() {
      if (redisState.throws) throw new Error('ECONNREFUSED')
    }
    async scan(): Promise<[string, string[]]> {
      return ['0', Object.keys(redisState.cards)]
    }
    async get(k: string): Promise<string | null> {
      return redisState.cards[k] ?? null
    }
    async quit() {}
    disconnect() {}
  },
}))

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
        what: 'reply to Kanal9 contract counsel',
        why_now: { cost_of_delay: 'blocking', decay: 'waiting 20h' },
        refs: ['cmt-aaaaaaaaaaaa'], one_tap: { approve: 'per-item-approval' },
        blast_worst_case: 'a message reaches a human outside the machine',
        filed_by: 'officer:cos', lane: 'bakery',
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
    expect(q!.decisions[0].what).toBe('reply to Kanal9 contract counsel')
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

  it('carries the census age, so the surface can say how old', () => {
    const r = readCensus(census(), NOW)
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.payload.censusAgeMs).toBe(5 * 60 * 1000)
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
    // Was `toBe(0)`. A census that does not carry the count has not measured
    // it, and a fresh-but-uncounted reading painting the green all-clear was
    // the same guess one level in (adversarial review, 2026-07-30).
    expect(q!.pendingCaptainItems).toBeNull()
    expect(q!.unknownReason).toMatch(/carries no count/)
    expect(attentionGlance(q!).state).toBe('unknown')
  })

  it('a fresh census with a NON-NUMERIC count measures nothing', () => {
    for (const bad of ['2', null, {}, [], Number.NaN, undefined]) {
      const q = parseCensus(census({ pending_captain_items: bad }), NOW)
      expect(q, String(bad)).not.toBeNull()
      expect(q!.pendingCaptainItems, String(bad)).toBeNull()
      expect(attentionGlance(q!).state, String(bad)).toBe('unknown')
    }
  })
})

describe('fallbackFromCards', () => {
  it('shapes live binder cards as an honest degraded queue', () => {
    const q = fallbackFromCards([
      {
        cid: 'c1', subject: 's1', lane: 'bakery', urgency: 'batch',
        confidence: 0.7, evidenceCount: 2, ts: '2026-07-09T10:00:00Z',
      },
    ])
    expect(q.source).toBe('redis-fallback')
    expect(q.pendingCaptainItems).toBe(1)
    expect(q.decisions[0].what).toBe('s1')
    // no invented clocks on the degraded path
    expect(q.decisions[0].deadline_iso).toBeNull()
  })

  it('an empty live read is UNKNOWN, not a zero', () => {
    // Structural, not just a call-site convention: the only way to build a
    // count from cards is this function, and it refuses to build 0.
    const q = fallbackFromCards([])
    expect(q.source).toBe('unknown')
    expect(q.pendingCaptainItems).toBeNull()
    expect(q.unknownReason).toBeTruthy()
  })
})

// ── THE LAW: a reading nobody took must never render as a number ────────────
//
// Every arm below is red against the pre-2026-07-30 code, which returned
// EMPTY_QUEUE (pendingCaptainItems: 0, source: 'empty') on all of these paths
// and whose own test called that "the honest zero".

describe('unmeasured is not zero', () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'census-test-'))
  const savedDir = process.env.CABINET_ATTENTION_DIR
  const savedRedis = process.env.REDIS_URL

  function writeCensus(text: string, dir = tmpRoot): void {
    fs.mkdirSync(dir, { recursive: true })
    fs.writeFileSync(path.join(dir, 'queue.json'), text)
  }

  beforeEach(() => {
    process.env.CABINET_ATTENTION_DIR = tmpRoot
    delete process.env.REDIS_URL
    redisState.cards = {}
    redisState.throws = false
    try {
      fs.unlinkSync(path.join(tmpRoot, 'queue.json'))
    } catch {
      /* already absent */
    }
  })
  afterEach(() => {
    if (savedDir === undefined) delete process.env.CABINET_ATTENTION_DIR
    else process.env.CABINET_ATTENTION_DIR = savedDir
    if (savedRedis === undefined) delete process.env.REDIS_URL
    else process.env.REDIS_URL = savedRedis
  })

  function expectUnknown(q: QueuePayload): void {
    expect(q.source).toBe('unknown')
    expect(q.pendingCaptainItems).toBeNull()
    expect(q.pendingTotal).toBeNull()
    expect(q.unknownReason).toBeTruthy()
    expect(attentionGlance(q).state).toBe('unknown')
  }

  it('THE REPRODUCTION: a 9-day-old census renders no number', async () => {
    // The exact live shape on 2026-07-30: a real reading saying 2 items are
    // waiting, taken nine days ago, with the org that writes it dead.
    const gen = new Date(NOW - 9 * 24 * 3600 * 1000).toISOString()
    writeCensus(census({ generated_at: gen }))
    const q = await readQueue(NOW)
    expectUnknown(q)
    // and it says how old, so the reader can judge it
    expect(q.unknownReason).toMatch(/stopped updating/)
    expect(q.censusAgeMs).toBeGreaterThan(8 * 24 * 3600 * 1000)
  })

  it('a fresh census still counts — the arm can tell measured from not', async () => {
    writeCensus(census({ generated_at: new Date(NOW - 60_000).toISOString() }))
    const q = await readQueue(NOW)
    expect(q.source).toBe('census')
    expect(q.pendingCaptainItems).toBe(2)
    expect(attentionGlance(q)).toEqual({ state: 'count', n: 2 })
  })

  it('a fresh census that really counted zero IS an all-clear', async () => {
    writeCensus(
      census({
        generated_at: new Date(NOW - 60_000).toISOString(),
        pending_captain_items: 0,
      })
    )
    const q = await readQueue(NOW)
    expect(q.source).toBe('census')
    expect(attentionGlance(q)).toEqual({ state: 'clear' })
  })

  it('an absent census renders no number', async () => {
    expectUnknown(await readQueue(NOW))
  })

  it('a malformed census renders no number', async () => {
    writeCensus('{ not json at all')
    expectUnknown(await readQueue(NOW))
  })

  it('an EMPTY census document renders no number', async () => {
    writeCensus('{}')
    expectUnknown(await readQueue(NOW))
  })

  it('an UNDATED census renders no number (was accepted as fresh)', async () => {
    // Degenerate end: with no generated_at the staleness test used to be
    // skipped entirely, so an arbitrarily old reading passed as current.
    const doc = JSON.parse(census()) as Record<string, unknown>
    delete doc.generated_at
    writeCensus(JSON.stringify(doc))
    const r = readCensus(JSON.stringify(doc), NOW)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.why).toBe('undated')
    expectUnknown(await readQueue(NOW))
  })

  it('an UNPARSEABLE stamp renders no number', async () => {
    writeCensus(census({ generated_at: 'sometime last week' }))
    expectUnknown(await readQueue(NOW))
  })

  it('a FUTURE-dated census renders no number (clock skew)', async () => {
    const ahead = new Date(NOW + 3 * CENSUS_MAX_AGE_MS).toISOString()
    const r = readCensus(census({ generated_at: ahead }), NOW)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.why).toBe('future-dated')
    writeCensus(census({ generated_at: ahead }))
    expectUnknown(await readQueue(NOW))
  })

  it('ordinary small skew still reads as measured', () => {
    const ahead = new Date(NOW + 30_000).toISOString()
    expect(readCensus(census({ generated_at: ahead }), NOW).ok).toBe(true)
  })

  it('the freshness boundary is exact in both directions', () => {
    const at = new Date(NOW - CENSUS_MAX_AGE_MS).toISOString()
    const over = new Date(NOW - CENSUS_MAX_AGE_MS - 1000).toISOString()
    expect(readCensus(census({ generated_at: at }), NOW).ok).toBe(true)
    const r = readCensus(census({ generated_at: over }), NOW)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.why).toBe('stale')
  })

  it('stale census + REACHABLE but empty live view is still unknown', async () => {
    // The live 2026-07-30 box: redis up, `cabinet:action:*` genuinely zero.
    // That view sees one class of item, so it cannot clear the whole list.
    process.env.REDIS_URL = 'redis://127.0.0.1:6399'
    writeCensus(census({ generated_at: '2026-07-01T00:00:00Z' }))
    const q = await readQueue(NOW)
    expectUnknown(q)
    expect(q.unknownReason).toMatch(/only sees one kind/)
  })

  it('stale census + UNREACHABLE live view is unknown, and says which', async () => {
    process.env.REDIS_URL = 'redis://127.0.0.1:6399'
    redisState.throws = true
    writeCensus(census({ generated_at: '2026-07-01T00:00:00Z' }))
    const q = await readQueue(NOW)
    expectUnknown(q)
    expect(q.unknownReason).toMatch(/could not be reached/)
  })

  it('stale census + live cards present degrades to a real count', async () => {
    process.env.REDIS_URL = 'redis://127.0.0.1:6399'
    redisState.cards = {
      'cabinet:action:c1': JSON.stringify({
        cid: 'c1',
        subject: 'a real pending card',
        lane: 'bakery',
        urgency: 'batch',
        ts: '2026-07-10T08:00:00Z',
      }),
    }
    writeCensus(census({ generated_at: '2026-07-01T00:00:00Z' }))
    const q = await readQueue(NOW)
    expect(q.source).toBe('redis-fallback')
    expect(attentionGlance(q)).toEqual({ state: 'count', n: 1 })
  })

  it('every rejection has a plain sentence naming what is missing', () => {
    for (const why of ['stale', 'undated', 'future-dated', 'malformed'] as const) {
      const s = censusRejectionReason({
        ok: false,
        why,
        ageMs: 9 * 24 * 3600 * 1000,
        generatedAt: '2026-07-21T16:36:13Z',
      })
      expect(s.length).toBeGreaterThan(20)
      expect(s).not.toMatch(/TODO|unknown error/i)
    }
  })

  it('attentionGlance never reports clear or a count without a reading', () => {
    for (const q of [
      unknownQueue('because'),
      fallbackFromCards([]),
      { ...unknownQueue('because'), pendingCaptainItems: Number.NaN },
    ]) {
      expect(attentionGlance(q).state).toBe('unknown')
    }
  })
})

// ── the RENDER decisions, driven ───────────────────────────────────────────
//
// The two React surfaces cannot be rendered in this package (vitest
// `environment: 'node'`, no DOM), and an adversarial pass proved that source
// greps do not substitute: a `false &&` in the page satisfied every grep while
// printing "0 need you". So the decisions live here, where a mutation to them
// turns something red, and the masthead numeral is a STRING — a surface with a
// broken branch can print "—", never a zero nobody counted.

describe('mastheadCount — the numeral a surface is handed', () => {
  it('a real count prints its digits', () => {
    expect(mastheadCount(parseCensus(census(), NOW)!)).toBe('2')
  })
  it('a MEASURED zero prints 0 — the all-clear is still sayable', () => {
    const q = parseCensus(census({ pending_captain_items: 0 }), NOW)!
    expect(mastheadCount(q)).toBe('0')
    expect(attentionGlance(q)).toEqual({ state: 'clear' })
  })
  it('an unmeasured count prints the em-dash, never a digit', () => {
    for (const q of [
      unknownQueue('because'),
      fallbackFromCards([]),
      parseCensus(census({ pending_captain_items: undefined }), NOW)!,
    ]) {
      expect(mastheadCount(q)).toBe(UNMEASURED_GLYPH)
      expect(mastheadCount(q)).not.toMatch(/[0-9]/)
    }
  })
})

describe('badgeState — hiding is a claim, so only a measurement may hide', () => {
  it('not asked yet shows nothing', () => {
    expect(badgeState(undefined)).toEqual({ show: 'nothing' })
  })
  it('asked and unknowable shows the unknown chip, never nothing', () => {
    expect(badgeState(null)).toEqual({ show: 'unknown' })
    expect(badgeState(Number.NaN)).toEqual({ show: 'unknown' })
  })
  it('a measured zero hides — that one is honest', () => {
    expect(badgeState(0)).toEqual({ show: 'nothing' })
  })
  it('a real count shows', () => {
    expect(badgeState(3)).toEqual({ show: 'count', n: 3 })
  })
})

describe('censusCountOrNull — the int the world SSE puts on the wire', () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'census-wire-'))
  const saved = process.env.CABINET_ATTENTION_DIR
  beforeEach(() => {
    process.env.CABINET_ATTENTION_DIR = tmpRoot
  })
  afterEach(() => {
    if (saved === undefined) delete process.env.CABINET_ATTENTION_DIR
    else process.env.CABINET_ATTENTION_DIR = saved
  })
  it('a fresh census puts the real number on the wire', () => {
    fs.writeFileSync(
      path.join(tmpRoot, 'queue.json'),
      census({ generated_at: new Date(NOW - 60_000).toISOString() })
    )
    expect(censusCountOrNull(NOW)).toBe(2)
  })
  it('a stale census puts NULL on the wire, never 0', () => {
    fs.writeFileSync(
      path.join(tmpRoot, 'queue.json'),
      census({ generated_at: '2026-07-01T00:00:00Z' })
    )
    expect(censusCountOrNull(NOW)).toBeNull()
  })
  it('an absent census puts NULL on the wire', () => {
    fs.unlinkSync(path.join(tmpRoot, 'queue.json'))
    expect(censusCountOrNull(NOW)).toBeNull()
  })
})

describe('no surface re-derives the all-clear from a bare zero', () => {
  const src = path.resolve(__dirname, '..', '..')
  it('the queue page decides through attentionGlance and mastheadCount', () => {
    const page = fs.readFileSync(
      path.join(src, 'app', '(authenticated)', 'queue', 'page.tsx'),
      'utf8'
    )
    expect(page).toMatch(/attentionGlance\(/)
    expect(page).toMatch(/mastheadCount\(/)
    expect(page).not.toMatch(/pendingCaptainItems/)
    expect(page).toMatch(/glance\.state === 'clear'/)
  })
  it('no client component imports the census reader (it reads node:fs)', () => {
    // FOUND BY RUNNING THE APP, not by the suite: pointing the badge at
    // lib/attention/queue.ts broke the Turbopack client bundle and 500'd every
    // page, while `tsc --noEmit` and all 2900 vitest arms stayed green — both
    // run in node, where a node-only import is invisible. The client-safe half
    // lives in lib/attention/glance.ts; this arm keeps it that way.
    const offenders: string[] = []
    const walk = (dir: string): void => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, e.name)
        if (e.isDirectory()) walk(p)
        else if (/\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name)) {
          const text = fs.readFileSync(p, 'utf8')
          if (!/^\s*['"]use client['"]/m.test(text)) continue
          if (/from\s+['"]@\/lib\/attention\/queue['"]/.test(text)) {
            offenders.push(path.relative(src, p))
          }
        }
      }
    }
    walk(src)
    expect(offenders).toEqual([])
    // the sweep must be real — a corpus of zero client files would pass vacuously
    const clientFiles = fs
      .readFileSync(path.join(src, 'components', 'needs-you-badge.tsx'), 'utf8')
      .startsWith("'use client'")
    expect(clientFiles).toBe(true)
  })

  it('the badge starts unknown and routes through badgeState', () => {
    const badge = fs.readFileSync(
      path.join(src, 'components', 'needs-you-badge.tsx'),
      'utf8'
    )
    expect(badge).toMatch(/useState<number \| null \| undefined>\(undefined\)/)
    expect(badge).toMatch(/badgeState\(/)
    // no second, inline zero-test that could disagree with badgeState
    expect(badge).not.toMatch(/count <= 0/)
    // EXACTLY ONE way to render nothing, and it is the measured-zero arm.
    // Hiding is a claim ("nothing is waiting"), so a second `return null` —
    // which is all a mutation needs to silence the unknown chip — is red.
    const code = badge
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/(^|\s)\/\/[^\n]*/g, '$1')
    expect(code.match(/return null/g) ?? []).toHaveLength(1)
    expect(code).toMatch(/if \(state\.show === 'nothing'\) return null/)
  })
  it('the world SSE route reads the count through the lib, not inline', () => {
    const raw = fs.readFileSync(
      path.join(src, 'app', 'api', 'world', 'stream', 'route.ts'),
      'utf8'
    )
    // COMMENTS ARE NOT CODE — the same rule ratchets.test.ts learned, in the
    // other direction: this file's own comment quotes `return 0` while
    // explaining why it is gone, and an unstripped grep reds on the prose.
    const code = raw
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/(^|\s)\/\/[^\n]*/g, '$1')
    // Pin the BINDING, not merely the import: `const pendingCaptainItems =
    // () => 0` keeps the import line and passes a looser grep (measured — the
    // reviewer's mutation f survived exactly that). This route's SSE handler
    // cannot be driven from this suite (auth + Redis + a stream), so the one
    // line that can lie is pinned by shape; the behaviour it delegates to is
    // driven directly above.
    expect(code).toMatch(/const pendingCaptainItems = censusCountOrNull\b/)
    expect(code).not.toMatch(/return\s+0\b/)
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
    // Signature-verified session (equal-authority-door law on the READ
    // leg too): presence-only cookie checks are not auth.
    expect(route).toMatch(/verifySessionValue\(/)
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
