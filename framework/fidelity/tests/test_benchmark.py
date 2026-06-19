from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.fidelity import benchmark, officer_prompt
from framework.fidelity.types import Case


def _write_outcomes(tmp_path) -> Path:
    rows = [
        {"ts": "2026-06-07T21:05:48+00:00", "lane": "send-1to1-reply",
         "action_id": "backfill-sent|MID1", "mode": "shadow", "source": "backfill",
         "would_text": "cut...", "nate_text": "cut...", "match": False},
        {"ts": "2026-06-07T21:05:49+00:00", "lane": "send-1to1-reply",
         "action_id": "backfill-sent|MID2", "mode": "shadow", "source": "backfill",
         "would_text": "cut...", "nate_text": "cut...", "match": True},
        {"ts": "2026-06-07T21:05:50+00:00", "lane": "some-other-lane",
         "action_id": "x", "mode": "shadow", "source": "backfill",
         "would_text": "t", "nate_text": "t", "match": False},
    ]
    p = tmp_path / "autonomy_outcomes.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


class TestAutonomyUniverse:
    def test_filters_to_lane(self, tmp_path):
        p = _write_outcomes(tmp_path)
        rows = benchmark.load_autonomy_rows(path=p)
        assert len(rows) == 2
        assert all(r["lane"] == "send-1to1-reply" for r in rows)

    def test_validation_count_is_universe_size(self, tmp_path):
        p = _write_outcomes(tmp_path)
        assert benchmark.validation_count(path=p) == 2

    def test_missing_file_is_zero(self, tmp_path):
        assert benchmark.validation_count(path=tmp_path / "nope.jsonl") == 0


class TestBuildCases:
    def test_maps_retro_cases_to_case_objects(self, monkeypatch):
        fake_rc = {
            "case_id": "c1", "reply_key": "k", "slug": "ulrik", "person": "Ulrik",
            "channel": "msgraph", "language": "da",
            "reply_ts": "2026-06-10T12:00:00+00:00", "subject": "s", "n_prior": 2,
            "thread_before": [{"date": "2026-06-09T00:00:00+00:00",
                               "direction": "received", "who": "Ulrik <u@x>",
                               "source": "msgraph", "text": "hej"}],
            "real_reply": "Ja.",
        }
        monkeypatch.setattr(benchmark.retro, "extract_cases",
                            lambda n_cases=24, people_dir=None: [fake_rc])
        cases = benchmark.build_cases(n=1)
        assert len(cases) == 1
        c = cases[0]
        assert isinstance(c, Case)
        assert c.lane == "send-1to1-reply"
        assert c.decision_type == "reply"
        assert c.cutoff_ts == "2026-06-10T12:00:00+00:00"
        assert c.real_reply == "Ja."

    def test_empty_extract_yields_no_cases(self, monkeypatch):
        monkeypatch.setattr(benchmark.retro, "extract_cases",
                            lambda n_cases=24, people_dir=None: [])
        assert benchmark.build_cases(n=0) == []

    def test_unsupported_cell_raises(self):
        with pytest.raises(NotImplementedError):
            benchmark.build_cases(lane="triage", decision_type="triage", n=1)


def _mower_rc():
    """A retro-case dict whose thread is about a robotic mower for the new
    house, with a held-out real_reply that pastes a Husqvarna URL. The reply
    carries a token ('husqvarna') that does NOT appear anywhere in the thread,
    so a benchmark intent contaminated by real_reply is detectable."""
    return {
        "case_id": "mower1", "reply_key": "k", "slug": "lars", "person": "Lars",
        "channel": "msgraph", "language": "da",
        "reply_ts": "2026-05-12T12:00:00+00:00", "subject": "s", "n_prior": 2,
        "thread_before": [
            {"date": "2026-05-11T09:00:00+00:00", "direction": "sent",
             "who": "Nate <n@x>", "source": "msgraph",
             "text": "Vi har lige overtaget huset med en stor plæne."},
            {"date": "2026-05-11T10:00:00+00:00", "direction": "received",
             "who": "Lars <l@x>", "source": "msgraph",
             "text": "Kan du anbefale en robotplæneklipper uden afgraensningskabel?"},
        ],
        "real_reply": "https://www.husqvarna.com/dk/robotplaeneklippere/automower/",
    }


class TestBenchmarkIntent:
    """F4 T7 (design §5, §1.6): build_cases caches a reconstructed intent on
    each Case, derived from the pre-cutoff thread ONLY — never from real_reply,
    and kept out of any index."""

    def _build_one(self, monkeypatch, rc):
        monkeypatch.setattr(benchmark.retro, "extract_cases",
                            lambda n_cases=24, people_dir=None: [rc])
        return benchmark.build_cases(n=1)[0]

    def test_built_case_carries_nonempty_intent(self, monkeypatch):
        c = self._build_one(monkeypatch, _mower_rc())
        assert c.intent, "build_cases must populate Case.intent"
        assert isinstance(c.intent, str)

    def test_intent_derived_from_thread_not_real_reply(self, monkeypatch):
        rc = _mower_rc()
        c = self._build_one(monkeypatch, rc)
        intent_lc = c.intent.lower()
        # A token unique to the held-out reply must NOT leak into the intent.
        assert "husqvarna" not in intent_lc
        assert "automower" not in intent_lc
        # A token from the pre-cutoff thread SHOULD ground the intent.
        assert "robotpl" in intent_lc or "lars" in intent_lc

    def test_intent_equals_pure_function_of_thread(self, monkeypatch):
        """The cached intent must equal intent_and_context(case) computed from
        the thread alone — i.e. it is exactly the pure reconstruction, with no
        real_reply contribution. Blanking real_reply must not change it."""
        rc = _mower_rc()
        c = self._build_one(monkeypatch, rc)
        c_noreply = Case.from_retro_case(rc)
        c_noreply.real_reply = ""
        c_noreply.ground_truth = {"real_reply": ""}
        expected = officer_prompt.intent_and_context(c_noreply)["reconstructed_intent"]
        assert c.intent == expected

    def test_every_case_gets_intent(self, monkeypatch):
        rcs = [_mower_rc(), {**_mower_rc(), "case_id": "mower2"}]
        monkeypatch.setattr(benchmark.retro, "extract_cases",
                            lambda n_cases=24, people_dir=None: rcs)
        cases = benchmark.build_cases(n=2)
        assert len(cases) == 2
        assert all(c.intent for c in cases)

    def test_preexisting_intent_not_overwritten(self, monkeypatch):
        """If a case already carries an intent (a refreshed benchmark), the
        cached value is preserved — enrichment is lazy (fill-if-empty)."""
        rc = _mower_rc()
        captured = {}
        real_ic = officer_prompt.intent_and_context

        def _spy(case):
            captured["called"] = True
            return real_ic(case)

        monkeypatch.setattr(benchmark, "intent_and_context", _spy)
        monkeypatch.setattr(benchmark.retro, "extract_cases",
                            lambda n_cases=24, people_dir=None: [rc])
        # Force Case.from_retro_case to yield a pre-populated intent.
        orig_from = Case.from_retro_case

        def _from(rcd, lane="send-1to1-reply", decision_type="reply"):
            c = orig_from(rcd, lane=lane, decision_type=decision_type)
            c.intent = "PRESET INTENT"
            return c

        monkeypatch.setattr(benchmark.Case, "from_retro_case",
                            staticmethod(_from))
        c = benchmark.build_cases(n=1)[0]
        assert c.intent == "PRESET INTENT"
        assert "called" not in captured, "must not recompute a preset intent"
