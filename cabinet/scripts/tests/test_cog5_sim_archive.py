"""test_cog5_sim_archive.py — COG-5 W2 T1, the ARCHIVE/LINEAGE family battery.

Contract: docs/plans/cognitive-core-phase-5-contract-2026-07-24.md
  §12 sim 1  — the E1 run: >=20 seeded candidates vs the eval substrate; full
               ranked archive; every lineage/failure preserved (X1);
               deterministic re-rank from the same archive + seeds.
               Mutants: the archive drops a failed candidate; rank order
               varies under PYTHONHASHSEED.
  §12 sim 9  — corrupt archive: truncated tail, bit-flipped row, forged
               prev_hash, broken seal — each DETECTED; serve REFUSES beyond
               the last good seal; pending.json heal completes exactly-once.
               Mutant: a skip-verify reader serves past corruption.
               Plus the per-STORE layer (`TestStoreLevelDetection`): the
               counters the store already writes — the manifest's
               row_count/chain_head and the §5.2 periodic anchor attestation
               — are READ BACK, which is what catches a row deleted at a
               record boundary from the UNSEALED open segment (no link
               breaks, no seal covers it, so neither the row nor the seal
               layer can see it).
               BOUND ON THAT CLAIM (say it here, because this docstring is
               the first thing a reader of this file sees): it holds against
               a BARE deletion — an editor that removes the row and leaves
               the store's own counters behind. It does NOT hold against a
               COMPLETE editor that also rewrites the manifest and re-mints
               the anchor over the shortened chain; that escape is real,
               declared, and pinned by
               `test_known_limit_the_complete_editor_that_also_re_mints_the_anchor`.
               The store layer raises the cost of a silent deletion; it is
               not a signature, and nothing here claims it is (E4).
  §12 sim 10 — lineage rollback: the independently rehearsed seal + RESTORE
               drill reproduces every chain head + row count, no lineage row
               lost. Mutants: a restore that drops or reorders a lineage row.
  §1 X1      — the E1 run produces no live mutation (observation-only).
  §5.3       — duplicate-tolerant ingest (dedupe by CONTENT FINGERPRINT, the
               P1 race), keyed against the fingerprints ALREADY IN THE TARGET
               STORE so the §11.2 periodic re-read of an accruing log admits
               each fact exactly once; the record_kind FIELD MAP; and the P1
               lock-fold rider property.
  §5.4/§6.2  — the archive record shape + the provenance counting predicate.

"At least 20 candidates" is sim #1's PARAMETER, never the sim count (the
recorded count-trap) — `E1_MIN_CANDIDATES` is asserted as a floor on the
seeded corpus, and nothing in this file counts sims.

WHAT RUNS LIVE vs WHAT IS VACUITY-GUARDED (the mergeability law, §13):
everything below runs LIVE on this tree — the reference substrate in
`lib_cog5_archive_fixtures.py` implements the §5.2 physics, so every sim
assert and every negative-control mutant is proven biting NOW, with zero
implementation present. Two arms are vacuity-guarded because they can only
bind the REAL surfaces once those land: the archive writer module
(`framework/evolution/archive.py` + its optional `emitter.py` split) and the
restore CLI (`cabinet/scripts/cog5-archive-restore.py`). Each carries a
COMPANION absence assertion that REDs the moment its path lands, plus a
RETIREMENT CONDITION in its docstring — a guard can never silently outlive
its reason. This unit merges GREEN on a tree where no implementation exists.

Synthetic corpora are sanctioned here for plumbing + known mutants (§8.1);
what synthetic may never do is open the league or ground a live-fitness
claim — `test_synthetic_never_counts_toward_minimums` is that law's
mechanical form.

S0: interpreter python3.12; no DB, no network; every archive root is a
tmp_path; every timestamp is declared. Provenance: authored per the
2026-07-07 full-autonomy grant + the 2026-07-20 cognitive-masterplan
continuous grant (COG-5 contract §12/§13, W2 T1).
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog5_archive_fixtures as FIX  # noqa: E402
import lib_cog5_corpus as CORE           # noqa: E402

# The ONE shipped framework surface this battery binds live: the evolution
# contracts already on the tree (T3's family imports it too). Never a future
# surface, and never the projection kernel (boundary row 6 — §10).
from framework.evolution import contracts  # noqa: E402

TRAJECTORY_SCHEMA_REL = "framework/schemas/cognitive-trajectory.v2.schema.json"


# ---------------------------------------------------------------------------
# shared builders
# ---------------------------------------------------------------------------
def _populated(root: Path, *, count: int = FIX.E1_DEFAULT_CANDIDATES,
               seed: int = 20260724) -> tuple[FIX.ReferenceArchive, dict]:
    archive = FIX.ReferenceArchive(root, rows_per_segment=8)
    result = FIX.run_e1(archive, FIX.seeded_candidates(count),
                        FIX.eval_substrate(), seed=seed)
    return archive, result


def _assert_healed_store_is_servable(archive, sequence: int,
                                     on_cadence: bool) -> None:
    """A healed store is not merely INTACT — a disciplined reader must be able
    to SERVE it, all of it.

    This is the property a heal that reconciles only the ROW silently breaks:
    the chain links, the exactly-once count and the manifest counters are all
    correct, `verify_archive` still says ANCHOR_MISSING, `safe_sequence`
    collapses to the last good seal, and `serve_rows` hands out nothing. So
    every heal arm asserts servability, never just row identity.
    """
    result = FIX.verify_archive(archive.root)
    assert result["ok"], (
        f"a correctly-healed store does not verify at sequence {sequence}: "
        f"{result['findings']}")
    assert result["safe_sequence"] == sequence
    assert ([int(r["sequence"]) for r in FIX.serve_rows(archive.root)]
            == list(range(1, sequence + 1))), "the healed store served short"
    assert (archive.root / FIX.ANCHOR_NAME).is_file() is on_cadence, (
        "the attestation the interrupted commit owed must be present exactly "
        "when the reconciled sequence lands on the cadence — no more, no less")


def _record(index: int, **overrides):
    base = dict(
        candidate_id=f"cand-{index:03d}", run_id="run-1", sequence=0,
        prev_hash=CORE.ZERO_HASH, source_class="arena",
        payload_ref=CORE.content_fingerprint({"i": index}),
        classification="internal", decision="allow", parent_ids=[],
        generation=1, operator="op", outcome="ranked",
    )
    base.update(overrides)
    return CORE.archive_record(**base)


# ===========================================================================
# the T1-owned shared core — the CROSS-UNIT contract T2 and T3 import
# ===========================================================================
class TestSharedCoreContract:
    """`lib_cog5_corpus.py` is imported by T2 (`as CORE`) and T3
    (`as _cog5_corpus`) under guards they wrote before it landed. These are
    the properties those guards depend on."""

    def test_core_imports_with_pure_stdlib(self):
        """T2's guard is `except ModuleNotFoundError`. If the core raised
        that from an import of its own, T2 would bind CORE=None and its
        companion would RED with a misleading message. So the core's module
        scope must import nothing outside the stdlib."""
        tree = ast.parse((_HERE / "lib_cog5_corpus.py").read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
        assert imported <= set(sys.stdlib_module_names), (
            f"lib_cog5_corpus imports non-stdlib modules {sorted(imported - set(sys.stdlib_module_names))} "
            f"— the sibling guards cannot survive that (see this test's docstring)")

    @pytest.mark.parametrize("attr", ("PROVENANCE", "LIB_COG5_CORPUS_PROVENANCE",
                                      "PROVENANCE_ENUM"))
    def test_provenance_exposed_under_every_probed_name(self, attr):
        """T3's cross-unit probe walks exactly these three names and binds the
        FIRST that exists. All three must carry the identical §6.2 enum, or
        the probe's verdict depends on attribute order."""
        vocab = getattr(CORE, attr)
        assert set(vocab) == {"real_live", "real_mined", "synthetic", "sim_replay"}

    def test_provenance_is_the_contract_enum(self):
        assert CORE.PROVENANCE == ("real_live", "real_mined", "synthetic",
                                   "sim_replay")
        assert CORE.REAL_PROVENANCE == frozenset({"real_live", "real_mined"})

    def test_provenance_is_ingester_stamped_not_candidate_set(self):
        """CHAIN OF CUSTODY (§6.2): whatever a candidate wrote is OVERWRITTEN
        from the source class — candidate code can never set or rewrite it."""
        laundered = {"candidate_id": "c1", "provenance": "real_live"}
        stamped = CORE.stamp_provenance(laundered, "generator")
        assert stamped["provenance"] == "synthetic"
        stamped_real = CORE.stamp_provenance({"x": 1}, "consequence_ledger")
        assert stamped_real["provenance"] == "real_mined"
        assert CORE.stamp_provenance({}, "live_emission")["provenance"] == "real_live"
        with pytest.raises(ValueError):
            CORE.stamp_provenance({}, "wishful_source")

    def test_mutant_laundering_and_out_of_enum_refuse(self):
        """NEGATIVE CONTROL (§6.2): a `real_*` claim from a non-real source
        class is LAUNDERING; an out-of-enum provenance REFUSES ingestion."""
        launder = {"provenance": "real_mined", "source_class": "generator"}
        findings = CORE.provenance_violations([launder])
        assert findings and "LAUNDERING" in findings[0]
        assert CORE.count_toward_minimums([launder]) == 0
        refused = CORE.provenance_violations(
            [{"provenance": "definitely_real", "source_class": "generator"}])
        assert refused and "REFUSE" in refused[0]

    def test_synthetic_never_counts_toward_minimums(self):
        """The §6.2/§8.1 law made mechanical: synthetic and sim_replay rows
        count ZERO toward any league-opening minimum, always."""
        rows = [
            CORE.stamp_provenance({"i": 0}, "consequence_ledger"),
            CORE.stamp_provenance({"i": 1}, "live_emission"),
            CORE.stamp_provenance({"i": 2}, "generator"),
            CORE.stamp_provenance({"i": 3}, "arena"),
            CORE.stamp_provenance({"i": 4}, "sim"),
        ]
        assert CORE.count_toward_minimums(rows) == 2
        assert CORE.provenance_violations(rows) == []

    def test_sibling_source_class_spellings_both_resolve(self):
        """RECORDED CROSS-UNIT DIVERGENCE (routed to the integrator): T2
        spells two source classes `verdict_inbox_labels` / `sim_replay`; T3
        spells them `verdict_inbox` / `sim`. The contract pins only the
        PROVENANCE enum, which both agree on — so the core accepts both
        spellings and folds them, and NEITHER sibling breaks at the join.

        This alias table is DEBT: when the integrator pins one spelling the
        table dies. The test pins the debt so it cannot be forgotten."""
        assert CORE.SOURCE_CLASS_ALIASES == {"verdict_inbox_labels": "verdict_inbox",
                                             "sim_replay": "sim"}
        for spelling in ("verdict_inbox", "verdict_inbox_labels"):
            assert CORE.stamp_provenance({}, spelling)["provenance"] == "real_mined"
            assert CORE.count_toward_minimums(
                [{"provenance": "real_mined", "source_class": spelling}]) == 1
        for spelling in ("sim", "sim_replay"):
            assert CORE.stamp_provenance({}, spelling)["provenance"] == "sim_replay"

    def test_the_alias_fold_is_structurally_incapable_of_changing_meaning(self):
        """THE RECORDED STRICTNESS ASYMMETRY, decided and pinned.

        T1 ACCEPTS `sim_replay` as a source-class spelling; T3 REFUSES it
        (`lib_cog5_boundary_stamp_provenance` raises on any class outside its
        own lists). DELIBERATE — but the earlier justification was loose and
        is corrected here.

        CONCEDED, because it is true: `sim_replay` IS a provenance token being
        used as a source-class slug. Calling that "a fold within one
        vocabulary" described the FOLD (source-slug -> source-slug) while
        saying nothing about the TOKEN, and the token crossing from the
        provenance vocabulary into the source-class one is structurally the
        same shape `record_kind_conflations` forbids. So the shape is not the
        defence.

        THE DEFENCE IS THE HARM TEST, and it survives: this fold's OUTPUT is
        provenance `sim_replay` — byte-identical to what T2's own table
        produces for the same slug — so the token cannot mean anything other
        than what it already means on both sides of the join. A conflation
        harms by making a token mean something ELSE in its new field; here it
        means exactly the same thing, and the arms below measure that rather
        than assert it. And `record_kind_conflations`, which governs the
        `record_kind` fields where the disjoint-vocabulary conflation actually
        lives, is untouched by any of this and stays strict.

        Why not simply refuse, matching T3: the spelling split is a RECORDED
        cross-unit divergence routed to the integrator, and the contract pins
        only the PROVENANCE enum — which both siblings already agree on.
        Refusing here would unilaterally settle that divergence in T3's favour
        on no authority. T1 is the JOIN point, the one place where refusing a
        sibling's un-pinned spelling costs mergeability; T3 is not, so its
        refusal is free and correct for T3. (Stated exactly: removing the
        alias would not RED T2's suite today — T2 carries its own table and
        imports this core only for presence-at-join — so the argument is the
        integrator's authority, not a breakage claim. MEASURED on the combined
        tree: deleting the alias leaves T2 and T3 fully green and REDs only
        T1's own two arms.)

        The strictness cost is bounded MECHANICALLY here: an alias whose key
        is a provenance token may only target a slug that stamps that very
        provenance. That structural rule is what makes this fold inert, and it
        REDs if the table grows an entry that could launder.

        HOW FAR THAT PREDICATE REACHES, honestly: `meaning_changing_aliases`
        inspects only PROVENANCE-KEYED aliases, so it is what catches
        `real_live -> generator`. The other laundering shapes — `arena ->
        live_emission`, `sim -> live_emission` — are keyed on non-provenance
        slugs and are caught instead by the pre-existing count-toward-minimum
        arms (`test_synthetic_never_counts_toward_minimums` and friends), each
        MEASURED RED. The guarantee is therefore SUITE-level, not
        predicate-level, and the difference is worth naming: a future reader
        who deletes those count arms would not be protected by this one.
        """
        def meaning_changing_aliases(table, source_map):
            return sorted(
                f"{key}->{target}" for key, target in table.items()
                if key in CORE.PROVENANCE_ENUM and source_map.get(target) != key)

        assert meaning_changing_aliases(CORE.SOURCE_CLASS_ALIASES,
                                        CORE.SOURCE_CLASS_TO_PROVENANCE) == []
        # the same predicate over a FORGED table, so it is not vacuous
        assert meaning_changing_aliases({"real_live": "generator"},
                                        CORE.SOURCE_CLASS_TO_PROVENANCE) == \
            ["real_live->generator"]

        # inert in the two ways that matter: identical rows, identical counts
        row = {"candidate_id": "c1"}
        assert (CORE.stamp_provenance(row, "sim_replay")
                == CORE.stamp_provenance(row, "sim"))
        for spelling in ("sim", "sim_replay"):
            stamped = CORE.stamp_provenance(row, spelling)
            assert CORE.count_toward_minimums([stamped]) == 0
            assert CORE.provenance_violations([stamped]) == []


# ===========================================================================
# the canonical dialect — a REPLICA with two live parity tripwires
# ===========================================================================
class TestCanonicalDialectParity:
    def test_replica_matches_the_kernel_source_bytes(self):
        """§5.2 (rev-1 SF-4): the archive replicates the kernel's canonical
        dialect instead of importing it, because boundary row 6 deliberately
        does not allowlist the cog5 globs (§10). The replica is kept honest
        by compiling the kernel's OWN function from its source bytes — an
        `ast` read, never an import, so the boundary sweep sees exactly what
        the boundary intends."""
        kernel_canonical = CORE.kernel_canonical_bytes_impl()
        for value in CORE.PARITY_CORPUS:
            assert kernel_canonical(value) == CORE.canonical_bytes(value), (
                f"replica dialect diverged from the kernel on {value!r} — "
                f"route to the integrator, never 'fix' by loosening the test")

    def test_this_family_never_imports_the_projection_kernel(self):
        """The boundary made self-checking: no file of this unit may carry a
        static or dynamic import of the projection package (§10 ROW-6
        non-extension). The gate sweeps for this too; failing here first
        gives the builder the reason rather than a rule id."""
        for name in ("lib_cog5_corpus.py", "lib_cog5_archive_fixtures.py",
                     Path(__file__).name):
            tree = ast.parse((_HERE / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith("framework.projection"), name
                elif isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").startswith("framework.projection"), name

    def test_replica_matches_the_shipped_contracts_dialect(self):
        """The other parity side, over a PUBLIC shipped surface: the
        evolution contracts fingerprint their payloads in the same recorder
        dialect (contracts.py:282-293). Same bytes in, same digest out."""
        payload = {"a": 1, "z": "ünïcodé", "n": [3, 1], "deep": {"k": None}}
        assert (contracts.holdout_receipt_payload_fingerprint(payload)
                == CORE.content_fingerprint(payload))

    def test_the_other_dialect_is_never_conflated(self):
        """§5.1 names the trap: the scheduler store's ensure_ascii=True
        FILE-ORDER dialect is a DIFFERENT dialect. If the replica ever
        drifted onto it, non-ASCII payloads would hash differently — pinned
        so the drift cannot pass silently."""
        value = {"city": "København"}
        ascii_dialect = json.dumps(value, ensure_ascii=True, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8")
        assert CORE.canonical_bytes(value) != ascii_dialect
        assert "\\u" not in CORE.canonical_bytes(value).decode("utf-8")


# ===========================================================================
# sim 1 — the E1 run
# ===========================================================================
class TestSim1E1Run:
    def test_at_least_twenty_seeded_candidates(self):
        """Sim #1's PARAMETER (never the sim count — the recorded
        count-trap): the E1 corpus is >= 20 seeded prompt/retrieval
        candidates."""
        candidates = FIX.seeded_candidates()
        assert len(candidates) >= FIX.E1_MIN_CANDIDATES == 20
        assert {c["kind"] for c in candidates} == {"prompt", "retrieval"}

    def test_full_ranked_archive_over_the_eval_substrate(self, tmp_path):
        archive, result = _populated(tmp_path / "archive")
        assert result["candidates"] == result["archived"] == 24
        assert len(result["ranked"]) == 24
        assert len(set(result["ranked"])) == 24, "the rank must be a TOTAL order"
        assert FIX.verify_archive(archive.root)["ok"]

    def test_x1_every_lineage_and_failure_preserved(self, tmp_path):
        """X1 (L198 verbatim, "ranked archive preserves every lineage/
        failure"): winners, losers AND crashed runs each get an archive
        lineage row — with parents, generation and operator intact."""
        archive, result = _populated(tmp_path / "archive")
        rows = archive.rows()
        assert {r["candidate_id"] for r in rows} == {
            c["candidate_id"] for c in FIX.seeded_candidates(24)}
        outcomes = {o: sum(1 for r in rows if r["outcome"] == o)
                    for o in CORE.CANDIDATE_OUTCOMES}
        assert outcomes["failed"] > 0 and outcomes["crashed"] > 0, (
            "the seeded corpus must contain real failures and crashes, or X1 "
            "is asserted over nothing")
        assert sum(outcomes.values()) == 24
        for row in rows:
            assert CORE.archive_record_violations(row) == []
            assert set(row["lineage"]) == set(CORE.LINEAGE_REQUIRED)

    def test_mutant_archive_drops_a_failed_candidate(self, tmp_path):
        """NEGATIVE CONTROL (sim 1): an archive that silently omits failed /
        crashed candidates. X1's completeness check must catch it."""
        archive = FIX.ReferenceArchive(tmp_path / "archive", rows_per_segment=8)
        FIX.run_e1(archive, FIX.seeded_candidates(24), FIX.eval_substrate(),
                   seed=1, drop_failed=True)
        archived = {r["candidate_id"] for r in archive.rows()}
        seeded = {c["candidate_id"] for c in FIX.seeded_candidates(24)}
        assert archived != seeded, "the drop mutant did not bite"
        assert len(seeded - archived) == 5      # 3 seeded failures + 2 crashes
        # the chain still verifies — silent lineage loss is invisible to
        # integrity alone, which is exactly why X1 is a SEPARATE gate
        assert FIX.verify_archive(archive.root)["ok"]

    def test_deterministic_rerank_under_three_distinct_hashseeds(self, tmp_path):
        """Sim 1's determinism claim, exercised the only way it can be: hash
        randomisation is fixed at interpreter start, so the re-rank runs in
        three SUBPROCESSES under distinct PYTHONHASHSEED values, from the
        same archive + seeds."""
        archive, result = _populated(tmp_path / "archive")
        orders = FIX.rerank_under_hashseeds(archive.root, ("0", "1", "2"))
        assert len({tuple(o) for o in orders}) == 1, (
            f"re-rank varied across PYTHONHASHSEED: {orders}")
        assert len(orders[0]) == 24

    def test_mutant_rank_order_varies_under_hashseed(self, tmp_path):
        """NEGATIVE CONTROL (sim 1): a ranker whose order is decided by set
        iteration. Five distinct seeds must produce more than one ordering —
        a mutant that happened to agree would be decoration."""
        archive, _ = _populated(tmp_path / "archive")
        orders = FIX.rerank_under_hashseeds(
            archive.root, ("0", "1", "2", "3", "4"), hash_dependent=True)
        assert len({tuple(o) for o in orders}) > 1, (
            "the hash-dependent ranker did not vary — the determinism gate "
            "is not proven load-bearing")


# ===========================================================================
# X1 — the E1 run produces NO live mutation (observation-only)
# ===========================================================================
class TestX1NoLiveMutation:
    def test_live_surface_is_byte_identical_after_the_run(self, tmp_path):
        """X8/X1 part (i): a BYTE-IDENTICAL before/after fingerprint over the
        quiescent live surfaces the run could plausibly touch."""
        live = tmp_path / "live"
        live.mkdir()
        (live / "services.yml").write_text("services: []\n", encoding="utf-8")
        (live / "prompt.md").write_text("# champion prompt\n", encoding="utf-8")
        before = FIX.fingerprint_tree(live)
        archive = FIX.ReferenceArchive(tmp_path / "archive", rows_per_segment=8)
        FIX.run_e1(archive, FIX.seeded_candidates(24), FIX.eval_substrate(),
                   seed=3, live_surface=live)
        assert FIX.fingerprint_tree(live) == before

    def test_archive_growth_is_additive_only(self, tmp_path):
        """X1 part (ii): every pre-run chain head remains a PREFIX of the
        post-run heads — nothing pre-existing modified or deleted."""
        archive = FIX.ReferenceArchive(tmp_path / "archive", rows_per_segment=8)
        FIX.run_e1(archive, FIX.seeded_candidates(24), FIX.eval_substrate(),
                   seed=3, run_id="e1-a")
        before = FIX.archive_report(archive.root)
        FIX.run_e1(archive, FIX.seeded_candidates(24), FIX.eval_substrate(),
                   seed=4, run_id="e1-b")
        after = FIX.archive_report(archive.root)
        assert FIX.chain_heads_prefix_preserved(before["segment_chain_heads"],
                                                after["segment_chain_heads"])
        assert after["lineage_order"][:before["row_count"]] == before["lineage_order"]
        assert after["row_count"] == before["row_count"] * 2
        assert after["ok"]

    def test_mutant_run_mutates_the_live_surface(self, tmp_path):
        """NEGATIVE CONTROL (X1): a run that writes into the live surface it
        is only allowed to observe. The fingerprint must catch it."""
        live = tmp_path / "live"
        live.mkdir()
        (live / "services.yml").write_text("services: []\n", encoding="utf-8")
        before = FIX.fingerprint_tree(live)
        archive = FIX.ReferenceArchive(tmp_path / "archive", rows_per_segment=8)
        FIX.run_e1(archive, FIX.seeded_candidates(24), FIX.eval_substrate(),
                   seed=3, live_surface=live, mutate_live=True)
        assert FIX.fingerprint_tree(live) != before, "the X1 mutant did not bite"


# ===========================================================================
# sim 9 — corrupt archive
# ===========================================================================
class TestSim9CorruptArchive:
    @pytest.mark.parametrize("name,corrupt,expected", (
        ("truncated tail", lambda a: FIX.corrupt_truncate_tail(a.root),
         "TRUNCATED_TAIL"),
        ("bit-flipped row", lambda a: FIX.corrupt_bitflip_row(a.root, sequence=20),
         "BITFLIP"),
        ("forged prev_hash",
         lambda a: FIX.corrupt_forge_prev_hash(a.root, sequence=20),
         "FORGED_PREV_HASH"),
        ("broken seal", lambda a: FIX.corrupt_break_seal(a.root, index=0),
         "BROKEN_SEAL"),
        ("re-signed seal forge",
         lambda a: FIX.corrupt_break_seal(a.root, index=0, resign=True),
         "BROKEN_SEAL"),
    ))
    def test_each_corruption_is_detected(self, tmp_path, name, corrupt, expected):
        """Sim 9's four corruptions, each DETECTED and each naming the exact
        escape. The re-signed seal is the sophisticated forge: internally
        self-consistent, so only the seal-vs-segment limb catches it — both
        seal limbs are therefore proven load-bearing."""
        archive, _ = _populated(tmp_path / "archive")
        archive.seal_open_segment()
        assert FIX.verify_archive(archive.root)["ok"], "precondition: clean"
        corrupt(archive)
        result = FIX.verify_archive(archive.root)
        assert not result["ok"], f"{name} was not detected"
        assert any(f.startswith(expected) for f in result["findings"]), (
            f"{name} detected, but not as {expected}: {result['findings']}")

    def test_serve_refuses_beyond_the_last_good_seal(self, tmp_path):
        """Sim 9: the disciplined reader serves only what a good seal still
        attests, and refuses everything past it."""
        archive, _ = _populated(tmp_path / "archive")
        archive.seal_open_segment()
        clean = FIX.serve_rows(archive.root)
        assert len(clean) == 24
        FIX.corrupt_bitflip_row(archive.root, sequence=20)
        result = FIX.verify_archive(archive.root)
        served = FIX.serve_rows(archive.root)
        assert result["safe_sequence"] < 20
        assert served, "a good sealed prefix must still be servable"
        assert [r["sequence"] for r in served] == list(
            range(1, result["safe_sequence"] + 1))
        assert max(r["sequence"] for r in served) < 20

    def test_mutant_skip_verify_reader_serves_past_corruption(self, tmp_path):
        """NEGATIVE CONTROL (sim 9): the reader that skips verification hands
        out the corrupted rows — proving the verification is load-bearing
        rather than decorative."""
        archive, _ = _populated(tmp_path / "archive")
        archive.seal_open_segment()
        FIX.corrupt_bitflip_row(archive.root, sequence=20)
        disciplined = FIX.serve_rows(archive.root)
        mutant = FIX.serve_rows(archive.root, skip_verify=True)
        assert len(mutant) > len(disciplined), "the skip-verify mutant did not bite"
        assert any(r["sequence"] == 20 for r in mutant)
        assert not any(r["sequence"] == 20 for r in disciplined)

    @pytest.mark.parametrize("crash_at,on_cadence", ((3, False), (4, True)),
                             ids=("off-cadence", "on-cadence"))
    def test_pending_heal_completes_exactly_once_after_a_lost_append(
            self, tmp_path, crash_at, on_cadence):
        """Sim 9: a crash BETWEEN the write-ahead and the append. The heal
        finishes it once; a second heal is a no-op (returns None), and the
        row count never moves twice.

        Parametrised over the CADENCE POSITION alongside its sibling below.
        This limb finishes the interrupted append through `_commit`, which
        owes the periodic attestation whenever the reconciled sequence lands
        on the cadence — so the on-cadence parameter is what proves the
        obligation is discharged here rather than assumed.
        """
        archive = FIX.ReferenceArchive(tmp_path / "archive", rows_per_segment=8)
        for i in range(1, crash_at):
            archive.append(_record(i))
        archive.append_crashing(_record(crash_at))
        assert len(archive.rows()) == crash_at - 1
        assert (archive.root / FIX.PENDING_NAME).exists()
        assert (crash_at % archive.anchor_every == 0) is on_cadence, (
            "the cadence parameters are mis-declared — this arm would prove "
            "the wrong thing")

        assert archive.heal() is not None
        assert len(archive.rows()) == crash_at
        assert archive.heal() is None, "the heal was not exactly-once"
        assert len(archive.rows()) == crash_at
        _assert_healed_store_is_servable(archive, crash_at, on_cadence)

    @pytest.mark.parametrize("crash", (
        lambda a, r: a.append_crashing_before_anchor(r),
        lambda a, r: a.append_crashing_after_commit(r),
    ), ids=("crash-before-the-anchor",
            "crash-before-the-pending-clear-anchor-omitted"))
    @pytest.mark.parametrize("crash_at,on_cadence", ((2, False), (4, True)),
                             ids=("off-cadence", "on-cadence"))
    def test_pending_heal_is_exactly_once_after_a_lost_ack(
            self, tmp_path, crash, crash_at, on_cadence):
        """The harder limb: a crash AFTER the append but BEFORE pending.json
        was cleared. A naive heal would append a SECOND copy; the disciplined
        one reconciles and writes nothing.

        PARAMETRISED OVER THE CADENCE POSITION, and that is the whole point of
        this arm's shape. `_commit` mints the periodic attestation AFTER the
        segment append, so a crash in that window at an ON-CADENCE sequence
        leaves a durable row whose attestation was never minted. A heal that
        reconciles the row but does not mint it returns a store that is
        permanently ANCHOR_MISSING: `verify_archive` never ok, `safe_sequence`
        pinned to the last good seal (0 here — nothing is sealed yet), and the
        disciplined reader serves NOTHING. A correctly-healed store, made
        unservable forever.

        This arm used to crash at sequence 2 only, which is OFF-cadence with
        `anchor_every=4`, and therefore could not see that. It now covers both
        cadence positions and both crash windows inside `_commit` — the true
        pre-anchor state (`append_crashing_before_anchor`: nothing but the row
        landed) and the later pre-pending-clear one. A test that only ever
        crashes off-cadence is why the regression shipped; the on-cadence
        parameters RED against a heal that does not mint.
        """
        archive = FIX.ReferenceArchive(tmp_path / "archive", rows_per_segment=8)
        for i in range(1, crash_at):
            archive.append(_record(i))
        crash(archive, _record(crash_at))
        assert len(archive.rows()) == crash_at
        assert (archive.root / FIX.PENDING_NAME).exists()
        assert (crash_at % archive.anchor_every == 0) is on_cadence, (
            "the cadence parameters are mis-declared — this arm would prove "
            "the wrong thing")

        assert archive.heal() is not None
        assert len(archive.rows()) == crash_at, "the heal duplicated a committed row"
        assert not (archive.root / FIX.PENDING_NAME).exists()
        assert archive.heal() is None, "the heal was not exactly-once"
        assert len(archive.rows()) == crash_at
        _assert_healed_store_is_servable(archive, crash_at, on_cadence)

    def test_pending_with_a_tampered_body_refuses(self, tmp_path):
        """A write-ahead record whose hash does not match its body is never
        replayed — the heal fails closed instead of committing a forgery."""
        archive = FIX.ReferenceArchive(tmp_path / "archive", rows_per_segment=8)
        archive.append(_record(1))
        archive.append_crashing(_record(2))
        pending_path = archive.root / FIX.PENDING_NAME
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        pending["event"]["classification"] = "public"
        pending_path.write_text(json.dumps(pending), encoding="utf-8")
        with pytest.raises(FIX.ArchiveError):
            archive.heal()
        assert len(archive.rows()) == 1


# ===========================================================================
# sim 9 (store layer) — the counters the store already writes, READ BACK
# ===========================================================================
#: Findings produced by the per-STORE layer, as opposed to the per-ROW and
#: per-SEAL layers. Used to prove which layer actually caught an escape.
_STORE_LEVEL = ("ROW_COUNT_MISMATCH", "MANIFEST_HEAD_MISMATCH",
                "ANCHOR_MISSING", "ANCHOR_SEQUENCE_MISMATCH", "FORGED_ANCHOR")


class TestStoreLevelDetection:
    """The archive writes two independent counters on every commit — the
    manifest's `row_count`/`chain_head` and the periodic `anchor.json`
    attestation (§5.2). Verification consults BOTH. These arms prove the
    escape they close is real, and that each detector bites.

    They also pin where the layer STOPS: the attestation is unsigned, so an
    editor who re-mints it escapes. That is declared, not hidden — see
    `test_known_limit_the_complete_editor_that_also_re_mints_the_anchor`."""

    def test_mutant_row_dropped_from_the_unsealed_open_segment(self, tmp_path):
        """NEGATIVE CONTROL (sim 9) — THE escape the row and seal layers
        cannot see: a whole record deleted at a record boundary from the
        UNSEALED open segment.

        No link breaks (the deleted row was the only one pointing forward),
        the file still ends on a newline so the truncated-tail detector is
        silent, the remaining sequences are contiguous, and no seal covers an
        open segment. This arm asserts BOTH halves: that the row/seal layers
        stay silent (so the escape is genuine, not a second spelling of an
        existing detector) and that the store layer names it anyway.
        """
        archive, _ = _populated(tmp_path / "archive")
        assert 2 not in {s["index"] for s in archive.manifest()["seals"]}, (
            "precondition: the tail segment must be OPEN, or this arm proves "
            "the seal layer rather than the store layer")
        assert FIX.verify_archive(archive.root)["ok"], "precondition: clean"

        removed = FIX.corrupt_drop_open_segment_tail(archive.root)
        assert removed == 1
        result = FIX.verify_archive(archive.root)

        assert not result["ok"], "the open-segment row deletion was not detected"
        assert any(f.startswith("ROW_COUNT_MISMATCH") for f in result["findings"]), (
            f"expected the manifest's own row_count to catch it: "
            f"{result['findings']}")
        assert all(f.split(":")[0] in _STORE_LEVEL for f in result["findings"]), (
            f"the row/seal layers were supposed to be BLIND to this escape — "
            f"if one of them caught it, this arm is not testing what it says: "
            f"{result['findings']}")
        assert len(archive.rows()) == 23 and archive.manifest()["row_count"] == 24

    def test_mutant_manifest_stops_declaring_its_row_count(self, tmp_path):
        """NEGATIVE CONTROL: a manifest that simply omits the counter. An
        absent declaration must FAIL CLOSED — reading it as agreement would
        hand any tail editor a one-line bypass of the detector above."""
        archive, _ = _populated(tmp_path / "archive")
        FIX.corrupt_strip_manifest_declaration(archive.root, field="row_count")
        result = FIX.verify_archive(archive.root)
        assert not result["ok"], "an undeclared row_count read as agreement"
        assert any(f.startswith("ROW_COUNT_MISMATCH") for f in result["findings"])

    def test_mutant_manifest_head_stops_matching_the_last_row(self, tmp_path):
        """NEGATIVE CONTROL: the manifest's declared chain head is the
        detector that covers the rows PAST the last anchor cadence point,
        which the attestation by construction cannot see."""
        archive, _ = _populated(tmp_path / "archive")
        manifest = archive.manifest()
        manifest["chain_head"] = "0" * 63 + "1"
        FIX.atomic_write(archive.root / FIX.MANIFEST_NAME,
                         json.dumps(manifest, ensure_ascii=False,
                                    sort_keys=True, indent=2) + "\n")
        result = FIX.verify_archive(archive.root)
        assert not result["ok"]
        assert any(f.startswith("MANIFEST_HEAD_MISMATCH") for f in result["findings"])

    def test_the_anchor_attests_the_walked_chain_at_its_cadence_point(self, tmp_path):
        """§5.2's periodic attestation, shown to be a real claim about THIS
        store: it stands at the last cadence point (a multiple of
        `anchor_every`, not the last row) and names that row's chain head."""
        archive, _ = _populated(tmp_path / "archive")
        anchor = json.loads((archive.root / FIX.ANCHOR_NAME).read_text(
            encoding="utf-8"))
        rows = archive.rows()
        cadence = (len(rows) // archive.anchor_every) * archive.anchor_every
        assert anchor["sequence"] == cadence == 24
        assert anchor["chain_head"] == rows[cadence - 1]["row_hash"]
        assert archive.manifest()["anchor_every"] == archive.anchor_every
        assert FIX.verify_archive(archive.root)["ok"]

    def test_the_attestation_lags_the_tail_without_being_a_finding(self, tmp_path):
        """The cadence is every N sequences, so rows past the last attestation
        point are legitimately un-attested — the check must compare against
        the CADENCE POINT, never the last row, or a normal store would RED."""
        archive, _ = _populated(tmp_path / "archive")
        for i in range(100, 102):                 # 24 -> 26, cadence stays 24
            archive.append(_record(i))
        anchor = json.loads((archive.root / FIX.ANCHOR_NAME).read_text(
            encoding="utf-8"))
        assert anchor["sequence"] == 24 < len(archive.rows()) == 26
        assert FIX.verify_archive(archive.root)["ok"]

    def test_mutant_tail_edit_that_also_rewrites_the_manifest(self, tmp_path):
        """NEGATIVE CONTROL — the THOROUGH editor, and the reason the two
        store detectors are not redundant: drop a row from the unsealed open
        segment AND repair the manifest's counters so they agree with the
        shortened store. The whole manifest layer now says nothing.

        The periodic attestation still does: it was minted at a cadence point
        BEFORE the edit, and repairing the manifest does not touch it. This
        arm asserts the anchor limb ALONE carries the detection.

        Bounded exactly, and NOT more: this catches an editor who stops at the
        manifest. It does not catch one who also re-mints the attestation —
        see `test_known_limit_the_complete_editor_that_also_re_mints_the_anchor`
        immediately below, which pins that limit rather than leaving the claim
        sounding absolute."""
        archive, _ = _populated(tmp_path / "archive")
        FIX.corrupt_drop_open_segment_tail(archive.root)
        repaired = FIX.repair_manifest_counters(archive.root)
        assert repaired["row_count"] == 23, "precondition: the manifest agrees"

        result = FIX.verify_archive(archive.root)
        assert not result["ok"], (
            "a tail edit that also rewrote the manifest verified CLEAN — the "
            "attestation is not load-bearing")
        assert [f for f in result["findings"]
                if f.startswith("ANCHOR_SEQUENCE_MISMATCH")], result["findings"]
        assert not any(f.startswith(("ROW_COUNT_MISMATCH",
                                     "MANIFEST_HEAD_MISMATCH"))
                       for f in result["findings"]), (
            f"the manifest layer was supposed to be silenced by the repair, "
            f"so this arm proves the ANCHOR: {result['findings']}")

    def test_known_limit_the_complete_editor_that_also_re_mints_the_anchor(
            self, tmp_path):
        """DECLARED KNOWN LIMIT of this reference model — pinned in the same
        idiom as the unit's other declared residuals, so a future reader
        cannot mistake the model for the real thing.

        Minting an attestation here needs NO SECRET. `write_anchor` is a pure
        digest over public fields (§5.2's shape "minus the signer" — SIGNING
        is the recorder's, and is deliberately out of scope for this corpus).
        So the COMPLETE editor — drop a tail row, repair the manifest
        counters, AND re-mint the anchor over the shortened chain — produces a
        fully self-consistent store: `verify_archive` returns ok, findings are
        empty, and the lost row is silently gone.

        What the anchor therefore buys, stated exactly: it defeats an editor
        who does not re-mint it, which is every editor that only knows how to
        repair the manifest (the arm above). It does not defeat one who does.
        Closing that gap is what a SIGNED attestation would buy, and nothing
        weaker — not another unsigned counter, which the same editor would
        simply also repair.

        This does NOT weaken the non-redundancy claim the arm above proves:
        the manifest layer and the anchor layer still catch escapes the other
        cannot, which was established by revert, not by this bound.

        Both halves are asserted so this is a MEASUREMENT and not a
        concession: without the re-mint the store is caught; with it, it is
        not. Should the model ever gain a signer, the first half stays true
        and the second half REDs — which is the point.

        RETIREMENT CONDITION: when the archive's attestation gains a signer
        (key material, or any secret an editor cannot reproduce), invert the
        second half to `assert not FIX.verify_archive(root)["ok"]` and assert
        the forged signature is named. A known-limit arm must never outlive
        its reason.
        """
        archive, _ = _populated(tmp_path / "archive")
        assert FIX.verify_archive(archive.root)["ok"], "precondition: clean"
        lost = archive.rows()[-1]["record_id"]

        FIX.corrupt_drop_open_segment_tail(archive.root)
        FIX.repair_manifest_counters(archive.root)
        caught = FIX.verify_archive(archive.root)
        assert not caught["ok"] and any(
            f.startswith("ANCHOR_SEQUENCE_MISMATCH") for f in caught["findings"]), (
            f"the editor who stops at the manifest must still be caught, or "
            f"this arm measures nothing: {caught['findings']}")

        reminted = FIX.remint_anchor(archive.root)
        assert reminted["sequence"] == 20, (
            "precondition: the shortened store's own cadence point")
        escaped = FIX.verify_archive(archive.root)
        assert escaped["ok"] and escaped["findings"] == [], (
            f"the complete editor was caught — if the model gained a signer, "
            f"RETIRE this known-limit arm per its docstring: "
            f"{escaped['findings']}")
        served = FIX.serve_rows(archive.root)
        assert len(served) == 23
        assert lost not in {r["record_id"] for r in served}, (
            "the whole point of the limit: the row is silently GONE")

    def test_mutant_store_shrunk_below_its_first_attestation(self, tmp_path):
        """NEGATIVE CONTROL: the same thorough edit against a store whose
        cadence point is its FIRST one — the walk no longer reaches sequence
        `anchor_every` at all, so there is no attested row left to compare.
        An attestation that exists for a point the store cannot reach is
        itself the finding; the check must not silently skip."""
        archive = FIX.ReferenceArchive(tmp_path / "archive", rows_per_segment=8)
        for i in range(5):
            archive.append(_record(i))
        assert (archive.root / FIX.ANCHOR_NAME).is_file()
        FIX.corrupt_drop_open_segment_tail(archive.root, rows=3)   # 5 -> 2
        FIX.repair_manifest_counters(archive.root)

        result = FIX.verify_archive(archive.root)
        assert not result["ok"], "a store below its own attestation read clean"
        assert any(f.startswith("ANCHOR_SEQUENCE_MISMATCH")
                   for f in result["findings"]), result["findings"]

    @pytest.mark.parametrize("name,resign,limb", (
        ("crude forge", False, "anchor_hash does not match"),
        ("re-signed forge", True, "names chain head"),
    ))
    def test_mutant_forged_anchor(self, tmp_path, name, resign, limb):
        """NEGATIVE CONTROL (§5.2): a lying attestation. The crude forge
        leaves `anchor_hash` stale; the RE-SIGNED forge recomputes it over the
        lie, so it is internally self-consistent and only the
        anchor-vs-walked-chain limb can catch it. Both limbs are therefore
        proven load-bearing — the seal pattern, applied to the attestation."""
        archive, _ = _populated(tmp_path / "archive")
        FIX.corrupt_forge_anchor(archive.root, resign=resign)
        result = FIX.verify_archive(archive.root)
        assert not result["ok"], f"{name} was not detected"
        forged = [f for f in result["findings"] if f.startswith("FORGED_ANCHOR")]
        assert forged, f"{name} detected, but not as FORGED_ANCHOR: {result['findings']}"
        assert any(limb in f for f in forged), (
            f"{name} was caught by the wrong limb: {forged}")

    def test_mutant_anchor_dropped(self, tmp_path):
        """NEGATIVE CONTROL: the attestation deleted outright — the shape a
        copy-out or restore that forgets to carry `anchor.json` produces. An
        absent attestation where one is due fails closed."""
        archive, _ = _populated(tmp_path / "archive")
        FIX.corrupt_drop_anchor(archive.root)
        result = FIX.verify_archive(archive.root)
        assert not result["ok"], "a missing attestation read as agreement"
        assert any(f.startswith("ANCHOR_MISSING") for f in result["findings"])

    def test_a_store_below_its_first_cadence_point_needs_no_attestation(self, tmp_path):
        """The other direction, so the check cannot be satisfied by simply
        always demanding an anchor: a young store that has not reached its
        first cadence point verifies clean with no attestation at all."""
        archive = FIX.ReferenceArchive(tmp_path / "archive", rows_per_segment=8)
        for i in range(3):                        # < anchor_every (4)
            archive.append(_record(i))
        assert not (archive.root / FIX.ANCHOR_NAME).exists()
        assert FIX.verify_archive(archive.root)["ok"]

    @pytest.mark.parametrize("name,seal,corrupt", (
        ("truncated tail", True, lambda a: FIX.corrupt_truncate_tail(a.root)),
        ("bit-flipped row", True,
         lambda a: FIX.corrupt_bitflip_row(a.root, sequence=20)),
        ("forged prev_hash", True,
         lambda a: FIX.corrupt_forge_prev_hash(a.root, sequence=20)),
        ("broken seal", True, lambda a: FIX.corrupt_break_seal(a.root, index=0)),
        ("re-signed seal forge", True,
         lambda a: FIX.corrupt_break_seal(a.root, index=0, resign=True)),
        ("dropped open-segment row", False,
         lambda a: FIX.corrupt_drop_open_segment_tail(a.root)),
        ("forged anchor", True,
         lambda a: FIX.corrupt_forge_anchor(a.root, resign=True)),
        ("dropped anchor", True, lambda a: FIX.corrupt_drop_anchor(a.root)),
    ))
    def test_safe_sequence_never_over_serves_at_any_corruption_position(
            self, tmp_path, name, seal, corrupt):
        """NON-REGRESSION on the refusal boundary (§12 sim 9): whatever the
        corruption and whichever layer catches it, the disciplined reader
        serves EXACTLY the last good seal's prefix and never one row more.
        Adding store-level detectors must not loosen that — a detector that
        made the reader serve further would be worse than no detector."""
        archive, _ = _populated(tmp_path / "archive")
        if seal:
            archive.seal_open_segment()
        assert FIX.verify_archive(archive.root)["ok"], "precondition: clean"
        corrupt(archive)

        result = FIX.verify_archive(archive.root)
        assert not result["ok"], f"{name} was not detected"
        expected = (int(result["last_good_seal"]["last_sequence"])
                    if result["last_good_seal"] else 0)
        assert result["safe_sequence"] == expected, (
            f"{name}: safe_sequence {result['safe_sequence']} is not the last "
            f"good seal's bound {expected}")
        served = FIX.serve_rows(archive.root)
        assert all(int(r["sequence"]) <= expected for r in served), (
            f"{name}: the reader served past the last good seal")


# ===========================================================================
# sim 10 — lineage rollback (the independently rehearsed RESTORE)
# ===========================================================================
class TestSim10LineageRollback:
    def test_seal_and_restore_reproduces_every_chain_head(self, tmp_path):
        """Sim 10 / ledger :3381: rollback is a seal + copy-out + verified
        re-read into a FRESH root — every chain head and the row count
        reproduced, no lineage row lost."""
        archive, _ = _populated(tmp_path / "archive")
        original = FIX.seal_and_copy_out(archive, tmp_path / "copy")
        restored = FIX.restore(tmp_path / "copy", tmp_path / "restored")

        assert restored["ok"]
        assert restored["row_count"] == original["row_count"] == 24
        assert restored["segment_chain_heads"] == original["segment_chain_heads"]
        assert restored["chain_head"] == original["chain_head"]
        assert restored["lineage_order"] == original["lineage_order"]
        assert restored["candidate_ids"] == original["candidate_ids"]

    def test_the_source_archive_is_never_deleted(self, tmp_path):
        """§5.2/§16, the ONE deliberate divergence from the cache grammar:
        the archive is RETAINED SEALED. A cache-delete rollback would forge
        the observation-only history and foreclose R5."""
        archive, _ = _populated(tmp_path / "archive")
        before = FIX.archive_report(archive.root)
        FIX.seal_and_copy_out(archive, tmp_path / "copy")
        FIX.restore(tmp_path / "copy", tmp_path / "restored")
        after = FIX.archive_report(archive.root)
        assert archive.root.exists()
        assert after["row_count"] == before["row_count"]
        assert after["lineage_order"] == before["lineage_order"]
        assert after["ok"]

    def test_the_restore_carries_the_attestation(self, tmp_path):
        """The rollback drill reproduces the STORE, and §5.2's attestation is
        part of it: a restore that left `anchor.json` behind would hand over a
        store that can no longer prove where its chain stood. Both directions
        — carried, the restore verifies; dropped, it fails closed."""
        archive, _ = _populated(tmp_path / "archive")
        FIX.seal_and_copy_out(archive, tmp_path / "copy")
        restored = FIX.restore(tmp_path / "copy", tmp_path / "restored")
        assert restored["ok"]
        source_anchor = (archive.root / FIX.ANCHOR_NAME).read_text(encoding="utf-8")
        for root in (tmp_path / "copy", tmp_path / "restored"):
            assert (root / FIX.ANCHOR_NAME).read_text(encoding="utf-8") == source_anchor

        FIX.corrupt_drop_anchor(tmp_path / "restored")
        assert not FIX.verify_archive(tmp_path / "restored")["ok"], (
            "a restore that dropped the attestation verified clean — the "
            "carry is not load-bearing")

    def test_mutant_restore_drops_a_lineage_row(self, tmp_path):
        """NEGATIVE CONTROL (sim 10): a restore that loses one row. Both the
        row count and the chain must catch it."""
        archive, _ = _populated(tmp_path / "archive")
        original = FIX.seal_and_copy_out(archive, tmp_path / "copy")
        mutant = FIX.restore_dropping_row(tmp_path / "copy", tmp_path / "bad",
                                          sequence=5)
        assert not mutant["ok"], "the dropped-row restore was not detected"
        assert mutant["row_count"] == original["row_count"] - 1
        assert mutant["lineage_order"] != original["lineage_order"]

    def test_mutant_restore_reorders_a_lineage_row(self, tmp_path):
        """NEGATIVE CONTROL (sim 10): a restore that preserves every row but
        REORDERS two. The row count and the id multiset are unchanged, so
        only an order-SENSITIVE chain can catch it — which is precisely why
        §5.1 refuses to make the archive a kernel projection."""
        archive, _ = _populated(tmp_path / "archive")
        original = FIX.seal_and_copy_out(archive, tmp_path / "copy")
        mutant = FIX.restore_reordering_rows(tmp_path / "copy", tmp_path / "bad")
        assert mutant["row_count"] == original["row_count"]
        assert mutant["candidate_ids"] == original["candidate_ids"]
        assert mutant["lineage_order"] != original["lineage_order"]
        assert not mutant["ok"], "the reordered restore was not detected"

    def test_the_kernel_algebra_would_miss_the_reorder(self, tmp_path):
        """§5.1's substrate decision, DEMONSTRATED rather than asserted: the
        kernel's `chained_rows_hash` SORTS by order_key, so it is unchanged
        by a reversal — an archive built on it could not detect the mutant
        above. The archive's sequential chain is order-sensitive. This is the
        evidence for "NOT a fourth kernel projection"."""
        archive, _ = _populated(tmp_path / "archive")
        values = FIX.kernel_would_miss_reorder(archive.rows()[:6])
        assert values["in_order"] == values["reversed"], (
            "the kernel algebra is supposed to be arrival-order INVARIANT "
            "(kernel.py:118-130) — re-anchor this demonstration")
        assert values["archive_in_order"] != values["archive_reversed"]


# ===========================================================================
# §5.3 — duplicate-tolerant ingest (the P1 race)
# ===========================================================================
class TestIngestDuplicateTolerance:
    def test_dedup_is_by_content_fingerprint(self, tmp_path):
        """§5.3: two dispatchers racing one log can each record the SAME
        idempotency key. The archive ingest dedupes on the canonical-bytes
        CONTENT fingerprint and records the duplication honestly."""
        result = FIX.ingest_shadow_rows(FIX.shadow_rows_with_p1_race())
        assert result["counts"] == {"ingested": 3, "duplicates_recorded": 1}
        assert result["duplicates"][0]["occurrence"] == 2
        assert result["duplicates"][0]["fingerprint"].startswith("sha256:")

    def test_same_key_different_body_is_two_facts(self):
        """The other direction, and the reason the key is the WRONG dedup
        surface: one idempotency key with two different decisions is two
        distinct facts and both must survive."""
        rows = FIX.shadow_rows_with_p1_race()
        decisions = [r["decision"] for r in FIX.ingest_shadow_rows(rows)["ingested"]
                     if "decision" in r]
        assert sorted(decisions) == ["would_dispatch", "would_skip"]

    def test_mutant_dedup_by_idempotency_key_loses_a_fact(self):
        """NEGATIVE CONTROL (§5.3): keying dedup on the idempotency key
        collapses two genuinely different records — silent data loss."""
        rows = FIX.shadow_rows_with_p1_race()
        mutant = FIX.ingest_shadow_rows(rows, dedupe="key")
        honest = FIX.ingest_shadow_rows(rows, dedupe="content")
        assert mutant["counts"]["ingested"] < honest["counts"]["ingested"]
        assert "would_skip" not in [r.get("decision") for r in mutant["ingested"]]

    def test_mutant_no_dedup_lands_the_raced_duplicate_twice(self):
        """NEGATIVE CONTROL (§5.3): without dedup the P1 race writes the same
        record twice and the archive over-counts."""
        rows = FIX.shadow_rows_with_p1_race()
        mutant = FIX.ingest_shadow_rows(rows, dedupe="none")
        assert mutant["counts"]["ingested"] == 4
        assert mutant["counts"]["duplicates_recorded"] == 0

    def test_re_ingesting_an_accruing_log_admits_nothing_twice(self):
        """§5.3/§11.2: shadow accrual is routed through a PERIODIC organ
        manifest, so cycle 2 necessarily re-presents every row cycle 1 already
        took — re-reading an accruing log is the normal cadence, not an edge
        case. Dedup is therefore keyed against the fingerprints ALREADY IN THE
        TARGET STORE: the second cycle admits nothing and records all four
        re-presentations honestly."""
        rows = FIX.shadow_rows_with_p1_race()
        first = FIX.ingest_shadow_rows(rows)
        assert first["counts"] == {"ingested": 3, "duplicates_recorded": 1}
        second = FIX.ingest_shadow_rows(rows, store=first["ingested"])
        assert second["counts"] == {"ingested": 0, "duplicates_recorded": 4}
        assert all(d["fingerprint"].startswith("sha256:")
                   for d in second["duplicates"])

    def test_periodic_ingest_cycles_are_idempotent_by_construction(self):
        """The disciplined caller: `ShadowIngestor` holds the target store
        across cycles, so the cadence converges after the first one however
        many times the organ manifest fires. Every fact is held exactly
        once."""
        rows = FIX.shadow_rows_with_p1_race()
        ingestor = FIX.ShadowIngestor()
        counts = [ingestor.ingest(rows)["counts"]["ingested"] for _ in range(4)]
        assert counts == [3, 0, 0, 0], f"the cycle did not converge: {counts}"
        assert len(ingestor.rows) == 3
        assert len(ingestor.duplicates) == 1 + 4 * 3
        decisions = sorted(r["decision"] for r in ingestor.rows if "decision" in r)
        assert decisions == ["would_dispatch", "would_skip"]

    def test_mutant_per_call_dedup_re_admits_the_whole_log_every_cycle(self):
        """NEGATIVE CONTROL (§5.3): the escape this closes — a caller that
        keys dedup only WITHIN one call. Under the expected cadence it
        re-admits the entire log on every cycle, so the archive over-counts
        without a single duplicate ever being recorded.

        This is the same defect shape as `shadow_append_racy` below: a
        decision taken from state held OUTSIDE the store of record. The store
        is the authority in both cases."""
        rows = FIX.shadow_rows_with_p1_race()
        blind = [FIX.ingest_shadow_rows(rows) for _ in range(3)]
        assert [r["counts"]["ingested"] for r in blind] == [3, 3, 3], (
            "the per-call-only escape did not reproduce")
        assert sum(r["counts"]["duplicates_recorded"] for r in blind) == 3
        threaded = FIX.ShadowIngestor()
        assert sum(threaded.ingest(rows)["counts"]["ingested"]
                   for _ in range(3)) == 3 < 9

    def test_re_seeding_from_the_DURABLE_archive_admits_nothing_twice(self, tmp_path):
        """The same §5.3/§11.2 cadence, with the store that a real ingester
        would actually hold: the DURABLE lineage archive, not a list in
        memory.

        `ReferenceArchive.append` stamps `sequence`/`prev_hash`/`record_id`/
        `row_hash` onto every row it takes, so rows read back are not
        byte-identical to the rows that went in. A dedup key computed over the
        row as-read would differ from the key the same fact produces on
        arrival, and the whole log would be re-admitted every cycle — MF-2's
        defect re-entering through the durable door, while the in-memory path
        kept looking correct. Measured before the fix: 3 ingested, not 0.

        Nothing shipped composes these two surfaces today, so this was latent
        rather than live — but `ingest_shadow_rows`'s own durability framing
        invites exactly this composition, so the invariance is closed at the
        dedup key and pinned here instead of left as a trap.
        """
        rows = FIX.shadow_rows_with_p1_race()
        first = FIX.ingest_shadow_rows(rows)
        assert first["counts"] == {"ingested": 3, "duplicates_recorded": 1}

        archive = FIX.ReferenceArchive(tmp_path / "archive", rows_per_segment=8)
        for row in first["ingested"]:
            archive.append(row)
        durable = FIX.serve_rows(archive.root)
        assert len(durable) == 3
        assert FIX.CHAIN_FIELDS <= set(durable[0]), (
            "precondition: the durable rows must actually carry the chain "
            "stamps, or this arm proves nothing")

        assert FIX.ingest_shadow_rows(rows, store=durable)["counts"] == \
            {"ingested": 0, "duplicates_recorded": 4}
        # and through the rehearsed RESTORE, which is how a store comes back
        restored_root = tmp_path / "restored"
        FIX.restore(archive.root, restored_root)
        assert FIX.ingest_shadow_rows(
            rows, store=FIX.serve_rows(restored_root))["counts"] == \
            {"ingested": 0, "duplicates_recorded": 4}

    def test_the_dedup_key_is_chain_field_invariant_but_still_content_sensitive(
            self, tmp_path):
        """The invariance above, bounded — because a dedup key that ignores
        fields is a WEAKENING unless the ignored set is exactly the store's
        own stamps.

        Two directions: the key must not move when the store stamps a row
        (that is the round trip), and it must move when any CONTENT field
        changes (so this can never collapse two genuinely different facts —
        the very loss `dedupe="key"` is the negative control for).

        `CHAIN_FIELDS` is checked against what `_prepare` ACTUALLY adds on a
        real append, never asserted from memory, so the set cannot silently
        drift away from the write path it describes.
        """
        archive = FIX.ReferenceArchive(tmp_path / "archive", rows_per_segment=8)
        incoming = CORE.stamp_provenance(
            CORE.map_shadow_record_kind(FIX.shadow_rows_with_p1_race()[0]), "sim")
        landed = archive.append(incoming)
        assert set(landed) - set(incoming) == set(FIX.CHAIN_FIELDS), (
            "CHAIN_FIELDS no longer describes what the store stamps — "
            "re-anchor it against `_prepare`")

        assert FIX.dedupe_key(landed) == FIX.dedupe_key(incoming)
        assert FIX.strip_chain_fields(landed) == incoming
        # still content-sensitive, in every field the row actually says
        for field, value in (("decision", "would_skip"),
                             ("idempotency_key", "idem-0002"),
                             ("wake_id", "wake-8"),
                             ("provenance", "synthetic")):
            assert FIX.dedupe_key({**landed, field: value}) != \
                FIX.dedupe_key(landed), (
                f"the dedup key ignored a change to content field {field!r} — "
                f"it would collapse two different facts")

    def test_ingested_shadow_rows_are_stamped_secondary_not_countable(self):
        """The shadow log is a SECONDARY source (§5.3 trust order): its rows
        can never count toward a §6.2 minimum."""
        result = FIX.ingest_shadow_rows(FIX.shadow_rows_with_p1_race(),
                                        source_class="sim")
        assert all(r["provenance"] == "sim_replay" for r in result["ingested"])
        assert CORE.count_toward_minimums(result["ingested"]) == 0


# ===========================================================================
# §5.3 — the record_kind FIELD MAP (two disjoint vocabularies)
# ===========================================================================
class TestRecordKindFieldMap:
    def test_shadow_vocabulary_matches_the_shipped_cli_bytes(self):
        """The shadow vocabulary is READ from the shipped CLI, not asserted
        from memory: every literal assigned to a `record_kind` key in
        cog4-dispatch-shadow.py must be exactly {run, decision}."""
        source = (_REPO / FIX.SHADOW_CLI_REL).read_text(encoding="utf-8")
        literals: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (isinstance(key, ast.Constant) and key.value == "record_kind"
                            and isinstance(value, ast.Constant)):
                        literals.add(value.value)
            elif isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "record_kind" and isinstance(kw.value, ast.Constant):
                        literals.add(kw.value.value)
        assert literals == set(CORE.SHADOW_RECORD_KIND), (
            f"the shadow CLI's record_kind vocabulary is {sorted(literals)}, "
            f"not {sorted(CORE.SHADOW_RECORD_KIND)} — re-anchor the §5.3 map")

    def test_trajectory_vocabulary_matches_the_shipped_schema_bytes(self):
        schema = json.loads((_REPO / TRAJECTORY_SCHEMA_REL).read_text(encoding="utf-8"))
        assert (schema["properties"]["record_kind"]["enum"]
                == list(CORE.TRAJECTORY_RECORD_KIND) == ["live", "public_benchmark"])

    def test_the_two_vocabularies_are_disjoint(self):
        assert not (set(CORE.SHADOW_RECORD_KIND) & set(CORE.TRAJECTORY_RECORD_KIND))

    def test_shadow_kind_lands_in_the_archive_native_field(self):
        """§5.3: shadow `record_kind` becomes `shadow_record_kind`; the
        trajectory field is not written at all."""
        mapped = CORE.map_shadow_record_kind(
            {"record_kind": "decision", "idempotency_key": "k"})
        assert mapped[CORE.SHADOW_RECORD_KIND_FIELD] == "decision"
        assert CORE.TRAJECTORY_RECORD_KIND_FIELD not in mapped
        assert CORE.record_kind_conflations(mapped) == []
        with pytest.raises(ValueError):
            CORE.map_shadow_record_kind({"record_kind": "live"})

    def test_mutant_conflation_writes_a_shadow_token_into_record_kind(self):
        """NEGATIVE CONTROL (§5.3): the conflation — a shadow token left in
        the trajectory `record_kind` field. It must RED, in both directions."""
        conflated = FIX.conflating_field_map(
            {"record_kind": "decision", "idempotency_key": "k"})
        findings = CORE.record_kind_conflations(conflated)
        assert findings and "CONFLATION" in findings[0]
        reverse = CORE.record_kind_conflations(
            {CORE.SHADOW_RECORD_KIND_FIELD: "public_benchmark"})
        assert reverse and "CONFLATION" in reverse[0]

    def test_an_archive_record_carrying_a_shadow_kind_stays_clean(self, tmp_path):
        row = _record(1, shadow_record_kind="run")
        assert CORE.archive_record_violations(row) == []
        assert row[CORE.SHADOW_RECORD_KIND_FIELD] == "run"
        assert CORE.TRAJECTORY_RECORD_KIND_FIELD not in row


# ===========================================================================
# §5.3 — the P1 lock-fold rider
# ===========================================================================
class TestP1LockFoldRider:
    def test_folded_read_and_append_admits_one_row_per_key(self, tmp_path):
        """The rider's TARGET property: the replay/dedupe read happens inside
        the same lock hold as the append, so a second writer observing the
        log after the first cannot re-append the key."""
        log = tmp_path / "shadow.jsonl"
        row = {"record_kind": "decision", "idempotency_key": "idem-1",
               "decision": "would_dispatch"}
        assert FIX.shadow_append_folded(log, [row]) == ["idem-1"]
        assert FIX.shadow_append_folded(log, [row]) == []
        assert FIX.read_log_keys(log) == ["idem-1"]

    def test_mutant_read_outside_the_lock_reproduces_the_p1_race(self, tmp_path):
        """NEGATIVE CONTROL (§5.3 / review :218): TODAY's shape — the replay
        keys are read at the call site (cog4-dispatch-shadow.py:859-861)
        before `append_shadow_log` takes its lock (:625-655), so two
        dispatchers each holding a pre-write snapshot both append the same
        key. The interleaving is passed explicitly, so the race is
        DETERMINISTIC — a flaky race test would prove nothing."""
        log = tmp_path / "shadow.jsonl"
        row = {"record_kind": "decision", "idempotency_key": "idem-1",
               "decision": "would_dispatch"}
        snapshot_a = set(FIX.read_log_keys(log))
        snapshot_b = set(FIX.read_log_keys(log))     # both read pre-write
        FIX.shadow_append_racy(log, [row], observed_keys=snapshot_a)
        FIX.shadow_append_racy(log, [row], observed_keys=snapshot_b)
        assert FIX.read_log_keys(log) == ["idem-1", "idem-1"], (
            "the P1 race did not reproduce — the rider test would be vacuous")

    def test_shipped_cli_has_not_yet_folded_the_read_companion(self):
        """COMPANION assertion (the mergeability pattern): the shipped
        `append_shadow_log` does NOT yet perform the replay read itself. This
        REDs the moment the W4 rider lands.

        RETIREMENT CONDITION: when the lock-fold rider lands in
        cabinet/scripts/cog4-dispatch-shadow.py, invert this to
        `assert FIX.shadow_cli_append_folds_read()` and bind the two tests
        above to the real CLI (integrator corpus surgery, §13 — builders
        never edit corpus).
        """
        assert FIX.shadow_cli_append_folds_read() is False, (
            "cog4-dispatch-shadow.py::append_shadow_log now folds the read "
            "in — the P1 rider LANDED: retire this companion per its "
            "docstring and bind the rider tests to the real CLI")


# ===========================================================================
# §5.4 — the archive record shape (observation-only, R5-shaped)
# ===========================================================================
class TestArchiveRecordShape:
    def test_every_required_field_is_present(self):
        row = _record(1)
        assert set(CORE.ARCHIVE_RECORD_REQUIRED) <= set(row)
        assert CORE.archive_record_violations(row) == []

    def test_identity_is_content_excluded(self):
        """The kernel's identity law, replicated: identity is the digest of
        what the record IS ABOUT, so it survives a content change — never a
        build-time ULID (the pinned COG-2 sim-1 mutant class)."""
        row = _record(1)
        changed = dict(row, classification="public",
                       outcome_refs=["evidence:other"])
        assert CORE.archive_identity(changed) == CORE.archive_identity(row)
        other = _record(2)
        assert CORE.archive_identity(other) != CORE.archive_identity(row)

    def test_fitness_claim_is_structurally_none_while_the_league_is_closed(self):
        """§6.3: any league/archive output while closed carries
        `fitness_claim: none`; a row claiming otherwise REDs."""
        assert _record(1)["fitness_claim"] == CORE.FITNESS_CLAIM_NONE
        findings = CORE.archive_record_violations(
            dict(_record(1), fitness_claim="improves_mission_value"))
        assert any("fitness_claim" in f for f in findings)

    def test_payload_refs_are_content_addressed_never_inline_authority(self):
        """foundry §3 L55: the archive may NAME receipts; it cannot assert
        authenticity/credit/eligibility/fitness."""
        findings = CORE.archive_record_violations(
            dict(_record(1), payload_ref={"secret": "inline payload"}))
        assert any("content-addressed" in f for f in findings)

    def test_classification_and_decision_are_recorded_separately(self):
        row = _record(1, decision="deny", classification="restricted")
        assert row["decision"] == "deny" and row["classification"] == "restricted"
        assert CORE.archive_record_violations(row) == []
        with pytest.raises(ValueError):
            _record(1, decision="promote")

    def test_a_lineage_less_row_refuses(self):
        broken = dict(_record(1))
        broken.pop("lineage")
        findings = CORE.archive_record_violations(broken)
        assert any("lineage" in f for f in findings)


# ===========================================================================
# §5.2 — the physical disciplines, asserted on real files
# ===========================================================================
class TestPhysicalDiscipline:
    def test_segments_are_append_only(self, tmp_path):
        """Append-only: prior bytes are never rewritten (the kernel's
        whole-file replace is the CACHE premise §5.1 refuses for an
        archive)."""
        archive = FIX.ReferenceArchive(tmp_path / "archive", rows_per_segment=64)
        archive.append(_record(1))
        first = archive.segment_path(0).read_bytes()
        archive.append(_record(2))
        second = archive.segment_path(0).read_bytes()
        assert second.startswith(first)
        assert len(second) > len(first)

    def test_manifest_writes_leave_no_partial_and_no_debris(self, tmp_path):
        """Manifest-class artifacts use the atomic-write REPLICA: a private
        O_EXCL tmp sibling, fsynced, then os.replace()d. No reader ever sees
        a partial, and no tmp debris is left behind."""
        archive, _ = _populated(tmp_path / "archive")
        manifest = archive.manifest()
        assert manifest["row_count"] == 24
        assert manifest["chain_head"] == archive.chain_head()
        debris = [p.name for p in archive.root.iterdir()
                  if p.name.startswith(".") and p.name.endswith(".tmp")]
        assert debris == []

    def test_sealed_segments_bound_reverify_without_a_retention_cap(self, tmp_path):
        """Sealed segments bound the whole-store re-verify class WITHOUT the
        recorder's mint cap — R5 forbids a cap (unbounded retention)."""
        archive, _ = _populated(tmp_path / "archive")
        archive.seal_open_segment()
        seals = archive.manifest()["seals"]
        assert len(seals) == len(archive.segment_indices()) >= 3
        assert sum(s["rows"] for s in seals) == 24
        assert all(s["seal_hash"] for s in seals)
        # no cap anywhere: keep appending past the sealed bound
        for i in range(100, 110):
            archive.append(_record(i))
        assert len(archive.rows()) == 34
        assert FIX.verify_archive(archive.root)["ok"]

    def test_mutant_non_atomic_manifest_write_is_readable_half_written(self, tmp_path):
        """NEGATIVE CONTROL (§5.2): the predictions store's disqualified
        mechanics are named anti-patterns — here the NON-ATOMIC manifest
        write (predictions-store :45-57). A truncate-then-write interrupted
        mid-payload leaves a manifest a reader can observe half-written; the
        archive's atomic replica cannot, because the target is byte-untouched
        until the `os.replace`.
        """
        archive, _ = _populated(tmp_path / "archive")
        target = archive.root / FIX.MANIFEST_NAME
        good = target.read_text(encoding="utf-8")

        # the anti-pattern: truncate in place, then "crash" mid-payload
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(good[: len(good) // 2])
        with pytest.raises(ValueError):
            json.loads(target.read_text(encoding="utf-8"))

        # the replica: a full-payload atomic replace restores a whole manifest
        FIX.atomic_write(target, good)
        assert archive.manifest()["row_count"] == 24
        assert FIX.verify_archive(archive.root)["ok"]


# ===========================================================================
# vacuity arms — the REAL surfaces land in W4 (companions RED on landing)
# ===========================================================================
class TestVacuityArms:
    def test_archive_module_absent_companion(self):
        """COMPANION absence assertion: REDs the moment the archive writer
        lands, forcing the retirement of the vacuity arm below."""
        for rel in (FIX.ARCHIVE_MODULE_REL, FIX.EMITTER_MODULE_REL):
            assert not (_REPO / rel).exists(), (
                f"{rel} LANDED — retire the archive-module vacuity arm: bind "
                f"the sim 1/9/10 batteries in this file to the real module "
                f"per its docstring RETIREMENT CONDITION.")

    def test_real_archive_module_vacuity(self):
        """VACUITY SKIP — RETIREMENT CONDITION: retire when
        framework/evolution/archive.py lands (W4). Replace this body with the
        live bindings: (a) run the SAME sim 1/9/10 batteries above against
        the real module's public API instead of `ReferenceArchive` (the
        batteries are proven TODAY on the reference tier; the implementation
        must satisfy them UNMODIFIED — builders never edit corpus,
        contradictions route to the integrator); (b) assert the module
        imports no `framework.projection` symbol (§5.2/§10 ROW-6
        non-extension — the replica path, not the seam); (c) assert its
        default archive root is the §5.4 cabinet default.
        """
        if not (_REPO / FIX.ARCHIVE_MODULE_REL).exists():
            pytest.skip(
                f"vacuity: {FIX.ARCHIVE_MODULE_REL} not yet landed (W4) — the "
                f"§5.2 physics is proven on the reference substrate today; "
                f"retire per this docstring when the module lands")
        raise AssertionError(
            "the surface LANDED: this vacuity arm must be retired and "
            "replaced with the live bindings named in this docstring")

    def test_restore_cli_absent_companion(self):
        """COMPANION absence assertion: REDs the moment the restore CLI
        lands, forcing the retirement of the vacuity arm below."""
        assert not (_REPO / FIX.RESTORE_CLI_REL).exists(), (
            f"{FIX.RESTORE_CLI_REL} LANDED — retire the restore-CLI vacuity "
            f"arm: bind the sim 10 seal/restore drill to the real CLI per "
            f"its docstring RETIREMENT CONDITION.")

    def test_restore_cli_vacuity(self):
        """VACUITY SKIP — RETIREMENT CONDITION: retire when
        cabinet/scripts/cog5-archive-restore.py lands (W4). Replace this body
        with the live drill: invoke the CLI as a subprocess to seal + copy
        out + restore a populated archive, and assert the SAME
        `archive_report` equality the reference drill asserts above (every
        chain head, the row count, the ordered lineage) — plus that the
        source root still exists afterwards (§16 `retained_sealed`, never a
        cache-delete).
        """
        if not (_REPO / FIX.RESTORE_CLI_REL).exists():
            pytest.skip(
                f"vacuity: {FIX.RESTORE_CLI_REL} not yet landed (W4) — the "
                f"rehearsed RESTORE is proven on the reference substrate "
                f"today; retire per this docstring when the CLI lands")
        raise AssertionError(
            "the surface LANDED: this vacuity arm must be retired and "
            "replaced with the live bindings named in this docstring")
