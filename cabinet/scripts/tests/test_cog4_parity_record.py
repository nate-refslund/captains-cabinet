"""COG-4 N9 — the TRACKED parity-record gate (W5 x3; contract §1 N9 + §5.3 +
§12 N9 battery).

This is the "pre-prove OUT-OF-BAND" arm for the tracked
`cog4-parity-record.json`: the W2 corpus's `test_cog4_parity.py` real-artifact
arm (`TestParityGateRealArtifact`) is RECORD-KEYED and VACUITY-GUARDED — its
companion assertion goes RED the moment a tracked record lands, which is the
DESIGNED tripwire that the integrator retire that skip (corpus surgery, §13:
builders never edit the corpus; this unit routes the retirement via
contradictions[]). Because a builder cannot edit that corpus file, THIS NEW
file proves — right now, green — exactly what the retired arm will assert:

  * the tracked record REPRODUCES from the committed manifests via the REAL
    `cabinet/scripts/cog4-parity.py` (subprocess, hermetic) — byte-identical;
  * it is DETERMINISTIC — byte-identical across three PYTHONHASHSEED values
    (the N1 determinism discipline applied to the parity artifact);
  * it is SHAPE-CLEAN and DIVERGENCE-FREE under the W2 reference checkers
    (`record_errors == []`, `divergent_rows == []` — imported from the corpus
    reference, never re-implemented);
  * it COVERS the ENTIRE pilot set + all three §12 fixture cabinets (the N9
    coverage law) — organ set and operation set both exact;
  * it is the SOLE tracked record (the retired arm loads THE record, singular).

Any divergence is a STRUCTURAL BUILD FAILURE, never a warning (§5.3).

S0: python3.12, no DB, no network, deterministic (the CLI reads no clock/env of
its own; the empty-ledger hermetic verdict is "unmeasured" on any machine).
Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W5 x3 (N9 parity record).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog4_parity_set as PSET  # noqa: E402
# reuse the W2 corpus reference checkers + the tracked-record finder VERBATIM
# (the gate law is single-sourced in the corpus; this file never re-defines it)
from test_cog4_parity import (  # noqa: E402
    record_errors, divergent_rows, _tracked_records, _RECORD_BASENAME)

_PARITY_CLI = _REPO / "cabinet" / "scripts" / "cog4-parity.py"


def _run_cli(manifest_dir: Path, out_path: Path, hashseed: str | None = None):
    env = dict(os.environ)
    if hashseed is not None:
        env["PYTHONHASHSEED"] = hashseed
    return subprocess.run(
        [sys.executable, str(_PARITY_CLI),
         "--manifest-dir", str(manifest_dir), "--out", str(out_path)],
        capture_output=True, text=True, env=env)


class TestTrackedParityRecord:
    def test_source_shape_pinned(self):
        """The pilot + cabinet organs on disk match the pinned constants — a
        manifest rename can never silently shrink N9 coverage."""
        PSET.assert_source_shape()
        assert PSET.RECORD_PATH.exists(), (
            f"tracked record missing at {PSET.RECORD_PATH} — W5 x3 must land it")

    def test_record_reproduces_from_manifests(self, tmp_path):
        """The committed record is EXACTLY `cog4-parity.py`'s output over the
        assembled pilot+cabinet set — regenerate and byte-compare (drift
        between the manifests and the record REDs here)."""
        assembled = PSET.assemble(tmp_path / "set")
        out = tmp_path / _RECORD_BASENAME
        proc = _run_cli(assembled, out)
        assert proc.returncode == 0, (
            f"cog4-parity.py exited {proc.returncode}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        assert out.read_bytes() == PSET.RECORD_PATH.read_bytes(), (
            "regenerated parity record differs from the tracked "
            f"{PSET.RECORD_PATH.name} — a manifest changed without regenerating "
            "the record, or the CLI output shape drifted")

    def test_record_is_deterministic_across_hashseeds(self, tmp_path):
        """Byte-identical across three PYTHONHASHSEED values AND equal to the
        tracked bytes (the N1 determinism discipline, on the parity artifact)."""
        committed = PSET.RECORD_PATH.read_bytes()
        digests = set()
        for i, seed in enumerate(("0", "1", "2")):
            assembled = PSET.assemble(tmp_path / f"set{i}")
            out = tmp_path / f"rec{i}.json"
            proc = _run_cli(assembled, out, hashseed=seed)
            assert proc.returncode == 0, proc.stderr
            b = out.read_bytes()
            assert b == committed, f"seed {seed} produced a different record"
            digests.add(hashlib.sha256(b).hexdigest())
        assert len(digests) == 1, f"non-deterministic bytes: {digests}"

    def test_record_is_shape_clean_and_divergence_free(self):
        """Under the W2 reference checkers: zero shape errors, zero divergent
        tuples (N9: any divergence is a structural build failure)."""
        record = json.loads(PSET.RECORD_PATH.read_text(encoding="utf-8"))
        assert record_errors(record) == [], record_errors(record)
        assert divergent_rows(record) == [], divergent_rows(record)
        assert record.get("schema") == "cog4-parity-record/v1"

    def test_record_covers_pilot_and_all_three_cabinets(self):
        """The N9 coverage law: the record spans the ENTIRE pilot set + all
        three §12 fixture cabinets — organ set AND operation set both exact,
        single-sourced from the manifests the CLI itself reads."""
        record = json.loads(PSET.RECORD_PATH.read_text(encoding="utf-8"))
        rows = record["rows"]
        organs = {r["organ"] for r in rows}
        assert organs == PSET.EXPECTED_ORGANS, (
            f"organ coverage {sorted(organs)} != expected "
            f"{sorted(PSET.EXPECTED_ORGANS)}")
        # every pilot organ AND every cabinet organ is present (explicit, so a
        # future reader sees both halves of the N9 coverage requirement)
        assert PSET.PILOT_ORGANS <= organs, "pilot set not fully covered"
        assert PSET.CABINET_ORGANS <= organs, "a fixture cabinet is missing"
        operations = {r["operation"] for r in rows}
        assert operations == PSET.declared_operations(), (
            "record operation set != the union declared by the manifests — "
            "coverage silently dropped or added an operation")
        assert len(operations) == len(rows), "duplicate operation rows"

    def test_record_is_the_sole_tracked_record(self):
        """The retired corpus arm loads THE tracked record (singular) — prove
        there is exactly one, and it is ours."""
        records = _tracked_records(_REPO)
        assert records == [PSET.RECORD_PATH], (
            f"expected exactly one tracked {_RECORD_BASENAME} at "
            f"{PSET.RECORD_PATH}, found {records}")
