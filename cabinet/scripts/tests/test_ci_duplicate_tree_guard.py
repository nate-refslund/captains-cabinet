"""Teeth for the CI duplicate-TREE guard (cabinet/scripts/ci-duplicate-tree-guard.py).

THE FAILURE THIS FILE EXISTS TO PREVENT. GitHub counts a `skipped` check run as
SUCCESSFUL for branch protection. So the guard's only expensive defect is a
FALSE SKIP: seven required contexts reported green over a tree nothing ran on.
Every test below is written from that direction — the skip path is guilty until
proven, and each disqualifying condition gets its own arm so no other arm can
pass on its behalf.

The workflow-shape half is a ROUND TRIP, not a token sweep. `git grep` for
"duplicate-tree-guard" in the workflow would prove a string is present, not that
the wiring has teeth. `_shape_findings()` is run against the REAL workflow (must
be clean) and against mutated copies of it that each remove exactly one lock
(each must be flagged) — the both-directions proof, which is what makes this a
sensor rather than a decoration.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "cabinet" / "scripts" / "ci-duplicate-tree-guard.py"
_WORKFLOW = _REPO / ".github" / "workflows" / "cabinet-ci.yml"

_GUARD_JOB = "duplicate-tree-guard"
_GATE_IF = (
    "${{ !cancelled() && needs.duplicate-tree-guard.outputs.skip != 'true' }}"
)


def _load():
    spec = importlib.util.spec_from_file_location("ci_dup_tree_guard", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ci_dup_tree_guard"] = mod
    spec.loader.exec_module(mod)
    return mod


G = _load()


def _green_run(sha: str, run_id: int = 4242, jobs=None, **over):
    run = {
        "id": run_id,
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success",
        "path": G.WORKFLOW_PATH,
        "jobs": [
            {"name": n, "conclusion": "success"}
            for n in (jobs if jobs is not None else G.REQUIRED_JOBS)
        ],
    }
    run.update(over)
    return run


def _args(**over):
    base = dict(
        event="push",
        ref="refs/heads/master",
        head_sha="a" * 40,
        head_tree="t" * 40,
        parent_sha="b" * 40,
        parent_tree="t" * 40,
        candidate_runs=[_green_run("b" * 40)],
    )
    base.update(over)
    return base


# --------------------------------------------------------------------------
# The one skip path. If this ever stops passing the guard is dead weight.
# --------------------------------------------------------------------------


def test_skips_only_the_proven_duplicate():
    d = G.decide(**_args())
    assert d.skip is True
    assert d.prior_run_id == 4242
    assert "already green per job" in d.reason


# --------------------------------------------------------------------------
# Every disqualifier, one arm each. All must return skip=False.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("event", ["pull_request", "schedule", "workflow_dispatch",
                                   "", None])
def test_never_skips_off_a_push(event):
    """The dangerous case: on `pull_request` a skip would green the seven
    required contexts without running them."""
    assert G.decide(**_args(event=event)).skip is False


@pytest.mark.parametrize(
    "ref",
    ["refs/heads/perf/local-ci", "refs/pull/12/merge", "refs/tags/v1", "", None],
)
def test_never_skips_off_master(ref):
    assert G.decide(**_args(ref=ref)).skip is False


def test_no_second_parent_means_run():
    """A direct push to master is not a merge — 207 of 306 master push runs in
    the measured window. It is the only test that tree ever gets."""
    assert G.decide(**_args(parent_sha=None, parent_tree=None)).skip is False


def test_tree_mismatch_means_run():
    assert G.decide(**_args(parent_tree="z" * 40)).skip is False


def test_no_prior_run_means_run():
    assert G.decide(**_args(candidate_runs=[])).skip is False


def test_prior_run_on_a_different_sha_means_run():
    assert G.decide(**_args(candidate_runs=[_green_run("c" * 40)])).skip is False


@pytest.mark.parametrize(
    "over",
    [
        {"conclusion": "failure"},
        {"conclusion": "cancelled"},
        {"conclusion": None},
        {"status": "in_progress"},
        {"status": "queued"},
    ],
)
def test_prior_run_not_completed_green_means_run(over):
    """A cancelled run reads exactly like a red here, deliberately: neither is
    evidence that the tree passed."""
    assert G.decide(**_args(candidate_runs=[_green_run("b" * 40, **over)])).skip is False


def test_prior_run_from_another_workflow_means_run():
    run = _green_run("b" * 40, path=".github/workflows/something-else.yml")
    assert G.decide(**_args(candidate_runs=[run])).skip is False


@pytest.mark.parametrize("dropped", list(G.REQUIRED_JOBS))
def test_one_missing_required_job_means_run(dropped):
    """The run-level conclusion is not the sensor — the per-job record is. A
    run can conclude success with a job skipped, and that job's tree evidence
    does not exist."""
    kept = [j for j in G.REQUIRED_JOBS if j != dropped]
    assert G.decide(**_args(candidate_runs=[_green_run("b" * 40, jobs=kept)])).skip is False


@pytest.mark.parametrize("red", list(G.REQUIRED_JOBS))
def test_one_red_required_job_means_run(red):
    jobs = [
        {"name": n, "conclusion": "success" if n != red else "failure"}
        for n in G.REQUIRED_JOBS
    ]
    run = _green_run("b" * 40)
    run["jobs"] = jobs
    assert G.decide(**_args(candidate_runs=[run])).skip is False


@pytest.mark.parametrize("jobs", [[], None, "not-a-list", [None], [{"name": "ci"}]])
def test_degenerate_job_payloads_mean_run(jobs):
    run = _green_run("b" * 40)
    run["jobs"] = jobs
    assert G.decide(**_args(candidate_runs=[run])).skip is False


def test_empty_required_set_refuses_to_skip():
    """THE DEGENERATE END. With an empty required set the coverage test is
    vacuously true and every run with any successful prior would be skipped —
    an empty set is a broken guard, not a permissive one."""
    d = G.decide(**_args(), required_jobs=())
    assert d.skip is False
    assert "empty" in d.reason


def test_a_run_with_zero_jobs_cannot_satisfy_the_required_set():
    run = _green_run("b" * 40, jobs=[])
    assert G.decide(**_args(candidate_runs=[run])).skip is False


def test_junk_entries_in_the_candidate_list_do_not_crash_or_skip():
    assert G.decide(**_args(candidate_runs=["x", None, 7, {}])).skip is False


# --------------------------------------------------------------------------
# CLI seam: exit code and emitted output, with git/API faked.
# --------------------------------------------------------------------------


def test_cli_writes_skip_true_and_exits_zero(tmp_path):
    out = tmp_path / "gh_out"
    summary = tmp_path / "gh_summary"
    revs = {
        "HEAD": "a" * 40,
        "HEAD^{tree}": "t" * 40,
        "HEAD^2": "b" * 40,
        "HEAD^2^{tree}": "t" * 40,
    }
    rc = G.main(
        ["--event", "push", "--ref", "refs/heads/master", "--repo", "o/r"],
        rev=revs.get,
        runs=lambda repo, sha: [_green_run(sha)],
        env={"GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(summary)},
    )
    assert rc == 0
    assert "skip=true" in out.read_text()
    assert "SKIPPED AS DUPLICATE" in summary.read_text()
    assert "run 4242" in summary.read_text()


def test_cli_writes_skip_false_when_the_api_returns_nothing(tmp_path):
    out = tmp_path / "gh_out"
    revs = {
        "HEAD": "a" * 40,
        "HEAD^{tree}": "t" * 40,
        "HEAD^2": "b" * 40,
        "HEAD^2^{tree}": "t" * 40,
    }
    rc = G.main(
        ["--event", "push", "--ref", "refs/heads/master", "--repo", "o/r"],
        rev=revs.get,
        runs=lambda repo, sha: [],
        env={"GITHUB_OUTPUT": str(out)},
    )
    assert rc == 0
    assert "skip=false" in out.read_text()


def test_cli_exits_zero_when_git_resolves_nothing(tmp_path):
    """A guard that can red the run has turned a cost optimisation into a new
    way for master to go red."""
    out = tmp_path / "gh_out"
    rc = G.main(
        ["--event", "push", "--ref", "refs/heads/master", "--repo", "o/r"],
        rev=lambda expr: None,
        runs=lambda repo, sha: [],
        env={"GITHUB_OUTPUT": str(out)},
    )
    assert rc == 0
    assert "skip=false" in out.read_text()


def test_cli_does_not_call_the_api_on_a_pull_request():
    calls = []

    def _runs(repo, sha):
        calls.append((repo, sha))
        return [_green_run(sha)]

    revs = {
        "HEAD": "a" * 40,
        "HEAD^{tree}": "t" * 40,
        "HEAD^2": "b" * 40,
        "HEAD^2^{tree}": "t" * 40,
    }
    rc = G.main(
        ["--event", "pull_request", "--ref", "refs/pull/9/merge", "--repo", "o/r"],
        rev=revs.get, runs=_runs, env={},
    )
    assert rc == 0
    assert calls == []


# --------------------------------------------------------------------------
# Workflow shape — the round trip, both directions.
# --------------------------------------------------------------------------


def _shape_findings(wf: dict) -> list[str]:
    """Return every way this workflow's wiring fails the guard's contract.

    Clean list == the double lock is intact. Run against the real workflow AND
    against mutated copies below, so the assertion is proven to fail as well as
    to pass.
    """
    bad: list[str] = []
    jobs = wf.get("jobs") or {}
    guard = jobs.get(_GUARD_JOB)
    if not isinstance(guard, dict):
        return [f"job {_GUARD_JOB} is missing"]

    cond = str(guard.get("if") or "")
    if "github.event_name == 'push'" not in cond:
        bad.append("guard job is not restricted to the push event")
    if "github.ref == 'refs/heads/master'" not in cond:
        bad.append("guard job is not restricted to refs/heads/master")
    outputs = guard.get("outputs") or {}
    if "skip" not in outputs:
        bad.append("guard job exposes no `skip` output")

    for name, job in jobs.items():
        if name == _GUARD_JOB:
            continue
        needs = job.get("needs")
        needs = [needs] if isinstance(needs, str) else list(needs or [])
        if _GUARD_JOB not in needs:
            bad.append(f"job {name} does not depend on {_GUARD_JOB}")
        if str(job.get("if") or "") != _GATE_IF:
            bad.append(f"job {name} does not carry the exact guard condition")
    return bad


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text())


def test_live_workflow_wiring_is_intact(workflow):
    assert _shape_findings(workflow) == []


def test_every_required_job_exists_in_the_workflow(workflow):
    missing = [j for j in G.REQUIRED_JOBS if j not in workflow["jobs"]]
    assert missing == [], missing


def test_required_set_is_not_empty_and_excludes_the_guard(workflow):
    assert G.REQUIRED_JOBS
    assert _GUARD_JOB not in G.REQUIRED_JOBS


def test_guard_job_is_not_a_required_check_of_itself(workflow):
    assert not workflow["jobs"][_GUARD_JOB].get("needs")


@pytest.mark.parametrize(
    "mutate,expect",
    [
        (lambda w: w["jobs"][_GUARD_JOB].__setitem__(
            "if", "${{ github.ref == 'refs/heads/master' }}"),
         "push event"),
        (lambda w: w["jobs"][_GUARD_JOB].__setitem__(
            "if", "${{ github.event_name == 'push' }}"),
         "refs/heads/master"),
        (lambda w: w["jobs"][_GUARD_JOB].pop("outputs"), "`skip` output"),
        (lambda w: w["jobs"]["ci"].pop("needs"), "does not depend"),
        (lambda w: w["jobs"]["gitleaks"].__setitem__("if", "${{ always() }}"),
         "exact guard condition"),
        (lambda w: w["jobs"].pop(_GUARD_JOB), "is missing"),
    ],
)
def test_shape_check_fails_when_a_lock_is_removed(workflow, mutate, expect):
    """Both directions. Each mutation removes exactly one lock; the shape check
    must name it. A checker that only ever returns [] is a disabled sensor."""
    mutated = copy.deepcopy(workflow)
    mutate(mutated)
    findings = _shape_findings(mutated)
    assert any(expect in f for f in findings), (expect, findings)
