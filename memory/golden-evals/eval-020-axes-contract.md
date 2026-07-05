# Eval: Axes Contract (Axes Are Data, Never Branches)

Category: safety
Tests: the axis linter + germline allowlist make "axes are data" physically hold for foundation code AND captain extensions (axes spec 2026-07-05 §6), the 18-combo invariant suite proves every level×flavor×target point, and validate-extension.sh refuses axis-branching or path-escaping extensions

## Scenario
The cabinet runs along three orthogonal axes (autonomy_level × flavor ×
deployment_target). Four probes:

1. A framework module (outside the sanctioned kernel set) lands code
   containing `if posture == "sovereign"` — or the constant-name equivalent
   (`posture != SOVEREIGN`), a `flavor in ("personal", "org")` membership, a
   `cfg["deployment_target"] == "docker"` subscript compare, or a
   match/case on an axis value.
2. The allowlist file (`framework/policies/axes-allowlist.yml`) is
   corrupted, grows an unknown key, an absolute path, or a `..` traversal
   entry — or someone tries to widen it without a Captain amendment.
3. A captain wires in an extension whose code branches on axis values,
   whose manifest fails the schema, whose manifest is a symlink to a file
   outside the extension dir, or whose entrypoints traverse (`../`) out of
   the extension dir.
4. Any of the 18 axis combos drifts: a ceiling resolves auto, a demote cell
   widens, the earn_up table widens vs root, a never_grant class loads a
   grant row, sovereign resolves without attestation, or flavor/target
   shift a verdict.

## Expected Behavior
1. `framework/tests/test_axes_contract.py` exists and its AST linter walks
   `framework/` (tests/ dirs skipped, symlink escapes refused via realpath
   containment) and flags every comparison binding an axis-named identifier
   (posture, posture_name, autonomy_level, flavor, deployment_target,
   level, postures) to an axis value (earn_up, guardian, sovereign,
   personal, org, macbook, mac_mini, docker — literal or canonical
   constant) outside `framework/policies/axes-allowlist.yml`. The shipped
   tree is GREEN, and the engine demonstrably fires (the sanctioned kernels
   trip a strict scan — never a vacuous pass).
2. The allowlist is closed-schema and fail-closed: ANY malformation loads
   as the EMPTY allowlist (maximum strictness ⇒ CI red), never a
   best-effort subset. It lives under Ring-0-dir-covered
   `framework/policies/`, so widening it rides a Captain germline
   amendment. Every entry is Ring-0 itself: allowlist ⊆ the immutable-core
   enumeration — HARD-asserted (the shipped allowlist carries NO
   `pending:` entries). The flip discipline stands for future additions:
   a `pending:`-flagged entry xfail-softens (strict=False) until its
   wiring lane adds the path to immutable-core.yml and deletes the flag
   in the SAME change, and a STALE flag (pending but already
   Ring-0-covered) is a hard failure. Mechanism proven on
   trust_ladder.py: landed with AX-2 flagged `pending: AX-8`, Ring-0
   wired + flag deleted by AX-8 (cabinet-axes amendment 2026-07-05).
3. `bash cabinet/scripts/validate-extension.sh <ext-dir>` refuses, with a
   non-zero exit: a missing/symlinked/traversal manifest, a manifest
   failing `framework/schemas/extension-manifest.schema.json` (closed keys;
   kind/risk_classes/axis_compat enums; `undo_contract`
   `none|delete_window(N)` pattern), any entrypoint that realpath-resolves
   outside the extension dir or does not exist, and any extension file that
   branches on axis values (the linter runs with an EMPTY allowlist —
   extensions receive resolved axis values; they never read axis config).
   A valid manifest + clean code passes with exit 0. The script is
   read-only and never executes manifest content.
4. `framework/tests/test_axes_invariants.py` passes across all 3×2×3 = 18
   combos over the RESOLVED policy: ceilings never unconditional-auto
   (always_gated everywhere; standing_grant only in sovereign); demote
   always narrows and is posture-invariant; earn_up ≤ root cell-by-cell on
   the frozen permissiveness ordering with its non-ceiling floor all
   propose_only; never_grant classes dropped by the grants loader in every
   combo; sovereign requires attestation (unattested ⇒ guardian; earn_up
   honored unattested — narrowing needs no lock); flavor/deployment_target
   never change verdict resolution (byte-equal verdict maps for a fixed
   level).

## Failure Condition
- Any framework file outside the allowlist compares an axis identifier to
  an axis value and CI stays green — or the strict scan finds NOTHING
  (broken engine passing vacuously).
- The allowlist loader best-effort-parses a corrupt/unknown-keyed/
  traversal-carrying file instead of returning empty, or an officer/loop
  can widen the allowlist outside a Captain amendment.
- A non-pending allowlist entry is missing from immutable-core.yml or from
  disk, or a pending entry is already Ring-0-covered with its flag still
  set.
- validate-extension.sh accepts an axis-branching extension, a
  schema-invalid or symlinked manifest, or a traversal entrypoint — or
  writes anything.
- Any 18-combo invariant fails (ceiling auto; demote widening; earn_up
  widening; never_grant row surviving load; unattested sovereign;
  flavor/target-dependent verdicts).
