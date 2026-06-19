from __future__ import annotations

import pytest

from framework.fidelity import leakguard
from framework.fidelity.types import Case, OfficerDecision

CUTOFF = "2026-06-10T12:00:00+00:00"


def _retro_case():
    return {
        "case_id": "abc1234567",
        "reply_key": "msgraph|MID1",
        "slug": "ulrik",
        "person": "Ulrik",
        "channel": "msgraph",
        "language": "da",
        "reply_ts": CUTOFF,
        "subject": "Re: lon",
        "n_prior": 3,
        "thread_before": [
            {"slug": "ulrik", "person": "Ulrik", "date": "2026-06-09T08:00:00+00:00",
             "direction": "received", "who": "Ulrik <u@x>", "source": "msgraph",
             "to": "", "cc": "", "text": "kan vi snakke lon?"},
        ],
        "real_reply": "Ja, lad os tage det fredag.",
    }


class TestCaseModel:
    def test_from_retro_case_sets_cutoff_and_ground_truth(self):
        c = Case.from_retro_case(_retro_case())
        assert c.cutoff_ts == CUTOFF
        assert c.ground_truth == {"real_reply": "Ja, lad os tage det fredag."}
        assert c.lane == "send-1to1-reply"
        assert c.decision_type == "reply"
        assert c.held_out is True
        assert c.channel == "msgraph" and c.slug == "ulrik"

    def test_to_retro_case_roundtrips_scoring_keys(self):
        c = Case.from_retro_case(_retro_case())
        rc = c.to_retro_case()
        assert rc["case_id"] == "abc1234567"
        assert rc["reply_ts"] == CUTOFF
        assert rc["channel"] == "msgraph"
        assert rc["real_reply"] == "Ja, lad os tage det fredag."
        assert rc["thread_before"] == c.thread_before

    def test_intent_defaults_empty(self):
        # F4 §1.6: Case.intent is a new field, default "".
        c = Case.from_retro_case(_retro_case())
        assert c.intent == ""

    def test_from_retro_case_leaves_intent_empty(self):
        # F4 §1.6/§8: from_retro_case leaves intent "" (computed lazily later,
        # never eagerly populated here).
        rc = _retro_case()
        c = Case.from_retro_case(rc)
        assert c.intent == ""

    def test_intent_never_set_from_real_reply(self):
        # F4 §1.6: intent must NEVER be populated from real_reply (the held-out
        # ground truth). Even with a long, distinctive real_reply, intent stays
        # decoupled — it is not the reply text, nor any substring derived from it.
        rc = _retro_case()
        rc["real_reply"] = "SECRET_HELD_OUT_GROUND_TRUTH lad os modes fredag kl 14"
        c = Case.from_retro_case(rc)
        assert c.intent == ""
        assert c.real_reply == "SECRET_HELD_OUT_GROUND_TRUTH lad os modes fredag kl 14"
        assert "SECRET_HELD_OUT_GROUND_TRUTH" not in c.intent
        assert c.intent != c.real_reply

    def test_officer_decision_shape(self):
        d = OfficerDecision(decision="draft text", rationale="why", chain=[])
        assert d.decision == "draft text"
        assert d.chain == []


class TestFilterMcpResult:
    def test_redacts_items_at_or_after_cutoff(self):
        result = {"hits": [
            {"date": "2026-06-09T08:00:00+00:00", "text": "before"},
            {"date": "2026-06-10T12:00:00+00:00", "text": "AT cutoff — leak"},
            {"date": "2026-06-11T09:00:00+00:00", "text": "after — leak"},
        ]}
        out = leakguard.filter_mcp_result(result, CUTOFF)
        kept = out["hits"]
        assert len(kept) == 1
        assert kept[0]["text"] == "before"

    def test_redacts_by_edit_date_and_reply_ts_keys(self):
        result = [
            {"edit_date": "2026-06-11T00:00:00+00:00", "v": "leak"},
            {"reply_ts": "2026-06-09T00:00:00+00:00", "v": "ok"},
        ]
        out = leakguard.filter_mcp_result(result, CUTOFF)
        assert len(out) == 1 and out[0]["v"] == "ok"

    def test_passes_through_timestampless_items(self):
        result = {"voice": "tone notes with no timestamp"}
        assert leakguard.filter_mcp_result(result, CUTOFF) == result


class TestThreadCutoffAssertion:
    def test_clean_thread_passes(self):
        leakguard.assert_thread_pre_cutoff(_retro_case()["thread_before"], CUTOFF)

    def test_equal_ts_is_a_leak(self):
        msgs = [{"date": CUTOFF, "text": "equal-ts leak"}]
        with pytest.raises(leakguard.LeakageDetectedError):
            leakguard.assert_thread_pre_cutoff(msgs, CUTOFF)

    def test_after_ts_is_a_leak(self):
        msgs = [{"date": "2026-06-11T00:00:00+00:00", "text": "after"}]
        with pytest.raises(leakguard.LeakageDetectedError):
            leakguard.assert_thread_pre_cutoff(msgs, CUTOFF)


class TestScanForLeaks:
    def test_flags_post_cutoff_timestamp_in_decision_text(self):
        text = "I will reply, scheduling for 2026-06-11T09:00:00+00:00 as discussed."
        leaks = leakguard.scan_for_leaks(text, _retro_case()["thread_before"], CUTOFF)
        assert any("2026-06-11" in s for s in leaks)

    def test_clean_decision_text_no_leaks(self):
        text = "Ja, lad os finde en tid."
        assert leakguard.scan_for_leaks(text, _retro_case()["thread_before"], CUTOFF) == []
