"""Comms Charter (attention-gateway P4, spec §4.7): load/classify/resolve +
the provenance-laddered amend path. The default is conservative; captured
content can never amend; the quiet-hours floor narrows only on Captain word."""
import json

import pytest

from framework.attention import charter


def test_default_loads_and_self_validates():
    ch = charter.load_charter()
    assert ch["_source"] == "default"
    assert ch["version"] >= 1
    charter.validate_charter(ch)   # the shipped default must pass its schema


def test_corrupt_instance_falls_back_to_default(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "comms-charter.yml"
    bad.write_text("version: 1\nclasses: not-a-list\n", encoding="utf-8")
    monkeypatch.setenv("CABINET_CHARTER_PATH", str(bad))
    ch = charter.load_charter()
    assert ch["_source"] == "default"
    assert "charter" in capsys.readouterr().err.lower()


def test_missing_instance_is_default(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_CHARTER_PATH", str(tmp_path / "nope.yml"))
    assert charter.load_charter()["_source"] == "default"


def test_valid_instance_loads_as_instance(tmp_path, monkeypatch):
    good = tmp_path / "comms-charter.yml"
    good.write_text(
        "version: 3\n"
        "quiet_hours: {start: '22:00', end: '06:00', floor_classes: [infra-page]}\n"
        "classes:\n"
        "  - {id: default, route: next-briefing}\n",
        encoding="utf-8")
    monkeypatch.setenv("CABINET_CHARTER_PATH", str(good))
    ch = charter.load_charter()
    assert ch["_source"] == "override" and ch["version"] == 3   # deployment charter won


def test_classify_kind_beats_keyword_beats_lane():
    ch = charter.load_charter()
    # kind match
    assert charter.classify({"kind": "action-card", "title": "x"}, ch) == "action-card"
    # keyword match (no kind hit) — 'fyi' keyword → fyi class
    assert charter.classify(
        {"kind": "note", "title": "fyi the build is green"}, ch) == "fyi"
    # no match → default
    assert charter.classify({"kind": "note", "title": "hello"}, ch) == "default"


def test_no_floor_class_is_keyword_matched():
    """A quiet-hours-floor class must never be selectable by a free-text
    keyword on captured content (review cp4-gauntlet HIGH) — else a card that
    merely says 'today' pierces quiet hours. Every floor class is kind-only."""
    ch = charter.load_charter()
    floor = set(ch["quiet_hours"]["floor_classes"])
    for c in ch["classes"]:
        if c["id"] in floor:
            assert not (c.get("matchers") or {}).get("keywords"), \
                f"floor class {c['id']} is keyword-matched — 3am false-send risk"


def test_word_today_does_not_reach_a_floor_class():
    ch = charter.load_charter()
    cid = charter.classify(
        {"kind": "action-card", "subject": "prep deck",
         "situation": "Nate wants it done today"}, ch)
    assert cid not in set(ch["quiet_hours"]["floor_classes"])


def test_classify_first_match_order():
    """A synthetic charter where two classes could match — the FIRST in
    document order wins."""
    ch = {"version": 1, "_source": "test",
          "quiet_hours": {"start": "21:00", "end": "07:00", "floor_classes": []},
          "classes": [
              {"id": "a", "matchers": {"keywords": ["x"]}, "route": "direct-now"},
              {"id": "b", "matchers": {"keywords": ["x"]}, "route": "mute"},
              {"id": "default", "route": "next-briefing"}]}
    assert charter.classify({"kind": "n", "title": "has x here"}, ch) == "a"


def test_resolve_carries_floor_for_floor_classes():
    ch = charter.load_charter()
    r = charter.resolve({"kind": "infra-page", "title": "disk full"}, ch)
    assert r["class_id"] == "infra-page" and r["floor"] is True
    assert r["route"] == "direct-now"
    r2 = charter.resolve({"kind": "action-card", "title": "x"}, ch)
    assert r2["floor"] is False and r2["route"] == "standing-card"


def test_resolve_defaults_silent_and_banner():
    ch = charter.load_charter()
    r = charter.resolve({"kind": "action-card", "title": "x"}, ch)
    assert r["silent"] is True
    assert r["show_injection_banner"] is False


# --- amend ladder (spec §4.7) -----------------------------------------------

def _instance(tmp_path, monkeypatch):
    p = tmp_path / "comms-charter.yml"
    p.write_text(
        "version: 1\n"
        "quiet_hours: {start: '21:00', end: '07:00', "
        "floor_classes: [deadline-critical, infra-page, security-alert]}\n"
        "classes:\n"
        "  - {id: default, route: next-briefing}\n",
        encoding="utf-8")
    monkeypatch.setenv("CABINET_CHARTER_PATH", str(p))
    return p


def test_amend_captain_happy_path(tmp_path, monkeypatch):
    p = _instance(tmp_path, monkeypatch)
    v = charter.amend({"verbosity": "verbose"}, "Captain asked for detail",
                      {"trust": "captain", "receipt_message_id": 4242})
    assert v == 2
    ch = charter.load_charter()
    assert ch["version"] == 2 and ch["verbosity"] == "verbose"
    rows = [json.loads(l) for l in
            (p.parent / "comms-charter-amendments.jsonl").read_text().splitlines()]
    assert rows[-1]["version"] == 2
    assert rows[-1]["provenance"]["receipt_message_id"] == 4242


def test_amend_captured_content_provenance_raises(tmp_path, monkeypatch):
    _instance(tmp_path, monkeypatch)
    for bad in ({"trust": "captured"}, {"trust": "officer"},
                {"trust": "captain"},  # no receipt id
                {"trust": "captain", "receipt_message_id": 0}, {}):
        with pytest.raises(ValueError):
            charter.amend({"verbosity": "verbose"}, "x", bad)


def test_chair_can_shrink_floor_but_not_grow(tmp_path, monkeypatch):
    """DISTURBANCE ASYMMETRY (review cp4-gauntlet): floor_classes = classes
    that PING at night, so ADDING one is louder (Captain-only) and REMOVING
    one is quieter (chair-free). The opposite of what the first cut had."""
    _instance(tmp_path, monkeypatch)
    # shrink: remove a class from the floor — quieter, allowed for chair
    v = charter.amend(
        {"quiet_hours": {"start": "21:00", "end": "07:00",
                         "floor_classes": ["deadline-critical", "infra-page"]}},
        "chair quieted security-alert at night", {"trust": "chair"})
    assert v == 2
    # grow: add a class to the floor — louder, chair CANNOT
    with pytest.raises(ValueError):
        charter.amend(
            {"quiet_hours": {"start": "21:00", "end": "07:00",
                             "floor_classes": ["deadline-critical", "infra-page",
                                               "meeting-ping"]}},
            "chair tried to make meetings ping at 3am", {"trust": "chair"})


def test_captain_can_grow_floor(tmp_path, monkeypatch):
    _instance(tmp_path, monkeypatch)
    v = charter.amend(
        {"quiet_hours": {"start": "21:00", "end": "07:00",
                         "floor_classes": ["deadline-critical", "infra-page",
                                           "security-alert", "meeting-ping"]}},
        "Captain: wake me for meetings too",
        {"trust": "captain", "receipt_message_id": 99})
    assert v == 2
    assert "meeting-ping" in charter.load_charter()["quiet_hours"]["floor_classes"]


def test_chair_amend_not_locked_out_after_captain_narrow(tmp_path, monkeypatch):
    """After a Captain shrinks the floor, an UNRELATED chair amendment (that
    doesn't touch quiet_hours) must still succeed — the guard checks the
    CURRENT base floor, not the framework default (review cp4-gauntlet)."""
    _instance(tmp_path, monkeypatch)
    charter.amend(
        {"quiet_hours": {"start": "21:00", "end": "07:00",
                         "floor_classes": ["deadline-critical"]}},
        "Captain narrows", {"trust": "captain", "receipt_message_id": 5})
    # unrelated chair tune — must not raise (floor unchanged ⊆ itself)
    v = charter.amend({"verbosity": "verbose"}, "chair tunes", {"trust": "chair"})
    assert v == 3


def test_amend_invalid_result_never_written(tmp_path, monkeypatch):
    p = _instance(tmp_path, monkeypatch)
    before = p.read_text()
    with pytest.raises(ValueError):
        charter.amend({"classes": "not-a-list"}, "breaks schema",
                      {"trust": "captain", "receipt_message_id": 7})
    assert p.read_text() == before   # atomic: no partial write
