"""COG-5 W2 T2 — LEAGUE CLOSURE + the §6.2 provenance-laundering arm + the
§9.1 fitness-vector law (contract cognitive-core-phase-5-contract-2026-07-24
§6.2/§6.3/§7-vector/§8.1; the exit battery names this file verbatim:
"`test_cog5_league_closed.py` incl. the §6.2 provenance laundering arm").
Tests-first: `framework/evolution/league.py` and the §6.3 arming record
`docs/plans/cog5-league-arming-record-2026-07-24.yml` do NOT exist on this
tree (the record ships at exit).

TWO TIERS (the COG-4 W2 mergeability idiom — this suite merges GREEN on the
bare tree):

  * FIXTURE-MACHINERY tests run LIVE NOW against the reference machinery in
    `lib_cog5_scoring_fixtures.py`: the chain-of-custody INGESTER (provenance
    stamped from the named source class, never row-supplied), the §6.2
    counting predicate (ONLY real_live/real_mined from NAMED real sources
    count), the closure validator, the open predicate, and the closed-league
    row shape. Every negative-control mutant is proven BITING in this run —
    the trusting ingester + the count-all counter (provenance LAUNDERING,
    §6.2's named mutant), the open-on-total-rows opener (synthetic volume
    opening the league — the §8.1 law), the live-fitness row + the
    league_open flip (closure), and the table_order-keyed predicate (§9.1's
    named mutant: a scalar reaching an admission joint). A gate without a
    biting mutant is decoration (§12).
  * REAL-SURFACE arms are VACUITY-GUARDED with COMPANION absence assertions
    + armed probes + retirement conditions (§13; the sibling
    test_cog5_sim_scoring.py guards scorers/candidate/the gate-arm CLI —
    this file owns league.py + the arming record so the two suites never
    double-own a guard).

THE LAWS THIS FILE ENCODES (the future league/exit builders bind to these):
  * §6.2 counting predicate: a row counts toward a minimum ONLY when its
    ingester-stamped provenance is real_live/real_mined AND its source class
    is one of the NAMED real sources; missing/out-of-enum provenance REFUSES
    ingestion and never counts; a row arriving with its OWN provenance field
    REFUSES (candidate/league/generator code can never set or rewrite it —
    the §5.2 WALL over the field).
  * §8.1/rule of the sanctioned substrate: synthetic corpora prove plumbing
    and mutants; synthetic may NEVER open the league nor ground a
    live-fitness claim — league_may_open() counts by the predicate above,
    and every closed-league row carries `fitness_claim: "none"`.
  * §6.3 closure: the arming record ships with `league_open: false`, the
    §6.2 minimums VERBATIM, the open-conditions checklist, and
    `holdout_freeze: pending-captain-window` until §7.5 Stage B lands;
    opening is a post-phase amendment event, never a code-existence event.
  * §9.1 vector law: the scorer output separates `vector` (floors) from
    `table_order` (presentation); a composite may order a league table; NO
    scalar reaches any promotion/admission/graduation joint; `unknown` never
    satisfies a floor; judge dims never satisfy a floor (X6).

RETIREMENT CONDITIONS: the league.py guard retires when
`framework/evolution/league.py` lands (run the SAME closure/row-shape/
counting batteries over the real league outputs — integrator corpus surgery
per §13); the arming-record guard retires when
`docs/plans/cog5-league-arming-record-2026-07-24.yml` lands at exit (the
guard body already validates the REAL record bytes via
validate_arming_record the moment the file exists).

S0: interpreter python3.12; no DB, no network. Provenance: authored per the
2026-07-07 full-autonomy grant + the 2026-07-20 cognitive-masterplan
continuous grant (COG-5 §12/§13, W2 T2 — corpus authorship is judgment-tier
work). ORIGINAL BUILD (ab8fe00a): Fable 5. FIX ROUNDS (27197a63 crown-jewel
circumventions; this round's five re-review notes): Opus 5, the program's
primary model from 2026-07-25.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog5_scoring_fixtures as FIX  # noqa: E402

from framework.fidelity import regression_gate as rg  # noqa: E402


def _tag(marker: str) -> str:
    return re.escape(marker)


# the league joint consumes SCORER PACKS, so the §9.1 fixtures here are built
# from the same REAL replay maps + REAL gate results the sim suite uses — a
# machine dim is only a machine dim if it was MEASURED (X6 custody).
IDS = FIX.case_ids(20)
BASELINE = FIX.results_baseline(IDS, learned=15)            # 15/20 = 0.75
IMPROVING = FIX.results_improving(BASELINE, "case-016")     # 16/20 = 0.80


# ---------------------------------------------------------------------------
# shared corpus rows: 12 real (2 strata) + 13 synthetic/sim + 3 refusable
# ---------------------------------------------------------------------------
def real_rows() -> list[dict]:
    rows = []
    for i in range(6):
        rows.append({"source_class": "consequence_ledger",
                     "stratum": "prompt/low", "payload_ref": f"sha-cl-{i}"})
    for i in range(3):
        rows.append({"source_class": "fidelity_receipts",
                     "stratum": "prompt/low", "payload_ref": f"sha-fr-{i}"})
    for i in range(2):
        rows.append({"source_class": "live_emission",
                     "stratum": "retrieval/low", "payload_ref": f"sha-le-{i}"})
    rows.append({"source_class": "verdict_inbox_labels",
                 "stratum": "retrieval/low", "payload_ref": "sha-vi-0"})
    return rows


def synthetic_rows(n: int = 13) -> list[dict]:
    out = []
    for i in range(n):
        source = ("generator", "arena", "sim_replay")[i % 3]
        out.append({"source_class": source, "stratum": "prompt/low",
                    "payload_ref": f"sha-syn-{i}"})
    return out


def refusable_rows() -> list[dict]:
    return [
        # the LAUNDERING attempt: a generator row smuggling its own stamp —
        # candidate/league/generator code can never set provenance (§6.2).
        {"source_class": "generator", "provenance": "real_live",
         "stratum": "prompt/low", "payload_ref": "sha-launder-0"},
        # missing source class → missing provenance derivation → refuse.
        {"stratum": "prompt/low", "payload_ref": "sha-missing-0"},
        # out-of-enum source class → refuse, never counts.
        {"source_class": "webscrape", "stratum": "prompt/low",
         "payload_ref": "sha-oob-0"},
    ]


# ===========================================================================
# §6.2 — chain of custody + the counting predicate + the LAUNDERING mutants
# ===========================================================================
class TestProvenanceChainOfCustody:
    def test_ingester_stamps_from_the_named_source_class(self):
        accepted, refused = FIX.ingest_rows(real_rows() + synthetic_rows())
        assert refused == []
        for row in accepted:
            assert row["provenance"] == \
                FIX.SOURCE_CLASS_TO_PROVENANCE[row["source_class"]]
            assert row["provenance"] in FIX.PROVENANCE_ENUM

    def test_row_supplied_provenance_refuses(self):
        # the WALL over the field: the laundering row REFUSES at ingestion —
        # it never reaches the corpus, so it can never reach a count.
        accepted, refused = FIX.ingest_rows(refusable_rows())
        assert accepted == []
        assert len(refused) == 3
        assert "row-supplied provenance" in refused[0]["refusal"]
        assert "unknown source_class" in refused[1]["refusal"]
        assert "unknown source_class" in refused[2]["refusal"]

    def test_counting_predicate_counts_only_named_real_sources(self):
        accepted, _ = FIX.ingest_rows(real_rows() + synthetic_rows())
        counts = FIX.count_toward_minimums(accepted)
        # 9 real_mined prompt/low; 2 real_live + 1 real_mined retrieval/low;
        # 13 synthetic/sim_replay rows contribute NOTHING.
        assert counts["prompt/low"] == {"real_live": 0, "real_mined": 9,
                                        "counted": 9}
        assert counts["retrieval/low"] == {"real_live": 2, "real_mined": 1,
                                           "counted": 3}
        FIX.assert_count_honest(counts, accepted)

    def test_mutant_count_all_launders_synthetic_REDS(self):
        # §6.2's NAMED mutant: a synthetic/sim_replay-marked row counted
        # toward a minimum.
        accepted, _ = FIX.ingest_rows(real_rows() + synthetic_rows())
        laundered = FIX.mutant_count_all(accepted)
        assert laundered["prompt/low"]["counted"] == 9 + 13, "fixture invariant"
        with pytest.raises(AssertionError, match=_tag("[LC-LAUNDER]")):
            FIX.assert_count_honest(laundered, accepted)

    # ---- the REWRITE direction of the same wall (§6.2 says provenance can
    # ---- never be SET *or* REWRITTEN; only SET was armed) ----------------
    def test_ingestion_seals_the_custody_fields(self):
        accepted, _ = FIX.ingest_rows(real_rows())
        FIX.assert_custody_intact(accepted)
        for row in accepted:
            assert FIX.custody_intact(row) is True
            assert isinstance(row[FIX.CUSTODY_SEAL_KEY], str)

    def test_mutant_provenance_REWRITTEN_after_ingest_REDS(self):
        # N2: a row whose provenance AND source_class are rewritten AFTER
        # ingestion used to count, and assert_count_honest AGREED — it
        # recomputed from the same mutated row, so the laundering was
        # self-consistent. Custody is now bound at ingest, so the rewrite is
        # detectable and the row stops counting.
        accepted, _ = FIX.ingest_rows(real_rows() + synthetic_rows())
        honest_before = FIX.count_toward_minimums(accepted)
        rewritten = FIX.mutant_rewrite_after_ingest(accepted)
        laundered_rows = [r for r in rewritten if not FIX.custody_intact(r)]
        assert len(laundered_rows) >= FIX.REAL_TRAJECTORY_FLOOR, (
            "fixture invariant: the rewrite must launder enough rows to CLEAR "
            f"the §6.2 floor ({len(laundered_rows)} < "
            f"{FIX.REAL_TRAJECTORY_FLOOR}) — otherwise the arm cannot tell a "
            "working custody check from a floor that was never reached")
        assert all(r["provenance"] == "real_mined"
                   and r["source_class"] == "consequence_ledger"
                   for r in laundered_rows), "fixture invariant"
        # (a) the seal battery catches the rewrite by name...
        with pytest.raises(AssertionError, match=_tag("[LC-CUSTODY]")):
            FIX.assert_custody_intact(rewritten)
        # (b) ...and the counting predicate refuses to count them, so the
        #     rewrite buys the laundering NOTHING.
        assert FIX.count_toward_minimums(rewritten) == honest_before

    def test_mutant_counter_ignoring_custody_REDS(self):
        # the counter-side escape: a counter that reads the provenance FIELD
        # and never verifies the seal counts every rewritten row.
        accepted, _ = FIX.ingest_rows(real_rows() + synthetic_rows())
        rewritten = FIX.mutant_rewrite_after_ingest(accepted)
        laundered = FIX.mutant_count_ignoring_custody(rewritten)
        assert laundered["prompt/low"]["counted"] > \
            FIX.count_toward_minimums(rewritten)["prompt/low"]["counted"], (
            "fixture invariant: the custody-blind counter must actually inflate")
        with pytest.raises(AssertionError, match=_tag("[LC-LAUNDER]")):
            FIX.assert_count_honest(laundered, rewritten)

    def test_rewritten_rows_cannot_open_the_league(self):
        # the joint that matters: rewriting synthetic rows to look real must
        # not reach the §6.2 floor through league_may_open.
        accepted, _ = FIX.ingest_rows(synthetic_rows(25))
        rewritten = FIX.mutant_rewrite_after_ingest(accepted)
        record = FIX.good_arming_record()
        record["open_conditions"] = {c: True for c in FIX.OPEN_CONDITIONS}
        record["holdout_freeze"] = "landed"
        assert FIX.league_may_open(record, rewritten) is False, (
            "[LC-SYNTH-NEVER-OPENS] a post-ingest provenance rewrite must not "
            "open the league — custody is bound at ingest (§6.2)")

    def test_laundered_actuals_from_a_rewritten_corpus_REDS(self):
        # the record-level composition: actuals computed by the custody-blind
        # counter over a rewritten corpus disagree with the §6.2 predicate.
        accepted, _ = FIX.ingest_rows(real_rows() + synthetic_rows())
        rewritten = FIX.mutant_rewrite_after_ingest(accepted)
        record = FIX.good_arming_record(
            actuals=FIX.mutant_count_ignoring_custody(rewritten))
        violations = FIX.validate_arming_record(record, rows=rewritten)
        assert any("[LC-LAUNDER]" in v for v in violations)

    def test_mutant_trusting_ingester_launders_REDS(self):
        # the custody mutant: an ingester TRUSTING the row-supplied stamp
        # lets the generator row masquerade as real_live — the honest-count
        # battery must catch the laundered corpus it produces.
        accepted, refused = FIX.mutant_ingest_trusting(refusable_rows()[:1])
        assert refused == [] and accepted[0]["provenance"] == "real_live", \
            "fixture invariant: the mutant must actually launder"
        counts = FIX.count_toward_minimums(accepted)
        # count_toward_minimums still refuses it (source_class is not a named
        # real source — belt), so the laundering surfaces one level up: the
        # mutant COUNTER over the mutant-ingested corpus inflates. Braces:
        laundered = FIX.mutant_count_all(accepted)
        assert counts["prompt/low"]["counted"] == 0
        with pytest.raises(AssertionError, match=_tag("[LC-LAUNDER]")):
            FIX.assert_count_honest(laundered, accepted)


# ===========================================================================
# §8.1 — synthetic NEVER opens the league; closed rows claim no fitness
# ===========================================================================
class TestSyntheticNeverOpens:
    def test_synthetic_only_corpus_cannot_open(self):
        # 25 synthetic rows >= every floor by raw volume — and open must
        # still be False: the counting predicate sees ZERO real rows.
        accepted, _ = FIX.ingest_rows(synthetic_rows(25))
        record = FIX.good_arming_record()
        record["open_conditions"] = {c: True for c in FIX.OPEN_CONDITIONS}
        record["holdout_freeze"] = "landed"
        assert FIX.league_may_open(record, accepted) is False, (
            "[LC-SYNTH-NEVER-OPENS] synthetic corpora prove plumbing and "
            "mutants; they can NEVER open the league (§8.1/§6.2)")

    def test_mutant_open_on_total_rows_REDS(self):
        # the §12-class escape: an opener keyed on TOTAL row count.
        accepted, _ = FIX.ingest_rows(synthetic_rows(25))
        record = FIX.good_arming_record()
        record["open_conditions"] = {c: True for c in FIX.OPEN_CONDITIONS}
        record["holdout_freeze"] = "landed"
        assert FIX.mutant_open_on_total_rows(record, accepted) is True, \
            "fixture invariant: the mutant must actually open on volume"
        assert FIX.mutant_open_on_total_rows(record, accepted) != \
            FIX.league_may_open(record, accepted), (
            "[LC-SYNTH-NEVER-OPENS] the volume-keyed opener diverges from "
            "the §6.2 counting predicate — the mutant is the named escape")

    def test_real_floor_met_but_conditions_unmet_stays_closed(self):
        # even a real corpus at floor cannot open while a §6.3 condition is
        # unmet (holdout freeze pending — the Stage-B checklist law).
        rows = [{"source_class": "consequence_ledger", "stratum": "prompt/low",
                 "payload_ref": f"sha-{i}"} for i in range(10)]
        accepted, _ = FIX.ingest_rows(rows)
        record = FIX.good_arming_record()          # conditions all false
        assert FIX.league_may_open(record, accepted) is False

    def test_closed_league_rows_carry_fitness_claim_none(self):
        for i in range(3):
            row = FIX.make_league_row(f"cand-{i}", scored=0.4 + i / 10,
                                      ranked=i)
            FIX.assert_league_row_closed_shape(row)

    def test_mutant_live_fitness_row_REDS(self):
        row = FIX.mutant_league_row_fitness("cand-x", scored=0.9, ranked=1)
        assert row["fitness_claim"] == "live_fitness", "fixture invariant"
        with pytest.raises(AssertionError, match=_tag("[LC-FITNESS]")):
            FIX.assert_league_row_closed_shape(row)

    def test_closed_league_rows_are_capped_at_the_states_p5_rung(self):
        # the closure property the row-shape battery now carries: a closed
        # league row's certainty sits at or below P5, bound to the states.py
        # ladder (read from bytes) — not to a word scan.
        row = FIX.make_league_row("cand-cap", scored=0.6, ranked=1)
        FIX.assert_league_row_closed_shape(row)
        above = FIX.mutant_league_row_above_cap("cand-cap", scored=0.6, ranked=1)
        assert FIX.vocab_violations(above) == [], (
            "fixture invariant: the vocabulary scan is blind to the P3 token")
        with pytest.raises(AssertionError, match=_tag("[P5-CAP]")):
            FIX.assert_league_row_closed_shape(above)

    def test_row_missing_the_schema_required_field_REDS(self):
        row = FIX.make_league_row("cand-y", scored=0.5, ranked=2)
        del row["fitness_claim"]
        with pytest.raises(AssertionError, match=_tag("[LC-FITNESS]")):
            FIX.assert_league_row_closed_shape(row)


# ===========================================================================
# §6.3 — the closure validator over the arming-record SHAPE (fixture tier)
# ===========================================================================
class TestArmingRecordClosureFixture:
    def test_good_record_validates_clean(self):
        accepted, _ = FIX.ingest_rows(real_rows() + synthetic_rows())
        record = FIX.good_arming_record(
            actuals=FIX.count_toward_minimums(accepted))
        assert FIX.validate_arming_record(record, rows=accepted) == []

    def test_record_roundtrips_through_yaml(self, tmp_path):
        # the record is a tracked YAML artifact at exit — the validator must
        # hold over PARSED BYTES, not just in-memory dicts.
        accepted, _ = FIX.ingest_rows(real_rows())
        record = FIX.good_arming_record(
            actuals=FIX.count_toward_minimums(accepted))
        path = tmp_path / "arming-record.yml"
        path.write_text(yaml.safe_dump(record, sort_keys=True),
                        encoding="utf-8")
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert FIX.validate_arming_record(parsed, rows=accepted) == []

    def test_open_flip_while_conditions_unmet_REDS(self):
        record = FIX.good_arming_record()
        record["league_open"] = True                # the premature flip
        violations = FIX.validate_arming_record(record)
        assert any("[LC-OPEN]" in v for v in violations), (
            "league_open: true with unmet conditions must be a violation — "
            "opening is a post-phase amendment event (§6.3)")

    def test_minimums_drift_REDS(self):
        record = FIX.good_arming_record()
        record["minimums"] = {**FIX.EXPECTED_MINIMUMS,
                              "real_trajectory_floor": 9}   # weakened floor
        violations = FIX.validate_arming_record(record)
        assert any("[LC-MINIMUMS]" in v for v in violations)

    def test_missing_holdout_freeze_line_REDS(self):
        record = FIX.good_arming_record()
        del record["holdout_freeze"]
        violations = FIX.validate_arming_record(record)
        assert any("[LC-FREEZE]" in v for v in violations)

    def test_laundered_actuals_block_REDS(self):
        # a record whose actuals were computed by the laundering counter
        # disagrees with the §6.2 predicate recomputation over the corpus.
        accepted, _ = FIX.ingest_rows(real_rows() + synthetic_rows())
        record = FIX.good_arming_record(actuals=FIX.mutant_count_all(accepted))
        violations = FIX.validate_arming_record(record, rows=accepted)
        assert any("[LC-LAUNDER]" in v for v in violations)


# ===========================================================================
# §9.1 — the fitness VECTOR law at the league joint
# ===========================================================================
class TestFitnessVectorLaw:
    def _packs(self):
        # 0.75 vs 0.80, zero regressions on both — MEASURED from the real
        # replay maps + the real predicate, so every machine dim carries a
        # machine derivation (X6) and the floors are read from evidence.
        incumbent = FIX.candidate_vector(
            candidate_results=BASELINE,
            gate_result=rg.GateResult(outcome=rg.OUTCOME_FAIL),
            judge_score=0.55, table_order=0.50)
        contender = FIX.candidate_vector(
            candidate_results=IMPROVING,
            gate_result=rg.evaluate_gate(IDS, BASELINE, IMPROVING),
            judge_score=0.40, table_order=0.10)
        return incumbent, contender

    def test_schema_separates_vector_from_table_order(self):
        incumbent, contender = self._packs()
        for pack in (incumbent, contender):
            assert set(pack) == {"vector", "table_order"}
            assert isinstance(pack["table_order"], float)

    def test_table_order_never_reaches_the_admission_joint(self):
        # the structural proof: two packs with IDENTICAL vectors and wildly
        # different table_order must get the SAME eligibility answer.
        incumbent, contender = self._packs()
        high = {**contender, "table_order": 0.99}
        low = {**contender, "table_order": 0.01}
        assert FIX.admission_eligible(high, incumbent) == \
            FIX.admission_eligible(low, incumbent)

    def test_a_composite_may_order_the_table(self):
        # presentation is sanctioned: sorting BY table_order for display is
        # legal — the law is about joints, not tables (§9.1).
        incumbent, contender = self._packs()
        table = sorted([("incumbent", incumbent), ("contender", contender)],
                       key=lambda kv: -kv[1]["table_order"])
        assert [n for n, _ in table] == ["incumbent", "contender"]
        # ...and the ordering scalar changed NO eligibility outcome:
        ok, _ = FIX.admission_eligible(contender, incumbent)
        assert ok is True

    def test_table_order_law_holds_as_a_reusable_battery(self):
        # N4: the §9.1 structural law promoted out of an inline assert into a
        # lib battery, so integrator surgery can re-run it against the REAL
        # league/scorer joint instead of re-deriving it by hand.
        incumbent, contender = self._packs()
        FIX.assert_table_order_never_reaches_the_joint(contender, incumbent)

    def test_mutant_predicate_keying_on_table_order_REDS(self):
        # §9.1's NAMED mutant: a predicate keying on table_order — the same
        # pack answers differently at 0.99 and 0.01, and the battery catches
        # it (both directions: reference above passes, mutant here REDs).
        incumbent, contender = self._packs()
        high = {**contender, "table_order": 0.99}
        low = {**contender, "table_order": 0.01}
        assert FIX.mutant_table_order_eligibility(high, incumbent) != \
            FIX.mutant_table_order_eligibility(low, incumbent), \
            "fixture invariant: the mutant must actually key on the scalar"
        with pytest.raises(AssertionError, match=_tag("[LC-TABLE-ORDER]")):
            FIX.assert_table_order_never_reaches_the_joint(
                contender, incumbent,
                predicate=FIX.mutant_table_order_eligibility)

    def test_unknown_never_satisfies_a_floor_at_the_league_joint(self):
        incumbent, _ = self._packs()
        # quarantined BUT honestly provenanced: the values came from the
        # sim-8 triple-run outputs, so the refusal is the UNKNOWN law, never
        # a missing-derivation artefact.
        triple = ["0.117", "0.640", "0.902"]
        quarantined = FIX.make_vector({
            "frozen_pass_rate": (FIX.UNKNOWN, FIX.MACHINE_KIND),
            "frozen_regressions": (FIX.UNKNOWN, FIX.MACHINE_KIND),
            "judge_score": (0.99, FIX.JUDGE_KIND),
        }, table_order=0.99, evidence={
            "frozen_pass_rate": triple, "frozen_regressions": triple,
            "judge_score": FIX.JudgeEvidence(0.99)})
        ok, reasons = FIX.admission_eligible(quarantined, incumbent)
        assert ok is False and any("[FLOOR-UNKNOWN]" in r for r in reasons)

    def test_judge_dimension_never_satisfies_a_floor_here_either(self):
        # X6 at the league joint: machine-flat + judge-max stays ineligible
        # (the sim-4 law re-asserted where the league consumes vectors). The
        # machine dims are MEASURED (baseline replay + real gate result), so
        # the refusal is the improvement floor — not the derivation gate.
        incumbent, _ = self._packs()
        judge_only = FIX.candidate_vector(
            candidate_results=BASELINE,
            gate_result=rg.GateResult(outcome=rg.OUTCOME_FAIL),
            judge_score=0.99, table_order=0.95)
        ok, reasons = FIX.admission_eligible(judge_only, incumbent)
        assert ok is False
        assert any("[FLOOR-IMPROVEMENT]" in r for r in reasons), (
            "the judge-max pack must be refused for the unmet MACHINE floor")
        assert not any("[FLOOR-DERIVATION]" in r for r in reasons), (
            "fixture invariant: this arm tests X6 at the floor, not custody")


# ===========================================================================
# REAL-SURFACE arms — vacuity-guarded (league.py + the §6.3 arming record)
# ===========================================================================
LEAGUE_PY = _REPO / "framework/evolution/league.py"
ARMING_RECORD = _REPO / FIX.ARMING_RECORD_REL


class TestLeagueSurfaceVacuityGuarded:
    def test_league_absence_companion(self):
        # COMPANION absence assertion: REDs the instant league.py lands so
        # the sibling skip cannot silently persist (§13).
        assert not LEAGUE_PY.exists(), (
            "framework/evolution/league.py LANDED — retire the paired skip "
            "(see its docstring): run the closure/row-shape/counting "
            "batteries over the real league outputs (integrator corpus "
            "surgery per §13).")

    def test_league_armed_import_probe(self, tmp_path):
        rc, err = FIX.import_probe(FIX.LEAGUE_MODULE, _REPO, tmp_path)
        assert rc != 0 and "No module named" in err

    def test_league_real_arm_guarded(self):
        """RETIREMENT CONDITION: retire this skip when
        framework/evolution/league.py lands — replacement body = the SAME
        batteries proven live above, over real league outputs:
        assert_league_row_closed_shape on every emitted row,
        assert_count_honest over its archive-bound corpus, league_may_open
        False on the shipped record, and the §9.1 vector-law asserts over
        its scorer packs (§13; contradictions route to the integrator)."""
        if LEAGUE_PY.exists():
            pytest.fail("league.py landed but the guard was not retired — "
                        "the absence companion should already be RED")
        pytest.skip("league.py not yet built — vacuity guard armed by the "
                    "ModuleNotFound probe; retire per docstring when it lands")


class TestArmingRecordVacuityGuarded:
    def test_record_absence_companion(self):
        # COMPANION absence assertion: the §6.3 record ships AT EXIT; the
        # moment it lands this REDs and the guard below goes live.
        assert not ARMING_RECORD.exists(), (
            f"{FIX.ARMING_RECORD_REL} LANDED — retire the paired skip: the "
            "guard body below already validates the real bytes "
            "(validate_arming_record + league_open false + the holdout_freeze "
            "posture); delete this companion and un-skip it.")

    def test_record_real_arm_guarded(self):
        """RETIREMENT CONDITION: retire this skip when the §6.3 arming
        record lands at exit (docs/plans/cog5-league-arming-record-2026-07-24
        .yml) — the body below then runs against the
        REAL bytes: minimums verbatim, league_open false, the open-conditions
        checklist, holdout_freeze pending-captain-window until §7.5 Stage B
        LANDS (then 'landed'). The validator is proven live on fixture
        records above (§13)."""
        if not ARMING_RECORD.exists():
            pytest.skip("arming record not yet shipped (ships at exit) — "
                        "vacuity guard; retire when "
                        f"{FIX.ARMING_RECORD_REL} lands")
        parsed = yaml.safe_load(ARMING_RECORD.read_text(encoding="utf-8"))
        violations = FIX.validate_arming_record(parsed)
        assert violations == [], f"real arming record violates §6.3: {violations}"
        assert parsed["league_open"] is False, (
            "the league ships CLOSED at exit — opening is a post-phase "
            "amendment event (§6.3)")
        assert parsed["holdout_freeze"] in (FIX.HOLDOUT_FREEZE_INTERIM,
                                            "landed")
