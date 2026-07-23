"""COG-3 OVI per-instrument shadow-parity FALSIFIER tests (C-F17 analog, contract
rev-1 §6.6 P10 / N6, attack C-M4). FILE-SEEDED, no DSN.

Pins cog3-ovi-parity.py's guarantees:
  * GROUND TRUTH = the legacy framework.ovi.compute module (per-instrument
    NORMALIZED components; the composite scalar is DROPPED, never compared);
  * the objectives per-instrument view is obtained as an EXTERNAL subprocess
    black box (the import ban — this file's parity script imports NO
    framework.objectives, enforced at the module level by the §6.5 gate);
  * EXACT per-instrument parity (N6 exact-only, no tolerance): a value mismatch,
    a dropped instrument, or a forbidden composite emission (C-M4) is a
    BREACH/ERROR that exits 1 loudly;
  * seeded instruments both sides -> exact match GREEN; a perturbed view -> RED.

The step-0 import gate (test_cog3_import_gate.py) already pins the module-level
enforcement (a scratch cog3-ovi-parity.py importing framework.objectives REDs as
UNALLOWLISTED_OBJECTIVES_IMPORTER). This suite re-proves that enforcement against
the gate AND confirms the REAL committed script is clean (imports no objectives,
reads no clock) — the "prove it then remove" the wave-4 brief names.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; wave-4 phase-complete.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
_PARITY_REL = "cabinet/scripts/cog3-ovi-parity.py"
_GATE_REL = "cabinet/scripts/cog2-import-gate.py"


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, _REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


parity = _load(_PARITY_REL, "cog3_ovi_parity")


# One raw sample carrying all five legacy instruments (compute_ovi rejects a
# missing component) — the pinned window's aggregated raw values.
_RAW = {
    "task_throughput": 30.0,
    "outcome_progress": 0.6,
    "captain_attention_cost": 4.0,
    "learning_rate": 2.0,
    "verification_pass_rate": 0.85,
}


def _write_view_driver(tmp_path: Path, body: str) -> list[str]:
    """Write a stdin->stdout objectives-view stand-in and return its argv (the
    external-black-box seam COG3_OVI_VIEW_CMD points at)."""
    driver = tmp_path / "view.py"
    driver.write_text(body, encoding="utf-8")
    return [sys.executable, str(driver)]


# ---------------------------------------------------------------------------
# 1. GREEN — the REAL objectives ovi_view agrees per-instrument with the legacy
# ---------------------------------------------------------------------------

def test_real_view_exact_match_is_green():
    # DEFAULT view cmd = a child python3.12 -c importing framework.objectives.ovi_view
    # IN THE CHILD (never this process). The view projects the legacy's per-instrument
    # components; exact per-instrument agreement => ok, exit 0.
    verdict = parity.run(cutoff="2026-07-21T00:00:00Z", window_days=7,
                         sample_data=json.dumps(_RAW))
    assert verdict["status"] == "ok", verdict
    assert not verdict["mismatches"]
    assert set(verdict["instruments"]) == set(_RAW)


def test_ground_truth_is_the_legacy_module_normalized_components():
    # C-F17: ground truth comes from framework.ovi.compute (the INDEPENDENT legacy
    # module), per-instrument NORMALIZED, with NO composite scalar in the compare set.
    gt = parity._legacy_components(_RAW, None)
    assert set(gt) == set(_RAW)                 # per-instrument, all five
    assert "composite_score" not in gt          # the scalar is dropped (never compared)
    for name, value in gt.items():
        assert 0.0 <= value <= 1.0, (name, value)  # normalized 0-1


# ---------------------------------------------------------------------------
# 2. RED — a perturbed / dropped / composite-emitting view
# ---------------------------------------------------------------------------

def test_perturbed_view_is_a_breach(tmp_path):
    # a view that shifts ONE instrument by a hair -> exact compare catches it (N6
    # exact-only, no tolerance) -> breach, exit 1.
    cmd = _write_view_driver(tmp_path,
        "import json, sys\n"
        "inst = json.load(sys.stdin)\n"
        "name = sorted(inst)[0]\n"
        "inst[name] = inst[name] + 1e-9\n"
        "print(json.dumps({k: {'value': v} for k, v in inst.items()}))\n")
    verdict = parity.run(cutoff="2026-07-21T00:00:00Z", window_days=7,
                         sample_data=json.dumps(_RAW), view_cmd=cmd)
    assert verdict["status"] == "breach", verdict
    assert len(verdict["mismatches"]) == 1
    assert verdict["mismatches"][0]["reason"] == "value_mismatch"


def test_dropped_instrument_is_a_breach(tmp_path):
    # a view that OMITS an instrument -> the legacy has it, the view does not ->
    # breach (absent_objectives), never a silent pass.
    cmd = _write_view_driver(tmp_path,
        "import json, sys\n"
        "inst = json.load(sys.stdin)\n"
        "inst.pop(sorted(inst)[0])\n"
        "print(json.dumps({k: {'value': v} for k, v in inst.items()}))\n")
    verdict = parity.run(cutoff="2026-07-21T00:00:00Z", window_days=7,
                         sample_data=json.dumps(_RAW), view_cmd=cmd)
    assert verdict["status"] == "breach", verdict
    assert any(m["reason"] == "absent_objectives" for m in verdict["mismatches"])


def test_composite_emitting_view_is_an_error(tmp_path):
    # THE C-M4 shape: a view growing a composite_score aggregate is a loud ERROR
    # (never a silent green), even if every per-instrument value still matches.
    cmd = _write_view_driver(tmp_path,
        "import json, sys\n"
        "inst = json.load(sys.stdin)\n"
        "out = {k: {'value': v} for k, v in inst.items()}\n"
        "out['composite_score'] = sum(inst.values()) / len(inst)\n"
        "print(json.dumps(out))\n")
    verdict = parity.run(cutoff="2026-07-21T00:00:00Z", window_days=7,
                         sample_data=json.dumps(_RAW), view_cmd=cmd)
    assert verdict["status"] == "error", verdict
    assert "composite" in verdict["note"].lower()


def test_cell_smuggled_aggregate_is_an_error(tmp_path):
    # THE per-cell C-M4 escape: a view keeps every per-instrument "value" matching
    # the legacy but SMUGGLES a numeric aggregate INSIDE each cell under a NON-LISTED
    # key ("rollup") — invisible to the top-level composite-token scan AND to the
    # value extraction (which reads only "value"). The extended scan catches any
    # numeric key beyond the pinned per-instrument field -> loud ERROR, never a
    # silent green even though every "value" still matches.
    cmd = _write_view_driver(tmp_path,
        "import json, sys\n"
        "inst = json.load(sys.stdin)\n"
        "out = {k: {'value': v, 'rollup': sum(inst.values())} for k, v in inst.items()}\n"
        "print(json.dumps(out))\n")
    verdict = parity.run(cutoff="2026-07-21T00:00:00Z", window_days=7,
                         sample_data=json.dumps(_RAW), view_cmd=cmd)
    assert verdict["status"] == "error", verdict
    assert "aggregate" in verdict["note"].lower() and "rollup" in verdict["note"]
    # a NON-numeric extra key (a benign label) is NOT a smuggled aggregate — the scan
    # is numeric-typed, so a string annotation still projects cleanly to green.
    ok_cmd = _write_view_driver(tmp_path,
        "import json, sys\n"
        "inst = json.load(sys.stdin)\n"
        "out = {k: {'value': v, 'unit': 'ratio'} for k, v in inst.items()}\n"
        "print(json.dumps(out))\n")
    ok = parity.run(cutoff="2026-07-21T00:00:00Z", window_days=7,
                    sample_data=json.dumps(_RAW), view_cmd=ok_cmd)
    assert ok["status"] == "ok", ok


def test_broken_reader_is_an_error(tmp_path):
    # a CONFIGURED view reader that exits non-zero must never park the falsifier
    # green (credential/rot-style loud error), exit 1.
    cmd = _write_view_driver(tmp_path, "import sys\nsys.exit(3)\n")
    verdict = parity.run(cutoff="2026-07-21T00:00:00Z", window_days=7,
                         sample_data=json.dumps(_RAW), view_cmd=cmd)
    assert verdict["status"] == "error", verdict


def test_main_exit_codes(tmp_path, monkeypatch):
    # main() exits 0 on ok, 1 on breach — the LOUD exit the watchdog/CI reads.
    monkeypatch.setenv("COG3_OVI_PARITY_DATA_JSON",
                       str(_seed_raw(tmp_path)))
    assert parity.main(["--json"]) == 0                     # real view, ok
    bad = _write_view_driver(tmp_path,
        "import json, sys\n"
        "inst = json.load(sys.stdin)\n"
        "print(json.dumps({k: {'value': 0.0} for k in inst}))\n")
    monkeypatch.setenv("COG3_OVI_VIEW_CMD", " ".join(bad))
    assert parity.main(["--json"]) == 1                     # perturbed view, breach


def _seed_raw(tmp_path: Path) -> Path:
    p = tmp_path / "raw.json"
    p.write_text(json.dumps(_RAW), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 3. Pure core — EXACT, no tolerance
# ---------------------------------------------------------------------------

def test_parity_scan_is_exact_no_tolerance():
    gt = {"a": 0.5, "b": 0.25}
    assert parity.parity_scan(ground_truth=gt, projection=dict(gt))["status"] == "ok"
    # a 1e-12 delta is a BREACH — exact-only (rev-0 §15 Q7: no per-instrument tolerance)
    off = {"a": 0.5 + 1e-12, "b": 0.25}
    assert parity.parity_scan(ground_truth=gt, projection=off)["status"] == "breach"


# ---------------------------------------------------------------------------
# 4. The import ban is REAL (prove-it-then-remove) + the REAL script is clean
# ---------------------------------------------------------------------------

def test_committed_parity_script_imports_no_objectives():
    # the REAL committed script reaches the objectives view ONLY via a subprocess
    # black box — it names framework.objectives on no import line (AST-blind text
    # check: a bare literal in an argv string is fine, an import statement is not).
    src = (_REPO / _PARITY_REL).read_text(encoding="utf-8")
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert "framework.objectives" not in stripped, \
                f"cog3-ovi-parity.py must not import framework.objectives: {line!r}"


def test_committed_parity_script_reads_no_clock():
    # PINNED, no datetime.now (A-M6 mirrored): the window is a DECLARED arg, never
    # a clock read — the legacy production gather is datetime.now-windowed, this
    # falsifier is not.
    src = (_REPO / _PARITY_REL).read_text(encoding="utf-8")
    # the CALL forms (with `(`) — the docstring may NAME datetime.now to explain
    # the pin, but no clock is ever CALLED in a fold/resolve path.
    for token in ("datetime.now(", "time.time(", "date.today("):
        assert token not in src, f"parity script reads a clock ({token}) — must be pinned"


def test_adding_an_objectives_import_reds_the_gate(tmp_path):
    # THE enforcement (C-F17 analog, §6.5): cog3-ovi-parity.py is deliberately OFF
    # the objectives-reader allowlist, so an objectives import from it REDs as
    # UNALLOWLISTED_OBJECTIVES_IMPORTER. Prove it against the real gate in a scratch
    # tree, then it is removed (tmp cleanup) — the wave-4 "prove it then remove".
    gate = _load(_GATE_REL, "cog3_ovi_parity_gate")
    scratch = tmp_path / "tree"
    tgt = scratch / _PARITY_REL
    tgt.parent.mkdir(parents=True, exist_ok=True)
    tgt.write_text("from framework.objectives import ovi_view\n", encoding="utf-8")
    violations = gate.scan(scratch)
    assert f"{_PARITY_REL}:{gate.RULE_UNALLOWLISTED_OBJ}" in violations, violations
    # the REAL committed script, by contrast, is clean under the gate at the repo.
    real = [v for v in gate.scan(_REPO) if v.startswith(_PARITY_REL + ":")]
    assert real == [], real
