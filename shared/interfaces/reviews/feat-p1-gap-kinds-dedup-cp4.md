# feat/p1-gap-kinds-dedup — checkpoint 4 (fix round on the cp3 rejection)

Reviewer verdict answered: **reject** at `dc4c4bf0`, one BLOCKING gap and four notes.
Every claim below carries the command that produced it, run this session in a fresh
clone of the branch at `/private/tmp/.../build/U3a`. Interpreter `python3.12`
(3.12.13); the box's bare `python3` is 3.9.6.

## The blocking gap — the architecture line budget was 31 short

`cabinet/config/cognitive-architecture-contract.yml ::
budgets.framework_production_noncomment_lines.maximum` **64839 -> 64870**.

Root cause, confirmed rather than assumed: `dc4c4bf0` added 36 lines to
`framework/learning/capability_gaps.py` — all of them docstring prose (the
claims-lock -> gaps-lock -> ledger-lock acquisition order, and the note on a
keyed gap's `hit_count`) — AFTER the budget row was last measured at `5ec26d61`.
`_non_comment_line_count` (cognitive-architecture-census.py:398-403) counts every
non-blank line that does not start with `#`, so a docstring is mass under this
law. 31 of the 36 lines were non-blank.

Why a bump and not a reword: turning the prose into `#` comments would dodge the
count and put the ordering rule where `help()` and the egg's own reader never see
it. The census docstring states the convention the bump follows — every class
pinned at observed == maximum, zero headroom (cognitive-architecture-census.py:9-12).

RED before / GREEN after, both this session:

| # | command | before | after |
|---|---|---|---|
| 1 | `python3.12 cabinet/scripts/cognitive-architecture-census.py --check` | rc 1 · `BLOCK framework_production_noncomment_lines: budget exceeded (79520 > 79489)` | rc 0 · `PASS` · `79520 <= 79520` |
| 2 | `pytest cabinet/scripts/tests/test_cognitive_architecture_census.py test_baseline_set_ratchet.py test_egg_export.py -q` | 33 failed, 179 passed, 7 skipped, **14 errors** | see the battery below |
| 3 | `pytest cabinet/scripts/tests -q` (whole suite) | 33 failed / 14 errors at `dc4c4bf0` | 1 failed — the documented pre-existing one |

The sensor here is the repo's own gate, not a new test: raising the maximum by any
value below 64870 leaves it red, and the census has zero headroom by construction,
so the arm cannot pass in both directions.

## Note 3 — the two auto-lane vetoes were redundant. Now one arm per veto.

The reviewer reproduced it: dropping `can_auto_apply`'s `STRUCTURAL_KINDS` refusal
OR `load_autonomy`'s `for k in ACTIONABLE_KINDS` loop, one at a time, left the whole
suite green; only the combined mutation reddened
`test_structural_kind_never_auto_applies_even_when_the_file_says_auto`. That arm
passes if EITHER veto stands, which is a sensor that cannot see half of what it
names. Two arms added, each reading only one veto:

- `TestStructuralKinds::test_the_config_veto_alone_keeps_the_lane_unconfigurable`
  — an `autonomy.yml` asking for `skill/authority/information: auto` must leave
  `policy.defaults` with no structural key at all.
- `TestStructuralKinds::test_the_gate_veto_alone_refuses_a_policy_that_already_says_auto`
  — a hand-built `AutonomyPolicy(defaults={kind: "auto"})` (the public parameter
  every caller may supply) must still be refused by `can_auto_apply`, with the
  config veto out of the picture. It asserts the policy really says `auto` first,
  so the gate is never fed a no-op.

Single-veto mutation results, run this session:

| mutant | arms red | arms green |
|---|---|---|
| V1 `load_autonomy` iterates `VALID_KINDS` | `test_the_config_veto_alone_keeps_the_lane_unconfigurable` (`AssertionError: {'authority','information','skill'}` extra) | the gate arm and the pre-existing combined arm |
| V2 `can_auto_apply`'s `if kind in STRUCTURAL_KINDS: return False` deleted | `test_the_gate_veto_alone_refuses_a_policy_that_already_says_auto` (`assert True is False` for `authority`) | the config arm and the pre-existing combined arm |

Each veto is now independently sensed, and the combined arm staying green under
both mutants is itself the evidence that it could not have caught either alone.

## Note 1 — the half of the lock-order rule this unit can pin

`framework/missions/claims.py` does not exist at this commit, so A3.1's letter
("keyed records are taken under the claims lock") is unsatisfiable and the unit
substitutes `_gaps_lock`. The acquisition order was written into that docstring
with nothing asserting it. The call-site half stays U2's — there is no order to
observe until a caller holds a claims lock. The half this module asserts about
ITSELF is checkable today and is now pinned:
`TestTheLockOrderThisUnitCanActuallyPin`.

- `test_this_module_never_acquires_a_claims_lock` — AST over
  `capability_gaps.py`: no import of a `claims` module, no `*claim*lock*` name or
  attribute. RED under a mutant that adds
  `from framework.missions.claims import claims_lock` at module scope
  (with a stub `claims.py` present so the module still IMPORTS and the arm reds
  for the reason the invariant names, not on `ModuleNotFoundError`).
- `test_the_ordering_sentence_is_still_in_the_docstring_it_binds` — RED under a
  mutant that edits the order line to `gaps-lock -> ledger-lock`.

Its stated limit is in the class docstring: it proves only that the acquisition
does not appear in THIS module. It cannot see an inversion in `claims.py` or at a
call site and is not a substitute for U2's ordering test.

## Notes 2, 4, 5 — no change, and why

- **Note 4** (the self-retiring PENDING rows in `framework/tests/test_interpreter_pin.py`
  vs. the §8 merge order) is an accurate description of a deliberate design, and its
  fix is a line in the U2/U3b briefs, not a code change here. Carried to the PR
  comment so the coupling is stated where the next builder reads it.
- **Note 5** (a keyed gap's `hit_count` stays 1, so `project_gaps`' `-hit_count`
  ranking sorts a standing keyed condition below a twice-seen free-text one) is
  contract-consistent — A3.1 mandates the silence — and no producer emits keyed
  gaps yet. The reviewer's own fix assigns the ranking decision to U3b.
- **Note 2** is the same claims-lock item as Note 1, answered above.

## Battery — post-commit, this session, this clone

Recorded in the PR comment with per-command exit codes. The failing set is
identical to the documented pre-existing set, proved by per-test verdict lines
rather than counts.
