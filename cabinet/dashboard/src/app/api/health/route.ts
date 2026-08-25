// GET /api/health — unauthenticated LIVENESS only (Wave D app-feel).
// Returns a static ok-boolean + timestamp: no config, no state, no secrets.
// This makes the existing cabinet/services.yml expectation for
// com.cabinet.dashboard true, and gives
// hatch.sh's app-feel probe (and any kiosk/doctor probe) an honest target
// that does not depend on the auth cookie. Excluded from the auth matcher
// in src/middleware.ts; every other /api/* stays cookie-gated.
//
// `service` IS THE IDENTITY MARKER, and it is load-bearing (2026-08-25). A
// bare HTTP 200 on this port proves only that SOME program answered: on a Mac
// where an unrelated local dev server held 3100, every probe in the tree read
// its 200-with-HTML as "the cabinet is up" while the real dashboard was down.
// Every probe now matches this string instead (cabinet/scripts/lib/dashboard.sh
// -> CABINET_DASH_MARKER). Renaming or dropping the field blinds all of them.
export const dynamic = 'force-dynamic'

export async function GET() {
  return Response.json({
    ok: true,
    service: 'cabinet-dashboard',
    ts: new Date().toISOString(),
  })
}
