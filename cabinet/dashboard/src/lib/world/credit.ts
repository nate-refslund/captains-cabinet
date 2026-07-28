/**
 * WHO THE ART CREDIT NAMES — derived from what the page paints, never assumed.
 *
 * The LimeZu licence requires the credit wherever LimeZu art is shown. The
 * inverse obligation is ours: printing "Art: LimeZu" over a frame LimeZu did
 * not draw attributes our own art to someone else. Both halves are wrong in
 * the same way — an unconditional credit line is a claim nobody measured.
 *
 * So the credit is a FUNCTION OF THE MANIFEST'S `license` FIELD over the ids
 * each mounted surface actually binds. Two surfaces carry art on /world:
 *
 *  - `world canvas` — under 'topdown' the kernel binds the outdoor sheet
 *    universe (LimeZu village/farm/street/office packs). Under 'iso' it binds
 *    the OWNED iso pack atlas and nothing else from the packs — every other
 *    top-down dynamic is deliberately absent from the iso path (see
 *    engine-canvas `drawIsoDynamics`) — plus the cast, whose directory is
 *    `CHARACTER_DIR`. That is why the iso arm is derived rather than hardcoded
 *    to `false`: flipping CHARACTER_DIR back to the licensed sheets restores
 *    the credit under iso by itself, with no second line to remember.
 *
 *  - `portrait rail` — chrome, not world, and therefore mounted under BOTH
 *    projections. Its portraits are `LimeZu commercial — derived pixels`
 *    compositions of the Portrait Generator pieces, so an iso frame with the
 *    rail open is still showing LimeZu-derived pixels. A credit rule that
 *    keyed on projection alone would drop the credit while they are on screen.
 *    The rail counts its own LimeZu portraits (it holds the manifest rows it
 *    paints) and reports the number up; this module owns the licence test both
 *    of them use, so there is one authority for what "LimeZu" means.
 *
 * KNOWN AND DELIBERATE IMPRECISION. This measures BINDING, not photons: a row
 * present in the manifest whose PNG is absent (a hatched cabinet has the whole
 * manifest but only the owned binaries) counts as bound, and the surface draws
 * a loud placeholder instead. The credit is therefore conservative — it can be
 * shown where nothing LimeZu actually loaded, never hidden where something
 * did. That direction is chosen on purpose: gating a licence notice on image
 * load would let a slow network or a 404 suppress a credit that IS owed, which
 * is the failure that costs something.
 */
import type { ProjectionKind } from './projection'
import type { ManifestRow, WorldAssetManifest } from './sprites'
import { ENGINE_CHARACTER_SHEETS, requiredOutdoorSheets } from './sprites-outdoor'

/** The owned iso pack atlas — the only manifest row the iso kernel paints
 * besides the cast (the pack itself loads from originals/iso/, off-manifest). */
export const ISO_ATLAS_ROW = 'originals/iso/atlas-0'

/** A surface that can owe the credit. Order is stable for display/testing. */
export type CreditSurface = 'world canvas' | 'portrait rail'

/**
 * Are these pixels LimeZu's? Raw pack rows and derived compositions both are —
 * the licence attaches to the pixels, and `world-compose-portraits.py` writes
 * "LimeZu commercial — derived pixels, do not redistribute" for exactly that
 * reason. Anything else (owned — org-original, CC0, or a row with no licence
 * recorded at all) is not.
 */
export function isLimeZuRow(row: ManifestRow | null | undefined): boolean {
  return /^LimeZu\b/.test(row?.license ?? '')
}

/** Manifest ids the world canvas paints under a projection. */
export function canvasAssetIds(projection: ProjectionKind): string[] {
  if (projection === 'iso') return [ISO_ATLAS_ROW, ...ENGINE_CHARACTER_SHEETS]
  // The top-down kernel's whole sheet universe — the island scene is the one
  // the engine builds (engine-canvas resolveOutdoorSprites(manifest, 'island')).
  return requiredOutdoorSheets('island')
}

export interface CreditInput {
  projection: ProjectionKind
  /** null until the manifest loads — nothing is known to be bound yet. */
  manifest: WorldAssetManifest | null
  /** LimeZu-licensed portraits the rail is currently painting (it counts them
   * with `isLimeZuRow`; 0 when the rail is closed, empty, or placeholdering). */
  limezuPortraits: number
}

/** Which mounted surfaces are bound to LimeZu-licensed art, right now. */
export function limezuSurfaces(input: CreditInput): CreditSurface[] {
  const { projection, manifest, limezuPortraits } = input
  const out: CreditSurface[] = []
  const byId = new Map((manifest?.assets ?? []).map((r) => [r.id, r]))
  if (canvasAssetIds(projection).some((id) => isLimeZuRow(byId.get(id)))) {
    out.push('world canvas')
  }
  if (limezuPortraits > 0) out.push('portrait rail')
  return out
}

/** The credit line renders iff this is true. */
export function creditOwed(input: CreditInput): boolean {
  return limezuSurfaces(input).length > 0
}

/** Human-readable "why is this line here" for the credit's tooltip. */
export function creditReason(surfaces: CreditSurface[]): string {
  return surfaces.length === 0
    ? 'no LimeZu art on screen'
    : `LimeZu art drawn by: ${surfaces.join(', ')}`
}
