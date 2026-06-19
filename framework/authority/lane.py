"""Shared lane resolver — the F+A join key's lane dimension [FIX-4].

ONE source of truth for the lane a session is scoped to, used by BOTH the
policy-engine gate (A) and the consequence emitter / `compute_ratios` (F) so
the cell tuple `(officer, lane, action_type)` is identical on both sides.

`start-officer.sh` exports `CABINET_LANE` (derived from `--project` / active
context) as the load-bearing source; `PROJECT` is the fallback; `None` when
neither is set (an estate-wide action). Pure except for the two named env
reads — no path interpolation, no filesystem access, no injection surface
(see docs/authority-matrix-design-2026-06-19.md §3, FIX-4).
"""
from __future__ import annotations

import os


def resolve_lane() -> str | None:
    """Return the active lane slug, or None when unscoped.

    Precedence: CABINET_LANE (load-bearing, set by start-officer.sh) →
    PROJECT (fallback) → None. An empty-string env value is treated as unset
    and falls through, so a blank CABINET_LANE never silently shadows PROJECT.
    """
    return os.environ.get("CABINET_LANE") or os.environ.get("PROJECT") or None
