'use client'

/**
 * PortraitRail — the optional always-on left rail (T3, spec §9.1).
 *
 * Hybrid DOM rail: chrome, NOT world — it never enters the gated world
 * framebuffer (the aesthetic gate judges the world; the rail reuses the
 * sprite pipeline via image-rendering: pixelated at integer scale).
 *
 * Slots: roster officers (cos first; the 'unknown' chronicle actor never
 * gets a slot — no attribution guess). Toggleable (P key / the HUD
 * button); collapses to 16px status dots in ambient mode.
 *
 * Portrait: deterministic per-officer composition from LimeZu Portrait
 * Pieces seeded fnv1a(slug) — derived at build by
 * cabinet/scripts/world-compose-portraits.py, manifest'd with provenance
 * (same officer, same face, forever). Talk animation (10-frame sheet row)
 * plays only while the activity verb is <5 min fresh, driven by the
 * LOGICAL tick — no wall clock in this tree (determinism ratchet #4);
 * freshness itself is server-computed by /api/world/rail.
 *
 * Status ring: reserved salience palette, dual-coded (color + glyph);
 * red NEVER (killswitch-only). Cost strip: strict cost-viz — today's
 * `<officer>_cost_micro` as DOM-mono `$X.XX` + an 8px bar normalized to
 * the day's max; missing → grey '—' (never $0.00-as-fact).
 */
import { useEffect, useState } from 'react'
import type { RailPayload, RailSlot } from '@/app/api/world/rail/route'
import { ASSET_BASE, type WorldAssetManifest } from '@/lib/world/sprites'
import { formatMicro, TALK_FRESH_S } from '@/lib/world/ui-cards'

/** Rail refresh cadence (ms) — freshness/cost re-read, server-computed. */
const RAIL_POLL_MS = 30_000
/** Native portrait cell (Portrait_Generator 32x32-family sheet cell). */
const CELL = 64
/** Talk sheet geometry: 10 frames per animation row (pack fact). */
const TALK_FRAMES = 10

const RING_CLASS: Record<RailSlot['ring'], string> = {
  green: 'border-emerald-400',
  amber: 'border-amber-400',
  grey: 'border-zinc-600',
}
const RING_TEXT: Record<RailSlot['ring'], string> = {
  green: 'text-emerald-300',
  amber: 'text-amber-300',
  grey: 'text-zinc-500',
}

let manifestPromise: Promise<WorldAssetManifest | null> | null = null
function loadManifest(): Promise<WorldAssetManifest | null> {
  if (!manifestPromise) {
    manifestPromise = fetch(ASSET_BASE + 'manifest.json')
      .then((r) => (r.ok ? (r.json() as Promise<WorldAssetManifest>) : null))
      .catch(() => null)
  }
  return manifestPromise
}

export default function PortraitRail({
  tick,
  onInspect,
}: {
  /** Logical director tick — the ONLY animation clock in this tree. */
  tick: number
  /** Click slot → the universal WHAT/NOW/PROOF inspect card. */
  onInspect: (slug: string) => void
}) {
  const [rail, setRail] = useState<RailPayload | null>(null)
  const [manifest, setManifest] = useState<WorldAssetManifest | null>(null)
  const [open, setOpen] = useState(true)
  const [ambient, setAmbient] = useState(false)

  useEffect(() => {
    let alive = true
    const pull = () =>
      fetch('/api/world/rail')
        .then((r) => (r.ok ? (r.json() as Promise<RailPayload>) : null))
        .then((p) => {
          if (alive && p) setRail(p)
        })
        .catch(() => {})
    pull()
    const t = setInterval(pull, RAIL_POLL_MS)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])
  useEffect(() => {
    let alive = true
    loadManifest().then((m) => {
      if (alive) setManifest(m)
    })
    return () => {
      alive = false
    }
  }, [])
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'p' || ev.key === 'P') setOpen((v) => !v)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const slots = rail?.slots ?? []
  if (slots.length === 0) return null

  const portraitRow = (slug: string) =>
    manifest?.assets.find((r) => r.id === `portraits/portrait_${slug}`) ?? null
  const sheetRow = (slug: string) =>
    manifest?.assets.find((r) => r.id === `portraits/portrait_${slug}_sheet`) ?? null

  if (!open) {
    return (
      <button
        data-world-rail="closed"
        onClick={() => setOpen(true)}
        title="portrait rail (P)"
        className="pointer-events-auto absolute left-2 top-14 z-20 rounded bg-zinc-900/80 px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-800"
      >
        rail
      </button>
    )
  }

  return (
    <div
      data-world-rail={ambient ? 'ambient' : 'open'}
      className="pointer-events-auto absolute left-2 top-14 z-20 flex flex-col gap-2 rounded-lg bg-zinc-950/85 p-2"
    >
      <div className="flex items-center justify-between gap-2 text-[10px] text-zinc-500">
        <button
          onClick={() => setAmbient((v) => !v)}
          className="rounded px-1 hover:bg-zinc-800 hover:text-zinc-300"
          title="ambient mode — collapse to status dots"
        >
          {ambient ? 'expand' : 'ambient'}
        </button>
        <button
          onClick={() => setOpen(false)}
          className="rounded px-1 hover:bg-zinc-800 hover:text-zinc-300"
          title="hide rail (P)"
        >
          hide
        </button>
      </div>
      {slots.map((s) => {
        const still = portraitRow(s.slug)
        const sheet = sheetRow(s.slug)
        const talking = s.freshS !== null && s.freshS <= TALK_FRESH_S && sheet !== null
        // Deterministic talk frame: logical tick only (4 ticks/frame = 1s).
        const frame = talking ? Math.floor(tick / 4) % TALK_FRAMES : 0
        const stale = s.ring === 'grey'
        if (ambient) {
          return (
            <button
              key={s.slug}
              onClick={() => onInspect(s.slug)}
              title={`${s.slug} — ${s.verb ?? 'no live verb'}`}
              className={`h-4 w-4 rounded-full border-2 ${RING_CLASS[s.ring]} bg-zinc-800`}
            >
              <span className="sr-only">{s.slug}</span>
            </button>
          )
        }
        return (
          <button
            key={s.slug}
            onClick={() => onInspect(s.slug)}
            className="group flex w-40 flex-col items-start gap-1 rounded border border-zinc-800 bg-zinc-900/70 p-1.5 text-left hover:border-zinc-600"
          >
            <div className="flex items-center gap-2">
              <div
                className={`relative overflow-hidden rounded border-2 ${RING_CLASS[s.ring]}`}
                style={{ width: CELL, height: CELL }}
              >
                {still ? (
                  <div
                    aria-label={`${s.slug} portrait`}
                    style={{
                      width: CELL,
                      height: CELL,
                      backgroundImage: `url(${ASSET_BASE}${(talking && sheet ? sheet : still).path})`,
                      backgroundPosition: talking && sheet ? `-${frame * CELL}px 0px` : '0px 0px',
                      backgroundRepeat: 'no-repeat',
                      imageRendering: 'pixelated',
                      filter: stale ? 'grayscale(0.8) brightness(0.7)' : undefined,
                    }}
                  />
                ) : (
                  // Visible placeholder doctrine: no derived portrait row in
                  // the manifest yet → initials block, never invented art.
                  <div
                    data-portrait="placeholder"
                    className="flex h-full w-full items-center justify-center bg-zinc-800 font-mono text-lg text-zinc-400"
                    title="no portrait asset — run world-compose-portraits.py"
                  >
                    {s.slug.slice(0, 2)}
                  </div>
                )}
              </div>
              <div className="min-w-0">
                <div className="truncate text-xs font-semibold text-zinc-100">
                  {s.slug}
                </div>
                <div className={`font-mono text-[10px] ${RING_TEXT[s.ring]}`}>
                  {s.glyph}{' '}
                  {s.ring === 'green'
                    ? 'active'
                    : s.ring === 'amber'
                      ? 'expected — quiet'
                      : 'unmeasured'}
                </div>
              </div>
            </div>
            <div
              className={`w-full truncate font-mono text-[10px] ${stale ? 'text-zinc-600' : 'text-zinc-300'}`}
            >
              {s.verb
                ? `${s.verb}${s.object ? ` · ${s.object.slice(0, 24)}` : ''}`
                : s.sinceHhmm
                  ? `idle since ${s.sinceHhmm}`
                  : 'no live verb'}
            </div>
            {/* strict cost-viz: DOM-mono numeral + 8px bar vs day max */}
            <div className="flex w-full items-center gap-1">
              <span
                className={`font-mono text-[10px] ${s.costMicro === null ? 'text-zinc-600' : 'text-zinc-200'}`}
              >
                {formatMicro(s.costMicro)}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-sm bg-zinc-800">
                {s.costMicro !== null && rail?.dayMaxMicro ? (
                  <div
                    className="h-full bg-zinc-500"
                    style={{
                      width: `${Math.max(2, Math.round((s.costMicro / rail.dayMaxMicro) * 100))}%`,
                    }}
                  />
                ) : null}
              </div>
            </div>
          </button>
        )
      })}
    </div>
  )
}
