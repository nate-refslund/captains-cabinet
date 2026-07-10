// GET /api/health — unauthenticated LIVENESS only (Wave D app-feel).
// Returns a static ok-boolean + timestamp: no config, no state, no secrets.
// This makes the existing cabinet/services.yml expectation for
// com.cabinet.dashboard ("HTTP 200 on :3100/api/health") true, and gives
// hatch.sh's app-feel probe (and any kiosk/doctor probe) an honest target
// that does not depend on the auth cookie. Excluded from the auth matcher
// in src/middleware.ts; every other /api/* stays cookie-gated.
export const dynamic = 'force-dynamic'

export async function GET() {
  return Response.json({
    ok: true,
    service: 'cabinet-dashboard',
    ts: new Date().toISOString(),
  })
}
