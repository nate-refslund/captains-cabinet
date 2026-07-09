"""W10d — calendar event source / first due_event_triggers consumer.

All seams injected (events / enqueue / registry / state) — no EventKit, no
TCC, no Redis. Pins: upcoming-event intake with (uid,start) dedup,
calendar:<needle> on-event matching (uid exact, title substring), one-shot
mark_fired through the registry contract, fail-quiet calendar read, state
pruning, and the services.yml row.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
import yaml

from framework.triggers import calendar_source as cs
from framework.triggers import registry as reg

NOW = dt.datetime(2026, 7, 9, 8, 0, tzinfo=dt.timezone.utc)


@pytest.fixture()
def state_file(tmp_path):
    return tmp_path / "calendar-intake.json"


@pytest.fixture()
def triggers_file(tmp_path, monkeypatch):
    f = tmp_path / "triggers.json"
    monkeypatch.setenv("CABINET_TRIGGERS_FILE", str(f))
    return f


def _event(uid="E1", title="PolAds scrum", start="2026-07-09T09:00:00Z"):
    return {"uid": uid, "title": title, "start": start,
            "end": "2026-07-09T09:30:00Z", "calendar": "Work"}


def _tick(events, state_file, enqueued, registry=reg, now=NOW):
    return cs.tick(now=now,
                   read_events_fn=lambda s, e: events,
                   enqueue_fn=lambda item: enqueued.append(item) or "1-0",
                   registry=registry,
                   state_file=state_file)


class TestCalendarToIntake:
    def test_upcoming_event_enqueued_once(self, state_file, triggers_file):
        enq = []
        s1 = _tick([_event()], state_file, enq)
        assert s1["enqueued"] == 1
        item = enq[0]
        assert item["source"] == "calendar-intake"
        assert item["kind"] == "calendar-upcoming"
        assert "PolAds scrum" in item["payload"]["summary"]
        # second tick: same event → deduped
        s2 = _tick([_event()], state_file, enq)
        assert s2["enqueued"] == 0 and len(enq) == 1

    def test_rescheduled_event_renags(self, state_file, triggers_file):
        enq = []
        _tick([_event()], state_file, enq)
        _tick([_event(start="2026-07-09T10:00:00Z")], state_file, enq)
        assert len(enq) == 2   # new start = new (uid,start) key

    def test_failed_calendar_read_is_reported_not_raised(
            self, state_file, triggers_file):
        def boom(s, e):
            raise RuntimeError("TCC denied")
        summary = cs.tick(now=NOW, read_events_fn=boom,
                          enqueue_fn=lambda i: "1-0",
                          registry=reg, state_file=state_file)
        assert summary["enqueued"] == 0
        assert any("calendar-read" in e for e in summary["errors"])

    def test_enqueue_failure_does_not_mark_seen(self, state_file,
                                                triggers_file):
        def bad(item):
            raise RuntimeError("redis down")
        cs.tick(now=NOW, read_events_fn=lambda s, e: [_event()],
                enqueue_fn=bad, registry=reg, state_file=state_file)
        enq = []
        s2 = _tick([_event()], state_file, enq)
        assert s2["enqueued"] == 1   # retried next tick

    def test_seen_state_pruned(self, state_file, triggers_file):
        old = (NOW - dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps({"seen": {"stale|x": old}}))
        _tick([], state_file, [])
        assert "stale|x" not in json.loads(state_file.read_text())["seen"]


class TestOnEventConsumer:
    def test_uid_and_title_matching_fire_once(self, state_file, triggers_file):
        t1 = reg.register_trigger(kind="on-event", label="scrum prep",
                                  event_key="calendar:polads",
                                  payload={"about": "prep board"})
        enq = []
        s = _tick([_event()], state_file, enq)
        assert s["fired"] == 1
        fired = [i for i in enq if i["kind"] == "trigger-fired"]
        assert len(fired) == 1
        assert fired[0]["urgency_tier"] == "ping-now"
        assert fired[0]["payload"]["trigger"]["id"] == t1["id"]
        # registry contract: on-event is one-shot
        rows = {r["id"]: r for r in reg.list_triggers(include_done=True)}
        assert rows[t1["id"]]["status"] == "fired"
        # next tick: nothing pending → no double fire
        s2 = _tick([_event()], state_file, enq)
        assert s2["fired"] == 0

    def test_uid_exact_match(self, state_file, triggers_file):
        reg.register_trigger(kind="on-event", label="by uid",
                             event_key="calendar:E1", payload={"about": "x"})
        enq = []
        assert _tick([_event(title="Unrelated")], state_file, enq)["fired"] == 1

    def test_non_matching_event_key_stays_pending(self, state_file,
                                                  triggers_file):
        t = reg.register_trigger(kind="on-event", label="other",
                                 event_key="calendar:board dinner",
                                 payload={"about": "x"})
        s = _tick([_event()], state_file, [])
        assert s["fired"] == 0
        assert reg.list_triggers()[0]["id"] == t["id"]   # still pending

    def test_non_calendar_event_keys_untouched(self, state_file,
                                               triggers_file):
        t = reg.register_trigger(kind="on-event", label="pr",
                                 event_key="pr.merged", payload={"about": "x"})
        s = _tick([_event(title="pr.merged party")], state_file, [])
        assert s["fired"] == 0
        assert reg.due_event_triggers("pr.merged")[0]["id"] == t["id"]


def test_intake_item_shape_passes_validation(tmp_path, triggers_file):
    from framework.frontdoor import intake
    captured = []

    def fake_enqueue(item):
        intake.validate_item(item)
        captured.append(item)
        return "1-0"

    cs.tick(now=NOW, read_events_fn=lambda s, e: [_event()],
            enqueue_fn=fake_enqueue, registry=reg,
            state_file=tmp_path / "s.json")
    assert captured, "no item enqueued"


def test_services_row_is_scheduled():
    repo = Path(cs.__file__).resolve().parents[2]
    services = yaml.safe_load(
        (repo / "cabinet" / "services.yml").read_text())["services"]
    rows = [s for s in services if s.get("name") == "calendar-intake"]
    assert len(rows) == 1, "calendar-intake row lost — perception tick unscheduled"
    row = rows[0]
    assert row["label"] == "com.cabinet.calendar-intake"
    assert "calendar_source" in row["command"]
    assert row["schedule"].get("interval_s"), "expected an interval schedule"
