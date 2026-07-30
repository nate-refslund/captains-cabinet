# FW-019 checkpoint review — fix/answer-binds-depth cp1

Reviewed-Scope-Digest: b2e60a059c45acd3f8e4ec871cabaa2df6709feb067092439bba5be00048092a

**What is under review:** the salience answer now BINDS depth. Six staged paths,
461 insertions / 12 deletions.

**Reviewer honesty statement:** this is the author's own hostile pass, not an
independent panel. It is labelled as such because a review artifact claiming a
fresh-context panel that never ran would be the same defect class the unit
itself fixes — a published claim with nothing behind it. Every line below is a
command run in this clone at this digest, with caches purged
(`PYTHONDONTWRITEBYTECODE=1`, `__pycache__` removed before each run) and a
private `--basetemp`.

## 1. The defect, driven — before and after, same script

`drive.py` (six cases) run against `31e3d6b2` (master tip) and against these bytes.

| case | before | after |
|---|---|---|
| answer `blueharbour`, propose `quarterly-tax-returns` | `ok=True`, Charter ratified, `access=active_read_only` — **the folder was read**, card still said "so that is where I spend depth" | `REFUSED [salience_window_off_target]`, stage stays `welcome`, `source` stays `None`, no `propose_window` event |
| answer `blueharbour`, propose `blue-harbour` | `ok=True`, `salience.window` absent, no binding sentence on the Charter card | `ok=True`, `window={relation: matched, evidence: [blue, blueharbour, harbour]}`, binding sentence on the Charter card |
| propose `bh-monorepo` with `salience_relation=same_thing` | field ignored; `KeyError: 'window'` | `relation=same_thing`, aliases learn `monorepo`/`bhmonorepo`, depth claim kept |
| propose `quarterly-tax-returns` with `salience_relation=elsewhere` | field ignored; `KeyError: 'window'` | `relation=elsewhere`, opened, depth claim **absent** from the card |
| `salience_relation="yes"` (junk) | **accepted**, `stage=charter_pending` | `REFUSED [salience_relation_invalid]` |
| no answer at all | `ok=True` | `ok=True` — unchanged, nothing to bind |

## 2. Both directions, cache purged (the VERIFY rule)

Nine new arms in `framework/onboarding/tests/test_journey.py`. Run against
`31e3d6b2` with the new test file copied in: **8 of 9 FAIL**
(`salience_window_off_target` never raised, `KeyError: 'window'`,
`AttributeError: _window_binding`, the Charter card carries no binding line).
The ninth — `test_with_no_answer_there_is_nothing_to_bind_and_no_claim_is_made` —
passes in both, correctly: it is the degenerate-end boundary arm asserting that
an unanswered journey is UNCHANGED, and an arm that changed there would be a
regression, not a proof.

Against these bytes: 9 of 9 pass; `framework/onboarding` 620 passed 1 skipped.

## 3. Adversarial reading of the fix itself

- **Sensor wired to the live artifact?** `_binding_note` is called from the
  welcome, Charter and dividend cards and reads `_window_binding`; the refusal in
  `propose_window` reads the SAME function. One decision function, so text and
  control cannot drift. `git grep -n _window_binding` returns the production
  callers and the test that asserts on it — no dead twin.
- **Degenerate ends.** No answer ⇒ `None` ⇒ no constraint AND no claim (arm 6).
  Answer with no window ⇒ `unbound` ⇒ the claim states the enforcement, which is
  now true. Empty/whitespace/`True`/list/dict/wrong-case relation ⇒ refused
  (`test_an_unrecognised_relation_is_refused_rather_than_read_as_consent`); a
  bypass field that accepted any truthy value would be no control.
- **Lopsided fixture.** `test_the_bind_is_lopsided_so_a_wrong_rule_cannot_pass_by_symmetry`
  asserts the SAME pair in both directions (`blue-harbour` binds, `quarterly-tax-returns`
  refuses), so an always-accept and an always-refuse rule each fail it.
- **Test-environment leakage.** The bind reads the folder's LEAF name only, never
  its ancestors, so a pytest tmp path containing the test's own name cannot make
  a fixture pass on a word the test author wrote. `_folder()` states this.
- **The hole from the other side.** A window opened BEFORE the answer cannot be
  retroactively refused; the card therefore stops claiming it
  (`off_target` ⇒ "depth is not yet spent where you pointed"), pinned by
  `test_an_answer_arriving_after_the_window_does_not_claim_the_window`.
- **Stated limit, not a hidden one.** The bind catches a window and an answer
  that share NO name-word. A target typed as a phrase lends every word in it, so
  a coincidental shared word binds silently. That limit is written into
  `_window_binding`'s docstring, and the card claims no more than the test does
  ("I refuse a window that does not carry that name").
- **Not enforceable, and said so.** The framework cannot know what a folder holds
  before it may open it — the same honesty `framework.authority.ownership` states
  about an attestation. What it does instead: refuse silently proceeding, require
  the claim, record it, print which one was made.

## 4. Gates re-run at this digest

| gate | result |
|---|---|
| `python3.12 -m pytest framework/ -q` | 7719 passed, 25 skipped, 1 failed — `test_retro_shim.py::test_reexports_constants`, the KNOWN local-only red (model-id constant), untouched by this change |
| `framework/onboarding` | 620 passed, 1 skipped |
| `cognitive-architecture-census.py --check` | PASS, `framework_production_noncomment_lines` re-pinned 75371 ≤ 75371 (zero headroom) |
| `cabinet/scripts/tests/test_cognitive_architecture_census.py` + `test_expansion_adjudication_binding.py` | 157 passed, 6 skipped |
| `test_declared_residuals_register.py` | 9 passed (RES-023 rows→tree and tree→rows both bound) |
| `check-layer-separation.sh` | OK — no new violations (new=0) |
| `docs-track-code-sweep.sh` | GREEN (files=64 findings=0) |
| `ledger-status-parity.sh` | GREEN (ids=353 md_rows=353) |

## 5. Budget and freeze

`framework_production_noncomment_lines` 60979 → 61094 (+115 measured, observed
75371 vs the then-effective 75256). RAISED VISIBLY, not an allowance: the
control cannot be deleted while the sentence ships. Zero new production modules.
The contract file sits inside the frozen COG-4 digest scope, so the COG-4
review artifact is re-bound in this same commit.
