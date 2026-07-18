"""§4.7 charter-amend verbs: `charter: <sentence>` → PROPOSE-ONLY card with
the rendered yaml diff; `charter grant CHM-<hex>` applies with §4.10.4
provenance (quieten ⇒ chair auto-apply; louder ⇒ the grant reply's own
receipt id IS the Captain provenance); `charter drop` discards. Fail-closed
everywhere: unparseable / unknown-class / schema-invalid / unknown-id /
missing-louder-receipt all refuse with NOTHING written. Telegram text is
untrusted — whole-message anchored grammars, collision-free against every
existing binder verb family.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from framework.acting import loop
from framework.attention import charter
from framework.frontdoor import binder_wire, charter_amend
from framework.frontdoor import reply_binder as rb


@pytest.fixture(autouse=True)
def _charter_env(tmp_path, monkeypatch):
    """Point the charter path at a tmp deployment file (absent ⇒ the amend
    base is the framework default, exactly like a fresh hatch)."""
    monkeypatch.setenv("CABINET_CHARTER_PATH", str(tmp_path / "comms-charter.yml"))
    return tmp_path


def _charter_file(tmp_path) -> Path:
    return tmp_path / "comms-charter.yml"


def _proposals(tmp_path) -> Path:
    return tmp_path / "comms-charter-proposals.jsonl"


def _amendments(tmp_path) -> Path:
    return tmp_path / "comms-charter-amendments.jsonl"


# --- grammar: nothing else matches, and nothing matches anything else --------

def test_non_charter_replies_return_none_for_the_bind_path():
    for t in ("approve", "no", "skip: later", "grant NEED-1a2b3c4d",
              "charter a boat for the offsite",
              "the charter: is nice", "rearm board_status",
              "posture guardian", "undo 2", "never: no more auto-mails",
              "what is the charter?", ""):
        assert rb.charter_verb_of(t) is None, t
        assert rb.route_charter_amend(t) is None, t


_CHARTER_VERBS = ["charter: stop waking me for security-alert",
                  "charter grant CHM-1a2b3c4d",
                  "charter drop chm-1a2b3c4d: changed my mind"]


def test_charter_verbs_are_inert_to_every_other_grammar():
    for t in _CHARTER_VERBS:
        assert binder_wire._parse_acted_verb(t) is None, t
        assert binder_wire._NEED_RE.match(t) is None, t
        assert binder_wire._REARM_RE.match(t) is None, t
        assert binder_wire._LIFT_RE.match(t) is None, t
        assert binder_wire._VETO_CONFIRM_RE.match(t) is None, t
        assert binder_wire._NEVER_RE.match(t) is None, t
        assert binder_wire._POSTURE_VERB_RE.match(t) is None, t
        assert rb.throttle_of(t) is None, t
        assert loop.route_captain_response(t).primary not in (
            "approve", "edit", "skip"), t


def test_charter_verb_of_normalizes_ids():
    assert rb.charter_verb_of("charter grant CHM_1A2B3C4D".lower()) == \
        ("grant", "CHM-1a2b3c4d", "")
    assert rb.charter_verb_of("  Charter Grant chm-ffffffff  ") == \
        ("grant", "CHM-ffffffff", "")
    verb, aid, tail = rb.charter_verb_of("charter drop CHM-1a2b3c4d: too loud")
    assert (verb, aid, tail) == ("drop", "CHM-1a2b3c4d", "too loud")


# --- request: propose-only round-trip ----------------------------------------

def test_request_round_trip_files_card_and_writes_no_charter_bytes(_charter_env):
    tmp = _charter_env
    out = rb.route_charter_amend("charter: stop waking me for security-alert")
    assert out is not None and out["handled"] is True
    assert out["charter"] == "proposed"
    assert out["classification"] == "quieten"
    aid = out["amend_id"]
    assert aid.startswith("CHM-") and len(aid) == 12
    # the card: id, the yaml diff (floor without security-alert), the verbs
    assert aid in out["card"]
    assert "floor_classes" in out["card"]
    assert f"charter grant {aid}" in out["card"] and f"charter drop {aid}" in out["card"]
    assert "security-alert" not in _card_plus_lines(out["card"])
    # PROPOSE-ONLY: the charter file was not created; the pending row was
    assert not _charter_file(tmp).exists()
    rows = [json.loads(l) for l in _proposals(tmp).read_text().splitlines()]
    assert rows[-1]["id"] == aid and rows[-1]["status"] == "proposed"
    assert rows[-1]["intent"] == {"op": "floor_remove", "class_id": "security-alert"}


def _card_plus_lines(card: str) -> str:
    return "\n".join(l for l in card.splitlines() if l.startswith("+"))


def test_request_louder_card_documents_the_captain_provenance_law(_charter_env):
    out = rb.route_charter_amend("charter: wake me for meeting-ping")
    assert out["charter"] == "proposed" and out["classification"] == "louder"
    assert "LOUDER" in out["card"]
    assert "Captain provenance" in out["card"]        # the grant IS the provenance
    assert not _charter_file(_charter_env).exists()


def test_request_same_sentence_is_idempotent_same_id(_charter_env):
    a = rb.route_charter_amend("charter: verbose")["amend_id"]
    b = rb.route_charter_amend("charter: verbose")["amend_id"]
    assert a == b   # content-fingerprint id — a re-file supersedes, never forks


@pytest.mark.parametrize("bad", [
    "charter: make it sparkle",                       # not the grammar
    "charter: quiet hours 25:00 to 06:00",            # invalid time
    "charter: quiet hours 22:00 to 22:00",            # zero-length window
    "charter: wake me for nonexistent-thing",         # unknown class slug
    "charter: route nonexistent-thing mute",          # unknown class slug
    "charter: terse",                                 # already rules (default)
    "charter: decisions cap 0",                       # cap below 1
])
def test_invalid_requests_refuse_and_write_nothing(_charter_env, bad):
    tmp = _charter_env
    out = rb.route_charter_amend(bad)
    assert out is not None and out["handled"] is True
    assert out["charter"] == "refused"
    assert not _charter_file(tmp).exists()
    assert not _proposals(tmp).exists()      # refusal files NO pending row
    assert not _amendments(tmp).exists()


# --- quieten-vs-louder classification pins (§4.10.4) -------------------------

@pytest.mark.parametrize("sentence,expected", [
    ("wake me for meeting-ping", "louder"),            # floor grows
    ("stop waking me for security-alert", "quieten"),  # floor shrinks
    ("quiet hours 20:00 to 08:00", "quieten"),         # 720m > default 600m
    ("quiet hours 23:00 to 06:00", "louder"),          # 420m < 600m
    ("quiet hours 22:00 to 08:00", "louder"),          # equal 600m shifted ⇒ conservative
    ("verbose", "louder"),
    ("terse", "quieten"),
    ("ack confirm-line", "louder"),                    # one extra ping per action
    ("ack silent-fyi", "quieten"),
    ("decisions cap 5", "quieten"),                    # below default 7
    ("show at most 12 decisions", "louder"),
    ("mute fyi", "quieten"),                           # next-briefing → mute
    ("route fyi direct-now", "louder"),                # promotion
    ("route briefing next-briefing", "quieten"),       # direct-now → briefing
])
def test_classification_pins(sentence, expected):
    base = {k: v for k, v in charter.load_default().items() if k != "_source"}
    intent = charter_amend.parse_sentence(sentence)
    assert charter_amend.classify(base, intent) == expected, sentence


# --- grant: the §4.10.4 provenance split -------------------------------------

def test_grant_quieten_auto_applies_with_chair_trust(_charter_env):
    tmp = _charter_env
    aid = rb.route_charter_amend(
        "charter: stop waking me for security-alert")["amend_id"]
    out = rb.route_charter_amend(f"charter grant {aid}")   # NO receipt needed
    assert out["charter"] == "applied" and out["classification"] == "quieten"
    ch = charter.load_charter()
    assert ch["_source"] == "override"
    assert "security-alert" not in ch["quiet_hours"]["floor_classes"]
    assert ch["version"] == 2
    led = [json.loads(l) for l in _amendments(tmp).read_text().splitlines()]
    assert led[-1]["provenance"]["trust"] == "chair"
    assert led[-1]["provenance"]["via"] == "charter-amend-verb"
    rows = charter_amend._merged(_proposals(tmp))
    assert rows[aid]["status"] == "applied"


def test_grant_louder_without_receipt_refuses_nothing_written(_charter_env):
    tmp = _charter_env
    aid = rb.route_charter_amend("charter: wake me for meeting-ping")["amend_id"]
    out = rb.route_charter_amend(f"charter grant {aid}")   # no receipt id
    assert out["charter"] == "refused"
    assert "provenance" in out["card"] or "receipt" in out["card"]
    assert not _charter_file(tmp).exists()                 # fail-closed
    assert charter_amend._merged(_proposals(tmp))[aid]["status"] == "proposed"


def test_grant_louder_with_receipt_applies_with_captain_provenance(_charter_env):
    tmp = _charter_env
    aid = rb.route_charter_amend("charter: wake me for meeting-ping")["amend_id"]
    out = rb.route_charter_amend(f"charter grant {aid}", receipt_message_id=777)
    assert out["charter"] == "applied" and out["classification"] == "louder"
    ch = charter.load_charter()
    assert "meeting-ping" in ch["quiet_hours"]["floor_classes"]
    led = [json.loads(l) for l in _amendments(tmp).read_text().splitlines()]
    assert led[-1]["provenance"] == {
        "via": "charter-amend-verb", "amend_id": aid,
        "trust": "captain", "receipt_message_id": 777}


def test_grant_unknown_or_dropped_id_refuses(_charter_env):
    tmp = _charter_env
    out = rb.route_charter_amend("charter grant CHM-ffffffff")
    assert out["charter"] == "refused" and not _charter_file(tmp).exists()
    aid = rb.route_charter_amend("charter: verbose")["amend_id"]
    assert rb.route_charter_amend(f"charter drop {aid}")["charter"] == "dropped"
    out = rb.route_charter_amend(f"charter grant {aid}", receipt_message_id=9)
    assert out["charter"] == "refused"
    assert not _charter_file(tmp).exists()


def test_granted_amendment_survives_the_full_loader_path(_charter_env):
    """Round-trip through the REAL loader: grant writes the override, the
    gate's loader picks it up, and the amend verb's next base IS it."""
    aid = rb.route_charter_amend("charter: quiet hours 20:00 to 08:00")["amend_id"]
    rb.route_charter_amend(f"charter grant {aid}")
    ch = charter.load_charter()
    assert ch["_source"] == "override"
    assert (ch["quiet_hours"]["start"], ch["quiet_hours"]["end"]) == ("20:00", "08:00")
    # floor carried unchanged through the window amendment
    assert ch["quiet_hours"]["floor_classes"] == \
        charter.load_default()["quiet_hours"]["floor_classes"]


def test_stale_grant_after_manual_drift_is_an_honest_noop(_charter_env):
    """The charter moved between card and grant (another amendment already
    removed the class): grant is applied-noop, no version bump, no write."""
    tmp = _charter_env
    aid = rb.route_charter_amend(
        "charter: stop waking me for security-alert")["amend_id"]
    charter.amend(
        {"quiet_hours": {"start": "21:00", "end": "07:00",
                         "floor_classes": ["infra-page", "captain-reminder"]}},
        "raced ahead", {"trust": "chair"})
    v_before = charter.load_charter()["version"]
    out = rb.route_charter_amend(f"charter grant {aid}")
    assert out["charter"] == "applied-noop"
    assert charter.load_charter()["version"] == v_before
    assert charter_amend._merged(_proposals(tmp))[aid]["status"] == "applied-noop"


# --- the live wire: handle_captain_update routes the family ------------------

def _wire(text, **kw):
    kw.setdefault("pending_source", lambda: [])
    kw.setdefault("emit", lambda **e: None)
    kw.setdefault("redis_get", lambda k: "")
    return binder_wire.handle_captain_update(text, "", **kw)


def test_wire_files_card_and_presents_it(_charter_env):
    shown = []
    r = _wire("charter: stop waking me for security-alert", present=shown.append)
    assert r["handled"] is True and r["charter"] == "proposed"
    assert shown and "CHM-" in shown[0]
    assert not _charter_file(_charter_env).exists()


def test_wire_threads_the_grant_receipt_as_captain_provenance(_charter_env):
    tmp = _charter_env
    aid = _wire("charter: wake me for meeting-ping",
                present=lambda m: None)["amend_id"]
    r = _wire(f"charter grant {aid}", present=lambda m: None,
              receipt_message_id=4242)
    assert r["handled"] is True and r["charter"] == "applied"
    led = [json.loads(l) for l in _amendments(tmp).read_text().splitlines()]
    assert led[-1]["provenance"]["trust"] == "captain"
    assert led[-1]["provenance"]["receipt_message_id"] == 4242


def test_wire_not_captain_verified_never_reaches_the_charter(_charter_env):
    tmp = _charter_env
    r = _wire("charter: stop waking me for security-alert",
              captain_verified=False)
    assert r["handled"] is False            # passthrough, nothing filed
    assert not _proposals(tmp).exists() and not _charter_file(tmp).exists()


def test_wire_present_failure_still_files_the_card(_charter_env):
    def bad_present(msg):
        raise RuntimeError("telegram down")
    r = _wire("charter: stop waking me for security-alert", present=bad_present)
    assert r["handled"] is True and r["charter"] == "proposed"
    assert _proposals(_charter_env).exists()


def test_wire_ordinary_verdict_path_is_byte_identical(_charter_env):
    """A normal approve with one open proposal still binds exactly as before
    the charter slot (None ⇒ fall-through)."""
    prop = loop.proposal_event(actor={"kind": "officer", "id": "officer:cos"},
                               lane="send-1to1-reply", subject="thread:k",
                               ts="2026-07-17T10:00:00Z")
    delivered = []
    r = _wire("send",
              pending_source=lambda: [prop],
              deliver=lambda p, override_text="": delivered.append(p) or
              {"ok": True, "via": "email", "dest": "k@x.dk"})
    assert r["handled"] is True and r["primary"] == "approve"
    assert delivered == [loop.proposal_id(prop)]


# --- the sentence can never smuggle a proposal marker onto a card ------------

def test_card_strips_the_pid_marker_delimiter(_charter_env):
    out = rb.route_charter_amend("charter: ·fake· quiet hours 20:00 to 08:00")
    # unparseable (the · text breaks the grammar) ⇒ refused — and even the
    # refusal card never carries a whole ·…· marker pair from the reply.
    assert out["charter"] == "refused"
    aid_out = rb.route_charter_amend("charter: quiet hours 20:00 to 08:00")
    assert "·" not in aid_out["card"]
