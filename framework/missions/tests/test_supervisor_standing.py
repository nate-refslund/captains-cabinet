"""SOV-8 supervisor second-source tests — standing-missions.yml compiles
ONLY when the posture resolves sovereign; guardian is bit-identical."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.missions import supervisor  # noqa: E402
from framework.missions.supervisor import route_pending_tasks  # noqa: E402

STANDING = """deployment: main
generated_by: framework.missions.standing_pull
outcomes:
  - id: standing-r1-abcd1234
    name: Resolve open need NEED-11223344
    description: "[standing/R1] credential: expired token"
    measurable_criteria:
      - node_id: standing-task
        title: Engineering resolves the expired credential need
        owner_role: engineering
        depends_on: []
    status: active
"""

OUTCOMES = """outcomes:
  - id: outcome-captain
    name: Captain outcome
    description: For standing-source tests
    measurable_criteria:
      - node_id: captain-task
        title: Engineering ships the captain thing
        owner_role: engineering
        depends_on: []
    status: active
"""


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CABINET_POSTURE", raising=False)
    (tmp_path / "instance" / "config").mkdir(parents=True)
    (tmp_path / "instance" / "roles" / "active").mkdir(parents=True)
    (tmp_path / "shared" / "interfaces").mkdir(parents=True)


@pytest.fixture
def engineering_role(tmp_path):
    from framework.roles.lifecycle import create_role
    create_role("engineering", "Engineering", "Build and ship code",
                capabilities=["engineering", "deploys_code"])


def _write_standing(tmp_path):
    (tmp_path / "shared" / "interfaces" / "standing-missions.yml").write_text(
        STANDING)


def _write_outcomes(tmp_path):
    (tmp_path / "instance" / "config" / "outcomes.yml").write_text(OUTCOMES)


def _force_posture(monkeypatch, posture):
    from framework.authority import posture as posture_mod
    monkeypatch.setattr(posture_mod, "resolve_posture",
                        lambda *a, **k: posture)


class TestGuardianBitIdentical:
    def test_standing_file_ignored_in_guardian(self, tmp_path,
                                               engineering_role, monkeypatch):
        _write_outcomes(tmp_path)
        _write_standing(tmp_path)
        _force_posture(monkeypatch, "guardian")
        decisions = route_pending_tasks(dry_run=True)
        assert [d["task_id"] for d in decisions] == ["captain-task"]

    def test_no_config_no_posture_module_needed(self, tmp_path,
                                                engineering_role, monkeypatch):
        # Even a BROKEN posture module answers guardian (fail-safe import).
        _write_outcomes(tmp_path)
        _write_standing(tmp_path)
        import framework.authority.posture as posture_mod
        monkeypatch.setattr(posture_mod, "resolve_posture",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
        decisions = route_pending_tasks(dry_run=True)
        assert [d["task_id"] for d in decisions] == ["captain-task"]

    def test_absent_outcomes_still_empty_in_guardian(self, tmp_path,
                                                     engineering_role,
                                                     monkeypatch):
        _write_standing(tmp_path)
        _force_posture(monkeypatch, "guardian")
        assert route_pending_tasks(dry_run=True) == []


class TestSovereignSecondSource:
    def test_standing_missions_route_alongside_outcomes(self, tmp_path,
                                                        engineering_role,
                                                        monkeypatch):
        _write_outcomes(tmp_path)
        _write_standing(tmp_path)
        _force_posture(monkeypatch, "sovereign")
        decisions = route_pending_tasks(dry_run=True)
        assert {d["task_id"] for d in decisions} == {"captain-task",
                                                     "standing-task"}
        standing = [d for d in decisions if d["task_id"] == "standing-task"][0]
        assert standing["officer"] == "engineering"
        assert standing["outcome_id"] == "standing-r1-abcd1234"

    def test_standing_routes_with_no_outcomes_file(self, tmp_path,
                                                   engineering_role,
                                                   monkeypatch):
        _write_standing(tmp_path)
        _force_posture(monkeypatch, "sovereign")
        decisions = route_pending_tasks(dry_run=True)
        assert [d["task_id"] for d in decisions] == ["standing-task"]

    def test_missing_standing_file_is_fine(self, tmp_path, engineering_role,
                                           monkeypatch):
        _write_outcomes(tmp_path)
        _force_posture(monkeypatch, "sovereign")
        decisions = route_pending_tasks(dry_run=True)
        assert [d["task_id"] for d in decisions] == ["captain-task"]

    def test_corrupt_standing_file_degrades_to_outcomes_only(self, tmp_path,
                                                             engineering_role,
                                                             monkeypatch):
        _write_outcomes(tmp_path)
        (tmp_path / "shared" / "interfaces" / "standing-missions.yml"
         ).write_text("not: [valid outcomes")
        _force_posture(monkeypatch, "sovereign")
        decisions = route_pending_tasks(dry_run=True)
        assert [d["task_id"] for d in decisions] == ["captain-task"]

    def test_confirmed_delivery_emits_assignment_once(self, tmp_path,
                                                      engineering_role, monkeypatch):
        from framework.missions.supervisor import confirm_delivered_assignments
        from framework.events.emitter import replay
        _write_standing(tmp_path)
        _force_posture(monkeypatch, "sovereign")
        first = route_pending_tasks()
        assert [d["task_id"] for d in first] == ["standing-task"]
        confirm_delivered_assignments(first)
        # idempotent: second pass routes nothing new
        assert route_pending_tasks() == []
        assigned = [ev for ev in replay(event_types=["work_item_assigned"])]
        assert len(assigned) == 1
