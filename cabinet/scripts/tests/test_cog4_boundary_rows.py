"""COG-4 W1 (C2) — the per-row boundary-manifest mutant harness (contract §8.2).

EVERY row of cabinet/config/boundary-manifest.yml ships with its bite proven:
each test here GENERATES its negative-control mutant FROM the row itself —
a scratch tmp tree + a forbidden import (or store mention) written into a fake
importer file — and asserts the engine (cabinet/scripts/cog2-import-gate.py)
REDs with exactly that row's declared rule id. Nothing is hardcoded per rule:
add a future row to the yml and this harness proves its bite on the same
commit, with zero new test code (§8.2 "every future row ships with its bite
proven").

WORKS BEFORE THE TARGET TREES EXIST (the §8.3 property, documented here): the
COG-4 rows fence framework/scheduler, framework/organs, framework/projection
and the schedule store — none of which exists on the committed tree yet. The
mutants below CREATE the offending files in scratch trees, so every row's bite
is proven now, while the committed repo stays green-by-vacuity. Deliberately,
NOTHING here asserts those trees are absent from the live repo — landing them
later (W3/W4) cannot invalidate this harness.

Also pinned: the nine §8.1 legacy rule ids all survive the conversion verbatim;
the committed tree scans clean (the byte-compat anchor); the §8.3 DELIBERATE
ABSENCES bite (cog4-organ-runner.py off the scheduler + schedule-store
allowlists; cog3-ovi-parity.py off the objectives allowlist); cog4-parity.py is
the ONE sanctioned organs importer among the cabinet CLIs while staying OFF the
scheduler allowlist; and the loader FAIL-CLOSES on manifest defects (unknown
keys, wrong rule-id coverage, duplicate ids, a contradicted absence).

No test here is a vacuity guard (nothing asserts a mere absence that a later
wave would legitimately fill) — every assertion exercises the engine on inputs
generated in this run, so nothing needs a retirement condition.

Data-plane tokens are ALWAYS taken from row data at runtime and never written
as contiguous literals in this source (the assembled-token discipline — this
file is swept by the objectives-store row, whose allowlist does not carry
test_cog4_* globs).

S0: interpreter python3.12. No DB — a pure text/AST scan over scratch trees.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-4 contract §8).
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# hyphenated filename -> importlib (the cog2 CLI-under-test idiom)
_GATE = Path(__file__).resolve().parents[1] / "cog2-import-gate.py"
_REPO = Path(__file__).resolve().parents[3]

_spec = _ilu.spec_from_file_location("cog2_import_gate_cog4", _GATE)
gate = _ilu.module_from_spec(_spec)
sys.modules["cog2_import_gate_cog4"] = gate
_spec.loader.exec_module(gate)

CONFIG = gate.load_config()
ROWS = list(CONFIG.rows)
MODULE_ROWS = [r for r in ROWS if r.kind == gate.MODULE_KIND]
DATA_ROWS = [r for r in ROWS if r.kind == gate.DATA_PLANE_KIND]
FORBIDDEN_ROWS = [r for r in MODULE_ROWS if r.forbidden_importers]
SWEEP_ROWS = [r for r in MODULE_ROWS if r.sweep]
REVERSE_ROWS = [r for r in MODULE_ROWS if r.reverse_forbidden]
FALSIFIER_ROWS = [r for r in MODULE_ROWS if r.falsifier_exact]
ABSENT_ROWS = [r for r in ROWS if r.deliberately_absent]

_IDS = [r.token for r in ROWS]


def _row_param(rows):
    return pytest.mark.parametrize(
        "row", rows, ids=[r.token for r in rows])


# a swept location that is (asserted below) in NO row's allowlists — the
# generic stray-importer home for generated sweep mutants.
_STRAY = "shared/_cog4_generated_leak.py"


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
# manifest content pins — the conversion's preserved ids + the §8.3 rows
# ===========================================================================

class TestManifestContent:
    def test_all_nine_legacy_rule_ids_preserved_verbatim(self):
        # §8.2 byte-compat clause: every §8.1 rule id survives the conversion.
        declared = {rid for r in ROWS for rid in r.rule_ids.values()}
        nine = {
            "FORBIDDEN_IMPORTS_CORTEX",
            "FORBIDDEN_CORTEX_TOKEN",
            "FALSIFIER_IMPORTS_CORTEX",
            "UNALLOWLISTED_CORTEX_IMPORTER",
            "FORBIDDEN_IMPORTS_OBJECTIVES",
            "FORBIDDEN_OBJECTIVES_TOKEN",
            "FORBIDDEN_OBJECTIVES_IMPORTS_ACTION",
            "UNALLOWLISTED_OBJECTIVES_IMPORTER",
            "FORBIDDEN_OBJECTIVES_DATAPLANE",
        }
        missing = nine - declared
        assert missing == set(), f"legacy rule ids lost in conversion: {missing}"

    def test_cog4_module_rows_exist_with_action_plane_forbidden(self):
        # §8.3: the three new tokens are rows whose forbidden_importers is the
        # action plane + the officer runner (same surface as the legacy rows).
        legacy_surface = tuple(
            CONFIG.row_for_token("framework.cortex").forbidden_importers)
        for token in ("framework.scheduler", "framework.organs",
                      "framework.projection"):
            row = CONFIG.row_for_token(token)
            assert row.kind == gate.MODULE_KIND
            assert tuple(row.forbidden_importers) == legacy_surface, token
            assert row.sweep is True, token

    def test_scheduler_and_organs_reverse_rows_fence_the_full_set(self):
        # §8.3: reverse_forbidden = action plane + fidelity/missions/ovi/
        # learning/evolution, for BOTH the scheduler and organs rows.
        expected = (
            "framework/frontdoor", "framework/acting", "framework/authority",
            "framework/fidelity", "framework/missions", "framework/ovi",
            "framework/learning", "framework/evolution",
        )
        for token in ("framework.scheduler", "framework.organs"):
            row = CONFIG.row_for_token(token)
            assert tuple(row.reverse_forbidden) == expected, token

    def test_schedule_store_data_plane_row_exists(self):
        # §8.3: the schedule store is a data_plane row owned by the scheduler
        # tree. Selected structurally — its token never appears in this file.
        rows = [r for r in DATA_ROWS
                if r.internal_prefix == "framework/scheduler/"]
        assert len(rows) == 1
        assert rows[0].rule_ids == {"data_plane": "FORBIDDEN_SCHEDULER_DATAPLANE"}

    def test_parity_cli_is_the_one_sanctioned_organs_importer_not_a_scheduler_one(self):
        # §8.3: cog4-parity.py is explicitly allowlisted on the organs row (the
        # ONE sanctioned dual-plane importer) and is NOT a scheduler reader.
        parity = "cabinet/scripts/cog4-parity.py"
        organs = CONFIG.row_for_token("framework.organs")
        sched = CONFIG.row_for_token("framework.scheduler")
        assert parity in organs.allowlist_exact
        assert parity not in sched.allowlist_exact
        assert not sched.is_allowlisted(parity)

    def test_deliberate_absences_are_declared_where_the_contract_pins_them(self):
        # §8.3: the organ-runner is deliberately absent from the scheduler
        # module row AND the schedule-store row; the OVI parity falsifier from
        # the objectives row (the cog2-import-gate:265-268 idiom, now a field).
        runner = "cabinet/scripts/cog4-organ-runner.py"
        sched = CONFIG.row_for_token("framework.scheduler")
        store = [r for r in DATA_ROWS
                 if r.internal_prefix == "framework/scheduler/"][0]
        objectives = CONFIG.row_for_token("framework.objectives")
        assert runner in sched.deliberately_absent
        assert runner in store.deliberately_absent
        assert "cabinet/scripts/cog3-ovi-parity.py" in objectives.deliberately_absent
        # ...and the runner IS a sanctioned ORGANS reader (§9.5: it loads
        # registry + descriptor, staying scheduler-blind).
        organs = CONFIG.row_for_token("framework.organs")
        assert runner in organs.allowlist_exact

    def test_stray_home_is_unallowlisted_everywhere(self):
        # the generated sweep mutants live at a location no row curates — if a
        # future row allowlists shared/, this harness must be rethought, loudly.
        for row in ROWS:
            assert not row.is_allowlisted(_STRAY), row.token
            assert not row.is_internal(_STRAY), row.token

    def test_committed_tree_is_clean_under_the_full_manifest(self):
        # THE byte-compat anchor (§8.2): engine-over-repo output is empty —
        # identical to the pre-conversion gate — with all seven rows loaded.
        assert gate.scan(_REPO) == []


# ===========================================================================
# generated mutants — check 1 (forbidden surface), from the row itself
# ===========================================================================

class TestForbiddenSurfaceMutants:
    @_row_param(FORBIDDEN_ROWS)
    def test_every_forbidden_importer_entry_bites_on_ast_import(self, tmp_path, row):
        # one generated mutant per forbidden_importers entry: a tree entry
        # hosts a generated file; a file entry IS the mutant file.
        rels = []
        for entry in row.forbidden_importers:
            rel = entry if entry.endswith(".py") \
                else f"{entry}/_cog4_generated_mutant.py"
            _write(tmp_path, rel, f"import os\nimport {row.token}\n")
            rels.append(rel)
        viol = gate.scan(tmp_path)
        hit = _paths_for(viol, row.rule_ids["forbidden_import"])
        for rel in rels:
            assert rel in hit, (row.token, rel, viol)

    @_row_param(FORBIDDEN_ROWS)
    def test_token_backstop_bites_without_any_import(self, tmp_path, row):
        # the C-F20 shape, generated: a live STRING naming the token's pathed
        # spelling — AST-invisible, backstop-visible. Assembled at runtime from
        # the row token; this source carries no token literal.
        parent, name = row.token.rsplit(".", 1)
        rel = f"{row.forbidden_importers[0]}/_cog4_generated_token.py"
        _write(tmp_path, rel, f'X = "{parent.replace(".", "/")}/{name}"\n')
        viol = gate.scan(tmp_path)
        rules = _rules_for(viol, rel)
        assert row.rule_ids["forbidden_token"] in rules, (row.token, viol)
        assert row.rule_ids["forbidden_import"] not in rules  # AST correctly silent

    @_row_param(FORBIDDEN_ROWS)
    def test_comment_mention_folds_clean(self, tmp_path, row):
        # anti-over-fencing control, generated per row.
        rel = f"{row.forbidden_importers[0]}/_cog4_generated_note.py"
        _write(tmp_path, rel,
               f"# never import {row.token} from here\nimport os  # noqa\n")
        assert gate.scan(tmp_path) == [], row.token


# ===========================================================================
# generated mutants — check 2 (falsifier total ban)
# ===========================================================================

class TestFalsifierMutants:
    @_row_param(FALSIFIER_ROWS)
    def test_falsifier_import_bites_however_spelled(self, tmp_path, row):
        parent, name = row.token.rsplit(".", 1)
        bodies = [
            f"import {row.token}\n",
            f"from {row.token} import x\n",
            f"from {parent} import {name}\n",
            f"import importlib\nm = importlib.import_module('{row.token}.q')\n",
            f"import importlib\nm = importlib.import_module('.{name}', '{parent}')\n",
        ]
        for fal in row.falsifier_exact:
            for body in bodies:
                # each write overwrites the same path — one spelling at a time
                _write(tmp_path, fal, '"""falsifier."""\n' + body)
                viol = gate.scan(tmp_path)
                assert fal in _paths_for(viol, row.rule_ids["falsifier"]), \
                    (row.token, fal, body, viol)

    @_row_param(FALSIFIER_ROWS)
    def test_falsifier_token_as_data_folds_clean(self, tmp_path, row):
        # the falsifier legitimately carries the token WORD as data — narrow
        # matching must not over-fence it.
        name = row.token.rsplit(".", 1)[1]
        for fal in row.falsifier_exact:
            _write(tmp_path, fal,
                   f'"""{name} parity falsifier."""\nimport json\n'
                   f'def _from_cmd():\n    return {{"{name}": {{}}}}\n')
        assert gate.scan(tmp_path) == [], row.token


# ===========================================================================
# generated mutants — check R (reverse direction), from the row itself
# ===========================================================================

class TestReverseMutants:
    @_row_param(REVERSE_ROWS)
    def test_every_reverse_forbidden_tree_bites(self, tmp_path, row):
        # one generated internal-tree file per reverse-forbidden tree; a single
        # scan must flag them all with the row's reverse rule id.
        rels = []
        for i, tree in enumerate(row.reverse_forbidden):
            dotted = tree.replace("/", ".")
            rel = f"{row.internal_prefix}_cog4_generated_rev_{i}.py"
            _write(tmp_path, rel, f"import os\nimport {dotted}\n")
            rels.append(rel)
        viol = gate.scan(tmp_path)
        hit = _paths_for(viol, row.rule_ids["reverse"])
        for rel in rels:
            assert rel in hit, (row.token, rel, viol)

    @_row_param(REVERSE_ROWS)
    def test_dynamic_reverse_reach_bites(self, tmp_path, row):
        # the AST-blind import_module spelling of the same escape.
        dotted = row.reverse_forbidden[0].replace("/", ".")
        rel = f"{row.internal_prefix}_cog4_generated_rev_dyn.py"
        _write(tmp_path, rel,
               f"import importlib\nm = importlib.import_module('{dotted}.x')\n")
        assert rel in _paths_for(gate.scan(tmp_path),
                                 row.rule_ids["reverse"]), row.token

    @_row_param(REVERSE_ROWS)
    def test_internal_self_import_is_not_reverse_flagged(self, tmp_path, row):
        # anti-over-fencing: the tree importing ITSELF (or stdlib) is clean.
        rel = f"{row.internal_prefix}_cog4_generated_ok.py"
        _write(tmp_path, rel, f"import json\nimport {row.token}\n")
        assert gate.scan(tmp_path) == [], row.token


# ===========================================================================
# generated mutants — check 3 (un-curated importer sweep)
# ===========================================================================

class TestSweepMutants:
    @_row_param(SWEEP_ROWS)
    def test_stray_static_import_bites(self, tmp_path, row):
        _write(tmp_path, _STRAY, f"import {row.token}\n")
        assert _STRAY in _paths_for(gate.scan(tmp_path),
                                    row.rule_ids["unallowlisted"]), row.token

    @_row_param(SWEEP_ROWS)
    def test_stray_dynamic_import_bites(self, tmp_path, row):
        _write(tmp_path, _STRAY,
               f"import importlib\nm = importlib.import_module('{row.token}.x')\n")
        assert _STRAY in _paths_for(gate.scan(tmp_path),
                                    row.rule_ids["unallowlisted"]), row.token

    @_row_param(SWEEP_ROWS)
    def test_first_curated_reader_folds_clean(self, tmp_path, row):
        # positive control, generated from the row's own allowlist: its first
        # curated exact reader imports the token and the tree stays clean.
        reader = sorted(row.allowlist_exact)[0]
        _write(tmp_path, reader, f"import {row.token}\n")
        assert gate.scan(tmp_path) == [], (row.token, reader)

    @_row_param(SWEEP_ROWS)
    def test_internal_tree_folds_clean(self, tmp_path, row):
        rel = f"{row.internal_prefix}_cog4_generated_internal.py"
        _write(tmp_path, rel, f"import {row.token}\n")
        assert gate.scan(tmp_path) == [], row.token

    @_row_param(SWEEP_ROWS)
    def test_bare_token_word_is_not_overfenced_in_sweep(self, tmp_path, row):
        # narrowness: the token's last name as prose/data (no import statement,
        # no import_module call) must not trip the sweep.
        name = row.token.rsplit(".", 1)[1]
        _write(tmp_path, _STRAY,
               f"CFG = {{'{name}': 'read elsewhere'}}\ndef run():\n    return CFG\n")
        assert gate.scan(tmp_path) == [], row.token


# ===========================================================================
# generated mutants — check D (data-plane store sweep)
# ===========================================================================

class TestDataPlaneMutants:
    @_row_param(DATA_ROWS)
    def test_live_store_mention_bites(self, tmp_path, row):
        # token taken from the ROW at runtime — never a literal here.
        _write(tmp_path, _STRAY, f"P = '{row.token}/x.jsonl'\n")
        viol = gate.scan(tmp_path)
        rules = _rules_for(viol, _STRAY)
        assert row.rule_ids["data_plane"] in rules, (row.token, viol)

    @_row_param(DATA_ROWS)
    def test_comment_mention_of_store_folds_clean(self, tmp_path, row):
        _write(tmp_path, _STRAY, f"# never touch {row.token} from here\nX = 1\n")
        assert gate.scan(tmp_path) == [], row.token

    @_row_param(DATA_ROWS)
    def test_curated_reader_and_internal_tree_fold_clean(self, tmp_path, row):
        reader = sorted(row.allowlist_exact)[0]
        _write(tmp_path, reader, f"P = '{row.token}/x.jsonl'\n")
        _write(tmp_path, f"{row.internal_prefix}_cog4_generated_store.py",
               f"P = '{row.token}'\n")
        assert gate.scan(tmp_path) == [], row.token


# ===========================================================================
# DELIBERATE ABSENCE — the §8.3 protections, generated from the rows
# ===========================================================================

class TestDeliberateAbsence:
    @_row_param(ABSENT_ROWS)
    def test_absent_files_are_off_every_allow_surface(self, row):
        for path in row.deliberately_absent:
            assert path not in row.allowlist_exact, (row.token, path)
            assert not row.is_allowlisted(path), (row.token, path)
            assert not row.is_internal(path), (row.token, path)

    @_row_param(ABSENT_ROWS)
    def test_each_deliberate_absence_bites(self, tmp_path, row):
        # a reach FROM the deliberately-absent file REDs as un-curated: import
        # for module rows, a live store mention for data_plane rows.
        for path in row.deliberately_absent:
            if row.kind == gate.MODULE_KIND:
                _write(tmp_path, path, f"import {row.token}\n")
                rule = row.rule_ids["unallowlisted"]
            else:
                _write(tmp_path, path, f"P = '{row.token}/x.jsonl'\n")
                rule = row.rule_ids["data_plane"]
            viol = gate.scan(tmp_path)
            assert path in _paths_for(viol, rule), (row.token, path, viol)
            (tmp_path / path).unlink()
            assert gate.scan(tmp_path) == []   # prove-then-remove


# ===========================================================================
# loader FAIL-CLOSED — a manifest defect can never silently drop protection
# ===========================================================================

def _mutated_manifest(tmp_path: Path, mutate) -> Path:
    doc = yaml.safe_load(gate.MANIFEST_PATH.read_text(encoding="utf-8"))
    mutate(doc)
    out = tmp_path / "boundary-manifest.yml"
    out.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return out


class TestLoaderFailClosed:
    def test_real_manifest_loads_and_matches_engine_config(self):
        cfg = gate.load_config(gate.MANIFEST_PATH)
        assert [r.token for r in cfg.rows] == [r.token for r in ROWS]

    def test_unknown_row_key_is_fatal(self, tmp_path):
        p = _mutated_manifest(
            tmp_path, lambda d: d["rows"][0].__setitem__("allowlist_exat", []))
        with pytest.raises(gate.ManifestError):
            gate.load_config(p)

    def test_missing_required_rule_id_is_fatal(self, tmp_path):
        def drop_unallowlisted(d):
            del d["rows"][0]["rule_ids"]["unallowlisted"]
        with pytest.raises(gate.ManifestError):
            gate.load_config(_mutated_manifest(tmp_path, drop_unallowlisted))

    def test_orphan_rule_id_is_fatal(self, tmp_path):
        def add_orphan(d):
            d["rows"][0]["rule_ids"]["reverse"] = "ORPHAN_RULE"
        # row 0 (cortex) declares no reverse_forbidden -> the id is an orphan.
        with pytest.raises(gate.ManifestError):
            gate.load_config(_mutated_manifest(tmp_path, add_orphan))

    def test_duplicate_rule_id_across_rows_is_fatal(self, tmp_path):
        def dup(d):
            d["rows"][1]["rule_ids"]["forbidden_import"] = \
                d["rows"][0]["rule_ids"]["forbidden_import"]
        with pytest.raises(gate.ManifestError):
            gate.load_config(_mutated_manifest(tmp_path, dup))

    def test_contradicted_deliberate_absence_is_fatal(self, tmp_path):
        def contradict(d):
            for row in d["rows"]:
                if row.get("deliberately_absent"):
                    row["allowlist_exact"] = (list(row.get("allowlist_exact") or [])
                                              + [row["deliberately_absent"][0]])
                    return
        with pytest.raises(gate.ManifestError):
            gate.load_config(_mutated_manifest(tmp_path, contradict))

    def test_data_plane_row_with_module_only_keys_is_fatal(self, tmp_path):
        def pollute(d):
            row = next(r for r in d["rows"] if r["kind"] == "data_plane")
            row["forbidden_importers"] = ["framework/frontdoor"]
        with pytest.raises(gate.ManifestError):
            gate.load_config(_mutated_manifest(tmp_path, pollute))


# ===========================================================================
# CLI — a generated new-row breach exits 1 and names the rule id
# ===========================================================================

class TestCLI:
    def test_generated_scheduler_breach_exits_one_via_cli(self, tmp_path):
        row = CONFIG.row_for_token("framework.scheduler")
        _write(tmp_path, _STRAY, f"import {row.token}\n")
        r = subprocess.run(
            [sys.executable, str(_GATE), "--root", str(tmp_path)],
            capture_output=True, text=True)
        assert r.returncode == 1
        assert row.rule_ids["unallowlisted"] in (r.stdout + r.stderr)

    def test_json_mode_lists_generated_breach(self, tmp_path):
        row = CONFIG.row_for_token("framework.organs")
        _write(tmp_path, _STRAY, f"import {row.token}\n")
        r = subprocess.run(
            [sys.executable, str(_GATE), "--root", str(tmp_path), "--json"],
            capture_output=True, text=True)
        payload = json.loads(r.stdout)
        assert payload["count"] == len(payload["violations"]) >= 1
        assert any(v.endswith(row.rule_ids["unallowlisted"])
                   for v in payload["violations"])
