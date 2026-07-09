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
 * Read-only by construction — with the ONE ruled exception: this tree
 * issues GET/EventSource requests only, EXCEPT the killswitch lever
 * (Captain ruling 2026-07-09: the lever is the single in-world actuator,
 * two-tap + confirm + captain cookie, wired to the EXISTING dashboard
 * killswitch action — see killswitch-lever.tsx). CI ratchets pin: no
 * server actions declared in this tree, exactly one actuator import, no
 * HTML injection surfaces, no wall-clock/unseeded-RNG calls in the render
 * path. T3 adds: portrait rail (chrome, never the world framebuffer),
 * pixel dialog frames, and the mailbox's READ-only decision-queue view.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import type {
  CameraState,
  ChronicleRecord,
  OfficerPresence,
  WorldOfficer,
  WorldSnapshot,
} from '@/lib/world/types'
import type { ShowGrammar, Morphology, GrammarCodex, SceneName } from '@/lib/world/grammar'
import { buildLayout, CLOCKWALL, ROOM_H, ROOM_W } from '@/lib/world/layout'
import { step, type DirectorState } from '@/lib/world/director'
import type { OfficerScene } from '@/lib/world/types'
import { TILE } from '@/lib/world/layout'
import { bucketForHour, formatClock } from '@/lib/world/lighting'
import { NOTE_PIN_MAX } from '@/lib/world/set-dressing'
import { buildGrowth, type CensusKeyframe, type GrowthModel } from '@/lib/world/growth'
import { buildStreetLayout, type StreetLayout } from '@/lib/world/street-layout'
import { buildIslandLayout, type IslandLayout } from '@/lib/world/island-layout'
import InspectCard, { type InspectTarget } from './inspect-card'
import PortraitRail from './portrait-rail'
import KillswitchLever from './killswitch-lever'
import DecisionQueueCard from './decision-queue-card'

const WorldCanvas = dynamic(() => import('./world-canvas'), { ssr: false })
const OutdoorCanvas = dynamic(() => import('./outdoor-canvas'), { ssr: false })

const ZOOMS: CameraState['z'][] = [0.5, 1, 2]
/** Logical ms per director tick (frame deltas quantize into this). */
const TICK_MS = 250
/** Scene-swap fade-through-black (§10.2 snap-tween: a cut reads cleaner). */
const FADE_MS = 120

interface GrammarPayload {
  pending: boolean
  showGrammar: ShowGrammar | null
  morphology: Morphology | null
  codexCoverage: number | null
  problems: string[]
  /** Census keyframe tail [prev, latest] (growth read-model, §4). */
  keyframes?: CensusKeyframe[]
  firstCensusDate?: string | null
}

/** Camera z → scene under grammar law; absent block fail-closes to the
 * v1 behavior (the Wardroom at every zoom). */
function sceneForZ(z: CameraState['z'], grammar: GrammarPayload | null): SceneName {
  if (!grammar || grammar.pending || !grammar.showGrammar) return 'wardroom'
  return grammar.showGrammar.scenes[String(z)] ?? 'wardroom'
}

function parseUrlState(search: string): {
  camera: CameraState
  sel: string | null
  at: string | null
} {
  const p = new URLSearchParams(search)
  const zRaw = Number(p.get('z'))
  // Default landing = the Wardroom (z2): scroll out reveals street → island.
  const z = (ZOOMS as number[]).includes(zRaw) ? (zRaw as CameraState['z']) : 2
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

export default function WorldClient({
  canActuate = false,
}: {
  /** Captain session verified server-side (page.tsx) — gates the ONE
   * actuator (killswitch lever); everything else ignores it. */
  canActuate?: boolean
}) {
  const [snapshot, setSnapshot] = useState<WorldSnapshot | null>(null)
  const [mailboxOpen, setMailboxOpen] = useState(false)
  const [grammar, setGrammar] = useState<GrammarPayload | null>(null)
  const [scenes, setScenes] = useState<OfficerScene[]>([])
  const [tick, setTick] = useState(0)
  const [camera, setCamera] = useState<CameraState>({ z: 2, x: ROOM_W / 2, y: ROOM_H / 2 })
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
  // Scene selector state: displayScene lags the camera z by the fade cut.
  const [displayScene, setDisplayScene] = useState<SceneName>('wardroom')
  const [fadeActive, setFadeActive] = useState(false)

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
          // Killswitch scene (§1.5): the client STOPS advancing the
          // director — officers/motes freeze mid-stride; the red wash +
          // unsuppressible banner carry the truth (dual-coded).
          if (snap?.killswitch) continue
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

  // ── cozy ambience inputs (grammar v2 night block; §2 lighting) ───────────
  // Wall time reaches this shell ONLY as snapshot.clock (server-stamped);
  // the mapping to a day bucket is the pure lib/world/lighting.ts fn.
  const bucket = useMemo(
    () =>
      bucketForHour(
        snapshot?.clock?.hour,
        grammar?.showGrammar?.night?.buckets
      ),
    [snapshot, grammar]
  )
  // Noticeboard pins: the last N chronicle records (texture-class binding —
  // squares on canvas, headline text on the inspect card, DOM-only).
  const pinnedRecords = useMemo(
    () => [...(snapshot?.chronicle ?? [])].slice(-NOTE_PIN_MAX).reverse(),
    [snapshot]
  )
  const pins = useMemo(() => pinnedRecords.map((r) => r.iid), [pinnedRecords])
  const clockText = formatClock(snapshot?.clock)

  // ── growth read-model (REAL census keyframes via /api/world/grammar) ────
  const growth: GrowthModel = useMemo(
    () => buildGrowth(grammar?.keyframes ?? [], grammar?.firstCensusDate ?? null),
    [grammar]
  )
  const officerSlugs = useMemo(
    () => (snapshot ? snapshot.officers.map((o) => o.slug) : []),
    [snapshot]
  )
  const streetLayout: StreetLayout = useMemo(
    () => buildStreetLayout(growth, officerSlugs),
    [growth, officerSlugs]
  )
  const islandLayout: IslandLayout = useMemo(
    () => buildIslandLayout(growth, officerSlugs),
    [growth, officerSlugs]
  )
  const presenceBySlug = useMemo(() => {
    const m: Record<string, OfficerPresence> = {}
    for (const o of snapshot?.officers ?? []) m[o.slug] = o.presence
    return m
  }, [snapshot])

  // ── scene selector: camera z → scene, swapped through a 120ms cut ───────
  // Layouts are read through refs at swap time: their useMemo identity churns
  // on every snapshot, and having them as effect deps cancelled the fade
  // timers mid-cut (2026-07-08 stuck-black-overlay incident).
  const targetScene = sceneForZ(camera.z, grammar)
  const streetLayoutRef = useRef(streetLayout)
  streetLayoutRef.current = streetLayout
  const islandLayoutRef = useRef(islandLayout)
  islandLayoutRef.current = islandLayout
  useEffect(() => {
    if (targetScene === displayScene) {
      // Swap done (or no swap pending): lift the cut AFTER the fade-out leg.
      // This branch MUST own the fade-out — when the swap timer below flips
      // displayScene, this effect re-runs and its cleanup cancels any timer
      // the previous run scheduled, so a fade-out scheduled alongside the
      // swap would never fire (the 2026-07-08 permanent-black regression:
      // z=1/z=0.5 rendered a stuck opacity-100 overlay over a live canvas).
      const t = setTimeout(() => setFadeActive(false), FADE_MS)
      return () => clearTimeout(t)
    }
    setFadeActive(true)
    const t1 = setTimeout(() => {
      setDisplayScene(targetScene)
      // Center on the scene's anchor at entry (§3 camera transitions).
      const anchor =
        targetScene === 'street'
          ? streetLayoutRef.current.anchor
          : targetScene === 'island'
            ? islandLayoutRef.current.anchor
            : { x: ROOM_W / 2, y: ROOM_H / 2 }
      setCamera((c) => ({ ...c, x: anchor.x, y: anchor.y }))
    }, FADE_MS)
    return () => clearTimeout(t1)
  }, [targetScene, displayScene])

  /** Scene-local render scale: outdoor scenes keep a legible fixed zoom —
   * z is the SCENE SELECTOR, not a magnifier, outside the Wardroom. */
  const sceneScale = displayScene === 'wardroom' ? camera.z : displayScene === 'street' ? 2 : 1
  const sceneDims =
    displayScene === 'street'
      ? { w: streetLayout.w, h: streetLayout.h }
      : displayScene === 'island'
        ? { w: islandLayout.w, h: islandLayout.h }
        : { w: ROOM_W, h: ROOM_H }

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
      } else if (target.id === 'noticeboard') {
        // The cork board is a BOUND texture (wardroom_noticeboard_pins),
        // not decor: cite the morphology codex and list the pinned
        // headlines as DOM text (the canvas draws only the squares).
        const station = layout.stations.get(target.id)
        if (!station) return
        const entry = (g?.morphology?.entries ?? []).find(
          (e) => e.id === 'wardroom_noticeboard_pins'
        )
        const records = [...(snap?.chronicle ?? [])]
          .slice(-NOTE_PIN_MAX)
          .reverse()
        setInspect({
          kind: 'station',
          id: target.id,
          title: station.label,
          codex: entry?.codex ?? null,
          presence: null,
          proof: records[0] ?? null,
          headlines: records.map(
            (r) => `#${r.iid} ${r.verb} · ${r.actor}${r.kind ? ` · ${r.kind}` : ''}`
          ),
        })
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
                  'The killswitch lever — cabinet:killswitch. Red ONLY when active (reserved salience hue). THE one in-world actuator (Captain ruling 2026-07-09): two-tap + confirm + captain cookie via the LEVER control (top right), wired to the existing dashboard killswitch write. Everything else in the world stays read-only.',
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
      // Per-scene clamp box (each scene keeps its own — §3 camera law).
      x: Math.max(-4, Math.min(sceneDims.w + 4, d.camX - dx / (TILE * sceneScale))),
      y: Math.max(-4, Math.min(sceneDims.h + 4, d.camY - dy / (TILE * sceneScale))),
    }))
  }, [sceneDims.w, sceneDims.h, sceneScale])
  const onPointerUp = useCallback(() => {
    dragRef.current = null
  }, [])
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') {
        setInspect(null)
        setMailboxOpen(false)
      }
      const pan = 2 / sceneScale
      if (ev.key === 'w' || ev.key === 'ArrowUp') setCamera((c) => ({ ...c, y: c.y - pan }))
      if (ev.key === 's' || ev.key === 'ArrowDown') setCamera((c) => ({ ...c, y: c.y + pan }))
      if (ev.key === 'a' || ev.key === 'ArrowLeft') setCamera((c) => ({ ...c, x: c.x - pan }))
      if (ev.key === 'd' || ev.key === 'ArrowRight') setCamera((c) => ({ ...c, x: c.x + pan }))
      if (ev.key === '+' || ev.key === '=') setCamera((c) => ({ ...c, z: ZOOMS[Math.min(2, ZOOMS.indexOf(c.z) + 1)] }))
      if (ev.key === '-') setCamera((c) => ({ ...c, z: ZOOMS[Math.max(0, ZOOMS.indexOf(c.z) - 1)] }))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [camera.z, sceneScale])

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

  // ── outdoor scenes: inspect + door-is-a-scene-swap navigation ───────────
  const outdoorProps = displayScene === 'street' ? streetLayout.props : islandLayout.props
  /** Live growth value cited on a bound surface's card (NOW-equivalent). */
  const morphValue = useCallback(
    (id: string): string | null => {
      switch (id) {
        case 'street_hq_floors':
          return `commits_total=${growth.hqFloors.value} → ${growth.hqFloors.tier} floors`
        case 'island_land_radius':
          return `R=${growth.radius} tiles`
        case 'island_officer_houses':
          return `${growth.officerHouses} roles defined`
        case 'island_fields':
          return `${growth.fieldPlots} outcomes · crop stage ${growth.cropStage.tier}/6`
        case 'island_harbor_beacon':
          return `cells_graduated=${growth.cellsGraduated}${growth.beaconLit ? '' : ' — dark until the first graduation'}`
        case 'island_harbor_crates':
          return `${growth.dockCrates} extension packs`
        case 'island_services_mill_row':
          return `${growth.millsTotal} service rows · ${growth.millsDisabled} disabled`
        case 'street_liveliness':
          return `org age band: ${growth.streetBand}`
        default:
          return null
      }
    },
    [growth]
  )
  const openOutdoorInspect = useCallback(
    (target: { kind: 'officer' | 'station'; id: string } | null) => {
      if (!target) {
        setLegendOpen(true)
        return
      }
      if (target.kind === 'officer') {
        openInspect(target)
        return
      }
      // Mailbox → the READ-only pending decision-queue view (Captain ruling
      // 2026-07-09: render + deep-link, no actuation in-world).
      if (target.id.startsWith('island:post')) {
        setMailboxOpen(true)
        return
      }
      const pr = outdoorProps.find((p) => p.id === target.id)
      if (!pr) return
      const entry = pr.morphId
        ? grammarRef.current?.morphology?.entries.find((e) => e.id === pr.morphId) ?? null
        : null
      const value = pr.morphId ? morphValue(pr.morphId) : null
      setInspect({
        kind: 'station',
        id: pr.id,
        title: value ? `${pr.label} · ${value}` : pr.label,
        codex: entry?.codex ?? null,
        decorative: pr.decorative && !pr.morphId,
        presence: null,
        proof: null,
      })
    },
    [outdoorProps, openInspect, morphValue]
  )
  const onOutdoorPrimary = useCallback(
    (target: { kind: 'officer' | 'station'; id: string } | null) => {
      if (dragRef.current?.moved || !target) return
      if (target.kind === 'officer') {
        openInspect(target)
        return
      }
      // Primary at Z0/Z1 = NAVIGATE (law): island HQ → Z1, street door → Z2.
      const pr = outdoorProps.find((p) => p.id === target.id)
      if (pr?.navigate) {
        setCamera((c) => ({ ...c, z: pr.navigate as 1 | 2 }))
      } else {
        openOutdoorInspect(target)
      }
    },
    [outdoorProps, openInspect, openOutdoorInspect]
  )
  // Scene swap clears the previous canvas's render issues (fresh badge).
  useEffect(() => {
    setRenderIssues([])
  }, [displayScene])

  // ── screen-space label projection (§10.6 legibility) ────────────────────
  const project = useCallback(
    (wx: number, wy: number, host: { w: number; h: number }) => ({
      x: host.w / 2 + (wx * TILE - camera.x * TILE) * sceneScale,
      y: host.h / 2 + (wy * TILE - camera.y * TILE) * sceneScale,
    }),
    [camera, sceneScale]
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
      {!eraMode && displayScene === 'wardroom' && (
        <WorldCanvas
          layout={layout}
          scenes={scenes}
          camera={camera}
          killswitch={snapshot?.killswitch ?? false}
          tick={tick}
          bucket={bucket}
          pins={pins}
          onPrimary={(t) => onPrimary(t)}
          onSecondary={(t) => onSecondary(t)}
          onIssues={(issues) => setRenderIssues(issues)}
        />
      )}
      {!eraMode && displayScene !== 'wardroom' && (
        <OutdoorCanvas
          key={displayScene}
          scene={displayScene}
          street={streetLayout}
          island={islandLayout}
          officers={presenceBySlug}
          camera={camera}
          tick={tick}
          killswitch={snapshot?.killswitch ?? false}
          clockHour={snapshot?.clock?.hour ?? null}
          onPrimary={onOutdoorPrimary}
          onSecondary={openOutdoorInspect}
          onIssues={(issues) => setRenderIssues(issues)}
        />
      )}

      {/* ── scene-swap fade-through-black (snap cut, §10.2) ── */}
      <div
        className={
          'pointer-events-none absolute inset-0 z-30 bg-black transition-opacity duration-150 ' +
          (fadeActive ? 'opacity-100' : 'opacity-0')
        }
      />

      {/* ── outdoor mote labels: text as text, never world-space ── */}
      {!eraMode && displayScene !== 'wardroom' && (
        <div className="pointer-events-none absolute inset-0 z-10">
          {(displayScene === 'street' ? streetLayout.motes : islandLayout.motes).map((m) => {
            const o = officersBySlug.get(m.slug)
            const p = project(m.x, m.y - 1.2, hostSize)
            if (p.x < -100 || p.x > hostSize.w + 100 || p.y < -50 || p.y > hostSize.h + 50) return null
            return (
              <div
                key={m.slug}
                className="absolute -translate-x-1/2 text-center"
                style={{ left: p.x, top: p.y }}
              >
                <div className="text-[11px] font-semibold leading-tight text-zinc-100 [text-shadow:0_1px_2px_rgba(0,0,0,0.9)]">
                  {m.slug}
                </div>
                <div className="text-[10px] leading-tight text-zinc-300 [text-shadow:0_1px_2px_rgba(0,0,0,0.9)]">
                  {o?.presence.present && o.presence.verb ? o.presence.verb : 'inside — no live verb'}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── wall clock chip: numbers are text, text is DOM (law). Renders
            ONLY from the server-stamped snapshot clock — absent clock,
            absent chip (never a fake time). ── */}
      {!eraMode && clockText && camera.z >= 2 && (
        <div className="pointer-events-none absolute inset-0 z-10">
          {(() => {
            const p = project(CLOCKWALL.x, CLOCKWALL.y, hostSize)
            if (p.x < -100 || p.x > hostSize.w + 100 || p.y < -50 || p.y > hostSize.h + 50) return null
            return (
              <div
                data-world-clock
                className="absolute -translate-x-1/2 rounded bg-zinc-900/80 px-1 font-mono text-[10px] text-zinc-300"
                style={{ left: p.x, top: p.y }}
              >
                {clockText}
              </div>
            )
          })()}
        </div>
      )}

      {/* ── screen-space labels: text as text, never world-space ── */}
      {!eraMode && displayScene === 'wardroom' && showLabels && (
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
          Cabinet World —{' '}
          {displayScene === 'wardroom'
            ? 'Wardroom (Z2)'
            : displayScene === 'street'
              ? 'Street (Z1)'
              : 'Island (Z0)'}
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
        {grammar && grammar.pending === false && !growth.available && (
          <span
            data-world-census-badge
            className="rounded bg-amber-900/80 px-2 py-1 font-medium text-amber-200"
          >
            census unavailable — growth surfaces at day-0
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
          {/* codex-coverage gauge (T3 §5.3): entries with codex-or-decorative
              ÷ emitted entity kinds — the Legend-Law honesty meter. */}
          {typeof grammar?.codexCoverage === 'number' && (
            <div data-world-coverage-gauge className="mb-2">
              <div className="mb-0.5 flex justify-between font-mono text-[10px] text-zinc-400">
                <span>codex coverage</span>
                <span>{(grammar.codexCoverage * 100).toFixed(0)}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-sm bg-zinc-800">
                <div
                  className={
                    'h-full ' +
                    (grammar.codexCoverage >= 1 ? 'bg-emerald-500' : 'bg-amber-500')
                  }
                  style={{ width: `${Math.round(grammar.codexCoverage * 100)}%` }}
                />
              </div>
            </div>
          )}
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

      {/* ── portrait rail (T3 §9.1): chrome, never the world framebuffer ── */}
      {!eraMode && (
        <PortraitRail
          tick={tick}
          onInspect={(slug) => openInspect({ kind: 'officer', id: slug })}
        />
      )}

      {/* ── mailbox: READ-only pending decision-queue view (ruling) ── */}
      {mailboxOpen && <DecisionQueueCard onClose={() => setMailboxOpen(false)} />}

      {/* ── inspect card ── */}
      {inspect && <InspectCard target={inspect} onClose={() => { setInspect(null); setSel(null) }} />}

      {/* ── THE killswitch lever: the ONE actuator; renders above the red
            wash (break-through law) and stays truthful to the live key ── */}
      <KillswitchLever
        active={snapshot?.killswitch ?? false}
        tick={tick}
        canActuate={canActuate}
      />

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
