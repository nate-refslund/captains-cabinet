"""F2 — per-cell autonomy state machine (the graduation gate's confidence read).

`evaluate(cell) -> {state, evidence}` is the SINGLE confidence source A (the
authority-matrix gate) reads. A never recomputes confidence — it reads what F
precomputes here. See:

  * docs/fidelity-harness-design-2026-06-18.md §7 (`graduation.py`) + §North-star
    (fitness = intent-served, NOT correction-count).
  * docs/authority-matrix-design-2026-06-19.md §3 (Component 3, the F->A seam)
    + §1 Component-1 bars (the ONE reconciled bar).

cell = (officer_actor_id, lane, action_type), e.g.
  ("officer:cos", "polads", "internal_message").

state in {unmeasured, propose_only, eligible, graduated, demote}:

  * `unmeasured`  — no data, or the review-confirmed denominator is 0 (None
    ratios). FAIL-SAFE: never silently `eligible`/`graduated`. (Ground-2
    no-silent-caps: an unmeasured cell is a VISIBLE state, not a pass.)
  * `propose_only`— measured but below the bar (too few samples, or match_rate
    under the floor) — the fail-safe verdict the gate proposes on.
  * `eligible`    — meets the sample floor + match bar, but the WRONG-ONLY
    recency clock has not yet matured: either the last `wrong` verdict is
    younger than `recency_clean_days`, or the cell itself is younger than the
    ~7d seasoning floor. Clean samples ACCUMULATE — they never reset the
    clock (defect-3 fix; see step 5 in `evaluate`). Not yet auto.
  * `graduated`   — clears the FULL bar (samples, match_rate, last-10 divergent,
    recency-clean). The only state that lets the gate auto.
  * `demote`      — a fresh wrong-verdict cluster (>=2 divergent in the last 10,
    tighter than the promotion `<=1`) drops the cell sub-bar. Ramp-down is
    designed as carefully as ramp-up.

THE BAR IS READ FROM `framework/policies/authority-matrix.yml` (via the matrix
loader) — graduation does NOT hardcode a second bar (A0 reconciled-bar rule
[FIX-1 reconcile]). Per-decision-type overrides are keyed by risk_class
(internal_comms 0.90/30/0/21, deploy_nonprod 0.95/30/0/21); everything else
uses `default` (0.85/20/1/14).

Fitness is `outcome_held_rate x review_confirmed_rate` — a POSITIVE signal
(outcome held AND the review confirmed it), never a correction-count (gameable;
rewards timidity). `match_rate` for the bar is `review_confirmed_rate` (the
decision-match channel); fitness is a stricter positive multiplier reported in
the evidence and required to be > 0 before a cell can graduate.

System Python is 3.9.6; only stdlib + the in-repo matrix loader / consequence
reader are used. This module is pure read-only over the consequence ledger and
the matrix YAML — no IO writes, no exit codes, no gate behavior (that is A's
`_eval_authority_matrix`).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.fidelity.consequence import (  # noqa: E402
    DIRECT_DEMOTE_REF,
    GraduationRatios,
    compute_ratios,
    read_ledger,
)


# Demotion trigger threshold: a divergent CLUSTER in the most recent N scored
# cases. Tighter than the promotion bar's max_divergent_last10 (which is the
# ceiling a graduated cell may carry) — >=2 fresh divergents demote.
# docs/authority-matrix-design-2026-06-19.md §4 trigger-3.
_DEMOTE_DIVERGENT_IN_LAST10 = 2
_LAST_N = 10

# [defect-3 fix] Cell-age seasoning floor (days). The recency-clean gate in
# `evaluate` step 5 is a WRONG-ONLY clock (clean samples accumulate; only a
# wrong verdict resets), so a brand-new cell that collects 20+ clean samples
# in one afternoon would otherwise clear the full bar same-day. The ratified
# rec pairs the wrong-only clock with this floor (proactive-org-strategy
# 2026-07-03 rec-2 / grand-plan Captain-Moment-1: "wrong-only recency clock +
# ~7d seasoning"): a cell must have EXISTED — first scored sample — at least
# this many days before it may graduate. Age only grows, so unlike the old
# days-since-last-SAMPLE clock it can never be reset by fresh clean activity.
_SEASONING_DAYS = 7.0


# --------------------------------------------------------------------------
# Bar (read from the YAML — never hardcoded here)
# --------------------------------------------------------------------------

def _load_bars() -> dict[str, dict[str, Any]]:
    """Return the per-decision-type bar table from authority-matrix.yml.

    The matrix loader is the single source of truth; this function is the seam
    the tests monkeypatch to prove the bar is read, not hardcoded. Keys are
    risk_class names (`default`, `internal_comms`, `deploy_nonprod`); each value
    has match_rate / samples / max_divergent_last10 / recency_clean_days.
    """
    from framework.authority.matrix import load_matrix, matrix_policy

    policy = matrix_policy(load_matrix())
    return policy["bars"]


def _risk_class_of(action_type: str) -> Optional[str]:
    """Map an action_type enum to its matrix risk_class (or None if unmapped).

    Read from the same authority-matrix.yml risk_classes map the gate uses, so
    the bar override selection agrees with the verdict lookup.
    """
    from framework.authority.matrix import load_matrix, matrix_policy

    policy = matrix_policy(load_matrix())
    for rc, spec in policy["risk_classes"].items():
        if action_type in (spec.get("action_types") or []):
            return rc
    return None


def _bar_for_action_type(action_type: str) -> dict[str, Any]:
    """Select the bar for a cell's action_type: the risk_class override if the
    YAML defines one, else `default`. The bar is the reconciled one from the
    matrix YAML — graduation carries no second copy.
    """
    bars = _load_bars()
    risk_class = _risk_class_of(action_type)
    if risk_class is not None and risk_class in bars:
        return bars[risk_class]
    return bars["default"]


# --------------------------------------------------------------------------
# Per-cell raw-row scan (ordering + recency the aggregated ratios drop)
# --------------------------------------------------------------------------

def _parse_ts(ts: str) -> Optional[datetime]:
    """Parse an ISO ts to an aware datetime, or None if unparseable."""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _cell_rows(
    cell: tuple[str, Optional[str], str],
    ledger: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The ledger rows belonging to this cell, oldest->newest by ts.

    `cell` keys on (actor_id, lane, action_type) exactly as compute_ratios does
    (actor flattened to 'kind:id', action_type the stamped enum). Rows are
    already deduped (last-write-wins) by read_ledger.
    """
    actor_id, lane, action_type = cell
    rows = []
    for ev in ledger:
        actor = ev.get("actor") or {}
        ev_actor_id = f"{actor.get('kind')}:{actor.get('id')}"
        if ev_actor_id != actor_id:
            continue
        if ev.get("lane") != lane:
            continue
        if ev.get("action_type") != action_type:
            continue
        rows.append(ev)
    rows.sort(key=lambda e: e.get("ts", ""))
    return rows


def _verdict(ev: dict[str, Any]) -> Optional[str]:
    return (ev.get("review") or {}).get("verdict")


def _divergent_in_last10(rows: list[dict[str, Any]]) -> int:
    """Count `wrong` review verdicts among the most recent _LAST_N rows that
    carried a confirmed/wrong verdict (unknown verdicts are not scored cases)."""
    scored = [e for e in rows if _verdict(e) in ("confirmed", "wrong")]
    last = scored[-_LAST_N:]
    return sum(1 for e in last if _verdict(e) == "wrong")


def _fresh_direct_demote(rows: list[dict[str, Any]]) -> bool:
    """[B2.9] True iff any of the most recent _LAST_N SCORED rows carries the
    B2.8 fabrication directive (`DIRECT_DEMOTE_REF` in refs). A single proven
    fabrication demotes directly — it does NOT wait for the ≥2 divergent cluster.
    Scoped to the same last-10-scored window as the cluster check so a fabrication
    aged out by 10 newer clean samples no longer bites (symmetric ramp-down)."""
    scored = [e for e in rows if _verdict(e) in ("confirmed", "wrong")]
    last = scored[-_LAST_N:]
    return any(DIRECT_DEMOTE_REF in (e.get("refs") or []) for e in last)


def _days_since_last_wrong(
    rows: list[dict[str, Any]], now: datetime
) -> Optional[float]:
    """Days since the most recent `wrong` verdict, or None if never wrong.

    None means the clean streak is unbroken by any wrong call — under the
    wrong-only recency clock (defect-3 fix) a never-wrong cell passes the
    streak check immediately and is bounded only by the cell-age seasoning
    floor (`_cell_age_days` >= `_SEASONING_DAYS`)."""
    wrongs = [e for e in rows if _verdict(e) == "wrong"]
    if not wrongs:
        return None
    last_wrong_ts = _parse_ts(wrongs[-1].get("ts", ""))
    if last_wrong_ts is None:
        return None
    return (now - last_wrong_ts).total_seconds() / 86400.0


def _days_since_last_sample(
    rows: list[dict[str, Any]], now: datetime
) -> Optional[float]:
    """Days since the most recent scored row, or None if none scored.

    Evidence/observability only since the defect-3 fix — the recency gate no
    longer reads it (a young CLEAN sample must not reset the streak)."""
    scored = [e for e in rows if _verdict(e) in ("confirmed", "wrong")]
    if not scored:
        return None
    last_ts = _parse_ts(scored[-1].get("ts", ""))
    if last_ts is None:
        return None
    return (now - last_ts).total_seconds() / 86400.0


def _cell_age_days(
    rows: list[dict[str, Any]], now: datetime
) -> Optional[float]:
    """Days since the FIRST scored row (cell age), or None if none scored.

    The seasoning floor keys on cell AGE precisely because age only grows —
    unlike days-since-last-sample (the defect-3 clock) it cannot be reset by
    fresh clean activity, so it brakes burst-graduation without punishing a
    continuously-used cell."""
    scored = [e for e in rows if _verdict(e) in ("confirmed", "wrong")]
    if not scored:
        return None
    first_ts = _parse_ts(scored[0].get("ts", ""))
    if first_ts is None:
        return None
    return (now - first_ts).total_seconds() / 86400.0


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------

def _fitness(ratios: GraduationRatios) -> Optional[float]:
    """outcome_held_rate x review_confirmed_rate (positive signal).

    None if either factor is unmeasured (denominator 0) — a cell with no
    outcome OR no review signal has no fitness and cannot graduate."""
    held = ratios.outcome_held_rate
    confirmed = ratios.review_confirmed_rate
    if held is None or confirmed is None:
        return None
    return held * confirmed


def evaluate(
    cell: tuple[str, Optional[str], str],
    *,
    since: Optional[str] = None,
    ledger: Optional[list[dict[str, Any]]] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Compute the per-cell autonomy state + the evidence behind it.

    cell = (officer_actor_id, lane, action_type). Returns
    {"state": <state>, "evidence": {...}}.

    Reads the consequence ledger (deduped) for this cell, applies the bar READ
    from authority-matrix.yml, and returns the fail-safe state. Optional
    `ledger`/`since`/`now` are test seams; production callers pass nothing and
    read the live ledger at call time.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    rows = ledger if ledger is not None else read_ledger(since=since)
    ratios_by_cell = compute_ratios(since=since, ledger=rows)
    ratios = ratios_by_cell.get(cell, GraduationRatios())
    cell_rows = _cell_rows(cell, rows)

    action_type = cell[2]
    bar = _bar_for_action_type(action_type)

    match_rate = ratios.review_confirmed_rate  # the decision-match channel
    fitness = _fitness(ratios)
    divergent_last10 = _divergent_in_last10(cell_rows)
    fabrication_demote = _fresh_direct_demote(cell_rows)
    days_since_wrong = _days_since_last_wrong(cell_rows, now)
    days_since_sample = _days_since_last_sample(cell_rows, now)
    cell_age = _cell_age_days(cell_rows, now)

    evidence: dict[str, Any] = {
        "sample_count": ratios.sample_count,
        "match_rate": match_rate,
        "fitness": fitness,
        "approval_unchanged_rate": ratios.approval_unchanged_rate,
        "outcome_held_rate": ratios.outcome_held_rate,
        "review_confirmed_rate": ratios.review_confirmed_rate,
        "divergent_last10": divergent_last10,
        "fabrication_demote": fabrication_demote,
        "days_since_last_wrong": days_since_wrong,
        "days_since_last_sample": days_since_sample,
        "cell_age_days": cell_age,
        "seasoning_days": _SEASONING_DAYS,
        "bar": dict(bar),
        "cell": list(cell),
    }

    # 1. FAIL-SAFE: no measurable decision signal -> unmeasured (never auto).
    #    A None match_rate means the confirmed/wrong denominator is 0.
    if match_rate is None or ratios.sample_count == 0:
        return {"state": "unmeasured", "evidence": evidence}

    # 2. DEMOTE: either a fresh divergent CLUSTER in the last 10 (tighter than
    #    the promotion ceiling) OR a single B2.8-verified fabrication drops the
    #    cell sub-bar regardless of history. A fabrication is a proven lie about
    #    success (the verifier's RT#4 gate already excluded upstream-outage) — it
    #    does not wait for a second divergence.
    if fabrication_demote or divergent_last10 >= _DEMOTE_DIVERGENT_IN_LAST10:
        return {"state": "demote", "evidence": evidence}

    # 3. Below the sample or match floor -> propose_only (the fail-safe).
    if ratios.sample_count < bar["samples"]:
        return {"state": "propose_only", "evidence": evidence}
    if match_rate < bar["match_rate"]:
        return {"state": "propose_only", "evidence": evidence}

    # Fitness must be a positive signal to graduate (outcome held AND review
    # confirmed) — never a low/zero blend.
    if fitness is None or fitness <= 0:
        return {"state": "propose_only", "evidence": evidence}

    # 4. Last-10 divergent must be within the promotion ceiling.
    if divergent_last10 > bar["max_divergent_last10"]:
        return {"state": "propose_only", "evidence": evidence}

    # 5. Recency-clean gate — a WRONG-ONLY clock [defect-3 fix, checkpoint
    #    2026-07-04 §7 rec-8]. Only a wrong verdict resets the streak; clean
    #    samples ACCUMULATE. (The previous rule also reset on days-since-last-
    #    SAMPLE, so a continuously-used, never-wrong cell could never reach
    #    `graduated` and a graduated cell flapped back to `eligible` on its
    #    next clean label — time-to-auto was infinite for exactly the cells
    #    earning trust. Wrong-only matches the ratified design language:
    #    proactive-org-strategy 2026-07-03 rec-2 "days-since-last-WRONG-only …
    #    never-wrong passes immediately" + both design docs' clean-STREAK
    #    wording.) A cell re-earning the streak after a wrong is `eligible`
    #    (proven-but-not-yet-auto), not `graduated`.
    need_clean = bar["recency_clean_days"]
    if days_since_wrong is not None and days_since_wrong < need_clean:
        # a recent wrong call: not yet clean — eligible, re-earning the streak.
        return {"state": "eligible", "evidence": evidence}

    # 5b. ~7d cell-age seasoning floor (same ratified rec, anti-burst leg):
    #     never-wrong is clean by definition, but the cell must still have
    #     EXISTED long enough that its clean record spans real calendar time —
    #     20 clean samples minted in one afternoon stay `eligible` until the
    #     cell is ~a week old. Age is measured from the FIRST scored sample
    #     and only grows, so this floor can never flap a graduated cell back.
    if cell_age is None or cell_age < _SEASONING_DAYS:
        return {"state": "eligible", "evidence": evidence}

    # 6. Clears the FULL bar.
    return {"state": "graduated", "evidence": evidence}
