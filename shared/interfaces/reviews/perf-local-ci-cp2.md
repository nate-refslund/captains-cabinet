# perf/local-ci — checkpoint 2: local agnosticism advisor (ADVISORY)

Reviewed-Scope-Digest: 700194e597f3fe0c3d0a434ffd5cfb343080ccdfda4b2b1424f951935d68e1a9

## What this checkpoint contains
- `cabinet/scripts/agnosticism-advisor.py` — a local, OAuth/Max-pool LLM lens
  on one question: does this change teach the framework about a specific tool,
  industry, role, organisation, product, jurisdiction or person?
- `cabinet/scripts/agnosticism-corpus/` — 8 planted violations + 8 clean
  fixtures with recorded ground truth. Every proper noun in it is SYNTHETIC.
- `cabinet/scripts/tests/test_agnosticism_advisor.py` — 36 hermetic arms.
- `docs/ci-cost-and-agnosticism-advisor-2026-07-28.md` — the measured record.

## What was reviewed, and against what
Reviewed against the three ways an LLM lens rots.

- **Rubber stamp.** `--calibrate` scores the planted corpus BLIND (opaque
  `item-<hash>.txt` names; an arm asserts no fixture-name or class token
  reaches the model). Missing one plant VOIDs; flagging more than one clean
  fixture VOIDs. BOTH directions are pinned: an always-agnostic stub VOIDs, an
  always-instance-specific stub VOIDs, an ORACLE stub PASSES — so the floors
  are satisfiable rather than merely unreachable. A degenerate corpus (no
  plants, or no clean set) VOIDs instead of passing vacuously.
- **Flake.** Model pinned, rubric+corpus hashed into a digest carried on every
  verdict, schema-constrained JSON, majority voting, verdict cache keyed by
  (rubric digest, content hash). An unparseable or absent answer is `error`,
  never `agnostic` — six arms.
- **Self-reference.** Any input set touching the advisor, rubric or corpus
  ABSTAINS without calling the model — four arms, each asserting zero calls.
- **Placement.** Advisory by construction: sweep mode always exits 0, and
  `test_the_advisor_is_not_wired_into_any_workflow` fails the moment the name
  appears in a workflow. The only non-zero exit in the tool is the tool
  grading itself.

## Non-vacuity, both directions
- 36/36 hermetic arms pass; every stub-judge arm was written to FAIL the
  calibration it is aimed at, and does.
- Real model (`claude-opus-5`), two independent uncached passes: 8/8 planted
  caught both times, 1/8 clean flagged both times, 16/16 row-level agreement,
  CALIBRATED both times.
- Sweep over 12 ordinary framework modules: 4 flagged, all four verified BY
  HAND against the source (real literals at named line numbers) while
  `check-layer-separation.sh` and `test_no_launcher_hardcode.py` are both
  green on the same tree. That gap is the reason the lens exists.

## Residual, stated
The one stable false positive (a helper that reads the repo's own CI workflow)
is left un-tuned inside the corpus budget: tuning a rubric until the corpus
goes green is how a calibration set becomes a fixture that agrees with the
judge's defect. The four real findings are follow-up work, deliberately not
fixed inside a cost PR.
