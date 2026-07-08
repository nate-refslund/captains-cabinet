'use client'

/**
 * WorldCanvas — the PixiJS PURE RENDERER (E1 Wardroom, LimeZu-textured).
 *
 * Doctrine enforced here:
 *  - pure renderer: draws ONLY what the deterministic director computed;
 *    no state of its own beyond GPU objects, no writes anywhere.
 *  - no world-space text: every glyph is DOM (the label layer) — the canvas
 *    carries geometry only.
 *  - no Math.random / Date.now in the render path: cosmetic phase comes
 *    from seeded hashes; the logical clock is advanced from frame deltas by
 *    the client shell and passed IN (CI ratchet greps this tree).
 *  - CSP: /world pins an eval-free script-src (next.config.ts ratchet).
 *    PixiJS v8's WebGL uniform-sync normally compiles new Function()s, so we
 *    import the official 'pixi.js/unsafe-eval' PATCH (AOT, eval-free) before
 *    init instead of ever widening the header — and keep preferWorkers off
 *    so Assets never constructs blob: workers the CSP would refuse.
 *    (Root cause of the 2026-07-08 black-canvas incident: init rejected on
 *    the eval check and the failure was swallowed — see the loud-failure
 *    contract below.)
 *  - LOUD FAILURE (configured-but-dead must be loud): boot errors, manifest
 *    gaps, and texture-load failures console.error AND surface through
 *    onIssues → the client shell badges them in DOM. Silent-black is a
 *    ratcheted regression class now (ratchets.test.ts #8/#9).
 *  - assets: LimeZu sheets resolve ONLY through the content-addressed
 *    manifest (lib/world/sprites.ts). Any entity whose sheet is missing
 *    renders as the outlined placeholder marker — visibly placeholder,
 *    never fake art, never invisible.
 */
import { useEffect, useRef } from 'react'
import type { Container, Graphics, Sprite, Texture, TilingSprite } from 'pixi.js'
import type { OfficerScene, CameraState } from '@/lib/world/types'
import type { WardroomLayout } from '@/lib/world/layout'
import { TILE } from '@/lib/world/layout'
import { fnv1a } from '@/lib/world/hash'
import {
  BUNK_SHEET,
  CHAR_STRETCH_CUT,
  charFrame,
  characterSheetFor,
  deskSheetFor,
  FLOOR_CUT,
  resolveWorldSprites,
  ROOM_SHEET,
  STATION_SPRITES,
  WALL_CUT,
  WALL_TILES,
  type CharFacing,
  type SpriteCut,
  type WorldAssetManifest,
} from '@/lib/world/sprites'

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
  /** Loud-failure surface: boot/manifest/texture problems, badged in DOM. */
  onIssues?: (issues: string[]) => void
}

interface PixiHandles {
  app: unknown
  destroy: () => void
  draw: (props: WorldCanvasProps) => void
}

/** Vertical foot offset (px) so officers stand legibly around fixtures. */
function standOffsetPx(s: OfficerScene): number {
  if (s.anim === 'walk') return 0
  if (s.stationId.startsWith('desk:')) return -2 // behind the desk, face clear of the monitor
  if (s.stationId.startsWith('bunk:')) return 0 // on the rest chair
  if (s.stationId.startsWith('seat:')) return 6 // at a table seat
  if (s.stationId.startsWith('wander:')) return 8 // pausing at a waypoint
  return 14 // civic fixture: stand in front of it, facing up
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
      const PIXI = await import('pixi.js')
      // CSP-compat: installs the AOT uniform-sync path BEFORE any renderer
      // exists. The /world header stays eval-free — never add 'unsafe-eval'.
      await import('pixi.js/unsafe-eval')
      if (cancelled || !hostRef.current) return

      // 16px art: nearest sampling, no blob: worker decode (CSP worker-src).
      PIXI.TextureSource.defaultOptions.scaleMode = 'nearest'
      PIXI.Assets.setPreferences({ preferWorkers: false })

      const app = new PIXI.Application()
      await app.init({
        background: 0x14161c,
        resizeTo: hostRef.current,
        antialias: false,
        roundPixels: true,
      })
      if (cancelled || !hostRef.current) {
        app.destroy(true)
        return
      }
      hostRef.current.appendChild(app.canvas)

      // ── texture phase: manifest-bound, loud on every gap ────────────────
      const issues: string[] = []
      const sheets = new Map<string, Texture>()
      try {
        const res = await fetch('/world-assets/manifest.json')
        if (!res.ok) throw new Error(`manifest HTTP ${res.status}`)
        const manifest = (await res.json()) as WorldAssetManifest
        const resolved = resolveWorldSprites(manifest)
        for (const id of resolved.missing) {
          issues.push(`missing sheet: ${id}`)
          console.error('[world] sprite sheet missing/invalid in manifest — placeholder fallback:', id)
        }
        const loaded = await Promise.all(
          Object.entries(resolved.urls).map(async ([id, url]) => {
            try {
              return [id, (await PIXI.Assets.load(url)) as Texture] as const
            } catch (err) {
              issues.push(`texture load failed: ${id}`)
              console.error('[world] texture load failed — placeholder fallback:', id, err)
              return [id, null] as const
            }
          })
        )
        for (const [id, tex] of loaded) if (tex) sheets.set(id, tex)
      } catch (err) {
        issues.push('asset manifest unavailable — placeholder mode')
        console.error('[world] asset manifest fetch failed — placeholder mode:', err)
      }
      if (cancelled || !hostRef.current) {
        app.destroy(true, { children: true })
        return
      }

      const cutCache = new Map<string, Texture>()
      const texFor = (sheetId: string, cut?: SpriteCut): Texture | null => {
        const base = sheets.get(sheetId)
        if (!base) return null
        if (!cut) return base
        const key = `${sheetId}|${cut.x},${cut.y},${cut.w},${cut.h}`
        let t = cutCache.get(key)
        if (!t) {
          t = new PIXI.Texture({
            source: base.source,
            frame: new PIXI.Rectangle(cut.x, cut.y, cut.w, cut.h),
          })
          cutCache.set(key, t)
        }
        return t
      }

      // ── scene graph ──────────────────────────────────────────────────────
      const world: Container = new PIXI.Container()
      app.stage.addChild(world)

      const layout0 = propsRef.current.layout
      let floorTS: TilingSprite | null = null
      let wallTS: TilingSprite | null = null
      const floorTex = texFor(ROOM_SHEET, FLOOR_CUT)
      if (floorTex) {
        floorTS = new PIXI.TilingSprite({
          texture: floorTex,
          width: layout0.widthPx,
          height: layout0.heightPx,
        })
        world.addChild(floorTS)
      }
      const floorG: Graphics = new PIXI.Graphics()
      world.addChild(floorG)
      const wallTex = texFor(ROOM_SHEET, WALL_CUT)
      if (wallTex) {
        wallTS = new PIXI.TilingSprite({
          texture: wallTex,
          width: layout0.widthPx,
          height: WALL_TILES * TILE,
        })
        world.addChild(wallTS)
      }
      const flatLayer: Container = new PIXI.Container() // mats/rugs, under everything mobile
      world.addChild(flatLayer)
      const stationG: Graphics = new PIXI.Graphics() // placeholder fixtures
      world.addChild(stationG)
      const propLayer: Container = new PIXI.Container() // y-sorted props + officers
      propLayer.sortableChildren = true
      world.addChild(propLayer)
      const officerG: Graphics = new PIXI.Graphics() // placeholder officers
      world.addChild(officerG)
      const fxG: Graphics = new PIXI.Graphics() // killswitch lamp (reserved red)
      world.addChild(fxG)

      const stationSprites = new Map<string, Sprite>()
      const officerSprites = new Map<string, Sprite>()

      /** Sync station props to the layout; returns ids drawn as sprites. */
      function syncStations(p: WorldCanvasProps): Set<string> {
        const wanted = new Map<
          string,
          {
            sheet: string
            flat: boolean
            cut?: SpriteCut
            x: number
            y: number
            kind: 'desk' | 'bunk' | 'civic' | 'flat' | 'wall'
          }
        >()
        for (const st of p.layout.stations.values()) {
          let sheet: string | null = null
          let flat = false
          let cut: SpriteCut | undefined
          let kind: 'desk' | 'bunk' | 'civic' | 'flat' | 'wall' = 'civic'
          if (st.id.startsWith('desk:')) {
            sheet = deskSheetFor(st.id.slice('desk:'.length))
            kind = 'desk'
          } else if (st.id.startsWith('bunk:')) {
            sheet = BUNK_SHEET
            kind = 'bunk'
          } else if (STATION_SPRITES[st.id]) {
            const ss = STATION_SPRITES[st.id]
            sheet = ss.sheet
            flat = ss.flat
            cut = ss.cut // big-sheet fixtures draw their verified cut ONLY
            kind = ss.wall ? 'wall' : flat ? 'flat' : 'civic'
          }
          if (!sheet) continue
          wanted.set(st.id, { sheet, flat, cut, x: st.x, y: st.y, kind })
        }
        for (const [id, sp] of stationSprites) {
          if (!wanted.has(id)) {
            sp.destroy()
            stationSprites.delete(id)
          }
        }
        const drawn = new Set<string>()
        for (const [id, w] of wanted) {
          const tex = texFor(w.sheet, w.cut)
          if (!tex) continue // placeholder rect path stays loud + visible
          let sp = stationSprites.get(id)
          if (!sp) {
            sp = new PIXI.Sprite(tex)
            sp.anchor.set(0.5, 1)
            ;(w.flat ? flatLayer : propLayer).addChild(sp)
            stationSprites.set(id, sp)
          }
          const px = w.x * TILE
          if (w.kind === 'flat') {
            sp.position.set(px, w.y * TILE + 12)
          } else if (w.kind === 'desk') {
            // Desk fronts its officer: bottom one tile below the stand tile,
            // z ahead of the officer standing behind it.
            const by = (w.y + 1) * TILE + 6
            sp.position.set(px, by)
            sp.zIndex = by
          } else if (w.kind === 'bunk') {
            const by = w.y * TILE + 2
            sp.position.set(px, by)
            sp.zIndex = by - 20 // chair back behind the resting officer
          } else if (w.kind === 'wall') {
            // Wall-hung fixture (windows, noticeboard): anchored to the wall
            // band's bottom edge, z behind anyone standing on the floor.
            const by = WALL_TILES * TILE + 2
            sp.position.set(px, by)
            sp.zIndex = by - 20
          } else {
            const by = w.y * TILE + 6
            sp.position.set(px, by)
            sp.zIndex = by
          }
          drawn.add(id)
        }
        return drawn
      }

      function syncOfficers(p: WorldCanvasProps) {
        officerG.clear()
        const seen = new Set<string>()
        for (const s of p.scenes) {
          seen.add(s.slug)
          const px = s.x * TILE
          const bob =
            s.anim === 'work'
              ? Math.round(((p.tick + (fnv1a(s.slug) % 7)) % 8) / 4)
              : 0
          const dy = standOffsetPx(s)
          const py = s.y * TILE + dy - bob
          // Facing is DIRECTOR-owned now (walk direction, station posture,
          // micro-loop glances, chat pairing) — the renderer just draws it.
          const facing: CharFacing = s.facing
          const cut =
            s.micro === 'stretch'
              ? CHAR_STRETCH_CUT // §1.1: static up-frame hold (leaning back)
              : charFrame(s.anim, facing, p.tick, fnv1a(s.slug) % 6)
          const tex = texFor(characterSheetFor(s.slug), cut)
          const sp = officerSprites.get(s.slug)
          if (!tex) {
            // Placeholder marker (visibly placeholder, never fake art).
            if (sp) sp.visible = false
            const bodyW = TILE
            const bodyH = TILE * 1.5
            const alpha = s.anim === 'asleep' ? 0.35 : 1
            officerG
              .rect(px - bodyW / 2, py - bodyH, bodyW, bodyH)
              .fill({ color: officerColor(s.slug), alpha })
            officerG
              .rect(px - bodyW / 2, py - bodyH, bodyW, bodyH)
              .stroke({ width: 2, color: 0x0c0e12 })
            continue
          }
          let osp = sp
          if (!osp) {
            osp = new PIXI.Sprite(tex)
            osp.anchor.set(0.5, 1)
            propLayer.addChild(osp)
            officerSprites.set(s.slug, osp)
          }
          osp.visible = true
          osp.texture = tex
          osp.position.set(px, py + 4)
          osp.alpha = s.anim === 'asleep' ? 0.45 : 1
          osp.zIndex = py + 4
        }
        for (const [slug, osp] of officerSprites) {
          if (!seen.has(slug)) {
            osp.destroy()
            officerSprites.delete(slug)
          }
        }
      }

      function draw(p: WorldCanvasProps) {
        const vw = app.renderer.width
        const vh = app.renderer.height
        const z = p.camera.z
        world.scale.set(z)
        world.position.set(
          vw / 2 - p.camera.x * TILE * z,
          vh / 2 - p.camera.y * TILE * z
        )

        // Floor: textured when the sheet resolved; placeholder fill + grid
        // otherwise (loud badge already raised). Border always drawn.
        floorG.clear()
        if (!floorTS) {
          floorG.rect(0, 0, p.layout.widthPx, p.layout.heightPx).fill(0x1d212b)
          for (let gx = 0; gx <= p.layout.widthPx; gx += TILE * 4) {
            floorG.moveTo(gx, 0).lineTo(gx, p.layout.heightPx).stroke({ width: 1, color: 0x232836 })
          }
          for (let gy = 0; gy <= p.layout.heightPx; gy += TILE * 4) {
            floorG.moveTo(0, gy).lineTo(p.layout.widthPx, gy).stroke({ width: 1, color: 0x232836 })
          }
        }
        floorG
          .rect(0, 0, p.layout.widthPx, p.layout.heightPx)
          .stroke({ width: 2, color: 0x3a4152 })

        const spriteStations = syncStations(p)

        // Placeholder fixtures for anything without a resolved sheet.
        stationG.clear()
        for (const st of p.layout.stations.values()) {
          if (spriteStations.has(st.id)) continue
          const isDesk = st.id.startsWith('desk:')
          const isBunk = st.id.startsWith('bunk:')
          const w = isDesk ? TILE * 2 : TILE * 1.5
          const h = isDesk ? TILE : TILE * 1.2
          const x = st.x * TILE - w / 2
          const y = st.y * TILE - h / 2
          const color = isDesk ? 0x4a5468 : isBunk ? 0x39415a : 0x475060
          stationG.rect(x, y, w, h).fill(color)
          stationG.rect(x, y, w, h).stroke({ width: 1, color: 0x2a2f3d })
        }

        syncOfficers(p)

        // Killswitch lamp on the lever fixture: red ONLY when active
        // (reserved salience hue — dual-coded by the DOM banner text).
        fxG.clear()
        if (p.killswitch) {
          // §1.5 grammar killswitch_scene: full-scene red wash. The director
          // is frozen by the reducer; this is the canvas half of the truth
          // (third channel = the unsuppressible DOM banner).
          fxG
            .rect(0, 0, p.layout.widthPx, p.layout.heightPx)
            .fill({ color: 0xcc2222, alpha: 0.14 })
        }
        const lever = p.layout.stations.get('lever')
        if (lever) {
          const lx = lever.x * TILE
          const ly = lever.y * TILE
          fxG
            .rect(lx - 4, ly - 46, 8, 6)
            .fill(p.killswitch ? 0xcc2222 : 0x555f72)
          if (p.killswitch) {
            fxG
              .rect(lx - 12, ly - 52, 24, 18)
              .stroke({ width: 2, color: 0xcc2222 })
          }
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
      if (issues.length) propsRef.current.onIssues?.(issues)
    }
    boot().catch((err: unknown) => {
      // The 2026-07-08 incident class: init/boot rejection must NEVER be
      // silent — badge it in DOM (the canvas may be dark, the truth is not).
      console.error('[world] renderer boot failed — placeholder DOM badge raised:', err)
      propsRef.current.onIssues?.([
        `renderer failed: ${err instanceof Error ? err.message : String(err)}`,
      ])
    })
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
