"""Read-only calendar overlap detector — the double-book precondition for
`calendar_event_create`.

DARK / INERT: nothing imports or calls this yet. A later germline window will
wire ``find_conflicts`` into ``framework/frontdoor/action_exec.py`` as a
precondition of the reversible ``calendar_event_create`` action (so an
unattended write never lands on top of an existing event). This module only
READS — it can never mutate a calendar.

Design mirrors ``calendar_template.py`` (the WRITE side): a single fixed
AppleScript run via ``osascript`` with an argv-passed value list. The two are
deliberately symmetric — write-template writes one event, this reads many —
but they share ZERO state and this one has no mutate verb anywhere.

Two lessons drive the shape:

  * **Bulk-get, don't whose-filter** (same lesson as Reminders 21s→1.6s). An
    AppleScript ``whose`` clause on Calendar is pathologically slow, so the
    script does a small number of BULK property reads per calendar
    (``start date of every event``, ``end date of every event``,
    ``summary of every event`` — a few Apple Events each, returning parallel
    lists) and never a per-event ``whose`` query. Window narrowing + the
    authoritative half-open overlap test happen in Python (fully unit-tested,
    see ``tests/test_calendar_read.py``).

  * **Untrusted text is inert data** (Corridor). The osascript source is a
    FIXED module constant; the ONLY values that cross into it are the two
    fixed ISO time bounds, passed as ``argv`` (never string-interpolated).
    No calendar name or event title is ever interpolated into the script
    source (command-injection surface). Every field read back from stdout is
    parsed as plain data and NEVER re-executed / eval'd. Parsing is
    defensive: empty stdout → empty list, malformed records skipped, never a
    crash.

Public surface (for the future germline wire):
    read_events(start_iso, end_iso, osascript=None) -> list[dict]
    overlaps(cand_start, cand_end, events)           -> list[dict]
    find_conflicts(cand_start, cand_end, osascript=None) -> list[dict]

WIRE CONTRACT (obligations on the future germline call-site in action_exec.py):
  * **Fail-closed on error.** ``find_conflicts`` / ``read_events`` raise
    ``CalendarReadError`` if the read itself failed (permission denied, Calendar
    unscriptable). The wire MUST treat a raise as 'conflict-state unknown → do
    NOT auto-write'. Only an empty list returned on SUCCESS means "no conflict,
    safe to write."
  * **Pass local wall-clock ISO only.** Calendar.app is naive/local; an
    offset-bearing bound is coerced to naive by DROPPING the offset (a
    wall-clock shift, not a conversion). The wire must hand in the same local
    wall-clock frame the write uses, never a zoned/UTC bound.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from typing import Callable

__all__ = ["read_events", "overlaps", "find_conflicts", "conflicts_for_due",
           "event_window", "CalendarReadError", "CALENDAR_READ_SCRIPT"]

# Delimiters between fields / records in the osascript stdout. Non-printable
# control chars (US / RS) that will not appear in a calendar name or title, so
# a title containing tabs / commas / newlines can never corrupt the framing.
_FS = "\x1f"  # ASCII 31 unit separator — between fields of one event
_RS = "\x1e"  # ASCII 30 record separator — between events

# [READ-ONLY] Fixed AppleScript source. Verbs used: `every event`, `name`,
# `start date`, `end date`, `summary`, `writable`. NONE of make/delete/set/save
# — this can only read. Only argv item 1/2 (the ISO bounds) cross in; they are
# used purely to pre-cull the already-bulk-read in-memory lists (a plain
# comparison, NOT a `whose` filter) so stdout stays bounded to the window. The
# authoritative filter still runs in Python. CRITICAL: the AS `parseIso` and the
# Python `_parse_iso` parse a bound to IDENTICAL precision (both keep seconds —
# see the seconds branch in `parseIso`), so the cull's `sD < d2` can never be
# stricter than Python's and thus can never drop a sub-minute conflict the
# authoritative filter would have kept.
CALENDAR_READ_SCRIPT = (
    'on run argv\n'
    'set d1 to my parseIso(item 1 of argv)\n'
    'set d2 to my parseIso(item 2 of argv)\n'
    'set fs to (ASCII character 31)\n'
    'set rs to (ASCII character 30)\n'
    'set out to ""\n'
    'tell application "Calendar"\n'
    ' repeat with c in every calendar\n'
    '  set wr to true\n'
    '  try\n'
    '   set wr to writable of c\n'
    '  end try\n'
    '  if wr then\n'
    '   try\n'
    '    set cn to name of c\n'
    '    set starts to start date of every event of c\n'
    '    set ends to end date of every event of c\n'
    '    set sums to summary of every event of c\n'
    '    repeat with i from 1 to (count of starts)\n'
    '     set sD to item i of starts\n'
    '     set eD to item i of ends\n'
    '     if (sD < d2) and (eD > d1) then\n'
    '      set sT to item i of sums\n'
    '      if sT is missing value then set sT to ""\n'
    '      set out to out & cn & fs & my isoOf(sD) & fs & my isoOf(eD) & fs & sT & rs\n'
    '     end if\n'
    '    end repeat\n'
    '   end try\n'
    '  end if\n'
    ' end repeat\n'
    'end tell\n'
    'return out\n'
    'end run\n'
    'on isoOf(dt)\n'
    ' set y to year of dt as integer\n'
    ' set mo to (month of dt as integer)\n'
    ' set dy to day of dt as integer\n'
    ' set hh to hours of dt as integer\n'
    ' set mm to minutes of dt as integer\n'
    ' set ss to seconds of dt as integer\n'
    ' return (my pad4(y)) & "-" & (my pad2(mo)) & "-" & (my pad2(dy)) & "T" & '
    '(my pad2(hh)) & ":" & (my pad2(mm)) & ":" & (my pad2(ss))\n'
    'end isoOf\n'
    'on pad2(n)\n'
    ' set s to n as string\n'
    ' if (count of s) < 2 then set s to "0" & s\n'
    ' return s\n'
    'end pad2\n'
    'on pad4(n)\n'
    ' set s to n as string\n'
    ' repeat while (count of s) < 4\n'
    '  set s to "0" & s\n'
    ' end repeat\n'
    ' return s\n'
    'end pad4\n'
    'on parseIso(s)\n'
    ' set d to current date\n'
    ' set year of d to (text 1 thru 4 of s) as integer\n'
    ' set month of d to (text 6 thru 7 of s) as integer\n'
    ' set day of d to (text 9 thru 10 of s) as integer\n'
    ' if (length of s) > 10 then\n'
    '  set hours of d to (text 12 thru 13 of s) as integer\n'
    '  set minutes of d to (text 15 thru 16 of s) as integer\n'
    ' else\n'
    '  set hours of d to 0\n'
    '  set minutes of d to 0\n'
    ' end if\n'
    ' if ((length of s) > 18) and ((text 17 thru 17 of s) is ":") then\n'
    '  set seconds of d to (text 18 thru 19 of s) as integer\n'
    ' else\n'
    '  set seconds of d to 0\n'
    ' end if\n'
    ' return d\n'
    'end parseIso')


class CalendarReadError(RuntimeError):
    """The calendar read could not be completed (osascript non-zero exit,
    automation permission denied, Calendar not scriptable). The future germline
    wire MUST treat this as 'conflict-state UNKNOWN → do NOT auto-write'
    (fail-closed). Contrast an empty result on SUCCESS — that means genuinely no
    overlapping event (safe to write). A silent empty string on failure would be
    the dangerous default (reads as 'no conflict' → double-book), so we raise."""


def _default_osascript(cmd: list) -> str:
    """Same invocation shape as action_exec._default_osascript — arg-list only,
    never shell=True, bounded timeout. Non-zero exit raises CalendarReadError so
    a total failure is LOUD (the wire fails closed) instead of a silent empty
    string. A single unreadable calendar does NOT reach here — the AppleScript
    wraps each calendar in its own ``try`` and skips only that one, so partial
    reads still exit 0."""
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise CalendarReadError(
            f"osascript exited {proc.returncode}: {(proc.stderr or '').strip()[:200]}")
    return proc.stdout.strip()


def _parse_iso(s: str) -> datetime | None:
    """Parse an ISO string to a NAIVE wall-clock datetime (or None if it can't
    be parsed). Calendar.app hands back local wall-clock times with no zone, so
    everything is compared in that frame — any 'Z'/offset on an incoming bound
    is dropped to keep both sides in the same (naive) frame. Missing time
    components default to 00:00:00 — identical to the AppleScript ``parseIso``,
    so the AS pre-cull and the Python filter can never disagree on a bound."""
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


def _parse_event_line(line: str) -> dict | None:
    """Parse one delimited stdout record into an inert event dict, or None if
    it is malformed (too few fields / unparseable dates). Never raises."""
    if not line:
        return None
    # maxsplit=3 so a title that somehow contains the field sep keeps its tail.
    fields = line.split(_FS, 3)
    if len(fields) < 4:
        return None
    cal, s_iso, e_iso, title = fields
    start = _parse_iso(s_iso)
    end = _parse_iso(e_iso)
    if start is None or end is None:
        return None
    return {
        "calendar": cal,
        "summary": title,
        "start": start,
        "end": end,
        "start_iso": s_iso,
        "end_iso": e_iso,
    }


def _parse_events(stdout: str) -> list[dict]:
    """Defensively parse the full osascript stdout into an event list. Empty /
    whitespace-only stdout → empty list; malformed records are skipped."""
    if not stdout or not stdout.strip():
        return []
    events: list[dict] = []
    for rec in stdout.split(_RS):
        if not rec.strip():
            continue
        ev = _parse_event_line(rec)
        if ev is not None:
            events.append(ev)
    return events


def overlaps(cand_start, cand_end, events: list[dict]) -> list[dict]:
    """Return the events (union across all calendars) that overlap the
    candidate block ``[cand_start, cand_end)`` under the HALF-OPEN interval
    test: two intervals (s1,e1) and (s2,e2) overlap iff ``s1 < e2 and s2 < e1``.
    Adjacent/touching blocks (one's end == the other's start) do NOT overlap.

    Pure Python — no osascript. ``cand_start`` / ``cand_end`` may be datetimes
    or ISO strings; each event must carry parsed ``start`` / ``end`` datetimes
    (as produced by ``read_events``). Events missing a parsed bound are skipped.
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
    across all WRITABLE local calendars.

    Runs the fixed read-only AppleScript once (bulk property reads, no
    ``whose``), then applies the authoritative Python-side half-open window
    filter. ``osascript`` is an injectable runner (arg-list → stdout str) for
    testing; defaults to a bounded ``subprocess.run``. Empty/garbled stdout on a
    SUCCESSFUL read yields an empty list (genuinely no overlap), never a crash.
    Raises ValueError on invalid caller-supplied bounds (a programming error);
    the default runner raises CalendarReadError if the read itself FAILS
    (non-zero exit / permission denied) — the wire must fail-closed on that,
    distinct from the safe empty-on-success case."""
    ws = _parse_iso(start_iso)
    we = _parse_iso(end_iso)
    if ws is None or we is None:
        raise ValueError("read_events requires valid ISO start/end bounds")
    runner = osascript or _default_osascript
    # ONLY the two fixed, inert ISO bounds cross into the AppleScript — as argv,
    # never interpolated into the script source.
    out = runner(["osascript", "-e", CALENDAR_READ_SCRIPT,
                  start_iso.strip(), end_iso.strip()])
    events = _parse_events(out or "")
    return overlaps(ws, we, events)


def find_conflicts(cand_start, cand_end,
                   osascript: Callable | None = None) -> list[dict]:
    """Convenience entry point for the future germline wire: given a candidate
    event block, return the existing events it would collide with. Thin wrapper
    — reads the window for the candidate block and returns the overlap set."""
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
    (Calendar.app's frame — the same frame ``_parse_iso`` / ``overlaps`` use).
    Raises ValueError on an unparseable due (a programming error, fail-loud)."""
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
    — the one call the future germline B2 wire in
    ``action_exec._exec_calendar_event`` needs before an act-first write. Uses
    ``event_window`` (block-window parity) + ``find_conflicts``. Propagates
    ``CalendarReadError`` unchanged: the wire MUST fail-closed (not write) on a
    raise, and treat a non-empty list as a conflict (per the WIRE CONTRACT)."""
    start, end = event_window(due_iso)
    return find_conflicts(start, end, osascript=osascript)
