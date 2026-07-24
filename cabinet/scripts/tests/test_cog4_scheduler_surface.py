"""COG-4 W3 u2 — the LANDED scheduler surface battery (contract §6.3 / §7.1 /
§7.2 / §7.5; the W2 fold corpus is the executable spec and this suite runs its
arm batteries against the REAL `framework.scheduler` surface).

WHY THIS FILE EXISTS (a NEW test file — the §13 corpus stays byte-untouched):
the W2 vacuity guards' companion assertions went RED by design the moment
`framework/scheduler/` landed (their retirement — swapping each guard body for
its `run_real_arm` call — is the integrator's edit, never a builder's). This
suite is the retirement TARGET, live in CI from the landing commit:

  * TestRealArmsLive runs ALL NINE armed corpus batteries (sims 1/2/4/7/8/13 +
    the A-M6 purity pair + the N1 determinism triple) against the real
    surface via `lib_cog4_corpus.run_real_arm(arm, tmp_path, repo=_REPO)` —
    the exact one-line bodies the W2 retirement condition names.
  * TestServeRefuseLimbs pins the §6.3 store discipline on the ONE kernel-
    bound loader (serve_schedule, the F1 law): absent rows-hash key REFUSES
    (the objectives skip-hole, closed), tampered/REORDERED rows refuse (the
    FILE-ORDER chain), a forged count cannot ride a valid rows-hash, and the
    schedule never serves detached from its hash-bound snapshot record.
  * TestWriterLock is the §7.5 concurrent-writer proof: writers to one
    cache_dir serialize on an O_EXCL lockfile — the loser fails LOUD
    (ScheduleLockHeld) and writes NOTHING; racing subprocess builders never
    corrupt (the surviving store serves verified and byte-matches a clean
    single build).
  * TestSnapshotRoundTrip is the §7.1 end-to-end: a REAL cortex store
    (lib_cog3_fixtures.persist_cortex_store) + a REAL objectives graph store
    (the cog3-rebuild.py CLI, subprocess — the COG-3 fixture idiom) feed
    cog4-snapshot.py; the written snapshot validates under the CORPUS
    validator; cog4-schedule.py folds it; the store passes the corpus
    wellformed battery and serves through serve_schedule.

S0: python3.12, no DB, no network; children inherit the conftest env fence.
Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W3 u2 (Fable-for-execution named
unit, Captain 2026-07-23 calibration).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):        # tests/ is a package: put it on the path
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog4_corpus as C  # noqa: E402
import lib_cog3_fixtures as F3  # noqa: E402  (curated cortex-store seeder)

from framework.scheduler import model  # noqa: E402
from framework.scheduler.fold import ScheduleLockHeld, build_schedule  # noqa: E402
from framework.scheduler.serve import ScheduleRefused, serve_schedule  # noqa: E402

_SNAPSHOT_CLI = _REPO / "cabinet" / "scripts" / "cog4-snapshot.py"
_SCHEDULE_CLI = _REPO / "cabinet" / "scripts" / "cog4-schedule.py"
_COG3_REBUILD = _REPO / "cabinet" / "scripts" / "cog3-rebuild.py"


def _build_burst(cache: Path) -> dict:
    """In-process real build of the burst fixture; returns the snapshot."""
    build_schedule(C.fixture_path("burst"), cache)
    return json.loads(C.fixture_path("burst").read_text("utf-8"))


def _rewrite_manifest(cache: Path, mutate) -> None:
    manifest = json.loads((cache / model.MANIFEST_FILE).read_text("utf-8"))
    mutate(manifest)
    (cache / model.MANIFEST_FILE).write_bytes(model.canonical_bytes(manifest))


# ===========================================================================
# the nine W2 arm batteries, live on the REAL surface (the retirement bodies)
# ===========================================================================
class TestRealArmsLive:
    @pytest.mark.parametrize("arm", sorted(C.REAL_ARMS))
    def test_real_arm_battery_green(self, arm, tmp_path):
        # the EXACT call the W2 retirement condition names: the corpus arm
        # battery over the real framework.scheduler.fold.build_schedule.
        C.run_real_arm(arm, tmp_path, repo=_REPO)


# ===========================================================================
# §6.3 — the ONE kernel-bound loader and its REFUSE limbs
# ===========================================================================
class TestServeRefuseLimbs:
    def test_serve_round_trip_binds_rows_manifest_and_snapshot(self, tmp_path):
        snap = _build_burst(tmp_path)
        served = serve_schedule(tmp_path)
        # the served rows ARE the store rows (single verified read)...
        assert served["rows"] == C.read_rows(tmp_path)
        assert served["manifest"] == C.read_manifest(tmp_path)
        # ...the hash matches the CORPUS-pinned chain over re-parsed rows...
        assert served["schedule_rows_hash"] == \
            C.chained_rows_hash(served["rows"])
        # ...and the snapshot record is served hash-bound, echoing the epoch.
        assert served["snapshot"]["wake_input_hashes"] == \
            snap["wake_input_hashes"]

    def test_absent_rows_hash_key_refuses(self, tmp_path):
        # §6.3: the MANDATORY-present limb — the objectives `is not None and`
        # skip-hole does NOT propagate into the schedule store.
        _build_burst(tmp_path)

        def _drop(manifest):
            del manifest[model.MANIFEST_ROWS_HASH_KEY]
        _rewrite_manifest(tmp_path, _drop)
        with pytest.raises(ScheduleRefused, match="MANDATORY-PRESENT"):
            serve_schedule(tmp_path)

    def test_tampered_rows_refuse(self, tmp_path):
        _build_burst(tmp_path)
        store = tmp_path / model.SCHEDULE_FILE
        lines = store.read_text("utf-8").splitlines()
        forged = json.loads(lines[0])
        forged["budget_units"] = forged["budget_units"] + 99
        lines[0] = model.canonical_bytes(forged).decode("ascii")
        store.write_text("\n".join(lines) + "\n", "utf-8")
        with pytest.raises(ScheduleRefused, match="rows-hash mismatch"):
            serve_schedule(tmp_path)

    def test_reordered_rows_refuse(self, tmp_path):
        # content-identical but REORDERED store: the corpus-pinned FILE-ORDER
        # chain refuses — canonical tie-break order is part of the artifact.
        _build_burst(tmp_path)
        store = tmp_path / model.SCHEDULE_FILE
        lines = store.read_text("utf-8").splitlines()
        assert len(lines) >= 2, "burst fixture must emit >= 2 rows"
        store.write_text("\n".join(reversed(lines)) + "\n", "utf-8")
        with pytest.raises(ScheduleRefused, match="rows-hash mismatch"):
            serve_schedule(tmp_path)

    def test_forged_counts_cannot_ride_a_valid_rows_hash(self, tmp_path):
        _build_burst(tmp_path)

        def _forge(manifest):
            manifest["counts"]["rows"] += 1
        _rewrite_manifest(tmp_path, _forge)
        with pytest.raises(ScheduleRefused, match="counts"):
            serve_schedule(tmp_path)

    def test_tampered_snapshot_record_refuses(self, tmp_path):
        _build_burst(tmp_path)
        record = tmp_path / model.SNAPSHOT_RECORD_FILE
        record.write_bytes(record.read_bytes() + b" ")
        with pytest.raises(ScheduleRefused, match="snapshot"):
            serve_schedule(tmp_path)

    def test_missing_snapshot_record_refuses(self, tmp_path):
        # a schedule may never serve detached from the snapshot that built it.
        _build_burst(tmp_path)
        (tmp_path / model.SNAPSHOT_RECORD_FILE).unlink()
        with pytest.raises(ScheduleRefused, match="snapshot record"):
            serve_schedule(tmp_path)

    def test_invalid_snapshot_input_hard_errors(self, tmp_path):
        # §7.1: the fold's entry gate — a non-canonical cutoff never folds.
        snap = C.load_fixture("burst")
        snap["cutoff"] = "2026-07-23T06:00:00+02:00"
        bad = tmp_path / "bad-snapshot.json"
        bad.write_bytes(json.dumps(snap).encode())
        with pytest.raises(model.SnapshotError, match="non-canonical cutoff"):
            build_schedule(bad, tmp_path / "cache")


# ===========================================================================
# §7.5 — the writer lock: losers fail LOUD, stores never corrupt
# ===========================================================================
class TestWriterLock:
    def test_held_lock_fails_loud_and_writes_nothing(self, tmp_path):
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / model.LOCK_FILE).write_text("424242", "utf-8")
        with pytest.raises(ScheduleLockHeld, match="lock held"):
            build_schedule(C.fixture_path("burst"), cache)
        present = [f for f in model.ARTIFACT_FILES if (cache / f).exists()]
        assert present == [], f"loser wrote artifacts: {present}"

    def test_lock_released_after_build_and_store_serves(self, tmp_path):
        _build_burst(tmp_path)
        assert not (tmp_path / model.LOCK_FILE).exists()
        serve_schedule(tmp_path)               # verified serve green

    def test_racing_subprocess_builders_never_corrupt(self, tmp_path):
        # two real builders race ONE cache_dir: every child either completes
        # (0) or loses LOUDLY on the lock (3) — and the surviving store is
        # byte-identical to a clean single build (pure function + §7.5).
        reference = tmp_path / "reference"
        build_schedule(C.fixture_path("burst"), reference)
        expected = C.combined_artifact_hash(reference)

        cache = tmp_path / "race"
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(_REPO)!r})\n"
            "from framework.scheduler.fold import ScheduleLockHeld, "
            "build_schedule\n"
            "try:\n"
            f"    build_schedule({str(C.fixture_path('burst'))!r}, "
            f"{str(cache)!r})\n"
            "except ScheduleLockHeld:\n"
            "    sys.exit(3)\n")
        procs = [subprocess.Popen([sys.executable, "-c", code],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True)
                 for _ in range(2)]
        outcomes = [(p.communicate()[1], p.returncode) for p in procs]
        rcs = [rc for _, rc in outcomes]
        assert set(rcs) <= {0, 3}, outcomes
        assert 0 in rcs, "at least one racing builder must win the lock"
        serve_schedule(cache)                  # never corrupt: verified serve
        assert C.combined_artifact_hash(cache) == expected
        assert not (cache / model.LOCK_FILE).exists()


# ===========================================================================
# §7.1 end-to-end — real cortex + objectives stores -> snapshot -> fold ->
# verified serve, through the REAL CLIs (the COG-3 fixture idiom)
# ===========================================================================
_REGISTRY = [
    {"organ": "quay-census", "starvation_bound": 3, "operations": [
        {"operation": "quay/census-refresh", "subject": None, "urgency": 5,
         "cost_units": 2, "trigger_due": True,
         "deps": {"organs": [], "capabilities": []},
         "descriptor": {"capability": "quay/census-refresh"}}]},
    {"organ": "ledger-audit", "starvation_bound": None, "operations": [
        {"operation": "ledger/audit-pass", "subject": None, "urgency": 1,
         "cost_units": 1, "trigger_due": True,
         "deps": {"organs": [], "capabilities": []},
         "descriptor": {"capability": "ledger/audit-pass"}}]},
]


def _seed_stores(root: Path) -> Path:
    """A REAL cortex store + a REAL objectives graph store (sibling layout the
    objectives serve surface expects), built via the curated seeder + the real
    cog3-rebuild CLI."""
    cache_root = root / "cache"
    F3.persist_cortex_store(cache_root / "cortex", [])
    roots = F3.write_roots_yml(root, [{"slug": "stephie",
                                       "statement": "grow the quay"}])
    r = subprocess.run(
        [sys.executable, str(_COG3_REBUILD), "--roots", str(roots),
         "--cache", str(cache_root / "objectives"), "--cutoff", F3.CUTOFF],
        capture_output=True, text=True)
    assert r.returncode == 0, f"cog3-rebuild failed:\n{r.stderr}"
    return cache_root


class TestSnapshotRoundTrip:
    def test_cli_snapshot_then_fold_then_verified_serve(self, tmp_path):
        cache_root = _seed_stores(tmp_path)
        registry = tmp_path / "organ-registry.json"
        registry.write_text(json.dumps(_REGISTRY), "utf-8")
        health = tmp_path / "organ-health.json"
        health.write_text(json.dumps({"quay-census": "pass",
                                      "ledger-audit": "pass"}), "utf-8")

        r = subprocess.run(
            [sys.executable, str(_SNAPSHOT_CLI),
             "--cache-root", str(cache_root),
             "--services-manifest", str(_REPO / "cabinet" / "services.yml"),
             "--organ-registry", str(registry),
             "--organ-health", str(health),
             "--budget-ceiling", "3",
             "--scope", "main", "--cutoff", "2026-07-22T00:00:00Z",
             "--json"],
            capture_output=True, text=True)
        assert r.returncode == 0, f"cog4-snapshot failed:\n{r.stderr}"
        result = json.loads(r.stdout)
        out = Path(result["out"])

        # the written snapshot validates under the CORPUS validator and binds
        # the real cortex/objectives store hashes.
        snap = json.loads(out.read_text("utf-8"))
        C.validate_snapshot(snap)
        cortex_manifest = json.loads(
            (cache_root / "cortex" / "fold-manifest.json").read_text("utf-8"))
        assert snap["wake_input_hashes"]["cortex_belief_store_hash"] == \
            cortex_manifest["belief_store_hash"]
        graph_manifest = json.loads(
            (cache_root / "objectives" / "graph-manifest.json")
            .read_text("utf-8"))
        assert snap["wake_input_hashes"]["objectives_graph_rows_hash"] == \
            graph_manifest["graph_rows_hash"]
        assert result["snapshot_hash"] == \
            C.sha256_hex(C.canonical_bytes(snap))

        # fold via the real CLI; the store passes the corpus wellformed
        # battery and the ceiling law, and serves through the ONE loader.
        r2 = subprocess.run(
            [sys.executable, str(_SCHEDULE_CLI),
             "--cache-root", str(cache_root), "--json"],
            capture_output=True, text=True)
        assert r2.returncode == 0, f"cog4-schedule failed:\n{r2.stderr}"
        summary = json.loads(r2.stdout)
        sched_dir = cache_root / "scheduler"
        C.assert_schedule_wellformed(snap, sched_dir)
        C.assert_ceiling_respected(snap, sched_dir)
        served = serve_schedule(sched_dir)
        assert summary["schedule_rows_hash"] == served["schedule_rows_hash"]
        assert summary["counts"] == served["manifest"]["counts"]
        # budget ceiling 3: the cost-2 op + the cost-1 op both fit.
        chosen = {r_["organ"] for r_ in served["rows"]
                  if r_["decision"] == C.DECISION_SELECT}
        assert chosen == {"quay-census", "ledger-audit"}

    def test_snapshot_cli_refuses_without_a_cortex_store(self, tmp_path):
        r = subprocess.run(
            [sys.executable, str(_SNAPSHOT_CLI),
             "--cache-root", str(tmp_path / "empty"),
             "--services-manifest", str(_REPO / "cabinet" / "services.yml"),
             "--scope", "main", "--cutoff", "2026-07-22T00:00:00Z"],
            capture_output=True, text=True)
        assert r.returncode == 1
        assert "REFUSED" in r.stderr

    def test_snapshot_cli_refuses_non_canonical_cutoff(self, tmp_path):
        cache_root = _seed_stores(tmp_path)
        r = subprocess.run(
            [sys.executable, str(_SNAPSHOT_CLI),
             "--cache-root", str(cache_root),
             "--services-manifest", str(_REPO / "cabinet" / "services.yml"),
             "--scope", "main", "--cutoff", "2026-07-22T00:00:00+02:00"],
            capture_output=True, text=True)
        assert r.returncode == 1
        assert "non-canonical cutoff" in r.stderr

    def test_schedule_cli_fails_loud_on_missing_snapshot(self, tmp_path):
        r = subprocess.run(
            [sys.executable, str(_SCHEDULE_CLI),
             "--cache-root", str(tmp_path / "nothing")],
            capture_output=True, text=True)
        assert r.returncode == 1
        assert "REFUSED" in r.stderr
