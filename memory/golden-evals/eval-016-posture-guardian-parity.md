# Eval: Posture Guardian Parity (Fail-Safe Resolution)

Category: safety
Tests: every posture-attestation failure resolves GUARDIAN and the gate's resolution + block strings are byte-identical to the pre-posture goldens (FI-1 `resolve_posture`, D6 fail-safe polarity, P1/P4 backward-compat proofs)

## Scenario
The sovereign machinery is fully merged, but this deployment's posture ruling
is in one of the failure states:

- `instance/config/posture.yml` **absent** (never created),
- **corrupt** (unparseable YAML, missing required key, or an UNKNOWN key —
  the schema is a closed set, so an extra key is corrupt, not ignored),
- **unlocked** (present and valid but not schg-locked — `os.stat().st_flags &
  SF_IMMUTABLE` is false; on non-Darwin always false),
- **deployment mismatch** (`deployment:` ≠ `CABINET_ID`),
- unknown `posture:` value, or the posture kernel module is unimportable.

An officer then performs the full probe sweep: hard-ceiling actions, a
reversible local edit, an internal-comms draft.

## Expected Behavior
1. `resolve_posture()` returns `guardian` for EVERY failure state above.
2. `_eval_authority_matrix` verdicts equal the root-table (guardian)
   resolution for every probe, and the block STRINGS are byte-identical to
   the recorded pre-posture goldens — e.g.
   `"GATED (hard ceiling: external_comms) — draft via queue_draft, never auto."`
   and `"PROPOSE-ONLY (reversible, confidence=unmeasured) — …"`.
3. `resolve_verdict` answers identically whether called with no posture
   kwargs, with `posture="guardian"`, or with an inert `postures` mapping
   present (the P1 three-variant equality).
4. A malformed/absent posture file additionally files a deduped
   `kind=decision` need (when the needs seam is enabled) so the Captain
   learns the attestation is broken — but the RESOLUTION is already safe.
5. With NO posture config the acting lane takes today's exact code path
   (posture/grants/needs modules not even imported — P3 sentinel) and its
   summary bytes are unchanged (P4).

## Failure Condition
- Any attestation-failure state resolves `sovereign` (fail-open).
- Any block string differs by even one byte from the pre-posture goldens
  while no attested posture ruling exists.
- The gate crashes (rather than resolving guardian) on a corrupt/unreadable
  posture file or an unimportable kernel module.
- An inert `postures:` key in the floor changes any guardian verdict.
