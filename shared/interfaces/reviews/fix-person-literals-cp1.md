# fix/person-literals — cp1

Reviewed-Scope-Digest: 807afd220db2740bdfcdfaf132d815309fc2821477dbdf25e4a13ab452b2cee4

## What this commit does

Two jobs, and the second is the one that lasts.

1. **Removes the operator's personal name from the framework layer.** Fifteen
   occurrences, measured: `framework/onboarding/research.py` (one docstring
   example), `framework/onboarding/tests/test_who_and_when.py` (five),
   `framework/authority/classifier.py` (two), its tests (one),
   `framework/acting/tests/test_action_lane.py` (one), `framework/env.py`
   (one), `framework/tests/test_amendment_doc_lint.py` (three),
   `framework/tests/test_env.py` (one). Every example becomes an
   obviously-synthetic placeholder: a metavariable (`<display> <user@<org>>`),
   an alphabet handle (`abcd`), or one of the synthetic fixture people the
   framework already uses (`Ada`, `Bo`, `Otto`).

2. **Makes the gate able to catch the next one.** Arm 3 of
   `framework/tests/test_no_launcher_hardcode.py` — the person ratchet. Arm 1
   pinned a SYNTHETIC token (`Testburg`) and so could only ever prove the
   placeholder absent; it was green over all fifteen. Arm 3 DERIVES the
   operator identity from what the repository and its instance layer declare
   about themselves — the licence copyright holder, the repository owner handle
   in the plugin manifests, and the instance layer's declared `captain_name` /
   onboarding identity — and forbids those tokens anywhere under `framework/`,
   tests and undated docs included. No list of names anywhere; the seeds all
   sit OUTSIDE `framework/`, so cleaning the subject can never blind the rule.

## Verification

* Reverse direction, cache purged: with the fifteen literals restored to their
  master text, `python3.12 framework/tests/test_no_launcher_hardcode.py --check`
  exits 1 and prints all fifteen with the surface each token was derived from.
  With them removed it exits 0.
* `pytest framework/tests framework/authority/tests framework/onboarding/tests
  framework/acting/tests -q` → 3699 passed, 2 skipped.
* `pytest framework/tests/test_no_launcher_hardcode.py -q` → 64 passed
  (43 on master; 21 new).
* `cabinet/scripts/check-layer-separation.sh` → OK, new=0.
* `cognitive-architecture-census.py` → PASS, every budget unchanged
  (framework_production_noncomment_lines 75972 <= 75972 — the three production
  docstring edits are line-count neutral, so no budget is raised).
* `pytest cabinet/scripts/tests/test_cognitive_architecture_census.py
  test_baseline_set_ratchet.py -q` → 166 passed, 6 skipped.
* `pytest cabinet/scripts/tests/test_agnosticism_advisor.py test_docs_sweep.py
  test_declared_residuals_register.py test_preset_developer_parity.py
  test_null_hatch_staging.py -q` → 80 passed.

## Judgement calls a reviewer should attack

* **The amendment lint lost a name and gained a shape.** Three anchors in
  `test_amendment_doc_lint.py` asserted a `**Captain:**` line spelling the operator's name, in a
  live amendment doc. Weakening them to `**Captain:**` alone would have traded
  a leak for a hole, so the value is now pinned separately by shape
  (`_ATTRIBUTED_RX`, non-empty, same line) and that predicate was proven
  against the degenerate cases before landing.
* **Dated design snapshots under `framework/docs/` are excluded**, on the same
  predicate Arm 2 uses and for the reason the egg manifest already ratified
  (R162 + R145: those files are the launching deployment's own minutes, are
  archived OUT of the egg, and rewording a dated record falsifies it). 70
  operator-name occurrences live there. A stranger never receives those bytes;
  a reader of the public repository does. That is a disclosure, not a defence.
* **Glued compounds are invisible**, deliberately and in line with Arm 1
  (`nate_model`, `owed_to_nate`, `ask_nate`): 95 occurrences across 23 files.
  They are a real agnosticism defect and a separate coordinated-rename unit
  with a byte-compat surface.
* **What it cannot see is in the docstring, not in a footnote** — a proper noun
  that is not the operator's (framework's own fidelity fixtures carry 27
  display-name literals this arm reads as green), a non-Latin identity, a
  fragmented literal, a token under four characters, a flow-style declaration.
* **What it can get WRONG is stated too**: an operator whose name collides with
  ordinary framework vocabulary goes red on a tree they never touched. The
  remedy is the capped, empty, shrink-only exclusion set, exactly as in Arm 2.

## Provenance

Per the 2026-07-07 full-autonomy grant.
