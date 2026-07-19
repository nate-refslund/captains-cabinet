# Cognitive Core / Foundry — Phase 0 (COG-0) fresh-context candidate review

Verdict: PASS

Reviewed-Scope-Digest: f543dc1e271dc590ade8b9dd98dfaa7421c1d46132154646454400dae2ebafd3
Reviewed-Commit: df251cad9fc18505a8a012e0090ab0c35b8c9e23 (advisory provenance only; the machine-verified binding is the scope digest above, recomputed over HEAD by cognitive-phase0-review-scope.py)

Lead synthesis of four independent cluster reviews (A: census/failure-domains;
B: trajectory anti-Goodhart/holdout; C: gates/binding/export/rollback; D:
agnosticism/docs/ledger/parity), each re-derived from the bytes at the frozen
commit. Zero P0/P1 across all clusters and the lead pass. All residuals are P3
(by-design ratchet, inherent-and-closed schema semantics, or landing-time CI
procedure). Ship.

## Scope-digest binding

The digest above was independently reproduced with
`python3.12 cabinet/scripts/cognitive-phase0-review-scope.py --print` at HEAD.
It is a SHA-256 over the mode+blob-sha of 20 committed Phase-0 paths from
`git ls-tree HEAD` (cognitive-phase0-review-scope.py:81-103). Teeth verified in an
isolated detached worktree: appending one line to a bound path
(framework/evolution/contracts.py) moved the digest to f02fb5d9…; a stale-digest
artifact fails `--verify` with exit 1 ("reviewed bytes != tested bytes",
cognitive-phase0-review-scope.py:124-129).

OPERATIVE-LEDGER EXCLUSION BOUNDARY (by design): the digest scope
(cognitive-phase0-review-scope.py:25-46) EXCLUDES the two operative ledgers
(docs/plans/operative-egg-ledger-2026-07-07.yml, docs/plans/operative-egg-plan-2026-07-07.md)
and this review artifact. I confirmed live that committing a change to ONLY the
operative ledger left the digest unchanged (f02fb5d9… → f02fb5d9…). Consequence:
the later COG-0=`done` flip, which edits only the two ledgers, CANNOT break this
binding — that edit is guarded solely by the independent ledger gates
(ledger-status-parity.sh + the A13 id-uniqueness/parity assertion in
verify-cognitive-phase0.sh:40-50), not by the scope digest.

## Findings — the 12 handoff questions (all PASS)

1. No competing Gate/evidence-schema/event-registry/effect-algebra/promotion path.
   contract.yml:59 `promotion: existing_gate_only`; masterplan foundry.md:48 "The
   Foundry has no alternate promotion path", :122/:192/:198 winners go to the
   existing Gate, "no live promotion"; contracts.py has no store write/rank/promote;
   forbidden-field grep (promot|fitness|eligib|graduat|champion|arena|league|mutat)
   empty in the trajectory schema.
2. Logical membrane preserves independent physical failure domains. contracts.py
   imports stdlib only (contracts.py:9-18; grep for non-stdlib import = none);
   enforcement facts arrive as inert data; contract.yml:60-61 declares
   `independent_physical_safety_enforcers`; no hook/schg/Seatbelt/broker/evidence
   file merged.
3. Truly additive & import-inert. name-status = 20 adds + 3 additive edits
   (egg-export-manifest.txt, null-hatch.sh, test_egg_export.py); framework/events,
   framework/authority, cabinet/services.yml NOT touched (grep of diff = none);
   full germline file set ∩ diff = ∅; null-hatch.sh:148 imports
   framework.evolution.contracts and boots green.
4. Framework production census baseline holds. census --check PASS at HEAD;
   framework_production_modules 208≤208 and noncomment_lines 61323≤61323 consume
   exactly the recorded COG-0 allowance (+2/+1256, contract.yml:39-53); census
   excludes tests/__pycache__ (census.py) so the counted +2 modules are
   contracts.py + __init__.py.
5. Trajectory is observation-only. cognitive-trajectory.schema.json top-level
   `additionalProperties:false` with 20 fixed keys, none of
   promotion/eligibility/fitness/graduation/holdout-case; every nested $def also
   closed; contracts.py:164-165 enforces; contract doc line 80 "The trajectory is
   observation-only … no promotion, eligibility, fitness, graduation-credit, or
   holdout-case field".
6. Stable authority_scope ancestry + transient execution binding correct.
   authority_scope_applies contracts.py:555-569 (cabinet→same-cabinet; lane→lane/
   project + same lane; project→project + same lane+project); sibling/cross-cabinet/
   descendant→ancestor FAIL; sentinels rejected (contracts.py:544-551, 386-389);
   execution_scope run/correlation/causation transient (schema executionScope);
   Captain root survives a new run (test_contracts.py:1134-1159).
7. No holdout content leak; aggregate-only receipt. trajectory schema has NO holdout
   field (join is the existing Gate's, external to Phase 0); holdout receipt values
   are BOOLEAN only, keys pinned + must equal the trusted suite registry
   (contracts.py:302-306), maxProperties 32, additionalProperties:false; missing
   context → fail-closed (contracts.py:299-300).
8. Never-a-score. No selection/promotion code exists (framework/evolution/__init__.py:1-5
   "exposes no arena, league, mutation, or promotion API"); the only judgment scalar
   is per-span confidence_ppm, consumed by nothing; the scope digest is a review-to-
   bytes binder over source, never officer-visible or a candidate input.
9. Census meaningful-growth mutants fail; shrink stays green. census --json shows
   every budget at zero slack (observed==maximum for all 10); the mutant suite
   (test_cognitive_architecture_census.py) forces 92nd event / 31st action / extra
   service / module+line growth / dynamic-enum evasion / expired allowance to FAIL
   and a legitimate shrink to PASS; 29 passed live.
10. Review-binding teeth (reproduced — see Scope-digest binding above): digest
    confirmed f543dc1e…, changes on a bound-path edit, unchanged on an excluded-
    ledger edit, blocks on a stale digest; fail-closed on scope drift both
    directions, dirty tree (verify-cognitive-phase0.sh:14), non-git tree, and
    non-blob (cognitive-phase0-review-scope.py:58-101).
11. Export gitless + Linux-portable; private tools excluded; rollback append-only +
    A13; gate honest. egg-export-manifest.txt:120-123 delete + :434-437 expect-absent
    for review-scope/rollback-rehearsal/verify-cognitive-phase0/test_rollback; census/
    contracts are pure stdlib (portable); rollback-rehearsal PASS ("only append-only
    operative history remains") with the A13 assertion run byte-identical inside the
    inverse tree (verify-cognitive-phase0.sh:40-50 ↔ rollback-rehearsal.py:38-47);
    verify-cognitive-phase0.sh:54 ends READY_FOR_CI, never a CI-green claim.
12. Agnostic + docs-track-code + ledger/A13 + holistic. No product/person/home-path
    token in added framework/census/contract lines (grep = none); contract doc §3.2
    authority_scope/execution_scope split matches contracts.py + schema; contract doc
    :207 "three one-time Phase-0 gate scripts" matches the 3 deleted; ledger COG-0
    `in-flight`, COG-1..COG-8 `todo`, 349 rows / 0 dup ids, plan↔ledger id parity
    exact; implementation covers the masterplan §6 deliverables and the contract §7
    exit-evidence list.

## Commands run (lead pass, at HEAD df251cad, macOS/python3.12)

- `git status --porcelain` → clean; `git rev-parse HEAD` → df251cad…
- `cognitive-phase0-review-scope.py --print` →
  f543dc1e271dc590ade8b9dd98dfaa7421c1d46132154646454400dae2ebafd3
- worktree teeth: bound-path edit → f02fb5d921c41c47498f8a40da85c2f4e77aa430a852510efb9e9d9962fcc39c;
  excluded-ledger-only edit → digest unchanged (f02fb5d9…)
- stale-digest `--verify` → BLOCK, exit 1, recompute over HEAD = f543dc1e…
- `cognitive-architecture-census.py --check` → PASS (all 10 budgets observed==maximum)
- pytest test_cognitive_architecture_census.py → 29 passed; test_cognitive_phase0_rollback.py
  → 5 passed; framework/evolution/tests/test_contracts.py → 47 passed
- diff greps: framework events/authority/services + germline ∩ diff = ∅; framework
  agnosticism grep = none; trajectory-schema forbidden-field grep = none
- worktree removed; frozen HEAD intact, tree clean

## Advisory (non-blocking, carry to landing / later phases)

- Linux CI job was not executed in this macOS review; code is pure stdlib+yaml+pytest
  with no platform branches. The gate's READY_FOR_CI protocol already mandates
  confirming every branch CI job green per-job (incl. Linux) BEFORE COG-0 flips to
  done — honor it.
- Census has zero framework-production headroom by design; any parallel framework
  wave before COG-7 must offset an equal line or add a dated allowance or it reds the
  census (now in null-hatch + CI).
- Structural id/digest patterns use re.search over `^…$`, so a single trailing
  newline passes structurally (inherent JSON-Schema semantics; the stdlib interpreter
  agrees with the reference engine). It leaks no holdout content and cannot
  manufacture eligibility (every id/digest is re-bound by exact equality
  contracts.py:422 / _parse_utc fullmatch :345). Optional hardening (re.fullmatch)
  for a later phase.

— Lead reviewer (run on Opus 4.8 1M per the Captain-authorized Fable-exhausted exception, 2026-07-19), synthesizing clusters A/B/C/D; every verdict
independently re-derived from the frozen bytes.