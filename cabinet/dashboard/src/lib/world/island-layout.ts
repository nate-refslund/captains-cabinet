/**
 * Z0 island layout — the whole org as land (world-alive §3.2, T3).
 *
 * PURE and DETERMINISTIC: integer tiles, fnv1a-seeded placement, growth
 * surfaces in as data. The island's land radius R comes from the fold law
 * (island_land_radius morphology entry): R = 24 + 6*floor(log10(events+1)).
 *
 * Honesty rules rendered here:
 *  - the beacon (interim silo sprite) stays DARK while cells_graduated = 0 —
 *    prominent, slightly oversized, never given a night light (§3.2);
 *  - golden_evals delta ≤ 0 → exactly ONE weathered scarecrow (no dummies);
 *  - houses uniform (per-officer tiers are dark — uniform is the honest
 *    render); one cottage per defined role, birth-order slots (sorted slugs
 *    as the stable stand-in), roof palette seeded per slug;
 *  - every anchor marked even when its building is future — absence of the
 *    building must never read as absence of the surface (§3.2).
 */
import { fnv1a } from './hash'
import type { GrowthModel } from './growth'
import type { OutdoorProp } from './street-layout'
import {
  CROP_SHEETS,
  F,
  FARM_SHEET,
  STREET_PROPS,
  V,
  VILLAGE_SHEET,
  cropCut,
} from './sprites-outdoor'

export interface FieldPlot {
  /** Plot index (one per ratified outcome). */
  k: number
  /** Top-left dirt tile. */
  x: number
  y: number
  w: number
  h: number
  /** Crop species sheet (seeded per outcome slot). */
  cropSheet: string
  /** Rendered stage 0..6 (aggregate work_completed tier under hysteresis). */
  stage: number
  /** Incoming stage under hysteresis (scaffold overlay) or null. */
  pendingStage: number | null
}

export interface IslandLayout {
  w: number
  h: number
  /** Land disc: center + radius in tiles (canvas masks terrain with it). */
  center: { x: number; y: number }
  radius: number
  /** Plaza disc radius (dirt, around the HQ). */
  plazaRadius: number
  /** Seeded pebble decal tiles on the plaza (plaza paving tier TEXTURE). */
  plazaDecals: Array<{ x: number; y: number }>
  props: OutdoorProp[]
  fields: FieldPlot[]
  /** Officer motes near the HQ (4px, same presence predicate as Z2). */
  motes: Array<{ slug: string; x: number; y: number }>
  anchor: { x: number; y: number }
}

/** Stable pseudo-angle in degrees for id (deterministic ring placement). */
function ringPos(id: string, cx: number, cy: number, rMin: number, rSpan: number,
  aMin: number, aSpan: number): { x: number; y: number } {
  const h = fnv1a(id)
  const a = ((aMin + (h % aSpan)) * Math.PI) / 180
  const r = rMin + ((h >>> 9) % Math.max(1, rSpan))
  return { x: Math.round(cx + Math.cos(a) * r), y: Math.round(cy + Math.sin(a) * r) }
}

export function buildIslandLayout(growth: GrowthModel, slugs: string[]): IslandLayout {
  const R = growth.radius
  const pad = 8
  const C = R + pad
  const w = 2 * C
  const h = 2 * C
  const props: OutdoorProp[] = []

  // ── center: the HQ (village large cottage; click → Z1) + plaza ──────────
  props.push({
    id: 'island:hq',
    sheet: VILLAGE_SHEET,
    cut: V.hq,
    x: C,
    y: C + 2,
    label: 'HQ — the org headquarters',
    decorative: false,
    navigate: 1,
  })
  props.push({
    id: 'island:hq:sign',
    sheet: VILLAGE_SHEET,
    cut: V.signpost,
    x: C + 4,
    y: C + 2,
    label: 'HQ signboard',
    decorative: true,
  })
  const plazaRadius = 6
  // Plaza paving decals: subagents-lifetime tier as TEXTURE density
  // (island plaza path: dirt→gravel→cobble→flagstone reads as decal count).
  const plazaDecals: Array<{ x: number; y: number }> = []
  const decals = growth.plazaTier.tier * 4
  for (let i = 0; i < decals; i++) {
    const p = ringPos(`island:plaza:${i}`, C, C, 1, plazaRadius - 2, 0, 360)
    plazaDecals.push(p)
  }

  // ── residential W: one uniform cottage per defined role ─────────────────
  const ordered = [...slugs].sort()
  const houses = Math.max(growth.officerHouses, ordered.length)
  for (let i = 0; i < houses; i++) {
    const slug = ordered[i] ?? `role:${i}`
    props.push({
      id: `island:house:${i}`,
      sheet: VILLAGE_SHEET,
      cut: V.cottage[fnv1a(`${slug}:roof`) % V.cottage.length],
      x: C - 11 - 6 * i,
      y: C - 2 + (i % 2) * 5,
      label: `${slug} — officer cottage`,
      decorative: false,
      morphId: 'island_officer_houses',
    })
  }

  // ── fields SE: one tilled plot per ratified outcome ──────────────────────
  const fields: FieldPlot[] = []
  for (let k = 0; k < growth.fieldPlots; k++) {
    const col = k % 5
    const row = Math.floor(k / 5)
    fields.push({
      k,
      x: C + 8 + col * 6,
      y: C + 9 + row * 6,
      w: 4,
      h: 3,
      cropSheet: CROP_SHEETS[fnv1a(`outcome:${k}`) % CROP_SHEETS.length],
      stage: growth.cropStage.tier,
      pendingStage: growth.cropStage.pendingTier,
    })
  }

  // ── harbor S: docks + boat + crates + THE dark beacon ────────────────────
  props.push({
    id: 'island:pier',
    sheet: VILLAGE_SHEET,
    cut: V.pier,
    x: C - 2,
    y: C + R - 5,
    label: 'harbor pier',
    decorative: true,
  })
  props.push({
    id: 'island:dock',
    sheet: VILLAGE_SHEET,
    cut: V.dock,
    x: C + 1,
    y: C + R - 2,
    label: 'harbor dock',
    decorative: true,
  })
  props.push({
    id: 'island:boat',
    sheet: STREET_PROPS.boat,
    x: C + 4,
    y: C + R + 2,
    label: 'moored boat',
    decorative: true,
  })
  // Dock crates: one per extension pack (island_harbor_crates).
  const crates = growth.dockCrates
  for (let i = 0; i < crates; i++) {
    const pair = i % 2 === 0 && i + 1 < crates
    props.push({
      id: `island:crate:${i}`,
      sheet: FARM_SHEET,
      cut: pair ? F.crate2 : F.crate,
      x: C - 6 + (i % 3) * 2,
      y: C + R - 7 + Math.floor(i / 3) * 2,
      label: 'dock crate — one per extension pack',
      decorative: false,
      morphId: 'island_harbor_crates',
    })
    if (pair) i++ // the stacked pair consumed two crates
  }
  // THE dark beacon: interim silo sprite, prominent, slightly oversized,
  // unlit until the first graduated cell — never give it a night light.
  props.push({
    id: 'island:beacon',
    sheet: FARM_SHEET,
    cut: F.silo,
    x: C + 9,
    y: C + R - 8,
    label: growth.beaconLit
      ? 'the beacon — first cell graduated'
      : 'the dark beacon — no cell has graduated yet',
    decorative: false,
    morphId: 'island_harbor_beacon',
  })

  // ── works E: barn + kiln cluster + service mill row ──────────────────────
  props.push({
    id: 'island:barn',
    sheet: FARM_SHEET,
    cut: F.barn,
    x: C + 22,
    y: C - 3,
    label: 'the barn — works cluster',
    decorative: true,
  })
  props.push({
    id: 'island:kiln',
    sheet: FARM_SHEET,
    cut: F.kilnShed,
    x: C + 20,
    y: C + 5,
    label: 'kiln house',
    decorative: true,
  })
  // Mill/furnace row: running rows as furnaces, ONE ghost frame marks the
  // disabled rows honestly (codex cites the real totals on inspect).
  const running = Math.min(4, 1 + Math.floor(Math.max(0, growth.millsTotal - growth.millsDisabled) / 12))
  for (let i = 0; i < running; i++) {
    props.push({
      id: `island:mill:${i}`,
      sheet: FARM_SHEET,
      cut: F.furnace,
      x: C + 26 + i * 3,
      y: C + 3,
      label: 'service furnace — running rows',
      decorative: false,
      morphId: 'island_services_mill_row',
    })
  }
  if (growth.millsDisabled > 0) {
    props.push({
      id: 'island:mill:ghost',
      sheet: FARM_SHEET,
      cut: F.furnace,
      x: C + 26 + running * 3,
      y: C + 3,
      label: `stopped service rows (${growth.millsDisabled} disabled)`,
      decorative: false,
      morphId: 'island_services_mill_row',
      ghost: true,
    })
  }

  // ── training NW: dojo banner + the honest scarecrow ─────────────────────
  props.push({
    id: 'island:scarecrow',
    sheet: FARM_SHEET,
    cut: F.scarecrow,
    x: C - 14,
    y: C - 13,
    label:
      growth.goldenEvalsDelta <= 0
        ? 'one weathered scarecrow — golden-eval delta ≤ 0 (honest)'
        : 'training scarecrow',
    decorative: false,
    morphId: 'island_fields',
    ghost: growth.goldenEvalsDelta <= 0,
  })
  props.push({
    id: 'island:dojo:sign',
    sheet: VILLAGE_SHEET,
    cut: V.signpost,
    x: C - 11,
    y: C - 14,
    label: 'training ground marker',
    decorative: true,
  })

  // ── memory NE: market stall + well (Library building lands in E2) ───────
  props.push({
    id: 'island:stall',
    sheet: FARM_SHEET,
    cut: F.stall,
    x: C + 12,
    y: C - 12,
    label: 'market stall — Library building lands in E2; the stall marks the anchor',
    decorative: false,
    morphId: 'wardroom_bookshelf_fill',
  })
  props.push({
    id: 'island:well',
    sheet: FARM_SHEET,
    cut: F.well,
    x: C + 16,
    y: C - 11,
    label: 'stone well',
    decorative: true,
  })

  // ── signals SW: the two manifest'd mailboxes as postal kiosks ────────────
  props.push({
    id: 'island:post:0',
    sheet: STREET_PROPS.mailbox,
    x: C - 14,
    y: C + 10,
    label: 'postal kiosk — outbound signals',
    decorative: true,
  })
  props.push({
    id: 'island:post:1',
    sheet: 'exteriors/ME_Singles_City_Props_16x16_Mailbox_1',
    x: C - 16,
    y: C + 12,
    label: 'postal kiosk',
    decorative: true,
  })

  // ── law N: fenced plot + signpost (the Keep-to-be) ───────────────────────
  props.push({
    id: 'island:law',
    sheet: VILLAGE_SHEET,
    cut: V.lawPlot,
    x: C,
    y: C - R + 12,
    label: 'the law plot — Keep building lands later; the fence marks the anchor',
    decorative: false,
    morphId: 'island_land_radius',
  })
  props.push({
    id: 'island:law:sign',
    sheet: VILLAGE_SHEET,
    cut: V.signpost,
    x: C + 4,
    y: C - R + 13,
    label: 'law marker',
    decorative: true,
  })

  // ── nature fill: trees thicken with org age; flowers inside R·0.6;
  //    rocks at the shoreline (all seeded, never moving once placed) ───────
  const treeCount = growth.streetBand === 'bare' ? 6 : growth.streetBand === 'benches' ? 10 : 14
  for (let i = 0; i < treeCount; i++) {
    // Arc excludes the SE fields / S harbor / N law plot sectors.
    const hsh = fnv1a(`island:tree:${i}`)
    let a = 150 + (hsh % 200)
    if (a >= 250) a += 40
    const rr = Math.round(R * 0.68) + ((hsh >>> 9) % Math.max(1, Math.round(R * 0.16)))
    const x = Math.round(C + Math.cos((a * Math.PI) / 180) * rr)
    const y = Math.round(C + Math.sin((a * Math.PI) / 180) * rr)
    props.push({
      id: `island:tree:${i}`,
      sheet: VILLAGE_SHEET,
      cut: i % 2 === 0 ? V.treeRow : V.treeRow2,
      x,
      y,
      label: 'tree row',
      decorative: true,
    })
  }
  for (let i = 0; i < 6; i++) {
    const p = ringPos(`island:flower:${i}`, C, C, 8, Math.max(1, Math.round(R * 0.6) - 8), 0, 360)
    props.push({
      id: `island:flower:${i}`,
      sheet: VILLAGE_SHEET,
      cut: V.flowerbed,
      x: p.x,
      y: p.y,
      label: 'flower bed',
      decorative: true,
    })
  }
  for (let i = 0; i < 10; i++) {
    const p = ringPos(`island:rock:${i}`, C, C, R - 2, 2, 0, 360)
    props.push({
      id: `island:rock:${i}`,
      sheet: VILLAGE_SHEET,
      cut: V.rock,
      x: p.x,
      y: p.y,
      label: 'shoreline rock',
      decorative: true,
    })
  }
  for (let i = 0; i < 4; i++) {
    const p = ringPos(`island:hedge:${i}`, C, C, 10, Math.max(1, Math.round(R * 0.5)), 150, 240)
    props.push({
      id: `island:hedge:${i}`,
      sheet: VILLAGE_SHEET,
      cut: V.hedge,
      x: p.x,
      y: p.y,
      label: 'hedge',
      decorative: true,
    })
  }

  // ── officer motes on the plaza (presence predicate identical to Z2) ─────
  const motes = ordered.map((slug, i) => ({
    slug,
    x: C - 3 + i * 2,
    y: C + 4,
  }))

  return {
    w,
    h,
    center: { x: C, y: C },
    radius: R,
    plazaRadius,
    plazaDecals,
    props,
    fields,
    motes,
    anchor: { x: C, y: C },
  }
}
