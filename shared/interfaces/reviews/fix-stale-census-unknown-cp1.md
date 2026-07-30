# Checkpoint review — fix/stale-census-unknown (cp1)

Reviewed-Scope-Digest: ab8bd4804114dbcb977efc96df7ffd8c2e3ba9251e1aa9438d57c3a0f7149d92

Date: 2026-07-30 · Reviewer: fresh-context adversarial subagent (Opus 5, own
clone of origin/master 4fd9b2b4 with the change applied) + orchestrator
re-verification. Verdict after remediation: **approve**.

## What the change is

An unmeasured value and a measured zero shared one representation, in two
planes, and both rendered the zero as fact.

- **TS.** The attention census was 9 days stale (`CENSUS_MAX_AGE_MS` = 30 min)
  and `/queue` rendered "Nothing needs you. All clear — your team is handling
  the rest. ✅". The bytes on disk said 2 decisions / 42 situations. The
  staleness bar worked; the FLOOR under it — `EMPTY_QUEUE.pendingCaptainItems:
  0` — was the lie, and `queue.test.ts` pinned it as "the honest zero".
- **Python.** `Probe.launchctl_list()` returned `{}` both when launchd could not
  be asked and when launchd answered with zero `com.cabinet.*` labels, so
  `registry.py`'s `if ll:` self-disabled the declared-but-not-loaded check —
  the one check written for a torn-down fleet — at the moment the fleet was
  torn down.

## First review round — findings and disposition

| sev | finding | disposition |
|---|---|---|
| blocker | a FRESH census whose `pending_captain_items` is absent/non-numeric still coerced to `0` → green all-clear. Timestamp degenerate ends were closed; the counted field's own was not. | FIXED — `num()` guard; both counts `null`; census payload carries "carries no count" reason. Arms: `queue.test.ts` non-numeric sweep + route arm. |
| blocker | every SURFACE could be reverted with the suite green (mailbox `pendingTotal: 0`, SSE `return 0`, verdict `=== 'unknown'`, badge hides unknown, page `unknown = false`). Only substring greps guarded them. | FIXED — new `app/api/attention/surfaces-unknown.test.ts` drives the three route handlers against stale/absent/malformed/uncounted censuses; SSE count moved to `censusCountOrNull` in the lib and driven there; masthead numeral is a STRING (`mastheadCount`) so a broken branch prints `—`, never `0`; badge decision moved to `badgeState`. |
| should-fix | mailbox's `redis-fallback` branch re-read Redis (`readPendingCards` maps failure → `[]` → confident `0`). | FIXED — reuses the rows already on `queue`. Arm: "the degraded live path counts what it actually read, once". |
| should-fix | `launchctl list` reports the CALLER's domain; as root it returns `{}` on a healthy box → the new contract would page every declared row with a false reason. | FIXED — `os.geteuid() == 0` → `None`, plus a positive control that this uid really does get a dict. |
| note | the comment claimed a GREEN watchdog row for five days; not reproducible (other log arms may have reddened). | FIXED — comment now claims only what is provable: both launchd arms switched themselves off. |
| note | `queue-page.test.ts` still said "hidden at zero". | FIXED. |

## Batteries, re-run by the reviewer on its own clone

| command | result |
|---|---|
| `tsc --noEmit` | exit 0 |
| `vitest run` (cache purged) | 2940 passed, 1 skipped |
| `pytest framework/watchdog/tests framework/attention/tests -q` (pycache purged) | 390 passed |
| `check-layer-separation.sh` | `new=0` OK |

## Mutation sweep (each applied alone, caches purged, reverted after)

| mutation | caught |
|---|---|
| `unknownQueue` → `pendingCaptainItems: 0` | yes (11 red) |
| `attentionGlance` null → clear | yes (10 red) |
| restore `if (generatedAt)` staleness skip | yes (4 red) |
| drop `fallbackFromCards` zero-guard | yes (2 red) |
| `registry.py` `if ll is not None:` → `if ll:` | yes (1 red) |
| delete the root guard in `check.py` | yes (1 red) |
| mailbox unknown branch → `pendingTotal: 0` | yes |
| mailbox degraded branch → `pendingTotal: 0` | yes |
| SSE `pendingCaptainItems` → `() => 0` | yes |
| verdict `!== 'census'` → `=== 'unknown'` | yes |
| badge hides unknown (extra `return null`) | yes |
| fresh-census count `?? 0` | yes (5 red) |
| `mastheadCount` unknown → `'0'` | yes |
| `badgeState` null → hide | yes |
| client component imports the census reader | yes |

## Found by RUNNING the app, not by any suite

Pointing the badge at `lib/attention/queue.ts` broke the Turbopack client
bundle ("Code generation for chunk item errored") and 500'd every page, while
`tsc --noEmit` and all 2900 vitest arms stayed green — both run in node, where
a `node:fs` import is invisible. Split into `lib/attention/glance.ts` (pure)
and pinned by a new arm that sweeps every `'use client'` file.

## Stated limits

- **`queue/page.tsx` unknown-branch mutation is NOT caught.** This package runs
  vitest with `environment: 'node'` and no DOM renderer, so a React server
  component cannot be rendered here. Mitigation is structural rather than
  behavioural: the page's only numeral source is `mastheadCount()`, which
  returns `'—'` for an unmeasured reading, and `dark` requires
  `glance.state === 'clear'` — so a broken branch degrades to "— need you",
  never to `0` or to the green all-clear.
- The world's own org state (`/api/world/engine` keyframes) still has NO
  freshness bound; the killswitch still renders `false` when Redis is
  unreachable. Both are the same class, both are recorded in cabinet-meta
  `BACKLOG.md` with the reason they were not fixed here (each needs a design
  call, not a patch).
