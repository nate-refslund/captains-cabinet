"""Tests for the scoped Kristoffer-UAT auto-reply core (graduated autonomy).

The module under test (``framework/autoreply/kristoffer_uat.py``) is a pure
decision + compose core: every side effect (send, copy-to-Nate, Redis, audit,
route) is INJECTED, so these tests use fakes — no real Redis, no real outbound,
no real Telegram. Mirrors the ``framework/authority/veto`` test convention.

The behaviours pinned here are the SAFETY contract:
  * ships DISARMED — a genuine UAT report does NOT send when the flag is unset;
  * SCOPE fence — wrong person / wrong channel / non-UAT text never auto-sends;
  * three gates fail CLOSED (scope, arm, killswitch) and in the right order;
  * bounded ack makes only the three allowed claims (received/routing/ETA);
  * Nate ALWAYS gets a copy of what went out;
  * the bug is routed to polads-ceo; a send failure is captured, not raised;
  * dry-run composes a sample to Nate but sends/routes nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.autoreply import kristoffer_uat as K


# ---------------------------------------------------------------------------
# Fakes / fixtures.
# ---------------------------------------------------------------------------

class Recorder:
    """Captures every injected side effect so assertions can inspect them."""

    def __init__(self, *, redis=None, send_ok=True, send_raises=False,
                 route_raises=False, copy_raises=False):
        self.redis = dict(redis or {})
        self.sent = []          # send_backend payloads
        self.copies = []        # copy_to_nate texts
        self.audits = []        # audit records
        self.routed = []        # route_bug items
        self._send_ok = send_ok
        self._send_raises = send_raises
        self._route_raises = route_raises
        self._copy_raises = copy_raises

    def redis_get(self, key):
        return self.redis.get(key)

    def send_backend(self, payload):
        if self._send_raises:
            raise RuntimeError("boom-send")
        self.sent.append(payload)
        return {"ok": self._send_ok, "sent": self._send_ok}

    def copy_to_nate(self, text):
        if self._copy_raises:
            raise RuntimeError("boom-copy")
        self.copies.append(text)

    def audit(self, rec):
        self.audits.append(rec)

    def route_bug(self, item):
        if self._route_raises:
            raise RuntimeError("boom-route")
        self.routed.append(item)


ARMED = {K.ARM_FLAG_KEY: "1"}
_UAT_TEXT = ("The publisher VIES auto-fill is broken on staging — 500 error "
             "when I click fetch. Repro: /register, type a CVR, hit fetch.")


def _run(rec: Recorder, *, sender="krmoj@step.dk", channel="teams",
         text=_UAT_TEXT, eta="", ref="", dry_run=False):
    return K.handle_message(
        sender=sender, channel=channel, text=text,
        redis_get=rec.redis_get, send_backend=rec.send_backend,
        copy_to_nate=rec.copy_to_nate, audit=rec.audit, route_bug=rec.route_bug,
        eta=eta, ref=ref, dry_run=dry_run,
    )


# ===========================================================================
# 1. DISARMED BY DEFAULT — the headline safety property.
# ===========================================================================

def test_disarmed_by_default_does_not_send():
    """A genuine, in-scope UAT report with NO arm flag set must NOT send."""
    rec = Recorder(redis={})  # no arm flag at all
    res = _run(rec)
    assert res["decision"] == "disarmed"
    assert res["sent"] is False
    assert rec.sent == []          # nothing sent to Kristoffer
    assert rec.routed == []        # nothing routed
    assert "default OFF" in res["reason"]


def test_arm_flag_must_be_exactly_one():
    for bad in ("0", "true", "yes", "enabled", " ", "1 ", "on"):
        rec = Recorder(redis={K.ARM_FLAG_KEY: bad})
        res = _run(rec)
        assert res["decision"] == "disarmed", f"value {bad!r} should NOT arm"
        assert rec.sent == []


def test_redis_down_fails_closed():
    """If the arm-flag getter raises (Redis unreachable), the lane is disarmed."""
    def boom(_key):
        raise RuntimeError("no redis")
    res = K.handle_message(
        sender="krmoj@step.dk", channel="teams", text=_UAT_TEXT,
        redis_get=boom, send_backend=lambda p: 1/0, copy_to_nate=lambda t: None,
        audit=lambda r: None, route_bug=lambda i: None,
    )
    assert res["decision"] == "disarmed"
    assert res["sent"] is False


# ===========================================================================
# 2. SCOPE FENCE — person, channel, topic.
# ===========================================================================

def test_wrong_person_declined_even_when_armed():
    rec = Recorder(redis=ARMED)
    res = _run(rec, sender="someone-else@gmail.com")
    assert res["decision"] == "declined"
    assert "not Kristoffer" in res["reason"]
    assert rec.sent == []


def test_wrong_channel_declined():
    rec = Recorder(redis=ARMED)
    res = _run(rec, channel="email")
    assert res["decision"] == "declined"
    assert "channel" in res["reason"]
    assert rec.sent == []


def test_non_uat_message_declined():
    rec = Recorder(redis=ARMED)
    res = _run(rec, text="hej Nate, skal vi tage en kaffe på fredag?")
    assert res["decision"] == "declined"
    assert "not a UAT" in res["reason"]
    assert rec.sent == []


def test_social_closer_declined():
    """A pure 'thanks!' must not trip on a stray signal word."""
    rec = Recorder(redis=ARMED)
    for msg in ("thanks!", "tusind tak", "👍", "ok perfect", "lyder godt"):
        res = _run(rec, text=msg)
        assert res["decision"] == "declined", f"{msg!r} should be declined"
    assert rec.sent == []


def test_scope_accepts_kristoffers_identity_forms():
    """Slug, accent-folded slug, display name, and primary email all match."""
    for sender in ("Kristoffer-Møller-Nielsen", "kristoffer-moller-nielsen",
                   "Kristoffer Møller Nielsen", "KRMOJ@STEP.DK"):
        rec = Recorder(redis=ARMED)
        res = _run(rec, sender=sender)
        assert res["decision"] == "sent", f"{sender!r} should be in scope"


def test_scope_checked_before_arm_state():
    """An out-of-scope message is 'declined' regardless of arm state (no arm-
    state leak, and the cheap common case short-circuits)."""
    rec = Recorder(redis={})  # disarmed
    res = _run(rec, sender="stranger@x.com")
    assert res["decision"] == "declined"  # not 'disarmed' — scope wins


# ===========================================================================
# 3. UAT DETECTION unit coverage (EN + DA, true/false).
# ===========================================================================

@pytest.mark.parametrize("text", [
    "the register flow is broken",
    "I get a 500 error on /with-sponsors",
    "publisher hierarchy doesn't work when expanded",
    "VIES auto-fill fails, see screenshot",
    "staging login virker ikke",
    "der er en fejl i transparency-labelen",
    "can't submit the sponsor section, it crashes",
])
def test_is_uat_report_true(text):
    assert K.is_uat_report(text) is True


@pytest.mark.parametrize("text", [
    "thanks for the fix!",
    "how's the publisher flow coming along?",
    "kaffe på fredag?",
    "great work on the deploy",
    "",
    "👍",
    # benign idioms that CONTAIN a signal token but are not reports (regression:
    # 'no problem' -> 'problem' must not auto-fire, even with a context word):
    "no problem, I'll re-test after the deploy",
    "no worries",
    "great, the VIES fix works now, thanks!",
    "works now after your fix",
    "all good on my end",
])
def test_is_uat_report_false(text):
    assert K.is_uat_report(text) is False


@pytest.mark.parametrize("text", [
    # a benign phrase PLUS a genuine surviving defect signal -> still a report:
    "no problem with login, but the register flow is broken on staging",
    "login virker nu, men register-flowet fejler stadig",
])
def test_benign_phrase_does_not_mask_a_real_signal(text):
    assert K.is_uat_report(text) is True


# ===========================================================================
# 4. GLOBAL KILLSWITCH gate.
# ===========================================================================

def test_global_killswitch_halts_even_when_armed_and_in_scope():
    rec = Recorder(redis={K.ARM_FLAG_KEY: "1", K.GLOBAL_KILLSWITCH_KEY: "active"})
    res = _run(rec)
    assert res["decision"] == "halted"
    assert res["sent"] is False
    assert rec.sent == []
    assert "killswitch" in res["reason"].lower()


# ===========================================================================
# 5. THE HAPPY PATH — armed + in-scope + clear -> bounded ack, routed, copied.
# ===========================================================================

def test_happy_path_sends_routes_and_copies():
    rec = Recorder(redis=ARMED)
    res = _run(rec, ref="BUG-123", eta="fix targeted for the next deploy")
    assert res["decision"] == "sent"
    assert res["sent"] is True and res["routed"] is True and res["copied"] is True
    # exactly one send, to Kristoffer's Teams identity
    assert len(rec.sent) == 1
    payload = rec.sent[0]
    assert payload["channel"] == "teams"
    assert payload["slug"] == K.KRISTOFFER_SLUG
    assert payload["recipient_email"] == "krmoj@step.dk"
    # routed to polads-ceo
    assert len(rec.routed) == 1 and rec.routed[0]["officer"] == "polads-ceo"
    # Nate got a copy, labelled as auto-sent
    assert len(rec.copies) == 1 and "AUTO-SENT" in rec.copies[0]


def test_ack_is_bounded_three_claims_only():
    """The ack makes ONLY the allowed claims: received + routing + ETA. It must
    never assert a fix/root-cause (no substantive content)."""
    ack = K.render_ack("the register 500", eta="fix in next deploy", ref="B-1")
    low = ack.lower()
    assert "got your uat report" in low      # received
    assert "routing it to the team" in low   # routing
    assert "next deploy" in low              # ETA echoed
    assert "ref b-1" in low
    # bounded: must NOT claim a fix is done or a cause is known
    for forbidden in ("fixed", "root cause", "resolved", "deployed the fix",
                      "i've corrected", "the problem was"):
        assert forbidden not in low


def test_ack_is_unsigned_and_casual():
    """Teams house style: lowercase-casual, never signed (no signature block)."""
    ack = K.render_ack("the staging error")
    assert "Best regards" not in ack and "Med venlig hilsen" not in ack
    assert ack[0].islower()  # starts lowercase ('got your...')


def test_topic_echo_is_verbatim_not_paraphrased():
    """The echoed topic is pulled from his own words (no paraphrase that could
    misstate). Greeting is stripped."""
    topic = K.detect_topic("Hi Nate - the VIES auto-fill returns a 500")
    assert topic.lower().startswith("the vies auto-fill")
    assert "hi nate" not in topic.lower()


def test_default_eta_when_unspecified():
    ack = K.render_ack("the bug")
    assert K.DEFAULT_ETA in ack


# ===========================================================================
# 6. FAILURE MODES — never raise; capture + still copy Nate.
# ===========================================================================

def test_send_failure_is_captured_not_raised_and_nate_still_copied():
    rec = Recorder(redis=ARMED, send_raises=True)
    res = _run(rec)
    assert res["decision"] == "send-failed"
    assert res["sent"] is False
    # bug was still routed (routing happens before send, and must survive a send fail)
    assert len(rec.routed) == 1
    # Nate STILL gets a copy — and it surfaces the failure
    assert len(rec.copies) == 1 and "send FAILED" in rec.copies[0]


def test_send_returns_not_ok_is_send_failed():
    rec = Recorder(redis=ARMED, send_ok=False)
    res = _run(rec)
    assert res["decision"] == "send-failed"
    assert res["sent"] is False


def test_route_failure_does_not_block_ack():
    """If routing to polads-ceo fails, the ack still sends (bug isn't lost — the
    failure is surfaced to Nate in the copy and audit)."""
    rec = Recorder(redis=ARMED, route_raises=True)
    res = _run(rec)
    assert res["decision"] == "sent"
    assert res["sent"] is True
    assert res["routed"] is False
    assert "FAILED" in rec.copies[0]


def test_copy_failure_is_captured_not_raised():
    rec = Recorder(redis=ARMED, copy_raises=True)
    res = _run(rec)        # must not raise
    assert res["copied"] is False
    assert res["sent"] is True  # the send itself still happened


# ===========================================================================
# 7. DRY RUN — sample to Nate, nothing to Kristoffer / polads-ceo.
# ===========================================================================

def test_dry_run_composes_sample_but_sends_nothing():
    rec = Recorder(redis=ARMED)  # even armed, dry_run must not egress
    res = _run(rec, dry_run=True)
    assert res["decision"] == "dry-run"
    assert rec.sent == []        # nothing to Kristoffer
    assert rec.routed == []      # nothing routed
    assert len(rec.copies) == 1  # Nate gets the sample
    assert "SAMPLE" in rec.copies[0] and "NOT sent" in rec.copies[0]
    assert res.get("ack")        # ack composed


def test_dry_run_works_even_when_disarmed():
    """A sample can be produced without arming (so Nate can review pre-arm)."""
    rec = Recorder(redis={})
    res = _run(rec, dry_run=True)
    assert res["decision"] == "dry-run"
    assert len(rec.copies) == 1 and "SAMPLE" in rec.copies[0]


# ===========================================================================
# 8. AUDIT — every decision leaves a record.
# ===========================================================================

@pytest.mark.parametrize("redis,sender,expect", [
    ({}, "krmoj@step.dk", "disarmed"),
    (ARMED, "stranger@x.com", "declined"),
    ({K.ARM_FLAG_KEY: "1", K.GLOBAL_KILLSWITCH_KEY: "active"}, "krmoj@step.dk", "halted"),
    (ARMED, "krmoj@step.dk", "sent"),
])
def test_every_decision_is_audited(redis, sender, expect):
    rec = Recorder(redis=redis)
    res = _run(rec, sender=sender)
    assert res["decision"] == expect
    assert len(rec.audits) == 1
    assert rec.audits[0]["decision"] == expect
    assert rec.audits[0]["lane"] == "autoreply:kristoffer-uat"


def test_audit_record_serializes_to_jsonl():
    rec = Recorder(redis=ARMED)
    _run(rec)
    line = K.jsonl(rec.audits[0])
    assert line.startswith("{") and '"decision"' in line
