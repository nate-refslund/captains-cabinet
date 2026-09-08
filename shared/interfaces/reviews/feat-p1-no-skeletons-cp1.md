# Checkpoint review — feat/p1-no-skeletons (phase-1 unit U6), cp1

Reviewed-Scope-Digest: c2f8c741da3ea4d2b1c0fdc1349b72b2307cb0482066cdf5eaa1a1a8400bd6a6

Contract of record: phase-1 contracts v2 (2026-09-07) §6 + amendment A6.1,
with arm A §6 and arm B §6 as the normative sensor set (B's "templates carry
no `<TODO:`" rider is withdrawn by A6.1).

## What the change is

A pattern the role-evolution generator has no concrete candidate for stops
becoming a form. `propose_one` returns `None`, writes no file and emits no
`role_charter_changed`; it records ONE keyed capability gap
(`dedup_key = evolution:<role>:<failure_type>`, kinds per the contract's MAP)
and reports it through the new `gaps_out` accumulator. The loop's report gains
`gaps_recorded` and `skipped_skeleton`.

## What I attacked, and what it found

1. **Is the invariant true for every template, or only the two the amendment
   names?** It was not. `quality_gap`'s placeholders were written `<TODO>`
   with no colon, so `TODO_RE` (`<TODO:[^>]*>`) never matched them and
   `_proposal_is_concrete` returned `ok` for a template-derived
   `add_quality_hat` amendment — auto-applicable today, before this change.
   The A6.1 sensor is parametrized over EVERY shipped template precisely so
   this could not hide; the fix completes the two malformed markers rather
   than special-casing the kind.
2. **Does the sensor stay armed after the change?** Stripping the `<TODO:`
   markers from the templates (the withdrawn rider) turns
   `test_no_template_derived_amendment_is_auto_applicable` red for
   `missing_skill` (add_hat), `wrong_authority` (expand_authority) and
   `quality_gap` — recorded in the PR body. A sensor green in both directions
   would have been a disabled sensor.
3. **Does `skipped_skeleton` become a key nothing can produce?** It would
   have. It is wired to two live producers instead: a skeleton FILE already on
   disk at the gap's own path (`existing_skeleton`), and the loop's own
   non-concrete branch. `test_a_pre_existing_skeleton_file_is_reported_not_
   rewritten` drives the first one to 1; a fresh root reads 0.
4. **Does the dry-run preview still tell the truth?** It did not: it reported
   `skipped_skeleton` / `would_stay_pending` for a pattern the live pass now
   records as a gap. Both preview branches name `would_record_gap`, with the
   ledger-untouched assertion kept.
5. **Is the write path de-armed?** No. `_proposal_is_concrete`, the validation
   gate and the mutation surface are untouched; two pins (a concrete template
   writes and emits; a template-derived proposal put on disk by another writer
   is still refused by the apply path) are green in both directions.

## Blast radius

`framework/roles/evolution.py` (+65 non-comment), `self_improvement_loop.py`
(+18), three test suites, one cron comment that documented the old behaviour,
and the line-budget maximum raised by exactly the measured +83. No locked path
is touched (checked against the parsed `germline-lock.sh` FILES/DIRS). No new
event type, no new module, no new UI.

## Residuals

* `propose_from_patterns` returns written proposals only, so the gap count
  reaches the loop through an out-parameter. A richer return type would have
  changed a shape the contract pins.
* The CLI's `--json` output becomes an object (`{proposals, gaps}`) so a run
  whose patterns all became gaps stops printing `[]`. No consumer in the tree.
