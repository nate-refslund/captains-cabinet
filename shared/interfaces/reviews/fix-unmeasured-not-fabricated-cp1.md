# Checkpoint review — fix/unmeasured-not-fabricated cp1

Reviewed-Scope-Digest: 1ccd23ec3b25735a821b2ca4998b3f97aad9e2084d89d039ecb51b038e0f549a

## What this change is

The top of the unknown-vs-value class filed after PR #330: **a dashboard with no
`REDIS_URL` was indistinguishable from a healthy live org.** `lib/redis.ts:1` made the
ABSENCE of configuration a licence to invent — five officer heartbeats, an all-`active`
roster, a randomised 30-day cost history in real dollars, seeded context percentages —
disclosed by nothing but a `console.log`. Photographed before/after against a running app
(`designs/mock-*.png` in the meta workspace).

Plus the next four ranked rows of the same sweep: malformed/future-dated heartbeats
rendering "Active" on five surfaces; cost totals with no null anywhere; a future-dated
activity stamp as a permanent green ring; and `org_events_total` missing from a PRESENT
census keyframe silently shrinking the island past the badge that should have announced it.

## The ruling, and how it was reached

Two models (Opus 5, Fable 5) ran blind and in parallel on "should mock mode exist at all".
Both positions, the four places they differed, and the adjudication are recorded in
`designs/mock-mode-ruling-2026-07-31.md` (meta workspace). They agreed:

- `!REDIS_URL` alone ⇒ **unconfigured**: an EMPTY in-process store. Every reading reaches
  its absent branch. Nothing is invented, and no ioredis client is constructed — Fable
  raised, and Opus did not, that a client pointed at nothing QUEUES commands rather than
  failing, so "just use the real client" would swap a lie for a hang.
- Fabrication requires an explicit opt-in (`MOCK_DATA=true` or the new store-only
  `CABINET_DEMO_DATA=true`) **and** `NODE_ENV !== 'production'` — the rule the AUTH plane
  already enforces at `middleware.ts:45` and `provisioning/guard.ts:91`.
- Disclosure on every surface, including `/display`, which is outside the authenticated
  layout and is the one a kiosk shows unattended all day.

**The claim, bounded exactly.** *Impossible*: a production deployment cannot render
fabricated data — no env combination reaches the seeded store, verified against the BUILT
app with `NODE_ENV=production MOCK_DATA=true CABINET_DEMO_DATA=true` and no `REDIS_URL`.
*Labelled*: a developer who sets the flag outside production sees fabricated data behind a
banner on every page. That second case is disclosed rather than prevented, deliberately.

## Evidence

- `npx tsc --noEmit` clean; `npx vitest run` **3067 passed / 1 skipped**, 148 files.
- `next build` clean, and the built app started in production mode — the class of defect
  (`node:fs` in a `'use client'` import graph) that `tsc` and vitest cannot see.
  `lib/store-posture.ts` and `lib/liveness.ts` are zero-import by construction.
- `check-layer-separation.sh`: `new=0`.
- **Mutation proof — 13 defects re-introduced one at a time, 13 caught.** Including the one
  that was NOT caught first time: the cron-sentinel fence passed against its own mutation
  because `RUNTIME_MODE` resolved to `docker` in vitest and the mutated line was
  unreachable. Fixed by pinning `CABINET_RUNTIME_MODE=native` in that arm, with the reason
  written into the test. A fence that cannot reach the code it names is a disabled sensor.

## Fences added, and what each one would miss

| Fence | Drives | Blind to |
|---|---|---|
| `lib/store-posture.test.ts` | the pure posture decision, incl. an exhaustive sweep proving no env combination fabricates under `NODE_ENV=production` | nothing renders it — a caller that ignores the posture |
| `lib/no-store-honesty.test.ts` | every reader in `redis.ts` + `docker.ts` + `killswitch-state.ts` with no store | JSX layout (vitest is `environment: 'node'`) |
| `lib/liveness.test.ts` | malformed / future / absent / boundary, and the printed WORD | which components call it |
| `app/api/world/unmeasured-surfaces.test.ts` | the rail and engine HANDLERS, on the wire | the client that renders their payloads |
| `lib/world/ui-cards.test.ts` (extended) | future-dated freshness → ring consequence | — |

Every table row has an **inverse arm**: a measured zero stays zero, a real total still
totals, a genuine day-zero census still reports 0. A "fix" that turns every reading into
unknown is exactly as useless as the one that turned every reading into a number.

## Residuals — recorded, not claimed closed

- `actions/projects.ts` / `project-config.ts` / `crons.ts` still return placeholder
  identifiers ("Widgets") with no store. Page-level banner discloses it; they are
  identifiers, not measurements of health, money or attention.
- `MOCK_DATA=true` still waives auth outside production. Both models wanted that severed;
  editing the auth plane in a data-honesty PR is a scope and blast-radius error, so the
  store-only `CABINET_DEMO_DATA` was added instead and the reverse direction is filed.
- `REDIS_URL` **set but unreachable** is untouched here, and still carries the ioredis
  queueing hazard.
- The typed `{value, source, reason}` envelope through the data layer (Opus's strongest
  mechanism) is a ~23-file refactor and is filed; its cheap 80% is taken — the store no
  longer HOLDS a fabricated value to escape with.
