"""Grant seeker [sovereign spec §4 SOV-8, §8 step 10] — rank + render the
case for standing grants and flavor-A sovereign lane flips.

This module GRANTS NOTHING (D7 killed every runtime grant-writer). It reads
the needs ledger + the consequence ledger, ranks where a Captain signature
would remove the most human-wait, renders each case in plain language with
the machine-effective scope, and — for `--argue-lanes` — files ONE deduped
`kind=decision` need per qualifying lane so the argument rides the next
needs digest. Grants still change only via `sudo grant-apply.sh` in an
unlock window; lane flips only via a Captain edit of posture.yml.

The lane-flip bar is evidence, not enthusiasm (EARN-DEMOTION doctrine —
posture unlocks unproven states, evidence must still be clean): a lane
qualifies only with ≥ `min_acted` acted rows, ZERO wrong verdicts in the
window, and an undo/veto-free record. All Captain-facing strings are
U+00B7-stripped (binder-injection defense, same as needs.py).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

EVIDENCE_WINDOW_DAYS = 28
MIN_ACTED_FOR_FLIP = 5

# cost_of_delay → rank weight (higher = argue sooner).
_DELAY_WEIGHT = {"blocking": 100, "high": 30, "medium": 10, "low": 3}

# Guess ratified in §9 Q5: the first flavor-A lanes worth arguing are the
# pm/calendar + internal_comms surfaces — used only as a tie-break nudge.
_PREFERRED_CLASSES = ("pm_write", "calendar_write", "internal_comms")


def _no_marker(s: str) -> str:
    return (s or "").replace("·", "")


def _now(now: str | None = None) -> str:
    if now:
        return now
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# rank — open grant-shaped needs, strongest case first
# ---------------------------------------------------------------------------

def rank(
    needs_rows: list[dict[str, Any]] | None = None,
    *,
    root: str | Path | None = None,
    now: str | None = None,
) -> list[dict[str, Any]]:
    """Rank open `standing_grant` (and grant-adjacent `credential`) needs by
    (cost-of-delay weight × re-file count), preferred classes nudged up.
    Read-only; never raises; [] on any failure."""
    try:
        if needs_rows is None:
            from framework.authority import needs
            needs_rows = needs.list_open(now, root=root)
        ranked: list[dict[str, Any]] = []
        for row in needs_rows or []:
            if row.get("kind") not in ("standing_grant", "credential"):
                continue
            if row.get("status") != "open":
                continue
            weight = _DELAY_WEIGHT.get(str(row.get("cost_of_delay")), 10)
            count = int(row.get("count") or 1)
            score = weight * count
            if row.get("risk_class") in _PREFERRED_CLASSES:
                score += 1
            ranked.append({
                "kind": "grant",
                "need_id": row.get("id"),
                "risk_class": row.get("risk_class"),
                "action_type": row.get("action_type"),
                "lane": row.get("lane"),
                "score": score,
                "count": count,
                "why": _no_marker(str(row.get("why") or "")),
                "proposed_grant_line": row.get("proposed_grant_line"),
            })
        ranked.sort(key=lambda r: (-r["score"], str(r["need_id"])))
        return ranked
    except Exception:
        return []


def render(ranked: list[dict[str, Any]]) -> list[str]:
    """Digest-ready plain-language lines. Each grant line names the
    MACHINE-EFFECTIVE scope (the exact appendable row) so the Captain signs
    what the machine will enforce, never a paraphrase."""
    lines: list[str] = []
    for r in ranked:
        if r.get("kind") == "lane_flip":
            lines.append(_no_marker(
                f"lane flip case — {r['lane']}: {r['why']} "
                f"(edit posture.yml lanes: {{{r['lane']}: sovereign}} in an "
                "unlock window)"))
            continue
        scope = r.get("proposed_grant_line") or "(no grant line composed yet)"
        lines.append(_no_marker(
            f"{r['need_id']} — {r.get('risk_class')}/{r.get('action_type')} "
            f"lane {r.get('lane')}: filed {r.get('count')}×; {r.get('why')} "
            f"| machine-effective scope: {scope}"))
    return lines


# ---------------------------------------------------------------------------
# argue_lanes — the flavor-A sovereign-flip case (evidence-gated)
# ---------------------------------------------------------------------------

def _lane_evidence(
    ledger: list[dict[str, Any]],
    *,
    since: str,
) -> dict[str, dict[str, int]]:
    """Per-lane acted/confirmed/wrong counts from the consequence ledger
    (acted rows = proposal.required is False + stamped action_type)."""
    lanes: dict[str, dict[str, int]] = {}
    for ev in ledger:
        if not isinstance(ev, dict):
            continue
        lane = ev.get("lane")
        if not isinstance(lane, str) or not lane:
            continue
        if str(ev.get("ts") or "") < since:
            continue
        stats = lanes.setdefault(lane, {"acted": 0, "confirmed": 0, "wrong": 0})
        review = ev.get("review") or {}
        if review.get("verdict") == "wrong":
            stats["wrong"] += 1
        prop = ev.get("proposal")
        at = ev.get("action_type")
        if (isinstance(prop, dict) and prop.get("required") is False
                and isinstance(at, str) and at and not at.startswith("__")):
            stats["acted"] += 1
            if review.get("verdict") == "confirmed":
                stats["confirmed"] += 1
    return lanes


def argue_lanes(
    *,
    ledger: list[dict[str, Any]] | None = None,
    root: str | Path | None = None,
    now: str | None = None,
    window_days: int = EVIDENCE_WINDOW_DAYS,
    min_acted: int = MIN_ACTED_FOR_FLIP,
    file_needs: bool = True,
) -> dict[str, Any]:
    """Build the flavor-A sovereign-flip case per lane; file ONE deduped
    `kind=decision` need per qualifying lane (gated by `needs_enabled` — in a
    pure-guardian unwired world this is automatically a no-op).

    A lane qualifies with ≥ min_acted acted rows and ZERO wrong verdicts in
    the window. Returns {qualifying: [...], considered: {...}} — the digest
    renders the filed needs; nothing here changes posture or grants."""
    ts = _now(now)
    try:
        if ledger is None:
            from framework.fidelity.consequence import read_ledger
            ledger = read_ledger()
    except Exception:
        ledger = []
    try:
        nowdt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        since = (nowdt - timedelta(days=window_days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        since = ""
    lanes = _lane_evidence(ledger or [], since=since)
    qualifying: list[dict[str, Any]] = []
    for lane, stats in sorted(lanes.items()):
        if stats["acted"] < min_acted or stats["wrong"] > 0:
            continue
        why = (
            f"lane {lane} earned a sovereign flip: {stats['acted']} acted "
            f"row(s), {stats['confirmed']} confirmed, 0 wrong in the last "
            f"{window_days}d — flip via posture.yml lanes: "
            f"{{{lane}: sovereign}} in an unlock window"
        )
        case: dict[str, Any] = {
            "kind": "lane_flip", "lane": lane, "why": _no_marker(why),
            "score": stats["acted"] + stats["confirmed"], **stats,
        }
        if file_needs:
            try:
                from framework.authority import needs
                case["need_id"] = needs.file_need(
                    "decision",
                    action_type="lane_posture",
                    lane=lane,
                    why=_no_marker(why),
                    unblocks=f"sovereign routing for lane {lane}",
                    filed_by="grant_seeker",
                    root=root,
                )
            except Exception:
                case["need_id"] = None
        qualifying.append(case)
    qualifying.sort(key=lambda c: (-c["score"], c["lane"]))
    return {"qualifying": qualifying, "considered": lanes,
            "window_days": window_days, "min_acted": min_acted}


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Grant seeker — rank/render grant + lane-flip cases "
                    "(files needs; grants NOTHING).")
    parser.add_argument("--argue-lanes", action="store_true",
                        help="Build + file the flavor-A sovereign lane-flip case")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.argue_lanes:
        out: dict[str, Any] = argue_lanes()
        lines = render(out["qualifying"])
    else:
        ranked = rank()
        out = {"ranked": ranked}
        lines = render(ranked)
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        for line in lines:
            print(line)
        if not lines:
            print("grant-seeker: nothing to argue")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
