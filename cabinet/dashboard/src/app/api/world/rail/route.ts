/**
 * GET /api/world/rail — portrait-rail data (T3 UI layer, spec §9.1).
 *
 * READ-ONLY (observer-class; CI ratchet #2 pins GET-only): per-officer
 * activity freshness, status-ring derivation, and TODAY's wage strip from
 * the cost ledger. Every value cites its exact Redis key on the inspect
 * card; missing data returns null → the rail renders grey '—' (strict
 * cost-viz ruling: absence is never $0.00-as-fact).
 *
 * Sources (all live-verified 2026-07-09, ui-pack.md §1):
 *   cabinet:officer:activity:<slug>   string JSON {verb, object, since}
 *   cabinet:officer:expected:<slug>   presence-expectation keys
 *   cabinet:cost:tokens:daily:<date>  hash, <officer>[_project]_cost_micro
 *
 * Wall time enters HERE (server), as data: fresh_s and since_hhmm are
 * computed server-side so the render path never reads a clock (determinism
 * ratchet #4 covers lib/world + components/world).
 */
import { NextRequest, NextResponse } from 'next/server'
import fs from 'node:fs'
import path from 'node:path'
import yaml from 'js-yaml'
import { freshSeconds, railOrder, ringFor } from '@/lib/world/ui-cards'

export const dynamic = 'force-dynamic'

export interface RailSlot {
  slug: string
  verb: string | null
  object: string | null
  since: string | null
  /** Captain-local HH:MM of `since` (timezone law) — display-ready. */
  sinceHhmm: string | null
  freshS: number | null
  ring: 'green' | 'amber' | 'grey'
  glyph: string
  /** Today's spend in microdollars; null = unmeasured (grey '—'). */
  costMicro: number | null
}

export interface RailPayload {
  slots: RailSlot[]
  /** Max officer spend today (bar normalization); null when no data. */
  dayMaxMicro: number | null
  proof: {
    activityKey: string
    costKey: string
  }
}

let captainTz: string | null = null
function captainTimezone(): string {
  if (captainTz !== null) return captainTz
  try {
    const root =
      process.env.CABINET_ROOT && fs.existsSync(process.env.CABINET_ROOT)
        ? process.env.CABINET_ROOT
        : path.resolve(process.cwd(), '..', '..')
    const raw = fs.readFileSync(
      path.join(root, 'instance', 'config', 'platform.yml'),
      'utf8'
    )
    const cfg = (yaml.load(raw, { schema: yaml.JSON_SCHEMA }) ?? {}) as Record<
      string,
      unknown
    >
    captainTz =
      typeof cfg.captain_timezone === 'string' ? cfg.captain_timezone : 'UTC'
  } catch {
    captainTz = 'UTC'
  }
  return captainTz
}

function hhmmLocal(iso: string | null): string | null {
  if (!iso) return null
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return null
  try {
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: captainTimezone(),
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(new Date(t))
    const hh = parts.find((p) => p.type === 'hour')?.value
    const mm = parts.find((p) => p.type === 'minute')?.value
    return hh && mm ? `${Number(hh) % 24}`.padStart(2, '0') + `:${mm}` : null
  } catch {
    return null
  }
}

type RedisLike = {
  get: (key: string) => Promise<string | null>
  keys: (pattern: string) => Promise<string[]>
  hgetall: (key: string) => Promise<Record<string, string>>
  quit?: () => Promise<unknown>
  disconnect?: () => void
}

export async function GET(_req: NextRequest) {
  // Auth gate cloned from /api/world/stream (ratchet #7 pattern).
  const { cookies } = await import('next/headers')
  const cookieStore = await cookies()
  if (!cookieStore.get('cabinet_session')?.value) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const today = new Date().toISOString().split('T')[0]
  const costKey = `cabinet:cost:tokens:daily:${today}`
  const empty: RailPayload = {
    slots: [],
    dayMaxMicro: null,
    proof: { activityKey: 'cabinet:officer:activity:<slug>', costKey },
  }

  const REDIS_URL = process.env.REDIS_URL
  if (!REDIS_URL) return NextResponse.json(empty)

  let redis: RedisLike | null = null
  try {
    const { default: Redis } = await import('ioredis')
    redis = new Redis(REDIS_URL) as unknown as RedisLike
    const [activityKeys, expectedKeys, costHash] = await Promise.all([
      redis.keys('cabinet:officer:activity:*'),
      redis.keys('cabinet:officer:expected:*'),
      redis.hgetall(costKey),
    ])
    const expected = new Set(
      expectedKeys
        .map((k) => k.replace('cabinet:officer:expected:', ''))
        .filter((s) => !s.includes(':'))
    )
    const slugs = railOrder(
      Array.from(
        new Set([
          ...activityKeys.map((k) => k.replace('cabinet:officer:activity:', '')),
          ...expected,
        ])
      )
    )
    const nowMs = Date.now()
    const slots: RailSlot[] = []
    let dayMax: number | null = null
    for (const slug of slugs) {
      let verb: string | null = null
      let object: string | null = null
      let since: string | null = null
      let present = false
      try {
        const raw = await redis.get(`cabinet:officer:activity:${slug}`)
        if (raw) {
          const a = JSON.parse(raw) as Record<string, unknown>
          verb = typeof a.verb === 'string' && a.verb ? a.verb : null
          object = typeof a.object === 'string' && a.object ? a.object : null
          since = typeof a.since === 'string' && a.since ? a.since : null
          present = true
        }
      } catch {
        /* honest absence */
      }
      // Cost: dual-shape sum (legacy <slug>_cost_micro + pool-mode
      // <slug>_<project>_cost_micro) — mirrors lib/redis.ts FW-072 logic.
      // ABSENT stays null (the rail already renders that as the honest '—').
      // PRESENT-BUT-GARBAGE used to become a measured $0.00: `parseInt('x') || 0`
      // contributed a zero and the `?? 0` promoted null to a real number, so a
      // corrupt cost field printed a confident nothing-spent for that officer.
      let micro: number | null = null
      let costMalformed = false
      if (costHash) {
        for (const [field, value] of Object.entries(costHash)) {
          if (
            field === `${slug}_cost_micro` ||
            (field.startsWith(`${slug}_`) && field.endsWith('_cost_micro'))
          ) {
            const n = Number.parseInt(value ?? '', 10)
            if (!Number.isFinite(n)) {
              costMalformed = true
              continue
            }
            micro = (micro ?? 0) + n
          }
        }
      }
      if (costMalformed) micro = null
      if (micro !== null) dayMax = Math.max(dayMax ?? 0, micro)
      const freshS = freshSeconds(since, nowMs)
      const { ring, glyph } = ringFor({ freshS, expected: expected.has(slug), present })
      slots.push({
        slug,
        verb,
        object,
        since,
        sinceHhmm: hhmmLocal(since),
        freshS,
        ring,
        glyph,
        costMicro: micro,
      })
    }
    return NextResponse.json({
      slots,
      dayMaxMicro: dayMax,
      proof: { activityKey: 'cabinet:officer:activity:<slug>', costKey },
    } satisfies RailPayload)
  } catch {
    return NextResponse.json(empty)
  } finally {
    try {
      if (redis?.quit) await redis.quit()
      else redis?.disconnect?.()
    } catch {
      /* ignore */
    }
  }
}
