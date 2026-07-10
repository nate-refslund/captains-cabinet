"""W9 / ledger A10 — predictions scored, finally (report-only Brier series).

Every action card the lane emits carries the model's OWN probability that the
act is right (``confidence`` in the ``cabinet:action:<pid>`` record,
action_lane.Proposal) — and until 2026-07-09 nothing ever scored it: the org
predicted daily and never learned whether its 0.9s were 0.9s. This module
joins those emitted predictions against the ground truth the estate already
produces —

  * the UNDO-3 TTL-survival sweep (action_reconcile: ``outcome=ok`` past TTL,
    ``outcome=failed`` + ``review=wrong`` on a silent revert),
  * Captain undo / veto verdicts through the binder (``review.verdict``),

— via the correlation cid each acted consequence row carries in ``refs``, and
emits a Brier + calibration-bin series line to
``shared/interfaces/prediction-calibration.jsonl`` (sibling of the
falsifier series; same idempotent-per-date append discipline).

PURE MEASUREMENT ("calibration as continuing control", ledger A10,
alpha-additive): nothing here reads the series back into any gate — the
scalar is evidence for the D5/CG-10 chain and the prerequisite for EIG
ordering. Widens no authority.

Ground-truth mapping (conservative, fail-closed):
  * ``outcome.status == "failed"`` or ``review.verdict == "wrong"`` → y=0
    (the act did not stick / was judged wrong);
  * ``outcome.status == "ok"`` with review not wrong → y=1;
  * anything else (``unknown`` / missing) → NOT ground-truthed yet — the
    prediction is counted but never scored on a guess.
A card whose steps produced several acted rows scores as ONE prediction:
any failed row makes y=0 (one bad step falsifies the card's confidence).

Fully injectable (records / ledger / now / out path) — tests run offline.
Production reads the live Redis action records (``redis-cli --scan``) and
``consequence.read_ledger()``.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from framework.fidelity.consequence import read_ledger
from framework.probes import correlation

SERIES_PATH = Path(__file__).resolve().parents[2] / \
    "shared/interfaces/prediction-calibration.jsonl"
_N_BINS = 10


# --------------------------------------------------------------------------
# gather: predictions (Redis action records) + ground truth (ledger)
# --------------------------------------------------------------------------

def _redis_cli(*args: str) -> str:
    try:
        r = subprocess.run(["redis-cli", *args], capture_output=True,
                           text=True, timeout=30)
        return r.stdout if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001 — a report must never crash on transport
        return ""


def load_action_records() -> List[dict]:
    """The live ``cabinet:action:*`` records (7-day TTL window). Best-effort:
    unreadable keys / non-JSON values are skipped, never raised."""
    out: List[dict] = []
    for key in _redis_cli("--scan", "--pattern", "cabinet:action:*").splitlines():
        key = key.strip()
        if not key:
            continue
        raw = _redis_cli("GET", key)
        try:
            rec = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def ground_truth_by_cid(ledger: Iterable[dict]) -> Dict[str, int]:
    """cid → y (1 the act stuck / 0 it failed or was judged wrong). Rows that
    are still ``outcome=unknown`` (or carry no outcome) contribute NOTHING —
    a prediction is never scored against a guess. Any failed/wrong row for a
    cid wins over ok rows (one bad step falsifies the card)."""
    truth: Dict[str, int] = {}
    for ev in ledger:
        if not isinstance(ev, dict):
            continue
        cid = correlation.cid_from_refs(ev.get("refs"))
        if not cid:
            continue
        status = ((ev.get("outcome") or {}).get("status") or "").strip()
        verdict = ((ev.get("review") or {}).get("verdict") or "").strip()
        if verdict == "wrong" or status == "failed":
            truth[cid] = 0
        elif status == "ok" and truth.get(cid) != 0:
            truth[cid] = 1
    return truth


def _clamp01(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, f))


def score_predictions(records: Iterable[dict],
                      truth: Dict[str, int]) -> Dict[str, Any]:
    """Join + score. Returns the pure metrics dict (no I/O)."""
    pairs: List[tuple] = []       # (confidence, y, lane)
    n_predictions = 0
    for rec in records:
        if not isinstance(rec, dict):
            continue
        conf = _clamp01(rec.get("confidence"))
        cid = str(rec.get("cid") or "").strip()
        if conf is None or not cid:
            continue
        n_predictions += 1
        if cid in truth:
            pairs.append((conf, truth[cid], str(rec.get("lane") or "")))

    brier = (sum((c - y) ** 2 for c, y, _ in pairs) / len(pairs)
             if pairs else None)   # None = unmeasured, never a silent 0.0

    bins: List[dict] = []
    for i in range(_N_BINS):
        lo, hi = i / _N_BINS, (i + 1) / _N_BINS
        inb = [(c, y) for c, y, _ in pairs
               if (lo <= c < hi) or (i == _N_BINS - 1 and c == 1.0)]
        if not inb:
            continue
        bins.append({
            "lo": round(lo, 1), "hi": round(hi, 1), "n": len(inb),
            "mean_confidence": round(sum(c for c, _ in inb) / len(inb), 4),
            "empirical_rate": round(sum(y for _, y in inb) / len(inb), 4),
        })

    by_lane: Dict[str, dict] = {}
    for lane in sorted({l for _, _, l in pairs if l}):
        lp = [(c, y) for c, y, l in pairs if l == lane]
        by_lane[lane] = {
            "n": len(lp),
            "brier": round(sum((c - y) ** 2 for c, y in lp) / len(lp), 4),
        }

    return {
        "n_predictions": n_predictions,
        "n_ground_truthed": len(pairs),
        "brier": round(brier, 4) if brier is not None else None,
        "calibration": bins,
        "by_lane": by_lane,
    }


# --------------------------------------------------------------------------
# emit: idempotent-per-date JSONL series (falsifier-series discipline)
# --------------------------------------------------------------------------

def _already_reported(path: Path, date: str) -> bool:
    try:
        with open(path) as f:
            for line in f:
                try:
                    if json.loads(line).get("date") == date:
                        return True
                except json.JSONDecodeError:
                    continue
    except OSError:
        return False
    return False


def emit_daily_line(*, records: Optional[List[dict]] = None,
                    ledger: Optional[List[dict]] = None,
                    now: Optional[dt.datetime] = None,
                    out_path: Optional[Path] = None) -> Optional[dict]:
    """Compute + append today's line; None when today is already reported
    (idempotent — a re-fired job never doubles a day). Report-only writer:
    the ONLY side effect is the append to the series file."""
    now = now or dt.datetime.now(dt.timezone.utc)
    path = out_path or SERIES_PATH
    date = now.strftime("%Y-%m-%d")
    if _already_reported(path, date):
        return None
    if records is None:
        records = load_action_records()
    if ledger is None:
        ledger = read_ledger()
    line = {"date": date, "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            **score_predictions(records, ground_truth_by_cid(ledger))}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return line


if __name__ == "__main__":
    res = emit_daily_line()
    if res is None:
        print("prediction-scorer: today already reported — nothing to do")
    else:
        print("prediction-scorer: " + json.dumps(res, sort_keys=True))
