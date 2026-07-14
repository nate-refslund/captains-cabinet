"""Attention gate (attention-gateway P4, spec §4.4-§4.6, §8 P4 acceptance):
situation-keyed standing cards, terse render, charter-driven route + quiet
hours + ping-now demotion. Deterministic given injected charter, clock, and
standing map."""
import json
from datetime import datetime, timezone

import pytest

from framework.attention import charter, gate


# A compact synthetic charter (no dependency on the shipped default's exact
# class list) — floor = infra-page; action-card is a standing-card class.
CH = {
    "version": 1, "_source": "test", "verbosity": "terse", "ack_style": "silent-fyi",
    "quiet_hours": {"start": "21:00", "end": "07:00", "floor_classes": ["infra-page"]},
    "classes": [
        {"id": "infra-page", "matchers": {"kinds": ["infra-page"]},
         "route": "direct-now", "silent": False, "reaction": ["🚨"]},
        {"id": "action-card", "matchers": {"kinds": ["action-card"]},
         "route": "standing-card", "silent": True, "reaction": ["👀"]},
        {"id": "default", "route": "next-briefing", "silent": True},
    ],
}

# noon and 2am in a fixed offset tz (UTC for determinism; gate reads
# CABINET_CAPTAIN_TZ which the fixtures set to UTC).
NOON = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
NIGHT = datetime(2026, 7, 9, 2, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_ATTENTION_DIR", str(tmp_path / "attention"))
    monkeypatch.setenv("CABINET_CAPTAIN_TZ", "UTC")
    monkeypatch.setenv("CABINET_BRIEFING_TIMES", "07:30,19:30")


def _item(**kw):
    base = {"kind": "action-card", "subject": "deed signing",
            "situation": "needs a calendar block",
            "evidence": ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md"],
            "steps": [{"title": "Block calendar"}]}
    base.update(kw)
    return base


def test_one_situation_one_message_across_state_flips():
    """Spec §8 P4: send ONCE, then edits reuse the same message_id."""
    sent, edited = [], []
    def send_fn(text, **kw): sent.append((text, kw)); return {"sent": True, "message_ids": [555]}
    def edit_fn(mid, text, **kw): edited.append((mid, text, kw)); return {"sent": True, "message_ids": [mid]}

    standing = {}
    it = _item()
    d1 = gate.decide(it, ch=CH, now=NOON, standing=standing)
    assert d1["action"] == "send"
    gate.deliver(d1, send_fn=send_fn, edit_fn=edit_fn, standing=standing)

    it2 = _item(steps=[{"title": "Block calendar"}, {"title": "Confirm travel"}], state="acted")
    d2 = gate.decide(it2, ch=CH, now=NOON, standing=standing)
    assert d2["action"] == "edit" and d2["message_id"] == 555
    gate.deliver(d2, send_fn=send_fn, edit_fn=edit_fn, standing=standing)

    it3 = _item(steps=[{"title": "Block calendar"}, {"title": "Confirm travel"}], state="resolved")
    d3 = gate.decide(it3, ch=CH, now=NOON, standing=standing)
    assert d3["action"] == "edit" and d3["message_id"] == 555
    gate.deliver(d3, send_fn=send_fn, edit_fn=edit_fn, standing=standing)

    assert len(sent) == 1 and len(edited) == 2


def test_identical_rerender_suppresses():
    standing = {}
    it = _item()
    d1 = gate.decide(it, ch=CH, now=NOON, standing=standing)
    gate.deliver(d1, send_fn=lambda t, **k: {"sent": True, "message_ids": [1]},
                 edit_fn=lambda m, t, **k: {"sent": True, "message_ids": [m]},
                 standing=standing)
    # same item again → byte-identical render → suppress
    d2 = gate.decide(_item(), ch=CH, now=NOON, standing=standing)
    assert d2["action"] == "suppress" and "no-change" in d2["reason"]


def test_mutate_standing_merges_other_keys_and_deletes():
    """RMW fix: _mutate_standing re-reads the on-disk map UNDER the lock and
    applies exactly one key, so a concurrent pass's OTHER keys survive (no
    last-writer-wins clobber that dropped entries + re-minted duplicate cards);
    a None updater deletes."""
    gate.save_standing({"k1": {"message_id": 1, "render_hash": "h1"}})
    gate._mutate_standing("k2", lambda _old: {"message_id": 2, "render_hash": "h2"})
    assert set(gate.load_standing()) == {"k1", "k2"}          # k1 NOT clobbered
    gate._mutate_standing("k1", lambda _old: None)
    assert set(gate.load_standing()) == {"k2"}                # delete works


def test_deliver_persists_per_key_preserving_concurrent_entry():
    """A stale-snapshot deliver must not lose a concurrent deliver's entry:
    deliver() persists its single key via merge-under-lock, re-reading disk."""
    send = lambda t, **k: {"sent": True, "message_ids": [321]}
    editf = lambda m, t, **k: {"sent": True, "message_ids": [m]}
    dA = gate.decide(_item(subject="alpha", evidence=["a.md"]), ch=CH, now=NOON, standing={})
    dB = gate.decide(_item(subject="beta", evidence=["b.md"]), ch=CH, now=NOON, standing={})
    assert dA["situation_key"] != dB["situation_key"]
    gate.deliver(dA, send_fn=send, edit_fn=editf, standing={})     # disk: {A}
    gate.deliver(dB, send_fn=send, edit_fn=editf, standing={})     # stale {} → merge
    disk = gate.load_standing()
    assert dA["situation_key"] in disk and dB["situation_key"] in disk


def test_failed_edit_drops_entry_so_next_pass_resends():
    """comms-attention-1: an edit that hits a DEAD message must DROP the standing
    entry (→ fresh re-send next pass), not persist a render_hash that forever
    suppresses every future update (silent darkening)."""
    send = lambda t, **k: {"sent": True, "message_ids": [777]}
    fail_edit = lambda m, t, **k: {"status": "error", "sent": False}
    d1 = gate.decide(_item(), ch=CH, now=NOON, standing={})
    gate.deliver(d1, send_fn=send, edit_fn=lambda m, t, **k: {"sent": True, "message_ids": [m]}, standing={})
    skey = d1["situation_key"]
    assert skey in gate.load_standing()
    st = gate.load_standing()
    d2 = gate.decide(_item(steps=[{"title": "Block"}, {"title": "Confirm"}], state="acted"),
                     ch=CH, now=NOON, standing=st)
    assert d2["action"] == "edit"
    gate.deliver(d2, send_fn=send, edit_fn=fail_edit, standing=st)
    assert skey not in gate.load_standing()      # dropped, not darkened


def test_successful_edit_updates_render_hash_and_keeps_entry():
    send = lambda t, **k: {"sent": True, "message_ids": [777]}
    ok_edit = lambda m, t, **k: {"sent": True, "message_ids": [m]}
    d1 = gate.decide(_item(), ch=CH, now=NOON, standing={})
    gate.deliver(d1, send_fn=send, edit_fn=ok_edit, standing={})
    skey = d1["situation_key"]
    h0 = gate.load_standing()[skey]["render_hash"]
    st = gate.load_standing()
    d2 = gate.decide(_item(steps=[{"title": "Block"}, {"title": "Confirm"}], state="acted"),
                     ch=CH, now=NOON, standing=st)
    assert d2["action"] == "edit"
    gate.deliver(d2, send_fn=send, edit_fn=ok_edit, standing=st)
    disk = gate.load_standing()
    assert skey in disk and disk[skey]["render_hash"] != h0


def test_batch_card_at_night_goes_to_briefing():
    d = gate.decide(_item(kind="note"), ch=CH, now=NIGHT, standing={})
    assert d["action"] == "briefing"


def test_floor_class_at_night_sends_unsilenced():
    d = gate.decide(_item(kind="infra-page", subject="disk full"),
                    ch=CH, now=NIGHT, standing={})
    assert d["action"] == "send" and d["silent"] is False


def test_batch_card_at_noon_standing_card_sends():
    d = gate.decide(_item(), ch=CH, now=NOON, standing={})
    assert d["action"] == "send" and d["silent"] is True


def test_pingnow_deadline_after_briefing_demoted():
    it = _item(kind="note", urgency="ping-now",
               deadline_iso="2026-07-11T00:00:00Z")   # 2 days out
    d = gate.decide(it, ch=CH, now=NOON, standing={})
    assert d["action"] == "briefing" and "ping-now" in d["reason"]


def test_pingnow_deadline_before_next_briefing_stays_direct():
    # now = noon UTC; next briefing = 19:30 UTC today; deadline 15:00 today
    it = _item(kind="infra-page", subject="cert expires 3pm",
               urgency="ping-now", deadline_iso="2026-07-09T15:00:00Z")
    d = gate.decide(it, ch=CH, now=NOON, standing={})
    assert d["action"] == "send"


def test_nonfloor_pingnow_imminent_deadline_pierces_quiet_hours():
    """Structural piercing (review cp4-gauntlet): a non-floor item with a REAL
    deadline before the next briefing pierces quiet hours — a timestamp, never
    a prose word, is what wakes the Captain at night. now=NIGHT (02:00),
    next briefing 07:30, deadline 05:00 → send."""
    it = _item(kind="note", urgency="ping-now",
               deadline_iso="2026-07-09T05:00:00Z")
    d = gate.decide(it, ch=CH, now=NIGHT, standing={})
    assert d["action"] == "send"


def test_nonfloor_note_saying_today_at_night_goes_to_briefing():
    """The headline cp4-gauntlet bug, pinned at the gate: a routine card whose
    text merely says 'today' must NOT send at 2am — no keyword pierces."""
    it = _item(kind="note", subject="prep deck",
               situation="Ada wants it done today")
    d = gate.decide(it, ch=CH, now=NIGHT, standing={})
    assert d["action"] == "briefing"


def test_templated_card_keeps_pid_marker_and_banner():
    """A class supplying a template must not swallow the binder ·pid· marker
    (the binder can't verdict without it) or the security banner (review
    cp4-gauntlet)."""
    ch = json_roundtrip(CH)
    ch["classes"].insert(0, {"id": "security-alert",
                             "matchers": {"kinds": ["security-alert"]},
                             "route": "direct-now", "show_injection_banner": True,
                             "template": "SEC: {subject}"})
    ch["quiet_hours"]["floor_classes"].append("security-alert")
    it = _item(kind="security-alert", subject="quarantine trip",
               injection_suspect=True, pid_marker="·cos|x|ts·")
    d = gate.decide(it, ch=ch, now=NOON, standing={})
    assert "SEC: quarantine trip" in d["text"]
    assert "·cos|x|ts·" in d["text"]            # marker preserved
    assert "INJECTION-SUSPECT" in d["text"]     # banner preserved


def test_injection_banner_hidden_and_pid_marker_survives():
    it = _item(injection_suspect=True, pid_marker="·cos|action-card|x|ts·")
    d = gate.decide(it, ch=CH, now=NOON, standing={})
    assert "INJECTION-SUSPECT" not in d["text"]
    assert "·cos|action-card|x|ts·" in d["text"]


def test_injection_banner_shown_for_security_class():
    ch = json_roundtrip(CH)
    ch["classes"].insert(0, {"id": "security-alert",
                             "matchers": {"kinds": ["security-alert"]},
                             "route": "direct-now", "show_injection_banner": True})
    ch["quiet_hours"]["floor_classes"].append("security-alert")
    it = _item(kind="security-alert", subject="quarantine trip", injection_suspect=True)
    d = gate.decide(it, ch=ch, now=NOON, standing={})
    assert "INJECTION-SUSPECT" in d["text"]


def test_charter_unavailable_raises(monkeypatch):
    """The gate must NOT silently send ungoverned if the charter machinery
    can't load — it raises so the surface service falls back."""
    import sys as _sys
    import framework.attention as _pkg
    # `from framework.attention import charter` resolves the already-bound
    # package attribute first; evict BOTH it and the sys.modules entry (None
    # sentinel → ImportError) to simulate the module genuinely not loading.
    monkeypatch.delattr(_pkg, "charter", raising=False)
    monkeypatch.setitem(_sys.modules, "framework.attention.charter", None)
    with pytest.raises(RuntimeError):
        gate.decide(_item(), ch=None, now=NOON, standing={})


def test_corrupt_standing_map_treated_empty(tmp_path, monkeypatch, capsys):
    d = tmp_path / "attention"
    d.mkdir()
    (d / "standing-cards.json").write_text("{ not json", encoding="utf-8")
    monkeypatch.setenv("CABINET_ATTENTION_DIR", str(d))
    st = gate.load_standing()
    assert st == {}
    assert "standing" in capsys.readouterr().err.lower()


def test_terse_render_no_payload_dump():
    it = _item(steps=[{"title": "Block calendar",
                       "payload": {"secret": "should-not-appear-in-card"}}])
    d = gate.decide(it, ch=CH, now=NOON, standing={})
    assert "should-not-appear" not in d["text"]
    assert "Block calendar" in d["text"]


def json_roundtrip(x):
    return json.loads(json.dumps(x))


def test_attention_submit_sh_dry_mode(tmp_path):
    """The shell producer resolves a decision without delivering in DRY mode."""
    import subprocess, os
    root = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    env = dict(os.environ, CABINET_GATE_DRY="1",
               CABINET_ATTENTION_DIR=str(tmp_path / "att"))
    out = subprocess.run(
        ["bash", os.path.join(root, "cabinet/scripts/attention-submit.sh"),
         "infra-page", "disk full on mini", "root partition at 98%"],
        capture_output=True, text=True, env=env, timeout=30)
    assert out.returncode == 0, out.stderr
    dec = json.loads(out.stdout.strip().splitlines()[-1])
    assert dec["class_id"] == "infra-page" and dec["action"] == "send"


# --- P5 T2 mode-pick (chair_review) ------------------------------------------

def test_chair_review_off_preserves_p4_mechanical():
    """Default (chair_review=False) is byte-identical to P4: an exceptional
    item still routes mechanically."""
    it = _item(kind="infra-page", urgency="ping-now",
               deadline_iso="2026-07-09T15:00:00Z")
    d = gate.decide(it, ch=CH, now=NOON, standing={})   # no chair_review
    assert d["action"] == "send"


def test_chair_review_routes_genuine_pingnow_to_chair():
    it = _item(kind="infra-page", urgency="ping-now",
               deadline_iso="2026-07-09T15:00:00Z")
    d = gate.decide(it, ch=CH, now=NOON, standing={}, chair_review=True)
    assert d["action"] == "chair" and d["reason"] == "chair-pingnow"
    assert d["floor"] is True and d["fallback"] == "mechanical-with-marker"


def test_chair_review_routes_act_carrying_to_chair():
    it = _item(steps=[{"kind": "reminder_create", "title": "Block cal"}])
    d = gate.decide(it, ch=CH, now=NOON, standing={}, chair_review=True)
    assert d["action"] == "chair" and d["reason"] == "chair-act-carrying"
    assert d["fallback"] == "hold-briefing"   # non-floor


def test_chair_review_routes_low_confidence_to_chair():
    it = _item(confidence=0.4)
    d = gate.decide(it, ch=CH, now=NOON, standing={}, chair_review=True)
    assert d["action"] == "chair" and d["reason"] == "chair-low-confidence"


def test_chair_review_routine_high_conf_stays_mechanical():
    """A routine, high-confidence, non-acting standing-card item is NOT
    exceptional — it sends mechanically even with chair_review on."""
    it = _item(confidence=0.95, steps=[])
    d = gate.decide(it, ch=CH, now=NOON, standing={}, chair_review=True)
    assert d["action"] == "send"


def test_chair_review_identity_dedup_still_wins():
    """A standing card that already exists edits/suppresses BEFORE the mode
    pick — an exceptional re-render must not re-file a T2 request."""
    standing = {}
    it = _item(steps=[{"kind": "reminder_create", "title": "x"}])
    d1 = gate.decide(it, ch=CH, now=NOON, standing=standing, chair_review=True)
    assert d1["action"] == "chair"
    # simulate the card now existing (chair sent it)
    from framework.attention.situation import situation_key
    skey = situation_key(it["evidence"], it["subject"])
    standing[skey] = {"message_id": 9, "render_hash": "different"}
    d2 = gate.decide(it, ch=CH, now=NOON, standing=standing, chair_review=True)
    assert d2["action"] == "edit"   # identity wins over mode-pick


def test_gate_briefing_item_renders_through_composer():
    """P5 acceptance: a briefing-routed gate decision produces a valid intake
    item the composer folds into the next briefing (gate→intake→composer)."""
    from framework.frontdoor import composer, intake
    it = _item(kind="note")
    d = gate.decide(it, ch=CH, now=NIGHT, standing={})   # night → briefing
    assert d["action"] == "briefing"
    intake_item = gate.briefing_item(it, d)
    intake.validate_item(intake_item)                    # raises if malformed
    rendered = composer.render_item(intake_item)
    assert "attention-gate" in rendered
    assert "briefing" in composer.compose([intake_item]).lower()
