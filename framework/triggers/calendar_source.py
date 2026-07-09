"""Calendar event source — the first ``due_event_triggers`` consumer (W10d).

The trigger registry has carried an ``on-event`` kind since Duty C shipped,
and ``registry.due_event_triggers(event_key)`` waited for an event source to
call it — NOTHING ever did (verified 2026-07-09): an on-event trigger was
write-only. The Captain's calendar is likewise perceived only at act-time
(overlap gather before a write) — upcoming events never reached the org's
attention path on their own.

One periodic tick closes both halves through EXISTING, already-granted
surfaces:

  1. calendar → intake: events starting inside the lookahead window (default
     120 min, ``CABINET_CAL_INTAKE_LEAD_MIN``) are enqueued as intake items
     (``source=calendar-intake``, ``kind=calendar-upcoming``, tier batch) via
     the signed read-only EventKit helper (framework.frontdoor.calendar_read
     — fail-closed CalendarReadError → tick reports, enqueues nothing).
     Dedup: one item per (uid, start) in a local seen-state, so a 15-min
     cadence never re-nags the same event.
  2. on-event consumer: pending ``on-event`` triggers whose ``event_key`` is
     ``calendar:<needle>`` fire when a window event matches (needle ==
     event uid, or case-insensitive substring of the title). Firing =
     intake item (``kind=trigger-fired``, tier ping-now honoring the
     trigger's own payload urgency) + ``registry.mark_fired`` (one-shot,
     exactly the registry's documented on-event contract).

Capture-only side effects: intake enqueue (always-safe durable capture, the
intake invariant) + mark_fired on matched on-event rows + its own seen-state
(atomic tmp+rename, ``~/.cabinet/state/calendar-intake.json``,
``CABINET_CALINTAKE_STATE`` override). No sends, no calendar writes — the
helper binary is read-only by construction.

Scheduled via the cabinet/services.yml row ``calendar-intake`` (every 15
min). Fully injectable (events / enqueue / registry / now) — tests run
without EventKit, TCC, or Redis.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

DEFAULT_LEAD_MIN = 120
_SEEN_TTL_DAYS = 7
EVENT_KEY_PREFIX = "calendar:"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lead_minutes() -> int:
    try:
        v = int(os.environ.get("CABINET_CAL_INTAKE_LEAD_MIN", DEFAULT_LEAD_MIN))
        return v if v > 0 else DEFAULT_LEAD_MIN
    except ValueError:
        return DEFAULT_LEAD_MIN


def state_path() -> Path:
    env = os.environ.get("CABINET_CALINTAKE_STATE")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".cabinet" / "state" / "calendar-intake.json"


def _load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _prune_seen(seen: dict, now: dt.datetime) -> dict:
    floor = _iso(now - dt.timedelta(days=_SEEN_TTL_DAYS))
    return {k: v for k, v in seen.items() if str(v) >= floor}


def _event_key_matches(needle: str, event: dict) -> bool:
    needle = (needle or "").strip()
    if not needle:
        return False
    if needle == str(event.get("uid") or ""):
        return True
    return needle.casefold() in str(event.get("title") or "").casefold()


def _event_brief(event: dict) -> dict:
    """The minimal, prompt-safe slice of an event that rides in a payload."""
    return {k: event.get(k) for k in ("uid", "title", "start", "end",
                                      "calendar") if event.get(k) is not None}


def _default_enqueue(item: dict) -> str:
    from framework.frontdoor import intake
    return intake.enqueue(item)


def _default_read_events(start_iso: str, end_iso: str) -> list[dict]:
    from framework.frontdoor import calendar_read
    return calendar_read.read_events(start_iso, end_iso)


def tick(*, now: Optional[dt.datetime] = None,
         read_events_fn: Optional[Callable[[str, str], list[dict]]] = None,
         enqueue_fn: Optional[Callable[[dict], str]] = None,
         registry=None,
         state_file: Optional[Path] = None) -> dict[str, Any]:
    """One perception tick. Returns a summary dict; never raises on the
    calendar transport (a failed read is REPORTED, not thrown — the tick
    runs under launchd and must not flap)."""
    now = now or _now()
    read_events_fn = read_events_fn or _default_read_events
    enqueue_fn = enqueue_fn or _default_enqueue
    if registry is None:
        from framework.triggers import registry as _reg
        registry = _reg
    spath = state_file or state_path()
    state = _load_state(spath)
    seen = _prune_seen(dict(state.get("seen") or {}), now)

    start_iso = _iso(now)
    end_iso = _iso(now + dt.timedelta(minutes=lead_minutes()))
    summary: dict[str, Any] = {"window": [start_iso, end_iso], "events": 0,
                               "enqueued": 0, "fired": 0, "errors": []}
    try:
        events = read_events_fn(start_iso, end_iso) or []
    except Exception as exc:  # noqa: BLE001 — fail-quiet, report the reason
        summary["errors"].append(f"calendar-read: {type(exc).__name__}: {exc}")
        return summary
    summary["events"] = len(events)

    # Pending calendar-keyed on-event triggers, fetched once.
    try:
        pending = [r for r in registry.list_triggers()
                   if r.get("kind") == "on-event"
                   and str(r.get("event_key") or "").startswith(EVENT_KEY_PREFIX)]
    except Exception as exc:  # noqa: BLE001
        pending = []
        summary["errors"].append(f"registry: {type(exc).__name__}: {exc}")

    for event in events:
        key = f"{event.get('uid') or event.get('title')}|{event.get('start')}"
        if key not in seen:
            item = {
                "source": "calendar-intake",
                "kind": "calendar-upcoming",
                "ts": _iso(now),
                "urgency_tier": "batch",
                "payload": {
                    "summary": (f"Upcoming: {event.get('title') or '(untitled)'}"
                                f" at {event.get('start')}"),
                    "event": _event_brief(event),
                },
                "context": {"why": "calendar perception tick",
                            "sources": ["calendar-intake"]},
            }
            try:
                enqueue_fn(item)
                seen[key] = _iso(now)
                summary["enqueued"] += 1
            except Exception as exc:  # noqa: BLE001 — one bad item ≠ dead tick
                summary["errors"].append(
                    f"enqueue: {type(exc).__name__}: {exc}")

        for trig in pending:
            if trig.get("status") != "pending":
                continue   # already fired via an earlier event this tick
            needle = str(trig.get("event_key") or "")[len(EVENT_KEY_PREFIX):]
            if not _event_key_matches(needle, event):
                continue
            item = {
                "source": "calendar-intake",
                "kind": "trigger-fired",
                "ts": _iso(now),
                "urgency_tier": "ping-now",
                "payload": {
                    "summary": (f"On-event trigger fired: "
                                f"{trig.get('label') or trig.get('id')} "
                                f"(matched calendar event "
                                f"{event.get('title') or event.get('uid')})"),
                    "trigger": {k: trig.get(k) for k in
                                ("id", "label", "payload", "event_key")},
                    "event": _event_brief(event),
                },
                "context": {"why": "on-event trigger matched a calendar event"
                                   " — gather-then-decide at fire time",
                            "sources": ["calendar-intake"]},
            }
            try:
                enqueue_fn(item)
                registry.mark_fired(trig["id"], now)
                trig["status"] = "fired"       # local view: one-shot
                summary["fired"] += 1
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append(
                    f"trigger-fire {trig.get('id')}: "
                    f"{type(exc).__name__}: {exc}")

    state["seen"] = seen
    state["last_tick"] = _iso(now)
    try:
        _save_state(spath, state)
    except OSError as exc:
        summary["errors"].append(f"state: {exc}")
    return summary


def main(argv: Optional[list[str]] = None) -> int:  # pragma: no cover - thin CLI
    import argparse
    parser = argparse.ArgumentParser(
        description="Calendar perception tick — upcoming events → intake; "
                    "calendar:<needle> on-event triggers fired (W10d).")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    summary = tick()
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"calendar-intake: events={summary['events']} "
              f"enqueued={summary['enqueued']} fired={summary['fired']} "
              f"errors={len(summary['errors'])}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys
    sys.exit(main())
