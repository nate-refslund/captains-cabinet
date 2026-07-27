# Checkpoint review — feat/draft-only-act-then-tell — cp1 (2026-07-26)

Reviewer: orchestrator session, Opus 5. Scope: the whole branch diff against
`origin/master` @ `a55dea44`. FW-019 artifact for a >300-line commit.

## What the diff does

`draft_only` moves from the earn-up ladder to `notify_after` (act-and-tell) at
all four non-demote confidence states, in the root/guardian table and the
sovereign posture table of `framework/policies/authority-matrix.yml`, per
CAPTAIN-RULING 2026-07-26 ("the act first, except for emailing real people").
`earn_up` untouched, all six hard ceilings untouched, `demote` stays
`propose_only`. Three germline modules get comment-only corrections; the
governance doc, the CI arms, the CG-35 amendment doc + ledger row follow.

## The diagnosis was verified, not inherited

The task arrived with a prior builder's diagnosis. Every claim in it was
re-checked against the file before editing: which tables exist (root/guardian,
`earn_up`, `sovereign` — `postures.guardian` is validator-rejected, so three),
what `notify_after` means at each state, and whether `demote → propose_only` is
validator-required here. **It is not** — rule (a) binds only rows granting
`act_with_undo` and rule (b) only the two `_TRUST_FIRST_UNMEASURED` members,
neither of which covers `draft_only`. It is kept anyway, on doctrine, and now
pinned by a CI arm. That correction is recorded in the amendment doc §3b rather
than left as an unstated assumption.

## Attacks run against the change

- **Does the widening reach a send?** Four independent legs checked in code,
  not assumed: the ceiling row's values; the gate's step-2 ceiling
  short-circuit sitting *above* cell resolution and above the earn_up rung
  lift; `classify_action` having **no branch that returns `draft_only`** (comms
  calls route by recipient, unresolvable is fail-closed to external); and the
  class owning exactly `[draft_only]`. Legs 3 and 4 are now CI arms.
- **Does `notify_after` need machinery that does not exist?** No. The
  allow-branch keys on the verdict string, not the risk class, emits the gate
  tell and returns allow. It never consults the undo plane, so `draft_only`
  keeping no registered inverse is correct and needed no change.
- **Does anything silently widen alongside?** `earn_up` diffed to zero changed
  lines; `demote` cells unchanged in both tables; the six ceiling rows
  byte-identical; `posture.py`'s `POSTURES` deliberately NOT extended (a token
  there widens every risk class at once, which is the failure the previous
  builder correctly refused).
- **Is the germline path SET changed?** No — `germline-lock.sh` untouched. Four
  already-locked files change CONTENT only, landed-then-ceremonied.

## Both directions proven

The new arms were run against master's YAML with `__pycache__` purged: 3 arms
go RED on `graduated: auto` + `propose_only` at the other four, and green after
the edit. The ceiling arms pass in both directions by design — so they are
backed by **mutation sensors** that must RAISE (letting `external_comms` act
via `auto` and via `notify_after`, letting a sovereign ceiling act, drifting
the sovereign demote cell), plus a non-degeneracy assertion on the egress set
so the egress loop cannot pass vacuously.

## Real defect found while reviewing — recorded, not hidden

A mutation sensor I wrote **failed against the shipped validator**, which is
how a pre-existing gap surfaced: `validate_matrix` pins that every action_type
is mapped exactly once but **not to which class**, so relocating
`external_email` off `external_comms` validates clean while the gate's ceiling
short-circuit is risk_class-keyed. `HARD_CEILING_TOUCHES` does not backstop it
(it guards self-extension, a different layer). Present identically on master
and not introduced here. The test was **not** weakened to match the behaviour —
it was rewritten to pin the shipped mapping (a genuine sensor), and the gap is
written up in the amendment doc §6 and the CG-35 ledger row as an open item,
because closing it needs framework production lines against a census budget at
its ceiling, which is a threshold decision rather than a mechanical fix.

## Two self-inflicted breaks, both caught by gates and fixed

1. **Census budget.** Docstring lines count as production lines
   (`_non_comment_line_count` counts any non-blank line not starting with `#`),
   so two docstring edits pushed `framework_production_noncomment_lines` to
   67329 > 67326 and BLOCKED. Fixed by making both edits line-neutral — the
   detail moved into `#` comments, which are free. Now exactly 67326 == 67326,
   zero net production lines. **No threshold was raised.**
2. **Residuals register.** A comment expansion in `action_undo.py` shifted the
   `RES-005` RESIDUAL declaration from line 581 to 585, breaking four register
   tests that cite it by file:line. Fixed by compressing the comment back to
   its original 6 lines rather than editing the shared register — the marker is
   back on 581 and the register is untouched.

## Evidence (this session, this branch)

| gate | result |
|---|---|
| `python3.12 framework/authority/matrix.py` | PASS + actor-id parity PASS |
| framework suite (serial, `-p no:randomly`) | 6592 passed · 26 skipped · 1 failed |
| re-measured master baseline @ `a55dea44` | 6572 passed · 26 skipped · 1 failed |
| delta | **+20 passed, same single failure, same skips** |
| the 1 failure | `test_retro_shim.py::test_reexports_constants` — known pre-existing, red on the baseline too |
| `cabinet/scripts/tests` | 4685 passed · 28 skipped · **0 failed** (exit 0) |
| golden evals | **30/30 PASS**, 0 fail |
| layer-separation | `new=0 fixed=0` — OK |
| cognitive-architecture census | all budgets within, `noncomment_lines 67326 <= 67326` |
| cog2 import gate | OK — shadow boundary intact |
| docs-track-code sweep | GREEN (62 files, 0 findings) |
| A13 ledger parity | GREEN (ids=353 md_rows=353, findings=0) — was 352/352 |
| amendment doc lint | 21 passed (incl. the new CG-35 package entry) |

## Verdict

**approve.** The change is narrow, the walls it leans on are proven rather than
assumed, both new failure modes I introduced were caught by the repo's own
gates and fixed at source, and the one thing I could not close is written down
where the next session will find it.
