"""Channel-flatline alarm — the detector and both of its delivery seams.

WHAT THESE ARMS ARE FOR. The failure being fixed is a SENSOR failure: a
captain-facing channel fell from ~146 cards/week to zero for seven days and no
part of the org said so. So the arms below are written to fail against
pre-change state in BOTH directions — a flatline fixture must produce the line
(it did not before), and each healthy / explained / degenerate fixture must
produce nothing (a detector that fires on those is the noise this alarm exists
to detect, and the Captain would stop reading it within a week).

Fully fixtured: every series is a list of dicts built here, ``now`` is frozen,
and ``gates`` are injected — no file read, no clock, no Redis, no network. The
two arms that DO touch the filesystem use tmp_path.
"""
from __future__ import annotations

import datetime as dt

from framework.frontdoor import card_flatline as cf
from framework.frontdoor import run_briefing, tell_digest as td

NOW = dt.datetime(2026, 7, 27, 19, 30, tzinfo=dt.timezone.utc)
LIVE = {"deliberate": False, "reasons": []}


def _row(date, cards, *, stamped=1000, acted=3, labels=2, **over):
    """One emission-series line, in the producer's real shape
    (cabinet/scripts/falsifier-report.py::compute_line)."""
    row = {"date": date, "proactive_cards_7d": cards, "acted_7d": acted,
           "approved_7d": 0, "reversal_rate_7d": None,
           "stamped_rows_total": stamped, "cells_accumulating": 4,
           "cells_graduated": 1,
           "labels_7d": {"verdict": labels, "outcome_resolved": 0},
           "memory_ingestion": None, "recall_drops": 0,
           "session_insert_failures": 0}
    row.update(over)
    return row


def _series(cards_by_date, **kw):
    """Series builder: [(date, cards), …] with stamped_rows_total advancing so
    the org reads ACTIVE unless an arm deliberately freezes it."""
    out = []
    for i, (date, cards) in enumerate(cards_by_date):
        out.append(_row(date, cards, stamped=1000 + i, **kw))
    return out


def _live_then_silent(days_silent):
    """The paid shape: a live week, then N consecutive zero days ending today."""
    rows = [("2026-07-2%d" % d, 20) for d in range(0, 4)]          # 20..23 live
    start = 24
    for i in range(days_silent):
        rows.append(("2026-07-%d" % (start + i), 0))
    return _series(rows)


# ---------------------------------------------------------------------------
# ARM 1 — the flatline fixture FIRES
# ---------------------------------------------------------------------------

def test_flatline_fixture_fires_on_the_crossing_day():
    # 20..23 carried cards; 24, 25, 26 are zero. now = the 26th's evening.
    series = _series([("2026-07-20", 20), ("2026-07-21", 14),
                      ("2026-07-22", 9), ("2026-07-23", 11),
                      ("2026-07-24", 0), ("2026-07-25", 0), ("2026-07-26", 0)])
    v = cf.evaluate(series, now=dt.datetime(2026, 7, 26, 19, 30,
                                            tzinfo=dt.timezone.utc), gates=LIVE)
    assert v["state"] == "flatline"
    assert v["announce"] is True
    assert v["silent_since"] == "2026-07-24"
    assert v["silent_hours"] == 48
    assert cf.render_line(v) == ("the proactive-card channel has been silent "
                                 "since 2026-07-24 — deliberate?")
    assert cf.probe_token(v).startswith("BREACH since=2026-07-24 hours=48")


def test_flatline_line_reaches_the_digest_loop_section():
    """The digest render arm: pre-change render_loop_readout parsed the series
    and rendered acted/reversal/cells only — proactive_cards_7d was read and
    dropped, which is precisely why seven zero days were invisible."""
    series = _series([("2026-07-23", 11), ("2026-07-24", 0),
                      ("2026-07-25", 0), ("2026-07-26", 0)])
    readout = {"kinds": {}, "undo": {}, "falsifier": series[-1],
               "series_len": len(series),
               "flatline": cf.evaluate(series,
                                       now=dt.datetime(2026, 7, 26, 19, 30,
                                                       tzinfo=dt.timezone.utc),
                                       gates=LIVE)}
    text = td.render_loop_readout(readout)
    assert "the proactive-card channel has been silent since 2026-07-24" in text
    assert "deliberate?" in text
    # It LEADS the section: a dead channel outranks the rates of a live one.
    assert text.splitlines()[1].strip().startswith("· ⚠️")


def test_flatline_line_reaches_the_briefing_card_headline(monkeypatch):
    """Card mode archives the composed body instead of sending it, so the
    headline is the ONLY thing the Captain sees. Pre-change the headline was
    counts-only and this arm fails."""
    monkeypatch.setattr(td, "flatline_notice",
                        lambda **kw: "the proactive-card channel has been "
                                     "silent since 2026-07-24 — deliberate?")
    head = run_briefing._plain_headline({"drained": 2, "sent": True},
                                        {"acted": 1})
    assert "silent since 2026-07-24 — deliberate?" in head
    # The card renderer caps the headline at 300 chars and strips the binder's
    # marker char; the question must survive both.
    from framework.comms.surface import briefing_card
    kwargs = briefing_card.render(head, {"pending_captain_items": 0},
                                  now=NOW, cfg={})
    assert "silent since 2026-07-24 — deliberate?" in kwargs["situation"]
    assert "·" not in kwargs["situation"]


# ---------------------------------------------------------------------------
# ARM 2 — the healthy fixture is SILENT
# ---------------------------------------------------------------------------

def test_healthy_fixture_is_silent():
    series = _series([("2026-07-24", 20), ("2026-07-25", 0),
                      ("2026-07-26", 18)])
    v = cf.evaluate(series, now=dt.datetime(2026, 7, 26, 19, 30,
                                            tzinfo=dt.timezone.utc), gates=LIVE)
    assert v["state"] == "active"
    assert v["announce"] is False
    assert cf.render_line(v) == ""
    assert cf.probe_token(v) == "OK cards_7d=18 date=2026-07-26"
    assert td.render_loop_readout({"kinds": {}, "undo": {}, "falsifier": None,
                                   "flatline": v}) == ""


def test_a_channel_that_was_never_active_is_not_an_alarm():
    """The fresh-hatch shape: zero from birth. Nothing went silent, so nothing
    is asked — otherwise every new cabinet would open with a false alarm."""
    series = _series([("2026-07-24", 0), ("2026-07-25", 0), ("2026-07-26", 0)])
    v = cf.evaluate(series, now=dt.datetime(2026, 7, 26, 19, 30,
                                            tzinfo=dt.timezone.utc), gates=LIVE)
    assert v["state"] == "never-active"
    assert v["announce"] is False
    assert cf.probe_token(v).startswith("NEVERACTIVE")


def test_a_quiet_org_is_a_fleet_finding_not_a_channel_finding():
    """No cards AND no acts, no new stamped rows, no labels: the fleet stopped.
    Blaming the card channel would point the Captain at the wrong organ."""
    rows = [_row("2026-07-23", 11, stamped=1000, acted=4, labels=2),
            _row("2026-07-24", 0, stamped=1000, acted=0, labels=0),
            _row("2026-07-25", 0, stamped=1000, acted=0, labels=0),
            _row("2026-07-26", 0, stamped=1000, acted=0, labels=0)]
    v = cf.evaluate(rows, now=dt.datetime(2026, 7, 26, 19, 30,
                                          tzinfo=dt.timezone.utc), gates=LIVE)
    assert v["state"] == "quiet"
    assert v["announce"] is False
    assert cf.probe_token(v).startswith("QUIET since=2026-07-24")


def test_under_the_bar_is_watched_not_alarmed():
    series = _series([("2026-07-24", 11), ("2026-07-25", 0), ("2026-07-26", 0)])
    v = cf.evaluate(series, now=dt.datetime(2026, 7, 26, 19, 30,
                                            tzinfo=dt.timezone.utc), gates=LIVE)
    assert v["state"] == "silent" and v["silent_hours"] == 24
    assert v["announce"] is False and cf.render_line(v) == ""


def test_an_aged_crossing_row_is_no_longer_delivered():
    """The delivery bound. If the series producer dies right after a crossing
    row, the question ages out instead of being pinned on the Captain's screen
    every briefing forever — the doctor probe keeps the standing signal."""
    series = _series([("2026-07-23", 11), ("2026-07-24", 0),
                      ("2026-07-25", 0), ("2026-07-26", 0)])
    late = dt.datetime(2026, 7, 28, 6, 0, tzinfo=dt.timezone.utc)   # ~54h
    v = cf.evaluate(series, now=late, gates=LIVE)
    assert v["state"] == "flatline" and v["crossing"] is True
    assert v["announce"] is False and cf.render_line(v) == ""
    assert cf.probe_token(v).startswith("BREACH")


# ---------------------------------------------------------------------------
# ARM 3 — a DELIBERATE disable is silent (and labelled, never alarmed)
# ---------------------------------------------------------------------------

def test_deliberate_disable_is_silent_and_labelled():
    series = _live_then_silent(4)
    gates = {"deliberate": True,
             "reasons": ["the action-lane fleet row is disabled in "
                         "cabinet/services.yml"]}
    v = cf.evaluate(series, now=NOW, gates=gates)
    assert v["state"] == "deliberate"
    assert v["announce"] is False
    assert cf.render_line(v) == ""
    token = cf.probe_token(v)
    assert token.startswith("NOSYNC") and "action-lane fleet row is disabled" in token
    assert td.render_loop_readout({"kinds": {}, "undo": {}, "falsifier": None,
                                   "flatline": v}) == ""


def test_read_gates_sees_an_absence_disable_annotation(tmp_path):
    """ABSENCE-DISABLE rows annotate INLINE. A parser that matches before
    stripping the trailing comment reads a parked service as live — the exact
    bug that once made parked services page every sweep."""
    (tmp_path / "cabinet").mkdir()
    (tmp_path / "cabinet" / "services.yml").write_text(
        "services:\n"
        "  - name: something-else\n"
        "    kind: cron\n"
        "  - name: action-lane\n"
        "    kind: daemon\n"
        "    disabled: true   # ABSENCE-DISABLE (cos 2026-07-27): parked\n"
        "    disabled_reason: parked on purpose\n", encoding="utf-8")
    gates = cf.read_gates(root=tmp_path)
    assert gates["deliberate"] is True
    assert any("action-lane" in r for r in gates["reasons"])


def test_read_gates_is_quiet_when_the_producer_row_is_live(tmp_path):
    (tmp_path / "cabinet").mkdir()
    (tmp_path / "cabinet" / "services.yml").write_text(
        "services:\n"
        "  - name: action-lane\n"
        "    kind: daemon\n"
        "    schedule: { interval_s: 1800 }\n", encoding="utf-8")
    assert cf.read_gates(root=tmp_path) == {"deliberate": False, "reasons": []}


def test_read_gates_never_raises_on_a_missing_manifest(tmp_path):
    assert cf.read_gates(root=tmp_path / "nope")["deliberate"] is False


# ---------------------------------------------------------------------------
# ARM 4 — recovery RESETS the cooldown (and the alarm never re-fires without it)
# ---------------------------------------------------------------------------

def test_the_question_is_asked_once_per_episode():
    """Walk the series day by day, exactly as the daily producer builds it, and
    count how often the Captain would be asked. Silent → silent → silent asks
    ONCE; the standing state is still true, but the question has been put."""
    days = [("2026-07-20", 20), ("2026-07-21", 14),
            ("2026-07-22", 0), ("2026-07-23", 0), ("2026-07-24", 0),
            ("2026-07-25", 0), ("2026-07-26", 0)]
    asked = []
    for i in range(1, len(days) + 1):
        series = _series(days[:i])
        when = dt.datetime.fromisoformat(days[i - 1][0]).replace(
            hour=19, minute=30, tzinfo=dt.timezone.utc)
        if cf.evaluate(series, now=when, gates=LIVE)["announce"]:
            asked.append(days[i - 1][0])
    assert asked == ["2026-07-24"]        # the crossing day, and only that day


def test_recovery_resets_the_cooldown():
    """silent → ACTIVE → silent is two episodes and asks twice. This is the
    whole cooldown mechanism: there is no stored 'already announced' flag to
    rot, because recovery is what clears it."""
    days = [("2026-07-10", 20),
            ("2026-07-11", 0), ("2026-07-12", 0), ("2026-07-13", 0),
            ("2026-07-14", 17),                       # <- recovery
            ("2026-07-15", 0), ("2026-07-16", 0), ("2026-07-17", 0)]
    asked = []
    for i in range(1, len(days) + 1):
        series = _series(days[:i])
        when = dt.datetime.fromisoformat(days[i - 1][0]).replace(
            hour=19, minute=30, tzinfo=dt.timezone.utc)
        v = cf.evaluate(series, now=when, gates=LIVE)
        if v["announce"]:
            asked.append((days[i - 1][0], v["silent_since"]))
    assert asked == [("2026-07-13", "2026-07-11"), ("2026-07-17", "2026-07-15")]


def test_a_missed_producer_day_still_crosses_exactly_once():
    """The bar is 48 HOURS, not two rows: a box that slept through the 25th
    must still cross once, and must not cross twice on the way past."""
    days = [("2026-07-20", 20),
            ("2026-07-24", 0), ("2026-07-26", 0), ("2026-07-27", 0)]
    asked = []
    for i in range(1, len(days) + 1):
        series = _series(days[:i])
        when = dt.datetime.fromisoformat(days[i - 1][0]).replace(
            hour=19, minute=30, tzinfo=dt.timezone.utc)
        if cf.evaluate(series, now=when, gates=LIVE)["announce"]:
            asked.append(days[i - 1][0])
    assert asked == ["2026-07-26"]


# ---------------------------------------------------------------------------
# ARM 5 — the degenerate end: measured absence, not a crash and not an alarm
# ---------------------------------------------------------------------------

def test_no_series_file_is_measured_absence():
    assert cf.evaluate([], now=NOW, gates=LIVE) == {
        "state": "no-series", "announce": False, "silent_since": None,
        "silent_hours": None, "latest_date": None, "latest_cards": None,
        "reasons": []}
    assert cf.probe_token(cf.evaluate([], now=NOW, gates=LIVE)) == "NOSERIES"


def test_missing_series_file_never_raises_and_never_alarms(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_FALSIFIER_SERIES", str(tmp_path / "absent.jsonl"))
    assert cf.series_path() == tmp_path / "absent.jsonl"
    assert td.flatline_notice() == ""
    assert run_briefing._flatline_notice() == ""


def test_the_root_conftest_fences_the_series_read():
    """Class-11: a live deployment's real emission history must not be able to
    decide whether this suite's arms pass — and the alarm must not be able to
    judge it from inside a test run. The fence points the resolver at a
    sandbox path that is never created."""
    import os
    assert os.environ.get("CABINET_FALSIFIER_SERIES")
    assert not cf.series_path().exists()


def test_degenerate_and_garbage_inputs_never_raise():
    for bad in (None, [], [None], ["x"], [{}], [{"date": "nope"}],
                [{"date": "2026-07-26"}], {"date": "2026-07-26"}):
        v = cf.evaluate(bad, now=NOW, gates=LIVE)
        assert v["announce"] is False
        assert isinstance(cf.probe_token(v), str)
    assert cf.render_line(None) == "" and cf.render_line({}) == ""
    assert cf.probe_token(None).startswith("ERROR")


def test_an_unmeasured_card_count_is_not_a_zero():
    """null is not 0. Conflating them is how a detector invents a silence that
    never happened — the same law the producer states for memory_ingestion."""
    series = [_row("2026-07-24", 11), _row("2026-07-25", None),
              _row("2026-07-26", None)]
    v = cf.evaluate(series, now=dt.datetime(2026, 7, 26, 19, 30,
                                            tzinfo=dt.timezone.utc), gates=LIVE)
    assert v["state"] == "unmeasured"
    assert v["announce"] is False
    # …and an unmeasured row BREAKS a run rather than extending it.
    series = [_row("2026-07-20", 11), _row("2026-07-21", 0),
              _row("2026-07-22", None), _row("2026-07-23", 0),
              _row("2026-07-24", 0)]
    v = cf.evaluate(series, now=dt.datetime(2026, 7, 24, 19, 30,
                                            tzinfo=dt.timezone.utc), gates=LIVE)
    assert v["silent_since"] == "2026-07-23"


def test_a_stale_series_yields_no_verdict_at_all():
    series = _live_then_silent(4)
    v = cf.evaluate(series, now=dt.datetime(2026, 8, 10, tzinfo=dt.timezone.utc),
                    gates=LIVE)
    assert v["state"] == "stale"
    assert v["announce"] is False
    assert cf.probe_token(v).startswith("STALE age_days=")


# ---------------------------------------------------------------------------
# wiring: the alarm may never cost the surface it rides on
# ---------------------------------------------------------------------------

def test_gather_loop_readout_carries_the_verdict_and_never_raises(tmp_path):
    p = tmp_path / "falsifier-series.jsonl"
    p.write_text("".join(
        __import__("json").dumps(r) + "\n"
        for r in _series([("2026-07-23", 11), ("2026-07-24", 0),
                          ("2026-07-25", 0), ("2026-07-26", 0)])),
        encoding="utf-8")
    out = td.gather_loop_readout(now="2026-07-26T19:30:00Z", ledger=[],
                                 series_path=p)
    assert isinstance(out["flatline"], dict)
    assert out["flatline"]["silent_since"] == "2026-07-24"
    # and a broken series is an absent verdict, never an exception
    out = td.gather_loop_readout(now="not-a-timestamp", ledger=[],
                                 series_path=tmp_path / "missing.jsonl")
    assert out["flatline"]["state"] == "no-series"


def test_a_broken_alarm_costs_the_captain_a_question_not_the_briefing(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("detector exploded")
    monkeypatch.setattr(cf, "evaluate", _boom)
    monkeypatch.setattr(cf, "render_line", _boom)
    assert td.flatline_notice() == ""
    assert run_briefing._flatline_notice() == ""
    head = run_briefing._plain_headline({"drained": 1, "sent": True}, None)
    assert head.startswith("Gathered 1 update")
    out = td.gather_loop_readout(now="2026-07-26T19:30:00Z", ledger=[])
    assert out["flatline"] is None
    assert any(e.startswith("card_flatline:") for e in out["errors"])
    assert td.render_loop_readout({"kinds": {}, "undo": {}, "falsifier": None,
                                   "flatline": {"announce": True,
                                                "silent_since": "2026-07-24"}}) == ""


def test_the_wording_lives_in_exactly_one_place():
    """Two surfaces render this question. If either restates it, the Captain
    gets two different accounts of the same silence."""
    v = cf.evaluate(_series([("2026-07-23", 11), ("2026-07-24", 0),
                             ("2026-07-25", 0), ("2026-07-26", 0)]),
                    now=dt.datetime(2026, 7, 26, 19, 30, tzinfo=dt.timezone.utc),
                    gates=LIVE)
    line = cf.render_line(v)
    assert line == cf.LINE_TEMPLATE.format(date="2026-07-24")
    digest = td.render_loop_readout({"kinds": {}, "undo": {}, "falsifier": None,
                                     "flatline": v})
    assert line in digest
    src = (__import__("pathlib").Path(td.__file__).read_text(encoding="utf-8")
           + __import__("pathlib").Path(run_briefing.__file__).read_text(
               encoding="utf-8"))
    assert "has been silent since" not in src


# ---------------------------------------------------------------------------
# The Captain's absence is a reason not to bother HIM, never a reason to stop
# watching the fleet. Until 2026-08-26 one flag did both, so a failure that
# began during an absence was only discovered on his return -- the absence
# being precisely the worst moment to stop looking.
# ---------------------------------------------------------------------------

def _away(monkeypatch):
    import framework.env as env
    monkeypatch.setattr(env, "captain_availability",
                        lambda: {"mode": "away"}, raising=False)


def test_away_still_spares_the_captain_the_question(tmp_path, monkeypatch):
    _away(monkeypatch)
    got = cf.read_gates(root=tmp_path)
    assert got["deliberate"] is True
    assert any("away" in r for r in got["reasons"])


def test_away_does_not_silence_the_fleet_watch(tmp_path, monkeypatch):
    # THE arm. Same world, same flag, and the standing check keeps looking.
    _away(monkeypatch)
    got = cf.read_gates(root=tmp_path,
                                   audience=cf.AUDIENCE_FLEET)
    assert got["deliberate"] is False


def test_the_away_reason_is_still_reported_to_the_fleet(tmp_path, monkeypatch):
    # It stops voting; it does not disappear. Hiding a fact to change a verdict
    # is how a gate becomes unauditable.
    _away(monkeypatch)
    got = cf.read_gates(root=tmp_path,
                                   audience=cf.AUDIENCE_FLEET)
    assert any("away" in r for r in got["reasons"])


def test_a_parked_producer_still_silences_both(tmp_path, monkeypatch):
    _away(monkeypatch)
    manifest = tmp_path.joinpath(*cf._SERVICES_REL)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("services:\n  - name: action-lane\n    disabled: true\n",
                        encoding="utf-8")
    for audience in (cf.AUDIENCE_CAPTAIN, cf.AUDIENCE_FLEET):
        got = cf.read_gates(root=tmp_path, audience=audience)
        assert got["deliberate"] is True, audience


def test_the_default_audience_is_unchanged(tmp_path, monkeypatch):
    # Every existing caller passes no audience and must behave exactly as it
    # did. The return SHAPE is unchanged too -- no new key -- because the
    # existing assertions compare this dict exactly.
    _away(monkeypatch)
    assert cf.read_gates(root=tmp_path) == \
        cf.read_gates(root=tmp_path,
                                 audience=cf.AUDIENCE_CAPTAIN)
    assert set(cf.read_gates(root=tmp_path)) == {"deliberate", "reasons"}
