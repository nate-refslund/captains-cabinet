"""F4 T5 — intent judge + DETERMINISTIC anti-rubber-stamp guard.

Tests the scorer.judge_with_oauth extension (design §3.1-§3.3, §1.4): the
INTENT_RUBRIC is appended after a divider (JUDGE_SYSTEM stays pristine), the
judge returns BOTH verdicts (decision-first), and the programmatic grounding +
topic-overlap guards force ``intent-divergent`` BEFORE any intent credit is
granted on a divergent decision.

The guards run over ``thread_before`` + the fenced ``full_cutoff_context``
ONLY — never ``real_reply`` (the held-out ground truth). All tests monkeypatch
``scorer.oauth_json_llm`` so no real OAuth/subprocess/network call is made.
"""

from __future__ import annotations

import pytest

from framework.fidelity import scorer

CUTOFF = "2026-05-06T12:00:00+00:00"


def _mower_case_dict():
    """Retro-case dict: a thread asking for help finding a robotic mower for a
    large lawn at the new house. real_reply is the held-out ground truth and
    MUST never reach the judge payload or the deterministic guards."""
    return {
        "case_id": "mower12345",
        "reply_key": "k",
        "slug": "bo",
        "person": "Bo",
        "channel": "msgraph",
        "language": "da",
        "reply_ts": CUTOFF,
        "thread_before": [
            {"direction": "sent", "who": "Nate",
             "date": "2026-05-04T08:00:00+00:00", "source": "msgraph",
             "text": "Ja, 3000 m2 graesplaene paa Mosevraavej. Ingen kanttraad."},
            {"direction": "received", "who": "Bo <b@x>",
             "date": "2026-05-05T08:00:00+00:00", "source": "msgraph",
             "text": "Vil du have hjaelp til at finde en robotplaeneklipper?"},
        ],
        "real_reply": "Her er en Husqvarna-link HEMMELIGT-SVAR.",
    }


_MOWER_INTENT = ("Goal: source a no-boundary-wire robotic mower "
                 "(robotplaeneklipper) for the 3000 m2 lawn. "
                 "Core: decisive, concrete, da on msgraph.")
_MOWER_CTX = {
    "vault_hits": [{"ts": "2026-05-02T08:00:00+00:00",
                    "text": "new house Mosevraavej, ~3000 m2 lawn"}],
}


# ---------------------------------------------------------------------------
# the two required T5 tests
# ---------------------------------------------------------------------------

class TestHallucinatedGroundForcedDivergent:
    def test_hallucinated_ground_forced_divergent(self, monkeypatch):
        """Judge returns intent-aligned with an intent_grounded_fact that is
        ABSENT from thread_before + full_cutoff_context → §3.2 grounding check
        forces intent-divergent and stamps the FORCED reason (the credit is
        revoked deterministically, not on the judge's word)."""
        calls = {"n": 0}

        def fake_oauth_json(payload, system, max_tokens=400,
                            model="claude-sonnet-4-6"):
            calls["n"] += 1
            # First call = decision pass (JUDGE_SYSTEM); second = intent pass.
            if calls["n"] == 1:
                return {"verdict": "divergent", "rationale": "diff surface",
                        "what_diverged": "no link", "real_decision": "",
                        "draft_decision": ""}
            return {
                "intent_verdict": "intent-aligned",
                "intent_rationale": "serves the mower goal",
                "intent_what_diverged": "",
                # A plausible-sounding but FABRICATED ground (no submarine
                # anywhere in the cutoff material).
                "intent_grounded_fact": ("From Bo at 2026-05-05: Nate already "
                                         "ordered a submarine and a yacht."),
            }

        monkeypatch.setattr(scorer, "oauth_json_llm", fake_oauth_json)
        out = scorer.judge_with_oauth(
            _mower_case_dict(),
            clone_draft="Jeg anbefaler en LiDAR-robotplaeneklipper til 3000 m2.",
            reconstructed_intent=_MOWER_INTENT,
            full_cutoff_context=_MOWER_CTX,
        )
        # decision verdict preserved, decision-first
        assert out["verdict"] == "divergent"
        # intent credit revoked deterministically
        assert out["intent_verdict"] == "intent-divergent"
        assert out["intent_grounded_fact"].startswith("FORCED:")

    def test_grounded_fact_present_is_not_forced(self, monkeypatch):
        """Control: when the cited ground actually exists in the cutoff
        material, the intent-aligned verdict survives the guard (the guard is
        not a blanket reject)."""
        calls = {"n": 0}

        def fake_oauth_json(payload, system, max_tokens=400,
                            model="claude-sonnet-4-6"):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"verdict": "divergent", "rationale": "",
                        "what_diverged": "", "real_decision": "",
                        "draft_decision": ""}
            return {
                "intent_verdict": "intent-aligned",
                "intent_rationale": "serves the mower goal",
                "intent_what_diverged": "",
                "intent_grounded_fact": ("From Bo at 2026-05-05: finde en "
                                         "robotplaeneklipper."),
            }

        monkeypatch.setattr(scorer, "oauth_json_llm", fake_oauth_json)
        out = scorer.judge_with_oauth(
            _mower_case_dict(),
            # An on-intent draft naturally echoes the goal vocabulary (robotic
            # mower, no boundary wire, the 3000 m2 lawn) — well above the floor.
            clone_draft=("Til din 3000 m2 lawn anbefaler jeg en robotic "
                         "robotplaeneklipper helt uden boundary wire."),
            reconstructed_intent=_MOWER_INTENT,
            full_cutoff_context=_MOWER_CTX,
        )
        assert out["intent_verdict"] == "intent-aligned"
        assert not out["intent_grounded_fact"].startswith("FORCED:")


class TestOfftopicForcedDivergent:
    def test_offtopic_forced_divergent(self, monkeypatch):
        """Draft topic disjoint from reconstructed_intent (token Jaccard <
        0.15) → §3.3b topic-overlap floor forces intent-divergent regardless of
        the LLM's verdict (reply was about the mower; draft is about vacuums)."""
        calls = {"n": 0}

        def fake_oauth_json(payload, system, max_tokens=400,
                            model="claude-sonnet-4-6"):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"verdict": "divergent", "rationale": "",
                        "what_diverged": "", "real_decision": "",
                        "draft_decision": ""}
            # The LLM (wrongly) credits the off-topic draft.
            return {
                "intent_verdict": "intent-aligned",
                "intent_rationale": "looks helpful",
                "intent_what_diverged": "",
                "intent_grounded_fact": ("From Bo at 2026-05-05: wants help "
                                         "finding a robotplaeneklipper."),
            }

        monkeypatch.setattr(scorer, "oauth_json_llm", fake_oauth_json)
        out = scorer.judge_with_oauth(
            _mower_case_dict(),
            # Off-topic: vacuum cleaners, nothing about the lawn/mower goal.
            clone_draft="Koeb en Dyson stoevsuger til stuen, super sugekraft.",
            reconstructed_intent=_MOWER_INTENT,
            full_cutoff_context=_MOWER_CTX,
        )
        assert out["verdict"] == "divergent"
        assert out["intent_verdict"] == "intent-divergent"
        assert "topic" in out["intent_grounded_fact"].lower()


# ---------------------------------------------------------------------------
# deterministic helper unit tests (the guard is a fact, not a promise)
# ---------------------------------------------------------------------------

class TestGroundingHelper:
    def test_substring_match_passes(self):
        # The mandated citation form quotes an EXCERPT drawn from the material;
        # the excerpt here is a verbatim substring of the thread.
        assert scorer._grounding_ok(
            "From Bo at 2026-05-05: finde en robotplaeneklipper",
            ctx_text="",
            thread_text="Bo: vil du have hjaelp til at finde en "
                        "robotplaeneklipper?") is True

    def test_absent_fact_fails(self):
        assert scorer._grounding_ok(
            "Nate already ordered a submarine and a yacht",
            ctx_text="new house Mosevraavej ~3000 m2 lawn",
            thread_text="Bo: finde en robotplaeneklipper?") is False

    def test_high_token_overlap_passes_without_exact_substring(self):
        # Reordered/partial wording but >=0.6 token Jaccard with the haystack.
        assert scorer._grounding_ok(
            "robotplaeneklipper lawn mower help",
            ctx_text="lawn mower",
            thread_text="help finding a robotplaeneklipper") is True

    def test_empty_fact_fails(self):
        # An empty/whitespace ground is not a citation — must not pass.
        assert scorer._grounding_ok("   ", ctx_text="anything",
                                    thread_text="anything else") is False


class TestTokenJaccard:
    def test_disjoint_is_zero(self):
        assert scorer._token_jaccard("dyson stoevsuger stue",
                                     "robotplaeneklipper graesplaene") == 0.0

    def test_identical_is_one(self):
        assert scorer._token_jaccard("a b c", "c b a") == 1.0

    def test_partial_overlap_between_zero_and_one(self):
        j = scorer._token_jaccard("a b c d", "c d e f")
        assert 0.0 < j < 1.0


class TestIntentRubricLayering:
    def test_intent_rubric_constant_exists_and_is_separate(self):
        # INTENT_RUBRIC is appended after a divider; JUDGE_SYSTEM stays pristine.
        assert "intent-aligned" in scorer.INTENT_RUBRIC
        assert "intent_grounded_fact" in scorer.INTENT_RUBRIC
        # The pristine decision rubric must not have grown the intent keys.
        assert "intent_verdict" not in scorer.retro.JUDGE_SYSTEM

    def test_intent_pass_system_includes_both_rubrics(self, monkeypatch):
        """The intent OAuth call must carry JUDGE_SYSTEM + INTENT_RUBRIC; the
        decision call carries the pristine JUDGE_SYSTEM."""
        systems = []
        calls = {"n": 0}

        def fake_oauth_json(payload, system, max_tokens=400,
                            model="claude-sonnet-4-6"):
            calls["n"] += 1
            systems.append(system)
            if calls["n"] == 1:
                return {"verdict": "match", "rationale": "", "what_diverged": "",
                        "real_decision": "", "draft_decision": ""}
            return {"intent_verdict": "intent-aligned", "intent_rationale": "",
                    "intent_what_diverged": "",
                    "intent_grounded_fact": "From Bo at 2026-05-05: "
                                            "robotplaeneklipper."}

        monkeypatch.setattr(scorer, "oauth_json_llm", fake_oauth_json)
        scorer.judge_with_oauth(
            _mower_case_dict(),
            clone_draft="robotplaeneklipper anbefaling til graesplaenen",
            reconstructed_intent=_MOWER_INTENT,
            full_cutoff_context=_MOWER_CTX,
        )
        # decision pass: pristine JUDGE_SYSTEM, no INTENT_RUBRIC
        assert scorer.INTENT_RUBRIC not in systems[0]
        # intent pass: both rubrics present
        assert scorer.INTENT_RUBRIC in systems[1]
        assert "IGNORE style" in systems[1]  # JUDGE_SYSTEM body carried


class TestJudgePayloadNoLeak:
    def test_real_reply_never_in_intent_payload(self, monkeypatch):
        """The intent pass payload must contain the reconstructed intent + the
        fenced context but NEVER real_reply (the held-out answer)."""
        payloads = []
        calls = {"n": 0}

        def fake_oauth_json(payload, system, max_tokens=400,
                            model="claude-sonnet-4-6"):
            calls["n"] += 1
            payloads.append(payload)
            if calls["n"] == 1:
                return {"verdict": "divergent", "rationale": "",
                        "what_diverged": "", "real_decision": "",
                        "draft_decision": ""}
            return {"intent_verdict": "intent-partial", "intent_rationale": "",
                    "intent_what_diverged": "",
                    "intent_grounded_fact": "From Bo at 2026-05-05: "
                                            "robotplaeneklipper."}

        monkeypatch.setattr(scorer, "oauth_json_llm", fake_oauth_json)
        scorer.judge_with_oauth(
            _mower_case_dict(),
            clone_draft="robotplaeneklipper anbefaling til graesplaenen",
            reconstructed_intent=_MOWER_INTENT,
            full_cutoff_context=_MOWER_CTX,
        )
        intent_payload = payloads[1]
        assert "HEMMELIGT-SVAR" not in intent_payload  # held-out reply excluded
        assert "RECONSTRUCTED INTENT" in intent_payload
        assert "FULL CUTOFF-SAFE CONTEXT" in intent_payload
        assert "robotplaeneklipper" in intent_payload  # intent text present


class TestBackwardCompatibleSignature:
    def test_legacy_two_arg_call_returns_decision_only(self, monkeypatch):
        """Calling judge_with_oauth with no intent args (the F1/T-prior call
        shape) returns the decision verdict and an empty intent layer — no
        second OAuth call is made (intent layer unavailable → '')."""
        calls = {"n": 0}

        def fake_oauth_json(payload, system, max_tokens=400,
                            model="claude-sonnet-4-6"):
            calls["n"] += 1
            return {"verdict": "match", "rationale": "same call",
                    "what_diverged": "", "real_decision": "ja",
                    "draft_decision": "ja"}

        monkeypatch.setattr(scorer, "oauth_json_llm", fake_oauth_json)
        out = scorer.judge_with_oauth(_mower_case_dict(), "Ja.")
        assert out["verdict"] == "match"
        assert out.get("intent_verdict", "") == ""
        assert calls["n"] == 1  # only the decision pass ran


# ---------------------------------------------------------------------------
# F4 T6 — composite blend (design §3.4) + CaseScore intent fields (§1.5, §8)
# ---------------------------------------------------------------------------

class TestCompositeBlend:
    """The decision-dominant, intent-penalizing blend (design §3.4).

        composite(dec, intent):
            dec_score = _DEC[dec]
            if intent in ("error",""): return dec_score   # F1 fallback
            if intent == "intent-divergent": return 0.0    # hollow/off-intent
            return max(dec_score, _INTENT[intent])         # credit the better
    """

    # The §3.4 worked-quadrants table, asserted EXACTLY.
    @pytest.mark.parametrize("dec, intent, expected", [
        ("match", "intent-aligned", 1.0),       # literal + on-intent (gold)
        ("match", "intent-divergent", 0.0),     # echoed words, missed goal -> ZERO
        ("divergent", "intent-aligned", 1.0),   # different/better, same intent (F4 path)
        ("divergent", "intent-divergent", 0.0),  # wrong action, wrong intent
        ("partial", "intent-aligned", 1.0),     # hedged literally but served goal
        ("partial", "intent-partial", 0.5),     # partial on both axes
        ("match", "error", 1.0),                # intent layer failed -> _DEC[match]
    ])
    def test_seven_quadrant_table_exact(self, dec, intent, expected):
        assert scorer.composite(dec, intent) == expected

    def test_match_intent_divergent_is_zero(self):
        # A surface-match whose intent missed the goal is gated to ZERO, not
        # rubber-stamped (the §3.4 intent-divergent branch is load-bearing).
        assert scorer.composite("match", "intent-divergent") == 0.0

    def test_divergent_intent_aligned_is_one(self):
        # The Husqvarna credit path: different surface, same intent -> 1.0.
        assert scorer.composite("divergent", "intent-aligned") == 1.0

    def test_intent_error_falls_back(self):
        # intent layer unavailable ("error") -> decision-only fallback == _DEC[dec].
        for dec in ("match", "partial", "divergent", "skipped"):
            assert scorer.composite(dec, "error") == scorer._DEC.get(dec, 0.0)

    def test_empty_intent_falls_back(self):
        # An empty intent verdict ("") is the F1 decision-only path too.
        for dec in ("match", "partial", "divergent"):
            assert scorer.composite(dec, "") == scorer._DEC.get(dec, 0.0)

    def test_dec_alias_matches_existing_composite_table(self):
        # _DEC is the design's name for the existing decision table; same values.
        assert scorer._DEC["match"] == 1.0
        assert scorer._DEC["partial"] == 0.5
        assert scorer._DEC["divergent"] == 0.0
        assert scorer._DEC["error"] == 0.0

    def test_intent_table_values(self):
        assert scorer._INTENT == {"intent-aligned": 1.0, "intent-partial": 0.5,
                                  "intent-divergent": 0.0, "error": 0.0}


class TestScoreIntentFields:
    """``score(..., intent_ctx=...)`` threads the intent context to the judge
    and exposes the intent axis on the CaseScore row (design §1.5, §8)."""

    def _case(self):
        from framework.fidelity.types import Case
        return Case.from_retro_case(_mower_case_dict())

    def _decision(self, text):
        from framework.fidelity.types import OfficerDecision
        return OfficerDecision(decision=text, rationale="", chain=[])

    def _fake_embedder(self, texts):
        return [[float(len(t or "")), 1.0, 0.0] for t in texts]

    def test_default_no_intent_ctx_is_decision_only(self, monkeypatch):
        """With no intent_ctx, the intent layer is empty and composite ==
        decision-only (F1 behavior unchanged — no regression)."""
        monkeypatch.setattr(
            scorer, "judge_with_oauth",
            lambda cd, draft: {"verdict": "match", "rationale": "",
                               "what_diverged": "", "real_decision": "",
                               "draft_decision": ""})
        cs = scorer.score(self._case(), self._decision("Ja."),
                          baseline_draft="x",
                          centroids={"msgraph": [1.0, 1.0, 0.0]},
                          embedder=self._fake_embedder)
        assert cs.decision_verdict == "match"
        assert cs.composite == 1.0
        assert cs.intent_verdict == ""
        assert cs.intent_grounded_fact == ""
        assert cs.intent_composite == 1.0  # composite("match","") == _DEC[match]

    def test_intent_ctx_threads_to_judge_and_credits_divergence(
            self, monkeypatch):
        """intent_ctx supplied -> judge receives reconstructed_intent +
        full_cutoff_context; a divergent decision with intent-aligned earns the
        F4 credit (intent_composite 1.0) while decision_verdict stays divergent
        (decision-first, still on the row)."""
        captured = {}

        def fake_judge(cd, draft, reconstructed_intent="",
                       full_cutoff_context=None):
            captured["intent"] = reconstructed_intent
            captured["ctx"] = full_cutoff_context
            return {"verdict": "divergent", "rationale": "", "what_diverged": "",
                    "real_decision": "", "draft_decision": "",
                    "intent_verdict": "intent-aligned", "intent_rationale": "",
                    "intent_what_diverged": "",
                    "intent_grounded_fact": "From Bo at 2026-05-05: mower."}

        monkeypatch.setattr(scorer, "judge_with_oauth", fake_judge)
        cs = scorer.score(
            self._case(), self._decision("LiDAR robotplaeneklipper anbefaling"),
            baseline_draft="x", centroids={"msgraph": [1.0, 1.0, 0.0]},
            embedder=self._fake_embedder,
            intent_ctx={"reconstructed_intent": _MOWER_INTENT,
                        "full_cutoff_context": _MOWER_CTX})
        assert captured["intent"] == _MOWER_INTENT
        assert captured["ctx"] == _MOWER_CTX
        assert cs.decision_verdict == "divergent"   # decision-first, preserved
        assert cs.intent_verdict == "intent-aligned"
        assert cs.intent_grounded_fact == "From Bo at 2026-05-05: mower."
        assert cs.intent_composite == 1.0           # max(_DEC[divergent], 1.0)

    def test_intent_ctx_hollow_match_gated_to_zero(self, monkeypatch):
        """A surface-match whose intent the judge flags divergent -> the row's
        intent_composite is 0.0 (the §3.4 gate fires through score)."""
        def fake_judge(cd, draft, reconstructed_intent="",
                       full_cutoff_context=None):
            return {"verdict": "match", "rationale": "", "what_diverged": "",
                    "real_decision": "", "draft_decision": "",
                    "intent_verdict": "intent-divergent", "intent_rationale": "",
                    "intent_what_diverged": "missed goal",
                    "intent_grounded_fact": "FORCED: ..."}

        monkeypatch.setattr(scorer, "judge_with_oauth", fake_judge)
        cs = scorer.score(
            self._case(), self._decision("echo"),
            baseline_draft="x", centroids={"msgraph": [1.0, 1.0, 0.0]},
            embedder=self._fake_embedder,
            intent_ctx={"reconstructed_intent": _MOWER_INTENT,
                        "full_cutoff_context": _MOWER_CTX})
        assert cs.decision_verdict == "match"       # decision-first, visible
        assert cs.intent_verdict == "intent-divergent"
        assert cs.intent_composite == 0.0           # hollow match -> ZERO

    def test_intent_ctx_uses_case_intent_when_no_reconstructed(
            self, monkeypatch):
        """If intent_ctx omits reconstructed_intent, score falls back to
        case.intent (cached benchmark intent) so a refreshed benchmark needs no
        recomputation (design §1.5/§1.6)."""
        captured = {}

        def fake_judge(cd, draft, reconstructed_intent="",
                       full_cutoff_context=None):
            captured["intent"] = reconstructed_intent
            return {"verdict": "divergent", "rationale": "", "what_diverged": "",
                    "real_decision": "", "draft_decision": "",
                    "intent_verdict": "intent-partial", "intent_rationale": "",
                    "intent_what_diverged": "",
                    "intent_grounded_fact": "From Bo at 2026-05-05: mower."}

        monkeypatch.setattr(scorer, "judge_with_oauth", fake_judge)
        case = self._case()
        case.intent = "Goal: cached mower intent. Core: decisive."
        cs = scorer.score(
            case, self._decision("anbefaling"),
            baseline_draft="x", centroids={"msgraph": [1.0, 1.0, 0.0]},
            embedder=self._fake_embedder,
            intent_ctx={"full_cutoff_context": _MOWER_CTX})
        assert captured["intent"] == "Goal: cached mower intent. Core: decisive."
        assert cs.intent_verdict == "intent-partial"
        assert cs.intent_composite == 0.5           # max(_DEC[divergent], 0.5)
