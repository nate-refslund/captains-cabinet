# Checkpoint review — fix/residuals-cite-anchor-pin cp1

Reviewed-Scope-Digest: c1def0fbd866b9cb9181dde736564ba74e57f3f9a4b8e22a31a939989e89bfa9

Reviewer: fresh-context adversarial subagent, Opus 5 (1M), own read of a clean
clone of origin/master at `a0cd4bc1` with the change staged. Brief: attack it,
do not confirm it; re-run the battery yourself; hunt for a disabled sensor;
audit every anchor independently of the module's own code.

## Verdict

`changes-requested` on the reviewed bytes → **all findings addressed**, then
re-proved by mutation. The verdict below records what was found and what
closed it; the digest above binds the FINAL bytes, which include the fixes.

## What the change does

`docs/plans/declared-residuals-register.md` cited each declared residual by
`path:line`, and the pin test asserted the anchor text sat AT that line. One
cite (`RES-007`) points into `shared/interfaces/reviews/cognitive-core-phase-4-review.md`,
a digest-bound FROZEN artifact that cannot be edited in place: every re-bind
ceremony appends a note ABOVE its findings table, so the cited P1 row moves down
without changing a byte.

The chain forcing those re-binds was verified from `resolve_scope()` and the
contract, not taken on report: `framework_production_noncomment_lines` is
zero-headroom, so any framework production line needs a row in
`cabinet/config/cognitive-architecture-contract.yml`, which is entry 2 of the
14 in `restore_from_baseline` — so **every framework landing re-binds that
digest**.

Cites are now PATH + one ANCHOR per path; the test derives the line by search.
Zero matches is RED, more than one is RED, and a `path:line` cite is refused at
parse time so the format cannot come back by copy-paste.

## Findings and disposition

| # | severity | finding | disposition |
|---|---|---|---|
| 1 | should-fix | The diff broke a line-pinned cross-reference INTO the register — `cabinet/config/state-persistence-policy.yml` read `declared-residuals-register.md :340`, and the added prose moved `RES-016` to `:381`. Self-inflicted instance of the exact rot the branch abolishes, and nothing machine-checks it. | FIXED — the cross-reference now cites the row id and says why it carries no line. |
| 2 | should-fix | `RES-007`'s anchor `Shadow-log replay window` is 24 chars of generic prose in the ONE artifact that cannot be edited to disambiguate. Proved ambiguous under a plausible future re-bind note mentioning the phrase → `AMBIGUOUS … matches 2 lines [61, 668]`. | FIXED — anchor extended to `` `\| P1 \| NOTE \| Shadow-log replay window` `` (1 occurrence; `\| P1 \| NOTE \|` occurs once in the file). Re-proved: same insertion → GREEN with the long anchor, RED with the short one. |
| 3 | should-fix | Four tag-only anchors (`RES-016`, `RES-019`, `RES-020`, `RES-021`) match the exact string a cross-REFERENCE to the row would use. | FIXED — all four extended with declaration-specific prose; each verified to occur exactly once. |
| 4 | note (proven regression) | HOLE-B: with a tag-only anchor a row can outlive its declaration silently. Delete `RES-020`'s declaration from `memory/golden-evals/framework/fw-a14-stop-guard.sh`, leave `# see RESIDUAL (RES-020) in the declared-residuals register` → reviewed bytes GREEN where pre-change code went RED. That file is outside `SWEEP_ROOTS`, so anchor resolution is the only sensor. | FIXED by 3, and re-proved here: the identical mutation now fails with `anchor … is ABSENT`. |
| 5 | note | `test_code_cites_sit_on_a_house_marker` is near-tautological now — it checks a line derived by searching for a string that itself contains the marker token. Not vacuous (repointing an anchor to a unique non-marker line turns it RED) but its teeth depend on anchor choice. | RECORDED in the test's own docstring rather than papered over. |
| 6 | note | One failure in the reviewer's full-battery run, `test_cog1_outbox_capture.py::TestB1B2Baselines::test_baselines_hold_the_bound`, is a wall-clock perf bound that flaked under the loaded 11-minute run; passes isolated on both the patched and the pre trees. | Unrelated. Two independent full runs here were `5006 passed, 34 skipped`. |
| 7 | note | FW-019 artifact required (420 changed lines). | This file. |
| 8 | note | `LEGACY_EXEMPT` backticked as a live symbol in one doc line. | Already fixed before the review returned; the constant is `LEGACY_EXEMPT_ANCHORS`. |

Checked and found fail-closed, so NOT findings: a non-resolving cite dropping
out of `row["cites"]` makes the TREE→ROWS half MORE red, never less (two
sensors fire on each mutation); `_legacy_exempt_coords()` dropping an
unresolvable exemption likewise fires two; a wrapped `**Anchor:**` field cannot
silently truncate (unclosed backtick → zero spans → `_fail`, or a path/anchor
count mismatch → `_fail`); no ordering or `lru_cache` staleness hazard — each
of the nine tests passes standalone. The pin test is the only machine consumer
of the register's format.

## Mutation evidence — four arms, both directions, `__pycache__` purged per run

| arm | pre-change (`a0cd4bc1`) | post-change |
|---|---|---|
| anchor present exactly once | GREEN | GREEN |
| anchor deleted from the artifact | RED | RED — property preserved |
| anchor duplicated | **GREEN (undetected)** | RED — new capability |
| 30 lines inserted ABOVE the anchor | **RED** | GREEN — the motivating case |
| row flipped `retired` while its declaration is live | **GREEN (undetected)** | RED — new capability |
| `RES-020` declaration deleted, pointer comment left behind | RED (incidentally, via line shift) | RED — after finding 3/4 fixed |

The last two are strengthenings the change did not have to make.
`test_retired_rows_have_no_live_declaration` compared row coordinates against
the SWEEP's discovered sites, and the sweep does not read `docs/`, `memory/` or
`shared/interfaces/reviews/` — so retiring any of the **six** rows citing those
places while the declaration was live passed silently. It now asserts the
anchor is ABSENT from the cited file.

Second sensor defect fixed in the same pass: supporting cites (`cites[1:]`) were
asserted only to be "a line that exists", which any line number inside a long
enough file satisfies — the anchor was never compared against them. Four rows
carried such a cite. Every cite has its own anchor now.

## Equivalence

All 24 cites across all 21 rows resolve to exactly one line, and every resolved
line equals the line number the pre-change register carried by hand
(656, 497, 69, 37, 581, 61, 667, 1, 1, 1, 1, 192, 202, 508, 339, 516, 71, 705,
42, 163→165, 631, 1411, 42, 96). Both legacy exemptions resolve to 283 and 722.
Measured twice: once by this session, once by the reviewer with its own parser.

One anchor was ALREADY ambiguous before the change and nobody could see it:
`RES-008`'s `officer-plist instance-leakage cleanup` matched both the file
title and a quoted restatement 164 lines lower. The old line pin hid it.

## Frozen-scope intersection

`resolve_scope()` returns 85 entries. The staged diff touches
`cabinet/scripts/tests/test_declared_residuals_register.py`,
`docs/plans/declared-residuals-register.md` and
`cabinet/config/state-persistence-policy.yml`. **Intersection: EMPTY**, with
`restore_from_baseline` (14 entries) likewise EMPTY. No re-bind ceremony is
required and none was performed; `cognitive-phase4-review-scope.py --verify`
returns OK unchanged.

## Scope of the fix — stated plainly

The re-bind ceremony itself is **untouched and still required**: a framework
landing still re-binds the COG-4 digest and still appends a note above the
findings table. What is gone is the consequence here — that note no longer
moves anything this register has to chase. The dance was made harmless, not
eliminated. Eliminating it would mean changing the digest scope or the
re-bind convention, both inside COG-4's frozen scope, which would require a
review that has not happened.

## Batteries re-run by both the author and the reviewer

- `python3.12 -m pytest cabinet/scripts/tests -q` → `5006 passed, 34 skipped`
  (the CI job's actual command), run twice on different bytes of this branch.
- `python3.12 -m pytest cabinet/scripts/tests/test_declared_residuals_register.py -q`
  → `9 passed`.
- `cabinet/scripts/docs-track-code-sweep.sh` → `DOCS_SWEEP GREEN (files=64 findings=0)`
- `cabinet/scripts/ledger-status-parity.sh` → `LEDGER_STATUS GREEN (ids=353 md_rows=353 findings=0)`
- `cabinet/scripts/check-layer-separation.sh` → `OK — no new layer-separation violations`
- `cabinet/scripts/state-persistence-preflight.py --repo .` → `OK — no durable path would be lost`
- `cabinet/scripts/cognitive-phase4-review-scope.py --verify …` → `OK`

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-21
ownership-on-GO ruling.
