from __future__ import annotations

import pytest

from framework.fidelity import scorer, retro
from framework.fidelity.types import Case, OfficerDecision

CUTOFF = "2026-06-10T12:00:00+00:00"


def _case():
    return Case.from_retro_case({
        "case_id": "abc1234567", "reply_key": "k", "slug": "ulrik",
        "person": "Ulrik", "channel": "msgraph", "language": "da",
        "reply_ts": CUTOFF, "subject": "s", "n_prior": 2,
        "thread_before": [
            {"slug": "ulrik", "person": "Ulrik",
             "date": "2026-06-09T08:00:00+00:00", "direction": "received",
             "who": "Ulrik <u@x>", "source": "msgraph", "to": "", "cc": "",
             "text": "kan vi snakke fredag?"},
        ],
        "real_reply": "Ja, fredag passer fint.",
    })


# deterministic fake embedder: identical text -> identical vector -> cosine 1.0
def _fake_embedder(texts):
    def vec(t):
        return [float(len(t or "")), 1.0, 0.0]
    return [vec(t) for t in texts]


class TestJudgeWithOauth:
    def test_routes_judge_through_oauth(self, monkeypatch):
        captured = {}
        def fake_oauth_json(payload, system, max_tokens=400, model="claude-sonnet-4-6"):
            captured["system"] = system
            return {"verdict": "match", "rationale": "same call",
                    "what_diverged": "", "real_decision": "ja", "draft_decision": "ja"}
        monkeypatch.setattr(scorer, "oauth_json_llm", fake_oauth_json)
        out = scorer.judge_with_oauth(_case().to_retro_case(), "Ja, fredag.")
        assert out["verdict"] == "match"
        assert "IGNORE style" in captured["system"]  # JUDGE_SYSTEM kept intact


class TestScore:
    def test_match_composite_is_one(self, monkeypatch):
        monkeypatch.setattr(scorer, "judge_with_oauth",
                            lambda cd, draft: {"verdict": "match", "rationale": "",
                                               "what_diverged": "", "real_decision": "",
                                               "draft_decision": ""})
        dec = OfficerDecision(decision="Ja, fredag passer fint.", rationale="", chain=[])
        centroids = {"msgraph": _fake_embedder(["x"])[0]}
        cs = scorer.score(_case(), dec, baseline_draft="Sure, sounds good.",
                          centroids=centroids, embedder=_fake_embedder)
        assert cs.decision_verdict == "match"
        assert cs.composite == 1.0
        assert cs.endorsement_adjusted is False
        assert isinstance(cs.mechanics_flags, list)

    def test_partial_composite_is_half(self, monkeypatch):
        monkeypatch.setattr(scorer, "judge_with_oauth",
                            lambda cd, draft: {"verdict": "partial", "rationale": "",
                                               "what_diverged": "scope", "real_decision": "",
                                               "draft_decision": ""})
        dec = OfficerDecision(decision="Maaske fredag?", rationale="", chain=[])
        cs = scorer.score(_case(), dec, baseline_draft="x",
                          centroids={"msgraph": _fake_embedder(["x"])[0]},
                          embedder=_fake_embedder)
        assert cs.composite == 0.5

    def test_divergent_composite_is_zero(self, monkeypatch):
        monkeypatch.setattr(scorer, "judge_with_oauth",
                            lambda cd, draft: {"verdict": "divergent", "rationale": "",
                                               "what_diverged": "diff", "real_decision": "",
                                               "draft_decision": ""})
        dec = OfficerDecision(decision="Nej, det kan jeg ikke.", rationale="", chain=[])
        cs = scorer.score(_case(), dec, baseline_draft="x",
                          centroids={"msgraph": _fake_embedder(["x"])[0]},
                          embedder=_fake_embedder)
        assert cs.composite == 0.0

    def test_style_win_when_clone_closer_than_baseline(self, monkeypatch):
        monkeypatch.setattr(scorer, "judge_with_oauth",
                            lambda cd, draft: {"verdict": "match", "rationale": "",
                                               "what_diverged": "", "real_decision": "",
                                               "draft_decision": ""})
        dec = OfficerDecision(decision="Ja, fredag passer fint.", rationale="", chain=[])
        cs = scorer.score(_case(), dec,
                          baseline_draft="A totally different long baseline answer here.",
                          centroids={"msgraph": _fake_embedder(["x"])[0]},
                          embedder=_fake_embedder)
        assert cs.style_win is True
