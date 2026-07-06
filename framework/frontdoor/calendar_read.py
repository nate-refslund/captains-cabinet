"""Read-only calendar overlap detector — the double-book precondition for
`calendar_event_create`.

Wired (germline B2) into ``framework/frontdoor/action_exec.py:_exec_calendar_event``
as a precondition of the reversible ``calendar_event_create`` action, so an
unattended write never lands on top of an existing event. This module only
READS — it can never mutate a calendar.

**Provider substrate (2026-07-05 rebuild).** The reader delegates the actual
calendar read to a SIGNED, read-only EventKit helper binary (the Apple Calendar
provider), invoked as ``<helper> read <start_iso> <end_iso>`` and emitting a
JSON array of ``{calendar,start,end,summary}``. Two real-integration findings
forced this (the prior AppleScript reader was only ever MOCK-tested, so its real
behavior was never validated — the root cause of every calendar bug):

  * **EventKit from a plain script is BLIND to the Captain's iCloud calendars.**
    macOS attributes calendar access to the *responsible process*; a bare
    ``osascript``/CLI inherits a write-only grant and sees one stub account. A
    binary SIGNED with ``NSCalendarsFullAccessUsageDescription`` gets its own
    grant and, at ``EKAuthorization.fullAccess``, sees ALL calendars (iCloud,
    Exchange, Google, subscriptions) — proven live (339 real events).

  * **An AppleScript ``whose`` scan is O(calendar size).** Reading the real
    calendars that way is ~70s (the ``start date`` index the old code assumed
    does not exist). EventKit's ``predicateForEvents(withStart:end:)`` is
    <0.1s and, unlike the AppleScript ``whose start date >= …`` cull, correctly
    returns events that START before the window but EXTEND into it.

The provider substrate is Mac-only by nature, but it is NEVER a hard framework
import: the helper is invoked as a subprocess (same shape as the old osascript
call) via a path resolved at runtime, so a clean-room / non-Mac deployment where
the helper is absent simply fails CLOSED (see the WIRE CONTRACT) — the framework
carries no compiled dependency and no launcher-specific path.

The target-agnostic Python half lives entirely here and is UNCHANGED across the
substrate swap: ``overlaps`` (the authoritative half-open interval filter),
``event_window`` / ``conflicts_for_due`` (block-window parity with the write),
``_parse_iso`` / ``_coerce_dt``.

Public surface (the germline wire calls ``conflicts_for_due``):
    read_events(start_iso, end_iso, osascript=None) -> list[dict]
    overlaps(cand_start, cand_end, events)          -> list[dict]
    find_conflicts(cand_start, cand_end, osascript=None) -> list[dict]
    conflicts_for_due(due_iso, osascript=None)      -> list[dict]

WIRE CONTRACT (obligations on the germline call-site in action_exec.py):
  * **Fail-closed on error.** ``read_events`` / ``conflicts_for_due`` raise
    ``CalendarReadError`` if the read itself failed (helper missing, permission
    denied, non-zero exit). The wire MUST treat a raise as 'conflict-state
    unknown → do NOT auto-write'. Only an empty list on SUCCESS means "no
    conflict, safe to write."
  * **Pass local wall-clock ISO only.** EventKit and the write template are both
    naive/local; an offset-bearing bound is coerced to naive by DROPPING the
    offset (a wall-clock shift, not a conversion). The wire must hand in the same
    local wall-clock frame the write uses, never a zoned/UTC bound.

The ``osascript=`` keyword on the public functions is the injectable command
runner (kept under that legacy name so the germline caller — which passes its own
runner — needs NO change). Whatever it names, it only ever executes the helper's
READ subcommand; the reader issues no mutating verb anywhere.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

__all__ = ["read_events", "overlaps", "find_conflicts", "conflicts_for_due",
           "event_window", "CalendarReadError", "CalendarShareError",
           "helper_path", "read_calinfo", "assert_calendar_private_for_actfirst"]

# The signed read-only EventKit helper (the Apple Calendar provider). Resolved at
# runtime — env override first, else a repo-root-relative `bin/` path. NEVER an
# `instance/`/`presets/` component (the layer-separation gate) and NEVER a
# hardcoded launcher path (the clean-room ratchet); an absent helper fails CLOSED.
_HELPER_ENV = "CABINET_CAL_HELPER"
_HELPER_BASENAME = "cabinet-calread"

# The subcommands this module invokes on the CONSOLIDATED helper. ``read`` is the
# read-only overlap gather; ``calinfo`` is the read-only per-calendar attribute
# report the act-first share-scope gate consults. Neither mutates a calendar (the
# mutating ``delete`` subcommand lives in the separate calendar_delete module so
# THIS module's read-only invariant stays literally true).
_READ_SUBCOMMAND = "read"
_CALINFO_SUBCOMMAND = "calinfo"

# --- all-day availability policy (env-flagged, reader-side) -------------------
# The consolidated helper no longer drops all-day events — it emits EVERY event
# tagged with all_day + availability, so 100% of the all-day/free-vs-busy policy
# lives here in the freely-editable reader and no future tweak needs another
# helper rebuild/re-grant. DEFAULT (flag unset/off): drop ALL all-day events —
# outcome byte-identical to the old helper-side ``.filter { !isAllDay }`` (records
# from an OLD helper carry no all_day field → parse as timed → kept, so a
# NEW-reader + OLD-helper combo is inert). When ON, an all-day event is dropped
# ONLY on an EXPLICIT free availability token; every other value — busy,
# unavailable, notSupported, tentative, unknown, OR a missing availability field —
# is KEPT as a conflict (the safe direction for a double-book guard: never a
# silent drop). Timed events are ALWAYS kept regardless of availability.
_ALLDAY_ENV = "CABINET_CAL_ALLDAY_BUSY_BLOCKS"
# Drop an all-day event ONLY on explicit ``free``. ``tentative`` means
# possibly-busy → KEEP (a safety-critical guard fails toward blocking); it is NOT
# in the drop-set (adopted verdict correction — the task spec drops FREE, keeps
# BUSY, and never says to drop tentative).
_ALLDAY_FREE_TOKENS = frozenset({"free"})

# --- real-sharees pre-write gate (F1) ----------------------------------------
# When set (comma-separated calendar names, normalized like CABINET_CAL_EXCLUDE),
# an act-first calendar write is PERMITTED only onto a listed calendar. This is
# the ONLY positive protection for the irreducible EventKit blind spot: a WRITABLE
# calDAV calendar the Captain shared with others reports shared_signal="none" and
# is indistinguishable from a private one. Unset → the allowlist is a no-op (the
# machine signal + the germline name-denylist are the only guards).
_PRIVATE_ENV = "CABINET_CAL_PRIVATE"

# Any positive machine shared-signal the helper's calinfo may report. A permit
# requires shared_signal == "none" exactly (a POSITIVE allow-list, not this
# deny-list) — this frozenset is only for readable diagnostics / docs.
_SHARED_SIGNALS = frozenset({"read_only", "subscription", "birthday", "sharees",
                             "delegated"})

# Calendar names the double-book gather IGNORES (comma-separated in
# CABINET_CAL_EXCLUDE) — a calendar the Captain can SEE but does NOT own (a
# partner's work calendar, a subscribed team calendar) must not block the
# Captain's time. Unset → exclude nothing (all calendars count — the safe default
# for a conflict guard). Instance policy, not framework default.
_EXCLUDE_ENV = "CABINET_CAL_EXCLUDE"


class CalendarReadError(RuntimeError):
    """The calendar read could not be completed (helper missing/non-executable,
    non-zero exit, automation permission denied, calendar not readable). The
    germline wire MUST treat this as 'conflict-state UNKNOWN → do NOT auto-write'
    (fail-closed). Contrast an empty result on SUCCESS — that means genuinely no
    overlapping event (safe to write). A silent empty on failure would be the
    dangerous default (reads as 'no conflict' → double-book), so we raise."""


def _repo_root() -> Path:
    """Repo root via CABINET_ROOT else a file-relative parents[N] — the sanctioned
    launcher-agnostic resolution (never a hardcoded path)."""
    root = os.environ.get("CABINET_ROOT")
    return Path(root) if root else Path(__file__).resolve().parents[2]


def _helper_path() -> str:
    """Resolve the signed EventKit helper binary path. ``CABINET_CAL_HELPER``
    wins (the instance points it at the built+signed binary); otherwise a
    repo-root ``bin/cabinet-calread``. Returns a path string — existence /
    executability is enforced at run time by the default runner (fail-closed)."""
    env = os.environ.get(_HELPER_ENV)
    if env:
        return env
    return str(_repo_root() / "bin" / _HELPER_BASENAME)


def helper_path() -> str:
    """Public alias of :func:`_helper_path` — the SHARED resolver so the read
    gather, the calinfo gate, and the calendar_delete reverse all resolve the
    SAME consolidated binary (env ``CABINET_CAL_HELPER`` else ``<root>/bin/
    cabinet-calread``). Pure path resolution — no calendar access, so exposing it
    does NOT break this module's read-only invariant."""
    return _helper_path()


def _allday_busy_blocks_enabled() -> bool:
    """True iff the all-day availability filter is opted IN via
    ``CABINET_CAL_ALLDAY_BUSY_BLOCKS`` (truthy = 1/true/yes/on, casefolded).
    Default False → the safe/no-op behavior (drop ALL all-day events)."""
    return (os.environ.get(_ALLDAY_ENV, "") or "").strip().casefold() in {
        "1", "true", "yes", "on"}


def _private_allowlist() -> set:
    """Calendar names (normalized: stripped + casefolded) an act-first write is
    permitted onto, from ``CABINET_CAL_PRIVATE`` (comma-separated). Empty/unset →
    an empty set (the allowlist is a no-op). Mirrors :func:`_excluded_calendars`."""
    raw = os.environ.get(_PRIVATE_ENV, "") or ""
    return {name.strip().casefold() for name in raw.split(",") if name.strip()}


def _excluded_calendars() -> set:
    """Calendar names (normalized: stripped + casefolded) the double-book gather
    ignores, from CABINET_CAL_EXCLUDE (comma-separated). Empty/unset → an empty
    set (exclude nothing). This is instance policy — which calendars are the
    Captain's OWN commitments; a partner/subscribed calendar the Captain can see
    but does not own goes here so its events never count as a conflict. A typo'd
    name simply doesn't match (no crash, no silent over-exclusion of a real one)."""
    raw = os.environ.get(_EXCLUDE_ENV, "") or ""
    return {name.strip().casefold() for name in raw.split(",") if name.strip()}


def _default_runner(cmd: list) -> str:
    """Default command runner — arg-list only, never shell=True, bounded timeout.
    RAISES CalendarReadError if the helper is missing/non-executable or exits
    non-zero, so a total failure is LOUD (the wire fails closed) instead of a
    silent empty string. Mirrors action_exec._default_osascript's raise-on-error
    contract (the germline caller injects that runner instead of this one)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError as e:                        # helper not built / bad path
        raise CalendarReadError(
            f"calendar helper not found ({cmd[0]!r}); build it via "
            f"cabinet/scripts/build-calendar-helper.sh or set {_HELPER_ENV}") from e
    except subprocess.TimeoutExpired as e:                # e.g. a headless first-run TCC hang
        raise CalendarReadError(f"calendar helper timed out (>30s): {cmd[0]!r}") from e
    except OSError as e:                                  # not executable, etc.
        raise CalendarReadError(f"calendar helper unrunnable ({cmd[0]!r}): {e}") from e
    if proc.returncode != 0:
        raise CalendarReadError(
            f"calendar helper exited {proc.returncode}: {(proc.stderr or '').strip()[:200]}")
    return proc.stdout.strip()


def _parse_iso(s: str) -> datetime | None:
    """Parse an ISO string to a NAIVE wall-clock datetime (or None if it can't be
    parsed). EventKit and the write template both hand back local wall-clock times
    with no zone, so everything is compared in that frame — any 'Z'/offset on an
    incoming bound is dropped to keep both sides in the same (naive) frame. Missing
    time components default to 00:00:00."""
    s = (s or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1]
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def _coerce_dt(v) -> datetime:
    """Accept either a datetime (tz stripped to naive) or an ISO string."""
    if isinstance(v, datetime):
        return v.replace(tzinfo=None) if v.tzinfo is not None else v
    if isinstance(v, str):
        dt = _parse_iso(v)
        if dt is None:
            raise ValueError(f"unparseable ISO datetime: {v!r}")
        return dt
    raise TypeError(f"expected datetime or ISO str, got {type(v).__name__}")


def _event_from_record(rec) -> dict | None:
    """Turn one helper JSON record ``{calendar,start,end,summary}`` into an inert
    event dict, or None if it is malformed (not an object / missing or unparseable
    bounds). Never raises. ``summary`` defaults to '' (an untitled event still
    occupies its slot). Every field is treated as plain data, never re-executed."""
    if not isinstance(rec, dict):
        return None
    start = _parse_iso(rec.get("start"))
    end = _parse_iso(rec.get("end"))
    if start is None or end is None:
        return None
    cal = rec.get("calendar")
    title = rec.get("summary")
    # all_day / availability (consolidated helper, 2026-07-06). Robust parse: a
    # missing all_day → False → treated as TIMED → kept (the safe direction; also
    # what an OLD helper's records do). availability lowercased; a non-str value
    # (or missing) → '' — an explicit isinstance guard so _event_from_record can
    # never raise on a malformed record (its 'never raises' contract).
    all_day = str(rec.get("all_day")).strip().lower() == "true"
    _av = rec.get("availability")
    availability = _av.strip().lower() if isinstance(_av, str) else ""
    return {
        "calendar": cal if isinstance(cal, str) else "",
        "summary": title if isinstance(title, str) else "",
        "start": start,
        "end": end,
        "start_iso": rec.get("start"),
        "end_iso": rec.get("end"),
        "all_day": all_day,
        "availability": availability,
    }


def _parse_events(stdout: str) -> list[dict]:
    """Parse the helper's JSON stdout into an event list. Empty / whitespace-only
    stdout → [] (the injected-runner 'no events' convention). But non-empty stdout
    that is NOT a JSON array is an ANOMALY on a successful read — the pristine
    helper always prints at least ``[]`` — so it RAISES CalendarReadError (a
    garbled/corrupted read must NEVER be mistaken for 'no conflict → safe to
    write'; that is the exact fail-open this rebuild exists to kill). Individual
    malformed records *within* a valid array are skipped. Parsing is inert: values
    are data, never eval'd."""
    if not stdout or not stdout.strip():
        return []
    try:
        data = json.loads(stdout)
    except (ValueError, TypeError) as e:
        raise CalendarReadError(
            f"calendar helper stdout is not valid JSON: {stdout[:120]!r}") from e
    if not isinstance(data, list):
        raise CalendarReadError(
            f"calendar helper stdout is not a JSON array (got {type(data).__name__})")
    events: list[dict] = []
    for rec in data:
        ev = _event_from_record(rec)
        if ev is not None:
            events.append(ev)
    return events


def overlaps(cand_start, cand_end, events: list[dict]) -> list[dict]:
    """Return the events (union across all calendars) that overlap the candidate
    block ``[cand_start, cand_end)`` under the HALF-OPEN interval test: two
    intervals (s1,e1) and (s2,e2) overlap iff ``s1 < e2 and s2 < e1``.
    Adjacent/touching blocks (one's end == the other's start) do NOT overlap —
    this is authoritative and corrects any boundary-touch EventKit's predicate may
    include.

    Pure Python — no subprocess. ``cand_start`` / ``cand_end`` may be datetimes or
    ISO strings; each event must carry parsed ``start`` / ``end`` datetimes (as
    produced by ``read_events``). Events missing a parsed bound are skipped.
    """
    s1 = _coerce_dt(cand_start)
    e1 = _coerce_dt(cand_end)
    hits: list[dict] = []
    for ev in events:
        s2 = ev.get("start")
        e2 = ev.get("end")
        if not isinstance(s2, datetime) or not isinstance(e2, datetime):
            continue
        if s1 < e2 and s2 < e1:  # half-open overlap; adjacency (==) excluded
            hits.append(ev)
    return hits


def read_events(start_iso: str, end_iso: str,
                osascript: Callable | None = None) -> list[dict]:
    """Return existing events overlapping the window ``[start_iso, end_iso)``
    across ALL of the Captain's calendars.

    Invokes the signed read-only EventKit helper once (``<helper> read <start>
    <end>``), then applies the authoritative Python-side half-open window filter.
    ``osascript`` is the injectable command runner (arg-list → stdout str) for
    testing and for the germline caller (which passes its own raise-on-error
    runner); it defaults to a bounded, fail-closed ``subprocess.run``. Empty /
    garbled stdout on a SUCCESSFUL read yields an empty list (genuinely no
    overlap), never a crash. Raises ValueError on invalid caller-supplied bounds
    (a programming error); the default runner raises CalendarReadError if the read
    itself FAILS (helper missing / non-zero exit / permission denied) — the wire
    must fail-closed on that, distinct from the safe empty-on-success case."""
    ws = _parse_iso(start_iso)
    we = _parse_iso(end_iso)
    if ws is None or we is None:
        raise ValueError("read_events requires valid ISO start/end bounds")
    runner = osascript or _default_runner
    # ONLY the two fixed, inert ISO bounds cross into the helper — as argv to the
    # READ subcommand, never interpolated / shell. This module issues no other
    # subcommand: it can never mutate a calendar.
    cmd = [_helper_path(), _READ_SUBCOMMAND, start_iso.strip(), end_iso.strip()]
    try:
        out = runner(cmd)
    except CalendarReadError:
        raise
    except Exception as e:
        # FAIL-CLOSED BY CONSTRUCTION. The germline caller injects its OWN runner
        # (action_exec._default_osascript — a bare subprocess.run that raises a raw
        # FileNotFoundError on a missing helper, subprocess.TimeoutExpired on a TCC
        # hang, RuntimeError on a non-zero exit). Since the helper binary is built
        # on demand (gitignored), 'missing helper' is the DEFAULT state of a fresh
        # deployment — so we normalize ANY runner failure to CalendarReadError here
        # rather than trust a specific runner's error typing. The wire then fails
        # closed (unknown conflict-state → no write) with the documented type.
        raise CalendarReadError(
            f"calendar read failed ({type(e).__name__}: {e})") from e
    events = _parse_events(out or "")
    excluded = _excluded_calendars()
    if excluded:
        # Drop calendars the Captain can see but does not own (CABINET_CAL_EXCLUDE)
        # BEFORE the overlap test, so a partner/subscribed calendar never conflicts.
        events = [e for e in events
                  if (e.get("calendar") or "").strip().casefold() not in excluded]
    # All-day availability filter (runs AFTER the exclude drop, BEFORE overlaps).
    # Keep every event UNLESS it is all-day AND (the flag is ON AND it carries an
    # explicit free token). Flag OFF → drop ALL all-day (byte-identical to the old
    # helper). A missing all_day → timed → kept.
    allday_on = _allday_busy_blocks_enabled()
    events = [e for e in events
              if (not e.get("all_day"))
              or (allday_on and e.get("availability") not in _ALLDAY_FREE_TOKENS)]
    return overlaps(ws, we, events)


def find_conflicts(cand_start, cand_end,
                   osascript: Callable | None = None) -> list[dict]:
    """Convenience entry point for the germline wire: given a candidate event
    block, return the existing events it would collide with. Thin wrapper — reads
    the window for the candidate block and returns the overlap set."""
    s = _coerce_dt(cand_start)
    e = _coerce_dt(cand_end)
    return read_events(s.isoformat(), e.isoformat(), osascript=osascript)


# 30-minute block, matching CALENDAR_EVENT_SCRIPT's `startDate + (30 * minutes)`.
_BLOCK_MINUTES = 30


def event_window(due_iso: str) -> tuple[datetime, datetime]:
    """The [start, end) block a calendar event will OCCUPY for ``due_iso`` — the
    single authoritative replica of the block math in
    ``framework/frontdoor/calendar_template.py`` CALENDAR_EVENT_SCRIPT (its
    ``parseIso`` + 30-minute span), so a double-book gather reads the SAME window
    the write lands on and cannot drift from it.

    Byte-for-byte with that AppleScript ``parseIso``: the date is chars 1-10; a
    due WITHOUT a time part (``len <= 10``) defaults to 09:00 local; a timed due
    takes its HH at 12-13 and MM at 15-16; seconds are ZEROED (the write template
    does not set seconds); the block is 30 minutes. Returns NAIVE local datetimes
    (the same frame ``_parse_iso`` / ``overlaps`` use). Raises ValueError on an
    unparseable due (a programming error, fail-loud)."""
    s = (due_iso or "").strip()
    if not s:
        raise ValueError("event_window requires a due_iso")
    try:
        year, month, day = int(s[0:4]), int(s[5:7]), int(s[8:10])
        if len(s) > 10:                       # timed — mirror AS text 12-13 / 15-16
            hour, minute = int(s[11:13]), int(s[14:16])
        else:                                 # date-only — AS defaults to 09:00
            hour, minute = 9, 0
        start = datetime(year, month, day, hour, minute, 0)   # seconds zeroed
    except (ValueError, IndexError):
        raise ValueError(f"event_window: unparseable due_iso {due_iso!r}")
    return start, start + timedelta(minutes=_BLOCK_MINUTES)


def conflicts_for_due(due_iso: str,
                      osascript: Callable | None = None) -> list[dict]:
    """The existing events that overlap the 30-min block ``due_iso`` will occupy
    — the one call the germline B2 wire in
    ``action_exec._exec_calendar_event`` needs before an act-first write. Uses
    ``event_window`` (block-window parity) + ``find_conflicts``. Propagates
    ``CalendarReadError`` unchanged: the wire MUST fail-closed (not write) on a
    raise, and treat a non-empty list as a conflict (per the WIRE CONTRACT)."""
    start, end = event_window(due_iso)
    return find_conflicts(start, end, osascript=osascript)


# --- real-sharees pre-write gate (F1) ----------------------------------------

class CalendarShareError(CalendarReadError):
    """The target calendar could NOT be positively cleared as the Captain's own
    private, un-shared, writable calendar for an act-first (unattended) write —
    because the helper's real EventKit attribute report was unobtainable/garbled
    (subclassing CalendarReadError so the germline wire's existing fail-closed
    catch treats it identically) OR because the report shows a positive shared
    signal / non-writability / duplicate-title ambiguity / an allowlist miss.
    The wire MUST fail-closed on a raise (refuse the write). 'Unknown share-state
    → refuse' is the whole point — an act-first block must never surface on a
    calendar a third party can see."""


def read_calinfo(cal_name: str,
                 osascript: Callable | None = None) -> dict:
    """Invoke the consolidated helper's read-only ``calinfo <calendar>`` and
    return the parsed attribute object. STRICT + fail-closed: RAISES
    CalendarShareError on ANY inability to obtain a clean report — runner
    raise (helper missing / non-zero exit incl. the fullAccess exit-3 that a
    write-only/officer context produces / timeout), non-JSON or non-object
    stdout, ``found:false``, or any of the safety keys {found, writable,
    ambiguous, shared, shared_signal} absent or of the wrong type. Returning a
    dict means every safety key was present and well-typed (the caller still
    checks their VALUES)."""
    name = (cal_name or "").strip()
    if not name:
        raise CalendarShareError("read_calinfo requires a calendar name")
    runner = osascript or _default_runner
    cmd = [_helper_path(), _CALINFO_SUBCOMMAND, name]
    try:
        out = runner(cmd)
    except CalendarReadError:
        raise
    except Exception as e:                       # normalize any runner failure
        raise CalendarShareError(
            f"calinfo read failed ({type(e).__name__}: {e})") from e
    try:
        obj = json.loads(out or "")
    except (ValueError, TypeError) as e:
        raise CalendarShareError(
            f"calinfo stdout is not valid JSON: {(out or '')[:120]!r}") from e
    if not isinstance(obj, dict):
        raise CalendarShareError(
            f"calinfo stdout is not a JSON object (got {type(obj).__name__})")
    # Strict presence + type check of every safety key — a partial/garbled object
    # must fail closed, never read as 'safe' by a missing key (fail-closed BY
    # CONSTRUCTION, mirroring _parse_events raising on a non-array).
    if obj.get("found") is False:
        raise CalendarShareError(f"calinfo: calendar {name!r} not found")
    for key, typ in (("found", bool), ("writable", bool), ("ambiguous", bool),
                     ("shared", bool), ("shared_signal", str)):
        if not isinstance(obj.get(key), typ):
            raise CalendarShareError(
                f"calinfo missing/mistyped safety key {key!r} — refusing")
    return obj


def assert_calendar_private_for_actfirst(cal_name: str,
                                         osascript: Callable | None = None) -> None:
    """Raise CalendarShareError unless the target calendar is POSITIVELY cleared
    as the Captain's own private, un-shared, writable calendar for an act-first
    write. POSITIVE ALLOW-LIST (fail-closed by construction): permit iff EVERY
    safety key holds its exact safe value —
        found is True AND writable is True AND ambiguous is False
        AND shared is False AND shared_signal == "none"
    — plus, when ``CABINET_CAL_PRIVATE`` is set, the name is a member. ANY other
    value, an unknown shared_signal, a partial report, or an unobtainable report
    raises (refuse). Called on the act-first path in the germline
    ``action_exec._exec_calendar_event`` (after the cheap name-denylist, before
    the double-book gather).

    The irreducible residual (real EventKit limit): a WRITABLE calDAV calendar the
    Captain shared with others reports shared_signal="none" and is PERMITTED unless
    CABINET_CAL_PRIVATE names the safe set — that allowlist + the germline
    name-denylist are the only positive protection for that case."""
    info = read_calinfo(cal_name, osascript=osascript)   # raises = refuse
    if info.get("found") is not True:
        raise CalendarShareError(f"calendar {cal_name!r} not found — refusing act-first write")
    if info.get("writable") is not True:
        raise CalendarShareError(f"calendar {cal_name!r} is not writable — refusing act-first write")
    if info.get("ambiguous") is not False:
        raise CalendarShareError(
            f"calendar {cal_name!r} is ambiguous (duplicate title) — refusing act-first write")
    if info.get("shared") is not False:
        raise CalendarShareError(f"calendar {cal_name!r} is shared — refusing act-first write")
    if info.get("shared_signal") != "none":
        raise CalendarShareError(
            "calendar %r has shared signal %r — refusing act-first write"
            % (cal_name, info.get("shared_signal")))
    allow = _private_allowlist()
    if allow and (cal_name or "").strip().casefold() not in allow:
        raise CalendarShareError(
            f"calendar {cal_name!r} not in CABINET_CAL_PRIVATE allowlist — refusing act-first write")
