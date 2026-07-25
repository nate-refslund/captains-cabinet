# Review artifact — fix/import-gate-dynamic-forms cp2 (2026-07-25)

Batch: close the BUILTIN hook-binding surface in the boundary-manifest engine
`cabinet/scripts/cog2-import-gate.py`, and correct the residual text that
under-claimed it. Plus the per-form arms in
`cabinet/scripts/tests/test_boundary_dynamic_forms.py`. 405 changed lines →
FW-019 artifact. Sits on top of cp1 (766a98c3).

**DO NOT LAND AS-IS — the cp1 re-bind obligation is UNCHANGED and still owed.**
Pushed for the integrator to sequence; deliberately NOT a PR.

## Gap

An independent probe against the LANDED cp1 engine reported a fifth evasion: the
alias/binding collector followed bindings sourced from `importlib` but not from
`builtins`. Reproduced before touching anything, against the holdout row
(`UNALLOWLISTED_HOLDOUT_GEN_IMPORTER`, the §7.3 league-invisibility case).

**The probe under-reported it.** The two named forms were real, but the same
class covers TEN spellings, all measured EVADES against 766a98c3:

| form | pre | post |
|---|---|---|
| `from builtins import __import__ as _b; _b('<token>')` | **EVADES** | **CAUGHT** |
| `from builtins import __import__ as _b; _b('framework' + '.…')` | **EVADES** | **CAUGHT** |
| `from builtins import __import__ as _b; _b(<midsplit>)` | **EVADES** | **CAUGHT** |
| `from builtins import __import__` (no alias) `; __import__(<midsplit>)` | **EVADES** | **CAUGHT** |
| `import builtins; builtins.__import__(<midsplit>)` | **EVADES** | **CAUGHT** |
| `import builtins as _b; _b.__import__(<midsplit>)` | **EVADES** | **CAUGHT** |
| `import builtins; _b = builtins.__import__; _b(<midsplit>)` | **EVADES** | **CAUGHT** |
| `from importlib import __import__ as _x; _x(<midsplit>)` | **EVADES** | **CAUGHT** |
| `from importlib import __import__` (no alias) `; __import__(<midsplit>)` | **EVADES** | **CAUGHT** |
| `import importlib; importlib.__import__(<midsplit>)` | **EVADES** | **CAUGHT** |

Controls, unchanged in both directions (verified, not assumed):

| control | pre | post |
|---|---|---|
| `__import__('<token>')` literal | CAUGHT | CAUGHT |
| `__import__(<midsplit>)`, no builtins import | CAUGHT | CAUGHT |
| `from importlib import import_module as _m; _m(<midsplit>)` | CAUGHT | CAUGHT |
| runtime-computed arg through a builtins alias | CLEAN | CLEAN |
| builtins alias importing an ALLOWED module (`os.path`) | CLEAN | CLEAN |

Two findings the probe did not contain:

- **`importlib.__import__` is a real, separate, public hook.** It is not
  `builtins.__import__` (`is` returns False — pinned at runtime, not assumed),
  and it imports. So every binding shape exists TWICE over, once per exporting
  module. Four of the ten spellings above are this.
- **One spelling was worse than a plain miss.** `from builtins import
  __import__` — the honest, explicit spelling — fell into the collector's
  `shadowed` set, which then removed the implicit builtin from `hooks`. So
  importing the hook explicitly switched builtin detection OFF for the whole
  file: a file that named the hook honestly was scanned WEAKER than one that
  said nothing. The bare-call control (CAUGHT) against the explicit-import form
  (EVADES) isolates it; `test_explicit_builtin_import_is_a_binding_not_a_shadow`
  pins both bodies RED.

## What shipped

The reported one-line fix (accept `ImportFrom` where module is `builtins`) is
**not sufficient** — verified: it closes 4 of the 10 spellings and leaves the
`import builtins` + attribute-call and assignment-binding forms open, i.e. the
exact spellings whose importlib twins cp1 already closed. Rather than close four
and add six lines to the residual list, the fix makes the two exporting modules
symmetric through one table:

```python
_HOOKS_OF_MODULE = {
    "importlib": frozenset({"import_module", "__import__"}),
    "builtins":  frozenset({"__import__"}),
}
```

`mod_binds` becomes `bound name -> exporting module` (was: a set of importlib
names), and the three binding shapes — `import <mod> [as X]`, `from <mod> import
<hook> [as X]`, `Y = <module-binding>.<hook>` — all key off that table. The
call scan reads `kind = func.attr`, so `importlib.__import__` correctly carries
the BUILTIN signature (2nd positional is `globals`, never a package) while
`importlib.import_module` still reads a package. No new fold logic — the probe
was right about that; the existing constant-fold handles every argument.

The symmetry is now STRUCTURAL, not two hand-written branches, so neither module
can drift ahead of the other; `test_both_exporting_modules_are_covered_by_one_table`
pins the table itself.

The gate stays MODULE-granular; binding-accuracy is preserved (four new
shadowing shapes pinned clean, incl. `builtins = object()` and a rebound alias).

## Residual text — the correction

cp1's honest-limitation note listed three deliberately-unwired-but-decidable
residuals. The aliased `__import__` binding was **neither caught nor listed** —
the note was false by omission, the same failure class cp1's own review (P1-3)
had already corrected once. Both halves are fixed here.

Residual (2) "explicitly NOT residual any more" GAINS:

> - the SAME three binding shapes on the BUILTIN, from either module that
>   exports it: `from builtins import __import__ [as _b]`, `import builtins
>   [as b]` + `b.__import__(...)`, `_b = builtins.__import__`, and the identical
>   set spelled through `importlib.__import__`. `from builtins import
>   __import__` is a hook binding, not a shadow of the implicit builtin;

Residual (c) "still-decidable, deliberately unwired" — before → after:

| before | after |
|---|---|
| the builtin's `fromlist`/`level` | *unchanged, plus* "Same for the `importlib.__import__` spelling of them" |
| alias chain deeper than one hop | *unchanged, plus* the builtin example `from builtins import __import__ as _b; _c = _b; _c(...)` |
| — *(nothing)* | **NEW:** a hook reached WITHOUT a name binding, so the call target is neither a Name nor an Attribute on a Name: a mapping subscript (`__builtins__['__import__'](...)`, `vars(builtins)[...]`, `sys.modules['builtins'].__import__(...)`) or a getattr walk (`getattr(builtins, '__import__')(...)`). The BINDING surface is now closed; this is the deliberate line, because the subscript/getattr surface is open-ended (any mapping or attribute expression can yield the hook) while a name binding is a closed, enumerable set |
| concatenation past `_FOLD_MAX_DEPTH` | *unchanged* |

Every residual entry is **measured** against this engine (8/8 confirmed still
CLEAN) and pinned in `TestDocumentedResidual` / `TestDynamicImportTargets`, so
the text cannot quietly rot. The list is now longer than cp1's, not shorter —
that is the point: it names a real boundary instead of implying coverage.

## Byte-compat (the gate on this change)

Captured before the first edit, re-diffed after the last — **all six streams
byte-identical, exit codes unchanged**:

```
check   : exit 0, stdout "[cog2-import-gate] OK — …", stderr empty   IDENTICAL
--report: exit 0, same stdout, stderr empty                          IDENTICAL
--json  : exit 0, {"violations": [], "count": 0}, stderr empty       IDENTICAL
```

All **nine** legacy rule ids preserved — proven mechanically by loading the
pre-fix and post-fix engines side by side and comparing: 9 module-level `RULE_*`
ids identical, and all 24 manifest rule-id rows identical. No id added, renamed
or removed.

`test_cog2_import_gate.py` and `test_cog3_import_gate.py` are **BYTE-UNTOUCHED**
(`git diff` empty and sha256-identical to a pristine 766a98c3 checkout) — cp1's
strongest-form byte-compat proof is not weakened. All new arms went into the
sibling file cp1 created.

## Non-vacuity — both directions, explicitly

cp1 shipped a vacuous falsifier class and caught it in review, so this is
accounted rather than asserted. The new suite was grafted onto a pristine
766a98c3 tree (engine pre-fix, caches purged, `PYTHONDONTWRITEBYTECODE=1`):

- 823 arms collected: 463 pre-existing + **360 added**, **0 removed**.
- Against the **pre-fix** engine: **148 FAIL**. Every one of the 148 is an added
  arm — **0 pre-existing arms regress** (set-differenced by node id, not eyeballed).
- Against the **fixed** engine: **all 823 pass**.
- The 148 split as **20 catch-arms for each of the 7 builtin forms** (140) plus
  8 form-independent arms (6 explicit-import-is-not-a-shadow, 1 table pin,
  1 all-spellings collector arm). No form is carried by another form's coverage.
- The other 212 added arms are **guards, not falsifiers**, and pass both ways BY
  DESIGN — they assert absence (no false positive, documented residual) or a
  runtime premise, so they fail only if the fix OVER-reaches. Stated in the test
  docstring so nobody mistakes them for evidence of the catch.
- `TestLegacyPatternEvasion` supplies the other half of the teeth: all 7 builtin
  forms are in `TRUE_EVASION_IDS` and are proven to match **none** of the
  engine's still-present pre-change regexes, per row (49 added arms). So the 148
  failures cannot be passing for an incidental reason — the cp1 P1-1 trap.

## Verification

- Byte-compat 6/6 streams identical, 3/3 exit codes unchanged (above).
- Bite map: 10/10 forms CAUGHT post-fix (0/10 pre-fix); 5/5 controls unchanged.
- Residual: 8/8 named forms confirmed still CLEAN, each pinned by a test.
- `cabinet/scripts/tests`: **4222 passed, 12 skipped** (cp1 tip 766a98c3: 3862
  passed, 12 skipped → **+360 passed, +0 skipped, +0 failures**). Master
  baseline for reference: 3399 passed, 12 skipped.
- `framework/`: 6433 passed, 25 skipped, **1 failed** —
  `test_retro_shim.py::TestRetroShim::test_reexports_constants`, asserting the
  stale model id `claude-sonnet-4-6` while the tree carries `claude-sonnet-5`.
  **PRE-EXISTING**: re-confirmed to fail identically on a pristine clone of
  origin/master (138a2532), with the identical assertion diff. Untouched here,
  deliberately not fixed — reported so the baseline stays honest.
- Existing engine-mutant suites pass unchanged (`test_cog2_import_gate.py`,
  `test_cog3_import_gate.py`, `test_cog4_boundary_rows.py` +
  `test_boundary_dynamic_forms.py`: 672 → 1032 with the new arms).
- `check-layer-separation.sh`: OK, new=0 (baseline 24, allowlist 19).
  `cognitive-architecture-census.py`: **PASS**, every counter at its cap.
- Both changed files scan clean under the gate itself — `gate.scan(_REPO) == []`
  is asserted over the modified tree by `TestByteCompat`. The assembled-token
  discipline holds: every new body is spelled MID-SPLIT, so no row token appears
  contiguously in the test source (`TestStrayHome` pins it).
- Sweeps run SERIALLY from an isolated clone; caches purged before each.

## Integrator: the cp1 re-bind is unchanged and still owed

This commit touches `cabinet/scripts/cog2-import-gate.py` again, so everything
in cp1's "required re-bind" section applies verbatim and is **not** discharged
here. The phase-4 binding already BLOCKs at 766a98c3 before this commit:

```
recorded  Reviewed-Scope-Digest: 093e5866…debe0ff6   (verifies at a1357829)
recomputed over 766a98c3:        b7fb451e…bd104400   → BLOCK
```

This commit moves the recomputed value again; recompute it at the branch tip
rather than trusting a literal here:

```
python3.12 cabinet/scripts/cognitive-phase4-review-scope.py --print
python3.12 cabinet/scripts/cognitive-phase4-review-scope.py --verify \
  shared/interfaces/reviews/cognitive-core-phase-4-review.md
```

Per the standing sequencing: a COG-5 wave landing does its own digest re-bind
first, then this branch rebases and does its own. Two competing re-binds would
collide, so this branch deliberately performs none and stops at push. No PR.

The two test files remain bound by no live digest, and the changes here are
confined to the net-new cp1 test file — so nothing else needs re-binding.
