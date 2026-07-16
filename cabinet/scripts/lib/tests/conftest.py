"""pytest config for the cabinet/scripts/lib test suite.

(Originally written for the FW-023 ETL-transform tests; those were carved
out of this directory to the Spec-039 set in f855ae96 (R073). Of the ETL
modules only etl-common.py remains in lib/, loaded here by
test_library_mcp_client.py.)

Stubs `requests` + `yaml` in sys.modules ONLY when the real package is not
installed. Tests can then import lib modules in containers lacking those
packages, while environments with real packages installed (CI, dev
machines post-FW-024) get the real modules — so framework tests that share
the pytest session (and need `yaml.safe_load`) don't get poisoned by a stub
import order race.

Also inserts the parent `lib/` dir onto sys.path so underscore-named lib
modules import directly (e.g. `from work_graph import WorkGraph`); the
hyphenated modules (etl-common.py, library-mcp-client.py, …) load via
explicit spec_from_file_location helpers in their test files.

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
