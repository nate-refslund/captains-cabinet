'use client'

/**
 * EngineCanvas — the ONE continuous world (T1, spec v2 D1/D3) + the T2
 * LIFE layer (v1a review fixes, 2026-07-09).
 *
 * One PixiJS stage renders the whole archipelago canvas from:
 *  - compositor-grade terrain (v1a must-fix): sheet-tile base + fnv1a-seeded
 *    dither patterns in SHEET-SAMPLED hues (lib/world/terrain-pattern.ts —
 *    the engine port of the GREEN offline compositor's three-pass ground
 *    painting + wave-dash water), coast carved per-tile through landAt()
 *    (coastWobble — never a perfect circle), forest-border tree mass;
 *  - era×rung-resolved buildings (lib/world/world-buildings.ts) with the
 *    RECOMPOSED lighthouse (Captain ruling 2026-07-09: the lamp must fit
 *    the tower — the 21_Beach banded tower, staged per the growth ladder;
 *    NEVER the water-tank/silo body) and honest worksite markers for
 *    staged-vocab elements (library/observatory) instead of wrong-object
 *    substitutions;
 *  - REAL officer characters (Premade_Character sheets — the same binder
 *    the Wardroom uses) at island/mid/close, seated at real desks inside
 *    the roof-cutaway interior (Room_Builder floor + wall + office desks);
 *  - the T2 LIFE layer (lib/world/life): commute walkers on the road with
 *    the verb-icon pixel bubble, construction sites (worksite kit + crew
 *    figures), apprentice figures — all grammar-gated fail-closed;
 *  - product isles + reef-buoys + mist pockets (opaque corpus-grey dither);
 *  - LOD rules (lib/world/lod.ts) — footprints in corpus-native slate;
 *  - weather bound to REAL signals; night that READS as night (deep wash +
 *    zoom-scaled lamp pools + window glow); rain that reads as rain.
 *
 * Doctrine unchanged: pure renderer, no writes, no wall clock, no unseeded
 * RNG, no world-space text (DOM labels), CSP eval-free boot, loud failure
 * via onIssues.
 */
import { useEffect, useRef } from 'react'
import type { Container, Graphics, Sprite, Texture, TilingSprite } from 'pixi.js'
import type { OfficerPresence } from '@/lib/world/types'
import {
  cameraTranslation,
  groundDiamond,
  projectionFor,
  screenToWorld,
  TOPDOWN_TILE,
  worldScale,
  type ProjectionKind,
} from '@/lib/world/projection'
import { fnv1a } from '@/lib/world/hash'
import { parsePack, type IsoPack } from '@/lib/world/iso-pack'
import {
  buildIsoScene,
  pickIsoSprite,
  LANE_PAINT_SQUASH,
  layoutStateFrom,
  unmeasuredIssues,
  type IsoScene,
} from '@/lib/world/iso-scene'
import { groundField, ROAD_GROUND, seaTile, type GroundClass, type TerrainBuffer } from '@/lib/world/iso-terrain'
import {
  deckStripRects,
  jettyDeckRects,
  jettyPostRects,
  wharfPostRects,
  type DeckRect,
} from '@/lib/world/iso-quay'
import {
  MOTTLE_TONES,
  PAINT_FEATHER,
  type Blob as PaintBlob,
  type LayoutState,
  type PaintRegion,
} from '@/lib/world/iso-layout'
import type { SpriteCut, WorldAssetManifest } from '@/lib/world/sprites'
import {
  CHAR_FRAME_H,
  CHAR_FRAME_W,
  charFrame,
  characterSheetFor,
  deskSheetFor,
  FLOOR_CUT,
  ROOM_SHEET,
  WALL_CUT,
  type CharFacing,
} from '@/lib/world/sprites'
import {
  BUCKET_LOAD,
  CHICKEN_SHEETS,
  chickenCut,
  DOG_SHEET,
  dogSleepCut,
  F,
  FARM_SHEET,
  FARM_TER,
  FARM_TREES,
  FISH_CUTS,
  FISH_SHEET,
  GRASS_VARIANT_CUTS,
  GRASS_VARIANTS,
  LIGHTHOUSE_LIT_SHEET,
  LIGHTHOUSE_SHEET,
  lighthouseCutFor,
  TER_GRASS,
  TER_GVAR,
  TREE_CUTS,
  TUFT_SHEETS,
  STAGED_VOCAB_ELEMENTS,
  STREET_PROPS,
  UI_SHEET,
  V,
  VILLAGE_SHEET,
  verbIconCut,
  WORKSITE_KIT,
  bucketOf,
  resolveOutdoorSprites,
  type DayBucket,
} from '@/lib/world/sprites-outdoor'
import {
  dirtTileFlecks,
  FOAM_WHITE,
  FOOT_SLATE,
  FOOT_SLATE_2,
  GLOW_CORE,
  GLOW_WARM,
  grassFlecks,
  grassTones,
  INK_BLACK,
  MIST_GREY,
  mistBandDashes,
  mistDots,
  NIGHT_VEIL_HUES,
  PATTERN_PX,
  PLANK_BROWN,
  shadowDots,
  smokePuffs,
  veilDots,
  WATER_BASE,
  waterDashes,
  waterTones,
  waveRingDashes,
} from '@/lib/world/terrain-pattern'
import { baseTile, landAt, shoreMask, shoreVariant } from '@/lib/world/chunks'
import { buildOutdoorDressing } from '@/lib/world/outdoor-dressing'
import { chickenAnimOf } from '@/lib/world/life/fauna'
import { CHART_TABLE_LOCAL, roadPoint, toWorld, type WorldGeo } from '@/lib/world/world-geo'
import type { LaneCourse, VoyageRender } from '@/lib/world/course'
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
import type { LifeOut } from '@/lib/world/life/life'
import { lotPerimeter } from '@/lib/world/life/sites'

/** Day/night ambience — night must READ as night (v1a should-fix), and it
 * must read PALETTE-NATIVE (cozy-density fix 2026-07-09: the old full-frame
 * alpha washes shifted EVERY pixel out of the corpus bins — the v1a live
 * captures measured 15–61% PALETTE_FOREIGN_MASS. Ambience is now an OPAQUE
 * seeded dither VEIL in an in-bin hue: covered pixels are exactly the veil
 * color, uncovered pixels keep their true color — the frame darkens/warms
 * perceptually while every pixel stays in the fitted palette). */
/**
 * The TOP-DOWN tile, taken from the ONE kernel module rather than re-declared.
 *
 * The scene builders below (buildTerrain, buildBuildings, buildDressing, the
 * interior, the LIFE draw sites) ARE the top-down renderer: they run only when
 * the projection is 'topdown', where the tile is square — w === h, pinned in
 * projection.test.ts — which is why one scalar serves both axes. Under 'iso'
 * none of them is called: the scene is driven from composeLayout, whose
 * coordinates are already projected. The camera, the pointer inverse and the
 * depth key go through the kernel in BOTH modes; those are the copies that had
 * to collapse, and they have.
 */
const TD = TOPDOWN_TILE.w

/**
 * The island's seed under the iso kernel.
 *
 * One deployment, one island, forever: composeLayout keys its coastline, its
 * plaza edge and every planting decision off this, so the same org always gets
 * the same ground. It is deliberately NOT derived from the camera, the clock or
 * the payload — a world that re-rolls its coastline when a metric moves is not
 * a place anyone can learn.
 */
const ISO_SEED = 'cabinet-world'

const VEIL: Record<DayBucket, { colors: readonly number[]; coverage: number } | null> = {
  dawn: { colors: [GLOW_CORE], coverage: 0.08 },
  day: null,
  dusk: { colors: [0xffc890], coverage: 0.16 }, // in-bin warm (verified)
  night: { colors: NIGHT_VEIL_HUES, coverage: 0.42 },
}

export interface EngineTarget {
  kind: 'officer' | 'building' | 'lane' | 'mailbox' | 'chart_table' | 'site' | 'ground'
  id: string
}

export interface EngineCanvasProps {
  /**
   * Which world→screen kernel this canvas renders with. Told, never
   * discovered: page.tsx reads ?iso server-side and threads it down, exactly
   * as it threads ?legacy, so the canvas never reads window and the two paths
   * are both permanently reachable for the bake-off.
   */
  projection: ProjectionKind
  geo: WorldGeo
  buildings: WorldBuilding[]
  resolution: WorldResolution | null
  officers: Record<string, OfficerPresence>
  life: LifeOut | null
  camera: EngineCamera
  cutaway: CutawayState
  weather: WeatherState
  tick: number
  killswitch: boolean
  clockHour: number | null
  /** Direction surface (grammar v4): the chart table renders only when
   * directions exist on this deployment (honest-absent otherwise). */
  chartTable?: boolean
  /** Per-lane course states (chart_table_view / voyage law) — hue+shape
   * dual-coded course lines; NO text ever reaches the canvas. */
  courses?: Record<string, LaneCourse> | null
  /** Voyage fold (pure, server-data-driven): moored vs on-the-line boat. */
  voyage?: VoyageRender | null
  onPrimary: (target: EngineTarget | null) => void
  onSecondary: (target: EngineTarget | null) => void
  onIssues?: (issues: string[]) => void
}

interface PixiHandles {
  destroy: () => void
  draw: (props: EngineCanvasProps) => void
}

/** Interim sprite-hint → verified pack cut. Staged-vocab elements
 * (STAGED_VOCAB_ELEMENTS) and the lighthouse resolve elsewhere. */
const HINT_CUT: Record<string, { sheet: string; cut?: SpriteCut } | null> = {
  great_house: { sheet: VILLAGE_SHEET, cut: V.hq },
  cottage: null, // seeded roof palette — resolved per building id
  workshop: { sheet: FARM_SHEET, cut: F.kilnShed }, // era-honest work shed
  well: { sheet: FARM_SHEET, cut: F.well },
  barn: { sheet: FARM_SHEET, cut: F.barn },
  law_plot: { sheet: VILLAGE_SHEET, cut: V.lawPlot },
  warehouse: { sheet: FARM_SHEET, cut: F.kilnShed },
  hut: { sheet: VILLAGE_SHEET, cut: V.cottage[1] },
  silo: { sheet: FARM_SHEET, cut: F.silo },
  stall: { sheet: FARM_SHEET, cut: F.crate },
  firepit: { sheet: VILLAGE_SHEET, cut: V.rock },
  water_store: { sheet: BUCKET_LOAD }, // buckets — era water store
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
      // The kernel is fixed for the life of this canvas: the flag is read
      // server-side and a change is a navigation, which remounts the effect.
      const proj = projectionFor(propsRef.current.projection)
      const isIso = proj.kind === 'iso'
      const PIXI = await import('pixi.js')
      await import('pixi.js/unsafe-eval') // CSP: AOT patch, header never widens
      if (cancelled || !hostRef.current) return

      PIXI.TextureSource.defaultOptions.scaleMode = 'nearest'
      PIXI.Assets.setPreferences({ preferWorkers: false })

      const app = new PIXI.Application()
      await app.init({
        background: WATER_BASE, // open sea — never a foreign void
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

      // ── the iso pack: one atlas + one resolve table, LOUD when absent ────
      // The top-down path has a placeholder mode because a missing LimeZu
      // sheet still leaves a world to look at. The iso path has none: without
      // the atlas there is nothing to draw at all, so an absent or malformed
      // pack raises the DOM badge and this canvas renders ground and no
      // sprites — never a silent black frame (2026-07-08 contract).
      let isoPack: IsoPack | null = null
      let isoAtlas: Texture | null = null
      if (isIso) {
        try {
          const res = await fetch('/world-assets/originals/iso/world-pack.json')
          if (!res.ok) throw new Error(`world-pack HTTP ${res.status}`)
          isoPack = parsePack(await res.json())
          const url = `/world-assets/originals/iso/${isoPack.atlases[0]}`
          isoAtlas = (await PIXI.Assets.load(url)) as Texture
          if (!isoAtlas) throw new Error(`atlas ${url} loaded as null`)
        } catch (err) {
          isoPack = null
          isoAtlas = null
          const msg = err instanceof Error ? err.message : String(err)
          issues.push(`iso pack unavailable — no sprites will draw: ${msg}`)
          console.error('[world/engine] iso pack/atlas failed:', err)
        }
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

      /** A field buffer as a nearest-neighbour texture, cached per key. */
      const fieldTex = new Map<string, Texture>()
      function fieldTexture(key: string, buf: TerrainBuffer): Texture {
        const hit = fieldTex.get(key)
        if (hit) return hit
        const cv = document.createElement('canvas')
        cv.width = buf.w
        cv.height = buf.h
        const ctx = cv.getContext('2d')
        if (!ctx) throw new Error('iso terrain: no 2d context for the ground bake')
        ctx.putImageData(new ImageData(buf.rgba, buf.w, buf.h), 0, 0)
        const tex = PIXI.Texture.from(cv)
        tex.source.scaleMode = 'nearest'
        fieldTex.set(key, tex)
        return tex
      }

      // ── compositor-grade patterns (baked ONCE; fnv1a-seeded, replayable) ──
      function bakePattern(
        base: Texture | null,
        fallback: number,
        dashes: ReturnType<typeof waterDashes>
      ): Texture {
        const c = new PIXI.Container()
        if (base) {
          c.addChild(
            new PIXI.TilingSprite({ texture: base, width: PATTERN_PX, height: PATTERN_PX })
          )
        } else {
          const g = new PIXI.Graphics()
          g.rect(0, 0, PATTERN_PX, PATTERN_PX).fill(fallback)
          c.addChild(g)
        }
        const g2 = new PIXI.Graphics()
        for (const d of dashes) g2.rect(d.x, d.y, d.len, d.h).fill(d.color)
        c.addChild(g2)
        const rt = PIXI.RenderTexture.create({ width: PATTERN_PX, height: PATTERN_PX })
        app.renderer.render({ container: c, target: rt })
        c.destroy({ children: true })
        return rt
      }
      // The open sea. Under 'iso' it is the reference's own computed water,
      // generated as a SEAMLESS patch (the sea repeats in screen space, so a
      // non-periodic field would draw a grid across the water); under
      // 'topdown' it stays the sheet-sampled pattern the world ships today.
      const waterPattern = isIso
        ? fieldTexture('sea', seaTile(fnv1a(ISO_SEED)))
        : bakePattern(texFor(VILLAGE_SHEET, V.water), WATER_BASE, [
            ...waterTones(), // tonal bands FIRST…
            ...waterDashes(), // …dashes on top (blocks never flat)
          ])
      /** Cozy-density ground (2026-07-09): the mockups' OWN three-pass
       * recipe — farm-terrain base + seeded variant daubs + speckle tile +
       * tonal bands + blade flecks. The v1a single-tile-plus-flecks lawn
       * collapsed into CLUSTER_FLAT_VOID on every live capture. */
      function bakeGrassPattern(): Texture {
        const c = new PIXI.Container()
        const base = texFor(FARM_TER, TER_GRASS) ?? texFor(VILLAGE_SHEET, V.grass)
        if (base) {
          c.addChild(
            new PIXI.TilingSprite({ texture: base, width: PATTERN_PX, height: PATTERN_PX })
          )
        } else {
          const g0 = new PIXI.Graphics()
          g0.rect(0, 0, PATTERN_PX, PATTERN_PX).fill(0x76c564)
          c.addChild(g0)
        }
        // pass 2: clustered variant daubs (compose_unified paint_grass port)
        const varTexes = GRASS_VARIANT_CUTS.map((cut) => texFor(GRASS_VARIANTS, cut)).filter(
          (t): t is Texture => t !== null
        )
        const TILES = PATTERN_PX / TD
        if (varTexes.length > 0) {
          const nDaub = Math.max(6, (TILES * TILES) / 6)
          for (let d = 0; d < nDaub; d++) {
            const h = fnv1a(`grass-daub:${d}`)
            const cx = h % TILES
            const cy = (h >>> 8) % TILES
            const v = varTexes[(h >>> 16) % varTexes.length]
            for (let k = 0; k < 2 + ((h >>> 24) % 3); k++) {
              const hh = fnv1a(`grass-daub:${d}:${k}`)
              const tx = Math.min(TILES - 1, Math.max(0, cx + ((hh % 5) - 2)))
              const ty = Math.min(TILES - 1, Math.max(0, cy + (((hh >>> 8) % 3) - 1)))
              const sp = new PIXI.Sprite(v)
              sp.position.set(tx * TD, ty * TD)
              c.addChild(sp)
            }
          }
          // pass 3: speckle tile over most tiles (the mockup's gvar pass)
          const gvarTex = texFor(FARM_TER, TER_GVAR)
          if (gvarTex) {
            for (let ty = 0; ty < TILES; ty++) {
              for (let tx = 0; tx < TILES; tx++) {
                if (fnv1a(`grass-speck:${tx},${ty}`) % 100 < 85) {
                  const sp = new PIXI.Sprite(gvarTex)
                  sp.position.set(tx * TD, ty * TD)
                  c.addChild(sp)
                }
              }
            }
          }
        }
        // pass 4: tonal bands + blade flecks (seeded primitives)
        const g2 = new PIXI.Graphics()
        for (const d of [...grassTones(), ...grassFlecks()]) {
          g2.rect(d.x, d.y, d.len, d.h).fill(d.color)
        }
        c.addChild(g2)
        const rt = PIXI.RenderTexture.create({ width: PATTERN_PX, height: PATTERN_PX })
        app.renderer.render({ container: c, target: rt })
        c.destroy({ children: true })
        return rt
      }
      const grassPattern = isIso ? PIXI.Texture.EMPTY : bakeGrassPattern()
      /** Ambience veils (palette-lawful dither, baked once per bucket). */
      const veilTextures = new Map<string, Texture>()
      function veilTexture(colors: readonly number[], coverage: number): Texture {
        const key = `${colors.join('-')}:${coverage}`
        let t = veilTextures.get(key)
        if (!t) {
          const g = new PIXI.Graphics()
          for (const d of veilDots(`veil:${key}`, coverage, colors.length)) {
            g.rect(d.x, d.y, 1, 1).fill(colors[d.hue])
          }
          const rt = PIXI.RenderTexture.create({ width: PATTERN_PX, height: PATTERN_PX })
          app.renderer.render({ container: g, target: rt })
          g.destroy()
          veilTextures.set(key, rt)
          t = rt
        }
        return t
      }

      // ── layers ──────────────────────────────────────────────────────────
      // The sea is SCREEN-space (the world is unbounded — no foreign void
      // beyond the canvas, ever); everything else lives in world space.
      const seaSprite: TilingSprite = new PIXI.TilingSprite({
        texture: waterPattern,
        width: app.renderer.width,
        height: app.renderer.height,
      })
      app.stage.addChild(seaSprite)
      const world: Container = new PIXI.Container()
      app.stage.addChild(world)
      const terrainLayer: Container = new PIXI.Container()
      world.addChild(terrainLayer)
      const shoreG: Graphics = new PIXI.Graphics()
      world.addChild(shoreG)
      // drop shadows sit UNDER every prop, over the ground (cozy pass #13:
      // opaque corpus-slate dither — static half at rebuild, dynamic half
      // per frame for walkers/officers/fauna)
      const staticShadowG: Graphics = new PIXI.Graphics()
      world.addChild(staticShadowG)
      const dynShadowG: Graphics = new PIXI.Graphics()
      world.addChild(dynShadowG)
      const propLayer: Container = new PIXI.Container()
      propLayer.sortableChildren = true
      world.addChild(propLayer)
      const placeholderG: Graphics = new PIXI.Graphics()
      world.addChild(placeholderG)
      const dynG: Graphics = new PIXI.Graphics() // buoys, mist, small marks
      world.addChild(dynG)
      // ambience veil: SCREEN-space palette-lawful dither (over the whole
      // frame incl. the open sea; replaces alpha washes + sea tint)
      const veilSprite: TilingSprite = new PIXI.TilingSprite({
        texture: PIXI.Texture.EMPTY,
        width: app.renderer.width,
        height: app.renderer.height,
      })
      veilSprite.visible = false
      app.stage.addChild(veilSprite)
      // glow layer rides ABOVE the veil (warm windows must cut through the
      // night dither — the light IS the story) but tracks world space:
      // draw() copies the world transform onto it every frame.
      const fxG: Graphics = new PIXI.Graphics() // world-coord glow dither
      app.stage.addChild(fxG)
      const weatherG: Graphics = new PIXI.Graphics() // SCREEN-space particles
      app.stage.addChild(weatherG)

      /** Opaque dither shadow at a world-px anchor (static or dynamic). */
      function drawShadow(g: Graphics, id: string, wxPx: number, wyPx: number, wPx: number) {
        for (const d of shadowDots(id, wPx)) {
          g.rect(wxPx + d.x, wyPx + d.y - 1, d.r, 1).fill(FOOT_SLATE)
        }
      }
      /** Opaque dither glow pool (lamps/windows — GLOW dots, never alpha). */
      function drawGlow(g: Graphics, id: string, wxPx: number, wyPx: number, r: number) {
        const n = Math.max(14, Math.floor(r * r * 0.55))
        for (let i = 0; i < n; i++) {
          const h = fnv1a(`glow:${id}:${i}`)
          const dx = (h % (r * 2 + 1)) - r
          const dy = ((h >>> 8) % (r * 2 + 1)) - r
          const d2 = (dx * dx + dy * dy) / (r * r)
          if (d2 > 1) continue
          // density falls off with distance — seeded holes, opaque hues
          if (((h >>> 16) % 100) / 100 < d2 * 0.82) continue
          g.rect(wxPx + dx, wyPx + dy, 1 + ((h >>> 24) % 2), 1).fill(
            d2 < 0.18 ? GLOW_CORE : GLOW_WARM
          )
        }
      }

      /** Building sprites by id (cutaway alpha is applied per frame). */
      const buildingSprites = new Map<string, Sprite>()
      let builtKey = ''

      // ── pooled dynamic display objects (officers, walkers, interiors) ────
      const pool = new Map<string, Container>()
      const poolUsed = new Set<string>()
      function pooled<T extends Container>(key: string, make: () => T): T {
        let obj = pool.get(key) as T | undefined
        if (!obj) {
          obj = make()
          pool.set(key, obj)
          propLayer.addChild(obj)
        }
        poolUsed.add(key)
        obj.visible = true
        return obj
      }
      function sweepPool() {
        for (const [key, obj] of pool) {
          if (!poolUsed.has(key)) {
            pool.delete(key)
            obj.destroy({ children: true })
          }
        }
        poolUsed.clear()
      }

      function clearStatics() {
        terrainLayer.removeChildren().forEach((c) => c.destroy())
        propLayer.removeChildren().forEach((c) => c.destroy())
        buildingSprites.clear()
        pool.clear()
        poolUsed.clear()
        shoreG.clear()
        staticShadowG.clear()
      }

      /** Foam strokes oriented per shore autotile variant (procedural pass;
       * hues sheet-sampled — never a foreign white). */
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
              const px = tx * TD
              const py = ty * TD
              const seed = fnv1a(`foam:${tx},${ty}`)
              const off = 3 + (seed % 5)
              const foam = { width: 2, color: FOAM_WHITE, alpha: 1 }
              if (v === 'edge_n' || v.startsWith('corner_n') || v === 'cove') {
                shoreG.moveTo(px + 2, py + 3).lineTo(px + off + 6, py + 3).stroke(foam)
              }
              if (v === 'edge_s' || v.startsWith('corner_s') || v === 'cove') {
                shoreG.moveTo(px + 2, py + TD - 3).lineTo(px + off + 6, py + TD - 3).stroke(foam)
              }
              if (v === 'edge_e' || v.endsWith('e') || v === 'channel_ew') {
                shoreG.moveTo(px + TD - 3, py + 2).lineTo(px + TD - 3, py + off + 4).stroke(foam)
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

      /** Per-tile terrain over each island bbox: the coastline is landAt()
       * (coastWobble — no perfect circles), the heart is the dithered grass
       * pattern, sand rings the coast, the forest border is tree MASS. */
      function buildTerrain(p: EngineCanvasProps) {
        const geo = p.geo
        for (const isl of geo.islands) {
          if (isl.r <= 0) continue
          const pad = 2
          const x0 = isl.cx - isl.r - pad
          const y0 = isl.cy - isl.r - pad
          const x1 = isl.cx + isl.r + pad
          const y1 = isl.cy + isl.r + pad
          // land mask (per-tile rects — the wobbled coast, not a circle)
          const mask = new PIXI.Graphics()
          for (let ty = y0; ty <= y1; ty++) {
            for (let tx = x0; tx <= x1; tx++) {
              if (landAt(tx, ty, geo)) mask.rect(tx * TD, ty * TD, TD, TD)
            }
          }
          mask.fill(0xffffff)
          const grass = new PIXI.TilingSprite({
            texture: grassPattern,
            width: (x1 - x0 + 1) * TD,
            height: (y1 - y0 + 1) * TD,
          })
          grass.position.set(x0 * TD, y0 * TD)
          grass.mask = mask
          terrainLayer.addChild(mask)
          terrainLayer.addChild(grass)
          // per-tile dressing: sand fringe, meadow decals, forest mass
          const sandTex = texFor(VILLAGE_SHEET, V.sand)
          const flowerTex = texFor(VILLAGE_SHEET, V.flowerbed)
          const pebbleTex = texFor(VILLAGE_SHEET, V.pebbles)
          // cozy pass #9: the mockups' tuft/flower decal set joins the
          // seeded picker (11 farm tuft singles — variety, not spam)
          const tuftTexes = TUFT_SHEETS.map((s) => texFor(s)).filter(
            (t): t is Texture => t !== null
          )
          // corpus tree canon: the SAME farm-pack oaks the palette
          // positives were composed from (Serene tree rows retired —
          // ~11% palette-foreign per pixel)
          const treeTexes = TREE_CUTS.map((c) => texFor(FARM_TREES, c)).filter(
            (t): t is Texture => t !== null
          )
          for (let ty = y0; ty <= y1; ty++) {
            for (let tx = x0; tx <= x1; tx++) {
              const t = baseTile(tx, ty, geo)
              if (t === 'sand' && sandTex) {
                const sp = new PIXI.Sprite(sandTex)
                sp.position.set(tx * TD, ty * TD)
                terrainLayer.addChild(sp)
              } else if (t === 'meadow') {
                const h = fnv1a(`meadow-decal:${tx},${ty}`)
                const roll = h & 7
                // mostly green tufts; flowers are the accent, not a blanket
                const tex =
                  roll === 0
                    ? pebbleTex
                    : roll === 1
                      ? flowerTex
                      : tuftTexes.length > 0
                        ? tuftTexes[(h >>> 8) % tuftTexes.length]
                        : flowerTex
                if (tex) {
                  const sp = new PIXI.Sprite(tex)
                  sp.position.set(tx * TD + (h % 4), ty * TD + ((h >>> 4) % 4))
                  terrainLayer.addChild(sp)
                }
              } else if (t === 'forest') {
                // tree-border MASS: seeded oaks on a 3×2 lattice, canopies
                // overlapping into a real border (compositor bar)
                const h = fnv1a(`forest:${tx},${ty}`)
                if (tx % 3 === (h >>> 3) % 3 && ty % 2 === 0 && treeTexes.length > 0) {
                  const tex = treeTexes[h % treeTexes.length]
                  const sp = new PIXI.Sprite(tex)
                  sp.anchor.set(0.5, 1)
                  const px = tx * TD + (h % 8) - 4
                  const py = (ty + 1) * TD + ((h >>> 6) % 8)
                  sp.position.set(px, py)
                  sp.zIndex = ty * TD - 2000 // canopy band behind buildings
                  propLayer.addChild(sp)
                  // cozy pass #13: soft dither shadow under every tree
                  drawShadow(staticShadowG, `tree:${tx},${ty}`, px, py - 2, tex.width - 14)
                }
              }
            }
          }
        }
        // road: dirt tile per carved spine tile + worn-path speckle
        // (cozy pass #10: the mockup street is walked earth, not a ribbon)
        const dirtTex = texFor(VILLAGE_SHEET, V.dirt)
        const dirtG = new PIXI.Graphics()
        if (dirtTex) {
          for (const key of p.geo.roadTiles) {
            const [xs, ys] = key.split(',')
            const tx = Number(xs)
            const ty = Number(ys)
            const sp = new PIXI.Sprite(dirtTex)
            sp.position.set(tx * TD, ty * TD)
            terrainLayer.addChild(sp)
            for (const d of dirtTileFlecks(tx, ty)) {
              dirtG.rect(tx * TD + d.x, ty * TD + d.y, d.len, d.h).fill(d.color)
            }
          }
        }
        terrainLayer.addChild(dirtG)
        // quay: the reclaimed working-wharf BAND (cozy pass fix — baseTile
        // has returned 'quay' for this band since v1a, but the renderer
        // never drew the tile type: the wharf read as lawn with a fence).
        for (let ty = geo.quayCenter.y - 1; ty <= geo.quayCenter.y + 1; ty++) {
          for (let tx = geo.quayCenter.x - 10; tx <= geo.quayCenter.x + 10; tx++) {
            if (baseTile(tx, ty, geo) !== 'quay') continue
            // V.dock is a 3-tile plank strip — take the per-tile 16px cut
            // (position-keyed, so the plank pattern runs continuously)
            const sub = ((tx % 3) + 3) % 3
            const plank = texFor(VILLAGE_SHEET, {
              x: V.dock.x + sub * 16,
              y: V.dock.y,
              w: 16,
              h: 16,
            })
            if (!plank) continue
            const sp = new PIXI.Sprite(plank)
            sp.position.set(tx * TD, ty * TD)
            terrainLayer.addChild(sp)
            for (const d of dirtTileFlecks(tx, ty)) {
              dirtG.rect(tx * TD + d.x, ty * TD + d.y, d.len, d.h).fill(d.color)
            }
          }
        }
        // pier below the road mouth (+ the moored rowboat — the egg's own
        // boat, era rung 0 of harbor_boat; wave rings seat both IN the sea)
        const pierTex = texFor(VILLAGE_SHEET, V.pier)
        const ringG = new PIXI.Graphics()
        if (pierTex) {
          const sp = new PIXI.Sprite(pierTex)
          sp.position.set((geo.quayCenter.x - 1) * TD, geo.quayCenter.y * TD)
          terrainLayer.addChild(sp)
          for (const [ri, [px, py]] of (
            [
              [(geo.quayCenter.x - 0.6) * TD, (geo.quayCenter.y + 2.1) * TD],
              [(geo.quayCenter.x + 1.7) * TD, (geo.quayCenter.y + 2.0) * TD],
            ] as const
          ).entries()) {
            for (const d of waveRingDashes(`pier:${ri}`)) {
              ringG.rect(px + d.x, py + d.y, d.len, d.h).fill(d.color)
            }
          }
        }
        const boatTex = texFor(STREET_PROPS.boat)
        if (boatTex) {
          // voyage law (show-grammar v4 / morphology harbor_boat_voyage):
          // position is a pure function of course state + last port call —
          // moored at the quay unless a lane is TACKING, then out-and-back
          // along the plotted course (progress arrives as server data via
          // the engine payload; the render never reads a clock). The boat's
          // SIZE/vocab stay the harbor_boat ladder's (dual-view D7).
          let bx = (geo.quayCenter.x + 3.1) * TD
          let by = (geo.quayCenter.y + 3.4) * TD
          const voy = p.voyage
          if (voy?.underway && voy.lane) {
            const site = p.geo.laneSites.find((s) => s.lane === voy.lane)
            if (site) {
              // out at progress ≤ 0.5, back at > 0.5 (triangle fold); stop
              // short of the isle center so the bow meets the dock, not land.
              const t =
                0.9 * (voy.progress <= 0.5 ? voy.progress * 2 : (1 - voy.progress) * 2)
              const x0 = geo.quayCenter.x + 3.1
              const y0 = geo.quayCenter.y + 3.4
              bx = (x0 + (site.cx - x0) * t) * TD
              by = (y0 + (site.cy - y0) * t) * TD
            }
          }
          const sp = new PIXI.Sprite(boatTex)
          sp.anchor.set(0.5, 1)
          sp.position.set(bx, by)
          terrainLayer.addChild(sp)
          for (const d of waveRingDashes('boat')) {
            ringG.rect(bx + d.x, by - 8 + d.y, d.len, d.h).fill(d.color)
          }
        }
        // ── direction surface (grammar v4): plotted course lines + port-call
        // chalk stamps. State-pure statics (staticsKey carries the course
        // signature); hue + shape dual-coded — amber(0xffc890, verified
        // in-bin warm) = adrift ONLY, grey stays unmeasured-only, red never;
        // NO text in world-space (dates live on the authed card).
        const courseG = new PIXI.Graphics()
        const qx = geo.quayCenter.x * TD
        const qy = (geo.quayCenter.y + 2) * TD
        for (const site of p.geo.laneSites) {
          const course = site.lane ? p.courses?.[site.lane] : undefined
          if (!course) continue
          const tx = site.cx * TD
          const ty = site.cy * TD
          const dx = tx - qx
          const dy = ty - qy
          const steps = Math.max(10, Math.floor(Math.hypot(dx, dy) / 12))
          // dash cadence + hue dual-code the state (shape carries alone too)
          const every =
            course.state === 'tacking' ? 1 : course.state === 'docked_refitting' ? 2 : 3
          const color =
            course.state === 'adrift'
              ? 0xffc890
              : course.state === 'tacking'
                ? PLANK_BROWN
                : FOOT_SLATE_2
          for (let i = 1; i < steps; i++) {
            if (i % every !== 0) continue
            const f = i / steps
            // an adrift course line hangs SLACK (sag = the second coding)
            const sag = course.state === 'adrift' ? Math.sin(Math.PI * f) * 10 : 0
            courseG.rect(qx + dx * f - 1, qy + dy * f + sag - 1, 3, 3).fill({ color })
          }
          // port-call chalk count-marks at the berth (dates: card-only)
          const stamps = Math.min(course.portCallDates.length, 12)
          const offY = site.cy < 100 ? -20 : 14
          for (let k = 0; k < stamps; k++) {
            courseG
              .rect(tx - 12 + (k % 6) * 4, ty + offY + Math.floor(k / 6) * 4, 2, 3)
              .fill({ color: FOAM_WHITE })
          }
        }
        terrainLayer.addChild(courseG)
        terrainLayer.addChild(ringG)
        // GROWTH-FOG horizon band (§2.4 "mist beyond" — engine port of the
        // egg compositor's mist_band): dithered opaque mist across the
        // UNMEASURED sea horizon. Derived from the same growth geometry —
        // the band hugs the canvas horizon south of everything earned and
        // thins/recedes as isles grow toward it. True by construction.
        const southMost = Math.max(
          ...geo.islands.map((i) => i.cy + i.r),
          geo.quayCenter.y
        )
        const bandY0 = Math.min(geo.canvas.h - 6, Math.max(geo.canvas.h - 16, southMost + 6))
        const mistG = new PIXI.Graphics()
        for (const d of mistBandDashes(bandY0, geo.canvas.h - 1, 0, geo.canvas.w - 1)) {
          mistG.rect(d.x, d.y, d.len, d.h).fill(d.color)
        }
        terrainLayer.addChild(mistG)
        drawShore(geo)
      }

      /** Cozy set-dressing pass (outdoor-dressing.ts data table): benches,
       * torch posts, quay cargo, hedges, rocks, trunks, hay, flowers —
       * decorative-honest, seeded, clustered per the composition rulebook. */
      function buildDressing(p: EngineCanvasProps) {
        const dressing = buildOutdoorDressing(p.geo, p.buildings, p.resolution)
        for (const d of dressing.decor) {
          const tex = texFor(d.sheet, d.cut)
          if (!tex) continue
          const sp = new PIXI.Sprite(tex)
          sp.anchor.set(0.5, 1)
          const px = d.x * TD
          const py = d.y * TD
          sp.position.set(px, py)
          sp.zIndex = py
          propLayer.addChild(sp)
          if (d.shadowW > 0) drawShadow(staticShadowG, d.id, px, py, d.shadowW)
        }
      }

      /** Honest STAGED-vocab marker: cleared earth + striped fences + the
       * worksite sign (never a wrong-object substitution — v1a era fix). */
      function buildStagedMarker(b: WorldBuilding) {
        const groundTex = texFor(WORKSITE_KIT.ground)
        const signTex = texFor(WORKSITE_KIT.sign)
        const fenceA = texFor(WORKSITE_KIT.fenceA)
        const fenceB = texFor(WORKSITE_KIT.fenceB)
        const moundsTex = texFor(WORKSITE_KIT.mounds)
        const c = new PIXI.Container()
        if (groundTex) {
          for (let ty = 0; ty < b.h; ty++) {
            for (let tx = 0; tx < b.w; tx++) {
              const g = new PIXI.Sprite(groundTex)
              g.position.set((b.x + tx) * TD, (b.y + ty) * TD)
              c.addChild(g)
            }
          }
        }
        // SPARSE lot dressing (dense perimeter fencing read as a red mass
        // at island zoom): corner barriers only + the sign carries the story
        const corners = [
          { x: b.x - 1, y: b.y - 1 },
          { x: b.x + b.w, y: b.y - 1 },
          { x: b.x - 1, y: b.y + b.h },
          { x: b.x + b.w, y: b.y + b.h },
        ]
        for (const pt of corners) {
          const h = fnv1a(`stagedfence:${b.id}:${pt.x},${pt.y}`)
          const tex = (h & 1) === 0 ? fenceA : fenceB
          if (!tex) continue
          const f = new PIXI.Sprite(tex)
          f.anchor.set(0.5, 1)
          f.position.set(pt.x * TD + TD / 2, (pt.y + 1) * TD)
          f.zIndex = (pt.y + 1) * TD
          c.addChild(f)
        }
        if (moundsTex) {
          const m = new PIXI.Sprite(moundsTex)
          m.anchor.set(0.5, 1)
          m.position.set((b.x + b.w / 2) * TD, (b.y + b.h - 0.5) * TD)
          c.addChild(m)
        }
        if (signTex) {
          const s = new PIXI.Sprite(signTex)
          s.anchor.set(0.5, 1)
          s.position.set((b.x + 0.6) * TD, (b.y + b.h + 0.4) * TD)
          s.zIndex = (b.y + b.h + 0.4) * TD
          c.addChild(s)
        }
        c.zIndex = (b.y + b.h) * TD
        propLayer.addChild(c)
      }

      /** The RECOMPOSED lighthouse (banded tower, staged per rung; the
       * dark_cairn rung composes shore rocks). */
      function buildLighthouse(b: WorldBuilding) {
        const cut = lighthouseCutFor(b.rungName)
        const bx = (b.x + b.w / 2) * TD
        const by = (b.y + b.h) * TD
        if (cut) {
          const tex = texFor(LIGHTHOUSE_SHEET, cut)
          if (tex) {
            const sp = new PIXI.Sprite(tex)
            sp.anchor.set(0.5, 1)
            sp.position.set(bx, by)
            sp.zIndex = by
            buildingSprites.set(b.id, sp)
            propLayer.addChild(sp)
            drawShadow(staticShadowG, `lh:${b.id}`, bx, by, 40)
          }
          // under-construction dressing while the tower is partial
          if (b.rungName !== 'tower_full') {
            const signTex = texFor(WORKSITE_KIT.sign)
            if (signTex) {
              const s = new PIXI.Sprite(signTex)
              s.anchor.set(0.5, 1)
              s.position.set(bx - 2.2 * TD, by + 4)
              s.zIndex = by + 4
              propLayer.addChild(s)
            }
          }
          return
        }
        // dark_cairn: rocks + nothing else — ambition visible from birth
        const rockTex = texFor(VILLAGE_SHEET, V.rock)
        if (rockTex) {
          for (const [dx, dy] of [
            [-0.6, 0],
            [0.5, -0.2],
            [0, 0.5],
          ] as const) {
            const r = new PIXI.Sprite(rockTex)
            r.anchor.set(0.5, 1)
            r.position.set(bx + dx * TD, by + dy * TD)
            r.zIndex = by + dy * TD
            propLayer.addChild(r)
            drawShadow(staticShadowG, `cairn:${b.id}:${dx},${dy}`, bx + dx * TD, by + dy * TD, 16)
          }
        }
      }

      /** The pens element as an actual PEN (cozy pass): hedge enclosure
       * around the bbox instead of one floating hedge — the chicken flock
       * (fauna) pecks inside it. */
      function buildPen(b: WorldBuilding) {
        const hedgeTex = texFor(VILLAGE_SHEET, V.hedge)
        if (!hedgeTex) return
        const pts: Array<[number, number]> = []
        for (let tx = 0; tx <= b.w; tx += 2) {
          pts.push([b.x + tx, b.y], [b.x + tx, b.y + b.h])
        }
        for (let ty = 2; ty < b.h; ty += 2) {
          pts.push([b.x, b.y + ty], [b.x + b.w, b.y + ty])
        }
        for (const [tx, ty] of pts) {
          const sp = new PIXI.Sprite(hedgeTex)
          sp.anchor.set(0.5, 1)
          const px = tx * TD
          const py = (ty + 1) * TD
          sp.position.set(px, py)
          sp.zIndex = py
          propLayer.addChild(sp)
        }
        drawShadow(staticShadowG, `pen:${b.id}`, (b.x + b.w / 2) * TD, (b.y + b.h + 1) * TD, 20)
      }

      function buildBuildings(p: EngineCanvasProps) {
        for (const b of p.buildings) {
          if (b.element === 'lighthouse') {
            buildLighthouse(b)
            continue
          }
          if (b.element === 'pens') {
            buildPen(b)
            continue
          }
          if (STAGED_VOCAB_ELEMENTS.has(b.element)) {
            buildStagedMarker(b)
            continue
          }
          const hint =
            b.sprite === 'cottage'
              ? { sheet: VILLAGE_SHEET, cut: V.cottage[fnv1a(`${b.id}:roof`) % V.cottage.length] }
              : HINT_CUT[b.sprite]
          const tex = hint ? texFor(hint.sheet, hint.cut) : null
          if (!tex) continue // loud placeholder rect drawn per-frame
          const sp = new PIXI.Sprite(tex)
          sp.anchor.set(0.5, 1)
          const bx = (b.x + b.w / 2) * TD
          const by = (b.y + b.h) * TD
          sp.position.set(bx, by)
          sp.zIndex = by
          buildingSprites.set(b.id, sp)
          propLayer.addChild(sp)
          // cozy pass #13: every grounded structure casts a dither shadow
          drawShadow(staticShadowG, `bld:${b.id}`, bx, by, Math.min(tex.width - 8, b.w * TD))
        }
        // the mailbox at the crossroads (read-only Captain surface)
        const mailTex = texFor(STREET_PROPS.mailbox)
        if (mailTex) {
          const sp = new PIXI.Sprite(mailTex)
          sp.anchor.set(0.5, 1)
          const mx = (p.geo.crossroads.x + 1.2) * TD
          const my = (p.geo.crossroads.y + 0.6) * TD
          sp.position.set(mx, my)
          sp.zIndex = my
          propLayer.addChild(sp)
          drawShadow(staticShadowG, 'mailbox', mx, my, 12)
        }
        // the chart table (direction surface, grammar v4 manor_chart_table;
        // mailbox precedent: small bound prop, read-only card). Renders ONLY
        // when directions exist — honest-absent otherwise. Derived own-pixel
        // composition in proven corpus hues (no pack ships a chart table —
        // the audited fish-precedent class, never a wrong-object sprite).
        if (p.chartTable) {
          const w = toWorld(CHART_TABLE_LOCAL.x, CHART_TABLE_LOCAL.y)
          const px = w.x * TD
          const py = w.y * TD
          const cg = new PIXI.Graphics()
          cg.rect(px + 2, py + 8, 2, 6).fill({ color: INK_BLACK }) // legs
          cg.rect(px + 12, py + 8, 2, 6).fill({ color: INK_BLACK })
          cg.rect(px, py + 4, 16, 5).fill({ color: PLANK_BROWN }) // table top
          cg.rect(px + 2, py + 2, 12, 5).fill({ color: FOAM_WHITE }) // the chart
          cg.rect(px + 4, py + 4, 3, 1).fill({ color: FOOT_SLATE }) // course marks
          cg.rect(px + 8, py + 5, 4, 1).fill({ color: FOOT_SLATE })
          cg.zIndex = py + 14
          propLayer.addChild(cg)
          drawShadow(staticShadowG, 'chart-table', px + 8, py + 14, 14)
        }
      }

      function buildFootprints(p: EngineCanvasProps) {
        // coast/archipelago LOD: seeded footprint blocks from the SAME
        // building list — corpus-native slates (palette gate).
        const g = new PIXI.Graphics()
        for (const b of p.buildings) {
          const h = fnv1a(`fp:${b.id}`)
          const c = (h & 1) === 0 ? FOOT_SLATE : FOOT_SLATE_2
          g.rect(b.x * TD, b.y * TD, b.w * TD, b.h * TD).fill({ color: c })
        }
        // the lighthouse silhouette survives every zoom — honest-zero anomaly
        const lh = p.buildings.find((b) => b.element === 'lighthouse')
        if (lh) {
          g.rect((lh.x + 1) * TD, (lh.y - 2) * TD, TD, 2 * TD).fill({ color: INK_BLACK })
        }
        terrainLayer.addChild(g)
      }

      // ── the ISO scene ────────────────────────────────────────────────────
      // Everything below drives the world from composeLayout instead of the
      // tile lattice. It is a SEPARATE set of builders rather than a branch
      // inside the top-down ones, because the two are different renderers that
      // happen to share a camera, a depth sort and a stage: mixing them would
      // put a tile-space tolerance in an iso path and leave neither honest.

      interface Extent {
        x0: number
        y0: number
        x1: number
        y1: number
      }

      const EMPTY_EXTENT: Extent = { x0: 0, y0: 0, x1: 0, y1: 0 }
      function extentOf(pts: Iterable<{ x: number; y: number }>, pad = 0): Extent {
        let x0 = Infinity
        let y0 = Infinity
        let x1 = -Infinity
        let y1 = -Infinity
        for (const p of pts) {
          x0 = Math.min(x0, p.x)
          y0 = Math.min(y0, p.y)
          x1 = Math.max(x1, p.x)
          y1 = Math.max(y1, p.y)
        }
        if (!Number.isFinite(x0)) return EMPTY_EXTENT
        return { x0: x0 - pad, y0: y0 - pad, x1: x1 + pad, y1: y1 + pad }
      }
      function blobExtent(regions: PaintRegion[], pad = 0): Extent {
        const pts: { x: number; y: number }[] = []
        for (const r of regions) {
          for (const b of r.blobs) {
            pts.push({ x: b.c.x - b.rx, y: b.c.y - b.ry }, { x: b.c.x + b.rx, y: b.c.y + b.ry })
          }
        }
        return extentOf(pts, pad)
      }
      const extentEmpty = (e: Extent) => e.x1 <= e.x0 || e.y1 <= e.y0

      /**
       * A ground class laid over an extent and cut to a mask.
       *
       * The field is generated at the extent's WORLD origin, so two patches of
       * the same class that abut are continuous — this is what keeps the plaza
       * stones lined up with their neighbours and the meadow from shimmering
       * when a region's bounding box moves.
       */
      function paintClass(
        into: Container,
        cls: GroundClass,
        seed: number,
        ext: Extent,
        mask: Container,
        alpha = 1
      ): void {
        if (extentEmpty(ext)) {
          mask.destroy()
          return
        }
        const w = Math.ceil(ext.x1 - ext.x0)
        const h = Math.ceil(ext.y1 - ext.y0)
        const key = `${cls}:${seed}:${ext.x0}:${ext.y0}:${w}:${h}`
        const buf = fieldTex.has(key)
          ? null
          : groundField(cls, w, h, seed, Math.floor(ext.x0), Math.floor(ext.y0))
        const tex = buf ? fieldTexture(key, buf) : fieldTex.get(key)!
        const sp = new PIXI.Sprite(tex)
        sp.position.set(Math.floor(ext.x0), Math.floor(ext.y0))
        sp.scale.set(2) // the field's `block`, upscaled nearest — the same grain
        sp.alpha = alpha
        into.addChild(mask)
        // A Graphics mask is a STENCIL — binary coverage, hard edge, which is
        // right for a surface with a real boundary (a plaza, a pond, a road).
        // A Sprite mask is an ALPHA mask, and `channel: 'alpha'` is what makes
        // it read the coverage this renderer actually wrote: the default 'red'
        // channel multiplies colour by alpha and would square the ramp, turning
        // a feather back into a shoulder.
        if (mask instanceof PIXI.Sprite) sp.setMask({ mask, channel: 'alpha' })
        else sp.mask = mask
        into.addChild(sp)
      }

      /** Run-length spans of a coastline raster row, as one mask Graphics. */
      function rasterMask(cells: Uint8Array, mw: number, mh: number, step: number): Graphics {
        const g = new PIXI.Graphics()
        for (let j = 0; j < mh; j++) {
          let run = -1
          for (let i = 0; i <= mw; i++) {
            const on = i < mw && cells[j * mw + i] === 1
            if (on && run < 0) run = i
            else if (!on && run >= 0) {
              g.rect(run * step, j * step, (i - run) * step, step)
              run = -1
            }
          }
        }
        g.fill(0xffffff)
        return g
      }

      /**
       * A region's blobs unioned into ONE feathered alpha mask.
       *
       * THE DEFECT (Captain, 2026-07-27): "the meadow patches read as hard dark
       * ellipses rather than as subtle variation". compose.py:149 draws its 70
       * patches into one mask and blurs the WHOLE mask by 26px before pasting
       * the dark grass through it; this renderer painted a stencil, which has
       * no edge at all between covered and not. iso-layout/paint.ts owns the
       * number (PAINT_FEATHER) and the offline rasteriser reads the same one out
       * of the draw list, so the two renderers cannot drift apart.
       *
       * ONE MASK, ONE BLUR, and both halves of that matter:
       *
       *   The per-blob STRENGTH is carried in the mask's own alpha instead of in
       *   one masked sprite per bucket. Compositing the buckets weakest-first at
       *   an incremental alpha lands on exactly max(w) — the same identity the
       *   bucket loop used, and the same `ImageChops.lighter` the offline
       *   rasteriser takes — but now it happens INSIDE the mask, so there is one
       *   thing left to blur rather than twenty.
       *
       *   Blurring LAST is not the same as blurring each blob. Feathering the
       *   pieces and then taking the union would restore a hard edge wherever
       *   two soft rims crossed, because the union of two ramps is a ramp with a
       *   crease. The reference blurs the finished mask and so does this.
       *
       * The extent is padded by 3σ so the Gaussian's own tail is inside the
       * texture; a mask cropped at its own edge would draw the crisp rectangle
       * it was trying to avoid.
       */
      function featheredBlobMask(blobs: readonly PaintBlob[], feather: number): Sprite | null {
        const ext = blobExtent([{ kind: 'meadow_dark', blobs } as PaintRegion], feather * 3)
        if (extentEmpty(ext)) return null
        const w = Math.ceil(ext.x1 - ext.x0)
        const h = Math.ceil(ext.y1 - ext.y0)
        const c = new PIXI.Container()
        const bucket = (b: PaintBlob) => Math.round((b.w ?? 1) * 20) / 20
        const levels = [...new Set(blobs.map(bucket))].sort((a, b) => a - b)
        let below = 0
        for (const level of levels) {
          const at = blobs.filter((b) => bucket(b) >= level)
          const step = below >= 1 ? 0 : (level - below) / (1 - below)
          below = level
          if (at.length === 0 || step <= 0.001) continue
          const g = new PIXI.Graphics()
          for (const b of at) {
            g.ellipse(b.c.x - ext.x0, b.c.y - ext.y0, Math.max(1, b.rx), Math.max(1, b.ry))
          }
          g.fill({ color: 0xffffff, alpha: step })
          c.addChild(g)
        }
        if (c.children.length === 0) {
          c.destroy({ children: true })
          return null
        }
        if (feather > 0) c.filters = [new PIXI.BlurFilter({ strength: feather, quality: 4 })]
        const rt = PIXI.RenderTexture.create({ width: w, height: h, antialias: false })
        app.renderer.render({ container: c, target: rt, clear: true })
        c.destroy({ children: true })
        const sp = new PIXI.Sprite(rt)
        sp.position.set(ext.x0, ext.y0)
        return sp
      }

      function blobMask(blobs: readonly PaintBlob[]): Graphics {
        const g = new PIXI.Graphics()
        for (const b of blobs) g.ellipse(b.c.x, b.c.y, Math.max(1, b.rx), Math.max(1, b.ry))
        g.fill(0xffffff)
        return g
      }

      /**
       * The lane network as a mask — the SAME shape the clearance rules
       * reserved, not a round stroke over it.
       *
       * iso-layout's occupancy field treats each lane sample as an ellipse
       * with y-radius `half * LANE_PAINT_SQUASH`, because a circle on the
       * ground projects flattened on a 2:1 screen. Painting a round stroke
       * instead lays 39% more road in y than was ever reserved, and every
       * structure the rules cleared against the ellipse can then be standing
       * on it. The path is drawn with y pre-divided by the squash and the
       * whole mask scaled back down, which reproduces the union of ellipses
       * exactly rather than approximating it.
       */
      function laneMask(scene: IsoScene, only?: string): Graphics {
        const g = new PIXI.Graphics()
        const s = LANE_PAINT_SQUASH
        for (const lane of scene.layout.lanes) {
          if (only !== undefined && lane.surface !== only) continue
          for (const run of lane.runs) {
            if (run.length < 2) continue
            g.moveTo(run[0].x, run[0].y / s)
            for (let i = 1; i < run.length; i++) g.lineTo(run[i].x, run[i].y / s)
            g.stroke({ width: lane.width, color: 0xffffff, cap: 'round', join: 'round' })
          }
        }
        g.scale.set(1, s)
        return g
      }

      /**
       * The whole ground, baked once into ONE RenderTexture.
       *
       * Order is the reference's (compose.py, and world-capture/raster.py's
       * build_ground which mirrors it): sand ring, grass, meadow shading,
       * mottle, water, THE LANES, then the paving and the tillage over them,
       * and the timber deck last. The lanes go down before the paving because
       * a road runs UNDER a paved square and out the other side; laying them
       * after made the road stop dead at the plaza edge.
       * Baking into a single texture is what makes an expensive
       * computed ground affordable — it is paid on a state change, never per
       * frame, through the statics cache that already exists.
       */
      function buildIsoTerrain(scene: IsoScene): void {
        const { space, layout } = scene
        const coast = layout.coast
        const seed = layout.seed >>> 0
        const c = new PIXI.Container()
        const regionsOf = (kind: string) => layout.paint.filter((r) => r.kind === kind)
        const landExt: Extent = { x0: 0, y0: 0, x1: space.w, y1: space.h }

        // 1. the beach ring, OUTSIDE the land mask — the waterline reads as sand
        paintClass(c, 'sand', seed, landExt, rasterMask(coast.beach, coast.mw, coast.mh, coast.step))
        // 2. the island itself
        paintClass(c, 'grass', seed, landExt, rasterMask(coast.land, coast.mw, coast.mh, coast.step))
        // 3. meadow shading — what the ground LOOKS like, not what it IS
        //
        // MAX, NOT SUM, and getting that wrong is visible. A blob's `w` is the
        // reference's per-blob mask VALUE (compose.py:148 fill 110..210), so
        // where two patches overlap the mask is the BRIGHTER of the two — which
        // is what raster.py does (ImageChops.lighter) and what the offline
        // still therefore shows. Compositing one masked sprite per alpha bucket
        // over another sums instead: two 0.5 patches read 0.75, so every
        // overlap draws a dark seam and the patches outline each other.
        //
        // That max identity now lives INSIDE the mask (featheredBlobMask) so
        // the region is one soft-edged shape painted once, rather than twenty
        // hard-edged ones stacked. The dark grass goes down at full strength
        // through it, exactly as the reference pastes GRASS2 through its
        // blurred patch mask.
        const meadowFeather = PAINT_FEATHER.meadow_dark ?? 0
        for (const r of regionsOf('meadow_dark')) {
          const mask = featheredBlobMask(r.blobs, meadowFeather)
          if (!mask) continue
          paintClass(c, 'grass_dark', seed, blobExtent([r], meadowFeather * 3), mask)
        }
        // 4. mottle: three flat tones at the reference's own alphas
        const mottleG = new PIXI.Graphics()
        for (const r of regionsOf('mottle')) {
          const tone = MOTTLE_TONES[r.tone ?? 0]
          for (const b of r.blobs) {
            mottleG
              .ellipse(b.c.x, b.c.y, Math.max(1, b.rx), Math.max(1, b.ry))
              .fill({ color: (tone[0] << 16) | (tone[1] << 8) | tone[2], alpha: (tone[3] / 255) * (b.w ?? 1) })
          }
        }
        c.addChild(mottleG)
        // 5. the pond: its sand bank first, then the water and the outflow
        for (const [kind, cls] of [
          ['pond_bank', 'sand'],
          ['pond', 'sea'],
          ['stream', 'sea'],
        ] as const) {
          const rs = regionsOf(kind)
          const blobs = rs.flatMap((r) => r.blobs)
          if (blobs.length === 0) continue
          paintClass(c, cls, seed, blobExtent(rs), blobMask(blobs))
        }
        // 6. the lanes, laid BEFORE the paving. The runs are already clipped to
        // land, but the painted band has a width, so the surface is cut to the
        // coastline as well — otherwise a road along the shore is on the sea.
        //
        // ORDER IS THE DEFECT, NOT THE SHAPE (Captain, 2026-07-27: "the road —
        // can you put it beneath the centre concrete?"). Painting the lanes
        // after the plaza laid a dirt band ACROSS the paved square, so the road
        // read as ending there instead of running under it and out the other
        // side. compose.py:351/362 and world-capture/raster.py:388/391 both lay
        // the lanes first and the paving on top, and this path was the only one
        // of the three that did not.
        // PAINTED IN THE MATERIAL THE ROAD LADDER SAYS, one mask per surface.
        // The rung names (dirt_path / dirt_worn / gravel_road / cobbled_road)
        // are materials, and since 2026-07-27 they are the ONLY thing that rung
        // controls — a lane's width is its own destination's traffic now
        // (iso-layout/lanes.ts). Painting the network as bare dirt here would
        // leave the org's road maturity with no way onto the live frame while
        // the offline still showed it, which is the two-renderers-one-world
        // rule broken in the direction nobody would notice.
        const lanes = new PIXI.Container()
        const surfaces = [...new Set(scene.layout.lanes.map((l) => l.surface))].sort()
        for (const surface of surfaces) {
          paintClass(lanes, ROAD_GROUND[surface] ?? 'dirt', seed, landExt, laneMask(scene, surface))
        }
        const landCut = rasterMask(coast.land, coast.mw, coast.mh, coast.step)
        lanes.addChild(landCut)
        lanes.mask = landCut
        c.addChild(lanes)
        // 7. the square and the tillage, over the lanes
        for (const [kind, cls] of [
          ['plaza', 'cobble'],
          ['ploughed', 'ploughed'],
          ['crop', 'crop'],
        ] as const) {
          const rs = regionsOf(kind)
          const blobs = rs.flatMap((r) => r.blobs)
          if (blobs.length === 0) continue
          paintClass(c, cls, seed, blobExtent(rs), blobMask(blobs))
        }
        // 8. the wharf deck and the finger pier — TIMBER over water, so neither
        // cut to land nor painted with a ground class. Painting them with the
        // lane's 'dirt' is what made the harbour read as a road walking into
        // the sea (Captain, 2026-07-27); iso-quay.ts is the port of the
        // reference's quay.py, the same deck world-capture/raster.py:417 draws.
        const hb = layout.harbour
        const deckRects: DeckRect[] = [
          ...(hb?.wharf && hb.wharf.shore.length > 1
            ? deckStripRects(hb.wharf.shore, hb.wharf.depth, seed + 3)
            : []),
          ...(hb?.jetty ? jettyDeckRects(hb.jetty.at, hb.jetty.end, hb.jetty.width, seed + 11) : []),
          // AND THE PILINGS, which the port did not have: raster.py:418 has
          // called quay.posts since it was written, so the offline still showed
          // a wharf standing on legs and the live engine showed a deck floating
          // on the sea. Measured on a fresh hamlet capture: 3 wharf and 6 jetty
          // pilings the engine never drew. They go AFTER the deck so a post
          // head reads as sitting under the front edge.
          ...(hb?.wharf && hb.wharf.shore.length > 1
            ? wharfPostRects(hb.wharf.shore, hb.wharf.depth, seed + 5)
            : []),
          ...(hb?.jetty ? jettyPostRects(hb.jetty.at, hb.jetty.end, hb.jetty.width, seed + 11) : []),
        ]
        if (deckRects.length > 0) {
          // grouped by colour so the whole deck is a handful of fills rather
          // than one per plank pixel
          const byColour = new Map<number, DeckRect[]>()
          for (const r of deckRects) {
            const at = byColour.get(r.color)
            if (at) at.push(r)
            else byColour.set(r.color, [r])
          }
          const deck = new PIXI.Graphics()
          for (const [colour, rects] of byColour) {
            for (const r of rects) deck.rect(r.x, r.y, r.w, r.h)
            deck.fill(colour)
          }
          c.addChild(deck)
        }

        const rt = PIXI.RenderTexture.create({ width: space.w, height: space.h })
        app.renderer.render({ container: c, target: rt })
        c.destroy({ children: true })
        const ground = new PIXI.Sprite(rt)
        terrainLayer.addChild(ground)
      }

      /**
       * Every sprite the scene resolved, at its base centre, depth-sorted by
       * base y on the propLayer the engine already sorts.
       *
       * The anchor is (0.5, 1) and nothing else: all 163 pack frames anchor at
       * their base centre, which is exactly what that anchor means. Size is set
       * from the pack's dw/dh — never from `scale`, which disagrees on 28 of
       * them.
       */
      function buildIsoSprites(scene: IsoScene, pack: IsoPack, atlas: Texture): void {
        for (const s of scene.sprites) {
          const f = pack.frames[s.frame]
          if (!f) continue // unreachable: buildIsoScene already reported it
          const key = `iso|${s.frame}`
          let tex = cutCache.get(key)
          if (!tex) {
            tex = new PIXI.Texture({
              source: atlas.source,
              frame: new PIXI.Rectangle(f.x, f.y, f.w, f.h),
            })
            cutCache.set(key, tex)
          }
          const sp = new PIXI.Sprite(tex)
          sp.anchor.set(0.5, 1)
          sp.setSize(s.dw, s.dh)
          sp.position.set(s.x, s.y)
          sp.scale.x = s.flip ? -Math.abs(sp.scale.x) : Math.abs(sp.scale.x)
          sp.zIndex = s.depth
          propLayer.addChild(sp)
          // The shadow IS the footprint: the pack's own ground diamond, in the
          // corpus slate the top-down world already casts.
          const g = groundDiamond(s.dw, s.dh)
          staticShadowG
            .ellipse(s.x, s.y - g.depth / 2, g.hw, g.depth / 2)
            .fill({ color: FOOT_SLATE, alpha: 0.22 })
        }
      }

      function staticsKey(p: EngineCanvasProps): string {
        const tier = lodTier(p.camera.z)
        const fp = LOD_RULES[tier].buildingsAsFootprints ? 'fp' : 'full'
        const geoKey = p.geo.islands.map((i) => `${i.id}:${i.r}`).join('|')
        const bKey = p.buildings.map((b) => `${b.id}:${b.rungName}`).join('|')
        // dressing inputs beyond buildings: lantern-post ladder rungs
        const posts = `${p.resolution?.elements.lantern_posts?.rungName ?? ''}·${p.resolution?.elements.posts_lit?.rungName ?? ''}`
        // direction surface: course lines / stamps / the voyage boat are
        // STATE-pure statics — a payload change rebuilds them (no per-tick
        // motion; the arrival is what replay renders).
        const courseKey = Object.entries(p.courses ?? {})
          .map(([l, c]) => `${l}:${c.state}:${c.portCallDates.length}`)
          .sort()
          .join(',')
        const voyKey = p.voyage?.underway
          ? `voy:${p.voyage.lane}:${p.voyage.progress.toFixed(3)}`
          : 'moored'
        const ct = p.chartTable ? 'ct1' : 'ct0'
        if (isIso) {
          // The iso scene is a function of the WHOLE resolution, not just the
          // buildings the top-down path reads, so the key is the whole rung
          // set. It deliberately does NOT carry the LOD tier: the iso path has
          // no footprint tier this round, and keying on one would re-bake the
          // computed ground on every zoom crossing for no change in output.
          const st = layoutStateFrom(p.resolution)
          const rungs = Object.entries(st.stages ?? {})
            .map(([k, v]) => `${k}:${v}`)
            .sort()
            .join(',')
          const counts = Object.entries(st.counts ?? {})
            .map(([k, v]) => `${k}=${v}`)
            .sort()
            .join(',')
          return `iso·${st.era}·${st.road}·${rungs}·${counts}`
        }
        return `${fp}·${geoKey}·${bKey}·${posts}·${ct}·${courseKey}·${voyKey}`
      }

      /** The composed scene for the current state, rebuilt with the statics. */
      let isoScene: IsoScene | null = null
      let isoIssued = false
      let isoUnmeasuredIssued = false

      function rebuildIsoStatics(p: EngineCanvasProps) {
        if (!isoPack || !isoAtlas) {
          // Loud already (the badge is raised at boot); draw nothing rather
          // than invent art. The ground still needs the layout, so compose it.
          isoScene = null
          return
        }
        // AN UNFED RENDERER AND A DAY-ZERO CABINET DRAW THE SAME ISLAND, so the
        // difference has to be said out loud — see UNMEASURED_STATE_ISSUE. It is
        // raised ONCE and then only again after a real resolution has arrived
        // and gone away, so a page that never authenticates badges once rather
        // than every poll.
        const unmeasured = unmeasuredIssues(p.resolution)
        if (unmeasured.length > 0) {
          if (!isoUnmeasuredIssued) {
            isoUnmeasuredIssued = true
            for (const i of unmeasured) console.error('[world/engine] iso scene:', i)
            propsRef.current.onIssues?.(unmeasured)
          }
        } else {
          isoUnmeasuredIssued = false
        }
        const state: LayoutState = layoutStateFrom(p.resolution)
        // The seed is the deployment's own island: same org, same island,
        // forever. `geo.canvas` is the top-down world's size and plays no part.
        const scene = buildIsoScene(isoPack, state, ISO_SEED)
        isoScene = scene
        buildIsoTerrain(scene)
        buildIsoSprites(scene, isoPack, isoAtlas)
        if (scene.issues.length && !isoIssued) {
          isoIssued = true
          for (const i of scene.issues) console.error('[world/engine] iso scene:', i)
          propsRef.current.onIssues?.(scene.issues)
        }
      }

      function rebuildStatics(p: EngineCanvasProps) {
        clearStatics()
        if (isIso) {
          rebuildIsoStatics(p)
          return
        }
        buildTerrain(p)
        if (LOD_RULES[lodTier(p.camera.z)].buildingsAsFootprints) {
          buildFootprints(p)
        } else {
          buildBuildings(p)
          buildDressing(p)
        }
      }

      function placeholderBuildings(p: EngineCanvasProps) {
        placeholderG.clear()
        if (isIso) return // the iso path draws no tile-space building boxes
        if (LOD_RULES[lodTier(p.camera.z)].buildingsAsFootprints) return
        for (const b of p.buildings) {
          if (buildingSprites.has(b.id)) continue
          if (STAGED_VOCAB_ELEMENTS.has(b.element) || b.element === 'lighthouse') continue
          placeholderG
            .rect(b.x * TD, b.y * TD, b.w * TD, b.h * TD)
            .fill({ color: 0x39415a, alpha: 0.7 })
          placeholderG
            .rect(b.x * TD, b.y * TD, b.w * TD, b.h * TD)
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

      /** One pooled character sprite (LimeZu Premade sheet frame). */
      function characterSprite(
        key: string,
        slug: string,
        anim: 'work' | 'walk' | 'idle',
        facing: CharFacing,
        tick: number,
        wx: number,
        wy: number,
        opts?: { alpha?: number; scale?: number }
      ): boolean {
        const sheet = characterSheetFor(slug)
        const cut = charFrame(anim === 'idle' ? 'work' : anim, facing, tick, fnv1a(slug) % 6)
        const tex = texFor(sheet, {
          x: cut.x,
          y: cut.y,
          w: CHAR_FRAME_W,
          h: CHAR_FRAME_H,
        })
        if (!tex) return false
        const sp = pooled(key, () => new PIXI.Sprite())
        if (sp instanceof PIXI.Sprite) {
          sp.texture = tex
          sp.anchor.set(0.5, 1)
          sp.position.set(wx * TD, wy * TD)
          sp.zIndex = wy * TD
          sp.alpha = opts?.alpha ?? 1
          sp.scale.set(opts?.scale ?? 1)
        }
        // cozy pass #13: figures cast dither shadows too (dynamic half)
        drawShadow(dynShadowG, key, wx * TD, wy * TD, 11)
        return true
      }

      /** Cutaway interior: real floor/wall/desks (Room_Builder + office
       * singles — v1a fix: no more 1-tile colored slivers on a brown box). */
      function interiorContainer(b: WorldBuilding, slugs: string[]): void {
        const c = pooled(`interior:${b.id}`, () => {
          const cont = new PIXI.Container()
          const floorTex = texFor(ROOM_SHEET, FLOOR_CUT)
          const wallTex = texFor(ROOM_SHEET, WALL_CUT)
          if (floorTex) {
            const floor = new PIXI.TilingSprite({
              texture: floorTex,
              width: b.w * TD - 4,
              height: b.h * TD - 4,
            })
            floor.position.set(b.x * TD + 2, b.y * TD + 2)
            cont.addChild(floor)
          } else {
            const g = new PIXI.Graphics()
            g.rect(b.x * TD + 2, b.y * TD + 2, b.w * TD - 4, b.h * TD - 4).fill(0x8a6a48)
            cont.addChild(g)
          }
          if (wallTex) {
            const wall = new PIXI.TilingSprite({
              texture: wallTex,
              width: b.w * TD - 4,
              height: TD,
            })
            wall.position.set(b.x * TD + 2, b.y * TD + 2)
            cont.addChild(wall)
          }
          // desks: one per officer slot (same grid officerPositions uses)
          slugs.forEach((slug, i) => {
            const deskTex = texFor(deskSheetFor(slug))
            if (!deskTex) return
            const col = i % 3
            const row = Math.floor(i / 3)
            const d = new PIXI.Sprite(deskTex)
            d.anchor.set(0.5, 1)
            d.position.set(
              (b.x + 1 + col * ((b.w - 2) / 2.5)) * TD,
              (b.y + 1.3 + row * 1.6) * TD
            )
            cont.addChild(d)
          })
          cont.zIndex = b.y * TD + 1
          return cont
        })
        c.zIndex = b.y * TD + 1
      }

      /**
       * The one dynamic the iso path draws this round: the lighthouse lamp.
       *
       * WHY ONLY THIS. Every other dynamic in drawDynamics — officers, commute
       * walkers, site crews, fauna, chimney smoke, lane-site buoys, window
       * glows, the cutaway — is placed in TILE space against the top-down
       * geometry, and the iso world is not that world. Drawing them here would
       * put a walker in open sea and call it a feature. They are named as
       * ABSENT in the port's own report rather than approximated; the LIFE
       * layer's own port is a separate step with its own risks.
       *
       * The lamp is different, and it is here because it is the biggest visual
       * event in the world's life: the layout already computes LAMP_AT in the
       * same space the scene draws in, and it already refuses to light a lamp
       * that has no tower to sit in. The glow rides fxG, which is added to the
       * stage ABOVE the ambience veil — so warm light cuts through the night
       * grade instead of being dithered away by it.
       */
      function drawIsoDynamics(): void {
        dynG.clear()
        dynShadowG.clear()
        const lamp = isoScene?.lamp
        if (lamp) {
          drawGlow(fxG, 'iso:lamp', lamp.x, lamp.y, 54)
          fxG.rect(lamp.x - 4, lamp.y - 4, 8, 8).fill({ color: GLOW_CORE })
        }
      }

      function drawDynamics(p: EngineCanvasProps) {
        dynG.clear()
        dynShadowG.clear()
        const tier = lodTier(p.camera.z)
        const rules = LOD_RULES[tier]
        const bucket = bucketOf(p.clockHour)
        const dark = bucket === 'night' || bucket === 'dusk'

        // cutaway: roof alpha per building; REAL interior under the fade
        const slugs = Object.keys(p.officers).sort()
        for (const b of p.buildings) {
          const sp = buildingSprites.get(b.id)
          const a = rules.cutawayEligible ? roofAlpha(p.cutaway, b.id, p.tick) : 1
          if (sp) sp.alpha = a
          if (a < 0.95 && b.interior) interiorContainer(b, slugs)
          // pending rung: honest worksite cone (visible-work seam)
          if (b.pending && !rules.buildingsAsFootprints) {
            const coneTex = texFor(WORKSITE_KIT.cone)
            if (coneTex) {
              const cone = pooled(`pend:${b.id}`, () => new PIXI.Sprite())
              if (cone instanceof PIXI.Sprite) {
                cone.texture = coneTex
                cone.anchor.set(0.5, 1)
                cone.position.set((b.x + 0.5) * TD, (b.y + 0.2) * TD)
                cone.zIndex = (b.y + 0.2) * TD
              }
            }
          }
        }

        // officers: REAL character sprites (walk/idle frames; dimmed away)
        if (rules.officers) {
          for (const o of officerPositions(p)) {
            const pres = p.officers[o.slug]
            const live = Boolean(pres?.present)
            characterSprite(`officer:${o.slug}`, o.slug, 'work', 'down', p.tick, o.x, o.y, {
              alpha: live ? 1 : 0.4,
            })
          }
        }

        // ── T2 LIFE: commute walkers + bubbles, sites + crews, apprentices ──
        if (rules.officers && p.life) {
          for (const cm of p.life.commuters) {
            const t = cm.walk.to === 'quay' ? cm.progress : 1 - cm.progress
            const pos = roadPoint(t)
            const facing: CharFacing = cm.walk.to === 'quay' ? 'down' : 'up'
            characterSprite(
              `walker:${cm.slug}`,
              cm.slug,
              'walk',
              cm.glance ? 'left' : facing,
              p.tick,
              pos.x + 0.5,
              pos.y + 1
            )
            // the verb-icon PIXEL bubble (grammar v3 bubble law)
            if (cm.walk.bubble) {
              const iconTex = texFor(UI_SHEET, verbIconCut(cm.walk.bubble.verb))
              const bub = pooled(`bubble:${cm.slug}`, () => {
                const cont = new PIXI.Container()
                const g = new PIXI.Graphics()
                g.roundRect(0, 0, 20, 16, 3).fill(0xf4efe2).stroke({ width: 1, color: FOOT_SLATE })
                g.poly([6, 16, 10, 16, 6, 21]).fill(0xf4efe2)
                cont.addChild(g)
                return cont
              })
              if (iconTex && bub.children.length < 2) {
                const ic = new PIXI.Sprite(iconTex)
                ic.position.set(3, 2)
                bub.addChild(ic)
              }
              bub.position.set((pos.x + 0.9) * TD, (pos.y - 1.6) * TD)
              bub.zIndex = 100000 // bubbles float over the scene
            }
          }
          for (const s of p.life.sites) {
            const f = s.site.footprint
            const siteC = pooled(`site:${s.site.id}`, () => {
              const cont = new PIXI.Container()
              const groundTex = texFor(WORKSITE_KIT.ground)
              if (groundTex) {
                for (let ty = 0; ty < f.h; ty++) {
                  for (let tx = 0; tx < f.w; tx++) {
                    const g = new PIXI.Sprite(groundTex)
                    g.position.set((f.x + tx) * TD, (f.y + ty) * TD)
                    cont.addChild(g)
                  }
                }
              }
              const fenceA = texFor(WORKSITE_KIT.fenceA)
              const fenceB = texFor(WORKSITE_KIT.fenceB)
              for (const pt of lotPerimeter(f)) {
                const h = fnv1a(`sitefence:${s.site.id}:${pt.x},${pt.y}`)
                const tex = (h & 1) === 0 ? fenceA : fenceB
                if (!tex) continue
                const fs = new PIXI.Sprite(tex)
                fs.anchor.set(0.5, 1)
                fs.position.set(pt.x * TD + TD / 2, (pt.y + 1) * TD)
                cont.addChild(fs)
              }
              const signTex = texFor(WORKSITE_KIT.sign)
              if (signTex) {
                const sg = new PIXI.Sprite(signTex)
                sg.anchor.set(0.5, 1)
                sg.position.set((f.x + 0.5) * TD, (f.y + f.h + 0.6) * TD)
                cont.addChild(sg)
              }
              cont.zIndex = (f.y + f.h) * TD
              return cont
            })
            siteC.zIndex = (f.y + f.h) * TD
            // crew figures: decorative-honest wrights (staging of a real
            // witnessed transition; the sign codex says exactly that)
            for (const w of s.crew) {
              characterSprite(
                `wright:${w.id}`,
                w.id,
                'walk',
                w.facing,
                p.tick,
                w.x,
                w.y,
                { scale: 1 }
              )
            }
          }
          for (const fig of p.life.apprentices.figures) {
            characterSprite(
              `apprentice:${fig.id}`,
              fig.id,
              'walk',
              'down',
              p.tick,
              fig.x,
              fig.y,
              { scale: 0.75, alpha: 0.95 }
            )
          }
          // ── fauna (cozy pass: first art landed — grammar staged flipped
          //    for dog/chicken_flock/fish; staged species never reach here,
          //    engine-client drops them at grammar parse) ─────────────────
          for (const fa of p.life.fauna) {
            let tex: Texture | null = null
            let flipX = false
            if (fa.kind === 'dog') {
              tex = texFor(DOG_SHEET, dogSleepCut(fa.frame))
              flipX = fa.facing === 'right'
            } else if (fa.kind === 'chicken') {
              const { anim, sub } = chickenAnimOf(fa.frame)
              tex = texFor(
                CHICKEN_SHEETS[fnv1a(fa.id) % CHICKEN_SHEETS.length],
                chickenCut(anim, sub)
              )
              flipX = fa.facing === 'right' // pack art faces left
            } else if (fa.kind === 'fish') {
              tex = texFor(FISH_SHEET, FISH_CUTS[fa.frame % FISH_CUTS.length])
              flipX = fa.facing === 'left'
            }
            if (!tex) continue
            const sp = pooled(`fauna:${fa.id}`, () => new PIXI.Sprite())
            if (sp instanceof PIXI.Sprite) {
              sp.texture = tex
              sp.anchor.set(0.5, 1)
              sp.position.set(fa.x * TD, fa.y * TD)
              sp.zIndex = fa.y * TD
              sp.scale.x = flipX ? -1 : 1
            }
            if (fa.layer === 'ground') {
              drawShadow(dynShadowG, fa.id, fa.x * TD, fa.y * TD, fa.kind === 'dog' ? 20 : 8)
            }
          }
        }

        // chimney smoke over the lived-in Great House while officers are
        // present (cozy pass #14 — decorative-honest, pure f(id, tick))
        if (!rules.buildingsAsFootprints) {
          const gh = p.buildings.find((b) => b.element === 'great_house')
          const anyPresent = Object.values(p.officers).some((o) => o.present)
          if (gh && anyPresent) {
            const cx = (gh.x + gh.w * 0.78) * TD
            const cy = (gh.y + 0.4) * TD
            for (const puff of smokePuffs(gh.id, p.tick)) {
              dynG.rect(cx + puff.x, cy + puff.y, puff.r, puff.r).fill({ color: puff.color })
            }
          }
        }

        // lane sites: buoys + isle docks/warehouses + mist pockets
        for (const site of p.geo.laneSites) {
          const px = site.cx * TD
          const py = site.cy * TD
          if (site.render === 'reef_buoy') {
            dynG.circle(px, py, 5).fill({ color: 0xc63228 })
            dynG.circle(px, py, 5).stroke({ width: 1, color: 0x35110d })
            dynG.circle(px, py + 8, 7).stroke({ width: 1, color: MIST_GREY })
          } else if (site.render === 'mist_reserved') {
            // OPAQUE corpus-grey dither (alpha blends leave the palette)
            for (const d of mistDots(site.slot)) {
              dynG.rect(px + d.x, py + d.y, d.r, d.r).fill({ color: MIST_GREY })
            }
            dynG.circle(px, py, 4).fill({ color: MIST_GREY }) // grey buoy (dual-code)
          } else if (site.render === 'isle') {
            // dock jetty marker; warehouses at ring r1 (corpus browns)
            dynG
              .rect(px - 10, py + (site.cy < 100 ? 12 : -14), 20, 5)
              .fill({ color: PLANK_BROWN })
            if (site.ringRung >= 2 && !rules.buildingsAsFootprints) {
              dynG.rect(px - 8, py - 6, 14, 10).fill({ color: PLANK_BROWN })
              dynG.rect(px - 8, py - 10, 14, 5).fill({ color: FOOT_SLATE })
            }
          }
        }

        // light masses — DUSK/NIGHT ONLY (day glows read foreign at noon).
        // Cozy pass: pools are OPAQUE seeded glow dither (in-bin warm hues,
        // density falloff) — alpha fills left the palette on every capture.
        if (dark) {
          if (rules.lightMassAggregate) {
            const live = Object.values(p.officers).filter((o) => o.present).length
            const main = p.geo.islands.find((i) => i.id === 'main')
            if (main && live > 0) {
              drawGlow(fxG, 'mass:main', main.cx * TD, main.cy * TD, (14 + live * 5) * 2)
            }
            for (const site of p.geo.laneSites) {
              if (site.render !== 'isle') continue
              drawGlow(fxG, `mass:${site.slot}`, site.cx * TD, site.cy * TD, 24)
            }
          } else {
            // window-glow lamp pools per lived-in building (island tier+)
            for (const b of p.buildings) {
              if (!b.interior) continue
              const wx = (b.x + 0.9) * TD
              const wy = (b.y + b.h * 0.55) * TD
              drawGlow(fxG, `win:${b.id}`, wx, wy, 12)
              fxG.rect(wx - 3, wy - 3, 6, 6).fill({ color: GLOW_CORE })
              if (b.w >= 4) {
                const wx2 = (b.x + b.w - 0.9) * TD
                drawGlow(fxG, `win2:${b.id}`, wx2, wy, 9)
                fxG.rect(wx2 - 2, wy - 3, 5, 5).fill({ color: GLOW_CORE })
              }
            }
          }
        }
        // the lighthouse lamp: LIT only when cells_graduated > 0 (honest 0).
        // Lit = the ratified derived lit variant (lamp-room glass in the
        // proven warm hue) + a glow pool — the biggest visual event in the
        // world's life, and never a minute earlier.
        const lamp = p.resolution?.elements.lighthouse_lamp
        const lh = p.buildings.find((b) => b.element === 'lighthouse')
        if (lh && lamp && lamp.rungName === 'lit') {
          const sp = buildingSprites.get(lh.id)
          const litCut = lighthouseCutFor(lh.rungName)
          const litTex = litCut ? texFor(LIGHTHOUSE_LIT_SHEET, litCut) : null
          if (sp && litTex) sp.texture = litTex
          drawGlow(fxG, 'lh:pool', (lh.x + lh.w / 2) * TD, lh.y * TD, 40)
        }
        sweepPool()
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
        // rain/storm: deterministic seeded drops (pure f(tick)) — v1a fix:
        // the sky must TELL the story (denser, longer, near-camera layer)
        if (kind === 'rain' || kind === 'storm') {
          const drops = rainDrops(p.tick, kind === 'storm' ? 340 : 220, vw, vh)
          for (let i = 0; i < drops.length; i++) {
            const d = drops[i]
            const near = i % 4 === 0 // near-camera streak layer
            weatherG
              .moveTo(d.x, d.y)
              .lineTo(d.x - (near ? 4 : 2), d.y + d.len * (near ? 6 : 4))
              .stroke({
                width: near ? 2 : 1,
                color: 0xb8cbe0,
                alpha: kind === 'storm' ? (near ? 0.8 : 0.6) : near ? 0.7 : 0.5,
              })
          }
          weatherG.rect(0, 0, vw, vh).fill({ color: 0x1a2230, alpha: kind === 'storm' ? 0.3 : 0.18 })
        }
        // ambient day/night VEIL (screen-space, from the server-stamped
        // clock): opaque in-bin dither instead of the old alpha wash — the
        // whole frame (open sea included) darkens/warms palette-natively.
        const veil = VEIL[bucket]
        if (veil) {
          veilSprite.texture = veilTexture(veil.colors, veil.coverage)
          veilSprite.width = vw
          veilSprite.height = vh
          veilSprite.visible = true
        } else {
          veilSprite.visible = false
        }
        seaSprite.tint = 0xffffff // the veil owns ambience now — never tint
        // killswitch red wash — SCREEN-space (the storm is the whole sky),
        // dual-coded with the DOM banner
        if (p.killswitch) weatherG.rect(0, 0, vw, vh).fill({ color: 0xcc2222, alpha: 0.14 })
      }

      function draw(p: EngineCanvasProps) {
        const key = staticsKey(p)
        if (key !== builtKey) {
          builtKey = key
          rebuildStatics(p)
        }
        // ONE viewport source of truth: renderer px, converted at the DOM edge
        // by Pixi itself. clientWidth and getBoundingClientRect() used to feed
        // the same math from two other places.
        const vw = app.renderer.width
        const vh = app.renderer.height
        // The camera is a PURE SCALE + TRANSLATE over the one world Container,
        // in both kernels: iso is applied per object at placement, never as a
        // matrix on the container (that would shear every sprite, and the
        // pack's sprites are already drawn in isometric).
        const s = worldScale(proj, p.camera.z)
        const t = cameraTranslation(proj, p.camera, { w: vw, h: vh })
        world.scale.set(s)
        world.position.set(t.x, t.y)
        // the glow layer tracks the world transform (it lives above the
        // screen-space veil so warm light cuts through the night dither)
        fxG.scale.set(s)
        fxG.position.copyFrom(world.position)
        // the open sea scrolls with the world (screen-space tiling). The
        // pattern scale floors at 0.75: at archipelago zoom a 1:1 scale
        // shrinks the wave dashes below a pixel and the sea collapses into
        // one flat dominant mass (CLUSTER_FLAT_VOID) — the floor keeps the
        // corpus wave texture readable at every LOD.
        seaSprite.width = vw
        seaSprite.height = vh
        seaSprite.tileScale.set(Math.max(s, 0.75))
        seaSprite.tilePosition.set(world.position.x, world.position.y)
        placeholderBuildings(p)
        const bucket = bucketOf(p.clockHour)
        drawWeather(p, bucket) // clears fxG first
        if (isIso) drawIsoDynamics() // then the lamp is composited onto fxG
        else drawDynamics(p) // …or the whole top-down dynamic layer is
      }

      /**
       * The iso pick: the scene's own sprites, front to back, on the SHARED
       * ground diamond.
       *
       * WHY IT CANNOT REUSE ANYTHING ABOVE. Under iso a sprite's position is a
       * layout PIXEL, not a tile: buildIsoSprites does `sp.position.set(s.x,
       * s.y)` straight from composeLayout. `screenToWorld` returns TILES,
       * because that is what the camera and the top-down world speak — so the
       * one conversion here is `proj.project(tx, ty)`, which is the same kernel
       * the camera projects with, run forward. project() is linear, so
       * project(tile) is the absolute layout px of that tile and no camera term
       * is needed twice.
       *
       * THE DIAMOND IS THE ONE IN ../lib/world/projection, the same geometry
       * the placement rules cleared against and checks/world_checks.py judges —
       * a fifth definition of where a sprite stands is the defect that file's
       * header records paying for. Front to back is the reverse of the depth
       * sort buildIsoScene already did, so the thing the eye sees on top is the
       * thing the pointer gets.
       *
       * DECORATION DOES NOT ABSORB THE CLICK. A sprite with no state role — a
       * tree, a barrel, a buoy — is skipped rather than answered, so a bush
       * standing in front of the library does not turn the library into
       * "ground". What answers is the front-most sprite that a STATE RULE
       * entitled, and when nothing does, `ground` says so plainly.
       */
      function isoHitTarget(tx: number, ty: number): EngineTarget {
        const scene = isoScene
        const GROUND: EngineTarget = { kind: 'ground', id: 'ground' }
        if (!scene) return GROUND
        const px = proj.project(tx, ty)
        const p = propsRef.current
        const s = pickIsoSprite(scene, px.x, px.y)
        if (!s) return GROUND
        // the two stations that are their own card, not a building row
        if (s.frame === 'mailbox') return { kind: 'mailbox', id: 'mailbox' }
        if (s.frame === 'chart_table' && p.chartTable) {
          return { kind: 'chart_table', id: 'chart-table' }
        }
        // A LADDER ROLE IS A BUILDING ROW BY ITS `element`, never by its id.
        // The engine's building ids are its own; the ladder object is the name
        // both sides already agree on (WorldBuilding.element), so the card that
        // opens is about the same measurement the sprite drew.
        const b = p.buildings.find((bb) => bb.element === s.role)
        if (b) return { kind: 'building', id: b.id }
        // A role the top-down building table has no row for is real and
        // measured but has no card yet. Answering `ground` is the honest reply
        // — better than opening a neighbour's card.
        return GROUND
      }

      function hitTarget(ev: MouseEvent): EngineTarget | null {
        const rect = app.canvas.getBoundingClientRect()
        const p = propsRef.current
        const s = p.camera.z
        // THE one inverse — the same kernel the camera projects with, so a
        // click can never land where the eye did not.
        const view = { w: app.renderer.width, h: app.renderer.height }
        const w = screenToWorld(proj, ev.clientX - rect.left, ev.clientY - rect.top, p.camera, view)
        const wx = w.x
        const wy = w.y
        // UNDER ISO THE PICK IS ITS OWN, because the world is its own.
        //
        // Every target below is a tile-space tolerance against the TOP-DOWN
        // geometry — building bboxes, the crossroads mailbox, lane-site
        // circles, the road walk. The iso world is not that world: its
        // buildings stand where composeLayout put them, in the compositor's
        // pixel space. Running these tests against an iso pointer would open
        // the inspect card for whatever top-down building happened to occupy
        // the coordinate, which is a card asserting something false about the
        // org. So the iso path answers from the SCENE it actually drew.
        if (isIso) return isoHitTarget(wx, wy)
        // officers first (small, on top)
        if (LOD_RULES[lodTier(s)].officers) {
          for (const o of officerPositions(p)) {
            if (Math.abs(wx - o.x) < 0.8 && Math.abs(wy - o.y + 0.3) < 1) {
              return { kind: 'officer', id: o.slug }
            }
          }
          // commute walkers inspect as their officer (the walk is presence
          // animation of a real verb shift — the card cites the mechanism)
          if (p.life) {
            for (const cm of p.life.commuters) {
              const t = cm.walk.to === 'quay' ? cm.progress : 1 - cm.progress
              const pos = roadPoint(t)
              if (Math.abs(wx - (pos.x + 0.5)) < 0.9 && Math.abs(wy - (pos.y + 1) + 0.5) < 1.2) {
                return { kind: 'officer', id: cm.slug }
              }
            }
            for (const st of p.life.sites) {
              const f = st.site.footprint
              if (wx >= f.x - 1 && wx <= f.x + f.w + 1 && wy >= f.y - 1 && wy <= f.y + f.h + 1) {
                return { kind: 'site', id: st.site.id }
              }
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
        // the chart table (direction surface — read-only card, never an
        // actuator; the killswitch lever stays THE one actuator, D2)
        if (p.chartTable) {
          const ctw = toWorld(CHART_TABLE_LOCAL.x, CHART_TABLE_LOCAL.y)
          if (Math.abs(wx - (ctw.x + 0.5)) < 1.1 && Math.abs(wy - (ctw.y + 0.5)) < 1.2) {
            return { kind: 'chart_table', id: 'chart-table' }
          }
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
