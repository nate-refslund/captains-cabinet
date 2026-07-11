import { cookies } from 'next/headers'
import crypto from 'crypto'

const COOKIE_NAME = 'cabinet_session'
const MAX_AGE = 7 * 24 * 60 * 60 // 7 days

/**
 * Resolve the session HMAC secret, fail-closed (mirrors verdict.ts:47
 * doorSecret). Resolved PER CALL (never a module-load const) so the guard
 * honours the live env and tests can stub it.
 *
 *   - A real DASHBOARD_PASSWORD (set and not the well-known dev 'changeme')
 *     is always the secret.
 *   - In production, an unset or 'changeme' password ⇒ null: the door never
 *     signs or verifies on the dev fallback, so no forged cookie can validate
 *     against a publicly-known secret. verifySession/checkPassword then
 *     fail-closed and createSession refuses.
 *   - Only outside production do we fall back to 'changeme' for local dev/test
 *     convenience (middleware already bypasses auth entirely in that mode).
 */
function resolveSecret(): string | null {
  const s = process.env.DASHBOARD_PASSWORD
  if (s && s !== 'changeme') return s
  if (process.env.NODE_ENV === 'production') return null
  return 'changeme'
}

function sign(value: string, secret: string): string {
  return crypto.createHmac('sha256', secret).update(value).digest('hex')
}

export async function createSession() {
  const secret = resolveSecret()
  if (!secret) {
    // Fail-closed: refuse to mint a session signed with the public 'changeme'
    // secret in production. A misconfigured deploy stays locked, never open.
    throw new Error(
      'DASHBOARD_PASSWORD must be set to a real value (not "changeme") in production'
    )
  }
  const token = crypto.randomBytes(32).toString('hex')
  const signed = `${token}.${sign(token, secret)}`
  const cookieStore = await cookies()
  cookieStore.set(COOKIE_NAME, signed, {
    httpOnly: true,
    secure: false, // Internal tool — HTTP is fine
    maxAge: MAX_AGE,
    path: '/',
    sameSite: 'lax',
  })
}

export async function verifySession(): Promise<boolean> {
  const secret = resolveSecret()
  if (!secret) return false // fail-closed in prod without a real password
  const cookieStore = await cookies()
  const cookie = cookieStore.get(COOKIE_NAME)
  if (!cookie) return false
  const [token, sig] = cookie.value.split('.')
  if (!token || !sig) return false
  // Constant-time compare (mirrors checkPassword). A plain === leaks, via
  // response timing, how many leading hex chars of the HMAC an attacker
  // guessed right. Length-guard first so timingSafeEqual never throws on an
  // attacker-chosen wrong-length signature.
  const expected = sign(token, secret)
  const a = Buffer.from(sig)
  const b = Buffer.from(expected)
  if (a.length !== b.length) return false
  return crypto.timingSafeEqual(a, b)
}

export async function destroySession() {
  const cookieStore = await cookies()
  cookieStore.delete(COOKIE_NAME)
}

export function checkPassword(password: string): boolean {
  const secret = resolveSecret()
  if (!secret) return false // fail-closed: no login with the public dev secret
  const a = Buffer.from(password)
  const b = Buffer.from(secret)
  if (a.length !== b.length) return false
  return crypto.timingSafeEqual(a, b)
}
