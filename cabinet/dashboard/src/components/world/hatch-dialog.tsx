'use client'

/**
 * HatchDialog — the ONE reusable pixel dialog (spec v2 §9.2 / §15.6; hatching
 * plan §7.1). A thin, side-effect-free view over the pure hatch-dialog model:
 * it renders renderFrame(props) and holds no state of its own; the pure model
 * decides what paints. The parent owns the
 * director tick and every actuation — the button set is handler PROPS, so this
 * tree imports no server action (ratchet #1b: only killswitch-lever may).
 *
 * Variants (all one component, no fork):
 *   - typewriter      — a body that reveals over ticks.
 *   - input-row       — + a controlled input (the v3 library-query customer).
 *   - hatching buttons— the H-2 set (Back/Next/Validate/Sign/Send), rendered
 *                       ONLY when mode='hatching'. In living mode the gate
 *                       returns [] and no button paints (read-only + deep-link).
 *
 * Typography law (§9.2 / §15.6): the body and every datum render in DOM mono
 * (legible interior); the frame is parchment (Harvestholm). Never the heavy
 * frame or red — that salience is killswitch-only.
 */
import {
  renderFrame,
  type DialogMode,
  type HatchButton,
} from '@/lib/world/hatch-dialog'
import PixelFrame, { type FrameTheme } from './pixel-frame'

export interface HatchDialogProps {
  /** 'hatching' = onboarding window (buttons render); 'living' = read-only
   *  living-world dialog (NO buttons — H-2, deep-link only). */
  mode: DialogMode
  /** Short title label (base ui-pack law: the title bar carries close). */
  title: string
  /** Body text, typewritten over ticks (data-bearing → DOM mono). */
  text: string
  /** The shell's logical director tick + the tick the dialog opened at; the
   *  reveal counts (tick − openedAtTick). No wall clock (ratchet #4). */
  tick: number
  openedAtTick: number
  /** Input-row variant: a controlled value (even '') renders the row; omit for
   *  a plain typewriter dialog. */
  input?: string | null
  onInputChange?: (value: string) => void
  /** Which hatching buttons this step offers / disables (ignored in living
   *  mode — the gate returns [] there by construction). */
  offered?: readonly HatchButton[]
  disabledButtons?: readonly HatchButton[]
  /** Hatching button handlers — the component actuates NOTHING itself. */
  onBack?: () => void
  onNext?: () => void
  onValidate?: () => void
  onSign?: () => void
  onSend?: () => void
  /** Base close (esc) — rendered only when provided. */
  onClose?: () => void
  /** Frame theme — parchment (Harvestholm) by default; heavy is refused by
   *  the type (reserved-salience law: heavy = killswitch only). */
  theme?: Exclude<FrameTheme, 'heavy'>
}

export default function HatchDialog({
  mode,
  title,
  text,
  tick,
  openedAtTick,
  input,
  onInputChange,
  offered,
  disabledButtons,
  onBack,
  onNext,
  onValidate,
  onSign,
  onSend,
  onClose,
  theme = 'parchment',
}: HatchDialogProps) {
  const frame = renderFrame({
    mode,
    text,
    tick,
    openedAtTick,
    input,
    offered,
    disabledButtons,
  })

  // Handler lookup — the gated list drives WHICH buttons paint; this only maps
  // an already-authorized kind to its parent-owned callback.
  const handlers: Partial<Record<HatchButton, (() => void) | undefined>> = {
    Back: onBack,
    Next: onNext,
    Validate: onValidate,
    Sign: onSign,
    Send: onSend,
  }

  return (
    <PixelFrame
      theme={theme}
      className="pointer-events-auto fixed left-1/2 top-24 z-40 w-[28rem] max-w-[92vw] -translate-x-1/2"
    >
      <div className="flex items-center justify-between border-b border-zinc-700 px-3 py-2">
        <span className="truncate text-sm font-semibold">{title}</span>
        {onClose ? (
          <button
            onClick={onClose}
            className="ml-2 rounded px-2 py-0.5 text-xs text-zinc-400 hover:bg-zinc-800"
            aria-label="close commissioning dialog"
          >
            esc
          </button>
        ) : null}
      </div>

      <div className="p-3">
        {/* Typewriter body — DOM mono for the datum (§9.2 / §15.6). */}
        <p
          data-typewriter
          className="whitespace-pre-wrap font-mono text-[13px] leading-relaxed text-zinc-100"
        >
          {frame.body}
          {!frame.revealed ? (
            <span aria-hidden className="opacity-60">
              ▋
            </span>
          ) : null}
        </p>

        {frame.hasInput ? (
          <div className="mt-3">
            <input
              value={frame.inputValue}
              onChange={(e) => onInputChange?.(e.target.value)}
              className="w-full rounded border border-zinc-600 bg-zinc-950 px-2 py-1 font-mono text-[13px] text-zinc-100 outline-none focus:border-zinc-400"
              aria-label="commissioning dialog input"
            />
          </div>
        ) : null}

        {frame.buttons.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2 border-t border-zinc-800 pt-3">
            {frame.buttons.map((b) => (
              <button
                key={b.kind}
                disabled={b.disabled}
                onClick={() => handlers[b.kind]?.()}
                className="rounded border border-zinc-600 px-3 py-1 text-xs font-medium text-zinc-100 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {b.kind}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </PixelFrame>
  )
}
