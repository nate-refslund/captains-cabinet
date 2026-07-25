"""COG-5 W2 T2 — the SCORING/CANDIDATE sim corpus (contract
cognitive-core-phase-5-contract-2026-07-24 §12 sims 2/3/4/5/8 + the §4 arming
battery with BOTH §4.5 honest-negative arms + the escape arm + the §9.3
certainty-grammar tripwires + SIM-2 extension arms). Tests-first:
`framework/evolution/{scorers,candidate,league}.py` and
`cabinet/scripts/cog5-gate-arm.py` do NOT exist on this tree.

TWO TIERS (the COG-4 W2 mergeability idiom — this suite merges GREEN on the
bare tree):

  * FIXTURE-MACHINERY tests run LIVE NOW against the reference machinery in
    `lib_cog5_scoring_fixtures.py`, DELIBERATELY composed over two REAL
    shipped surfaces: `framework.fidelity.regression_gate.evaluate_gate`
    (the §4.3/§4.5 admission predicate — real bytes, real three-valued
    semantics) and `framework.learning.gate.ratify` via its injectable
    `runner=`/`probe_fn=`/`root=` seam on a SCRATCH root (gate.py consumed
    at the call-site, byte-untouched — §4.1; evidence writes confined to the
    scratch root; org emits ride the repo conftest fence). Every §12-named
    negative-control mutant is proven BITING here in this run — judge-only
    rank (sim 2), insensitive fold (sim 3), judge-satisfies-a-floor (sim 4,
    THE certainty-law arm), divergence-averaged-away (sim 5), nondeterminism-
    averaged (sim 8), no_verdict→pass, no_verdict→fail, flat→pass,
    flat→error (§4.5 both directions), env-passthrough + outside-writer
    (escape), verdict_human-minting + promotes-on-league-score (§9.3 SIM-2
    extensions). A gate without a biting mutant is decoration (§12).
  * REAL-SURFACE arms are VACUITY-GUARDED: each carries (a) a COMPANION
    absence assertion that goes RED the instant the surface lands (the skip
    cannot silently persist — §13), (b) an ARMED proof that the import probe
    currently fails ModuleNotFound (plus a scratch-tree fixture proof that
    the probe FLIPS when a surface lands — the probe is a discriminator,
    not a constant), and (c) the skip with its RETIREMENT CONDITION.

RETIREMENT CONDITION (all guarded arms): retire the skips when
`framework/evolution/scorers.py` / `candidate.py` (and for the arming arm
`cabinet/scripts/cog5-gate-arm.py`) land — integrator corpus surgery per §13
replaces each guard body with the SAME lib assert batteries run over the
landed surface (the batteries are proven TODAY on the reference tier; the
implementation must satisfy them UNMODIFIED — builders never edit corpus;
contradictions route to the integrator). The t1 shared-core join guard
(TestCorpusCoreJoin) retired AT THE W2 INTEGRATION LANDING: `lib_cog5_corpus.py`
is in-tree, both arms are live assertions, and no skip remains at that seam.

S0: interpreter python3.12; no DB, no network (children are local
subprocesses with explicit env); the repo conftest fences every durable
surface. Provenance: authored per the 2026-07-07 full-autonomy grant + the
2026-07-20 cognitive-masterplan continuous grant (COG-5 §12/§13, W2 T2 —
corpus authorship is judgment-tier work). ORIGINAL BUILD (ab8fe00a): Fable 5.
FIX ROUNDS (27197a63 crown-jewel circumventions; this round's five re-review
notes): Opus 5, the program's primary model from 2026-07-25.
"""
from __future__ import annotations

import inspect
import os
import re
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog5_scoring_fixtures as FIX  # noqa: E402

from framework.fidelity import regression_gate as rg  # noqa: E402
from framework.learning import gate as gate_mod       # noqa: E402


def _tag(marker: str) -> str:
    return re.escape(marker)


# ===========================================================================
# the t1-owned shared core — the parallel-wave join, guarded honestly
# ===========================================================================
class TestCorpusCoreJoin:
    """RETIRED AT THE W2 INTEGRATION LANDING — the join happened, so both arms
    are LIVE assertions (integrator corpus surgery per §13, discharging the
    RETIREMENT CONDITION written into this class before the join).

    What the two arms were pre-join: a vacuity `pytest.skip` while T1's
    `lib_cog5_corpus.py` had not landed, plus a COMPANION absence assertion
    that REDs the instant it did. Both are now unconditional: the sibling is
    in-tree, so its presence is a STANDING property and a core that vanishes,
    stops importing, or binds to some other file on `sys.path` REDs here
    instead of silently reverting to a skip."""

    CORE_PATH = _HERE / "lib_cog5_corpus.py"

    def test_core_is_joined_and_bound(self):
        # was `test_core_absence_companion` (a pre-join-only arm: it asserted
        # the core's ABSENCE and returned early once it landed). Stated
        # positively now — T2's import guard is `except ModuleNotFoundError`,
        # so a broken/renamed core binds CORE=None SILENTLY, which post-join is
        # a regression and not a state this corpus may skip on.
        assert FIX.CORE is not None, (
            "lib_cog5_corpus.py did not import — T2's guarded import bound "
            "CORE=None. The W2 join is LANDED, so this is a real regression, "
            "never the pre-join state the retired guard tolerated.")

    def test_core_import_binds_the_bytes_on_disk(self):
        # was `test_core_join_guard` (the skip limb is retired; its live limb
        # only checked that the file exists). Strengthened to what the join
        # actually has to mean: the module object T2 holds IS this file, not a
        # same-named module shadowed from elsewhere on sys.path.
        assert self.CORE_PATH.exists(), "the t1-owned shared core is missing"
        assert Path(FIX.CORE.__file__).resolve() == self.CORE_PATH.resolve(), (
            f"T2 imported lib_cog5_corpus from {FIX.CORE.__file__!r}, not the "
            f"sibling-unit file at {self.CORE_PATH} — the cross-unit contract "
            "T1 pins is being read from the wrong bytes")


# ===========================================================================
# the gate seam + predicate vocabulary — LIVE pins over REAL bytes (§4.1/§4.3)
# ===========================================================================
class TestGateSeamPins:
    def test_ratify_exposes_the_injectable_seam(self):
        # §4.2: the armed wrapper injects ratify(runner=, probe_fn=, root=) —
        # the seam must exist TODAY (gate.py:498-517), or call-site arming is
        # impossible without a germline edit.
        sig = inspect.signature(gate_mod.ratify)
        kwonly = {p.name for p in sig.parameters.values()
                  if p.kind is p.KEYWORD_ONLY}
        assert {"runner", "probe_fn", "root"} <= kwonly, (
            "gate.ratify lost its injectable seam — §4 arming is call-site "
            "ONLY; gate.py is schg germline and must stay byte-untouched")

    @pytest.mark.parametrize("rel", ("framework/learning/gate.py",
                                     "framework/fidelity/graduation.py"))
    @pytest.mark.parametrize("token", ("regression", "league", "foundry",
                                       "evolution"))
    def test_germline_files_carry_no_arming_tokens(self, rel, token):
        # §4.1 weakening tripwire, made mechanical: arming/league wiring lands
        # OUTSIDE the germline pair (the regression_gate.py:38-41 precedent;
        # §4.3 "grep: ZERO regression refs in gate.py today"). Any of these
        # tokens appearing in either file means someone wired the foundry INTO
        # the germline instead of composing at the call-site.
        text = (_REPO / rel).read_text(encoding="utf-8").lower()
        assert token not in text, (
            f"{rel} now mentions {token!r} — §4 arming/league composition "
            "must stay at the call-site; gate.py/graduation.py byte-untouched")

    def test_regression_gate_three_valued_vocabulary_pinned(self):
        # the §4.5 ground: outcomes are exactly pass/fail/no_verdict; passed
        # is True ONLY for pass (both fail and no_verdict are False).
        assert (rg.OUTCOME_PASS, rg.OUTCOME_FAIL, rg.OUTCOME_NO_VERDICT) == \
            ("pass", "fail", "no_verdict")
        assert rg.GateResult(outcome=rg.OUTCOME_NO_VERDICT).passed is False
        assert rg.GateResult(outcome=rg.OUTCOME_FAIL).passed is False
        assert rg.GateResult(outcome=rg.OUTCOME_PASS).passed is True

    def test_minimums_bind_the_estate_constants(self):
        # §6.2: the derivation constants are the estate's own — drift here
        # means the recorded minimums no longer match their source bytes.
        jc = "framework/fidelity/judge_calibration.py"
        assert FIX.estate_constant(jc, "JUDGE_HARD_BAR") == FIX.JUDGE_AGREEMENT_BAR
        assert FIX.estate_constant(jc, "MIN_PAIRS") == FIX.JUDGE_MIN_PAIRS \
            == FIX.REAL_TRAJECTORY_FLOOR == FIX.CAPTAIN_LABEL_FLOOR
        assert FIX.estate_constant("framework/fidelity/run_f1.py",
                                   "BASELINE_MATCH_RATE") == FIX.BASELINE_MATCH_RATE

    def test_certainty_grammar_binds_the_states_tokens(self):
        # §9.3: the P5 cap + the human-verdict source are the REAL
        # framework.objectives.states tokens (grammar drift tripwire).
        grammar = FIX.estate_grammar()
        assert grammar["p5"] == FIX.P5_CAP == "observationally_supported"
        assert grammar["human_source"] == FIX.HUMAN_VERDICT_SOURCE == \
            "verdict_human"


# ===========================================================================
# shared candidate fixtures (module scope — the sims share one frozen corpus)
# ===========================================================================
IDS = FIX.case_ids(20)
BASELINE = FIX.results_baseline(IDS, learned=15)      # 15/20 learned
IMPROVING = FIX.results_improving(BASELINE, "case-016")   # fixes ONE failing
KNOWN_BAD = FIX.results_known_bad(BASELINE, "case-003")   # loses ONE learned
FLAT = dict(BASELINE)                                     # improves nothing


def _gate_result(candidate):
    return rg.evaluate_gate(IDS, BASELINE, candidate)


def _named_vectors():
    """incumbent + the three sim candidates, machine dims grounded in the
    REAL predicate; judge dims are the seeded traps (known-bad and judge-only
    carry the HIGH judge scores)."""
    return {
        "incumbent": FIX.candidate_vector(
            candidate_results=BASELINE,
            gate_result=rg.GateResult(outcome=rg.OUTCOME_FAIL),
            judge_score=0.55),
        "known-bad": FIX.candidate_vector(
            candidate_results=KNOWN_BAD, gate_result=_gate_result(KNOWN_BAD),
            judge_score=0.95),
        "improving": FIX.candidate_vector(
            candidate_results=IMPROVING, gate_result=_gate_result(IMPROVING),
            judge_score=0.50),
        "judge-only": FIX.candidate_vector(
            candidate_results=FLAT, gate_result=_gate_result(FLAT),
            judge_score=0.99),
    }


# ===========================================================================
# sim 2 — known-bad candidate (X2)
# ===========================================================================
class TestSim2KnownBad:
    def test_regression_stage_catches_the_seeded_regression(self):
        res = _gate_result(KNOWN_BAD)
        assert res.outcome == rg.OUTCOME_FAIL and "case-003" in res.regressed, (
            "[SIM2-X2] the REAL regression stage must catch the seeded "
            "frozen-case regression")

    def test_known_bad_ranks_below_incumbent_on_machine_dimensions(self):
        rank = FIX.rank_by_machine(_named_vectors(), incumbent="incumbent")
        FIX.assert_sim2_known_bad_loses(rank, bad="known-bad",
                                        incumbent="incumbent")

    def test_known_bad_is_admission_ineligible(self):
        vecs = _named_vectors()
        ok, reasons = FIX.admission_eligible(vecs["known-bad"],
                                             vecs["incumbent"])
        assert ok is False and any("[FLOOR-REGRESSION]" in r for r in reasons)

    def test_mutant_judge_only_rank_REDS(self):
        # the §12 named escape: a scorer ignoring machine outcomes ranks the
        # known-bad candidate (judge 0.95) ABOVE the incumbent (judge 0.55) —
        # the sim-2 battery must catch exactly that.
        mutant_rank = FIX.mutant_judge_only_rank(_named_vectors())
        assert mutant_rank.index("known-bad") < mutant_rank.index("incumbent"), \
            "fixture invariant: the mutant must actually invert the order"
        with pytest.raises(AssertionError, match=_tag("[SIM2-MACHINE-RANK]")):
            FIX.assert_sim2_known_bad_loses(mutant_rank, bad="known-bad",
                                            incumbent="incumbent")


# ===========================================================================
# sim 3 — known-good small improvement (sensitivity)
# ===========================================================================
class TestSim3SmallImprovement:
    def test_real_predicate_detects_the_improvement(self):
        res = _gate_result(IMPROVING)
        assert res.outcome == rg.OUTCOME_PASS and res.improved == ["case-016"] \
            and res.regressed == []

    def test_improvement_ranked_above_on_the_machine_dimension(self):
        rank = FIX.rank_by_machine(_named_vectors(), incumbent="incumbent")
        FIX.assert_sim3_improvement_detected(rank, good="improving",
                                             incumbent="incumbent")

    def test_improving_candidate_is_admission_eligible(self):
        vecs = _named_vectors()
        ok, reasons = FIX.admission_eligible(vecs["improving"],
                                             vecs["incumbent"])
        assert ok is True and reasons == []

    def test_mutant_insensitive_fold_REDS(self):
        # the §12 named escape: a quarter-bucket aggregate collapses 0.80
        # (16/20) and 0.75 (15/20) into one bucket — the one-case improvement
        # is buried and the sensitivity assert must catch it.
        vecs = _named_vectors()
        assert FIX.insensitive_fold(16 / 20) == FIX.insensitive_fold(15 / 20), \
            "fixture invariant: the fold must actually bury the improvement"
        folded_rank = FIX.rank_by_machine(vecs, fold=FIX.insensitive_fold,
                                          incumbent="incumbent")
        with pytest.raises(AssertionError, match=_tag("[SIM3-SENSITIVITY]")):
            FIX.assert_sim3_improvement_detected(folded_rank, good="improving",
                                                 incumbent="incumbent")


# ===========================================================================
# sim 4 — judge-only winner (X3, THE certainty-law arm)
# ===========================================================================
class TestSim4JudgeOnly:
    def test_judge_only_winner_is_ineligible(self):
        vecs = _named_vectors()
        ok, reasons = FIX.admission_eligible(vecs["judge-only"],
                                             vecs["incumbent"])
        FIX.assert_sim4_judge_only_ineligible(ok, reasons)

    def test_judge_dimension_is_recorded_ranking_only(self):
        # the §9.1 schema: the judge dim rides the vector as kind "judge" —
        # structurally invisible to machine_dims() and so to every floor.
        pack = _named_vectors()["judge-only"]
        assert pack["vector"]["judge_score"]["kind"] == FIX.JUDGE_KIND
        assert "judge_score" not in FIX.machine_dims(pack)

    def test_judge_only_also_fails_the_real_regression_stage(self):
        # belt + braces: a machine-flat candidate cannot even honest-PASS the
        # predicate (§4.2 — "a merely-flat candidate cannot honest-PASS").
        res = _gate_result(FLAT)
        assert res.outcome == rg.OUTCOME_FAIL and res.improved == []

    def test_mutant_judge_satisfies_a_floor_REDS(self):
        # the §12 named escape (X3): the judge score (0.99 >= the 0.80 bar)
        # reaching the admission joint — the certainty-law arm.
        vecs = _named_vectors()
        ok, reasons = FIX.mutant_judge_floor_eligibility(vecs["judge-only"],
                                                         vecs["incumbent"])
        assert ok is True, "fixture invariant: the mutant must actually admit"
        with pytest.raises(AssertionError, match=_tag("[SIM4-X3]")):
            FIX.assert_sim4_judge_only_ineligible(ok, reasons)

    # ---- X6 at the VALUE, not the label (the derivation/custody arm) -----
    def test_reference_scorer_binds_every_machine_dim_to_machine_evidence(self):
        # the positive law: the reference scorer stamps each dim with the
        # evidence source it actually read (replay map / gate result / judge),
        # so a machine floor rests on machine EVIDENCE, not a self-declared
        # `kind` label. Re-runnable against the real scorers.py at W6.
        for name, pack in _named_vectors().items():
            FIX.assert_machine_floors_machine_derived(pack)
            vector = pack["vector"]
            assert vector["frozen_pass_rate"][FIX.DERIVATION_KEY] == \
                FIX.DERIVATION_REPLAY_MAP, name
            assert vector["frozen_regressions"][FIX.DERIVATION_KEY] == \
                FIX.DERIVATION_GATE_RESULT, name
            assert vector["judge_score"][FIX.DERIVATION_KEY] == \
                FIX.DERIVATION_JUDGE_LLM, name

    def test_the_constructor_wall_no_caller_may_name_a_derivation(self):
        # the §6.2 WALL shape lifted to the vector (mirror of
        # test_row_supplied_provenance_refuses): honest construction takes
        # EVIDENCE, never a derivation label — there is structurally no
        # parameter through which a scorer could NAME a derivation.
        #
        # SCOPE, stated exactly (integrator fold of the N1 stale echo): this
        # is the LABEL channel and nothing more. The sentence that stood here
        # ran on to "...for a number it did not measure", and N1 disproved
        # that: the evidence OBJECT is still the caller's, so a machine-SHAPED
        # fabrication earns machine custody with no label forgery anywhere.
        # The VALUE channel (make_vector's measure-from-evidence law) is what
        # answers "a number it did not measure", and even that leaves the
        # self-consistent fabrication as a DECLARED RESIDUAL — pinned by
        # test_declared_residual_self_consistent_fabricated_evidence and
        # make_vector's own HONEST SCOPE block. A docstring claiming what the
        # bytes do not deliver is the failure class this corpus exists to
        # catch, so the claim is kept to the channel this test actually walls.
        #
        # N2 (re-review): this check used to sit INLINE over the fixture
        # constructors, so at W6 it would still have been checking fixture
        # code. It is now a LIB battery — integrator surgery points it at the
        # real scorer/vector constructor, the same promotion N4's table_order
        # law got.
        FIX.assert_no_derivation_parameter(FIX.make_vector, FIX.candidate_vector)
        # ...and handing judge evidence to a machine dim stamps the TRUTH:
        pack = FIX.make_vector(
            {"frozen_pass_rate": (0.99, FIX.MACHINE_KIND)},
            evidence={"frozen_pass_rate": FIX.JudgeEvidence(0.99)})
        assert pack["vector"]["frozen_pass_rate"][FIX.DERIVATION_KEY] == \
            FIX.DERIVATION_JUDGE_LLM

    def test_mutant_constructor_naming_its_own_derivation_REDS(self):
        # the promoted battery needs its own biting mutant or it is
        # decoration (§12): a constructor that DOES take derivation labels
        # lets the caller stamp `machine:replay_map` on the judge's number.
        forged = FIX.mutant_constructor_with_derivation_parameter(
            {"frozen_pass_rate": (0.99, FIX.MACHINE_KIND)},
            derivation={"frozen_pass_rate": FIX.DERIVATION_REPLAY_MAP})
        assert forged["vector"]["frozen_pass_rate"][FIX.DERIVATION_KEY] == \
            FIX.DERIVATION_REPLAY_MAP, (
            "fixture invariant: the mutant constructor must actually let the "
            "caller name machine custody")
        assert FIX.machine_derivation_violations(forged) == [], (
            "fixture invariant: the forged LABEL is indistinguishable at the "
            "stamp battery — which is exactly why the wall is a signature "
            "check and not a value check")
        with pytest.raises(AssertionError, match=_tag("[SIM4-X6-NO-LABEL]")):
            FIX.assert_no_derivation_parameter(
                FIX.mutant_constructor_with_derivation_parameter)

    def test_machine_dim_values_are_measured_from_their_evidence(self):
        # the VALUE channel (N1b): a machine dim's number IS what its evidence
        # says. The reference scorer's pass rate equals the replay map's own
        # passed/total and its regression count equals the gate result's own
        # regressed length — not numbers reported alongside them.
        for name, pack in _named_vectors().items():
            FIX.assert_machine_values_measured_from_evidence(pack)
        measured = FIX.make_vector({
            "frozen_pass_rate": (0.5, FIX.MACHINE_KIND),
        }, evidence={"frozen_pass_rate": {"a": True, "b": False}})
        dim = measured["vector"]["frozen_pass_rate"]
        assert dim["value"] == 0.5 and dim[FIX.DERIVATION_KEY] == \
            FIX.DERIVATION_REPLAY_MAP
        assert FIX.measure_from_evidence({"a": True, "b": False}) == 0.5
        assert FIX.measure_from_evidence(
            rg.GateResult(outcome=rg.OUTCOME_FAIL, regressed=["c1", "c2"])) == 2

    def test_mutant_fabricated_evidence_for_a_machine_dim_REDS(self):
        # THE escape the targeted re-review proved was STILL OPEN after the
        # label channel closed: the caller controls the `evidence` argument,
        # and the evidence OBJECT'S TYPE decided the stamp on its own. A
        # machine-SHAPED object — one fabricated replay row — handed beside
        # the judge's 0.99 stamped `machine:replay_map` with no label forgery,
        # and admission_eligible returned (True, []). The docstring claiming
        # this could not happen was FALSE; the value channel closes it.
        vecs = _named_vectors()
        fake = FIX.mutant_fabricated_evidence_for_a_machine_dim(judge_score=0.99)
        rate = fake["vector"]["frozen_pass_rate"]
        assert rate[FIX.DERIVATION_KEY] == FIX.DERIVATION_VALUE_MISMATCH, (
            "fixture invariant: the fabricated map is machine-SHAPED, so the "
            "stamp can only catch it via the value it fails to match")
        assert fake["vector"]["frozen_regressions"][FIX.DERIVATION_KEY] == \
            FIX.DERIVATION_GATE_RESULT, (
            "fixture invariant: the mutant's OTHER machine dim is honest — it "
            "must fail for the one reason under test")
        assert 0.99 not in {d["value"] for n, d in fake["vector"].items()
                            if n != "judge_score"}, (
            "fixture invariant: the judge's number never enters the vector — "
            "the recorded value is the measurement, not the claim")
        # the joint refuses fail-closed, before any floor is read...
        ok, reasons = FIX.admission_eligible(fake, vecs["incumbent"])
        FIX.assert_derivation_refused(ok, reasons)
        # ...the stamp battery REDs (the mismatch is out-of-enum custody)...
        with pytest.raises(AssertionError,
                           match=_tag("[SIM4-X6-DERIVATION]")):
            FIX.assert_machine_floors_machine_derived(fake)
        # ...and the value battery names WHY, under its own distinct tag.
        with pytest.raises(AssertionError, match=_tag("[SIM4-X6-MEASURED]")):
            FIX.assert_machine_values_measured_from_evidence(fake)

    def test_declared_residual_self_consistent_fabricated_evidence(self):
        # HONEST BOUNDARY, armed as a test so it cannot rot into a claim: a
        # fabricated replay map whose declared value AGREES with it still
        # reads as machine custody. The vector layer cannot see that the map
        # is not the frozen corpus — that binding lives upstream, at the
        # replay stage that mints the map, and §9.1 ratifies no clause for it
        # here. Recorded verbatim in make_vector's HONEST SCOPE (1).
        vecs = _named_vectors()
        self_consistent = FIX.make_vector({
            "frozen_pass_rate": (1.0, FIX.MACHINE_KIND),
            "frozen_regressions": (0, FIX.MACHINE_KIND),
        }, evidence={"frozen_pass_rate": {"case-001": True},
                     "frozen_regressions": rg.GateResult(outcome=rg.OUTCOME_PASS)})
        assert FIX.machine_derivation_violations(self_consistent) == []
        ok, _ = FIX.admission_eligible(self_consistent, vecs["incumbent"])
        assert ok is True, (
            "this arm PINS the declared residual, it does not celebrate it: "
            "if a future round binds replay maps to the frozen corpus, this "
            "assert flips and the residual paragraph in make_vector's HONEST "
            "SCOPE must be retired in the same commit")

    def test_mutant_judge_derived_number_on_a_machine_floor_REDS(self):
        # THE escape this arm closes (fresh-context review, must-fix 1): a
        # judge number written into a machine dim satisfied a MACHINE floor
        # because the floor law read the `kind` label and nothing bound the
        # VALUE to machine evidence. The pack is machine-plausible — 0.99
        # pass rate, zero regressions, `kind: machine` on both floor dims.
        vecs = _named_vectors()
        proxy = FIX.mutant_judge_number_into_machine_dim(judge_score=0.99)
        assert all(d["kind"] == FIX.MACHINE_KIND
                   for n, d in proxy["vector"].items()
                   if n != "judge_score"), "fixture invariant"
        assert proxy["vector"]["frozen_pass_rate"]["value"] > \
            FIX.machine_dims(vecs["incumbent"])["frozen_pass_rate"], (
            "fixture invariant: the judge number must CLEAR the machine floor "
            "numerically — otherwise the refusal proves nothing")
        # the joint refuses, citing the derivation (not merely a floor)...
        ok, reasons = FIX.admission_eligible(proxy, vecs["incumbent"])
        FIX.assert_derivation_refused(ok, reasons)
        # ...and the standalone battery REDs on the same pack.
        with pytest.raises(AssertionError,
                           match=_tag("[SIM4-X6-DERIVATION]")):
            FIX.assert_machine_floors_machine_derived(proxy)

    def test_mutant_unprovenanced_machine_dim_REDS(self):
        # fail-closed direction: a machine dim with NO derivation (evidence
        # the constructor could not classify) is exactly as untrustworthy as
        # a judge-derived one — absence never satisfies a floor (L239).
        vecs = _named_vectors()
        naked = FIX.make_vector({
            "frozen_pass_rate": (0.99, FIX.MACHINE_KIND),
            "frozen_regressions": (0, FIX.MACHINE_KIND),
        })
        assert naked["vector"]["frozen_pass_rate"][FIX.DERIVATION_KEY] is None
        ok, reasons = FIX.admission_eligible(naked, vecs["incumbent"])
        FIX.assert_derivation_refused(ok, reasons)
        with pytest.raises(AssertionError,
                           match=_tag("[SIM4-X6-DERIVATION]")):
            FIX.assert_machine_floors_machine_derived(naked)

    def test_a_laundered_incumbent_refuses_too(self):
        # both sides of the joint are checked: a laundered INCUMBENT would
        # otherwise let a real candidate "improve" over a judge number.
        vecs = _named_vectors()
        proxy = FIX.mutant_judge_number_into_machine_dim(judge_score=0.10)
        ok, reasons = FIX.admission_eligible(vecs["improving"], proxy)
        FIX.assert_derivation_refused(ok, reasons)
        assert any("incumbent" in r for r in reasons)

    def test_mutant_promotion_joint_on_judge_evidence_REDS(self):
        # §9.2: machine/judge artifacts never promote a mission edge — the
        # reference predicate refuses; a predicate consuming the high league/
        # judge score as fuel is the named escape.
        evidence = [{"kind": "league_score", "value": 0.99,
                     "candidate": "judge-only"}]
        FIX.assert_no_promotion_without_human(
            FIX.reference_edge_promotion(evidence))
        with pytest.raises(AssertionError, match=_tag("[SIM2X-LEAGUE-FUEL]")):
            FIX.assert_no_promotion_without_human(
                FIX.mutant_promotes_on_league_score(evidence))


# ===========================================================================
# sim 5 — proxy-overfit winner (X4)
# ===========================================================================
class TestSim5ProxyOverfit:
    def test_divergence_flags_demote_withhold(self):
        out = FIX.divergence_check(public=0.92, private=0.58)
        FIX.assert_sim5_divergence_flagged(out)

    def test_non_divergent_candidate_is_not_flagged(self):
        # honest negative: aligned aggregates emit NO signal (a comparator
        # that flags everything is as useless as one that flags nothing).
        out = FIX.divergence_check(public=0.80, private=0.78)
        assert out["divergent"] is False and out["signal"] is None
        assert "public" in out and "private" in out

    def test_mutant_silent_average_REDS(self):
        # the §12 named escape: the divergence averaged away into a single
        # scalar — both aggregate keys vanish and no signal is emitted.
        out = FIX.mutant_average_divergence(public=0.92, private=0.58)
        assert out == {"aggregate": 0.75}, "fixture invariant"
        with pytest.raises(AssertionError,
                           match=_tag("[SIM5-NO-SILENT-AVERAGE]")):
            FIX.assert_sim5_divergence_flagged(out)


# ===========================================================================
# sim 8 — nondeterministic scorer (triple-run discipline + quarantine)
# ===========================================================================
class TestSim8NondeterministicScorer:
    def test_deterministic_scorer_is_stable_across_the_triple(self, tmp_path):
        script = FIX.write_scorer(tmp_path, "det_scorer.py", FIX.DET_SCORER_SRC)
        outs = FIX.run_scorer_triple(script, tmp_path)
        assert FIX.classify_determinism(outs) == "deterministic"
        assert isinstance(FIX.quarantine_fold(outs), float)

    def test_nondeterministic_scorer_is_flagged_and_quarantined(self, tmp_path):
        # 3 subprocess runs under 3 DISTINCT PYTHONHASHSEED values on
        # identical input (§12 sim 8): the hash()-keyed scorer varies; its
        # scores land quarantined `unknown`, never averaged.
        script = FIX.write_scorer(tmp_path, "nondet_scorer.py",
                                  FIX.NONDET_SCORER_SRC)
        outs = FIX.run_scorer_triple(script, tmp_path)
        assert FIX.classify_determinism(outs) == "nondeterministic", (
            "fixture invariant: hash() must vary across distinct "
            f"PYTHONHASHSEED runs (got {outs})")
        FIX.assert_sim8_quarantined(FIX.quarantine_fold(outs))

    def test_quarantined_unknown_never_satisfies_a_floor(self, tmp_path):
        # the L239 join: an `unknown` machine dim can never make a candidate
        # eligible — quarantine composes with the §9.1 floor law. The dim is
        # honestly provenanced (the REAL triple-run outputs of the REAL
        # nondeterministic scorer), so the refusal is the UNKNOWN law and not
        # a missing-derivation artefact.
        script = FIX.write_scorer(tmp_path, "nondet_scorer.py",
                                  FIX.NONDET_SCORER_SRC)
        triple = FIX.run_scorer_triple(script, tmp_path)
        vecs = _named_vectors()
        quarantined = FIX.make_vector({
            "frozen_pass_rate": (FIX.quarantine_fold(triple), FIX.MACHINE_KIND),
            "frozen_regressions": (0, FIX.MACHINE_KIND),
            "judge_score": (0.99, FIX.JUDGE_KIND),
        }, evidence={
            "frozen_pass_rate": triple,
            "frozen_regressions": rg.GateResult(outcome=rg.OUTCOME_PASS),
            "judge_score": FIX.JudgeEvidence(0.99)})
        assert quarantined["vector"]["frozen_pass_rate"]["value"] == FIX.UNKNOWN
        ok, reasons = FIX.admission_eligible(quarantined, vecs["incumbent"])
        assert ok is False and any("[FLOOR-UNKNOWN]" in r for r in reasons)
        assert not any("[FLOOR-DERIVATION]" in r for r in reasons), (
            "fixture invariant: the quarantined dim IS machine-derived — it "
            "fails the UNKNOWN law, not the custody law")

    def test_quarantined_scorer_never_outranks_known_evidence(self):
        vecs = dict(_named_vectors())
        triple = ["0.117", "0.640", "0.902"]
        vecs["quarantined"] = FIX.make_vector({
            "frozen_pass_rate": (FIX.UNKNOWN, FIX.MACHINE_KIND),
            "frozen_regressions": (FIX.UNKNOWN, FIX.MACHINE_KIND),
            "judge_score": (0.99, FIX.JUDGE_KIND),
        }, evidence={"frozen_pass_rate": triple, "frozen_regressions": triple,
                     "judge_score": FIX.JudgeEvidence(0.99)})
        rank = FIX.rank_by_machine(vecs, incumbent="incumbent")
        assert rank[-1] == "quarantined", (
            "[SIM8-QUARANTINE] quarantined evidence sorts LAST — it can "
            "never rank above measured machine outcomes")

    def test_mutant_average_into_the_vector_REDS(self, tmp_path):
        # the §12 named escape: the three differing outputs averaged into a
        # single number entering the vector.
        script = FIX.write_scorer(tmp_path, "nondet_scorer.py",
                                  FIX.NONDET_SCORER_SRC)
        outs = FIX.run_scorer_triple(script, tmp_path)
        averaged = FIX.mutant_average_fold(outs)
        assert isinstance(averaged, float), "fixture invariant"
        with pytest.raises(AssertionError, match=_tag("[SIM8-QUARANTINE]")):
            FIX.assert_sim8_quarantined(averaged)


# ===========================================================================
# the §4 ARMING battery — REAL predicate + REAL seam on a scratch root
# ===========================================================================
class TestArmingBattery:
    def _corpus(self, tmp_path):
        return FIX.write_scratch_corpus(tmp_path / "corpus", IDS)

    def test_honest_pass_demo_end_to_end(self, tmp_path, monkeypatch):
        # §4.2 exit-evidence shape at fixture scale: the improving candidate
        # (fixes >=1 frozen case, regresses none) rides the REAL evaluate_gate
        # + the REAL ratify seam; every stage present + non-vacuous; verdict
        # pass; evidence confined to the scratch root; candidate stages run
        # under the scrubbed ALLOWLIST env with the outside tree untouched.
        monkeypatch.setenv(FIX.CANARY_ENV, "live-credential-fixture")
        scratch_root = FIX.make_scratch_gate_root(tmp_path)
        workdir = tmp_path / "candidate-workdir"
        workdir.mkdir()
        outside = tmp_path / "outside-live-tree"
        outside.mkdir()
        (outside / "sentinel.txt").write_text("live", encoding="utf-8")
        before = FIX.snapshot_tree(outside)
        repo_evidence = _REPO / "shared" / "interfaces" / "gate-evidence"
        repo_evidence_before = FIX.snapshot_tree(repo_evidence)

        pack = FIX.reference_arming_composition(
            scratch_root=scratch_root, corpus_dir=self._corpus(tmp_path),
            baseline=BASELINE, candidate=IMPROVING,
            proposal={"id": "cand-improving", "diff": FIX.FIXTURE_DIFF,
                      "workdir": str(workdir)},
            runner=FIX.make_scrubbed_runner(workdir))
        FIX.assert_arm_honest_pass(pack)
        FIX.assert_arm_escape(workdir, outside_before=before,
                              outside_after=FIX.snapshot_tree(outside))
        # evidence pack landed UNDER the scratch root...
        edir = gate_mod.evidence_dir(scratch_root)
        assert list(edir.glob("pack-*.json")), "scratch evidence pack missing"
        assert (edir / "variants").exists(), "S4 variant archive missing"
        # ...and the LIVE repo's gate-evidence surface is byte-identical.
        assert FIX.snapshot_tree(repo_evidence) == repo_evidence_before, (
            "[ARM-CONFINEMENT] a fixture ratify wrote into the repo's "
            "gate-evidence surface — the scratch root= injection leaked")

    def test_known_bad_fails_the_same_composition(self, tmp_path):
        pack = FIX.reference_arming_composition(
            scratch_root=FIX.make_scratch_gate_root(tmp_path),
            corpus_dir=self._corpus(tmp_path),
            baseline=BASELINE, candidate=KNOWN_BAD)
        FIX.assert_arm_known_bad_refused(pack, case="case-003")
        assert pack["ratify"] is None, (
            "a regression-failing candidate must short-circuit BEFORE ratify")

    def test_empty_corpus_no_verdict_refuses_with_the_named_reason(self, tmp_path):
        empty = tmp_path / "empty-corpus"
        empty.mkdir()
        pack = FIX.reference_arming_composition(
            scratch_root=FIX.make_scratch_gate_root(tmp_path),
            corpus_dir=empty, baseline={}, candidate={})
        FIX.assert_arm_no_verdict_refusal(pack)
        assert pack["ratify"] is None

    def test_flat_candidate_is_an_honest_negative(self, tmp_path):
        pack = FIX.reference_arming_composition(
            scratch_root=FIX.make_scratch_gate_root(tmp_path),
            corpus_dir=self._corpus(tmp_path),
            baseline=BASELINE, candidate=FLAT)
        FIX.assert_arm_flat_honest_negative(pack)
        assert pack["ratify"] is None

    # ---- §4.5 negative controls, BOTH directions on BOTH arms ------------
    def test_mutant_no_verdict_to_pass_REDS(self, tmp_path):
        empty = tmp_path / "empty-corpus"
        empty.mkdir()
        pack = FIX.reference_arming_composition(
            scratch_root=FIX.make_scratch_gate_root(tmp_path),
            corpus_dir=empty, baseline={}, candidate={},
            decision=FIX.mutant_no_verdict_to_pass)
        assert pack["admission"] == FIX.ADMISSION_ELIGIBLE, "fixture invariant"
        with pytest.raises(AssertionError, match=_tag("[ARM-NOVERDICT]")):
            FIX.assert_arm_no_verdict_refusal(pack)

    def test_mutant_no_verdict_to_fail_REDS(self, tmp_path):
        empty = tmp_path / "empty-corpus"
        empty.mkdir()
        pack = FIX.reference_arming_composition(
            scratch_root=FIX.make_scratch_gate_root(tmp_path),
            corpus_dir=empty, baseline={}, candidate={},
            decision=FIX.mutant_no_verdict_to_fail)
        assert pack["regression"]["outcome"] == rg.OUTCOME_FAIL, \
            "fixture invariant: the mutant misrecords absence as regression"
        with pytest.raises(AssertionError, match=_tag("[ARM-NOVERDICT]")):
            FIX.assert_arm_no_verdict_refusal(pack)

    def test_mutant_flat_to_pass_REDS(self, tmp_path):
        pack = FIX.reference_arming_composition(
            scratch_root=FIX.make_scratch_gate_root(tmp_path),
            corpus_dir=self._corpus(tmp_path),
            baseline=BASELINE, candidate=FLAT,
            decision=FIX.mutant_flat_to_pass)
        assert pack["admission"] == FIX.ADMISSION_ELIGIBLE, "fixture invariant"
        with pytest.raises(AssertionError, match=_tag("[ARM-FLAT]")):
            FIX.assert_arm_flat_honest_negative(pack)

    def test_mutant_flat_to_error_REDS(self, tmp_path):
        pack = FIX.reference_arming_composition(
            scratch_root=FIX.make_scratch_gate_root(tmp_path),
            corpus_dir=self._corpus(tmp_path),
            baseline=BASELINE, candidate=FLAT,
            decision=FIX.mutant_flat_to_error)
        assert pack["regression"]["outcome"] == rg.OUTCOME_NO_VERDICT, \
            "fixture invariant: the mutant misrecords the honest negative"
        with pytest.raises(AssertionError, match=_tag("[ARM-FLAT]")):
            FIX.assert_arm_flat_honest_negative(pack)

    # ---- escape negative controls ----------------------------------------
    def test_mutant_env_passthrough_REDS(self, tmp_path, monkeypatch):
        monkeypatch.setenv(FIX.CANARY_ENV, "live-credential-fixture")
        workdir = tmp_path / "candidate-workdir"
        workdir.mkdir()
        outside = tmp_path / "outside-live-tree"
        outside.mkdir()
        before = FIX.snapshot_tree(outside)
        FIX.reference_arming_composition(
            scratch_root=FIX.make_scratch_gate_root(tmp_path),
            corpus_dir=self._corpus(tmp_path),
            baseline=BASELINE, candidate=IMPROVING,
            proposal={"id": "cand-escape", "diff": FIX.FIXTURE_DIFF,
                      "workdir": str(workdir)},
            runner=FIX.make_passthrough_mutant_runner(workdir))
        with pytest.raises(AssertionError, match=_tag("[ARM-ESCAPE]")):
            FIX.assert_arm_escape(workdir, outside_before=before,
                                  outside_after=FIX.snapshot_tree(outside))

    def test_mutant_partial_credential_leak_REDS(self, tmp_path, monkeypatch):
        # N7: the escape arm was ONE named canary, but the child env carried
        # other vars — a harness leaking a DIFFERENT credential var would have
        # sailed through. This mutant scrubs the canary and leaks
        # ANTHROPIC_OAUTH_TOKEN instead; §4.4 is an allowlist law about the
        # credential CLASS, so it must still RED.
        monkeypatch.setenv(FIX.CANARY_ENV, "live-credential-fixture")
        workdir = tmp_path / "candidate-workdir"
        workdir.mkdir()
        outside = tmp_path / "outside-live-tree"
        outside.mkdir()
        before = FIX.snapshot_tree(outside)
        FIX.reference_arming_composition(
            scratch_root=FIX.make_scratch_gate_root(tmp_path),
            corpus_dir=self._corpus(tmp_path),
            baseline=BASELINE, candidate=IMPROVING,
            proposal={"id": "cand-partial-leak", "diff": FIX.FIXTURE_DIFF,
                      "workdir": str(workdir)},
            runner=FIX.make_partial_leak_mutant_runner(workdir))
        env = FIX.observed_env(workdir, "S1_verify")
        assert FIX.CANARY_ENV not in env, (
            "fixture invariant: the canary is scrubbed, so the OLD single-name "
            "assert would have passed this leak")
        assert FIX.LEAK_ENV in env, "fixture invariant: the leak must land"
        with pytest.raises(AssertionError, match=_tag("[ARM-ESCAPE]")):
            FIX.assert_arm_escape(workdir, outside_before=before,
                                  outside_after=FIX.snapshot_tree(outside))

    def test_scrubbed_env_carries_no_credential_shaped_name(self, tmp_path,
                                                            monkeypatch):
        # the honest positive: the reference allowlist env survives the CLASS
        # check (a pattern that flagged everything would be as useless as one
        # that flagged nothing).
        monkeypatch.setenv(FIX.CANARY_ENV, "live-credential-fixture")
        workdir = tmp_path / "candidate-workdir"
        workdir.mkdir()
        FIX.reference_arming_composition(
            scratch_root=FIX.make_scratch_gate_root(tmp_path),
            corpus_dir=self._corpus(tmp_path),
            baseline=BASELINE, candidate=IMPROVING,
            proposal={"id": "cand-clean-env", "diff": FIX.FIXTURE_DIFF,
                      "workdir": str(workdir)},
            runner=FIX.make_scrubbed_runner(workdir))
        env = FIX.observed_env(workdir, "S1_verify")
        # the harness's explicit dict is {PATH, PYTHONHASHSEED} — but the OS
        # injects locale vars BELOW it (macOS adds LC_CTYPE and
        # __CF_USER_TEXT_ENCODING even to an explicit env), so an exact-set
        # claim would be FALSE. That is precisely why the escape arm checks
        # the credential CLASS and not an exact allowlist: the harness cannot
        # honestly promise "only these two names reach the child".
        assert {"PATH", "PYTHONHASHSEED"} <= set(env), (
            f"the allowlist env lost its own vars: {sorted(env)}")
        assert [n for n in env if FIX.CREDENTIAL_ENV_RE.search(n)] == [], (
            f"a credential-shaped name reached the child: {sorted(env)}")
        assert FIX.CANARY_ENV not in env and FIX.LEAK_ENV not in env
        # non-vacuity: the LIVE env is far larger, so this is a real scrub and
        # not an accident of an already-empty environment.
        assert len(env) < len(os.environ), (
            "the child env is not smaller than the live env — nothing was "
            "actually scrubbed")

    def test_mutant_outside_writer_REDS(self, tmp_path, monkeypatch):
        monkeypatch.setenv(FIX.CANARY_ENV, "live-credential-fixture")
        workdir = tmp_path / "candidate-workdir"
        workdir.mkdir()
        outside = tmp_path / "outside-live-tree"
        outside.mkdir()
        before = FIX.snapshot_tree(outside)
        FIX.reference_arming_composition(
            scratch_root=FIX.make_scratch_gate_root(tmp_path),
            corpus_dir=self._corpus(tmp_path),
            baseline=BASELINE, candidate=IMPROVING,
            proposal={"id": "cand-outside", "diff": FIX.FIXTURE_DIFF,
                      "workdir": str(workdir)},
            runner=FIX.make_outside_writer_mutant_runner(workdir, outside))
        with pytest.raises(AssertionError, match=_tag("[ARM-ESCAPE]")):
            FIX.assert_arm_escape(workdir, outside_before=before,
                                  outside_after=FIX.snapshot_tree(outside))

    def test_ring0_diff_refuses_on_the_scratch_root(self, tmp_path):
        # the S0 law holds through the seam: a diff touching the scratch
        # root's Ring-0 listing REFUSES (generator-refusal's law-source, §8.2).
        pack = FIX.reference_arming_composition(
            scratch_root=FIX.make_scratch_gate_root(tmp_path),
            corpus_dir=self._corpus(tmp_path),
            baseline=BASELINE, candidate=IMPROVING,
            proposal={"id": "cand-ring0", "diff": FIX.RING0_DIFF})
        assert pack["ratify"]["verdict"] == "refused"
        assert pack["admission"] == FIX.ADMISSION_REFUSED


# ===========================================================================
# §9.3 — certainty grammar tripwires + SIM-2 extension arms
# ===========================================================================
class TestVocabularyTripwires:
    def test_reference_league_artifacts_speak_machine_class(self):
        rows = [FIX.make_league_row(f"cand-{i}", scored=0.5 + i / 100,
                                    ranked=i) for i in range(3)]
        for row in rows:
            FIX.assert_machine_class_vocab(row)
            FIX.assert_league_row_closed_shape(row)
            assert row["certainty"] == FIX.P5_CAP  # capped at P5, never higher

    @pytest.mark.parametrize("claim", (
        "candidate tested on live traffic",
        "hypothesis falsified by the league",
        "it worked in production",
    ))
    def test_captain_vocabulary_in_a_foundry_artifact_REDS(self, claim):
        row = FIX.make_league_row("cand-x", scored=0.9, ranked=1)
        row["summary"] = claim
        assert FIX.vocab_violations(row), "fixture invariant: scan must see it"
        with pytest.raises(AssertionError, match=_tag("[VOCAB]")):
            FIX.assert_machine_class_vocab(row)

    def test_machine_speak_does_not_false_positive(self):
        # scored/ranked/observed (and 'attested'/'protested' — word-boundary
        # honesty) never trip the scan.
        row = FIX.make_league_row("cand-y", scored=0.7, ranked=2)
        row["summary"] = ("candidate scored 0.7, ranked 2, observed on 20 "
                          "public cases; result attested; nothing protested")
        assert FIX.vocab_violations(row) == []

    # ---- the KEY arm: the vocabulary is spoken by field names too --------
    def test_captain_vocabulary_in_a_FIELD_NAME_REDS(self):
        # the escape a values-only walk was blind to (must-fix 2i): a foundry
        # artifact minting `{"tested": true, "falsified": false}` as KEYS says
        # the Captain word just as loudly, and the tripwire stayed green.
        row = FIX.mutant_league_row_captain_vocab_keys("cand-k", scored=0.9,
                                                       ranked=1)
        violations = FIX.vocab_violations(row)
        assert len(violations) == 2 and all("<key>" in v for v in violations), (
            f"fixture invariant: both KEYS must be seen ({violations})")
        with pytest.raises(AssertionError, match=_tag("[VOCAB]")):
            FIX.assert_machine_class_vocab(row)

    def test_nested_captain_vocabulary_keys_are_seen_at_depth(self):
        # the walk must reach keys inside nested mappings and lists, not just
        # the top level (a scan that only sees depth 0 is the same hole).
        row = FIX.make_league_row("cand-n", scored=0.5, ranked=1)
        row["runs"] = [{"detail": {"falsified": False}}]
        assert FIX.vocab_violations(row), "fixture invariant: depth must be seen"
        with pytest.raises(AssertionError, match=_tag("[VOCAB]")):
            FIX.assert_machine_class_vocab(row)

    def test_machine_speak_keys_do_not_false_positive(self):
        # the honest negative for the key walk: the reference row's own keys
        # (candidate/scored/ranked/observed/fitness_claim/certainty) and
        # near-miss words must never trip the scan.
        row = FIX.make_league_row("cand-w", scored=0.7, ranked=2)
        row["contested"] = True
        row["attested_by"] = "harness"
        assert FIX.vocab_violations(row) == []
        FIX.assert_machine_class_vocab(row)

    # ---- the P5 cap, bound to the states.py ladder -----------------------
    def test_p5_cap_ladder_is_derived_from_the_states_bytes(self):
        # the cap is READ from framework/objectives/states.py, never a
        # hardcoded list: the states ABOVE it are exactly those
        # derive_edge_state can reach only through human-verdict fuel.
        ladder = FIX.estate_certainty_ladder()
        assert ladder["cap"] == FIX.P5_CAP
        assert ladder["human_fuel_flags"], (
            "the scan found no human-verdict fuel flags — states.py:34-39 "
            "names them as the ONLY promotion/refutation fuel")
        assert FIX.P5_CAP in ladder["machine_reachable"]
        assert ladder["above_cap"] and \
            ladder["above_cap"] <= ladder["all_states"], (
            "the above-cap set must be a non-empty subset of the real tokens")
        # the two above-cap states are the human-only rungs; neither is
        # reachable without human fuel, which is WHY the cap exists.
        assert FIX.estate_constant(FIX.STATES_REL,
                                   "STATE_INTERVENTION_SUPPORTED") in \
            ladder["above_cap"]
        assert FIX.estate_constant(FIX.STATES_REL, "STATE_FALSIFIED") in \
            ladder["above_cap"]

    def test_ladder_scan_is_a_discriminator_not_a_constant(self):
        # vacuity proof (the probe-flip idiom): feed a MUTATED states.py in
        # which the P2 rule no longer tests the human-fuel flag, and the
        # derived sets must MOVE — otherwise the scan proves nothing.
        real = (_REPO / FIX.STATES_REL).read_text(encoding="utf-8")
        assert "    if any_human_wrong:" in real, "fixture invariant (P2 rule)"
        mutated = real.replace("    if any_human_wrong:", "    if any_supporting:")
        moved = FIX.estate_certainty_ladder(source=mutated)
        base = FIX.estate_certainty_ladder(source=real)
        falsified = FIX.estate_constant(FIX.STATES_REL, "STATE_FALSIFIED")
        assert falsified in base["above_cap"], "fixture invariant"
        assert falsified in moved["machine_reachable"] and \
            falsified not in moved["above_cap"], (
            "the ladder scan did not react to a changed guard — it is a "
            "constant, not a read of the real rules")

    def test_reference_rows_are_capped_at_p5(self):
        row = FIX.make_league_row("cand-c", scored=0.6, ranked=1)
        FIX.assert_certainty_capped(row)
        assert row["certainty"] == FIX.P5_CAP

    @pytest.mark.parametrize("old,new,why", (
        ('source == HUMAN_VERDICT_SOURCE', 'source == "any"',
         "no rung is human-gated any more, so the ladder derives an EMPTY "
         "above-cap set and would pass any certainty"),
        ('STATE_OBSERVATIONALLY_SUPPORTED = "observationally_supported"',
         'STATE_OBSERVATIONALLY_SUPPORTED = "observationally_supported_v2"',
         "the P5 cap token drifted out from under the corpus"),
    ))
    def test_mutant_broken_ladder_scan_REDS(self, old, new, why):
        # N4 (re-review): [P5-LADDER] was the only new tag with no paired
        # pytest.raises arm — proven non-vacuous by hand, unarmed in the
        # corpus. Both integrity guards are now armed against a genuinely
        # BROKEN states.py (fed through the same `source` seam the
        # discriminator proof uses), not against a hand-made ladder dict.
        real = (_REPO / FIX.STATES_REL).read_text(encoding="utf-8")
        assert old in real, f"fixture invariant: {old!r} must exist to mutate"
        mutated = real.replace(old, new)
        # a HONEST row — the certainty is at the cap, so anything that REDs
        # here is the ladder integrity guard and never a cap violation.
        row = FIX.make_league_row("cand-l", scored=0.6, ranked=1)
        FIX.assert_certainty_capped(row, source=real)      # honest negative
        with pytest.raises(AssertionError, match=_tag("[P5-LADDER]")):
            FIX.assert_certainty_capped(row, source=mutated)

    @pytest.mark.parametrize("state_name", ("STATE_INTERVENTION_SUPPORTED",
                                            "STATE_FALSIFIED"))
    def test_mutant_certainty_above_the_p5_cap_REDS(self, state_name):
        # must-fix 2ii: an ABOVE-cap certainty passed both the vocabulary
        # scan and the closed-row shape. `intervention_supported` is the
        # sharp case — a real states.py P3 token whose Captain word is
        # literally 'tested', carrying none of the banned words.
        row = FIX.mutant_league_row_above_cap("cand-p", state_name=state_name,
                                              scored=0.9, ranked=1)
        assert row["certainty"] == FIX.estate_constant(FIX.STATES_REL,
                                                       state_name), "invariant"
        with pytest.raises(AssertionError, match=_tag("[P5-CAP]")):
            FIX.assert_certainty_capped(row)
        # ...and the cap now rides the closed-shape battery, so every
        # row-validating caller inherits it.
        with pytest.raises(AssertionError, match=_tag("[P5-CAP]")):
            FIX.assert_league_row_closed_shape(row)

    def test_mutant_intervention_supported_slips_the_vocabulary_scan(self):
        # the exact reason the cap needs its OWN binding: the P3 token is
        # invisible to the Captain-vocabulary regex, so the word scan can
        # never be the cap's enforcement.
        row = FIX.mutant_league_row_above_cap(
            "cand-p", state_name="STATE_INTERVENTION_SUPPORTED",
            scored=0.9, ranked=1)
        assert FIX.vocab_violations(row) == [], (
            "fixture invariant: the vocabulary scan is blind to this token — "
            "that blindness IS the hole assert_certainty_capped closes")

    @pytest.mark.parametrize("token", (None, "observed", "tested", "green"))
    def test_certainty_outside_the_states_vocabulary_REDS(self, token):
        # fail closed: an absent certainty, the Captain WORD ('observed' is
        # the presentation word for P5, never the stored token), or any
        # invented token are all refused — no second drifting enum (§5.2).
        row = FIX.make_league_row("cand-o", scored=0.5, ranked=1)
        if token is None:
            del row["certainty"]
        else:
            row["certainty"] = token
        with pytest.raises(AssertionError, match=_tag("[P5-CAP]")):
            FIX.assert_certainty_capped(row)

    def test_sim2_extension_league_writes_verdict_human_REDS(self):
        # §9.3 arm (a): a foundry code path minting review.source
        # verdict_human is the machine speaking as the human channel.
        clean = FIX.make_league_row("cand-z", scored=0.8, ranked=1)
        FIX.assert_league_row_closed_shape(clean)
        mutant = FIX.mutant_league_row_verdict_human("cand-z", scored=0.8,
                                                     ranked=1)
        with pytest.raises(AssertionError, match=_tag("[SIM2X-VH]")):
            FIX.assert_league_row_closed_shape(mutant)

    def test_sim2_extension_forged_league_row_cannot_promote_REDS(self):
        # N1: the two §9.3 arms were never COMPOSED — the minting battery
        # REDs on a league row that mints review.source verdict_human, but
        # the promotion predicate read `review.source` off any dict, so the
        # forged row walked into the joint with the battery uncalled.
        forged = FIX.mutant_league_row_verdict_human("cand-forge", scored=0.99,
                                                     ranked=1)
        assert forged["review"]["source"] == FIX.HUMAN_VERDICT_SOURCE, "invariant"
        # (a) the minting battery still REDs on the forgery...
        with pytest.raises(AssertionError, match=_tag("[SIM2X-VH]")):
            FIX.assert_league_row_closed_shape(forged)
        # (b) ...and the JOINT refuses it too: machine class never promotes.
        assert FIX.reference_edge_promotion([forged]) is False
        FIX.assert_no_promotion_without_human(
            FIX.reference_edge_promotion([forged]))
        # (c) the class-blind predicate (the shape before this fix) promotes
        #     on the forgery — the named escape, proven biting.
        assert FIX.mutant_promotes_on_forged_league_review([forged]) is True, (
            "fixture invariant: the class-blind predicate must actually "
            "promote on the forged row")
        with pytest.raises(AssertionError, match=_tag("[SIM2X-LEAGUE-FUEL]")):
            FIX.assert_no_promotion_without_human(
                FIX.mutant_promotes_on_forged_league_review([forged]))

    def test_composed_battery_runs_minting_and_joint_together(self):
        # the composition itself, as a re-runnable battery: a CLEAN league row
        # beside a real human verdict passes; the forged row REDs.
        clean = FIX.make_league_row("cand-clean", scored=0.8, ranked=1)
        FIX.assert_machine_class_never_promotes(
            [clean], FIX.reference_edge_promotion([clean]))
        forged = FIX.mutant_league_row_verdict_human("cand-forge", scored=0.99,
                                                     ranked=1)
        with pytest.raises(AssertionError, match=_tag("[SIM2X-VH]")):
            FIX.assert_machine_class_never_promotes(
                [forged], FIX.reference_edge_promotion([forged]))
        # and the joint arm of the SAME battery bites when a predicate did
        # promote on machine-class evidence.
        with pytest.raises(AssertionError, match=_tag("[SIM2X-FORGED-VH]")):
            FIX.assert_machine_class_never_promotes([clean], True)

    def test_a_real_human_verdict_still_promotes(self):
        # the honest negative for the class check: the human channel must not
        # be broken by it — a non-machine-class human verdict still promotes.
        human = [{"review": {"verdict": "confirmed",
                             "source": FIX.HUMAN_VERDICT_SOURCE}}]
        assert FIX.reference_edge_promotion(human) is True
        assert FIX.is_machine_class_artifact(human[0]) is False

    def test_sim2_extension_promotes_on_league_score_REDS(self):
        # §9.3 arm (b): an edge/graduation predicate consuming a league score
        # as promotion fuel. The reference predicate promotes ONLY on a human
        # verdict; the mutant promotes on the machine number.
        human = [{"review": {"verdict": "confirmed",
                             "source": FIX.HUMAN_VERDICT_SOURCE}}]
        assert FIX.reference_edge_promotion(human) is True
        league_only = [{"kind": "league_score", "value": 0.97}]
        FIX.assert_no_promotion_without_human(
            FIX.reference_edge_promotion(league_only))
        with pytest.raises(AssertionError, match=_tag("[SIM2X-LEAGUE-FUEL]")):
            FIX.assert_no_promotion_without_human(
                FIX.mutant_promotes_on_league_score(league_only))


# ===========================================================================
# REAL-SURFACE arms — vacuity-guarded (the mergeability pattern)
# ===========================================================================
GUARDED_SURFACES = {
    "scorers": _REPO / "framework/evolution/scorers.py",
    "candidate": _REPO / "framework/evolution/candidate.py",
    "gate-arm-cli": _REPO / FIX.GATE_ARM_CLI_REL,
}


class TestRealSurfaceArmsVacuityGuarded:
    @pytest.mark.parametrize("name", sorted(GUARDED_SURFACES))
    def test_absence_companion(self, name):
        # COMPANION absence assertion: REDs the instant the surface lands so
        # the sibling skip cannot silently persist (§13).
        path = GUARDED_SURFACES[name]
        assert not path.exists(), (
            f"{path.relative_to(_REPO)} LANDED — retire the paired vacuity "
            "skip (see its docstring): run the SAME lib_cog5_scoring_fixtures "
            "assert batteries over the landed surface (integrator corpus "
            "surgery per §13).")

    @pytest.mark.parametrize("module", (FIX.SCORERS_MODULE,
                                        FIX.CANDIDATE_MODULE))
    def test_armed_import_probe_fails_on_the_bare_tree(self, module, tmp_path):
        rc, err = FIX.import_probe(module, _REPO, tmp_path)
        assert rc != 0 and "No module named" in err, (
            f"{module} imports on the supposedly-bare tree — the vacuity "
            "guard premise is false")

    def test_probe_flips_when_a_surface_lands(self, tmp_path):
        # fixture proof: the probe is a DISCRIMINATOR — it fails on a bare
        # scratch tree and succeeds the moment the surface exists there.
        tree = tmp_path / "scratch-repo"
        tree.mkdir()
        rc_bare, err_bare = FIX.import_probe(FIX.SCORERS_MODULE, tree, tmp_path)
        assert rc_bare != 0 and "No module named" in err_bare
        FIX.plant_evolution_module(tree, "scorers")
        rc_landed, err_landed = FIX.import_probe(FIX.SCORERS_MODULE, tree,
                                                 tmp_path)
        assert rc_landed == 0, err_landed

    @pytest.mark.parametrize("name", sorted(GUARDED_SURFACES))
    def test_real_surface_arm_guarded(self, name):
        """RETIREMENT CONDITION: retire this skip when the named surface
        lands — framework/evolution/scorers.py + candidate.py (W-build) and
        cabinet/scripts/cog5-gate-arm.py (§4.3). Replacement body = the SAME
        lib batteries the live tier proves today: rank/eligibility/quarantine
        asserts over the real scorer output (sims 2/3/4/8), and the arming
        asserts (assert_arm_*) over the real CLI composition — run against
        the landed surface, UNMODIFIED (§13; contradictions route to the
        integrator)."""
        if GUARDED_SURFACES[name].exists():
            pytest.fail(f"{name} landed but the guard was not retired — "
                        "the absence companion above should already be RED")
        pytest.skip(f"{name} not yet built — vacuity guard armed by the "
                    "ModuleNotFound probe; retire per docstring when it lands")
