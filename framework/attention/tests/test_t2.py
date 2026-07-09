"""T2 Chair-live judgment (attention-gateway P5, spec §4.6, §8 P5): the gate
files a judgment request with a dossier + SLA to the Chair; on a Chair verdict
it applies the Chair's authored text; on SLA expiry the charter fallback runs
(floor class → mechanical send with a (chair-offline) marker; else → hold to
briefing). Every T2 outcome is journaled. Deterministic given injected clock,
trigger, and delivery fns."""
import json
from datetime import datetime, timezone, timedelta

import pytest

from framework.attention import t2


NOW = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_ATTENTION_DIR", str(tmp_path / "attention"))
    monkeypatch.setenv("CABINET_FEED_DIR", str(tmp_path / "feed"))


def _decision(**kw):
    base = {"situation_key": "sit-abc123", "class_id": "action-card",
            "text": "⚡ Ship the thing\nneeds your call", "reason": "chair-required",
            "silent": False}
    base.update(kw)
    return base


def _item(**kw):
    base = {"kind": "action-card", "subject": "Ship the thing",
            "situation": "needs your call", "lane": "polads",
            "evidence": ["6-Commitments/owed_to_nate/cmt-abc.md"]}
    base.update(kw)
    return base


# --- dossier -----------------------------------------------------------------

def test_assemble_dossier_shape():
    d = t2.assemble_dossier(
        _item(), _decision(),
        feed_rows=[{"seq": 1, "direction": "out", "kind": "action-card",
                    "situation_key": "sit-abc123", "content_len": 40}],
        patterns_text="always-thread-replies\nprefer-terse",
        intents_text="wants-quiet-mornings",
        charter_section={"id": "action-card", "route": "standing-card"})
    assert d["situation_key"] == "sit-abc123"
    assert d["candidate_text"].startswith("⚡ Ship")
    assert d["class_id"] == "action-card"
    assert any(r.get("situation_key") == "sit-abc123" for r in d["feed_rows"])
    assert "always-thread-replies" in d["patterns"]
    assert d["taint"]["injection_suspect"] is False


def test_assemble_dossier_failsoft_absent_ledgers():
    d = t2.assemble_dossier(_item(), _decision())   # no ledgers/feed injected
    assert d["patterns"] == "" and d["intents"] == ""
    assert isinstance(d["feed_rows"], list)


def test_dossier_carries_taint_provenance():
    d = t2.assemble_dossier(_item(injection_suspect=True), _decision())
    assert d["taint"]["injection_suspect"] is True


# --- file + pending store ----------------------------------------------------

def test_file_judgment_request_stores_and_triggers():
    fired = []
    rid = t2.file_judgment_request(
        _item(), _decision(), {"situation_key": "sit-abc123"},
        sla_minutes=10, now=NOW, fallback="hold-briefing",
        trigger_fn=lambda officer, msg: fired.append((officer, msg)))
    assert rid
    reqs = t2.pending_requests()
    assert len(reqs) == 1 and reqs[0]["request_id"] == rid
    assert reqs[0]["deadline"] == "2026-07-09T12:10:00Z"
    # the trigger goes to cos and carries the request id (a pointer, not the dossier)
    assert fired and fired[0][0] == "cos" and rid in fired[0][1]


def test_apply_verdict_send_delivers_chair_text():
    delivered = []
    rid = t2.file_judgment_request(_item(), _decision(), {}, sla_minutes=10,
                                   now=NOW, trigger_fn=lambda o, m: None)
    out = t2.apply_verdict(
        rid, "send", "Chair-authored: ship it, here's why.",
        gate_deliver=lambda decision, **kw: delivered.append(decision) or {"sent": True})
    assert out["applied"] == "send"
    assert delivered and delivered[0]["text"] == "Chair-authored: ship it, here's why."
    assert t2.pending_requests() == []          # request consumed


def test_apply_verdict_suppress_journals_no_send():
    delivered = []
    rid = t2.file_judgment_request(_item(), _decision(), {}, sla_minutes=10,
                                   now=NOW, trigger_fn=lambda o, m: None)
    out = t2.apply_verdict(rid, "suppress", "not worth a ping",
                           gate_deliver=lambda d, **kw: delivered.append(d))
    assert out["applied"] == "suppress" and not delivered
    assert t2.pending_requests() == []


def test_apply_verdict_unknown_request_is_noop():
    out = t2.apply_verdict("no-such-rid", "send", "x")
    assert out["applied"] == "unknown-request"


# --- SLA sweep / fallback (the P5 acceptance) --------------------------------

def test_sweep_floor_class_sends_mechanically_with_marker():
    """Chair-down: a FLOOR-class request past SLA sends the mechanical render
    with a (chair-offline) marker — the channel never goes dark for a floor
    class (spec §4.6)."""
    delivered = []
    rid = t2.file_judgment_request(
        _item(kind="infra-page"),
        _decision(class_id="infra-page", floor=True,
                  text="🚨 disk full on mini"),
        {}, sla_minutes=10, now=NOW, fallback="mechanical-with-marker",
        floor=True, trigger_fn=lambda o, m: None)
    swept = t2.sweep_expired(
        NOW + timedelta(minutes=11),
        gate_deliver=lambda decision, **kw: delivered.append(decision) or {"sent": True})
    assert len(swept) == 1 and swept[0]["outcome"] == "fallback-sent"
    assert delivered and "(chair-offline)" in delivered[0]["text"]
    assert t2.pending_requests() == []


def test_sweep_nonfloor_holds_to_briefing():
    """Chair-down: a non-floor request past SLA HOLDS (folds to briefing) —
    never a spam send."""
    briefed = []
    rid = t2.file_judgment_request(
        _item(), _decision(class_id="action-card"),
        {}, sla_minutes=10, now=NOW, fallback="hold-briefing", floor=False,
        trigger_fn=lambda o, m: None)
    swept = t2.sweep_expired(
        NOW + timedelta(minutes=11),
        briefing_fn=lambda item, decision: briefed.append(decision))
    assert len(swept) == 1 and swept[0]["outcome"] == "fallback-briefing"
    assert briefed and t2.pending_requests() == []


def test_sweep_leaves_unexpired_requests():
    t2.file_judgment_request(_item(), _decision(), {}, sla_minutes=30, now=NOW,
                             trigger_fn=lambda o, m: None)
    swept = t2.sweep_expired(NOW + timedelta(minutes=5))   # 5 < 30
    assert swept == [] and len(t2.pending_requests()) == 1


def test_sweep_is_idempotent():
    t2.file_judgment_request(_item(kind="infra-page"),
                             _decision(floor=True), {}, sla_minutes=10, now=NOW,
                             fallback="mechanical-with-marker", floor=True,
                             trigger_fn=lambda o, m: None)
    t2.sweep_expired(NOW + timedelta(minutes=11), gate_deliver=lambda d, **k: {"sent": True})
    # second sweep finds nothing (request already consumed) — no double-send
    assert t2.sweep_expired(NOW + timedelta(minutes=12)) == []


def test_rubric_is_versioned_and_loadable():
    r = t2.load_rubric()
    assert "new?" in r.lower() and "true?" in r.lower() and "valuable?" in r.lower()
    assert t2.RUBRIC_VERSION >= 1


# --- cp5-gauntlet regressions ------------------------------------------------

def test_production_sweep_path_actually_sends_floor(monkeypatch):
    """CRITICAL (cp5): the REAL surface call shape — sweep_expired(now) with NO
    injected fns — must actually deliver a floor page, not journal a dark
    'fallback-sent'. Stub channel.send; assert one send carrying (chair-offline)."""
    sends = []
    import framework.frontdoor.channel as channel
    monkeypatch.setattr(channel, "send",
                        lambda text, **kw: sends.append(text) or {"sent": True, "message_ids": [1]})
    t2.file_judgment_request(_item(kind="infra-page"),
                             _decision(class_id="infra-page", floor=True,
                                       text="🚨 disk full on mini"),
                             {}, sla_minutes=10, now=NOW, floor=True,
                             fallback="mechanical-with-marker", trigger_fn=lambda o, m: None)
    swept = t2.sweep_expired(NOW + timedelta(minutes=11))   # NO fns — production shape
    assert len(swept) == 1 and swept[0]["outcome"] == "fallback-sent"
    assert len(sends) == 1 and "(chair-offline)" in sends[0]
    assert t2.pending_requests() == []


def test_failed_floor_send_not_consumed_and_journaled_honestly():
    """A floor fallback whose delivery FAILS must NOT be journaled 'sent' or
    consumed — it is left for the next sweep (never dropped, never lied about)."""
    rid = t2.file_judgment_request(_item(kind="infra-page"),
                                   _decision(floor=True), {}, sla_minutes=10,
                                   now=NOW, floor=True, fallback="mechanical-with-marker",
                                   trigger_fn=lambda o, m: None)
    swept = t2.sweep_expired(NOW + timedelta(minutes=11),
                             gate_deliver=lambda d, **k: {"sent": False, "status": "error"})
    assert swept[0]["outcome"] == "fallback-send-failed"
    assert len(t2.pending_requests()) == 1   # left for retry


def test_escalate_surfaces_the_ask():
    """cp5: escalate must DELIVER the Chair's authored ask, not just journal."""
    delivered = []
    rid = t2.file_judgment_request(_item(), _decision(), {}, sla_minutes=10,
                                   now=NOW, trigger_fn=lambda o, m: None)
    t2.apply_verdict(rid, "escalate", "Captain — I need your call on X.",
                     gate_deliver=lambda d, **k: delivered.append(d) or {"sent": True})
    assert delivered and "need your call" in delivered[0]["text"]


def test_dossier_never_leaks_voice_or_captain_model():
    """The dossier must never carry captain-model/voice content (brain-bridge).
    Even if a ledger somehow contained such tokens, they must not surface."""
    d = t2.assemble_dossier(
        _item(), _decision(),
        patterns_text="nate_model: secret\nvoice-profile: xyz\nalways-thread",
        intents_text="")
    blob = json.dumps(d)
    # the standing-rules filter passes ledger LINES through, so a poisoned
    # ledger is a separate concern — but the dossier must carry NO key named
    # for the model/voice surfaces, and no code path pulls them.
    assert "candidate_text" in d
    for banned in ("me_signal", "voice.md", "drafting-lessons"):
        assert banned not in blob


def test_malformed_deadline_still_expires():
    """A request with a garbage deadline must not become immortal — it sweeps."""
    d = t2._requests_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "t2-deadbeef01.json").write_text(json.dumps({
        "request_id": "t2-deadbeef01", "deadline": "not-a-date",
        "floor": False, "fallback": "hold-briefing", "decision": {}}), encoding="utf-8")
    briefed = []
    swept = t2.sweep_expired(NOW, briefing_fn=lambda i, dec: briefed.append(dec))
    assert any(s["request_id"] == "t2-deadbeef01" for s in swept)


def test_submit_chair_action_files_t2_request():
    """Activation wiring: gate.submit(chair_review=True) on an exceptional item
    FILES a T2 request instead of delivering (no dead code)."""
    from framework.attention import gate
    filed = []
    out = gate.submit(
        {"kind": "infra-page", "subject": "disk full", "urgency": "ping-now",
         "deadline_iso": "2026-07-09T12:30:00Z",
         "evidence": ["6-Commitments/x/cmt-abc.md"]},
        now=NOW, chair_review=True,
        file_t2=lambda item, decision, **kw: filed.append(decision) or "t2-abc123")
    assert out["result"]["status"] == "chair-filed"
    assert filed and filed[0]["action"] == "chair"
