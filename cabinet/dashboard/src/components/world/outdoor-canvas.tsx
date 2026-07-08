'use client'

/**
 * OutdoorCanvas — PixiJS pure renderer for the Z1 street / Z0 island scenes
 * (world-alive §3, T3). Sibling of WorldCanvas (the Wardroom renderer) and
 * bound by the identical doctrine:
 *  - pure renderer over deterministic layout modules (street-layout.ts /
 *    island-layout.ts) — no state beyond GPU objects, no writes, no wall
 *    clock, no unseeded RNG (CI ratchet greps this tree);
 *  - CSP: same eval-free boot — official 'pixi.js/unsafe-eval' AOT patch
 *    imported before init, preferWorkers off, /world header untouched;
 *  - LOUD FAILURE: manifest gaps / texture failures / boot rejection
 *    console.error AND badge via onIssues (ratchets #8/#9 extend to every
 *    new asset class);
 *  - no world-space text: officer labels stay DOM (client shell);
 *  - officers here are BADGE MOTES, not walkers-on-the-street: they are
 *    honestly inside the HQ. A mote drifts along the facade only while its
 *    officer holds a live verb (same Redis predicate as Z2), seeded from
 *    (slug, logical tick); TTL-expired motes stand still.
 */
import { useEffect, useRef } from 'react'
import type { Container, Graphics, Texture } from 'pixi.js'
import type { CameraState, OfficerPresence } from '@/lib/world/types'
import { TILE } from '@/lib/world/layout'
import { fnv1a } from '@/lib/world/hash'
import type { SpriteCut, WorldAssetManifest } from '@/lib/world/sprites'
import {
  V,
  VILLAGE_SHEET,
  bucketOf,
  cropCut,
  moteColor,
  motePatrolX,
  resolveOutdoorSprites,
  type DayBucket,
  type OutdoorScene,
} from '@/lib/world/sprites-outdoor'
import type { StreetLayout } from '@/lib/world/street-layout'
import { hqStack } from '@/lib/world/street-layout'
import type { IslandLayout } from '@/lib/world/island-layout'

const AMBIENT: Record<DayBucket, { color: number; alpha: number } | null> = {
  dawn: { color: 0xffe8d0, alpha: 0.06 },
  day: null,
  dusk: { color: 0xffc890, alpha: 0.1 },
  night: { color: 0x2a3560, alpha: 0.22 },
}

export interface OutdoorTarget {
  kind: 'officer' | 'station'
  id: string
}

export interface OutdoorCanvasProps {
  scene: OutdoorScene
  street: StreetLayout | null
  island: IslandLayout | null
  officers: Record<string, OfficerPresence>
  camera: CameraState
  tick: number
  killswitch: boolean
  /** Server-stamped captain-local hour (snapshot.clock), or null = day. */
  clockHour: number | null
  onPrimary: (target: OutdoorTarget | null) => void
  onSecondary: (target: OutdoorTarget | null) => void
  onIssues?: (issues: string[]) => void
}

interface PixiHandles {
  destroy: () => void
  draw: (props: OutdoorCanvasProps) => void
}

export default function OutdoorCanvas(props: OutdoorCanvasProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const handlesRef = useRef<PixiHandles | null>(null)
  const propsRef = useRef(props)
  propsRef.current = props

  useEffect(() => {
    let cancelled = false
    async function boot() {
      if (!hostRef.current) return
      const PIXI = await import('pixi.js')
      await import('pixi.js/unsafe-eval') // CSP: AOT patch, header never widens
      if (cancelled || !hostRef.current) return

      PIXI.TextureSource.defaultOptions.scaleMode = 'nearest'
      PIXI.Assets.setPreferences({ preferWorkers: false })

      const app = new PIXI.Application()
      await app.init({
        background: 0x101318,
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
      const scene0 = propsRef.current.scene
      try {
        const res = await fetch('/world-assets/manifest.json')
        if (!res.ok) throw new Error(`manifest HTTP ${res.status}`)
        const manifest = (await res.json()) as WorldAssetManifest
        const resolved = resolveOutdoorSprites(manifest, scene0)
        for (const id of resolved.missing) {
          issues.push(`missing sheet: ${id}`)
          console.error('[world/outdoor] sheet missing/invalid in manifest — placeholder fallback:', id)
        }
        const loaded = await Promise.all(
          Object.entries(resolved.urls).map(async ([id, url]) => {
            try {
              return [id, (await PIXI.Assets.load(url)) as Texture] as const
            } catch (err) {
              issues.push(`texture load failed: ${id}`)
              console.error('[world/outdoor] texture load failed — placeholder fallback:', id, err)
              return [id, null] as const
            }
          })
        )
        for (const [id, tex] of loaded) if (tex) sheets.set(id, tex)
      } catch (err) {
        issues.push('asset manifest unavailable — placeholder mode')
        console.error('[world/outdoor] asset manifest fetch failed — placeholder mode:', err)
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

      const world: Container = new PIXI.Container()
      app.stage.addChild(world)
      const terrainLayer: Container = new PIXI.Container()
      world.addChild(terrainLayer)
      const terrainG: Graphics = new PIXI.Graphics() // placeholder terrain
      world.addChild(terrainG)
      const propLayer: Container = new PIXI.Container()
      propLayer.sortableChildren = true
      world.addChild(propLayer)
      const propG: Graphics = new PIXI.Graphics() // placeholder props
      world.addChild(propG)
      const dynG: Graphics = new PIXI.Graphics() // motes, windows, ghosts
      world.addChild(dynG)
      const fxG: Graphics = new PIXI.Graphics() // ambient tint, pools, wash
      world.addChild(fxG)

      /** Identity of the statics currently built into the layers. */
      let builtKey = ''

      function clearStatics() {
        terrainLayer.removeChildren().forEach((c) => c.destroy())
        propLayer.removeChildren().forEach((c) => c.destroy())
      }

      function buildStreet(p: OutdoorCanvasProps) {
        const L = p.street
        if (!L) return
        for (const g of L.ground) {
          const tex = texFor(g.sheet)
          if (!tex) continue // terrain placeholder handled in draw()
          const sp = new PIXI.Sprite(tex)
          sp.position.set(g.x * TILE, g.y * TILE)
          terrainLayer.addChild(sp)
        }
        // The HQ modular stack (one Middle_Floor per commits tier — §3.1).
        const floors = hqStack(L.hqFloors)
        for (const piece of floors) {
          const tex = texFor(piece.sheet)
          if (!tex) continue
          const sp = new PIXI.Sprite(tex)
          sp.anchor.set(0.5, 1)
          sp.position.set(32 * TILE, piece.bottomPx)
          sp.zIndex = piece.bottomPx - 1000 // building band behind props
          propLayer.addChild(sp)
        }
        buildProps(L.props)
      }

      function buildIsland(p: OutdoorCanvasProps) {
        const L = p.island
        if (!L) return
        const wpx = L.w * TILE
        const hpx = L.h * TILE
        // Water everywhere (tiling the real water tile), then the land disc
        // (grass) masked to R, sand ring, plaza dirt — all real pack pixels.
        const waterTex = texFor(VILLAGE_SHEET, V.water)
        if (waterTex) {
          const water = new PIXI.TilingSprite({ texture: waterTex, width: wpx, height: hpx })
          terrainLayer.addChild(water)
        }
        const sandTex = texFor(VILLAGE_SHEET, V.sand)
        if (sandTex) {
          const sand = new PIXI.TilingSprite({ texture: sandTex, width: wpx, height: hpx })
          const m = new PIXI.Graphics()
          m.circle(L.center.x * TILE, L.center.y * TILE, L.radius * TILE).fill(0xffffff)
          sand.mask = m
          terrainLayer.addChild(m)
          terrainLayer.addChild(sand)
        }
        const grassTex = texFor(VILLAGE_SHEET, V.grass)
        if (grassTex) {
          const grass = new PIXI.TilingSprite({ texture: grassTex, width: wpx, height: hpx })
          const m = new PIXI.Graphics()
          m.circle(L.center.x * TILE, L.center.y * TILE, (L.radius - 1.5) * TILE).fill(0xffffff)
          grass.mask = m
          terrainLayer.addChild(m)
          terrainLayer.addChild(grass)
        }
        const dirtTex = texFor(VILLAGE_SHEET, V.dirt)
        if (dirtTex) {
          const plaza = new PIXI.TilingSprite({ texture: dirtTex, width: wpx, height: hpx })
          const m = new PIXI.Graphics()
          m.circle(L.center.x * TILE, L.center.y * TILE, L.plazaRadius * TILE).fill(0xffffff)
          plaza.mask = m
          terrainLayer.addChild(m)
          terrainLayer.addChild(plaza)
          // Field plots: tilled dirt rectangles.
          for (const f of L.fields) {
            const patch = new PIXI.TilingSprite({
              texture: dirtTex,
              width: f.w * TILE,
              height: f.h * TILE,
            })
            patch.position.set(f.x * TILE, f.y * TILE)
            terrainLayer.addChild(patch)
          }
        }
        const pebbleTex = texFor(VILLAGE_SHEET, V.pebbles)
        if (pebbleTex) {
          for (const d of L.plazaDecals) {
            const sp = new PIXI.Sprite(pebbleTex)
            sp.position.set(d.x * TILE, d.y * TILE)
            terrainLayer.addChild(sp)
          }
        }
        // Crops: per-plot growth-stage strip cuts (REAL census data — the
        // aggregate work_completed tier until E2 sector emitters land).
        for (const f of L.fields) {
          const sheet = sheets.get(f.cropSheet)
          if (!sheet) continue
          const cut = cropCut(sheet.source.height, f.stage)
          const tex = texFor(f.cropSheet, cut)
          if (!tex) continue
          for (let cy = 0; cy < 2; cy++) {
            for (let cx = 0; cx < 3; cx++) {
              const sp = new PIXI.Sprite(tex)
              sp.anchor.set(0.5, 1)
              const bx = (f.x + 0.7 + cx * 1.2) * TILE
              const by = (f.y + 1.2 + cy * 1.4) * TILE
              sp.position.set(bx, by)
              sp.zIndex = by
              propLayer.addChild(sp)
            }
          }
        }
        buildProps(L.props)
      }

      function buildProps(propsList: Array<{
        id: string; sheet: string; cut?: SpriteCut; x: number; y: number
        ghost?: boolean; hitOnly?: boolean
      }>) {
        for (const pr of propsList) {
          if (pr.hitOnly) continue // hit/inspect region — never drawn
          const tex = texFor(pr.sheet, pr.cut)
          if (!tex) continue // placeholder path drawn in draw() — stays loud
          const sp = new PIXI.Sprite(tex)
          sp.anchor.set(0.5, 1)
          const by = pr.y * TILE + 4
          sp.position.set(pr.x * TILE, by)
          sp.zIndex = by
          if (pr.ghost) sp.alpha = 0.45
          propLayer.addChild(sp)
        }
      }

      /** Props whose sheet failed to resolve — drawn as loud placeholders. */
      function placeholderProps(p: OutdoorCanvasProps) {
        propG.clear()
        const list = p.scene === 'street' ? p.street?.props : p.island?.props
        for (const pr of list ?? []) {
          if (pr.hitOnly) continue
          if (texFor(pr.sheet, pr.cut)) continue
          const w = (pr.cut ? pr.cut.w : TILE) * 1
          const h = (pr.cut ? pr.cut.h : TILE * 2) * 1
          const x = pr.x * TILE - w / 2
          const y = pr.y * TILE + 4 - h
          propG.rect(x, y, w, h).fill({ color: 0x39415a, alpha: 0.7 })
          propG.rect(x, y, w, h).stroke({ width: 2, color: 0x9aa4bd })
        }
      }

      function drawStreetDynamics(p: OutdoorCanvasProps, bucket: DayBucket) {
        const L = p.street
        if (!L) return
        const slugs = Object.keys(p.officers).sort()
        // Lit windows: ONE per officer with a live verb; others dim at night.
        for (const wnd of L.windows) {
          const slug = slugs[wnd.officerIdx]
          const live = slug ? Boolean(p.officers[slug]?.present && p.officers[slug]?.verb) : false
          if (live) {
            dynG.rect(wnd.px, wnd.py, wnd.w, wnd.h).fill({ color: 0xffc35c, alpha: 0.85 })
          } else if (bucket === 'night' || bucket === 'dusk') {
            dynG.rect(wnd.px, wnd.py, wnd.w, wnd.h).fill({ color: 0x1a2030, alpha: 0.8 })
          }
        }
        // Badge motes at the facade: drift while the verb is live (seeded),
        // stand still when the activity TTL expired. Same predicate as Z2.
        for (const m of L.motes) {
          const pres = p.officers[m.slug]
          const live = Boolean(pres?.present && pres?.verb)
          const x = live ? motePatrolX(m.x, m.span, m.phase, p.tick) : m.x
          const px = x * TILE
          const py = m.y * TILE
          dynG.rect(px - 3, py - 10, 6, 10).fill({ color: moteColor(fnv1a(m.slug)), alpha: pres?.present ? 1 : 0.4 })
          dynG.rect(px - 3, py - 10, 6, 10).stroke({ width: 1, color: 0x0c0e12 })
        }
        // Night: warm lamp pools (additive circles) — §2 lighting law.
        if (bucket === 'night' || bucket === 'dusk') {
          for (const lt of L.lampTiles) {
            fxG.circle(lt.x * TILE, lt.y * TILE - 4, 28).fill({ color: 0xffb050, alpha: 0.15 })
          }
        }
      }

      function drawIslandDynamics(p: OutdoorCanvasProps, bucket: DayBucket) {
        const L = p.island
        if (!L) return
        for (const m of L.motes) {
          const pres = p.officers[m.slug]
          const px = m.x * TILE
          const py = m.y * TILE
          dynG.rect(px - 2, py - 4, 4, 4).fill({ color: moteColor(fnv1a(m.slug)), alpha: pres?.present ? 1 : 0.4 })
        }
        if (bucket === 'night' || bucket === 'dusk') {
          // Cottage windows glow warm; the dark beacon stays DARK (§3.2 —
          // never give the beacon a night light; the zero is the point).
          for (const pr of L.props) {
            if (!pr.id.startsWith('island:house:') && pr.id !== 'island:hq') continue
            fxG.rect(pr.x * TILE - 8, pr.y * TILE - 20, 6, 6).fill({ color: 0xffc35c, alpha: 0.8 })
            fxG.rect(pr.x * TILE + 4, pr.y * TILE - 20, 6, 6).fill({ color: 0xffc35c, alpha: 0.8 })
          }
        }
      }

      function draw(p: OutdoorCanvasProps) {
        const L = p.scene === 'street' ? p.street : p.island
        if (!L) return
        // Rebuild statics when the scene/layout identity changes (growth or
        // roster changed → the client rebuilt the layout object).
        const key = `${p.scene}:${(L as { w: number; h: number }).w}x${(L as { w: number; h: number }).h}:` +
          `${p.scene === 'street' ? p.street?.props.length : p.island?.props.length}:` +
          `${p.scene === 'street' ? streetFloorsKey(p) : islandKey(p)}`
        if (key !== builtKey) {
          builtKey = key
          clearStatics()
          if (p.scene === 'street') buildStreet(p)
          else buildIsland(p)
        }

        const vw = app.renderer.width
        const vh = app.renderer.height
        const z = p.camera.z
        // Outdoor scenes render at their own scale: z is the SCENE SELECTOR
        // (§10.2 adapted); inside a scene we keep a legible fixed zoom.
        const sceneScale = p.scene === 'street' ? 2 : 1
        world.scale.set(sceneScale)
        world.position.set(
          vw / 2 - p.camera.x * TILE * sceneScale,
          vh / 2 - p.camera.y * TILE * sceneScale
        )
        void z

        // Terrain placeholder when textures are absent (loud badge already
        // raised): flat fill + grid — visibly placeholder, never invisible.
        terrainG.clear()
        if (terrainLayer.children.length === 0) {
          const wpx = (L as { w: number }).w * TILE
          const hpx = (L as { h: number }).h * TILE
          terrainG.rect(0, 0, wpx, hpx).fill(0x1d212b)
          for (let gx = 0; gx <= wpx; gx += TILE * 4) {
            terrainG.moveTo(gx, 0).lineTo(gx, hpx).stroke({ width: 1, color: 0x232836 })
          }
          for (let gy = 0; gy <= hpx; gy += TILE * 4) {
            terrainG.moveTo(0, gy).lineTo(wpx, gy).stroke({ width: 1, color: 0x232836 })
          }
        }

        placeholderProps(p)

        dynG.clear()
        fxG.clear()
        const bucket = bucketOf(p.clockHour)
        if (p.scene === 'street') drawStreetDynamics(p, bucket)
        else drawIslandDynamics(p, bucket)

        // Ambient tint (dawn/dusk/night — ambience only, never state).
        const amb = AMBIENT[bucket]
        const wpx = (L as { w: number }).w * TILE
        const hpx = (L as { h: number }).h * TILE
        if (amb) fxG.rect(0, 0, wpx, hpx).fill({ color: amb.color, alpha: amb.alpha })
        // Killswitch: red wash (reserved hue; dual-coded with the DOM
        // banner; the client stops advancing the tick — frozen mid-drift).
        if (p.killswitch) fxG.rect(0, 0, wpx, hpx).fill({ color: 0xcc2222, alpha: 0.14 })
      }

      function streetFloorsKey(p: OutdoorCanvasProps): string {
        return `f${p.street?.hqFloors ?? 0}:${p.street?.motes.length ?? 0}`
      }
      function islandKey(p: OutdoorCanvasProps): string {
        return `r${p.island?.radius ?? 0}:${p.island?.fields.length ?? 0}`
      }

      function hitTarget(ev: MouseEvent): OutdoorTarget | null {
        const rect = app.canvas.getBoundingClientRect()
        const p = propsRef.current
        const sceneScale = p.scene === 'street' ? 2 : 1
        const wx = (ev.clientX - rect.left - app.renderer.width / 2) / (TILE * sceneScale) + p.camera.x
        const wy = (ev.clientY - rect.top - app.renderer.height / 2) / (TILE * sceneScale) + p.camera.y
        const L = p.scene === 'street' ? p.street : p.island
        if (!L) return null
        // Motes first (small, on top).
        for (const m of L.motes as Array<{ slug: string; x: number; y: number }>) {
          if (Math.abs(wx - m.x) < 0.8 && Math.abs(wy - m.y + 0.4) < 1) {
            return { kind: 'officer', id: m.slug }
          }
        }
        // Props by anchor box (wider for buildings via cut width).
        const list = (p.scene === 'street' ? p.street?.props : p.island?.props) ?? []
        let best: { id: string; d: number } | null = null
        for (const pr of list) {
          const halfW = Math.max(1, (pr.cut ? pr.cut.w : 24) / TILE / 2)
          const hTiles = Math.max(1.2, (pr.cut ? pr.cut.h : 32) / TILE)
          if (Math.abs(wx - pr.x) <= halfW && wy <= pr.y + 0.6 && wy >= pr.y - hTiles) {
            const d = Math.abs(wx - pr.x) + Math.abs(wy - pr.y)
            if (!best || d < best.d) best = { id: pr.id, d }
          }
        }
        if (best) return { kind: 'station', id: best.id }
        // Street: the HQ stack face counts as the HQ door's building.
        if (p.scene === 'street' && Math.abs(wx - 32) <= 3.5 && wy <= 20 && wy >= 20 - 14) {
          return { kind: 'station', id: 'street:hq:door' }
        }
        // Island: the HQ cottage already covers its box via props.
        return null
      }

      const onClick = (ev: MouseEvent) => propsRef.current.onPrimary(hitTarget(ev))
      const onContext = (ev: MouseEvent) => {
        ev.preventDefault()
        propsRef.current.onSecondary(hitTarget(ev))
      }
      app.canvas.addEventListener('click', onClick)
      app.canvas.addEventListener('contextmenu', onContext)

      handlesRef.current = {
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
      console.error('[world/outdoor] renderer boot failed — DOM badge raised:', err)
      propsRef.current.onIssues?.([
        `outdoor renderer failed: ${err instanceof Error ? err.message : String(err)}`,
      ])
    })
    return () => {
      cancelled = true
      handlesRef.current?.destroy()
      handlesRef.current = null
    }
    // Scene changes remount this component (key= in the client shell).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    handlesRef.current?.draw(props)
  }, [props])

  return (
    <div ref={hostRef} className="absolute inset-0 overflow-hidden" data-world-outdoor-canvas />
  )
}
