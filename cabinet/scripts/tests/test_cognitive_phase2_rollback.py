"""COG-2 unit-5 — rollback manifest closure + phase-2 review-scope digest teeth.

Plan: docs/plans/cognitive-core-phase-2-contract-2026-07-22.md §12.4 (machine-
readable rollback manifest, schema cognitive-phase-rollback/v1, runtime inverses
+ code inverse + allowance removal + append-only retain + must_remain_unchanged
+ rehearsal) and §6/§12.3 (phase-local review-scope + rollback rehearsal twins
CLONING the phase-0/1 pattern; the phase-0/1 instances stay untouched).

Clones the phase-1 rollback test's structure
(cabinet/scripts/tests/test_cognitive_phase1_rollback.py) against the COG-2
manifest/tool/rehearsal. Read-only against the real tree except in a throwaway
worktree. Run:
  python3.12 -m pytest cabinet/scripts/tests/test_cognitive_phase2_rollback.py -q

Landing note: units 1-4 are COMMITTED at HEAD; the unit-5 landing wave (the
import gate, verify twin, this test, the review-scope binder + rollback
rehearsal + rollback manifest, and the egg/consequence/doctor/parity edits) is
WORKING-TREE-only during this wave. Every assertion here is GREEN pre-commit:
the committed-footprint ratchet validates units 1-4 now and, by construction,
keeps covering unit-5 once it lands (unit-5 files are already in the manifest
AND statically pinned by test_manifest_covers_unit5_working_tree_files). There
is no post-commit-only assertion in this file.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
ROLLBACK = ROOT / "docs/plans/cognitive-core-phase-2-rollback-manifest-2026-07-22.yml"
TOOL_REL = "cabinet/scripts/cognitive-phase2-review-scope.py"
REHEARSAL_REL = "cabinet/scripts/cognitive-phase2-rollback-rehearsal.py"
VERIFY_REL = "cabinet/scripts/verify-cognitive-phase2.sh"
REVIEW_ARTIFACT_REL = "shared/interfaces/reviews/cognitive-core-phase-2-review.md"

# S0 pin: the COG-2 phase-2 contract commit == the parent of unit 1 (7f44a3ed).
BASELINE_SHA = "b393f41b579c5ff4723f4502b006df58e9664cf1"

# The COMMITTED COG-2 footprint (units 1-4, baseline_sha..HEAD). Added -> remove;
# modified -> restore. The completeness ratchet below re-derives this from git so
# a later commit that lands a file without extending the manifest trips it.
REMOVE_COMMITTED = {
    "cabinet/config/cortex-source-trust.v1.yml",
    "cabinet/scripts/cog2-belief-hash.py",
    "cabinet/scripts/cog2-parity-falsifier.py",
    "cabinet/scripts/cog2-rebuild.py",
    "cabinet/scripts/cog2-verifier.py",
    "cabinet/scripts/tests/lib_cog2_envelope.py",
    "cabinet/scripts/tests/test_cog2_asof_fence.py",
    "cabinet/scripts/tests/test_cog2_consequence_seam.py",
    "cabinet/scripts/tests/test_cog2_contradiction.py",
    "cabinet/scripts/tests/test_cog2_corruption.py",
    "cabinet/scripts/tests/test_cog2_fencing.py",
    "cabinet/scripts/tests/test_cog2_parity.py",
    "cabinet/scripts/tests/test_cog2_provenance.py",
    "cabinet/scripts/tests/test_cog2_rebuild_determinism.py",
    "framework/cortex/__init__.py",
    "framework/cortex/adapters.py",
    "framework/cortex/belief.py",
    "framework/cortex/engine.py",
    "framework/cortex/query.py",
    "framework/schemas/domains/cortex/belief.v1.json",
    "framework/schemas/domains/cortex/source-trust.v1.json",
    "framework/schemas/domains/observations/observation.v1.json",
    "shared/interfaces/reviews/feat-cog2-unit1-rebuild-core-cp1.md",
    "shared/interfaces/reviews/feat-cog2-unit2-query-fence-cp1.md",
    "shared/interfaces/reviews/feat-cog2-unit3-consequence-cp1.md",
}
# The unit-5 landing wave NEW files (working-tree only this wave; the review
# artifact lands later via §12.3). Pinned statically because they are not yet in
# baseline_sha..HEAD.
REMOVE_UNIT5 = {
    "cabinet/scripts/cog2-import-gate.py",
    "cabinet/scripts/tests/test_cog2_import_gate.py",
    "cabinet/scripts/tests/test_cog2_measurement.py",
    "cabinet/scripts/tests/test_cog2_parity_wiring.py",
    "cabinet/scripts/verify-cognitive-phase2.sh",
    "cabinet/scripts/cognitive-phase2-review-scope.py",
    "cabinet/scripts/cognitive-phase2-rollback-rehearsal.py",
    "cabinet/scripts/tests/test_cognitive_phase2_rollback.py",
    "docs/plans/cognitive-core-phase-2-rollback-manifest-2026-07-22.yml",
    "shared/interfaces/reviews/feat-cog2-unit5-complete-cp1.md",
    REVIEW_ARTIFACT_REL,  # excluded from the digest; created by the §12.3 review
}
EXPECTED_REMOVE = REMOVE_COMMITTED | REMOVE_UNIT5

# COMMITTED COG-2 edits (baseline_sha..HEAD "M").
RESTORE_COMMITTED = {
    "cabinet/config/cognitive-architecture-contract.yml",
    "cabinet/scripts/evidence-coverage.py",
    "framework/fidelity/consequence.py",
}
# unit-5 edits to pre-existing files (working-tree "M" this wave).
RESTORE_UNIT5 = {
    "cabinet/scripts/cabinet-doctor.sh",
    "cabinet/scripts/task-sync-drift-falsifier.py",
    "cabinet/scripts/egg-export-manifest.txt",
    "cabinet/scripts/tests/test_egg_export.py",
    "cabinet/scripts/tests/test_task_sync_drift_falsifier.py",
}
EXPECTED_RESTORE = RESTORE_COMMITTED | RESTORE_UNIT5
EXPECTED_RETAIN = {
    "docs/plans/operative-egg-ledger-2026-07-07.yml",
    "docs/plans/operative-egg-plan-2026-07-07.md",
}


# ---------------------------------------------------------------------------
# Manifest closure (clones test_phase_1_manifest_is_closed...)
# ---------------------------------------------------------------------------

def test_phase_2_manifest_is_closed_and_append_only_aware():
    manifest = yaml.safe_load(ROLLBACK.read_text())
    assert set(manifest) == {
        "schema_version",
        "phase",
        "baseline_sha",
        "runtime_inverses",
        "remove",
        "restore_from_baseline",
        "allowance_removal",
        "retain_append_only",
        "must_remain_unchanged",
        "rehearsal",
    }
    assert manifest["schema_version"] == "cognitive-phase-rollback/v1"
    assert manifest["phase"] == "COG-2"
    assert manifest["baseline_sha"] == BASELINE_SHA
    all_paths = manifest["remove"] + manifest["restore_from_baseline"]
    assert len(all_paths) == len(set(all_paths)), "remove/restore overlap or dup"
    assert all(not Path(p).is_absolute() and ".." not in Path(p).parts for p in all_paths)
    assert set(manifest["remove"]) == EXPECTED_REMOVE
    assert set(manifest["restore_from_baseline"]) == EXPECTED_RESTORE
    retained = {row["path"]: row for row in manifest["retain_append_only"]}
    assert set(retained) == EXPECTED_RETAIN
    expected_rows = [f"COG-{i}" for i in range(9)]
    assert all(row["rows"] == expected_rows for row in retained.values())
    # every remove path exists NOW except the review artifact (created later by
    # the §12.3 post-implementation review); every restore + protected path exists.
    for p in manifest["remove"]:
        if p == REVIEW_ARTIFACT_REL:
            continue
        assert (ROOT / p).exists(), f"declared remove path absent: {p}"
    assert all((ROOT / p).exists() for p in manifest["restore_from_baseline"])
    assert all((ROOT / p).exists() for p in manifest["must_remain_unchanged"])


def test_phase_2_runtime_inverses_are_one_command_each():
    manifest = yaml.safe_load(ROLLBACK.read_text())
    inverses = {r["name"]: r for r in manifest["runtime_inverses"]}
    # COG-2 is shadow-only: the inverses are the read pointer (`none` all phase),
    # the disposable projection cache, and the additive cortex_ro role — each a
    # single safe-by-construction command, no authority cutover like COG-1's.
    assert set(inverses) == {"read_pointer", "projection", "provision_ro"}
    # read pointer is `none` all phase — the inverse is the fail-safe default (§9 r8)
    assert "cog2-read-pointer" in inverses["read_pointer"]["command"]
    assert "none" in inverses["read_pointer"]["command"]
    # the projection cache is deleted (safe by construction, §7.3); rebuild reverses it
    assert "cabinet/cache/cortex" in inverses["projection"]["command"]
    assert "cog2-rebuild.py" in inverses["projection"]["reversible_by"]
    # the cortex_ro role is dropped; re-provisioned via --provision-ro (§7.2)
    assert "DROP ROLE" in inverses["provision_ro"]["command"]
    assert inverses["provision_ro"]["reversible_by"].endswith("cog2-rebuild.py --provision-ro")
    # the allowance-rows removal rides the contract.yml restore (§12.4)
    ar = manifest["allowance_removal"]
    assert ar["path"] == "cabinet/config/cognitive-architecture-contract.yml"
    assert ar["path"] in manifest["restore_from_baseline"]


def test_phase_2_must_remain_unchanged_covers_phase0_and_phase1_protected_surfaces():
    # G-F2: the block is the Phase-0 ∪ Phase-1 protected-surface union (the two
    # phases pin the identical set); COG-2 (shadow-only) touches none of them.
    manifest = yaml.safe_load(ROLLBACK.read_text())
    protected = set(manifest["must_remain_unchanged"])
    for rel in (
        "cabinet/services.yml",
        "framework/events/emitter.py",
        "framework/authority/classifier.py",
        "framework/policies/authority-matrix.yml",
        "framework/learning/gate.py",
        "framework/authority",
        "framework/evidence",
        "shared/interfaces/captain-vetoes.yml",
        ".layer-separation-baseline",
        ".layer-separation-allowlist",
    ):
        assert rel in protected, f"must_remain_unchanged missing phase-0∪1 surface: {rel}"


# ---------------------------------------------------------------------------
# Completeness ratchet: the manifest covers the ACTUAL committed COG-2 footprint
# ---------------------------------------------------------------------------

def _git_name_status(rangespec: str) -> list[tuple[str, str]]:
    out = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-status", rangespec],
                         capture_output=True, text=True, check=True).stdout
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0][0], parts[-1]))
    return rows


def test_manifest_covers_committed_cog2_footprint():
    # Shallow CI checkouts (actions/checkout default) lack the baseline commit ->
    # `git diff BASELINE..HEAD` exits 128. The ratchet enforces on every full
    # clone (local batteries + the phase gate); skip honestly here.
    probe = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", BASELINE_SHA + "^{commit}"],
        capture_output=True, text=True)
    if probe.returncode != 0:
        pytest.skip("baseline SHA absent (shallow checkout) — footprint ratchet "
                    "runs on full clones")
    # Deterministic (no working-tree scan -> no other-wave interference): every
    # file COG-2 changed between baseline and HEAD is classified. A -> remove;
    # M -> restore or retain. GREEN over units 1-4 now; once the unit-5 landing
    # commit lands, its files ALSO appear here and are already covered (they are
    # in the manifest + pinned by test_manifest_covers_unit5_working_tree_files).
    manifest = yaml.safe_load(ROLLBACK.read_text())
    remove = set(manifest["remove"])
    restore = set(manifest["restore_from_baseline"])
    retain = {r["path"] for r in manifest["retain_append_only"]}
    for status, path in _git_name_status(f"{BASELINE_SHA}..HEAD"):
        if status == "A":
            assert path in remove, f"COG-2-added file missing from manifest.remove: {path}"
        elif status == "M":
            assert path in (restore | retain), \
                f"COG-2-modified file missing from manifest.restore/retain: {path}"


def test_manifest_covers_unit5_working_tree_files():
    # The unit-5 files are working-tree-only during this wave (not in
    # baseline..HEAD), so pin them statically. Every unit-5 new file is a remove;
    # every unit-5-modified pre-existing file is a restore.
    manifest = yaml.safe_load(ROLLBACK.read_text())
    remove = set(manifest["remove"])
    restore = set(manifest["restore_from_baseline"])
    assert REMOVE_UNIT5 <= remove
    assert RESTORE_UNIT5 <= restore


# ---------------------------------------------------------------------------
# review-scope tool: EXPECTED_SCOPE == manifest derivation (clones phase-1)
# ---------------------------------------------------------------------------

def _load_tool():
    spec = importlib.util.spec_from_file_location("cog2_scope", ROOT / TOOL_REL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tool_expected_scope_matches_manifest_derivation():
    mod = _load_tool()
    manifest = yaml.safe_load(ROLLBACK.read_text())
    derived = (set(manifest["remove"]) - {mod.REVIEW_ARTIFACT}) | set(manifest["restore_from_baseline"])
    assert set(mod.EXPECTED_SCOPE) == derived
    assert mod.REVIEW_ARTIFACT == REVIEW_ARTIFACT_REL
    assert mod.REVIEW_ARTIFACT not in mod.EXPECTED_SCOPE
    # the append-only operative ledgers are NEVER bound (they take the later flips)
    assert "docs/plans/operative-egg-ledger-2026-07-07.yml" not in mod.EXPECTED_SCOPE
    assert "docs/plans/operative-egg-plan-2026-07-07.md" not in mod.EXPECTED_SCOPE
    # self-binding teeth: the tool AND the manifest are in their own scope
    assert TOOL_REL in mod.EXPECTED_SCOPE
    assert "docs/plans/cognitive-core-phase-2-rollback-manifest-2026-07-22.yml" in mod.EXPECTED_SCOPE


# ---------------------------------------------------------------------------
# digest determinism + TEETH (always-on: bootstraps the full scope in a worktree)
# ---------------------------------------------------------------------------

def _digest_of(tree: Path) -> str:
    proc = subprocess.run([sys.executable, str(tree / TOOL_REL), "--print"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    assert re.fullmatch(r"[0-9a-f]{64}", out), (out, proc.stderr)
    return out


def _commit_all(wt: Path, msg: str) -> None:
    # -f: review artifacts under shared/interfaces/**/*.md are gitignored by
    # default (.gitignore:173) and force-added at landing (the phase-1
    # precedent). The bootstrap must force-add too, or a gitignored in-scope
    # artifact not yet in HEAD (e.g. the FW-019 cp1) never reaches the worktree
    # HEAD and review-scope --print BLOCKs on an absent scope path.
    subprocess.run(["git", "-C", str(wt), "add", "-A", "-f"], check=True, capture_output=True, text=True)
    # Tolerate an already-clean tree: once the scope files are all committed the
    # bootstrap copy produces no delta. Only commit when there is something staged.
    staged = subprocess.run(["git", "-C", str(wt), "status", "--porcelain"],
                            check=True, capture_output=True, text=True).stdout.strip()
    if staged:
        subprocess.run(["git", "-C", str(wt), "-c", "user.email=t@t", "-c", "user.name=t",
                        "-c", "commit.gpgsign=false", "commit", "-m", msg],
                       check=True, capture_output=True, text=True)


def test_review_scope_binding_is_deterministic_and_has_teeth(tmp_path):
    # The unit-5 scope files are working-tree-only this wave, so bootstrap them
    # into a throwaway worktree (commit them there) to exercise the FULL scope
    # digest now — determinism + teeth + end-to-end --verify BLOCK.
    mod = _load_tool()
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach", str(wt), "HEAD"],
                   check=True, capture_output=True, text=True)
    try:
        # Any in-scope file absent from HEAD (the unit-5 new files) is copied from
        # the working tree so the FULL scope digest resolves.
        for rel in sorted(mod.EXPECTED_SCOPE):
            if (wt / rel).exists():
                continue
            src = ROOT / rel
            if not src.exists():
                pytest.skip(f"scope file not yet present in the tree: {rel}")
            dst = wt / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        _commit_all(wt, "stage uncommitted scope")
        base = _digest_of(wt)
        assert _digest_of(wt) == base, "digest is not deterministic over identical bytes"
        # TEETH: mutate ONE in-scope impl path and COMMIT -> digest changes.
        victim = wt / "framework/cortex/belief.py"
        victim.write_text(victim.read_text(encoding="utf-8") + "\n# teeth probe\n",
                          encoding="utf-8")
        _commit_all(wt, "teeth")
        assert _digest_of(wt) != base, \
            "binding has NO teeth: an in-scope mutation left the digest unchanged"
        # end-to-end --verify BLOCKS when the artifact records the pre-mutation digest.
        art = wt / REVIEW_ARTIFACT_REL
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_text("Verdict: PASS\nReviewed-Scope-Digest: " + base + "\n", encoding="utf-8")
        v = subprocess.run([sys.executable, str(wt / TOOL_REL), "--verify", REVIEW_ARTIFACT_REL],
                           capture_output=True, text=True)
        assert v.returncode != 0, "verify must BLOCK on a stale recorded digest"
        assert "reviewed bytes != tested bytes" in v.stderr, v.stderr
    finally:
        subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force", str(wt)],
                       check=False, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# rehearsal wiring (clones test_rehearsal_runs_identical_a13_assertion...)
# ---------------------------------------------------------------------------

def _load_rehearsal():
    spec = importlib.util.spec_from_file_location("cog2_rehearsal", ROOT / REHEARSAL_REL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _extract_verify_a13() -> str:
    lines = (ROOT / VERIFY_REL).read_text(encoding="utf-8").splitlines()
    start = lines.index("python3.12 - <<'PY'") + 1
    end = lines.index("PY", start)
    return "\n".join(lines[start:end])


def test_rehearsal_runs_a13_assertion_on_inverse_tree():
    rehearsal = _load_rehearsal()
    # byte-identity: the rehearsal's A13 assertion is the SAME source
    # verify-cognitive-phase2.sh runs via its `<<'PY'` heredoc — no silent drift.
    assert rehearsal.A13_ASSERTION.strip() == _extract_verify_a13().strip()
    proc = subprocess.run(["python3.12", "-c", rehearsal.A13_ASSERTION],
                          cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    # wiring: the rehearsal runs A13 on the inverse tree AFTER the inverse-diff
    # check and BEFORE ledger-status-parity.sh (same order the phase-0/1 twins pin).
    src = (ROOT / REHEARSAL_REL).read_text(encoding="utf-8")
    call_idx = src.index('run(["python3.12", "-c", A13_ASSERTION], cwd=scratch)')
    diff_idx = src.index("inverse diff is not append-only-only")
    parity_idx = src.index('run(["bash", "cabinet/scripts/ledger-status-parity.sh"], cwd=scratch)')
    assert diff_idx < call_idx < parity_idx


def test_rehearsal_declares_baseline_and_retained_surfaces():
    rehearsal = _load_rehearsal()
    assert rehearsal.EXPECTED_RETAINED == EXPECTED_RETAIN
    manifest = yaml.safe_load(ROLLBACK.read_text())
    assert manifest["baseline_sha"] == BASELINE_SHA


def test_a13_assertion_has_teeth_on_id_set_drift(tmp_path):
    rehearsal = _load_rehearsal()
    ledger_rel = "docs/plans/operative-egg-ledger-2026-07-07.yml"
    plan_rel = "docs/plans/operative-egg-plan-2026-07-07.md"
    (tmp_path / "docs/plans").mkdir(parents=True)
    real_ledger = (ROOT / ledger_rel).read_text(encoding="utf-8")
    real_plan = (ROOT / plan_rel).read_text(encoding="utf-8")
    # (a) plan/ledger id-set drift: a fabricated plan row absent from the ledger
    (tmp_path / ledger_rel).write_text(real_ledger, encoding="utf-8")
    (tmp_path / plan_rel).write_text(real_plan + "\n| COG-99 | x | y |\n", encoding="utf-8")
    drift = subprocess.run(["python3.12", "-c", rehearsal.A13_ASSERTION],
                           cwd=tmp_path, capture_output=True, text=True)
    assert drift.returncode != 0 and "COG-99" in drift.stderr
    # (b) duplicate ledger id
    data = yaml.safe_load(real_ledger)
    data["entries"].append(dict(data["entries"][0]))
    (tmp_path / ledger_rel).write_text(yaml.safe_dump(data), encoding="utf-8")
    (tmp_path / plan_rel).write_text(real_plan, encoding="utf-8")
    dup = subprocess.run(["python3.12", "-c", rehearsal.A13_ASSERTION],
                         cwd=tmp_path, capture_output=True, text=True)
    assert dup.returncode != 0 and "duplicate operative ledger ids" in dup.stderr
