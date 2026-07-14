# Frontdoor verified-noise discriminator — design + rollout (2026-07-14)

**Author:** cos (Chair) · **Branch:** `frontdoor-signal-discriminator` · **Status:** built + unit/integration-green on branch; PENDING fresh-context review + polads-ceo live-Sentry verification before merge.
**Contract of record:** `shared/interfaces/polads-sentry-triage-discriminator-contract-2026-07-14.md` (polads-ceo).
**Reference impl:** `instance/tools/polads-sentry-triage.sh` (polads-ceo).

## Problem
The ops-health synthesis layer (`framework/frontdoor/morning_synthesis.py`) read RAW signal — a Sentry issue's `count`, a failed-deploy tally — and relayed it as an incident to the Chair. On 2026-07-14 this surfaced a false `[INCIDENT — ping-now]`: "Failed query 2811". The core error: **a Sentry `count` is CUMULATIVE-since-firstSeen, not a 24h rate** — that issue was 83h frozen (contributed 0 recently) and bot-sourced. Same class: chronic / frozen / staging / bot / stale signal misread as LIVE failure. (Sibling cases: the once-daily cabinet-doctor snapshot frozen as an all-day exit-1; fidelity-f1/judge-calibration R&D gates paging the ops watchdog.)

## Design — CORE logic (lane-agnostic) + TELLS (per-lane)
- **`framework/frontdoor/signal_discriminator.py`** (new) — the lane-agnostic CORE: two-signal split (magnitude-delta + recency), freshness cutoffs (≤15m ongoing / ≤120m attribution gate), host/path→verdict attribution tree, verdict enum + precedence (`NO_UNRESOLVED > REAL_USER_SUSPECT > PROD_SMOKE_NON_200 > NOISE`), smoke-outranks-count. Pure logic + injected I/O (url_fetcher, smoke_ok) → fully unit-tested with zero network.
- **`instance/config/signals.yml`** (new, instance data) — the per-lane TELLS keyed by Sentry project: `prod_hosts` (EXACT allowlist), `staging_host_patterns`, `bot_host_patterns`, `template_path_pattern`, `smoke_paths`. Ships with a sanitized `.example` twin; the live file is `delete`d from the egg (R120) so instance-verify stays green.
- **The TELLS seam (framework/→instance/ decoupled).** framework never reads `signals.yml` directly — that would trip the layer-separation gate. Instead the **briefing wrapper** `cabinet/scripts/run-frontdoor-briefing.sh` (a `cabinet/` script, free to read `instance/`) resolves the configured project's tells from `signals.yml` and exports them as JSON in `CABINET_SENTRY_TELLS`; **`framework.env.signal_tells`** reads that env var. This is the SAME env-graft seam already used for `CABINET_SENTRY_ORG/PROJECT` — the discriminator receives a *resolved* value, framework holds zero instance-config paths.
- **`framework/acting/product_health.py::sentry_health`** — extended additively to carry `short_id`/`id`/`last_seen` (the recency + attribution fields; existing `title`/`events` consumers unaffected).
- **`framework/frontdoor/morning_synthesis.py::sentry_health_items`** — wired: NOISE→suppress, REAL_USER_SUSPECT→ping-now (with route), PROD_SMOKE_NON_200→ping-now, INCONCLUSIVE→fail-open (raw emit as before). Tells resolved via `env.signal_tells(project)`.

## The safety property — FAIL-OPEN
The discriminator classifies a signal NOISE (→ suppress) **only with affirmative evidence**: a frozen/settled issue (recency), or a fresh issue that positively attributes to a bot/staging/preview tell. On ANY uncertainty — no tells, unparseable timestamp, un-fetchable/unclassified url — it returns INCONCLUSIVE and the caller PASSES THE SIGNAL THROUGH (today's behavior). A mis/un-configured lane degrades to noisy-but-safe, never to a hidden real incident. Consequence: the recency win (suppress a frozen `count` spike) works **even before signals.yml exists**; signals.yml only makes it sharper (prod-smoke + fresh-issue attribution + the staging fix).

## The staging must-fix (from the contract)
The reference regex `(^|\.)polads\.eu$` also matches `test.polads.eu` (suffix) → a fresh staging error would false-positive as prod real-user. The generalization uses an EXACT `prod_hosts` allowlist + explicit `staging_host_patterns`, tested BEFORE the prod check. Covered by a named regression test (unit + integration): a fresh `test.polads.eu` error classifies NOISE, never real-user.

## Test coverage — 62 green + fresh-context review
`test_signal_discriminator.py` (unit, incl. both named contract fixtures: 07-11 bot-burst→NOISE, fresh test.polads.eu→NOISE-not-real-user, + env.signal_tells resolution) · `test_signal_discriminator_anchoring.py` (label-boundary host matching + multi-host smoke — the review-hardening) · `test_sentry_health_items_wiring.py` (integration, emit-path end-to-end) · `test_morning_synthesis.py` (29 existing, unbroken). A fresh-context adversarial review (Sonnet) empirically confirmed the fail-open safety property, the staging fix, and caught the egg-verify + unanchored-substring issues fixed above.

## Rollout
1. Fresh-context review (Infra Change Protocol) — DONE before merge.
2. **polads-ceo verifies the framework version reproduces the contract against LIVE PolAds Sentry** (they are the reference impl + verifier; the 07-11 bot-burst = the canonical noise fixture, a fresh test.polads.eu = the staging regression).
3. Merge to master (Chair operational authority — non-germline frontdoor infra, routes to the Chair not the Captain, reduces false positives; branch + review + polads-verify + soak first). Note in the first post-return briefing (batch, FYI — not a Captain decision).
4. Rollback: revert the branch merge; ledger/config files are additive; INCONCLUSIVE fail-open means even a bad tells file only over-emits, never hides.

## Follow-ups (fast-follow, same discriminator shape)
- `deploy_health_items` — filter dependabot/preview builds (target=null ≠ target=production). Needs the Vercel source adapter to expose `target`/`creator`; scoped separately to avoid ballooning this change.
- cabinet-doctor / fidelity-f1 / judge-calibration — apply the magnitude→recency→attribution→verdict mapping so R&D/bootstrap/stale signals stop paging the ops outcome-watchdog (contract §"Generalizing beyond Sentry").

## Parity note
`instance/config/signals.yml` is per-instance (does NOT auto-sync). The Personal Cabinet needs its own signals.yml IF it has Sentry-monitored lanes; absent it, fail-open = no-op. Parity todo filed rather than blind-editing Personal (its lanes unknown from here).
