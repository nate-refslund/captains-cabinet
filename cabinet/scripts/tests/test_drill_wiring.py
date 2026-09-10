"""The one-responsibility drill is wired, and it is still alive.

Phase-1 contract §4 ("Sensors") and §8 amendments. The drill is the acceptance
sensor for the whole phase: one declared responsibility, ratified by a named
door, claimed once out of a crowd, surviving its holder being killed, finished
by a different holder, visible as receipts, and reaching an installed Cabinet.
A sensor that large is worth exactly as much as the answer to two questions,
and this file is those two questions.

  IS IT RUN?          A drill nobody runs is a file. The wiring arms read the
                      real workflow and require the `responsibility-drill`
                      job — the drill itself plus the claims and update-path
                      suites (§8 amendment B14), cloned from null-hatch, needs
                      tree-dedupe, python 3.12.

  IS IT ALIVE?        A drill that cannot go red is worse than no drill: it
                      certifies. The red arms hand the drill a MUTATED tree
                      through its own `--tree` seam and require the exit code
                      the invariant names — 20 when the claim path stops
                      resolving a crowd to one holder, 21 when the pull path
                      cannot be imported at all (A4.1: an ImportError is not
                      the red the claim invariant names, so it gets its own
                      code and this file proves the two do not collapse).

The mutated tree is cut with `git archive HEAD`, never copied from the working
tree: the drill measures a committed tree because that is the only tree an
export, a hatch or a stranger ever sees, and a red arm built on uncommitted
bytes would prove something about a tree nobody can get. A checkout that
cannot produce one FAILS here rather than skipping — a skipped arm is a
disabled sensor, and this file exists to keep exactly that from happening to
the drill.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[3]
_WORKFLOW = _REPO / ".github" / "workflows" / "cabinet-ci.yml"
_DRILL = _REPO / "cabinet" / "scripts" / "drills" / "one-responsibility.sh"
_WORKER = _REPO / "cabinet" / "scripts" / "drills" / "lib" / "worker.py"
_VERDICT = _REPO / "cabinet" / "scripts" / "drills" / "lib" / "verdict.sh"
_UPDATER = _REPO / "cabinet" / "scripts" / "cabinet-update.sh"
_JOB = "responsibility-drill"

# The drill hatches a tree, races eight holders, kills one, waits out a lease
# and walks the locked hook. Measured on the reference box: ~15 s per red arm
# with --skip-update. 300 s is a runaway guard, not a performance claim.
_ARM_TIMEOUT = 300


# ---------------------------------------------------------------------------
# is it run?
# ---------------------------------------------------------------------------

def _jobs() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _run_bodies(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in job["steps"])


def test_the_drill_and_its_worker_are_present_and_executable():
    for path in (_DRILL, _WORKER, _VERDICT):
        assert path.is_file(), f"{path} is missing — the drill cannot run"
    assert os.access(_DRILL, os.X_OK), f"{_DRILL} is not executable"


def test_the_workflow_carries_the_responsibility_drill_job():
    jobs = _jobs()
    assert _JOB in jobs, (
        f"no {_JOB} job in the workflow — under the CI-outage protocol "
        '"wired into job X" means the step exists in the yml AND the same '
        "command is green in a fresh clone (A0.6), and this is the first half")
    job = jobs[_JOB]
    assert job.get("needs") == ["tree-dedupe"], (
        f"{_JOB} must need tree-dedupe like every sibling gate: {job.get('needs')!r}")
    body = _run_bodies(job)
    assert "cabinet/scripts/drills/one-responsibility.sh" in body, (
        f"the {_JOB} job never runs the drill")
    versions = [str(step.get("with", {}).get("python-version", ""))
                for step in job["steps"] if "setup-python" in str(step.get("uses", ""))]
    assert "3.12" in versions, (
        f"{_JOB} must pin python 3.12 (the drill's own interpreter law): {versions!r}")
    # And the job READS the drill's report. A drill that exited 0 having run
    # three of its twelve stages would satisfy an exit-code check; §4 says the
    # top-level json is asserted on the stages array, never on exit 0 alone.
    assert '["stages"]' in body, (
        f"the {_JOB} job gates on the drill's exit code alone; the stages array "
        "is where 'every stage was reached and none failed' is written down, and "
        "reading it means subscripting it")


def test_the_drill_job_carries_the_claims_and_update_path_suites():
    """§8 amendment B14: this job, not framework-tests, carries those two.

    framework-tests already runs a 24 m median under a 40 m guard, so the two
    suites that belong beside the drill ride here."""
    body = _run_bodies(_jobs()[_JOB])
    for suite in ("framework/missions/tests/test_claims.py",
                  "cabinet/scripts/tests/test_cabinet_update.py",
                  "cabinet/scripts/tests/test_drill_wiring.py"):
        assert suite in body, f"the {_JOB} job does not run {suite}"


def test_the_drill_job_does_not_skip_itself_on_a_master_push():
    """The dedupe clause is the sibling gates' clause, not a broader one.

    A job that can be skipped by a condition nobody reads is a gate with an
    off switch; this pins it to the same `!cancelled()` + push-dedupe shape
    null-hatch uses."""
    condition = str(_jobs()[_JOB].get("if", ""))
    assert "!cancelled()" in condition, condition
    assert "needs.tree-dedupe.outputs.skip != 'true'" in condition, condition


# ---------------------------------------------------------------------------
# the restart seam: one name, read on both sides
# ---------------------------------------------------------------------------

def _seam_names_in(text: str) -> set:
    return set(re.findall(r"CABINET_[A-Z0-9_]*RESTART_CMD", text))


def test_the_drill_and_the_updater_name_the_same_restart_seam():
    """P7 drives a restart command; the updater must be the thing that reads it.

    The drill's gate-red leg makes the health gate go red by handing the apply
    a restart that does nothing. If the installed update path reads no such
    variable the dashboard restarts normally, the gate goes green, and the
    whole rollback arm becomes a measurement of a healthy server — a sensor
    pointed at a seam that does not exist. The drill refuses to run that leg
    unless this holds; this arm is the same claim, mechanically, so the two
    sides cannot drift apart without a red here."""
    drill_names = _seam_names_in(_DRILL.read_text(encoding="utf-8"))
    assert drill_names, "the drill drives no restart seam at all"
    updater = _UPDATER.read_text(encoding="utf-8")
    for name in sorted(drill_names):
        assert "${%s:-}" % name in updater, (
            f"the drill drives {name} and cabinet-update.sh never reads it "
            "(searched for the ${%s:-} expansion) — the gate-red leg would "
            "drive nothing" % name)
        # A5.14: a seam that can turn a leg of the health gate green is a TEST
        # seam and says so in its name, or it becomes behaviour by being
        # mistaken for a production knob.
        assert name.startswith("CABINET_UPDATE_TEST_"), (
            f"{name} turns part of the health gate green and is not named as a "
            "test seam (A5.14)")


def test_the_drill_checks_for_work_before_it_grades_the_health_gate():
    """An apply can exit 0 having never reached the gate, and P7 grades exits.

    `cabinet-update.sh apply` returns 0 on two paths that run NO health gate:
    an install already stamped with the bundle sha, and a plan whose changed
    and deleted sets are both empty. Neither prints on stdout — both go to the
    updater log — so a leg that reads only the exit code scores a never-gated
    apply as an identity probe that passed. Measured 2026-09-10: that is how
    P7 went red on the CI runner while passing on the reference box, with an
    empty captured output and nothing to read.

    So the drill asserts the bundle and the install genuinely differ at the one
    mutated path BEFORE it grades anything, and it does so by the same
    comparison the plan makes (manifest digest vs the installed file). This arm
    welds the two facts together: the updater still has the silent exit-0 path,
    and the drill still checks for work first — mechanically, so neither side
    can drift without a red here."""
    updater = _UPDATER.read_text(encoding="utf-8")
    assert "changes nothing outside the preserve set" in updater, (
        "the updater no longer has the empty-plan exit-0 path this guard is "
        "about — if it really is gone, retire the guard deliberately")
    drill = _DRILL.read_text(encoding="utf-8")
    assert "BUNDLE_DELTA" in drill, (
        "P7 no longer checks that the bundle differs from the install, so an "
        "empty-plan apply would be graded as a green health gate")
    check_at = drill.index("BUNDLE_DELTA")
    grade_at = drill.index("RED_RC")
    assert check_at < grade_at, (
        "P7 checks for work AFTER it grades the apply exit code; the check has "
        "to come first or the grade is already wrong")


# ---------------------------------------------------------------------------
# is it alive?
# ---------------------------------------------------------------------------

def _tree_from_head(tmp_path: Path) -> Path:
    """A cut of HEAD, the way the drill stages its own root.

    Never the working tree (evidence class 2): the drill's subject is the
    committed tree. A checkout that cannot produce one fails — a skip here
    would silently retire both red arms."""
    proc = subprocess.run(["git", "-C", str(_REPO), "rev-parse", "--is-inside-work-tree"],
                          capture_output=True, text=True)
    assert proc.returncode == 0 and proc.stdout.strip() == "true", (
        "the red arms need a git checkout to cut a mutated tree from HEAD; this "
        "is not one, and skipping would leave the drill with no proof that it "
        "can still go red (%s)" % (proc.stderr.strip() or proc.stdout.strip()))
    tree = tmp_path / "tree"
    tree.mkdir()
    archive = subprocess.run(["git", "-C", str(_REPO), "archive", "--format=tar", "HEAD"],
                             capture_output=True)
    assert archive.returncode == 0, archive.stderr[-400:]
    untar = subprocess.run(["tar", "-xf", "-", "-C", str(tree)], input=archive.stdout,
                           capture_output=True)
    assert untar.returncode == 0, untar.stderr[-400:]
    return tree


def _run_drill(tree: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # The drill scrubs its own environment; these two only choose where it
    # works. --skip-update because both red arms land at the claim stage, long
    # before the update leg, and cutting a bundle would double the runtime for
    # nothing.
    return subprocess.run(
        ["bash", str(_DRILL), "--tree", str(tree), "--skip-update", "--json"],
        capture_output=True, text=True, timeout=_ARM_TIMEOUT, env=env,
        cwd=str(tmp_path))


def test_drill_fails_without_claim(tmp_path):
    """A4.1's first red arm: a claim that does not fence lets the crowd through.

    `claim()` is mutated to hand every caller a claim of its own — the lock is
    still taken, the ledger is still written, and eight holders all win. That
    is precisely the state the claim unit exists to remove, and the drill must
    exit 20 (the claim stage) rather than 0."""
    tree = _tree_from_head(tmp_path)
    claims = tree / "framework" / "missions" / "claims.py"
    text = claims.read_text(encoding="utf-8")
    needle = "        existing = _live_from_state(state, moment)\n"
    assert needle in text, "claims.py no longer decides liveness where this arm mutates it"
    # The one-line defect: nobody is ever found to be holding the task, so
    # every racer claims it.
    claims.write_text(text.replace(needle, needle + "        existing = None\n"),
                      encoding="utf-8")

    result = _run_drill(tree, tmp_path)
    assert result.returncode == 20, (
        "a tree whose claim path fences nothing must fail the drill at the claim "
        "stage (exit 20); got %d\nSTDERR: %s"
        % (result.returncode, result.stderr[-1500:]))


def test_drill_fails_on_missing_subject(tmp_path):
    """A4.1's second red arm, and it is a DIFFERENT code on purpose.

    With the pull path absent nothing can be measured, and a drill that
    reported "the crowd did not resolve" would be describing a race that never
    happened. 21 is "the measurement was impossible"; 20 is "the measurement
    failed". Collapsing them is how a broken import gets read as a broken
    fence."""
    tree = _tree_from_head(tmp_path)
    (tree / "framework" / "missions" / "session_bridge.py").unlink()

    result = _run_drill(tree, tmp_path)
    assert result.returncode == 21, (
        "a tree with no pull path must fail as unmeasurable (exit 21), not as a "
        "lost race; got %d\nSTDERR: %s"
        % (result.returncode, result.stderr[-1500:]))


def test_the_drill_passes_on_the_committed_tree(tmp_path):
    """And the arms above are not passing because the drill fails on everything.

    Two red arms with no green one is a sensor that says no to every question;
    this is the third leg that makes the other two mean something. It runs the
    UNMUTATED cut of HEAD, and it asserts the stage list — every stage present
    with a pass or a thin verdict — never `exit 0` alone (§4: the drill's
    top-level json is asserted on the stages array)."""
    import json

    tree = _tree_from_head(tmp_path)
    result = _run_drill(tree, tmp_path)
    assert result.returncode == 0, (
        "the drill does not pass on the committed tree; exit %d\nSTDERR: %s"
        % (result.returncode, result.stderr[-2000:]))
    report = json.loads(result.stdout)
    assert report["verdict"] == "pass", report
    stages = {row["stage"]: row["verdict"] for row in report["stages"]}
    for stage in ("hatch", "seed", "P1", "P2", "P2b", "P3", "P4", "P2h", "P5", "P6",
                  "hermeticity"):
        assert stages.get(stage) in ("pass", "thin", "note"), (
            "stage %s came back %r" % (stage, stages.get(stage)))
    assert stages.get("P7") == "thin", (
        "this arm runs with --skip-update, so P7 must record itself as THIN "
        "rather than silently absent: %r" % (stages.get("P7"),))
    assert not [row for row in report["stages"] if row["verdict"] == "fail"], report


# ---------------------------------------------------------------------------
# the staged rebuild is the leg nothing walked (A5.18)
# ---------------------------------------------------------------------------

def test_the_drill_does_not_hardcode_a_skipped_rebuild():
    """The one line that let the update path ship a build nobody ran.

    Until 2026-09-10 P7 set `REBUILD_ARG="--skip-rebuild"` and only cleared it
    under an opt-in flag no gate passed, so the staged build — dependencies,
    `next build`, the rename-last swap — was never executed by any sensor in
    this repository. The first person to run it for real was the Captain, on
    his own installed Cabinet, and it failed. The rebuild may still be skipped
    on a box that cannot do it; what it may not be is skipped by default."""
    text = _DRILL.read_text(encoding="utf-8")
    assert 'REBUILD_MODE="REAL"' in text, (
        "the drill has no real-rebuild path at all — P7 cannot walk the staged "
        "build, which is the leg that failed on the Captain's box (A5.18)")
    # The decision is made from the BOX, not from a flag: npm on PATH and an
    # installed dependency tree in this clone.
    assert re.search(r'command -v npm[^\n]*\n[^\n]*REBUILD_MODE="REAL"', text) or \
        ("command -v npm" in text and "DRILL_NODE_MODULES" in text), (
        "the drill's rebuild decision does not read the box (npm on PATH, an "
        "installed dependency tree), so it cannot be REAL where it can be")
    assert "p7_rebuild" in text, (
        "the drill's JSON report does not carry the rebuild mode, so a run that "
        "went THIN is indistinguishable from one that built for real")


def test_the_drill_job_installs_the_dependencies_its_real_rebuild_needs():
    """A5.18(2): the CI job runs the drill on the REAL path, or it proves less.

    The drill decides REAL vs THIN by looking for an installed dependency tree
    in its own clone. A job that never installs one gets THIN for ever, which
    is exactly the state that let the staged build reach an operator untested —
    so the install step and the REAL assertion are both pinned here."""
    job = _jobs()[_JOB]
    body = _run_bodies(job)
    uses = " ".join(str(step.get("uses", "")) for step in job["steps"])
    assert "actions/setup-node" in uses, (
        f"the {_JOB} job installs no node, so P7's rebuild can only be THIN")
    assert "npm ci" in body, (
        f"the {_JOB} job never installs the dashboard's dependencies, so the drill "
        "will report THIN and the staged build stays unexercised")
    assert "p7_rebuild" in body, (
        f"the {_JOB} job does not read the drill's rebuild mode, so a run that "
        "silently fell back to THIN would still be green")
    assert '"REAL"' in body, (
        f"the {_JOB} job does not REQUIRE the real rebuild; on this runner THIN "
        "is a gate switching itself off")


def test_the_drill_links_dependencies_through_the_shipped_mechanism():
    """The drill and the updater must share one mechanism, or the drill proves
    a copy of it.

    `cabinet_dash_link_modules` lives in the dashboard library that ships with
    every export; both callers source that file. A drill with a private `cp -R`
    would pass while the updater's own mechanism was broken — which is the
    shape of the defect that got here."""
    drill = _DRILL.read_text(encoding="utf-8")
    updater = _UPDATER.read_text(encoding="utf-8")
    lib = (_REPO / "cabinet" / "scripts" / "lib" / "dashboard.sh").read_text(encoding="utf-8")
    assert "cabinet_dash_link_modules() {" in lib, "the mechanism is not in the shipped library"
    for who, text in (("the drill", drill), ("the updater", updater)):
        assert "cabinet_dash_link_modules" in text, f"{who} does not call the shipped mechanism"
        assert not re.search(r"ln -s [^\n]*node_modules", text), (
            f"{who} still symlinks a node_modules — the exact line the Captain's "
            "first real apply died on")


def test_the_stub_reads_its_build_stamp_off_the_build(tmp_path):
    """The drill's health stub must not be able to invent a build stamp.

    The gate's build leg asks the running process for `build_commit` and
    compares it with the bundle. If the stub answered that from a file the
    drill wrote, the leg would be green whether or not a build had ever run —
    the disabled-sensor shape this whole unit exists to remove. So the stub
    reads it out of the artifact `next build` leaves behind, and this arm walks
    both ends: no artifact, no stamp; an artifact, the stamp that is in it."""
    import json
    stub = _REPO / "cabinet" / "scripts" / "drills" / "lib" / "stub_dashboard.py"
    src = stub.read_text(encoding="utf-8")
    assert "--build-stamp-from" in src and "required-server-files.json" in src, (
        "the stub does not read the build stamp off the built artifact")

    dash = tmp_path / "dashboard"
    (dash / ".next").mkdir(parents=True)
    out = subprocess.run(
        ["python3.12", "-c",
         "import sys; sys.path.insert(0, %r); import stub_dashboard as s;"
         "print(repr(s._built_stamp(%r)))" % (str(stub.parent), str(dash))],
        capture_output=True, text=True, timeout=_ARM_TIMEOUT)
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert out.stdout.strip() == "''", (
        "with no build output the stub still produced a build stamp: %r" % out.stdout)

    (dash / ".next" / "required-server-files.json").write_text(
        json.dumps({"config": {"env": {"CABINET_BUILD_SOURCE_COMMIT": "c0ffee1234"}}}),
        encoding="utf-8")
    out = subprocess.run(
        ["python3.12", "-c",
         "import sys; sys.path.insert(0, %r); import stub_dashboard as s;"
         "print(s._built_stamp(%r))" % (str(stub.parent), str(dash))],
        capture_output=True, text=True, timeout=_ARM_TIMEOUT)
    assert out.stdout.strip() == "c0ffee1234", (out.stdout, out.stderr)
