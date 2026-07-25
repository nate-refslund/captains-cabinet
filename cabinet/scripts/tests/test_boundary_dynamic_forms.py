"""Engine pin — the boundary gate's DYNAMIC-FORM resolution (constant folding +
alias tracking) in cabinet/scripts/cog2-import-gate.py.

WHAT THIS CLOSES. The gate's per-row dynamic regexes only ever saw a dynamic
import whose module name was a CONTIGUOUS literal directly after the call paren.
A measured review found two forms that evaded every row while a plain literal
call was caught:

  * CONSTANT-FOLDABLE argument  — `import_module('<head>' + '.<tail>')`, and the
    f-string spelling `import_module(f'<token>')` (the `f` prefix alone defeated
    the `\\(['\"]` anchor).
  * ALIASED binding of the hook  — `from importlib import import_module as _m`
    then `_m('<token>')`, or `import importlib as il` then `il.import_module(...)`.

A third form, found in adversarial review of the first cut, evaded too and is
closed with them: the ASSIGNMENT binding `_im = importlib.import_module`, which
is more idiomatic than either measured form.

All three are now resolved by an AST pass (`_dynamic_import_targets`), whose
alias tracking mirrors the COG-4 exec-pin idiom in lib_cog4_ast_pins.py
(bindings collected over a FULL walk BEFORE the call scan, so binding order
never matters), and which is BINDING-ACCURATE — a file defining its own
`def import_module(...)` is not misread as reaching importlib.

EVIDENCE DISCIPLINE. Not every arm below is load-bearing, and this file does not
pretend otherwise. The head-split forms evade a row's OWN dynamic pattern but
some trip a different legacy branch on some rows — notably the falsifier's broad
`'.<name>'` alternative, which made the whole falsifier class of the first cut
vacuous (7/7 passing against the pre-fix engine). The load-bearing arms are
TRUE_EVASION_IDS, and TestLegacyPatternEvasion PROVES they match none of the
engine's still-present pre-change regexes rather than asserting it in prose.

SCOPE DISCIPLINE. This widens DYNAMIC-FORM detection ONLY. The gate stays
MODULE-granular by design — nothing here asserts symbol-level enforcement, which
lives in the sibling AST pins (contract §8.4). The pass is strictly ADDITIVE:
TestByteCompat pins that engine-over-repo output is still empty and that the
pre-existing regex attribution is unmoved (a folded/aliased reach carries the
SAME rule id its literal spelling already carried in that check).

RESIDUAL HONESTY. The engine docstring documents what remains undetectable
after this change. TestDocumentedResidual pins that boundary from the other
side: an argument that is genuinely computed at runtime must NOT be reported as
a definite violation — it belongs to the residual, and a scanner that guessed
there would be lying. If a future change makes one of those decidable, the
residual text and these tests move together.

ROW-GENERIC. Every arm is generated FROM the manifest rows, so a future row
inherits this coverage with zero new test code (the test_cog4_boundary_rows.py
harness property). Tokens are ALWAYS read from row data at runtime and never
written as contiguous literals in this source — this file sits in a swept tree
and is on NO row's allowlist (TestStrayHome pins that), so a literal would flag
the file itself.

NO VACUITY GUARD: every assertion exercises the engine on inputs generated in
this run, so no test here needs a retirement condition (the §13 discipline for
vacuity-armed tests does not apply).

S0: interpreter python3.12. No DB — a pure text/AST scan over scratch trees.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import ast
import importlib.util as _ilu
import sys
from pathlib import Path

import pytest

# hyphenated filename -> importlib (the cog2 CLI-under-test idiom)
_GATE = Path(__file__).resolve().parents[1] / "cog2-import-gate.py"
_REPO = Path(__file__).resolve().parents[3]

_spec = _ilu.spec_from_file_location("cog2_import_gate_dynforms", _GATE)
gate = _ilu.module_from_spec(_spec)
sys.modules["cog2_import_gate_dynforms"] = gate
_spec.loader.exec_module(gate)

CONFIG = gate.load_config()
ROWS = list(CONFIG.rows)
MODULE_ROWS = [r for r in ROWS if r.kind == gate.MODULE_KIND]
SWEEP_ROWS = [r for r in MODULE_ROWS if r.sweep]
FORBIDDEN_ROWS = [r for r in MODULE_ROWS if r.forbidden_importers]
FALSIFIER_ROWS = [r for r in MODULE_ROWS if r.falsifier_exact]
REVERSE_ROWS = [r for r in MODULE_ROWS if r.reverse_forbidden]
ABSENT_MODULE_ROWS = [r for r in MODULE_ROWS if r.deliberately_absent]

# a swept home curated by NO row — the stray-importer site for generated mutants
_STRAY = "shared/_dynforms_generated_leak.py"


def _row_param(rows):
    return pytest.mark.parametrize("row", rows, ids=[r.token for r in rows])


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _paths_for(violations, rule: str) -> set[str]:
    return {v.rsplit(":", 1)[0] for v in violations if v.rsplit(":", 1)[1] == rule}


def _rules_for(violations, path: str) -> set[str]:
    return {v.rsplit(":", 1)[1] for v in violations if v.rsplit(":", 1)[0] == path}


def _split(dotted: str) -> tuple[str, str]:
    """Token -> (head, tail) so `'<head>' + '.<tail>'` reassembles it WITHOUT
    the name ever appearing contiguously in the generated fixture."""
    head, tail = dotted.split(".", 1)
    return head, tail


# ---------------------------------------------------------------------------
# the evading-form bodies, generated from a dotted module name. Each renders a
# reach that the pre-fix engine could not see.
# ---------------------------------------------------------------------------

def _body_concat(dotted: str) -> str:
    head, tail = _split(dotted)
    return ("import importlib\n"
            f"m = importlib.import_module('{head}' + '.{tail}')\n")


def _body_fstring(dotted: str) -> str:
    head, tail = _split(dotted)
    return ("import importlib\n"
            f"m = importlib.import_module(f'{head}' f'.{tail}')\n")


def _body_alias_func(dotted: str) -> str:
    head, tail = _split(dotted)
    return ("from importlib import import_module as _m\n"
            f"m = _m('{head}' '.{tail}')\n")


def _body_alias_module(dotted: str) -> str:
    head, tail = _split(dotted)
    return ("import importlib as _il\n"
            f"m = _il.import_module('{head}' '.{tail}')\n")


def _body_alias_defined_after_use(dotted: str) -> str:
    """The binding-order arm: the call is written ABOVE its own import."""
    head, tail = _split(dotted)
    return ("def load():\n"
            f"    return _m('{head}' '.{tail}')\n"
            "from importlib import import_module as _m\n")


def _body_alias_relative_two_arg(dotted: str) -> str:
    """Aliased hook + the two-argument RELATIVE form together."""
    parent, name = dotted.rsplit(".", 1)
    return ("from importlib import import_module as _m\n"
            f"m = _m('.{name}', '{parent}')\n")


def _body_builtin_concat(dotted: str) -> str:
    head, tail = _split(dotted)
    return f"m = __import__('{head}' + '.{tail}')\n"


def _body_midsplit_concat(dotted: str) -> str:
    """THE universal true-evasion form: the split falls INSIDE the last
    segment, so the body matches none of the row's legacy patterns — not the
    token prefix, not the `'.<name>'` alternative the falsifier pattern carries,
    not the pathed backstop. TestLegacyPatternEvasion pins exactly that."""
    return ("import importlib\n"
            f"m = importlib.import_module('{dotted[:-2]}' '{dotted[-2:]}')\n")


def _body_assign_alias(dotted: str) -> str:
    """The assignment binding — `_im = importlib.import_module` — which is more
    idiomatic than either originally-measured form and evaded the gate too."""
    return ("import importlib\n"
            "_im = importlib.import_module\n"
            f"m = _im('{dotted[:-2]}' '{dotted[-2:]}')\n")


EVADING_FORMS = [
    ("concat", _body_concat),
    ("fstring", _body_fstring),
    ("alias_func", _body_alias_func),
    ("alias_module", _body_alias_module),
    ("alias_defined_after_use", _body_alias_defined_after_use),
    ("alias_relative_two_arg", _body_alias_relative_two_arg),
    ("builtin_concat", _body_builtin_concat),
    ("midsplit_concat", _body_midsplit_concat),
    ("assign_alias", _body_assign_alias),
]

# the forms that evade EVERY legacy pattern for EVERY row — the honest core of
# the change. The others evade the row's own dynamic/backstop patterns but some
# happen to trip a different legacy branch on some rows (the falsifier's broad
# `'.<name>'` alternative especially), so only these carry the load-bearing
# "was genuinely missed before" claim. Pinned in TestLegacyPatternEvasion.
TRUE_EVASION_IDS = ("midsplit_concat", "assign_alias")

_FORM_IDS = [name for name, _ in EVADING_FORMS]


def _form_param():
    return pytest.mark.parametrize("form", [f for _, f in EVADING_FORMS],
                                   ids=_FORM_IDS)


# ===========================================================================
# preconditions — the harness itself is honest
# ===========================================================================

class TestStrayHome:
    def test_stray_home_is_curated_by_no_row(self):
        # if a future row allowlists shared/, every sweep arm below would go
        # vacuously green — fail loudly here instead.
        for row in ROWS:
            assert not row.is_allowlisted(_STRAY), row.token
            assert not row.is_internal(_STRAY), row.token

    def test_this_file_is_on_no_row_allowlist(self):
        # the assembled-token discipline is LOAD-BEARING here: this file is
        # swept and un-curated, so a contiguous token literal in this source
        # would flag this very file. Pin the premise.
        rel = Path(__file__).resolve().relative_to(_REPO).as_posix()
        for row in ROWS:
            assert not row.is_allowlisted(rel), (row.token, rel)
            assert not row.is_internal(rel), (row.token, rel)

    def test_generated_bodies_never_spell_the_token_contiguously(self):
        # necessary but NOT sufficient (see TestLegacyPatternEvasion): a body
        # that reassembled the token contiguously would be caught by the old
        # engine and prove nothing.
        for row in MODULE_ROWS:
            for name, form in EVADING_FORMS:
                if name == "alias_relative_two_arg":
                    continue          # the relative form names only the leaf
                body = form(row.token)
                assert row.token not in body, (row.token, name, body)


class TestLegacyPatternEvasion:
    """THE teeth check. The engine still carries every pre-change regex on each
    compiled row, so 'this form was genuinely missed before' is checkable HERE
    rather than asserted in prose: a true-evasion body must match NONE of them.

    Without this, an arm can pass against the pre-fix engine for the wrong
    reason — which is exactly what happened on the first cut of this file: the
    falsifier's broad `'.<name>'` alternative caught every head-split form, so
    the whole falsifier class was vacuous and the docstring's 'every arm fails
    against the pre-fix engine' was false for it.
    """

    def _legacy_hits(self, row, body: str) -> list[str]:
        """Which pre-change patterns fire on this body (live lines + raw)."""
        live = [l for l in body.splitlines()
                if l.strip() and not l.strip().startswith("#")]
        hits = []
        if row.backstop is not None and any(row.backstop.search(l) for l in live):
            hits.append("backstop")
        if row.dynamic is not None and any(row.dynamic.search(l) for l in live):
            hits.append("dynamic")
        if row.falsifier_dynamic is not None and any(
                row.falsifier_dynamic.search(l) for l in live):
            hits.append("falsifier_dynamic")
        if row.falsifier_import_line is not None and any(
                row.falsifier_import_line.search(l) for l in body.splitlines()):
            hits.append("falsifier_import_line")
        if row.reverse_dynamic is not None and any(
                row.reverse_dynamic.search(l) for l in live):
            hits.append("reverse_dynamic")
        return hits

    @_row_param(MODULE_ROWS)
    @pytest.mark.parametrize("form_id", TRUE_EVASION_IDS)
    def test_true_evasion_form_matches_no_legacy_pattern(self, row, form_id):
        form = dict(EVADING_FORMS)[form_id]
        body = form(row.token)
        assert self._legacy_hits(row, body) == [], (row.token, form_id, body)

    @_row_param(FALSIFIER_ROWS)
    @pytest.mark.parametrize("form_id", TRUE_EVASION_IDS)
    def test_falsifier_class_has_a_genuinely_new_catch(self, tmp_path, row, form_id):
        # the strictest surface (C-F17) must gain REAL coverage, not coverage it
        # already had via the broad `'.<name>'` alternative.
        form = dict(EVADING_FORMS)[form_id]
        body = '"""falsifier."""\n' + form(row.token)
        assert self._legacy_hits(row, body) == [], (row.token, form_id)
        for fal in row.falsifier_exact:
            _write(tmp_path, fal, body)
            assert fal in _paths_for(gate.scan(tmp_path),
                                     row.rule_ids["falsifier"]), (row.token, fal)

    @_row_param(MODULE_ROWS)
    def test_head_split_forms_are_documented_as_weaker_arms(self, row):
        # honesty pin: the head-split forms DO trip a legacy pattern on rows
        # whose falsifier alternative matches `'.<name>'`. They are still useful
        # arms (they evade the row's own dynamic pattern) but they are NOT the
        # load-bearing evidence, and TRUE_EVASION_IDS must exclude them.
        assert "concat" not in TRUE_EVASION_IDS
        assert "alias_func" not in TRUE_EVASION_IDS


# ===========================================================================
# BYTE-COMPAT — the pass is strictly additive
# ===========================================================================

class TestByteCompat:
    def test_committed_tree_is_still_clean(self):
        # THE anchor: engine-over-repo output is empty, before and after.
        assert gate.scan(_REPO) == []

    def test_literal_dynamic_form_keeps_its_original_rule_attribution(self):
        # a plain literal import_module call was ALREADY caught; the new pass
        # must not move which rule it lands under.
        for row in SWEEP_ROWS:
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                _write(Path(td), _STRAY,
                       f"import importlib\nm = importlib.import_module('{row.token}')\n")
                rules = _rules_for(gate.scan(td), _STRAY)
            assert rules == {row.rule_ids["unallowlisted"]}, row.token


# ===========================================================================
# check 3 (un-curated sweep) — every evading form now bites, per row
# ===========================================================================

class TestSweepDynamicForms:
    @_row_param(SWEEP_ROWS)
    @_form_param()
    def test_evading_form_bites_in_sweep(self, tmp_path, row, form):
        _write(tmp_path, _STRAY, form(row.token))
        viol = gate.scan(tmp_path)
        assert _STRAY in _paths_for(viol, row.rule_ids["unallowlisted"]), \
            (row.token, viol)

    @_row_param(SWEEP_ROWS)
    @_form_param()
    def test_curated_reader_still_folds_clean_on_every_form(self, tmp_path, row, form):
        # the allowlist must keep working for the newly-caught spellings too —
        # a curated reader reaching dynamically is still curated.
        reader = sorted(row.allowlist_exact)[0]
        _write(tmp_path, reader, form(row.token))
        assert gate.scan(tmp_path) == [], (row.token, reader)

    @_row_param(SWEEP_ROWS)
    @_form_param()
    def test_row_internal_file_still_folds_clean_on_every_form(self, tmp_path, row, form):
        rel = f"{row.internal_prefix}_dynforms_generated_internal.py"
        _write(tmp_path, rel, form(row.token))
        assert gate.scan(tmp_path) == [], row.token


# ===========================================================================
# checks 1 / 2 / R — the same forms bite on the other check shapes
# ===========================================================================

class TestForbiddenSurfaceDynamicForms:
    @_row_param(FORBIDDEN_ROWS)
    @_form_param()
    def test_evading_form_bites_on_forbidden_surface(self, tmp_path, row, form):
        # attribution: the forbidden surface's dynamic complement is the TOKEN
        # backstop, so a folded/aliased reach carries forbidden_token — exactly
        # what the literal dynamic spelling already carried there.
        rel = f"{row.forbidden_importers[0]}/_dynforms_generated_mutant.py"
        _write(tmp_path, rel, form(row.token))
        rules = _rules_for(gate.scan(tmp_path), rel)
        assert row.rule_ids["forbidden_token"] in rules, (row.token, rules)


class TestFalsifierDynamicForms:
    @_row_param(FALSIFIER_ROWS)
    @_form_param()
    def test_evading_form_bites_on_falsifier(self, tmp_path, row, form):
        # C-F17 is the STRICTEST surface: no module of the token, however
        # spelled — which now genuinely includes folded and aliased spellings.
        for fal in row.falsifier_exact:
            _write(tmp_path, fal, '"""falsifier."""\n' + form(row.token))
            viol = gate.scan(tmp_path)
            assert fal in _paths_for(viol, row.rule_ids["falsifier"]), \
                (row.token, fal, viol)


class TestReverseDynamicForms:
    @_row_param(REVERSE_ROWS)
    @_form_param()
    def test_evading_form_bites_on_reverse_direction(self, tmp_path, row, form):
        dotted = row.reverse_forbidden[0].replace("/", ".")
        rel = f"{row.internal_prefix}_dynforms_generated_rev.py"
        _write(tmp_path, rel, form(dotted))
        assert rel in _paths_for(gate.scan(tmp_path),
                                 row.rule_ids["reverse"]), (row.token, dotted)


# ===========================================================================
# the deliberately_absent law keeps working, on the new forms too
# ===========================================================================

class TestDeliberateAbsenceOnDynamicForms:
    @_row_param(ABSENT_MODULE_ROWS)
    @_form_param()
    def test_absent_file_reaching_dynamically_still_reds(self, tmp_path, row, form):
        # a target left OFF an allowlist REDs as un-curated — the absence is the
        # protection, and it must not be escapable by folding or aliasing.
        for path in row.deliberately_absent:
            _write(tmp_path, path, form(row.token))
            viol = gate.scan(tmp_path)
            assert path in _paths_for(viol, row.rule_ids["unallowlisted"]), \
                (row.token, path, viol)
            (tmp_path / path).unlink()
            assert gate.scan(tmp_path) == []          # prove-then-remove


# ===========================================================================
# POSITIVE CONTROLS — no false positives
# ===========================================================================

class TestNoFalsePositives:
    @_row_param(SWEEP_ROWS)
    def test_unrelated_module_via_every_hook_spelling_is_clean(self, tmp_path, row):
        # an ordinary dynamic import of a module NO row fences — through the
        # plain hook, an aliased function and an aliased module — must not flag.
        _write(tmp_path, _STRAY,
               "import importlib\n"
               "import importlib as _il\n"
               "from importlib import import_module as _m\n"
               "a = importlib.import_module('json')\n"
               "b = _il.import_module('collections' + '.abc')\n"
               "c = _m('email.utils')\n"
               "d = __import__('os' + '.path')\n")
        assert gate.scan(tmp_path) == [], row.token

    def test_submodule_alias_is_not_treated_as_the_hook(self, tmp_path):
        # `import importlib.util as iu` binds the SUBMODULE — iu.import_module
        # is not the hook, so it must not resolve as one. Pins the alias rule's
        # narrow edge (only the exact-name form adds a binding).
        row = SWEEP_ROWS[0]
        _write(tmp_path, _STRAY,
               "import importlib.util as iu\n"
               f"m = iu.import_module('{row.token}')\n")
        facts = gate._FileFacts((tmp_path / _STRAY).read_text(encoding="utf-8"),
                                _STRAY)
        assert facts.dyn_targets == ()
        # ...and the claim that the pre-existing contiguous-literal regex still
        # fires is PINNED, not merely asserted in a comment: the file still REDs.
        assert _STRAY in _paths_for(gate.scan(tmp_path),
                                    row.rule_ids["unallowlisted"])

    @_row_param(SWEEP_ROWS)
    @pytest.mark.parametrize("body_tpl,label", [
        ("def import_module(a, b=None):\n    return a\n"
         "x = import_module({split})\n", "own def shadows the hook"),
        ("class Fake:\n    def import_module(self, n):\n        return n\n"
         "importlib = Fake()\n"
         "x = importlib.import_module({split})\n", "instance named importlib"),
        ("from importlib import import_module\n"
         "import_module = str\n"
         "x = import_module({split})\n", "hook rebound to something else"),
        ("def __import__(n):\n    return n\n"
         "x = __import__({split})\n", "builtin shadowed by a local def"),
    ], ids=["own_def", "fake_instance", "rebound", "shadowed_builtin"])
    def test_shadowed_or_unbound_hook_names_do_not_flag(self, tmp_path, row,
                                                        body_tpl, label):
        # BINDING-ACCURATE, not name-matching: a file that never binds the real
        # hook performs no import, so a baseline-zero gate must not RED on it.
        # (A plain name-match would flag every one of these.)
        split = f"'{row.token[:-2]}' '{row.token[-2:]}'"
        _write(tmp_path, _STRAY, body_tpl.format(split=split))
        assert gate.scan(tmp_path) == [], (row.token, label)

    @_row_param(SWEEP_ROWS)
    def test_unrelated_attribute_call_named_like_the_hook_is_clean(self, tmp_path, row):
        # a method that merely SHARES the hook's name on an unrelated object is
        # not a dynamic import — the AST pass requires an importlib binding.
        head, tail = _split(row.token)
        _write(tmp_path, _STRAY,
               "class Loader:\n"
               "    def import_module(self, n):\n        return n\n"
               "loader = Loader()\n"
               f"x = loader.import_module('{head}' '.{tail}')\n")
        assert gate.scan(tmp_path) == [], row.token


# ===========================================================================
# DOCUMENTED RESIDUAL — what must still NOT be reported
# ===========================================================================

class TestDocumentedResidual:
    @_row_param(SWEEP_ROWS)
    @pytest.mark.parametrize("expr", [
        "name",                                    # a parameter
        "CFG['mod']",                              # a table lookup
        "'.'.join(PARTS)",                         # runtime join
        "'{}.{}'.format(A, B)",                    # runtime format
        "'%s.%s' % (A, B)",                        # runtime %-format
        "os.environ['MOD']",                       # an env lookup
        "f'{A}.{B}'",                              # an interpolated f-string
    ], ids=["param", "lookup", "join", "format", "percent", "env", "fstring"])
    def test_runtime_computed_argument_is_not_reported(self, tmp_path, row, expr):
        # THE residual, pinned from the other side: these are not statically
        # decidable, so the gate must stay silent rather than guess. This is the
        # exact set the engine docstring claims remains residual — if one ever
        # becomes decidable, that text and this arm move together.
        _write(tmp_path, _STRAY,
               "import importlib\nimport os\n"
               "PARTS = []\nCFG = {}\nA = B = ''\n"
               "def load(name):\n"
               f"    return importlib.import_module({expr})\n")
        assert gate.scan(tmp_path) == [], (row.token, expr)

    @_row_param(SWEEP_ROWS)
    @pytest.mark.parametrize("tpl,label", [
        ("m = __import__('{parent}', globals(), locals(), ['{name}'])\n",
         "builtin fromlist"),
        ("import importlib\n"
         "a = importlib.import_module\nb = a\nm = b('{token}')\n",
         "two-hop alias chain"),
    ], ids=["fromlist", "alias_chain"])
    def test_named_decidable_residuals_are_not_reported(self, tmp_path, row,
                                                        tpl, label):
        # residual (c) in the engine docstring: forms that ARE statically
        # decidable but which this pass deliberately does not resolve yet. They
        # are NAMED there rather than hidden, and pinned here so the claim stays
        # true — if a future change closes one, this arm fails and the docstring
        # must move with it.
        parent, name = row.token.rsplit(".", 1)
        _write(tmp_path, _STRAY,
               tpl.format(parent=parent, name=name, token=row.token))
        viol = _rules_for(gate.scan(tmp_path), _STRAY)
        assert row.rule_ids["unallowlisted"] not in viol, (row.token, label)

    def test_deeply_nested_concat_does_not_crash_the_scan(self, tmp_path):
        # a fold deeper than the cap must decline to decide, NEVER raise —
        # scan() catches only SyntaxError/ValueError, so a RecursionError here
        # would abort the whole run rather than report a violation.
        row = SWEEP_ROWS[0]
        chain = " + ".join(f"'{c}'" for c in row.token)
        _write(tmp_path, _STRAY,
               f"import importlib\nm = importlib.import_module({chain})\n")
        gate.scan(tmp_path)          # must not raise
        big = " + ".join(["'a'"] * 4000)
        _write(tmp_path, _STRAY,
               f"import importlib\nm = importlib.import_module({big})\n")
        gate.scan(tmp_path)          # must not raise

    def test_getattr_walk_is_not_reported(self, tmp_path):
        # the other residual half: an attribute walk that never names a module.
        _write(tmp_path, _STRAY,
               "import importlib, sys\n"
               "def reach(root, parts):\n"
               "    obj = sys.modules[root]\n"
               "    for p in parts:\n"
               "        obj = getattr(obj, p)\n"
               "    return obj\n")
        assert gate.scan(tmp_path) == []


# ===========================================================================
# unit-level pins on the folding + resolution helpers
# ===========================================================================

class TestFoldStr:
    @pytest.mark.parametrize("src,want", [
        ("'a.b'", "a.b"),
        ("'a' + '.b'", "a.b"),
        ("'a' + '.' + 'b'", "a.b"),
        ("'a' '.b'", "a.b"),                       # adjacent-literal concat
        ("f'a.b'", "a.b"),
        ("f'a' f'.b'", "a.b"),
        ("f'{\"a\"}.b'", "a.b"),                   # literal inside a field
    ])
    def test_decidable_shapes_fold(self, src, want):
        assert gate._fold_str(ast.parse(src, mode="eval").body) == want

    @pytest.mark.parametrize("src", [
        "name",
        "'a' + name",
        "name + '.b'",
        "'.'.join(parts)",
        "'{}.{}'.format(a, b)",
        "'%s' % a",
        "f'{a}.b'",
        "f'{a!r}'",
        "CFG['k']",
        "b'a.b'",                                  # bytes, not a module name
        "1 + 2",
    ])
    def test_undecidable_shapes_fold_to_none(self, src):
        assert gate._fold_str(ast.parse(src, mode="eval").body) is None

    def test_none_input_folds_to_none(self):
        assert gate._fold_str(None) is None


class TestResolveDynTarget:
    @pytest.mark.parametrize("name,package,want", [
        ("a.b.c", None, "a.b.c"),                  # absolute passes through
        ("a.b.c", "ignored", "a.b.c"),
        (".c", "a.b", "a.b.c"),                    # level 1 = the package
        ("..c", "a.b", "a.c"),                     # level 2 = its parent
        ("...c", "a.b", None),                     # past the top-level package
        (".c", None, None),                        # relative, no package
        ("", None, None),
    ])
    def test_resolution_matches_the_stdlib_rule(self, name, package, want):
        assert gate._resolve_dyn_target(name, package) == want

    @pytest.mark.parametrize("name", [
        "c", "c.d", ".c", "..c", "...c", "....c", ".c.d", "..c.d", ".", "..",
    ])
    @pytest.mark.parametrize("package", ["a", "a.b", "a.b.c"])
    def test_differential_against_cpython_resolve_name(self, name, package):
        # ORACLE: the resolver must agree with CPython's own relative-name
        # resolution, which is what import_module actually does at runtime.
        # Disagreement either over-fences (a module the caller never named) or
        # under-fences (a real reach missed) — this arm caught the original
        # `keep < 0` off-by-one that resolved '...c' against 'a.b' to bare 'c'.
        import importlib.util as _iu
        try:
            expected = _iu.resolve_name(name, package)
        except (ImportError, ValueError):
            expected = None
        assert gate._resolve_dyn_target(name, package) == expected, \
            (name, package, expected)


class TestDynamicImportTargets:
    def _targets(self, src: str) -> list[str]:
        return gate._dynamic_import_targets(ast.parse(src))

    def test_builtin_second_positional_is_globals_not_package(self):
        # __import__(name, globals, ...) — the 2nd arg must NEVER be read as a
        # package, or the builtin form would resolve relative names wrongly.
        assert self._targets("m = __import__('a.b', {})") == ["a.b"]
        assert self._targets("m = __import__('.b', 'a')") == []

    def test_import_module_keyword_arguments_resolve(self):
        assert self._targets("import importlib\n"
                             "m = importlib.import_module(name='a.b')") == ["a.b"]
        assert self._targets("import importlib\n"
                             "m = importlib.import_module(name='.b', "
                             "package='a')") == ["a.b"]

    def test_call_with_no_arguments_is_ignored(self):
        assert self._targets("import importlib\n"
                             "m = importlib.import_module()") == []

    def test_string_literal_spelling_a_call_is_not_a_call(self):
        # the AST pass reads CALLS, never string contents — so a test fixture
        # that merely spells a call in a string adds no target.
        assert self._targets("BODY = \"importlib.import_module('a.b')\"") == []

    def test_every_hook_spelling_collects(self):
        src = ("import importlib\n"
               "import importlib as il\n"
               "from importlib import import_module\n"
               "from importlib import import_module as _m\n"
               "_im = importlib.import_module\n"
               "a = importlib.import_module('p.a')\n"
               "b = il.import_module('p' + '.b')\n"
               "c = import_module('p.c')\n"
               "d = _m(f'p' f'.d')\n"
               "e = __import__('p.e')\n"
               "f = _im('p' '.f')\n")
        assert sorted(self._targets(src)) == ["p.a", "p.b", "p.c", "p.d",
                                              "p.e", "p.f"]

    def test_walrus_argument_folds(self):
        assert self._targets("import importlib\n"
                             "m = importlib.import_module(x := 'a' '.b')") == ["a.b"]

    @pytest.mark.parametrize("src", [
        "def import_module(n):\n    return n\nm = import_module('a.b')\n",
        "class F:\n    def import_module(s, n):\n        return n\n"
        "importlib = F()\nm = importlib.import_module('a.b')\n",
        "from importlib import import_module\nimport_module = str\n"
        "m = import_module('a.b')\n",
        "def __import__(n):\n    return n\nm = __import__('a.b')\n",
        "import importlib.util as iu\nm = iu.import_module('a.b')\n",
        "m = import_module('a.b')\n",            # never imported: NameError at runtime
    ], ids=["own_def", "fake_instance", "rebound", "shadowed_builtin",
            "submodule_alias", "never_bound"])
    def test_unbound_or_shadowed_hooks_collect_nothing(self, src):
        assert self._targets(src) == []

    def test_alias_chain_beyond_one_hop_is_conservative(self):
        # documented residual (c): resolves to nothing rather than guessing.
        assert self._targets("import importlib\n"
                             "a = importlib.import_module\nb = a\n"
                             "m = b('x.y')\n") == []

    def test_builtin_fromlist_is_not_resolved(self):
        # documented residual (c): decidable, deliberately not wired yet.
        assert self._targets(
            "m = __import__('a', globals(), locals(), ['b'])") == ["a"]

    def test_malformed_package_is_undecidable(self):
        assert self._targets("import importlib\n"
                             "m = importlib.import_module('.b', 'a..c')") == []

    def test_deeply_nested_fold_returns_none_not_recursionerror(self):
        chain = " + ".join(["'a'"] * 5000)
        assert self._targets(f"import importlib\n"
                             f"m = importlib.import_module({chain})") == []
