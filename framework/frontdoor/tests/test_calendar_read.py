"""Unit tests for the read-only calendar overlap detector
(framework/frontdoor/calendar_read).

Pure Python — NO osascript in the unit path. The AppleScript bulk-read is a
separate seam; here we exercise the parse + half-open interval logic directly,
plus ``read_events`` / ``find_conflicts`` through an INJECTED fake runner that
returns canned delimited stdout (never spawns a subprocess).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime

import pytest

from framework.frontdoor import calendar_read as cr


def _dt(y, mo, d, h=0, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s)


def _ev(cal, start, end, summary="ev"):
    """Build an event dict in the shape read_events produces."""
    return {"calendar": cal, "summary": summary, "start": start, "end": end,
            "start_iso": start.isoformat(), "end_iso": end.isoformat()}


# --- overlaps: the half-open interval core ------------------------------------

def test_overlap_true_partial():
    events = [_ev("Cabinet", _dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0))]
    hits = cr.overlaps(_dt(2026, 7, 5, 10, 30), _dt(2026, 7, 5, 11, 30), events)
    assert hits == events


def test_no_overlap_disjoint():
    events = [_ev("Cabinet", _dt(2026, 7, 5, 9, 0), _dt(2026, 7, 5, 10, 0))]
    hits = cr.overlaps(_dt(2026, 7, 5, 11, 0), _dt(2026, 7, 5, 12, 0), events)
    assert hits == []


def test_exact_adjacency_does_not_overlap_after():
    # existing ends 10:00, candidate starts 10:00 → touching, NOT overlapping.
    events = [_ev("Cabinet", _dt(2026, 7, 5, 9, 0), _dt(2026, 7, 5, 10, 0))]
    hits = cr.overlaps(_dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0), events)
    assert hits == []


def test_exact_adjacency_does_not_overlap_before():
    # candidate ends 10:00, existing starts 10:00 → touching, NOT overlapping.
    events = [_ev("Cabinet", _dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0))]
    hits = cr.overlaps(_dt(2026, 7, 5, 9, 0), _dt(2026, 7, 5, 10, 0), events)
    assert hits == []


def test_containment_event_inside_candidate():
    events = [_ev("Cabinet", _dt(2026, 7, 5, 10, 15), _dt(2026, 7, 5, 10, 45))]
    hits = cr.overlaps(_dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0), events)
    assert hits == events


def test_containment_candidate_inside_event():
    events = [_ev("Cabinet", _dt(2026, 7, 5, 9, 0), _dt(2026, 7, 5, 12, 0))]
    hits = cr.overlaps(_dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0), events)
    assert hits == events


def test_multi_event_union_across_calendars():
    a = _ev("Cabinet", _dt(2026, 7, 5, 10, 30), _dt(2026, 7, 5, 11, 0), "a")
    b = _ev("Work", _dt(2026, 7, 5, 9, 0), _dt(2026, 7, 5, 10, 0), "b")   # miss
    c = _ev("Personal", _dt(2026, 7, 5, 10, 45), _dt(2026, 7, 5, 11, 30), "c")
    hits = cr.overlaps(_dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0), [a, b, c])
    assert hits == [a, c]  # union across calendars, adjacency-miss excluded


def test_empty_event_list():
    assert cr.overlaps(_dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0), []) == []


def test_overlaps_accepts_iso_strings():
    events = [_ev("Cabinet", _dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0))]
    hits = cr.overlaps("2026-07-05T10:30:00", "2026-07-05T11:30:00Z", events)
    assert hits == events


def test_overlaps_skips_events_missing_parsed_bounds():
    good = _ev("Cabinet", _dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0))
    bad = {"calendar": "X", "summary": "no dates", "start": None, "end": None}
    hits = cr.overlaps(_dt(2026, 7, 5, 10, 30), _dt(2026, 7, 5, 11, 30),
                       [bad, good])
    assert hits == [good]


# --- defensive stdout parsing (no osascript) ----------------------------------

def _line(cal, s_iso, e_iso, title):
    return cr._FS.join([cal, s_iso, e_iso, title])


def test_parse_events_empty_stdout_is_empty_list():
    assert cr._parse_events("") == []
    assert cr._parse_events("   \n  ") == []


def test_parse_events_well_formed_records():
    stdout = cr._RS.join([
        _line("Cabinet", "2026-07-05T10:00:00", "2026-07-05T11:00:00", "standup"),
        _line("Work", "2026-07-05T13:00:00", "2026-07-05T14:00:00", "review"),
    ]) + cr._RS  # trailing RS like the real script emits
    events = cr._parse_events(stdout)
    assert len(events) == 2
    assert events[0]["calendar"] == "Cabinet"
    assert events[0]["summary"] == "standup"
    assert events[0]["start"] == _dt(2026, 7, 5, 10, 0)
    assert events[1]["end"] == _dt(2026, 7, 5, 14, 0)


def test_parse_events_skips_malformed_records():
    stdout = cr._RS.join([
        "too" + cr._FS + "few",                                    # 2 fields
        _line("Cabinet", "not-a-date", "2026-07-05T11:00:00", "x"),  # bad start
        _line("Cabinet", "2026-07-05T10:00:00", "2026-07-05T11:00:00", "ok"),
    ])
    events = cr._parse_events(stdout)
    assert len(events) == 1
    assert events[0]["summary"] == "ok"


def test_parse_event_line_title_keeps_trailing_separator():
    # a title that itself contains the field sep must not lose its tail.
    line = _line("Cabinet", "2026-07-05T10:00:00", "2026-07-05T11:00:00",
                 "a" + cr._FS + "b")
    ev = cr._parse_event_line(line)
    assert ev is not None
    assert ev["summary"] == "a" + cr._FS + "b"


# --- read_events / find_conflicts through an injected fake runner --------------

def _fake_runner(stdout):
    calls = []

    def run(cmd):
        calls.append(cmd)
        return stdout

    run.calls = calls
    return run


def test_read_events_filters_window_and_passes_only_bounds_as_argv():
    stdout = cr._RS.join([
        _line("Cabinet", "2026-07-05T10:30:00", "2026-07-05T11:00:00", "in"),
        _line("Cabinet", "2026-07-05T08:00:00", "2026-07-05T09:00:00", "before"),
    ]) + cr._RS
    runner = _fake_runner(stdout)
    events = cr.read_events("2026-07-05T10:00:00", "2026-07-05T11:00:00",
                            osascript=runner)
    assert [e["summary"] for e in events] == ["in"]  # 'before' filtered out
    # argv carries ONLY osascript -e SCRIPT + the two fixed ISO bounds.
    cmd = runner.calls[0]
    assert cmd[0] == "osascript" and cmd[1] == "-e"
    assert cmd[2] is cr.CALENDAR_READ_SCRIPT
    assert cmd[3:] == ["2026-07-05T10:00:00", "2026-07-05T11:00:00"]


def test_read_events_empty_stdout_returns_empty_list():
    events = cr.read_events("2026-07-05T10:00:00", "2026-07-05T11:00:00",
                            osascript=_fake_runner(""))
    assert events == []


def test_read_events_rejects_bad_bounds():
    with pytest.raises(ValueError):
        cr.read_events("not-a-date", "2026-07-05T11:00:00",
                       osascript=_fake_runner(""))


def test_find_conflicts_returns_colliding_events():
    stdout = _line("Cabinet", "2026-07-05T10:30:00",
                   "2026-07-05T11:30:00", "clash") + cr._RS
    hits = cr.find_conflicts(_dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0),
                             osascript=_fake_runner(stdout))
    assert [e["summary"] for e in hits] == ["clash"]


def test_script_is_read_only_no_mutation_verbs():
    # security invariant: the fixed script contains no calendar-mutating verb.
    src = cr.CALENDAR_READ_SCRIPT
    for verb in ("make new", "delete ", "save ", "move ", "add ", "duplicate ",
                 "set start date", "set end date", "set summary"):
        assert verb not in src, f"mutation verb {verb!r} present in read script"
    # Stronger than an allowlist: every `set <prop> of <obj>` may target ONLY the
    # local date variable `d` (parseIso/isoOf build a `current date`). A `set ...
    # of c` / `of (item ...)` / event would be a calendar mutation — forbidden.
    for m in re.finditer(r"set\s+\w+\s+of\s+(\w+)", src):
        assert m.group(1) == "d", (
            f"`set ... of {m.group(1)}` mutates a non-local object — not read-only")


def test_overlap_true_sub_minute():
    # Regression pin for the AS/Python bound-precision parity fix: a conflict
    # living entirely in the sub-minute gap MUST be caught by the authoritative
    # Python filter. Before the parseIso seconds fix the AS pre-cull could drop
    # exactly this (a missed double-book).
    events = [_ev("Cabinet", _dt(2026, 7, 5, 10, 0, 15), _dt(2026, 7, 5, 10, 0, 45))]
    hits = cr.overlaps(_dt(2026, 7, 5, 10, 0, 0), _dt(2026, 7, 5, 10, 0, 30), events)
    assert hits == events


def test_read_events_propagates_read_error_for_failclosed_wire():
    # The wire fails closed only if a FAILED read surfaces as an exception rather
    # than a silent empty list. Pin that read_events propagates CalendarReadError.
    def boom(cmd):
        raise cr.CalendarReadError("automation permission denied")

    with pytest.raises(cr.CalendarReadError):
        cr.read_events("2026-07-05T10:00:00", "2026-07-05T11:00:00", osascript=boom)


# --- event_window / conflicts_for_due (B2 block-window, parity with the write) --

def test_event_window_timed():
    start, end = cr.event_window("2026-07-06T14:00")
    assert start == _dt(2026, 7, 6, 14, 0)
    assert end == _dt(2026, 7, 6, 14, 30)     # 30-min block


def test_event_window_date_only_defaults_0900():
    # CALENDAR_EVENT_SCRIPT parseIso defaults a date-only due to 09:00 local.
    start, end = cr.event_window("2026-07-06")
    assert start == _dt(2026, 7, 6, 9, 0)
    assert end == _dt(2026, 7, 6, 9, 30)


def test_event_window_zeroes_seconds():
    # the write template zeroes seconds; the gather window must occupy the same span.
    start, end = cr.event_window("2026-07-06T14:00:45")
    assert start == _dt(2026, 7, 6, 14, 0) and end == _dt(2026, 7, 6, 14, 30)


def test_event_window_rejects_bad_due():
    for bad in ("", "not-a-date", "2026-13-40T14:00"):
        with pytest.raises(ValueError):
            cr.event_window(bad)


def test_conflicts_for_due_uses_block_window():
    # an existing event overlapping the 09:00–09:30 block of a DATE-ONLY due.
    stdout = _line("Home", "2026-07-06T09:15:00", "2026-07-06T09:45:00", "clash") + cr._RS
    hits = cr.conflicts_for_due("2026-07-06", osascript=_fake_runner(stdout))
    assert [e["summary"] for e in hits] == ["clash"]


def test_conflicts_for_due_adjacent_is_not_conflict():
    # existing ends exactly at the block start (09:00) → adjacency, no overlap.
    stdout = _line("Home", "2026-07-06T08:30:00", "2026-07-06T09:00:00", "before") + cr._RS
    hits = cr.conflicts_for_due("2026-07-06", osascript=_fake_runner(stdout))
    assert hits == []


def test_conflicts_for_due_propagates_read_error_failclosed():
    def boom(cmd):
        raise cr.CalendarReadError("permission denied")
    with pytest.raises(cr.CalendarReadError):
        cr.conflicts_for_due("2026-07-06T10:00", osascript=boom)


@pytest.mark.skipif(shutil.which("osascript") is None,
                    reason="osascript unavailable (non-macOS / CI)")
def test_applescript_parseiso_preserves_seconds_parity():
    # Exercise the SHIPPED parseIso+isoOf handlers (everything after the run
    # block) with a tiny driver, and assert AS keeps the :30 seconds so the AS
    # pre-cull and the Python authoritative filter parse a bound identically.
    handlers = cr.CALENDAR_READ_SCRIPT.split("end run\n", 1)[1]
    driver = ("on run argv\n"
              "return my isoOf(my parseIso(item 1 of argv))\n"
              "end run\n") + handlers
    bound = "2026-07-05T10:00:30"
    proc = subprocess.run(["osascript", "-e", driver, bound],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    as_iso = proc.stdout.strip()
    assert as_iso == "2026-07-05T10:00:30", f"AS dropped seconds: {as_iso!r}"
    assert cr._parse_iso(as_iso) == cr._parse_iso(bound)


@pytest.mark.skipif(shutil.which("osacompile") is None,
                    reason="osacompile unavailable (non-macOS / CI)")
def test_calendar_read_script_actually_compiles():
    """The generated AppleScript must COMPILE — the pure-Python tests mock
    osascript, so a syntax bug (e.g. the poison var 'sT', which AppleScript reads
    as a reserved ordinal token) would otherwise ship silently and only fail live.
    osacompile is compile-only: no Calendar access, no side effects."""
    import os
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".applescript", delete=False) as f:
        f.write(cr.CALENDAR_READ_SCRIPT)
        src = f.name
    try:
        p = subprocess.run(["osacompile", "-o", os.devnull, src],
                           capture_output=True, text=True, timeout=30)
        assert p.returncode == 0, f"CALENDAR_READ_SCRIPT does not compile:\n{p.stderr}"
    finally:
        os.unlink(src)
