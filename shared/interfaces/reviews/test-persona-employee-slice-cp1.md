# Checkpoint review — test/persona-employee-slice cp1

Branch: `test/persona-employee-slice`
Date: 2026-07-26
Model: Opus 5
Churn: 553 added / 5 removed = 558 (over the 300-line FW-019 threshold)

## What the change is

A fourth persona for the Onboarding v2 acceptance harness, shaped as an
employee's slice of a large organisation (a service repo they contribute to
but do not own, a tracker CSV export, a partial docs-space sync), plus the
measurement it was built to produce and two tests pinning the uncomfortable
half of that measurement.

Deliverable report: `docs/persona-employee-slice-2026-07-26.md`.

## Files

| Path | Change |
|---|---|
| `framework/onboarding/fixtures/enterprise-employee/**` | New. 15 synthetic files across three simulated systems. |
| `framework/onboarding/fixtures/README.md` | Documents the fourth estate and forbids tuning it toward the detectors. |
| `framework/onboarding/evaluate_personas.py` | Registers the persona; docstring no longer says "three". |
| `framework/onboarding/tests/test_journey.py` | Persona-list assertion extended 3 → 4; test renamed count-agnostic; two new cap tests. |
| `framework/onboarding/tests/test_evaluate_personas.py` | Docstring follows the rename. |
| `docs/persona-employee-slice-2026-07-26.md` | New. The measurement and its verdict. |

## Adversarial pass over my own change

**Did I weaken a test?** No. `test_three_persona_evaluation_harness_is_executable`
was renamed to `test_persona_evaluation_harness_is_executable` and its exact
ordered-list assertion extended from three entries to four. It asserts strictly
more than before. The red-path suite in `test_evaluate_personas.py` is
untouched apart from a docstring following the rename; it still proves the
acceptance gate can report failure.

**Is `expected_kind: software_command_drift` a tuned assertion?** Yes, and it
is declared as such in a comment at the registration site. It pins what the
detectors *actually* produce, not what the estate's most valuable fact is —
those are different things, and the report says so. The alternative (pinning
the kind I wished for) would be a vacuous gate.

**Did I tune the fixture until it produced findings?** No. Eight predictions
were registered in writing before the first execution, including two
predictions of *misses*; all eight landed on the first run and no fixture
content was changed afterwards. The authoring-bias disclosure in the report
names the two elements placed with detector knowledge rather than hiding them.

**Are the new cap tests real sensors or tautologies?** Two arms over the same
tree: uncapped, `_command_drift` fires and the dividend is
`software_command_drift`; capped to three files, the pair is split, the
detector returns `[]`, and the dividend is `orientation_map`. The control arm
fails if the capped arm's premise is wrong, and vice versa. The capped arm also
pins the two properties that make the behaviour dangerous rather than merely
limited — that the card carries no truncation wording, and that
`scan_statistics` reports `candidate_files == included_files` with zero
exclusions. Any coverage, ranking or disclosure fix flips it, which is the
point.

**Degenerate ends.** The capped arm *is* the degenerate end (a window smaller
than the estate). Zero-file and empty-window behaviour is already covered by
the existing `empty_window` path in `_first_dividend`, untouched here.

**Is the sensor wired to the live artifact?** The tests call
`journey._scan_source`, `journey._command_drift` and `journey._first_dividend`
— the same functions `journey.act` calls on the production path. The persona
harness runs the real `journey.act` end to end via subprocess.

**Did I change any behaviour?** No production code path was modified. The
change is a fixture, a persona registration, tests and a document.

## Verification run against the committed tree

Recorded in the PR body and the task return. Local battery run serially from
this clone with `__pycache__` purged and `PYTHONDONTWRITEBYTECODE=1`, using
`python3.12`, against the committed tree — not the working tree, since the
whole-tree ratchets and the phase-4 gate read `git ls-files` and HEAD.

## Residual risk

- The fixture is synthetic and authored by someone who had read the detectors.
  It is evidence about the detector vocabulary, not a survey of real employee
  estates. The report states this in §8 rather than burying it.
- `evaluate()` requires `quality == "strong"` to pass, so the harness still
  cannot express an honest orientation-only persona. Flagged in the report §7
  as worth fixing before more personas are added; not fixed here, because
  changing the pass predicate is a behaviour change that deserves its own
  review rather than riding along in a fixture commit.

Verdict: PASS
