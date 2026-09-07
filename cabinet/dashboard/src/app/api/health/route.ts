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
//
// TWO MORE FIELDS, both for the update path's health gate (2026-09-07):
//
//   source_commit — baked at `npm run build` (next.config.ts `env`), so it
//     describes the BYTES SERVING, not the environment of whoever asks. An
//     update that swapped the tree but whose restart silently failed answers
//     with the OLD commit here, which is the whole point.
//   started_at — this process's own start time. Identity plus commit still
//     passes an old process on a machine where the previous build carried the
//     same commit (a rebuild, a rollback-then-forward); a start time later
//     than the apply began is the part that cannot be faked by not restarting.
//
// Neither is a secret and neither is state: a commit id and a clock reading,
// on an endpoint that is deliberately unauthenticated.
export const dynamic = 'force-dynamic'

// Module scope: evaluated once when the server process boots, so this is the
// PROCESS start time and not the time of the request that read it.
const STARTED_AT = new Date().toISOString()

export async function GET() {
  return Response.json({
    ok: true,
    service: 'cabinet-dashboard',
    ts: new Date().toISOString(),
    source_commit: process.env.CABINET_BUILD_SOURCE_COMMIT || '',
    started_at: STARTED_AT,
  })
}
