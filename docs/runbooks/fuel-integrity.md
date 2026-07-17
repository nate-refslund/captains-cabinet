# Fuel-integrity check — report-only shadow runbook (Phase 4)

Module: `framework/evidence_fuel_integrity.py` · Tests:
`framework/tests/test_fuel_integrity.py` · Design of record: whole-cabinet
evidence design 2026-07-16 §3 Phase 4 item 2, §2.4/§2.5, HP-1/HP-2/HP-3.

## The honest claim (read this first, repeat it everywhere)

This check **detects retroactive single-plane tamper and INCONSISTENT
forgery only; consistent same-user forgery of both planes (the same OS user
writes the consequence ledger and the evidence store, and the store signing
key is same-user-readable) stays open until HP-1 (OS-user/key isolation)
lands — necessary, not sufficient.**

Concretely: a forger who writes a consequence row, its matching signed
mirror receipt, a Captain label event, *and* the journal digest — all
writable by the officer OS user today — produces a `grounded` verdict.
`framework/tests/test_fuel_integrity.py::TestConsistentDualPlaneForgeryIsTheDocumentedGap`
pins this gap by name so it can never be silently forgotten. Related
residual: purge-receipt presence is checked by file *name* (the
check_anchor rule); receipt signature validity is the verifier's and the
external anchor's job. Process attestation (`attestation_mode: "process"`)
is same-user-*declared* identity, never broker attestation.

## What it is

A read-only, out-of-band re-derivation of the six preconditions the design
requires **before any consequence row mints graduation fuel** (fuel =
`review.verdict == confirmed` with `source == verdict_human`;
`verdict_gate` fuel is structurally zero today — the A3 label floor is
absent, CG-1):

1. verified recorder mirror (receipt present in the `evt-consequence-*`
   day class, trial verifies green);
2. consequence↔evidence consistency (`row_sha256` join over the surviving
   last-write-wins row);
3. third-leg presence — Captain labels re-counted against the off-store
   `shared/interfaces/governance-labels.jsonl` digests (B1; unanchored
   in-store labels are advisory and satisfy nothing — HP-3); the machine
   ttl-survival marker is reported as producer-adjacent (A5: two same-hand
   planes are not corroboration);
4. attestation on the receipt (absent today on consequence-mirror
   receipts — reported honestly as `unattested`);
5. no purge-overlap (a purged fuel window is reduced-confidence ⇒
   would-withhold, §2.4);
6. per-cell intent→outcome closure floor and unknown-rate ceiling — floors
   reuse `judge_calibration.JUDGE_HARD_BAR` / `MIN_PAIRS` (R-8/R-11: no
   second number, no argv override; the unknown ceiling is the derived
   complement `1 − JUDGE_HARD_BAR`).

## What it is NOT (shadow law)

**Report-only. It never blocks minting, never gates, never scores.**
Nothing imports the module (grep-proven by its own test suite); its exit
code carries no verdict signal (0 = measured, 2 = could not measure); its
output file is Captain-facing runtime data at
`cabinet/logs/fuel-integrity-report.jsonl` (gitignored) and is never
officer-projected, never an org event, never in the attention feed. The
weekly line carries counts, never rates. The **enforce flip** — putting
this check in front of `compute_ratios`/`evaluate` — is a **later,
Captain-only ceremony** (a pure narrowing per the posture asymmetry,
design §2.6, with immutable-core admission per §3 Phase 4 item 5). Its
removal after that flip is likewise Captain-only.

## Verdict vocabulary

- `grounded` — all six preconditions affirmatively pass.
- `ungrounded:<reason>` — affirmative failure: `verify_failed`,
  `row_sha_mismatch`, `trial_missing` (tamper-shaped);
  `unmirrored_row` (chokepoint invariant violated: no mirror ref AND no
  degradation row — still not a tamper claim); `purge_overlap`;
  `cell_closure_below_floor`; `cell_unknown_rate_above_ceiling`.
- `unknown:<reason>` — insufficiency, pass-through (the discriminator
  triage law: NOISE only with affirmative evidence): `mirror_degraded`
  (explained by the degradation ledger), `third_leg_absent` /
  `third_leg_unanchored` / `third_leg_producer_adjacent`,
  `attestation_absent`, `cell_insufficient_pairs`, `store_unavailable`,
  `store_error`.

`would_withhold` = anything not grounded (HP-2 fail-closed wording) and is
information only in this batch.

## Running it (Captain/launchd context only)

```
python3.12 -m framework.evidence_fuel_integrity            # defaults
python3.12 -m framework.evidence_fuel_integrity --no-write # print only
```

The officer hook layer screens the `framework.evidence` command substring,
so officers structurally cannot run it — intended: shadow reports are
Captain-facing only. There is deliberately **no services.yml row in this
batch**; scheduling it is a separate staged-dark wiring step
(`disabled: true`, the evidence-anchor precedent), and the weekly
governance-review line ("graduations grounded: N/M verified …") is wired
by the review-surface owner tailing the report file — this module only
produces the line text.

## Reading the report

JSONL, three line kinds, every line carrying `honest_claim`:
`kind: "row"` (one per fuel row: verdict, signals, `tamper_shaped`,
`would_withhold`), `kind: "cell"` (per fuel-bearing cell: n, closure/
unknown rates, floors, stratum annotation from the authority matrix), and
`kind: "summary"` (counts + the weekly line + the gate-fuel honesty note).
Expect production reality today to read mostly `unknown:attestation_absent`
/ `unknown:third_leg_absent` — that is the true grounding state of current
fuel, not a malfunction: the mirror does not attest yet and most human
verdicts predate the anchored labeling ritual.

## Safety envelope

Reads ride the minter's own ledger read path (`read_ledger`) and the
public `EvidenceRecorder.read_events` API; the sole store side effect is
the sanctioned first-verify watermark advance (identical to the verify
verb; two-pass byte-stability pinned in the test suite). The checker never
constructs a recorder over an absent store (construction would create
scaffolding) and `write_report` refuses any output path inside the store
or the consequence-ledger dir — it can never write anything the minter
reads.
