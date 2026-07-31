/**
 * WHO MAY SKIP THE LOGIN — one decision, one place.
 *
 * WHY THIS FILE EXISTS. `MOCK_DATA=true` meant TWO things at once: "invent the
 * data" and "no login". One name for two unrelated powers is how a flag someone
 * sets to see a chart ends up removing the door, and both models at the
 * 2026-07-31 mock-mode gate asked for them severed. The data half was split then
 * (`CABINET_DEMO_DATA`); editing the auth plane inside a data-honesty PR was a
 * scope and blast-radius error, so this half was filed. This is that half.
 *
 * The predicate was ALSO written twice — `middleware.ts` and
 * `provisioning/guard.ts` each carried their own copy, with a comment in each
 * saying it must stay identical to the other. A rule that depends on two files
 * agreeing by hand is a rule with a drift date. Now they both call this.
 *
 * WHAT CHANGED, EXACTLY: `MOCK_DATA=true` no longer waives the login.
 * `DASHBOARD_NO_AUTH=true` does — a name that says what it does, so nobody
 * reaches it by accident while asking for demo numbers. The two remaining
 * openings are unchanged: that explicit flag, and development with no password
 * configured.
 *
 * WHAT DID NOT CHANGE: none of this can open a production deploy. Both openings
 * are inert when `NODE_ENV === 'production'` — the explicit flag is checked
 * against it, and the no-password branch requires `development` exactly. That
 * property is the point of the module and has its own arm.
 *
 * The one legitimate consumer of the old coupling is unaffected:
 * `cabinet/scripts/demo-dashboard.sh` already sets `CABINET_DEMO_DATA=true` and
 * its own `DASHBOARD_PASSWORD`, and its header already says the demo flag
 * "does not waive the login below".
 *
 * EDGE-SAFE BY CONSTRUCTION — zero imports. `middleware.ts` runs in the Edge
 * runtime, where a node-only import in the graph breaks the build.
 */

/** The env this decision reads. Injected so the function is pure and testable. */
export interface AuthEnv {
  DASHBOARD_NO_AUTH?: string
  DASHBOARD_PASSWORD?: string
  NODE_ENV?: string
}

/**
 * TRUE when this deployment has deliberately taken the door off.
 *
 * Order does not matter here — both arms are production-inert — but the
 * production guard is repeated per arm rather than hoisted, on purpose: a single
 * hoisted guard is one edit away from being moved above a new arm somebody adds
 * later, and this is the function where that mistake is unrecoverable.
 */
export function isNoAuthPosture(env: AuthEnv): boolean {
  const explicit =
    env.DASHBOARD_NO_AUTH === 'true' && env.NODE_ENV !== 'production'
  const devWithoutPassword =
    !env.DASHBOARD_PASSWORD && env.NODE_ENV === 'development'
  return explicit || devWithoutPassword
}
