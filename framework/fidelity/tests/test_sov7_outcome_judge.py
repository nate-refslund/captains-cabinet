"""SOV-7 / D17 — the OUTCOME_RUBRIC pass-3 judge (AGB axis) in scorer.py.

The personal-agent reframe: clone_draft vs the held-out real_reply as
ANONYMIZED CANDIDATE A/B (assignment = sha256(case_id) parity), judged ONLY
against the reconstructed intent + fenced cutoff context. Verified here:
  - A/B assignment determinism + corpus balance;
  - winner→verdict mapping respects the parity (both orders);
  - deterministic guards reuse _topic_overlap/_grounding_ok verbatim:
    forced-WORSE on an off-topic clone credit, forced-INCOMPARABLE on a
    fabricated citation (incl. a citation drawn from real_reply itself — the
    grounding haystack must exclude the candidates);
  - the no-intent path stays byte-identical to F1 (one OAuth call, no new
    keys);
  - retro.JUDGE_SYSTEM stays pristine (the outcome pass is standalone);
  - score() carries outcome_verdict/outcome_grounded_fact onto CaseScore.

All LLM calls are monkeypatched — no OAuth/subprocess/network.
"""

from __future__ import annotations

import pytest

from framework.fidelity.retro import retro_available

if not retro_available():  # flavor-A coupling — mirror the conftest guard
    pytest.skip("screenpipe retrodiction lib absent (flavor-A coupling)",
                allow_module_level=True)

from framework.fidelity import scorer

CUTOFF = "2026-05-06T12:00:00+00:00"


def _mower_case_dict(case_id="mower12345"):
    """Same shape as test_f4_judge: thread about sourcing a robotic mower.
    real_reply is the held-out ground truth — in THIS pass it legitimately
    reaches the judge as an anonymized candidate, but never the guards."""
    return {
        "case_id": case_id,
        "reply_key": "k",
        "slug": "bo",
        "person": "Bo",
        "channel": "msgraph",
        "language": "da",
        "reply_ts": CUTOFF,
        "thread_before": [
            {"direction": "sent", "who": "Ada",
             "date": "2026-05-04T08:00:00+00:00", "source": "msgraph",
             "text": "Ja, 2500 m2 graesplaene paa Eksempelvej. Ingen kanttraad."},
            {"direction": "received", "who": "Bo <b@x>",
             "date": "2026-05-05T08:00:00+00:00", "source": "msgraph",
             "text": "Vil du have hjaelp til at finde en robotplaeneklipper?"},
        ],
        "real_reply": "Her er en Acme-link HEMMELIGT-SVAR.",
    }


_MOWER_INTENT = ("Goal: source a no-boundary-wire robotic mower "
                 "(robotplaeneklipper) for the 2500 m2 lawn. "
                 "Core: decisive, concrete, da on msgraph.")
_MOWER_CTX = {
    "vault_hits": [{"ts": "2026-05-02T08:00:00+00:00",
                    "text": "new house Eksempelvej, ~2500 m2 lawn"}],
}
# An on-topic clone draft (clears the §3.3b floor against _MOWER_INTENT).
_ONTOPIC_DRAFT = ("Til din 2500 m2 lawn anbefaler jeg en robotic "
                  "robotplaeneklipper helt uden boundary wire.")
# A ground that genuinely exists in the thread (passes _grounding_ok).
_REAL_GROUND = "From Bo at 2026-05-05: finde en robotplaeneklipper."


def _id_with_parity(clone_is_a: bool) -> str:
    """Deterministically find a case_id whose A/B assignment has the wanted
    orientation (self-validating — no hardcoded hash assumptions)."""
    i = 0
    while True:
        cid = f"case{i:04d}"
        if scorer.outcome_ab_clone_is_a(cid) == clone_is_a:
            return cid
        i += 1


def _three_pass_fake(outcome_res, intent_res=None, decision_verdict="match"):
    """Fake oauth_json_llm: call 1 = decision, call 2 = intent, call 3 =
    outcome. Records systems + payloads for assertions."""
    seen = {"systems": [], "payloads": [], "n": 0}
    intent_res = intent_res or {
        "intent_verdict": "intent-aligned", "intent_rationale": "",
        "intent_what_diverged": "", "intent_grounded_fact": _REAL_GROUND,
    }

    def fake(payload, system, max_tokens=400, model="claude-sonnet-4-6"):
        seen["n"] += 1
        seen["systems"].append(system)
        seen["payloads"].append(payload)
        if seen["n"] == 1:
            return {"verdict": decision_verdict, "rationale": "",
                    "what_diverged": "", "real_decision": "",
                    "draft_decision": ""}
        if seen["n"] == 2:
            return intent_res
        return outcome_res

    return fake, seen


# ---------------------------------------------------------------------------
# A/B assignment — determinism + balance
# ---------------------------------------------------------------------------

class TestABAssignment:
    def test_deterministic_per_case(self):
        for cid in ("mower12345", "abc1234567", ""):
            first = scorer.outcome_ab_clone_is_a(cid)
            assert all(scorer.outcome_ab_clone_is_a(cid) == first
                       for _ in range(50))

    def test_balanced_across_corpus(self):
        # sha256 first-byte parity over 400 ids: both orders occur, roughly
        # half each (generous band — this pins balance, not exact halves).
        ids = [f"case-{i}" for i in range(400)]
        a_frac = sum(scorer.outcome_ab_clone_is_a(c) for c in ids) / len(ids)
        assert 0.35 < a_frac < 0.65

    def test_both_orientations_reachable(self):
        assert scorer.outcome_ab_clone_is_a(_id_with_parity(True)) is True
        assert scorer.outcome_ab_clone_is_a(_id_with_parity(False)) is False


# ---------------------------------------------------------------------------
# winner → verdict mapping (parity-aware) + anonymization
# ---------------------------------------------------------------------------

class TestOutcomeMapping:
    def _judge(self, monkeypatch, case_id, outcome_res,
               clone_draft=_ONTOPIC_DRAFT):
        fake, seen = _three_pass_fake(outcome_res)
        monkeypatch.setattr(scorer, "oauth_json_llm", fake)
        out = scorer.judge_with_oauth(
            _mower_case_dict(case_id), clone_draft=clone_draft,
            reconstructed_intent=_MOWER_INTENT,
            full_cutoff_context=_MOWER_CTX)
        return out, seen

    def test_clone_wins_is_agb_when_clone_is_a(self, monkeypatch):
        cid = _id_with_parity(True)  # clone == CANDIDATE A
        out, _ = self._judge(monkeypatch, cid, {
            "outcome_winner": "A", "outcome_rationale": "clone better",
            "outcome_grounded_fact": _REAL_GROUND})
        assert out["outcome_verdict"] == "as_good_or_better"

    def test_clone_wins_is_agb_when_clone_is_b(self, monkeypatch):
        cid = _id_with_parity(False)  # clone == CANDIDATE B
        out, _ = self._judge(monkeypatch, cid, {
            "outcome_winner": "B", "outcome_rationale": "clone better",
            "outcome_grounded_fact": _REAL_GROUND})
        assert out["outcome_verdict"] == "as_good_or_better"

    def test_real_wins_is_worse_respecting_parity(self, monkeypatch):
        cid = _id_with_parity(False)  # real reply == CANDIDATE A
        out, _ = self._judge(monkeypatch, cid, {
            "outcome_winner": "A", "outcome_rationale": "real better",
            "outcome_grounded_fact": _REAL_GROUND})
        assert out["outcome_verdict"] == "worse"
        assert not out["outcome_grounded_fact"].startswith("FORCED:")

    def test_tie_is_agb(self, monkeypatch):
        out, _ = self._judge(monkeypatch, _id_with_parity(True), {
            "outcome_winner": "tie", "outcome_rationale": "equal",
            "outcome_grounded_fact": _REAL_GROUND})
        assert out["outcome_verdict"] == "as_good_or_better"

    def test_unparseable_outcome_is_error(self, monkeypatch):
        out, _ = self._judge(monkeypatch, "mower12345",
                             {"nonsense": True})
        assert out["outcome_verdict"] == "error"
        assert out["outcome_grounded_fact"] == ""

    def test_candidates_anonymized_in_payload(self, monkeypatch):
        cid = _id_with_parity(True)
        out, seen = self._judge(monkeypatch, cid, {
            "outcome_winner": "tie", "outcome_rationale": "",
            "outcome_grounded_fact": _REAL_GROUND})
        payload = seen["payloads"][2]
        # both candidates present, in parity order, under anonymous labels
        assert "# CANDIDATE A" in payload and "# CANDIDATE B" in payload
        assert _ONTOPIC_DRAFT in payload
        assert "HEMMELIGT-SVAR" in payload  # real reply IS candidate material
        assert payload.index(_ONTOPIC_DRAFT) < payload.index("HEMMELIGT-SVAR")
        # no de-anonymizing labels anywhere in the pass
        for tell in ("MODEL DRAFT", "REAL REPLY", "clone", "human-written A"):
            assert tell not in payload
        # judged against the intent + fenced context
        assert "RECONSTRUCTED INTENT" in payload
        assert "FULL CUTOFF-SAFE CONTEXT" in payload

    def test_outcome_system_is_standalone_and_judge_system_pristine(
            self, monkeypatch):
        out, seen = self._judge(monkeypatch, "mower12345", {
            "outcome_winner": "tie", "outcome_rationale": "",
            "outcome_grounded_fact": _REAL_GROUND})
        assert seen["systems"][2] == scorer.OUTCOME_RUBRIC
        # standalone: the decision rubric is NOT embedded in the outcome
        # system (JUDGE_SYSTEM names MODEL DRAFT / REAL REPLY, which would
        # de-anonymize the candidates)
        assert scorer.retro.JUDGE_SYSTEM not in scorer.OUTCOME_RUBRIC
        assert "MODEL DRAFT" not in scorer.OUTCOME_RUBRIC
        # and the pristine decision rubric gained no outcome keys
        assert "outcome_winner" not in scorer.retro.JUDGE_SYSTEM

    def test_empty_real_reply_skips_pass(self, monkeypatch):
        case = _mower_case_dict()
        case["real_reply"] = ""
        fake, seen = _three_pass_fake({"outcome_winner": "tie"})
        monkeypatch.setattr(scorer, "oauth_json_llm", fake)
        out = scorer.judge_with_oauth(
            case, clone_draft=_ONTOPIC_DRAFT,
            reconstructed_intent=_MOWER_INTENT,
            full_cutoff_context=_MOWER_CTX)
        assert seen["n"] == 2  # decision + intent only — no A/B possible
        assert out["outcome_verdict"] == ""
        assert out["outcome_grounded_fact"] == ""


# ---------------------------------------------------------------------------
# deterministic guards — forced-worse / forced-incomparable
# ---------------------------------------------------------------------------

class TestForcedGuards:
    def _judge(self, monkeypatch, outcome_res, clone_draft):
        fake, _ = _three_pass_fake(outcome_res)
        monkeypatch.setattr(scorer, "oauth_json_llm", fake)
        return scorer.judge_with_oauth(
            _mower_case_dict(), clone_draft=clone_draft,
            reconstructed_intent=_MOWER_INTENT,
            full_cutoff_context=_MOWER_CTX)

    def test_offtopic_clone_credit_forced_worse(self, monkeypatch):
        """LLM credits the clone but the clone draft is off-topic vs the
        reconstructed intent (vacuums, not the mower) → §3.3b floor FORCES
        'worse' — an off-intent draft is never as-good-or-better."""
        cid = _id_with_parity(True)
        fake, _ = _three_pass_fake({
            "outcome_winner": "A", "outcome_rationale": "looks helpful",
            "outcome_grounded_fact": _REAL_GROUND})
        monkeypatch.setattr(scorer, "oauth_json_llm", fake)
        out = scorer.judge_with_oauth(
            _mower_case_dict(cid),
            clone_draft="Koeb en Dyson stoevsuger til stuen, super sugekraft.",
            reconstructed_intent=_MOWER_INTENT,
            full_cutoff_context=_MOWER_CTX)
        assert out["outcome_verdict"] == "worse"
        assert out["outcome_grounded_fact"].startswith("FORCED:")
        assert "topic" in out["outcome_grounded_fact"].lower()

    def test_fabricated_ground_forced_incomparable(self, monkeypatch):
        """LLM credits the clone with a citation absent from the cutoff
        material → §3.2 grounding check FORCES 'incomparable' (the credit is
        unverifiable — demoted, not flipped into a fabricated loss)."""
        out = self._judge(monkeypatch, {
            "outcome_winner": "tie", "outcome_rationale": "both fine",
            "outcome_grounded_fact": ("From Bo at 2026-05-05: Ada already "
                                      "ordered a submarine and a yacht."),
        }, clone_draft=_ONTOPIC_DRAFT)
        assert out["outcome_verdict"] == "incomparable"
        assert out["outcome_grounded_fact"].startswith("FORCED:")
        assert "ground" in out["outcome_grounded_fact"].lower()

    def test_ground_cited_from_real_reply_is_forced(self, monkeypatch):
        """The grounding haystack is thread + fenced ctx ONLY — a citation
        drawn from the real reply itself (candidate material) must fail the
        guard. Pins that the candidates never became the haystack."""
        out = self._judge(monkeypatch, {
            "outcome_winner": "tie", "outcome_rationale": "",
            "outcome_grounded_fact": ("From Ada at 2026-05-06: Acme "
                                      "link HEMMELIGT SVAR."),
        }, clone_draft=_ONTOPIC_DRAFT)
        assert out["outcome_verdict"] == "incomparable"
        assert out["outcome_grounded_fact"].startswith("FORCED:")

    def test_grounded_ontopic_credit_survives(self, monkeypatch):
        """Control: an on-topic clone credit with a genuine citation keeps
        as_good_or_better — the guards are not a blanket reject."""
        out = self._judge(monkeypatch, {
            "outcome_winner": "tie", "outcome_rationale": "both serve goal",
            "outcome_grounded_fact": _REAL_GROUND,
        }, clone_draft=_ONTOPIC_DRAFT)
        assert out["outcome_verdict"] == "as_good_or_better"
        assert not out["outcome_grounded_fact"].startswith("FORCED:")

    def test_real_win_never_forced(self, monkeypatch):
        """'worse' is already the conservative direction — the guards do not
        touch it even when the clone draft is off-topic AND the citation is
        fabricated."""
        cid = _id_with_parity(True)  # clone is A ⇒ real is B
        fake, _ = _three_pass_fake({
            "outcome_winner": "B", "outcome_rationale": "real better",
            "outcome_grounded_fact": "From nowhere: fabricated."})
        monkeypatch.setattr(scorer, "oauth_json_llm", fake)
        out = scorer.judge_with_oauth(
            _mower_case_dict(cid), clone_draft="Dyson stoevsuger.",
            reconstructed_intent=_MOWER_INTENT,
            full_cutoff_context=_MOWER_CTX)
        assert out["outcome_verdict"] == "worse"
        assert not out["outcome_grounded_fact"].startswith("FORCED:")

    def test_guards_are_the_shared_helpers(self):
        """The guard thresholds/functions are the §3.2/§3.3b ones — reused
        verbatim, not re-derived (a drifted copy would fork the fence)."""
        assert scorer._TOPIC_FLOOR_MIN == 0.15
        assert scorer._GROUNDING_JACCARD_MIN == 0.6
        assert callable(scorer._topic_overlap)
        assert callable(scorer._grounding_ok)


# ---------------------------------------------------------------------------
# F1 byte-identity + intent-error independence + CaseScore carry
# ---------------------------------------------------------------------------

class TestNoIntentByteIdentical:
    def test_no_intent_single_call_no_outcome_keys(self, monkeypatch):
        """No reconstructed_intent (the F1/T-prior shape) ⇒ ONE OAuth call and
        the returned dict is the decision dict exactly — no intent keys, no
        outcome keys (byte-identical F1 path)."""
        calls = {"n": 0}
        decision = {"verdict": "match", "rationale": "same call",
                    "what_diverged": "", "real_decision": "ja",
                    "draft_decision": "ja"}

        def fake(payload, system, max_tokens=400, model="claude-sonnet-4-6"):
            calls["n"] += 1
            return dict(decision)

        monkeypatch.setattr(scorer, "oauth_json_llm", fake)
        out = scorer.judge_with_oauth(_mower_case_dict(), "Ja.")
        assert calls["n"] == 1
        assert out == decision
        assert "outcome_verdict" not in out
        assert "intent_verdict" not in out


class TestIntentErrorStillRunsOutcome:
    def test_intent_judge_failure_does_not_skip_outcome(self, monkeypatch):
        """The outcome question is independent of the intent VERDICT — an
        unparseable intent pass still yields the AGB axis (3rd call runs)."""
        fake, seen = _three_pass_fake(
            {"outcome_winner": "tie", "outcome_rationale": "",
             "outcome_grounded_fact": _REAL_GROUND},
            intent_res={"garbage": True})
        monkeypatch.setattr(scorer, "oauth_json_llm", fake)
        out = scorer.judge_with_oauth(
            _mower_case_dict(), clone_draft=_ONTOPIC_DRAFT,
            reconstructed_intent=_MOWER_INTENT,
            full_cutoff_context=_MOWER_CTX)
        assert seen["n"] == 3
        assert out["intent_verdict"] == "error"
        assert out["outcome_verdict"] == "as_good_or_better"


class TestScoreCarriesOutcome:
    def _case(self):
        from framework.fidelity.types import Case
        return Case.from_retro_case(_mower_case_dict())

    def _decision(self, text):
        from framework.fidelity.types import OfficerDecision
        return OfficerDecision(decision=text, rationale="", chain=[])

    def _fake_embedder(self, texts):
        return [[float(len(t or "")), 1.0, 0.0] for t in texts]

    def test_score_populates_outcome_fields(self, monkeypatch):
        def fake_judge(cd, draft, reconstructed_intent="",
                       full_cutoff_context=None):
            return {"verdict": "divergent", "rationale": "",
                    "what_diverged": "", "real_decision": "",
                    "draft_decision": "",
                    "intent_verdict": "intent-aligned",
                    "intent_rationale": "", "intent_what_diverged": "",
                    "intent_grounded_fact": _REAL_GROUND,
                    "outcome_verdict": "as_good_or_better",
                    "outcome_rationale": "clone served goal",
                    "outcome_grounded_fact": _REAL_GROUND}

        monkeypatch.setattr(scorer, "judge_with_oauth", fake_judge)
        cs = scorer.score(
            self._case(), self._decision(_ONTOPIC_DRAFT), baseline_draft="x",
            centroids={"msgraph": [1.0, 1.0, 0.0]},
            embedder=self._fake_embedder,
            intent_ctx={"reconstructed_intent": _MOWER_INTENT,
                        "full_cutoff_context": _MOWER_CTX})
        assert cs.outcome_verdict == "as_good_or_better"
        assert cs.outcome_grounded_fact == _REAL_GROUND

    def test_score_without_intent_ctx_leaves_outcome_empty(self, monkeypatch):
        monkeypatch.setattr(
            scorer, "judge_with_oauth",
            lambda cd, draft: {"verdict": "match", "rationale": "",
                               "what_diverged": "", "real_decision": "",
                               "draft_decision": ""})
        cs = scorer.score(
            self._case(), self._decision("Ja."), baseline_draft="x",
            centroids={"msgraph": [1.0, 1.0, 0.0]},
            embedder=self._fake_embedder)
        assert cs.outcome_verdict == ""
        assert cs.outcome_grounded_fact == ""
