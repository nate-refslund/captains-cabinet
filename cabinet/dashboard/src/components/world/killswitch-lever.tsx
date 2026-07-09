'use client'

/**
 * KillswitchLever — THE one in-world actuator (Captain ruling 2026-07-09;
 * spec §9.3). Everything else in the world reads, inspects, or deep-links;
 * this lever, alone, acts.
 *
 * - Renders REAL state every frame: `killswitch` arrives on the SSE
 *   snapshot (E0b polls GET cabinet:killswitch each tick), so out-of-band
 *   shell flips render truthfully here too.
 * - Break-through: the pin renders in the HUD above night tint / weather /
 *   red wash (z-60 > the killswitch wash's z-50) — findable ≤2s at any zoom.
 * - Two-tap + confirm + cookie: tap 1 arms (amber, 10s auto-expire — pure
 *   tick-driven machine in lib/world/lever.ts) and opens the heavy confirm
 *   frame (the ONLY surface that frame appears on); tap 2 PULL fires the
 *   EXISTING dashboard killswitch write (src/actions/killswitch.ts — the
 *   same server action the home-page Kill Switch card has always used; no
 *   new write machinery). Without the captain session the lever is
 *   view-only: truth renders, PULL refuses.
 * - Honest degradation: a failed call prints the exact CLI fallback
 *   command — never a silent failure.
 * - Witness: state changes are observed by the chronicle daemon's presence
 *   snapshot (killswitch flag each tick). Per-pull actor attribution
 *   (`killswitch.pull` chronicle verb, P-KS) is future plumbing — the card
 *   says so rather than inventing a who.
 *
 * RATCHET NOTE: world ratchet #1 carries a single-file carve-out for this
 * component (the ONE actuator); ui-layer.test.ts asserts no OTHER world
 * file imports any server action.
 */
import { useEffect, useRef, useState } from 'react'
import { toggleKillSwitch } from '@/actions/killswitch'
import {
  fallbackCommand,
  LEVER_IDLE,
  leverReduce,
  type LeverState,
} from '@/lib/world/lever'
import PixelFrame from './pixel-frame'

export default function KillswitchLever({
  active,
  tick,
  canActuate,
}: {
  /** REAL killswitch state from the SSE snapshot (never local guess). */
  active: boolean
  /** Logical director tick — drives the 10s arm expiry (no wall clock). */
  tick: number
  /** Captain session present (server-verified) — the actuation gate. */
  canActuate: boolean
}) {
  const [lever, setLever] = useState<LeverState>(LEVER_IDLE)
  // Ref mirror so dispatch reduces from the CURRENT state without putting
  // side effects inside a React updater (StrictMode double-invoke safety).
  const leverRef = useRef<LeverState>(LEVER_IDLE)
  const firing = useRef(false)

  const dispatch = (ev: Parameters<typeof leverReduce>[1]) => {
    const out = leverReduce(leverRef.current, ev, { tick, canActuate })
    leverRef.current = out.state
    setLever(out.state)
    if (out.fire && !firing.current) {
      firing.current = true
      // The ONE actuation path: the pre-existing dashboard server action
      // (Redis SET/DEL cabinet:killswitch). Intent pinned to the rendered
      // state so a stale toggle can never invert the Captain's intent.
      toggleKillSwitch(active ? 'deactivate' : 'activate')
        .then((r) =>
          dispatch({
            type: 'result',
            ok: !!r?.success,
            error: r?.success
              ? undefined
              : `${r?.error ?? 'actuation failed'} — run: ${fallbackCommand(active)}`,
          })
        )
        .catch(() =>
          dispatch({
            type: 'result',
            ok: false,
            error: `actuation unreachable — run: ${fallbackCommand(active)}`,
          })
        )
        .finally(() => {
          firing.current = false
        })
    }
  }
  // Tick the machine (auto-expiry) from the shell's logical clock.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => dispatch({ type: 'tick', tick }), [tick])

  const dialogOpen = lever.phase !== 'idle'
  const armed = lever.phase === 'armed'

  return (
    <>
      {/* ── the far-zoom lever pin: break-through, always locatable ── */}
      <button
        data-world-lever={active ? 'thrown' : 'up'}
        onClick={() => dispatch({ type: 'tap' })}
        title={`killswitch lever — ${active ? 'THROWN (fleet halted)' : 'up (fleet running)'}`}
        className={
          'pointer-events-auto absolute right-3 top-12 z-[60] flex items-center gap-1 rounded px-2 py-1 font-mono text-[11px] font-bold ' +
          (active
            ? 'animate-pulse bg-red-900 text-red-100'
            : armed
              ? 'bg-amber-900 text-amber-100'
              : 'bg-zinc-900/90 text-zinc-300 hover:bg-zinc-800')
        }
      >
        {/* lever glyph: pixel-drawn state, dual-coded with the word */}
        <span aria-hidden className="inline-block leading-none">
          {active ? '↓' : '↑'}
        </span>
        LEVER {active ? 'THROWN' : 'UP'}
      </button>

      {/* ── the heavy confirm dialog (two-tap ceremony) ── */}
      {dialogOpen && (
        <div className="pointer-events-auto fixed inset-0 z-[70] flex items-center justify-center bg-black/50">
          <PixelFrame theme="heavy" className="w-[28rem] max-w-[94vw]">
            <div className="p-4 text-sm">
              <div className="mb-2 font-bold text-zinc-100">
                {active ? 'RELEASE the killswitch?' : 'PULL the killswitch?'}
              </div>
              <p className="mb-2 text-xs text-zinc-300">
                {active
                  ? 'Officer operations resume: sessions act again on their next tool invocation.'
                  : 'All officer operations halt on their next tool invocation — not instantly.'}
              </p>
              <div className="mb-2 rounded bg-zinc-950 p-2 font-mono text-[11px] text-zinc-400">
                <div>
                  PROOF: redis GET cabinet:killswitch →{' '}
                  {active ? '"active"' : '(nil)'}
                </div>
                <div className="text-zinc-600">
                  witness: chronicle presence snapshot observes this key each
                  tick; per-pull actor attribution is future plumbing (P-KS)
                </div>
              </div>
              {lever.phase === 'armed' && (
                <p className="mb-2 text-[11px] text-amber-300">
                  armed — auto-disarms in 10s.{' '}
                  {canActuate
                    ? 'Second tap on PULL acts.'
                    : 'View-only: no captain session — the lever renders truth, you cannot act.'}
                </p>
              )}
              {lever.phase === 'pending' && (
                <p className="mb-2 text-[11px] text-zinc-400">acting…</p>
              )}
              {lever.phase === 'ok' && (
                <p className="mb-2 text-[11px] text-emerald-300">
                  done — the world renders the new state on the next snapshot.
                </p>
              )}
              {lever.phase === 'fail' && (
                <p className="mb-2 break-all font-mono text-[11px] text-red-300">
                  {lever.error}
                </p>
              )}
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => dispatch({ type: 'abort' })}
                  className="rounded bg-zinc-800 px-3 py-1 text-xs font-medium text-zinc-200 hover:bg-zinc-700"
                >
                  {lever.phase === 'ok' || lever.phase === 'fail' ? 'close' : 'ABORT'}
                </button>
                {armed && (
                  <button
                    onClick={() => dispatch({ type: 'tap' })}
                    disabled={!canActuate}
                    className={
                      'rounded px-3 py-1 text-xs font-bold ' +
                      (canActuate
                        ? active
                          ? 'bg-emerald-700 text-white hover:bg-emerald-600'
                          : // the ONLY red interactive element anywhere
                            'bg-red-700 text-white hover:bg-red-600'
                        : 'cursor-not-allowed bg-zinc-800 text-zinc-500')
                    }
                  >
                    {active ? 'RELEASE' : 'PULL'}
                  </button>
                )}
              </div>
            </div>
          </PixelFrame>
        </div>
      )}
    </>
  )
}
