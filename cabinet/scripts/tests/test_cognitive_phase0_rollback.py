import importlib.util
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
ROLLBACK = ROOT / "docs/plans/cognitive-core-phase-0-rollback-manifest-2026-07-19.yml"
TOOL_REL = "cabinet/scripts/cognitive-phase0-review-scope.py"
REHEARSAL_REL = "cabinet/scripts/cognitive-phase0-rollback-rehearsal.py"
VERIFY_REL = "cabinet/scripts/verify-cognitive-phase0.sh"
REVIEW_ARTIFACT_REL = "shared/interfaces/reviews/codex-cognitive-foundry-masterplan-cp1.md"


def test_phase_0_inverse_manifest_is_closed_and_append_only_aware():
    manifest = yaml.safe_load(ROLLBACK.read_text())
    assert set(manifest) == {
        "schema_version",
        "phase",
        "baseline_sha",
        "remove",
        "restore_from_baseline",
        "retain_append_only",
        "must_remain_unchanged",
        "rehearsal",
    }
    assert manifest["schema_version"] == "cognitive-phase-rollback/v1"
    assert manifest["phase"] == "COG-0"
    assert manifest["baseline_sha"] == "8f9c555d2064d55a159a53fcedd6df33434a9291"
    all_paths = manifest["remove"] + manifest["restore_from_baseline"]
    assert len(all_paths) == len(set(all_paths))
    assert all(not Path(item).is_absolute() and ".." not in Path(item).parts for item in all_paths)
    assert set(manifest["remove"]) == {
        "cabinet/config/cognitive-architecture-contract.yml",
        "cabinet/scripts/cognitive-architecture-census.py",
        "cabinet/scripts/cognitive-phase0-review-scope.py",
        "cabinet/scripts/cognitive-phase0-rollback-rehearsal.py",
        "cabinet/scripts/tests/test_cognitive_architecture_census.py",
        "cabinet/scripts/tests/test_cognitive_phase0_rollback.py",
        "cabinet/scripts/verify-cognitive-architecture.sh",
        "cabinet/scripts/verify-cognitive-phase0.sh",
        "docs/cognitive-core-foundry.md",
        "docs/plans/cognitive-core-phase-0-contract-2026-07-19.md",
        "docs/plans/cognitive-core-phase-0-rollback-manifest-2026-07-19.yml",
        "framework/evolution/__init__.py",
        "framework/evolution/contracts.py",
        "framework/evolution/tests/__init__.py",
        "framework/evolution/tests/test_contracts.py",
        "framework/schemas/cognitive-trajectory.schema.json",
        "framework/schemas/holdout-evaluation-receipt.schema.json",
        "shared/interfaces/reviews/codex-cognitive-foundry-masterplan-cp1.md",
    }
    assert set(manifest["restore_from_baseline"]) == {
        "cabinet/scripts/egg-export-manifest.txt",
        "cabinet/scripts/null-hatch.sh",
        "cabinet/scripts/tests/test_egg_export.py",
    }
    retained = {row["path"]: row for row in manifest["retain_append_only"]}
    assert set(retained) == {
        "docs/plans/operative-egg-ledger-2026-07-07.yml",
        "docs/plans/operative-egg-plan-2026-07-07.md",
    }
    expected_rows = [f"COG-{index}" for index in range(9)]
    assert all(row["rows"] == expected_rows for row in retained.values())
    assert all((ROOT / path).exists() for path in manifest["must_remain_unchanged"])
    assert all((ROOT / path).exists() for path in manifest["remove"])


def _load_tool():
    spec = importlib.util.spec_from_file_location("cog0_scope", ROOT / TOOL_REL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tool_expected_scope_matches_manifest_derivation():
    # Pure (no git): the tool's hard-coded EXPECTED_SCOPE must equal the scope
    # DERIVED from the manifest, and must exclude the artifact + both ledgers.
    mod = _load_tool()
    manifest = yaml.safe_load(ROLLBACK.read_text())
    derived = (set(manifest["remove"]) - {mod.REVIEW_ARTIFACT}) | set(manifest["restore_from_baseline"])
    assert set(mod.EXPECTED_SCOPE) == derived
    assert len(mod.EXPECTED_SCOPE) == 20
    assert mod.REVIEW_ARTIFACT not in mod.EXPECTED_SCOPE
    assert "docs/plans/operative-egg-ledger-2026-07-07.yml" not in mod.EXPECTED_SCOPE
    assert "docs/plans/operative-egg-plan-2026-07-07.md" not in mod.EXPECTED_SCOPE
    # self-binding teeth: the tool AND the manifest are in their own scope
    assert TOOL_REL in mod.EXPECTED_SCOPE
    assert "docs/plans/cognitive-core-phase-0-rollback-manifest-2026-07-19.yml" in mod.EXPECTED_SCOPE


def _scope_committed_at_head() -> bool:
    proc = subprocess.run([sys.executable, str(ROOT / TOOL_REL), "--print"],
                          capture_output=True, text=True)
    return proc.returncode == 0


def _digest_of(tree: Path) -> str:
    proc = subprocess.run([sys.executable, str(tree / TOOL_REL), "--print"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    assert re.fullmatch(r"[0-9a-f]{64}", out), (out, proc.stderr)
    return out


def test_review_scope_binding_is_deterministic_and_has_teeth(tmp_path):
    # Runs post-freeze / in CI (scope committed at HEAD); SKIPS in a pre-freeze
    # working tree where nothing is committed yet.
    if subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--is-inside-work-tree"],
                      capture_output=True).returncode != 0 or not _scope_committed_at_head():
        pytest.skip("Phase-0 scope not committed at HEAD — binding runs post-freeze / in CI")
    base = _digest_of(ROOT)
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach", str(wt), "HEAD"],
                   check=True, capture_output=True, text=True)
    try:
        # determinism: same committed bytes -> same digest
        assert _digest_of(wt) == base
        # TEETH: mutate ONE in-scope impl path and COMMIT it -> digest changes
        victim = wt / "framework/evolution/contracts.py"
        victim.write_text(victim.read_text(encoding="utf-8") + "\n# teeth probe\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(wt), "add", "framework/evolution/contracts.py"],
                       check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(wt), "-c", "user.email=t@t", "-c", "user.name=t",
                        "-c", "commit.gpgsign=false", "commit", "-m", "teeth"],
                       check=True, capture_output=True, text=True)
        assert _digest_of(wt) != base, "binding has NO teeth: impl mutation left the digest unchanged"
        # end-to-end --verify BLOCKS when the artifact records the pre-mutation digest
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


def _load_rehearsal():
    spec = importlib.util.spec_from_file_location("cog0_rehearsal", ROOT / REHEARSAL_REL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _extract_verify_a13() -> str:
    # The A13 assertion verify-cognitive-phase0.sh runs is the heredoc body
    # strictly between the full line `python3.12 - <<'PY'` and the line `PY`.
    lines = (ROOT / VERIFY_REL).read_text(encoding="utf-8").splitlines()
    start = lines.index("python3.12 - <<'PY'") + 1
    end = lines.index("PY", start)
    return "\n".join(lines[start:end])


def test_rehearsal_runs_identical_a13_assertion_on_inverse_tree():
    rehearsal = _load_rehearsal()
    # byte-identity pin: the rehearsal's raw-string assertion is the SAME source
    # verify-cognitive-phase0.sh runs via its `<<'PY'` heredoc — no silent drift.
    assert rehearsal.A13_ASSERTION.strip() == _extract_verify_a13().strip()
    # the shared assertion actually passes on the real committed operative pair
    proc = subprocess.run(["python3.12", "-c", rehearsal.A13_ASSERTION],
                          cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    # wiring: the rehearsal runs it on the inverse tree AFTER the inverse-diff
    # check and BEFORE ledger-status-parity.sh
    src = (ROOT / REHEARSAL_REL).read_text(encoding="utf-8")
    call_idx = src.index('run(["python3.12", "-c", A13_ASSERTION], cwd=scratch)')
    diff_idx = src.index("inverse diff is not append-only-only")
    parity_idx = src.index('run(["bash", "cabinet/scripts/ledger-status-parity.sh"], cwd=scratch)')
    assert diff_idx < call_idx < parity_idx


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
    assert drift.returncode != 0
    assert "COG-99" in drift.stderr, drift.stderr

    # (b) duplicate ledger id
    data = yaml.safe_load(real_ledger)
    data["entries"].append(dict(data["entries"][0]))
    (tmp_path / ledger_rel).write_text(yaml.safe_dump(data), encoding="utf-8")
    (tmp_path / plan_rel).write_text(real_plan, encoding="utf-8")
    dup = subprocess.run(["python3.12", "-c", rehearsal.A13_ASSERTION],
                         cwd=tmp_path, capture_output=True, text=True)
    assert dup.returncode != 0
    assert "duplicate operative ledger ids" in dup.stderr, dup.stderr
