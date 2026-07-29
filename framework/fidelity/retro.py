"""Thin shim that imports the personal-source adapter's retrodiction scoring
engine into the Cabinet's framework namespace.

The fidelity harness REUSES retrodiction's leak-safe scoring logic
(extract_cases / score_case / judge_decision / cusum / score_draft /
author_centroid / aggregate / mechanics_flags) — it does NOT re-derive it
(docs/fidelity-harness-design-2026-06-18.md §25-37). This module is the single
import seam; the rest of framework/fidelity/ imports from
`framework.fidelity.retro`, never from a hardcoded adapter-specific path.

The lib is loaded via an EXPLICIT importlib spec (unique module name
'retrodiction_lib') so it can never shadow or be shadowed by another
top-level `lib` on sys.path during a combined `pytest framework/` run. The
lib's own bootstrap (inserting _PIPES/_shared on sys.path for sp_lib /
commitments_lib / draft_lib) still runs at load.

IMPORTANT (3.9.6 boundary): this module transitively imports the retrodiction
lib, which must remain importable under the framework interpreter (system
Python 3.9.6). test_retro_shim.py asserts this so an upstream 3.10+-only
construct fails loudly at the F1 boundary, not mid-batch.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from framework import env  # instance-config resolver (retro_pipe_dir)

# Resolve the retrodiction pipe dir. Override via CABINET_RETRO_PIPE_DIR (tests /
# non-default installs) — read verbatim here so THAT behavior stays
# byte-identical; else the instance-config resolver (framework.env.retro_pipe_dir
# reads instance/config/platform.yml -> retro_pipe_dir), so this universal-base
# shim carries no launcher path (source-adapter boundary, the parallel EVALUATION
# seam). A generic deployment resolves neither -> a non-existent sentinel dir ->
# retro_available() False -> the scoring stub raises with guidance on first use.
# The SCORING functions live in framework (the EvaluationEngine); only this PATH
# is instance-bound. Byte-identical on this instance to the removed default.
_RETRO_DIR = os.environ.get("CABINET_RETRO_PIPE_DIR") or env.retro_pipe_dir()
RETRO_PIPE_DIR = (
    Path(_RETRO_DIR).expanduser() if _RETRO_DIR
    else Path(__file__).resolve().parent / "_retrodiction-absent"
)
_SHARED_DIR = RETRO_PIPE_DIR.parent / "_shared"


def _exists_unprivileged(p: Path) -> bool:
    """``p.exists()`` that treats an UNREADABLE path as absent instead of
    crashing at import. The null-hatch gate (operative-egg A15/P1, the sole
    clean-room CI job since 2026-07-29) plants an unreadable stand-in for
    the adapter's state dir as present-but-mode-000, and ``Path.exists()``
    PROPAGATES EACCES (pathlib
    swallows only ENOENT/ENOTDIR/EBADF/ELOOP) — which took this module down at
    import. A lib we cannot stat is a lib we cannot import: honest False,
    degrade to the ``_RetroUnavailable`` stub exactly like plain absence."""
    try:
        return p.exists()
    except OSError:  # EACCES/EPERM — unreadable ≡ absent for this probe
        return False


def retro_available() -> bool:
    """True iff the retrodiction lib is importable from RETRO_PIPE_DIR."""
    return _exists_unprivileged(RETRO_PIPE_DIR / "lib.py")


# Put the pipe dir + its _shared deps on sys.path (idempotent) so the lib's
# transitive imports (sp_lib, commitments_lib, draft_lib) resolve.
for _p in (str(RETRO_PIPE_DIR), str(_SHARED_DIR), str(RETRO_PIPE_DIR.parent)):
    if _p not in sys.path and _exists_unprivileged(Path(_p)):
        sys.path.insert(0, _p)

# Import-safe when the lib is absent (2026-07-02, CI run 2861848…): a clean
# runner / flavor-B Mini has no adapter-specific state dir, and an import-time crash here
# took 18 test modules down at COLLECTION. Absence now degrades to a stub
# module whose every attribute raises with guidance on FIRST USE — importers
# can `import retro` + check `retro_available()`; only actual scoring calls
# require the lib. Deletes when plan A2.1 vendors the lib into framework/.
class _RetroUnavailable:
    def __getattr__(self, attr):
        # Honor the dunder contract: CPython's from-import machinery probes
        # __path__ (hasattr in _handle_fromlist) and pickling/copy probe other
        # dunders; those MUST raise AttributeError, not RuntimeError, or a plain
        # `from framework.fidelity.retro import retro_available` crashes at import
        # on a retro-less tree (the import-then-branch contract this module
        # documents). Only real scoring-attribute misses raise the guidance error.
        if attr.startswith("__") and attr.endswith("__"):
            raise AttributeError(attr)
        raise RuntimeError(
            f"retrodiction lib not available (looked in {RETRO_PIPE_DIR}) — "
            f"attribute {attr!r} needs the personal-source adapter's retrodiction pipe "
            "(flavor-A coupling; set CABINET_RETRO_PIPE_DIR or wait for the "
            "A2.1 vendoring). retro_available() lets callers branch cleanly."
        )


if retro_available():
    _spec = importlib.util.spec_from_file_location(
        "retrodiction_lib", str(RETRO_PIPE_DIR / "lib.py")
    )
    if _spec is None or _spec.loader is None:  # pragma: no cover - install guard
        raise ImportError(f"retrodiction lib not found at {RETRO_PIPE_DIR / 'lib.py'}")
    _retro = importlib.util.module_from_spec(_spec)
    sys.modules["retrodiction_lib"] = _retro
    _spec.loader.exec_module(_retro)
else:  # pragma: no cover - exercised only on lib-less installs (CI, flavor B)
    _retro = _RetroUnavailable()

# Re-export the reused surface (import/port — do NOT rebuild these). On a
# lib-less install the names resolve lazily through PEP 562 module __getattr__
# → the stub, which raises with guidance at FIRST USE, never at import.
if retro_available():
    extract_cases = _retro.extract_cases
    score_case = _retro.score_case
    judge_decision = _retro.judge_decision
    score_draft = _retro.score_draft
    author_centroid = _retro.author_centroid
    aggregate = _retro.aggregate
    cusum = _retro.cusum
    mechanics_flags = _retro.mechanics_flags
    parse_json_block = _retro.parse_json_block
    lessons_before = _retro.lessons_before
    parse_conversations = _retro.parse_conversations
    cosine = _retro.cosine

    JUDGE_SYSTEM = _retro.JUDGE_SYSTEM
    BASELINE_SYSTEM = _retro.BASELINE_SYSTEM
    RETRO_ADDENDUM = _retro.RETRO_ADDENDUM
    LLM_MODEL = _retro.LLM_MODEL
else:  # pragma: no cover - exercised only on lib-less installs (CI, flavor B)
    def __getattr__(name):  # PEP 562: module imports cleanly, surface fails loudly
        # Dunder probes (import machinery's __path__, pickling, etc.) must raise
        # AttributeError so `from framework.fidelity.retro import <name>` on a
        # retro-less tree does not crash at import — the import-then-branch
        # contract. Non-dunder scoring names still fail loudly via the stub.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return getattr(_retro, name)  # _RetroUnavailable raises with guidance

__all__ = [
    "RETRO_PIPE_DIR", "retro_available",
    "extract_cases", "score_case", "judge_decision", "score_draft",
    "author_centroid", "aggregate", "cusum", "mechanics_flags",
    "parse_json_block", "lessons_before", "parse_conversations", "cosine",
    "JUDGE_SYSTEM", "BASELINE_SYSTEM", "RETRO_ADDENDUM", "LLM_MODEL",
]
