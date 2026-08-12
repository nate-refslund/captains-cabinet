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
 */
export const PASSWORD_MIN_LENGTH = 12

/**
 * The characters a chosen password may contain.
 *
 * cabinet/.env is SOURCED by bash at every dashboard and officer start
 * (start-dashboard.sh / start-all-officers.sh do `set -a; . cabinet/.env`), so
 * the stored value becomes a shell assignment. A value carrying a space or a
 * shell metacharacter ($ ` ; & | ( ) < > # ' " \ and friends) would break that
 * assignment — or, with backticks or $(), EXECUTE on every restart. The
 * previously generated password was base64 alphanumeric and dodged this by
 * construction; a human-chosen one must be constrained to a set that is safe
 * unquoted on one assignment line. Letters, numbers and a handful of safe
 * symbols clear the 12-char floor with room to spare.
 */
const ALLOWED_PASSWORD = /^[A-Za-z0-9._,:@%^+=-]+$/

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
 */
export function validateChosenPassword(
  password: string,
  confirm: string
): PasswordCheck {
  if (!password || password.length < PASSWORD_MIN_LENGTH) {
    return {
      ok: false,
      error: `Please choose at least ${PASSWORD_MIN_LENGTH} characters, so it is not easy to guess.`,
    }
  }
  if (!ALLOWED_PASSWORD.test(password)) {
    return {
      ok: false,
      error:
        'Please use only letters, numbers, and these symbols: . _ - , : @ % ^ + = (no spaces).',
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
