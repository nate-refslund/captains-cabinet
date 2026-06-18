"""Thin shim that imports the screenpipe retrodiction scoring engine into the
Cabinet's framework namespace.

The fidelity harness REUSES retrodiction's leak-safe scoring logic
(extract_cases / score_case / judge_decision / cusum / score_draft /
author_centroid / aggregate / mechanics_flags) — it does NOT re-derive it
(docs/fidelity-harness-design-2026-06-18.md §25-37). This module is the single
import seam; the rest of framework/fidelity/ imports from
`framework.fidelity.retro`, never from a hardcoded screenpipe path.

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

# Resolve the retrodiction pipe dir. Override via CABINET_RETRO_PIPE_DIR for
# tests / non-default installs; default to the canonical screenpipe location.
RETRO_PIPE_DIR = Path(
    os.environ.get(
        "CABINET_RETRO_PIPE_DIR",
        str(Path.home() / ".screenpipe" / "pipes" / "retrodiction"),
    )
).expanduser()
_SHARED_DIR = RETRO_PIPE_DIR.parent / "_shared"


def retro_available() -> bool:
    """True iff the retrodiction lib is importable from RETRO_PIPE_DIR."""
    return (RETRO_PIPE_DIR / "lib.py").exists()


# Put the pipe dir + its _shared deps on sys.path (idempotent) so the lib's
# transitive imports (sp_lib, commitments_lib, draft_lib) resolve.
for _p in (str(RETRO_PIPE_DIR), str(_SHARED_DIR), str(RETRO_PIPE_DIR.parent)):
    if _p not in sys.path and Path(_p).exists():
        sys.path.insert(0, _p)

_spec = importlib.util.spec_from_file_location(
    "retrodiction_lib", str(RETRO_PIPE_DIR / "lib.py")
)
if _spec is None or _spec.loader is None:  # pragma: no cover - install guard
    raise ImportError(f"retrodiction lib not found at {RETRO_PIPE_DIR / 'lib.py'}")
_retro = importlib.util.module_from_spec(_spec)
sys.modules["retrodiction_lib"] = _retro
_spec.loader.exec_module(_retro)

# Re-export the reused surface (import/port — do NOT rebuild these).
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

__all__ = [
    "RETRO_PIPE_DIR", "retro_available",
    "extract_cases", "score_case", "judge_decision", "score_draft",
    "author_centroid", "aggregate", "cusum", "mechanics_flags",
    "parse_json_block", "lessons_before", "parse_conversations", "cosine",
    "JUDGE_SYSTEM", "BASELINE_SYSTEM", "RETRO_ADDENDUM", "LLM_MODEL",
]
