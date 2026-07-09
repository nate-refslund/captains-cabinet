/**
 * DOM LABEL COLLISION LAYOUT — pure resolver (v1a review must-fix: officer
 * labels collided and garbled at the great-house yard, e.g. two officers'
 * name+verb lines interleaving into unreadable text).
 *
 * Contract: given projected screen anchors (px), return per-label vertical
 * stack offsets such that no two labels overlap. Deterministic: processing
 * order is the CALLER's order (engine-client passes slug-sorted labels —
 * the same seeded order the canvas draws), no clocks, no randomness.
 */

export interface LabelAnchor {
  id: string
  /** Projected screen anchor (px, label centered on x). */
  x: number
  y: number
}

export interface LaidOutLabel extends LabelAnchor {
  /** Vertical offset (px) applied to avoid collisions (0 = untouched). */
  dy: number
  /** True when the label was displaced — caller may draw a leader line. */
  displaced: boolean
}

/** Approximate label box (name + verb rows) used for collision checks. */
export const LABEL_W = 88
export const LABEL_H = 26
/** Vertical stacking step for displaced labels. */
export const LABEL_STEP = LABEL_H + 2

/**
 * Stack colliding labels downward: each label keeps its anchor unless its
 * box intersects an already-placed one, in which case it steps down until
 * free (bounded — never loops forever).
 */
export function layoutLabels(anchors: readonly LabelAnchor[]): LaidOutLabel[] {
  const placed: LaidOutLabel[] = []
  for (const a of anchors) {
    let dy = 0
    let guard = 0
    const collides = () =>
      placed.some(
        (p) =>
          Math.abs(p.x - a.x) < LABEL_W &&
          Math.abs(p.y + p.dy - (a.y + dy)) < LABEL_H
      )
    while (collides() && guard < 24) {
      dy += LABEL_STEP
      guard += 1
    }
    placed.push({ ...a, dy, displaced: dy > 0 })
  }
  return placed
}
