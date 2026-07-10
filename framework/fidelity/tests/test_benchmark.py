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
            "case_id": "c1", "reply_key": "k", "slug": "otto", "person": "Otto",
            "channel": "msgraph", "language": "da",
            "reply_ts": "2026-06-10T12:00:00+00:00", "subject": "s", "n_prior": 2,
            "thread_before": [{"date": "2026-06-09T00:00:00+00:00",
                               "direction": "received", "who": "Otto <u@x>",
                               "source": "msgraph", "text": "hej"}],
            "real_reply": "Ja.",
        }
        monkeypatch.setattr(benchmark.retro, "extract_cases",
                            lambda n_cases=24, people_dir=None: [fake_rc])
        # scoreable_only=False: this test exercises retro-case -> Case MAPPING,
        # not the fairness filter; "Ja." is a deliberate degenerate ack fixture.
        cases = benchmark.build_cases(n=1, scoreable_only=False)
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
             "who": "Ada <n@x>", "source": "msgraph",
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
        # scoreable_only=False: the mower fixture's real_reply is a bare URL
        # (deliberate — it proves the intent is NOT contaminated by the reply).
        # The fairness filter would exclude it, so disable it here to exercise
        # the intent path; the filter itself is covered by TestScoreableFilter.
        return benchmark.build_cases(n=1, scoreable_only=False)[0]

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
        # scoreable_only=False: mower fixtures use a bare-URL real_reply.
        cases = benchmark.build_cases(n=2, scoreable_only=False)
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
        # scoreable_only=False: mower fixture's real_reply is a bare URL.
        c = benchmark.build_cases(n=1, scoreable_only=False)[0]
        assert c.intent == "PRESET INTENT"
        assert "called" not in captured, "must not recompute a preset intent"


def _msg(direction, text, date="2026-05-11T09:00:00+00:00"):
    return {"slug": "x", "person": "X", "date": date, "direction": direction,
            "who": "X <x@x>", "source": "msgraph", "to": "", "cc": "",
            "text": text}


def _case(real_reply, thread_before, *, case_id="c"):
    """Minimal Case for fairness-filter tests (mapping path not exercised)."""
    return Case(
        case_id=case_id, lane="send-1to1-reply", decision_type="reply",
        situation_ref=case_id, ground_truth={"real_reply": real_reply},
        endorsement="unknown", cutoff_ts="2026-05-12T12:00:00+00:00",
        source="retrodiction", held_out=True, slug="x", person="X",
        channel="msgraph", language="en", thread_before=thread_before,
        real_reply=real_reply,
    )


# A clean, multi-message thread that asks a real question and gets a
# substantive multi-word reply — the canonical SCOREABLE case.
_CLEAN_THREAD = [
    _msg("sent", "Hej, jeg sender lige status paa publisher-floedet."),
    _msg("received", "Tak! Kan du naa at faa DPA-dokumentet klar inden launch?"),
    _msg("sent", "Ja, jeg kigger paa det nu."),
]
_CLEAN_REPLY = ("Ja, jeg har kigget paa det og DPA-dokumentet er klar nu - "
                "jeg sender det over til dig om lidt.")


class TestScoreableFilter:
    """The scoreable fairness filter (design §25-27): excludes degenerate /
    un-scoreable held-out reply cases so every eval is a fair target."""

    def test_clean_case_is_scoreable(self):
        assert benchmark.is_scoreable(_case(_CLEAN_REPLY, _CLEAN_THREAD))

    def test_empty_reply_excluded(self):
        assert not benchmark.is_scoreable(_case("", _CLEAN_THREAD))

    def test_jwt_dump_excluded(self):
        jwt = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
               "eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdEFGHijklMNOPqrst")
        assert not benchmark.is_scoreable(_case(jwt, _CLEAN_THREAD))

    def test_jwt_anywhere_in_reply_excluded(self):
        reply = "here is the token you wanted: eyJ" + "a" * 20 + " — use it"
        assert not benchmark.is_scoreable(_case(reply, _CLEAN_THREAD))

    def test_bare_url_dump_excluded(self):
        url = "https://www.husqvarna.com/dk/robotplaeneklippere/automower/"
        assert not benchmark.is_scoreable(_case(url, _CLEAN_THREAD))

    def test_mostly_url_reply_excluded(self):
        # >50% of the reply is the URL -> bare-link dump.
        reply = "se her https://example.com/" + "a" * 80
        assert not benchmark.is_scoreable(_case(reply, _CLEAN_THREAD))

    def test_url_with_substantive_prose_kept(self):
        # A link wrapped in a real, multi-word message is still scoreable.
        reply = ("Ja det lyder fornuftigt, jeg har lagt forslaget herunder saa "
                 "vi kan tage en hurtig snak om det: https://example.com/x")
        assert benchmark.is_scoreable(_case(reply, _CLEAN_THREAD))

    def test_substantive_reply_dominated_by_long_url_kept(self):
        # Regression: a real question whose BYTES are mostly a long URL must
        # still be scoreable (>=6 substantive words after stripping). The old
        # >50%-URL byte-ratio rule wrongly excluded real Danish questions that
        # carried long Sheets/Monday links.
        reply = ("Kan du lige tjekke tallene i arket inden vi sender det? "
                 "https://docs.google.com/spreadsheets/d/" + "a" * 90)
        assert benchmark.is_scoreable(_case(reply, _CLEAN_THREAD))

    def test_short_ack_excluded(self):
        for ack in ("Ja.", "Tak! 👌🏻", "okay, Nielsen 👌🏻", "Lyder godt!"):
            assert not benchmark.is_scoreable(_case(ack, _CLEAN_THREAD)), ack

    def test_six_word_reply_is_scoreable(self):
        # Exactly the minimum word count, on a signal-bearing thread.
        assert benchmark.is_scoreable(
            _case("yes one two three four five", _CLEAN_THREAD))

    def test_short_low_signal_thread_excluded(self):
        # <3 exchanges (1 prior + reply = 2) AND no decision-forcing content.
        thread = [_msg("received", "Fik lige set din besked, fint nok.")]
        reply = "Tak skal du have det lyder rigtig godt"  # 8 words, no signal
        assert not benchmark.is_scoreable(_case(reply, thread))

    def test_short_thread_with_question_kept(self):
        # <3 exchanges but the inbound asks a real question -> scoreable.
        thread = [_msg("received",
                       "Kan du naa at review PR'en inden launch i morgen?")]
        reply = "Ja det kan jeg sagtens, jeg kigger paa den nu"
        assert benchmark.is_scoreable(_case(reply, thread))

    def test_short_thread_with_request_keyword_kept(self):
        thread = [_msg("received",
                       "Please recommend a robotplaeneklipper for the new house")]
        reply = "I would go with a wire-free model for that lawn size"
        assert benchmark.is_scoreable(_case(reply, thread))

    def test_filter_does_not_mutate_case(self):
        """LEAK-SAFETY: the filter is read-only — it must never copy real_reply
        into a clone-visible field or otherwise mutate the case."""
        c = _case(_CLEAN_REPLY, [dict(m) for m in _CLEAN_THREAD])
        before_reply = c.real_reply
        before_intent = c.intent
        before_thread = [dict(m) for m in c.thread_before]
        benchmark.is_scoreable(c)
        assert c.real_reply == before_reply
        assert c.intent == before_intent  # still "" — never seeded from reply
        assert c.thread_before == before_thread


class TestBuildCasesFilter:
    """build_cases wiring of the fairness filter: over-fetch, filter, truncate,
    and the scoreable_only=False legacy escape hatch."""

    def _rc(self, case_id, real_reply, thread=None):
        return {
            "case_id": case_id, "reply_key": case_id, "slug": "x", "person": "X",
            "channel": "msgraph", "language": "en",
            "reply_ts": "2026-06-10T12:00:00+00:00", "subject": "s", "n_prior": 2,
            "thread_before": thread if thread is not None else [
                {"date": "2026-06-09T09:00:00+00:00", "direction": "sent",
                 "who": "Ada <n@x>", "source": "msgraph", "text": "status update"},
                {"date": "2026-06-09T10:00:00+00:00", "direction": "received",
                 "who": "X <x@x>", "source": "msgraph",
                 "text": "Can you finish the DPA doc before launch?"},
            ],
            "real_reply": real_reply,
        }

    def test_degenerate_cases_filtered_out(self, monkeypatch):
        # Mix of one clean + several degenerate cases; only the clean survives.
        rcs = [
            self._rc("clean", "Yes I finished the DPA doc and sent it over now"),
            self._rc("ack", "Ja."),
            self._rc("url", "https://example.com/" + "a" * 80),
            self._rc("jwt", "eyJ" + "x" * 30),
        ]
        monkeypatch.setattr(benchmark.retro, "extract_cases",
                            lambda n_cases=24, people_dir=None: rcs)
        cases = benchmark.build_cases(n=24)
        assert [c.case_id for c in cases] == ["clean"]

    def test_scoreable_only_false_keeps_degenerate(self, monkeypatch):
        rcs = [self._rc("ack", "Ja."), self._rc("url", "https://x.example/y")]
        monkeypatch.setattr(benchmark.retro, "extract_cases",
                            lambda n_cases=24, people_dir=None: rcs)
        cases = benchmark.build_cases(n=24, scoreable_only=False)
        assert {c.case_id for c in cases} == {"ack", "url"}

    def test_overfetches_so_result_approximates_n(self, monkeypatch):
        # Universe is 50% degenerate; over-fetch must still fill n=10.
        clean = [self._rc(f"clean{i}",
                          "Yes I finished it and sent the document over to you")
                 for i in range(20)]
        junk = [self._rc(f"junk{i}", "Ja.") for i in range(20)]
        universe = []
        for c, j in zip(clean, junk):
            universe += [c, j]  # interleave clean/junk

        captured = {}

        def _extract(n_cases=24, people_dir=None):
            captured["n_cases"] = n_cases
            return universe[:n_cases]

        monkeypatch.setattr(benchmark.retro, "extract_cases", _extract)
        cases = benchmark.build_cases(n=10)
        # Over-fetched more than n from the extractor...
        assert captured["n_cases"] > 10
        # ...and still returned exactly n scoreable cases, truncated.
        assert len(cases) == 10
        assert all(c.case_id.startswith("clean") for c in cases)

    def test_truncates_to_n(self, monkeypatch):
        rcs = [self._rc(f"clean{i}",
                        "Yes I finished it and sent the document over to you")
               for i in range(30)]
        monkeypatch.setattr(benchmark.retro, "extract_cases",
                            lambda n_cases=24, people_dir=None: rcs[:n_cases])
        cases = benchmark.build_cases(n=5)
        assert len(cases) == 5
