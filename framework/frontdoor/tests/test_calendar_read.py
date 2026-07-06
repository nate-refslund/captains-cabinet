"""Unit tests for the read-only calendar overlap detector
(framework/frontdoor/calendar_read).

Pure Python — NO real helper spawn in the unit path. The signed EventKit read
helper is a separate seam; here we exercise the JSON parse + half-open interval
logic directly, plus ``read_events`` / ``find_conflicts`` through an INJECTED
fake runner that returns canned JSON stdout (never spawns a subprocess).

The reader was rebuilt onto a SIGNED read-only EventKit helper (2026-07-05):
EventKit from a plain script is blind to the Captain's iCloud calendars
(write-only access), and an AppleScript bulk `whose` scan is O(calendar size)
(~70s across the real calendars). A signed helper holding EKAuthorization
fullAccess reads ALL calendars fast and complete. The helper emits a JSON array
of ``{calendar,start,end,summary}``; the authoritative half-open overlap filter
still runs in Python (this file).
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
from datetime import datetime

import pytest

from framework.frontdoor import calendar_read as cr


def _dt(y, mo, d, h=0, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s)


def _ev(cal, start, end, summary="ev"):
    """Build an event dict in the shape read_events produces."""
    return {"calendar": cal, "summary": summary, "start": start, "end": end,
            "start_iso": start.isoformat(), "end_iso": end.isoformat()}


# --- overlaps: the half-open interval core (backend-agnostic) ------------------

def test_overlap_true_partial():
    events = [_ev("Home", _dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0))]
    hits = cr.overlaps(_dt(2026, 7, 5, 10, 30), _dt(2026, 7, 5, 11, 30), events)
    assert hits == events


def test_no_overlap_disjoint():
    events = [_ev("Home", _dt(2026, 7, 5, 9, 0), _dt(2026, 7, 5, 10, 0))]
    hits = cr.overlaps(_dt(2026, 7, 5, 11, 0), _dt(2026, 7, 5, 12, 0), events)
    assert hits == []


def test_exact_adjacency_does_not_overlap_after():
    # existing ends 10:00, candidate starts 10:00 → touching, NOT overlapping.
    events = [_ev("Home", _dt(2026, 7, 5, 9, 0), _dt(2026, 7, 5, 10, 0))]
    hits = cr.overlaps(_dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0), events)
    assert hits == []


def test_exact_adjacency_does_not_overlap_before():
    # candidate ends 10:00, existing starts 10:00 → touching, NOT overlapping.
    events = [_ev("Home", _dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0))]
    hits = cr.overlaps(_dt(2026, 7, 5, 9, 0), _dt(2026, 7, 5, 10, 0), events)
    assert hits == []


def test_containment_event_inside_candidate():
    events = [_ev("Home", _dt(2026, 7, 5, 10, 15), _dt(2026, 7, 5, 10, 45))]
    hits = cr.overlaps(_dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0), events)
    assert hits == events


def test_containment_candidate_inside_event():
    events = [_ev("Home", _dt(2026, 7, 5, 9, 0), _dt(2026, 7, 5, 12, 0))]
    hits = cr.overlaps(_dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0), events)
    assert hits == events


def test_multi_event_union_across_calendars():
    a = _ev("Home", _dt(2026, 7, 5, 10, 30), _dt(2026, 7, 5, 11, 0), "a")
    b = _ev("Work", _dt(2026, 7, 5, 9, 0), _dt(2026, 7, 5, 10, 0), "b")   # miss
    c = _ev("Calendar", _dt(2026, 7, 5, 10, 45), _dt(2026, 7, 5, 11, 30), "c")
    hits = cr.overlaps(_dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0), [a, b, c])
    assert hits == [a, c]  # union across calendars, adjacency-miss excluded


def test_empty_event_list():
    assert cr.overlaps(_dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0), []) == []


def test_overlaps_accepts_iso_strings():
    events = [_ev("Home", _dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0))]
    hits = cr.overlaps("2026-07-05T10:30:00", "2026-07-05T11:30:00Z", events)
    assert hits == events


def test_overlaps_skips_events_missing_parsed_bounds():
    good = _ev("Home", _dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0))
    bad = {"calendar": "X", "summary": "no dates", "start": None, "end": None}
    hits = cr.overlaps(_dt(2026, 7, 5, 10, 30), _dt(2026, 7, 5, 11, 30),
                       [bad, good])
    assert hits == [good]


# --- defensive JSON parsing (no subprocess) -----------------------------------

def _rec(cal, s_iso, e_iso, title):
    return {"calendar": cal, "start": s_iso, "end": e_iso, "summary": title}


def test_parse_events_empty_stdout_is_empty_list():
    assert cr._parse_events("") == []
    assert cr._parse_events("   \n  ") == []
    assert cr._parse_events("[]") == []


def test_parse_events_well_formed_records():
    stdout = json.dumps([
        _rec("Home", "2026-07-05T10:00:00", "2026-07-05T11:00:00", "standup"),
        _rec("Work", "2026-07-05T13:00:00", "2026-07-05T14:00:00", "review"),
    ])
    events = cr._parse_events(stdout)
    assert len(events) == 2
    assert events[0]["calendar"] == "Home"
    assert events[0]["summary"] == "standup"
    assert events[0]["start"] == _dt(2026, 7, 5, 10, 0)
    assert events[1]["end"] == _dt(2026, 7, 5, 14, 0)


def test_parse_events_skips_malformed_records():
    stdout = json.dumps([
        {"calendar": "Home"},                                        # missing dates
        _rec("Home", "not-a-date", "2026-07-05T11:00:00", "x"),      # bad start
        "not-an-object",                                             # not a dict
        _rec("Home", "2026-07-05T10:00:00", "2026-07-05T11:00:00", "ok"),
    ])
    events = cr._parse_events(stdout)
    assert len(events) == 1
    assert events[0]["summary"] == "ok"


def test_parse_events_garbage_json_raises_failclosed():
    # Non-empty stdout that is not a JSON array is an ANOMALY on a successful read
    # (the pristine helper always prints at least '[]') → must RAISE, never be
    # swallowed to [] (which the wire would read as 'no conflict → safe to write').
    with pytest.raises(cr.CalendarReadError):
        cr._parse_events("this is not json")
    with pytest.raises(cr.CalendarReadError):
        cr._parse_events("{not: valid}")


def test_parse_events_non_array_json_raises_failclosed():
    # Valid JSON that is not an array (e.g. an error object, or the old diagnostic
    # dump) must also fail closed, not read as zero events.
    with pytest.raises(cr.CalendarReadError):
        cr._parse_events('{"error": "denied"}')
    with pytest.raises(cr.CalendarReadError):
        cr._parse_events('42')


def test_parse_events_missing_summary_defaults_empty():
    stdout = json.dumps([{"calendar": "Home", "start": "2026-07-05T10:00:00",
                          "end": "2026-07-05T11:00:00"}])
    events = cr._parse_events(stdout)
    assert len(events) == 1
    assert events[0]["summary"] == ""


# --- read_events / find_conflicts through an injected fake runner --------------

def _fake_runner(stdout):
    calls = []

    def run(cmd):
        calls.append(cmd)
        return stdout

    run.calls = calls
    return run


def _json_out(records):
    return json.dumps(records)


def test_read_events_filters_window_and_invokes_helper_read_with_bounds():
    stdout = _json_out([
        _rec("Home", "2026-07-05T10:30:00", "2026-07-05T11:00:00", "in"),
        _rec("Home", "2026-07-05T08:00:00", "2026-07-05T09:00:00", "before"),
    ])
    runner = _fake_runner(stdout)
    events = cr.read_events("2026-07-05T10:00:00", "2026-07-05T11:00:00",
                            osascript=runner)
    assert [e["summary"] for e in events] == ["in"]  # 'before' filtered out
    # The command is the signed helper's READ subcommand + the two ISO bounds as
    # argv (never interpolated). cmd[0] is the resolved helper path.
    cmd = runner.calls[0]
    assert cmd[1] == "read", "reader must only ever invoke the read subcommand"
    assert cmd[2:] == ["2026-07-05T10:00:00", "2026-07-05T11:00:00"]


def test_reader_never_invokes_a_mutating_subcommand():
    # Read-only invariant at the Python layer: whatever else changes, the reader
    # may ONLY ever ask the helper to `read` — never create/delete/write.
    runner = _fake_runner("[]")
    cr.read_events("2026-07-05T10:00:00", "2026-07-05T11:00:00", osascript=runner)
    for cmd in runner.calls:
        assert cmd[1] == "read"
        for mutate in ("create", "delete", "write", "save", "remove", "update"):
            assert mutate not in cmd, f"reader issued a mutating subcommand: {cmd!r}"


def test_read_events_empty_stdout_returns_empty_list():
    events = cr.read_events("2026-07-05T10:00:00", "2026-07-05T11:00:00",
                            osascript=_fake_runner(""))
    assert events == []


def test_read_events_rejects_bad_bounds():
    with pytest.raises(ValueError):
        cr.read_events("not-a-date", "2026-07-05T11:00:00",
                       osascript=_fake_runner(""))


def test_find_conflicts_returns_colliding_events():
    stdout = _json_out([_rec("Home", "2026-07-05T10:30:00",
                             "2026-07-05T11:30:00", "clash")])
    hits = cr.find_conflicts(_dt(2026, 7, 5, 10, 0), _dt(2026, 7, 5, 11, 0),
                             osascript=_fake_runner(stdout))
    assert [e["summary"] for e in hits] == ["clash"]


def test_read_events_propagates_read_error_for_failclosed_wire():
    # The wire fails closed only if a FAILED read surfaces as an exception rather
    # than a silent empty list. Pin that read_events propagates CalendarReadError.
    def boom(cmd):
        raise cr.CalendarReadError("automation permission denied")

    with pytest.raises(cr.CalendarReadError):
        cr.read_events("2026-07-05T10:00:00", "2026-07-05T11:00:00", osascript=boom)


def test_read_events_normalizes_injected_runner_failures_to_failclosed():
    # The germline caller injects its OWN runner (a bare subprocess.run) that
    # raises RAW errors, not CalendarReadError: FileNotFoundError on a missing
    # helper (the DEFAULT state — the binary is gitignored/built on demand),
    # TimeoutExpired on a headless TCC hang, RuntimeError on a non-zero exit. All
    # must normalize to CalendarReadError so the wire fails CLOSED by construction.
    import subprocess as _sp
    for exc in (FileNotFoundError("no such helper"),
                _sp.TimeoutExpired(cmd="cabinet-calread", timeout=30),
                RuntimeError("osascript exited 1")):
        def boom(cmd, _e=exc):
            raise _e
        with pytest.raises(cr.CalendarReadError):
            cr.read_events("2026-07-05T10:00:00", "2026-07-05T11:00:00", osascript=boom)


# --- helper-path resolution + fail-closed (no real binary) --------------------

def test_helper_path_prefers_env(monkeypatch):
    monkeypatch.setenv("CABINET_CAL_HELPER", "/tmp/some/cabinet-calread")
    assert cr._helper_path() == "/tmp/some/cabinet-calread"


def test_helper_path_default_is_repo_bin_never_instance(monkeypatch):
    monkeypatch.delenv("CABINET_CAL_HELPER", raising=False)
    monkeypatch.delenv("CABINET_ROOT", raising=False)
    p = cr._helper_path()
    assert p.endswith("/bin/cabinet-calread")
    # clean-room / layer-separation: framework must never resolve into instance/.
    assert "/instance/" not in p


def test_default_runner_fail_closed_when_helper_absent(monkeypatch):
    # With NO injected runner, a missing/non-executable helper must raise
    # CalendarReadError (fail-closed), not return [] (which would read as
    # 'no conflict' → double-book).
    monkeypatch.setenv("CABINET_CAL_HELPER", "/nonexistent/cabinet-calread")
    with pytest.raises(cr.CalendarReadError):
        cr.read_events("2026-07-05T10:00:00", "2026-07-05T11:00:00")


def test_default_runner_raises_on_nonzero_exit(monkeypatch):
    # A helper that exits non-zero (permission denied / crash) must surface as
    # CalendarReadError through the default runner, never a silent empty read.
    script = tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False)
    script.write("#!/bin/sh\necho 'boom' >&2\nexit 3\n")
    script.close()
    os.chmod(script.name, os.stat(script.name).st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CABINET_CAL_HELPER", script.name)
    try:
        with pytest.raises(cr.CalendarReadError):
            cr.read_events("2026-07-05T10:00:00", "2026-07-05T11:00:00")
    finally:
        os.unlink(script.name)


def test_default_runner_reads_real_helper_stdout(monkeypatch):
    # Drive the DEFAULT runner (real subprocess) against a stub helper that
    # echoes a JSON array — proves the subprocess plumbing + JSON parse without
    # needing the signed EventKit binary or calendar access.
    stub = tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False)
    stub.write('#!/bin/sh\n'
               'echo \'[{"calendar":"Home","start":"2026-07-05T10:30:00",'
               '"end":"2026-07-05T11:00:00","summary":"stub"}]\'\n')
    stub.close()
    os.chmod(stub.name, os.stat(stub.name).st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CABINET_CAL_HELPER", stub.name)
    try:
        events = cr.read_events("2026-07-05T10:00:00", "2026-07-05T11:00:00")
        assert [e["summary"] for e in events] == ["stub"]
    finally:
        os.unlink(stub.name)


# --- calendar exclude list (CABINET_CAL_EXCLUDE) ------------------------------

def test_exclude_drops_named_calendar(monkeypatch):
    # A partner's shared work calendar the Captain can SEE but does not own must
    # not count as a conflict on the Captain's time.
    monkeypatch.setenv("CABINET_CAL_EXCLUDE", "Solveig's arbejde - Dyrenes Beskyttelse")
    stdout = _json_out([
        _rec("Home", "2026-07-06T09:15:00", "2026-07-06T09:45:00", "mine"),
        _rec("Solveig's arbejde - Dyrenes Beskyttelse",
             "2026-07-06T09:15:00", "2026-07-06T09:45:00", "hers"),
    ])
    hits = cr.read_events("2026-07-06T09:00:00", "2026-07-06T10:00:00",
                          osascript=_fake_runner(stdout))
    assert [e["summary"] for e in hits] == ["mine"]


def test_exclude_unset_includes_all_calendars(monkeypatch):
    monkeypatch.delenv("CABINET_CAL_EXCLUDE", raising=False)
    stdout = _json_out([
        _rec("Home", "2026-07-06T09:15:00", "2026-07-06T09:45:00", "mine"),
        _rec("Solveig's arbejde - Dyrenes Beskyttelse",
             "2026-07-06T09:15:00", "2026-07-06T09:45:00", "hers"),
    ])
    hits = cr.read_events("2026-07-06T09:00:00", "2026-07-06T10:00:00",
                          osascript=_fake_runner(stdout))
    assert len(hits) == 2  # default: ALL calendars count (safe for a conflict guard)


def test_exclude_multiple_case_and_space_insensitive(monkeypatch):
    monkeypatch.setenv("CABINET_CAL_EXCLUDE", "  work ,  FAMILY  ")
    stdout = _json_out([
        _rec("Home", "2026-07-06T09:15:00", "2026-07-06T09:45:00", "keep"),
        _rec("Work", "2026-07-06T09:15:00", "2026-07-06T09:45:00", "drop1"),
        _rec("Family", "2026-07-06T09:15:00", "2026-07-06T09:45:00", "drop2"),
    ])
    hits = cr.read_events("2026-07-06T09:00:00", "2026-07-06T10:00:00",
                          osascript=_fake_runner(stdout))
    assert [e["summary"] for e in hits] == ["keep"]


def test_exclude_typo_does_not_over_exclude(monkeypatch):
    # A name that matches nothing excludes nothing — never silently drops a real
    # calendar; fail-safe toward INCLUDING conflicts.
    monkeypatch.setenv("CABINET_CAL_EXCLUDE", "Nonexistent Cal")
    stdout = _json_out([_rec("Home", "2026-07-06T09:15:00", "2026-07-06T09:45:00", "mine")])
    hits = cr.read_events("2026-07-06T09:00:00", "2026-07-06T10:00:00",
                          osascript=_fake_runner(stdout))
    assert [e["summary"] for e in hits] == ["mine"]


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
    stdout = _json_out([_rec("Home", "2026-07-06T09:15:00",
                             "2026-07-06T09:45:00", "clash")])
    hits = cr.conflicts_for_due("2026-07-06", osascript=_fake_runner(stdout))
    assert [e["summary"] for e in hits] == ["clash"]


def test_conflicts_for_due_adjacent_is_not_conflict():
    # existing ends exactly at the block start (09:00) → adjacency, no overlap.
    # (EventKit's predicate may include a boundary-touch; the Python half-open
    # filter is authoritative and excludes it.)
    stdout = _json_out([_rec("Home", "2026-07-06T08:30:00",
                             "2026-07-06T09:00:00", "before")])
    hits = cr.conflicts_for_due("2026-07-06", osascript=_fake_runner(stdout))
    assert hits == []


def test_conflicts_for_due_propagates_read_error_failclosed():
    def boom(cmd):
        raise cr.CalendarReadError("permission denied")
    with pytest.raises(cr.CalendarReadError):
        cr.conflicts_for_due("2026-07-06T10:00", osascript=boom)


# --- live integration seam (skipped unless the signed helper is present) -------

@pytest.mark.skipif(not os.environ.get("CABINET_CAL_HELPER")
                    or not os.access(os.environ.get("CABINET_CAL_HELPER", ""), os.X_OK),
                    reason="signed EventKit helper not present (CABINET_CAL_HELPER unset / non-mac / CI)")
def test_live_helper_returns_valid_json_array():
    """Smoke the REAL signed helper: `read <start> <end>` must exit 0 and print a
    JSON array (possibly empty). Correctness of the calendar view is proven by
    the granted round-trip, not here — this only pins the CLI/JSON contract so a
    helper regression fails a test rather than shipping silently (the mocked-only
    root cause this whole rebuild fixes)."""
    helper = os.environ["CABINET_CAL_HELPER"]
    p = subprocess.run([helper, "read", "2026-07-06T00:00:00", "2026-07-06T00:30:00"],
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, f"helper read failed: {p.stderr}"
    parsed = json.loads(p.stdout)
    assert isinstance(parsed, list)
