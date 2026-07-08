"""Load the gates/judge packages under unique names — no sys.path pollution.

WHY: cabinet/scripts/gates is an existing package imported as top-level
"gates" by the framework suite. This dir's gates/ package must therefore
never be importable as "gates"; everything (runner, calibrate, tests) goes
through load_gates(), which registers it as "world_aesthetic_gates" via
importlib with an explicit file location. load_judge() applies the same
contract to judge/ ("world_aesthetic_judge" — the vision-judge protocol);
its CLI modules also self-anchor onto that name when executed directly.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PKG_NAME = "world_aesthetic_gates"
JUDGE_PKG_NAME = "world_aesthetic_judge"
HERE = Path(__file__).resolve().parent


def _load_pkg(name: str, pkg_dir: Path):
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location(
        name, pkg_dir / "__init__.py",
        submodule_search_locations=[str(pkg_dir)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


def load_gates():
    return _load_pkg(PKG_NAME, HERE / "gates")


def load_judge():
    return _load_pkg(JUDGE_PKG_NAME, HERE / "judge")
