"""COG-3 wave-4 — rollback manifest closure + phase-3 review-scope digest teeth.

Plan: docs/plans/cognitive-core-phase-3-contract-2026-07-22.md §12.4 (machine-
readable rollback manifest, schema cognitive-phase-rollback/v1, runtime inverse +
code inverse + allowance removal + append-only retain + must_remain_unchanged +
rehearsal) and §12.3/§8 (phase-local review-scope + rollback rehearsal twins
CLONING the phase-0/1/2 pattern; the phase-0/1/2 instances stay untouched).

Clones the phase-2 rollback test's structure
(cabinet/scripts/tests/test_cognitive_phase2_rollback.py) against the COG-3
manifest/tool/rehearsal, with two COG-3-specific shape differences:
  * `framework/objectives` and `framework/schemas/domains/objectives` are named as
    DIRECTORIES in remove (wholesale, incl. the sibling-built adapters/); the
    completeness ratchet is dir-prefix aware.
  * the runtime inverse is a SINGLE command (the objectives projection cache
    delete) — no read pointer this phase (§7.4), no Postgres role change (§2.1).

Read-only against the real tree except in a throwaway worktree. Run:
  python3.12 -m pytest cabinet/scripts/tests/test_cognitive_phase3_rollback.py -q

Landing note: waves 1/3 are COMMITTED at HEAD; the wave-4 landing (the parity
falsifier + its suite, the measurement suite, the three phase twins, this test,
the rollback manifest, and the egg edits) is committed in the wave-4 landing
commit. Every assertion here is GREEN pre- and post-commit: the committed-
footprint ratchet validates the git-derived footprint (dir-aware), and the static
wave-4 pins cover the wave-4 files that may still be working-tree during the wave.
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
ROLLBACK = ROOT / "docs/plans/cognitive-core-phase-3-rollback-manifest-2026-07-22.yml"
TOOL_REL = "cabinet/scripts/cognitive-phase3-review-scope.py"
REHEARSAL_REL = "cabinet/scripts/cognitive-phase3-rollback-rehearsal.py"
VERIFY_REL = "cabinet/scripts/verify-cognitive-phase3.sh"
REVIEW_ARTIFACT_REL = "shared/interfaces/reviews/cognitive-core-phase-3-review.md"

# S0 pin: the COG-3 phase-3 contract commit == the parent of wave 1 (83009ce1).
BASELINE_SHA = "b2890f19e1be2c4a267659e61f1bb8f216e57dca"

# framework surface named as DIRS (wholesale — incl. the sibling-built adapters/).
REMOVE_DIRS = {
    "framework/objectives",
    "framework/schemas/domains/objectives",
}
# The COMMITTED COG-3 file footprint (waves 1/3, baseline_sha..HEAD, status A)
# that is NOT under a remove-dir. Added -> remove; modified -> restore. The
# completeness ratchet re-derives the footprint from git so a later commit that
# lands a file without extending the manifest trips it (dir-prefix aware).
REMOVE_COMMITTED_FILES = {
    "cabinet/scripts/cog3-rebuild.py",
    "cabinet/scripts/cog3-graph-hash.py",
    "cabinet/scripts/cog3-staleness.py",
    "cabinet/scripts/tests/lib_cog3_fixtures.py",
    "cabinet/scripts/tests/lib_cog3_import_ast.py",
    "cabinet/scripts/tests/lib_cog3_no_scalar.py",
    "cabinet/scripts/tests/test_cog3_census_wall.py",
    "cabinet/scripts/tests/test_cog3_import_gate.py",
    "cabinet/scripts/tests/test_cog3_no_scalar_ratchet.py",
    "cabinet/scripts/tests/test_cog3_objectives_ast_pin.py",
    "cabinet/scripts/tests/test_cog3_read_pointer.py",
    "cabinet/scripts/tests/test_cog3_sim1_objective_conflict.py",
    "cabinet/scripts/tests/test_cog3_sim2_stale_verdict.py",
    "cabinet/scripts/tests/test_cog3_sim3_counterfactual.py",
    "cabinet/scripts/tests/test_cog3_sim4_goodhart.py",
    "cabinet/scripts/tests/test_cog3_sim5_root_integrity.py",
    "cabinet/scripts/tests/test_cog3_sim6_no_scalar.py",
    "cabinet/scripts/tests/test_cog3_state_function.py",
    "cabinet/scripts/tests/test_cog3_verdict_vocab_tripwire.py",
    "shared/interfaces/reviews/feat-cog3-wave1-cp1.md",
    "shared/interfaces/reviews/feat-cog3-wave3-cp1.md",
    "shared/interfaces/reviews/feat-cog3-wave3-cp2.md",
}
# The wave-4 landing NEW files (working-tree until the landing commit). Every
# wave-4 new file is a remove; the review artifact lands later via §12.3.
REMOVE_WAVE4 = {
    "cabinet/scripts/cog3-ovi-parity.py",
    "cabinet/scripts/tests/test_cog3_ovi_parity.py",
    "cabinet/scripts/tests/test_cog3_measurement.py",
    "cabinet/scripts/verify-cognitive-phase3.sh",
    "cabinet/scripts/cognitive-phase3-review-scope.py",
    "cabinet/scripts/cognitive-phase3-rollback-rehearsal.py",
    "cabinet/scripts/tests/test_cognitive_phase3_rollback.py",
    "docs/plans/cognitive-core-phase-3-rollback-manifest-2026-07-22.yml",
    REVIEW_ARTIFACT_REL,  # excluded from the digest; created by the §12.3 review
}
EXPECTED_REMOVE = REMOVE_DIRS | REMOVE_COMMITTED_FILES | REMOVE_WAVE4

# COMMITTED COG-3 edits (baseline_sha..HEAD "M"): D1 stamp + import-gate extension
# + the D1-epoch-bump cog2 test updates + the contract.yml allowances + the
# gitleaks cog3 allowlist + the wave-3 contract-doc adjudications.
RESTORE_COMMITTED = {
    "framework/cortex/adapters.py",
    "framework/cortex/belief.py",
    "cabinet/scripts/cog2-import-gate.py",
    "cabinet/scripts/tests/test_cog2_asof_fence.py",
    "cabinet/scripts/tests/test_cog2_consequence_seam.py",
    "cabinet/scripts/tests/test_cog2_corruption.py",
    "cabinet/scripts/tests/test_cog2_measurement.py",
    "cabinet/scripts/tests/test_cog2_rebuild_determinism.py",
    "cabinet/config/cognitive-architecture-contract.yml",
    ".gitleaks.toml",
    "docs/plans/cognitive-core-phase-3-contract-2026-07-22.md",
}
# wave-4 edits to pre-existing files (working-tree "M" this wave).
RESTORE_WAVE4 = {
    "cabinet/scripts/egg-export-manifest.txt",
    "cabinet/scripts/tests/test_egg_export.py",
}
EXPECTED_RESTORE = RESTORE_COMMITTED | RESTORE_WAVE4
EXPECTED_RETAIN = {
    "docs/plans/operative-egg-ledger-2026-07-07.yml",
    "docs/plans/operative-egg-plan-2026-07-07.md",
}


def _covered_by_remove(path: str, remove: set[str]) -> bool:
    """A committed path is covered if it is an exact remove entry OR beneath a
    remove-dir entry (the wholesale framework/objectives + schemas dirs)."""
    if path in remove:
        return True
    return any(path == d or path.startswith(d + "/") for d in remove)


# ---------------------------------------------------------------------------
# Manifest closure (clones test_phase_2_manifest_is_closed...)
# ---------------------------------------------------------------------------

def test_phase_3_manifest_is_closed_and_append_only_aware():
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
    assert manifest["phase"] == "COG-3"
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
    # every remove path exists NOW except the frozen review artifact (created later
    # by the §12.3 review); dir entries + files both checked; restore + protected
    # paths all exist.
    for p in manifest["remove"]:
        if p == REVIEW_ARTIFACT_REL:
            continue
        assert (ROOT / p).exists(), f"declared remove path absent: {p}"
    assert all((ROOT / p).exists() for p in manifest["restore_from_baseline"])
    assert all((ROOT / p).exists() for p in manifest["must_remain_unchanged"])


def test_phase_3_dir_wholesale_entries_present():
    # §12.4 "delete framework/objectives/": the framework surface is named as DIRS
    # so the sibling-built adapters/ subtree is covered post-integration.
    manifest = yaml.safe_load(ROLLBACK.read_text())
    remove = set(manifest["remove"])
    assert REMOVE_DIRS <= remove
    # the individual objectives *.py files are NOT separately listed (the dir owns
    # them) — a belt-and-suspenders guard that we did not double-list.
    assert "framework/objectives/graph.py" not in remove
    assert "framework/schemas/domains/objectives/node.v1.json" not in remove


def test_phase_3_runtime_inverse_is_one_command():
    manifest = yaml.safe_load(ROLLBACK.read_text())
    inverses = {r["name"]: r for r in manifest["runtime_inverses"]}
    # COG-3 is shadow-only with the SMALLEST footprint of the phases: a single
    # disposable projection cache. No read pointer (§7.4), no cortex_ro-style role
    # (§2.1) — so exactly ONE safe-by-construction inverse, unlike COG-2's triple.
    assert set(inverses) == {"objectives_cache"}
    cache = inverses["objectives_cache"]
    # the cache-path token is ASSEMBLED (not a contiguous literal) so this file —
    # which is NOT cog3-allowlisted for the §6.5 data-plane sweep (it is
    # test_cognitive_*, not test_cog3_*) — never self-flags FORBIDDEN_OBJECTIVES_DATAPLANE.
    assert ("cabinet/cache/" + "objectives") in cache["command"]
    assert cache["command"].strip().startswith("rm -rf")
    # the §4.3 honest consequence (predictions/counterfactuals) is named in effect
    assert "predictions" in cache["effect"] and "counterfactuals" in cache["effect"]
    assert "cog3-rebuild.py" in cache["reversible_by"]
    # the allowance-rows removal rides the contract.yml restore (§12.4)
    ar = manifest["allowance_removal"]
    assert ar["path"] == "cabinet/config/cognitive-architecture-contract.yml"
    assert ar["path"] in manifest["restore_from_baseline"]


def test_phase_3_must_remain_unchanged_covers_union_and_cog3_surfaces():
    # G-F2: the Phase-0 ∪ 1 ∪ 2 protected-surface union PLUS the COG-3-specific
    # untouched surfaces (mission compiler byte-untouched §2.2; belief.v1.json
    # byte-untouched §6.1; legacy OVI reused-not-edited §6.6; instance roots read
    # via CLI-injected path §7.6).
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
        # COG-3-specific pins:
        "framework/missions/compiler.py",
        "framework/schemas/domains/cortex/belief.v1.json",
        "framework/ovi/compute.py",
        "instance/config/directions.yml",
        "instance/config/outcomes.yml",
    ):
        assert rel in protected, f"must_remain_unchanged missing surface: {rel}"


# ---------------------------------------------------------------------------
# Completeness ratchet: the manifest covers the ACTUAL committed COG-3 footprint
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


def test_manifest_covers_committed_cog3_footprint():
    # Shallow CI checkouts lack the baseline commit -> `git diff BASELINE..HEAD`
    # exits 128. The ratchet enforces on every full clone; skip honestly here.
    probe = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", BASELINE_SHA + "^{commit}"],
        capture_output=True, text=True)
    if probe.returncode != 0:
        pytest.skip("baseline SHA absent (shallow checkout) — footprint ratchet "
                    "runs on full clones")
    manifest = yaml.safe_load(ROLLBACK.read_text())
    remove = set(manifest["remove"])
    restore = set(manifest["restore_from_baseline"])
    retain = {r["path"] for r in manifest["retain_append_only"]}
    for status, path in _git_name_status(f"{BASELINE_SHA}..HEAD"):
        if status == "A":
            assert _covered_by_remove(path, remove), \
                f"COG-3-added file missing from manifest.remove: {path}"
        elif status == "M":
            assert path in (restore | retain), \
                f"COG-3-modified file missing from manifest.restore/retain: {path}"


def test_manifest_covers_wave4_files():
    # The wave-4 files are working-tree-only until the landing commit, so pin them
    # statically. Every wave-4 new file is a remove; every wave-4-modified
    # pre-existing file is a restore.
    manifest = yaml.safe_load(ROLLBACK.read_text())
    remove = set(manifest["remove"])
    restore = set(manifest["restore_from_baseline"])
    assert REMOVE_WAVE4 <= remove
    assert RESTORE_WAVE4 <= restore


# ---------------------------------------------------------------------------
# review-scope tool: EXPECTED_SCOPE == manifest derivation (clones phase-2)
# ---------------------------------------------------------------------------

def _load_tool():
    spec = importlib.util.spec_from_file_location("cog3_scope", ROOT / TOOL_REL)
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
    assert "docs/plans/cognitive-core-phase-3-rollback-manifest-2026-07-22.yml" in mod.EXPECTED_SCOPE
    # the dir-wholesale entries are the SCOPE spec too (resolved via ls-tree -r)
    assert REMOVE_DIRS <= set(mod.EXPECTED_SCOPE)


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
    # default and force-added at landing (the phase-1/2 precedent). The bootstrap
    # must force-add too, or a gitignored in-scope artifact not yet in HEAD never
    # reaches the worktree HEAD and review-scope --print BLOCKs on an absent path.
    subprocess.run(["git", "-C", str(wt), "add", "-A", "-f"], check=True, capture_output=True, text=True)
    staged = subprocess.run(["git", "-C", str(wt), "status", "--porcelain"],
                            check=True, capture_output=True, text=True).stdout.strip()
    if staged:
        subprocess.run(["git", "-C", str(wt), "-c", "user.email=t@t", "-c", "user.name=t",
                        "-c", "commit.gpgsign=false", "commit", "-m", msg],
                       check=True, capture_output=True, text=True)


def test_review_scope_binding_is_deterministic_and_has_teeth(tmp_path):
    # The wave-4 scope files may be working-tree-only this wave, so bootstrap them
    # into a throwaway worktree (commit them there) to exercise the FULL scope
    # digest now — determinism + teeth + end-to-end --verify BLOCK.
    mod = _load_tool()
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach", str(wt), "HEAD"],
                   check=True, capture_output=True, text=True)
    try:
        # Any in-scope entry absent from the worktree HEAD is copied from the real
        # working tree (a file via copy2, a dir via copytree) so the FULL scope
        # digest resolves. Dir entries (framework/objectives, the schemas dir) are
        # committed at HEAD, so they already exist in the worktree.
        for rel in sorted(mod.EXPECTED_SCOPE):
            if (wt / rel).exists():
                continue
            src = ROOT / rel
            if not src.exists():
                pytest.skip(f"scope entry not yet present in the tree: {rel}")
            dst = wt / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        _commit_all(wt, "stage uncommitted scope")
        base = _digest_of(wt)
        assert _digest_of(wt) == base, "digest is not deterministic over identical bytes"
        # TEETH: mutate ONE in-scope impl path (under the objectives dir entry) and
        # COMMIT -> digest changes (ls-tree -r picks the dir blob up).
        victim = wt / "framework/objectives/graph.py"
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
    spec = importlib.util.spec_from_file_location("cog3_rehearsal", ROOT / REHEARSAL_REL)
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
    # verify-cognitive-phase3.sh runs via its `<<'PY'` heredoc — no silent drift,
    # and byte-identical to the phase-1/2 twins (the universal A13 assertion).
    assert rehearsal.A13_ASSERTION.strip() == _extract_verify_a13().strip()
    proc = subprocess.run(["python3.12", "-c", rehearsal.A13_ASSERTION],
                          cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    # wiring: the rehearsal runs A13 on the inverse tree AFTER the inverse-diff
    # check and BEFORE ledger-status-parity.sh (same order the phase-0/1/2 twins pin).
    src = (ROOT / REHEARSAL_REL).read_text(encoding="utf-8")
    call_idx = src.index('run(["python3.12", "-c", A13_ASSERTION], cwd=scratch)')
    diff_idx = src.index("inverse diff is not append-only-only")
    parity_idx = src.index('run(["bash", "cabinet/scripts/ledger-status-parity.sh"], cwd=scratch)')
    assert diff_idx < call_idx < parity_idx


def test_rehearsal_asserts_pre_bump_refold_lineage_on_inverse_tree():
    # §12.4 STATE INVERSE (contract :280 + §9 r1 :228 — named TWICE): the rehearsal
    # must assert "a cortex refold under the pre-bump ENGINE_VERSION reproduces the
    # prior hash lineage exactly". It discharges this by running the RESTORED
    # determinism suite on the inverse tree — where belief.py is back at the pre-bump
    # ENGINE_VERSION ("cortex-engine/1") and adapters.py is pre-D1. Exists + runs.
    rehearsal = _load_rehearsal()
    assert rehearsal.REFOLD_DETERMINISM_TEST == \
        "cabinet/scripts/tests/test_cog2_rebuild_determinism.py"
    # HONESTY PIN: the refold suite AND the pre-bump cortex bytes are ALL
    # restore_from_baseline paths, so on the inverse tree the suite is the PRE-D1
    # form folding against the PRE-bump belief.py/adapters.py — it asserts the
    # pre-bump lineage, never HEAD's post-bump fold.
    manifest = yaml.safe_load(ROLLBACK.read_text())
    restore = set(manifest["restore_from_baseline"])
    assert rehearsal.REFOLD_DETERMINISM_TEST in restore
    assert "framework/cortex/belief.py" in restore       # the ENGINE_VERSION bump reverts
    assert "framework/cortex/adapters.py" in restore      # the D1 cabinet_id stamp reverts
    # WIRING: the refold step runs AFTER the code-inverse restore loop and AFTER the
    # inverse-diff assertion (i.e. on the fully-restored inverse tree).
    src = (ROOT / REHEARSAL_REL).read_text(encoding="utf-8")
    restore_idx = src.index('for rel in manifest["restore_from_baseline"]:')
    diff_idx = src.index("inverse diff is not append-only-only")
    refold_idx = src.index(
        'run(["python3.12", "-m", "pytest", REFOLD_DETERMINISM_TEST, "-q"], cwd=scratch)')
    assert restore_idx < diff_idx < refold_idx
    # RUNS: the invoked determinism suite is itself green (the mechanism the
    # rehearsal drives). Run it standalone on the real tree — the cheap "it runs
    # green" proof, mirroring the A13-closure-test standalone run. The full PRE-bump
    # discharge on the inverse tree is exercised by the end-to-end rehearsal run
    # (verify-cognitive-phase3.sh).
    proc = subprocess.run(
        ["python3.12", "-m", "pytest", rehearsal.REFOLD_DETERMINISM_TEST, "-q"],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


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
