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


# FIX A (SAFETY) — a leading approve token followed by a hold/cancel/negated-send
# in the REMAINDER must FAIL CLOSED (downgrade to 'none', never auto-approve).
class TestApproveFailsClosed:
    def test_ja_men_vent_svar_ikke_endnu(self):
        # Danish: "yes but wait — don't reply yet" must NOT auto-approve.
        r = loop.route_captain_response("ja, men vent — svar ikke endnu")
        assert r.primary == "none"

    def test_yes_but_do_not_send_this(self):
        r = loop.route_captain_response("yes but do not send this")
        assert r.primary == "none"

    def test_send_it_to_the_trash_do_not_reply(self):
        r = loop.route_captain_response("send it to the trash, do not reply")
        assert r.primary == "none"

    def test_contradiction_remainder_is_not_a_durable_policy(self):
        # downgraded to none AND the one-off negation must NOT seed a standing rule
        r = loop.route_captain_response("yes but do not send this")
        assert r.primary == "none"
        assert not r.policies


# FIX C (correctness) — approve branch captures instruction AND policy
# INDEPENDENTLY: a compound reply keeps BOTH non-empty.
class TestApproveCompoundCapture:
    def test_instruction_and_policy_both_captured(self):
        r = loop.route_captain_response(
            "send, also build A, and in general suppress marketing threads")
        assert r.primary == "approve"
        assert r.instructions, "should capture the build-A instruction"
        assert r.policies, "should ALSO capture the suppress-marketing policy"


# FIX B (correctness) — expire_event closes a pending proposal as 'expired';
# run_lane emits it on a policy/instruction-only reply (primary='none').
class TestExpireEvent:
    def test_expire_event_shape_and_validity(self):
        prop = _proposal()
        ev = loop.expire_event(prop)
        validate_consequence(ev)
        assert ev["proposal"]["decision"] == "expired"
        assert "decided_at" in ev["proposal"]
        assert "outcome" not in ev          # NO outcome object on expiry
        assert ev["review"]["verdict"] == "unknown"
        for k in ("actor", "action", "subject", "ts"):
            assert ev[k] == prop[k]          # supersedes on identity tuple

    def test_run_lane_policy_only_expires_proposal(self):
        events, dispatched = [], []
        result = loop.run_lane(
            thread_ref="thr", subject="x", ts=TS, actor=ACTOR,
            gather=lambda tr: {}, draft_fn=lambda tr, ctx: "a draft",
            present=lambda d, p: None,
            get_response=lambda: (
                "don't reply to these people unless they explicitly await me"),
            dispatch=lambda routed, d, p: dispatched.append(routed.primary),
            emit=lambda **ev: events.append(ev))
        assert result["primary"] == "none"
        assert result["status"] == "expired"
        # ledger: a pending proposal then a superseding expired event
        assert len(events) == 2
        for ev in events:
            validate_consequence(ev)
        assert events[0]["proposal"]["decision"] is None          # pending
        assert events[1]["proposal"]["decision"] == "expired"     # closed out
        assert events[0]["ts"] == events[1]["ts"]                 # supersession


# FIX E (SAFETY) — the draft only reaches dispatch on an explicit approve.
class TestDispatchDraftGuard:
    def test_skip_dispatch_gets_no_draft(self):
        seen = {}
        loop.run_lane(
            thread_ref="thr", subject="x", ts=TS, actor=ACTOR,
            gather=lambda tr: {}, draft_fn=lambda tr, ctx: "a draft",
            present=lambda d, p: None,
            get_response=lambda: "skip: jeg har allerede svaret",
            dispatch=lambda routed, d, p: seen.update(draft=d),
            emit=lambda **ev: None)
        assert seen["draft"] is None  # non-approve path can never carry the draft

    def test_approve_dispatch_gets_the_draft(self):
        seen = {}
        loop.run_lane(
            thread_ref="thr", subject="x", ts=TS, actor=ACTOR,
            gather=lambda tr: {}, draft_fn=lambda tr, ctx: "the draft",
            present=lambda d, p: None, get_response=lambda: "send",
            dispatch=lambda routed, d, p: seen.update(draft=d),
            emit=lambda **ev: None)
        assert seen["draft"] == "the draft"  # only approve carries it


# FIX D (correctness) — lesson_ref attaches only when the mapped verdict is
# 'wrong' (edit). The ledger rejects lesson_ref on confirmed/unknown.
class TestLessonRefGuard:
    def test_approve_drops_lesson_ref(self):
        ev = loop.outcome_event(_proposal(),
                                loop.route_captain_response("send"),
                                lesson_ref="x")
        validate_consequence(ev)
        assert "lesson_ref" not in ev["review"]   # confirmed -> no lesson_ref

    def test_edit_carries_lesson_ref(self):
        ev = loop.outcome_event(_proposal(),
                                loop.route_captain_response("edit: min version"),
                                lesson_ref="x")
        validate_consequence(ev)
        assert ev["review"]["lesson_ref"] == "x"  # wrong -> lesson_ref kept


# FIX F (correctness) — a standalone (no verb) reply needs a GENERALIZING marker
# to record a durable policy; a bare one-off refusal must NOT become policy.
class TestStandalonePolicyGuard:
    def test_bare_one_off_refusal_is_not_policy(self):
        r = loop.route_captain_response("please dont send this")
        assert r.primary == "none"
        assert not r.policies  # one-off refusal, NOT a standing rule

    def test_generalizing_refusal_is_policy(self):
        r = loop.route_captain_response(
            "don't reply to these people unless they explicitly await me, "
            "just give me a summary every now and then")
        assert r.primary == "none"
        assert r.policies  # has 'unless' + 'these people' -> durable policy
