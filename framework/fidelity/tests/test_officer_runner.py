from __future__ import annotations

from pathlib import Path

import pytest

from framework.fidelity import officer_runner, leakguard
from framework.fidelity.types import Case, OfficerDecision


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path


CUTOFF = "2026-06-10T12:00:00+00:00"


def _case():
    return Case.from_retro_case({
        "case_id": "abc1234567",
        "reply_key": "msgraph|MID1",
        "slug": "ulrik", "person": "Ulrik", "channel": "msgraph",
        "language": "da", "reply_ts": CUTOFF, "subject": "Re: lon",
        "n_prior": 3,
        "thread_before": [
            {"slug": "ulrik", "person": "Ulrik",
             "date": "2026-06-09T08:00:00+00:00", "direction": "received",
             "who": "Ulrik <u@x>", "source": "msgraph", "to": "", "cc": "",
             "text": "kan vi snakke lon?"},
        ],
        "real_reply": "Ja, lad os tage det fredag.",
    })


class TestRunCase:
    def test_captures_draft_as_decision(self):
        fake = lambda payload, system, max_tokens=1500, model="claude-sonnet-4-6": \
            "Ja, lad os finde en tid i naeste uge."
        dec = officer_runner.run_case(_case(), "chair", llm=fake)
        assert isinstance(dec, OfficerDecision)
        assert dec.decision == "Ja, lad os finde en tid i naeste uge."
        assert dec.chain == []  # no live MCP chain in F1

    def test_eval_system_prompt_carries_eval_mode_and_cutoff(self):
        seen = {}
        def fake(payload, system, max_tokens=1500, model="claude-sonnet-4-6"):
            seen["system"] = system
            seen["payload"] = payload
            return "ok"
        officer_runner.run_case(_case(), "chair", llm=fake)
        assert "EVALUATION MODE" in seen["system"]
        assert "captured, not executed" in seen["system"]
        assert CUTOFF in seen["system"]
        # the held-out reply is never in the prompt
        assert "Ja, lad os tage det fredag." not in seen["system"]
        assert "Ja, lad os tage det fredag." not in seen["payload"]

    def test_thread_leak_hard_fails_and_emits(self, event_log_dir):
        c = _case()
        c.thread_before = [{"date": CUTOFF, "direction": "received",
                            "who": "x", "source": "msgraph", "text": "equal-ts leak"}]
        with pytest.raises(leakguard.LeakageDetectedError):
            officer_runner.run_case(c, "chair",
                                    llm=lambda *a, **k: "should never run")
        cfiles = list(Path(event_log_dir).glob("consequence-events-*.jsonl"))
        assert cfiles, "leak event not emitted"
        assert "fidelity-case-leak-detected" in cfiles[0].read_text()

    def test_output_leak_hard_fails(self):
        fake = lambda *a, **k: "Sure, meeting set for 2026-06-11T09:00:00+00:00."
        with pytest.raises(leakguard.LeakageDetectedError):
            officer_runner.run_case(_case(), "chair", llm=fake)

    def test_clean_case_emits_case_evaluated(self, event_log_dir):
        officer_runner.run_case(_case(), "chair",
                                llm=lambda *a, **k: "Ja, fredag passer fint.")
        cfiles = list(Path(event_log_dir).glob("consequence-events-*.jsonl"))
        assert "fidelity-case-evaluated" in cfiles[0].read_text()

    def test_emit_events_false_skips_ledger(self, event_log_dir):
        officer_runner.run_case(_case(), "chair",
                                llm=lambda *a, **k: "Ja.", emit_events=False)
        assert not list(Path(event_log_dir).glob("consequence-events-*.jsonl"))
