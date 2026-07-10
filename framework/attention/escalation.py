"""framework.attention.escalation — the tiered-escalation gate on the Captain
surface (captain-surface master prompt §3.9, 2026-07-10).

THE LAW: a problem is fixed at the LOWEST tier that can fix it. A lane CEO
self-fixes first; only a truly-stuck lane escalates to the Chair; only a
truly-Chair-unfixable item that genuinely needs Captain authority reaches the
Captain — and it arrives WITH PROOF the lower tiers were exhausted:
"the lane tried X, the Chair tried Y, this needs you because Z" (a credential,
approval, or decision only the Captain holds). This is the single biggest
Captain-volume reducer, built as an explicit GATE where captain-bound cards
enter the attention gateway (``gate.decide``), not a norm.

MECHANISM: a NEW open decision card must carry an exhaustion proof —

    item["escalation"] = {
        "lane_tried":            "what the lane did to fix it itself",
        "chair_tried":           "what the Chair did before rising",
        "needs_captain_because": "the authority only the captain holds",
    }

(all three non-empty). Without it the card does NOT reach the Captain: the
gate returns ``action="bounce"`` and the producing officer gets the reason
back through its own tool result — the item goes back to the org, with why.

EXEMPT (never bounced):
  * floor classes — a safety page is never blocked by paperwork;
  * standing-card EDITS — updates/closures of an already-admitted situation
    (the gate's identity path returns before this check);
  * non-open states — a closure/acted report is telling, not asking;
  * non-decision kinds — FYIs/digests ride their own routes.

DARK BY DEFAULT: armed only when ``CABINET_ESCALATION_GATE=1`` (today's
producers attach no proof yet — arming before they do would bounce
everything; same deploy discipline as the admission law). Bounces are
journaled (``bounces.jsonl`` in the attention dir) and best-effort emitted to
the org event ledger (``captain_gate_bounced``) so the pattern is auditable.

This module never imports ``gate`` (gate calls it — one-way).
"""
from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# The three fields of an exhaustion proof — "the lane tried X, the Chair tried
# Y, this specifically needs you because Z" (master prompt §3.9, verbatim law).
REQUIRED_FIELDS = ("lane_tried", "chair_tried", "needs_captain_because")

# Captain-bound DECISION kinds subject to the gate. Data, not a branch —
# extendable via CABINET_ESCALATION_KINDS (csv) without touching code.
_DEFAULT_DECISION_KINDS = frozenset({"action-card"})

_BOUNCE_JOURNAL = "bounces.jsonl"

_FIX_GUIDANCE = (
    "Resolve this at your own tier first (lane, then Chair). If it truly "
    "needs the captain, attach escalation={lane_tried, chair_tried, "
    "needs_captain_because} — what each tier already tried, and the "
    "credential/approval/decision only the captain holds.")


def armed(env: "dict | None" = None) -> bool:
    e = env if env is not None else os.environ
    return str(e.get("CABINET_ESCALATION_GATE", "")).strip() == "1"


def decision_kinds(env: "dict | None" = None) -> frozenset:
    e = env if env is not None else os.environ
    raw = str(e.get("CABINET_ESCALATION_KINDS", "")).strip()
    if not raw:
        return _DEFAULT_DECISION_KINDS
    kinds = {k.strip() for k in raw.split(",") if k.strip()}
    return frozenset(kinds) if kinds else _DEFAULT_DECISION_KINDS


def exhaustion_proof(item: dict) -> "dict | None":
    """The item's proof dict when structurally valid (all three fields
    non-empty strings), else None."""
    proof = (item or {}).get("escalation")
    if not isinstance(proof, dict):
        return None
    for f in REQUIRED_FIELDS:
        if not str(proof.get(f) or "").strip():
            return None
    return proof


def missing_fields(item: dict) -> list:
    proof = (item or {}).get("escalation")
    if not isinstance(proof, dict):
        return list(REQUIRED_FIELDS)
    return [f for f in REQUIRED_FIELDS if not str(proof.get(f) or "").strip()]


def check(item: dict, *, resolved: "dict | None" = None,
          armed_override: "bool | None" = None) -> dict:
    """The admission decision for one item entering the gateway. Returns
    ``{"admitted": bool, "reason": str, "missing": [...], "fix": str}``.
    Pure given (item, resolved, armed_override); reads only the arming env
    when ``armed_override`` is None. Never raises."""
    item = item if isinstance(item, dict) else {}
    is_armed = armed() if armed_override is None else bool(armed_override)
    if not is_armed:
        return {"admitted": True, "reason": "gate-dark", "missing": [], "fix": ""}
    if (resolved or {}).get("floor"):
        return {"admitted": True, "reason": "floor-exempt", "missing": [], "fix": ""}
    if item.get("kind") not in decision_kinds():
        return {"admitted": True, "reason": "not-a-decision-card",
                "missing": [], "fix": ""}
    if str(item.get("state", "open")) != "open":
        return {"admitted": True, "reason": "not-a-new-decision",
                "missing": [], "fix": ""}
    missing = missing_fields(item)
    if missing:
        return {"admitted": False, "reason": "escalation-unexhausted",
                "missing": missing, "fix": _FIX_GUIDANCE}
    return {"admitted": True, "reason": "exhaustion-proof-present",
            "missing": [], "fix": ""}


# ---------------------------------------------------------------------------
# Bounce journal — the auditable trail of what the gate sent back to the org
# ---------------------------------------------------------------------------

def _attention_dir() -> Path:
    # Same resolution as gate._attention_dir, re-stated here so the dependency
    # stays one-way (gate → escalation, never back).
    return Path(os.environ.get("CABINET_ATTENTION_DIR") or
                os.path.expanduser("~/Library/Application Support/cabinet/attention"))


def bounce_journal_path() -> Path:
    return _attention_dir() / _BOUNCE_JOURNAL


def journal_bounce(item: dict, decision: dict,
                   now: "datetime | None" = None) -> None:
    """Append one bounce row (flock-serialized) + best-effort org event. Never
    raises — a journaling failure must not turn a bounce into a crash."""
    item = item if isinstance(item, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    bounce = decision.get("bounce") or {}
    row = {
        "ts": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "subject": str(item.get("subject") or "")[:200],
        "kind": item.get("kind"),
        "lane": item.get("lane"),
        "reason": decision.get("reason"),
        "missing": bounce.get("missing") or [],
        "situation_key": decision.get("situation_key"),
    }
    try:
        d = _attention_dir()
        d.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(bounce_journal_path()),
                     os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    except Exception:
        pass
    try:
        # Durable org record (org-runtime-native rule) — best-effort.
        from framework.events.emitter import emit
        emit("captain_gate_bounced",
             actor=str(item.get("lane") or "attention-gate"),
             payload={"subject": row["subject"], "kind": row["kind"],
                      "reason": row["reason"], "missing": row["missing"]})
    except Exception:
        pass


def bounce_rows(limit: int = 500) -> list:
    """Recent bounce rows (for retros / tests)."""
    p = bounce_journal_path()
    if not p.exists():
        return []
    rows = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for ln in lines[-int(limit):]:
        try:
            row = json.loads(ln)
        except (ValueError, TypeError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows
