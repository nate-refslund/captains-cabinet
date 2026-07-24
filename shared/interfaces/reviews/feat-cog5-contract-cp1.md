# FW-019 review artifact — feat/cog5-contract cp1 (2026-07-24)

## What lands in this batch

1. **`docs/plans/cognitive-core-phase-5-contract-2026-07-24.md`** — the
   COG-5 phase contract of record (rev 1, 347 lines), copied BYTE-FOR-BYTE
   from the reviewed artifact (sha256
   `bf27c2d7400746ea556f154e3a000317798acb2c818cae719d502ca5b0a5f1cd`;
   `diff` empty against the source). Foundry E1/E2/E3 in shadow: honest
   Gate arming, immutable trajectory archive, arenas, benchmarks, league,
   frozen holdout oracle. Everything in shadow — no live promotion, league
   CLOSED for live-fitness claims, gate-apply stays dark.
2. **`docs/proposals/germline-amendment-immutable-core-holdout-2026-07-24.md`**
   — the MR1 holdout-freeze Captain-window proposal (CG-34): EXACTLY ONE
   `files`-class listing `framework/evolution/holdout_gen.py` +
   `pending: [germline-lock, hook-s5, hook-s5b, base-safety]` added to
   `framework/policies/immutable-core.yml` (germline by
   `framework/policies` DIR-cover — germline-lock.sh DIRS :145; the file's
   own EDIT DISCIPLINE header). Complete proposed edit text + Stage A/B
   semantics + one-revert rollback (itself Captain-windowed) + §7
   verification battery + window procedure. NOTHING APPLIED — proposal
   only. (The contract's §7.5.1/§14.1 reference this document by its
   drafting title `germline-amendment-holdout-ring0-2026-07-24.md`; the
   landed filename is the doc of record and the proposal says so.)
3. **`docs/plans/operative-egg-ledger-2026-07-07.yml`** — COG-5 row
   `todo → in-flight`, `last_update: 2026-07-24`, note gains the
   contract-of-record sentence; NEW row **CG-34** (captain-gated, germ-keep,
   modeled field-for-field on CG-33) carrying the window ceremony gate_cmd
   (batchable with CG-33), the proposal-doc reference, and the PARK
   fallback.
4. **`docs/plans/operative-egg-plan-2026-07-07.md`** — §9 COG-5 twin
   flipped to in-flight with the contract ref + CG-34 handback note (the
   COG-4 twin convention); NEW `| CG-34 |` table row after CG-33 (A13
   parity).

## Review chain of record (do NOT re-litigate here)

- **Premise-check** workflow `wf_fc493c16-a6a`: 8 ground readers +
  synthesis verdict **READY-TO-PLAN** (6 concerns, 14 plan_seeds) +
  adversarial attack **self-corrected UPHOLD** (its `final` field misfired
  as FLIP; its own notes rule "treat this output's final as UPHOLD") with
  **4 serious refutations** (+3 minor) — each landed as a MUST-RESOLVE
  (MR1 germline window for the holdout listing; MR2 promote.py = COG-6;
  MR3 E1/E2/E3 are RUNS; MR4 disposition table) — contract §19 register.
- **Four-lens plan-attack panel** over rev 0 (architecture,
  adversarial-correctness on Fable; operations, governance on Opus):
  **1 MF + 10 SF + notes, ALL ACCEPTED** by orchestrator adjudication and
  applied in place; dispositions of record in the contract's rev-1
  appendix; every byte-claim re-verified against the ground clone at tip
  `70bca2ae` before being written.
- **rev-1** editor pass (Fable 5, judgment tier): added gates only
  (declared regression bound §12.1, provenance/laundering arm §6.2,
  flat-candidate honest-negative arm §4.5, ROW-6 non-extension §10),
  weakened none.
- **Independent MF-verify**: verdict **LAND** (all five MF/SF resolutions
  present + wired + byte-supported at `70bca2ae`; 3/3 appendix spot-checks
  true); its three minor findings fixed in the orchestrator landing pass
  (F-1 cite re-anchor, F-2 ls-claim `__init__.py`, F-3 egg-manifest path)
  — zero obligation bytes changed.
- **Orchestrator landing pass** (2026-07-24): appendix updated with the
  landing-pass record; this landing agent copies bytes and flips ledger
  state only — content not re-litigated.

## Germline handback note (Captain-facing)

This landing FILES the phase's **second pending Captain window**: the CG-34
holdout listing, explicitly **BATCHABLE with the first** (CG-33
extension-gate window, HANDBACKS item 19) at the Captain's convenience —
one sudo window, the reviewed edits together, same-day relock. Nothing is
applied now; until a window opens, dependent COG-5 freeze-verification
units PARK with dated markers and the arming record carries
`holdout_freeze: pending-captain-window`. schg is never worked around.

## Gates run in this batch (worktree, pre-push)

- A13 parity gate_cmd GREEN (352 yml ids == 352 plan-doc rows, 1:1).
- `cabinet/scripts/ledger-status-parity.sh` → `LEDGER_STATUS GREEN
  (ids=352 md_rows=352 findings=0)`.
- Duplicate-id + row-shape check GREEN (CG-34 keys mirror CG-33
  field-for-field; COG-5 row carries exactly one `status:` key).
- `python3.12 -m pytest framework/tests/test_amendment_doc_lint.py -q` →
  16 passed (new proposal doc in the union; per-package table untouched).
- Contract copy byte-verified (empty diff + sha256 match).
- HEAD-bytes YAML parse via `git archive` re-run at commit time.

Provenance: per the 2026-07-07 full-autonomy grant + the Captain
2026-07-20 cognitive-masterplan grant; the germline window itself is
Captain-only, non-grantable. FW-019 artifact for a >300-line docs batch.
