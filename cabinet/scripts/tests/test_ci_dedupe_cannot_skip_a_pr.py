"""The precondition `tree-dedupe` rests on, made executable.

WHAT THIS PINS, AND WHY IT IS THE ONE THING WORTH PINNING. `tree-dedupe` skips
a master push run when the pushed tree already went green on a `pull_request`
run. Two claims in its header carry the whole safety argument:

  1. "A pull_request or schedule run can NEVER be skipped." GitHub reports a
     job skipped by an `if:` as SUCCESSFUL to branch protection, so a condition
     that went false on a PR would show a green merge button over a tree
     nothing ran on.
  2. "A run-level `success` … means all eight jobs ran and passed." That is not
     a property of GitHub — a run concludes `success` with jobs merely skipped.
     It is true here ONLY because of claim 1: on a `pull_request` event no gate
     job's condition can go false, so a successful PR run really did run all
     eight.

Both claims are properties of expression strings in a YAML file, which is
exactly the kind of thing that decays silently the next time someone adds a
condition. So they are evaluated here rather than asserted in prose: the real
`if:` expressions are translated into Python and evaluated under a simulated
`pull_request` context, for EVERY value the dedupe output can take.

Non-vacuity, both directions, because a checker that only ever passes is a
disabled sensor:
  * the same evaluator must report the gate jobs as SKIPPED on a master push
    with `skip=true` — so it is measuring the mechanism, not agreeing with it;
  * mutation arms strip the event guard out of the real expression and require
    the PR assertion to FAIL;
  * the translator itself has arms in both directions before it is trusted.
"""

from __future__ import annotations

import ast
import copy
import re
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]
_WORKFLOW = _REPO / ".github" / "workflows" / "cabinet-ci.yml"
_DEDUPE = "tree-dedupe"


def _reduce(node: ast.AST, names: dict[str, bool]) -> object:
    """Walk an allowlisted AST. Deliberately NOT eval(): the input is a string
    from a YAML file, and a general evaluator would execute whatever it failed
    to understand. Only boolean operators, `not`, string/bool comparison,
    literals and the two known names are reachable — anything else raises."""
    if isinstance(node, ast.Expression):
        return _reduce(node.body, names)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in names:
            raise AssertionError(f"unknown name {node.id!r} in the condition")
        return names[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _reduce(node.operand, names)
    if isinstance(node, ast.BoolOp):
        vals = [_reduce(v, names) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left = _reduce(node.left, names)
        right = _reduce(node.comparators[0], names)
        if isinstance(node.ops[0], ast.Eq):
            return left == right
        if isinstance(node.ops[0], ast.NotEq):
            return left != right
    raise AssertionError(f"unsupported expression node {type(node).__name__}")


def _evaluate(expr: str, ctx: dict[str, str], *, cancelled: bool = False) -> bool:
    """Evaluate the subset of the GitHub expression language this workflow uses.

    Deliberately narrow: it understands the context lookups, the three status
    functions, the boolean operators and string comparison, and REFUSES
    anything else rather than guessing. A silent mis-parse here would be a
    sensor agreeing with whatever it failed to read.
    """
    body = expr.strip()
    if body.startswith("${{") and body.endswith("}}"):
        body = body[3:-2].strip()

    body = body.replace("always()", "True")
    body = body.replace("!cancelled()", "not CANCELLED")
    body = body.replace("cancelled()", "CANCELLED")
    body = body.replace("success()", "True")

    for key, value in ctx.items():
        body = body.replace(key, repr(value))

    body = re.sub(r"&&", " and ", body)
    body = re.sub(r"\|\|", " or ", body)
    body = re.sub(r"!(?=[A-Za-z(])", " not ", body)

    # Scan for identifiers OUTSIDE string literals: `'refs/heads/master'` is
    # data, not a name, and treating it as one would reject every real
    # condition in the file.
    outside = re.sub(r"'[^']*'|\"[^\"]*\"", " ", body)
    leftover = re.findall(r"[A-Za-z_][A-Za-z0-9_.\-]*", outside)
    allowed = {"and", "or", "not", "True", "False", "CANCELLED"}
    unknown = [t for t in leftover if t not in allowed]
    if unknown:
        raise AssertionError(
            f"unrecognised token(s) {sorted(set(unknown))} in {expr!r} — extend "
            "the evaluator rather than letting it guess"
        )
    try:
        tree = ast.parse(body, mode="eval")
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise AssertionError(f"could not parse {expr!r}: {exc}") from exc
    return bool(_reduce(tree, {"CANCELLED": cancelled, "True": True,
                               "False": False}))


# --- the evaluator is trusted only after it fails in the right places -------


@pytest.mark.parametrize("expr,ctx,expected", [
    ("${{ github.event_name == 'push' }}", {"github.event_name": "push"}, True),
    ("${{ github.event_name == 'push' }}", {"github.event_name": "pull_request"}, False),
    ("${{ github.event_name != 'push' || A != 'true' }}",
     {"github.event_name": "pull_request", "A": "true"}, True),
    ("${{ github.event_name != 'push' || A != 'true' }}",
     {"github.event_name": "push", "A": "true"}, False),
    ("${{ github.event_name != 'push' || A != 'true' }}",
     {"github.event_name": "push", "A": "false"}, True),
    ("${{ !cancelled() }}", {}, True),
])
def test_evaluator(expr, ctx, expected):
    assert _evaluate(expr, ctx) is expected


def test_evaluator_treats_cancelled_as_stopping_the_job():
    assert _evaluate("${{ !cancelled() }}", {}, cancelled=True) is False


def test_evaluator_refuses_what_it_cannot_read():
    with pytest.raises(AssertionError):
        _evaluate("${{ hashFiles('x') == 'y' }}", {})


# --- the workflow itself ---------------------------------------------------


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text())


def _gate_jobs(wf: dict) -> dict[str, dict]:
    return {k: v for k, v in wf["jobs"].items() if k != _DEDUPE}


def _ctx(event: str, skip: str) -> dict[str, str]:
    return {
        "github.event_name": event,
        "github.ref": ("refs/heads/master" if event == "push"
                       else "refs/pull/1/merge"),
        f"needs.{_DEDUPE}.outputs.skip": skip,
    }


def _pr_skippable(wf: dict) -> list[str]:
    """Every gate job that COULD be skipped on a non-push event. Must be empty."""
    bad: list[str] = []
    for name, job in _gate_jobs(wf).items():
        cond = job.get("if")
        if cond is None:
            continue  # no condition at all == always runs; that is safe
        for event in ("pull_request", "schedule", "workflow_dispatch"):
            for skip in ("true", "false", ""):
                if not _evaluate(str(cond), _ctx(event, skip)):
                    bad.append(f"{name} skipped on {event} with skip={skip!r}")
    return bad


def test_no_gate_job_can_be_skipped_off_a_push(workflow):
    """Claim 1. If this ever fails, a required check reports green to branch
    protection over a tree nothing ran on."""
    assert _pr_skippable(workflow) == []


def test_all_eight_gate_jobs_are_present(workflow):
    expected = {
        "ci", "framework-tests", "clean-room-foundation", "clean-room-source",
        "null-hatch", "cognitive-phase4", "gitleaks", "zizmor",
    }
    assert set(_gate_jobs(workflow)) == expected


def test_a_successful_pr_run_really_did_run_every_gate_job(workflow):
    """Claim 2, which is only true BECAUSE of claim 1: no gate job can be
    skipped on a pull_request, so a run-level success there is not hiding one."""
    assert _pr_skippable(workflow) == []
    assert all(job.get("if") is None or "cancelled()" in str(job.get("if"))
               for job in _gate_jobs(workflow).values())


def test_the_mechanism_still_actually_skips_on_a_duplicate_master_push(workflow):
    """The other direction. An evaluator that says 'never skipped' to
    everything would pass the test above while measuring nothing."""
    skipped = [
        name for name, job in _gate_jobs(workflow).items()
        if job.get("if") and not _evaluate(str(job["if"]), _ctx("push", "true"))
    ]
    assert set(skipped) == set(_gate_jobs(workflow))


def test_a_master_push_that_is_not_a_duplicate_runs_everything(workflow):
    for name, job in _gate_jobs(workflow).items():
        cond = job.get("if")
        if cond:
            assert _evaluate(str(cond), _ctx("push", "false")), name
            assert _evaluate(str(cond), _ctx("push", "")), name


def test_a_failed_dedupe_job_forces_the_gates_to_run(workflow):
    """`!cancelled()` is load-bearing: a dedupe job that FAILED must produce a
    full run, never a skipped one. Its output is empty in that case."""
    for name, job in _gate_jobs(workflow).items():
        cond = job.get("if")
        if cond:
            assert _evaluate(str(cond), _ctx("push", "")), name


def test_the_dedupe_job_itself_is_push_and_master_only(workflow):
    cond = str(workflow["jobs"][_DEDUPE]["if"])
    assert _evaluate(cond, _ctx("push", ""))
    for event in ("pull_request", "schedule", "workflow_dispatch"):
        assert not _evaluate(cond, _ctx(event, ""))


def test_every_gate_job_depends_on_the_dedupe_job(workflow):
    for name, job in _gate_jobs(workflow).items():
        needs = job.get("needs")
        needs = [needs] if isinstance(needs, str) else list(needs or [])
        assert _DEDUPE in needs, name


# --- mutation arms: the checker must fail when the guard is removed --------


@pytest.mark.parametrize("job_name", [
    "ci", "framework-tests", "clean-room-foundation", "clean-room-source",
    "null-hatch", "cognitive-phase4", "gitleaks", "zizmor",
])
def test_dropping_the_event_guard_from_one_job_is_caught(workflow, job_name):
    mutated = copy.deepcopy(workflow)
    mutated["jobs"][job_name]["if"] = (
        "${{ !cancelled() && needs.tree-dedupe.outputs.skip != 'true' }}"
    )
    findings = _pr_skippable(mutated)
    assert any(job_name in f for f in findings), (job_name, findings)


def test_inverting_the_guard_to_always_skip_is_caught(workflow):
    mutated = copy.deepcopy(workflow)
    mutated["jobs"]["gitleaks"]["if"] = "${{ github.event_name == 'push' }}"
    assert _pr_skippable(mutated) != []
