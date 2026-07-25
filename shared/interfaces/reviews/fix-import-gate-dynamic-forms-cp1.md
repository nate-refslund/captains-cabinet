# Review artifact — fix/import-gate-dynamic-forms cp1 (2026-07-25)

Batch: dynamic-form resolution (constant folding + binding-accurate alias
tracking) in the boundary-manifest engine `cabinet/scripts/cog2-import-gate.py`,
plus its per-form proof suite `cabinet/scripts/tests/test_boundary_dynamic_forms.py`.
~200 engine lines + ~600 test lines → FW-019 artifact.

**DO NOT LAND AS-IS — see "Integrator: required re-bind" at the bottom.**
This branch is pushed for the integrator to sequence; it is deliberately NOT a PR.

## Gap

A fresh-context reviewer measured that two dynamic-import spellings evaded every
boundary row while the literal forms were caught. Reproduced exactly before
touching anything, against the holdout row (`UNALLOWLISTED_HOLDOUT_GEN_IMPORTER`,
importer `framework/evolution/league.py` — the §7.3 league-invisibility case):

| form | pre | post |
|---|---|---|
| `import <token>` | CAUGHT | CAUGHT |
| `from <parent> import <name>` | CAUGHT | CAUGHT |
| `import_module('<token>')` literal | CAUGHT | CAUGHT |
| `__import__('<token>')` literal | CAUGHT | CAUGHT |
| `import_module('framework' + '.evolution.<name>')` — constant-foldable | **EVADES** | **CAUGHT** |
| `from importlib import import_module as _m; _m('<token>')` — aliased | **EVADES** | **CAUGHT** |

Root cause: every row's dynamic pattern anchors on `(?:import_module|__import__)\(`
immediately followed by a quote and the CONTIGUOUS token. Splitting the literal,
or reaching the hook through any other name, defeats the anchor.

Two further evasions were found during the work and closed with them:
- `import_module(f'<token>')` — the `f` prefix alone defeated the `\(['"]` anchor.
- `_im = importlib.import_module; _im('<token>')` — the ASSIGNMENT binding, found
  by adversarial review of the first cut. More idiomatic than either measured form.

## What shipped

`_fold_str` (constant-fold str literals, `+` concatenation, all-literal f-strings,
walrus; depth-capped so a pathological nest declines rather than raising
RecursionError out of `scan()`), `_resolve_dyn_target` (relative name+package by
the stdlib rule; malformed packages undecidable), and
`_dynamic_import_targets_from_nodes` (the call scan). Wired as one additional
OR-clause into checks 1, 2, R and 3, each carrying the SAME rule id that check's
literal dynamic spelling already carried — attribution unmoved.

BINDING-ACCURATE, not name-matching. Bindings are collected over a full walk
before the call scan (so a call above its own import still resolves — the
lib_cog4_ast_pins `os_names` idiom), and a name only counts as a hook if the file
actually binds it to one and never rebinds it. Recognised: `import importlib
[as X]`, `import importlib.<sub>`, `from importlib import import_module [as X]`,
`X = importlib.import_module`, `X = __import__`. A file with its own
`def import_module(...)`, or `importlib = SomeClass()`, is NOT misread as
reaching importlib — it would NameError at runtime.

The gate stays MODULE-granular: this widens DYNAMIC-FORM detection only, and
adds no symbol-level enforcement (that remains the §8.4 sibling AST pins).

## Byte-compat (the gate on this change)

Engine-over-repo output captured before the first edit and re-diffed after every
revision — **all six streams byte-identical**, exit codes unchanged:

```
check  : exit 0, stdout "[cog2-import-gate] OK — …", stderr empty   IDENTICAL
--report: exit 0, same stdout                                        IDENTICAL
--json : exit 0, {"violations": [], "count": 0}                      IDENTICAL
```

All nine legacy rule ids preserved (no id added, renamed or removed — the change
touches no `rule_ids`). **229 existing engine-mutant tests pass unchanged**
(`test_cog2_import_gate.py`, `test_cog3_import_gate.py`,
`test_cog4_boundary_rows.py`, `test_cog5_boundary_rows.py`) — the header's
"run unchanged" claim survives literally; neither file was edited.

Why the repo output cannot move: no aliased importlib binding exists anywhere in
the tree (grepped), and every literal `import_module`/`__import__` argument
resolves to a non-fenced module (`json`, `os`, `sys`, `io`, `hashlib`,
`framework.evidence.classification`, `framework.attention.situation`,
`flavor_a.screenpipe_source`). Independently re-verified by the reviewer across
all 963 repo `.py` files.

Scan cost: 1.96s → 2.01s (+2.5%). A naive first cut was +43%; recovered with a
single shared AST walk and a source-level short-circuit (every hook form this
pass resolves must spell `import_module` or `__import__` literally, so a source
containing neither skips the walk entirely — semantics-free).

## Review

Independent adversarial review (fresh-context subagent, clean clone). Verified
sound: byte-compat across 12 runs; strict additivity via a 1512-cell pre/post
differential (**0 cells lose a violated path**, 534 gain a catch);
`_dynamic_import_targets` raised on none of 963 files; self-flag safety for both
new files; `keep < 1` correct against `importlib.util.resolve_name` over 153 pairs.

Findings raised, **all fixed in this commit**:
- **P1-1 the falsifier test class was VACUOUS** — 7/7 arms passed against the
  pre-fix engine. `_split()` cut on the first dot, so every body contained
  `'.<name>'`, which the falsifier's broad third regex branch already matched.
  The strictest surface (C-F17) had zero real new coverage while the file's
  docstring claimed "every arm fails against the pre-fix engine". FIXED: added a
  MID-SEGMENT split form (`'<token[:-2]>' '<token[-2:]>'`) that matches no legacy
  pattern on any row, plus the assignment-alias form; the falsifier class now
  fails pre-fix for the right reason.
- **P1-2 the anti-vacuity guard had no teeth** — it only checked the token was
  not contiguous, which does not preclude the four OTHER legacy branches. FIXED:
  new `TestLegacyPatternEvasion` runs the engine's still-present pre-change
  regexes directly and PROVES the load-bearing arms (`TRUE_EVASION_IDS`) match
  none of them, per row. The weaker head-split arms are now labelled as such
  instead of being presented as evidence.
- **P1-3 the rewritten residual text made false claims** — it said aliased hooks
  were caught "through any binding, in any order" while `_im = importlib.import_module`
  was a full bypass, and implied everything statically decidable was covered
  while `__import__(…, fromlist)`, the `level` form and deep alias chains were
  not. FIXED both ways: the assignment binding and the walrus are now genuinely
  caught, and the still-decidable-but-unwired forms are NAMED explicitly as
  residual (c) rather than hidden — each pinned by a test so the text stays true.
- **P2-1 new false-positive class** — hook names were matched by spelling, so
  `def import_module(...)` + a folded arg would RED a file that imports nothing.
  FIXED by the binding-accurate rewrite; four shadowing shapes pinned clean.
- **P2-2 attribution can shift** — a file with TWO reaches (one newly caught by
  check 1, one already caught by check 3) trades its sweep id for the more
  specific forbidden id, via the engine's pre-existing `flagged` de-duplication.
  The file still REDs and the exit code is unchanged. NOT code-fixed (that is
  existing engine behaviour on a newly visible input); the docstring's
  "no attribution moves" over-claim was corrected to state this precisely.
- P3s fixed: RecursionError depth cap; the double AST walk; `two_arg_relative`
  now keyed off the BINDING not the spelling (so `from importlib import
  import_module as __import__` is handled); malformed packages undecidable; the
  submodule-alias test's unverified comment is now a pinned assertion.

## Verification

- Byte-compat: 6/6 streams identical, 3/3 exit codes unchanged (above).
- Bite map: 6/6 forms caught post-fix (was 4/6); the two residual controls
  (`import_module(os.environ['X'])`, aliased import of an allowed module) stay
  EVADES in both directions, as they must.
- Every new arm fails against the pre-fix engine and passes against the fixed one
  (verified by restoring only the engine in a copy of the branch): sweep 54
  failed, forbidden-surface 45, reverse 36, deliberate-absence 18, falsifier 2.
  `TestDocumentedResidual` passes in BOTH directions (56) — residuals unmoved.
- `cabinet/scripts/tests`: **3862 passed, 12 skipped** (master baseline at
  a1357829: 3399 passed, 12 skipped → **+463 passed, +0 skipped, +0 failures**).
- `framework/`: 6433 passed, 25 skipped, 1 failed —
  `test_retro_shim.py::test_reexports_constants`, **PRE-EXISTING**: it fails
  identically on a pristine clone of a1357829. Untouched by this branch.
- `cabinet/scripts/task_adapters/tests` 38 passed; `world-aesthetic/tests` 87
  passed, 5 skipped.
- `check-layer-separation.sh`: OK, new=0. `cognitive-architecture-census.py`: PASS.
- Both new/changed files scan clean under the gate itself (both sit in the swept
  `cabinet/scripts` tree on no row's allowlist; the test file follows the
  assembled-token discipline — tokens read from row data at runtime, never
  literals — pinned by `TestStrayHome`).

## Integrator: required re-bind (why this is not a PR)

`cabinet/scripts/cog2-import-gate.py` is in the COG-4 frozen review scope, so
committing it moves the phase-4 digest, which is computed over `git ls-tree -r HEAD`:

```
shared/interfaces/reviews/cognitive-core-phase-4-review.md   Reviewed-Scope-Digest:
python3.12 cabinet/scripts/cognitive-phase4-review-scope.py --print
python3.12 cabinet/scripts/cognitive-phase4-review-scope.py --verify \
  shared/interfaces/reviews/cognitive-core-phase-4-review.md
```

At a1357829 that digest verifies OK
(`093e586636ea40716d353508429439d099adc54e48b574aa1efa6860debe0ff6`); after this
commit it must be re-recorded with a dated MECHANICAL-DELTA re-bind note naming
`cabinet/scripts/cog2-import-gate.py` and why the phase-4 verdict stands, then
`verify-cognitive-phase4.sh` re-run. COG-5 §12.1 puts zero regression tolerance
on the COG-4 battery, so an engine change without a same-commit re-bind turns it
RED. A COG-5 wave landing is already doing a digest re-bind; two competing
re-binds would collide, so this branch deliberately does neither and stops at push.

The two test files are bound by NO live digest (phase-2/phase-3 scopes contain
them but both already BLOCK on master and are digest-frozen historical), and the
new test file is net-new — so nothing else needs re-binding.
