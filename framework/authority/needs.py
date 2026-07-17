"""The ONE needs-ledger [FI-3] — a missing grant never asks per-item.

Kills the three-way needs split: every blocked-but-proceeding chain files its
need HERE (`shared/interfaces/needs-ledger.jsonl`), the digest renders it, the
binder grant/deny/snooze verbs mark it, and `grant-apply.sh` closes it in an
unlock window. The ledger is append-only **O_APPEND JSONL with last-write-wins
per id** — one `os.write` per event, no read-modify-write lock, so concurrent
filers can interleave without corruption (the reason veto_registry.next_id was
rejected for the hook path).

Ids are content fingerprints (free dedup + unguessable-enough):
`NEED-` + sha256(f"{kind}|{risk_class}|{action_type}|{lane}|{CABINET_ID}")[:8]
— re-filing the same blocked cell bumps `count`/`last_seen` instead of
spamming rows, and the binder's `[0-9a-f]{8}` grammar [FI-4] matches exactly.

`needs_enabled()` is the filing seam: `resolve_posture()=="sovereign"` OR
`CABINET_NEEDS_WIRED=1` OR the `instance/config/needs-wired` flag file — every
filing short-circuits to a no-op otherwise, so the guardian default world is
bit-identical. `file_need` NEVER raises and stays ~ms (single append): a
broken ledger must never block an acting chain.

DATA is SKIP-class (the ledger is runtime state, not germline); this MODULE is
germline. All Captain-facing strings are stripped of the U+00B7 pid-marker
(same binder-injection defense as `action_lane._no_marker`).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

# FI-3 closed vocabularies.
KINDS = frozenset({
    "access", "credential", "decision", "standing_grant",
    "resource", "hardware", "capability", "unfreeze",
})
STATUSES = frozenset({
    "open", "approved_pending_apply", "granted", "denied",
    "snoozed", "expired", "superseded",
})

OPEN_EXPIRY_DAYS = 30    # inline sweep on read: stale open needs expire
DENY_SUPPRESS_DAYS = 90  # a denied need is a no-op to re-file for 90d
SNOOZE_DAYS = 7          # binder `later|snooze` hides the need for 7d

# status → emitted event (subset — only lifecycle verbs with an FI-3 event).
# approved_pending_apply added 2026-07-17 (evidence R-1 Batch B): the
# Captain's Telegram `grant NEED-x` verb IS the authority decision moment and
# was previously event-silent — only the later root ceremony's `granted`
# emitted. need_approved (decision) and need_granted (applied) are DISTINCT
# verbs on one need_id; consumers must never treat them as duplicates.
_STATUS_EVENTS = {
    "approved_pending_apply": "need_approved",
    "granted": "need_granted",
    "denied": "need_denied",
    "snoozed": "need_snoozed",
    "expired": "need_expired",
}

# Blocking escalation rides the intake stream at ping-now (FI-3).
_BLOCKING = "blocking"


# ---------------------------------------------------------------------------
# Roots, ids, time
# ---------------------------------------------------------------------------

def cabinet_id() -> str:
    return os.environ.get("CABINET_ID", "main")


def _root(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(os.environ.get("CABINET_ROOT") or str(_FRAMEWORK_ROOT))


def ledger_path(root: str | Path | None = None) -> Path:
    """shared/interfaces/needs-ledger.jsonl under the cabinet root."""
    return _root(root) / "shared" / "interfaces" / "needs-ledger.jsonl"


def need_id(
    kind: str,
    risk_class: str | None = None,
    action_type: str | None = None,
    lane: str | None = None,
) -> str:
    """Deterministic content-fingerprint id (FI-3, exact formula)."""
    raw = f"{kind}|{risk_class}|{action_type}|{lane}|{cabinet_id()}"
    return "NEED-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_dt(v: Any) -> datetime | None:
    """Tolerant timestamp parse (ISO str / datetime / date) → aware UTC."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _now(now: Any = None) -> datetime:
    return _to_dt(now) or datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# The filing seam gate
# ---------------------------------------------------------------------------

def needs_enabled(root: str | Path | None = None) -> bool:
    """True iff needs may be filed: sovereign posture OR CABINET_NEEDS_WIRED=1
    OR the instance/config/needs-wired flag file. False short-circuits every
    filing seam ⇒ the guardian default world stays bit-identical."""
    if os.environ.get("CABINET_NEEDS_WIRED") == "1":
        return True
    try:
        if (_root(root) / "instance" / "config" / "needs-wired").exists():
            return True
    except OSError:
        pass
    try:
        # Lazy + file_needs=False: posture's corrupt-config filing calls back
        # into needs_enabled — this read must not re-file (no recursion).
        from framework.authority.posture import resolve_posture
        return resolve_posture(root=root, file_needs=False) == "sovereign"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Ledger IO (O_APPEND, last-write-wins per id)
# ---------------------------------------------------------------------------

def _no_marker(s: str) -> str:
    # U+00B7 pid-marker strip — same defense as action_lane._no_marker.
    return (s or "").replace("·", "")


def _clean(v: Any) -> Any:
    if isinstance(v, str):
        return _no_marker(v)
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return v


def _append(path: Path, row: dict[str, Any]) -> None:
    """ONE os.write per event on an O_APPEND fd — concurrent-append safe."""
    line = (json.dumps(row, default=str, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def _read_rows(path: Path) -> list[dict[str, Any]]:
    try:
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue  # torn/corrupt line — skip, never raise
        if isinstance(row, dict) and row.get("id"):
            rows.append(row)
    return rows


def _merged(path: Path) -> dict[str, dict[str, Any]]:
    """Compacted view: last written row wins per id."""
    state: dict[str, dict[str, Any]] = {}
    for row in _read_rows(path):
        state[str(row["id"])] = row
    return state


# ---------------------------------------------------------------------------
# Events + escalation (best-effort, never block the chain)
# ---------------------------------------------------------------------------

def _emit(event_type: str, row: dict[str, Any]) -> None:
    try:
        from framework.events.emitter import emit
        emit(event_type, actor=str(row.get("filed_by") or "needs"), payload={
            "need_id": row.get("id"),
            "kind": row.get("kind"),
            "status": row.get("status"),
            "risk_class": row.get("risk_class"),
            "action_type": row.get("action_type"),
            "lane": row.get("lane"),
            "count": row.get("count"),
        })
    except Exception:
        pass


def _escalate(row: dict[str, Any]) -> None:
    """cost_of_delay=blocking ⇒ ALSO ride the intake stream at ping-now."""
    try:
        from framework.frontdoor import intake
        intake.enqueue({
            "source": "needs",
            "kind": "need",
            "ts": row.get("last_seen") or _iso(_now()),
            "urgency_tier": "ping-now",
            "payload": {
                "summary": _no_marker(
                    f"BLOCKING need {row.get('id')} ({row.get('kind')}): "
                    f"{row.get('why') or ''}"
                )[:300],
                "need_id": row.get("id"),
            },
        })
    except Exception:
        pass
    _emit("need_escalated", row)


# ---------------------------------------------------------------------------
# Narrowest proposed grant line (kind=standing_grant auto-compose)
# ---------------------------------------------------------------------------

def _compose_grant_line(
    nid: str,
    risk_class: str | None,
    action_type: str | None,
    lane: str | None,
    scope_hint: dict[str, Any] | None,
    now: datetime,
) -> str | None:
    """The NARROWEST appendable grant row for the blocked step: the single
    action_type, the single lane (never `lane:'*'`; no lane ⇒ empty list the
    Captain must fill), rate 1/day, 90d expiry, class-appropriate scope
    skeleton seeded from `scope_hint` when the blocked step supplied one.
    Composable only when the step's class+type are known."""
    if not risk_class or not action_type:
        return None
    hint = scope_hint or {}
    if risk_class == "external_comms":
        recipient = str(hint.get("recipient") or "").strip()
        allow = json.dumps(recipient) if recipient else ""
        scope = ("{recipient_allowlist: [%s], max_eur_per_day: 0, "
                 "vendor_allowlist: []}" % allow)
    elif risk_class == "spend":
        amt = hint.get("amount_eur")
        amt = amt if isinstance(amt, (int, float)) and not isinstance(amt, bool) else 0
        scope = ("{recipient_allowlist: [], max_eur_per_day: %s, "
                 "vendor_allowlist: []}" % amt)
    else:
        vendor = str(hint.get("vendor") or "").strip()
        allow = json.dumps(vendor) if vendor else ""
        scope = ("{recipient_allowlist: [], max_eur_per_day: 0, "
                 "vendor_allowlist: [%s]}" % allow)
    lanes = "[%s]" % json.dumps(str(lane)) if lane else "[]"
    expires = (now + timedelta(days=90)).date().isoformat()
    return (
        "- {id: GRANT-%s, deployment: %s, risk_class: %s, action_types: [%s], "
        "lanes: %s, scope: %s, rate: {max_per_day: 1}, expires: %s, "
        "granted_by: \"Captain\", granted_at: %s, basis: %s, revoked: false}"
        % (
            nid[len("NEED-"):], json.dumps(cabinet_id())[1:-1], risk_class,
            json.dumps(str(action_type)), lanes, scope, expires,
            json.dumps(_iso(now)), json.dumps(nid),
        )
    )


# ---------------------------------------------------------------------------
# file_need — never raises, ~ms, single append
# ---------------------------------------------------------------------------

def file_need(
    kind: str,
    *,
    risk_class: str | None = None,
    action_type: str | None = None,
    lane: str | None = None,
    why: str,
    unblocks: str = "",
    proposed_grant_line: str | None = None,
    cost_of_delay: str = "medium",
    cost_note: str | None = None,
    filed_by: str,
    cid: str | None = None,
    root: str | Path | None = None,
    scope_hint: dict[str, Any] | None = None,
) -> str | None:
    """File (or re-file) a need; returns its id, or None on any no-op/failure.

    NEVER raises. No-ops: unknown kind, `needs_enabled()` false (the guardian
    bit-identical seam), denied-and-suppressed (90d). Re-filing an existing
    need bumps count/last_seen (full-row append, last-write-wins — concurrent
    re-files may under-count, tolerated by design). `scope_hint`
    ({recipient|amount_eur|vendor}) seeds the auto-composed NARROWEST
    proposed_grant_line for kind=standing_grant.
    """
    try:
        return _file_need(
            kind, risk_class=risk_class, action_type=action_type, lane=lane,
            why=why, unblocks=unblocks, proposed_grant_line=proposed_grant_line,
            cost_of_delay=cost_of_delay, cost_note=cost_note, filed_by=filed_by,
            cid=cid, root=root, scope_hint=scope_hint,
        )
    except Exception:
        return None


def _file_need(
    kind: str, *, risk_class, action_type, lane, why, unblocks,
    proposed_grant_line, cost_of_delay, cost_note, filed_by, cid, root,
    scope_hint,
) -> str | None:
    if kind not in KINDS:
        return None
    if not needs_enabled(root):
        return None
    now = _now()
    nid = need_id(kind, risk_class, action_type, lane)
    path = ledger_path(root)
    prev = _merged(path).get(nid)

    if prev and prev.get("status") == "denied":
        until = _to_dt(prev.get("suppressed_until"))
        if until and now < until:
            return None  # denied-and-suppressed ⇒ no-op (90d)

    if kind == "standing_grant" and proposed_grant_line is None:
        proposed_grant_line = _compose_grant_line(
            nid, risk_class, action_type, lane, scope_hint, now)

    row: dict[str, Any] = {
        "id": nid,
        "kind": kind,
        "risk_class": risk_class,
        "action_type": action_type,
        "lane": lane,
        "deployment": cabinet_id(),
        "status": "open",
        "why": why,
        "unblocks": unblocks,
        "proposed_grant_line": proposed_grant_line,
        "cost_of_delay": cost_of_delay,
        "cost_note": cost_note,
        "filed_by": filed_by,
        "cid": cid,
        "count": 1,
        "first_seen": _iso(now),
        "last_seen": _iso(now),
    }
    if prev:
        row["count"] = int(prev.get("count") or 0) + 1
        row["first_seen"] = prev.get("first_seen") or row["first_seen"]
        if proposed_grant_line is None and prev.get("proposed_grant_line"):
            row["proposed_grant_line"] = prev["proposed_grant_line"]
        status = prev.get("status")
        if status == "approved_pending_apply":
            # The Captain already said grant — keep the approval sticky.
            row["status"] = status
            for carry in ("marked_by", "marked_at", "reason"):
                if prev.get(carry) is not None:
                    row[carry] = prev[carry]
        elif status == "snoozed":
            until = _to_dt(prev.get("snoozed_until"))
            if until and now < until:
                # The Captain said later — re-filing must not un-snooze.
                row["status"] = status
                row["snoozed_until"] = prev.get("snoozed_until")

    row = _clean(row)
    _append(path, row)
    _emit("need_filed", row)
    if cost_of_delay == _BLOCKING:
        _escalate(row)
    return nid


# ---------------------------------------------------------------------------
# Read + lifecycle verbs
# ---------------------------------------------------------------------------

def list_open(
    now: Any = None,
    *,
    root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Compacted current needs (status open|approved_pending_apply), newest
    first. Inline 30d-expiry sweep on read: a stale open/lapsed-snooze row is
    appended as expired (+ need_expired event) and excluded. A snoozed row
    past its window is effectively open again. Every field _no_marker-safe.
    Never raises (a broken ledger reads as empty)."""
    try:
        nowdt = _now(now)
        path = ledger_path(root)
        out: list[dict[str, Any]] = []
        for nid, row in _merged(path).items():
            status = row.get("status")
            if status == "snoozed":
                until = _to_dt(row.get("snoozed_until"))
                if until and nowdt < until:
                    continue
                row = dict(row, status="open")  # snooze lapsed
                status = "open"
            if status not in ("open", "approved_pending_apply"):
                continue
            if status == "open":
                last = _to_dt(row.get("last_seen"))
                if last and (nowdt - last) > timedelta(days=OPEN_EXPIRY_DAYS):
                    expired = _clean(dict(
                        row, status="expired",
                        marked_by="sweep", marked_at=_iso(nowdt),
                    ))
                    _append(path, expired)
                    _emit("need_expired", expired)
                    continue
            out.append(_clean(dict(row)))
        out.sort(key=lambda r: str(r.get("last_seen") or ""), reverse=True)
        return out
    except Exception:
        return []


def mark(
    need_id: str,
    status: str,
    *,
    by: str,
    reason: str | None = None,
    root: str | Path | None = None,
    now: Any = None,
) -> dict[str, Any] | None:
    """Transition a need; returns the new row, or None on unknown id / bad
    status (the binder's fail-closed passthrough — a stale hex id must never
    approve anything). `denied` stamps 90d suppression; `snoozed` stamps 7d.
    Never raises."""
    try:
        if status not in STATUSES:
            return None
        nowdt = _now(now)
        path = ledger_path(root)
        prev = _merged(path).get(str(need_id))
        if prev is None:
            return None
        row = dict(prev)
        row["status"] = status
        row["marked_by"] = by
        row["marked_at"] = _iso(nowdt)
        if reason is not None:
            row["reason"] = reason
        if status == "denied":
            row["suppressed_until"] = _iso(nowdt + timedelta(days=DENY_SUPPRESS_DAYS))
        if status == "snoozed":
            row["snoozed_until"] = _iso(nowdt + timedelta(days=SNOOZE_DAYS))
        row = _clean(row)
        _append(path, row)
        ev = _STATUS_EVENTS.get(status)
        if ev:
            _emit(ev, row)
        return row
    except Exception:
        return None


def cross_check_grants(
    check_fn: Callable[..., dict[str, Any]],
    *,
    root: str | Path | None = None,
    now: Any = None,
) -> list[str]:
    """Close open standing_grant needs the grants table now covers.

    `check_fn(risk_class, action_type, *, lane)` → {granted, grant_id, ...};
    wire it to `grants.covers` (structural coverage — the per-item hard-scope
    predicate is act-time data, so `grants.check` without context would never
    close anything). Returns the closed need ids. Never raises."""
    closed: list[str] = []
    try:
        for row in list_open(now, root=root):
            if row.get("kind") != "standing_grant" or row.get("status") != "open":
                continue
            try:
                res = check_fn(
                    row.get("risk_class"), row.get("action_type"),
                    lane=row.get("lane"),
                )
            except Exception:
                continue
            if isinstance(res, dict) and res.get("granted"):
                mark(
                    row["id"], "granted",
                    by=f"cross_check:{res.get('grant_id')}",
                    reason="covered by standing grant",
                    root=root, now=now,
                )
                closed.append(row["id"])
    except Exception:
        pass
    return closed
