import { NextRequest, NextResponse } from 'next/server'

/**
 * Constant-time comparison of two hex strings. The middleware runs in the Edge
 * runtime (Web Crypto only — no Node `crypto.timingSafeEqual`), so this is done
 * by hand: length-guard, then XOR-accumulate over every char so the loop cost
 * is independent of WHERE the first mismatch is. A plain === would short-circuit
 * at the first differing hex char and leak, via timing, how much of the HMAC an
 * attacker has guessed. Length is allowed to leak (same as timingSafeEqual's
 * equal-length requirement) — the secret bytes are what must stay constant-time.
 */
function timingSafeEqualHex(a: string, b: string): boolean {
  if (a.length !== b.length) return false
  let mismatch = 0
  for (let i = 0; i < a.length; i++) {
    mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i)
  }
  return mismatch === 0
}

async function verify(
  token: string,
  sig: string,
  secret: string
): Promise<boolean> {
  const encoder = new TextEncoder()
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  )
  const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(token))
  const expected = Array.from(new Uint8Array(signature))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
  return timingSafeEqualHex(expected, sig)
}

export async function middleware(request: NextRequest) {
  // Skip auth in mock/dev mode when no password is configured. MOCK_DATA is a
  // dev/demo affordance, honoured ONLY outside production so a single env var
  // can never re-open a production deploy (mirrors guard.ts isNoAuthPosture).
  if ((process.env.MOCK_DATA === 'true' && process.env.NODE_ENV !== 'production') || (!process.env.DASHBOARD_PASSWORD && process.env.NODE_ENV === 'development')) {
    return NextResponse.next()
  }

  if (request.nextUrl.pathname.startsWith('/login')) {
    return NextResponse.next()
  }

  // The office wall-display (/display) is READ-ONLY status — no controls, no
  // secrets, no kill switch. It's meant to render on the Mac mini's monitor in
  // kiosk Chrome without a login step. Allow it unauthenticated. Sensitive
  // routes (env vars, governance, kill switch) remain behind auth. Exposure is
  // limited to whoever can already reach the dashboard host (office LAN /
  // tailnet) — the same audience authorized for the cabinet anyway.
  if (request.nextUrl.pathname.startsWith('/display')) {
    return NextResponse.next()
  }

  // Fail-closed secret resolution (mirrors lib/auth.resolveSecret +
  // verdict.ts doorSecret): in production an unset or 'changeme' password
  // yields NO usable secret, so no cookie can be valid and every gated route
  // redirects to /login. The middleware never verifies against the public
  // 'changeme' fallback in production — otherwise an attacker who knows the
  // well-known secret could forge a passing cookie.
  const rawSecret = process.env.DASHBOARD_PASSWORD
  const secret =
    rawSecret && rawSecret !== 'changeme'
      ? rawSecret
      : process.env.NODE_ENV === 'production'
        ? null
        : 'changeme'
  if (!secret) {
    return NextResponse.redirect(new URL('/login', request.url))
  }

  const cookie = request.cookies.get('cabinet_session')
  if (!cookie) {
    return NextResponse.redirect(new URL('/login', request.url))
  }

  const [token, sig] = cookie.value.split('.')
  if (!token || !sig) {
    return NextResponse.redirect(new URL('/login', request.url))
  }

  const valid = await verify(token, sig, secret)
  if (!valid) {
    return NextResponse.redirect(new URL('/login', request.url))
  }

  return NextResponse.next()
}

export const config = {
  // Wave D app-feel: browsers fetch the PWA manifest + icons WITHOUT cookies
  // (a cookie-gated manifest 307s to /login and install never triggers), so
  // EXACTLY these five surfaces leave auth: the manifest, the three icon
  // paths, and the /api/health liveness boolean. Static brand assets + an
  // {ok:true} — no config, no state, no secrets. Every other route,
  // including every other /api/*, stays behind the HMAC cookie check above.
  //
  // NOTE: the exclusions are PREFIX matches (regex alternatives, dots
  // unescaped), not exact paths — `api/health` also un-authenticates
  // /api/healthz, /api/health-report, /api/health/anything. The health
  // namespace is therefore pinned closed (exactly api/health/route.ts,
  // nothing nested, no health-prefixed siblings) by a tripwire in
  // cabinet/scripts/tests/test_dashboard_pwa_static.py — adding a route
  // under that prefix is a conscious auth adjudication, not a file drop.
  matcher: ['/((?!_next/static|_next/image|favicon.ico|manifest.webmanifest|icon.svg|apple-icon.png|icons/|api/health).*)'],
}
