# Checkpoint review — test/persona-employee-slice cp1

Branch: `test/persona-employee-slice`
Date: 2026-07-26
Model: Opus 5
Churn: over the 300-line FW-019 threshold (fixture + report + tests)

## What the change is

A fourth Onboarding v2 fixture estate, shaped as an employee's slice of a
large organisation (a service repo they contribute to but do not own, a tracker
CSV export, a partial docs-space sync), plus the measurement it was built to
produce and the tests that keep that measurement in the suite rather than in a
report nobody re-runs.

Deliverable report: `docs/persona-employee-slice-2026-07-26.md`.

## Files

| Path | Change |
|---|---|
| `framework/onboarding/fixtures/enterprise-employee/**` | New. 15 synthetic files across three simulated systems. |
| `framework/onboarding/fixtures/README.md` | Documents the fourth estate and forbids tuning it toward the detectors. |
| `framework/onboarding/tests/test_journey.py` | Five new tests: three driving the estate through the real `journey.act` path (finding, finding-count measurement, anti-tuning guard) and two pinning the cap behaviour. |
| `docs/persona-employee-slice-2026-07-26.md` | New. The measurement and its verdict. |

## Adversarial pass over my own change

**Did I weaken a test?** No. Every pre-existing test is byte-identical;
`evaluate_personas.py`, `test_evaluate_personas.py` and the architecture
contract are byte-identical to master. The change is additive: five new tests
and a fixture directory.

**Why is the estate not registered as a fourth acceptance persona?** It was,
and the registration was reverted mid-review. `evaluate_personas.py` is a
framework production module and `framework_production_noncomment_lines` is
pinned at observed==max with zero headroom, so one line reds the census. The
contract's `temporary_allowances` mechanism would carry it — an entry of
`additional: 1` was written and verified green — but
`cabinet/config/cognitive-architecture-contract.yml` sits inside
`EXPECTED_SCOPE`, so editing it invalidates the frozen COG-4
`Reviewed-Scope-Digest` and `verify-cognitive-phase4.sh` blocks with "reviewed
bytes != tested bytes". Re-stamping that digest would record a review of bytes
no reviewer saw. The registration was therefore dropped rather than the gate
bent, and the estate is exercised from a tests path instead, which costs
nothing and drives the same `journey.act` calls the harness drives. Recorded in
the report §1 because it will block the next person too.

**Are the estate assertions tuned to the output?** The kind and citation
assertions pin what the detectors actually produce, not what I wished for —
those differ, and that difference is the measurement. The anti-tuning test
inverts the usual direction: it asserts each planted cross-system fact is
still present in the bytes and still absent from the findings, so making the
fixture more detector-friendly trips it.

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

**Did I change any behaviour?** No. Not one file under a production path
differs from master: the change is a fixture directory, tests, a fixtures
README and a report.

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
