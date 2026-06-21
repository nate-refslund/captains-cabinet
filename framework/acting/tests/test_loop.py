"""Dry-run core of the acting loop: the captain-response router + the
consequence recorder. Pure, no I/O. Every recorded event must pass
validate_consequence (the durable ledger contract)."""
from framework.acting import loop
from framework.fidelity.consequence import validate_consequence

ACTOR = {"kind": "officer", "id": "cos"}  # the clone runs as a cabinet officer
TS = "2026-06-21T10:00:00Z"


def _proposal(**kw):
    return loop.proposal_event(actor=ACTOR, lane="send-1to1-reply",
                               subject="kristoffer", ts=TS, **kw)


class TestRouter:
    def test_send(self):
        assert loop.route_captain_response("send").primary == "approve"

    def test_emoji_approve(self):
        assert loop.route_captain_response("👍").primary == "approve"

    def test_ok_with_draft_prefix(self):
        # "draft-reply OK" — the approve token follows a prefix.
        assert loop.route_captain_response("draft-reply OK").primary == "approve"

    def test_edit_captures_text(self):
        r = loop.route_captain_response("edit: her er min version")
        assert r.primary == "edit" and "min version" in r.edit_text

    def test_skip_captures_why(self):
        r = loop.route_captain_response("skip: jeg har allerede svaret")
        assert r.primary == "skip" and "allerede" in r.skip_why
        assert not r.policies  # a plain reason, not a standing rule

    def test_approve_plus_instruction_danish(self):
        # Nate's example shape, in Danish: approve + a new imperative.
        r = loop.route_captain_response(
            "OK, gå også i gang med at bygge A og sig til når det er done")
        assert r.primary == "approve"
        assert r.instructions, "should capture the build-A instruction"

    def test_standing_policy_only(self):
        r = loop.route_captain_response(
            "don't reply to these people unless they explicitly await me, "
            "just give me a summary every now and then")
        assert r.primary == "none"
        assert r.policies, "should capture the standing policy"

    def test_skip_with_embedded_policy(self):
        r = loop.route_captain_response(
            "skip: don't reply to this thread in general unless they await me")
        assert r.primary == "skip"
        assert r.policies, "skip reason that is also a standing rule"

    def test_empty_is_none(self):
        assert loop.route_captain_response("").primary == "none"


class TestRecorder:
    def test_proposal_is_valid_and_pending(self):
        ev = _proposal(required=False)
        validate_consequence(ev)  # must not raise
        assert ev["proposal"]["decision"] is None  # pending
        assert ev["action"] == "draft-reply"
        assert ev["lane"] == "send-1to1-reply"

    def test_outcome_approve_is_confirmed_proof(self):
        prop = _proposal()
        ev = loop.outcome_event(prop, loop.route_captain_response("send"))
        validate_consequence(ev)
        assert ev["ts"] == prop["ts"]                 # supersedes on same ts
        assert ev["proposal"]["decision"] == "approved"
        assert ev["outcome"]["status"] == "ok"
        assert ev["review"]["verdict"] == "confirmed"  # climbs the ladder

    def test_outcome_edit_is_wrong(self):
        ev = loop.outcome_event(_proposal(),
                                loop.route_captain_response("edit: min version"))
        validate_consequence(ev)
        assert ev["proposal"]["decision"] == "edited"
        assert ev["review"]["verdict"] == "wrong"      # correction, no climb

    def test_outcome_skip_is_unknown(self):
        ev = loop.outcome_event(_proposal(),
                                loop.route_captain_response("skip: allerede svaret"))
        validate_consequence(ev)
        assert ev["proposal"]["decision"] == "rejected"
        assert ev["outcome"]["status"] == "unknown"
        assert ev["review"]["verdict"] == "unknown"

    def test_outcome_requires_a_decision(self):
        # A policy-only reply has no draft outcome to record.
        import pytest
        routed = loop.route_captain_response("never reply to marketing blasts")
        with pytest.raises(ValueError):
            loop.outcome_event(_proposal(), routed)

    def test_identity_tuple_preserved_for_supersession(self):
        prop = _proposal()
        out = loop.outcome_event(prop, loop.route_captain_response("send"))
        for k in ("actor", "action", "subject", "ts"):
            assert out[k] == prop[k]  # ledger reader dedups on this tuple


class TestRunLaneEndToEndDry:
    def test_approve_records_proof(self):
        events, dispatched = [], []
        result = loop.run_lane(
            thread_ref="thr-kristoffer", subject="kristoffer", ts=TS, actor=ACTOR,
            gather=lambda tr: {"ctx": "as-of-cutoff"},
            draft_fn=lambda tr, ctx: "perfekt 👌🏻 gør det så efterfølgende",
            present=lambda d, p: None,
            get_response=lambda: "send",
            dispatch=lambda routed, d, p: dispatched.append(routed.primary),
            emit=lambda **ev: events.append(ev))
        assert result["status"] == "decided" and result["primary"] == "approve"
        assert result["verdict"] == "confirmed"
        # ledger: a pending proposal then a superseding outcome (same identity)
        assert len(events) == 2
        for ev in events:
            validate_consequence(ev)
        assert events[0]["proposal"]["decision"] is None        # pending
        assert events[1]["review"]["verdict"] == "confirmed"    # proof
        assert events[0]["ts"] == events[1]["ts"]               # supersession
        assert dispatched == ["approve"]

    def test_gated_thread_emits_nothing(self):
        events = []
        result = loop.run_lane(
            thread_ref="thr", subject="x", ts=TS, actor=ACTOR,
            gather=lambda tr: {}, draft_fn=lambda tr, ctx: None,  # gate: no reply
            present=lambda d, p: None, get_response=lambda: "send",
            dispatch=lambda *a: None, emit=lambda **e: events.append(e))
        assert result["status"] == "gated"
        assert events == []

    def test_skip_dispatches_no_send(self):
        events, dispatched = [], []
        result = loop.run_lane(
            thread_ref="thr", subject="x", ts=TS, actor=ACTOR,
            gather=lambda tr: {}, draft_fn=lambda tr, ctx: "a draft",
            present=lambda d, p: None,
            get_response=lambda: "skip: jeg har allerede svaret",
            dispatch=lambda routed, d, p: dispatched.append(routed.primary),
            emit=lambda **ev: events.append(ev))
        assert result["primary"] == "skip" and result["verdict"] == "unknown"
        assert dispatched == ["skip"]  # the caller's dispatch must NOT send on skip
