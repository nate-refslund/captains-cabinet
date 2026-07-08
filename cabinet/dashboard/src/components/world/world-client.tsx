'use client'

/**
 * WorldClient — the Wardroom shell (E1).
 *
 * Owns: SSE wiring, the LOGICAL clock (frame deltas → integer ticks — the
 * only place time enters; the director itself is clock-free), quantized
 * camera + URL state, the DOM label layer (ALL text is text — no
 * world-space glyphs), the three-tab inspect card, the killswitch
 * break-through, the grammar-pending banner, the chronicle ticker, and the
 * Legend Law panel.
 *
 * Read-only by construction: this tree issues GET/EventSource requests
 * only. CI ratchets pin: no server actions, no HTML injection surfaces, no
 * wall-clock/unseeded-RNG calls in the render path.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import type {
  CameraState,
  ChronicleRecord,
  WorldOfficer,
  WorldSnapshot,
} from '@/lib/world/types'
import type { ShowGrammar, Morphology, GrammarCodex } from '@/lib/world/grammar'
import { buildLayout, CLOCKWALL, ROOM_H, ROOM_W } from '@/lib/world/layout'
import { step, type DirectorState } from '@/lib/world/director'
import type { OfficerScene } from '@/lib/world/types'
import { TILE } from '@/lib/world/layout'
import InspectCard, { type InspectTarget } from './inspect-card'

const WorldCanvas = dynamic(() => import('./world-canvas'), { ssr: false })

const ZOOMS: CameraState['z'][] = [0.5, 1, 2]
/** Logical ms per director tick (frame deltas quantize into this). */
const TICK_MS = 250

interface GrammarPayload {
  pending: boolean
  showGrammar: ShowGrammar | null
  morphology: Morphology | null
  codexCoverage: number | null
  problems: string[]
}

function parseUrlState(search: string): {
  camera: CameraState
  sel: string | null
  at: string | null
} {
  const p = new URLSearchParams(search)
  const zRaw = Number(p.get('z'))
  const z = (ZOOMS as number[]).includes(zRaw) ? (zRaw as CameraState['z']) : 1
  const x = Number.isFinite(Number(p.get('x'))) && p.get('x') !== null
    ? Number(p.get('x'))
    : ROOM_W / 2
  const y = Number.isFinite(Number(p.get('y'))) && p.get('y') !== null
    ? Number(p.get('y'))
    : ROOM_H / 2
  // sel is an OPAQUE server-issued handle — never a slug (S1-F4).
  const sel = p.get('sel')
  const at = p.get('at')
  return { camera: { z, x, y }, sel, at }
}

export default function WorldClient() {
  const [snapshot, setSnapshot] = useState<WorldSnapshot | null>(null)
  const [grammar, setGrammar] = useState<GrammarPayload | null>(null)
  const [scenes, setScenes] = useState<OfficerScene[]>([])
  const [tick, setTick] = useState(0)
  const [camera, setCamera] = useState<CameraState>({ z: 1, x: ROOM_W / 2, y: ROOM_H / 2 })
  const [sel, setSel] = useState<string | null>(null)
  const [at, setAt] = useState<string | null>(null)
  const [inspect, setInspect] = useState<InspectTarget | null>(null)
  const [legendOpen, setLegendOpen] = useState(false)
  const [connected, setConnected] = useState(false)
  // Loud-failure surface (2026-07-08 black-canvas incident): renderer boot
  // errors and manifest/texture gaps badge HERE, in DOM — silent-black is a
  // ratcheted regression class (world/ratchets.test.ts #9).
  const [renderIssues, setRenderIssues] = useState<string[]>([])

  const directorState = useRef<DirectorState>({})
  const tickRef = useRef(0)
  const accRef = useRef(0)
  const snapshotRef = useRef<WorldSnapshot | null>(null)
  const grammarRef = useRef<GrammarPayload | null>(null)
  const dragRef = useRef<{ x: number; y: number; moved: boolean; camX: number; camY: number } | null>(null)
  const wheelAcc = useRef(0)
  const eraMode = at !== null

  // ── URL state (read once; write on change) ──────────────────────────────
  useEffect(() => {
    const s = parseUrlState(window.location.search)
    setCamera(s.camera)
    setSel(s.sel)
    setAt(s.at)
  }, [])
  useEffect(() => {
    const p = new URLSearchParams()
    p.set('z', String(camera.z))
    p.set('x', camera.x.toFixed(1))
    p.set('y', camera.y.toFixed(1))
    if (sel) p.set('sel', sel)
    if (at) p.set('at', at)
    const url = `${window.location.pathname}?${p.toString()}`
    window.history.replaceState(null, '', url)
  }, [camera, sel, at])

  // ── data feeds ───────────────────────────────────────────────────────────
  useEffect(() => {
    fetch('/api/world/grammar')
      .then((r) => (r.ok ? r.json() : null))
      .then((g: GrammarPayload | null) => {
        setGrammar(g)
        grammarRef.current = g
      })
      .catch(() => setGrammar(null))
  }, [])

  useEffect(() => {
    const es = new EventSource('/api/world/stream')
    const onSnap = (ev: MessageEvent) => {
      try {
        const snap = JSON.parse(ev.data) as WorldSnapshot
        setSnapshot(snap)
        snapshotRef.current = snap
        setConnected(true)
      } catch {
        /* ignore malformed frame */
      }
    }
    es.addEventListener('world:snapshot', onSnap)
    es.addEventListener('world:updated', onSnap)
    es.onerror = () => setConnected(false)
    return () => es.close()
  }, [])

  // ── the logical clock (frame deltas → integer ticks) ────────────────────
  useEffect(() => {
    let raf = 0
    let last: number | null = null
    const loop = (now: number) => {
      if (last !== null) {
        accRef.current += now - last
        while (accRef.current >= TICK_MS) {
          accRef.current -= TICK_MS
          tickRef.current += 1
          const snap = snapshotRef.current
          const g = grammarRef.current
          if (snap && !eraModeRef.current) {
            const officers: Record<string, WorldOfficer['presence']> = {}
            for (const o of snap.officers) officers[o.slug] = o.presence
            const layout = buildLayout(Object.keys(officers))
            const out = step(directorState.current, {
              officers,
              grammar: g && !g.pending ? g.showGrammar : null,
              layout,
              tick: tickRef.current,
              // Wall time + killswitch enter as snapshot DATA only — the
              // render path never reads a clock (determinism ratchet).
              clockHour: snap.clock?.hour ?? null,
              killswitch: snap.killswitch,
            })
            directorState.current = out.state
            setScenes(out.scenes)
            setTick(tickRef.current)
          }
        }
      }
      last = now
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [])
  const eraModeRef = useRef(eraMode)
  eraModeRef.current = eraMode

  const layout = useMemo(
    () => buildLayout(snapshot ? snapshot.officers.map((o) => o.slug) : []),
    [snapshot]
  )

  const officersBySel = useMemo(() => {
    const m = new Map<string, WorldOfficer>()
    for (const o of snapshot?.officers ?? []) m.set(o.sel, o)
    return m
  }, [snapshot])
  const officersBySlug = useMemo(() => {
    const m = new Map<string, WorldOfficer>()
    for (const o of snapshot?.officers ?? []) m.set(o.slug, o)
    return m
  }, [snapshot])

  // ── inspect assembly (officer / station / record) ────────────────────────
  const openInspect = useCallback(
    (target: { kind: 'officer' | 'station'; id: string } | null) => {
      if (!target) {
        setInspect(null)
        setSel(null)
        return
      }
      const snap = snapshotRef.current
      const g = grammarRef.current
      if (target.kind === 'officer') {
        const o = officersBySlug.get(target.id)
        if (!o) return
        const verb = o.presence.verb
        const codex: GrammarCodex | null =
          (verb && g?.showGrammar?.verbs[verb]?.codex) || null
        const proof =
          [...(snap?.chronicle ?? [])]
            .reverse()
            .find((r) => r.actor === target.id) ?? null
        setInspect({
          kind: 'officer',
          id: o.sel, // opaque handle is the card's id — slug only in title (T2)
          title: `${o.slug} — officer`,
          codex,
          presence: o.presence,
          proof,
        })
        setSel(o.sel)
      } else {
        const station = layout.stations.get(target.id)
        if (!station) return
        const isDesk = target.id.startsWith('desk:')
        const isLever = target.id === 'lever'
        setInspect({
          kind: 'station',
          id: target.id,
          title: station.label,
          codex: isLever
            ? {
                represents:
                  'The killswitch lever — cabinet:killswitch. Red ONLY when active (reserved salience hue). Pull/reset stays in Telegram/CLI where auth lives; the world never grows a write path.',
                mechanism_path: 'cabinet/scripts/kill-switch.sh',
                day0: 'lever present, inactive',
              }
            : null,
          decorative: !isDesk && !isLever,
          presence: isDesk
            ? officersBySlug.get(target.id.slice('desk:'.length))?.presence ?? null
            : null,
          proof: isDesk
            ? [...(snapshotRef.current?.chronicle ?? [])]
                .reverse()
                .find((r) => r.actor === target.id.slice('desk:'.length)) ?? null
            : null,
        })
      }
    },
    [layout, officersBySlug]
  )

  // Deep-link: ?sel=<handle> restores the inspect card post-connect.
  useEffect(() => {
    if (!sel || inspect || !snapshot) return
    const o = officersBySel.get(sel)
    if (o) openInspect({ kind: 'officer', id: o.slug })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel, snapshot])

  // ── camera controls ──────────────────────────────────────────────────────
  const onWheel = useCallback((ev: React.WheelEvent) => {
    wheelAcc.current += ev.deltaY
    if (Math.abs(wheelAcc.current) > 60) {
      const dir = wheelAcc.current > 0 ? -1 : 1
      wheelAcc.current = 0
      setCamera((c) => {
        const i = ZOOMS.indexOf(c.z)
        const nz = ZOOMS[Math.min(ZOOMS.length - 1, Math.max(0, i + dir))]
        return { ...c, z: nz }
      })
    }
  }, [])
  const onPointerDown = useCallback((ev: React.PointerEvent) => {
    dragRef.current = {
      x: ev.clientX,
      y: ev.clientY,
      moved: false,
      camX: camera.x,
      camY: camera.y,
    }
  }, [camera])
  const onPointerMove = useCallback((ev: React.PointerEvent) => {
    const d = dragRef.current
    if (!d) return
    const dx = ev.clientX - d.x
    const dy = ev.clientY - d.y
    // Drag threshold ≥5px = pan, never click (UI-F2).
    if (!d.moved && Math.hypot(dx, dy) < 5) return
    d.moved = true
    setCamera((c) => ({
      ...c,
      x: Math.max(-4, Math.min(ROOM_W + 4, d.camX - dx / (TILE * c.z))),
      y: Math.max(-4, Math.min(ROOM_H + 4, d.camY - dy / (TILE * c.z))),
    }))
  }, [])
  const onPointerUp = useCallback(() => {
    dragRef.current = null
  }, [])
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') setInspect(null)
      const pan = 2 / camera.z
      if (ev.key === 'w' || ev.key === 'ArrowUp') setCamera((c) => ({ ...c, y: c.y - pan }))
      if (ev.key === 's' || ev.key === 'ArrowDown') setCamera((c) => ({ ...c, y: c.y + pan }))
      if (ev.key === 'a' || ev.key === 'ArrowLeft') setCamera((c) => ({ ...c, x: c.x - pan }))
      if (ev.key === 'd' || ev.key === 'ArrowRight') setCamera((c) => ({ ...c, x: c.x + pan }))
      if (ev.key === '+' || ev.key === '=') setCamera((c) => ({ ...c, z: ZOOMS[Math.min(2, ZOOMS.indexOf(c.z) + 1)] }))
      if (ev.key === '-') setCamera((c) => ({ ...c, z: ZOOMS[Math.max(0, ZOOMS.indexOf(c.z) - 1)] }))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [camera.z])

  const onPrimary = useCallback(
    (target: { kind: 'officer' | 'station'; id: string } | null) => {
      if (dragRef.current?.moved) return
      if (camera.z >= 2) {
        openInspect(target)
      } else if (target) {
        // Z0/Z1 primary click = navigation: zoom toward the target.
        const pos =
          target.kind === 'officer'
            ? scenes.find((s) => s.slug === target.id)
            : layout.stations.get(target.id)
        if (pos) {
          setCamera((c) => ({
            z: ZOOMS[Math.min(2, ZOOMS.indexOf(c.z) + 1)],
            x: pos.x,
            y: pos.y,
          }))
        }
      }
    },
    [camera.z, layout, openInspect, scenes]
  )
  const onSecondary = useCallback(
    (target: { kind: 'officer' | 'station'; id: string } | null) => {
      // Secondary gesture = universal inspect / Legend-Law cite path.
      if (target) openInspect(target)
      else setLegendOpen(true)
    },
    [openInspect]
  )

  // ── screen-space label projection (§10.6 legibility) ────────────────────
  const project = useCallback(
    (wx: number, wy: number, host: { w: number; h: number }) => ({
      x: host.w / 2 + (wx * TILE - camera.x * TILE) * camera.z,
      y: host.h / 2 + (wy * TILE - camera.y * TILE) * camera.z,
    }),
    [camera]
  )
  const hostRef = useRef<HTMLDivElement | null>(null)
  const [hostSize, setHostSize] = useState({ w: 1024, h: 640 })
  useEffect(() => {
    const el = hostRef.current
    if (!el) return
    const ro = new ResizeObserver(() =>
      setHostSize({ w: el.clientWidth, h: el.clientHeight })
    )
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const ticker = useMemo(
    () => [...(snapshot?.chronicle ?? [])].slice(-8).reverse(),
    [snapshot]
  )

  // ── behavior chips (grammar v2): DOM glyphs, never world-space text ──────
  // 'z' above sleepers, one shared '…' per chat pair, one verb chip per
  // table meeting. All derived from director scenes — no content invented.
  const behaviorChips = useMemo(() => {
    const chips: Array<{ key: string; x: number; y: number; text: string; kind: 'zzz' | 'talk' | 'meet' }> = []
    for (const s of scenes) {
      if (s.chip === 'zzz') {
        chips.push({ key: `z:${s.slug}`, x: s.x, y: s.y - 2.6, text: 'z', kind: 'zzz' })
      }
    }
    // Chat pairs: pair (0,1),(2,3)… in sorted-slug order per waypoint —
    // mirrors the director's pairing walk exactly.
    const byWp = new Map<string, OfficerScene[]>()
    for (const s of scenes) {
      if (s.chip !== 'ellipsis') continue
      const wp = s.stationId.replace(/^wander:/, '').replace(/:\d+$/, '')
      const list = byWp.get(wp) ?? []
      list.push(s)
      byWp.set(wp, list)
    }
    for (const [wp, group] of byWp) {
      group.sort((a, b) => (a.slug < b.slug ? -1 : 1))
      for (let i = 0; i + 1 < group.length; i += 2) {
        const a = group[i]
        const b = group[i + 1]
        chips.push({
          key: `t:${wp}:${a.slug}`,
          x: (a.x + b.x) / 2,
          y: Math.min(a.y, b.y) - 2.6,
          text: '…',
          kind: 'talk',
        })
      }
    }
    // Table meetings: one shared chip listing the verb (§1.3).
    const seats = new Map<string, OfficerScene[]>()
    for (const s of scenes) {
      if (!s.stationId.startsWith('seat:') || s.anim === 'walk') continue
      const base = s.stationId.split(':').slice(0, 2).join(':')
      const list = seats.get(base) ?? []
      list.push(s)
      seats.set(base, list)
    }
    for (const [base, group] of seats) {
      if (group.length < 2) continue
      const cx = group.reduce((acc, s) => acc + s.x, 0) / group.length
      const cy = group.reduce((acc, s) => acc + s.y, 0) / group.length
      chips.push({
        key: `m:${base}`,
        x: cx,
        y: cy - 3.2,
        text: group[0].verb ?? 'meeting',
        kind: 'meet',
      })
    }
    return chips
  }, [scenes])

  const showLabels = camera.z >= 2 || (snapshot?.officers.length ?? 0) <= 8

  return (
    <div
      ref={hostRef}
      className="relative h-[calc(100vh-3rem)] w-full select-none overflow-hidden bg-zinc-950 text-zinc-100"
      onWheel={onWheel}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
    >
      {!eraMode && (
        <WorldCanvas
          layout={layout}
          scenes={scenes}
          camera={camera}
          killswitch={snapshot?.killswitch ?? false}
          tick={tick}
          onPrimary={(t) => onPrimary(t)}
          onSecondary={(t) => onSecondary(t)}
          onIssues={(issues) => setRenderIssues(issues)}
        />
      )}

      {/* ── screen-space labels: text as text, never world-space ── */}
      {!eraMode && showLabels && (
        <div className="pointer-events-none absolute inset-0 z-10">
          {scenes.map((s) => {
            const o = officersBySlug.get(s.slug)
            const p = project(s.x, s.y - 2.2, hostSize)
            if (p.x < -100 || p.x > hostSize.w + 100 || p.y < -50 || p.y > hostSize.h + 50) return null
            return (
              <div
                key={s.slug}
                className="absolute -translate-x-1/2 text-center"
                style={{ left: p.x, top: p.y }}
              >
                <div className="text-[12px] font-semibold leading-tight text-zinc-100 [text-shadow:0_1px_2px_rgba(0,0,0,0.9)]">
                  {s.slug}
                </div>
                <div className="text-[11px] leading-tight text-zinc-300 [text-shadow:0_1px_2px_rgba(0,0,0,0.9)]">
                  {s.verb
                    ? o?.presence.object
                      ? `${s.verb} · ${o.presence.object.slice(0, 40)}`
                      : s.verb
                    : 'idle'}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── behavior chips + wall clock: DOM text, never canvas glyphs ── */}
      {!eraMode && (
        <div className="pointer-events-none absolute inset-0 z-10">
          {behaviorChips.map((c) => {
            const p = project(c.x, c.y, hostSize)
            if (p.x < -100 || p.x > hostSize.w + 100 || p.y < -50 || p.y > hostSize.h + 50) return null
            return (
              <div
                key={c.key}
                data-world-chip={c.kind}
                className={
                  'absolute -translate-x-1/2 rounded bg-zinc-900/80 px-1 leading-tight ' +
                  (c.kind === 'zzz'
                    ? 'text-[10px] italic text-zinc-400'
                    : c.kind === 'talk'
                      ? 'text-[12px] text-zinc-200'
                      : 'text-[10px] font-medium text-zinc-200')
                }
                style={{ left: p.x, top: p.y }}
              >
                {c.text}
              </div>
            )
          })}
          {snapshot?.clock && camera.z >= 2 && (() => {
            const p = project(CLOCKWALL.x, CLOCKWALL.y, hostSize)
            if (p.x < -100 || p.x > hostSize.w + 100 || p.y < -50 || p.y > hostSize.h + 50) return null
            const hh = String(snapshot.clock.hour).padStart(2, '0')
            const mm = String(snapshot.clock.minute).padStart(2, '0')
            return (
              <div
                data-world-clock
                className="absolute -translate-x-1/2 rounded bg-zinc-900/80 px-1 font-mono text-[10px] text-zinc-300"
                style={{ left: p.x, top: p.y }}
              >
                {hh}:{mm}
              </div>
            )
          })()}
        </div>
      )}

      {/* ── top HUD ── */}
      <div className="pointer-events-none absolute left-0 right-0 top-0 z-20 flex items-center gap-2 px-3 py-2 text-xs">
        <span className="rounded bg-zinc-900/80 px-2 py-1 font-semibold">
          Cabinet World — Wardroom (E1)
        </span>
        <span className="rounded bg-zinc-900/80 px-2 py-1 text-zinc-400">
          z{camera.z} · iid {snapshot?.iidHigh ?? 0} ·{' '}
          {connected ? 'live' : 'reconnecting…'}
        </span>
        {grammar?.pending !== false && (
          <span className="rounded bg-amber-900/80 px-2 py-1 font-medium text-amber-200">
            grammar pending Captain merge — presence markers only (founding
            act: merge the morphology/show-grammar v1 PR)
          </span>
        )}
        {typeof grammar?.codexCoverage === 'number' && (
          <span className="rounded bg-zinc-900/80 px-2 py-1 text-zinc-400">
            codex coverage {(grammar.codexCoverage * 100).toFixed(0)}%
          </span>
        )}
        {renderIssues.length > 0 && (
          <span
            data-world-issues
            title={renderIssues.slice(0, 10).join('\n')}
            className="rounded bg-red-900/85 px-2 py-1 font-semibold text-red-200"
          >
            render: {renderIssues.length} issue{renderIssues.length === 1 ? '' : 's'} — see console
          </span>
        )}
        <button
          onClick={() => setLegendOpen((v) => !v)}
          className="pointer-events-auto ml-auto rounded bg-zinc-800/90 px-2 py-1 font-medium text-zinc-200 hover:bg-zinc-700"
        >
          legend
        </button>
      </div>

      {/* ── era replay chip (?at= preserved; honest S1-F5 stance) ── */}
      {eraMode && (
        <div className="absolute inset-0 z-10 flex items-center justify-center">
          <div className="max-w-md rounded-lg border border-zinc-700 bg-zinc-900 p-6 text-center text-sm">
            <div className="mb-2 font-semibold">era view @ {at}</div>
            <p className="text-zinc-400">
              Live presence renders dark under an era pin (replay: none — a
              TTL key cannot honestly replay). Full keyframe + roll-forward
              replay lands in E2; the URL state already composes.
            </p>
            <button
              className="mt-4 rounded bg-zinc-800 px-3 py-1 text-xs hover:bg-zinc-700"
              onClick={() => setAt(null)}
            >
              back to live
            </button>
          </div>
        </div>
      )}

      {/* ── chronicle ticker (citations-only; click = PROOF) ── */}
      <div className="absolute bottom-0 left-0 right-0 z-20 flex gap-2 overflow-x-auto border-t border-zinc-800 bg-zinc-950/90 px-2 py-1 text-[11px]">
        {ticker.length === 0 ? (
          <span className="text-zinc-600">chronicle quiet…</span>
        ) : (
          ticker.map((r) => (
            <button
              key={r.iid}
              onClick={() =>
                setInspect({
                  kind: 'record',
                  id: String(r.iid),
                  title: `${r.verb} — chronicle #${r.iid}`,
                  codex: null,
                  proof: r,
                  presence: null,
                })
              }
              className="whitespace-nowrap rounded px-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            >
              {r.verb} · {r.actor}
            </button>
          ))
        )}
      </div>

      {/* ── Legend Law panel ── */}
      {legendOpen && (
        <div className="absolute left-4 top-16 z-30 max-h-[70vh] w-96 max-w-[92vw] overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900/95 p-3 text-xs shadow-2xl">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-semibold">Legend (auto-generated from grammar law)</span>
            <button
              onClick={() => setLegendOpen(false)}
              className="rounded px-2 text-zinc-400 hover:bg-zinc-800"
            >
              close
            </button>
          </div>
          {grammar?.pending !== false ? (
            <p className="text-amber-300">
              Grammar law not yet merged — no mappings to cite. The legend
              populates from cabinet/world/show-grammar.yml +
              morphology.yml the moment the Captain merges the v1 PR.
            </p>
          ) : (
            <div className="space-y-2">
              {Object.entries(grammar?.showGrammar?.verbs ?? {}).map(([verb, m]) => (
                <div key={verb} className="rounded bg-zinc-950 p-2">
                  <div className="font-mono text-zinc-200">
                    {verb} → {m.station} ({m.anim})
                  </div>
                  {m.codex ? (
                    <div className="text-zinc-400">{m.codex.represents}</div>
                  ) : (
                    <div className="text-amber-300">codex pending</div>
                  )}
                </div>
              ))}
              {(grammar?.morphology?.entries ?? []).map((e) => (
                <div key={e.id} className="rounded bg-zinc-950 p-2">
                  <div className="font-mono text-zinc-200">{e.id}</div>
                  <div className="break-all font-mono text-[10px] text-zinc-500">
                    {e.source_binding}
                  </div>
                  <div className="text-zinc-400">
                    scope {e.scope} · tier {e.tier} · replay {e.replay}
                  </div>
                </div>
              ))}
            </div>
          )}
          <p className="mt-3 text-[10px] text-zinc-500">
            Secondary gesture (right-click / long-press) inspects any object
            at any zoom — every pixel cites its mechanism (Legend Law).
          </p>
        </div>
      )}

      {/* ── inspect card ── */}
      {inspect && <InspectCard target={inspect} onClose={() => { setInspect(null); setSel(null) }} />}

      {/* ── killswitch break-through: unsuppressible, above everything ── */}
      {snapshot?.killswitch && (
        <div className="absolute inset-0 z-50 flex items-start justify-center bg-red-950/60">
          <div className="mt-20 rounded-lg border-2 border-red-500 bg-red-900 px-6 py-4 text-center">
            <div className="text-lg font-bold text-red-100">KILLSWITCH ACTIVE</div>
            <div className="text-sm text-red-200">
              fleet halted — reset is a Captain act (Telegram/CLI; the world
              renders, never acts)
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
