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
- redaction categories, diagnostic-mode state, and an explicit
  `untrusted_observation` label.

Successful, refused, failed, retried, interrupted, recovered, duplicate,
paused, revoked, undone, and purged paths are all first-class evidence.

The recorder never accepts caller-supplied sequence/hash/signature/timestamp
fields. It never stores raw credentials, unrestricted source contents,
absolute local paths, or hidden chain-of-thought. Evidence content is always
treated as untrusted data and never grants authority.

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

Verify one live trial or the whole store:

```bash
python3.12 -m framework.evidence --store instance/evidence/v1 verify --trial <trial-id>
python3.12 -m framework.evidence --store instance/evidence/v1 verify
```

Create a redacted, checksummed review bundle:

```bash
python3.12 -m framework.evidence --store instance/evidence/v1 \
  export <trial-id> --output /captain/chosen/review-bundle
```

Read or change retention and temporarily enable diagnostic mode:

```bash
python3.12 -m framework.evidence --store instance/evidence/v1 control
python3.12 -m framework.evidence --store instance/evidence/v1 \
  control --retention-days 90 --diagnostic on
python3.12 -m framework.evidence --store instance/evidence/v1 \
  control --forever --diagnostic off
python3.12 -m framework.evidence --store instance/evidence/v1 retain
```

Diagnostic mode still passes the same redaction boundary. It records that the
mode was active and expires by default after 24 hours.

Typed purge is fail-closed and trial-specific:

```bash
python3.12 -m framework.evidence --store instance/evidence/v1 \
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
Review bundles contain the verifier result plus `SHA256SUMS` and a
plain-language audit report.

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
