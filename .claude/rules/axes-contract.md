# Axes Contract Rule (axes are data, never branches)

The cabinet is configured along three orthogonal axes — `autonomy_level`
(`earn_up` | `guardian` | `sovereign`), `flavor` (`personal` | `org`) and
`deployment_target` (`macbook` | `mac_mini` | `docker`). They are DATA,
consumed through the sanctioned resolvers, tables, and backends (spec of
record: `docs/plans/cabinet-axes-spec-2026-07-05.md` §6). This rule is the
contract in prose for every officer, loop, foundation developer, and captain
extension; the machine half is the axis linter + allowlist +
validate-extension gate named below.

The pre-tool-use hook treats this file as **germline** (read-only for
officers and loops): propose changes to the Captain; only the Captain
applies them in an unlock window.

## 1. Axes are data — never write an axis branch

- Never write `if posture == "sovereign"`, `flavor in ("personal", ...)`, a
  `deployment_target` comparison, or any equivalent branch on an axis value.
  Behavior differences live in TABLES (`framework/policies/
  authority-matrix.yml` posture tables) and pluggable BACKENDS (attestation,
  schedulers, channel/source adapters), selected by the ONE resolver chain:
  `framework/authority/posture.py` → the matrix → the gate.
- The ONLY sanctioned branching surface is enumerated in
  `framework/policies/axes-allowlist.yml` (Ring-0, dir-covered by
  immutable-core). CI enforces it: `framework/tests/test_axes_contract.py`
  AST-walks `framework/` and goes red on any axis comparison outside the
  allowlist. **Widening the allowlist is a Captain germline amendment**,
  never an officer edit — and a corrupt allowlist loads EMPTY (maximum
  strictness), never best-effort.
- One sentence per axis: *level* selects a verdict table over the ONE
  authority matrix; *flavor* selects evidence supply and optimization
  target; *target* selects backends. Flavor and target NEVER change verdict
  resolution — the 18-combo invariant suite
  (`framework/tests/test_axes_invariants.py`) proves all 3×2×3 combos per
  commit.

## 2. Extensions receive resolved values — they never read axis config

- An extension (channel adapter, source adapter, skill, MCP) is handed the
  RESOLVED axis values by its loader. It never reads `posture.yml`, the
  matrix, grants, the ladder, or any other axis config itself.
- Every extension ships a manifest (`manifest.yml|.yaml|.json` at its root;
  schema `framework/schemas/extension-manifest.schema.json`: name, version,
  kind, action_types, risk_classes, undo_contract, axis_compat,
  entrypoints) and must pass
  `bash cabinet/scripts/validate-extension.sh <extension-dir>` — manifest
  schema + entrypoint realpath containment (traversal/symlink escapes
  refused) + the axis linter over the extension's files with an EMPTY
  allowlist. The extend-cabinet skill routes every captain through it;
  loaders skip manifest-invalid extensions fail-closed and file a need.
- An adapter with `undo_contract: none` can never make its action_types
  act-first-eligible, in any posture (the inverse-required rule).

## 3. Upgrade is an attested ritual; downgrade is always allowed

- WIDENING (anything → `sovereign`) happens ONLY through the Captain's
  attested ritual: unlock `instance/config/posture.yml`, edit, re-lock. The
  resolver honors sovereign only from a locked, deployment-matched ruling.
  No officer, dashboard tile, chat verb, or env var may widen — a "go
  sovereign" button is a forge vector and is structurally refused.
  Dashboards may RENDER posture and OFFER the downgrade; for upgrade they
  print the ritual.
- NARROWING (→ `guardian` or `earn_up`) is always allowed, from anywhere,
  instantly: `CABINET_POSTURE=guardian|earn_up`, the
  `instance/config/posture-narrow` file (the Captain's binder verb writes
  it), or an `earn_up` ruling honored even unattested. Narrowing is
  fail-safe by construction and needs no attestation.
- FAIL-CLOSED default: absent, corrupt, unattested, unknown, or
  deployment-mismatched axis config resolves `guardian` — every ambiguity
  narrows, never widens. Grant rows in a `never_grant` class are dropped at
  load and file ONE decision need per class.

## Scope

Universal: every officer, every loop, every preset, every deployment target,
and every captain extension. Golden eval
`memory/golden-evals/eval-020-axes-contract.md` pins the linter, the
allowlist, and their Ring-0 coverage; a violation is CI-red, not a review
note.
