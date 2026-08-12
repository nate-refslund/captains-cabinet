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
 * TRUE only when the request came DIRECTLY from the machine the dashboard runs
 * on. Choosing the FIRST password is the one action allowed before any password
 * exists, so it must not be reachable from another device: a tailnet peer that
 * reaches the box through `tailscale serve` (or any reverse proxy) arrives with a
 * forwarded header and a non-loopback Host, and is refused here. A direct
 * loopback browser carries neither.
 *
 * Defence in depth ON TOP OF the loopback BIND (start-dashboard.sh defaults the
 * listener to 127.0.0.1); this is the check that still holds if the box is later
 * opted onto the tailnet with CABINET_DASHBOARD_HOST=0.0.0.0.
 */
export function isLocalRequest(h: { get(name: string): string | null }): boolean {
  // Any proxy hop is disqualifying — a direct local connection sets none of these.
  if (h.get('x-forwarded-for') || h.get('x-forwarded-host') || h.get('x-real-ip')) {
    return false
  }
  const host = (h.get('host') || '').toLowerCase().trim()
  // Drop a trailing :port, then any [ ] framing an IPv6 literal.
  const hostname = host.replace(/:\d+$/, '').replace(/^\[/, '').replace(/\]$/, '')
  return hostname === '127.0.0.1' || hostname === 'localhost' || hostname === '::1'
}
