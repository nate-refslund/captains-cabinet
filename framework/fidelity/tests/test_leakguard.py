from __future__ import annotations

from datetime import datetime, timezone

import pytest

from framework.fidelity import leakguard
from framework.fidelity.types import Case, OfficerDecision

CUTOFF = "2026-06-10T12:00:00+00:00"


def _retro_case():
    return {
        "case_id": "abc1234567",
        "reply_key": "msgraph|MID1",
        "slug": "otto",
        "person": "Otto",
        "channel": "msgraph",
        "language": "da",
        "reply_ts": CUTOFF,
        "subject": "Re: lon",
        "n_prior": 3,
        "thread_before": [
            {"slug": "otto", "person": "Otto", "date": "2026-06-09T08:00:00+00:00",
             "direction": "received", "who": "Otto <u@x>", "source": "msgraph",
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
        assert c.channel == "msgraph" and c.slug == "otto"

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

    def test_open_commitment_empty_source_date_future_due_is_kept(self):
        # An open commitment whose source_date is empty but whose `due` is in
        # the future is legitimate as-of-cutoff knowledge — it must be KEPT.
        # `due` is NOT a content-creation key (design §2.1); only source_date /
        # resolved_ts fence a commitment. With `due` excluded from _TS_KEYS,
        # _item_ts finds no creation timestamp (empty source_date is skipped),
        # so the record survives the fence.
        cmt = {"commitment_id": "c1", "text": "send the deck",
               "source_date": "", "due": "2026-12-31T09:00:00+00:00",
               "status": "open"}
        out = leakguard.filter_mcp_result([cmt], CUTOFF)
        assert len(out) == 1
        assert out[0]["commitment_id"] == "c1"

    def test_commitment_source_date_at_or_after_cutoff_is_dropped(self):
        # source_date >= cutoff is a post-cutoff content-creation record → drop.
        cmt = {"commitment_id": "c2", "text": "AFTER promise (leak)",
               "source_date": CUTOFF, "due": "2026-12-31T09:00:00+00:00",
               "status": "open"}
        assert leakguard.filter_mcp_result([cmt], CUTOFF) == []

    def test_commitment_resolved_ts_at_or_after_cutoff_is_dropped(self):
        # resolved_ts >= cutoff means the commitment was resolved after the
        # cutoff — knowing that is a leak → drop.
        cmt = {"commitment_id": "c3", "text": "resolved after cutoff (leak)",
               "source_date": "2026-05-01T09:00:00+00:00",
               "resolved_ts": "2026-06-11T09:00:00+00:00", "status": "resolved"}
        assert leakguard.filter_mcp_result([cmt], CUTOFF) == []

    def test_due_alone_in_future_never_drops_a_record(self):
        # Belt: a record whose ONLY ts-like field is a future `due` is never
        # fenced out — `due` is excluded from _TS_KEYS entirely.
        cmt = {"id": "c4", "due": "2099-01-01T00:00:00+00:00", "text": "open"}
        assert leakguard.filter_mcp_result([cmt], CUTOFF) == [cmt]


class TestDatetimeTypedTimestamps:
    """Audit finding #2a. _item_ts must coerce a datetime/date-typed timestamp
    to an ISO string before the cutoff compare, and scan ALL _TS_KEYS (not stop
    at the first) so an earlier empty/wrong-typed key can't shadow a later
    post-cutoff key. A datetime ts >= cutoff MUST be caught and the record
    dropped by the fence; mtime/datetime values silently bypassing the cutoff
    was the leak."""

    POST_DT = datetime(2026, 6, 11, 9, 0, 0, tzinfo=timezone.utc)
    PRE_DT = datetime(2026, 6, 9, 8, 0, 0, tzinfo=timezone.utc)

    def test_datetime_ts_post_cutoff_is_dropped(self):
        # (a) a DATETIME-typed ts >= cutoff must be DROPPED — previously it
        # failed isinstance(v, str) and silently bypassed the fence.
        rec = {"id": "d1", "ts": self.POST_DT, "text": "datetime post-cutoff (leak)"}
        assert leakguard.filter_mcp_result([rec], CUTOFF) == []

    def test_commitment_empty_source_date_datetime_resolved_ts_dropped(self):
        # (b) empty source_date (earlier key) must NOT shadow a post-cutoff
        # datetime resolved_ts (later key). _item_ts must keep scanning and the
        # post-cutoff resolved_ts must gate the drop.
        cmt = {"commitment_id": "c5", "text": "resolved after cutoff (leak)",
               "source_date": "", "resolved_ts": self.POST_DT, "status": "resolved"}
        assert leakguard.filter_mcp_result([cmt], CUTOFF) == []

    def test_pre_cutoff_datetime_ts_is_kept(self):
        # (c) a pre-cutoff DATETIME ts is legitimate as-of-cutoff content and
        # must be KEPT (coercion must not over-drop).
        rec = {"id": "d2", "ts": self.PRE_DT, "text": "datetime pre-cutoff (ok)"}
        out = leakguard.filter_mcp_result([rec], CUTOFF)
        assert len(out) == 1 and out[0]["id"] == "d2"

    def test_date_typed_value_post_cutoff_is_dropped(self):
        # date (not datetime) post-cutoff must also coerce + gate.
        from datetime import date
        rec = {"id": "d3", "source_date": date(2026, 6, 11), "text": "date leak"}
        assert leakguard.filter_mcp_result([rec], CUTOFF) == []

    def test_item_ts_returns_gating_candidate_when_any_post_cutoff(self):
        # _item_ts contract: with multiple candidates, it returns one that gates
        # (>= cutoff) when any candidate is post-cutoff — a pre-cutoff earlier
        # key must not be returned in preference to a post-cutoff later key.
        item = {"ts": self.PRE_DT, "resolved_ts": self.POST_DT}
        got = leakguard._item_ts(item)
        assert got is not None and got >= CUTOFF
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
