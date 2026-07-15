# Germline Amendment — Evidence Recorder v1

**Status:** Captain-approved by the Evidence Recorder v1 goal. The code lands
through review and CI; each deployed Cabinet applies the ordinary
unlock → update → `germline-lock.sh lock` ceremony before autonomous operation.

## Ruling

Evidence about an officer cannot be controlled by that officer. The recorder,
independent verifier, redaction boundary, repair policy, and trusted
integration seams therefore join Ring-0. Live evidence remains writable only
through the sanctioned recorder because append, recovery, retention, export,
and Captain-typed purge are required runtime operations.

The Cabinet may consume only `cabinet/scripts/evidence-read.sh`, which emits a
bounded read-only projection with an explicit untrusted-data instruction
boundary. Direct officer access to raw JSONL, anchors, receipts, controls, and
signing material is blocked. Captain/operator verification, export, retention,
diagnostics, and purge remain available through `python3.12 -m
framework.evidence` outside the officer tool surface.

This is access inversion, not a claim that same-UID string hooks defeat an
arbitrary hostile native process. On current Mac Mini deployments, static code
is additionally protected by `schg`; runtime evidence is hash-chained, locally
signed, anchored, and independently verified so mutation, deletion, and
truncation fail visibly. The commercial app boundary should place the signing
key in its sandbox/Keychain so officers never share the key's OS principal.

## Ring-0 edit set

| Path | Reason |
|---|---|
| `framework/evidence/` | Recorder, redaction, repair policy, bounded CLI, independent verifier, and their contract tests. |
| `framework/onboarding/journey.py` | Canonical Onboarding v2 evidence writer; mutating it can suppress evidence. |
| `framework/schemas/evidence-event.schema.json` | Public evidence record contract. |
| `cabinet/dashboard/src/app/api/onboarding/` | Dashboard/World server-side action and observation transport seam. |
| `cabinet/dashboard/src/lib/onboarding/bridge.ts` | Only Dashboard bridge into the canonical writer. |
| `cabinet/dashboard/src/lib/onboarding/telegram.ts` | Telegram action/feedback correlation seam. |
| `cabinet/dashboard/src/app/api/telegram/provisioning-webhook/route.ts` | Telegram delivery success/failure instrumentation. |
| `cabinet/dashboard/src/components/onboarding/journey-card.tsx` | Dashboard/World UI, transport-error, handoff, and usefulness observation seam. |
| `cabinet/companion/main.swift` | App-shell handoff correlation seam. |
| `cabinet/scripts/evidence-read.sh` | The sole bounded officer read doorway. |
| `instance/evidence/v1/` | Runtime-appended evidence store; hook/policy protected and deliberately not `schg` locked. |

Enforcement files changed in the same amendment are
`framework/policies/immutable-core.yml`,
`framework/policies/base-safety.yml`,
`cabinet/scripts/germline-lock.sh`, and
`cabinet/scripts/hooks/pre-tool-use.sh`. The lockstep meta-test was extended
only to model a trailing-slash runtime-appended directory; all four enforcement
lists remain bidirectionally checked.

## Verification

- `python3.12 -m pytest framework/tests/test_germline_lockstep_consistency.py -q`
- `bash cabinet/tests/hook-regression/germline-readonly.sh`
- `bash cabinet/tests/hook-regression/germline-bash-write.sh`
- `bash cabinet/tests/hook-regression/evidence-access.sh`
- `bash -n cabinet/scripts/hooks/pre-tool-use.sh cabinet/scripts/evidence-read.sh`
- Evidence Recorder unit/integration, Dashboard, Telegram, companion, and
  DOGFOOD-001 gates named in the Evidence Recorder v1 review report.

## Apply and rollback

Apply on each target in a Captain-controlled unlock window, update to the
reviewed commit, run the verification set, then execute `sudo bash
cabinet/scripts/germline-lock.sh lock` and `bash
cabinet/scripts/germline-lock.sh status`.

Rollback is one revert of the Evidence Recorder v1 milestone inside an unlock
window. It removes `framework/evidence/`, the schema, the protected integration
seams, `cabinet/scripts/evidence-read.sh`, and the `instance/evidence/v1/`
enumeration together, then restores the prior four-list boundary and relocks.
Runtime evidence and explicit exports are not silently deleted by code
rollback; the Captain may export or typed-purge them separately.
