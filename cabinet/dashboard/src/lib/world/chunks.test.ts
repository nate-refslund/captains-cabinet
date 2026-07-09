/**
 * Chunked tilemap suite (T1) — chunk math, procedural base determinism,
 * authored-island geography, shore autotiling, O(built) storage.
 */
import { describe, expect, it } from 'vitest'
import {
  CHUNK_SIZE,
  ChunkStore,
  baseTile,
  chunkKey,
  chunkOf,
  chunksInRect,
  landAt,
  localOf,
  shoreMask,
  shoreVariant,
} from './chunks'
import {
  buildWorldGeo,
  carvePolyline,
  CANVAS,
  ISLE_ANCHORS,
  MAIN_OFFSET,
  QUAY_CENTER,
  type WorldGeo,
} from './world-geo'

const GEO: WorldGeo = buildWorldGeo({
  orgEventsTotal: 168_917, // R = 54 by the fold law, capped to the 60×48 core
  lanes: {
    polads: { ever: 5, active: 3, achieved: 1, retired: 0 },
    stephie: { ever: 2, active: 1, achieved: 1, retired: 0 },
    stepnetwork: { ever: 1, active: 0, achieved: 0, retired: 1 },
  },
})

describe('chunk math', () => {
  it('chunkOf/localOf handle signed unbounded coords', () => {
    expect(chunkOf(0)).toBe(0)
    expect(chunkOf(15)).toBe(0)
    expect(chunkOf(16)).toBe(1)
    expect(chunkOf(-1)).toBe(-1)
    expect(chunkOf(-16)).toBe(-1)
    expect(chunkOf(-17)).toBe(-2)
    expect(localOf(0)).toBe(0)
    expect(localOf(-1)).toBe(15)
    expect(localOf(-16)).toBe(0)
    expect(localOf(35)).toBe(3)
  })
  it('local index round-trips: t = chunkOf(t)*16 + localOf(t)', () => {
    for (const t of [-33, -17, -16, -1, 0, 7, 15, 16, 240, 1000]) {
      expect(chunkOf(t) * CHUNK_SIZE + localOf(t)).toBe(t)
    }
  })
  it('chunksInRect covers exactly the intersecting chunks', () => {
    const cs = chunksInRect(0, 0, 15, 15)
    expect(cs).toEqual([{ cx: 0, cy: 0 }])
    expect(chunksInRect(-1, 0, 16, 0)).toHaveLength(3)
  })
  it('chunkKey is stable + signed', () => {
    expect(chunkKey(-2, 11)).toBe('-2,11')
  })
})

describe('authored geography', () => {
  it('main island composes in at offset (90,8); center is land, far sea is water', () => {
    const main = GEO.islands.find((i) => i.id === 'main')!
    expect(main.cx).toBe(MAIN_OFFSET.x + 30)
    expect(landAt(main.cx, main.cy, GEO)).toBe(true)
    expect(landAt(2, 2, GEO)).toBe(false)
    expect(landAt(-500, -500, GEO)).toBe(false) // unbounded: off-canvas samples fine
  })
  it('active lanes earn isles; retired lane renders reef-buoy (ruling)', () => {
    const polads = GEO.laneSites.find((s) => s.lane === 'polads')!
    expect(polads.render).toBe('isle')
    expect(polads.ringRung).toBe(2)
    const retired = GEO.laneSites.find((s) => s.lane === 'stepnetwork')!
    expect(retired.render).toBe('reef_buoy')
    expect(retired.why).toContain('retired')
    expect(landAt(retired.cx, retired.cy, GEO)).toBe(false) // a buoy has no land
    const reserved = GEO.laneSites.filter((s) => s.render === 'mist_reserved')
    expect(reserved).toHaveLength(2) // slots 4/5 under mist + grey buoys
  })
  it('instance-test lane → reef-buoy even with achieved outcomes (sensed law)', () => {
    const geo = buildWorldGeo({
      orgEventsTotal: 1000,
      lanes: { polads: { ever: 5, active: 3, achieved: 2, retired: 0, instanceTest: true } },
    })
    const site = geo.laneSites.find((s) => s.lane === 'polads')!
    expect(site.render).toBe('reef_buoy')
    expect(site.why).toContain('instance-only')
  })
  it('the road spine carves dirt from the village rise to the quay', () => {
    expect(GEO.roadTiles.size).toBeGreaterThan(20)
    expect(baseTile(GEO.crossroads.x, GEO.crossroads.y, GEO)).toBe('dirt')
  })
  it('carvePolyline is 8-connected and deduplicated', () => {
    const tiles = carvePolyline([
      [0, 0],
      [3, 3],
      [3, 6],
    ])
    expect(tiles[0]).toEqual([0, 0])
    expect(tiles).toContainEqual([3, 6])
    const keys = tiles.map(([x, y]) => `${x},${y}`)
    expect(new Set(keys).size).toBe(keys.length)
  })
  it('the quay line renders reclaimed stone (beside the road mouth)', () => {
    expect(baseTile(QUAY_CENTER.x + 3, QUAY_CENTER.y, GEO)).toBe('quay')
  })
  it('anchors are law: fan slots pairwise ≥ 58 apart (no tier-7 collision)', () => {
    for (let i = 0; i < ISLE_ANCHORS.length; i++) {
      for (let j = i + 1; j < ISLE_ANCHORS.length; j++) {
        const a = ISLE_ANCHORS[i]
        const b = ISLE_ANCHORS[j]
        const d = Math.hypot(a.cx - b.cx, a.cy - b.cy)
        expect(d).toBeGreaterThan(58)
      }
    }
  })
})

describe('procedural base field', () => {
  it('is deterministic (same tile, same geo → same terrain, every call)', () => {
    for (let ty = 0; ty < CANVAS.h; ty += 7) {
      for (let tx = 0; tx < CANVAS.w; tx += 7) {
        expect(baseTile(tx, ty, GEO)).toBe(baseTile(tx, ty, GEO))
      }
    }
  })
  it('main island layers: cleared heart inside, forest ring, sand fringe', () => {
    const main = GEO.islands.find((i) => i.id === 'main')!
    expect(['grass', 'meadow']).toContain(baseTile(main.cx + 2, main.cy + 2, GEO))
    // forest ring between clearR and r (sample a ring tile off the road/quay)
    const ringX = main.cx - (main.clearR + 2)
    const t = baseTile(ringX, main.cy, GEO)
    expect(['forest', 'sand']).toContain(t)
  })
  it('land growth needs zero chunk rewrites: R change moves the coastline', () => {
    const small = buildWorldGeo({ orgEventsTotal: 0, lanes: {} })
    const big = buildWorldGeo({ orgEventsTotal: 10_000_000, lanes: {} })
    const main = small.islands[0]
    const probe = { x: main.cx + main.r + 2, y: main.cy }
    expect(landAt(probe.x, probe.y, small)).toBe(false)
    expect(landAt(probe.x, probe.y, big)).toBe(true) // same tile, grown world
  })
})

describe('shore autotiling', () => {
  it('mask is 0 on land and on open water', () => {
    const main = GEO.islands.find((i) => i.id === 'main')!
    expect(shoreMask(main.cx, main.cy, GEO)).toBe(0)
    expect(shoreMask(2, 2, GEO)).toBe(0)
    expect(shoreVariant(0)).toBe('open')
  })
  it('water adjacent to land carries a nonzero mask → shore tile', () => {
    const main = GEO.islands.find((i) => i.id === 'main')!
    // walk east from the center until we leave land: first water tile is shore
    let tx = main.cx
    while (landAt(tx, main.cy, GEO)) tx++
    expect(shoreMask(tx, main.cy, GEO)).not.toBe(0)
    expect(baseTile(tx, main.cy, GEO)).toBe('shore')
  })
  it('variant table: edges, corners, inner corners, channels, cove', () => {
    const N = 1,
      NE = 2,
      E = 4,
      SE = 8,
      S = 16,
      SW = 32,
      W = 64,
      NW = 128
    expect(shoreVariant(N)).toBe('edge_n')
    expect(shoreVariant(E)).toBe('edge_e')
    expect(shoreVariant(S)).toBe('edge_s')
    expect(shoreVariant(W)).toBe('edge_w')
    expect(shoreVariant(N | E)).toBe('corner_ne')
    expect(shoreVariant(S | W)).toBe('corner_sw')
    expect(shoreVariant(N | NE | E)).toBe('corner_ne')
    expect(shoreVariant(NE)).toBe('inner_ne')
    expect(shoreVariant(SW)).toBe('inner_sw')
    expect(shoreVariant(N | S)).toBe('channel_ns')
    expect(shoreVariant(E | W)).toBe('channel_ew')
    expect(shoreVariant(N | E | S)).toBe('cove')
    expect(shoreVariant(N | E | S | W)).toBe('cove')
    expect(shoreVariant(NW | SE)).toBe('inner_se') // diagonal pair → first inner match
  })
})

describe('O(built) storage', () => {
  it('reading the whole canvas stores NOTHING; only authored diffs store', () => {
    const store = new ChunkStore()
    for (let ty = -32; ty < CANVAS.h + 32; ty += 3) {
      for (let tx = -32; tx < CANVAS.w + 32; tx += 3) {
        store.tileAt(tx, ty, GEO)
      }
    }
    expect(store.storedChunkCount()).toBe(0) // base is never stored
    store.setOverride(100, 40, { terrain: 'dirt', by: 'site:test' })
    store.setOverride(101, 40, { terrain: 'dirt', by: 'site:test' })
    expect(store.storedChunkCount()).toBe(1) // both tiles share one chunk
    expect(store.tileAt(100, 40, GEO)).toBe('dirt')
    expect(store.getOverride(100, 40)?.by).toBe('site:test')
    // an override in a far chunk = exactly one more stored chunk
    store.setOverride(-1000, -1000, { terrain: 'quay', by: 'site:far' })
    expect(store.storedChunkCount()).toBe(2)
  })
})
