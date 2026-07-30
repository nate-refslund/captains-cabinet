'use client'

/**
 * KillswitchLever — THE one in-world actuator (Captain ruling 2026-07-09;
 * spec §9.3). Everything else in the world reads, inspects, or deep-links;
 * this lever, alone, acts.
 *
 * - Renders REAL state every frame: the emergency-stop reading arrives on the
 *   SSE snapshot (the chronicle daemon asks the ONE reader each tick), so
 *   out-of-band shell flips render truthfully here too.
 * - THREE STATES, never two (2026-07-31). The prop is a `KillswitchGlance`,
 *   not a boolean, because a boolean has nowhere to put "nobody could read
 *   it" — and `?? false` silently put it in the same pixels as "verified not
 *   engaged". A tagged union cannot be coerced back: no `??` turns
 *   `{state:'unknown'}` into `{state:'clear'}`, and the word on the pin comes
 *   from `killswitchWord`, which never returns UP for an unknown.
 * - Break-through: the pin renders in the HUD above night tint / weather /
 *   red wash (z-60 > the killswitch wash's z-50) — findable ≤2s at any zoom.
 * - Two-tap + confirm + cookie: tap 1 arms (amber, 10s auto-expire — pure
 *   tick-driven machine in lib/world/lever.ts) and opens the heavy confirm
 *   frame (the ONLY surface that frame appears on); tap 2 fires the EXISTING
 *   dashboard killswitch write (src/actions/killswitch.ts — the same server
 *   action the home-page Kill Switch card has always used; no new write
 *   machinery). Without the captain session the lever is view-only: truth
 *   renders, the act refuses.
 * - INTENT IS NEVER GUESSED. It used to be `active ? 'deactivate' :
 *   'activate'`, which under an unknown reading derives the direction from the
 *   very guess it is meant to avoid. `intentFor` returns null for an unknown
 *   state, and the dialog then asks WHICH WAY with two explicit verbs —
 *   capability preserved, guess removed.
 * - Honest degradation: a failed call prints the exact CLI fallback
 *   command — never a silent failure.
 * - Witness: state changes are observed by the chronicle daemon's presence
 *   snapshot each tick. Per-pull actor attribution (`killswitch.pull`
 *   chronicle verb, P-KS) is future plumbing — the card says so rather than
 *   inventing a who.
 *
 * RATCHET NOTE: world ratchet #1 carries a single-file carve-out for this
 * component (the ONE actuator); ui-layer.test.ts asserts no OTHER world
 * file imports any server action.
 */
import { useEffect, useRef, useState } from 'react'
import { toggleKillSwitch } from '@/actions/killswitch'
import {
  fallbackCommandFor,
  intentFor,
  killswitchAttr,
  killswitchGlyph,
  killswitchTitle,
  killswitchWord,
  KILLSWITCH_CHECK_COMMAND,
  type KillswitchGlance,
} from '@/lib/world/killswitch'
import { LEVER_IDLE, leverReduce, type LeverState } from '@/lib/world/lever'
import PixelFrame from './pixel-frame'

export default function KillswitchLever({
  state,
  tick,
  canActuate,
}: {
  /** REAL emergency-stop reading from the SSE snapshot (never a local guess). */
  state: KillswitchGlance
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

  const engaged = state.state === 'engaged'
  const unknown = state.state === 'unknown'
  /** null exactly when the reading is unknown — the dialog then asks. */
  const defaultIntent = intentFor(state)

  const dispatch = (
    ev: Parameters<typeof leverReduce>[1],
    explicitIntent?: 'activate' | 'deactivate'
  ) => {
    const out = leverReduce(leverRef.current, ev, { tick, canActuate })
    leverRef.current = out.state
    setLever(out.state)
    if (!out.fire || firing.current) return
    const intent = explicitIntent ?? defaultIntent
    if (!intent) {
      // Unreachable by construction: under an unknown reading the pin's tap
      // only ever ARMS, and each dialog verb passes its own intent. Refusing
      // rather than picking one keeps the guess out even if a future edit
      // wires a bare tap straight to fire.
      dispatch({
        type: 'result',
        ok: false,
        error: `the emergency stop is UNREADABLE, so there is no direction to pin — choose ENGAGE or RELEASE, or run: ${KILLSWITCH_CHECK_COMMAND}`,
      })
      return
    }
    firing.current = true
    // The ONE actuation path: the pre-existing dashboard server action
    // (Redis SET/DEL cabinet:killswitch, read back before it reports
    // success). Intent is pinned to an END STATE, so a stale toggle can
    // never invert the Captain's intent.
    toggleKillSwitch(intent)
      .then((r) =>
        dispatch({
          type: 'result',
          ok: !!r?.success,
          error: r?.success
            ? undefined
            : `${r?.error ?? 'actuation failed'} — run: ${fallbackCommandFor(intent)}`,
        })
      )
      .catch(() =>
        dispatch({
          type: 'result',
          ok: false,
          error: `actuation unreachable — run: ${fallbackCommandFor(intent)}`,
        })
      )
      .finally(() => {
        firing.current = false
      })
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
        data-world-lever={killswitchAttr(state)}
        onClick={() => dispatch({ type: 'tap' })}
        title={killswitchTitle(state)}
        aria-label={killswitchTitle(state)}
        className={
          'pointer-events-auto absolute right-3 top-12 z-[60] flex items-center gap-1 rounded px-2 py-1 font-mono text-[11px] font-bold ' +
          (engaged
            ? 'animate-pulse bg-red-900 text-red-100'
            : unknown
              ? // NOT the calm zinc of a verified-up lever, and NOT red — red
                // claims the stop IS engaged, the opposite guess. Dashed amber
                // on dark reads as "this is not a reading".
                'border border-dashed border-amber-400 bg-zinc-900/90 text-amber-200'
              : armed
                ? 'bg-amber-900 text-amber-100'
                : 'bg-zinc-900/90 text-zinc-300 hover:bg-zinc-800')
        }
      >
        {/* lever glyph: pixel-drawn state, dual-coded with the word */}
        <span aria-hidden className="inline-block leading-none">
          {killswitchGlyph(state)}
        </span>
        LEVER {killswitchWord(state)}
      </button>

      {/* ── the heavy confirm dialog (two-tap ceremony) ── */}
      {dialogOpen && (
        <div className="pointer-events-auto fixed inset-0 z-[70] flex items-center justify-center bg-black/50">
          <PixelFrame theme="heavy" className="w-[28rem] max-w-[94vw]">
            <div className="p-4 text-sm">
              <div className="mb-2 font-bold text-zinc-100">
                {unknown
                  ? 'The killswitch state is UNKNOWN'
                  : engaged
                    ? 'RELEASE the killswitch?'
                    : 'PULL the killswitch?'}
              </div>
              <p className="mb-2 text-xs text-zinc-300">
                {unknown
                  ? 'Nobody knows whether the fleet is halted. This is not "not engaged" — it is unread. Choose the state you want; nothing is toggled from a guess.'
                  : engaged
                    ? 'Officer operations resume: sessions act again on their next tool invocation.'
                    : 'All officer operations halt on their next tool invocation — not instantly.'}
              </p>
              <div className="mb-2 rounded bg-zinc-950 p-2 font-mono text-[11px] text-zinc-400">
                {state.state === 'unknown' ? (
                  <div data-world-lever-reason className="text-amber-300">
                    NO READING: {state.reason}
                  </div>
                ) : (
                  // Says what it IS — the last snapshot reading — rather than
                  // "PROOF: redis GET …", which claimed a fresh round trip
                  // this dialog has never performed.
                  <div>
                    LAST SNAPSHOT READING: cabinet:killswitch ={' '}
                    {engaged ? '"active"' : '(absent)'}
                  </div>
                )}
                <div className="text-zinc-600">
                  verify out of band: {KILLSWITCH_CHECK_COMMAND} · witness:
                  chronicle presence snapshot observes this key each tick;
                  per-pull actor attribution is future plumbing (P-KS)
                </div>
              </div>
              {lever.phase === 'armed' && (
                <p className="mb-2 text-[11px] text-amber-300">
                  armed — auto-disarms in 10s.{' '}
                  {canActuate
                    ? unknown
                      ? 'Pick a verb below; each acts on its second tap.'
                      : 'Second tap on PULL acts.'
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
                {armed &&
                  (unknown ? (
                    // Two explicit verbs: capability kept, direction stated.
                    (['activate', 'deactivate'] as const).map((intent) => (
                      <button
                        key={intent}
                        onClick={() => dispatch({ type: 'tap' }, intent)}
                        disabled={!canActuate}
                        className={
                          'rounded px-3 py-1 text-xs font-bold ' +
                          (canActuate
                            ? intent === 'activate'
                              ? // the ONLY red interactive element anywhere
                                'bg-red-700 text-white hover:bg-red-600'
                              : 'bg-emerald-700 text-white hover:bg-emerald-600'
                            : 'cursor-not-allowed bg-zinc-800 text-zinc-500')
                        }
                      >
                        {intent === 'activate' ? 'ENGAGE' : 'RELEASE'}
                      </button>
                    ))
                  ) : (
                    <button
                      onClick={() => dispatch({ type: 'tap' })}
                      disabled={!canActuate}
                      className={
                        'rounded px-3 py-1 text-xs font-bold ' +
                        (canActuate
                          ? engaged
                            ? 'bg-emerald-700 text-white hover:bg-emerald-600'
                            : // the ONLY red interactive element anywhere
                              'bg-red-700 text-white hover:bg-red-600'
                          : 'cursor-not-allowed bg-zinc-800 text-zinc-500')
                      }
                    >
                      {engaged ? 'RELEASE' : 'PULL'}
                    </button>
                  ))}
              </div>
            </div>
          </PixelFrame>
        </div>
      )}
    </>
  )
}
