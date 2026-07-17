# Evidence Recorder v1 — Captain runbook

Evidence Recorder v1 is the universal, local evidence plane for every Cabinet.
Onboarding v2 is its first complete integration. It does not replace
`org_events`, the consequence ledger, action feed, or provisioning journals;
those remain their domain truths. Evidence Recorder joins their intent,
policy, execution, verification, receipt, error, undo, and outcome facts with
stable trial, trace, action, and correlation IDs.

## What is recorded

Each owner-only trial ledger is append-only, sequence-numbered, SHA-256
hash-chained, locally HMAC-signed, and closed by a signed anchor. Events carry:

- phase, status, UTC timestamp, safe monotonic timing, and surface;
- actor kind/id and component version/commit provenance;
- stable trial, trace, action, correlation, event, and linked receipt IDs;
- bounded details such as error/reason code, revision, counts, exclusions,
  source-integrity hashes, transport result, and Captain usefulness/correction;
- reserved v1.1 detail vocabulary (all optional, additive): delegation
  lineage (`parent_trial_id` — the structured parent→child key, `spawned_by`,
  `delegation_depth`), scheduled-trigger provenance (`scheduled_by`,
  `trigger_kind`, `scheduled_for`), an opaque egress approval reference
  (`egress_approval_ref` — never a URL, email, or destination), cost/resource
  observations (`input_tokens`, `output_tokens`, `cost_usd`, `resource_kind`
  — recorded for the Captain, never exposed in the officer projection), and
  broker/runtime-sourced model provenance (`model_id`, `effort_tier`,
  `skill_revision` — never read from environment variables);
- redaction categories, diagnostic-mode state, and an explicit
  `untrusted_observation` label.

Successful, refused, failed, retried, interrupted, recovered, duplicate,
paused, revoked, undone, and purged paths are all first-class evidence — and
so are absences: work that was missed, deliberately skipped, or expired
records its non-occurrence as a terminal status (`missed`, `skipped`,
`expired`).

The recorder never accepts caller-supplied sequence/hash/signature/timestamp
fields. It never stores raw credentials, unrestricted source contents,
absolute local paths, or hidden chain-of-thought. Evidence content is always
treated as untrusted data and never grants authority.

Every detail key additionally carries a trust class registered in
`framework/evidence/classification.py`: today all detail keys are
producer-asserted (recorded faithfully, not corroborated); only
recorder-minted fields (ids, timestamps, hashes, signatures) are
independently established. Component version/commit may fall back to
`CABINET_BUILD_VERSION`/`CABINET_GIT_COMMIT` and are therefore untrusted
provenance — never fuel-bearing; broker-attested model/effort/skill
provenance rides the reserved detail keys instead. Trial lineage is
structured: a child trial minted by delegation or re-mint carries
`parent_trial_id` in its genesis event detail (an `evidence-parent:<id>`
link is an optional mirror; the detail key is authoritative).

Act-class producers (Onboarding v2 today; every future producer) record
through one shared helper inside the locked evidence package
(`framework/evidence/lifecycle.py`): the same intent → policy → execution →
verification → receipt → outcome lifecycle with refusal/error branches,
evidence-before-action fail-closed semantics, id unification across the
producer and evidence planes, and trial re-mint lineage. The helper is an
import seam for sanctioned code admitted by ceremony — it adds no CLI, no
generic emit command, and no environment-derived store, and every payload
still flows through the recorder's sanitization and signing unchanged.

## Data locations and permissions

The canonical Cabinet integration writes below `instance/evidence/v1/`:

```text
control.json
.signing-key
trials/<trial-id>/.lock
trials/<trial-id>/events.jsonl
trials/<trial-id>/anchor.json
purge-receipts/purge-*.json
exports/<trial-id>-<utc>/...
```

Directories are mode `0700`; files are `0600`. The whole store is ignored by
git. Recorder code and trusted integrations are Ring-0 and `schg`-locked on an
armed Mac. The runtime store is deliberately not `schg`-locked because the
product must append, recover, retain, export, and purge it. Officer tools are
blocked from direct raw reads and writes; officers use only:

```bash
cabinet/scripts/evidence-read.sh <trial-id> [limit]
```

That command emits the smaller prompt-injection-resistant Cabinet projection.
It excludes free-form comments and source excerpts and begins with an explicit
“untrusted observations” boundary.

## Captain/operator commands

Run from the Cabinet repository. The commands below are Captain controls, not
officer tools.

### Captain capability token (required for mutating commands)

Mutating commands — any `control` change, `purge`, `retain`, and `export` —
never execute on a caller-supplied `"captain"` string. The caller must present
a Captain capability token: a value derived from the store's private signing
key (`HMAC(signing-key, "cabinet.evidence-captain-capability/v1")`). Mint it
once, keep it outside the officer tool surface (mode `0600`), and present it via
`--captain-token-file` or `$CABINET_CAPTAIN_TOKEN_FILE`:

```bash
python3.12 -m framework.evidence --store instance/evidence/v1 \
  grant-token --output /captain/chosen/captain.token
export CABINET_CAPTAIN_TOKEN_FILE=/captain/chosen/captain.token
```

`grant-token` requires read access to the store's private signing key and
refuses to overwrite an existing token file. Read-only commands (`verify`,
`project`, and `control` with no change) require no token. This is
defense-in-depth, not a complete boundary: in a same-UID deployment any process
that can read the signing key can re-derive the token, so full closure comes
from the separate-UID deployment boundary plus the officer hook layer that
structurally blocks importing the recorder modules.

### Read-only (no token)

Verify one live trial or the whole store:

```bash
python3.12 -m framework.evidence --store instance/evidence/v1 verify --trial <trial-id>
python3.12 -m framework.evidence --store instance/evidence/v1 verify
```

### Mutating (token required)

Create a redacted, checksummed review bundle:

```bash
python3.12 -m framework.evidence --store instance/evidence/v1 \
  --captain-token-file /captain/chosen/captain.token \
  export <trial-id> --output /captain/chosen/review-bundle
```

Read or change retention and temporarily enable diagnostic mode (reading
`control` needs no token; changing it does — shown here via the exported env
var):

```bash
python3.12 -m framework.evidence --store instance/evidence/v1 control
python3.12 -m framework.evidence --store instance/evidence/v1 \
  control --retention-days 90 --diagnostic on
python3.12 -m framework.evidence --store instance/evidence/v1 \
  control --forever --diagnostic off
python3.12 -m framework.evidence --store instance/evidence/v1 retain
```

Diagnostic mode still passes the same redaction boundary. It records that the
mode was active and expires by default after 24 hours. A lapsed diagnostic
window is never replayed into an unrelated retention change.

Typed purge is fail-closed and trial-specific:

```bash
python3.12 -m framework.evidence --store instance/evidence/v1 \
  --captain-token-file /captain/chosen/captain.token \
  purge <trial-id> --confirmation 'PURGE <trial-id>'
```

Purge holds the trial lock, verifies integrity, records durable intent, deletes
the trial, then leaves a signed content-free receipt binding the purged trial
hash, final event count, and final event hash. The signed receipt also acts as
a tombstone: a delayed or replayed action cannot reopen the purged trial.
Explicit Captain exports survive by design.
Onboarding's product UI asks for `PURGE`; its canonical core converts that into
the exact evidence-trial confirmation and completes both purge receipts.

## Crash and continuity behavior

Every append writes a signed `pending.json`, fsyncs the event, writes the
anchor, then removes the pending record. On restart, the recorder trims only a
partial tail, re-verifies continuity, reconciles the pending write exactly
once, records `interrupted`, and records `recovered`. It refuses new writes if
hash, sequence, signature, anchor, or pending continuity fails.

`framework.evidence.verifier` and the `verify` CLI path are read-only: they do
not initialize a store, create a key, recover a write, or call recorder
append/purge code. They re-derive the ledger from the bytes already present.
The verifier also maintains one signed anti-rollback watermark sidecar
(`.verify-watermarks.json`) in the store root: a monotonic high-water mark of
each trial's verified length and tip hash, keyed by hashed trial id. It never
mutates ledgers, anchors, controls, or receipts; a present-but-invalid sidecar
is treated as tamper evidence and fails closed rather than being rewritten.
Review bundles contain the verifier result plus `SHA256SUMS` and a
plain-language audit report.

Two continuity behaviors are visible in an audit and never drop a real action:

- **Trial re-mint on tombstone.** If retention or a Captain CLI purge
  tombstones the *live* onboarding trial, the journey mints a fresh trial under
  its state lock so later actions keep recording instead of wedging on
  `evidence_unavailable`. The fresh trial opens with a `system/recovered`
  genesis event whose `purged_trial_id_hash` links the tombstone, so the audit
  shows exactly where and why the trial lineage restarted. Purge *finality*
  still wins: a purged journey is never re-minted.
- **Deletion never blocked by a broken evidence plane.** A typed `PURGE`
  proceeds even when the evidence ledger cannot be verified (e.g. a corrupt
  byte). Onboarding source-derived data is deleted, and the evidence-side
  failure is recorded inside the purge receipt (`evidence_purge_status:
  pending`) with the pending marker kept so recovery or a Captain force-purge
  can finish the evidence-side deletion. Reporting the purge as failed would
  wrongly tell the Captain the data was not deleted.

## Cabinet self-diagnosis and repair

The Cabinet may inspect only the bounded projection. It may detect, diagnose,
reproduce, test, and propose a repair. Automatic repair is permitted only when
all of these are true:

- explicitly granted;
- internal and narrowly scoped;
- reversible, with a concrete rollback;
- regression tests pass;
- independent verification passes;
- a repair receipt is produced.

External, irreversible, security-sensitive, authority-changing,
audit-changing, and governance-changing repairs remain Captain-gated. The
Cabinet cannot edit, delete, suppress, disable, or forge the recorder or its
evidence through its sanctioned tool surface.

## Threat boundary

Today’s Mac Mini runtime uses access-inversion hooks plus OS `schg` for static
Ring-0 code, and tamper evidence for the live same-UID store. This detects
mutation, deletion, truncation, and unsigned forgery and blocks ordinary
officer tool access. It does not claim that string hooks and a file HMAC key
defeat an arbitrary hostile native process running as the Captain’s Unix user.

For the commercial signed app, move the signing key into the app
sandbox/Keychain with an app-specific principal. A separate verifier/public
anchor can then validate continuity without sharing signing authority.

## Verification and dogfood

The reproducible adversarial run is:

```bash
python3.12 -m framework.evidence.dogfood \
  --output /tmp/DOGFOOD-001-review-bundle
```

The landed [DOGFOOD-001 review](../evidence/DOGFOOD-001-review-bundle/audit-report.md)
records 15 passing scenarios across Dashboard → Telegram → World, including
transport/UI failure, crash recovery, source non-mutation, secret checks, and
typed purge. Verify its files with:

```bash
cd docs/evidence/DOGFOOD-001-review-bundle
shasum -a 256 -c SHA256SUMS
```

## Per-class retention (Phase 1, additive)

`control.json` carries an optional `retention_classes` map next to the
scalar `retention_days` dial, so high-churn day-bounded trials and
long-lived authority/outcome trials stop sharing one number. A retention
class is the `<class>` segment of the day-bounded trial taxonomy
`evt-<class>-<yyyymmdd>` (e.g. `evt-digest-anchor-20260716` → class
`digest-anchor`); trials that do not match the taxonomy always keep the
scalar dial. Defaults preserve current behavior exactly:

- `retention_classes` unset/`null` → the retention pass is byte-for-byte
  the previous scalar behavior.
- Old `control.json` files (written before the key existed) keep verifying
  unchanged — the control signature covers only present keys.
- A trial whose effective policy is "forever" is skipped without being
  verified (verification advances anti-rollback watermarks; a no-op
  retention pass must not have side effects).

Changing the map is a Captain control mutation behind the same capability
token as every other control change (read-only `control` stays tokenless):

```bash
python3.12 -m framework.evidence --store instance/evidence/v1 \
  --captain-token-file <path> control \
  --retention-class transport=45 --retention-class ui=45
```

`--retention-class` flags REPLACE the whole stored map; unset classes fall
back to `--retention-days`; `--clear-retention-classes` returns everything
to the scalar dial. `retain` then applies per-class ages at the usual trial
granularity with the usual verified-purge + signed-receipt semantics.

## External anchoring + the daily digest-anchor trial (Phase 1)

The store's hash chain, tip anchors, and signed watermarks all live INSIDE
the store, so restoring an old copy of the whole store resets protection —
absence is not provable locally (the verifier's documented residual). The
daily anchor job closes it from outside:

- `cabinet/scripts/evidence-anchor.py` (services.yml row `evidence-anchor`,
  staged) exports a content-free record — trial tip hashes, watermark rows,
  `control.json` digest, purge-receipt manifest, Captain-label file digests
  — to TWO Captain-owned surfaces outside the store: an appended+committed
  JSONL line in the private meta repo and a plain-English Telegram receipt
  through the front-door channel (design decision D3: both). Each run also
  compares the live store against the last exported record and pages
  (FATAL line, exit 2) on rollback, tip divergence, missing trials without
  purge receipts, or watermark deletion/regression. `--check` runs the
  comparison standalone (the restore drill).
- The same run appends one event per day to the evidence trial
  `evt-digest-anchor-<yyyymmdd>` recording checksums of the org-events day
  file, the consequence-ledger day file, and the trigger-archive manifest —
  the weaker breadth ledgers become tamper-evident without touching their
  emitters.
- Read-only by construction: the job never opens `.signing-key`, never runs
  the verifier (verify advances watermarks), and its one write path is the
  sanctioned recorder append seam. Collection/check logic lives in
  `framework/evidence_anchor.py` (deliberately outside the germline
  package; all paths explicit, no env-driven store selection). Unconfigured
  surfaces skip cleanly — bindings live in the deployment-local
  `evidence-anchor.yml`; start from the committed template
  `instance/config/evidence-anchor.yml.example`.

## Measured envelope (Phase 2 Batch A, 2026-07-17)

Design R-8: envelope numbers are **measured, then enforced** — never
invented. Source harness: `cabinet/scripts/evidence-bench.py`
(scratch-store only; it refuses anything under `instance/evidence` and
never consults `CABINET_EVIDENCE_DIR`). Re-run:

```bash
python3.12 cabinet/scripts/evidence-bench.py --output /tmp/evidence-bench.json
```

Run of record: 2026-07-17 (UTC 2026-07-16T23:28Z), macOS 26.6 arm64
(Apple Silicon), Python 3.12.13, APFS. Workload: 990 appends — 20
journey-shaped 8-event act trials, one 150-event mirror day trial
(`evt-benchorgmirror-<yyyymmdd>`), one 48-event consequence-mirror day
trial, a 512-event long-trial sweep, 120 single-event trials (watermark
axis). Final scratch store: 143 trials, 1,234,439 bytes; `verify_store`
green.

**Append latency** (`append` re-verifies the whole trial per write —
O(n²) total per trial; fsync-dominated at small depths):

| shape (depth) | p50 | p95 | max |
|---|---|---|---|
| journey (8-event act trial) | 1.43 ms | 1.78 ms | 2.09 ms |
| consequence day trial (48) | 2.77 ms | 4.39 ms | 6.80 ms |
| mirror day trial (150) | 6.33 ms | 10.67 ms | 11.32 ms |
| sweep trial (to 512) | 18.07 ms | 33.91 ms | 35.91 ms |
| overall (990 appends) | 6.93 ms | 31.72 ms | 35.91 ms |

Sweep p95 by depth: 1–8: 1.76 ms · 9–64: 5.46 ms · 65–128: 9.67 ms ·
129–256: 17.71 ms · 257–384: 26.23 ms · 385–512: 34.76 ms — linear
per-append growth ≈ +0.065 ms/event; a full 512-event day trial costs
≈ 9.3 s of cumulative append time spread across the day.

**Store growth**: ~1.2 KB/event stored (journey 1211 B, mirror 1203 B,
sweep 1190 B — anchors, locks and watermark churn amortized). Projected
against the live volumes measured in recon (2026-07-14..16: org events
1,313–2,372/day of which ~94 % excluded exhaust; mirrored org-signal
tens–142/day; consequence 1–48/day; 20 acts/day assumed):

| scenario | events/day | MB/day | MB/90d |
|---|---|---|---|
| org-signal typical | 80 | 0.09 | 8.3 |
| org-signal worst measured | 142 | 0.16 | 14.7 |
| consequence worst | 48 | 0.06 | 5.0 |
| journey acts (20×8) | 160 | 0.19 | 16.6 |
| combined worst day | 350 | 0.40 | 36.2 |

**Watermark axis** (the second growth axis — every append rewrites the
store-wide signed anti-rollback index, O(#trials) per append; bounded by
day-rolling + retention, **not** by the per-trial cap): 120 trials →
27,192 B index; single-event append p95 1.07 ms (early) vs 1.13 ms
(late) — flat at this scale. State the envelope claim precisely: the
per-trial cap bounds per-append verify cost, the taxonomy + retention
bound the watermark axis.

**Verification cost** (doctor bounded-runtime basis): whole-store verify
(143 trials / 990 events) = 0.172 s; single-trial verify at 512-event cap
depth = 0.032 s.

**Measured recommendation: `512` · Enforced constant: `MAX_TRIAL_EVENTS
= 500` (provisional).** Both numbers are recorded here deliberately
(Batch-A seam reconciliation). The bench's measured recommendation is 512:
smallest candidate ≥ 3.0× the worst simulated day-bounded mirror trial
(150 events; live worst measured org-signal day ≈ 142), with p95 append at
depth 385–512 = 34.8 ms — well inside the 250 ms budget — and headroom
absorbing crash-recovery tails (+2), re-mint genesis (+1) and journey
completion tails (+5). The ENFORCED value in
`framework/evidence/recorder.py` stays the provisional `500` that landed
with the germline envelope wave (sized from the live recon volumes with
5–10× headroom; a code constant, never env- or `control.json`-derived).
Retuning 500 → 512 is a follow-up germline ceremony with this measured
basis — never a silent edit. The telemetry-mirror module aligns its own
per-segment constant to the enforced value
(`framework/evidence_mirror.py MAX_MIRROR_EVENTS_PER_TRIAL = 500`) and
chains suffixed day segments (`evt-orgmirror-b-<yyyymmdd>`, up to 6) before
the recorder cap can refuse. Day-bounded taxonomy trials are the primary
envelope; the cap is the backstop, and a cap hit on a mirror trial degrades
loud + re-mints a chained trial (suffix inside the class segment) rather
than blocking any domain emit.

**Doctor thresholds derived from this run**
(`cabinet-doctor.sh` check 12, AMBER-max): freshness 48 h; growth ceiling
256 MB ≈ 7× the projected 90-day worst case (36.2 MB); cap-approach warn
at 80 % of the enforced 500 (= 400 events in one day trial;
`EV_CAP_DEFAULT` tracks `MAX_TRIAL_EVENTS` — sync pinned by
`framework/tests/test_evidence_doctor_probes.py`); chain continuity =
read-only single-newest-trial verifier spot-check (~32 ms at cap depth);
degradation markers = mtime-recency probes over the telemetry-mirror
ledger `cabinet/logs/evidence-mirror-degradations.jsonl` (probed even when
the store is absent) and the act-class lifecycle sidecar
`<store>/degradations.jsonl` (24 h window).

Caveat: latency numbers are per-machine (fsync-dominated) — re-run the
bench on the deployment target (Mac Mini) before tightening any
threshold; growth numbers scale with the mirrored-class allow-list, so
re-measure when classes are added.

## Telemetry mirror tier (Phase 2 Batch A, 2026-07-17 — observation-only)

Batch A adds the first whole-cabinet producers: telemetry MIRRORS at the two
breadth-plane chokepoints. Recording is purely observational — receipts
about already-happened events; no downstream consumer changes its read
path, and the org/consequence domain writes are never blocked.

- **Chokepoints:** `framework/events/emitter.py` (org events) and
  `framework/fidelity/consequence.py` (consequence rows) call the
  non-germline mirror engine `framework/evidence_mirror.py` at emit time
  (`from framework import evidence_mirror` — the code-level import seam;
  there is no emit CLI/API).
- **Allow-list law (the 59%-plumbing lesson):** only classes in
  `MIRRORED_ORG_EVENT_TYPES` mirror (Captain/role/mission/graduation/
  trust/safety/needs signal — a strict subset of `VALID_EVENT_TYPES`,
  pinned by test). Nervous-system trigger delivery/ACK/heartbeat exhaust
  structurally never reaches the chokepoints and must never join the list;
  session/notification/outbox/`policy_evaluated`/eval-run exhaust is pinned
  out via `NEVER_MIRRORED_EXHAUST` (disjointness is a test tripwire).
  Consequence rows mirror on live lifecycle presence (proposal/outcome/
  review); rows carrying `sim:true` and refused rows never mirror.
- **Trials:** day-bounded taxonomy trials (`evt-orgmirror-<yyyymmdd>` /
  `evt-consequence-<yyyymmdd>`), per-segment constant
  `MAX_MIRROR_EVENTS_PER_TRIAL = 500` (aligned with the recorder's
  enforced `MAX_TRIAL_EVENTS`), chained suffix segments inside the class
  token (`evt-orgmirror-b-<yyyymmdd>`, ≤ 6 segments) before loud skip.
- **Correlation both directions:** forward, the emitter stamps
  `payload["evidence_mirror"]["trial_id"]` into a COPY of the payload
  (org) and the consequence chokepoint appends one namespaced
  `evidence-trial:<trial-id>` ref; reverse, each receipt's
  `correlation_id` is the org event id / the canonical row sha256, and
  `detail` carries join keys only (ids and digests, never payload copies).
- **Degradation contract:** mirrors degrade LOUD and NEVER block the
  domain emit — one stderr WARN per (chokepoint, reason) per process, one
  marker line per 900 s window appended to the runtime ledger
  `cabinet/logs/evidence-mirror-degradations.jsonl` (doctor check 12 probes
  its recency, even when the store is absent), and a best-effort
  `evidence_mirror_degraded` org event (registered in the emitter
  vocabulary; never itself mirrored — no recursion). An integrity-red
  trial is tamper evidence: degraded loud, never auto-reminted (the day
  boundary recovers). Act-class producers (fail-closed
  evidence-before-action) are Batch B, not this tier.
- **Producer identity (A6):** fixed module constants
  (`org-event-mirror` / `consequence-mirror`); the mirrored row's own
  claimed actor is DATA in `detail`, never the evidence `actor`. The
  germline `framework/evidence/identity.py` seam is the Batch-A
  attestation primitive: `attest_process_identity()` freezes one validated
  identity per process (idempotent identical re-attest; typed
  `identity_conflict` refusal; fail-closed accessors; never env-derived,
  and explicit version/commit values keep the recorder's env provenance
  fallback unconsulted). Attested events carry the producer-asserted
  `attestation_mode: "process"` detail stamp — audit/fuel-integrity
  vocabulary, deliberately NOT officer-projected. Out-of-process broker
  attestation is a later ceremony; Phase 6 hard-requires it (HP-1).
- **Officer surface: NONE.** No CLI, no read API; the mirror join keys are
  not in `PROJECTION_ALLOWED_DETAIL`, so the fail-closed officer
  projection drops them (never-a-score by construction).
  `cabinet/scripts/evidence-read.sh` remains the ONLY officer path and is
  untouched by Batch A.
- **Coverage line (A2, mechanical):**
  `python3.12 cabinet/scripts/evidence-coverage.py` reconciles producers
  vs enumerated action-taking surfaces. At the Batch A pin: *evidence
  covers 4 of 13 action-taking surfaces* — wired: the two chokepoint
  mirrors, the onboarding journey, the digest-anchor; everything else was
  an honest named KNOWN-GAP (superseded by Batch B — current line in the
  act-class tier section below). An UNENUMERATED producer exits 1 (drift
  catch); `--strict` turns any gap into a failure and is the Phase-2-end
  gate. Shell invocations of the evidence CLI are detector-only, never
  producer wiring.
- **Pytest fence:** under `PYTEST_CURRENT_TEST` the mirror is disabled
  unless the test supplies scratch `CABINET_EVIDENCE_MIRROR_STORE` /
  `CABINET_EVIDENCE_MIRROR_MARKER` overrides — consulted ONLY under
  pytest; production store resolution never reads the environment (A10)
  and reuses the one canonical journey `EVIDENCE_REL` constant.

## Act-class producer tier (Phase 2 Batch B, 2026-07-17 — evidence-before-action)

Batch B wires the design's direct producers (§3 Phase 2 items 2+3 and
refinement R-1) — the surfaces where act semantics matter — and enforces
the per-class recording contract as written law:

- **The contract:** ACT-CLASS producers (the moment BEFORE an effect) use
  `framework/evidence/lifecycle.py` `ActLifecycle` with
  evidence-before-action FAIL-CLOSED semantics — if the evidence plane
  cannot record, the ACTION DOES NOT RUN (typed refusal, e.g.
  `GateEvidenceError` / the lane's refusal path; a designed behavior
  change on the broken-plane branch ONLY — the happy path is
  domain-stable). TELEMETRY receipts (something ALREADY happened) ride the
  Batch A mirror: degrade LOUD (stderr WARN + marker sidecar +
  `evidence_mirror_degraded` org event), never block the domain write.
  When genuinely ambiguous, prefer receipts and say so in code — nothing
  is silently fail-closed. Tightenings (freeze/veto/kill-switch) are NEVER
  evidence-gated: their receipts are best-effort AFTER the durable domain
  write.
- **Act-class producers wired:** the act-first action lane
  (`framework/frontdoor/action_exec.py` + `framework/acting/
  run_action_lane.py` — full signed lifecycle trials; the hourly
  reconciler `framework/frontdoor/action_reconcile.py` lands machine
  outcome labels as verification/outcome events linked to the undo-journal
  row) and the learning/gate machinery recording itself
  (`framework/learning/gate.py` verdict trials, `framework/learning/
  apply_watch.py` apply-watch decision trials; the apply arm is
  fail-closed, brake/receipt arms degrade loud).
- **Receipt-class producers wired:** watchdog/doctor verdicts through the
  typed lens `framework/watchdog/receipts.py` (`watchdog_outcome_failed`
  cooldown-bounded, `doctor_verdict` 1/day, `officer_restarted` capped,
  `officer_limit_wake` exactly-once) invoked by `check.py`,
  `cabinet-doctor.sh` and the cron watchdogs; officer-session lifecycle
  transitions from the unlocked state-diff observer
  `cabinet/scripts/emit-officer-lifecycle-transitions.py`
  (`officer_session_started/ended/compacted`, per-officer daily cap,
  transitions only); and the R-1 authority/control-plane —
  `binder_wire.py` posture-cap verb receipts
  (`posture_cap_narrowed/cleared`), `needs.py` `need_approved` (the
  Captain's grant-verb DECISION moment, distinct from the applied
  ceremony's `need_granted`), `action_undo.py` `kind_frozen` (freeze/lift
  symmetry), `veto_registry.py` structured `veto-scope:` consequence refs,
  and the unlocked sweep `cabinet/scripts/emit-authority-transitions.py`
  (`posture_changed`, `germline_unlock_observed`/`germline_relock_observed`,
  kill-switch transitions; first run seeds silently; at-least-once).
  Both sweeps ship in `cabinet/services.yml` as `disabled: true` — the
  enable is a deploy step (generate-plists + load), soak-safe (D8).
- **One recording path per event class (R-13):** act surfaces record
  signed lifecycle trials directly and their org events stay OFF the
  mirror allow-list; each receipt class has exactly one emit site (the
  lifecycle sweep deliberately does not re-emit the watchdogs' restart/
  wake verbs). Both sweeps self-check their classes against
  `MIRRORED_ORG_EVENT_TYPES` at run start — LOUD, never blocking.
- **Never recorded:** trigger/heartbeat/delivery exhaust, healthy
  passes, per-poll sweep rows, generic session/subagent exhaust (~94% of
  live org volume — pinned out via `NEVER_MIRRORED_EXHAUST`).
- **Coverage line (A2, mechanical) at the Batch B pin:**
  `evidence covers 9 of 13 action-taking surfaces; named gaps:
  attention-hygiene, probes-verification, roles-missions-lifecycle,
  ops-consequence-scripts` — the named gaps are future waves;
  UNKNOWN-not-health, the Act layer is frozen over them (§2.4).
- **Germline ceremony:** the 8 schg files this batch changes are listed
  (exact union + same-day unlock→checkout→relock block) in
  `docs/proposals/germline-amendment-evidence-phase2b-2026-07-17.md`;
  review artifact
  `shared/interfaces/reviews/evidence-phase2-batch-b-cp1.md`.
