# COG-4 W4 u1 — organ SCHEMA VALIDATION parked (germline window unopened) — 2026-07-24

**Status:** PARKED with this dated marker per contract §4.5 build sequencing
(`docs/plans/cognitive-core-phase-4-contract-2026-07-23.md`) — schg is NEVER
worked around; a recorded handback beats a workaround.

## What is parked

Everything that requires the CG-33 germline amendment to be APPLIED to the
extension gate pair (`framework/schemas/extension-manifest.schema.json` +
`cabinet/scripts/validate-extension.sh` — both schg-locked,
`germline-lock.sh` FILES[] :128-129):

1. **Schema-validated organ manifests** — running any organ manifest through
   the REAL `validate-extension.sh` (both validator paths, proposal §4 gates
   A/B) and claiming §4.2 schema validity anywhere. The landed
   `framework/organs/registry.py` therefore performs STRUCTURAL reads with
   honest errors ONLY and its docstring disclaims schema validation by name.
2. **The validate-extension.sh ORGAN BLOCK verification unit** — asserting
   the .sh's required-when-organ tuple equals the thirteen-field
   `ORGAN_REQUIRED` set and that the germline kind enum carries `organ`
   (proposal §1b; the W2 corpus vacuity arm
   `test_cog4_organ_manifest.py::TestRealSurfacesVacuityArms::test_real_germline_validator_arm`
   stays SKIPPED on its own companion assertions until the window lands).
3. **AX-suite organ-block extension over the REAL schema** (§4.3 N-d
   matrix-consistency + the `test_axes_contract.py` risk-class enum drift-pin
   extension over every occurrence in the EXTENDED schema) — these bind to
   the post-amendment schema bytes and land with (or after) the windowed
   micro-unit.

## Why

The Captain unlock window for the extension gate pair is **UNOPENED** at W4
landing time. The amendment is fully FILED and awaiting Captain action at
convenience: proposal doc
`docs/proposals/germline-amendment-extension-manifest-organ-2026-07-23.md`
(the complete §1a/§1b edit text — the read-only spec this unit built
against), captain-gated ledger row **CG-33**
(`docs/plans/operative-egg-ledger-2026-07-07.yml`), and the NAMED Captain
sudo-unlock handback — **HANDBACKS item 19** (`~/cabinet-meta` HANDBACKS
file). Reply "apply organ-packaging" authorizes the window (proposal header).

## What proceeded anyway (built AGAINST the proposal text, per §4.5)

- `framework/organs/{__init__,registry,descriptor}.py` — structural registry
  (directory parameter CLI-injected; content-addressed registry hash = the
  honest epoch bump) + the §5.2 ONE-descriptor resolution from
  manifest-DECLARED values (MF-A1: no action-plane import; operation names
  carry zero authority).
- `cabinet/scripts/tests/test_cog4_organs_package.py` — the W4 u1 battery;
  its fixtures are §4.2-shaped per the PROPOSAL text and pass the W2 corpus
  reference validator + N-d consistency at test time.
- The N-b suite-level `state_ownership` disjointness sweep
  (`registry.state_ownership_collisions`) — cross-manifest by necessity,
  validator-independent, live now.

## Retirement condition

When the Captain window lands the CG-33 edit (schema `kind` enum gains
`organ` + the fourteen fields + the undo-grammar superset; the .sh gains the
integer branch + ORGAN BLOCK; same-day relock; §4 battery green):

1. The W2 corpus vacuity arm retires per its own in-file RETIREMENT
   CONDITION (its companion assertions RED the moment the amendment lands —
   integrator corpus surgery per §13).
2. A follow-up unit binds organ-manifest validation to the REAL
   validate-extension.sh on both paths and lands the AX organ-block checks
   (item 3 above); the registry KEEPS its structural-read posture (validation
   stays gate/AX-side — the registry never becomes a second validator).
3. This marker is superseded in place with a dated note (never deleted).

## Rollback note

If the window is instead declined or rolled back (proposal §3 one-revert),
NOTHING here needs reverting: no landed W4 u1 surface reads the germline
pair; the package binds to the proposal text only through its fixtures and
docstrings, exactly as §4.5 prescribes for a never-opened window.

**Provenance:** authored per the 2026-07-07 full-autonomy grant + the
Captain 2026-07-20 cognitive-masterplan continuous grant; COG-4 W4 u1
(Fable-for-execution named unit).
