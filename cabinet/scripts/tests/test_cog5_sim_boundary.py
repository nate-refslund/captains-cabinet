"""COG-5 §12 SIM 6 — holdout leakage attempt (+ the X7 exit arm + the §7.4
Stage-A honesty assert + the §6.2 synthetic-never-counts law).

Contract: docs/plans/cognitive-core-phase-5-contract-2026-07-24.md §12 row 6:
  seeds   — league/generator code paths attempting case/fingerprint/per-case
            reads; a receipt carrying per-case data
  asserts — every attempt REFUSES (boundary + oracle + validate_holdout_receipt);
            the aggregate-only receipt validates
  mutants — per-case field tolerated in a receipt; an allowlisted league
            import of holdout_gen
plus §1 X7 (benchmark cases carry cutoff/leakage metadata; a metadata-less
case REFUSES ingestion — mutant) and the task-pinned Stage-A honesty assert
(§7.4: the in-phase interim is honestly NOT Ring-0 — compensating controls
present, no Ring-0 claim).

WHAT RUNS LIVE NOW (fixture machinery, the §12 sanction):
  - the aggregate-only receipt VALIDATES via the committed
    framework/evolution/contracts.py `validate_holdout_receipt` (:310);
  - every per-case-carrying receipt REFUSES structurally
    (additionalProperties:false — the oracle-side refusal layer);
  - the TOLERANT-VALIDATOR mutant misses exactly that leak (the escape it
    names) while the real validator bites;
  - league/generator scratch-tree imports of the holdout module RED under
    the SHIPPED cog2-import-gate engine + the W1 ROW 8 manifest row (the
    boundary refusal layer);
  - the ALLOWLISTED-LEAGUE-IMPORT mutant: a mutated manifest copy that
    allowlists the league fails to bite the very tree the real manifest
    REDs — proven side by side;
  - the X7 metadata gate + its metadata-less mutant on fixture cases;
  - the §6.2 provenance custody/counting law over this family's synthetic
    fixtures (synthetic NEVER counts toward a league minimum; laundering
    REDs).

VACUITY ARMS (the mergeability pattern — each with its RETIREMENT CONDITION
here and a COMPANION absence assertion that REDs the moment the path lands):
  - BEHAVIORAL oracle-vs-league runtime arm — retire when
    framework/evolution/holdout_gen.py lands (W5): replace the skip with a
    live run proving league/generator-side case/fingerprint/per-case READS
    refuse at runtime, not only at import granularity.
  - SOLE-READER CLI arm — retire when cabinet/scripts/cog5-holdout-oracle.py
    lands (W5): assert the CLI is the one sanctioned reader and emits ONLY
    aggregate receipts that validate.
  - X7 INGESTION arm — retire when framework/evolution/bench_factory.py
    lands (W5): feed the real miner a metadata-less case and assert it
    REFUSES ingestion with the X7 gate.

S0: python3.12, no DB, no network, file-seeded, deterministic. Provenance:
authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-5 W2 corpus, unit T3).
"""
from __future__ import annotations

import importlib.util as _ilu
import sys
from pathlib import Path

import pytest
import yaml

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog5_boundary_fixtures as B  # noqa: E402

# the shipped boundary engine (hyphenated filename -> importlib; the
# test_cog5_boundary_rows.py idiom)
_GATE_PATH = _HERE.parents[0] / "cog2-import-gate.py"
_spec = _ilu.spec_from_file_location("cog2_import_gate_cog5_sim6", _GATE_PATH)
gate = _ilu.module_from_spec(_spec)
sys.modules["cog2_import_gate_cog5_sim6"] = gate
_spec.loader.exec_module(gate)

CONFIG = gate.load_config()

# module tokens are safe as bare string literals (only a real import or an
# import_module call trips the sweep — the W1 doctrine)
HOLDOUT_TOKEN = "framework.evolution.holdout_gen"
HOLDOUT_GEN_REL = "framework/evolution/holdout_gen.py"
BENCH_FACTORY_REL = "framework/evolution/bench_factory.py"
ORACLE_CLI_REL = "cabinet/scripts/cog5-holdout-oracle.py"
# ROW 8's ONE sanctioned glob: the holdout content-pin sibling tests
HOLDOUT_PIN_TEST_GLOB = "cabinet/scripts/tests/test_cog5_holdout_*.py"
_IMMUTABLE_CORE = _REPO / "framework/policies/immutable-core.yml"
_EGG_MANIFEST = _REPO / "cabinet/scripts/egg-export-manifest.txt"


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _paths_for(violations, rule: str) -> set[str]:
    return {v.rsplit(":", 1)[0] for v in violations if v.rsplit(":", 1)[1] == rule}


# ===========================================================================
# sim 6 leg 1 — the ORACLE refusal layer: validate_holdout_receipt
# ===========================================================================
class TestReceiptRefusalLayer:
    def test_aggregate_only_receipt_validates(self):
        """The positive control (sim-6 assert): a fully aggregate receipt
        with a trusted oracle attestation yields ZERO issues."""
        receipt, context = B.lib_cog5_boundary_valid_receipt()
        from framework.evolution.contracts import validate_holdout_receipt
        assert validate_holdout_receipt(receipt, context) == ()

    @pytest.mark.parametrize("leak_field", B.lib_cog5_boundary_per_case_leak_fields())
    def test_receipt_carrying_per_case_data_refuses(self, leak_field):
        """sim-6 seed 2: a receipt smuggling per-case data REFUSES — the
        schema is additionalProperties:false, so EVERY unknown per-case
        payload is a structural refusal (cases, fingerprints, per-case
        scores/results, raw outputs)."""
        from framework.evolution.contracts import (
            holdout_receipt_structural_issues,
            validate_holdout_receipt,
        )
        receipt, context = B.lib_cog5_boundary_valid_receipt()
        leaked = {**receipt, leak_field: ["case-shaped payload"]}
        assert holdout_receipt_structural_issues(leaked), leak_field
        assert validate_holdout_receipt(leaked, context), leak_field

    @pytest.mark.parametrize("leak_field", B.lib_cog5_boundary_per_case_leak_fields())
    def test_mutant_tolerant_validator_misses_the_leak(self, leak_field):
        """NEGATIVE CONTROL (§12 row 6 mutant 1 — 'per-case field tolerated
        in a receipt'): a validator that silently drops unknown fields
        ACCEPTS the leaking receipt (the escape, demonstrated) while the
        real validator REDs the same bytes — the gate is load-bearing."""
        receipt, _context = B.lib_cog5_boundary_valid_receipt()
        leaked = {**receipt, leak_field: ["case-shaped payload"]}
        # the mutant tolerates the leak (misses it entirely)…
        assert B.lib_cog5_boundary_tolerant_structural_issues(leaked) == ()
        # …the real gate does not.
        from framework.evolution.contracts import holdout_receipt_structural_issues
        assert holdout_receipt_structural_issues(leaked), leak_field

    def test_untrusted_context_never_validates(self):
        """The oracle receipt is trust-anchored: without the trusted
        ValidationContext even an aggregate-only receipt refuses (context
        required — no self-attesting receipts)."""
        from framework.evolution.contracts import validate_holdout_receipt
        receipt, _context = B.lib_cog5_boundary_valid_receipt()
        issues = validate_holdout_receipt(receipt, None)
        assert issues
        assert any(i.code == "verification.context_required" for i in issues)


# ===========================================================================
# sim 6 leg 2 — the BOUNDARY refusal layer: league/generator import attempts
# ===========================================================================
class TestBoundaryRefusalLayer:
    def test_league_and_generator_read_attempts_red(self, tmp_path):
        """sim-6 seed 1: league/generator code paths attempting to reach the
        holdout module RED under the shipped engine + the W1 ROW 8 row —
        each blind sibling, the specific rule id."""
        row = CONFIG.row_for_token(HOLDOUT_TOKEN)
        for name in ("league", "generator"):
            rel = f"framework/evolution/{name}.py"
            _write(tmp_path, rel,
                   f"import {HOLDOUT_TOKEN}\n"
                   f"CASES = {name}_cases = None  # a case-read attempt\n")
            viol = gate.scan(tmp_path)
            assert rel in _paths_for(viol, row.rule_ids["unallowlisted"]), (name, viol)
            (tmp_path / rel).unlink()
        assert gate.scan(tmp_path) == []

    def test_mutant_allowlisted_league_import_escapes(self, tmp_path):
        """NEGATIVE CONTROL (§12 row 6 mutant 2 — 'an allowlisted league
        import of holdout_gen'): mutate a COPY of the manifest to allowlist
        the league on ROW 8, and the SAME tree the real manifest REDs scans
        CLEAN — the named escape, proven side by side; the real row's
        deliberate absence is what bites."""
        rel = "framework/evolution/league.py"
        _write(tmp_path, "tree" + "/" + rel, f"import {HOLDOUT_TOKEN}\n")
        tree = tmp_path / "tree"
        # real manifest: the league import REDs
        real_row = CONFIG.row_for_token(HOLDOUT_TOKEN)
        assert rel in _paths_for(gate.scan(tree),
                                 real_row.rule_ids["unallowlisted"])
        # mutated manifest: league allowlisted onto ROW 8
        raw = yaml.safe_load(
            (_REPO / "cabinet/config/boundary-manifest.yml").read_text(encoding="utf-8"))
        mutated = False
        for row in raw["rows"]:
            if row.get("token") == HOLDOUT_TOKEN:
                row["allowlist_exact"] = list(row.get("allowlist_exact") or []) + [rel]
                mutated = True
        assert mutated, "ROW 8 not found in the manifest — cannot build the mutant"
        mutant_manifest = tmp_path / "mutant-boundary-manifest.yml"
        mutant_manifest.write_text(yaml.safe_dump(raw, sort_keys=False),
                                   encoding="utf-8")
        mutant_config = gate.load_config(mutant_manifest)
        # the mutant row TOLERATES the import…
        assert mutant_config.row_for_token(HOLDOUT_TOKEN).is_allowlisted(rel)
        # …and the engine under the mutant config misses the escape entirely.
        assert gate.scan(tree, mutant_config) == []

    def test_blind_sibling_curation_check_bites_on_the_mutant_row(self, tmp_path):
        """Belt-and-braces on the same mutant: a curation-level checker (any
        blind sibling allowlisted/internal on ROW 8 = finding) returns [] on
        the REAL row and REDs on the mutated row."""
        def _row8_curation_findings(row) -> list[str]:
            findings = []
            for name in ("league", "generator", "arena", "candidate",
                         "scorers", "bench_factory"):
                sib = f"framework/evolution/{name}.py"
                if row.is_allowlisted(sib) or row.is_internal(sib):
                    findings.append(f"blind sibling curated onto ROW 8: {sib}")
            return findings

        assert _row8_curation_findings(CONFIG.row_for_token(HOLDOUT_TOKEN)) == []
        raw = yaml.safe_load(
            (_REPO / "cabinet/config/boundary-manifest.yml").read_text(encoding="utf-8"))
        for row in raw["rows"]:
            if row.get("token") == HOLDOUT_TOKEN:
                row["allowlist_exact"] = (list(row.get("allowlist_exact") or [])
                                          + ["framework/evolution/league.py"])
        mutant_manifest = tmp_path / "mutant-boundary-manifest.yml"
        mutant_manifest.write_text(yaml.safe_dump(raw, sort_keys=False),
                                   encoding="utf-8")
        mutant_row = gate.load_config(mutant_manifest).row_for_token(HOLDOUT_TOKEN)
        findings = _row8_curation_findings(mutant_row)
        assert findings and "league" in findings[0]


# ===========================================================================
# §7.4 — the Stage-A honesty assert (task-pinned: the interim is honestly
# NOT Ring-0; both the Stage-A boundary and the eventual listing enforce)
# ===========================================================================
class TestStageAHonesty:
    def test_stage_a_interim_is_honest_not_ring0(self):
        """While framework/policies/immutable-core.yml carries NO holdout
        listing (Stage A), the §7.5.5 compensating controls must ALL be
        in-tree — content-pin sibling, egg delete + expect-absent pair, the
        ROW 8 invisibility row — and nothing here claims Ring-0. When the
        listing LANDS (Stage B, the Captain window) the premise flips and
        this test is trivially green: Stage B is strictly stronger, and the
        Stage-A controls' own retirement is governed by their owning files
        (test_cog5_holdout_pin.py), never re-keyed here."""
        listing_text = _IMMUTABLE_CORE.read_text(encoding="utf-8")
        if HOLDOUT_GEN_REL in listing_text:
            pytest.skip(
                "Stage B landed: immutable-core.yml now LISTS the holdout "
                "module, so the gate-S0 refusal binds from the listing and the "
                "Stage-A interim premise no longer applies (Stage B is strictly "
                "stronger). Declared as a SKIP, not a silent pass, so the "
                "Stage A -> B transition is visible in the skip report.")
        # Stage A: (a) the content-pin sibling test exists
        assert (_HERE / "test_cog5_holdout_pin.py").exists(), (
            "Stage-A control missing: the holdout content-pin sibling test")
        # (b) the egg exclusion sibling pair (delete + expect-absent)
        manifest_text = _EGG_MANIFEST.read_text(encoding="utf-8")
        assert f"delete {HOLDOUT_GEN_REL}" in manifest_text, (
            "Stage-A control missing: the egg-manifest holdout delete rule")
        assert f"expect-absent {HOLDOUT_GEN_REL}" in manifest_text, (
            "Stage-A control missing: the egg-manifest holdout expect-absent rule")
        # (c) the ROW 8 invisibility row is live in the shipped engine
        row = CONFIG.row_for_token(HOLDOUT_TOKEN)
        assert row.sweep is True
        assert set(row.allowlist_exact) == {ORACLE_CLI_REL}, (
            "ROW 8 sole-reader curation drifted while Stage-A interim")
        # globs are a second curation surface: a widened pattern admits a
        # reader without ever touching allowlist_exact, so pin it too.
        assert set(row.allowlist_globs) == {HOLDOUT_PIN_TEST_GLOB}, (
            "ROW 8 allowlist_globs drifted while Stage-A interim — a widened "
            "glob smuggles a reader past the exact-list pin")
        # honesty: Stage A is NOT Ring-0 — the gate-S0 refusal is absent by
        # construction until the listing lands; asserting the listing's
        # ABSENCE here is the honest statement (no overclaim).
        assert "holdout_gen" not in listing_text


# ===========================================================================
# X7 — benchmark-case metadata gate (live on fixtures; ingestion arm W5)
# ===========================================================================
class TestX7CaseMetadata:
    def test_complete_case_passes_the_gate(self):
        assert B.lib_cog5_boundary_case_metadata_violations(
            B.lib_cog5_boundary_make_case()) == []

    @pytest.mark.parametrize("missing", B.LIB_COG5_BOUNDARY_X7_REQUIRED)
    def test_mutant_metadata_less_case_refuses(self, missing):
        """NEGATIVE CONTROL (X7 mutant — 'a metadata-less case REFUSES
        ingestion'): dropping ANY required field is a named refusal."""
        case = B.lib_cog5_boundary_make_case()
        del case[missing]
        findings = B.lib_cog5_boundary_case_metadata_violations(case)
        assert findings and missing in findings[0]

    def test_malformed_metadata_refuses(self):
        bad_split = B.lib_cog5_boundary_make_case(split="training")
        assert any("split" in f for f in
                   B.lib_cog5_boundary_case_metadata_violations(bad_split))
        bad_cutoff = B.lib_cog5_boundary_make_case(cutoff_ts="2026-07-24 00:00:00")
        assert any("canonical UTC" in f for f in
                   B.lib_cog5_boundary_case_metadata_violations(bad_cutoff))
        bad_flag = B.lib_cog5_boundary_make_case(promotion_eligible="no")
        assert any("promotion_eligible" in f for f in
                   B.lib_cog5_boundary_case_metadata_violations(bad_flag))
        bad_leak = B.lib_cog5_boundary_make_case(leakage_constraints={})
        assert any("leakage_constraints" in f for f in
                   B.lib_cog5_boundary_case_metadata_violations(bad_leak))

    def test_split_law_league_sees_public_cases_only(self):
        """§7.1: public = league-visible cases; private = aggregates only;
        holdout = oracle receipt only (never cases, never per-case)."""
        assert B.lib_cog5_boundary_league_sees_cases("public") is True
        assert B.lib_cog5_boundary_league_sees_cases("private") is False
        assert B.lib_cog5_boundary_league_sees_cases("holdout") is False
        with pytest.raises(ValueError):
            B.lib_cog5_boundary_league_sees_cases("training")


# ===========================================================================
# §6.2 — synthetic NEVER opens the league (this family's touchpoint)
# ===========================================================================
class TestSyntheticNeverCounts:
    def test_this_familys_synthetic_fixtures_count_zero(self):
        """The task-pinned law: synthetic corpora are sanctioned for
        plumbing/mutants, and NEVER count toward a league-opening minimum.
        Every fixture row this family mints is synthetic/sim_replay and the
        §6.2 counting predicate counts ZERO of them."""
        rows = [
            B.lib_cog5_boundary_stamp_provenance(
                {"candidate_id": f"cand-{i}"}, source_class)
            for i, source_class in enumerate(("generator", "arena", "sim"))
        ]
        assert all(r["provenance"] in ("synthetic", "sim_replay") for r in rows)
        assert B.lib_cog5_boundary_provenance_violations(rows) == []
        assert B.lib_cog5_boundary_count_toward_minimums(rows) == 0

    def test_named_real_sources_do_count(self):
        """The positive control: ingester-stamped rows from NAMED real
        sources are exactly what counts."""
        rows = [
            B.lib_cog5_boundary_stamp_provenance({"id": 1}, "consequence_ledger"),
            B.lib_cog5_boundary_stamp_provenance({"id": 2}, "live_emission"),
        ]
        assert [r["provenance"] for r in rows] == ["real_mined", "real_live"]
        assert B.lib_cog5_boundary_count_toward_minimums(rows) == 2

    def test_mutant_laundering_reds(self):
        """NEGATIVE CONTROL (§6.2 laundering arm): a generator-side row that
        CLAIMS real provenance REDs custody; the ingester stamp overwrites
        whatever a candidate wrote; out-of-enum provenance refuses."""
        laundered = {"candidate_id": "cand-x", "provenance": "real_mined",
                     "source_class": "generator"}
        findings = B.lib_cog5_boundary_provenance_violations([laundered])
        assert findings and "LAUNDERING" in findings[0]
        assert B.lib_cog5_boundary_count_toward_minimums([laundered]) == 0
        # the ingester stamp is custody: candidate-set provenance is overwritten
        stamped = B.lib_cog5_boundary_stamp_provenance(laundered, "generator")
        assert stamped["provenance"] == "synthetic"
        # out-of-enum refuses ingestion
        assert B.lib_cog5_boundary_provenance_violations(
            [{"provenance": "definitely_real", "source_class": "generator"}])
        with pytest.raises(ValueError):
            B.lib_cog5_boundary_stamp_provenance({}, "wishful_source")


# ===========================================================================
# t1 integration probe — the shared corpus core (SELF-ARMING import guard)
# ===========================================================================
class TestSharedCorpusIntegration:
    def test_provenance_vocabulary_agrees_with_t1_core(self):
        """SELF-ARMING (no retirement needed): skips while the t1-owned
        lib_cog5_corpus.py has not landed (W2 runs t1/t2/t3 in parallel) and
        goes LIVE automatically at integration. When live: if the shared
        core exposes a provenance vocabulary under its expected names, it
        must MATCH the §6.2 closed enum — a drift routes loud, never
        silently forked."""
        corpus = B.lib_cog5_boundary_corpus_module()
        if corpus is None:
            pytest.skip(
                "t1-owned lib_cog5_corpus.py not yet landed (parallel W2 unit) — "
                "this probe arms itself the moment t1's file lands at integration; "
                "no retirement condition needed (import-guard, not vacuity).")
        for attr in ("PROVENANCE", "LIB_COG5_CORPUS_PROVENANCE", "PROVENANCE_ENUM"):
            vocab = getattr(corpus, attr, None)
            if vocab is not None:
                assert set(vocab) == set(B.LIB_COG5_BOUNDARY_PROVENANCE), (
                    f"t1 corpus {attr} diverges from the §6.2 closed enum — "
                    f"route to the integrator")
                break


# ===========================================================================
# vacuity arms — behavioral surfaces that land W5 (companions RED on landing)
# ===========================================================================
class TestVacuityArms:
    def test_holdout_gen_absent_companion(self):
        """COMPANION absence assertion: REDs the moment holdout_gen.py lands
        (W5), forcing the docstring RETIREMENT CONDITION (replace the
        behavioral skip below with the live oracle-vs-league runtime arm)."""
        assert not (_REPO / HOLDOUT_GEN_REL).exists(), (
            "holdout_gen.py LANDED — retire this vacuity arm: enable the live "
            "behavioral leakage battery per this file's docstring RETIREMENT "
            "CONDITION (league/generator case/fingerprint/per-case READS must "
            "refuse at runtime).")

    def test_behavioral_leakage_arm_vacuity(self):
        """VACUITY SKIP — retire when framework/evolution/holdout_gen.py
        lands (W5): the runtime arm proves league/generator-side case,
        fingerprint, and per-case-result reads REFUSE against the real
        module, beyond the import-granular boundary proven live above."""
        if not (_REPO / HOLDOUT_GEN_REL).exists():
            pytest.skip(
                "vacuity: framework/evolution/holdout_gen.py not yet landed (W5) — "
                "retire when it lands; the absence companion above REDs then.")
        pytest.fail("unreachable while the absence companion holds")

    def test_oracle_cli_absent_companion(self):
        """COMPANION absence assertion for the sole-reader CLI (W5)."""
        assert not (_REPO / ORACLE_CLI_REL).exists(), (
            "cog5-holdout-oracle.py LANDED — retire this vacuity arm: assert the "
            "CLI is the sole sanctioned holdout reader and emits ONLY aggregate "
            "receipts that validate (per the docstring RETIREMENT CONDITION).")

    def test_oracle_cli_sole_reader_arm_vacuity(self):
        """VACUITY SKIP — retire when cabinet/scripts/cog5-holdout-oracle.py
        lands (W5): drive the CLI on a fixture suite and assert its emitted
        receipt validates aggregate-only (and nothing else leaves)."""
        if not (_REPO / ORACLE_CLI_REL).exists():
            pytest.skip(
                "vacuity: cog5-holdout-oracle.py not yet landed (W5) — retire when "
                "it lands; the absence companion above REDs then.")
        pytest.fail("unreachable while the absence companion holds")

    def test_bench_factory_absent_companion(self):
        """COMPANION absence assertion for the X7 ingestion surface (W5)."""
        assert not (_REPO / BENCH_FACTORY_REL).exists(), (
            "bench_factory.py LANDED — retire this vacuity arm: feed the real "
            "miner a metadata-less case and assert it REFUSES ingestion (X7), "
            "per the docstring RETIREMENT CONDITION.")

    def test_x7_ingestion_arm_vacuity(self):
        """VACUITY SKIP — retire when framework/evolution/bench_factory.py
        lands (W5): the real miner must stamp the full X7 block on every
        produced case and REFUSE a metadata-less one (the live twin of the
        fixture gate proven above)."""
        if not (_REPO / BENCH_FACTORY_REL).exists():
            pytest.skip(
                "vacuity: bench_factory.py not yet landed (W5) — retire when it "
                "lands; the absence companion above REDs then.")
        pytest.fail("unreachable while the absence companion holds")
