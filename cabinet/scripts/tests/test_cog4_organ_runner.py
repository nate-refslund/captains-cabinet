"""COG-4 W2 T2 — the RUNNER-INVARIANCE battery (contract
cognitive-core-phase-4-contract-2026-07-23 §9.5 / MF-AC2, named in §12
"Runner-invariance battery"): the composed wake vehicle is SCHEDULER-BLIND BY
CONSTRUCTION — running the runner fixture with and without a schedule artifact
injected into the cache yields BYTE-IDENTICAL behavior, and the mutant runner
that reads the schedule artifact REDs. The shadow-only guarantee is mechanical,
not doctrinal.

WHAT RUNS LIVE NOW vs WHAT IS SKIPPED (the W1-u2 mergeability idiom, §13):

  * LIVE — a reference runner simulator encodes the §9.5 spec on scratch
    fixtures: it loads EXACTLY the organ manifests its row NAMES (the declared
    row→manifest association — never discovery), runs each organ into its own
    declared output/state surface, and never observes the schedule cache. The
    invariance property, the cache-untouched property (the behavioral twin of
    the boundary manifest's deliberate-absence data-plane row, §8.3), and the
    declared-list law are asserted against the reference NOW — and each ships
    with a real divergent mutant proven to FAIL in this run (schedule-READER,
    schedule-WRITER, manifest-DISCOVERY): a gate without a biting mutant is
    decoration (§12).
  * RETIRED 2026-07-24 (W6 landing; per §13 + the routed contradictions,
    feat-cog4-w6-e2-cp1.md §6.1-6.2) — the vacuity arms that targeted the
    then-unbuilt `cabinet/scripts/cog4-organ-runner.py` are retired per their
    own RETIREMENT CONDITIONS: the CLI landed in W6-e2 and the §9.5 battery
    is BOUND to it in `test_cog4_organ_runner_real.py::TestRealRunnerCliBattery`
    (real_cli_runner subprocess adapter feeding _check_invariance /
    _check_cache_untouched / _check_declared_list from THIS file — imported,
    never re-implemented; a corpus back-import would be circular, so the
    binding lives there by design).

SELF-CONTAINED BY LAW (LESSONS L1111): the tiny schedule-artifact writer below
is local to this file — parallel W2 units never maintain shared pinned
constants; nothing here imports from a sibling corpus file.

FIXTURE-SHAPE HONESTY: fixture organ manifests model the PROPOSED §4.2 fields
(outputs / state_ownership / trigger_policy / freshness_needs / fallback) as
plain JSON data. Nothing validates against the germline extension schema —
that is the §4.5 Captain-windowed W4 micro-unit; these tests neither touch nor
depend on it. The schedule-artifact fixture is written into a tmp cache dir
only (the boundary manifest allowlists test_cog4_* for the scheduler store
token; no fenced literal appears here regardless).

CORPUS LAW (§13): purely ADDITIVE — no existing test/lib file is edited;
contradictions route to the integrator; retirement of the vacuity arms is the
integrator's move when the runner CLI lands (W6). PERFORMED 2026-07-24 at the
W6 landing (the edit above/below IS that integrator move).

S0: python3.12, no DB, no network, no subprocess. Provenance: authored per the
2026-07-07 full-autonomy grant + the 2026-07-20 cognitive-masterplan
continuous grant (COG-4 contract §9.5/§12/§13; Fable 5 corpus authorship per
the two-tier law).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The real target surface landed in W6-e2 (cabinet/scripts/cog4-organ-runner.py);
# its §9.5 battery binding lives in test_cog4_organ_runner_real.py (see the
# module docstring's RETIRED note — the former vacuity-arm constants are gone
# with the arms).


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ===========================================================================
# Fixture surface: organ manifests, the runner row, the injected artifact
# ===========================================================================

def write_organ_manifest(manifest_dir: Path, name: str, *, payload="v1"):
    """A fixture organ manifest modelling the PROPOSED §4.2 fields as data."""
    manifest = {
        "name": name,
        "kind": "organ",
        "outputs": [f"out/{name}.json"],
        "state_ownership": [f"state/{name}/"],
        "trigger_policy": "periodic",
        "fallback": "skip",
        "freshness_needs": {"max_staleness_seconds": 3600,
                            "expected_output": f"out/{name}.json"},
        "payload": payload,
    }
    manifest_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_dir / f"{name}.manifest.json"
    path.write_text(json.dumps(manifest, sort_keys=True, indent=1) + "\n",
                    encoding="utf-8")
    return path


def make_runner_row(organs):
    """The §9.5 wake-row shape: the services row EXPLICITLY names its composed
    organ manifests — the row→manifest association is DECLARED, never
    discovered."""
    return {"service": "cog4-organ-runner-fixture", "wake_id": "wake-0001",
            "organs": list(organs)}


def inject_schedule_artifact(cache_dir: Path):
    """Drop a plausible schedule artifact into the cache the runner can see —
    the §9.5 injection: rows that, if a runner READ them, would tell it to run
    only organ-b (so a reader-mutant visibly diverges)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows = [{"organ": "organ-b", "operation": "collect",
             "reason": "schedule-says-only-b", "budget_units": 1}]
    (cache_dir / "schedule.jsonl").write_text(
        "".join(_canon(r).decode("utf-8") + "\n" for r in rows),
        encoding="utf-8")
    (cache_dir / "schedule-manifest.json").write_text(
        json.dumps({"schema_version": "cog4-schedule-fixture/v1",
                    "rows_hash": "fixture-hash"}, sort_keys=True) + "\n",
        encoding="utf-8")


def _dir_bytes(root: Path):
    """Byte snapshot of a directory tree (relpath -> bytes)."""
    if not root.exists():
        return {}
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


# ===========================================================================
# The runner (reference + named-escape mutants) — §9.5 spec encoded
# ===========================================================================

def reference_runner(row, manifest_dir: Path, run_root: Path, cache_dir: Path):
    """The §9.5 reference: loads EXACTLY the manifests the row names, runs each
    organ per its own manifest into its declared output surface, and is BLIND
    to `cache_dir` — the schedule store is never opened, listed, or written.
    (`cache_dir` is accepted because the real runner runs in an environment
    where the store exists; blindness to it is the property under test.)
    Returns the behavior tuple (organs_selected, outputs, exit_status)."""
    selected, outputs = [], {}
    for name in row["organs"]:
        manifest = json.loads(
            (manifest_dir / f"{name}.manifest.json").read_text(encoding="utf-8"))
        selected.append(manifest["name"])
        out_rel = manifest["outputs"][0]
        out_path = run_root / out_rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        body = _canon({"organ": manifest["name"],
                       "payload": manifest["payload"],
                       "wake_id": row["wake_id"]}).decode("utf-8") + "\n"
        out_path.write_text(body, encoding="utf-8")
        outputs[out_rel] = _digest(body.encode("utf-8"))
    return {"organs_selected": selected, "outputs": outputs, "exit_status": 0}


def mutant_schedule_reader_runner(row, manifest_dir, run_root, cache_dir):
    """§9.5 NAMED mutant — the runner that READS the schedule artifact: when
    the store is present it obeys the schedule's organ selection instead of its
    row. Must FAIL the invariance battery (behavior differs with vs without
    the artifact)."""
    schedule = Path(cache_dir) / "schedule.jsonl"
    organs = list(row["organs"])
    if schedule.exists():
        scheduled = {json.loads(line)["organ"] for line
                     in schedule.read_text(encoding="utf-8").splitlines()
                     if line.strip()}
        organs = [o for o in organs if o in scheduled]
    return reference_runner(dict(row, organs=organs), manifest_dir, run_root,
                            cache_dir)


def mutant_schedule_writer_runner(row, manifest_dir, run_root, cache_dir):
    """Named escape (the §8.3 data-plane row's behavioral twin): a runner that
    WRITES into the schedule cache. Must FAIL the cache-untouched property."""
    result = reference_runner(row, manifest_dir, run_root, cache_dir)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "runner-was-here.json").write_text(
        json.dumps({"ran": row["organs"]}) + "\n", encoding="utf-8")
    return result


def mutant_discovery_runner(row, manifest_dir, run_root, cache_dir):
    """Named escape (the §9.5 declared-association law inverted): ignores the
    row's declared organ list and DISCOVERS manifests by globbing the manifest
    dir. Must FAIL the declared-list property (it runs the stray organ)."""
    discovered = sorted(p.name[:-len(".manifest.json")]
                        for p in Path(manifest_dir).glob("*.manifest.json"))
    return reference_runner(dict(row, organs=discovered), manifest_dir,
                            run_root, cache_dir)


# ===========================================================================
# Harness
# ===========================================================================

def _arm(runner, base: Path, arm_name: str, *, inject: bool,
         stray_manifest: bool = False):
    """One battery arm in a fresh root: returns (behavior, run-tree bytes,
    cache bytes BEFORE the run, cache bytes AFTER the run)."""
    root = base / arm_name
    manifest_dir = root / "manifests"
    run_root = root / "run"
    cache_dir = root / "cache" / "scheduler-fixture"
    cache_dir.mkdir(parents=True)
    write_organ_manifest(manifest_dir, "organ-a")
    write_organ_manifest(manifest_dir, "organ-b")
    if stray_manifest:
        # present on disk, NOT named by the row — must never run (§9.5).
        write_organ_manifest(manifest_dir, "organ-stray")
    if inject:
        inject_schedule_artifact(cache_dir)
    row = make_runner_row(["organ-a", "organ-b"])
    before = _dir_bytes(cache_dir)
    behavior = runner(row, manifest_dir, run_root, cache_dir)
    after = _dir_bytes(cache_dir)
    return behavior, _dir_bytes(run_root), before, after


def _check_invariance(runner, base: Path):
    """THE §9.5/§12 runner-invariance property: with and without a schedule
    artifact injected into the cache, the behavior tuple AND the produced
    output bytes are identical — the runner is scheduler-blind."""
    bare_behavior, bare_bytes, _b0, _a0 = _arm(runner, base, "bare",
                                               inject=False)
    inj_behavior, inj_bytes, _b1, _a1 = _arm(runner, base, "injected",
                                             inject=True)
    assert inj_behavior == bare_behavior, (
        "behavior diverged when a schedule artifact was present — the runner "
        "observed the schedule store (§9.5)")
    assert inj_bytes == bare_bytes, (
        "output bytes diverged when a schedule artifact was present (§9.5)")
    assert bare_behavior["organs_selected"] == ["organ-a", "organ-b"]
    assert bare_behavior["exit_status"] == 0


def _check_cache_untouched(runner, base: Path):
    """The §8.3 deliberate-absence row's behavioral twin: the runner leaves the
    schedule cache BYTE-UNTOUCHED in both arms (no read is provable only by
    invariance; no write is provable directly)."""
    for arm_name, inject in (("bare-w", False), ("injected-w", True)):
        _behavior, _bytes, before, after = _arm(runner, base, arm_name,
                                                inject=inject)
        assert after == before, (
            f"{arm_name}: the runner wrote into the schedule cache — the "
            "composed wake vehicle may never touch the schedule store (§8.3/§9.5)")


def _check_declared_list(runner, base: Path):
    """§9.5: the row→manifest association is DECLARED — a stray manifest on
    disk (not named by the row) is never loaded, never run, never emitted."""
    behavior, run_bytes, _b, _a = _arm(runner, base, "stray", inject=False,
                                       stray_manifest=True)
    assert behavior["organs_selected"] == ["organ-a", "organ-b"], behavior
    assert "organ-stray" not in behavior["organs_selected"]
    assert not any("organ-stray" in rel for rel in run_bytes), (
        "the stray organ produced output — the runner DISCOVERED a manifest "
        "its row never declared (§9.5)")


# ===========================================================================
# LIVE battery — reference passes, every mutant bites NOW
# ===========================================================================

class TestRunnerInvariance:
    def test_invariance_with_and_without_schedule_artifact(self, tmp_path):
        _check_invariance(reference_runner, tmp_path)

    def test_runner_leaves_schedule_cache_untouched(self, tmp_path):
        _check_cache_untouched(reference_runner, tmp_path)

    def test_row_declared_manifests_only_never_discovery(self, tmp_path):
        _check_declared_list(reference_runner, tmp_path)

    def test_runner_behavior_is_deterministic(self, tmp_path):
        """Same row + manifests ⇒ byte-identical behavior across two fresh
        runs (the byte-identical claim of §9.5 is meaningful only if the
        runner itself is deterministic)."""
        b1, bytes1, _x, _y = _arm(reference_runner, tmp_path, "run1",
                                  inject=False)
        b2, bytes2, _z, _w = _arm(reference_runner, tmp_path, "run2",
                                  inject=False)
        assert b1 == b2
        assert bytes1 == bytes2

    def test_mutant_schedule_reader_bites(self, tmp_path):
        """THE §9.5/§12 negative control MUST FAIL: the runner that reads the
        schedule artifact diverges the moment one is present."""
        with pytest.raises(AssertionError):
            _check_invariance(mutant_schedule_reader_runner, tmp_path)

    def test_mutant_schedule_writer_bites(self, tmp_path):
        """The cache-untouched negative control MUST FAIL: a runner writing
        into the schedule cache is the data-plane breach the §8.3 deliberate
        absence fences statically."""
        with pytest.raises(AssertionError):
            _check_cache_untouched(mutant_schedule_writer_runner, tmp_path)

    def test_mutant_discovery_runner_bites(self, tmp_path):
        """The declared-association negative control MUST FAIL: a discovery
        runner picks up the stray manifest its row never declared."""
        with pytest.raises(AssertionError):
            _check_declared_list(mutant_discovery_runner, tmp_path)


# ===========================================================================
# FORMER VACUITY ARMS — RETIRED 2026-07-24 (W6 landing; per §13 + the routed
# contradictions, feat-cog4-w6-e2-cp1.md §6.1-6.2). The runner CLI landed in
# W6-e2, tripping both companion absence assertions; per their RETIREMENT
# CONDITIONS the §9.5 battery is bound to the real CLI in
# test_cog4_organ_runner_real.py::TestRealRunnerCliBattery:
#   * test_real_runner_invariance_battery  -> test_real_cli_invariance
#     (real_cli_runner subprocess adapter through _check_invariance above)
#   * test_real_runner_store_blindness     -> test_real_cli_leaves_schedule_
#     cache_untouched + test_real_cli_declared_list_never_discovery
#     (through _check_cache_untouched/_check_declared_list above)
# The checkers stay HERE (single source); the binding file imports them —
# the reverse import would be circular, so the retired arms leave no stub.
# ===========================================================================
