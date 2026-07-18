"""The portfolio Chair's first-boot resources survive a fresh clone (fresh-
hatch #13).

Two defects fixed:
  * the operating-loop skill lived at memory/skills/evolved/chair-front-door-
    loop.md, which is GITIGNORED — absent on a fresh clone, so chair-preflight
    check 5 failed deterministically. It is now a TRACKED resource at
    memory/skills/chair-front-door-loop.md, and every referrer points there.
  * chair-preflight check 4 HARD-required a personal `brain` MCP; a captain-
    agnostic portfolio Chair (and the egg, which scrubs instance/) ships no
    brain server, so it false-failed. brain is now optional (non-fatal).

Run: python3.12 -m pytest cabinet/scripts/tests/test_portfolio_chair_resources.py -q
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PREFLIGHT = REPO_ROOT / "cabinet" / "scripts" / "chair-preflight.sh"
TRACKED_SKILL = "memory/skills/chair-front-door-loop.md"


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT,
                          capture_output=True, text=True).stdout.strip()


def test_skill_is_tracked_at_the_canonical_path():
    assert _git("ls-files", TRACKED_SKILL) == TRACKED_SKILL, (
        f"{TRACKED_SKILL} is not a tracked file — a fresh clone would lack the "
        "Chair's operating loop")
    # and it is non-trivial content, not an accidental empty/stub file
    assert (REPO_ROOT / TRACKED_SKILL).stat().st_size > 1000


def test_no_tracked_referrer_points_at_the_gitignored_evolved_path():
    # A tracked *functional* referrer (script / agent-doc / config / plan) to
    # the gitignored evolved/ path breaks a fresh clone, so it MUST trip this.
    # Two benign self-matches are excluded — neither is a resource referrer:
    #   * this test file itself, which must contain the grep literal to grep for it;
    #   * shared/interfaces/reviews/ — FW-019 review artifacts are prose recording
    #     the relocation history, not a path anything loads from.
    hits = subprocess.run(
        ["git", "grep", "-lI", "evolved/chair-front-door-loop", "--",
         ":(exclude)cabinet/scripts/tests/test_portfolio_chair_resources.py",
         ":(exclude)shared/interfaces/reviews/"],
        cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    assert not hits, (
        "tracked files still reference the gitignored evolved/ skill path:\n"
        + hits)


def test_expected_referrers_point_at_the_tracked_path():
    referrers = subprocess.run(
        ["git", "grep", "-lI", TRACKED_SKILL],
        cwd=REPO_ROOT, capture_output=True, text=True).stdout.split()
    for expected in (
        "cabinet/scripts/chair-preflight.sh",
        "presets/portfolio/agents/cos.md",
        "instance/agents/cos.md",
        "instance/officer-skills/cos.txt",
        "docs/plans/EXECUTION-STATUS.md",
        "docs/plans/operative-egg-plan-2026-07-07.md",
    ):
        assert expected in referrers, (expected, referrers)


def _preflight_fixture(tmp_path: Path, *, skill: bool, brain: bool) -> Path:
    root = tmp_path / "root"
    (root / "cabinet" / "scripts").mkdir(parents=True)
    # chair-preflight derives ROOT from its own location (../..), so run a COPY
    # inside the fixture tree.
    dst = root / "cabinet" / "scripts" / "chair-preflight.sh"
    dst.write_text(PREFLIGHT.read_text(encoding="utf-8"), encoding="utf-8")
    dst.chmod(0o755)
    (root / "instance" / "config").mkdir(parents=True)
    extra = {"mcpServers": ({"brain": {"command": "x"}} if brain else {})}
    import json
    (root / "instance" / "config" / "extra-mcps.json").write_text(
        json.dumps(extra), encoding="utf-8")
    if skill:
        (root / "memory" / "skills").mkdir(parents=True)
        (root / "memory" / "skills" / "chair-front-door-loop.md").write_text(
            "# fixture skill\n", encoding="utf-8")
    return root, dst


def _run_preflight(dst: Path) -> str:
    p = subprocess.run(["bash", str(dst)], capture_output=True, text=True, timeout=60)
    return p.stdout + p.stderr


def test_preflight_passes_skill_and_is_soft_on_missing_brain(tmp_path):
    _root, dst = _preflight_fixture(tmp_path, skill=True, brain=False)
    out = _run_preflight(dst)
    # check 5: the tracked skill is found
    assert "operating-loop skill present" in out, out
    assert "chair-front-door-loop skill missing" not in out, out
    # check 4: a missing brain is a soft note, NOT a hard fail
    assert "brain MCP not configured" in out, out
    assert "brain MCP not in extra-mcps.json" not in out, out


def test_preflight_still_fails_a_genuinely_missing_skill(tmp_path):
    # negative control: check 5 keeps its teeth when the skill is truly absent
    _root, dst = _preflight_fixture(tmp_path, skill=False, brain=False)
    out = _run_preflight(dst)
    assert "chair-front-door-loop skill missing" in out, out
