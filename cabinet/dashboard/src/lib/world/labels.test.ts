import { describe, expect, it } from 'vitest'
import { LABEL_H, LABEL_STEP, LABEL_W, layoutLabels } from './labels'

describe('label collision layout (v1a fix: garbled yard labels)', () => {
  it('non-colliding labels keep their anchors', () => {
    const laid = layoutLabels([
      { id: 'a', x: 0, y: 0 },
      { id: 'b', x: LABEL_W + 10, y: 0 },
    ])
    expect(laid.map((l) => l.dy)).toEqual([0, 0])
    expect(laid.every((l) => !l.displaced)).toBe(true)
  })

  it('colliding labels stack downward deterministically', () => {
    const laid = layoutLabels([
      { id: 'a', x: 100, y: 50 },
      { id: 'b', x: 104, y: 52 }, // would garble over a
      { id: 'c', x: 98, y: 49 }, // would garble over both
    ])
    expect(laid[0].dy).toBe(0)
    expect(laid[1].displaced).toBe(true)
    expect(laid[2].displaced).toBe(true)
    // pairwise separation ≥ LABEL_H after layout
    for (let i = 0; i < laid.length; i++) {
      for (let j = i + 1; j < laid.length; j++) {
        const dxOk = Math.abs(laid[i].x - laid[j].x) >= LABEL_W
        const dyOk = Math.abs(laid[i].y + laid[i].dy - (laid[j].y + laid[j].dy)) >= LABEL_H
        expect(dxOk || dyOk, `${laid[i].id} vs ${laid[j].id}`).toBe(true)
      }
    }
  })

  it('is pure + deterministic (same input ⇒ identical output)', () => {
    const input = Array.from({ length: 6 }, (_, i) => ({
      id: `o${i}`,
      x: 200 + (i % 2) * 8,
      y: 300 + i,
    }))
    expect(layoutLabels(input)).toEqual(layoutLabels(input))
  })

  it('stack step clears the label box', () => {
    expect(LABEL_STEP).toBeGreaterThanOrEqual(LABEL_H)
  })
})
