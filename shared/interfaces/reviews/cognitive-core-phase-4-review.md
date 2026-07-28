# COG-4 §12.3/§15 FROZEN REVIEW — Composable Cognitive Organs + Deterministic Shadow Scheduler

**Scope:** the COG-4 surface at commit `f62094f7c6ee419db20df3d5445a89f5258467bb` (`feat/cog4-w6-e4`,
"COG-4 W6 e4: census done-flip tighten (§9.4/§11) — record final phase actuals, N7 machine-pinned",
over master `fc51fd59`; W1-W5 already on master, W6 e1-e4 = `6502f597`→`b4bc2c34`→`2ab7d607`→`2338d6c9`→tip):
`framework/projection/{__init__,kernel}.py`, `framework/scheduler/{__init__,model,snapshot,fold,serve}.py`,
`framework/organs/{__init__,registry,descriptor}.py`, `framework/schemas/cognitive-trajectory.v2.schema.json` +
the `framework/evolution/contracts.py` version dispatch, `framework/watchdog/registry.py` `_parse_organ_manifests`,
`cabinet/config/boundary-manifest.yml` + the converted engine `cabinet/scripts/cog2-import-gate.py`,
`cabinet/scripts/{cog4-snapshot,cog4-schedule,cog4-dispatch-shadow,cog4-parity,cog4-measure,cog4-organ-runner}.py`,
the W6-e2 compose (`cabinet/services.yml` + 5 organ manifests under `cabinet/config/organs/`), the phase twins
(`verify-cognitive-phase4.sh`, `cognitive-phase4-review-scope.py`, `cognitive-phase4-rollback-rehearsal.py`,
rollback manifest `docs/plans/cognitive-core-phase-4-rollback-manifest-2026-07-24.yml`), the `test_cog4_*`/`lib_cog4_*`
corpus, and the egg-export manifest extension.
**Reviewer:** frozen fresh-context Fable panel (clean-room clone off the canonical remote, zero prior-session
context; 2026-07-24). The F1 lesson bound this review: every public entry point of every new serve surface was
attacked with the panel's OWN tamper code, never only the suite's.
**Contract:** `docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` rev 1 (§15 standing questions answered
below, every one).
**Method:** every claim is bound to bytes (`file:line`) or a run executed by this panel (`python3.12`). No doc or
comment was trusted un-run. 74 independent panel probes + the full committed batteries; the clone worktree was
byte-clean (`git status --porcelain` empty) after every run.

Reviewed-Scope-Digest: 264478e38b6f99c1d18ef657df5206b8cd84ff54d0bb07673bbe00add6c3a52d

(MERGE RE-BIND, 2026-07-28, `fix/needs-anti-vacuity-and-depth-labels` x
`feat/connector-registry`: both sides re-bound this line and both moved
`cabinet/config/cognitive-architecture-contract.yml` — this branch a PROSE-ONLY
correction of the evidence-append-quadratic row's trial-depth labels (no budget,
no maximum, no additional, no row identity; census unmoved at 71931 <= 71931),
master a connector-registry allowance row. git auto-merged the file with no
contested byte. Neither recorded digest describes the merged tree, so the value
above is RECOMPUTED over it rather than picked from a parent, and every note
from both sides is kept below, none superseded. NO COG-4 implementation byte
moved on either side: `resolve_scope()` intersected with
`git diff --name-only origin/master...HEAD` over this branch yields exactly the
contract file, and the intersection with the manifest's DIR entries is empty.)

(MERGE RE-BIND, 2026-07-28, `feat/connector-registry` x `fix/evidence-append-quadratic`: both sides re-bound this line and both moved `cabinet/config/cognitive-architecture-contract.yml` — this branch a `temporary_allowances` row for the connector registry, master the evidence recorder's own budget note. git auto-merged the allowance list with no contested byte. Neither recorded digest describes the merged tree, so the value above is RECOMPUTED over it. Every note from both sides is kept below, none superseded. NO COG-4 implementation byte moved on either side: this branch's only digest-bound path is the contract file, verified by intersecting `resolve_scope()` with `git diff --name-only 6ec81460 HEAD`.)

(RE-BOUND AGAIN 2026-07-28 at the merge of `origin/master` 3126cfac into
`feat/connector-registry` — the connector-registry landing moved
`cabinet/config/cognitive-architecture-contract.yml`, its ONLY in-scope path
(one `temporary_allowances` row, +566 non-comment lines; no maximum raised, no
bijection class touched), and master had re-bound this line in the merge
described below, so neither recorded value survives. The value above is
RECOMPUTED over the merged tree. Verified by intersecting
`git diff --name-only 6ec81460 HEAD` with the tool's resolved scope: the
contract file is the only digest-bound path this branch touched, and NO COG-4
implementation byte moved — no organ, no scheduler surface, no serve surface,
no fixture, no boundary row. Nothing below was re-reviewed, because no reviewed
byte moved. The prior re-bind's own note follows verbatim.)

(RE-BOUND 2026-07-28, `fix/needs-anti-vacuity-and-depth-labels`, in the SAME
commit as the change that moved the bytes — the re-bind-at-landing procedure
this artifact prescribes. Prior digest: `d85d407f5047ea53…`. The moved file in
scope is the ONE budget surface again:
`cabinet/config/cognitive-architecture-contract.yml`, whose
`evidence-append-quadratic` row cited trial depths 40 and 499 for latency
figures the `filing_latency` fixture takes at depths 16 and 495 — a governance
record asserting a measurement the code does not take. PROSE ONLY: no `budget`,
no `maximum`, no `additional`, no `owner`, no `sunset` and no row identity
changed, and the census is byte-for-byte unmoved at 71931 <= 71931.
MECHANICALLY VERIFIED rather than asserted: `resolve_scope()` was intersected
with `git diff --name-only` over this landing for ALL FIVE phase scopes and this
file is the only digest-bound path any of them touches; the intersection with
the manifest's DIR entries is empty. The other two paths —
`framework/authority/tests/test_needs.py` (its latency fixture's fill loop
bounded, so the fixture's own anti-vacuity assert becomes reachable instead of
spinning forever) and one dated doc correction — are in no phase scope. No
organ, no scheduler surface, no serve surface, no COG-4 entry point. Neither
`cognitive-phase4-rollback-rehearsal.py` nor `verify-cognitive-phase4.sh` is
touched: the frozen battery is byte-identical, which is what keeps this re-bind
mechanical rather than a restamp of a review that never happened. The
rehearsal's compatibility battery runs in a worktree detached at the pinned
anchor `c58d4a57`, so the `test_needs.py` edit is not in the bytes it runs.)

(MERGE RE-BIND, 2026-07-28, `fix/evidence-append-quadratic` x `iso-port-composition`:
PR #223 landed on master while this branch sat green in CI, and BOTH sides had
re-bound this line — `5435fddb…` here, `eebcf40b…` on master. Neither describes
the merged tree, so the value above is RECOMPUTED over it rather than picked
from a parent; every note from both sides is kept below, none superseded. The
two sides' in-scope deltas are disjoint and were computed, not read off the
diff: intersecting `resolve_scope()` with `git diff --name-only HEAD
origin/master` and with this branch's own changed paths gives
`cabinet/config/cognitive-architecture-contract.yml` (this branch's allowance
row) and `cabinet/scripts/egg-export-manifest.txt` (master's iso-art export
rows) — different files, no contested byte, git auto-merged both. No COG-4
implementation byte moved on either side.)

(MERGE RE-BIND, 2026-07-28, `fix/evidence-append-quadratic`: origin/master's
`feat/onboarding-ordering-inversion` landing re-bound this same digest while this
branch was in flight. Two concurrent landings cannot both be right about one
number, so it is RECOMPUTED over the MERGED committed tree rather than either
side being picked — a hand-picked digest from either parent records a tree that
never existed. Both parents moved the SAME one scope file,
`cabinet/config/cognitive-architecture-contract.yml`, and their edits are
disjoint rows; both re-bind notes are kept below.)

(RE-BOUND 2026-07-28, `fix/evidence-append-quadratic`, the re-bind-at-landing
procedure this artifact prescribes. Prior digest: `deca1533428d8df8…`. The moved
file in scope is the ONE budget surface again:
`cabinet/config/cognitive-architecture-contract.yml` gains an
`evidence-append-quadratic` allowance row on
`framework_production_noncomment_lines` (+126, exact measured running total
71277 vs 71151) for a fix to `framework/evidence/verifier.py` and
`recorder.py` — the append path was O(n) in the trial and O(n^2) overall.
MECHANICALLY VERIFIED rather than asserted: `resolve_scope()` was intersected
with `git diff --cached --name-only` over this landing and the contract file is
the ONLY digest-bound path it touches; the intersection with the manifest's DIR
entries is empty too. The other seven paths are the evidence verifier and
recorder, their tests, `framework/authority/tests/test_needs.py`,
`cabinet/scripts/governance-review.py` (one renamed-helper doc reference) and
one dated doc correction — none in COG-4 scope. No organ, no scheduler surface,
no serve surface, no COG-4 entry point, no budget `maximum` and no `additional`
on any pre-existing row changed. `framework/authority/classifier.py` remains in
the manifest's `must_remain_unchanged` block against the pinned phase anchor,
which the rollback rehearsal re-checks. The rehearsal's nine-directory
compatibility battery runs in a worktree detached at the pinned anchor
`c58d4a57`, so the edit to `framework/authority/tests/test_needs.py` is not in
the bytes it runs; that same battery at HEAD, which
`verify-cognitive-phase4.sh` runs, is green. The phase-4 findings below are
unaffected.)
(RE-BOUND 2026-07-28 at the merge of `origin/master` dd01ce8f into
`iso-port-composition` — the merge that unblocked PR #223, which had been
CONFLICTING for days and was therefore running NO CI at all. Both sides of the
merge had re-bound this line, so neither recorded value can be carried: the
branch's `dbdf515c…` and master's `fa66d3d0…` are each a digest over a tree that
no longer exists. The value above is RECOMPUTED over the merged tree and folded
into the merge commit itself.

Exactly TWO in-scope paths differ across the merge, and the delta is disjoint by
side — computed, not read off the diff, by intersecting
`git diff --name-only HEAD origin/master` with the tool's resolved 85-entry
scope: `cabinet/config/cognitive-architecture-contract.yml` moved on MASTER only
(the branch never touched it — the two allowance/budget landings its own notes
below describe), and `cabinet/scripts/egg-export-manifest.txt` moved on the
BRANCH only (master never touched it — the `delete`/`expect-absent` rows that
keep the org's commissioned iso art out of the public export). Neither side
contested a byte of the other's, so git auto-merged both and no row of either was
dropped. NO COG-4 implementation byte changed on either side: no organ, no
scheduler surface, no serve surface, no fixture, no boundary row, and
`framework/authority/classifier.py` remains in the manifest's
`must_remain_unchanged` block against the pinned phase anchor. Only two files in
the whole merge were touched by BOTH sides — this artifact and
`.github/workflows/cabinet-ci.yml`, whose four added steps sit in four disjoint
regions and all four survive in the merged file. The phase-4 findings below are
unaffected, and nothing here was re-reviewed, because no reviewed byte moved.)

(RE-BOUND 2026-07-28 at the landing of `feat/onboarding-ordering-inversion`,
same commit as the change that moved the bytes. Prior digest:
`deca1533428d8df8…`. The one moved file in scope is again
`cabinet/config/cognitive-architecture-contract.yml`, and the move is: the
`framework_production_modules` budget maximum raised visibly 206 -> 207, the
duplicate temporary-allowance row for `framework/onboarding/estate.py` removed
(master's bijection-allowance-bypass landing refuses an allowance that names a
bijection class, and an expansion row for that member was already present), and
the `framework_production_noncomment_lines` allowance 646 -> 654 for eight lines
fixing two defects found in this unit by the landing review. No COG-4
implementation byte changed; `framework/authority/classifier.py` remains in the
manifest's `must_remain_unchanged` block against the pinned phase anchor. The
phase-4 findings below are unaffected.)

(RE-BOUND 2026-07-27, `fix/bijection-allowance-bypass`, same commit as the change
that moved the bytes — the re-bind-at-landing procedure this artifact prescribes.
Prior digest: `8bee10cdcd41994b…`. The one moved file in scope is
`cabinet/config/cognitive-architecture-contract.yml`, and the move is COMMENT
bytes plus one allowance `reason` string: the expansion-registry header now
states what the census actually enforces after an adversarial review falsified
its previous claim by execution. No budget maximum, no `additional`, no member
and no expansion row changed — verified by loading both revisions and comparing
the parsed budgets/allowances/expansions. NO COG-4 implementation byte changed;
`framework/authority/classifier.py` remains in the manifest's
`must_remain_unchanged` block against the pinned phase anchor, which the rollback
rehearsal re-checks. The phase-4 findings below are unaffected. Re-bound a
second time at the merge of `origin/master` b6a58b15, which had itself re-bound
to `e3675c7b4b1db4c2…` for the `onboarding-three-entry-modes` row; the digest
above is recomputed over the MERGED tree, since both sides moved the same one
scope file.)



(RE-BOUND repeatedly on 2026-07-27 — the census-shift-left, expansion-registry and
census-set-pins landings each edited `cabinet/config/cognitive-architecture-contract.yml`,
which sits in `restore_from_baseline` and is therefore digest-bound, and so did this
branch's `recipient-exclusion-carve-backs` allowance row, and again for the
`onboarding-three-entry-modes` allowance row (2026-07-27). NO COG-4 implementation byte
changed by any of them: every edit is a budget/allowance row, and
`framework/authority/classifier.py` remains in the manifest's `must_remain_unchanged`
block against the pinned phase anchor, which the rollback rehearsal re-checks. The
phase-4 findings below are unaffected.)
(RE-BOUND 2026-07-27, `fix/propose-means-propose`, same commit as the change that
moved the bytes — the re-bind-at-landing procedure this artifact already
prescribes. Prior digest: `b8ee235e0c34bd2a…`. The moved file in scope is
`framework/authority/policy_engine.py`: `_eval_authority_matrix` now returns a
`GateDecision` carrying a structured verdict kind instead of a bare `str`, so
`propose_only` and `always_gated` stop being operationally identical. The COG-4
findings are unaffected — the change adds no organ, no scheduler surface and no
serve surface, touches no COG-4 entry point, and is separately reviewed in
`fix-propose-means-propose-cp1.md` with six per-ceiling arms and a corpus
cross-check over 80,307 recorded calls. Exit codes and all guardian block
strings are byte-identical, which is what keeps this re-bind mechanical rather
than a re-review.)
(RE-BOUND 2026-07-27, `feat/onboarding-entry-modes`, same commit as the change
that moved the bytes. The moved file in scope is the ONE budget surface again:
`cabinet/config/cognitive-architecture-contract.yml` gains an
`onboarding-three-entry-modes` allowance row. MECHANICALLY VERIFIED rather than
asserted: `resolve_scope()` was intersected with `git diff --name-only` over that
landing and the contract file is the ONLY digest-bound path it touches — the rest
are the onboarding entry-mode surface, its tests, its vendored pre/post-migration
snapshot and the dashboard, none of them in COG-4 scope. No organ, no scheduler
surface, no serve surface, no COG-4 entry point. A re-bind that moved an
implementation byte would not be a mechanical delta and is not what this records.)
(MERGE RE-BIND, 2026-07-27, `feat/onboarding-entry-modes`: the propose/gate and
hook-redos landings each re-bound this same digest while this branch was in CI.
Two concurrent landings cannot both be right about one number, so it is
RECOMPUTED over the MERGED committed tree rather than either side being picked —
a hand-picked digest from either parent records a tree that never existed. The
digest line was the ONLY conflict in this artifact both times; every landing's
note above is preserved verbatim, none overwritten. In-scope paths carried in by
the merges: the census contract only. Census re-measured on the merged bytes:
PASS, observed==max with zero headroom.)
(MERGE RE-BIND #2, 2026-07-27, same branch: the source-ownership-class and
killswitch-test-fence landings re-bound this digest again while the branch was
in CI. Recomputed over the merged committed tree for the same reason — a
hand-picked digest from either parent records a tree that never existed. The
digest line was again the only conflict here; every note is preserved. In-scope
paths carried in by the merge: the census contract only. Census re-measured on
the merged bytes: PASS, observed==max with zero headroom.)
(MERGE RE-BIND #3, 2026-07-27, same branch: the personal-preset-live landing
re-bound this digest while the branch was in CI. Recomputed over the merged
committed tree, same reason and same mechanics as #1 and #2 — in-scope paths
carried in by the merge: the census contract only; census re-measured on the
merged bytes: PASS, observed==max with zero headroom. Three merge re-binds on
one branch is not drift, it is a hot shared surface: every concurrent landing
that pays line mass edits the same contract file, which is in this digest's
restore_from_baseline set.)
(As frozen, the panel bound the DECLARED W1-W5 scope: `cognitive-phase4-review-scope.py` EXPECTED_SCOPE
deliberately excluded the e2/e3 sibling surfaces (cog4-organ-runner.py, cog4-measure.py, organ manifests,
their out-of-band tests, the FW-019 sibling artifacts) pending the landing integrator's PAIRED extension of
the §16 rollback manifest + EXPECTED_SCOPE in the same commit — `resolve_scope()` fails closed on any
one-sided edit, and the digest is re-bound at landing per the phase-3 precedent. The e2/e3 surfaces
themselves WERE fully reviewed by this panel; only the mechanical digest scope awaited the pair-extension.)
(Re-bound at the W6 landing, 2026-07-24 — the cp3 precedent, a MECHANICAL-DELTA re-bind, not a restamp.
The panel's original digest was d6625b82fc969ce9958e3eebcb96b58c4c6483cf5e3f14fb6cce8908f086ac6e, binding
tip f62094f7. Four landing commits moved it: (1) 48028427 committed THIS artifact (excluded from the digest
but named in the manifest remove list); (2) 93b26f74 the §13 corpus surgery — the panel's OWN named
discharge of the 5 designed flip-arms, each retired-live per its retirement text, pre-proven green
out-of-band by the panel-reviewed test_cog4_measure_baseline.py + test_cog4_organ_runner_real.py; (3)
eefc9c11 the §16/EXPECTED_SCOPE pair-extension, which pulled the ALREADY-PANEL-REVIEWED e2/e3 surfaces into
the digest scope (+ the P5 egg tidy rows; the L61 draft-lane plist DELETION declared as
out_of_phase_in_range residue — a deleted-at-HEAD path cannot be digest-bound); (4) 5d1547c0 the wave
FW-019 batch proof + its own pair rows. Mechanical deltas only — ZERO behavior bytes changed beyond the
§13 corpus surgery itself. Re-verified on the final bytes: full battery armed 690 passed 1 declared skip /
unarmed 689 passed 2 declared skips (ZERO failures — the designed interim discharged); rollback rehearsal
PASS with the compose-revert arm ARMED (the 12-file sibling residue resolved); egg battery 58 passed 1
declared skip; verify-cognitive-phase4.sh full green end-to-end after this re-bind. The panel verdict
stands. MOVED AGAIN same day (2026-07-24, 3ce64a36… → the value above) by the first-PR-CI root-cause
commit 429fa17b — the REMAINING e2-routed §6.4-6.7 sibling-suite re-anchors (charter-shadow /
judge-calibration / preference-pairs / prediction-scorer locks re-anchored to the composed vehicle; these
four files join restore_from_baseline + EXPECTED_SCOPE, the pair-extension that moved the digest), the
evidence-proof allowlist row for this phase's rollback manifest (that proof file is out-of-phase, unbound
by this digest), and the wave artifact's §6 addendum. Zero behavior bytes beyond that routed §13 surgery;
the full twin re-ran green end-to-end after this second re-bind. The panel verdict stands. FINAL MOVE
(2026-07-24, e2c35aa9… → the value above): the post-flip range-seal commit pinned the manifest's
done_flip_sha to the ledger flip commit c58d4a57 (the §16 retirement condition, the phase-3 e7f95d5a
retrofit shape) — a one-line YAML pin inside the scope; zero behavior bytes; the W6 merge dfb1a00e and the
flip c58d4a57 each carried all 7 CI jobs green. The panel verdict stands. MOVED BY THE COG-5 W1 LANDING
(2026-07-24, 95e6ea8bf1288655a488342ea2675e515d7332829c2ff623664db5cd23a10c42 → the value above): a
NEXT-PHASE rows-only extension, sanctioned IN ADVANCE by the COG-5 contract §10 (+ §7.5 Stage A) — zero
engine/behavior bytes. Exactly TWO in-scope paths moved vs the last binding (verified by diffing the
resolved 85-entry scope over 70bca2ae..HEAD; the COG-5 contract doc + the operative ledger sit OUTSIDE this
scope, and the parallel master doc-hygiene pair 21df33c9 moved ZERO in-scope paths): (1)
`cabinet/config/boundary-manifest.yml` +103 lines — COG-5 ROWs 8/9/10 APPENDED (holdout_gen sweep /
foundry-archive data-plane / evolution reverse); ROW 6 byte-untouched (the deliberate non-extension); the
engine `cog2-import-gate.py` byte-untouched; (2) `cabinet/scripts/egg-export-manifest.txt` +15 lines — the
§7.5.5 Stage-A INTERIM vacuity-armed holdout delete/expect-absent pair. Re-run at the landing on the merged
bytes: the boundary harness `test_cog4_boundary_rows.py` (the generic per-row mutant generator — a biting
mutant auto-generated per NEW row) + `test_cog5_boundary_rows.py` (content pins) 113 passed;
`cog2-import-gate.py` rc0; the full `test_cog4_*` battery 702 passed 2 declared skips; armed
`cog4-measure --check` within bound; `verify-cognitive-phase4.sh` full green end-to-end after this re-bind.
A MECHANICAL-DELTA re-bind per the cp3 precedent, never a restamp: zero COG-4 claims are touched by rows
APPENDED for the next phase. The panel verdict stands.
MOVED BY THE BOUNDARY-ENGINE DYNAMIC-FORM LANDING (2026-07-25,
d8d316b244e10156d45b3b46cff7bddb52bfbd526b736d1b7bb97745f1241eb2 -> the value above; from
093e5866...). Landed branch `fix/import-gate-dynamic-forms`, two commits, closing ten spellings of a
dynamic-import evasion in the boundary engine. READ THIS ONE DIFFERENTLY: every re-bind above is a
MECHANICAL-DELTA re-bind (zero behavior bytes). This is the FIRST BEHAVIOR-DELTA re-bind of this
artifact — the engine's own logic changed, so "mechanical delta" would be a false claim and is not made
here. EXACTLY ONE in-scope path moved (verified by diffing the resolved 85-entry scope over
origin/master 26d4cce2..HEAD): `cabinet/scripts/cog2-import-gate.py`, +432/-13, adding an AST pass
(constant-fold + binding-accurate hook resolution over `_HOOKS_OF_MODULE` {importlib, builtins}).
The other three landed paths sit OUTSIDE this scope and are named for the record: the new suite
`cabinet/scripts/tests/test_boundary_dynamic_forms.py` (only the enumerated `test_cog4_*`/`lib_cog4_*`
files are scope entries — `cabinet/scripts/tests` is NOT a DIR entry) and the two FW-019 batch proofs
`fix-import-gate-dynamic-forms-cp{1,2}.md`.
WHY THE PANEL VERDICT STILL STANDS — the Q9 engine claims were RE-MEASURED by the landing integrator on
the merged bytes, not inherited: (a) engine over the committed repo rc0, and its `check`/`--report`/
`--json` streams are BYTE-IDENTICAL to master's engine on the same tree (so the change is invisible to
every real caller — no new false positive anywhere in the repo); (b) the legacy suites
`test_cog2_import_gate.py` + `test_cog3_import_gate.py` are BYTE-UNTOUCHED vs master (`git diff` empty)
and, with `test_cog4_boundary_rows.py` + `test_cog5_boundary_rows.py`, 229 passed; (c) the panel's
six-mutant shape was re-run by the integrator against BOTH engines side by side with the fenced token
SPLIT (so the token-grep rule cannot mask the result): the two literal controls keep IDENTICAL rule-id
attribution on both engines, all ten dynamic spellings go rc0-on-master -> rc1-on-this-engine carrying
the SAME rule id the literal dynamic spelling already carried (`FORBIDDEN_PROJECTION_TOKEN` — attribution
does not move), and six false-positive controls (own-`def import_module`, rebound name, unrelated target,
allowlisted importer, non-fenced lane, 200-deep fold nest) stay CLEAN on both. The change is therefore
STRICTLY WIDENING: it can only add catches, never retract one or re-attribute one. (d) `cog4-measure
--check` armed and within bound; census PASS at the e4-tightened maxima with zero headroom preserved
(the engine lives in `cabinet/scripts`, outside the `framework_production_*` counters); layer-sep new=0;
`verify-cognitive-phase4.sh` full green end-to-end after this re-bind.
WHAT WAS NOT DONE, stated plainly: this was NOT re-reviewed by a fresh frozen COG-4 panel. The
integrator re-ran the panel's Q9 claim surface (above) and the branch carries its own two adversarial
fresh-context review artifacts, cp1 and cp2; cp2 records that cp1's own residual text was FALSE BY
OMISSION and corrects it. A later session that wants a panel-grade re-review of the widened engine
should read cp2 first — its residual set is measured against these exact bytes and pinned by tests.
SIBLING BINDERS: `cabinet/scripts/cog2-import-gate.py` also sits in the COG-2 and COG-3 EXPECTED_SCOPEs,
so this landing moves those digests too (COG-2 98bae784 -> 59514d4a, COG-3 34a382fa -> 61644fda). They
are NOT re-bound and must not be: COG-0/1/2/3 are the digest-frozen historical instances their own
docstrings describe and were ALREADY BLOCK on master 26d4cce2 before this branch (measured: COG-0
f543dc1e vs 63f4643a, COG-1 25c2f5e3 vs 2fb7a390, COG-2, COG-3) — a pre-existing, by-design condition
this landing neither improves nor worsens. COG-4 is the one LIVE binding, and it is the one re-bound
here.)
(MOVED BY THE CAPTAIN-CONTACT LIVENESS LANDING, 2026-07-25 — d8d316b2... -> the value above. Landed
branch `feat/captain-contact-liveness` (PR #196, one commit db2a3346, merge 0830a076) over master
32ff7384: the Captain-contact dead-man (D1), the honest queued-vs-delivered sender (D4-cheap), and
severity-ordered watchdog findings (X). EXACTLY TWO in-scope paths moved, verified by intersecting the
resolved 85-entry scope with `git diff --name-only 32ff7384..db2a3346` rather than by reading the diff:
  (1) `cabinet/config/cognitive-architecture-contract.yml` — two `temporary_allowances` rows APPENDED
      (`framework_production_modules` +2, `framework_production_noncomment_lines` +386) for the new
      stdlib-only `framework/liveness` package. Declarative budget consumed by the census gate, not by
      any COG-4 engine. Census re-measured on the merged bytes: PASS at 238<=238 and 66934<=66934 —
      exact totals, zero headroom preserved, no maximum relaxed and no threshold touched.
  (2) `framework/watchdog/registry.py` — the path named in this review's scope for its
      `_parse_organ_manifests` surface. That function's body is BYTE-IDENTICAL on the merged bytes
      (measured line-exact over its 71-line span, base vs merged), as is `_resolve_organ_artifact`.
      What changed is its CALLER.
A BEHAVIOR-DELTA RE-BIND, stated plainly rather than inheriting the MECHANICAL-DELTA formula from the
re-binds above: `verify_no_silent_cron_failure` now tags every finding with a causal severity
(`_SEV_NOT_LOADED` 0 .. `_SEV_MARKER` 5; organ findings are `_SEV_ORGAN` 4) and STABLY SORTS before the
pre-existing 8-item truncation. Per-finding message TEXT is unchanged — measured, both organ literals
byte-identical base vs merged — and so is finding MEMBERSHIP; what moves is ORDER, and therefore WHICH
eight survive when more than eight findings exist. Differential run on this repo's own `_mini_probe`
fixture (memory-worker unloaded + retro-trigger exit 127):
    base   -> "...retro-trigger: last exit status 127; memory-worker: declared ... but not loaded ..."
    merged -> "...memory-worker: declared ... but not loaded ...; retro-trigger: last exit status 127"
Same set, same per-finding text, CAUSE first. That inversion is the point: the not-loaded scan appends
LAST, so in exactly the broad-outage case the truncation exists for, the line naming the cause was
always the first casualty. No COG-4 claim is retracted — the organ-floor detection logic and the
reviewed property "a silent organ inside a live runner trips its own floor" are untouched; only the
rendering order of a multi-finding detail string moved, and organ findings can now be displaced by
strictly more-causal rows (not-loaded / no-log / non-zero-exit) and can now displace error-marker
symptoms. Re-measured on the merged bytes, not inherited: `verify-cognitive-phase4.sh` full green
end-to-end after this re-bind; census PASS; layer-sep new=0; `framework/` 6511 passed and
`cabinet/scripts/tests` 4534 passed against a re-measured 32ff7384 baseline (6454 / 4523).
WHAT WAS NOT DONE, stated plainly: this was NOT re-reviewed by a fresh frozen COG-4 panel. The branch
carries its own adversarial fresh-context artifact,
`shared/interfaces/reviews/feat-captain-contact-liveness-cp1.md`, whose residual section records the
honest limit of that unit — the primary off-machine detector is INERT until an operator registers a
watcher, so the branch ships the mechanism, not the activation.
SIBLING BINDERS: `cabinet/config/cognitive-architecture-contract.yml` sits in the COG-0/1/2/3
EXPECTED_SCOPEs too, so this landing moves those digests as well (COG-0 63f4643a -> 869b2db6, COG-1
2fb7a390 -> 7f17308d, COG-2 59514d4a -> 7f4047d3, COG-3 61644fda -> 727b8fee). They are NOT re-bound
and must not be: all four were ALREADY BLOCK on pre-merge master 32ff7384 — measured, not assumed, by
running each verify twin there (recorded vs recomputed: COG-0 f543dc1e vs 63f4643a, COG-1 25c2f5e3 vs
2fb7a390, COG-2 b38632b9 vs 59514d4a, COG-3 78a7bf18 vs 61644fda; all exit 1). COG-4 was the one
binding GREEN on 32ff7384 (verify twin exit 0, recorded == recomputed == d8d316b2) and the only one
this landing turned BLOCK, so it is the only one re-bound. This commit edits ONLY the digest-excluded
review artifact, so the digest it records is stable under its own landing.)

(MOVED BY THE EGG EGRESS-DEFAULT FLIP, 2026-07-26 —
6f04c4bc47876ba2152aceaf9cb7feb003c8cd1f7f498d0c0c3cb955937e1cae -> the value above. Landed branch
`fix/egg-egress-default` over master f3914dde, executing the Captain's 2026-07-26 ruling that the egg
ship the framework's documented allow-all egress default with enforcement left as a one-command OPTION.
EXACTLY TWO in-scope paths moved, verified by intersecting the resolved 85-entry scope with
`git diff --name-only origin/master..HEAD` rather than by reading the diff:
  (1) `cabinet/scripts/egg-export-manifest.txt` — COMMENT LINES ONLY. The `delete
      instance/config/egress.yml` row and the `transform egress-default` row are byte-identical; only
      their explanatory prose changed, to stop claiming the shipped twin is `enforce: true`. Zero
      manifest semantics, zero rows added or removed, no expect-present/expect-absent rule touched.
  (2) `cabinet/scripts/tests/test_egg_export.py` — one assertion in
      `test_egress_default_is_the_scrubbed_twin` INVERTED under the ruling, plus its docstring. The
      byte-identity assertion (`shipped == twin`) is untouched; what changed is the posture pinned on
      top of it, and it was made STRICTLY STRONGER in the same edit: substring presence
      (`b"enforce: true" in shipped`) became an exact match on the single active `enforce:` scalar, so
      the egg shipping ANY unratified posture is still red. Substring matching would in fact have been
      wrong post-flip, since the twin's prose legitimately names the enabling value while telling a
      stranger how to opt in.
A MECHANICAL-DELTA re-bind per the cp3 precedent, never a restamp, and — unlike the two BEHAVIOR-DELTA
re-binds above — the claim is made here because it holds: ZERO COG-4 engine, organ, scheduler,
projection or trajectory bytes are touched by this landing. Neither moved path is a COG-4 surface; they
are bound only because the egg packaging manifest and its test sit inside the declared scope. The four
COG-4 §15 findings are untouched and none is re-derived. Re-measured on the merged bytes, not inherited:
`verify-cognitive-phase4.sh` full green end-to-end after this re-bind; the full `test_cog4_*` battery
702 passed 2 declared skips; `test_cog4_boundary_rows.py` + `test_cog5_boundary_rows.py` 113 passed;
`cog2-import-gate.py` rc0; the egg battery (`test_egg_export.py` + `test_egress_guard.py` +
`test_egress_dry_run_asymmetry.py`) 108 passed 1 skip; census PASS at every maximum with zero headroom
preserved — no maximum relaxed, no threshold touched, no `temporary_allowances` row added (this landing
adds no framework Python at all); layer-sep new=0; `null-hatch.sh` rc0.
WHAT WAS NOT DONE, stated plainly: this was NOT re-reviewed by a fresh frozen COG-4 panel. The two moved
paths are the egg packaging contract, not the phase's claim surface, and the landing carries its own
adversarial fresh-context review artifact for the branch.
SIBLING BINDERS: both moved paths sit in the COG-0/1/2/3 EXPECTED_SCOPEs too (measured: each of the four
scope tools names both), so this landing moves those digests as well (COG-0 dcf3b43d -> b454304d, COG-1
16f7547a -> e0efb3cf, COG-2 7f4047d3 -> 03a65104, COG-3 727b8fee -> 6a7bc7fe). They are NOT re-bound and
must not be: all four were ALREADY BLOCK on pristine master f3914dde — measured, not assumed, by running
each verify twin there (recorded vs recomputed: COG-0 f543dc1e vs dcf3b43d, COG-1 25c2f5e3 vs 16f7547a,
COG-2 b38632b9 vs 7f4047d3, COG-3 78a7bf18 vs 727b8fee; all exit 1). COG-4 was the one binding GREEN on
f3914dde (verify twin exit 0, recorded == recomputed == 6f04c4bc) and the only one this landing turned
BLOCK, so it is the only one re-bound. This commit edits ONLY the digest-excluded review artifact, so the
digest it records is stable under its own landing.)

(MOVED BY THE ATTENTION-WELL-SPENT LANDING, 2026-07-26 —
93839d991e56db1fe048e1df97774e1dd4b248f0071d90171979d38ab08109d4 -> the value above. Landed branch
`fix/attention-silence-ratchet` over master f07787fa: the cabinet was structurally biased toward going
quiet and its own score rewarded it — the OVI attention term was weighted `direction: inverse`, reading a
perfect 1.00 in EVERY window (7d/30d/365d) including a 7d window with 0.0 throughput and 0.0 verification.
EXACTLY ONE in-scope path moved, verified by intersecting the resolved scope with
`git diff --name-only origin/master..HEAD` (27 changed files, one of them in scope) rather than by reading
the diff:
  (1) `cabinet/config/cognitive-architecture-contract.yml` — ONE `temporary_allowances` row APPENDED
      (`framework_production_noncomment_lines` +252, phase `attention-well-spent`) for the fix's framework
      surface. Declarative budget consumed by the census gate, not by any COG-4 engine — the same class as
      the captain-contact-liveness rows two re-binds above. Census re-measured on the branch bytes: PASS at
      67186<=67186 — exact total, zero headroom preserved, no `maximum` relaxed and no threshold touched.
      The row's own reason records the honest accounting: 209 of those 252 lines are docstring prose and
      only 43 are executable code (measured, not estimated), and they were deliberately NOT reformatted
      into `#` comments — which the counter ignores, and which would have bought back ~209 lines by moving
      words sideways instead of shrinking anything.
A MECHANICAL-DELTA re-bind per the cp3 precedent, never a restamp, and the claim is made here because it
holds: ZERO COG-4 engine, organ, scheduler, projection or trajectory bytes are touched by this landing.
The moved path is not a COG-4 surface; it is bound only because the census contract sits inside the
declared scope. The four COG-4 §15 findings are untouched and none is re-derived. Re-measured on the
branch bytes, not inherited: `verify-cognitive-phase4.sh` full green end-to-end after this re-bind;
census PASS; layer-sep new=0; `cog2-import-gate.py` rc0; `null-hatch.sh` rc0; golden evals 30/30;
`framework/` 6587 passed and `cabinet/scripts/tests` 4665 passed against a re-measured f07787fa baseline,
with the one declared pre-existing red (`test_retro_shim.py::test_reexports_constants`) reproduced
identically on pristine master.
WHAT WAS NOT DONE, stated plainly: this was NOT re-reviewed by a fresh frozen COG-4 panel. The moved path
is a declarative budget row, not the phase's claim surface, and the landing carries its own review
artifact `shared/interfaces/reviews/fix-attention-silence-ratchet-cp1.md`.
SIBLING BINDERS: `cabinet/config/cognitive-architecture-contract.yml` sits in the COG-1/2/3
EXPECTED_SCOPEs too, so this landing moves those digests as well (COG-1 e0efb3cf -> 497909af, COG-2
03a65104 -> 9fc88f5c, COG-3 6a7bc7fe -> 6a6aa580). They are NOT re-bound and must not be: all three were
ALREADY BLOCK on pristine master f07787fa — measured, not assumed, by running each verify twin there
(recorded vs recomputed: COG-1 25c2f5e3 vs e0efb3cf, COG-2 b38632b9 vs 03a65104, COG-3 78a7bf18 vs
6a7bc7fe; all exit 1). COG-0 has a scope tool but NO review artifact on this tree, so it has no binding to
move. COG-4 was the one binding GREEN on f07787fa (verify twin exit 0, recorded == recomputed ==
93839d99) and the only one this landing turned BLOCK, so it is the only one re-bound. This commit edits
ONLY the digest-excluded review artifact, so the digest it records is stable under its own landing.)

(RE-BOUND ON THE MASTER MERGE, 2026-07-27 —
60ab5575264c12afc2bec225e9a943c8762900c2a4fa8b8fbb1ad2971ece1e38 -> the value above. The
attention-well-spent branch was rebased onto master by merge rather than by rewrite, and master had moved
f07787fa -> ac56ce78 under it.
READ THIS ONE DIFFERENTLY FROM THE NOTE ABOVE: when that note was written, COG-4 was the one binding GREEN
on f07787fa and this landing was the only thing turning it BLOCK. That is NO LONGER the starting
condition. COG-4 is ALREADY BLOCK on master ac56ce78 — measured, not assumed: the verify twin run there
exits 1 with recorded 93839d99 vs recomputed e7fccd9b, and the full `verify-cognitive-phase4.sh` on
pristine ac56ce78 exits 1 on that same binding. The captain-availability-dial landing (PR #210, merge
ac56ce78) appended two `temporary_allowances` rows to `cabinet/config/cognitive-architecture-contract.yml`
— an in-scope path — and did not discharge the re-bind ceremony. So this commit re-binds the digest to the
MERGED bytes and, as a side effect, clears a pre-existing BLOCK it did not cause. Recording that plainly
rather than quietly inheriting the credit: one of the two deltas folded into this digest is not this
branch's work.
EXACTLY ONE in-scope path moved vs origin/master ac56ce78, verified by intersecting the resolved scope
with `git diff --name-only origin/master..HEAD` (29 changed files, one in scope):
`cabinet/config/cognitive-architecture-contract.yml` — now carrying BOTH landings' rows, master's two
captain-availability-dial rows and this branch's one attention-well-spent row, reconciled by keeping both
sides rather than taking either wholesale. Census re-measured on the merged bytes: PASS at 239<=239 and
67578<=67578 — exact totals, zero headroom preserved, no maximum relaxed. This branch's row is unchanged
at +252; only its recorded running total was re-measured (67186/66934 -> 67578/67326) because master's
rows moved the base underneath it.
STILL A MECHANICAL-DELTA re-bind, and the claim still holds: ZERO COG-4 engine, organ, scheduler,
projection or trajectory bytes are touched by either landing folded here. Both are declarative budget rows
consumed by the census gate. The four COG-4 §15 findings are untouched and none is re-derived.
Re-measured on the merged bytes: `verify-cognitive-phase4.sh` full green end-to-end after this re-bind.
SIBLING BINDERS: the contract yml sits in the COG-1/2/3 scopes too, so this landing moves those digests as
well. They are NOT re-bound and must not be: all three were ALREADY BLOCK on pristine master ac56ce78 —
measured by running each verify twin there, all exit 1 (recorded vs recomputed: COG-1 25c2f5e3/3e0e6a84,
COG-2 b38632b9/04c276bb, COG-3 78a7bf18/218ba7dd). COG-0 has a scope tool but no review artifact on this
tree, so it has no binding to move. This commit edits ONLY the digest-excluded review artifact, so the
digest it records is stable under its own landing.)
MOVED BY THE SPEND-METER LANDING (2026-07-27, a30366943126b05011435269b1f72335a4455bd8f0fbfd1518a426ab462c2df2 -> the value above): a
MECHANICAL-DELTA re-bind per the cp3 precedent, never a restamp, and the claim is made here because it
holds. ZERO COG-4 engine, organ, scheduler, projection or trajectory bytes are touched. EXACTLY ONE
in-scope path moved, verified by intersecting the resolved 85-entry scope with
`git diff --name-only origin/master...HEAD` (41 changed files, one in scope) rather than by reading the
diff: `cabinet/config/cognitive-architecture-contract.yml` gains TWO temporary_allowances rows recording
the framework/cost/ package as an exact measured total (+4 modules, +778 noncomment lines). That file is
not a COG-4 surface; it is bound only because the census contract sits in the declared scope — precisely
the class of the attention-well-spent re-bind immediately prior (3dcd3e62) and the contact-liveness rows
before it (598868ed). No maximum was relaxed: the census re-measures PASS at 243<=243 modules and
68356<=68356 lines, exact totals, zero headroom preserved.
Re-measured on the branch bytes, not inherited: `verify-cognitive-phase4.sh` full green end-to-end after
this re-bind; census 29 passed; egg battery 58 passed 1 declared skip; `framework/` 6658 passed with the one
declared pre-existing red (`test_retro_shim::test_reexports_constants`) reproduced identically on pristine
master. NOT re-reviewed by a fresh frozen COG-4 panel; the branch carries its own review artifacts
(fix-spend-meter-uncapped-cp1.md, unit-sensor-cp1.md, unit-lanes-cp1.md).
SIBLING BINDERS NOT TOUCHED, deliberately: the contract yml also sits in the COG-1/2/3 scopes, all three of
which were ALREADY BLOCK on pristine master before this branch existed. Re-binding them would restamp
frozen gate archaeology. This commit edits ONLY the digest-excluded review artifact, so the digest it
records is stable under its own landing.)

---

## §15 standing questions — findings

### Q1 — Does any serve path return rows it did not hash in the same read?

**NO.** `framework/scheduler/serve.py` has exactly ONE public entry, `serve_schedule` (:126), routing through
`framework/projection/kernel.py::verified_single_read` (:223-285): the store is read ONCE (`read_jsonl_rows`,
:271 "the ONE read"), the chained hash re-derived from the RE-PARSED rows, bound to the manifest, and the
returned rows ARE the hashed rows. Panel probe (own code, store built end-to-end via the real
`cog3-rebuild.py`→`cog4-snapshot.py`→`cog4-schedule.py` CLIs in a tmp root): served rows == disk rows ==
`model.schedule_rows_hash` input; tampered row / REORDERED-but-identical rows (file-order chain, model.py:126-134)
/ forged counts / tampered+missing snapshot record / partial epoch key-set / snapshot echo forgery — 8/8
tamper classes `ScheduleRefused`, 1/1 pristine control ANSWERED. Package roots are import-inert in a fresh
subprocess (forbidden closure EMPTY; loaded = framework{,.organs,.projection,.scheduler} only). The serve
module's public surface is {`serve_schedule`, `ScheduleRefused`} + its imports — no second loader exists;
`cog4-schedule.py` reports THROUGH the loader (:69 "F1: report via the loader"); `cog4-dispatch-shadow.py`
serves through it (`run_shadow_dispatch` :569) and its availability probe returns no rows (Q4/F2).

### Q2 — Does any manifest-absent key skip a limb?

**NO.** The rows-hash key is MANDATORY-PRESENT (kernel :264-269): panel-deleted `schedule_rows_hash` AND
empty-string value both REFUSE ("MANDATORY-PRESENT (§6.3)"); the objectives `is not None and` skip-hole is
closed for this store. Epoch completeness limb refuses a partial wake-input key SET (serve.py:70-72, panel
probe). Snapshot builder: absent cortex `belief_store_hash` / objectives `graph_rows_hash` REFUSE
(snapshot.py:100-104/128-132 — "never an invented wake input"). Dispatcher: manifest-absent
`freshness_needs` => `freshness_underivable` REFUSE; absent `idempotency` => `idempotency_underivable`
REFUSE; missing organ manifest => `organ_manifest_missing` REFUSE (all panel-probed, zero would_dispatch).
Descriptor: absent block/member/idempotency discipline => `DescriptorRefused` (8 panel refusal probes incl.
the unknown-key fail-closed subset guard, descriptor.py:121-126).

### Q3 — Can any non-declared input (env/clock) reach the fold?

**NO.** Grep over `framework/{scheduler,projection,organs}`
(`os.environ|getenv|datetime.now|utcnow|time.time|getcwd|Path.cwd|expanduser|gethostname|random`): zero code
hits (three docstring prose mentions only). `build_snapshot` takes every input as a declared parameter
(snapshot.py:107-115); `validate_snapshot` recomputes SF2 family hashes + the registry hash from the
snapshot's own data (model.py:207-215). N1 panel probe: 3 subprocess rebuilds under PYTHONHASHSEED 0/1/987654321
from the same snapshot file → identical `schedule_rows_hash` (a9def50c37d7…). AST pins green in the battery
(`test_cog4_scheduler_ast_pin.py`); `test_cog4_sim_fold.py` purity mutants green.

### Q4 — Can the dispatcher execute anything?

**NO.** AST trace over `cog4-dispatch-shadow.py` + the whole planner tree: zero
subprocess/socket/http/urllib imports, zero `os.system/popen/exec*/spawn*` attributes. The CLI writes ONLY
the shadow log (O_EXCL lock + O_EXCL tmp + fsync + os.replace, :625-658). Hermetic mode never calls
`_act_with_undo_gap` (:301 live-only guard). All SIX §7.3 limbs fire in order — panel per-limb fixtures
(violate limb k, satisfy k−1): (1) tamper=>`serve_refused`/`rows_hash_mismatch` rc2 zero records; absent
key=>`rows_hash_key_absent`; missing store=>`safe_fallback` rc4, fixed safe schedule echoed, NEVER permission;
(2) any live-vs-recorded difference incl. recorded-exists/live-null AND live-extra-key (symmetric union,
:583-587) => `stale_snapshot` rc2; (3) `authority:ceiling` / `authority:undo_gap` / `authority:propose_only`
fail-safe, allow-set {auto, act_with_undo, auto_with_veto_window, notify_after} (:166-167); (4)
`budget_overflow` with `planner_admitted: true`; (5) `stale_organ:age=…` + `staleness_flagged`, never
auto-permission; eligibility rechecks (crashed-vs-unhealthy health classification :215-222, fallback honored,
dependency/capability unavailability with ORIGINAL identity); (6) re-derived idempotency key (row-carried keys
never trusted), replay across runs refuses `idempotency_replay` (panel double-run probe). §7.4 pointer
tripwire: a pointer created under a scratch-HOME `~/.cabinet/state/cog4-dispatch-pointer` => rc5
`pointer_tripwire`, zero records, on the DEFAULT path (expanduser proven live); no pointer => normal rc0. The
live machine carries no pointer file. Import pin `test_cog4_dispatch_ast_pin.py` green.

### Q5 — Can `capability` reach any verdict predicate?

**NO.** `_AuthorityJoint.check` (dispatch :257-309) reads ceiling/action_type/risk_class/undo_contract only;
grep for capability-keyed predicates over organs+scheduler+dispatcher: zero. Panel probe: two operations with
identical declared members resolve IDENTICAL enforcement tuples under distinct capabilities
(descriptor.py resolution is identity lookup). The corpus capability-blindness harness
(`test_cog4_exit_fixtures.py::_assert_capability_blindness`, capability-keyed mutant REDs) ran green per
cabinet across all three non-software fixtures.

### Q6 — Does any path grow ACTION_TYPES or bypass the adapter parity?

**NO.** `len(ACTION_TYPES) == 30` incl. `ambiguous`; the consequence-schema closed enum == ACTION_TYPES+null
(byte-mirror probe); census `central_action_types 30 <= 30`; v1 trajectory schema byte-identical to master
(`git diff --quiet` clean); the §16 protected union (classifier/matrix/policy_engine/matrix-yml/consequence
schema/v1 schema/HUMAN_PHRASES both mirrors/graduation/cog3 AST pin/extension gate pair) verified
byte-unchanged over baseline..HEAD by the rehearsal's per-path diff leg (that leg PASSED; the rehearsal's
later red is the sibling-residue ratchet, Q10). Parity: legs independent BY CONSTRUCTION
(`cog4-parity.py` leg b: own declarer scan `_leg_b_owner` :211 + own raw merge `_leg_b_declared` :225; source
between `action_types_leg` and `_leg_tuple` never calls `resolve_descriptor`/`descriptor_leg` — byte-probe).
Panel-seeded divergent manifest (declared `spend` vs matrix-derived `read_only_dispatch`) => exit 2, the
divergence RECORDED in the written record with both legs; flat operation id => setup exit 3 (the
collision guard — load-bearing while CG-33 schema validation is parked); zero-operations => exit 3 (no
vacuous green); the REAL composed pilot manifests => exit 0, zero divergent tuples. Trajectory v2: version
dispatch decided BEFORE v1 checks (contracts.py:265-275, `_is_v2_record` exact-literal marker); a namespaced
id in the effect compat `action_type` FAILS the v2 pattern (`compatActionType` excludes `/` — panel probe:
schema.pattern violation at `$.effects[0].action_type`); forged `v3` and absent versions fall to the FROZEN
v1 path and fail; the full evolution contracts suite green (47 passed).

### Q7 — Does composing rows drop a floor or LOOSEN its (cadence, threshold, probe) tuple?

**NO — recomputed by this panel from the pre-compose tree.** Pre-compose services.yml (master `fc51fd59`):
57 rows / 44 enabled; the five absorbed rows (charter-shadow, judge-calibration, prediction-calibration,
preference-pairs, world-census) all ENABLED, all daily. Post: 52 rows / 40 enabled; runner row
`interval_s: 43200` ≤ every absorbed 86400 period (cadence leg). Threshold leg: every organ
`max_staleness_seconds` 90000 ≤ the absorbed row's `_floor_for_entry` floor 93600 (all five, computed via the
REAL registry functions against the pre-compose text). Probe leg: five DISTINCT per-organ
`cabinet/cache/organs/<name>/last-run.json` receipt artifacts — never the shared runner log; the runner stamps
receipts only on HEALTHY completion (ok|honest_failure — judge-calibration's exit-1-by-design encoded as
`health_proof.exit_codes.honest_failure`), so a silent organ trips ITS OWN floor. COUNT leg: the REAL
`_parse_organ_manifests` over the post manifest derives exactly the 5 floors, zero problems; disabled rows
derive none (belt-and-braces re-filter, registry.py). `test_cog4_organ_runner_real.py`
TestRealDerivationCrossCheck + TestRealComposeForwardTree green (incl. thresholds-do-not-loosen and
per-organ-probe cells). Draft-lane: the ONE disabled-row retirement (L61 evidence bundle in
`feat-cog4-w6-e2-cp1.md`), row + hand-made plist deleted together.

### Q8 — Can the organ-runner observe the schedule store at all?

**NO — three independent ways.** (a) Behavioral, panel's own variant on the REAL CLI: a full schedule
artifact set injected under the runner's run-root `cabinet/cache/scheduler/` => byte-identical behavior JSON
vs the clean run, and the injected store byte-untouched after the wake. (b) Static: zero
`framework.scheduler` imports and zero store-path literals in the runner source (the two grep hits are
docstring prose :13/:70); `test_cog4_organ_runner_real.py::test_real_cli_source_is_statically_scheduler_blind`
green. (c) Boundary DELIBERATE ABSENCE bites: panel scratch-tree mutants — runner importing
`framework.scheduler` REDs `UNALLOWLISTED_SCHEDULER_IMPORTER`; runner naming the store (assembled token)
REDs `FORBIDDEN_SCHEDULER_DATAPLANE` (rows 4/7 `deliberately_absent`). Row→manifest association is DECLARED
(`organs:` block, services.yml:946-951; bare-name discovery refused without `--manifest-dir`).

### Q9 — The boundary ENGINE + exit gates N1-N9 (table below).

Engine: committed-tree run OK rc0; legacy suites `test_cog2_import_gate.py` + `test_cog3_import_gate.py`
116 passed (byte-compat + completeness invariant + every legacy mutant); per-row generated mutants
(`test_cog4_boundary_rows.py`) green in the battery; panel's own six mutants all RED with the row-correct
rule ids (runner→scheduler, runner→store, frontdoor→scheduler, scheduler→authority reverse, organs→frontdoor
reverse MF-A1, un-curated kernel importer).

### Q10 — Anything else that would refuse ship?

**No must-fix.** Full COG-4 battery: armed `5 failed, 687 passed, 1 skipped`; unarmed `5 failed, 686 passed,
2 skipped` — ALL five failures are DESIGNED retire-me flip signals ("<artifact> has LANDED — retire this
vacuity skip") awaiting the landing integrator's §13 corpus surgery: the floor derivation arm
(test_cog4_floor_conservation), the verify-twin + real-pilot measurement arms (test_cog4_measurement), and
the runner invariance + store-blindness arms (test_cog4_organ_runner). Every flipped property is pre-proven
GREEN out-of-band: `test_cog4_measure_baseline.py` 16/16; `test_cog4_organ_runner_real.py` (e2's routed
drop-in) full green. Both skips declared (wall-clock posture skip, armed by the twin; CG-33 germline-window
vacuity skip — the §4.5 amendment is FILED, window unopened, PARK marker present). `verify-cognitive-phase4.sh`:
every pre-battery leg green — `cog4-measure --check` ARMED within bound ("proxies EXACT, wall-clock <= bound"),
review-absent skip-loud branch, pointer tripwire clean, `verify-cognitive-architecture.sh` 76 passed,
census PASS at the e4-TIGHTENED maxima (`services_total 52<=52`, `services_enabled 40<=40`,
`central_action_types 30<=30`, modules `236<=236`, lines `66548<=66548` — zero headroom, observed==max),
layer-sep OK (new=0); overall exit 1 at the battery leg = the documented pre-surgery interim, and the
ROLLBACK REHEARSAL is likewise DESIGNED-RED at HEAD (12-file e2/e3 sibling residue — the §16 manifest's
`sibling_landing_note` + e3 cp1 §6 declare it; the strict inverse-diff equality is the completeness ratchet
WORKING; its protected-surface and A13 legs passed before the ratchet). The §16/scope pair is
force-coupled: `resolve_scope()` fails closed on a one-sided edit. Standalone: A13 parity OK (351 rows);
egg battery 58 passed + 1 declared machine-shape skip (twin delete + expect-absent pairs for all three
phase-4 twins; expect-present for parity/dispatch/runner/measure CLIs + the tracked parity record + S0
baseline); anti-phantom probe — `COG4_ENFORCE_BOUND` is the only COG4_* flag in the twin and has live
non-twin consumers (cog4-measure.py, test_cog4_measurement.py, test_cog4_measure_baseline.py); the e3
claim-surface fix (2338d6c9) removed the phantom `--mode` flag. All four PARK markers exist (officer-plist
cleanup W1-u3; cortex serve adoption W3-u3; objectives kernel adoption W3-u4; organ schema validation W4-u1).
Fleet truth: rowless template-organ set pinned to EXACTLY the 9 (conservation guard green; officer-leakage
subset tolerant pending parked u3). N8: the three non-software cabinets (garden-delivery extended +
harbor-warehouse + care-rota, MR4) ran end-to-end through the REAL CLIs in the battery with the enum-growth
walls asserted and the operation-name-authority mutant exercised per cabinet.

---

## Findings register

| id | severity | finding | file:line | disposition |
|---|---|---|---|---|
| P1 | NOTE | Shadow-log replay window: `replay_keys` are read BEFORE `append_shadow_log`'s O_EXCL lock, so two dispatchers racing one log could each record `would_dispatch` for the same idempotency key (the log itself cannot corrupt; single-process replay refusal panel-proven). Zero effect surface exists this phase. | cog4-dispatch-shadow.py:858-877 vs :625-658 | Recorded; MUST be folded into the future cutover amendment's requirements (read+check+append under one lock) before any dispatch becomes real. Not ship-blocking in shadow. |
| P2 | NOTE (as designed) | After a `ScheduleRefused`, `_classify_refusal`/`_probe_availability` re-read store bytes to CLASSIFY the refusal (availability vs integrity). No rows are served from the probe; a raced re-read degrades conservative (`store_corrupt`). Documented in the CLI header. | cog4-dispatch-shadow.py:315-356 | As designed; recorded so the second read is never mistaken for a serve path. |
| P3 | INFO | `framework/organs` imports third-party `yaml` — a declared allowance in the organs package pin (stdlib \| yaml \| internal), unlike the stdlib-only kernel/watchdog surfaces; the canonical-bytes stdlib replica is parity-pinned against the kernel. | framework/organs/registry.py:54; test_cog4_organs_package.py:622 | As designed (module docstring states the row-6 rationale). |
| P4 | INFO | Designed interim at this tip: 5 corpus flip-arms RED + rollback rehearsal RED (sibling residue) + review-scope EXPECTED_SCOPE excludes e2/e3 surfaces; verify twin exits 1 overall. All declared in-tree with forcing functions; discharge = the landing integrator's §13 surgery + §16-manifest/EXPECTED_SCOPE paired extension + review re-freeze/digest re-bind. | verify-cognitive-phase4.sh:14-22; rollback manifest sibling_landing_note; e3 cp1 §6-7 | The integrator's named move at landing; this panel's verdict binds the reviewed bytes. |
| P5 | INFO | `cog4-snapshot.py` and `cog4-schedule.py` have no `expect-present` egg lines (they ship by default; the other four cog4 CLIs + records are asserted) — consistency nit vs the cog3 expect-present precedent. | cabinet/scripts/egg-export-manifest.txt:489-520 | Optional tidy at landing; egg battery green either way. |

## N1-N9 exit-gate table

| gate | mechanical proof | run + result |
|---|---|---|
| N1 determinism | panel triple: 3 subprocess rebuilds × PYTHONHASHSEED {0,1,987654321} from one snapshot → identical chained hash; delete→rebuild = the kernel rollback grammar; file-order chain refuses reorder | PASS (panel probe + sim-fold battery green) |
| N2 starvation | declared bounds are snapshot inputs (organ `starvation_bound` else scheduler_policy default, fold.py:99-107); sim-7 battery | PASS (battery) |
| N3 forged/stale | tamper/absent-key/reorder/counts/snapshot-binding all REFUSE at serve; stale/null/extra-key symmetric union REFUSES at dispatch | PASS (8 serve + 3 dispatch panel probes) |
| N4 budget | `budget_overflow` at dispatch though planner admitted (`planner_admitted: true`) | PASS (panel probe) |
| N5 authority | ceiling/undo-gap/propose_only/gated refuse via the pinned read-only joint; allow-set exact | PASS (panel probes + exit fixtures) |
| N6 latency/cost | armed `cog4-measure --check` vs the tracked S0 baseline within bound; proxies EXACT always-on; `COG4_ENFORCE_BOUND` consumers live (anti-phantom probe) | PASS (verify leg + probe) |
| N7 service-retirement | 57/44 → 52/40 recounted by panel parser; census maxima TIGHTENED to actuals (52<=52, 40<=40, observed==max); fleet-truth conservation green (rowless == the pinned 9) | PASS |
| N8 three non-software cabinets | garden-delivery (extended) + harbor-warehouse + care-rota end-to-end via real CLIs; zero new central members (30 pinned, mirrors byte-intact) | PASS (battery + panel walls) |
| N9 parity | real pilot manifests → exit 0 zero divergent tuples; seeded divergence exit 2 + recorded; legs independent at bytes; tracked record gated by test_cog4_parity_record.py | PASS |

## Command log (this run)

1. clone canonical remote + checkout `f62094f7c6ee419db20df3d5445a89f5258467bb` (chain verified over master fc51fd59)
2. `verify-cognitive-phase4.sh` full → N6 armed within bound; census PASS (52/40/30/236/66548 observed==max); layer-sep OK; battery `5 failed 687 passed 1 skipped` (the 5 = designed flip-arms) → exit 1 (documented interim)
3. unarmed battery → `5 failed 686 passed 2 skipped` (both skips declared)
4. `cog2-import-gate.py` → OK rc0; legacy engine suites → 116 passed
5. A13 heredoc → OK 351 rows; `test_egg_export.py` → 58 passed 1 declared skip
6. `cognitive-phase4-rollback-rehearsal.py` → protected-surface + A13 legs PASS, then DESIGNED-RED on the declared 12-file e2/e3 sibling residue (completeness ratchet)
7. panel probe battery 1 (31): real-CLI store build; 8 serve tamper classes REFUSE + pristine control; dispatch limbs 1-6 per-limb fixtures; pointer tripwire under scratch HOME (rc5) + clean run (rc0); no-subprocess AST trace; import-inertness (subprocess re-probe)
8. panel probe battery 2 (43): 8 organ refusals + collision + capability-blindness + registry refusals; trajectory v2 dispatch/namespaced/forged/absent + v1 suite 47 passed; parity divergence rc2 + record / flat-id rc3 / vacuity rc3 / real pilot rc0 / leg-independence bytes; 6 boundary mutants RED with row-correct ids; runner injection byte-identical + store untouched; N1 triple; census recount; floor COUNT+TUPLE recompute; anti-phantom flags
9. panel sweep 3: A-M6 grep clean; freshness/idempotency/manifest underivable refusals; ACTION_TYPES walls; egg lines; PARK markers ×4; draft-lane plist gone; v1 schema byte-untouched; worktree clean
10. `cognitive-phase4-review-scope.py --print` → `d6625b82fc969ce9958e3eebcb96b58c4c6483cf5e3f14fb6cce8908f086ac6e`

## Must-fix list

**None.** The five corpus flip-arms + the rehearsal sibling-residue red are the DOCUMENTED pre-surgery
interim (pre-proven green out-of-band), discharged by the landing integrator's §13 corpus surgery + the
force-paired §16-manifest/EXPECTED_SCOPE extension + review re-freeze; P1 binds the future cutover
amendment, not this phase.

(MOVED BY THE ARM-THE-CABINET LANDING, 2026-07-26 —
93839d991e56db1fe048e1df97774e1dd4b248f0071d90171979d38ab08109d4 -> the value above. Landed branch
`feat/arm-the-cabinet` over master 6079be4d, executing four Captain rulings of 2026-07-26 as one unit.
EXACTLY TWO in-scope paths moved, verified by intersecting the resolved 114-entry scope with
`git diff --name-only origin/master..HEAD` rather than by reading the diff:
  (1) `cabinet/services.yml` — 8 parked rows armed, 2 NEW rows added (the two COG-3 captain-report
      CLIs), 2 rows given machine-readable parking reasons. The COG-4 organ-runner row, its `organs:`
      block and every organ manifest are BYTE-UNTOUCHED.
  (2) `cabinet/config/cognitive-architecture-contract.yml` — the two fleet maxima raised
      (`services_total` 52->54, `services_enabled` 40->50) and `framework_production_noncomment_lines`
      60067->60155, each re-pinned at observed==max with zero headroom; NO `temporary_allowances` row
      added; no other budget touched.
A BEHAVIOR-DELTA RE-BIND, and — unlike the mechanical ones above — it moves a number this review's own
exit gate names, so that is stated first rather than buried. N7's exit condition was
`services_total` < 57 AND `services_enabled` < 44 AT THE DONE-FLIP, with maxima tightened to the phase
actuals under the shrink-only law. That condition WAS met and stays historically true (52 < 57,
40 < 44, measured at the flip). This landing GROWS the fleet past those actuals under an explicit
Captain ruling of 2026-07-26 — one bump for the whole batch, re-pinned with zero slack so the ratchet
still bites at 54/50. Shrink-only is therefore SUSPENDED ONCE BY RULING, not quietly relaxed; no
maximum was set above the observed value and no allowance row hides the growth.
What is NOT retracted, measured rather than asserted on the landed bytes: the §9 fleet-truth
conservation guard and the §9.2 COUNT+TUPLE floor conservation both re-run GREEN
(`test_cog4_fleet_truth.py` + `test_cog4_floor_conservation.py`, 29 passed) — no row moved OUT of the
manifest, no new row-less template plist appeared, and every composed organ keeps its own derived
floor. The composed-runner claim ("a persistently failing organ inside a live runner trips its own
floor") is untouched; the compose itself is untouched.
Re-measured on the landed bytes, not inherited: `verify-cognitive-phase4.sh` full green end-to-end
after this re-bind; census PASS at 54/50 with observed==max; layer-sep new=0; golden evals 29/29;
null-hatch PASS; `framework/` 6531 passed / 25 skipped / 1 failed (the single known pre-existing
`test_retro_shim.py::test_reexports_constants`, identical to the re-measured origin/master baseline)
and `cabinet/scripts/tests` 4686 passed / 28 skipped against a re-measured 6079be4d baseline
(6531/25/1 and 4670/28).
WHAT WAS NOT DONE, stated plainly: this was NOT re-reviewed by a fresh frozen COG-4 panel. The branch
carries its own artifact, `shared/interfaces/reviews/feat-arm-the-cabinet-cp1.md`, whose residual
section records the honest limits of that unit — two rows the Captain asked for that were verified off
for a REAL reason and left off, and one ruling (drafting to act-then-tell) that could not ship because
its file is germline and is filed as CG-35 instead.
SIBLING BINDERS: `cabinet/config/cognitive-architecture-contract.yml` sits in the COG-0/1/2/3
EXPECTED_SCOPEs too, so this landing moves those digests as well. They are NOT re-bound and must not
be: all four were ALREADY BLOCK on pre-change master 6079be4d — measured, not assumed, by running each
verify twin in a detached worktree there (all exit 1; recorded digests COG-0 f543dc1e, COG-1 25c2f5e3,
COG-2 b38632b9, COG-3 78a7bf18). COG-4 was the one binding GREEN on 6079be4d (verify twin exit 0) and
the only one this landing turned BLOCK, so it is the only one re-bound. This commit edits ONLY the
digest-excluded review artifact, so the digest it records is stable under its own landing.)
RE-BOUND AFTER MERGING origin/master 888255b6 (2026-07-27, 0305f77547e14563c1a8505c14336ec4e8993fbc133217ce81136f7e4c5c4ce5 -> the value above): the merge brought a concurrent landing's own re-bind of this same artifact, so the two digest lines conflicted textually while BOTH landings' in-scope deltas were additive and disjoint. Resolved by recomputing over the MERGED committed tree rather than by picking a side — a hand-picked digest from either parent would have recorded a tree that never existed. Still a MECHANICAL-DELTA re-bind, never a restamp: ZERO COG-4 engine, organ, scheduler, projection or trajectory bytes are touched by this branch; its only in-scope path remains cabinet/config/cognitive-architecture-contract.yml (the two census allowance rows). Census re-measured on the merged bytes; verify-cognitive-phase4.sh re-run green after this re-bind.)

(RE-BOUND BY THE ARM-THE-CABINET LANDING REVIEW, 2026-07-26 — 77df1746138bb26148bed68ccbed438e5291da65a7ac4ee1ec1002366f35880e
-> the value above. Mechanical, and the reason is stated before the claim: this binding was ALREADY
BLOCK on origin/master before this branch existed. Master carries the ORIGINAL
93839d991e56db1fe048e1df97774e1dd4b248f0071d90171979d38ab08109d4 while computing
e7fccd9b622f479d1f098962778163725a88927fde1bb85394496463f2b2dbe4 (measured on master a55dea44,
`verify-cognitive-phase4.sh` exit 1) — PR #210 moved an in-scope path and did not re-bind. This
landing does not inherit that red; it closes it.
EXACTLY TWO in-scope paths moved since the re-bind above, verified by intersecting the resolved
85-entry scope with `git diff --name-only 9883f270..HEAD` rather than by reading the diff:
  (1) `cabinet/config/cognitive-architecture-contract.yml` — the captain-availability dial's two
      allowance rows (from master, PR #210) plus this review's own
      `framework_production_noncomment_lines` 60155 -> 60164 re-pin (+9 measured), still
      observed==max with zero headroom.
  (2) `cabinet/scripts/egg-export-manifest.txt` — the availability dial's delete + expect-present
      pair (from master, PR #210).
NO COG-4 implementation path moved: not `framework/projection`, `framework/scheduler`,
`framework/organs`, no organ manifest, no runner, no measurement surface, no fixture. The behavior
this review's verdict covers is byte-untouched, so this is a scope-membership re-bind and NOT a
behavior-delta re-bind like the entry above it.
WHAT WAS NOT DONE, stated plainly: no fresh frozen COG-4 panel ran. What DID run, on the landed
bytes: `verify-cognitive-phase4.sh` green end-to-end after this re-bind; census PASS at 54/50/67423
observed==max; layer-sep new=0; import gate exit 0; golden evals 30/30; A13 ledger parity GREEN
(353/353, 0 findings); null-hatch PASS; `framework/` 6573 passed / 25 skipped / 1 failed and
`cabinet/scripts/tests` 4711 passed / 28 skipped — the single failure being the known pre-existing
`test_retro_shim.py::test_reexports_constants`, identical to a re-measured origin/master a55dea44
baseline (6573/25/1). The landing review's own findings — a role_slug traversal that let the ARMED
loop rewrite an arbitrary tracked .yml, and a phantom journal row whose advertised inverse removes a
capability the loop never granted — are fixed in this same branch with ten arms that fail against the
pre-fix module.
SIBLING BINDERS unchanged from the note above: COG-0/1/2/3 were already BLOCK on pre-change master and
are NOT re-bound here.)

(MERGE RE-BIND, 2026-07-26: `fix/attention-silence-ratchet` (PR #211) landed on master while this
branch was in review and re-bound this same digest to 41a85f9e...'s sibling
a30366943126b05011435269b1f72335a4455bd8f0fbfd1518a426ab462c2df2. Two concurrent landings cannot both
be right about one number, so it is recomputed over the MERGED tree rather than either side being
picked: 0305f77547e14563c1a8505c14336ec4e8993fbc133217ce81136f7e4c5c4ce5. The digest line was the ONLY merge conflict in this
artifact; both landings' notes above are preserved verbatim, neither overwritten. In-scope paths
carried in by that merge: the census contract (its attention allowance) — no COG-4 implementation
path, so this stays a scope-membership re-bind. `verify-cognitive-phase4.sh` exits 0 on the merged
tree.)

(RE-BOUND BY THE CAPTAIN-DATES LANDING, 2026-07-27 — 0305f77547e14563c1a8505c14336ec4e8993fbc133217ce81136f7e4c5c4ce5
-> 5615aae1867d54024ac851578e7970611e55ff7a2860bd83d7d879bb5f10f0aa, superseded by the merge note below. EXACTLY TWO in-scope paths moved, verified by intersecting the resolved 85-entry
scope with `git diff --name-only origin/master..HEAD` rather than by reading the diff:
  (1) `cabinet/config/cognitive-architecture-contract.yml` — one new
      `framework_production_noncomment_lines` allowance row for the dates store (+208 measured; the
      env.py resolver family plus the morning_synthesis briefing leg, ZERO new modules), re-measured
      OVER THE MERGED TREE at 67883 vs 67675 base, still observed==max with zero headroom.
  (2) `cabinet/scripts/egg-export-manifest.txt` — the dates store's `delete` +
      `expect-present` pair, the same shape the availability dial added.
NO COG-4 implementation path moved: not `framework/projection`, `framework/scheduler`,
`framework/organs`, no organ manifest, no runner, no measurement surface, no fixture. The behavior
this review's verdict covers is byte-untouched, so this is a SCOPE-MEMBERSHIP re-bind, not a
behavior-delta one.
WHAT WAS NOT DONE, stated plainly: no fresh frozen COG-4 panel ran. What DID run on the merged bytes:
`verify-cognitive-phase4.sh` green end-to-end after this re-bind; census PASS at 54/50/67883
observed==max; layer-sep new=0; state-persistence 0 UNACCOUNTED; docs-track-code GREEN; A13 ledger
parity GREEN (353/353); golden evals 30/30 (EVAL-027 included, extended by this landing and shown RED
against pre-change state first); `framework/` 6653 passed / 26 skipped / 1 failed and
`cabinet/scripts/tests` 4727 passed / 28 skipped / 1 failed — the framework failure being the known
pre-existing `test_retro_shim.py::test_reexports_constants` (a locally-installed pipe constant CI does
not have), and the cabinet one a wall-clock latency bound over an ephemeral Postgres cluster that
passes in isolation under no load.
SIBLING BINDERS unchanged: COG-0/1/2/3 were already BLOCK on pre-change master and are NOT re-bound
here. This commit edits ONLY the digest-excluded review artifact, so the digest it records is stable
under its own landing — verified by recomputing after the edit.)
(RE-BOUND 2026-07-27, `fix/hook-redos`, same commit as the change that moved the
bytes. The moved file in scope is `cabinet/config/cognitive-architecture-contract.yml`:
ONE `temporary_allowances` row paying for the +1 framework line of
`policy_engine._STMT_RUN`, the rewrite that removes catastrophic backtracking from
the `sed -i` write pattern (52 of 80,307 recorded officer calls exceeded 1.5s in it,
and the hook has no time bound). The COG-4 findings are unaffected — no organ, no
scheduler surface, no serve surface, no COG-4 entry point. The landing's other two
files, `framework/authority/policy_engine.py` and `cabinet/scripts/policy-shadow.py`,
are not in EXPECTED_SCOPE. Reviewed in `fix-hook-redos-cp1.md`, with equality proved
in both directions and re-checked over all 80,307 recorded calls: 0 verdict changes.)

(MERGE RE-BIND, 2026-07-27: the spend-meter landing (PR #215) reached master while this branch was in
CI and re-bound this same digest to 540c08fb.... Two concurrent landings cannot both be right about one
number, so it is recomputed over the MERGED committed tree rather than either side being picked — a
hand-picked digest from either parent would record a tree that never existed. Merged value:
e68adad9456b80394270fa6354b65d6f4a5de10162235232b787571e1e3e2b0a. The digest line was the ONLY conflict in this artifact;
both landings' notes above are preserved verbatim, neither overwritten. In-scope paths carried in by the
merge: the census contract (the spend meter's two allowance rows) — no COG-4 implementation path, so this
stays a scope-membership re-bind. Census re-measured on the merged bytes: PASS at 243 modules / 68661
lines, observed==max with zero headroom, the dates row still +208. `verify-cognitive-phase4.sh` re-run
green end-to-end on the merged tree after this re-bind.)

(MOVED BY THE CHANNEL-FLATLINE ALARM LANDING, 2026-07-27 —
e68adad9456b80394270fa6354b65d6f4a5de10162235232b787571e1e3e2b0a -> the value above. Branch
`feat/channel-flatline-alarm` (PR #224), one commit b7dcde05 over master 19d1c2e1: a captain-facing
channel that goes silent now says so once, per Captain-Seat dry-run finding 2.
A SCOPE-MEMBERSHIP re-bind, and the claim is made here because it holds. EXACTLY ONE in-scope path
moved, verified by intersecting the resolved 85-entry scope with
`git diff --name-only origin/master...HEAD` (12 changed files, one in scope) rather than by reading
the diff: `cabinet/config/cognitive-architecture-contract.yml` gains TWO `temporary_allowances` rows
(`framework_production_modules` +1, `framework_production_noncomment_lines` +390) for the new
`framework/frontdoor/card_flatline.py` detector and its two delivery seams. That file is not a COG-4
surface; it is bound only because the census contract sits in the declared scope — the same class as
the spend-meter (a3036694), attention-well-spent (3dcd3e62) and contact-liveness (598868ed) re-binds
above. NO maximum was relaxed and no threshold touched: the census re-measures PASS at 244<=244
modules and 69051<=69051 lines, exact totals, zero headroom preserved.
NO COG-4 implementation path moved: not `framework/projection`, `framework/scheduler`,
`framework/organs`, no organ manifest, no runner, no measurement surface, no fixture, no boundary row.
The eleven other changed paths sit OUTSIDE this scope and are named for the record: the new detector,
probe, runbook and two test modules; `framework/frontdoor/{tell_digest,run_briefing}.py`;
`cabinet/scripts/cabinet-doctor.sh` (a new check 16); `cabinet/scripts/docs-sweep-allowlist.txt`;
the root `conftest.py` (one new read fence); and this landing's own FW-019 proof
`feat-channel-flatline-alarm-cp1.md`.
Re-measured on the branch bytes, not inherited: `verify-cognitive-phase4.sh` full green end-to-end
after this re-bind; census 29 passed; `cabinet/scripts/tests` 4768 passed / 28 skipped;
`framework/` 6748 passed with the one declared pre-existing red
(`test_retro_shim::test_reexports_constants`, a locally-installed pipe constant CI does not have)
reproduced identically on pristine master.
NOT re-reviewed by a fresh frozen COG-4 panel; the branch carries its own FW-019 artifact.
SIBLING BINDERS NOT TOUCHED, deliberately: the contract yml also sits in the COG-1/2/3 scopes, all
three of which were ALREADY BLOCK on pristine master before this branch existed. Re-binding them
would restamp frozen gate archaeology. This commit edits ONLY the digest-excluded review artifact, so
the digest it records is stable under its own landing — verified by recomputing after the edit.)

Verdict: PASS

MOVED BY THE MATRIX-CLASS-MAPPING-PIN LANDING (2026-07-27,
e68adad9456b80394270fa6354b65d6f4a5de10162235232b787571e1e3e2b0a -> the value
above). MECHANICAL-DELTA re-bind: exactly ONE in-scope path moved,
`cabinet/config/cognitive-architecture-contract.yml`, and the only change to it
is one appended `temporary_allowances` row (`matrix-class-mapping-pin`,
framework_production_noncomment_lines +65, 68661 -> 68726). No reviewed BEHAVIOUR
byte changed: the branch's executable changes are all in
`framework/authority/{matrix,classifier,deploy_classifier}.py` and
`framework/authority/tests/test_matrix.py`, none of which is in this scope
(verified by intersecting `git diff --name-only origin/master...HEAD` against
the tool's resolved EXPECTED_SCOPE, not by reading the diff).

RE-MEASURED, not assumed: `cognitive-architecture-census.py --check` PASS at
observed == max (68726 <= 68726), and the full `verify-cognitive-phase4.sh`
twin runs end-to-end green on this commit. The digest was recomputed over the
COMMITTED tree and folded into the SAME commit — this artifact is excluded from
its own scope, so the amend is stable under itself. NOT done: no COG-0/1/2/3
twin was re-bound (frozen-historical, already BLOCK by design), and no prose
section of this review was edited — no reviewer saw new bytes, because none of
the reviewed bytes changed behaviour.

RE-BOUND ON THE MASTER MERGE, 2026-07-27 —
8421cbabbc5331087530603011d139ae0acfdd4d82cfeed45f95006ffa171f82 -> the value
above. The matrix-class-mapping-pin branch merged origin/master 91412878
(fail-closed-control-plane, channel-flatline-alarm, ask-batching and
dashboard-availability landings). Both sides had appended a
`temporary_allowances` row to `cabinet/config/cognitive-architecture-contract.yml`,
the one in-scope path either side touched; the conflict was resolved by keeping
BOTH rows, and the branch's own row was RE-MEASURED against the new base rather
than carried (69116 vs 69051 at 91412878; +65 unchanged, since the growth is
that unit's own lines). Still a MECHANICAL-DELTA re-bind: no reviewed BEHAVIOUR
byte changed on either side of the merge.

MOVED BY THE RECIPIENT-ALL-INTERNAL-QUANTIFIER LANDING (2026-07-27,
7f05bdcfaa716f78a9fb638ab464d5fd41699a388e9c13107957fdc128ca7e35 -> the value
above). MECHANICAL-DELTA re-bind: exactly ONE in-scope path moved,
`cabinet/config/cognitive-architecture-contract.yml`, and the only change to it
is one appended `temporary_allowances` row
(`recipient-all-internal-quantifier`, framework_production_noncomment_lines
+13, 69116 -> 69129). No reviewed BEHAVIOUR byte changed: the branch's
executable changes are all in `framework/authority/classifier.py` and
`framework/authority/tests/test_classifier.py`, neither of which is in this
scope — verified by intersecting `git diff --name-only origin/master...HEAD`
against the tool's resolved scope, not by reading the diff (the intersection is
exactly the contract file).

RE-MEASURED, not assumed: the old digest above was recomputed over HEAD rather
than carried from the previous re-bind note (master moved between them), and
`cognitive-architecture-census.py` is PASS at observed == max (69129 <= 69129).
The digest was recomputed over the COMMITTED tree and folded into the SAME
commit — this artifact is excluded from its own scope, so the amend is stable
under itself. NOT done: no COG-0/1/2/3 twin was re-bound (frozen-historical,
already BLOCK by design), and no prose section of this review was edited — no
reviewer saw new bytes, because none of the reviewed bytes changed behaviour.

RE-BOUND 2026-07-27 by the `feat/personal-preset-live` landing: 3188bf08… -> 26528114….
(First bound at b3523559… -> e7926158…; RE-MEASURED after merging origin/master,
whose `fix/propose-means-propose` landing moved the same two in-scope files
mid-flight. The merge kept BOTH allowance blocks — neither landing's row was
dropped — and the branch census re-reads PASS at observed == max against every new
baseline (6e50570f, then 8095ded9 after the hook-redos landing), with the module
delta exactly +1/+331 each time, which is the check that the number measures
this module and not a merge.)
ONE in-scope surface changed, `cabinet/config/cognitive-architecture-contract.yml`
(it sits in `restore_from_baseline` and is therefore digest-bound), and the change
is two `temporary_allowances` rows plus one `expansions` row paying for
`framework/sources/local.py` — the local-folder PersonalSource that unblocks
`presets/personal/`. NO COG-4 implementation byte changed: intersecting
`git diff --name-only origin/master...HEAD` with the tool's resolved scope yields
exactly the contract file. `cognitive-architecture-census.py` is PASS at
observed == max (245 <= 245 modules, 69985 <= 69985 lines) with the expansion row
registered. The digest was recomputed over the COMMITTED tree and folded into the
same landing; this artifact is excluded from its own scope, so the edit is stable
under itself.

NOT done: the COG-0/1/2/3 twins were NOT re-bound, which is the state the
`cognitive-phase4` CI job's own scope note already records ("the phase-0/1/2/3
twins are the digest-frozen HISTORICAL instances their own docstrings describe,
and all of them are already BLOCK on master by design"). Re-measured here on a
clean clone of `origin/master` at 91faed1b, before this branch existed: phase 0
f543dc1e -> 268e01b4, phase 1 25c2f5e3 -> 3168b0b1, phase 2 b3863291 ->
ae79b6e2, phase 3 78a7bf18 -> fde71324, and phase 4 clean. Re-binding a frozen
historical twin here would absorb earlier landings' drift under this one's name
and bless bytes no reviewer on this branch has read, so they are left as they
were.

RE-BOUND 2026-07-27 by the `feat/personal-preset-live` landing: 9c1a8082… -> 8bee10cd….
ONE in-scope surface changed, `cabinet/config/cognitive-architecture-contract.yml`
(`restore_from_baseline`, therefore digest-bound): two `temporary_allowances` rows
plus one `expansions` row paying for `framework/sources/local.py`, the
local-folder PersonalSource that unblocks `presets/personal/`. NO COG-4
implementation byte changed — intersecting `git diff --name-only
origin/master...HEAD` with the tool's resolved scope yields exactly that file.
RE-MEASURED on every merge rather than carried: master moved four times while
this branch was in flight, and the census re-reads PASS at observed == max
against each new baseline with the module delta exactly +1/+331 every time
(d7c66fe2 70434 -> 70765), which is the check that the number measures this
module and not a merge. The concurrent `feat/source-ownership-class` landing
edited the same contract and the same census tests; BOTH landings' allowance and
expansion rows are kept (verified by set-difference against
`origin/master`, zero rows lost), and this branch took master's census-test
version wholesale — its bijection assertion is strictly stronger than the
"no unregistered surplus" form this branch had written for the same defect, and
it additionally catches a row that outlives its member.

---

## Re-bind 2026-07-27 (merge of origin/master into iso-port-composition)

The gate blocked correctly — reviewed bytes were not tested bytes — and this records why
the digest moved rather than quietly restamping it.

Three of the 85 in-scope paths changed, and NONE of them by this branch. All three are
master's own commits arriving through the merge, each already reviewed on its own PR:

  cabinet/config/cognitive-architecture-contract.yml  — the expansion-gate set pins
      (D3, 2026-07-27), adding budget arms for the surfaces the mass budgets are blind to
  cabinet/scripts/egg-export-manifest.txt             — the recipient-exclusions and
      expansion-registry rows
  cabinet/scripts/tests/test_egg_export.py            — the matching assertion for the
      recipient-exclusions twin

Nothing in this branch's own work touches the COG-4 scope: it is the world layout, the
renderer and the check harness. The digest is re-anchored over the merged tree so the
binding again means "these exact bytes were reviewed", with the delta named above rather
than absorbed silently.

Recorded digest: dbdf515ca91c7f4c9d618b9029af44e8cb02e626123738c4df230dabf7f90300
Previous:        9c1a8082d1d6348f345e3aad1faee87fef59e98d3538b08fe9c1f130dce5d68d

SUPERSEDED 2026-07-28 — the `dbdf515c…` above is HISTORY, not the live binding. It is
kept because it records what was reviewed at that merge; the live value is the single
`Reviewed-Scope-Digest:` line at the top of this file, recomputed over the 2026-07-28
merge of `origin/master` dd01ce8f. Both this branch's note and the master-line notes
above it survive that merge verbatim: they describe different landings and neither is
the other's restamp.

---

## Re-bind 2026-07-28 (merge of origin/master dd01ce8f into iso-port-composition)

PR #223 had been CONFLICTING for days. An unmergeable PR gets no checks at all, so this
artifact's own gate — and every other gate on the branch — had been silently OFF the
whole time; the merge is what turns them back on. That is the finding worth recording:
the digest did not drift unnoticed, it went UNCHECKED, which is the worse failure of the
two and is invisible from a green-looking PR page.

The conflict here was in this file only, and it was two append-only note histories
colliding, not a contested byte. Resolution kept BOTH sides in full — verified by
`grep -c` for each side's marker strings in the merged file, so the claim is a count and
not a reading — and the digest was RECOMPUTED over the merged tree rather than either
side's value being carried, since both sides' values are digests over trees that no
longer exist.

The in-scope delta and why it is mechanical are stated with the digest at the top of
this file. Nothing was re-reviewed and no prose finding was edited, because no reviewed
byte moved: the branch's entire diff is the world layout, the renderer, the hit test and
the check harness, none of which is in the COG-4 scope.
