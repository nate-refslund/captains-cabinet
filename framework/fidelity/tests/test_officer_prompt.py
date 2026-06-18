from __future__ import annotations

import pytest

from framework.fidelity import officer_prompt
from framework.fidelity.types import Case

CUTOFF = "2026-06-10T12:00:00+00:00"


def _case():
    return Case.from_retro_case({
        "case_id": "abc1234567", "reply_key": "k", "slug": "ulrik",
        "person": "Ulrik", "channel": "msgraph", "language": "da",
        "reply_ts": CUTOFF, "subject": "Re: lon", "n_prior": 2,
        "thread_before": [
            {"slug": "ulrik", "person": "Ulrik",
             "date": "2026-06-08T08:00:00+00:00", "direction": "sent",
             "who": "Nate", "source": "msgraph", "to": "", "cc": "",
             "text": "Hej, vi tager den i naeste uge."},
            {"slug": "ulrik", "person": "Ulrik",
             "date": "2026-06-09T08:00:00+00:00", "direction": "received",
             "who": "Ulrik <u@x>", "source": "msgraph", "to": "", "cc": "",
             "text": "kan vi snakke lon paa fredag?"},
        ],
        "real_reply": "Ja, fredag passer.",
    })


class TestRoleDefinition:
    def test_missing_role_returns_fallback_not_crash(self):
        out = officer_prompt.role_definition("nonexistent-role-xyz")
        assert isinstance(out, str) and "nonexistent-role-xyz" in out


class TestBuildEvalSystem:
    def test_includes_lane_and_decision_type(self):
        s = officer_prompt.build_eval_system(_case(), "chair")
        assert "send-1to1-reply" in s
        assert "reply" in s

    def test_never_includes_held_out_reply(self):
        s = officer_prompt.build_eval_system(_case(), "chair")
        assert "Ja, fredag passer." not in s


class TestFormatSituation:
    def test_oldest_first_and_both_messages_present(self):
        s = officer_prompt.format_situation(_case())
        i_first = s.index("naeste uge")
        i_last = s.index("snakke lon")
        assert i_first < i_last  # oldest-first

    def test_carries_cutoff_header(self):
        s = officer_prompt.format_situation(_case())
        assert CUTOFF in s
        assert "HELD-OUT SITUATION" in s

    def test_never_includes_held_out_reply(self):
        s = officer_prompt.format_situation(_case())
        assert "Ja, fredag passer." not in s

    def test_sent_messages_labelled_nate(self):
        s = officer_prompt.format_situation(_case())
        assert "Nate:" in s
