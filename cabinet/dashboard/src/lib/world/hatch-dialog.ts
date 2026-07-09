/**
 * hatch-dialog — the ONE reusable pixel-dialog model (spec v2 §9.2 / §15.6;
 * hatching plan §7.1). Pulled forward from the v3 library-query dialog
 * family: hatching is the earlier customer, the living-world query dialog is
 * the later one — SAME component, no fork. The mode prop is the only
 * difference between customers.
 *
 * PURE + tick-based: no wall clock — determinism ratchet #4. The typewriter
 * reveal and the button gate are pure functions of (props, tick), so the
 * same props replayed over the same ticks produce byte-identical frames
 * (hatching plan L635: "same answers + ticks => byte-identical frames"). The
 * .tsx owns side effects (the director tick, input focus); this module owns
 * every visible decision — mirroring lever.ts.
 */

/** Characters revealed per logical director tick (250ms). Tuning knob; the
 *  determinism property holds at any value, so tests derive from it. */
export const REVEAL_CHARS_PER_TICK = 2

/**
 * Dialog mode — the H-2 seam.
 *   living   — a read-only living-world dialog: NO buttons, deep-link only
 *              (room ruling 2026-07-09; the living mailbox never actuates).
 *   hatching — the onboarding window: the hatching button set renders. These
 *              dialogs only ever exist on hatching routes, so the buttons are
 *              unreachable outside the window by construction.
 */
export type DialogMode = 'living' | 'hatching'

/** The H-2 hatching button set (plan L80-83). Never rendered in living mode. */
export type HatchButton = 'Back' | 'Next' | 'Validate' | 'Sign' | 'Send'

/** Canonical render order: navigate, then commit. */
export const HATCH_BUTTON_ORDER: readonly HatchButton[] = [
  'Back',
  'Next',
  'Validate',
  'Sign',
  'Send',
]

export interface RevealState {
  /** The visible prefix of the full text at this tick. */
  visible: string
  /** True once the whole string has been revealed (idempotent thereafter). */
  done: boolean
}

/**
 * Pure typewriter: the visible prefix after `ticks` logical ticks since the
 * reveal began. A function of (text, ticks) alone — no clock, no randomness
 * (ratchet #4), so it is replay-identical. Negative/zero ticks reveal
 * nothing; ticks past the end clamp to the full string.
 */
export function reveal(text: string, ticks: number): RevealState {
  // Slice by code point, not UTF-16 unit, so a multi-unit glyph (emoji, astral
  // char) never flashes as a lone broken surrogate mid-reveal.
  const chars = Array.from(text)
  const total = chars.length
  // Non-finite guard: a director clock is always a finite integer, but a NaN /
  // −Infinity tick must still resolve to a DEFINED frame, never undefined
  // arithmetic (silent-blank is the failure class this tree ratchets against).
  // +Infinity reveals all; NaN / −Infinity reveal nothing.
  const steps = Number.isFinite(ticks)
    ? Math.max(0, Math.floor(ticks))
    : ticks === Infinity
      ? total
      : 0
  const count = Math.min(total, steps * REVEAL_CHARS_PER_TICK)
  return { visible: chars.slice(0, count).join(''), done: count >= total }
}

/** Logical ticks required to fully reveal `text` (for caller scheduling).
 *  Counts code points, matching reveal()'s unit. */
export function ticksToReveal(text: string): number {
  return Math.ceil(Array.from(text).length / REVEAL_CHARS_PER_TICK)
}

export interface ButtonGateInput {
  mode: DialogMode
  /** Buttons this step offers (subset of the set); defaults to the full set. */
  offered?: readonly HatchButton[]
  /** Buttons shown but disabled (e.g. Send before Validate passes). */
  disabled?: readonly HatchButton[]
}

export interface GatedButton {
  kind: HatchButton
  disabled: boolean
}

/**
 * The H-2 gate. Buttons exist ONLY in hatching mode: in living mode this is
 * ALWAYS the empty list — a living-world dialog is read-only + deep-link by
 * construction, never actuating. In hatching mode the offered subset renders
 * in canonical order, honoring the disabled set.
 */
export function gateButtons(input: ButtonGateInput): GatedButton[] {
  if (input.mode !== 'hatching') return []
  const offered = new Set(input.offered ?? HATCH_BUTTON_ORDER)
  const disabled = new Set(input.disabled ?? [])
  return HATCH_BUTTON_ORDER.filter((kind) => offered.has(kind)).map((kind) => ({
    kind,
    disabled: disabled.has(kind),
  }))
}

export interface DialogFrameInput {
  mode: DialogMode
  /** Full body text to typewrite (data-bearing → DOM mono in the view). */
  text: string
  /** The shell's current logical director tick. */
  tick: number
  /** Tick the dialog opened at; the reveal counts (tick − openedAtTick). */
  openedAtTick: number
  /** Input-row variant: a controlled value (even '') renders the row; null /
   *  undefined renders a plain typewriter dialog. */
  input?: string | null
  /** Hatching button offer / disable (ignored unless mode === 'hatching'). */
  offered?: readonly HatchButton[]
  disabledButtons?: readonly HatchButton[]
}

export interface DialogFrame {
  mode: DialogMode
  /** The visible (typewritten) body at this tick. */
  body: string
  /** True once the body is fully revealed. */
  revealed: boolean
  /** Whether the input row renders (input-row variant). */
  hasInput: boolean
  /** The input's current value ('' when hasInput but empty). */
  inputValue: string
  /** The gated button list — always [] in living mode (H-2). */
  buttons: GatedButton[]
}

/**
 * The ONE pure frame function. Everything the dialog paints at a given tick
 * is a deterministic function of its props, so renderFrame(p) called any
 * number of times with equal props yields a byte-identical frame (determinism
 * replay). The .tsx renders THIS; it decides nothing itself.
 */
export function renderFrame(input: DialogFrameInput): DialogFrame {
  const elapsed = input.tick - input.openedAtTick
  const r = reveal(input.text, elapsed)
  const hasInput = input.input !== undefined && input.input !== null
  return {
    mode: input.mode,
    body: r.visible,
    revealed: r.done,
    hasInput,
    inputValue: hasInput ? (input.input as string) : '',
    // The frame input names it `disabledButtons` (clarity at the component
    // boundary); the gate primitive names the same concept `disabled` — bridged
    // here, the one place the two layers meet.
    buttons: gateButtons({
      mode: input.mode,
      offered: input.offered,
      disabled: input.disabledButtons,
    }),
  }
}
