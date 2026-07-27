# feat/census-set-pins — checkpoint review 1 (FW-019)

Verdict: PASS
Date: 2026-07-27
Base: origin/master 3a710183
Unit: SET pins for the surfaces the architecture census is BLIND to
Adjudication of record: the 2026-07-27 expansion-gate direction gate (D3), two
blind arms (Fable 5 / Opus 5), SPLIT ruling — no line-mass budget in
cabinet/scripts, set pins on the named classes instead.

## 1. The hole, reproduced before anything was written

`_production_python_files` rglobs `framework/` and matches `*.py` only. So
`cabinet/scripts/**`, `cabinet/config/**`, `.claude/**` and every non-`.py`
file cost the census ZERO — a blind spot the contract already recorded in its
own words ("the new framework/schemas/cognitive-trajectory.v2.schema.json is
JSON so the census — which counts only *.py — adds ZERO modules and ZERO lines
for it"), and where both live expansion escapes landed.

Measured on a pristine worktree of `origin/master`, each expansion applied to a
scratch copy and the OLD census run over it:

| expansion applied to pre-change master | census verdict |
|---|---|
| a new organ manifest under `cabinet/config/organs/` | ok=True, no failures |
| a new `.claude/skills/<name>/SKILL.md` | ok=True, no failures |
| a new wired hook in `.claude/settings.json` | ok=True, no failures |
| a new member in `framework/frontdoor/action_lessons.py::_VERDICTS` | ok=True, no failures |
| a new verdict vocabulary in `cabinet/scripts/` | ok=True, no failures |
| a new durable store in `.gitignore` | ok=True, no failures |

Six for six free. That is the claim the unit exists to falsify, and it is
falsified by execution, not by reading.

## 2. What landed

Six budgets, all DERIVED FROM THE TREE, none a hand-maintained list:

| budget | source | derivation | max |
|---|---|---|---|
| `organ_manifests` | `cabinet/config/organs` | files matching `*.yml` | 5 |
| `claude_skills` | `.claude/skills` | files matching `SKILL.md` | 21 |
| `claude_hook_wirings` | `.claude/settings.json` | `hooks.<Event>[].hooks[]` entries | 27 |
| `framework_verdict_vocabulary_members` | `framework` | static members of module-level names matching `VERDICT` | 70 |
| `cabinet_script_verdict_vocabulary_members` | `cabinet/scripts` | same | 18 |
| `durable_store_units` | `.gitignore` | positive patterns reduced to their deepest wildcard-free prefix | 96 |

Zero headroom on every one (`observed == maximum`), pinned by its own arm
(`test_set_pin_budgets_have_zero_headroom`) so a pin cannot land with slack.

Data rows and one reader, per the ruling: no new module, no new schedule, no new
Captain surface, no new decider. `framework_production_modules` (244) and
`framework_production_noncomment_lines` (69315) are UNCHANGED — the whole unit
lives in `cabinet/scripts` and `cabinet/config`, so no `temporary_allowances`
row is owed and none was taken.

## 3. Derivation, not lists

`durable_store_units` reuses `state-persistence-preflight.py`'s own two rules
verbatim — skip comments and negations (a negation re-includes a TRACKED file,
which survives a fresh worktree by definition), and reduce each pattern to its
durability UNIT — so `memory/logs/*.jsonl` and `memory/logs/*.log` are ONE
store. That is the in-tree standard, stated there as "does NOT add a fourth
hand-maintained list". Pinned arms: `test_durable_store_units_collapse_globs_to_one_store`
and `test_negated_gitignore_rule_is_not_a_store`.

The verdict pins discover by NAME across the production tree, so a vocabulary in
a file the contract has never heard of is counted on the run it lands. No list
to drift.

## 4. Fail-closed at the degenerate end

Every pin was attacked at its zero end, because a sensor that reads 0 on an
absent input is a disabled sensor that reports green:

| attack | result |
|---|---|
| delete `cabinet/config/organs` entirely | ContractError, not 0 |
| delete `.claude/skills` entirely | ContractError, not 0 |
| empty `.gitignore` | ContractError, not 0 |
| `hooks` key removed / `hooks` a list / event a mapping / entry without `hooks` / command without `command` | ContractError, not a smaller count |
| verdict vocabulary built by call, comprehension, `|=`, `.add()`, or tuple-unpacking | ContractError, not skipped |
| a non-verdict dynamic constant in the same file | still green — the fail-closed rule is scoped to the NAMES the pin claims |

The last row matters: a gate that reds on unrelated code is a gate that gets
switched off.

## 5. Both directions, per pin

Eighteen parametrized arms — six GROWTH mutants proving RED with the correct
budget named, six CEILING arms proving the red comes from CROSSING the ceiling
rather than from touching the file, six SHRINK arms proving a legitimate removal
stays GREEN and lands strictly under the maximum. A pin that can only ratchet
upward is a pin nobody can ever pay down.

Verified against PRE-CHANGE code, cache purged (`PYTHONDONTWRITEBYTECODE=1`,
`__pycache__` removed): the new test file run against a pristine
`origin/master` worktree gives **32 failed, 30 passed** — every new arm fails,
every pre-existing arm still passes. Against the changed tree: **63 passed,
6 skipped** (the six ceiling arms skip where headroom is already zero, which is
the whole source tree by law).

### 5a. The arms were vacuous in the egg — found by running them there

The first cut of these arms hardcoded a `+1` growth and named specific files.
`test_egg_export.py::test_cognitive_architecture_verifier_runs_inside_export`
drives `verify-cognitive-architecture.sh` through the actual export, and the
export deliberately deletes one skill (`delete .claude/skills/brain-audit`,
R168). Inside that tree the pin had one unit of slack, so:

- the growth mutant added a skill, landed exactly ON the ceiling, and **passed
  while proving nothing** — a sensor testing something other than the control;
- the shrink arm named `brain-audit`, which the export had removed, and died on
  the missing path rather than on the property;
- the zero-headroom arm asserted a law that is false in a derived tree by
  construction.

Fixed by deriving both the target and the SIZE from the tree at hand: grow by
`headroom + 1`, shrink whatever the pin's own discovery finds first, and scope
the zero-headroom law to the source instance (no `.git` ⇒ skip, loudly). The
CEILING arms exist so a future tree with slack cannot make a growth mutant
vacuous again without a red.

## 6. Measured false-positive rates, per first-parent landing on master

30 days to 2026-07-27 (601 landings), 7-day steady state (67 landings) beside:

| pin | 30d | 7d |
|---|---|---|
| `organ_manifests` | 0/601 = 0.00% | 0.00% |
| `claude_hook_wirings` | 0/601 = 0.00% | 0.00% |
| `claude_skills` | 2/601 = 0.33% | 0.00% |
| `cabinet_script_verdict_vocabulary_members` | 6/601 = 1.00% | 2.99% |
| `framework_verdict_vocabulary_members` | 14/601 = 2.33% | 2.99% |
| `durable_store_units` | 36/601 = 5.99% | 7.46% |

## 7. Dissent on record — the durable-store pin

The last row is loud and is not buried. **5.99%/landing is the same band as the
8.2% cabinet/scripts add-rate this same gate REFUSED**, on the reasoning that a
detector firing on every routine change is switched off within a week.

Two facts decided it in favour of keeping the row, and both are recorded so a
later session can argue with the evidence rather than with a summary:

1. **Every one of the 36 fires was a genuinely NEW durable store** — captain
   dates, the availability dial, the evidence recorder, the foundry archive, the
   world chronicle. They are true positives at a high rate, not false alarms on
   routine edits. That is the exact distinction the cabinet/scripts refusal
   turned on: there, most fires would have been ordinary edits to existing
   scripts.
2. **Raw `.gitignore` line count was measured and rejected** (38 of 39 touching
   commits) in favour of the unit set, which is both quieter and semantically
   the store registry.

Honest overlap, stated rather than hidden: `state-persistence-preflight.py`
already fails closed on a new unaccounted store and demands a written reason —
**proven by execution here** (appending one ignored path to a scratch copy made
it exit non-zero and print "1 path(s) unaccounted for"), and it runs in CI. It
asks whether a store SURVIVES A DEPLOY. The census pin asks whether the org grew
another memory at all, which no gate asked before. If this row ever starts
firing on things that are not stores, delete it rather than widen it.

## 8. Residual holes, named

- **Offsetting churn.** Members are pinned, vocabulary COUNT is not: shrinking
  one vocabulary by N while adding a new N-member one nets zero. A second budget
  was judged not worth the row; recorded here so it is a known hole, not a
  silent one.
- **A hook invoked from inside an existing hook script** adds no wiring entry and
  so costs `claude_hook_wirings` nothing. The wiring is what makes a hook live;
  a dispatcher inside one is beyond what this pin can see.
- **Non-`VERDICT`-named decision vocabularies** are not discovered. The pattern
  is contract data (`symbol_pattern`), so widening it is a data edit, not a code
  change.
- **Non-`.py`, non-pinned files in `cabinet/scripts`** remain free by design —
  the ruling refused mass there, and this unit did not smuggle it back in.

## 9. Gates run (local, committed tree unless noted)

- `cognitive-architecture-census.py --check` → PASS, 16 budgets, all
  `observed == maximum`
- `cabinet/scripts/tests` → 4818 passed, 34 skipped, 1 failed
  (`test_cog1_outbox_capture.py::TestB1B2Baselines::test_baselines_hold_the_bound`
  — a 100-iteration `time.perf_counter()` benchmark against an ephemeral PG17
  cluster; it PASSED in the earlier full run of this same branch and passes in
  isolation, 24/24. Classified as the wall-clock class, not a regression: this
  unit adds no code to that path)
- `framework/` full sweep → 6954 passed, 25 skipped, 1 failed
  (`test_retro_shim.py::test_reexports_constants` — pre-existing on master,
  a model-id shim assertion, untouched by this unit)
- `check-layer-separation.sh` → rc=0, new=0
- `cog2-import-gate.py` → rc=0
- A13 ledger/plan parity → OK, 353 rows
- `test_egg_export.py` → 58 passed, 1 skipped (including the in-export
  verifier arm that caught §5a)
- `test_cog3_census_wall.py` → 4 passed
- `null-hatch.sh` on the committed unit → PASS, census reporting all 16 budgets
- `verify-cognitive-phase4.sh` → READY_FOR_CI; golden evals 29/29 including
  EVAL-024-CANDOR; rollback rehearsal PASS; digest binding OK
- `hatch.sh --defaults --clean-room` from a scratch export of this commit →
  HATCH VERDICT: GREEN. Honest note: the FIRST attempt failed at proof-a with
  `tar: (null)` while staging the gitless copy. It did not reproduce — a fresh
  export of the same commit is GREEN, and `null-hatch.sh` run standalone in a
  gitless export of the same commit is PASS. The staging step reads no census
  surface.

## 10. §15 digest re-bind

`cabinet/config/cognitive-architecture-contract.yml` sits inside the frozen
phase-4 review scope. PR #210 skipped this re-bind and left the phase-4 gate red
on master for three merges. The `Reviewed-Scope-Digest` in
`shared/interfaces/reviews/cognitive-core-phase-4-review.md` is updated in the
SAME commit as the contract edit; the review artifact is excluded from its own
digest, so the amend that carries it does not move the value it records.
