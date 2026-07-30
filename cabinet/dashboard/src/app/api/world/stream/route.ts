/**
 * GET /api/world/stream — SSE feed for the Cabinet World Wardroom (E1).
 *
 * Byte-for-byte clone of the /api/tasks/stream pattern (Spec 038 §4.6):
 * cookie auth, Redis Pub/Sub on cabinet:world:updated, 15s keep-alive,
 * polling fallback, disconnect cleanup.
 *
 * READ-ONLY BY DOCTRINE (observer-class; CI ratchet pins it): this route
 * exports GET only — the world never grows a write path. Data served:
 *   snapshot — cabinet:world:presence (E0b snapshot) + XREVRANGE tail of
 *              cabinet:world:chronicle (already PII-scrubbed at ingest) +
 *              grammar status (pending until the Captain merges v1).
 *   world:updated — re-emitted on the E0b daemon's pub/sub poke.
 *
 * Opaque handles (S1-F4): officer slugs are T2 (fine in this authed
 * payload) but URL-identifying params must be opaque — each officer carries
 * a server-issued `sel` handle; the client puts ONLY the handle in URLs.
 */
import { NextRequest, NextResponse } from 'next/server'
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import yaml from 'js-yaml'
import { loadGrammar } from '@/lib/world/grammar'
import { censusCountOrNull } from '@/lib/attention/queue'
import type {
  ChronicleRecord,
  PresenceSnapshot,
  SnapshotClock,
  WorldOfficer,
  WorldSnapshot,
} from '@/lib/world/types'

export const dynamic = 'force-dynamic'

const KEEPALIVE_INTERVAL_MS = 15_000
const POLL_INTERVAL_MS = 3_000
const CHRONICLE_TAIL_COUNT = 200

/**
 * Opaque URL handle for an officer slug. Opacity, not secrecy: role slugs
 * are org ids (not pid-family); the rule is that the URL string never
 * CONTAINS a slug. pid-family ids get no handles at all in E1 (unrendered).
 */
export function selHandle(slug: string): string {
  return 'h' + createHash('sha256')
    .update(`cabinet-world-sel:${slug}`)
    .digest('hex')
    .slice(0, 12)
}

/** Cached captain timezone (platform.yml is deployment config — stable). */
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

/**
 * Captain-local wall clock, stamped onto the snapshot (grammar v2 `night`
 * block). This route is the ONE sanctioned wall-clock door — the render
 * path consumes the value as data and never reads a clock itself.
 */
function captainClock(): SnapshotClock | null {
  try {
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: captainTimezone(),
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(new Date())
    const hour = Number(parts.find((p) => p.type === 'hour')?.value)
    const minute = Number(parts.find((p) => p.type === 'minute')?.value)
    if (!Number.isFinite(hour) || !Number.isFinite(minute)) return null
    // Intl may render midnight as "24" in some ICU builds — normalize.
    return { hour: hour % 24, minute }
  } catch {
    return null // honest absence: the world falls back to night-at-bunk
  }
}

type RedisLike = {
  get: (key: string) => Promise<string | null>
  xrevrange: (
    key: string,
    end: string,
    start: string,
    countToken: 'COUNT',
    count: number
  ) => Promise<Array<[string, string[]]>>
  quit?: () => Promise<unknown>
  disconnect?: () => void
}

/**
 * pending_captain_items (world-spec §14 P1, command-center Stage 1): the ONE
 * glance int the HUD chip, lantern gantry, and mailbox flag all share —
 * |Decisions| incl. overflow, from the census artifact the framework's 300s
 * surface drain writes. Cheap fs read per snapshot (no extra Redis client on
 * the 3s poll path).
 *
 * NULL when no reading was obtained. It used to return 0 there, which put a
 * confident "nothing is waiting" on every snapshot the world ever emitted
 * while the drain was dead — the same guess /queue was making, on the wire.
 * A renderer that hides its chip at 0 must NOT hide it at null.
 *
 * The decision lives in the lib (`censusCountOrNull`) rather than here because
 * a helper inside a route file cannot be unit-tested: reverting this line to
 * `return 0` left the whole suite green under adversarial review.
 */
const pendingCaptainItems = censusCountOrNull

async function readSnapshot(redis: RedisLike | null): Promise<WorldSnapshot> {
  const grammarLoaded = loadGrammar()
  const grammar = {
    pending: grammarLoaded.pending,
    showGrammarVersion: grammarLoaded.showGrammar?.version ?? null,
    morphologyVersion: grammarLoaded.morphology?.version ?? null,
    codexCoverage: grammarLoaded.codexCoverage,
  }
  if (!redis) {
    return {
      connectedAt: new Date().toISOString(),
      killswitch: false,
      iidHigh: 0,
      officers: [],
      chronicle: [],
      grammar,
      clock: captainClock(),
      pendingCaptainItems: pendingCaptainItems(),
    }
  }
  let presence: PresenceSnapshot | null = null
  try {
    const raw = await redis.get('cabinet:world:presence')
    if (raw) presence = JSON.parse(raw) as PresenceSnapshot
  } catch {
    presence = null
  }
  const officers: WorldOfficer[] = []
  if (presence?.officers) {
    for (const [slug, p] of Object.entries(presence.officers).sort()) {
      officers.push({ slug, sel: selHandle(slug), presence: p })
    }
  }
  const chronicle: ChronicleRecord[] = []
  try {
    const rows = await redis.xrevrange(
      'cabinet:world:chronicle',
      '+',
      '-',
      'COUNT',
      CHRONICLE_TAIL_COUNT
    )
    for (const [, fields] of rows) {
      const idx = fields.indexOf('line')
      if (idx >= 0 && fields[idx + 1]) {
        try {
          chronicle.push(JSON.parse(fields[idx + 1]) as ChronicleRecord)
        } catch {
          /* skip unparseable */
        }
      }
    }
    chronicle.reverse() // oldest → newest
  } catch {
    /* stream absent — honest empty */
  }
  return {
    connectedAt: new Date().toISOString(),
    killswitch: presence?.killswitch ?? false,
    iidHigh: presence?.iid_high ?? 0,
    officers,
    chronicle,
    grammar,
    clock: captainClock(),
    pendingCaptainItems: pendingCaptainItems(),
  }
}

export async function GET(req: NextRequest) {
  // Verify auth cookie exists (same check as layout.tsx / tasks stream).
  const { cookies } = await import('next/headers')
  const cookieStore = await cookies()
  const sessionToken = cookieStore.get('cabinet_session')?.value
  if (!sessionToken) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const stream = new ReadableStream({
    async start(controller) {
      let closed = false
      let keepaliveTimer: ReturnType<typeof setInterval> | null = null
      let pollTimer: ReturnType<typeof setInterval> | null = null
      let subClient: {
        subscribe: (channel: string) => Promise<unknown>
        unsubscribe: (channel: string) => void
        on: (event: string, handler: (...args: unknown[]) => void) => void
        quit?: () => Promise<unknown>
        disconnect?: () => void
      } | null = null
      let dataClient: RedisLike | null = null

      function emit(eventName: string, data: unknown) {
        if (closed) return
        try {
          controller.enqueue(
            new TextEncoder().encode(
              `event: ${eventName}\ndata: ${JSON.stringify(data)}\n\n`
            )
          )
        } catch {
          cleanup()
        }
      }

      function ping() {
        if (closed) return
        try {
          controller.enqueue(new TextEncoder().encode(':\n\n'))
        } catch {
          cleanup()
        }
      }

      function cleanup() {
        if (closed) return
        closed = true
        if (keepaliveTimer) clearInterval(keepaliveTimer)
        if (pollTimer) clearInterval(pollTimer)
        if (subClient) {
          try {
            subClient.unsubscribe('cabinet:world:updated')
            if (typeof subClient.quit === 'function') subClient.quit()
            else if (typeof subClient.disconnect === 'function') subClient.disconnect()
          } catch { /* ignore */ }
          subClient = null
        }
        if (dataClient) {
          try {
            if (typeof dataClient.quit === 'function') dataClient.quit()
            else if (typeof dataClient.disconnect === 'function') dataClient.disconnect()
          } catch { /* ignore */ }
          dataClient = null
        }
        try { controller.close() } catch { /* already closed */ }
      }

      const REDIS_URL = process.env.REDIS_URL
      if (REDIS_URL) {
        try {
          const { default: Redis } = await import('ioredis')
          dataClient = new Redis(REDIS_URL) as unknown as RedisLike
        } catch {
          dataClient = null
        }
      }

      // Initial snapshot (instant client join — E0b presence + tail).
      emit('world:snapshot', await readSnapshot(dataClient))

      keepaliveTimer = setInterval(() => {
        if (closed) return
        try { ping() } catch { cleanup() }
      }, KEEPALIVE_INTERVAL_MS)

      if (REDIS_URL) {
        try {
          const { default: Redis } = await import('ioredis')
          const sub = new Redis(REDIS_URL)
          subClient = sub

          sub.subscribe('cabinet:world:updated').catch((err: unknown) => {
            console.warn('[world/stream] Redis subscribe error', err)
            cleanup()
          })

          sub.on('message', async () => {
            if (closed) return
            // Re-read the snapshot on each poke: presence + fresh tail.
            emit('world:updated', await readSnapshot(dataClient))
          })

          sub.on('error', (err: Error) => {
            console.warn('[world/stream] Redis sub error', err)
            cleanup()
          })
        } catch (err) {
          console.warn('[world/stream] Redis Pub/Sub unavailable, polling', err)
          subClient = null
        }
      }

      if (!subClient) {
        pollTimer = setInterval(async () => {
          if (closed) return
          emit('world:updated', await readSnapshot(dataClient))
        }, POLL_INTERVAL_MS)
      }

      req.signal?.addEventListener('abort', () => {
        cleanup()
      })
    },
  })

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  })
}
