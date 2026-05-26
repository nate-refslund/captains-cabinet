"""pytest config for ETL transform tests (FW-023).

Stubs `requests` + `yaml` in sys.modules ONLY when the real package is not
installed. Pure-function tests (_map_state, _map_status, _extract_fw_marker)
can then import etl-linear / etl-github / etl-common in containers lacking
those packages, while environments with real packages installed (CI, dev
machines post-FW-024) get the real modules — so framework tests that share
the pytest session (and need `yaml.safe_load`) don't get poisoned by a stub
import order race.

Also inserts the parent `lib/` dir onto sys.path so `test_etl_fixtures` +
the hyphenated ETL modules resolve.

History: previously this file unconditionally stubbed yaml/requests, which
broke framework tests running in the same pytest session once the
convergence branch added compiler/lifecycle imports that need real yaml.
The new behaviour: stub only on ImportError, real package wins otherwise.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path


def _ensure_module(name: str) -> None:
    """Import real module if available; otherwise install a bare stub.

    Idempotent — if the module is already in sys.modules (real or stub),
    leave it alone.
    """
    if name in sys.modules:
        return
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = types.ModuleType(name)


for _mod in ("requests", "yaml"):
    _ensure_module(_mod)

_LIB_DIR = Path(__file__).parent.parent.resolve()
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
