'use client'

/**
 * EngineClient — THE world shell (T1; replaced the three-scene wardroom /
 * street / island shell per spec v2 supersession #5: LOD zoom + pan only,
 * never a scene swap). That shell was deleted 2026-07-29 after the bake-off,
 * so this is now the only one.
 *
 * Owns: SSE wiring, the LOGICAL clock (frame deltas → integer ticks), the
 * continuous camera (+ URL state), the era×rung engine feed (hot-reloaded
 * growth-ladders via /api/world/engine), the weather machine, the cutaway
 * machine, DOM labels (text is text — never world-space glyphs), inspect
 * cards, the mailbox read-only view, the portrait rail, THE killswitch
 * lever, and the killswitch break-through banner.
 *
 * Read-only by construction with the ONE ruled exception (the lever).
 * Determinism: the render path never reads a clock — wall time enters as
 * snapshot data; weather/era evals arrive as server data; everything else
 * is fnv1a-seeded off stable ids + the logical tick.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import type {
  ChronicleRecord,
  OfficerPresence,
  WorldOfficer,
  WorldSnapshot,
} from '@/lib/world/types'
import type { GrammarCodex, Morphology, ShowGrammar } from '@/lib/world/grammar'
import {
  DEFAULT_PROJECTION,
  projectionFor,
  screenDeltaToTiles,
  worldToScreen,
  worldUrlSearch,
  type ProjectionKind,
} from '@/lib/world/projection'
import { cameraClamp, cameraHome } from '@/lib/world/iso-scene'
import { creditReason, limezuSurfaces } from '@/lib/world/credit'
import { ASSET_BASE, type WorldAssetManifest } from '@/lib/world/sprites'
import { fnv1a } from '@/lib/world/hash'
import { formatClock } from '@/lib/world/lighting'
import {
  engineStep,
  initialEngineState,
  type EngineEval,
  type EngineState,
  type GrowthLaddersConfig,
  type WorldResolution,
} from '@/lib/world/era-engine'
import { buildWorldGeo, type WorldGeo } from '@/lib/world/world-geo'
import {
  buildOutdoorDressing,
  type OutdoorDressing,
} from '@/lib/world/outdoor-dressing'
import { buildWorldBuildings, type WorldBuilding } from '@/lib/world/world-buildings'
import {
  clampZoom,
  cutawayCandidate,
  cutawayStep,
  initialCutaway,
  lodTier,
  type CutawayState,
  type EngineCamera,
} from '@/lib/world/lod'
import {
  initialWeather,
  weatherStep,
  weatherTarget,
  type WeatherSignals,
  type WeatherState,
} from '@/lib/world/weather'
import {
  initialLifeState,
  lifeStep,
  type LifeOut,
  type LifeState,
} from '@/lib/world/life/life'
import type { LifeGrammar } from '@/lib/world/life/life-grammar'
import type { WorkSite } from '@/lib/world/life/sites'
import type { DirectionsDoc, PortCallsArtifact } from '@/lib/world/directions'
import {
  buildChartTableCard,
  voyageRender,
  type LaneCourse,
} from '@/lib/world/course'
import { layoutLabels } from '@/lib/world/labels'
import { STAGED_VOCAB_ELEMENTS } from '@/lib/world/sprites-outdoor'
import InspectCard, { type InspectTarget } from './inspect-card'
import PortraitRail from './portrait-rail'
import KillswitchLever from './killswitch-lever'
import DecisionQueueCard from './decision-queue-card'
import LibraryCard from './library-card'
import type { EngineTarget } from './engine-canvas'
import { officerSlots } from '@/lib/world/pick'

const EngineCanvas = dynamic(() => import('./engine-canvas'), { ssr: false })

/** Logical ms per tick (frame deltas quantize into this). */
const TICK_MS = 250
/** Engine feed refresh (hot-reload door + weather evals) — server data. */
const ENGINE_POLL_MS = 60_000

interface GrammarPayload {
  pending: boolean
  showGrammar: ShowGrammar | null
  morphology: Morphology | null
  codexCoverage: number | null
  problems: string[]
}

interface EnginePayload {
  ladders: { config: GrowthLaddersConfig | null; problems: string[]; mtimeMs: number | null }
  evalPrev: EngineEval | null
  eval: EngineEval | null
  weather: WeatherSignals
  orgEventsTotal: number
  /** Isle berth bindings (instance world-state, server-folded — Wave G).
   * Absent/empty ⇒ slots render mist (honest absence, no invented names). */
  berths?: (string | null)[]
  /** Lanes with a probes.yml row (isle why-string provenance). */
  probeWiredLanes?: string[]
  /** T2 LIFE feed (grammar-gated fail-closed; absent → behaviors OFF). */
  life?: {
    grammar: LifeGrammar
    siteEntries: WorkSite[]
    productLanes: string[]
  }
  /** Direction surface (grammar v4 — Captain ratifications 2026-07-17):
   * apex + lane directions, port-call artifact, per-lane course states.
   * All fail-honest server folds; absent ⇒ uncharted card / moored boat. */
  directions?: DirectionsDoc | null
  portCalls?: PortCallsArtifact | null
  courses?: Record<string, LaneCourse>
  /** Server-stamped YYYY-MM-DD (the engine route's sanctioned clock door). */
  todayISO?: string
}

function parseUrlState(
  search: string,
  projection: ProjectionKind
): { camera: EngineCamera; sel: string | null; at: string | null } {
  const p = new URLSearchParams(search)
  const zRaw = Number(p.get('z'))
  const z = Number.isFinite(zRaw) && zRaw > 0 ? clampZoom(zRaw) : 1
  // Default landing: the whole island in frame. The two kernels frame
  // DIFFERENT worlds — the iso world is the compositor's canvas, not the tile
  // canvas — so the home position comes from the kernel rather than a literal.
  const home = cameraHome(projection)
  const x = p.get('x') !== null && Number.isFinite(Number(p.get('x'))) ? Number(p.get('x')) : home.x
  const y = p.get('y') !== null && Number.isFinite(Number(p.get('y'))) ? Number(p.get('y')) : home.y
  return { camera: { z, x, y }, sel: p.get('sel'), at: p.get('at') }
}

export default function EngineClient({
  canActuate = false,
  // NOT a literal: a second copy of the default kernel is a second thing to
  // remember on flip day, and the one that gets forgotten.
  projection = DEFAULT_PROJECTION,
}: {
  canActuate?: boolean
  /** Which world→screen kernel to render with — read server-side from ?iso. */
  projection?: ProjectionKind
}) {
  const [snapshot, setSnapshot] = useState<WorldSnapshot | null>(null)
  const [grammar, setGrammar] = useState<GrammarPayload | null>(null)
  const [engine, setEngine] = useState<EnginePayload | null>(null)
  const [resolution, setResolution] = useState<WorldResolution | null>(null)
  const [weather, setWeather] = useState<WeatherState>(initialWeather())
  const [tick, setTick] = useState(0)
  const [camera, setCamera] = useState<EngineCamera>({ z: 1, ...cameraHome(projection) })
  const [cutaway, setCutaway] = useState<CutawayState>(initialCutaway())
  const [sel, setSel] = useState<string | null>(null)
  const [at, setAt] = useState<string | null>(null)
  const [inspect, setInspect] = useState<InspectTarget | null>(null)
  const [mailboxOpen, setMailboxOpen] = useState(false)
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [legendOpen, setLegendOpen] = useState(false)
  const [connected, setConnected] = useState(false)
  const [renderIssues, setRenderIssues] = useState<string[]>([])
  // ART CREDIT INPUTS — the credit line names LimeZu only where LimeZu pixels
  // are on screen, so both facts are measured: the manifest says which rows are
  // licensed, and the rail reports how many of its portraits it is painting.
  const [artManifest, setArtManifest] = useState<WorldAssetManifest | null>(null)
  const [railLimeZu, setRailLimeZu] = useState(0)

  const tickRef = useRef(0)
  const accRef = useRef(0)
  const snapshotRef = useRef<WorldSnapshot | null>(null)
  const grammarRef = useRef<GrammarPayload | null>(null)
  const engineStateRef = useRef<EngineState>(initialEngineState())
  const weatherRef = useRef<WeatherState>(initialWeather())
  const cutawayRef = useRef<CutawayState>(initialCutaway())
  const lifeStateRef = useRef<LifeState>(initialLifeState())
  const lifeFeedRef = useRef<EnginePayload['life'] | null>(null)
  const lifeOutRef = useRef<LifeOut | null>(null)
  const [lifeOut, setLifeOut] = useState<LifeOut | null>(null)
  const cameraRef = useRef(camera)
  cameraRef.current = camera
  const buildingsRef = useRef<WorldBuilding[]>([])
  const dressingRef = useRef<OutdoorDressing | null>(null)
  const dragRef = useRef<{ x: number; y: number; moved: boolean; camX: number; camY: number } | null>(null)
  const hostRef = useRef<HTMLDivElement | null>(null)
  const [hostSize, setHostSize] = useState({ w: 1024, h: 640 })
  const eraMode = at !== null

  // ── URL state ────────────────────────────────────────────────────────────
  useEffect(() => {
    const s = parseUrlState(window.location.search, projection)
    setCamera(s.camera)
    setSel(s.sel)
    setAt(s.at)
  }, [projection])
  useEffect(() => {
    // The kernel flag SURVIVES the rewrite, in BOTH directions — see
    // `worldUrlSearch`, which owns the reason. Without this the first pan drops
    // the flag from the address bar and the page the Captain reloads or shares
    // is whichever renderer happens to be the default that week.
    const qs = worldUrlSearch({ camera, sel, at, projection })
    window.history.replaceState(null, '', `${window.location.pathname}?${qs}`)
  }, [camera, sel, at, projection])

  // The manifest, for its `license` column only — the canvas resolves its own
  // copy for drawing. Same URL, so this is a browser-cache hit, not a second
  // download.
  useEffect(() => {
    let alive = true
    fetch(ASSET_BASE + 'manifest.json')
      .then((r) => (r.ok ? (r.json() as Promise<WorldAssetManifest>) : null))
      .then((m) => {
        if (alive) setArtManifest(m)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])
  /** Mounted surfaces currently painting LimeZu-licensed pixels. */
  const creditSurfaces = useMemo(
    () =>
      limezuSurfaces({
        projection,
        manifest: artManifest,
        limezuPortraits: railLimeZu,
      }),
    [projection, artManifest, railLimeZu]
  )

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

  // Engine feed: growth-ladders (hot-reload on the server by mtime), era
  // eval inputs, weather signals. Polled — a Captain VALUE edit to
  // growth-ladders.yml reaches the render within one poll.
  useEffect(() => {
    let stop = false
    let lastMtime: number | null = null
    const pull = async () => {
      try {
        const r = await fetch('/api/world/engine')
        if (!r.ok) return
        const e = (await r.json()) as EnginePayload
        if (stop) return
        setEngine(e)
        lifeFeedRef.current = e.life ?? null
        if (e.ladders.config && e.eval) {
          // Config changed (hot-reload) → fresh engine state: hysteresis
          // holders re-seed from the eval pair (prev then latest), exactly
          // the honest two-keyframe view the backtest replays.
          if (e.ladders.mtimeMs !== lastMtime) {
            lastMtime = e.ladders.mtimeMs
            engineStateRef.current = initialEngineState()
            if (e.evalPrev) {
              engineStateRef.current = engineStep(
                engineStateRef.current,
                e.evalPrev,
                e.ladders.config
              ).state
            }
          }
          const step = engineStep(engineStateRef.current, e.eval, e.ladders.config)
          engineStateRef.current = step.state
          setResolution(step.out)
        } else {
          setResolution(null)
        }
        // weather machine: one eval per pull (hysteresis in weatherStep;
        // the killswitch ALSO storms instantly via the SSE snapshot below).
        weatherRef.current = weatherStep(weatherRef.current, weatherTarget(e.weather))
        setWeather(weatherRef.current)
      } catch {
        /* transient — badges stay quiet; next poll retries */
      }
    }
    pull()
    const t = setInterval(pull, ENGINE_POLL_MS)
    return () => {
      stop = true
      clearInterval(t)
    }
  }, [])

  useEffect(() => {
    const es = new EventSource('/api/world/stream')
    const onSnap = (ev: MessageEvent) => {
      try {
        const snap = JSON.parse(ev.data) as WorldSnapshot
        setSnapshot(snap)
        snapshotRef.current = snap
        setConnected(true)
        // killswitch → storm immediately (never waits for the next poll)
        if (snap.killswitch && weatherRef.current.kind !== 'storm') {
          weatherRef.current = weatherStep(weatherRef.current, {
            kind: 'storm',
            why: 'cabinet:killswitch active — the storm is the red wash',
          })
          setWeather(weatherRef.current)
        }
      } catch {
        /* ignore malformed frame */
      }
    }
    es.addEventListener('world:snapshot', onSnap)
    es.addEventListener('world:updated', onSnap)
    es.onerror = () => setConnected(false)
    return () => es.close()
  }, [])

  // ── the logical clock (frame deltas → integer ticks) ─────────────────────
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
          // Killswitch: the world FREEZES (tick stops advancing state);
          // the red wash + banner + lever carry the truth.
          if (snap?.killswitch) continue
          // cutaway machine (pure; candidates from the current buildings)
          const host = hostRef.current
          const vp = { w: host?.clientWidth ?? 1024, h: host?.clientHeight ?? 640 }
          const cand = cutawayCandidate(buildingsRef.current, cameraRef.current, vp)
          cutawayRef.current = cutawayStep(cutawayRef.current, cand, tickRef.current)
          setCutaway(cutawayRef.current)
          // T2 LIFE step (pure reducer; grammar-gated fail-closed). Officer
          // positions mirror the canvas's seeded great-house yard slots.
          const feed = lifeFeedRef.current
          const gh = buildingsRef.current.find((b) => b.element === 'great_house')
          if (feed && snap && gh) {
            const officers: Record<
              string,
              { presence: OfficerPresence; x: number; y: number }
            > = {}
            const slugsSorted = (snap.officers ?? []).map((o) => o.slug).sort()
            slugsSorted.forEach((slug, i) => {
              const o = (snap.officers ?? []).find((x) => x.slug === slug)
              if (!o) return
              const h = fnv1a(`officer:${slug}`)
              officers[slug] = {
                presence: o.presence,
                x: gh.x + 0.5 + ((h >>> 4) % (gh.w * 2)) / 2,
                y: gh.y + gh.h + 1 + (i % 2),
              }
            })
            // time as DATA: the newest chronicle ts (never a wall clock)
            let nowTsMs = Date.parse(snap.connectedAt) || 0
            for (const r of snap.chronicle ?? []) {
              const t = r.ts ? Date.parse(r.ts) : NaN
              if (Number.isFinite(t) && t > nowTsMs) nowTsMs = t
            }
            // staged fauna species render nothing until their art lands
            // (grammar v3 fauna entries declare the staged scope) — drop
            // them from the active config so grammar and render align.
            const cfg = feed.grammar
              ? {
                  ...feed.grammar,
                  fauna: feed.grammar.fauna
                    ? Object.fromEntries(
                        Object.entries(feed.grammar.fauna).filter(
                          ([, v]) => !(v as { staged?: boolean }).staged
                        )
                      )
                    : undefined,
                }
              : null
            const step = lifeStep(lifeStateRef.current, {
              tick: tickRef.current,
              nowTsMs,
              clockHour: snap.clock?.hour ?? null,
              killswitch: snap.killswitch,
              officers,
              records: snap.chronicle ?? [],
              productLanes: new Set(feed.productLanes ?? []),
              siteEntries: feed.siteEntries ?? [],
              siteKeyframes: {},
              fauna: {
                bounds: { w: 240, h: 192 },
                // cozy pass 2026-07-09: real anchors from the dressing
                // table (flowers → butterflies-when-unstaged, quay water →
                // fish, porch → the dog, pens yard → chickens). Cat stays
                // staged (no art yet) — perch stays null.
                flowerAnchors: dressingRef.current?.flowerAnchors ?? [],
                quayWater: dressingRef.current?.quayWater ?? [],
                catPerch: null,
                dogPerch: dressingRef.current?.dogPerch ?? null,
                chickenSpots: dressingRef.current?.chickenSpots ?? [],
              },
              config: cfg,
            })
            lifeStateRef.current = step.state
            lifeOutRef.current = step.out
            setLifeOut(step.out)
          }
          setTick(tickRef.current)
        }
      }
      last = now
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [])

  // The kernel this client speaks in: one instance, shared by the pan
  // inverse, the DOM-label projection and the clamp box, so none of them can
  // drift from the canvas.
  const proj = useMemo(() => projectionFor(projection), [projection])

  // ── derived world models (all pure) ──────────────────────────────────────
  const geo: WorldGeo = useMemo(
    () =>
      buildWorldGeo({
        orgEventsTotal: engine?.orgEventsTotal ?? 0,
        lanes: engine?.eval?.lanes ?? {},
        berths: engine?.berths ?? [],
        probeWiredLanes: engine?.probeWiredLanes ?? [],
      }),
    [engine]
  )
  const clamp = useMemo(() => cameraClamp(projection, geo.canvas), [projection, geo.canvas])
  const buildings: WorldBuilding[] = useMemo(
    () => (resolution ? buildWorldBuildings(resolution, geo) : []),
    [resolution, geo]
  )
  buildingsRef.current = buildings
  const dressing = useMemo(
    () => buildOutdoorDressing(geo, buildings, resolution),
    [geo, buildings, resolution]
  )
  dressingRef.current = dressing

  // ── direction surface (grammar v4): courses + voyage + chart table ──────
  const courses = useMemo(() => engine?.courses ?? null, [engine])
  const voyage = useMemo(() => voyageRender(courses ?? {}), [courses])
  const chartTable = !!(
    engine?.directions &&
    (engine.directions.apex !== null ||
      Object.keys(engine.directions.lanes).length > 0)
  )

  const presenceBySlug = useMemo(() => {
    const m: Record<string, OfficerPresence> = {}
    for (const o of snapshot?.officers ?? []) m[o.slug] = o.presence
    return m
  }, [snapshot])
  const officersBySlug = useMemo(() => {
    const m = new Map<string, WorldOfficer>()
    for (const o of snapshot?.officers ?? []) m.set(o.slug, o)
    return m
  }, [snapshot])
  const officersBySel = useMemo(() => {
    const m = new Map<string, WorldOfficer>()
    for (const o of snapshot?.officers ?? []) m.set(o.sel, o)
    return m
  }, [snapshot])
  const clockText = formatClock(snapshot?.clock)

  // ── inspect assembly ─────────────────────────────────────────────────────
  const openInspect = useCallback(
    (target: EngineTarget | null) => {
      if (!target || target.kind === 'ground') {
        // catch-all honesty: unmapped pixels answer plainly (no dead clicks)
        if (target?.kind === 'ground') {
          setInspect({
            kind: 'station',
            id: 'ground',
            title: 'ground / water — carries no data',
            codex: null,
            decorative: true,
            presence: null,
            proof: null,
          })
          return
        }
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
        const codex: GrammarCodex | null = (verb && g?.showGrammar?.verbs[verb]?.codex) || null
        const proof =
          [...(snap?.chronicle ?? [])].reverse().find((r) => r.actor === target.id) ?? null
        setInspect({
          kind: 'officer',
          id: o.sel,
          title: `${o.slug} — officer`,
          codex,
          presence: o.presence,
          proof,
        })
        setSel(o.sel)
        return
      }
      if (target.kind === 'mailbox') {
        setMailboxOpen(true)
        return
      }
      if (target.kind === 'chart_table') {
        // read-only direction-chart card (show-grammar v4 chart_table_view):
        // WHAT = the manor_chart_table codex (grammar law), NOW = apex
        // verbatim + per-lane course rows + the grey drift gauge, PROOF =
        // dated port calls + the artifact's as-of line. Free text lives
        // ONLY here (authed card), never world-space. Never an actuator.
        const card = buildChartTableCard(
          engine?.directions ?? null,
          engine?.courses ?? {},
          engine?.portCalls ?? null
        )
        const codex =
          (g?.morphology?.entries ?? []).find((e) => e.id === 'manor_chart_table')
            ?.codex ?? null
        setInspect({
          kind: 'station',
          id: 'chart-table',
          title: card.title,
          codex,
          nowRows: card.nowRows,
          proofLines: card.proofLines,
          presence: null,
          proof: null,
        })
        setSel('chart-table') // deep-link: ?sel=chart-table (opaque fixed id)
        return
      }
      if (target.kind === 'site') {
        // T2 construction site — the sign card (WHAT/NOW/PROOF discipline:
        // crew figures are decorative-honest staging of a witnessed event)
        const st = lifeOutRef.current?.sites.find((s) => s.site.id === target.id)
        if (!st) return
        setInspect({
          kind: 'station',
          id: st.site.id,
          title:
            `${st.site.element} → ${st.site.targetStage} — ` +
            `${st.progress.phase} (${Math.round(st.progress.progress * 100)}%) · ` +
            `witness ${st.site.witness.kind}:${st.site.witness.ref}`,
          codex: lifeFeedRef.current?.grammar?.construction?.codex ?? null,
          presence: null,
          proof: null,
        })
        return
      }
      if (target.kind === 'lane') {
        const slot = Number(target.id.split(':')[1])
        const site = geo.laneSites.find((s) => s.slot === slot)
        if (!site) return
        setInspect({
          kind: 'station',
          id: target.id,
          title: site.lane
            ? `${site.lane} — ${site.render === 'isle' ? `isle ring r${site.ringRung - 1}` : site.render === 'reef_buoy' ? 'reef buoy' : 'reserved slot'}`
            : `reserved fan slot ${site.slot}`,
          codex: {
            represents: site.why,
            mechanism_path: 'instance/config/outcomes.yml',
            day0: 'reef — no ratified outcome',
          },
          presence: null,
          proof: null,
        })
        return
      }
      // building
      const b = buildings.find((x) => x.id === target.id)
      if (!b) return
      const el = resolution?.elements[b.element]
      const morphEntry = (g?.morphology?.entries ?? []).find((e) =>
        e.id.includes(b.element)
      )
      const staged = STAGED_VOCAB_ELEMENTS.has(b.element)
        ? ' · era art STAGED — honest worksite marker until proper art lands'
        : ''
      const now = el
        ? el.measured
          ? `${b.element}: ${el.rungName}${el.vocab ? ` (${el.vocab})` : ''} — metric ${el.value ?? '—'}${el.pending !== null ? ` · rung ${el.pending} pending hysteresis` : ''}${staged}`
          : `${b.element}: unmeasured — baseline rung renders grey, never interpolated${staged}`
        : b.element + staged
      setInspect({
        kind: 'station',
        id: b.id,
        title: now,
        codex:
          morphEntry?.codex ??
          ({
            represents: `${b.element} — era×rung ladder element (growth-ladders.yml); era styles it, its own metric sizes it.`,
            mechanism_path: 'cabinet/world/growth-ladders.yml',
            day0: 'baseline rung',
          } as GrammarCodex),
        decorative: false,
        presence: null,
        proof: null,
      })
    },
    [buildings, geo, officersBySlug, resolution, engine]
  )

  // Deep-link: ?sel=<handle> restores the officer card post-connect.
  useEffect(() => {
    if (!sel || inspect || !snapshot) return
    const o = officersBySel.get(sel)
    if (o) openInspect({ kind: 'officer', id: o.slug })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel, snapshot])

  // Deep-link: ?sel=chart-table restores the direction-chart card once the
  // engine payload (directions/courses/port calls) has arrived.
  useEffect(() => {
    if (sel !== 'chart-table' || inspect || !engine) return
    openInspect({ kind: 'chart_table', id: 'chart-table' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel, engine])

  // ── camera controls: CONTINUOUS zoom + pan (no scene swap, ever) ─────────
  const onWheel = useCallback((ev: React.WheelEvent) => {
    const factor = Math.exp(-ev.deltaY * 0.0016)
    setCamera((c) => ({ ...c, z: clampZoom(c.z * factor) }))
  }, [])
  const onPointerDown = useCallback((ev: React.PointerEvent) => {
    dragRef.current = { x: ev.clientX, y: ev.clientY, moved: false, camX: camera.x, camY: camera.y }
  }, [camera])
  const onPointerMove = useCallback((ev: React.PointerEvent) => {
    const d = dragRef.current
    if (!d) return
    const dx = ev.clientX - d.x
    const dy = ev.clientY - d.y
    if (!d.moved && Math.hypot(dx, dy) < 5) return
    d.moved = true
    setCamera((c) => {
      // A screen drag walks the INVERSE kernel basis. Dividing by a tile size
      // is only correct when the axes are uncoupled; under iso it slides the
      // camera diagonally under the cursor.
      const step = screenDeltaToTiles(proj, dx, dy, c.z)
      return {
        ...c,
        // one world, one clamp box — derived from the PROJECTED corners, so
        // the iso world's diamond extent is not cut off at two of them
        x: Math.max(clamp.x0, Math.min(clamp.x1, d.camX - step.tx)),
        y: Math.max(clamp.y0, Math.min(clamp.y1, d.camY - step.ty)),
      }
    })
  }, [proj, clamp])
  const onPointerUp = useCallback(() => {
    dragRef.current = null
  }, [])
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') {
        setInspect(null)
        setMailboxOpen(false)
        setLibraryOpen(false)
      }
      const pan = 3 / cameraRef.current.z
      if (ev.key === 'w' || ev.key === 'ArrowUp') setCamera((c) => ({ ...c, y: c.y - pan }))
      if (ev.key === 's' || ev.key === 'ArrowDown') setCamera((c) => ({ ...c, y: c.y + pan }))
      if (ev.key === 'a' || ev.key === 'ArrowLeft') setCamera((c) => ({ ...c, x: c.x - pan }))
      if (ev.key === 'd' || ev.key === 'ArrowRight') setCamera((c) => ({ ...c, x: c.x + pan }))
      if (ev.key === '+' || ev.key === '=') setCamera((c) => ({ ...c, z: clampZoom(c.z * 1.25) }))
      if (ev.key === '-') setCamera((c) => ({ ...c, z: clampZoom(c.z / 1.25) }))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const onPrimary = useCallback(
    (target: EngineTarget | null) => {
      if (dragRef.current?.moved) return
      if (!target || target.kind === 'ground') return
      if (target.kind === 'mailbox') {
        setMailboxOpen(true)
        return
      }
      const tier = lodTier(camera.z)
      if (tier === 'close' || tier === 'mid') {
        // The Library building's primary interaction = ENTER it: the reading
        // surface opens as chrome over the live canvas (spec v2 §5.2 [v3] /
        // P6). One continuous world — the camera, canvas, and tick are
        // untouched; NEVER a scene swap. Secondary still cites the era×rung
        // card (Legend Law).
        if (target.kind === 'building' && target.id === 'library') {
          setLibraryOpen(true)
          return
        }
        openInspect(target)
        return
      }
      // far zoom primary = NAVIGATE: fly toward the target (still one world)
      const pos =
        target.kind === 'building'
          ? (() => {
              const b = buildings.find((x) => x.id === target.id)
              return b ? { x: b.x + b.w / 2, y: b.y + b.h / 2 } : null
            })()
          : target.kind === 'lane'
            ? (() => {
                const site = geo.laneSites.find((s) => `lane:${s.slot}` === target.id)
                return site ? { x: site.cx, y: site.cy } : null
              })()
            : null
      if (pos) setCamera((c) => ({ z: clampZoom(c.z * 2), x: pos.x, y: pos.y }))
      else openInspect(target)
    },
    [camera.z, buildings, geo, openInspect]
  )
  const onSecondary = useCallback(
    (target: EngineTarget | null) => {
      if (target && target.kind !== 'ground') openInspect(target)
      else if (target?.kind === 'ground') openInspect(target)
      else setLegendOpen(true)
    },
    [openInspect]
  )

  // ── DOM labels (text is text) ────────────────────────────────────────────
  useEffect(() => {
    const el = hostRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setHostSize({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  // THE one forward projection for DOM chrome — the same kernel the canvas
  // draws with, so a label can never drift off the sprite it names.
  const project = useCallback(
    (wx: number, wy: number) => worldToScreen(proj, wx, wy, camera, hostSize),
    [proj, camera, hostSize]
  )

  // Label positions MIRROR engine-canvas officerPositions exactly (same
  // seeded math) so the DOM text sits on the drawn motes.
  // Cozy pass (gap #5 interim): name+verb chips only at CLOSE zoom — the
  // approved mockups carry ZERO floating labels; at island/mid tiers
  // identity is the sprite (portrait rail + inspect keep names one click
  // away). Full pixel two-tier typography stays the v1b row.
  const officerLabels = useMemo(() => {
    const gh = buildings.find((b) => b.element === 'great_house')
    if (!gh || lodTier(camera.z) !== 'close') return []
    // officerSlots is THE seeded placement — the canvas draws from it and the
    // hit test picks against it, so a name chip cannot drift off the officer it
    // names. It was re-derived here, and nothing held the two copies equal.
    return officerSlots(gh, Object.keys(presenceBySlug).sort(), cutaway.openId === gh.id).map(
      (o) => ({
        slug: o.slug,
        x: o.x,
        y: o.y,
        verb: presenceBySlug[o.slug]?.present ? presenceBySlug[o.slug]?.verb ?? null : null,
      })
    )
  }, [buildings, camera.z, presenceBySlug, cutaway.openId])

  const ticker = useMemo(
    () => [...(snapshot?.chronicle ?? [])].slice(-8).reverse(),
    [snapshot]
  )
  const tier = lodTier(camera.z)

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
        <EngineCanvas
          projection={projection}
          geo={geo}
          buildings={buildings}
          resolution={resolution}
          officers={presenceBySlug}
          life={lifeOut}
          camera={camera}
          cutaway={cutaway}
          weather={weather}
          tick={tick}
          killswitch={snapshot?.killswitch ?? false}
          clockHour={snapshot?.clock?.hour ?? null}
          chartTable={chartTable}
          courses={courses}
          voyage={voyage}
          onPrimary={onPrimary}
          onSecondary={onSecondary}
          onIssues={(issues) => setRenderIssues(issues)}
        />
      )}

      {/* ── officer labels: DOM text over the world (collision-laid-out —
           v1a fix: colliding labels garbled at the great-house yard) ── */}
      {!eraMode &&
        (() => {
          const projected = officerLabels
            .map((m) => ({ m, p: project(m.x, m.y - 2.2) }))
            .filter(
              ({ p }) =>
                !(p.x < -100 || p.x > hostSize.w + 100 || p.y < -50 || p.y > hostSize.h + 50)
            )
          const laid = layoutLabels(projected.map(({ m, p }) => ({ id: m.slug, x: p.x, y: p.y })))
          return (
            <div className="pointer-events-none absolute inset-0 z-10">
              {laid.map((l, i) => {
                const m = projected[i].m
                return (
                  <div
                    key={m.slug}
                    className="absolute -translate-x-1/2 text-center"
                    style={{ left: l.x, top: l.y + l.dy }}
                  >
                    {l.displaced && (
                      <div className="mx-auto h-3 w-px bg-zinc-400/60" aria-hidden />
                    )}
                    <div className="text-[11px] font-semibold leading-tight text-zinc-100 [text-shadow:0_1px_2px_rgba(0,0,0,0.9)]">
                      {m.slug}
                    </div>
                    <div className="text-[10px] leading-tight text-zinc-300 [text-shadow:0_1px_2px_rgba(0,0,0,0.9)]">
                      {m.verb ?? 'no live verb'}
                    </div>
                  </div>
                )
              })}
            </div>
          )
        })()}

      {/* ── top HUD ── */}
      <div className="pointer-events-none absolute left-0 right-0 top-0 z-20 flex flex-wrap items-center gap-2 px-3 py-2 text-xs">
        <span className="rounded bg-zinc-900/80 px-2 py-1 font-semibold">
          Cabinet World — one world · {tier}
        </span>
        <span className="rounded bg-zinc-900/80 px-2 py-1 text-zinc-400">
          ×{camera.z.toFixed(2)} · iid {snapshot?.iidHigh ?? 0} · {connected ? 'live' : 'reconnecting…'}
          {clockText ? ` · ${clockText}` : ''}
        </span>
        {resolution && (
          <span data-world-era className="rounded bg-zinc-900/80 px-2 py-1 text-zinc-300">
            era: {resolution.era} @ {resolution.eraIndex.toFixed(3)}
          </span>
        )}
        <span
          data-world-weather
          title={weather.why}
          className="rounded bg-zinc-900/80 px-2 py-1 text-zinc-300"
        >
          {weather.kind === 'sun' ? '☀' : weather.kind === 'rain' ? '🌧' : weather.kind === 'fog' ? '🌫' : '⛈'}{' '}
          {weather.kind}
        </span>
        {engine && engine.ladders.problems.length > 0 && (
          <span className="rounded bg-amber-900/80 px-2 py-1 font-medium text-amber-200">
            growth config refused: {engine.ladders.problems[0]}
          </span>
        )}
        {engine && !engine.eval && (
          <span data-world-census-badge className="rounded bg-amber-900/80 px-2 py-1 font-medium text-amber-200">
            census unavailable — the world renders its egg
          </span>
        )}
        {grammar?.pending !== false && (
          <span className="rounded bg-amber-900/80 px-2 py-1 font-medium text-amber-200">
            grammar pending Captain merge
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
              Live presence renders dark under an era pin. Keyframe replay
              rides world-preview (`cabinet/scripts/world-preview.py
              --maturity {at}`) until in-browser replay lands.
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

      {/* ── chronicle ticker (citations-only; click = PROOF) + art credit ── */}
      <div className="absolute bottom-0 left-0 right-0 z-20 flex items-center gap-2 border-t border-zinc-800 bg-zinc-950/90 px-2 py-1 text-[11px]">
        <div className="flex flex-1 gap-2 overflow-x-auto">
          {ticker.length === 0 ? (
            <span className="text-zinc-600">chronicle quiet…</span>
          ) : (
            ticker.map((r: ChronicleRecord) => (
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
        {/* LimeZu license credit (Captain-ratified 2026-07-12), shown WHERE IT
            IS OWED: the licence requires it wherever LimeZu art is drawn, and
            printing it over a frame LimeZu did not draw attributes our own art
            to someone else. `limezuSurfaces` derives that from the manifest's
            licence column over what each mounted surface binds — see
            lib/world/credit.ts. It is in the always-on bottom bar, never behind
            the legend toggle. */}
        {creditSurfaces.length > 0 && (
          <span
            data-world-credit
            data-credit-surfaces={creditSurfaces.join(',')}
            title={creditReason(creditSurfaces)}
            className="shrink-0 whitespace-nowrap text-[10px] text-zinc-500"
          >
            Art: LimeZu — limezu.itch.io
          </span>
        )}
      </div>

      {/* ── Legend Law panel (grammar + growth-ladders provenance) ── */}
      {legendOpen && (
        <div className="absolute left-4 top-16 z-30 max-h-[70vh] w-96 max-w-[92vw] overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900/95 p-3 text-xs shadow-2xl">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-semibold">Legend (grammar law + growth ladders)</span>
            <button onClick={() => setLegendOpen(false)} className="rounded px-2 text-zinc-400 hover:bg-zinc-800">
              close
            </button>
          </div>
          {typeof grammar?.codexCoverage === 'number' && (
            <div data-world-coverage-gauge className="mb-2">
              <div className="mb-0.5 flex justify-between font-mono text-[10px] text-zinc-400">
                <span>codex coverage</span>
                <span>{(grammar.codexCoverage * 100).toFixed(0)}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-sm bg-zinc-800">
                <div
                  className={'h-full ' + (grammar.codexCoverage >= 1 ? 'bg-emerald-500' : 'bg-amber-500')}
                  style={{ width: `${Math.round(grammar.codexCoverage * 100)}%` }}
                />
              </div>
            </div>
          )}
          {resolution && (
            <div className="mb-2 rounded bg-zinc-950 p-2">
              <div className="font-mono text-zinc-200">
                era = {resolution.era} · index {resolution.eraIndex.toFixed(3)}
              </div>
              <div className="text-zinc-400">
                growth-ladders.yml (hot-reloaded, mtime{' '}
                {engine?.ladders.mtimeMs ? Math.round(engine.ladders.mtimeMs) : '—'}) · era styles,
                rungs measure. Unmeasured metrics: {resolution.eraUnmeasured.join(', ') || 'none'}
              </div>
            </div>
          )}
          <div className="space-y-2">
            {(grammar?.morphology?.entries ?? []).map((e) => (
              <div key={e.id} className="rounded bg-zinc-950 p-2">
                <div className="font-mono text-zinc-200">{e.id}</div>
                <div className="break-all font-mono text-[10px] text-zinc-500">{e.source_binding}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── portrait rail (chrome, never the world framebuffer) ── */}
      {!eraMode && (
        <PortraitRail
          tick={tick}
          onInspect={(slug) => openInspect({ kind: 'officer', id: slug })}
          onLimeZuPortraits={setRailLimeZu}
        />
      )}

      {/* ── mailbox: READ-only pending decision-queue view (ruling) ── */}
      {mailboxOpen && <DecisionQueueCard onClose={() => setMailboxOpen(false)} />}

      {/* ── the Library: READ-only browse/read/search over the org vault
           (spec v2 §5.2 Memory Library + §9.2 query dialog; chrome over the
           live canvas — the world keeps ticking, never a scene swap) ── */}
      {libraryOpen && <LibraryCard onClose={() => setLibraryOpen(false)} />}

      {/* ── inspect card ── */}
      {inspect && (
        <InspectCard
          target={inspect}
          onClose={() => {
            setInspect(null)
            setSel(null)
          }}
        />
      )}

      {/* ── THE killswitch lever: the ONE actuator (break-through law) ── */}
      <KillswitchLever active={snapshot?.killswitch ?? false} tick={tick} canActuate={canActuate} />

      {/* ── killswitch break-through: unsuppressible, above everything ── */}
      {snapshot?.killswitch && (
        <div className="absolute inset-0 z-50 flex items-start justify-center bg-red-950/60">
          <div className="mt-20 rounded-lg border-2 border-red-500 bg-red-900 px-6 py-4 text-center">
            <div className="text-lg font-bold text-red-100">KILLSWITCH ACTIVE</div>
            <div className="text-sm text-red-200">
              fleet halted — the storm is the sky; release is the lever&apos;s ceremony
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
