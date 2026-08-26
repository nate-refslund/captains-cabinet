"""Flywheel step 3 — LLM-judge calibration against human labels + the
demotion precondition flag.

WHY (fresh review 2026-07-04 §6.3, "judge calibration before judges gate
autonomy" — LangChain Align-Evals pattern): flavor-A already makes
`verdict_human` the only promotion fuel (consequence.py::compute_ratios:697-708)
and lets a `verdict_judge` 'wrong' hold/demote. The missing piece is proof
that the judge AGREES with the Captain before its verdicts get ANY gating
power. This module measures verdict_judge ↔ verdict_human agreement over the
human-labeled fidelity cases (June 2026 onward — the first human-labeled
window; --since narrows/widens it) and exposes ONE fail-closed boolean:

    judge_verdicts_may_demote() -> bool

THE HARD BAR (task contract, 2026-07-05): agreement >= 80% (JUDGE_HARD_BAR)
over at least MIN_PAIRS pairs, proven by a status file younger than
STATUS_MAX_AGE_DAYS. These are CODE CONSTANTS, deliberately not CLI flags —
a bar someone can lower from argv is not a bar (no-widening rule; hard
ceilings stay human-gated, and loosening THIS gate widens machine power).

INTERFACE FOR THE SUPPLY LANE (composes with framework/probes/verifier.py —
NOT edited here; the supply lane owns it):
  * The verifier calls `judge_verdicts_may_demote()` BEFORE emitting a
    demotion-capable verdict_judge row (a 'wrong' verdict, and especially the
    DIRECT_DEMOTE_REF fabrication directive). Flag closed -> it downgrades to
    review.verdict='unknown' + a `calibration:uncalibrated` ref (observable,
    never scored) or simply withholds the demote ref — the calibration data
    keeps flowing either way because CONFIRMED judge rows are always safe to
    emit (they can never promote — flavor-A — and never demote).
  * Any other consumer that wants to let verdict_judge rows count toward
    demotion checks the same function. The flag is process-independent: it is
    a JSON status file, not module state.

PAIRING MODEL (dated decision 2026-07-05): a calibration pair is ONE subject
that carries BOTH a judge verdict and a human verdict in {confirmed, wrong}.
  * The reader is RAW (file order, NOT read_ledger's last-write-wins dedup):
    a judge verdict later SUPERSEDED by a human verdict on the same identity
    tuple is precisely a calibration datapoint — dedup would erase the judge's
    side of it. Sim rows are always dropped (SIE-7: simulated consequences
    never calibrate the judge that gates live autonomy).
  * Latest verdict per side wins (the human's final word vs the judge's final
    opinion); 'unknown' verdicts score neither side, mirroring how
    review_confirmed_rate excludes unknowns (consequence.py:622-624).
  * The window filters on the HUMAN row's ts (the human labels define the
    calibration set — "against the June human-labeled fidelity cases"); the
    judge row may land any time.
  * The frozen regression corpus is deliberately NOT a second label source:
    it is derived from this same ledger's human rows (corrections only, no
    confirms), so pairing against it would double-count and skew toward
    'wrong'. One source of truth: the ledger.

FAIL-SAFE (Corridor invariant): every failure mode — no status file, corrupt
JSON, stale proof, insufficient pairs, rate below bar, unparseable timestamp —
reads as flag CLOSED. An uncalibrated judge has no gating power; there is no
error path that grants it.

STATUS FILE: $CABINET_EVENT_LOG_DIR/judge-calibration-status.json — the same
env resolution as the consequence ledger (ONE path rule; the repo-root pytest
fence and fenced runs therefore cover it automatically). Distinct basename:
the ledger readers glob only their own filename families
(consequence-events-*.jsonl / events-*.jsonl), so no collision. Written
atomically (tmp + os.replace).

System Python is 3.9.6 — stdlib only, `from __future__ import annotations`.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Private-helper reuse from the ledger module is deliberate (in-repo, same
# package): _consequence_log_dir is the ONE env resolution rule and
# _safe_ledger_files is the ONE symlink fence — duplicating either here would
# create a second rule that can drift (the exact defect FIX-1 exists to
# prevent elsewhere).
from framework.fidelity.consequence import (
    _consequence_log_dir,
    _is_consequence_row,
    _safe_ledger_files,
)

# ---------------------------------------------------------------------------
# constants — the HARD bar (not configurable at runtime; see module docstring)
# ---------------------------------------------------------------------------

JUDGE_HARD_BAR = 0.80        # >= 80% agreement required (0.80 exactly passes)

# THE WRONG-CLASS FLOOR (2026-08-26). The bar above scores POOLED agreement, so
# a judge that has only ever been shown work that was fine can clear it on
# agreement alone -- ten confirmations and the door opens. The permission it
# wins is the right to call something WRONG, which is the one thing that
# evidence never tested.
#
# The data to catch it was already being written and never read: the 2x2
# confusion block records how many times the judge said "wrong". This floor
# reads it, and asks for a minimum number of wrong calls before the permission
# is granted at all -- and, among those, the same 80% the pooled bar asks for,
# reusing JUDGE_HARD_BAR rather than inventing a second rate.
#
# THE PRICE, stated as intended behaviour rather than left as a surprise: a
# judge shown nothing but clean work can never open this door, however long it
# agrees. That is correct. The door is "may overrule", and a reviewer with no
# observed wrong call has no evidence for it. Breaking the deadlock means
# putting genuinely wrong work in front of it, which is the work that should
# have been done before granting the permission in the first place.
MIN_WRONG_CALLS = 5
MIN_PAIRS = 10               # below this the measurement is not evidence —
                             # 100% agreement on 3 pairs proves nothing; the
                             # flag stays closed until real volume exists.
STATUS_MAX_AGE_DAYS = 14.0   # a calibration proof EXPIRES: judge power decays
                             # unless recalibrated on cadence (fail-safe
                             # direction — stale proof -> flag closed).
STATUS_BASENAME = "judge-calibration-status.json"
STATUS_FORMAT = 1

# Default human-label window start: June 2026 — the first human-labeled
# fidelity cases (review §6.3's calibration anchor). Overridable per run
# (--since), never hardcoded tighter than the data.
DEFAULT_SINCE = "2026-06-01"

_SCOREABLE = ("confirmed", "wrong")


def status_path() -> Path:
    """The status-file path, derived from the SAME env rule as the ledger
    (CABINET_EVENT_LOG_DIR, else the durable per-user default)."""
    return _consequence_log_dir() / STATUS_BASENAME


# ---------------------------------------------------------------------------
# raw ledger read (calibration needs superseded history — see module docstring)
# ---------------------------------------------------------------------------

def iter_raw_rows() -> list[dict[str, Any]]:
    """Every consequence row in write order per file, ts-sorted overall, sim
    rows dropped unconditionally, junk lines skipped (never crash on a bad
    line — a fabricated verdict is worse than a skipped row, and a crash here
    would just leave the previous status to age out)."""
    log_dir = _consequence_log_dir()
    if not log_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for log_file in _safe_ledger_files(log_dir):
        try:
            text = log_file.read_text()
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not _is_consequence_row(ev):
                continue
            if ev.get("sim"):
                continue  # SIE-7: sim rows never calibrate the live judge
            rows.append(ev)
    # Stable sort by ts: equal-ts rows keep file/line order, so "latest verdict
    # per side" below respects both chronology and supersede write order.
    rows.sort(key=lambda e: e.get("ts", ""))
    return rows


# ---------------------------------------------------------------------------
# pairing + agreement
# ---------------------------------------------------------------------------

def collect_pairs(
    rows: Optional[list[dict[str, Any]]] = None,
    since: Optional[str] = DEFAULT_SINCE,
    until: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Build the calibration pairs: one per subject carrying BOTH a scoreable
    human verdict and a scoreable judge verdict (module docstring has the full
    pairing model + window rule). Returns a deterministic subject-sorted list
    of {subject, human, judge, human_ts, judge_ts, agree}."""
    if rows is None:
        rows = iter_raw_rows()

    humans: dict[str, tuple[str, str]] = {}  # subject -> (ts, verdict)
    judges: dict[str, tuple[str, str]] = {}
    for ev in rows:
        review = ev.get("review") or {}
        verdict = review.get("verdict")
        if verdict not in _SCOREABLE:
            continue  # 'unknown' scores neither side (mirrors ratio math)
        subject = ev.get("subject") or ""
        if not subject:
            continue
        ts = ev.get("ts", "")
        source = review.get("source")
        if source == "verdict_human":
            # Window filter on the HUMAN side only — the human labels define
            # the calibration set (ISO strings compare lexicographically,
            # same convention as read_ledger's `since`).
            if since is not None and ts < since:
                continue
            if until is not None and ts >= until:
                continue
            humans[subject] = (ts, verdict)  # rows are ts-sorted: last wins
        elif source == "verdict_judge":
            judges[subject] = (ts, verdict)
        # source None / "system": unattributed or non-judgment — neither side
        # (fail-closed attribution, same posture as promotion math).

    pairs: list[dict[str, Any]] = []
    for subject in sorted(set(humans) & set(judges)):
        h_ts, h_v = humans[subject]
        j_ts, j_v = judges[subject]
        pairs.append({
            "subject": subject,
            "human": h_v,
            "judge": j_v,
            "human_ts": h_ts,
            "judge_ts": j_ts,
            "agree": h_v == j_v,
        })
    return pairs


def compute_agreement(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Agreement report over the pairs. agreement_rate is None when there are
    zero pairs — an UNMEASURED calibration must read as a visible None, never
    a silent 0.0/1.0 (the no-silent-caps rule graduation follows)."""
    n = len(pairs)
    agreements = sum(1 for p in pairs if p["agree"])
    # 2x2 confusion detail so a failing calibration is diagnosable (is the
    # judge harsh — human confirmed / judge wrong — or blind — the reverse?).
    confusion = {"hc_jc": 0, "hc_jw": 0, "hw_jc": 0, "hw_jw": 0}
    for p in pairs:
        key = ("hc" if p["human"] == "confirmed" else "hw") + "_" + (
            "jc" if p["judge"] == "confirmed" else "jw")
        confusion[key] += 1
    rate = (agreements / n) if n else None
    return {
        "pairs": n,
        "agreements": agreements,
        "disagreements": n - agreements,
        "agreement_rate": rate,
        "confusion": confusion,
        # bar_met is the PRECOMPUTED verdict, but readers re-derive it from the
        # stored numbers too (belt + braces in judge_verdicts_may_demote).
        "bar_met": bool(n >= MIN_PAIRS and rate is not None
                        and rate >= JUDGE_HARD_BAR),
        "hard_bar": JUDGE_HARD_BAR,
        "min_pairs": MIN_PAIRS,
    }


# ---------------------------------------------------------------------------
# status file — the process-independent flag
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, text: str) -> None:
    """tmp-in-same-dir + os.replace — a crash can never leave a torn status
    file that a fail-closed reader would then (correctly) treat as closed
    forever without explanation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-calib-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_status(
    report: dict[str, Any],
    since: Optional[str],
    until: Optional[str],
    path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> Path:
    """Persist the calibration proof (atomic). Written on EVERY successful
    measurement — including a below-bar one, so a freshly failing calibration
    closes the flag immediately rather than riding a stale green proof."""
    if now is None:
        now = datetime.now(timezone.utc)
    target = Path(path) if path is not None else status_path()
    body = dict(report)
    body.update({
        "format": STATUS_FORMAT,
        "computed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "since": since,
        "until": until,
        "max_age_days": STATUS_MAX_AGE_DAYS,
    })
    _atomic_write(target, json.dumps(body, sort_keys=True, indent=2) + "\n")
    return target


def _parse_ts(ts: Any) -> Optional[datetime]:
    """ISO ts -> aware datetime, or None. Mirrors graduation._parse_ts:137-147
    (3.9's fromisoformat cannot read a trailing 'Z')."""
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def calibration_status(
    path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """The full readable precondition record: {"allowed": bool, "reason": str,
    "status": <file body or None>}. `allowed` is fail-closed — see
    judge_verdicts_may_demote for the exact ladder. Never raises."""
    if now is None:
        now = datetime.now(timezone.utc)
    target = Path(path) if path is not None else status_path()
    try:
        body = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return {"allowed": False,
                "reason": f"no readable calibration proof at {target}",
                "status": None}
    if not isinstance(body, dict) or body.get("format") != STATUS_FORMAT:
        return {"allowed": False, "reason": "unknown status format",
                "status": None}

    # Re-derive the bar from the STORED NUMBERS — a hand-edited bar_met:true
    # with failing numbers must not open the flag (belt + braces).
    pairs = body.get("pairs")
    rate = body.get("agreement_rate")
    if not isinstance(pairs, int) or isinstance(pairs, bool):
        return {"allowed": False, "reason": "malformed pairs count",
                "status": body}
    if pairs < MIN_PAIRS:
        return {"allowed": False,
                "reason": f"insufficient pairs ({pairs} < {MIN_PAIRS})",
                "status": body}
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        return {"allowed": False, "reason": "malformed agreement_rate",
                "status": body}
    if float(rate) < JUDGE_HARD_BAR:
        return {"allowed": False,
                "reason": (f"agreement {float(rate):.3f} below hard bar "
                           f"{JUDGE_HARD_BAR}"),
                "status": body}
    if body.get("bar_met") is not True:
        # The writer disagreed with its own numbers — refuse (integrity alarm).
        return {"allowed": False, "reason": "status bar_met flag not true",
                "status": body}

    computed_at = _parse_ts(body.get("computed_at"))
    if computed_at is None:
        return {"allowed": False, "reason": "unparseable computed_at",
                "status": body}
    age_days = (now - computed_at).total_seconds() / 86400.0
    if age_days < 0:
        # A future-dated proof is a clock lie, not freshness — refuse.
        return {"allowed": False, "reason": "computed_at is in the future",
                "status": body}
    if age_days > STATUS_MAX_AGE_DAYS:
        return {"allowed": False,
                "reason": (f"calibration proof stale "
                           f"({age_days:.1f}d > {STATUS_MAX_AGE_DAYS}d)"),
                "status": body}

    # Last rung, and deliberately last: it is only ever evaluated on inputs
    # that would previously have been allowed, so no existing refusal changes
    # its reason string.
    confusion = body.get("confusion")
    if not isinstance(confusion, dict):
        return {"allowed": False,
                "reason": "no confusion detail, so the judge has never been "
                          "observed calling anything wrong",
                "status": body}
    try:
        judge_wrong = int(confusion["hc_jw"]) + int(confusion["hw_jw"])
        agreed_wrong = int(confusion["hw_jw"])
    except (KeyError, TypeError, ValueError):
        # Malformed reads as CLOSED, never as allowed. A permission granted
        # off a block nobody could parse is a permission granted off nothing.
        return {"allowed": False,
                "reason": "malformed confusion detail", "status": body}
    if judge_wrong < MIN_WRONG_CALLS:
        return {"allowed": False,
                "reason": (f"the judge has called something wrong {judge_wrong} "
                           f"time(s), below the {MIN_WRONG_CALLS} needed to "
                           f"judge it on the thing this permission allows"),
                "status": body}
    wrong_precision = agreed_wrong / judge_wrong
    if wrong_precision < JUDGE_HARD_BAR:
        return {"allowed": False,
                "reason": (f"when the judge called something wrong a human "
                           f"agreed {wrong_precision:.3f} of the time, below "
                           f"the hard bar {JUDGE_HARD_BAR}"),
                "status": body}

    return {"allowed": True,
            "reason": (f"agreement {float(rate):.3f} >= {JUDGE_HARD_BAR} over "
                       f"{pairs} pairs, proof {age_days:.1f}d old"),
            "status": body}


def judge_verdicts_may_demote(
    path: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> bool:
    """THE precondition (task contract): True ONLY when a fresh calibration
    proof shows verdict_judge/human agreement >= 80% over >= MIN_PAIRS pairs.

    Until this returns True, NO verdict_judge row may count toward demotion —
    the supply lane's verifier checks it before emitting demotion-capable
    judge verdicts (module docstring §interface). Fail-closed: missing file,
    corrupt JSON, malformed numbers, stale or future-dated proof, below-bar
    rate, insufficient pairs — ALL read False. Never raises."""
    try:
        return calibration_status(path=path, now=now)["allowed"] is True
    except Exception:  # noqa: BLE001 — the catch-all IS the fail-safe
        return False
