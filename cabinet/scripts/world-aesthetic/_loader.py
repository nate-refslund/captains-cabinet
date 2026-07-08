"""Load the gates package under a unique name — no sys.path pollution.

WHY: cabinet/scripts/gates is an existing package imported as top-level
"gates" by the framework suite. This dir's gates/ package must therefore
never be importable as "gates"; everything (runner, calibrate, tests) goes
through load_gates(), which registers it as "world_aesthetic_gates" via
importlib with an explicit file location.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PKG_NAME = "world_aesthetic_gates"
HERE = Path(__file__).resolve().parent


def load_gates():
    mod = sys.modules.get(PKG_NAME)
    if mod is not None:
        return mod
    pkg_dir = HERE / "gates"
    spec = importlib.util.spec_from_file_location(
        PKG_NAME, pkg_dir / "__init__.py",
        submodule_search_locations=[str(pkg_dir)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG_NAME] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(PKG_NAME, None)
        raise
    return mod
