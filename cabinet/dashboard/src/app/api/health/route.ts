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
// THREE MORE FIELDS, all for the update path's health gate (2026-09-07). They
// answer three DIFFERENT questions, and collapsing any two of them is how an
// update lies about itself:
//
//   source_commit — WHICH CABINET this process was started against. Read at
//     request time from the environment the process was spawned with:
//     start-dashboard.sh resolves it from egg-manifest.json, which an update
//     rewrites BEFORE it restarts the dashboard. A process that survived a
//     failed restart still carries the OLD value — its environment was fixed
//     when it started and nothing can reach into a running process to change
//     it — so the gate sees the restart that did not happen.
//   build_commit — WHICH BUILD is serving. Inlined by `next build`
//     (next.config.ts `env`), so it cannot be anything but the commit the
//     bundle was made from. The update gate demands this one only when the
//     apply actually rebuilt: a bundle that changes no dashboard file needs no
//     rebuild, and requiring it there rolled every framework-only update back
//     (found in review, 2026-09-07).
//   started_at — this process's own start time, derived from `process.uptime()`
//     rather than from a module-scope `new Date()`. A route module in a Next
//     production server is loaded on the FIRST REQUEST that reaches it, which
//     can be long after the process started — and, worse, after the update
//     that was supposed to restart it. Uptime is the process's, however late
//     this module loads.
//
// None of the three is a secret and none is state: two commit ids and a clock
// reading, on an endpoint that is deliberately unauthenticated.
export const dynamic = 'force-dynamic'

export async function GET() {
  const startedAt = new Date(Date.now() - Math.round(process.uptime() * 1000)).toISOString()
  return Response.json({
    ok: true,
    service: 'cabinet-dashboard',
    ts: new Date().toISOString(),
    source_commit: process.env.CABINET_SOURCE_COMMIT || '',
    build_commit: process.env.CABINET_BUILD_SOURCE_COMMIT || '',
    started_at: startedAt,
  })
}
