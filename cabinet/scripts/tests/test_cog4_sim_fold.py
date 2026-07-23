"""COG-4 W2 T1 — the SCHEDULER-FOLD corpus (contract
cognitive-core-phase-4-contract-2026-07-23 §12 sims 1, 2, 4, 7, 8, 13 + the N1
determinism battery + the N2 starvation exit assertions + the §7.1 A-M6 purity
mutants). Tests-first: `framework/scheduler/` does NOT exist on this tree.

TWO TIERS (the W1-u2 mergeability idiom — this suite merges GREEN on the bare
tree):

  * FIXTURE-MACHINERY tests run LIVE NOW: every sim battery executes against
    the REFERENCE FOLD SIMULATOR (lib_cog4_corpus.reference_fold — the §7.2
    semantics over authored wake-snapshot data files under
    fixtures/cog4/fold/), and every §12-named negative-control mutant is
    proven BITING on those fixtures in this run — dict-order tie-break (sim
    1), idle-spin (sim 2), cost-ignoring (sim 4), starvation-prone (sim 7),
    LWW/auto-resolve (sim 8), self-weight-update (sim 13), plus the A-M6
    env-reading and datetime.now purity mutants. A gate without a biting
    mutant is decoration (§12).
  * REAL-SURFACE arms are VACUITY-GUARDED: each carries (a) a COMPANION
    absence assertion that goes RED the instant `framework/scheduler/` lands
    (so the skip cannot silently persist — §13 law), (b) an ARMED proof that
    the real import probe currently fails ModuleNotFound, and (c) the skip
    with its RETIREMENT CONDITION. Retirement is mechanical: the arm bodies
    are the SAME lib batteries the live tier already exercises —
    `lib_cog4_corpus.run_real_arm(<arm>, tmp_path, repo=_REPO)` — so the
    retirement path is proven TODAY on the reference runner.

RETIREMENT CONDITION (all guarded arms): retire the skips when
`framework/scheduler/` (specifically `framework.scheduler.fold.build_schedule`
per §7.2) lands — replace each guard body with the `run_real_arm` call named
in its comment. The corpus is the executable spec: the implementation must
satisfy these batteries UNMODIFIED (§13 — builders never edit tests;
contradictions route to the integrator).

N1 (§1): identical combined artifact hash across 3 subprocess rebuilds under 3
distinct PYTHONHASHSEED values from the SAME wake-snapshot (the C-F3 triple);
delete→rebuild reproduces the hash; covers schedule.jsonl +
schedule-manifest.json + the snapshot record. N2 (§1): the seeded high-urgency
organ is chosen within its DECLARED starvation bound — organ-declared or the
scheduler_policy default, both SNAPSHOT INPUTS (SF2), never planner-invented.

S0: python3.12, no DB, no network; children inherit the conftest env fence.
Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (Fable 5 — corpus authorship is
judgment-tier work).
"""
from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):        # tests/ is a package: put it on the path
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog4_corpus as C  # noqa: E402

FIXTURES = ("burst", "quiet", "cost-spike", "starvation", "contradiction",
            "self-prioritization")


def _tag(marker: str) -> str:
    return re.escape(marker)


# ===========================================================================
# fixture self-consistency (LIVE) — the corpus seeds are validated data files
# ===========================================================================
class TestFixtureCorpus:
    @pytest.mark.parametrize("name", FIXTURES)
    def test_fixture_parses_and_validates(self, name):
        snap = C.load_fixture(name)     # validate_snapshot inside
        # §7.1 field inventory: the seven wake-input hashes + the four
        # declared version params + the SF2 families are all present.
        assert set(snap["wake_input_hashes"]) == set(C.WAKE_INPUT_HASH_KEYS)
        for fam in ("organ_health", "failure_history",
                    "capability_availability"):
            assert isinstance(snap[fam], dict)

    @pytest.mark.parametrize("name", FIXTURES)
    def test_operation_ids_are_namespaced(self, name):
        # §4.2: domain operations are namespaced `<domain>/<op>` — the `/`
        # separator makes the flat central vocabulary structurally
        # un-collidable.
        for organ in C.load_fixture(name)["organs"]:
            for op in organ["operations"]:
                assert "/" in op["operation"]
                assert C.OP_ID_RE.fullmatch(op["operation"])

    def test_sf2_tamper_is_caught(self):
        # NEGATIVE CONTROL for the self-consistency law: mutate an SF2 family
        # WITHOUT refreshing its declared hash → validation REDs. Fixture
        # drift can never be silent.
        snap = C.load_fixture("burst")
        snap["organ_health"]["harvest-census"] = "fail"
        with pytest.raises(AssertionError, match="organ_health_hash"):
            C.validate_snapshot(snap)

    def test_registry_hash_is_order_independent(self):
        # §4.4 sorted-manifests law — the sim-8 symmetry twin depends on it.
        snap = C.load_fixture("contradiction")
        twin = C.make_swapped_registry(snap)
        assert twin["wake_input_hashes"] == snap["wake_input_hashes"]
        assert twin["organs"] != snap["organs"]      # order genuinely differs

    def test_cutoff_validator_hard_errors(self):
        # §7.1 replicated validator: non-canonical cutoff is a hard error.
        snap = C.load_fixture("burst")
        snap["cutoff"] = "2026-07-23T06:00:00+02:00"
        with pytest.raises(AssertionError, match="non-canonical cutoff"):
            C.validate_snapshot(snap)


# ===========================================================================
# the sim batteries run LIVE on the reference fold — these bodies are
# EXACTLY the real arms (run_real_arm), so the retirement path is proven now
# ===========================================================================
class TestFoldBatteriesLiveOnReference:
    @pytest.mark.parametrize("arm", sorted(C.REAL_ARMS))
    def test_arm_battery_green_on_reference(self, arm, tmp_path):
        C.run_real_arm(arm, tmp_path, runner=C.corpus_runner("reference"))


# ===========================================================================
# sim 1 — burst load: the §12 mutant (dict-order tie-break) must FAIL N1
# ===========================================================================
class TestSim1BurstMutant:
    def test_dict_order_mutant_breaks_the_triple(self, tmp_path):
        # the named escape: a fold whose selection/emission order rides the
        # salted str hash diverges across the PYTHONHASHSEED triple.
        with pytest.raises(AssertionError, match=_tag("[N1-TRIPLE]")):
            C.assert_n1_triple(C.corpus_runner("dict_order"),
                               C.fixture_path("burst"), tmp_path)

    def test_reference_rows_are_canonically_ordered(self, tmp_path):
        # §7.2: emitted decision rows ride the canonical total order.
        cache = tmp_path / "cache"
        C.corpus_runner("reference")(C.fixture_path("burst"), cache)
        keys = [r["tie_break_key"] for r in C.read_rows(cache)]
        assert keys == sorted(keys)


# ===========================================================================
# sim 2 — quiet period: the idle-spin mutant must FAIL (invented work)
# ===========================================================================
class TestSim2QuietMutant:
    def test_idle_spin_mutant_invents_work(self, tmp_path):
        with pytest.raises(AssertionError, match=_tag("[SIM2-EMPTY]")):
            C.assert_sim2_quiet(C.corpus_runner("idle_spin"),
                                C.fixture_path("quiet"), tmp_path)


# ===========================================================================
# sim 4 — cost spike: the cost-ignoring mutant must FAIL (ceiling breached)
# ===========================================================================
class TestSim4CostSpikeMutant:
    def test_cost_ignoring_mutant_selects_above_ceiling(self, tmp_path):
        with pytest.raises(AssertionError, match=_tag("[SIM4-CEILING]")):
            C.assert_sim4_cost_spike(C.corpus_runner("cost_ignore"),
                                     C.fixture_path("cost-spike"), tmp_path)


# ===========================================================================
# sim 7 + N2 — starvation: bounds are SNAPSHOT INPUTS; the bound-ignoring
# mutant must FAIL
# ===========================================================================
class TestSim7Starvation:
    def test_reference_promotion_tracks_the_declared_bound(self, tmp_path):
        # The bound is a snapshot INPUT, never planner-invented (N2): under
        # identical adversarial load the reference fold's choice wake moves
        # exactly with the declared value — organ-declared 3, organ-declared
        # 5, and the scheduler_policy DEFAULT 4 when the organ declares none.
        base = C.load_fixture("starvation")
        chosen = {}
        for label, snap, bound in C.starvation_variants(base, "ledger-audit"):
            wake, _ = C.run_starvation_series(
                C.corpus_runner("reference"), snap, "ledger-audit",
                tmp_path / label, k_max=bound + 3)
            chosen[label] = (wake, bound)
        for label, (wake, bound) in chosen.items():
            assert wake == bound, (label, chosen)
        assert len({w for w, _ in chosen.values()}) == 3, chosen

    def test_starvation_prone_mutant_starves_past_bound(self, tmp_path):
        base = C.load_fixture("starvation")
        with pytest.raises(AssertionError, match=_tag("[SIM7-BOUND]")):
            C.assert_sim7_starvation(C.corpus_runner("starvation_prone"),
                                     base, "ledger-audit", tmp_path)


# ===========================================================================
# sim 8 — contradictory organs: the LWW/auto-resolve mutant must FAIL
# ===========================================================================
class TestSim8ContradictionMutant:
    def test_lww_mutant_drops_a_side(self, tmp_path):
        with pytest.raises(AssertionError, match=_tag("[SIM8-BOTH]")):
            C.assert_sim8_contradiction(C.corpus_runner("lww"),
                                        C.load_fixture("contradiction"),
                                        tmp_path)


# ===========================================================================
# sim 13 — self-prioritization: the self-weight-update mutant must FAIL all
# three named escapes, each proven on its own narrow check
# ===========================================================================
class TestSim13SelfPrioritizationMutant:
    def _build_with_mutant(self, tmp_path):
        snap = C.load_fixture("self-prioritization")
        snap_path, cache, pre = C.prepare_sim13_sandbox(snap, tmp_path)
        C.corpus_runner("self_weight")(snap_path, cache, cwd=tmp_path)
        return snap, cache, pre

    def test_mutant_writes_outside_its_cache(self, tmp_path):
        _, cache, pre = self._build_with_mutant(tmp_path)
        with pytest.raises(AssertionError, match=_tag("[SIM13-CACHE-ONLY]")):
            C.check_sim13_cache_only(tmp_path, cache, pre)

    def test_mutant_bumps_the_policy_version(self, tmp_path):
        snap, cache, _ = self._build_with_mutant(tmp_path)
        with pytest.raises(AssertionError, match=_tag("[SIM13-POLICY-ECHO]")):
            C.check_sim13_policy_echo(snap, cache)

    def test_mutant_gives_self_targeting_ops_special_weight(self, tmp_path):
        snap, cache, _ = self._build_with_mutant(tmp_path)
        with pytest.raises(AssertionError,
                           match=_tag("[SIM13-NO-SELF-WEIGHT]")):
            C.check_sim13_no_self_weight(snap, cache)


# ===========================================================================
# §7.1 A-M6 purity — env-reading and datetime.now folds must FAIL
# ===========================================================================
class TestFoldPurityMutants:
    def test_env_reading_fold_is_red(self, tmp_path):
        with pytest.raises(AssertionError, match=_tag("[PURITY-ENV]")):
            C.assert_env_invariance(C.corpus_runner("env_reading"),
                                    C.fixture_path("burst"), tmp_path)

    def test_datetime_now_fold_is_red(self, tmp_path):
        with pytest.raises(AssertionError, match=_tag("[PURITY-CLOCK]")):
            C.assert_clock_invariance(C.corpus_runner("datetime_now"),
                                      C.fixture_path("burst"), tmp_path)


# ===========================================================================
# the N1 instrument itself — artifact coverage is real, not decorative
# ===========================================================================
class TestN1Instrument:
    def test_combined_hash_requires_all_three_artifacts(self, tmp_path):
        # N1 "covers schedule.jsonl + schedule-manifest.json + the snapshot
        # record": removing ANY of the three artifacts fails the instrument.
        cache = tmp_path / "cache"
        C.corpus_runner("reference")(C.fixture_path("burst"), cache)
        baseline = C.combined_artifact_hash(cache)
        for name in C.ARTIFACT_FILES:
            data = (cache / name).read_bytes()
            (cache / name).unlink()
            with pytest.raises(AssertionError, match=_tag("[N1-ARTIFACTS]")):
                C.combined_artifact_hash(cache)
            (cache / name).write_bytes(data)
        assert C.combined_artifact_hash(cache) == baseline

    def test_combined_hash_sees_every_artifact_byte(self, tmp_path):
        # tampering any ONE artifact changes the combined hash — each of the
        # three files is genuinely covered.
        for victim in C.ARTIFACT_FILES:
            cache = tmp_path / f"tamper-{victim}"
            C.corpus_runner("reference")(C.fixture_path("burst"), cache)
            before = C.combined_artifact_hash(cache)
            path = cache / victim
            path.write_bytes(path.read_bytes() + b" ")
            assert C.combined_artifact_hash(cache) != before, victim


# ===========================================================================
# the vacuity-guard machinery is itself proven (LIVE, scratch tree)
# ===========================================================================
class TestArmedProbeMachinery:
    def test_probe_flips_when_the_surface_lands(self, tmp_path):
        # the guarded arms' ARMED proof relies on the import probe failing on
        # the bare tree and succeeding once framework/scheduler/fold.py
        # exists. Prove BOTH directions on a scratch repo root now — the
        # probe is a discriminator, not a constant.
        rc_bare, err_bare = C.real_surface_import_probe(str(tmp_path))
        assert rc_bare != 0 and "No module named" in err_bare
        pkg = tmp_path / "framework" / "scheduler"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("", "utf-8")
        (pkg / "fold.py").write_text(
            "def build_schedule(snapshot_path, cache_dir):\n"
            "    raise NotImplementedError\n", "utf-8")
        C.real_surface_import_probe.cache_clear()
        rc_landed, err_landed = C.real_surface_import_probe(str(tmp_path))
        C.real_surface_import_probe.cache_clear()
        assert rc_landed == 0, err_landed


# ===========================================================================
# REAL-SURFACE ARMS — vacuity-guarded until framework/scheduler lands (§13)
# ===========================================================================
class TestRealFoldSurfaceArms:
    @pytest.mark.parametrize("arm", sorted(C.REAL_ARMS))
    def test_real_arm_is_armed_and_surface_absent(self, arm, tmp_path):
        # VACUITY GUARD — RETIREMENT CONDITION: retire this skip when
        # framework/scheduler/ lands (§7.2 build_schedule). Activation is one
        # line — the SAME battery the live tier already proves:
        #     C.run_real_arm("<arm>", tmp_path, repo=_REPO)
        # The COMPANION assertion below fails the instant the planner tree
        # lands, so this skip cannot silently persist (§13).
        tree = _REPO / C.SCHEDULER_TREE_REL
        assert not tree.exists(), (
            f"{C.SCHEDULER_TREE_REL}/ has LANDED — retire this vacuity skip: "
            f"run C.run_real_arm({arm!r}, tmp_path, repo=_REPO) per the "
            "docstring RETIREMENT CONDITION")
        # ARMED proof: the real import probe fails ModuleNotFound TODAY (the
        # probe's two-way discrimination is proven in TestArmedProbeMachinery).
        rc, stderr = C.real_surface_import_probe(str(_REPO))
        assert rc != 0 and "No module named" in stderr, (rc, stderr)
        pytest.skip(
            f"VACUITY: {C.SCHEDULER_TREE_REL}/ absent this phase — the "
            f"{arm} battery runs live on the reference fold "
            "(TestFoldBatteriesLiveOnReference) and arms for the real "
            "surface; retire when framework/scheduler lands.")


# ===========================================================================
# starvation harness honesty — the wait state the series carries is DECLARED
# ===========================================================================
class TestStarvationHarness:
    def test_series_redeclares_wait_state_per_wake(self, tmp_path):
        # the multi-wake harness re-declares wakes_waiting into
        # failure_history and REFRESHES its family hash each wake — the wait
        # state rides the snapshot (SF2), never a planner memory.
        base = C.load_fixture("starvation")
        snap = copy.deepcopy(base)
        snap["failure_history"]["ledger-audit"]["wakes_waiting"] = 2
        with pytest.raises(AssertionError, match="failure_history_hash"):
            C.validate_snapshot(snap)       # stale hash caught...
        C.refresh_sf2_hashes(snap)
        C.validate_snapshot(snap)           # ...refreshed hash honest
        assert snap["wake_input_hashes"]["failure_history_hash"] != \
            base["wake_input_hashes"]["failure_history_hash"]
