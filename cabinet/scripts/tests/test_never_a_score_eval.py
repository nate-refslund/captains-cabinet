"""Tests for the never-a-score eval harness (EVAL-025) + the pairing rule.

The harness is the mechanical scanner for the NEVER-A-SCORE LAW golden eval
(body: memory/golden-evals/eval-025-never-a-score.md; whole-cabinet evidence
design §2.5, 2026-07-16): evidence-derived aggregates are monitoring metrics
and kill criteria ONLY — never officer-visible scores, never inputs to
generation or selection. These tests pin:
  * the deny tokenizer (score/aggregate/cost/fuel-shaped keys) on both
    polarities, including the pinned exemption path;
  * AST extraction against the REAL recorder.py (the officer projection's
    allow-list and shape are parseable, non-empty, and clean today);
  * the scalar-consumer scan: a synthetic unsanctioned reader is a
    violation; allowlisted references are clean (tmp trees, no git);
  * teeth: an emptied allowlist makes the real repo's own writer an
    unsanctioned consumer and --self-test exits non-zero;
  * the shipped fixture self-test exits 0 (what the golden-eval runner
    invokes on every master push);
  * the PAIRING VALIDATOR: eval body + harness + runner section stay wired
    for EVAL-024-CANDOR and EVAL-025-NEVER-A-SCORE — an eval silently
    unplugged from run-golden-evals.sh is itself a failure.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_DIR = REPO_ROOT / "cabinet" / "evals" / "never-a-score"
HARNESS = EVAL_DIR / "harness.py"
FIXTURES = EVAL_DIR / "fixtures"
RUNNER = REPO_ROOT / "cabinet" / "scripts" / "run-golden-evals.sh"

spec = importlib.util.spec_from_file_location("never_a_score_harness", HARNESS)
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


# --- deny tokenizer -------------------------------------------------------

def test_score_shaped_keys_are_denied():
    for key in ("officer_score", "win_rate", "elo", "cost_usd",
                "input_tokens", "fuel_balance", "graduation_rate",
                "autonomy_level", "avg_latency", "percentile_95",
                "officer_rating", "kpi_total", "success-rate", "mean.time"):
        assert harness.is_score_shaped(key), key


def test_operational_fact_keys_are_allowed():
    for key in ("action", "error_code", "file_count", "total_bytes",
                "retry_count", "before_revision", "manifest_hash",
                "parent_trial_id", "spawned_by", "scheduled_by",
                "trigger_kind", "model_id", "skill_revision",
                "egress_approval_ref", "purge_scope"):
        assert not harness.is_score_shaped(key), key


def test_fixture_vectors_match_classifier():
    fixture = harness.load_fixture(FIXTURES)
    for vector in fixture["deny_vectors"]["denied"]:
        assert harness.is_score_shaped(vector), vector
    for vector in fixture["deny_vectors"]["allowed"]:
        assert not harness.is_score_shaped(vector), vector


# --- AST pins against the real projection --------------------------------

def test_real_projection_allow_list_is_extractable_and_clean_today():
    fn = harness._projection_fn(
        REPO_ROOT / "framework" / "evidence" / "recorder.py")
    allowed = harness.extract_allowed_detail(fn)
    assert "action" in allowed
    fixture = harness.load_fixture(FIXTURES)
    exemptions = fixture["projection"]["detail_key_exemptions"]
    offenders = [k for k in allowed
                 if harness.is_score_shaped(k) and k not in exemptions]
    assert offenders == []


def test_real_projection_shape_matches_pins_and_trust_is_untrusted():
    fn = harness._projection_fn(
        REPO_ROOT / "framework" / "evidence" / "recorder.py")
    top_level, record_keys, trust_value = harness.extract_projection_shape(fn)
    fixture = harness.load_fixture(FIXTURES)
    assert set(top_level) == set(fixture["projection"]["top_level_keys"])
    assert set(record_keys) == set(fixture["projection"]["record_keys"])
    assert trust_value == "untrusted_observation"


def test_missing_projection_function_fails_closed(tmp_path: Path):
    stub = tmp_path / "recorder.py"
    stub.write_text("def somewhere_else():\n    return {}\n", encoding="utf-8")
    try:
        harness._projection_fn(stub)
    except harness.HarnessError:
        return
    raise AssertionError("a vanished cabinet_projection must be a failure")


# --- scalar-consumer scan (synthetic trees, walk fallback, no git) --------

def test_unsanctioned_scalar_reader_is_a_violation(tmp_path: Path):
    (tmp_path / "ok.py").write_text("print('clean')\n", encoding="utf-8")
    (tmp_path / "rogue.py").write_text(
        "series = open('shared/interfaces/golden-eval-scalar.jsonl')\n",
        encoding="utf-8")
    hits, violations = harness.scan_scalar_references(
        tmp_path, ["golden-eval-scalar", "golden_scalar"], set())
    assert hits == ["rogue.py"]
    assert violations == ["rogue.py"]


def test_allowlisted_scalar_reference_is_clean(tmp_path: Path):
    (tmp_path / "writer.sh").write_text(
        "golden_scalar_emit model 1 0 0 series\n", encoding="utf-8")
    hits, violations = harness.scan_scalar_references(
        tmp_path, ["golden-eval-scalar", "golden_scalar"], {"writer.sh"})
    assert hits == ["writer.sh"]
    assert violations == []


def test_scan_is_case_insensitive(tmp_path: Path):
    (tmp_path / "shouty.py").write_text(
        "PATH = 'GOLDEN-EVAL-SCALAR.JSONL'\n", encoding="utf-8")
    _, violations = harness.scan_scalar_references(
        tmp_path, ["golden-eval-scalar"], set())
    assert violations == ["shouty.py"]


# --- self-test CLI (what the golden-eval runner invokes) ------------------

def _run_self_test(*extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HARNESS), "--self-test",
         "--repo-root", str(REPO_ROOT), *extra],
        capture_output=True, text=True, timeout=120,
    )


def test_self_test_green_on_the_shipped_fixture():
    proc = _run_self_test()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "NEVER-A-SCORE-EVAL:" in proc.stdout


def test_self_test_teeth_emptied_allowlist_fails(tmp_path: Path):
    doc = json.loads((FIXTURES / "law-pins.json").read_text(encoding="utf-8"))
    doc["scalar_reference_allowlist"] = [
        {"path": ".gitignore", "why": "keep one sanctioned entry"},
    ]
    alt = tmp_path / "fixtures"
    alt.mkdir()
    (alt / "law-pins.json").write_text(json.dumps(doc), encoding="utf-8")
    proc = _run_self_test("--fixtures", str(alt))
    assert proc.returncode != 0
    assert "unsanctioned" in proc.stderr


def test_self_test_missing_fixture_fails_closed(tmp_path: Path):
    proc = _run_self_test("--fixtures", str(tmp_path / "nowhere"))
    assert proc.returncode != 0
    assert "fixture" in proc.stderr.lower()


# --- pairing validator: bodies, harnesses, runner sections ---------------
# The anti-unplug rule from both eval bodies, made mechanical: a golden
# eval whose runner section silently disappears has been unplugged rather
# than failed. Extend PAIRS when a new harness-backed eval ships.

PAIRS = (
    ("memory/golden-evals/eval-024-candor.md",
     "cabinet/evals/candor/harness.py", "EVAL-024-CANDOR"),
    ("memory/golden-evals/eval-025-never-a-score.md",
     "cabinet/evals/never-a-score/harness.py", "EVAL-025-NEVER-A-SCORE"),
)


def test_eval_bodies_harnesses_and_runner_sections_stay_paired():
    runner_text = RUNNER.read_text(encoding="utf-8")
    for body, harness_path, label in PAIRS:
        assert (REPO_ROOT / body).is_file(), f"eval body missing: {body}"
        assert (REPO_ROOT / harness_path).is_file(), (
            f"harness missing: {harness_path}")
        assert label in runner_text, (
            f"runner section {label} unplugged from run-golden-evals.sh")


def test_runner_section_is_fail_closed_not_skip():
    runner_text = RUNNER.read_text(encoding="utf-8")
    start = runner_text.index("EVAL-025-NEVER-A-SCORE:")
    section = runner_text[start:start + 2400]
    assert 'fail "never-a-score harness missing' in section
    assert "--self-test" in section
