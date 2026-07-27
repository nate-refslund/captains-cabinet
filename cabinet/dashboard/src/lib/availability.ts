/**
 * The availability dial's VALUE GRAMMAR for the dashboard — the strict
 * allowlist that stands between a settings form and a shell command.
 *
 * WHY A MIRROR EXISTS AT ALL. `framework/env.py` owns the canonical table
 * (`AVAILABILITY_MODES`, `AVAILABILITY_MAX_MINUTES`) and
 * `cabinet/scripts/lib/captain_availability.py` deliberately refuses to keep a
 * fallback copy of it — "a second copy of the bands would drift, and a drifted
 * budget is worse than a verb that fails open". The dashboard is a different
 * runtime in a different language and cannot import that table, so it keeps a
 * mirror the way the READ side already mirrors the precedence rule
 * (`lib/config.ts`) — and pays for it with a parity arm that reads
 * `framework/env.py` and reds the build the moment the two disagree
 * (`availability.test.ts`). A mirror without that arm IS the drift the lib
 * warns about; with it, drift cannot merge.
 *
 * STRICT ALLOWLIST. Exactly two shapes are admitted: a canonical mode verb
 * from the table, or a whole number of minutes 0..1440. That is deliberately
 * narrower than the phone grammar ("2h", "1.5h", "20 min"): every form the
 * dashboard accepts is a form this file must keep in step with the python
 * parser, and the picker offers the modes anyway.
 *
 * REFUSE, DON'T ROUND. "90.5" is neither 90 nor 91 — it is a number the dial
 * cannot represent, so it comes back to the Captain untouched. Same rule the
 * phone verb applies to a fractional minute.
 *
 * THE CANONICAL TOKEN. A successful parse carries `cli`: the token re-derived
 * from the table or from the parsed integer, never the caller's string. The
 * server action interpolates THAT into the command it runs, so a shell
 * metacharacter cannot survive parsing even in principle.
 *
 * The value itself is something the Captain declared about HIMSELF. It is a
 * budget — what may reach him — never a measure of anyone, and no surface here
 * may render it as one.
 */

export interface AvailabilityMode {
  /** canonical verb — what the store, the phone verb and the resolver use */
  mode: string
  /** the band's minutes per day */
  minutes: number
  /** what the Captain reads in the picker */
  label: string
}

/**
 * Mirrors `framework/env.py::AVAILABILITY_MODES`, least → most available.
 * `mode` and `minutes` are load-bearing and pinned by the parity arm; `label`
 * is this surface's own wording.
 */
export const AVAILABILITY_MODES: readonly AvailabilityMode[] = [
  { mode: 'away', minutes: 0, label: 'Away — nothing but a genuine emergency' },
  { mode: 'minimal', minutes: 10, label: 'Minimal — about 10 minutes a day' },
  { mode: 'part_time', minutes: 30, label: 'Part-time — about 30 minutes a day' },
  { mode: 'substantial', minutes: 120, label: 'Substantial — about 2 hours a day' },
  { mode: 'full_time', minutes: 480, label: 'Full-time — the cabinet is my main seat' },
]

/** Mirrors `framework/env.py::AVAILABILITY_MAX_MINUTES` — minutes in a day. */
export const AVAILABILITY_MAX_MINUTES = 24 * 60

export interface ParsedAvailability {
  kind: 'mode' | 'minutes'
  minutes: number
  mode: string | null
  /** the canonical token to hand the writer — never the caller's raw string */
  cli: string
}

/** Digits only: no sign, no decimal point, no exponent, no unit suffix. */
const MINUTES_TOKEN_RE = /^\d{1,4}$/

/**
 * A shell-inert verb shape. The verbs all come from the table above, so this
 * guards the TABLE rather than the input: a mode added later with a space or a
 * quote in it is refused here instead of reaching a command string.
 */
const MODE_TOKEN_RE = /^[a-z][a-z_]{0,31}$/

/**
 * `raw` → a canonical availability value, or null when the dial cannot hold
 * it. Null is a refusal, never a repair.
 */
export function parseAvailabilityValue(raw: unknown): ParsedAvailability | null {
  if (typeof raw !== 'string') return null
  const trimmed = raw.trim()
  if (!trimmed) return null

  if (MINUTES_TOKEN_RE.test(trimmed)) {
    const minutes = Number(trimmed)
    if (!Number.isInteger(minutes)) return null
    if (minutes < 0 || minutes > AVAILABILITY_MAX_MINUTES) return null
    return { kind: 'minutes', minutes, mode: null, cli: String(minutes) }
  }

  // Hyphen and case are tolerated the way the phone verb tolerates them
  // ("part-time", "FULL_TIME"); everything else must match the enum exactly.
  const verb = trimmed.toLowerCase().replace(/-/g, '_')
  if (!MODE_TOKEN_RE.test(verb)) return null
  const found = AVAILABILITY_MODES.find((m) => m.mode === verb)
  if (!found) return null
  if (!MODE_TOKEN_RE.test(found.mode)) return null
  return { kind: 'mode', minutes: found.minutes, mode: found.mode, cli: found.mode }
}

/** The one sentence every surface uses to say why a value was refused. */
export const AVAILABILITY_REFUSAL =
  'That is not a budget the dial can hold. Give whole minutes from 0 to ' +
  `${AVAILABILITY_MAX_MINUTES}, or one of: ` +
  AVAILABILITY_MODES.map((m) => m.mode).join(', ') +
  '.'

/**
 * The declared budget as one plain line, or an honest absence. UNKNOWN is a
 * legal state and means "nobody has said" — never a zero, which is the real
 * ruling `away`.
 */
export function renderAvailability(a: {
  minutesPerDay: number | null
  mode: string | null
}): string {
  if (a.minutesPerDay === null) return 'Not set'
  const band = a.mode ? ` (${a.mode.replace(/_/g, ' ')})` : ''
  return `${a.minutesPerDay} min/day${band}`
}
