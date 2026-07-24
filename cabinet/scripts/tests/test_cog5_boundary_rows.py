"""COG-5 W1 (§10) — the Evolutionary-Foundry boundary rows: COG-5-specific
content pins + per-row biting mutants (the SPECIFIC rule ids, belt-and-braces
beyond the generic test_cog4_boundary_rows.py harness) + the §10 projection-
store denies / deliberate ROW-6 non-extension proofs.

The three rows this pins (all appended AFTER ROW 7; ROW 6 :316-345 byte-
untouched):
  ROW 8  framework.evolution.holdout_gen (module, sweep) — league-invisible:
         importable by the oracle CLI + its own tests ONLY; league/generator/
         arena/candidate/scorers/bench_factory structurally BLIND (§7.2/§7.3).
  ROW 9  shared/interfaces/foundry/archive (data_plane) — the immutable archive
         store: written by archive.py/emitter + cog5-archive-restore + appended
         by cog5-league only; candidate/generator/arena DELIBERATELY ABSENT (no
         candidate write path, the §5.2 WALL made static). Also delivers the
         projections-cannot-read-the-archive half of §10's projection deny.
  ROW 10 framework.evolution (module, reverse) — the shadow lab may never import
         framework.frontdoor / framework.acting (no alternate promotion/apply
         path, §3 L48). authority is DELIBERATELY OUT of reverse_forbidden — the
         package legitimately reads authority's read-only vocab/policy constants
         (ACTION_TYPES/RISK_CLASSES; test_contracts.py:16-17), a symbol-level
         joint governed by a sibling AST pin, never a row (§10, rev-1 SF-4).

The generic harness (test_cog4_boundary_rows.py) already GENERATES a biting
mutant per row from the row data; this file adds the COG-5 STRUCTURE pins (the
rows exist with the right tokens/allowlists/absences/rule ids) + the §10 denies
that are delivered by existing rows + ROW 9 (not by new rows) and so are proven
here by assertion, not auto-generated.

Data-plane tokens are ALWAYS taken from row data at runtime and never written as
contiguous literals in this swept source (the assembled-token discipline — this
file IS allowlisted on ROW 9 via the test_cog5_* glob, but the discipline is
kept so the file never self-flags on the objectives/scheduler store rows, whose
allowlists carry test_cog3_*/test_cog4_* globs, not test_cog5_*). Module tokens
are safe as string literals: a bare dotted string trips no sweep (only a real
import or import_module call does).

S0: interpreter python3.12. No DB — a pure text/AST scan over scratch trees.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-5 contract §10).
"""
from __future__ import annotations

import importlib.util as _ilu
import sys
from pathlib import Path

# hyphenated filename -> importlib (the cog2 CLI-under-test idiom)
_GATE = Path(__file__).resolve().parents[1] / "cog2-import-gate.py"
_REPO = Path(__file__).resolve().parents[3]

_spec = _ilu.spec_from_file_location("cog2_import_gate_cog5", _GATE)
gate = _ilu.module_from_spec(_spec)
sys.modules["cog2_import_gate_cog5"] = gate
_spec.loader.exec_module(gate)

CONFIG = gate.load_config()

# module tokens are safe as string literals (no sweep trips on a bare dotted
# string); the archive DATA-PLANE token is read from the row at runtime.
HOLDOUT_TOKEN = "framework.evolution.holdout_gen"
EVOLUTION_TOKEN = "framework.evolution"
PROJECTION_TOKEN = "framework.projection"

# the evolution siblings that MUST be blind to holdout_gen (§7.3) and have no
# archive write path (§5.2) — named as future modules, none exists yet.
_BLIND_SIBLINGS = ("league", "generator", "arena", "candidate", "scorers",
                   "bench_factory")


def _holdout_row():
    return CONFIG.row_for_token(HOLDOUT_TOKEN)


def _evolution_row():
    return CONFIG.row_for_token(EVOLUTION_TOKEN)


def _archive_row():
    # structural selection — the archive store is the data_plane row owned by the
    # archive namespace tree; its token is read from the row, never a literal.
    rows = [r for r in CONFIG.data_plane_rows()
            if r.internal_prefix == "framework/evolution/archive/"]
    assert len(rows) == 1, "exactly one archive data-plane row expected"
    return rows[0]


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _paths_for(violations, rule: str) -> set[str]:
    return {v.rsplit(":", 1)[0] for v in violations if v.rsplit(":", 1)[1] == rule}


def _rules_for(violations, path: str) -> set[str]:
    return {v.rsplit(":", 1)[1] for v in violations if v.rsplit(":", 1)[0] == path}


# ===========================================================================
# ROW 8 — the frozen holdout generator (league-invisible)
# ===========================================================================
class TestHoldoutRow:
    def test_row_shape(self):
        row = _holdout_row()
        assert row.kind == gate.MODULE_KIND
        assert row.sweep is True
        assert row.rule_ids == {"unallowlisted": "UNALLOWLISTED_HOLDOUT_GEN_IMPORTER"}
        # the ONLY sanctioned exact reader is the oracle CLI (§7.2).
        assert set(row.allowlist_exact) == {"cabinet/scripts/cog5-holdout-oracle.py"}
        # its own tests are the only glob reader (§7.3).
        assert "cabinet/scripts/tests/test_cog5_holdout_*.py" in row.allowlist_globs
        # symbol law points at the sibling AST pin (documentation-only).
        assert row.symbol_pin == "cabinet/scripts/tests/test_cog5_holdout_ast_pin.py"

    def test_blind_siblings_are_not_allowlisted(self):
        # league/generator/arena/candidate/scorers/bench_factory are structurally
        # blind — none is a curated reader, so any import from them REDs (§7.3).
        row = _holdout_row()
        for name in _BLIND_SIBLINGS:
            rel = f"framework/evolution/{name}.py"
            assert not row.is_allowlisted(rel), name
            # the narrow internal_prefix keeps them NON-internal (a
            # framework/evolution/ prefix would silently blind them).
            assert not row.is_internal(rel), name

    def test_blind_sibling_import_bites(self, tmp_path):
        # the SPECIFIC rule id, one sibling at a time (belt-and-braces).
        row = _holdout_row()
        for name in _BLIND_SIBLINGS:
            rel = f"framework/evolution/{name}.py"
            _write(tmp_path, rel, f"import {HOLDOUT_TOKEN}\n")
            viol = gate.scan(tmp_path)
            assert rel in _paths_for(viol, row.rule_ids["unallowlisted"]), (name, viol)
            (tmp_path / rel).unlink()
            assert gate.scan(tmp_path) == []

    def test_alias_spelling_bites(self, tmp_path):
        # `from framework.evolution import holdout_gen` names the token via the
        # imported NAME (the alias spelling) — the sweep sees it too.
        row = _holdout_row()
        rel = "framework/evolution/league.py"
        _write(tmp_path, rel, "from framework.evolution import holdout_gen\n")
        assert rel in _paths_for(gate.scan(tmp_path), row.rule_ids["unallowlisted"])

    def test_oracle_reader_folds_clean(self, tmp_path):
        # the positive control: the ONE sanctioned reader imports it — clean.
        _write(tmp_path, "cabinet/scripts/cog5-holdout-oracle.py",
               f"import {HOLDOUT_TOKEN}\n")
        assert gate.scan(tmp_path) == []


# ===========================================================================
# ROW 9 — the immutable trajectory archive store (data plane)
# ===========================================================================
class TestArchiveRow:
    def test_row_shape(self):
        row = _archive_row()
        assert row.kind == gate.DATA_PLANE_KIND
        assert row.sweep is True
        assert row.internal_prefix == "framework/evolution/archive/"
        assert row.rule_ids == {"data_plane": "FORBIDDEN_ARCHIVE_DATAPLANE"}
        # the sole in-package writer + its optional split + the restore/league
        # CLIs (§5.2/§8.3) — an EXACT allowlist (archive.py is NOT internal under
        # the narrow prefix, so it must be curated explicitly).
        assert set(row.allowlist_exact) == {
            "framework/evolution/archive.py",
            "framework/evolution/emitter.py",
            "cabinet/scripts/cog5-archive-restore.py",
            "cabinet/scripts/cog5-league.py",
        }

    def test_candidate_generator_arena_are_deliberately_absent(self):
        row = _archive_row()
        for name in ("candidate", "generator", "arena"):
            rel = f"framework/evolution/{name}.py"
            assert rel in row.deliberately_absent, name
            assert not row.is_allowlisted(rel), name
            assert not row.is_internal(rel), name

    def test_absent_writer_bites(self, tmp_path):
        # the SPECIFIC data-plane rule id: a store mention from candidate/
        # generator/arena REDs (no candidate write path — §5.2 WALL made static).
        row = _archive_row()
        token = row.token   # from row data — never a literal in this source
        for name in ("candidate", "generator", "arena"):
            rel = f"framework/evolution/{name}.py"
            _write(tmp_path, rel, f"P = '{token}/seg-0001.jsonl'\n")
            viol = gate.scan(tmp_path)
            assert rel in _paths_for(viol, row.rule_ids["data_plane"]), (name, viol)
            (tmp_path / rel).unlink()
            assert gate.scan(tmp_path) == []

    def test_archive_writer_folds_clean(self, tmp_path):
        # the positive control: the sole in-package writer names the store — clean.
        row = _archive_row()
        _write(tmp_path, "framework/evolution/archive.py",
               f"STORE = '{row.token}'\n")
        assert gate.scan(tmp_path) == []

    def test_league_appends_clean_but_a_bare_sibling_does_not(self, tmp_path):
        # cog5-league is allowlisted (appends via the emitter); a NON-allowlisted
        # sibling naming the store REDs — the discriminator is curation, not tree.
        row = _archive_row()
        _write(tmp_path, "cabinet/scripts/cog5-league.py", f"S = '{row.token}'\n")
        assert gate.scan(tmp_path) == []
        _write(tmp_path, "framework/evolution/scorers.py", f"S = '{row.token}'\n")
        assert "framework/evolution/scorers.py" in _paths_for(
            gate.scan(tmp_path), row.rule_ids["data_plane"])


# ===========================================================================
# ROW 10 — the evolution package reverse boundary
# ===========================================================================
class TestEvolutionReverseRow:
    def test_row_shape(self):
        row = _evolution_row()
        assert row.kind == gate.MODULE_KIND
        assert row.sweep is False          # reverse-only: no forward sweep
        assert row.internal_prefix == "framework/evolution/"
        assert row.rule_ids == {"reverse": "FORBIDDEN_EVOLUTION_IMPORTS_ACTION"}
        # the two live-execution action lanes — and NOTHING else. authority /
        # learning / fidelity are DELIBERATELY out (legitimate read joints, §10).
        assert tuple(row.reverse_forbidden) == ("framework/frontdoor",
                                                "framework/acting")

    def test_frontdoor_and_acting_imports_bite(self, tmp_path):
        row = _evolution_row()
        for tree in ("framework.frontdoor", "framework.acting"):
            rel = "framework/evolution/generator.py"
            _write(tmp_path, rel, f"import {tree}\n")
            assert rel in _paths_for(gate.scan(tmp_path), row.rule_ids["reverse"]), tree
            (tmp_path / rel).unlink()

    def test_authority_read_is_the_carve_out_not_reverse_flagged(self, tmp_path):
        # the CARVE-OUT (§10, never a row): the evolution package legitimately
        # reads authority's read-only constants — exactly what the committed
        # framework/evolution/tests/test_contracts.py:16-17 does — so importing
        # framework.authority.{classifier,matrix} must NOT be reverse-flagged.
        # (The symbol-level narrowing of that read is a sibling AST pin, not this
        # module-granular row.)
        _write(tmp_path, "framework/evolution/scorers.py",
               "from framework.authority.classifier import ACTION_TYPES\n"
               "from framework.authority.matrix import RISK_CLASSES\n")
        viol = gate.scan(tmp_path)
        assert "FORBIDDEN_EVOLUTION_IMPORTS_ACTION" not in _rules_for(
            viol, "framework/evolution/scorers.py"), viol

    def test_learning_and_fidelity_reads_are_not_reverse_flagged(self, tmp_path):
        # touches_ring0 (framework.learning, §8.2) + the graduation/scorer read
        # surface (framework.fidelity, §3) are legitimate evolution reads.
        _write(tmp_path, "framework/evolution/generator.py",
               "from framework.learning.gate import touches_ring0\n"
               "from framework.fidelity.graduation import evaluate\n")
        viol = gate.scan(tmp_path)
        assert "FORBIDDEN_EVOLUTION_IMPORTS_ACTION" not in _rules_for(
            viol, "framework/evolution/generator.py"), viol

    def test_self_import_is_not_reverse_flagged(self, tmp_path):
        _write(tmp_path, "framework/evolution/candidate.py",
               f"import {EVOLUTION_TOKEN}.archive\n")
        assert gate.scan(tmp_path) == []


# ===========================================================================
# §10 projection-store denies + the deliberate ROW-6 non-extension
# (delivered by existing rows + ROW 9; proven here by assertion)
# ===========================================================================
class TestProjectionDeniesAndRow6NonExtension:
    def test_row6_projection_allowlists_no_evolution_importer(self):
        # the deliberate ROW-6 non-extension (rev-1 SF-4): NO framework/evolution
        # importer is allowlisted onto the kernel row — so evolution can never
        # import framework.projection through a curated seam. ROW 6 stays
        # byte-untouched; this asserts the property, not the bytes.
        row = CONFIG.row_for_token(PROJECTION_TOKEN)
        for entry in row.allowlist_exact:
            assert not entry.startswith("cabinet/scripts/cog5-"), entry
        for g in row.allowlist_globs:
            assert "evolution" not in g, g
        assert not any(g.startswith("framework/evolution") for g in row.allowlist_globs)

    def test_evolution_importing_projection_reds_via_row6(self, tmp_path):
        # the non-extension BITES: an evolution import of the C3 kernel REDs as
        # UNALLOWLISTED_PROJECTION_IMPORTER (ROW 6's own sweep; the replica path
        # is the phase's pick, §5.1/§5.2).
        row = CONFIG.row_for_token(PROJECTION_TOKEN)
        rel = "framework/evolution/archive.py"
        _write(tmp_path, rel, f"import {PROJECTION_TOKEN}.kernel\n")
        assert rel in _paths_for(gate.scan(tmp_path), row.rule_ids["unallowlisted"])

    def test_evolution_reading_the_projection_shadow_models_reds(self, tmp_path):
        # observation-only both directions (§10): evolution reading the
        # cortex/objectives/scheduler shadow models REDs as unallowlisted on each
        # of those existing rows (evolution is on none of their allowlists).
        for token in ("framework.cortex", "framework.objectives",
                      "framework.scheduler"):
            row = CONFIG.row_for_token(token)
            rel = "framework/evolution/scorers.py"
            _write(tmp_path, rel, f"import {token}\n")
            assert rel in _paths_for(gate.scan(tmp_path),
                                     row.rule_ids["unallowlisted"]), token
            (tmp_path / rel).unlink()

    def test_projection_reader_cannot_read_the_archive_store(self, tmp_path):
        # the other direction of §10's deny (delivered by ROW 9): a projection
        # reader (cortex/objectives/scheduler) mentioning the archive store REDs
        # as FORBIDDEN_ARCHIVE_DATAPLANE — the archive is excluded from every
        # projection (§5.2).
        arow = _archive_row()
        token = arow.token
        for tree in ("framework/cortex", "framework/objectives",
                     "framework/scheduler"):
            rel = f"{tree}/reader.py"
            _write(tmp_path, rel, f"P = '{token}/seg-0001.jsonl'\n")
            assert rel in _paths_for(gate.scan(tmp_path),
                                     arow.rule_ids["data_plane"]), tree
            (tmp_path / rel).unlink()


# ===========================================================================
# committed-tree anchor — the full manifest (incl. the 3 COG-5 rows) is clean
# ===========================================================================
def test_committed_tree_is_clean_with_the_cog5_rows():
    # green-by-vacuity: the COG-5 target modules do not exist yet, and this
    # unit's own test/lib files (which DO name the archive store token) are
    # allowlisted on ROW 9 via the test_cog5_*/lib_cog5_* globs.
    assert gate.scan(_REPO) == []
