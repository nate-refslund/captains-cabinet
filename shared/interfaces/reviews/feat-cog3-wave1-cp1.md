# Checkpoint review — feat/cog3-wave1, cp1 (COG-3 wave 1: step-0 gates + D1 precursor)

**Scope:** 7 commits off `origin/master` `b2890f19` — U0 (contract §12.2 step 0:
the constitutional gates that land BEFORE any COG-3 implementation code; 5
commits incl. one review-fix) + U1 (contract §6.1 D1: the consequence
`cabinet_id` stamp; 1 commit) + 1 integration commit (census allowance row +
this artifact). ~1800 net lines → FW-019. Also covers U0's own >300-line
commit (`u0:` gate+tests, 566 lines) per its builder's self-flag.

## Build + review basis (the COG-2 pattern)

Both units built tests-first by isolated Opus 4.8 agents in their own clones
(incremental commits, mutant-bite discipline), each unit then adversarially
reviewed by a fresh-context Fable 5 agent that re-ran gates and re-bit mutants
itself.

- **U1 verdict: SHIP.** D1 cases (i)-(iv) green: stamped consequence subject
  servable in local scope with the FULL row as `.value`; foreign scope still
  `ScopeError`s; unstamped-proto mutant reproduces the pre-D1 hard-ScopeError;
  the existing `read_ledger` chain-head equivalence test unchanged. Honest
  epoch bump (`ENGINE_VERSION` cortex-engine/1→/2, belief identities stable);
  `belief.v1.json` byte-untouched; no landed test pins a literal store hash
  (re-verified).
- **U0 verdict: FIX_FIRST → fixed → re-verified.** The reviewer PROVED LIVE a
  reverse-direction dynamic-import escape: a `framework/objectives/` file with
  a literal `importlib.import_module("framework.authority.classifier")` passed
  every gate (the forward direction already treats literal dynamic-import
  strings as reachable, so this sat outside the accepted C-F20 residual by the
  gate's own standard). Fix commit adds the mirrored `_DYNAMIC_ACTION` check to
  Check R (`FORBIDDEN_OBJECTIVES_IMPORTS_ACTION`), with the exact-escape
  mutant, an `__import__` variant, and a comment-safety control. The
  integrator re-ran the reviewer's exact probe on the integrated tree:
  `sneaky.py` → gate RED with that rule id; restore → rc=0. A second nit was
  closed in the same fix: lambda-assignment scalar evasion
  (`total_value = lambda: …`) now trips the P12 ratchet (`SCALAR_ACCESSOR`);
  the honest G-m4 limitation note (dynamic construction evades AST scans —
  evasion IS the violation) is retained.

## What the gates now enforce (all mutant-bitten, 127+1-skip cog3 tests)

Both-directions module gate (static + dynamic + token, forward and reverse) ·
symbol-level AST import pin (stdlib | objectives | the 7 enumerated cortex
query-surface symbols; `load_beliefs` and engine/adapters/fidelity/ovi RED) ·
transitive-closure subprocess test (fidelity-import mutant REDs via
`consequence.py:33`'s authority load) · defaults-only `as_of` whitelist
{beliefs, subject_key, scope, observation} · P12 no-scalar ratchet incl.
ovi-composite + numeric-weight + lambda-assign forms · SWEEP_TREES-wide
data-plane sweep (missions `open()` mutant REDs) · census compiler wall
(scratch-copy RED-then-GREEN proof) · §7.4 read-pointer tripwire. The one
skip is the explicit vacuity marker: the transitive-closure test skips while
`framework.objectives` does not exist, with the scratch-package mutant proving
the bite.

## Ratified judgment calls (orchestrator, on record)

`as_of` pin is a whitelist (the contract's "five mutant-seam kwargs" is a
miscount — the signature has six fold-control kwargs; the whitelist covers all
six plus dimension/source) · `cog3-ovi-parity.py` deliberately NOT in the gate
allowlist (C-F17 falsifier ban enforced by exclusion until the parity wave
ships its dedicated internals-ban rule) · third-party imports (incl. `yaml`)
RED inside `framework/objectives/` — the roots-YAML parsing question routes to
the CLI at the adapters wave (design note tracked, decided consciously then).

## Verification on the integrated tree (`python3.12`, PG17)

- Battery: **445 passed / 4 skipped / 1 failed** — the failure is the KNOWN
  PRE-EXISTING `test_cognitive_phase2_rollback.py::test_manifest_covers_committed_cog2_footprint`,
  which fails on PRISTINE `b2890f19` full clones (verified independently by
  the U1 reviewer): the phase-2 ratchet's open-ended BASELINE..HEAD range
  flags every later-phase addition (the contract-docs commit tripped it first;
  this wave's cog3 files extend the trigger set). CI shallow-skips it (master
  CI green). Backlogged systemic fix (same class as the phase-1 `.mcp.json`
  instance); NOT fixed here by the same no-scope-creep precedent the COG-2 PR
  set. The COG-3 §12.4 rollback manifest (wave-2 deliverable) must name
  `framework/cortex/belief.py` alongside `adapters.py` (U1 reviewer nit,
  tracked).
- Census `--check` PASS with the COG-3 allowance row: noncomment-lines
  63493==63493 EXACT (+7 measured, the D1 delta), modules 214==214,
  named_compiler 1==1 — the zero-headroom observed==max law holds.
- `cog2-import-gate.py` rc=0 on the real tree; `test_cog2_import_gate.py` 58
  passed (byte-compat).
- `services.yml` untouched; no `framework/objectives/` production files exist
  yet (step-0 law); read pointer absent.

Provenance: per the 2026-07-07 full-autonomy grant + the Captain 2026-07-20
cognitive-masterplan grant; contract `docs/plans/cognitive-core-phase-3-contract-2026-07-22.md`
(CAPTAIN-APPROVED, premise-check-of-record 2026-07-22).
