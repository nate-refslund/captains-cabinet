"""Durable trigger registry — the Chair's Duty C primitive.

Backs "remind me tomorrow about X", "every 30 min check Y", "when Z happens do A".
The Chair REGISTERS a trigger when Nate asks; a checker (cabinet/scripts/check-triggers.py,
launchd every minute) finds DUE triggers and fires them into the Chair's Redis trigger
stream, which wakes the Chair to **gather-then-decide at fire time** (re-check before acting;
never a stale nudge). This is the primitive the screenpipe `reminders` pipe needs before it
can migrate into the cabinet.

Storage: a JSON file (durable across restarts; atomic write), `instance/state/triggers.json`
by default (override `CABINET_TRIGGERS_FILE`). Pure + dependency-free so it is unit-testable
and the checker/Chair both import it.

Kinds:
  - `at-time`   : fire ONCE at `fire_at` (ISO-8601 UTC), then status→fired.
  - `interval`  : fire every `interval_sec`; on fire, reschedule fire_at += interval_sec.
  - `on-event`  : fire when an external event matches `event_key` (the checker is time-based;
                  on-event triggers are surfaced via `due_event_triggers(event_key)` instead).

A trigger row:
  {id, kind, label, payload, fire_at, interval_sec, event_key, status, created_at, last_fired, fire_count}
`payload` is whatever the Chair needs to act (e.g. {"about": "...", "person": "...", "course": [...]}).
"""
from __future__ import annotations

import os
import json
import uuid
import tempfile
import datetime
from typing import Any, Optional

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_FILE = os.path.join(_REPO_ROOT, "instance", "state", "triggers.json")

_VALID_KINDS = ("at-time", "interval", "on-event")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt: datetime.datetime) -> str:
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: str) -> Optional[datetime.datetime]:
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _path() -> str:
    return os.environ.get("CABINET_TRIGGERS_FILE") or _DEFAULT_FILE


def _load() -> list[dict]:
    """All trigger rows (or [] if none). Tolerant of a missing/garbage file."""
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(rows: list[dict]) -> None:
    """Atomic write (temp + rename) so a crash never leaves a half-written registry."""
    p = _path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=".triggers-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def register_trigger(*, kind: str, payload: dict, label: str = "",
                     fire_at: Optional[str] = None,
                     interval_sec: Optional[int] = None,
                     event_key: Optional[str] = None) -> dict:
    """Register a durable trigger. Returns the stored row (with its id).

    - at-time : pass `fire_at` (ISO-8601). Required.
    - interval: pass `interval_sec` (and optional `fire_at` for the first fire;
                defaults to now+interval_sec).
    - on-event: pass `event_key` (the external event name the checker matches).
    Raises ValueError on an invalid/under-specified spec — fail loud, never a silent
    no-fire reminder.
    """
    if kind not in _VALID_KINDS:
        raise ValueError(f"kind must be one of {_VALID_KINDS}, got {kind!r}")
    if not isinstance(payload, dict) or not payload:
        raise ValueError("payload must be a non-empty dict (what to do at fire time)")

    now = _now()
    if kind == "at-time":
        if not _parse(fire_at or ""):
            raise ValueError("at-time trigger needs a valid ISO-8601 fire_at")
        fa = fire_at
    elif kind == "interval":
        if not interval_sec or interval_sec <= 0:
            raise ValueError("interval trigger needs interval_sec > 0")
        fa = fire_at or _iso(now + datetime.timedelta(seconds=int(interval_sec)))
    else:  # on-event
        if not event_key:
            raise ValueError("on-event trigger needs an event_key")
        fa = None

    row = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "label": label or payload.get("about") or payload.get("label") or kind,
        "payload": payload,
        "fire_at": fa,
        "interval_sec": int(interval_sec) if interval_sec else None,
        "event_key": event_key,
        "status": "pending",
        "created_at": _iso(now),
        "last_fired": None,
        "fire_count": 0,
    }
    rows = _load()
    rows.append(row)
    _save(rows)
    return row


def due_triggers(now: Optional[datetime.datetime] = None) -> list[dict]:
    """Pending time-based (at-time / interval) triggers whose fire_at <= now."""
    now = now or _now()
    out = []
    for r in _load():
        if r.get("status") != "pending" or r.get("kind") == "on-event":
            continue
        fa = _parse(r.get("fire_at") or "")
        if fa and fa <= now:
            out.append(r)
    return out


def due_event_triggers(event_key: str) -> list[dict]:
    """Pending on-event triggers matching `event_key` (the event source calls this)."""
    return [r for r in _load()
            if r.get("status") == "pending" and r.get("kind") == "on-event"
            and r.get("event_key") == event_key]


def mark_fired(trigger_id: str, now: Optional[datetime.datetime] = None) -> Optional[dict]:
    """Record a fire. at-time/on-event → status=fired (one-shot). interval →
    reschedule fire_at += interval_sec and stay pending. Returns the updated row."""
    now = now or _now()
    rows = _load()
    updated = None
    for r in rows:
        if r.get("id") != trigger_id:
            continue
        r["last_fired"] = _iso(now)
        r["fire_count"] = int(r.get("fire_count") or 0) + 1
        if r.get("kind") == "interval" and r.get("interval_sec"):
            r["fire_at"] = _iso(now + datetime.timedelta(seconds=int(r["interval_sec"])))
            r["status"] = "pending"
        else:
            r["status"] = "fired"
        updated = r
        break
    if updated is not None:
        _save(rows)
    return updated


def cancel_trigger(trigger_id: str) -> bool:
    """Cancel a trigger (status→cancelled). Returns True if found."""
    rows = _load()
    found = False
    for r in rows:
        if r.get("id") == trigger_id and r.get("status") == "pending":
            r["status"] = "cancelled"
            found = True
            break
    if found:
        _save(rows)
    return found


def list_triggers(include_done: bool = False) -> list[dict]:
    """All pending triggers (or everything if include_done)."""
    rows = _load()
    if include_done:
        return rows
    return [r for r in rows if r.get("status") == "pending"]
