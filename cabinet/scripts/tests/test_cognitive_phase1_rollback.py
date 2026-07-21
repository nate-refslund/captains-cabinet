"""COG-1 W5 — rollback manifest closure + phase-1 review-scope digest teeth.

Plan: docs/plans/cognitive-core-phase-1-contract-2026-07-20.md §12.4 (machine-
readable rollback manifest, schema cognitive-phase-rollback/v1, 3 runtime
inverses + code inverse + append-only retain + rehearsal) and §12.3/§10.3
(phase-local review-scope + verify twins CLONING the Phase-0 pattern; the
Phase-0 instances stay untouched — digest-frozen historical).

Clones the Phase-0 rollback test's structure
(cabinet/scripts/tests/test_cognitive_phase0_rollback.py) against the COG-1
manifest/tool/rehearsal. Read-only against the real tree except in a throwaway
worktree. Run:
  python3.12 -m pytest cabinet/scripts/tests/test_cognitive_phase1_rollback.py -q
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
ROLLBACK = ROOT / "docs/plans/cognitive-core-phase-1-rollback-manifest-2026-07-20.yml"
TOOL_REL = "cabinet/scripts/cognitive-phase1-review-scope.py"
REHEARSAL_REL = "cabinet/scripts/cognitive-phase1-rollback-rehearsal.py"
VERIFY_REL = "cabinet/scripts/verify-cognitive-phase1.sh"
REVIEW_ARTIFACT_REL = "shared/interfaces/reviews/cognitive-core-phase-1-review.md"

BASELINE_SHA = "0bf60e698a148616bebc1676119913d11b272535"

# The COG-1 footprint as of W5 (W1-W3 committed-new + my W5 new). Pending waves
# (§9.3 replay-hash tool; the §7/§8.3/§9.4 edits to task_sync_runner.py /
# task-sync-drift-falsifier.py / cabinet-ci.yml) EXTEND remove/restore + re-freeze
# the digest when they land — the completeness test below is the ratchet.
REMOVE_W1_W3 = {
    "cabinet/scripts/tests/lib_cog1_harness.py",
    "cabinet/scripts/tests/test_cog1_outbox_capture.py",
    "cabinet/sql/047-officer-tasks-outbox.sql",
    "framework/outbox/tests/lib_relay_harness.py",
    "framework/outbox/tests/test_effective_mapping.py",
    "framework/outbox/tests/test_outbox_relay_wrapper.py",
    "framework/outbox/tests/test_relay_fencing.py",
    "framework/outbox/tests/test_relay_table_drain.py",
    # F1 seam rig (landed 2026-07-21 under §12.3 re-review)
    "framework/outbox/tests/test_relay_live_target.py",
    "framework/schemas/domains/tasks/task-event.v1.json",
    "framework/triggers/schema_registry.py",
    "framework/triggers/tests/test_envelope_v2.py",
    "framework/triggers/tests/test_schema_registry.py",
    "shared/interfaces/reviews/feat-cog1-impl-cp1.md",
    "shared/interfaces/reviews/feat-cog1-impl-cp2.md",
    "shared/interfaces/reviews/feat-cog1-impl-cp3.md",
    # cp4/cp5 were minted by the W4/W5 commit step AFTER this file was authored
    "shared/interfaces/reviews/feat-cog1-impl-cp4.md",
    "shared/interfaces/reviews/feat-cog1-impl-cp5.md",
}
# W4 (fencing §7 / parity §8.3 / replay-hash §9.3) landed concurrently in this
# shared tree; folded into the W5-owned manifest for a complete phase rollback
# (W4 cannot edit this manifest). If W4's set drifts, the committed-footprint
# ratchet below catches it.
REMOVE_W4 = {
    "cabinet/scripts/cog1-replay-hash.py",
    "cabinet/scripts/tests/test_cog1_replay_hash.py",
    "cabinet/scripts/tests/test_cog1_fencing.py",
    "cabinet/scripts/tests/test_cog1_parity.py",
}
REMOVE_W5 = {
    "cabinet/scripts/cog1-authority-flip.sh",
    "cabinet/scripts/verify-cognitive-phase1.sh",
    "cabinet/scripts/cognitive-phase1-review-scope.py",
    "cabinet/scripts/cognitive-phase1-rollback-rehearsal.py",
    "cabinet/scripts/tests/test_cog1_cutover.py",
    "cabinet/scripts/tests/test_cognitive_phase1_rollback.py",
    "docs/plans/cognitive-core-phase-1-rollback-manifest-2026-07-20.yml",
    REVIEW_ARTIFACT_REL,   # excluded from the digest; created by the §12.3 review
}
EXPECTED_REMOVE = REMOVE_W1_W3 | REMOVE_W4 | REMOVE_W5
RESTORE_W1_W3 = {
    "cabinet/config/cognitive-architecture-contract.yml",
    "cabinet/cron/outbox-relay.sh",
    "cabinet/scripts/load-preset.sh",
    "framework/outbox/relay.py",
    "framework/triggers/envelope.py",
    "docs/plans/cognitive-core-phase-1-contract-2026-07-20.md",
}
RESTORE_W4 = {
    "cabinet/scripts/task_sync_runner.py",
    "cabinet/scripts/task-sync-drift-falsifier.py",
}
RESTORE_W5 = {
    "cabinet/scripts/my-tasks.sh",
    "cabinet/scripts/task-events-watch.py",
    "cabinet/scripts/egg-export-manifest.txt",
    "cabinet/scripts/tests/test_egg_export.py",
    # W6 (CI edit, own commit) — added when W6 landed after this file was authored
    ".github/workflows/cabinet-ci.yml",
}
EXPECTED_RESTORE = RESTORE_W1_W3 | RESTORE_W4 | RESTORE_W5
EXPECTED_RETAIN = {
    "docs/plans/operative-egg-ledger-2026-07-07.yml",
    "docs/plans/operative-egg-plan-2026-07-07.md",
}


# ---------------------------------------------------------------------------
# Manifest closure (clones test_phase_0_inverse_manifest_is_closed...)
# ---------------------------------------------------------------------------

def test_phase_1_manifest_is_closed_and_append_only_aware():
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
    assert manifest["phase"] == "COG-1"
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


def test_phase_1_three_runtime_inverses_are_one_command_each():
    manifest = yaml.safe_load(ROLLBACK.read_text())
    inverses = {r["name"]: r for r in manifest["runtime_inverses"]}
    assert set(inverses) == {"authority", "capture_emergency", "drain"}
    # authority + capture inverses are the flip script's verbs; drain is bootout.
    assert inverses["authority"]["command"].endswith("cog1-authority-flip.sh legacy")
    assert inverses["authority"]["reversible_by"].endswith("cog1-authority-flip.sh outbox")
    assert "cog1-authority-flip.sh disarm" in inverses["capture_emergency"]["command"]
    assert "DISABLE TRIGGER trg_officer_tasks_outbox_capture" in inverses["capture_emergency"]["effect"]
    assert inverses["capture_emergency"]["reversible_by"].endswith("cog1-authority-flip.sh enable")
    assert "launchctl bootout" in inverses["drain"]["command"]
    assert "com.cabinet.outbox-relay" in inverses["drain"]["command"]
    # the allowance-rows removal rides the contract.yml restore (§12.4)
    ar = manifest["allowance_removal"]
    assert ar["path"] == "cabinet/config/cognitive-architecture-contract.yml"
    assert ar["path"] in manifest["restore_from_baseline"]


def test_phase_1_must_remain_unchanged_covers_phase0_protected_surfaces():
    # COG-1 touches none of these either — Phase-0's promise is preserved (§10.2).
    manifest = yaml.safe_load(ROLLBACK.read_text())
    protected = set(manifest["must_remain_unchanged"])
    for rel in ("cabinet/services.yml", "framework/events/emitter.py",
                "framework/authority/classifier.py"):
        assert rel in protected


# ---------------------------------------------------------------------------
# Completeness ratchet: the manifest covers the ACTUAL committed COG-1 footprint
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


def test_manifest_covers_committed_cog1_footprint():
    # Shallow CI checkouts (actions/checkout default) lack the baseline
    # commit -> `git diff BASELINE..HEAD` exits 128. The ratchet enforces on
    # every full clone (local batteries + the phase gate); skip honestly here.
    probe = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", BASELINE_SHA + "^{commit}"],
        capture_output=True, text=True)
    if probe.returncode != 0:
        pytest.skip("baseline SHA absent (shallow checkout) — footprint ratchet "
                    "runs on full clones")
    # Deterministic (no working-tree scan -> no other-wave interference): every
    # file COG-1 changed between baseline and HEAD is classified. A -> remove;
    # M -> restore or retain. A later wave that lands a file without extending
    # the manifest trips this immediately.
    manifest = yaml.safe_load(ROLLBACK.read_text())
    remove = set(manifest["remove"])
    restore = set(manifest["restore_from_baseline"])
    retain = {r["path"] for r in manifest["retain_append_only"]}
    for status, path in _git_name_status(f"{BASELINE_SHA}..HEAD"):
        if status == "A":
            assert path in remove, f"COG-1-added file missing from manifest.remove: {path}"
        elif status == "M":
            assert path in (restore | retain), \
                f"COG-1-modified file missing from manifest.restore/retain: {path}"


def test_manifest_covers_w5_working_tree_files():
    # My W5 files are working-tree-only during this wave (not in baseline..HEAD),
    # so pin them statically. Every W5 new file is a remove; every W5 modified
    # file is a restore.
    manifest = yaml.safe_load(ROLLBACK.read_text())
    remove = set(manifest["remove"])
    restore = set(manifest["restore_from_baseline"])
    assert REMOVE_W5 <= remove
    assert RESTORE_W5 <= restore


# ---------------------------------------------------------------------------
# review-scope tool: EXPECTED_SCOPE == manifest derivation (clones phase-0)
# ---------------------------------------------------------------------------

def _load_tool():
    spec = importlib.util.spec_from_file_location("cog1_scope", ROOT / TOOL_REL)
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
    assert "docs/plans/cognitive-core-phase-1-rollback-manifest-2026-07-20.yml" in mod.EXPECTED_SCOPE


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
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True, capture_output=True, text=True)
    # Tolerate an already-clean tree: after Commit-C the scope files are all
    # committed, so the bootstrap copy produces no delta (the test predates
    # that commit). Only commit when there is something staged.
    staged = subprocess.run(["git", "-C", str(wt), "status", "--porcelain"],
                            check=True, capture_output=True, text=True).stdout.strip()
    if staged:
        subprocess.run(["git", "-C", str(wt), "-c", "user.email=t@t", "-c", "user.name=t",
                        "-c", "commit.gpgsign=false", "commit", "-m", msg],
                       check=True, capture_output=True, text=True)


def test_review_scope_binding_is_deterministic_and_has_teeth(tmp_path):
    # The W5 new scope files are working-tree-only this wave, so bootstrap them
    # into a throwaway worktree (commit them there) to exercise the FULL scope
    # digest now — determinism + teeth + end-to-end --verify BLOCK.
    mod = _load_tool()
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach", str(wt), "HEAD"],
                   check=True, capture_output=True, text=True)
    try:
        # Any in-scope file absent from HEAD (W5 + concurrently-landing W4 new
        # files) is copied from the working tree so the FULL scope digest resolves.
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
        victim = wt / "cabinet/sql/047-officer-tasks-outbox.sql"
        victim.write_text(victim.read_text(encoding="utf-8") + "\n-- teeth probe\n",
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
    spec = importlib.util.spec_from_file_location("cog1_rehearsal", ROOT / REHEARSAL_REL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _extract_verify_a13() -> str:
    lines = (ROOT / VERIFY_REL).read_text(encoding="utf-8").splitlines()
    start = lines.index("python3.12 - <<'PY'") + 1
    end = lines.index("PY", start)
    return "\n".join(lines[start:end])


def test_rehearsal_runs_identical_a13_assertion_on_inverse_tree():
    rehearsal = _load_rehearsal()
    # byte-identity: the rehearsal's A13 assertion is the SAME source
    # verify-cognitive-phase1.sh runs via its `<<'PY'` heredoc — no silent drift.
    assert rehearsal.A13_ASSERTION.strip() == _extract_verify_a13().strip()
    proc = subprocess.run(["python3.12", "-c", rehearsal.A13_ASSERTION],
                          cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    # wiring: the rehearsal runs A13 on the inverse tree AFTER the inverse-diff
    # check and BEFORE ledger-status-parity.sh (same order phase-0 pins).
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
