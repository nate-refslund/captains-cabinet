"""The pull path stays importable and correct under Python 3.9 (A0.3).

WHY THIS EXISTS.  The prompt hook that pulls work is schg-locked: it runs
``python3`` from the officer's own PATH, and on the reference box that is
/usr/bin/python3 — **3.9.6**.  Changing the hook to pin a newer interpreter is
a Captain-only ceremony.  So every module the hook can reach has a hard 3.9
floor, and a single ``X | Y`` annotation evaluated at runtime, a ``match``
statement, or a 3.10+ stdlib import would take the whole pull path down on the
box it actually runs on — silently, because the hook redirects stderr.

TWO ARMS, and neither may skip.

* The GRAMMAR arm parses each module with the stdlib ``ast`` and rejects the
  3.10+ constructs by shape.  It runs on every interpreter, everywhere, and is
  the half that has teeth in CI on a 3.12-only runner.
* The EXECUTION arm runs the hook's own import-and-call under a real 3.9
  interpreter when the host has one.  It is the half that catches what the
  grammar arm cannot see — a 3.10+ stdlib symbol, a changed default, a C
  extension.  On a host with no 3.9 it reports the gap loudly instead of
  passing: an absent interpreter is an unmeasured claim, not a green one.

The CI half of the execution arm is a step in the workflow that sets up 3.9 and
runs the same command; it is never `continue-on-error` and never skipped.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]

#: Every module the locked hook can reach, transitively, from
#: `from framework.missions.session_bridge import get_next_task`.
PULL_PATH_MODULES = (
    "framework/missions/session_bridge.py",
    "framework/missions/claims.py",
    "framework/missions/compiler.py",
    "framework/missions/supervisor.py",
    "framework/missions/gaps.py",
    "framework/learning/capability_gaps.py",
    "framework/events/emitter.py",
    "framework/roles/lifecycle.py",
    "cabinet/scripts/lib/work_graph.py",
)

#: LIMIT, said rather than implied: this tuple is hand-maintained, and the real
#: transitive closure of `session_bridge` is larger than it (17 first-party
#: modules, measured 2026-09-08). It is the set A0.3 names, not the set the
#: import graph produces, so a module that arrives on the path without being
#: added here is unpinned by the grammar arms. The EXECUTION arm below is what
#: covers the remainder: it imports and calls the real entry point under a real
#: 3.9, so anything reachable is exercised whether or not it is listed.

#: Modules that arrived in 3.10 or later. An import of one of these is a hard
#: failure on 3.9 regardless of how it is guarded at the top level.
POST_39_STDLIB = frozenset({"tomllib", "graphlib.TopologicalSorter"})


def _module_paths():
    return [(rel, _ROOT / rel) for rel in PULL_PATH_MODULES]


def test_every_pull_path_module_exists():
    """A renamed module would make every arm below vacuous."""
    missing = [rel for rel, path in _module_paths() if not path.is_file()]
    assert missing == [], "pull-path modules are missing: %r" % missing


_BUILTIN_TYPE_NAMES = frozenset(
    "str int float bool bytes bytearray list dict set frozenset tuple complex "
    "object type".split()
)


def _is_inside_annotation(tree, target):
    for node in ast.walk(tree):
        for field in ("annotation", "returns"):
            child = getattr(node, field, None)
            if child is not None and target in ast.walk(child):
                return True
    return False


def _typeish(operand):
    """True when this operand reads as a TYPE rather than as a value.

    The distinction the whole check rests on. `os.O_RDWR | os.O_CREAT` and
    `fcntl.LOCK_EX | fcntl.LOCK_NB` are bit flags, not unions, and reporting
    them would train the next reader to ignore this sensor — so an ALL_CAPS
    name is never type-ish, whatever its first letter.
    """
    if isinstance(operand, ast.Constant) and operand.value is None:
        return True
    if isinstance(operand, ast.Subscript):
        return True
    if isinstance(operand, ast.Name):
        if operand.id in _BUILTIN_TYPE_NAMES:
            return True
        return operand.id[:1].isupper() and not operand.id.isupper()
    if isinstance(operand, ast.Attribute):
        return operand.attr[:1].isupper() and not operand.attr.isupper()
    return False


def union_offenders(source, label=""):
    """Every runtime `X | Y` type union in *source*, as (label, description)."""
    offenders = []
    tree = ast.parse(source)
    has_future = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in tree.body
    )
    if not has_future:
        return [(label, "no `from __future__ import annotations`")]
    # Postponed annotations cover annotations only. A union written in a
    # RUNTIME position — a default, an isinstance, a cast, a TypeAlias
    # assignment — still evaluates on 3.9.
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.BitOr):
            continue
        if _is_inside_annotation(tree, node):
            continue
        if _typeish(node.left) and _typeish(node.right):
            offenders.append((label, "runtime `X | Y` at line %d" % node.lineno))
    return offenders


def test_the_union_checker_is_not_vacuous():
    """The checker is exercised against a real offender on every run.

    Without this arm a checker that had quietly stopped matching anything would
    read as a clean tree — the disabled-sensor shape this program keeps paying
    for.
    """
    caught = union_offenders(
        "from __future__ import annotations\n"
        "Alias = str | None\n",
        "synthetic",
    )
    assert len(caught) == 1, caught

    assert union_offenders(
        "from __future__ import annotations\n"
        "def f(a: str | None = None) -> int | None:\n"
        "    return None\n",
        "annotated",
    ) == []

    assert union_offenders("x = 1\n", "no-future") == [
        ("no-future", "no `from __future__ import annotations`")
    ]

    # bit flags are values, not types
    assert union_offenders(
        "from __future__ import annotations\n"
        "import os\n"
        "F = os.O_RDWR | os.O_CREAT\n",
        "flags",
    ) == []


def test_no_runtime_union_annotations_outside_future_annotations():
    """`X | Y` is a TypeError at 3.9 unless annotations are postponed."""
    offenders = []
    for rel, path in _module_paths():
        offenders.extend(union_offenders(path.read_text(encoding="utf-8"), rel))
    assert offenders == [], "3.10-only unions on the pull path: %r" % offenders


def test_no_match_statements():
    """`match` is a SyntaxError on 3.9 — the module would not even parse."""
    offenders = []
    for rel, path in _module_paths():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if type(node).__name__ == "Match":
                offenders.append((rel, node.lineno))
    assert offenders == []


def test_no_post_39_stdlib_imports():
    offenders = []
    for rel, path in _module_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                root = name.split(".")[0]
                if root in {entry.split(".")[0] for entry in POST_39_STDLIB}:
                    offenders.append((rel, name))
    assert offenders == []


def _python39():
    """A real 3.9 interpreter on this host, or None."""
    for candidate in ("python3.9", "/usr/bin/python3"):
        binary = shutil.which(candidate) or (
            candidate if os.path.exists(candidate) else None
        )
        if not binary:
            continue
        try:
            out = subprocess.run(
                [binary, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30,
            )
        except Exception:  # noqa: BLE001
            continue
        if out.returncode == 0 and out.stdout.decode().strip() == "3.9":
            return binary
    return None


#: The CI job that pays the execution claim where no local 3.9 exists, and the
#: three properties that make it a carrier rather than a name in a file. It is
#: one of the PINNED gate jobs (cabinet/scripts/tests/test_ci_dedupe_cannot_
#: skip_a_pr.py::test_every_gate_job_is_present pins the set EXACTLY, in both
#: directions), which is what stops it from being quietly deleted.
_CARRIER_JOB = "pull-path-python39"
_WORKFLOW = _ROOT / ".github/workflows/cabinet-ci.yml"


def _carrier_gap() -> str:
    """"" when the carrier job really carries the claim, else why it does not.

    Reads the SAME workflow the gate-job pin reads, and asks for the three
    properties a carrier needs: it exists; it cannot be skipped on a pull
    request (the `!cancelled()` guard every gate job here carries); it sets up a
    real 3.9; and it executes the pull path's own entry point rather than
    merely mentioning it.
    """
    import yaml

    try:
        workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — an unreadable workflow IS a gap
        return "%s could not be read (%s)" % (_WORKFLOW, exc)
    job = (workflow.get("jobs") or {}).get(_CARRIER_JOB)
    if not isinstance(job, dict):
        return "no %r job in %s" % (_CARRIER_JOB, _WORKFLOW.name)
    condition = str(job.get("if") or "")
    if condition and "cancelled()" not in condition:
        return ("%r carries the guard %r, which can skip it on a pull request"
                % (_CARRIER_JOB, condition))
    steps = job.get("steps") or []
    sets_up_39 = any(
        "setup-python" in str(step.get("uses") or "")
        and str((step.get("with") or {}).get("python-version") or "").strip("'\" ") == "3.9"
        for step in steps if isinstance(step, dict)
    )
    if not sets_up_39:
        return "%r no longer sets up a 3.9 interpreter" % _CARRIER_JOB
    runs_the_pull_path = any(
        "framework.missions.session_bridge" in str(step.get("run") or "")
        for step in steps if isinstance(step, dict)
    )
    if not runs_the_pull_path:
        return ("%r no longer runs the pull path's own entry point, so it "
                "proves nothing about it" % _CARRIER_JOB)
    return ""


def test_the_python_39_claim_has_a_carrier_job():
    """THE SENSOR THAT NEVER SKIPS, wherever this suite runs.

    The execution arm below can only run where a 3.9 exists. This arm runs
    everywhere and asks the question that actually matters when it cannot: is
    ANYONE paying the claim? Deleting the carrier job, dropping its 3.9 setup,
    defanging its guard, or pointing it at something other than the pull path
    reds HERE — on every runner and every laptop — which is what makes the skip
    below a routing decision rather than a disabled sensor.
    """
    gap = _carrier_gap()
    assert gap == "", (
        "nothing carries the 3.9 execution claim: %s. Either restore the job or "
        "make this suite run the arm itself." % gap
    )


def test_the_hook_command_runs_under_a_real_python_39(tmp_path):
    """The hook's own import-and-call, on a 3.9 interpreter.

    This is the arm the grammar checks cannot replace, and it RUNS wherever a
    3.9 exists — including the reference box, whose /usr/bin/python3 is the very
    interpreter the locked hook uses.

    WHERE NO 3.9 EXISTS it used to `pytest.fail`, which is why this suite was
    red on the 3.12-only `framework-tests` runner while the claim was being paid
    in full, one job away, by `pull-path-python39`. Failing there does not buy
    coverage: it makes a green job impossible on any host without a second
    interpreter, and a check that is red for a reason nobody can act on gets
    ignored, which is how a real red gets missed.

    So the branch is a ROUTING decision, taken against evidence rather than
    assumed: `_carrier_gap()` re-derives, from the workflow itself, that the
    pinned `pull-path-python39` gate job exists, cannot be skipped on a pull
    request, sets up a real 3.9 and executes this same entry point. If it does
    NOT, this arm fails exactly as before — an unmeasured claim, named. If it
    does, the skip says who is measuring it instead, and
    `test_the_python_39_claim_has_a_carrier_job` above keeps that answer honest
    on every runner, without skipping.
    """
    binary = _python39()
    if binary is None:
        gap = _carrier_gap()
        if gap:
            pytest.fail(
                "no python3.9 on this host AND nothing carries the claim: %s. "
                "The execution arm did not run and nobody else ran it." % gap
            )
        pytest.skip(
            "no python3.9 on this host; the execution arm is carried by the "
            "%s gate job in %s, which is pinned into the gate-job set and "
            "verified by test_the_python_39_claim_has_a_carrier_job. Install a "
            "3.9 to run it locally." % (_CARRIER_JOB, _WORKFLOW.name)
        )

    # The outcomes path comes from the live resolver rather than being spelled
    # out here: a fixture that hardcodes the layout would keep passing after the
    # resolver moved, which is the wired-to-a-dead-twin shape.
    from framework.missions.session_bridge import _outcomes_path

    root = tmp_path / "cabinet"
    outcomes = _outcomes_path(str(root))
    outcomes.parent.mkdir(parents=True)
    outcomes.write_text(
        "outcomes:\n"
        "  - id: outcome-p39\n"
        "    name: Nine\n"
        "    measurable_criteria:\n"
        "      - node_id: p39-task\n"
        "        title: Do the thing\n"
        "        owner_role: engineering\n"
        "        depends_on: []\n"
        "    status: active\n"
    )
    env = dict(os.environ)
    env["CABINET_EVENT_LOG_DIR"] = str(tmp_path / "events")
    env["CABINET_WORKER_ID"] = "engineering@session:py39"
    env.pop("PYTEST_CURRENT_TEST", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    # Byte-for-byte the shape cabinet/scripts/hooks/session-task-inject.sh runs.
    source = (
        "import sys; sys.path.insert(0, %r)\n"
        "from framework.missions.session_bridge import get_next_task, format_task_for_session\n"
        "task = get_next_task('engineering', cabinet_root=%r)\n"
        "if task:\n"
        "    print(format_task_for_session(task))\n"
    ) % (str(_ROOT), str(root))

    out = subprocess.run(
        [binary, "-c", source],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=180,
    )
    stderr = out.stderr.decode("utf-8", "replace")
    assert out.returncode == 0, stderr
    stdout = out.stdout.decode("utf-8", "replace")
    assert "Do the thing" in stdout, (stdout, stderr)
    assert "Claim:" in stdout, (stdout, stderr)


def test_the_ci_job_runs_the_hook_command_under_39():
    """The CI half exists, is not skipped and is not continue-on-error."""
    workflow = (_ROOT / ".github" / "workflows" / "cabinet-ci.yml").read_text()
    assert "pull-path-python39" in workflow
    marker = workflow.index("pull-path-python39")
    block = workflow[marker : marker + 2400]
    assert "python-version: '3.9'" in block
    assert "continue-on-error" not in block
    assert "framework.missions.session_bridge" in block
