# Checkpoint review — feat/cog3-contract, cp1 (COG-3 contract landing)

**Scope:** docs-only landing off `origin/master` `754998f8` — the Captain-approved
COG-3 contract (`docs/plans/cognitive-core-phase-3-contract-2026-07-22.md`, ~360
lines) + the operative-ledger COG-3 row flip todo→in-flight + the plan-doc §9
parity row. No code, no framework files, no census-relevant surface touched.
Over the FW-019 300-line threshold on line count alone → this artifact.

## Reviewer basis

The contract is rev 1 of a four-lens adversarial plan-attack (architecture +
adversarial-correctness lenses on Fable 5; operations + governance lenses on
Opus 4.8) over the rev-0 draft: **3 blockers / 19 majors / 8 minors — every
finding adjudicated** in contract §14 with byte-grounded dispositions
re-verified against master `754998f8`. Highlights: the consequence-evidence
seam rebuilt around served-claim-bytes evaluation (zero fidelity imports;
dissolves the transitive-authority-import blocker), typed `expected_effect`
(makes `falsified` computable), an ordered TOTAL transition function, OVI
demoted to a per-instrument view (no composite), counterfactuals namespaced
with serve-REFUSE, census allowance rows made explicit, rollback gains
allowance-removal + retain-append-only blocks.

**Captain premise-check-of-record (2026-07-22): COMPLETE.** Both surfaced forks
resolved and recorded in the contract's closing section: (1) OVI end-state =
SUNSET (named program-end milestone; no permanent scalar). (2) "tested"
promotion fuel = human verdict only — the Captain's or any other person's,
incl. via internal/external comms; never a machine/LLM; any future
machine-widening is a fresh contract amendment + adversarial pass. The
`verdict_human = any human` prose amendment is applied at §5.2/§6.4.

## Ledger reconciliation (candor)

The COG-3 row's original `gate_cmd` named a "Captain-veto" simulation. The
attack (finding C-M5) proved that sim vacuous this phase — no veto input exists
anywhere in the shadow build's input set — so the contract (§6.7) excises it
and records veto-awareness as a NAMED obligation on the future
read-pointer-flip amendment. The `gate_cmd` + plan row are reconciled to the
adjudicated sim set (root-integrity retained), with the supersession recorded
in the row note — never silently dropped.

## Verification

- A13 id-parity gate green before and after the row flip (same commit).
- Docs-only diff: `git diff --stat` shows exactly the three tracked files +
  this artifact; no framework/census surface in the diff.
- Status flip + `last_update` in the SAME commit per ledger law; row not
  deleted, note supersedes.

Provenance: per the 2026-07-07 full-autonomy grant + the Captain 2026-07-20
cognitive-masterplan grant + the 2026-07-22 premise-check-of-record.
