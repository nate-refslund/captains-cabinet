"""Tests for the armed self-improvement loop's reversibility safeguard.

Captain ruling 2026-07-26: auto-apply was armed (REPORT_ONLY=0 on the
`self-improvement-loop` services.yml row) with the risk stated, on condition
that (a) every auto-applied change is individually reversible and logged with
what changed, why and the evidence it cited — a ONE-COMMAND revert of any
single application — and (b) a visible weekly line states what the loop
applied to itself.

These tests pin both. They are the reason the arming is observably safe rather
than merely fast, so they are load-bearing on the ruling itself: if the undo
round-trip stops working, the Captain's accepted risk window stops being
closeable.

Every test owns its own tmp CABINET_ROOT — no live role, journal, event ledger
or skill file is touched (the repo-root conftest fence plus an explicit root
override; the same idiom as test_killswitch_watchdog.py).
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI = REPO_ROOT / "cabinet" / "scripts" / "self-improvement-journal.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_cli_module():
    """Import the hyphenated CLI by path (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location("_sij", CLI)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def cab(tmp_path, monkeypatch):
    """A throwaway cabinet root with one role and an empty journal."""
    (tmp_path / "instance" / "roles" / "active").mkdir(parents=True)
    (tmp_path / "cabinet" / "logs").mkdir(parents=True)
    (tmp_path / "instance" / "roles" / "active" / "testrole.yml").write_text(
        "slug: testrole\ncharter: test\ncapabilities:\n- base_cap\n"
        "authority_level: mission_executor\n"
    )
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    return tmp_path


def _journal(cab_root: Path) -> Path:
    return cab_root / "cabinet" / "logs" / "self-improvement-applications.jsonl"


def _apply_cap(cab_root: Path, cap: str = "new_cap") -> str:
    """Do exactly what the armed loop does for an add_hat proposal."""
    from framework.learning import self_improvement_loop as L
    from framework.roles.lifecycle import adapt_role
    adapt_role("testrole", adaptation_type="capability_added",
               description=f"self-improvement: added {cap}",
               changes={"capability": cap}, evidence="proposal p-1",
               rationale="pattern seen 3x", approved_by="self_improvement_loop")
    aid = L._journal_application(
        "capability_added", "testrole", {"capability": cap},
        {"op": "capability_removed", "role_slug": "testrole", "capability": cap},
        "p-1", "proposal p-1", "pattern seen 3x", "loop-1")
    assert aid
    return aid


def _run_cli(cab_root: Path, *args: str) -> subprocess.CompletedProcess:
    import os
    env = dict(os.environ)
    env["CABINET_ROOT"] = str(cab_root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, env=env, timeout=120)


# ---------------------------------------------------------------------------
# (a) every application is logged with what/why/evidence + its exact inverse
# ---------------------------------------------------------------------------

def test_application_is_journalled_with_what_why_evidence_and_inverse(cab):
    aid = _apply_cap(cab)
    rows = [json.loads(x) for x in _journal(cab).read_text().splitlines() if x.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["application_id"] == aid
    assert row["kind"] == "capability_added"
    assert row["change"]["capability"] == "new_cap"      # what changed
    assert row["rationale"] == "pattern seen 3x"          # why
    assert row["evidence"] == "proposal p-1"              # the evidence cited
    assert row["undo"] == {"op": "capability_removed",    # the exact inverse
                           "role_slug": "testrole", "capability": "new_cap"}
    assert row["reverted"] is False
    assert row["loop_id"] == "loop-1"


def test_authority_change_records_its_pre_image(cab):
    """An authority_change inverse only exists against the BEFORE value, and
    nothing else in the tree records it — lineage.yml carries no `changes`."""
    from framework.learning import self_improvement_loop as L
    from framework.roles.lifecycle import adapt_role, load_role
    before = load_role("testrole")["authority_level"]
    adapt_role("testrole", adaptation_type="authority_change", description="widen",
               changes={"authority_level": "captain_proxy"}, evidence="proposal p-2",
               rationale="earned", approved_by="self_improvement_loop")
    L._journal_application(
        "authority_change", "testrole",
        {"authority_level_before": before, "authority_level_after": "captain_proxy"},
        {"op": "authority_change", "role_slug": "testrole", "authority_level": before},
        "p-2", "proposal p-2", "earned", "loop-1")
    row = json.loads(_journal(cab).read_text().splitlines()[-1])
    assert row["undo"]["authority_level"] == "mission_executor"


def test_journal_write_failure_never_aborts_the_application(cab, monkeypatch):
    """Journalling is best-effort-LOUD: a half-applied loop is worse than an
    unlogged one, and the org events stay the durable record either way."""
    from framework.learning import self_improvement_loop as L
    monkeypatch.setattr(L, "_journal_path",
                        lambda: cab / "nope" / "\0bad" / "j.jsonl")
    assert L._journal_application("capability_added", "testrole", {}, {},
                                  None, None, None) is None


# ---------------------------------------------------------------------------
# one-command revert, per application
# ---------------------------------------------------------------------------

def test_undo_capability_round_trip(cab):
    from framework.roles.lifecycle import load_role
    aid = _apply_cap(cab)
    assert "new_cap" in load_role("testrole")["capabilities"]

    dry = _run_cli(cab, "--undo", aid, "--dry-run")
    assert dry.returncode == 0, dry.stderr
    assert "dry-run" in dry.stdout
    assert "new_cap" in load_role("testrole")["capabilities"], "dry-run mutated state"

    real = _run_cli(cab, "--undo", aid)
    assert real.returncode == 0, real.stderr
    assert "new_cap" not in load_role("testrole")["capabilities"]


def test_undo_authority_restores_the_pre_image(cab):
    from framework.learning import self_improvement_loop as L
    from framework.roles.lifecycle import adapt_role, load_role
    adapt_role("testrole", adaptation_type="authority_change", description="widen",
               changes={"authority_level": "captain_proxy"},
               approved_by="self_improvement_loop")
    aid = L._journal_application(
        "authority_change", "testrole",
        {"authority_level_before": "mission_executor",
         "authority_level_after": "captain_proxy"},
        {"op": "authority_change", "role_slug": "testrole",
         "authority_level": "mission_executor"}, None, None, None)
    assert load_role("testrole")["authority_level"] == "captain_proxy"
    assert _run_cli(cab, "--undo", aid).returncode == 0
    assert load_role("testrole")["authority_level"] == "mission_executor"


def test_undo_skill_status_round_trip(cab):
    from framework.learning import self_improvement_loop as L
    skill = cab / "memory" / "skills" / "evolved" / "s.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: s\nstatus: validated\n---\n\nbody\n")
    aid = L._journal_application(
        "skill_validated", "s", {"status_before": "draft"},
        {"op": "skill_status", "skill_path": str(skill), "status": "draft"},
        None, None, None)
    assert _run_cli(cab, "--undo", aid).returncode == 0
    assert "status: draft" in skill.read_text()


def test_double_undo_is_refused(cab):
    aid = _apply_cap(cab)
    assert _run_cli(cab, "--undo", aid).returncode == 0
    again = _run_cli(cab, "--undo", aid)
    assert again.returncode == 1
    assert "already reverted" in again.stderr


def test_unknown_application_id_is_refused(cab):
    r = _run_cli(cab, "--undo", "sia-doesnotexist")
    assert r.returncode == 1


def test_undo_without_a_pre_image_refuses_rather_than_guessing(cab):
    """A pre-journal application cannot be inverted — say so, never invent a
    value to write into a role's authority field."""
    _journal(cab).write_text(json.dumps({
        "application_id": "sia-old", "applied_at": "2026-07-01T00:00:00+00:00",
        "kind": "authority_change", "role_slug": "testrole",
        "change": {}, "undo": {"op": "authority_change",
                               "role_slug": "testrole", "authority_level": None},
        "reverted": False,
    }) + "\n")
    r = _run_cli(cab, "--undo", "sia-old")
    assert r.returncode == 1
    assert "no pre-image" in r.stderr


# ---------------------------------------------------------------------------
# (b) the visible weekly line
# ---------------------------------------------------------------------------

def test_weekly_section_is_honest_when_nothing_was_applied(cab):
    r = _run_cli(cab, "--weekly-section", "--now", "2026-07-26T09:30:00Z")
    assert r.returncode == 0
    assert "Self-improvement — applied to itself" in r.stdout
    assert "**Nothing.**" in r.stdout
    # An empty window must not read as "the loop is off".
    assert "not the loop being off" in r.stdout


def test_weekly_section_counts_only_real_applications(cab):
    """Revert rows are bookkeeping: counting them would inflate the report with
    the loop's own undos."""
    aid = _apply_cap(cab)
    _apply_cap(cab, "second_cap")
    assert _run_cli(cab, "--undo", aid).returncode == 0
    r = _run_cli(cab, "--weekly-section", "--now", "2026-07-26T09:30:00Z")
    assert r.returncode == 0
    assert "**1 change(s) stand; 1 were reverted.**" in r.stdout
    assert "why: pattern seen 3x" in r.stdout
    assert "evidence cited: proposal p-1" in r.stdout


def test_weekly_section_window_excludes_older_applications(cab):
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    _journal(cab).write_text(json.dumps({
        "application_id": "sia-old", "applied_at": old,
        "kind": "capability_added", "role_slug": "testrole",
        "change": {"capability": "ancient"}, "undo": {}, "reverted": False,
    }) + "\n")
    r = _run_cli(cab, "--weekly-section")
    assert r.returncode == 0
    assert "**Nothing.**" in r.stdout


def test_torn_journal_line_is_skipped_not_fatal(cab):
    _apply_cap(cab)
    with open(_journal(cab), "a") as f:
        f.write('{"application_id": "sia-tor')  # crash mid-append
    r = _run_cli(cab, "--list")
    assert r.returncode == 0
    assert "new_cap" in r.stdout


def test_cli_module_declares_the_measured_mutation_surface():
    """The docstring is the Captain-facing claim about what arming bought. It
    must keep naming the code-is-out-of-reach construction — if the loop ever
    grows a code-apply path, this claim becomes a lie and the ruling changes."""
    text = CLI.read_text()
    assert "CODE IS OUT OF REACH BY CONSTRUCTION" in text
    assert "gate.ratify" in text
    src = (REPO_ROOT / "framework" / "learning" / "self_improvement_loop.py").read_text()
    assert "_route_code_diff_through_gate" in src
    assert "NEVER _apply_proposal" in src
