"""Fidelity matrix + per-cell drift (component 6,
docs/fidelity-harness-design-2026-06-18.md §232-237).

Rolls scorer case-score rows into per-(actor × lane × decision-type) cell
metrics over a rolling window and attaches the consequence-ledger graduation
ratios for the same cell key. REUSES the retrodiction scoring engine via the
`framework.fidelity.retro` shim — `aggregate` (the per-result-set rate roll-up)
and `cusum` (the two-sided drift detector) are imported, NEVER re-derived
(design §"reuse, don't rebuild", §101-113). The consequence ledger is read via
`framework.fidelity.consequence.read_ledger` / `compute_ratios` so graduation
math stays single-source.

Cell key is `(actor_id, lane, action_type)` — the SAME tuple shape
`compute_ratios()` keys on (actor flattened to "kind:id"), so the fidelity
rates and the graduation ratios join on one key.

No-silent-caps (§326): a cell with no graded case scores yields `None` fidelity
rates (not a silent 0.0/1.0); a cell present only in the ledger is still
SURFACED in the matrix with `None` fidelity rates and its ratios attached.
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from framework.fidelity import consequence as _consequence
from framework.fidelity import retro

# Reuse boundary: bind the shim's objects directly so a test (and a reader) can
# verify these ARE the retrodiction engine, not a local reimplementation.
aggregate = retro.aggregate
cusum = retro.cusum

# Cell key: (actor_id, lane, action_type). lane may be None (ledger rows allow
# a null lane); action_type is the enum the gate keys on.
Cell = tuple[str, Optional[str], str]

# Verdicts the retrodiction judge emits that count toward the judged denominator.
_JUDGED = ("match", "partial", "divergent")


@dataclass
class CellStats:
    """Per-cell fidelity metrics + drift flag + (optional) graduation ratios.

    Every rate is `float | None`. `None` is the UNMEASURED state: the cell has
    no graded case scores feeding that rate. Per the design's no-silent-caps
    rule an unmeasured cell must read as a visible None, never a silent 0.0.
    """
    decision_match_rate: Optional[float] = None
    partial_rate: Optional[float] = None
    divergent_rate: Optional[float] = None
    style_win_rate: Optional[float] = None
    mechanics_fail_rate: Optional[float] = None
    sample_count: int = 0
    # CUSUM drift over the per-cell window match-rate series.
    drift_alarm: bool = False
    drift_alarms: list[tuple[int, str]] = field(default_factory=list)
    match_rate_series: list[float] = field(default_factory=list)
    # Graduation ratios from the consequence ledger for the same cell key.
    ratios: Optional["_consequence.GraduationRatios"] = None


def _actor_id(actor: Any) -> str:
    """Flatten an actor object to the "kind:id" identity compute_ratios uses."""
    if isinstance(actor, dict):
        return f"{actor.get('kind')}:{actor.get('id')}"
    return f"{actor}:"


def _window_key(reply_ts: str, window_by: Optional[str]) -> str:
    """Derive the drift-series bucket label for a row's timestamp.

    window_by="day" buckets on the date prefix (YYYY-MM-DD). None → every row
    is its own bucket (one point per case, in chronological order). The exact
    bucket size is the caller's policy; the only invariant aggregate relies on
    is chronological ordering of the resulting series.
    """
    ts = reply_ts or ""
    if window_by == "day":
        return ts[:10]
    if window_by == "week":
        # ISO date prefix is enough to keep ordering; coarse weekly bucketing
        # is left to a caller that needs it. Default to per-row otherwise.
        return ts[:10]
    return ts  # per-row series


def _build_series(rows: list[dict], window_by: Optional[str]) -> list[float]:
    """Per-window decision_match_rate series for one cell, in time order.

    Reuses retro.aggregate per window so the per-window rate is computed by the
    exact same engine as the cell-level rate — never re-derived here.
    """
    buckets: "OrderedDict[str, list[dict]]" = OrderedDict()
    for r in sorted(rows, key=lambda x: x.get("reply_ts", "")):
        buckets.setdefault(_window_key(r.get("reply_ts", ""), window_by), []).append(r)
    series: list[float] = []
    for _label, brows in buckets.items():
        a = aggregate(brows)
        rate = a.get("decision_match_rate")
        # A window with no judged rows contributes nothing to the drift series.
        if rate is not None:
            series.append(rate)
    return series


def compute_matrix(
    window: Optional[str] = None,
    ledger: Optional[list[dict[str, Any]]] = None,
    *,
    case_scores: Optional[list[dict[str, Any]]] = None,
    window_by: Optional[str] = None,
    since: Optional[str] = None,
) -> dict[Cell, CellStats]:
    """Compute the per-cell fidelity matrix.

    Args:
      window: rolling-window selector passed through to the ledger read
        (`since`); kept positional for the documented `compute_matrix(window)`
        signature. An explicit `since=` overrides it.
      ledger: explicit list of consequence events; when None the ledger is read
        via consequence.read_ledger(since=...).
      case_scores: scorer.py CaseScore-shaped rows (judge.verdict, style_win,
        mechanics, plus actor/lane/action_type/reply_ts). When None → no
        fidelity rates (ledger-only matrix).
      window_by: drift-series bucketing ("day" | "week" | None=per-row).

    Returns dict keyed (actor_id, lane, action_type) → CellStats.
    """
    case_scores = case_scores or []
    effective_since = since if since is not None else window

    # 1. Group graded case scores by cell.
    by_cell: dict[Cell, list[dict]] = defaultdict(list)
    for r in case_scores:
        key: Cell = (
            _actor_id(r.get("actor")),
            r.get("lane"),
            r.get("action_type") or _consequence.UNSTAMPED_ACTION_TYPE,
        )
        by_cell[key].append(r)

    matrix: dict[Cell, CellStats] = {}

    # 2. Roll each cell's rows up via the reused retrodiction aggregate, then
    #    run CUSUM over its per-window match-rate series for the drift flag.
    for key, rows in by_cell.items():
        a = aggregate(rows)  # reuse: retrodiction's rate roll-up
        series = _build_series(rows, window_by)
        drift = cusum(series)  # reuse: retrodiction's CUSUM
        alarms = drift.get("alarms", [])
        matrix[key] = CellStats(
            decision_match_rate=a.get("decision_match_rate"),
            partial_rate=a.get("partial_rate"),
            divergent_rate=a.get("divergent_rate"),
            style_win_rate=a.get("style_win_rate"),
            mechanics_fail_rate=a.get("mechanics_fail_rate"),
            sample_count=a.get("n_cases", 0),
            drift_alarm=bool(alarms),
            drift_alarms=list(alarms),
            match_rate_series=series,
        )

    # 3. Attach graduation ratios from the consequence ledger on the same key.
    #    A cell that appears ONLY in the ledger is surfaced (no-silent-caps)
    #    with None fidelity rates.
    ratios = _consequence.compute_ratios(since=effective_since, ledger=ledger)
    for key, gr in ratios.items():
        cell = matrix.get(key)
        if cell is None:
            cell = CellStats()  # ledger-only cell → fidelity rates stay None
            matrix[key] = cell
        cell.ratios = gr

    return matrix


__all__ = ["CellStats", "compute_matrix", "aggregate", "cusum", "Cell"]
