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
