"""COG-3 STEP 0 — the objectives SYMBOL-level import boundary (contract §6.5
bullet 3 + §5.1 discipline 1), tests-first, gates-before-code.

The coarse module gate (test_cog3_import_gate.py) says framework/objectives/ MAY
read the cortex; this suite pins WHICH cortex names it may import (only the seven
enumerated query-surface symbols) and that every as_of read is defaults-only. Two
static AST pins + one runtime transitive-closure test, each with the negative
control mutant it names (COG-2 §8 law):

  * symbol pin: `from framework.cortex.query import load_beliefs` (or engine /
    adapters / fidelity / ovi / authority / the cortex module object / a
    third-party dep) is RED; only the 7 symbols fold.
  * transitive closure: importing framework.objectives must pull NOTHING under
    framework.{authority,acting,frontdoor,fidelity,missions,ovi} — the scratch
    mutant that imports framework.fidelity.consequence goes RED because
    consequence.py:33 top-level-imports framework.authority (attack C-B1).
  * defaults-only as_of: any fold-seam kwarg (rederive / scope_mode / lineage /
    …) — or dimension/source, or a **splat — is RED; only the canonical
    scope+observation read folds.

Green-by-vacuity today (framework/objectives/ absent). S0: python3.12, no DB.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):        # tests/ is a package: put it on the path
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog3_import_ast as L  # noqa: E402


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# ===========================================================================
# the symbol-level import pin (§6.5 bullet 3)
# ===========================================================================

class TestSymbolImportPin:
    def test_real_tree_is_green_by_vacuity(self):
        # framework/objectives/ does not exist yet — the pin folds, armed.
        assert L.objectives_import_violations(_REPO) == []

    def test_the_seven_sanctioned_symbols_fold_clean(self, tmp_path):
        _write(tmp_path, "framework/objectives/query.py",
               "from __future__ import annotations\n"
               "import json\n"
               "from pathlib import Path\n"
               "from framework.cortex.query import (\n"
               "    load_beliefs_verified, as_of, BeliefView, AsOfResult,\n"
               "    ScopeError, StoreCorruptError, UNKNOWN)\n"
               "from framework.objectives import model\n")
        assert L.objectives_import_violations(tmp_path) == []

    def test_load_beliefs_symbol_is_red(self, tmp_path):
        # THE named escape: load_beliefs is the C-F15-bypassing trusted-bytes
        # loader — importing it from the query module must RED even though the
        # module is the sanctioned one.
        _write(tmp_path, "framework/objectives/graph.py",
               "from framework.cortex.query import as_of, load_beliefs\n")
        v = L.objectives_import_violations(tmp_path)
        assert any("load_beliefs" in x and x.endswith("load_beliefs") for x in v), v
        # as_of on the same line is fine; only load_beliefs is flagged
        assert not any(x.endswith(":as_of") for x in v)

    @pytest.mark.parametrize("stmt", [
        "from framework.cortex import query\n",                  # the module object
        "from framework.cortex import engine\n",
        "from framework.cortex.engine import resolve_relationships\n",
        "from framework.cortex.adapters import build_consequence_protos\n",
        "from framework.fidelity.consequence import _REVIEW_SOURCES\n",
        "from framework.ovi.compute import composite\n",
        "from framework.authority.classifier import ACTION_TYPES\n",
        "from framework.acting import runner\n",
        "from framework.frontdoor import door\n",
        "import framework.cortex\n",
        "import framework.cortex.query\n",                       # module object, dotted
        "import framework.ovi\n",
        "from framework import cortex\n",                        # alias spelling
        "import yaml\n",                                         # third-party dep
        "from ..cortex import query\n",                          # relative escape -> framework.cortex
    ])
    def test_forbidden_imports_are_red(self, tmp_path, stmt):
        _write(tmp_path, "framework/objectives/x.py", stmt)
        assert L.objectives_import_violations(tmp_path), stmt

    def test_internal_relative_imports_fold_clean(self, tmp_path):
        # a submodule reaching its own package by relative import is internal.
        _write(tmp_path, "framework/objectives/adapters/roots.py",
               "from .. import model\n"
               "from ..query import serve\n"
               "from . import mission_inputs\n")
        assert L.objectives_import_violations(tmp_path) == []

    def test_stdlib_and_future_fold_clean(self, tmp_path):
        _write(tmp_path, "framework/objectives/model.py",
               "from __future__ import annotations\n"
               "import json, hashlib\n"
               "from dataclasses import dataclass\n"
               "from pathlib import Path\n"
               "from typing import Optional\n")
        assert L.objectives_import_violations(tmp_path) == []


# ===========================================================================
# the transitive import-closure test (§6.5 bullet 3, attack C-B1)
# ===========================================================================

_FORBIDDEN_NS = ("framework.authority", "framework.acting", "framework.frontdoor",
                 "framework.fidelity", "framework.missions", "framework.ovi")


def _closure_after_import(module_name: str, extra_path: Path | None = None):
    """Subprocess-import `module_name` (framework importable via cwd=_REPO) and
    return (returncode, stderr, forbidden_modules_loaded)."""
    lines = ["import sys, json"]
    if extra_path is not None:
        lines.append(f"sys.path.insert(0, {str(extra_path)!r})")
    lines += [
        f"import {module_name}",
        f"FZ = {_FORBIDDEN_NS!r}",
        "loaded = sorted(m for m in sys.modules "
        "if any(m == f or m.startswith(f + '.') for f in FZ))",
        "print(json.dumps(loaded))",
    ]
    r = subprocess.run([sys.executable, "-c", "\n".join(lines)],
                       cwd=str(_REPO), capture_output=True, text=True)
    loaded = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else []
    return r.returncode, r.stderr, loaded


class TestTransitiveClosure:
    def test_objectives_closure_is_clean_or_absent(self):
        rc, stderr, loaded = _closure_after_import("framework.objectives")
        if rc != 0 and "No module named 'framework.objectives'" in stderr:
            pytest.skip("VACUITY: framework.objectives absent this phase — the "
                        "transitive-closure gate is armed for when it lands.")
        assert rc == 0, stderr
        assert loaded == [], (
            "framework.objectives' import closure reached the fidelity/authority/"
            f"action trees: {loaded}")

    def test_mutant_importing_consequence_loads_authority(self, tmp_path):
        # the exact C-B1 escape: a module that imports framework.fidelity.consequence
        # transitively loads framework.authority (consequence.py:33). The closure
        # check MUST see it — proving the gate is not a no-op.
        _write(tmp_path, "_cog3_scratch_leak/__init__.py",
               "import framework.fidelity.consequence  # MUTANT: pulls the action plane\n")
        rc, stderr, loaded = _closure_after_import("_cog3_scratch_leak",
                                                   extra_path=tmp_path)
        assert rc == 0, stderr
        assert "framework.authority" in loaded, loaded

    def test_clean_scratch_pkg_closure_is_empty(self, tmp_path):
        # the anti-no-op control: a pkg importing only stdlib has an EMPTY forbidden
        # closure, so the check is genuinely discriminating (not always-RED).
        _write(tmp_path, "_cog3_scratch_clean/__init__.py",
               "import json, hashlib  # only stdlib\n")
        rc, stderr, loaded = _closure_after_import("_cog3_scratch_clean",
                                                   extra_path=tmp_path)
        assert rc == 0, stderr
        assert loaded == []


# ===========================================================================
# the defaults-only as_of pin (§5.1 discipline 1)
# ===========================================================================

class TestDefaultsOnlyAsOf:
    def test_real_tree_is_green_by_vacuity(self):
        assert L.asof_default_violations(_REPO) == []

    def test_canonical_read_folds_clean(self, tmp_path):
        _write(tmp_path, "framework/objectives/graph.py",
               "def build():\n"
               "    a = as_of(beliefs, subject_key, scope=sc, observation=cut)\n"
               "    b = as_of(beliefs, subject_key=sk, scope=sc, observation=cut)\n"
               "    return a, b\n")
        assert L.asof_default_violations(tmp_path) == []

    @pytest.mark.parametrize("kwarg", [
        "rederive=False",
        "scope_mode='lenient'",
        "lineage='correlation'",
        "unknown_mode='implicit'",
        "supersession_order='ts'",
        "fence_axis='source'",
        "dimension='budget'",
        "source='2026-01-01T00:00:00Z'",
    ])
    def test_nondefault_kwarg_is_red(self, tmp_path, kwarg):
        _write(tmp_path, "framework/objectives/graph.py",
               "def build():\n"
               f"    return as_of(beliefs, subject_key, scope=sc, {kwarg})\n")
        v = L.asof_default_violations(tmp_path)
        assert v, kwarg
        assert all(x.startswith("framework/objectives/graph.py:"
                                + L.RULE_ASOF) for x in v), v

    def test_kwargs_splat_is_red(self, tmp_path):
        _write(tmp_path, "framework/objectives/graph.py",
               "def build():\n"
               "    return as_of(beliefs, subject_key, scope=sc, **opts)\n")
        v = L.asof_default_violations(tmp_path)
        assert any(x.endswith("**splat") for x in v), v

    def test_attribute_form_asof_is_scanned(self, tmp_path):
        # even a q.as_of(...) attribute call (which the symbol pin already forbids
        # by module) is defended here — belt and suspenders.
        _write(tmp_path, "framework/objectives/graph.py",
               "def build():\n"
               "    return q.as_of(beliefs, sk, scope=sc, rederive=False)\n")
        assert any(x.endswith(":rederive") for x in L.asof_default_violations(tmp_path))

    def test_non_asof_call_with_those_kwargs_is_ignored(self, tmp_path):
        # narrowness: another function that happens to take rederive= is NOT an
        # as_of call and must not be flagged.
        _write(tmp_path, "framework/objectives/graph.py",
               "def build():\n"
               "    return some_other(rederive=False, lineage='x')\n")
        assert L.asof_default_violations(tmp_path) == []
