#!/usr/bin/env python3.12
"""CI duplicate-TREE guard — skip a master push run only when the exact tree
was already tested green, per job, by an earlier run of this same workflow.

WHY THIS EXISTS (measured 2026-07-28 over the trailing 30 days, 776 runs):
306 of them were `push` runs on master. 99 of those 306 pushed a MERGE commit
whose tree hash was byte-identical to the tree of its second parent — the PR
head that branch protection (`strict: true`) had just made CI test. All 99 had
a COMPLETED, conclusion=success run of this workflow on that exact parent SHA;
zero exceptions. At the 60.0 billable minutes a full run costs today (14 most
recent completed runs, per-job wall time rounded up per job, ubuntu 1x), those
99 runs are ~5,940 billable minutes a month spent re-testing bytes that had
already been tested green.

The other 207 master push runs pushed a genuinely NEW tree (direct pushes to
master, which `enforce_admins: false` still permits). They are the only test
that tree ever gets and this guard never touches them.

WHAT MAKES THIS LOSSLESS RATHER THAN CHEAPER-AND-BLINDER
An identical tree hash means identical bytes for every file the suite reads.
Every job in this workflow is a function of the checked-out tree plus the
runner environment; environment drift is the nightly schedule run's job, and
that run is never skipped. The one input that differs between a merge commit
and its second parent is commit METADATA (the merge's own SHA, message and
parents), and the two steps in this workflow that read history both resolve to
the same comparison either way:

  * `cognitive-phase4`'s baseline ratchet uses `github.event.pull_request.base.sha`
    on a PR and `github.event.before` on a push. With `strict: true` the PR
    branch must be up to date with master, so both are the same commit — the
    master tip the merge lands on, which is the merge's FIRST parent.
  * `gitleaks` scans the pushed range on a push and the PR commits on a PR;
    both cover the same commits, and the nightly run is the full-history sweep.

WHAT IT DELIBERATELY DOES NOT DO
It does not chase tree identity beyond the pushed commit's own parents, does
not skip anything on `pull_request` or `schedule`, and does not treat "no red
found" as "green found" — a missing prior run, an incomplete prior run, or a
prior run that did not carry every required job all mean RUN, not skip.

THE FAIL-OPEN DIRECTION IS DELIBERATE. Every unknown, every error and every
degenerate input resolves to skip=false, i.e. run the whole suite. The
expensive failure of a CI dedup guard is a false SKIP (a tree that never got
tested while the record says it was fine); a false RUN costs 60 minutes.

DOUBLE LOCK ON THE EVENT. GitHub counts a `skipped` check run as SUCCESSFUL
for branch protection, so a guard that wrongly emitted skip=true on a
`pull_request` event would turn all seven required contexts green without
running them. That must not depend on one condition being right, so it is
enforced twice and independently: the workflow gates the guard JOB on
`github.event_name == 'push' && github.ref == 'refs/heads/master'`, and
`decide()` below re-derives the same predicate from its own inputs and refuses
to skip for any other event or ref. Either lock alone is sufficient;
`cabinet/scripts/tests/test_ci_duplicate_tree_guard.py` pins both, and pins
that removing either one from the workflow makes the shape assertion fail.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

# The workflow this guard is allowed to reason about. A "green run" on another
# workflow file proves nothing about these jobs.
WORKFLOW_PATH = ".github/workflows/cabinet-ci.yml"

# The branch-protection required-check set, verified against
# GET /repos/{owner}/{repo}/branches/master/protection on 2026-07-28.
# `cognitive-phase4` is deliberately NOT here: it is not a required context
# (checked the same day), so requiring it would make the guard refuse to skip
# for a reason branch protection does not actually enforce. It still runs on
# every non-skipped run.
REQUIRED_JOBS: tuple[str, ...] = (
    "ci",
    "framework-tests",
    "clean-room-foundation",
    "clean-room-source",
    "null-hatch",
    "gitleaks",
    "zizmor",
)

MASTER_REF = "refs/heads/master"


@dataclass(frozen=True)
class Decision:
    """skip=True means: this exact tree already has a per-job green record."""

    skip: bool
    reason: str
    prior_run_id: int | None = None


def _green_job_names(run: dict[str, Any]) -> set[str]:
    jobs = run.get("jobs")
    if not isinstance(jobs, list):
        return set()
    names: set[str] = set()
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if job.get("conclusion") == "success" and isinstance(job.get("name"), str):
            names.add(job["name"])
    return names


def decide(
    *,
    event: str | None,
    ref: str | None,
    head_sha: str | None,
    head_tree: str | None,
    parent_sha: str | None,
    parent_tree: str | None,
    candidate_runs: Iterable[dict[str, Any]],
    required_jobs: Sequence[str] = REQUIRED_JOBS,
    workflow_path: str = WORKFLOW_PATH,
) -> Decision:
    """Pure decision. No git, no network, no environment.

    Ordered so that the cheapest disqualification is first and so that every
    branch that is not a proven duplicate returns skip=False with a reason a
    human can read in the job summary.
    """
    required = tuple(required_jobs)
    if not required:
        # DEGENERATE END, and the whole reason this branch is written out
        # rather than left implicit: with an empty required set the coverage
        # test below is vacuously true and EVERY run with any successful prior
        # run would be skipped. An empty required set is a broken guard, not a
        # permissive one.
        return Decision(False, "required-job set is empty — refusing to skip")

    if event != "push":
        return Decision(False, f"event is {event!r}, not a push — never skipped")
    if ref != MASTER_REF:
        return Decision(False, f"ref is {ref!r}, not {MASTER_REF} — never skipped")
    if not head_sha or not head_tree:
        return Decision(False, "head sha/tree unresolved — running the suite")
    if not parent_sha or not parent_tree:
        return Decision(
            False, "HEAD has no resolvable second parent (not a merge) — running"
        )
    if head_tree != parent_tree:
        return Decision(
            False,
            f"tree {head_tree[:12]} != second-parent tree {parent_tree[:12]} — "
            "genuinely new bytes, running",
        )

    seen = 0
    for run in candidate_runs:
        if not isinstance(run, dict):
            continue
        seen += 1
        if run.get("head_sha") != parent_sha:
            continue
        if run.get("path") not in (None, workflow_path):
            continue
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            continue
        green = _green_job_names(run)
        missing = [j for j in required if j not in green]
        if missing:
            continue
        run_id = run.get("id")
        return Decision(
            True,
            f"tree {head_tree[:12]} already green per job on {parent_sha[:12]} "
            f"(run {run_id}); all {len(required)} required jobs succeeded there",
            int(run_id) if isinstance(run_id, int) else None,
        )

    return Decision(
        False,
        f"no completed green run on {parent_sha[:12]} covering all "
        f"{len(required)} required jobs ({seen} candidate run(s) examined) — running",
    )


# --------------------------------------------------------------------------
# IO seams. Kept trivial and separate so the decision above stays testable.
# --------------------------------------------------------------------------


def _run(argv: Sequence[str]) -> str | None:
    try:
        proc = subprocess.run(
            list(argv), capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    return out or None


def git_rev(expr: str) -> str | None:
    return _run(["git", "rev-parse", "--verify", "--quiet", expr])


def fetch_runs(repo: str, head_sha: str) -> list[dict[str, Any]]:
    """Completed successful runs of this workflow on one SHA, jobs attached.

    Any failure returns [] — which `decide()` reads as "no proof", i.e. run.
    """
    raw = _run(
        [
            "gh",
            "api",
            "-X",
            "GET",
            f"repos/{repo}/actions/workflows/cabinet-ci.yml/runs",
            "-f",
            f"head_sha={head_sha}",
            "-f",
            "status=success",
            "-f",
            "per_page=20",
        ]
    )
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        return []
    out: list[dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("id"), int):
            continue
        jobs_raw = _run(
            ["gh", "api", f"repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100"]
        )
        jobs: list[dict[str, Any]] = []
        if jobs_raw:
            try:
                jobs = json.loads(jobs_raw).get("jobs") or []
            except (json.JSONDecodeError, ValueError, AttributeError):
                jobs = []
        run = dict(run)
        run["jobs"] = jobs
        out.append(run)
    return out


def _emit(decision: Decision, github_output: str | None,
          step_summary: str | None) -> None:
    value = "true" if decision.skip else "false"
    line = (
        f"duplicate-tree-guard: skip={value} — {decision.reason}"
    )
    print(line)
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(f"skip={value}\n")
            fh.write(f"reason={decision.reason}\n")
    if step_summary:
        verdict = (
            f"**SKIPPED AS DUPLICATE** — {decision.reason}"
            if decision.skip
            else f"**RAN** — {decision.reason}"
        )
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(f"### Duplicate-tree guard\n\n{verdict}\n")


def main(
    argv: Sequence[str] | None = None,
    *,
    rev: Callable[[str], str | None] = git_rev,
    runs: Callable[[str, str], list[dict[str, Any]]] = fetch_runs,
    env: dict[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", default=None)
    parser.add_argument("--ref", default=None)
    parser.add_argument("--repo", default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)
    environ = dict(os.environ if env is None else env)

    event = args.event or environ.get("GITHUB_EVENT_NAME")
    ref = args.ref or environ.get("GITHUB_REF")
    repo = args.repo or environ.get("GITHUB_REPOSITORY") or ""

    head_sha = rev("HEAD")
    head_tree = rev("HEAD^{tree}")
    parent_sha = rev("HEAD^2")
    parent_tree = rev("HEAD^2^{tree}") if parent_sha else None

    candidates: list[dict[str, Any]] = []
    # Only pay for the API round-trip once the cheap, local, purely-git
    # preconditions already hold.
    pre = decide(
        event=event,
        ref=ref,
        head_sha=head_sha,
        head_tree=head_tree,
        parent_sha=parent_sha,
        parent_tree=parent_tree,
        candidate_runs=[],
    )
    if not pre.skip and pre.reason.startswith("no completed green run") and repo:
        candidates = runs(repo, parent_sha or "")

    decision = decide(
        event=event,
        ref=ref,
        head_sha=head_sha,
        head_tree=head_tree,
        parent_sha=parent_sha,
        parent_tree=parent_tree,
        candidate_runs=candidates,
    )
    _emit(decision, environ.get("GITHUB_OUTPUT"), environ.get("GITHUB_STEP_SUMMARY"))
    # ALWAYS 0. A guard that can red the run has turned a cost optimisation
    # into a new way for master to go red.
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
