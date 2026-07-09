/**
 * hatch-dialog pure model — unit suite (v1b).
 *
 * Pins the three acceptance behaviours of the dialog framework: the
 * typewriter reveal, the input-row variant, and the H-2 button gate — plus
 * the load-bearing determinism property: same props + ticks => byte-identical
 * frames (hatching plan L635). node env, no DOM (the .tsx is grep-ratcheted
 * separately in components/world/hatch-dialog.test.ts).
 */
import { describe, expect, it } from 'vitest'
import {
  gateButtons,
  HATCH_BUTTON_ORDER,
  renderFrame,
  reveal,
  REVEAL_CHARS_PER_TICK,
  ticksToReveal,
  type DialogFrameInput,
} from './hatch-dialog'

const CPT = REVEAL_CHARS_PER_TICK

describe('typewriter reveal', () => {
  it('reveals nothing at or before tick 0', () => {
    expect(reveal('hello world', 0)).toEqual({ visible: '', done: false })
    expect(reveal('hello world', -5)).toEqual({ visible: '', done: false })
  })

  it('reveals CPT characters per tick (derived from the constant)', () => {
    expect(reveal('hello world', 1).visible).toBe('hello world'.slice(0, CPT))
    expect(reveal('hello world', 2).visible).toBe('hello world'.slice(0, 2 * CPT))
  })

  it('clamps to the full string and marks done (idempotent thereafter)', () => {
    const text = 'abc'
    const full = reveal(text, ticksToReveal(text))
    expect(full).toEqual({ visible: 'abc', done: true })
    // Ticking past the end never changes the frame.
    expect(reveal(text, 999)).toEqual({ visible: 'abc', done: true })
  })

  it('ticksToReveal covers the whole string', () => {
    const text = 'a somewhat longer sentence to reveal'
    const done = reveal(text, ticksToReveal(text))
    expect(done.done).toBe(true)
    expect(done.visible).toBe(text)
    // One tick short is NOT done.
    expect(reveal(text, ticksToReveal(text) - 1).done).toBe(false)
  })

  it('is a pure function — repeated calls are byte-identical', () => {
    const a = reveal('deterministic', 3)
    const b = reveal('deterministic', 3)
    expect(JSON.stringify(a)).toBe(JSON.stringify(b))
  })
})

describe('reveal — edge cases (unicode, non-finite ticks)', () => {
  it('never reveals a lone surrogate — slices by code point, not UTF-16 unit', () => {
    const text = 'a😀b' // '😀' is one code point / two UTF-16 units
    for (let t = 0; t <= ticksToReveal(text) + 2; t++) {
      const v = reveal(text, t).visible
      // A dangling high surrogate at the end == a broken glyph. Must never happen.
      expect(/[\uD800-\uDBFF]$/.test(v), `tick ${t}: ${JSON.stringify(v)}`).toBe(false)
    }
    // The emoji reveals whole, and ticksToReveal covers the full string.
    expect(reveal(text, ticksToReveal(text))).toEqual({ visible: 'a😀b', done: true })
  })

  it('floors fractional ticks (same frame as the floor)', () => {
    const text = 'fractional'
    expect(reveal(text, 1.9).visible).toBe(reveal(text, 1).visible)
  })

  it('non-finite ticks resolve to a DEFINED frame (no silent-undefined arithmetic)', () => {
    const text = 'defined always'
    // NaN / −Infinity reveal nothing but stay defined + deterministic.
    expect(reveal(text, NaN)).toEqual({ visible: '', done: false })
    expect(JSON.stringify(reveal(text, NaN))).toBe(JSON.stringify(reveal(text, NaN)))
    expect(reveal(text, -Infinity)).toEqual({ visible: '', done: false })
    // +Infinity reveals all.
    expect(reveal(text, Infinity)).toEqual({ visible: text, done: true })
  })

  it('empty string is immediately done', () => {
    expect(reveal('', 0)).toEqual({ visible: '', done: true })
  })
})

describe('H-2 button gate', () => {
  it('renders NO buttons in living mode, whatever is offered', () => {
    expect(gateButtons({ mode: 'living' })).toEqual([])
    expect(
      gateButtons({ mode: 'living', offered: ['Sign', 'Send', 'Next'] })
    ).toEqual([])
  })

  it('renders the full set in canonical order in hatching mode by default', () => {
    const kinds = gateButtons({ mode: 'hatching' }).map((b) => b.kind)
    expect(kinds).toEqual([...HATCH_BUTTON_ORDER])
  })

  it('renders only the offered subset, still in canonical order', () => {
    const kinds = gateButtons({
      mode: 'hatching',
      offered: ['Send', 'Back'], // offered out of order…
    }).map((b) => b.kind)
    expect(kinds).toEqual(['Back', 'Send']) // …rendered in canonical order
  })

  it('honors the disabled set without dropping the button', () => {
    const out = gateButtons({
      mode: 'hatching',
      offered: ['Validate', 'Send'],
      disabled: ['Send'],
    })
    expect(out).toEqual([
      { kind: 'Validate', disabled: false },
      { kind: 'Send', disabled: true },
    ])
  })
})

describe('renderFrame — variants', () => {
  const base: DialogFrameInput = {
    mode: 'hatching',
    text: 'question one',
    tick: 0,
    openedAtTick: 0,
  }

  it('typewriter variant: body reveals off (tick − openedAtTick)', () => {
    // Opened at tick 10; at tick 12 that is 2 ticks elapsed.
    const f = renderFrame({ ...base, tick: 12, openedAtTick: 10 })
    expect(f.body).toBe('question one'.slice(0, 2 * CPT))
    expect(f.hasInput).toBe(false)
    expect(f.inputValue).toBe('')
  })

  it('input-row variant: a controlled value (even empty) renders the row', () => {
    expect(renderFrame({ ...base, input: '' }).hasInput).toBe(true)
    expect(renderFrame({ ...base, input: 'typed' })).toMatchObject({
      hasInput: true,
      inputValue: 'typed',
    })
    // Omitted / null → plain typewriter dialog, no row.
    expect(renderFrame({ ...base, input: null }).hasInput).toBe(false)
    expect(renderFrame(base).hasInput).toBe(false)
  })

  it('living mode never carries buttons even with handlers offered', () => {
    const f = renderFrame({
      ...base,
      mode: 'living',
      offered: ['Send', 'Sign'],
    })
    expect(f.buttons).toEqual([])
  })
})

describe('determinism replay — same props + ticks => byte-identical frames', () => {
  function sequence(input: Omit<DialogFrameInput, 'tick'>, ticks: number): string {
    const frames = []
    for (let t = 0; t <= ticks; t++) frames.push(renderFrame({ ...input, tick: t }))
    return JSON.stringify(frames)
  }

  it('a replayed hatching sequence is identical byte-for-byte', () => {
    const input: Omit<DialogFrameInput, 'tick'> = {
      mode: 'hatching',
      text: 'Welcome to the hatchery. Answer to continue.',
      openedAtTick: 0,
      input: 'draft answer',
      offered: ['Back', 'Next', 'Validate'],
      disabledButtons: ['Validate'],
    }
    expect(sequence(input, 40)).toBe(sequence(input, 40))
  })

  it('a replayed living sequence is identical and button-free throughout', () => {
    const input: Omit<DialogFrameInput, 'tick'> = {
      mode: 'living',
      text: 'A read-only living-world notice.',
      openedAtTick: 3,
    }
    const first = sequence(input, 30)
    expect(first).toBe(sequence(input, 30))
    // No button ever appears across the whole replay (H-2).
    expect(first).not.toMatch(/"kind"/)
  })
})
