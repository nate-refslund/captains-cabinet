"""Teeth for the agnosticism advisor (cabinet/scripts/agnosticism-advisor.py).

Hermetic: every arm injects a stub in place of the LLM, so this file makes no
network call, needs no credential and runs identically in CI and on a laptop.
The REAL-model rates are a separate, measured artifact
(docs/ci-cost-and-agnosticism-advisor-2026-07-28.md) — this file proves the
machinery around the model, which is the half that can rot silently.

THE THREE ROT MODES, EACH WITH ITS OWN ARM:
  1. Rubber stamp — a judge that answers "agnostic" to everything must VOID
     calibration, and so must one that answers "instance-specific" to
     everything. Both directions, because a one-sided floor leaves the other
     free to rot. An ORACLE stub must PASS, so the floors are provably
     satisfiable rather than merely unreachable.
  2. Flake / silence — an unparseable or absent answer is ERROR, never
     AGNOSTIC. "Nothing came back" must never read as "nothing found".
  3. Self-reference — a run whose inputs touch the advisor, rubric or corpus
     ABSTAINS without calling the model at all.

Plus the placement pin: the advisor must not appear in any workflow. That is
what keeps an advisory lens from quietly becoming a gate.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "cabinet" / "scripts" / "agnosticism-advisor.py"
_WORKFLOWS = _REPO / ".github" / "workflows"


def _load():
    spec = importlib.util.spec_from_file_location("agnosticism_advisor", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agnosticism_advisor"] = mod
    spec.loader.exec_module(mod)
    return mod


A = _load()


# --- stubs ----------------------------------------------------------------


def _const(verdict, nouns=("x",)):
    def _llm(payload, system, model):
        return {"verdict": verdict, "nouns": list(nouns), "why": "stub"}

    return _llm


def _oracle():
    """Answers from the recorded ground truth, keyed by the BLIND name the
    advisor actually sends — which is the only handle a real judge gets."""
    man = A.load_manifest()
    truth = {}
    for entry in man["known_bad"]:
        truth[A._blind_name(entry["file"])] = A.SPECIFIC
    for entry in man["known_good"]:
        truth[A._blind_name(entry["file"])] = A.AGNOSTIC

    def _llm(payload, system, model):
        first = payload.splitlines()[0]
        name = first.split("FILE: ", 1)[1].strip()
        return {"verdict": truth[name], "nouns": [], "why": "oracle"}

    return _llm


# --- rot mode 1: the judge cannot be a rubber stamp -----------------------


def test_always_agnostic_stub_voids_calibration():
    cal = A.calibrate(llm=_const(A.AGNOSTIC))
    assert cal.void is True
    assert cal.caught == 0
    assert any("planted" in r for r in cal.reasons)


def test_always_specific_stub_voids_calibration():
    """A judge that flags everything catches every plant and is still useless."""
    cal = A.calibrate(llm=_const(A.SPECIFIC))
    assert cal.void is True
    assert cal.caught == cal.planted
    assert cal.false_positives == cal.clean
    assert any("clean fixtures" in r for r in cal.reasons)


def test_oracle_stub_passes_calibration():
    """The floors must be satisfiable. A calibration nothing can pass is a
    disabled sensor wearing a strict face."""
    cal = A.calibrate(llm=_oracle())
    assert cal.void is False, cal.reasons
    assert cal.caught == cal.planted
    assert cal.false_positives == 0


def test_one_miss_voids_even_with_everything_else_right():
    man = A.load_manifest()
    missed = A._blind_name(man["known_bad"][0]["file"])
    oracle = _oracle()

    def _llm(payload, system, model):
        if missed in payload.splitlines()[0]:
            return {"verdict": A.AGNOSTIC, "nouns": [], "why": "miss"}
        return oracle(payload, system, model)

    cal = A.calibrate(llm=_llm)
    assert cal.void is True
    assert cal.caught == cal.planted - 1


def test_false_positive_budget_is_one_not_unlimited():
    man = A.load_manifest()
    oracle = _oracle()
    two = {A._blind_name(e["file"]) for e in man["known_good"][:2]}

    def _fp(n):
        def _llm(payload, system, model):
            name = payload.splitlines()[0].split("FILE: ", 1)[1].strip()
            if name in list(two)[:n]:
                return {"verdict": A.SPECIFIC, "nouns": [], "why": "fp"}
            return oracle(payload, system, model)
        return _llm

    assert A.calibrate(llm=_fp(1)).void is False
    assert A.calibrate(llm=_fp(2)).void is True


@pytest.mark.parametrize(
    "manifest",
    [
        {"known_bad": [], "known_good": [{"file": "known_good/backoff.txt"}]},
        {"known_bad": [{"file": "known_bad/org_domain.txt"}], "known_good": []},
        {"known_bad": [], "known_good": []},
    ],
)
def test_degenerate_corpus_voids(manifest):
    """THE DEGENERATE END. With no plants the true-positive rate is vacuously
    perfect and every stub passes; with no clean set the false-positive floor
    is vacuous the same way."""
    cal = A.calibrate(llm=_const(A.AGNOSTIC), manifest=manifest)
    assert cal.void is True
    assert any("degenerate" in r for r in cal.reasons)


def test_calibration_is_blind():
    """The judge must not be able to read the answer off the file name."""
    seen = []

    def _llm(payload, system, model):
        seen.append(payload.splitlines()[0])
        return {"verdict": A.AGNOSTIC, "nouns": [], "why": ""}

    A.calibrate(llm=_llm)
    assert seen
    joined = "\n".join(seen)
    for token in ("known_bad", "known_good", "org_domain", "backoff", "plant"):
        assert token not in joined, token


# --- rot mode 2: silence is not approval ----------------------------------


@pytest.mark.parametrize(
    "bad", [None, {}, {"verdict": "maybe"}, {"verdict": None}, "not-a-dict", 7]
)
def test_unparseable_answer_is_error_not_agnostic(bad):
    v = A.review_text("f.py", "x", llm=lambda p, s, m: bad)
    assert v.verdict == A.ERROR
    assert v.flagged is False


def test_majority_of_three():
    calls = {"n": 0}

    def _llm(payload, system, model):
        calls["n"] += 1
        verdict = A.SPECIFIC if calls["n"] <= 2 else A.AGNOSTIC
        return {"verdict": verdict, "nouns": ["Acme"], "why": "w"}

    v = A.review_text("f.py", "x", llm=_llm, votes=3)
    assert v.verdict == A.SPECIFIC
    assert v.votes == [A.SPECIFIC, A.SPECIFIC, A.AGNOSTIC]


def test_minority_does_not_carry():
    calls = {"n": 0}

    def _llm(payload, system, model):
        calls["n"] += 1
        verdict = A.SPECIFIC if calls["n"] == 1 else A.AGNOSTIC
        return {"verdict": verdict, "nouns": [], "why": "w"}

    assert A.review_text("f.py", "x", llm=_llm, votes=3).verdict == A.AGNOSTIC


def test_cache_replays_instead_of_re_deciding(tmp_path):
    calls = {"n": 0}

    def _llm(payload, system, model):
        calls["n"] += 1
        return {"verdict": A.SPECIFIC, "nouns": ["Acme"], "why": "w"}

    cache = A.VerdictCache(tmp_path, digest="d1")
    assert A.review_text("f.py", "body", llm=_llm, cache=cache).flagged
    assert A.review_text("f.py", "body", llm=_llm, cache=cache).flagged
    assert calls["n"] == 1

    other = A.VerdictCache(tmp_path, digest="d2")
    A.review_text("f.py", "body", llm=_llm, cache=other)
    assert calls["n"] == 2, "a different rubric digest must not hit the cache"


# --- rot mode 3: it does not judge its own judge --------------------------


@pytest.mark.parametrize("path", [
    "cabinet/scripts/agnosticism-advisor.py",
    "cabinet/scripts/agnosticism-corpus/manifest.yml",
    "cabinet/scripts/agnosticism-corpus/known_bad/org_domain.txt",
    "cabinet/scripts/tests/test_agnosticism_advisor.py",
])
def test_self_reference_abstains_without_calling_the_model(path, capsys):
    called = []
    rc = A.main(["--paths", path, "framework/env.py"],
                llm=lambda p, s, m: called.append(1) or {"verdict": A.AGNOSTIC})
    assert rc == 0
    assert called == []
    assert "ABSTAIN" in capsys.readouterr().out


# --- placement: advisory, and mechanically kept that way ------------------


def test_the_advisor_is_not_wired_into_any_workflow():
    """An LLM verdict may create work; it may never create permission. The
    moment this name appears in a workflow it is on the way to becoming a
    required check."""
    for wf in _WORKFLOWS.glob("*.yml"):
        assert "agnosticism-advisor" not in wf.read_text(), wf.name


def test_sweep_exits_zero_even_when_everything_is_flagged(capsys):
    rc = A.main(["--paths", "framework/env.py"],
                llm=_const(A.SPECIFIC, nouns=["Acme Corp"]))
    assert rc == 0
    out = capsys.readouterr().out
    assert "ADVISORY" in out and "FLAG" in out


def test_calibrate_exits_nonzero_on_void(capsys):
    """The ONE non-zero exit in the tool, and it is the tool grading itself."""
    assert A.main(["--calibrate"], llm=_const(A.AGNOSTIC)) == 1
    assert "VOID" in capsys.readouterr().out
    assert A.main(["--calibrate"], llm=_oracle()) == 0


def test_json_mode_carries_the_rubric_digest(capsys):
    A.main(["--paths", "framework/env.py", "--json"], llm=_const(A.AGNOSTIC))
    payload = json.loads(capsys.readouterr().out)
    assert payload["digest"] == A.rubric_digest()
    assert payload["model"] == A.MODEL


# --- scope + corpus integrity ---------------------------------------------


@pytest.mark.parametrize("rel,expected", [
    ("framework/env.py", True),
    ("cabinet/scripts/foo.sh", True),
    ("cabinet/docs/x.md", True),
    ("instance/config/platform.yml", False),
    ("presets/flavor-a/x.py", False),
    ("framework/assets/logo.png", False),
    ("README.md", False),
])
def test_scope(rel, expected):
    assert A.in_scope(rel) is expected


def test_corpus_files_all_exist_and_are_disjoint():
    man = A.load_manifest()
    bad = [e["file"] for e in man["known_bad"]]
    good = [e["file"] for e in man["known_good"]]
    assert len(bad) >= 5 and len(good) >= 5
    assert not (set(bad) & set(good))
    assert len(set(bad)) == len(bad) and len(set(good)) == len(good)
    for rel in bad + good:
        assert (A.CORPUS_DIR / rel).is_file(), rel
        assert (A.CORPUS_DIR / rel).read_text().strip(), rel


def test_rubric_digest_covers_the_corpus_not_just_the_prompt():
    import hashlib
    assert A.rubric_digest() == A.rubric_digest()
    assert A.rubric_digest() != hashlib.sha256(A.RUBRIC.encode()).hexdigest()


def test_model_is_pinned():
    assert A.MODEL and A.MODEL != "default"
