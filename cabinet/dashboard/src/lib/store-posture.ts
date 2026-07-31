/**
 * WHAT PRODUCED THE NUMBERS ON THIS PAGE — three postures, never two.
 *
 * WHY THIS FILE EXISTS. `lib/redis.ts:1` was
 *
 *     const IS_MOCK = !process.env.REDIS_URL || process.env.MOCK_DATA === 'true'
 *
 * so the ABSENCE of configuration was a licence to invent. A dashboard started
 * without `REDIS_URL` served an in-process object seeded with five officer
 * heartbeats, all-`active` officer expectations, a RANDOMISED 30-day cost
 * history in real dollars, and seeded context-window percentages. Photographed
 * before this change: "Officers: 4/5 running", four officers "Running" with
 * heartbeats "2m ago", "Today's Cost $65.61", a 7-day stacked per-officer trend
 * and a 30-day per-officer cost table — pixel-indistinguishable from a healthy
 * live org. The only tell was a `console.log`.
 *
 * That is the emergency-stop defect and the attention-census defect at the
 * widest possible scope: not one reading lying, but EVERY reading inventing
 * itself at once, on the surface whose whole purpose is to tell the Captain
 * what is true. And it was the only fail-OPEN left in the app —
 * `middleware.ts` resolves its secret fail-closed, `killswitch-state.ts`
 * returns unknown on any error; this one alone answered a question it had not
 * asked.
 *
 * THE RULE, adjudicated 2026-07-31 (two models, blind, both agreeing;
 * `designs/mock-mode-ruling-2026-07-31.md` in the meta workspace carries both
 * positions and the four places they differed):
 *
 *   - `!REDIS_URL` alone  ⇒  UNCONFIGURED. The store is EMPTY. Every reading
 *     reaches its absent branch. Nothing is invented.
 *   - Fabricated data requires an EXPLICIT opt-in (`MOCK_DATA=true` or
 *     `CABINET_DEMO_DATA=true`) AND `NODE_ENV !== 'production'`.
 *   - Therefore a production deployment CANNOT render fabricated data. That is
 *     stronger than labelling it: there is no configuration of a real deploy
 *     that reaches the seeded store. The developer who typed the flag outside
 *     production gets the fabrication WITH a banner on every surface — that
 *     case is disclosed rather than prevented, deliberately, because somebody
 *     asked for it.
 *
 * The production refusal is not a new idea in this codebase — it is the rule
 * the AUTH plane already enforces (`middleware.ts:45`,
 * `lib/provisioning/guard.ts:91`: "MOCK_DATA is a dev/demo affordance, so a
 * single env var can never re-open a production deploy"). The data plane never
 * got that memo.
 *
 * WHY UNCONFIGURED IS AN EMPTY IN-PROCESS STORE AND NOT A REAL CLIENT: an
 * ioredis client pointed at nothing QUEUES commands rather than failing, so
 * "just construct the real client and let it error" would swap a lie for a
 * hang. (The separate case — `REDIS_URL` SET but unreachable — is untouched by
 * this module and still carries that hazard.)
 *
 * CLIENT-SAFE BY CONSTRUCTION — zero imports, same rule as
 * `lib/world/killswitch.ts`. The banner is rendered from a server component
 * today, but a `'use client'` surface that pulls a module with `node:fs` in its
 * import graph breaks the Turbopack client bundle outright (every page 500)
 * while `tsc` and the whole vitest suite stay green. Nothing node-only may ever
 * be imported here — and `process.env` is read only through the injected
 * `env` argument, never off the global, so this file is pure.
 */

/**
 * live = a store was configured AND answers · demo = fabricated on request ·
 * unconfigured = nothing was configured · unreachable = a store was configured
 * and did not answer.
 *
 * `unreachable` is the one posture that is NOT a function of the environment —
 * it is a runtime fact, discovered by asking. `resolveStorePosture` therefore
 * never returns it; `lib/redis.ts` composes it from the breaker in
 * `lib/store-reachability.ts`. Keeping the env decision pure is what lets every
 * other end of it be tested without a store.
 */
export type StorePosture = 'live' | 'demo' | 'unconfigured' | 'unreachable'

/** A reading about the READINGS: what produced everything else on the page. */
export interface StoreReading {
  posture: StorePosture
  /**
   * Plain-words provenance, in the dialect `lib/world/weather.ts` uses ("every
   * state names its exact source"). Rendered, not just logged.
   */
  source: string
  /** TRUE only when values are invented. `unconfigured` is NOT fabricated — it is empty. */
  fabricated: boolean
}

/** The env this decision reads. Injected so the function stays pure and every end is testable. */
export interface StoreEnv {
  REDIS_URL?: string
  MOCK_DATA?: string
  CABINET_DEMO_DATA?: string
  NODE_ENV?: string
}

export const UNCONFIGURED_SOURCE =
  'no store is configured (REDIS_URL unset) — this dashboard has not contacted your cabinet, and nothing below is a measurement of it'

export const DEMO_SOURCE =
  'demo data, generated in this process — every officer, heartbeat and dollar figure below is invented and none of it came from your cabinet'

export const LIVE_SOURCE = 'the configured store'

/**
 * The `unreachable` reading, built WITH the reason the store gave — there is no
 * zero-argument constant to reach for, the same rule `unknownKillswitch` follows,
 * so the reason cannot be forgotten by a caller in a hurry.
 */
export function unreachableReading(detail: string): StoreReading {
  return {
    posture: 'unreachable',
    source: `the store this dashboard is configured to read (REDIS_URL) did not answer — ${detail}. Nothing below was measured from your cabinet.`,
    // NOT fabricated. Nothing was invented; nothing was obtained either. The
    // flag means "these numbers are made up", and reusing it here would send
    // every consumer that branches on it down the demo path.
    fabricated: false,
  }
}

/**
 * The one place the posture is decided.
 *
 * Order matters and is the ruling: the explicit opt-in is checked FIRST so it
 * is the only way to reach fabrication, and it is dropped in production so no
 * env var can make a real deployment lie. `REDIS_URL` is then the live test.
 * Everything else is unconfigured — which is a POSTURE, not an error.
 */
export function resolveStorePosture(env: StoreEnv): StoreReading {
  const askedForDemo =
    env.MOCK_DATA === 'true' || env.CABINET_DEMO_DATA === 'true'
  if (askedForDemo && env.NODE_ENV !== 'production') {
    return { posture: 'demo', source: DEMO_SOURCE, fabricated: true }
  }
  // A non-empty REDIS_URL is the live test. An empty string is not a store:
  // `REDIS_URL=` in a .env file is a MISSING value that happens to be set, and
  // reading it as "configured" would hand a real client an empty endpoint.
  if (env.REDIS_URL) {
    return { posture: 'live', source: LIVE_SOURCE, fabricated: false }
  }
  return {
    posture: 'unconfigured',
    source: UNCONFIGURED_SOURCE,
    fabricated: false,
  }
}

/**
 * TRUE when a PRODUCTION build has no store configured.
 *
 * THE ASYMMETRY THIS NAMES. `demo` carries a production exclusion — no env var
 * can make a real deploy fabricate — and that exclusion is the reason the
 * fabrication rule above is stronger than labelling. `unconfigured` had none.
 * So the one posture that IS reachable on a production deploy was also the one
 * nothing diagnosed, and `lib/docker.ts` spent it as a licence to no-op every
 * actuator in the app and answer `mock: command executed` — measured
 * 2026-07-31 against the built app in `NODE_ENV=production` with `REDIS_URL`
 * unset: "Officer Created · the officer is booting and will announce on the
 * warroom shortly", underneath this module's own "NO STORE CONFIGURED —
 * nothing here is a measurement" banner, with `create-officer.sh` never run.
 *
 * Outside production, unconfigured is an ordinary state: somebody has not
 * finished setting up. In production it is a MISCONFIGURATION, and saying so is
 * the whole value of this predicate — the refusal a caller renders should name
 * the deploy as broken rather than describe a mode.
 *
 * It deliberately does NOT gate behaviour on `NODE_ENV`: nothing here is
 * allowed in one environment and refused in another. Both environments refuse;
 * only the sentence differs. A rule that changes what the code DOES between dev
 * and production is a rule whose production side is never exercised.
 */
export function isUnconfiguredInProduction(env: StoreEnv): boolean {
  return (
    resolveStorePosture(env).posture === 'unconfigured' &&
    env.NODE_ENV === 'production'
  )
}

/**
 * TRUE when this process is NOT talking to the fleet's store — demo,
 * unconfigured OR unreachable.
 *
 * Deliberately covers both, and the emergency stop is why. `readKillswitch`
 * takes `contacted: true` as its licence to report a MEASURED "clear"; an empty
 * unconfigured store answering `null` would earn a confident "the emergency
 * stop is not engaged" about a fleet this process has never reached — which is
 * exactly the defect PR #330 closed for the seeded `''`. Not-live means
 * not-a-reading, in both postures.
 */
export function isNotLiveStore(r: StoreReading): boolean {
  return r.posture !== 'live'
}

/** Headline for the disclosure banner. Never says anything is fine. */
export function storeBannerTitle(r: StoreReading): string | null {
  if (r.posture === 'live') return null
  if (r.posture === 'demo') return 'DEMO DATA — this is not your cabinet'
  if (r.posture === 'unreachable') {
    return 'STORE UNREACHABLE — nothing here is a measurement'
  }
  return 'NO STORE CONFIGURED — nothing here is a measurement'
}

/**
 * The `data-store-posture` attribute. DOM probes, the frame harness and the
 * after-capture read it, and it is the one assertion a screenshot test can make
 * that does not depend on prose.
 */
export function storeBannerAttr(r: StoreReading): string {
  return r.posture
}

/** What to do about it, per posture. Actionable, not decorative. */
export function storeBannerHint(r: StoreReading): string | null {
  if (r.posture === 'live') return null
  if (r.posture === 'demo') {
    return 'Unset MOCK_DATA / CABINET_DEMO_DATA and set REDIS_URL to see your cabinet. Demo data is refused in production.'
  }
  if (r.posture === 'unreachable') {
    return 'The dashboard keeps trying; it will start measuring again on its own the moment the store answers. To check from a terminal: redis-cli -u "$REDIS_URL" ping'
  }
  return 'Set REDIS_URL to your cabinet’s store (start-dashboard.sh defaults it to redis://localhost:6379).'
}
