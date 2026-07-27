/**
 * PAINT — the ground regions the renderer paints under everything else.
 *
 * PORTED FROM compose.py lines 142-177 (broken meadow, pond, outflow, bank),
 * 355-386 (plaza, tilled plots, value mottle).
 *
 * WHY THE ISLAND NEEDS THIS AT ALL. The reference's own comment at :142 says
 * it: "patches of the darker grass keep the field from reading as one flat
 * sheet". Without the meadow break and the mottle, an island is a lawn with
 * objects on it — which is exactly how the port read before this module
 * existed, and no amount of planting fixes a flat ground plane.
 *
 * EVERY PAINTED MASK IS CLIPPED TO LAND — compose.py clips all of them
 * (`ImageChops.darker(m, landmask)`): paths :343, plaza :360, each field plot
 * :374, the pond and its outflow :171, the meadow patches :149. A blob here is
 * an ellipse, not pixels, so the honest equivalent is to SHRINK it until its
 * whole extent is on land and DROP it when it cannot fit. Shrinking never
 * paints water and never invents a shape the reference would not have painted;
 * it can only paint less.
 *
 * ONE STREAM PER REGION. A single shared rng stream makes each region's shape
 * depend on how many draws the regions BEFORE it consumed, so gaining a field
 * plot would silently reshape the pond — and the pond is morphology. Water does
 * not wait for an org to grow. Per-region streams are also what let this module
 * gain the meadow, mottle, stream and bank passes without moving a single
 * plaza, plot or pond blob of the layouts that already exist.
 *
 * PURE: no clocks, no unseeded randomness, no IO, no DOM.
 */
import { fnv1a, seededRng } from '../hash'
import type { Coastline } from './coastline'
import { SQUARE } from './lanes'
import { clamp, ISO_AXIS_SLOPE, type Point } from './space'

/** One painted blob — the renderer unions them into an organic region. */
export interface Blob {
  c: Point
  rx: number
  ry: number
  /**
   * Blend strength in 0..1, for the regions whose reference draws a per-blob
   * mask VALUE rather than a solid fill (the meadow patches at fill 110-210 and
   * the mottle at alpha 18-22). Absent means solid — the plaza, the plots and
   * the water are painted at full strength, as in the reference.
   */
  w?: number
}

/**
 * The regions this stage emits.
 *
 * `meadow_dark` was declared here for weeks and never produced — the
 * broken-meadow pass was not ported, and a declared-but-unreachable member is a
 * promise to the renderer that nothing keeps. It is produced now, and so are
 * the four members that came with the rest of the ground passes.
 *
 * THE KINDS SPLIT INTO THREE CLASSES, and the difference is load-bearing rather
 * than cosmetic:
 *   SURFACE — `plaza`, `ploughed`, `crop`. Paved or tilled ground. Nothing is
 *     planted on them (see index.ts free()).
 *   WATER — `pond`, `stream`. Nothing but a lilypad is planted in them.
 *   SHADING — `meadow_dark`, `mottle`, `pond_bank`. These are what the ground
 *     LOOKS like, not what it IS: grass is grass, and a tree grows on shaded
 *     grass exactly as it grows on plain grass. Feeding them to the planting
 *     exclusions would carve bald patches at random across the meadow, which is
 *     the same defect as the keep-out discs in reverse.
 */
export type PaintKind =
  | 'plaza'
  | 'ploughed'
  | 'crop'
  | 'pond'
  | 'stream'
  | 'pond_bank'
  | 'meadow_dark'
  | 'mottle'

export interface PaintRegion {
  kind: PaintKind
  blobs: Blob[]
  /**
   * Which of MOTTLE_TONES this region is painted in. Only `mottle` carries it:
   * the reference picks one of three colours per blob, and a region per colour
   * is how that survives being data instead of a Pillow paste.
   */
  tone?: number
}

/**
 * compose.py:385 — the three mottle colours, RGBA with the reference's own
 * alphas. Exported because a renderer that had to invent them would invent a
 * different ground every time the file was read.
 */
export const MOTTLE_TONES: readonly (readonly [number, number, number, number])[] = [
  [152, 178, 120, 22],
  [98, 132, 80, 22],
  [178, 192, 132, 18],
]

/**
 * compose.py:366 — the tilled plots in the south-east, taken in order and
 * truncated to the number of field plots that really exist.
 */
export const FIELD_PLOTS: readonly { c: Point; w: number; h: number; kind: PaintKind }[] = [
  { c: { x: 1548, y: 1218 }, w: 150, h: 74, kind: 'ploughed' },
  { c: { x: 1772, y: 1152 }, w: 138, h: 68, kind: 'crop' },
  { c: { x: 1650, y: 1332 }, w: 158, h: 70, kind: 'crop' },
  { c: { x: 1420, y: 1300 }, w: 120, h: 58, kind: 'ploughed' },
]

/** compose.py:154 — the inland pond, which gave the dead west meadow a reason. */
export const POND: Point = { x: 612, y: 1086 }

/**
 * compose.py:163 — the outflow's course to the west coast, as the reference's
 * three waypoints. The stream is what makes the pond part of the island rather
 * than a puddle dropped on it: water that arrives from nowhere and goes nowhere
 * reads as a mistake.
 */
export const OUTFLOW: readonly Point[] = [
  { x: 492, y: 1120 },
  { x: 404, y: 1152 },
  { x: 330, y: 1176 },
]

/**
 * compose.py:172 — the bank is `blur(pond_mask, 9) - pond_mask`, i.e. a sand
 * ring just outside the water. Without a bitmap the equivalent is the same blob
 * set grown by that radius: the renderer paints the bank first and the water
 * over it, and the difference IS the ring. Emitting the ring as its own region
 * rather than as a subtraction is what lets the reed pass ask "is this the
 * bank?" as a plain predicate.
 */
const BANK_GROW = 9

/**
 * THE WHOLE ELLIPSE IS SAMPLED, not just its rim: a lattice at ~`probe` px plus
 * the rim at the same arc spacing. Rim-only sampling has a hole in the middle
 * (a blob wide enough to straddle an inlet has water inside it its rim never
 * sees), and a FIXED number of rim angles has holes between them that grow with
 * the blob — a 150px field plot probed at 24 angles skips 39px of arc at a time,
 * and the coastline mask is quantised to its raster step, so the gaps do not
 * average out.
 *
 * THE ANGLE FLOOR IS THE OTHER HALF OF THE SAME BUG, and it took the pond bank
 * to expose it. `max(24, ...)` bounded the count from BELOW, which is the wrong
 * end: a 24px blob got 31 angles, i.e. a 4.9px arc gap, and the coastline is an
 * 8px raster at the sampling step the tests use — so a cell the rim only clips
 * at a corner falls between two probes. Measured on the stream's bank blobs on
 * seed acme-corp, where the independent 90-angle probe in the test suite found
 * open water inside a blob this function had just certified. The floor is now
 * high enough that the arc gap is sub-pixel at every radius a region here uses.
 *
 * AND THE STEP FOLLOWS THE RASTER — a REDUNDANT rule, kept, and said so rather
 * than implied. The old comment claimed the probe step was "finer than the
 * finest coastline raster this library will build"; it was not, because the
 * production coastline samples every 2px and the probe was fixed at 5, so at the
 * step that ships the sensor was coarser than the thing it measured. `probe` is
 * now min(BLOB_PROBE_STEP, the raster's own step). Measured 2026-07-27 by
 * pinning it back at 5: every arm stayed green, including the production-step
 * extent arm in planting.test.ts. The reason is BLOB_RIM_ANGLES above — at 512
 * the rim is sub-pixel for every radius any region here uses, whatever the step,
 * so following the raster now only refines the INTERIOR lattice and nothing
 * currently distinguishes the two. It stays because the claim in this comment
 * has to be true of the code, not merely true today.
 */
const BLOB_PROBE_STEP = 5
const BLOB_MIN_RADIUS = 8
const BLOB_RIM_ANGLES = 512

/**
 * How much bigger than itself a blob must be clear, to be certified clear.
 *
 * DENSITY WAS NEVER THE PROBLEM — GRAZING WAS. This function samples the rim at
 * 512 angles and the interior on a ~5px lattice, and an independent 90-angle
 * probe in iso-layout.test.ts still found a point off land inside a blob this
 * had just certified. Measured on seed `harbour`, crop plot 2: the blob's rim
 * reaches y = 1175.99 and the raster cell boundary is y = 1176.00, so the two
 * samplers land either side of an 8px cell edge and disagree by 0.01px. No
 * finite angle count fixes that; both are honest samples of the same curve, and
 * the curve genuinely grazes water.
 *
 * The fix is a MARGIN rather than more probes: the blob is tested at
 * rx + MARGIN, ry + MARGIN and painted at rx, ry, so the painted rim sits a
 * real distance inside the certified one and ANY sampler at any density agrees.
 * 2px, because growing both semi-axes by m moves the true rim outward by at
 * least m * min(rx,ry) / max(rx,ry), and no region here is flatter than 1:2 —
 * so 2 buys at least 1px of genuine clearance. It can only paint less.
 */
const BLOB_LAND_MARGIN = 2

function blobOnLand(
  c: Point,
  rx: number,
  ry: number,
  onLand: (x: number, y: number) => boolean,
  probe: number
): boolean {
  if (!onLand(c.x, c.y)) return false
  const n = Math.max(
    BLOB_RIM_ANGLES,
    Math.ceil((2 * Math.PI * Math.max(rx, ry)) / probe)
  )
  for (let i = 0; i < n; i++) {
    const a = (i * Math.PI * 2) / n
    if (!onLand(c.x + Math.cos(a) * rx, c.y + Math.sin(a) * ry)) return false
  }
  const sx = Math.max(1, Math.ceil(rx / probe))
  const sy = Math.max(1, Math.ceil(ry / probe))
  for (let ix = -sx; ix <= sx; ix++) {
    for (let iy = -sy; iy <= sy; iy++) {
      const fx = ix / sx
      const fy = iy / sy
      if (fx * fx + fy * fy > 1) continue
      if (!onLand(c.x + fx * rx, c.y + fy * ry)) return false
    }
  }
  return true
}

/**
 * The blob that fits on land, or null when even a shrunken one does not.
 *
 * `probe` is the sampling step; pass the coastline's own raster step so the
 * sensor is never coarser than the mask it reads.
 */
export function clipBlobToLand(
  b: Blob,
  onLand: (x: number, y: number) => boolean,
  probe: number = BLOB_PROBE_STEP
): Blob | null {
  const p = Math.max(0.5, Math.min(BLOB_PROBE_STEP, probe))
  let rx = b.rx
  let ry = b.ry
  for (let i = 0; i < 10; i++) {
    // tested with the margin, kept without it — see BLOB_LAND_MARGIN
    if (blobOnLand(b.c, rx + BLOB_LAND_MARGIN, ry + BLOB_LAND_MARGIN, onLand, p)) {
      return b.w === undefined ? { c: b.c, rx, ry } : { c: b.c, rx, ry, w: b.w }
    }
    rx *= 0.82
    ry *= 0.82
    if (rx < BLOB_MIN_RADIUS || ry < BLOB_MIN_RADIUS) break
  }
  return null
}

/**
 * compose.py:176-177 in_water() — nothing is planted in water, and since the
 * outflow is drawn into the SAME mask as the pond (compose.py:169), the stream
 * is water too.
 *
 * THE STREAM IS WHY THIS TERM IS NO LONGER QUIET. The pond sits inside its own
 * 190px keep-out disc, so while the pond was the only water the term was
 * redundant — measured, and recorded as such. The outflow runs 280px west of
 * the pond centre, far outside that disc and across open meadow, so from here
 * on the water term is the ONLY thing standing between the general planting and
 * a bush in the middle of a stream.
 *
 * Built from the painted regions rather than from POND/OUTFLOW, so it is the
 * water that was actually emitted (clipped, possibly absent) and not the water
 * that was intended.
 */
export function waterField(paint: readonly PaintRegion[]): (x: number, y: number) => boolean {
  return paintField(paint, ['pond', 'stream'])
}

/**
 * Is this point inside a painted region of one of these kinds?
 *
 * A PAVED SQUARE AND A TILLED PLOT ARE SURFACES, NOT SPACING HINTS — the same
 * argument the keep-out discs needed. Until 2026-07-27 nothing tested for them
 * at all: the property "no tree on the plaza, no reed in the crop" was carried
 * incidentally by whichever district disc happened to overlap the region, and
 * it LEAKED wherever one did not. Measured across 80 seeds with the discs
 * enforced: 9 shore-band items standing in a crop plot, all on the east plot's
 * outer rim at x>=1900, which lies outside every disc.
 */
export function paintField(
  paint: readonly PaintRegion[],
  kinds: readonly PaintKind[]
): (x: number, y: number) => boolean {
  const blobs = paint.filter((r) => kinds.includes(r.kind)).flatMap((r) => r.blobs)
  if (blobs.length === 0) return () => false
  return (x, y) =>
    blobs.some((b) => ((x - b.c.x) / b.rx) ** 2 + ((y - b.c.y) / b.ry) ** 2 <= 1)
}

/**
 * The same membership test as paintField, with every blob GROWN by `grow` px.
 *
 * It exists because the painted sand fringe and the plantable margin are two
 * different widths of the same thing. The fringe is 9px, which is what the
 * reference's 9px blur produces and what a renderer should paint; a reed clump
 * is 47x55 and a Poisson pass seeded by uniform sampling over the whole canvas
 * will essentially never find a 9px annulus — measured, the bank pass planted
 * nothing at all on any of five seeds. Reeds grow along a margin, not on a
 * hairline, so the PLANTING band is the water grown by REED_MARGIN and the
 * painted band stays the reference's 9px.
 */
export function grownField(
  paint: readonly PaintRegion[],
  kinds: readonly PaintKind[],
  grow: number
): (x: number, y: number) => boolean {
  const blobs = paint.filter((r) => kinds.includes(r.kind)).flatMap((r) => r.blobs)
  if (blobs.length === 0) return () => false
  return (x, y) =>
    blobs.some(
      (b) => ((x - b.c.x) / (b.rx + grow)) ** 2 + ((y - b.c.y) / (b.ry + grow)) ** 2 <= 1
    )
}

/** How far out from the water a reed may stand. */
export const REED_MARGIN = 52

/**
 * How many lobes break a meadow patch's rim (see the meadow pass below).
 *
 * SEVEN, not four and not sixteen. Four leaves the core ellipse visible between
 * the bumps and reads as a clover; sixteen at these radii closes back into a
 * circle and buys nothing for 16x the blobs. Seven is the smallest count whose
 * union has no straight arc long enough to read as an ellipse edge, measured by
 * eye on the hamlet frame at 1.0 and by blob count in paint.test.ts.
 */
export const MEADOW_LOBES = 7

/**
 * How far a SHADING region's edge is feathered, in layout px, per kind.
 *
 * THE DEFECT (Captain, 2026-07-27): "the meadow patches read as HARD DARK
 * ELLIPSES rather than as subtle variation". They did, and the reason is in the
 * meadow pass's own docstring twelve lines down: compose.py draws its ellipses
 * and then blurs the WHOLE mask by 26px (compose.py:149,
 * `patch.filter(ImageFilter.GaussianBlur(26))`), and this port replaced that
 * blur with an irregular OUTLINE. A lobed edge is still an edge — it broke the
 * razor oval into a razor cloud and the frame still read as blobs. The lobes
 * are kept, because they stop the silhouette being an oval; the blur is what
 * stops it being a silhouette at all.
 *
 * IT IS SHIPPED, NOT RE-TYPED, for exactly the reason LANE_SQUASH is: two
 * renderers paint this layout — the engine and cabinet/scripts/world-capture —
 * and a feather that lived in each of them separately would be two grounds.
 * blueprint.ts puts it in the draw list, raster.py reads it from there, and
 * engine-canvas.tsx imports this constant. Nobody holds a second copy.
 *
 * ONLY `meadow_dark`. The mottle is already three flat tones at alpha 18-22/255
 * and the reference does not blur it; the plaza, the tillage and the water are
 * SURFACES with real edges — a pond has a bank, not a fade — and feathering
 * them would blur the boundary the planting rules actually use.
 */
export const PAINT_FEATHER: Readonly<Partial<Record<PaintKind, number>>> = {
  meadow_dark: 26,
}

/**
 * All the ground regions for a world state.
 *
 * `fieldPlots` and `village` rather than the whole LayoutState: this module is
 * downstream of nothing and must stay that way, and a paint stage that could
 * read the whole state would eventually read something it has no business
 * knowing. They are also the only two things the reference's ground stage
 * branches on.
 */
export function paintRegions(
  seed: number,
  coast: Coastline,
  fieldPlots: number,
  village: boolean
): PaintRegion[] {
  const streamFor = (tag: string) => seededRng(fnv1a(`${seed}:paint:${tag}`))
  const out: PaintRegion[] = []
  const onLand = (x: number, y: number) => coast.landAt(x, y)
  // Clip AFTER every draw, never instead of one: the rng stream must be
  // consumed in the reference's order whatever the coastline does, or a blob
  // that fell in the sea would reshape every blob after it.
  const keep = (kind: PaintKind, blobs: Blob[], tone?: number): Blob[] => {
    const clipped = blobs
      .map((b) => clipBlobToLand(b, onLand, coast.step))
      .filter((b): b is Blob => b !== null)
    if (clipped.length > 0) out.push(tone === undefined ? { kind, blobs: clipped } : { kind, blobs: clipped, tone })
    return clipped
  }

  // ---- broken meadow (compose.py:142-150) ---------------------------------
  // 70 patches of the darker grass, so the field does not read as one flat
  // sheet. MORPHOLOGY, not doctrine: a camp's meadow is as broken as a town's,
  // because grass does not know what an org has built. The reference skips the
  // radius and fill draws for an off-land candidate, so this does too — the
  // stream has to be consumed in the same order or the patches move.
  //
  // AND THE PATCH IS A CLOUD, NOT AN ELLIPSE. The reference draws one ellipse
  // per patch and then blurs the WHOLE mask by 26px (compose.py:149), which is
  // what turns 70 hard ovals into shading you cannot see the edges of. A blob
  // here is vector, not pixels, so there is no blur to apply — and painting the
  // ellipses as drawn gave exactly what the first render was judged on:
  // "eight-plus flat darker-green ovals with razor edges, the most artificial
  // thing in the frame". The honest vector equivalent of a blurred mask is an
  // IRREGULAR OUTLINE: a smaller core plus satellites scattered round its rim,
  // all at the SAME fill so the union is still one flat patch at one strength.
  // The union's extent matches the ellipse it replaces (core 0.62r + satellites
  // at 0.56r carrying 0.44r ≈ 1.0r), so nothing downstream moves; only the
  // silhouette stops being a razor oval.
  //
  // SAME FILL ON EVERY PIECE IS LOAD-BEARING, not incidental. Both renderers
  // union a region's blobs and take the MAX of their strengths (raster.py
  // _blob_mask uses ImageChops.lighter; the engine unions one Graphics path per
  // alpha bucket). Satellites at a different fill would composite at the
  // overlaps and draw a dark ring round every patch — the opposite of a feather.
  {
    const rng = streamFor('meadow')
    const blobs: Blob[] = []
    for (let i = 0; i < 70; i++) {
      const x = Math.floor(rng() * 2401)
      const y = Math.floor(rng() * 1761)
      if (!onLand(x, y)) continue
      const r = 90 + Math.floor(rng() * 151)
      const fill = 110 + Math.floor(rng() * 101)
      const w = fill / 255
      blobs.push({ c: { x, y }, rx: r * 0.62, ry: r * 0.62 * 0.62, w })
      for (let k = 0; k < MEADOW_LOBES; k++) {
        // the rim angle is jittered inside its own slice, so the lobes never
        // land on a regular polygon — a ring of evenly spaced bumps reads as a
        // cog, which is a different artificial shape rather than none
        const a = ((k + rng()) * Math.PI * 2) / MEADOW_LOBES
        const rr = r * (0.42 + rng() * 0.28)
        const lobe = r * (0.34 + rng() * 0.2)
        blobs.push({
          c: { x: x + Math.cos(a) * rr, y: y + Math.sin(a) * rr * 0.62 },
          rx: lobe,
          ry: lobe * 0.62,
          w,
        })
      }
    }
    keep('meadow_dark', blobs)
  }

  // ---- the paved square (compose.py:355-359) ------------------------------
  // The square is PAVED only once there is a village to gather in it. A camp
  // has trodden grass, which is the absence of this region, not a smaller one.
  if (village) {
    const rng = streamFor('plaza')
    const blobs: Blob[] = []
    for (let i = 0; i < 26; i++) {
      const a = rng() * Math.PI * 2
      const rr = Math.sqrt(rng())
      const r = 54 + rng() * 42
      blobs.push({
        c: { x: SQUARE.x + Math.cos(a) * rr * 124, y: SQUARE.y + Math.sin(a) * rr * 74 },
        rx: r,
        ry: r * 0.62,
      })
    }
    keep('plaza', blobs)
  }

  // ---- the tilled plots (compose.py:364-376) ------------------------------
  //
  // A PLOUGHED FIELD IS A RHOMBUS ON THE ISO AXES, NOT AN OVAL — and this is a
  // deliberate departure from the reference, stated so nobody has to guess.
  // compose.py:369-372 draws NINE copies of one 150x74 ellipse jittered by
  // (±40, ±18); the jitter is small against the radii, so the union is an
  // ellipse with a slightly wobbly rim, and that is exactly how the first frame
  // rendered: "the field plots are ellipses too. Furrows are correct and on the
  // iso axis; the plot outline is a perfect oval. Nobody ploughs an ellipse."
  // The furrows inside were already on the iso axes (ground.py's `furrow`
  // modulation), so the boundary was contradicting its own contents.
  //
  // The fix keeps the plot's authored CENTRE and EXTENT and changes only the
  // silhouette: blobs are laid on a lattice of the two isometric axes
  // (±1, ±ISO_AXIS_SLOPE), so the union's edges run along the same axes the
  // furrows and every roofline do. Corners stay rounded because the lattice is
  // painted with overlapping ellipses rather than a polygon — a razor-cornered
  // parallelogram would be a second artificial shape in place of the first.
  //
  // WHY THE AREA MATTERS AND WAS MEASURED: check_terrain sweeps each declared
  // field ellipse and needs 45% of it to read as cultivated (field_min). A
  // rhombus inscribed in a bounding box covers only 64% of that box's inscribed
  // ellipse, so the lattice is sized to fill the box rather than to inscribe in
  // it, and the emitted coverage is asserted in paint.test.ts rather than
  // assumed. Measured on the hamlet fixture after the change: the three plots
  // read 66-71% cultivated, against the same 45% floor.
  const plots = clamp(fieldPlots, 0, FIELD_PLOTS.length)
  for (let i = 0; i < plots; i++) {
    const plot = FIELD_PLOTS[i]
    // per-plot stream: plot 1 looks the same whether or not plot 2 exists
    const rng = streamFor(`field-${i}`)
    const blobs: Blob[] = []
    // THE EXTENT IS THE ONE THE REFERENCE PRODUCED, not a new one. Its nine
    // jittered ellipses union to a half-extent of about (w + 40, h + 18); the
    // rhombus is sized to the same half-width X, and a rhombus on the iso axes
    // has half-height X/2 by construction, which lands within a few px of the
    // authored h + 18 on every plot in FIELD_PLOTS. The plots therefore cover
    // the same ground they always did — only the silhouette changed.
    const halfX = plot.w + 40
    const alongA = halfX * 0.63 // the long furrow axis
    const alongB = halfX * 0.37 // across it
    const nu = 5
    const nv = 3
    const su = alongA / nu
    const sv = alongB / nv
    // A LOBE MUST COVER ITS OWN LATTICE CELL OR THE FIELD DRAWS AS STRIPES.
    // Measured on the first attempt, which stepped su=37 with a lobe of 29 and
    // rendered as a set of loose diagonal bands rather than one worked field:
    // the union has to be solid, because a ploughed plot with grass showing
    // between its rows is not a plot. rx covers the wider of the two steps and
    // ry covers the y step, which is half of it (both axes fall by ISO_AXIS_SLOPE).
    const lobe = Math.max(BLOB_MIN_RADIUS + 2, Math.max(su, sv) * 1.1)
    for (let u = -nu; u <= nu; u++) {
      for (let v = -nv; v <= nv; v++) {
        // a jitter well inside one lobe: enough that the boundary is a hand's
        // furrow line rather than a ruled one, never enough to open a hole
        const jx = (rng() - 0.5) * lobe * 0.35
        const jy = (rng() - 0.5) * lobe * 0.35 * ISO_AXIS_SLOPE
        blobs.push({
          c: {
            x: plot.c.x + (u * su + v * sv) + jx,
            y: plot.c.y + (u * su - v * sv) * ISO_AXIS_SLOPE + jy,
          },
          rx: lobe,
          ry: lobe * ISO_AXIS_SLOPE * 1.3,
        })
      }
    }
    keep(plot.kind, blobs)
  }

  // ---- the pond, its outflow, and the bank (compose.py:153-174) -----------
  // The pond is morphology, not doctrine: it is there in every era, because
  // water does not wait for an org to grow — and its own stream is what makes
  // that literally true rather than merely intended.
  const water: Blob[] = []
  /**
   * The pond and stream blobs THAT WERE ACTUALLY PAINTED, which is what the
   * bank must ring.
   *
   * It used to grow the UNCLIPPED water, and the two clip independently: a bank
   * blob starts 9px larger, so its shrink ladder lands on different radii and it
   * can survive at a size where the water it rings was dropped altogether. That
   * is a sand ring around water nobody painted — and planting.test.ts's
   * "every bank blob centre is a water blob centre" caught it the moment the
   * land certification got 2px stricter. Ringing the emitted water makes the
   * property true by construction instead of by coincidence.
   */
  const keptWater: Blob[] = []
  {
    const rng = streamFor('pond')
    for (let i = 0; i < 14; i++) {
      const a = rng() * Math.PI * 2
      const rr = Math.sqrt(rng())
      // continuous, not the reference's randint: this pass is unchanged from
      // the layout that already shipped, and re-rounding it here would move
      // every pond on every seed for no gain a viewer could see.
      const r = 46 + rng() * 32
      water.push({
        c: { x: POND.x + Math.cos(a) * rr * 74, y: POND.y + Math.sin(a) * rr * 38 },
        rx: r,
        ry: r * 0.58,
      })
    }
    keptWater.push(...keep('pond', water))
  }

  // The outflow: 26 discs per leg, tapering 15 -> 12, exactly as the reference
  // walks it. It is UNSEEDED in the reference (a fixed course between fixed
  // waypoints) and so it is here — a river that wandered with the org's seed
  // would be a river the island's shape does not explain.
  const stream: Blob[] = []
  {
    let prev = POND
    for (const step of OUTFLOW) {
      const n = 26
      for (let i = 0; i <= n; i++) {
        const t = i / n
        const x = prev.x + (step.x - prev.x) * t
        const y = prev.y + (step.y - prev.y) * t
        const r = 15 - t * 3
        stream.push({ c: { x, y }, rx: r, ry: r * 0.66 })
      }
      prev = step
    }
    keptWater.push(...keep('stream', stream))
  }

  // The bank is the water grown by BANK_GROW; the renderer paints it first and
  // the water over it. Clipped like everything else, so a bank never reaches
  // past the shore even where the water it rings was itself clipped.
  keep(
    'pond_bank',
    keptWater.map((b) => ({ c: b.c, rx: b.rx + BANK_GROW, ry: b.ry + BANK_GROW }))
  )

  // ---- the calm value mottle (compose.py:378-386) -------------------------
  // 200 soft ellipses in three greens at 7-9% alpha. It is the difference
  // between "a green rectangle" and "a field seen from a distance", and like
  // the meadow break it is shading rather than surface.
  {
    const rng = streamFor('mottle')
    const byTone: Blob[][] = MOTTLE_TONES.map(() => [])
    for (let i = 0; i < 200; i++) {
      const x = Math.floor(rng() * 2401)
      const y = Math.floor(rng() * 1761)
      if (!onLand(x, y)) continue
      const r = 34 + Math.floor(rng() * 59)
      const tone = Math.min(MOTTLE_TONES.length - 1, Math.floor(rng() * MOTTLE_TONES.length))
      byTone[tone].push({ c: { x, y }, rx: r, ry: r * 0.6, w: MOTTLE_TONES[tone][3] / 255 })
    }
    byTone.forEach((blobs, tone) => keep('mottle', blobs, tone))
  }

  return out
}
