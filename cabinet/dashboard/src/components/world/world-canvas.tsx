'use client'

/**
 * WorldCanvas — the PixiJS PURE RENDERER (E1 Wardroom).
 *
 * Doctrine enforced here:
 *  - pure renderer: draws ONLY what the deterministic director computed;
 *    no state of its own beyond GPU objects, no writes anywhere.
 *  - no world-space text: every glyph is DOM (the label layer) — the canvas
 *    carries geometry only.
 *  - no Math.random / Date.now in the render path: cosmetic phase comes
 *    from seeded hashes; the logical clock is advanced from frame deltas by
 *    the client shell and passed IN (CI ratchet greps this tree).
 *  - assets: LimeZu packs are a Captain purchase (kickoff to-do 1). Until
 *    they drop into public/world-assets/ (conformance-gated), officers
 *    render as outlined placeholder markers — visibly placeholder, never
 *    fake art (WORLD-E1-ASSETS ledger row).
 */
import { useEffect, useRef } from 'react'
import type { OfficerScene, CameraState } from '@/lib/world/types'
import type { WardroomLayout } from '@/lib/world/layout'
import { TILE } from '@/lib/world/layout'
import { fnv1a } from '@/lib/world/hash'

// Stable per-slug placeholder color (cosmetic; zero information — the
// literacy rule: salience colors are RESERVED and never used here).
function officerColor(slug: string): number {
  const h = fnv1a(slug)
  // Muted palette band away from the reserved salience hues.
  const r = 90 + (h % 90)
  const g = 90 + ((h >> 8) % 90)
  const b = 120 + ((h >> 16) % 100)
  return (r << 16) | (g << 8) | b
}

export interface WorldCanvasProps {
  layout: WardroomLayout
  scenes: OfficerScene[]
  camera: CameraState
  killswitch: boolean
  tick: number
  onPrimary: (target: { kind: 'officer' | 'station'; id: string } | null, screen: { x: number; y: number }) => void
  onSecondary: (target: { kind: 'officer' | 'station'; id: string } | null, screen: { x: number; y: number }) => void
}

interface PixiHandles {
  app: unknown
  destroy: () => void
  draw: (props: WorldCanvasProps) => void
}

export default function WorldCanvas(props: WorldCanvasProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const handlesRef = useRef<PixiHandles | null>(null)
  const propsRef = useRef(props)
  propsRef.current = props

  useEffect(() => {
    let cancelled = false
    async function boot() {
      if (!hostRef.current) return
      const { Application, Container, Graphics } = await import('pixi.js')
      if (cancelled || !hostRef.current) return
      const app = new Application()
      await app.init({
        background: 0x14161c,
        resizeTo: hostRef.current,
        antialias: false,
      })
      if (cancelled || !hostRef.current) {
        app.destroy(true)
        return
      }
      hostRef.current.appendChild(app.canvas)

      const world = new Container()
      app.stage.addChild(world)
      const floorG = new Graphics()
      const stationG = new Graphics()
      const officerG = new Graphics()
      world.addChild(floorG)
      world.addChild(stationG)
      world.addChild(officerG)

      function draw(p: WorldCanvasProps) {
        const vw = app.renderer.width
        const vh = app.renderer.height
        const z = p.camera.z
        world.scale.set(z)
        world.position.set(
          vw / 2 - p.camera.x * TILE * z,
          vh / 2 - p.camera.y * TILE * z
        )

        // Floor + grid (geometry only; decorative — carries no data).
        floorG.clear()
        floorG.rect(0, 0, p.layout.widthPx, p.layout.heightPx).fill(0x1d212b)
        floorG
          .rect(0, 0, p.layout.widthPx, p.layout.heightPx)
          .stroke({ width: 2, color: 0x3a4152 })
        for (let gx = 0; gx <= p.layout.widthPx; gx += TILE * 4) {
          floorG.moveTo(gx, 0).lineTo(gx, p.layout.heightPx).stroke({ width: 1, color: 0x232836 })
        }
        for (let gy = 0; gy <= p.layout.heightPx; gy += TILE * 4) {
          floorG.moveTo(0, gy).lineTo(p.layout.widthPx, gy).stroke({ width: 1, color: 0x232836 })
        }

        // Stations (props): outlined fixtures; desks slightly larger.
        stationG.clear()
        for (const st of p.layout.stations.values()) {
          const isDesk = st.id.startsWith('desk:')
          const isBunk = st.id.startsWith('bunk:')
          const w = isDesk ? TILE * 2 : TILE * 1.5
          const h = isDesk ? TILE : TILE * 1.2
          const x = st.x * TILE - w / 2
          const y = st.y * TILE - h / 2
          const color = isDesk ? 0x4a5468 : isBunk ? 0x39415a : 0x475060
          stationG.rect(x, y, w, h).fill(color)
          stationG.rect(x, y, w, h).stroke({ width: 1, color: 0x2a2f3d })
          if (st.id === 'lever') {
            // The killswitch lever fixture: red ONLY when active (reserved
            // salience hue — dual-coded by the DOM banner text).
            stationG
              .rect(x + w / 4, y - TILE, w / 2, TILE)
              .fill(p.killswitch ? 0xcc2222 : 0x555f72)
          }
        }

        // Officers (placeholder markers until LimeZu lands): 2px outline,
        // idle bob from seeded phase + logical tick (never wall clock).
        officerG.clear()
        for (const s of p.scenes) {
          const px = s.x * TILE
          const bob =
            s.anim === 'work'
              ? Math.round(((p.tick + (fnv1a(s.slug) % 7)) % 8) / 4)
              : 0
          const py = s.y * TILE - bob
          const bodyW = TILE
          const bodyH = TILE * 1.5
          const alpha = s.anim === 'asleep' ? 0.35 : 1
          officerG
            .rect(px - bodyW / 2, py - bodyH, bodyW, bodyH)
            .fill({ color: officerColor(s.slug), alpha })
          officerG
            .rect(px - bodyW / 2, py - bodyH, bodyW, bodyH)
            .stroke({ width: 2, color: 0x0c0e12 })
        }
      }

      function hitTarget(ev: MouseEvent): { kind: 'officer' | 'station'; id: string } | null {
        const rect = app.canvas.getBoundingClientRect()
        const p = propsRef.current
        const z = p.camera.z
        const wx =
          (ev.clientX - rect.left - app.renderer.width / 2) / (TILE * z) +
          p.camera.x
        const wy =
          (ev.clientY - rect.top - app.renderer.height / 2) / (TILE * z) +
          p.camera.y
        for (const s of p.scenes) {
          if (Math.abs(wx - s.x) < 1 && wy < s.y && wy > s.y - 2) {
            return { kind: 'officer', id: s.slug }
          }
        }
        for (const st of p.layout.stations.values()) {
          if (Math.abs(wx - st.x) < 1.2 && Math.abs(wy - st.y) < 1.2) {
            return { kind: 'station', id: st.id }
          }
        }
        return null
      }

      const onClick = (ev: MouseEvent) => {
        propsRef.current.onPrimary(hitTarget(ev), { x: ev.clientX, y: ev.clientY })
      }
      const onContext = (ev: MouseEvent) => {
        // Universal secondary gesture (UI-F2): inspect anything, any zoom.
        ev.preventDefault()
        propsRef.current.onSecondary(hitTarget(ev), { x: ev.clientX, y: ev.clientY })
      }
      app.canvas.addEventListener('click', onClick)
      app.canvas.addEventListener('contextmenu', onContext)

      handlesRef.current = {
        app,
        draw,
        destroy: () => {
          app.canvas.removeEventListener('click', onClick)
          app.canvas.removeEventListener('contextmenu', onContext)
          app.destroy(true, { children: true })
        },
      }
      draw(propsRef.current)
    }
    boot()
    return () => {
      cancelled = true
      handlesRef.current?.destroy()
      handlesRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    handlesRef.current?.draw(props)
  }, [props])

  return (
    <div
      ref={hostRef}
      className="absolute inset-0 overflow-hidden"
      data-world-canvas
    />
  )
}
