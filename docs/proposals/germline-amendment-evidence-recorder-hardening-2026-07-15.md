# Germline amendment — EVIDENCE RECORDER HARDENING — 2026-07-15

**Status:** PROPOSED on `feat/evidence-recorder-hardening` (off `2f0253b7`).
The Captain's FF-merge of this branch to master (after CI is green) is the
apply; the post-merge on-Mac unlock ceremony below re-materializes the schg
files at the landed bytes and relocks the same day.

**Ledger:** row `CG-EVIDENCE-HARDENING` (the orchestrator adds the matching
`docs/plans/operative-egg-ledger-2026-07-07.yml` entry post-merge, with its
A13 plan-doc parity row).

**Wave:** the fix batch for the 27-finding deep review of PR #140 Evidence
Recorder v1 (source review `designs/PR140-EVIDENCE-RECORDER-REVIEW-2026-07-15.md`
→ orchestrator commit `e5ec86e`; checkpoint review
`shared/interfaces/reviews/feat-evidence-recorder-hardening-cp1.md`).

## Why this touches germline

The Evidence Recorder is the Captain's onboarding audit plane — it records a
full onboarding so the Captain can later review the logs and judge/repair
onboarding. Its code and trusted integration seam are Ring-0 and `schg`-locked
precisely so officers cannot edit, disable, or forge the audit plane. PR #140
shipped that plane AND schg-locked its own code, so the plane's own reviewed
bugs — including 3 P0 same-UID hook bypasses that falsify its
"Captain-only-evidence-boundary" claim — now sit behind the lock that protects
it. Fixing them is a germline edit by construction; it cannot be done by the
loop/officers and must route through the Captain sudo unlock ceremony. This is
doctrine-correct: the audit plane evolves only under the Captain's hand.

No new paths JOIN the locked set — every germline file here is ALREADY locked
(the `framework/evidence` and `cabinet/scripts/hooks` directories, the
`cabinet/dashboard/src/app/api/onboarding` directory, and the named
`journey.py` / provisioning-webhook `route.ts` files). This amendment records
the CONTENT change to existing germline paths, not a boundary extension. So
`cabinet/scripts/germline-lock.sh` FILES/DIRS, `framework/policies/immutable-core.yml`,
and `pre-tool-use.sh` §5/§5b need NO edit — the lockstep meta-test stays green.

## Germline (schg-locked) files changed by this batch

These are inside the locked set and require the unlock ceremony to update on an
armed Mac:

| Path | Locked via | Change |
|---|---|---|
| `cabinet/scripts/hooks/pre-tool-use.sh` | `cabinet/scripts/hooks` dir (-R) | §0a/§5a: path-normalize the raw-read boundary, reject multi-line doorways, destructive-verb store-wipe arm, interpreter-import screen (findings #1/#2/#3/#4) |
| `framework/evidence/__main__.py` | `framework/evidence` dir (-R) | Captain-capability token gate + `grant-token`; lapsed-diagnostic-window fix (#4/#22) |
| `framework/evidence/policy.py` | `framework/evidence` dir (-R) | `RepairRequest` danger dimensions default fail-closed `True` (#23) |
| `framework/evidence/recorder.py` | `framework/evidence` dir (-R) | typed canonical error, external mutex + ghost-dir heal, `"\n"`-only reader, `recover_pending` on construct, retention `exclude` (#5/#6/#12/#13/#14) |
| `framework/evidence/redaction.py` | `framework/evidence` dir (-R) | URI/bot/email/chat-id/underscore-keyword redaction, surrogate scrub, ReDoS bound, re-scan after path-sub/truncate (#7/#8/#12/#16/#17) |
| `framework/evidence/verifier.py` | `framework/evidence` dir (-R) | non-dict-anchor fail-closed, signed anti-rollback watermark, purge-resurrection cross-check, `b"\n"`-only framing (#6/#9/#24/#25) |
| `framework/evidence/tests/test_recorder.py` | `framework/evidence` dir (-R) | regression teeth |
| `framework/evidence/tests/test_cli_policy.py` (new) | `framework/evidence` dir (-R) | capability-gate + policy teeth |
| `framework/evidence/tests/test_redaction.py` (new) | `framework/evidence` dir (-R) | redaction/PII/surrogate teeth |
| `framework/evidence/tests/test_verifier.py` (new) | `framework/evidence` dir (-R) | adversarial verifier teeth |
| `framework/onboarding/journey.py` | named FILE | trial re-mint, degraded-but-recorded purge, shared id anchor, surrogate scrub (#5/#10/#12/#15/#26/#27) |
| `cabinet/dashboard/src/app/api/onboarding/evidence/route.ts` | `.../api/onboarding` dir (-R) | require bounded Content-Length before buffering (#11) |
| `cabinet/dashboard/src/app/api/onboarding/evidence/route.test.ts` | `.../api/onboarding` dir (-R) | body-bounding teeth |
| `cabinet/dashboard/src/app/api/telegram/provisioning-webhook/route.ts` | named FILE | purge-suppression grammar derived from real intent regex (#20) |

## Non-germline files changed by this batch (land with the merge, no ceremony)

- `cabinet/scripts/run-hook-regression.sh` — wires in the new harness
- `cabinet/tests/hook-regression/evidence-pathnorm.sh` (new) — hook teeth
- `framework/onboarding/tests/test_journey.py` — journey teeth
- `cabinet/dashboard/src/app/api/telegram/provisioning-webhook/route.test.ts` — teeth
- `cabinet/dashboard/src/components/onboarding/journey-card.test.ts` — teeth
  (the germline `journey-card.tsx` is NOT changed — only its test)

## Apply ceremony (Captain sudo, on the armed Mac, same day)

The bytes are already landed on master by the FF-merge; the ceremony brings the
on-disk germline files up to that landed ref inside an unlock window and relocks.

```bash
# 0. from a CLEAN /Users/nate/captains-cabinet on master @ the merged tip
git -C /Users/nate/captains-cabinet fetch origin
git -C /Users/nate/captains-cabinet merge --ff-only origin/master

# 1. open the Captain edit window (schg is system-immutable; needs root)
sudo bash cabinet/scripts/germline-lock.sh unlock

# 2. re-materialize ONLY the landed germline files at the merged ref
#    (working tree already holds them from the ff-merge; this is the explicit,
#    auditable checkout of exactly the amendment's file set)
git -C /Users/nate/captains-cabinet checkout origin/master -- \
  cabinet/scripts/hooks/pre-tool-use.sh \
  framework/evidence/__main__.py framework/evidence/policy.py \
  framework/evidence/recorder.py framework/evidence/redaction.py \
  framework/evidence/verifier.py \
  framework/evidence/tests/test_recorder.py \
  framework/evidence/tests/test_cli_policy.py \
  framework/evidence/tests/test_redaction.py \
  framework/evidence/tests/test_verifier.py \
  framework/onboarding/journey.py \
  cabinet/dashboard/src/app/api/onboarding/evidence/route.ts \
  cabinet/dashboard/src/app/api/onboarding/evidence/route.test.ts \
  cabinet/dashboard/src/app/api/telegram/provisioning-webhook/route.ts

# 3. RELOCK the SAME day (arms schg over the whole set; idempotent)
sudo bash cabinet/scripts/germline-lock.sh lock

# 4. verify the boundary is armed
bash cabinet/scripts/germline-lock.sh status
bash cabinet/scripts/germline-lock.sh verify
```

Because schg is *system*-immutable, steps 1 and 3 are the ONLY writable window
— the loop/officers cannot perform them. If interactive sudo is unavailable to
the orchestrator, this stays a named handback to Nate (external limit that
survives the standing grant). Do not work around the lock.

## What does NOT change

- No boundary extension: the locked SET is byte-identical; only the CONTENT of
  already-locked files changes.
- No behavior change to any non-evidence surface: the batch is scoped to the
  evidence/onboarding plane and its hook boundary.
- The `schg`/access-inversion threat model in
  `docs/runbooks/evidence-recorder-v1.md` is unchanged; this batch CLOSES the
  three P0 same-UID hook gaps that the runbook's own threat-boundary section
  already disclaimed as residual.
