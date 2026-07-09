'use client'

/**
 * EngineCanvas — the ONE continuous world (T1, spec v2 D1/D3).
 *
 * Replaces the three-scene renderer (wardroom/street/island scene swap —
 * supersession #5: the scenes enum is retired). One PixiJS stage renders
 * the whole archipelago canvas from:
 *  - the chunked procedural base field (lib/world/chunks.ts) over the
 *    authored geography (lib/world/world-geo.ts) — coastline autotiled via
 *    the shore-mask table (foam strokes oriented per variant; same legal
 *    class as blob shadows/lamp pools: procedural pass, no invented art);
 *  - era×rung-resolved buildings (lib/world/world-buildings.ts) — interim
 *    pack cuts, visibly-placeholder rects when a sheet is missing (LOUD);
 *  - product isles + reef-buoys (retired/instance-test lanes — honest
 *    markers) + mist pockets over reserved anchor slots (grey-unmeasured
 *    made geographic);
 *  - LOD rules (lib/world/lod.ts): coast/archipelago collapse buildings to
 *    seeded footprint blocks, cull props/officers, aggregate light masses —
 *    the dark lighthouse survives every zoom (honest zero);
 *  - roof-cutaway IN PLACE at close zoom (single-active; roofAlpha fades
 *    the roof sprite; a simple interior floor + present officers reveal
 *    beneath — the world keeps ticking around the open room);
 *  - the weather layer bound to REAL signals (lib/world/weather.ts) with
 *    deterministic seeded rain, and day/night tint from the server-stamped
 *    snapshot clock.
 *
 * Doctrine unchanged from the sibling renderers: pure renderer, no writes,
 * no wall clock, no unseeded RNG, no world-space text (DOM labels), CSP
 * eval-free boot, loud failure via onIssues.
 */
import { useEffect, useRef } from 'react'
import type { Container, Graphics, Sprite, Texture } from 'pixi.js'
import type { OfficerPresence } from '@/lib/world/types'
import { TILE } from '@/lib/world/layout'
import { fnv1a } from '@/lib/world/hash'
import type { SpriteCut, WorldAssetManifest } from '@/lib/world/sprites'
import {
  F,
  FARM_SHEET,
  STREET_PROPS,
  V,
  VILLAGE_SHEET,
  bucketOf,
  moteColor,
  resolveOutdoorSprites,
  type DayBucket,
} from '@/lib/world/sprites-outdoor'
import { baseTile, shoreMask, shoreVariant } from '@/lib/world/chunks'
import type { WorldGeo } from '@/lib/world/world-geo'
import type { WorldBuilding } from '@/lib/world/world-buildings'
import {
  LOD_RULES,
  lodTier,
  roofAlpha,
  type CutawayState,
  type EngineCamera,
} from '@/lib/world/lod'
import type { WeatherState } from '@/lib/world/weather'
import { rainDrops } from '@/lib/world/weather'
import type { WorldResolution } from '@/lib/world/era-engine'

const AMBIENT: Record<DayBucket, { color: number; alpha: number } | null> = {
  dawn: { color: 0xffe8d0, alpha: 0.06 },
  day: null,
  dusk: { color: 0xffc890, alpha: 0.1 },
  night: { color: 0x2a3560, alpha: 0.22 },
}

export interface EngineTarget {
  kind: 'officer' | 'building' | 'lane' | 'mailbox' | 'ground'
  id: string
}

export interface EngineCanvasProps {
  geo: WorldGeo
  buildings: WorldBuilding[]
  resolution: WorldResolution | null
  officers: Record<string, OfficerPresence>
  camera: EngineCamera
  cutaway: CutawayState
  weather: WeatherState
  tick: number
  killswitch: boolean
  clockHour: number | null
  onPrimary: (target: EngineTarget | null) => void
  onSecondary: (target: EngineTarget | null) => void
  onIssues?: (issues: string[]) => void
}

interface PixiHandles {
  destroy: () => void
  draw: (props: EngineCanvasProps) => void
}

/** Interim sprite-hint → verified pack cut (visibly interim where noted). */
const HINT_CUT: Record<string, { sheet: string; cut?: SpriteCut } | null> = {
  great_house: { sheet: VILLAGE_SHEET, cut: V.hq },
  cottage: null, // seeded roof palette — resolved per building id
  library: { sheet: FARM_SHEET, cut: F.stall },
  workshop: { sheet: FARM_SHEET, cut: F.furnace },
  well: { sheet: FARM_SHEET, cut: F.well },
  observatory: { sheet: VILLAGE_SHEET, cut: V.signpost },
  barn: { sheet: FARM_SHEET, cut: F.barn },
  law_plot: { sheet: VILLAGE_SHEET, cut: V.lawPlot },
  warehouse: { sheet: FARM_SHEET, cut: F.kilnShed },
  hut: { sheet: VILLAGE_SHEET, cut: V.cottage[1] },
  lighthouse: { sheet: FARM_SHEET, cut: F.silo }, // interim beacon (precedent)
  silo: { sheet: FARM_SHEET, cut: F.silo },
  stall: { sheet: FARM_SHEET, cut: F.crate },
  firepit: { sheet: VILLAGE_SHEET, cut: V.rock },
  water_store: { sheet: FARM_SHEET, cut: F.crate2 },
  pen: { sheet: VILLAGE_SHEET, cut: V.hedge },
  mailbox: { sheet: STREET_PROPS.mailbox },
}

export default function EngineCanvas(props: EngineCanvasProps) {
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
        background: 0x0e1a26, // deep sea beyond the canvas — the world is unbounded
        resizeTo: hostRef.current,
        antialias: false,
        roundPixels: true,
      })
      if (cancelled || !hostRef.current) {
        app.destroy(true)
        return
      }
      hostRef.current.appendChild(app.canvas)

      // ── textures: manifest-bound, loud on every gap ─────────────────────
      const issues: string[] = []
      const sheets = new Map<string, Texture>()
      try {
        const res = await fetch('/world-assets/manifest.json')
        if (!res.ok) throw new Error(`manifest HTTP ${res.status}`)
        const manifest = (await res.json()) as WorldAssetManifest
        const resolved = resolveOutdoorSprites(manifest, 'island')
        for (const id of resolved.missing) {
          issues.push(`missing sheet: ${id}`)
          console.error('[world/engine] sheet missing/invalid — placeholder fallback:', id)
        }
        const loaded = await Promise.all(
          Object.entries(resolved.urls).map(async ([id, url]) => {
            try {
              return [id, (await PIXI.Assets.load(url)) as Texture] as const
            } catch (err) {
              issues.push(`texture load failed: ${id}`)
              console.error('[world/engine] texture load failed:', id, err)
              return [id, null] as const
            }
          })
        )
        for (const [id, tex] of loaded) if (tex) sheets.set(id, tex)
      } catch (err) {
        issues.push('asset manifest unavailable — placeholder mode')
        console.error('[world/engine] manifest fetch failed — placeholder mode:', err)
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
      const seaLayer: Container = new PIXI.Container()
      world.addChild(seaLayer)
      const terrainLayer: Container = new PIXI.Container()
      world.addChild(terrainLayer)
      const shoreG: Graphics = new PIXI.Graphics()
      world.addChild(shoreG)
      const propLayer: Container = new PIXI.Container()
      propLayer.sortableChildren = true
      world.addChild(propLayer)
      const interiorG: Graphics = new PIXI.Graphics() // cutaway floors/desks
      world.addChild(interiorG)
      const placeholderG: Graphics = new PIXI.Graphics()
      world.addChild(placeholderG)
      const dynG: Graphics = new PIXI.Graphics() // motes, buoys, light masses
      world.addChild(dynG)
      const fxG: Graphics = new PIXI.Graphics() // world-space tint, fog, wash
      world.addChild(fxG)
      const weatherG: Graphics = new PIXI.Graphics() // SCREEN-space particles
      app.stage.addChild(weatherG)

      /** Building sprites by id (cutaway alpha is applied per frame). */
      const buildingSprites = new Map<string, Sprite>()
      let builtKey = ''

      function clearStatics() {
        seaLayer.removeChildren().forEach((c) => c.destroy())
        terrainLayer.removeChildren().forEach((c) => c.destroy())
        propLayer.removeChildren().forEach((c) => c.destroy())
        buildingSprites.clear()
        shoreG.clear()
      }

      /** Foam strokes oriented per shore autotile variant (procedural pass). */
      function drawShore(geo: WorldGeo) {
        shoreG.clear()
        for (const isl of geo.islands) {
          if (isl.r <= 0) continue
          const pad = 3
          for (let ty = isl.cy - isl.r - pad; ty <= isl.cy + isl.r + pad; ty++) {
            for (let tx = isl.cx - isl.r - pad; tx <= isl.cx + isl.r + pad; tx++) {
              const mask = shoreMask(tx, ty, geo)
              if (mask === 0) continue
              const v = shoreVariant(mask)
              const px = tx * TILE
              const py = ty * TILE
              const seed = fnv1a(`foam:${tx},${ty}`)
              const off = 3 + (seed % 5)
              const foam = { width: 2, color: 0xdce9f2, alpha: 0.5 }
              if (v === 'edge_n' || v.startsWith('corner_n') || v === 'cove') {
                shoreG.moveTo(px + 2, py + 3).lineTo(px + off + 6, py + 3).stroke(foam)
              }
              if (v === 'edge_s' || v.startsWith('corner_s') || v === 'cove') {
                shoreG.moveTo(px + 2, py + TILE - 3).lineTo(px + off + 6, py + TILE - 3).stroke(foam)
              }
              if (v === 'edge_e' || v.endsWith('e') || v === 'channel_ew') {
                shoreG.moveTo(px + TILE - 3, py + 2).lineTo(px + TILE - 3, py + off + 4).stroke(foam)
              }
              if (v === 'edge_w' || v.endsWith('w') || v === 'channel_ew') {
                shoreG.moveTo(px + 3, py + 2).lineTo(px + 3, py + off + 4).stroke(foam)
              }
              if (v === 'channel_ns') {
                shoreG.moveTo(px + 2, py + 8).lineTo(px + 10, py + 8).stroke(foam)
              }
            }
          }
        }
      }

      function buildTerrain(p: EngineCanvasProps) {
        const geo = p.geo
        const cw = geo.canvas.w * TILE
        const ch = geo.canvas.h * TILE
        const waterTex = texFor(VILLAGE_SHEET, V.water)
        if (waterTex) {
          const water = new PIXI.TilingSprite({ texture: waterTex, width: cw, height: ch })
          seaLayer.addChild(water)
        } else {
          const g = new PIXI.Graphics()
          g.rect(0, 0, cw, ch).fill(0x14283a)
          seaLayer.addChild(g)
        }
        for (const isl of geo.islands) {
          if (isl.r <= 0) continue
          const sandTex = texFor(VILLAGE_SHEET, V.sand)
          if (sandTex) {
            const sand = new PIXI.TilingSprite({ texture: sandTex, width: cw, height: ch })
            const m = new PIXI.Graphics()
            m.circle(isl.cx * TILE, isl.cy * TILE, isl.r * TILE).fill(0xffffff)
            sand.mask = m
            terrainLayer.addChild(m)
            terrainLayer.addChild(sand)
          }
          const grassTex = texFor(VILLAGE_SHEET, V.grass)
          if (grassTex) {
            const grass = new PIXI.TilingSprite({ texture: grassTex, width: cw, height: ch })
            const m = new PIXI.Graphics()
            m.circle(isl.cx * TILE, isl.cy * TILE, Math.max(1, isl.r - 1.2) * TILE).fill(0xffffff)
            grass.mask = m
            terrainLayer.addChild(m)
            terrainLayer.addChild(grass)
          }
          // forest ring: tree rows seeded between clearR and r (base field law)
          const treeTexA = texFor(VILLAGE_SHEET, V.treeRow)
          const treeTexB = texFor(VILLAGE_SHEET, V.treeRow2)
          if (treeTexA || treeTexB) {
            const count = Math.max(6, Math.round(isl.r * 0.9))
            for (let i = 0; i < count; i++) {
              const h = fnv1a(`${isl.id}:forest:${i}`)
              const a = ((h % 360) * Math.PI) / 180
              const band = Math.max(1, isl.r - isl.clearR - 2)
              const rr = isl.clearR + 1 + ((h >>> 9) % band)
              const tx = Math.round(isl.cx + Math.cos(a) * rr)
              const ty = Math.round(isl.cy + Math.sin(a) * rr)
              if (baseTile(tx, ty, geo) !== 'forest') continue
              const tex = (h & 1) === 0 ? treeTexA : treeTexB
              if (!tex) continue
              const sp = new PIXI.Sprite(tex)
              sp.anchor.set(0.5, 1)
              sp.position.set(tx * TILE, ty * TILE)
              sp.zIndex = ty * TILE - 2000 // canopy band behind buildings
              propLayer.addChild(sp)
            }
          }
        }
        // road: dirt tile per carved spine tile
        const dirtTex = texFor(VILLAGE_SHEET, V.dirt)
        if (dirtTex) {
          for (const key of p.geo.roadTiles) {
            const [xs, ys] = key.split(',')
            const sp = new PIXI.Sprite(dirtTex)
            sp.position.set(Number(xs) * TILE, Number(ys) * TILE)
            terrainLayer.addChild(sp)
          }
        }
        // quay: dock planks along the quay band
        const dockTex = texFor(VILLAGE_SHEET, V.dock)
        if (dockTex) {
          for (let dx = -10; dx <= 10; dx += 3) {
            const sp = new PIXI.Sprite(dockTex)
            sp.position.set((geo.quayCenter.x + dx) * TILE, (geo.quayCenter.y - 1) * TILE)
            terrainLayer.addChild(sp)
          }
        }
        // pier below the road mouth
        const pierTex = texFor(VILLAGE_SHEET, V.pier)
        if (pierTex) {
          const sp = new PIXI.Sprite(pierTex)
          sp.position.set((geo.quayCenter.x - 1) * TILE, geo.quayCenter.y * TILE)
          terrainLayer.addChild(sp)
        }
        drawShore(geo)
      }

      function buildBuildings(p: EngineCanvasProps) {
        for (const b of p.buildings) {
          const hint =
            b.sprite === 'cottage'
              ? { sheet: VILLAGE_SHEET, cut: V.cottage[fnv1a(`${b.id}:roof`) % V.cottage.length] }
              : HINT_CUT[b.sprite]
          const tex = hint ? texFor(hint.sheet, hint.cut) : null
          if (!tex) continue // loud placeholder rect drawn per-frame
          const sp = new PIXI.Sprite(tex)
          sp.anchor.set(0.5, 1)
          const bx = (b.x + b.w / 2) * TILE
          const by = (b.y + b.h) * TILE
          sp.position.set(bx, by)
          sp.zIndex = by
          buildingSprites.set(b.id, sp)
          propLayer.addChild(sp)
        }
        // the mailbox at the crossroads (read-only Captain surface)
        const mailTex = texFor(STREET_PROPS.mailbox)
        if (mailTex) {
          const sp = new PIXI.Sprite(mailTex)
          sp.anchor.set(0.5, 1)
          sp.position.set((p.geo.crossroads.x + 1.2) * TILE, (p.geo.crossroads.y + 0.6) * TILE)
          sp.zIndex = (p.geo.crossroads.y + 0.6) * TILE
          propLayer.addChild(sp)
        }
      }

      function buildFootprints(p: EngineCanvasProps) {
        // coast/archipelago LOD: seeded footprint blocks from the SAME
        // building list (silhouettes; light mass drawn in dynamics).
        const g = new PIXI.Graphics()
        for (const b of p.buildings) {
          const h = fnv1a(`fp:${b.id}`)
          const c = 0x2c3242 + ((h % 5) << 3)
          g.rect(b.x * TILE, b.y * TILE, b.w * TILE, b.h * TILE).fill({ color: c, alpha: 0.95 })
        }
        // the lighthouse silhouette survives every zoom — honest-zero anomaly
        const lh = p.buildings.find((b) => b.element === 'lighthouse')
        if (lh) {
          g.rect((lh.x + 1) * TILE, (lh.y - 2) * TILE, TILE, 2 * TILE).fill({ color: 0x1c2030 })
        }
        terrainLayer.addChild(g)
      }

      function staticsKey(p: EngineCanvasProps): string {
        const tier = lodTier(p.camera.z)
        const fp = LOD_RULES[tier].buildingsAsFootprints ? 'fp' : 'full'
        const geoKey = p.geo.islands.map((i) => `${i.id}:${i.r}`).join('|')
        const bKey = p.buildings.map((b) => `${b.id}:${b.rungName}`).join('|')
        return `${fp}·${geoKey}·${bKey}`
      }

      function rebuildStatics(p: EngineCanvasProps) {
        clearStatics()
        buildTerrain(p)
        if (LOD_RULES[lodTier(p.camera.z)].buildingsAsFootprints) buildFootprints(p)
        else buildBuildings(p)
      }

      function placeholderBuildings(p: EngineCanvasProps) {
        placeholderG.clear()
        if (LOD_RULES[lodTier(p.camera.z)].buildingsAsFootprints) return
        for (const b of p.buildings) {
          if (buildingSprites.has(b.id)) continue
          placeholderG
            .rect(b.x * TILE, b.y * TILE, b.w * TILE, b.h * TILE)
            .fill({ color: 0x39415a, alpha: 0.7 })
          placeholderG
            .rect(b.x * TILE, b.y * TILE, b.w * TILE, b.h * TILE)
            .stroke({ width: 2, color: 0x9aa4bd })
        }
      }

      /** Officer world positions: present officers stand at the Great House
       * yard (seeded slots); on cutaway they render INSIDE at desks. */
      function officerPositions(p: EngineCanvasProps): Array<{
        slug: string
        x: number
        y: number
        inside: boolean
      }> {
        const gh = p.buildings.find((b) => b.element === 'great_house')
        if (!gh) return []
        const open = p.cutaway.openId === gh.id
        const slugs = Object.keys(p.officers).sort()
        return slugs.map((slug, i) => {
          const h = fnv1a(`officer:${slug}`)
          if (open) {
            const col = i % 3
            const row = Math.floor(i / 3)
            return {
              slug,
              x: gh.x + 1 + col * ((gh.w - 2) / 2.5),
              y: gh.y + 1.6 + row * 1.6,
              inside: true,
            }
          }
          return {
            slug,
            x: gh.x + 0.5 + ((h >>> 4) % (gh.w * 2)) / 2,
            y: gh.y + gh.h + 1 + (i % 2),
            inside: false,
          }
        })
      }

      function drawDynamics(p: EngineCanvasProps) {
        dynG.clear()
        interiorG.clear()
        const tier = lodTier(p.camera.z)
        const rules = LOD_RULES[tier]
        const bucket = bucketOf(p.clockHour)

        // cutaway: roof alpha per building; interior floor under the fade
        for (const b of p.buildings) {
          const sp = buildingSprites.get(b.id)
          const a = rules.cutawayEligible ? roofAlpha(p.cutaway, b.id, p.tick) : 1
          if (sp) sp.alpha = a
          if (a < 0.95 && b.interior) {
            // simple interior: warm plank floor + wall caps + desk blocks —
            // the officers inside are drawn below (revealed mid-verb)
            interiorG
              .rect(b.x * TILE + 2, b.y * TILE + 2, b.w * TILE - 4, b.h * TILE - 4)
              .fill({ color: 0x8a6a48, alpha: 0.95 })
            interiorG
              .rect(b.x * TILE + 2, b.y * TILE + 2, b.w * TILE - 4, 4)
              .fill({ color: 0x4c3826, alpha: 0.95 })
            const desks = Math.min(4, Math.max(1, Math.floor(b.w / 2)))
            for (let i = 0; i < desks; i++) {
              interiorG
                .rect((b.x + 1 + i * 1.4) * TILE, (b.y + 1) * TILE, 14, 8)
                .fill({ color: 0x5c452e, alpha: 0.95 })
            }
          }
          // pending rung: construction scaffold chip (visible-work seam —
          // the full crewed pipeline is T2's site system)
          if (b.pending && !rules.buildingsAsFootprints) {
            dynG
              .rect(b.x * TILE, (b.y - 0.4) * TILE, 10, 6)
              .fill({ color: 0xd9a441, alpha: 0.9 })
          }
        }

        // officers (motes; inside on cutaway) — culled at coast/archipelago
        if (rules.officers) {
          for (const o of officerPositions(p)) {
            const pres = p.officers[o.slug]
            const live = Boolean(pres?.present)
            dynG
              .rect(o.x * TILE - 2, o.y * TILE - 8, 5, 8)
              .fill({ color: moteColor(fnv1a(o.slug)), alpha: live ? 1 : 0.35 })
            dynG.rect(o.x * TILE - 2, o.y * TILE - 8, 5, 8).stroke({ width: 1, color: 0x0c0e12 })
          }
        }

        // lane sites: buoys + isle docks/warehouses + mist pockets
        for (const site of p.geo.laneSites) {
          const px = site.cx * TILE
          const py = site.cy * TILE
          if (site.render === 'reef_buoy') {
            dynG.circle(px, py, 5).fill({ color: 0xc63228 })
            dynG.circle(px, py, 5).stroke({ width: 1, color: 0x35110d })
            dynG.circle(px, py + 8, 7).stroke({ width: 1, color: 0x88a5b8, alpha: 0.5 })
          } else if (site.render === 'mist_reserved') {
            const h = fnv1a(`mist:${site.slot}`)
            for (let i = 0; i < 26; i++) {
              const a = (((h >>> (i % 24)) + i * 37) % 360) * (Math.PI / 180)
              const rr = (fnv1a(`mist:${site.slot}:${i}`) % 60) + 12
              dynG
                .circle(px + Math.cos(a) * rr, py + Math.sin(a) * rr, 3)
                .fill({ color: 0x9aa4ad, alpha: 0.18 })
            }
            dynG.circle(px, py, 4).fill({ color: 0x8b949c }) // grey buoy (dual-code)
          } else if (site.render === 'isle') {
            // dock jetty marker; warehouses at ring r1
            dynG.rect(px - 10, py + (site.cy < 100 ? 12 : -14), 20, 5).fill({ color: 0x6b4d30 })
            if (site.ringRung >= 2 && !rules.buildingsAsFootprints) {
              dynG.rect(px - 8, py - 6, 14, 10).fill({ color: 0x7d5a38 })
              dynG.rect(px - 8, py - 10, 14, 5).fill({ color: 0x4c3826 })
            }
          }
        }

        // light masses (dusk/night; and always at far LOD as state lights)
        const dark = bucket === 'night' || bucket === 'dusk'
        if (rules.lightMassAggregate) {
          // per-isle presence light; main island glow scaled to live officers
          const live = Object.values(p.officers).filter((o) => o.present).length
          const main = p.geo.islands.find((i) => i.id === 'main')
          if (main && live > 0) {
            fxG
              .circle(main.cx * TILE, main.cy * TILE, (10 + live * 4) * 2)
              .fill({ color: 0xffc35c, alpha: dark ? 0.16 : 0.08 })
          }
          for (const site of p.geo.laneSites) {
            if (site.render !== 'isle') continue
            fxG
              .circle(site.cx * TILE, site.cy * TILE, 18)
              .fill({ color: 0xffc35c, alpha: dark ? 0.14 : 0.06 })
          }
        } else if (dark) {
          for (const b of p.buildings) {
            if (!b.interior) continue
            fxG
              .rect((b.x + 0.6) * TILE, (b.y + 1) * TILE, 5, 5)
              .fill({ color: 0xffc35c, alpha: 0.8 })
          }
        }
        // the lighthouse lamp: LIT only when cells_graduated > 0 (honest 0)
        const lamp = p.resolution?.elements.lighthouse_lamp
        const lh = p.buildings.find((b) => b.element === 'lighthouse')
        if (lh && lamp && lamp.rungName === 'lit') {
          fxG
            .circle((lh.x + lh.w / 2) * TILE, lh.y * TILE, 40)
            .fill({ color: 0xffe9a8, alpha: 0.25 })
        }
      }

      function drawWeather(p: EngineCanvasProps, bucket: DayBucket) {
        weatherG.clear()
        fxG.clear() // fx redrawn each frame (light masses re-added by dynamics)
        const vw = app.renderer.width
        const vh = app.renderer.height
        const kind = p.weather.kind
        // fog: horizon band + global haze (dithered, never full opaque wash)
        if (kind === 'fog') {
          for (let i = 0; i < 140; i++) {
            const h = fnv1a(`fogdot:${i}`)
            weatherG
              .circle(h % vw, (h >>> 12) % vh, 6 + (h % 5))
              .fill({ color: 0xa9b2ba, alpha: 0.07 })
          }
          weatherG.rect(0, vh * 0.78, vw, vh * 0.22).fill({ color: 0x9aa4ad, alpha: 0.18 })
        }
        // rain/storm: deterministic seeded drops (pure f(tick))
        if (kind === 'rain' || kind === 'storm') {
          const drops = rainDrops(p.tick, kind === 'storm' ? 160 : 80, vw, vh)
          for (const d of drops) {
            weatherG
              .moveTo(d.x, d.y)
              .lineTo(d.x - 2, d.y + d.len * 3)
              .stroke({ width: 1, color: 0xb8cbe0, alpha: kind === 'storm' ? 0.6 : 0.4 })
          }
          weatherG.rect(0, 0, vw, vh).fill({ color: 0x1a2230, alpha: kind === 'storm' ? 0.28 : 0.12 })
        }
        // ambient day/night tint (world-space, from the server-stamped clock)
        const amb = AMBIENT[bucket]
        const cw = p.geo.canvas.w * TILE
        const ch = p.geo.canvas.h * TILE
        if (amb) fxG.rect(0, 0, cw, ch).fill({ color: amb.color, alpha: amb.alpha })
        // killswitch red wash (reserved hue; dual-coded with the DOM banner)
        if (p.killswitch) fxG.rect(0, 0, cw, ch).fill({ color: 0xcc2222, alpha: 0.14 })
      }

      function draw(p: EngineCanvasProps) {
        const key = staticsKey(p)
        if (key !== builtKey) {
          builtKey = key
          rebuildStatics(p)
        }
        const vw = app.renderer.width
        const vh = app.renderer.height
        const s = p.camera.z // continuous zoom = world scale (16px tiles ×z)
        world.scale.set(s)
        world.position.set(
          vw / 2 - p.camera.x * TILE * s,
          vh / 2 - p.camera.y * TILE * s
        )
        placeholderBuildings(p)
        const bucket = bucketOf(p.clockHour)
        drawWeather(p, bucket) // clears fxG first
        drawDynamics(p) // then dynamics adds light masses onto fxG
      }

      function hitTarget(ev: MouseEvent): EngineTarget | null {
        const rect = app.canvas.getBoundingClientRect()
        const p = propsRef.current
        const s = p.camera.z
        const wx = (ev.clientX - rect.left - app.renderer.width / 2) / (TILE * s) + p.camera.x
        const wy = (ev.clientY - rect.top - app.renderer.height / 2) / (TILE * s) + p.camera.y
        // officers first (small, on top)
        if (LOD_RULES[lodTier(s)].officers) {
          for (const o of officerPositions(p)) {
            if (Math.abs(wx - o.x) < 0.8 && Math.abs(wy - o.y + 0.3) < 1) {
              return { kind: 'officer', id: o.slug }
            }
          }
        }
        // the mailbox (crossroads)
        if (
          Math.abs(wx - (p.geo.crossroads.x + 1.2)) < 1.2 &&
          Math.abs(wy - p.geo.crossroads.y) < 1.6
        ) {
          return { kind: 'mailbox', id: 'mailbox' }
        }
        // buildings by bbox (footprints hit the same boxes at far LOD)
        for (const b of p.buildings) {
          if (wx >= b.x - 0.3 && wx <= b.x + b.w + 0.3 && wy >= b.y - 1 && wy <= b.y + b.h + 0.3) {
            return { kind: 'building', id: b.id }
          }
        }
        // lane sites (buoys / isles / mist)
        for (const site of p.geo.laneSites) {
          const r = site.render === 'isle' ? 12 : 4
          if (Math.hypot(wx - site.cx, wy - site.cy) <= r) {
            return { kind: 'lane', id: `lane:${site.slot}` }
          }
        }
        return { kind: 'ground', id: 'ground' }
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
      console.error('[world/engine] renderer boot failed — DOM badge raised:', err)
      propsRef.current.onIssues?.([
        `engine renderer failed: ${err instanceof Error ? err.message : String(err)}`,
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

  return <div ref={hostRef} className="absolute inset-0 overflow-hidden" data-world-engine-canvas />
}
