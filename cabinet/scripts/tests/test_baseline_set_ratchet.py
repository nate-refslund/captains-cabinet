"""Both-ways arms for the git-aware baseline-set ratchet.

WHAT THESE PIN, and why each arm exists rather than "the script has tests".

The 2026-07-27 expansion-gate landing closed three purchase channels and NAMED
the fourth in four separate claim surfaces rather than relabelling it covered:

    a baseline line added in the SAME commit as the file it names still empties
    the surplus, and the bijection cannot tell the difference.

`test_the_named_residual_*` below IS that purchase, built commit-by-commit on a
faithful copy of this repo: a net-new production module, one line in
architecture-baseline-sets.yml, and a visible `maximum` raise. The first arm
proves the CENSUS still returns ok=True on that tree — if it ever stops, this
whole script is standing in for a check that already fires and its greens mean
nothing. The second proves the ratchet reds it. A gate whose "before" state was
never measured is an assumption.

Every arm runs against a REAL tree — the repository copied into a scratch git
repo — never a hand-written fixture shaped like the code's expectations. A
fixture written in the buggy shape makes the sensor agree with the defect, and
this program has paid for that one.

THE HARD CASE, which is the whole reason the ratchet is not "refuse every
addition": a RENAME is a legitimate PAIRED baseline edit (the baseline header
says so, and calls it the correct remedy). `test_paired_rename_stays_green`
proves the sanctioned remedy actually passes, because an untested remedy sends
the next author straight back to the instrument the gate is closing.

THE DEGENERATE ENDS are arms too: an empty diff, a pure deletion, an addition
with the baseline untouched, a baseline absent at the base commit, a shallow
clone, and a directory that is not a git work tree. A ratchet that answers
"green" to a question it could not measure is worse than no ratchet, so the
last two must ERROR (exit 2), never pass.

THE CI WIRING is round-tripped, not grepped: the workflow step's real `run:`
body is extracted and EXECUTED against both a clean head and the mutant head. A
grep would prove a string is present, never that the gate has teeth.

Provenance: authored per the 2026-07-07 full-autonomy grant.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
RATCHET_REL = "cabinet/scripts/baseline-set-ratchet.py"
CENSUS_REL = "cabinet/scripts/cognitive-architecture-census.py"
BASELINE_REL = "cabinet/config/architecture-baseline-sets.yml"
CONTRACT_REL = "cabinet/config/cognitive-architecture-contract.yml"
WORKFLOW_REL = ".github/workflows/cabinet-ci.yml"
CI_STEP_NAME = "Architecture baseline ratchet (the snapshot may not net-grow)"

# A real production module the arms rename, delete and swap. It carries no
# expansion row, so it is a plain baseline member — exactly the shape a rename
# or a deletion touches.
VICTIM = "framework/liveness/deadman.py"

_IGNORE = shutil.ignore_patterns(
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", ".next"
)
_IDENTITY = (
    "-c", "user.name=ratchet-arm",
    "-c", "user.email=ratchet-arm@example.invalid",
    "-c", "commit.gpgsign=false",
)


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False
    )
    if check:
        assert proc.returncode == 0, f"git {' '.join(args)}: {proc.stderr}"
    return proc.stdout


def _commit(cwd: Path, message: str) -> str:
    _git(cwd, "add", "-A")
    _git(cwd, *_IDENTITY, "commit", "-q", "-m", message)
    return _git(cwd, "rev-parse", "HEAD").strip()


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A faithful copy of this repository, in its own git repo, one base commit.

    Copied from the working tree rather than `git archive` so the arms measure
    the code as it stands right now — including uncommitted work, which is when
    an author most needs to know whether the gate fires.
    """

    work = tmp_path_factory.mktemp("baseline-set-ratchet")
    copy = work / "repo"
    shutil.copytree(ROOT, copy, ignore=_IGNORE, symlinks=True)
    _git(copy, "init", "-q")
    base = _commit(copy, "base: the tree as it stands")

    # NON-VACUITY ANCHOR. If the copy is not a faithful stand-in — a stray
    # untracked file, a half-applied edit — every arm below silently measures
    # something else. The copy's census must agree with the live tree's, and
    # must be GREEN, or the arms are meaningless.
    live = json.loads(_run(ROOT / CENSUS_REL, "--root", str(ROOT), "--json").stdout)
    mirrored = json.loads(_run(copy / CENSUS_REL, "--root", str(copy), "--json").stdout)
    assert mirrored["ok"] is True, mirrored["failures"]
    assert mirrored["observed"] == live["observed"], "the fixture is not this tree"
    assert mirrored["member_sets"] == live["member_sets"]
    assert VICTIM in mirrored["member_sets"]["framework_production_modules"]
    return copy, base


def _arm(repo_and_base: tuple[Path, str], name: str) -> Path:
    """Reset the fixture to base on a fresh branch, ready to be mutated."""

    copy, base = repo_and_base
    _git(copy, "checkout", "-q", "-B", name, base)
    # HARD, not a checkout: `git checkout -B` CARRIES uncommitted edits across,
    # so one arm that fails mid-mutation would silently poison every arm after
    # it — which is how the first run of this file produced five cascading
    # failures that had nothing to do with the code under test.
    _git(copy, "reset", "-q", "--hard", base)
    _git(copy, "clean", "-qfd")
    return copy


def _edit_baseline(copy: Path, *, add: list[str] = (), drop: list[str] = ()) -> None:
    path = copy / BASELINE_REL
    text = path.read_text()
    for member in drop:
        line = f"  - {member}\n"
        assert text.count(line) == 1, f"{member} is not a lone baseline line"
        text = text.replace(line, "", 1)
    anchor = "  framework_production_modules:\n"
    for member in add:
        assert text.count(anchor) == 1
        text = text.replace(anchor, anchor + f"  - {member}\n", 1)
    path.write_text(text)


def _raise_maxima(copy: Path, *, modules: int, lines: int) -> None:
    """Raise the two ceilings a net-new module consumes — the VISIBLE purchase.

    Both arms that plant a module do this, so the only thing that can red those
    trees is the ratchet, never a zero-headroom budget standing in for it.
    """

    path = copy / CONTRACT_REL
    text = path.read_text()
    for key, delta in (("framework_production_modules", modules),
                       ("framework_production_noncomment_lines", lines)):
        block = text.index(f"  {key}:")
        marker = text.index("    maximum: ", block)
        end = text.index("\n", marker)
        current = int(text[marker + len("    maximum: "):end])
        text = text[:marker] + f"    maximum: {current + delta}" + text[end:]
    path.write_text(text)


def _plant_module(copy: Path, relative: str) -> int:
    """Write a net-new production module; return its non-comment line count."""

    body = textwrap.dedent(
        '''\
        """A synthetic net-new production module planted by a ratchet arm."""


        def probe() -> str:
            return "probe"
        '''
    )
    target = copy / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body)
    return sum(1 for line in body.splitlines() if line.strip() and not line.lstrip().startswith("#"))


def _expansion_row(member: str) -> str:
    return (
        f"  - member: {member}\n"
        "    member_class: framework_production_modules\n"
        "    gate_date: '2026-07-28'\n"
        "    models_run:\n"
        "      - Fable 5\n"
        "      - Opus 5\n"
        "    adjudication: docs/proposals/synthetic-ratchet-arm.md\n"
        "    merge_refuted: framework/events/emitter.py::VALID_EVENT_TYPES synthetic arm\n"
        "    consumer: framework/env.py\n"
        "    provenance: synthetic ratchet arm\n"
    )


def _add_expansion(copy: Path, member: str) -> None:
    path = copy / CONTRACT_REL
    document = path.read_text()
    marker = "\nexpansions:\n"
    assert document.count(marker) == 1
    document = document.replace(marker, marker + _expansion_row(member), 1)
    path.write_text(document)
    parsed = yaml.safe_load(path.read_text())
    assert any(row["member"] == member for row in parsed["expansions"])


def _census(copy: Path) -> dict:
    proc = _run(copy / CENSUS_REL, "--root", str(copy), "--json")
    assert proc.stdout, proc.stderr
    return json.loads(proc.stdout)


def _ratchet(copy: Path, base: str, *extra: str) -> tuple[int, dict | None, str]:
    proc = _run(copy / RATCHET_REL, "--root", str(copy), "--base", base, "--json", *extra)
    if proc.returncode == 2:
        return proc.returncode, None, proc.stderr
    assert proc.stdout, proc.stderr
    return proc.returncode, json.loads(proc.stdout), proc.stderr


def _reasons(report: dict) -> set[str]:
    return {failure["reason"] for failure in report["failures"]}


class TestTheNamedResidual:
    """The purchase four shipped claim surfaces named as still open."""

    def test_the_census_alone_still_passes_it(self, repo):
        copy, base = repo
        _arm(repo, "residual-census")
        added = _plant_module(copy, "framework/synthetic_purchase_probe.py")
        _edit_baseline(copy, add=["framework/synthetic_purchase_probe.py"])
        _raise_maxima(copy, modules=1, lines=added)
        _commit(copy, "plant a module, excuse it with a baseline line, raise the ceilings")

        report = _census(copy)
        assert report["ok"] is True, report["failures"]
        # The LIVE registry's adjudicated members, and it grows by one each time
        # an expansion lands. What the arm proves is unchanged and is the whole
        # point: the PLANTED module is absent from this list, because a baseline
        # line plus a raised ceiling bought it invisibly.
        assert report["surplus_members"]["framework_production_modules"] == [
            "framework/authority/ownership.py",
            "framework/onboarding/estate.py",
            "framework/onboarding/salience.py",
            "framework/sources/local.py",
        ], "the planted module must NOT be surplus — that is the whole purchase"

    def test_the_ratchet_reds_it(self, repo):
        copy, base = repo
        _arm(repo, "residual-ratchet")
        added = _plant_module(copy, "framework/synthetic_purchase_probe.py")
        _edit_baseline(copy, add=["framework/synthetic_purchase_probe.py"])
        _raise_maxima(copy, modules=1, lines=added)
        _commit(copy, "the same purchase, measured by the ratchet")

        code, report, _ = _ratchet(copy, base, "--check")
        assert code == 1, report
        assert report["ok"] is False
        assert "baseline set grew" in _reasons(report)
        assert "baseline adds a path that is not a detected rename" in _reasons(report)
        assert report["classes"]["framework_production_modules"]["added"] == [
            "framework/synthetic_purchase_probe.py"
        ]
        assert report["classes"]["framework_production_modules"]["credited_removals"] == []


class TestTheSanctionedRemedies:
    """Every red above has a stated green path; these prove the paths are open."""

    def test_paired_rename_stays_green(self, repo):
        copy, base = repo
        _arm(repo, "paired-rename")
        moved = "framework/liveness/deadman_renamed.py"
        _git(copy, "mv", VICTIM, moved)
        _edit_baseline(copy, drop=[VICTIM], add=[moved])
        _commit(copy, "rename a production module, paired baseline edit, same commit")

        census = _census(copy)
        assert census["ok"] is True, census["failures"]

        code, report, _ = _ratchet(copy, base, "--check")
        assert code == 0, report
        assert report["ok"] is True
        delta = report["classes"]["framework_production_modules"]
        assert delta["added"] == [moved]
        assert delta["credited_removals"] == [VICTIM]

    def test_a_registered_expansion_never_touches_the_baseline(self, repo):
        copy, base = repo
        _arm(repo, "registered-expansion")
        member = "framework/synthetic_registered_probe.py"
        added = _plant_module(copy, member)
        _add_expansion(copy, member)
        _raise_maxima(copy, modules=1, lines=added)
        _commit(copy, "the sanctioned purchase: an adjudicated row, no baseline line")

        census = _census(copy)
        assert census["ok"] is True, census["failures"]
        assert member in census["surplus_members"]["framework_production_modules"]

        code, report, _ = _ratchet(copy, base, "--check")
        assert code == 0, report
        assert report["classes"]["framework_production_modules"]["added"] == []

    def test_a_pure_deletion_is_always_safe(self, repo):
        copy, base = repo
        _arm(repo, "pure-deletion")
        (copy / VICTIM).unlink()
        _edit_baseline(copy, drop=[VICTIM])
        _commit(copy, "delete a production module and its baseline line")

        code, report, _ = _ratchet(copy, base, "--check")
        assert code == 0, report
        delta = report["classes"]["framework_production_modules"]
        assert delta["added"] == [] and delta["credited_removals"] == [VICTIM]

    def test_an_untouched_baseline_is_green(self, repo):
        copy, base = repo
        _arm(repo, "untouched")
        (copy / "framework" / "liveness" / "deadman.py").write_text(
            (copy / VICTIM).read_text() + "\n\nSYNTHETIC_TAIL = 1\n"
        )
        _commit(copy, "edit a module without touching the baseline")

        code, report, _ = _ratchet(copy, base, "--check")
        assert code == 0, report
        assert report["classes"] == {} or all(
            not delta["added"] and not delta["removed"]
            for delta in report["classes"].values()
        )


class TestTheChannelsThatFundAnAddition:
    """A ratchet that can be funded by its own arithmetic is not a ratchet."""

    def test_a_removal_the_tree_still_carries_buys_nothing(self, repo):
        """Vacating a baseline line onto an expansion row must not pay for a member.

        This is the ratchet funding ITSELF: move an existing member out of the
        baseline and onto an adjudicated expansion row — the member stays in the
        tree, the census stays GREEN because the row registers it — and spend the
        vacated line on a net-new module. Counting removals naively, that is
        one-for-one and green. It must not be.
        """

        copy, base = repo
        _arm(repo, "uncredited-removal")
        member = "framework/synthetic_funded_probe.py"
        added = _plant_module(copy, member)
        _edit_baseline(copy, drop=[VICTIM], add=[member])
        _add_expansion(copy, VICTIM)
        _raise_maxima(copy, modules=1, lines=added)
        _commit(copy, "fund a net-new module by vacating a baseline line")

        census = _census(copy)
        assert census["ok"] is True, census["failures"]
        assert VICTIM in census["surplus_members"]["framework_production_modules"]

        code, report, _ = _ratchet(copy, base, "--check")
        assert code == 1, report
        delta = report["classes"]["framework_production_modules"]
        assert delta["removed"] == [VICTIM]
        assert delta["credited_removals"] == [], "the member is still in the tree"
        assert delta["uncredited_removals"] == [VICTIM]
        assert "baseline set grew" in _reasons(report)

    def test_a_swap_is_not_a_rename(self, repo):
        """Delete one real module, add an unrelated one: net zero, still refused."""

        copy, base = repo
        _arm(repo, "swap")
        member = "framework/synthetic_swap_probe.py"
        (copy / VICTIM).unlink()
        _plant_module(copy, member)
        _edit_baseline(copy, drop=[VICTIM], add=[member])
        _commit(copy, "swap a real module for an unadjudicated one")

        census = _census(copy)
        assert census["ok"] is True, census["failures"]

        code, report, _ = _ratchet(copy, base, "--check")
        assert code == 1, report
        delta = report["classes"]["framework_production_modules"]
        assert delta["credited_removals"] == [VICTIM], "the swap IS net-zero"
        assert _reasons(report) == {"baseline adds a path that is not a detected rename"}

    def test_a_name_the_tree_does_not_carry_is_refused(self, repo):
        copy, base = repo
        _arm(repo, "phantom")
        _edit_baseline(copy, add=["framework/synthetic_phantom_probe.py"])
        _commit(copy, "pre-load an inventory line with no file behind it")

        code, report, _ = _ratchet(copy, base, "--check")
        assert code == 1, report
        assert "baseline adds a member the tree does not carry" in _reasons(report)
        assert "baseline set grew" in _reasons(report)


class TestItRefusesRatherThanGuesses:
    """The two environments where a SHA-diff ratchet silently measures nothing."""

    def test_a_shallow_clone_errors_and_says_so(self, repo, tmp_path):
        copy, base = repo
        _arm(repo, "shallow-source")
        # A real two-commit branch, so the depth-1 clone genuinely cannot see
        # the base: the guard has to refuse, not shrug at an empty diff.
        _plant_module(copy, "framework/synthetic_shallow_probe.py")
        _edit_baseline(copy, add=["framework/synthetic_shallow_probe.py"])
        _commit(copy, "a head the shallow clone will not be able to measure")
        shallow = tmp_path / "shallow"
        clone = subprocess.run(
            ["git", "clone", "-q", "--depth", "1", f"file://{copy}", str(shallow)],
            capture_output=True, text=True, check=False,
        )
        assert clone.returncode == 0, clone.stderr
        assert _git(shallow, "rev-parse", "--is-shallow-repository").strip() == "true"

        proc = _run(copy / RATCHET_REL, "--root", str(shallow), "--base", base, "--check")
        assert proc.returncode == 2, proc.stdout
        assert "shallow" in proc.stderr
        assert "fetch-depth" in proc.stderr

    def test_a_directory_with_no_history_errors(self, repo, tmp_path):
        copy, _ = repo
        bare = tmp_path / "not-a-repo"
        bare.mkdir()
        proc = _run(copy / RATCHET_REL, "--root", str(bare), "--base", "HEAD", "--check")
        assert proc.returncode == 2, proc.stdout
        assert "git work tree" in proc.stderr

    def test_a_baseline_absent_at_the_base_is_all_addition(self, repo):
        copy, base = repo
        _arm(repo, "no-baseline-at-base")
        _git(copy, "rm", "-q", BASELINE_REL)
        without = _commit(copy, "a base commit that predates the baseline file")
        _git(copy, "checkout", "-q", base, "--", BASELINE_REL)
        _commit(copy, "the baseline file arrives")

        code, report, _ = _ratchet(copy, without, "--check")
        assert code == 1, report
        assert report["baseline_absent_at_base"] is True
        # Every class is wholly "added", and every module path is an addition
        # git cannot score as a rename — both rules fire, which is the honest
        # reading of a snapshot arriving from nowhere.
        assert _reasons(report) == {
            "baseline set grew",
            "baseline adds a path that is not a detected rename",
        }
        assert len(report["classes"]) == 6


class TestTheCiWiringIsLive:
    """The workflow step is executed, not grepped — a string proves nothing."""

    @staticmethod
    def _step_body() -> str:
        workflow = yaml.safe_load((ROOT / WORKFLOW_REL).read_text())
        steps = [
            step
            for job in workflow["jobs"].values()
            for step in job.get("steps", [])
            if step.get("name") == CI_STEP_NAME
        ]
        assert len(steps) == 1, f"expected exactly one {CI_STEP_NAME!r} step, got {len(steps)}"
        body = steps[0]["run"]
        assert RATCHET_REL in body, "the step must invoke the ratchet it is named for"
        return body

    @staticmethod
    def _execute(copy: Path, body: str, before: str) -> subprocess.CompletedProcess[str]:
        path = os.environ["PATH"]
        if shutil.which("python3.12") is None:  # pragma: no cover - runner-dependent
            shim = copy.parent / "shim"
            shim.mkdir(exist_ok=True)
            (shim / "python3.12").write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
            (shim / "python3.12").chmod(0o755)
            path = f"{shim}{os.pathsep}{path}"
        return subprocess.run(
            ["bash", "-c", body],
            cwd=str(copy),
            capture_output=True,
            text=True,
            check=False,
            env=dict(
                os.environ,
                PATH=path,
                PYTHONDONTWRITEBYTECODE="1",
                RATCHET_EVENT="push",
                RATCHET_PUSH_BEFORE=before,
            ),
        )

    def test_the_step_passes_on_an_honest_head(self, repo):
        copy, base = repo
        _arm(repo, "ci-clean")
        (copy / VICTIM).unlink()
        _edit_baseline(copy, drop=[VICTIM])
        _commit(copy, "an honest shrink")

        proc = self._execute(copy, self._step_body(), base)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "PASS" in proc.stdout

    def test_the_step_fails_on_the_named_residual(self, repo):
        copy, base = repo
        _arm(repo, "ci-mutant")
        added = _plant_module(copy, "framework/synthetic_ci_probe.py")
        _edit_baseline(copy, add=["framework/synthetic_ci_probe.py"])
        _raise_maxima(copy, modules=1, lines=added)
        _commit(copy, "the purchase, seen through the CI step")

        proc = self._execute(copy, self._step_body(), base)
        assert proc.returncode != 0, proc.stdout
        assert "baseline set grew" in proc.stdout
