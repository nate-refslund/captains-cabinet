/**
 * FIRST-RUN PASSWORD BOOTSTRAP — the decisions that gate "the operator has not
 * chosen a dashboard password yet".
 *
 * WHY THIS EXISTS. A fresh Cabinet used to boot with a RANDOM DASHBOARD_PASSWORD
 * that setup-env.sh generated and copied to the clipboard; the only recovery the
 * login page offered was a Terminal command a non-technical operator could not
 * run. The Captain's call (2026-08-12): the operator CHOOSES their own password
 * on first open. So a fresh instance boots with NO password, the dashboard shows
 * a "create a password" screen, and every gated route stays closed until one is
 * set — the middleware already redirects to /login when no real password is
 * configured, and THAT is the first-run lock.
 *
 * These functions are PURE (the env and the request headers are injected) so the
 * security decisions are unit-testable without a running server. The "real
 * password" test mirrors lib/auth.resolveSecret / middleware / verdict.doorSecret
 * EXACTLY — one definition of "a password is configured", used everywhere.
 */

/**
 * Plain-language floor. Short and honest: this is the operator's OWN machine,
 * not an account with a breach history, so the bar is "not trivially guessable",
 * not an enterprise policy. Stated to the operator in plain words on screen.
 *
 * Lowered from 12 to 8 (Captain, 2026-08-25) together with dropping the charset
 * gate below: a floor people accept and a keyboard they can use whole beat a
 * longer floor typed around.
 */
export const PASSWORD_MIN_LENGTH = 8

/**
 * The ceiling, in CODE POINTS. Not a security bound — a sanity one, so a paste
 * accident or a stuck key cannot push a novel into the file every script reads.
 * Anything an operator types deliberately is far below it.
 */
export const PASSWORD_MAX_LENGTH = 128

/*
 * THE CHARSET GATE IS GONE (Captain, 2026-08-25: "allow all symbols").
 *
 * What used to be here: `/^[A-Za-z0-9._,:@%^+=-]+$/`, refusing spaces and every
 * shell metacharacter. Its stated reason was real at the time — cabinet/.env is
 * bash-`source`d by 30+ scripts under `set -a`, so a stored `$(…)` EXECUTED on
 * the next start, and a space broke the assignment.
 *
 * That reason no longer holds, and it is worth being precise about why rather
 * than trusting the deletion. The problem was never the password; it was that
 * the WRITER emitted values raw. `lib/config-write.envValueLiteral` now emits a
 * value bare only when it is provably literal unquoted, and SINGLE-QUOTES
 * everything else (`'` escaped as `'\''`), which bash treats as inert text — no
 * command substitution, no expansion, no word-splitting. That is proven against
 * a real bash in `lib/env-source-safety.test.ts`, and proven end-to-end from
 * this screen in `actions/create-password.test.ts`, where a chosen
 * `$(touch …)` password is written, sourced by bash, and comes back as the exact
 * literal with no side effect. Keeping the charset gate on top of a writer that
 * is already safe would only be making the operator pay for a fixed bug.
 *
 * So the remaining rules are the ones that are about the PASSWORD, not about the
 * file: long enough, not blank, not absurd, and no control characters.
 */

/**
 * The one refused class: Unicode control characters — C0 (including tab, CR and
 * LF), DEL, and C1.
 *
 * WHY THESE AND NOTHING ELSE. A control character cannot be typed into a
 * password box on purpose — Tab moves focus and Enter submits — so one that
 * arrives is always an accident of pasting (a copied line brings its newline
 * with it). It would be stored invisibly, and the operator would then be unable
 * to reproduce a password they cannot see. A newline is additionally impossible
 * to store at all: cabinet/.env is line-oriented, and the writer refuses one
 * outright, so accepting it here would only move the refusal somewhere with a
 * worse error message.
 */
// Written as explicit ranges rather than `\p{Cc}`: the same set, with no
// dependency on the Unicode-property-escape target level. C0 + DEL + C1.
// eslint-disable-next-line no-control-regex
const CONTROL_CHARS = /[\u0000-\u001F\u007F-\u009F]/

/** Code points, not UTF-16 units — an emoji is one character to the person typing it. */
function codePointLength(s: string): number {
  return Array.from(s).length
}

export type PasswordCheck = { ok: true } | { ok: false; error: string }

/**
 * TRUE when a real dashboard password is configured. Mirrors EXACTLY the
 * "real secret" test in lib/auth.resolveSecret / middleware / verdict.doorSecret:
 * a set value that is not the well-known dev placeholder 'changeme'. When this is
 * false, the dashboard is in the first-run "must create a password" state.
 */
export function hasRealPassword(env?: { DASHBOARD_PASSWORD?: string }): boolean {
  const s = (env ?? process.env).DASHBOARD_PASSWORD
  return !!(s && s !== 'changeme')
}

/**
 * Validate a freshly chosen password + its confirmation. Plain-language errors,
 * no "credential"/"policy"/"complexity" jargon — the reader is not technical.
 *
 * The password is taken EXACTLY as typed and is never trimmed, lower-cased or
 * normalised. A space at either end is part of the password, because the login
 * box will send it too and the comparison is byte-for-byte; silently eating one
 * here would lock the operator out of the password they just chose.
 */
export function validateChosenPassword(
  password: string,
  confirm: string
): PasswordCheck {
  const length = codePointLength(password)
  if (length < PASSWORD_MIN_LENGTH) {
    return {
      ok: false,
      error: `Please choose at least ${PASSWORD_MIN_LENGTH} characters, so it is not easy to guess.`,
    }
  }
  if (length > PASSWORD_MAX_LENGTH) {
    return {
      ok: false,
      error: `That is longer than ${PASSWORD_MAX_LENGTH} characters. Please shorten it a little.`,
    }
  }
  if (CONTROL_CHARS.test(password)) {
    return {
      ok: false,
      error:
        'That has a line break or another invisible character in it — probably from pasting. Those cannot be typed on purpose, so please type the password instead.',
    }
  }
  if (!password.trim()) {
    return {
      ok: false,
      error: 'That is only spaces. Please use something you could tell apart from an empty box.',
    }
  }
  if (password !== confirm) {
    return {
      ok: false,
      error: 'The two passwords do not match. Please type the same one in both boxes.',
    }
  }
  return { ok: true }
}

/**
 * TRUE for the loopback set: 127.0.0.0/8, ::1, ::ffff:127.x, and the name
 * `localhost`. Accepts a Host-style `hostname[:port]` or `[ipv6][:port]` as well
 * as a bare X-Forwarded-For address. Empty/absent ⇒ false (a missing Host is not
 * local). A single normaliser so the four request signals below judge "on-box"
 * the same way.
 */
function isLoopback(raw: string | null | undefined): boolean {
  if (!raw) return false
  let a = raw.trim().toLowerCase()
  if (!a) return false
  if (a.startsWith('[')) {
    // [ipv6] or [ipv6]:port — take what is inside the brackets.
    const end = a.indexOf(']')
    a = end === -1 ? a.replace(/[[\]]/g, '') : a.slice(1, end)
  } else if (a.split(':').length === 2) {
    // hostname:port or ipv4:port (exactly one colon) — drop the port. A bare
    // IPv6 (two+ colons, no brackets) is left intact so its address colons are
    // never mistaken for a port.
    a = a.slice(0, a.indexOf(':'))
  }
  if (a === 'localhost' || a === '::1' || a === '0:0:0:0:0:0:0:1') return true
  const v4 = a.startsWith('::ffff:') ? a.slice(7) : a // IPv4-mapped IPv6
  return /^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(v4)
}

/**
 * TRUE only when the request physically originated on the machine the dashboard
 * runs on. Choosing the FIRST password is the one action allowed before any
 * password exists, so it must not be reachable from another device: a tailnet
 * peer that reaches the box through `tailscale serve` (or any reverse proxy)
 * arrives carrying the ORIGINAL client's non-loopback Host / X-Forwarded-* and is
 * refused here.
 *
 * WHY PRESENCE IS NOT THE TEST (measured on a real Next 16 `next start` server,
 * 2026-08-12). A server action's `await headers()` does NOT carry only what the
 * client sent — Next SYNTHESISES `x-forwarded-host`, `x-forwarded-port`,
 * `x-forwarded-proto` and `x-forwarded-for` on EVERY request, including a direct
 * loopback hit, where they hold LOOPBACK values (`x-forwarded-host:
 * 127.0.0.1:<port>`, `x-forwarded-for: 127.0.0.1`). The earlier rule "any
 * forwarded header ⇒ not local" therefore refused the genuine on-box operator at
 * the very first screen. The unit mock (`new Headers({host})`) never had these
 * injected headers, so it stayed green while the live control was broken.
 *
 * WHAT HOLDS THE SECURITY PROPERTY. Next PRESERVES an incoming proxy's
 * `x-forwarded-*` (verified: a request bearing `x-forwarded-for: 100.64.0.9` /
 * `x-forwarded-host: <tailnet host>` surfaces those exact non-loopback values).
 * So a real remote hop always leaves a non-loopback fingerprint in at least one
 * of Host, X-Forwarded-Host, X-Real-IP, or a hop of X-Forwarded-For — every one
 * of which is required to be loopback below. Local passes; a proxied peer does
 * not.
 *
 * Defence in depth ON TOP OF the loopback BIND (start-dashboard.sh defaults the
 * listener to 127.0.0.1); this is the check that still holds if the box is later
 * opted onto the tailnet with CABINET_DASHBOARD_HOST=0.0.0.0.
 */
export function isLocalRequest(h: { get(name: string): string | null }): boolean {
  // The connection's own Host must be loopback (absent Host is not local).
  if (!isLoopback(h.get('host'))) return false
  // A proxy records the browser-visible host here; it must be loopback too.
  const xfHost = h.get('x-forwarded-host')
  if (xfHost && !isLoopback(xfHost)) return false
  // Single client-IP header some proxies set — loopback if present.
  const xRealIp = h.get('x-real-ip')
  if (xRealIp && !isLoopback(xRealIp)) return false
  // EVERY hop in the client→proxy chain must be loopback; one remote hop fails.
  const xff = h.get('x-forwarded-for')
  if (xff) {
    for (const hop of xff.split(',')) {
      if (hop.trim() && !isLoopback(hop)) return false
    }
  }
  return true
}
