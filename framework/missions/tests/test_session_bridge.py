"""Tests for the session-to-mission bridge."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from datetime import timedelta
from pathlib import Path

import pytest

# Ensure framework root is importable
_ROOT = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, _ROOT)

from cabinet.scripts.lib.work_graph import NodeStatus
from framework.events.emitter import replay
from framework.missions import claims
from framework.missions.compiler import compile_from_yaml
from framework.missions.session_bridge import get_next_task, format_task_for_session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    """Route event logs to a temp directory so emitter doesn't fail."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CABINET_CLAIM_LEASE_SECONDS", raising=False)
    # A stable holder by default: the derived one names the session process,
    # which is fine in production and noise inside a test.
    monkeypatch.setenv(claims.WORKER_ID_ENV, "holder-under-test")
    return tmp_path / "events"


@pytest.fixture
def sample_roles():
    """Sample role definitions for testing."""
    return [
        {
            "slug": "engineering",
            "title": "Chief Technology Officer",
            "capabilities": ["deploys_code", "engineering", "reviews_implementations"],
        },
        {
            "slug": "product",
            "title": "Chief Product Officer",
            "capabilities": ["product", "reviews_specs"],
        },
        {
            "slug": "research",
            "title": "Chief Research Officer",
            "capabilities": ["research", "reviews_research"],
        },
    ]


@pytest.fixture
def outcomes_dir(tmp_path):
    """Create a temporary cabinet root with an outcomes file."""
    config_dir = tmp_path / "instance" / "config"
    config_dir.mkdir(parents=True)
    return tmp_path


def _write_outcomes(outcomes_dir: Path, content: str) -> Path:
    """Write outcomes YAML and return the cabinet root."""
    outcomes_file = outcomes_dir / "instance" / "config" / "outcomes.yml"
    outcomes_file.write_text(content)
    return outcomes_dir


# ---------------------------------------------------------------------------
# Tests: get_next_task
# ---------------------------------------------------------------------------


class TestGetNextTask:
    def test_no_outcomes_file_returns_none(self, tmp_path):
        """When outcomes.yml does not exist, returns None."""
        result = get_next_task("engineering", cabinet_root=str(tmp_path))
        assert result is None

    def test_matching_role_returns_task(self, outcomes_dir, sample_roles, monkeypatch):
        """When outcomes exist and role matches, returns a task dict."""
        # Use "database schema" (early-phase keyword) so the engineering task
        # is a root node in the work graph and therefore ready immediately.
        cabinet_root = _write_outcomes(outcomes_dir, """outcomes:
  - id: outcome-001
    name: "Ship MVP"
    measurable_criteria:
      - "Database schema created and API endpoints built"
      - "User signup flow functional end-to-end"
    status: active
""")
        # Patch list_roles so the compiler finds our test roles
        monkeypatch.setattr(
            "framework.missions.compiler.list_roles",
            lambda status="active": sample_roles,
        )

        task = get_next_task("engineering", cabinet_root=str(cabinet_root))

        assert task is not None
        assert task["mission_name"] == "Ship MVP"
        assert task["assigned_role"] == "engineering"
        assert "task_description" in task
        assert "verification_criteria" in task
        assert isinstance(task["dependencies_met"], list)

    def test_no_matching_role_returns_none(self, outcomes_dir, sample_roles, monkeypatch):
        """When outcomes exist but no tasks match the role, returns None."""
        cabinet_root = _write_outcomes(outcomes_dir, """outcomes:
  - id: outcome-002
    name: "Research Phase"
    measurable_criteria:
      - "Complete competitive analysis brief"
    status: active
""")
        monkeypatch.setattr(
            "framework.missions.compiler.list_roles",
            lambda status="active": sample_roles,
        )

        # "operations" role has no matching tasks in this outcome
        task = get_next_task("operations", cabinet_root=str(cabinet_root))
        assert task is None

    def test_draft_outcomes_ignored(self, outcomes_dir, sample_roles, monkeypatch):
        """Draft outcomes are not compiled, so no tasks are returned."""
        cabinet_root = _write_outcomes(outcomes_dir, """outcomes:
  - id: outcome-draft
    name: "Future Work"
    measurable_criteria:
      - "Build API endpoints"
    status: draft
""")
        monkeypatch.setattr(
            "framework.missions.compiler.list_roles",
            lambda status="active": sample_roles,
        )

        task = get_next_task("engineering", cabinet_root=str(cabinet_root))
        assert task is None

    def test_invalid_yaml_returns_none(self, outcomes_dir):
        """Malformed outcomes file returns None (no crash)."""
        cabinet_root = _write_outcomes(outcomes_dir, "not_valid: true\n")

        task = get_next_task("engineering", cabinet_root=str(cabinet_root))
        assert task is None

    def test_projection_compile_emits_no_mission_created(
        self, outcomes_dir, sample_roles, monkeypatch, event_log_dir,
    ):
        """The compile inside the pull is a projection and never materializes.

        This runs from session hooks every few minutes; before the emit_event
        flag it wrote mission_created on every invocation. The pull now emits a
        work_item_started for the claim it takes — that IS the point of the
        claim — so the assertion names the event type it forbids instead of
        counting the ledger, and the claim=False arm below keeps the
        zero-events property for callers that only look.
        """
        cabinet_root = _write_outcomes(outcomes_dir, """outcomes:
  - id: outcome-001
    name: "Ship MVP"
    measurable_criteria:
      - "Database schema created and API endpoints built"
    status: active
""")
        monkeypatch.setattr(
            "framework.missions.compiler.list_roles",
            lambda status="active": sample_roles,
        )

        task = get_next_task("engineering", cabinet_root=str(cabinet_root))
        assert task is not None  # the projection itself still works

        assert replay(event_types=["mission_created"]) == []

    def test_pull_records_holder_gap(self, outcomes_dir, event_log_dir):
        """A §3 sensor 4: the pull path's silence leaves a row behind.

        No roster and no owner on the node, which is the state a fresh
        instance is actually in. Before this the pull answered None and wrote
        nothing at all, so "why is nothing happening" had no answer anywhere
        in the tree."""
        cabinet_root = _write_outcomes(outcomes_dir, """outcomes:
  - id: outcome-unowned
    name: "Nobody owns this"
    measurable_criteria:
      - node_id: lonely-task
        title: A thing with no owner
        depends_on: []
    status: active
""")

        assert get_next_task("engineering", cabinet_root=str(cabinet_root)) is None

        recorded = replay(event_types=["capability_gap_recorded"])
        assert len(recorded) == 1, recorded
        payload = recorded[0]["payload"]
        assert payload["kind"] == "skill"
        assert payload["dedup_key"] == "holder:outcome-unowned:lonely-task"

    def test_a_failing_observation_never_costs_the_pull(
        self, outcomes_dir, sample_roles, monkeypatch, event_log_dir,
    ):
        """§3's caller invariant: the observation cannot cost a task.

        `_observe_gaps` wraps the whole holder-gap pass because the caller is
        the locked prompt hook: an exception here would kill the officer's
        session, not just the observation. Nothing in the tree went red when
        that `except` was deleted, so this is the arm that notices.

        And the failure is recorded DURABLY. The only production caller is
        cabinet/scripts/hooks/session-task-inject.sh, which runs the pull as
        `RESULT="$(python3 -c "..." 2>/dev/null)"` — stderr is discarded
        there, so an observation failing on every tick would be exactly the
        silence this unit exists to remove, one layer up. The sibling claim
        path in this same function already writes `claims.err` beside the
        ledger; the observation joins it.
        """
        from framework.missions import gaps as gaps_module

        cabinet_root = _write_outcomes(outcomes_dir, """outcomes:
  - id: outcome-owned
    name: "Somebody owns this"
    measurable_criteria:
      - node_id: owned-task
        title: A thing with an owner
        owner_role: engineering
        depends_on: []
    status: active
""")
        monkeypatch.setattr(
            "framework.missions.compiler.list_roles",
            lambda status="active": sample_roles,
        )

        def _boom(*args, **kwargs):
            raise RuntimeError("the observer is down")

        monkeypatch.setattr(gaps_module, "observe_holder_gaps", _boom)

        task = get_next_task("engineering", cabinet_root=str(cabinet_root))

        assert task is not None, "a failing observation swallowed the task"
        assert task["task_id"] == "owned-task"

        durable = claims.error_path()
        assert durable.exists(), "the observation failure left no durable trace"
        text = durable.read_text(encoding="utf-8")
        assert "the observer is down" in text, text
        assert "holder-gap observation failed" in text, text

    def test_claim_false_is_side_effect_free(
        self, outcomes_dir, sample_roles, monkeypatch, event_log_dir,
    ):
        """The read-only projection writes nothing at all."""
        cabinet_root = _write_outcomes(outcomes_dir, """outcomes:
  - id: outcome-001
    name: "Ship MVP"
    measurable_criteria:
      - "Database schema created and API endpoints built"
    status: active
""")
        monkeypatch.setattr(
            "framework.missions.compiler.list_roles",
            lambda status="active": sample_roles,
        )

        task = get_next_task("engineering", cabinet_root=str(cabinet_root), claim=False)
        assert task is not None
        assert task.get("claim_id") is None
        assert list(event_log_dir.glob("events-*.jsonl")) == []
        assert claims.live_claims() == {}


# ---------------------------------------------------------------------------
# Tests: format_task_for_session
# ---------------------------------------------------------------------------


class TestFormatTaskForSession:
    def test_produces_readable_string(self):
        """Formatted output contains mission name, task, role, and criteria."""
        task = {
            "mission_name": "Ship MVP",
            "task_id": "outcome-001-task-000",
            "task_description": "Core API endpoints deployed",
            "verification_criteria": ["API returns 200 on /health"],
            "dependencies_met": ["Database schema created"],
            "assigned_role": "engineering",
        }
        result = format_task_for_session(task)

        assert "Ship MVP" in result
        assert "Core API endpoints deployed" in result
        assert "engineering" in result
        assert "API returns 200 on /health" in result
        assert "Database schema created" in result

    def test_empty_dependencies(self):
        """Works correctly when no dependencies are met (root task)."""
        task = {
            "mission_name": "Research Phase",
            "task_id": "outcome-002-task-000",
            "task_description": "Competitive analysis",
            "verification_criteria": ["Brief published"],
            "dependencies_met": [],
            "assigned_role": "research",
        }
        result = format_task_for_session(task)

        assert "Research Phase" in result
        assert "Competitive analysis" in result
        assert "Completed dependencies" not in result

    def test_multiple_criteria(self):
        """Multiple verification criteria are all listed."""
        task = {
            "mission_name": "Launch",
            "task_id": "outcome-001-task-001",
            "task_description": "Deploy to production",
            "verification_criteria": [
                "Health check passes",
                "No errors in logs",
                "Response time under 200ms",
            ],
            "dependencies_met": [],
            "assigned_role": "engineering",
        }
        result = format_task_for_session(task)

        assert "Health check passes" in result
        assert "No errors in logs" in result
        assert "Response time under 200ms" in result


# ---------------------------------------------------------------------------
# Tests: the claim in the real pull path
# ---------------------------------------------------------------------------


_ONE_TASK = """outcomes:
  - id: outcome-001
    name: "Ship MVP"
    measurable_criteria:
      - "Database schema created and API endpoints built"
    status: active
"""

_TWO_TASKS = """outcomes:
  - id: outcome-001
    name: "Ship MVP"
    measurable_criteria:
      - node_id: task-a
        title: "Database schema created and API endpoints built"
        owner_role: engineering
        depends_on: []
      - node_id: task-b
        title: "Backend build for the second endpoint"
        owner_role: engineering
    status: active
"""


@pytest.fixture
def one_task_root(outcomes_dir, sample_roles, monkeypatch):
    monkeypatch.setattr(
        "framework.missions.compiler.list_roles",
        lambda status="active": sample_roles,
    )
    return _write_outcomes(outcomes_dir, _ONE_TASK)


_ONE_TASK_EXPLICIT_OWNER = """outcomes:
  - id: outcome-001
    name: "Ship MVP"
    measurable_criteria:
      - node_id: task-a
        title: "Database schema created"
        owner_role: engineering
        depends_on: []
    status: active
"""


@pytest.fixture
def explicit_owner_root(outcomes_dir):
    """An outcome whose owner is declared, so no roster lookup is needed.

    Subprocess arms cannot see a monkeypatched list_roles, and a roster is not
    what those arms are measuring.
    """
    return _write_outcomes(outcomes_dir, _ONE_TASK_EXPLICIT_OWNER)


@pytest.fixture
def two_task_root(outcomes_dir, sample_roles, monkeypatch):
    monkeypatch.setattr(
        "framework.missions.compiler.list_roles",
        lambda status="active": sample_roles,
    )
    return _write_outcomes(outcomes_dir, _TWO_TASKS)


class TestPullClaims:
    def test_pull_claims_by_default(self, one_task_root):
        """RED before: the pull emitted nothing and claimed nothing."""
        task = get_next_task("engineering", cabinet_root=str(one_task_root))

        assert task["claim_id"]
        assert task["expires_at"]
        assert task["holder"] == "holder-under-test"
        started = replay(event_types=["work_item_started"])
        assert len(started) == 1
        assert started[0]["payload"]["task_id"] == task["task_id"]
        assert started[0]["payload"]["outcome_id"] == "outcome-001"

    def test_pull_emits_ids_and_a_recompile_overlays_in_progress(self, one_task_root):
        """A §2 sensor 4, END TO END: the pull's payload is the shape the
        overlay keys on.

        The two halves are proved apart elsewhere — the started event carries
        both ids, and an unexpired lease holds a node IN_PROGRESS — but neither
        proves the SEAM. The overlay matches on ``payload.outcome_id`` and
        ``payload.task_id`` together (compiler.py); a pull that emitted the
        right ids under the wrong keys, or the node id where the overlay wants
        the outcome id, would pass both halves and still never take the task
        out of ``ready_tasks()``. So this one goes through the real compile.

        RED before this unit: ``get_next_task`` emitted nothing at all, so the
        recompiled node stays PENDING and stays ready.
        """
        task = get_next_task("engineering", cabinet_root=str(one_task_root))
        assert task is not None

        outcomes_file = one_task_root / "instance" / "config" / "outcomes.yml"
        missions = compile_from_yaml(
            outcomes_file, actor="test", roles=None, emit_event=False,
        )
        graph = missions[0]["work_graph"]
        assert graph.nodes[task["task_id"]].status is NodeStatus.IN_PROGRESS
        assert task["task_id"] not in [node.id for node in graph.ready_tasks()]

    def test_second_holder_gets_nothing_while_the_claim_is_live(
        self, one_task_root, monkeypatch,
    ):
        """RED before: session_bridge handed the SAME node to every caller."""
        first = get_next_task("engineering", cabinet_root=str(one_task_root))
        assert first is not None

        monkeypatch.setenv(claims.WORKER_ID_ENV, "a-second-session")
        second = get_next_task("engineering", cabinet_root=str(one_task_root))
        assert second is None
        assert len(replay(event_types=["work_item_started"])) == 1

    def test_own_claim_is_renewed_and_not_re_returned(self, one_task_root):
        """A2.3: re-injecting the same task every tick for its whole life is noise."""
        first = get_next_task("engineering", cabinet_root=str(one_task_root))
        assert first is not None

        again = get_next_task("engineering", cabinet_root=str(one_task_root))
        assert again is None

        renewed = replay(event_types=["work_item_claim_renewed"])
        assert len(renewed) == 1
        assert renewed[0]["payload"]["claim_id"] == first["claim_id"]
        assert len(replay(event_types=["work_item_started"])) == 1

    def test_include_own_returns_the_renewed_task(self, one_task_root):
        first = get_next_task("engineering", cabinet_root=str(one_task_root))
        again = get_next_task(
            "engineering", cabinet_root=str(one_task_root), include_own=True,
        )
        assert again is not None
        assert again["task_id"] == first["task_id"]
        assert again["claim_id"] == first["claim_id"]
        assert again["expires_at"] > first["expires_at"]

    def test_a_tick_shorter_than_the_lease_never_loses_the_task(self, one_task_root):
        """A2.1: 300 s tick, 900 s lease — renew on EVERY tick, not under 25%.

        A 300 s tick against a 900 s lease finds two thirds of the lease
        remaining and would never renew under a 25%-remaining rule, so the task
        would be lost the first time the worker took longer than the lease.
        """
        first = get_next_task("engineering", cabinet_root=str(one_task_root))
        assert first is not None
        assert claims.DEFAULT_LEASE_SECONDS == 900

        # Four ticks at 300 s each = 1200 s > the 900 s lease.
        for _ in range(4):
            assert get_next_task("engineering", cabinet_root=str(one_task_root)) is None

        live = claims.live_claim(first["task_id"])
        assert live is not None
        assert live["claim_id"] == first["claim_id"]
        assert len(replay(event_types=["work_item_claim_renewed"])) == 4

        # ...and the completion is accepted, which is the property that matters.
        event = claims.complete(
            first["task_id"], "outcome-001", "holder-under-test",
            claim_id=first["claim_id"], status="done",
        )
        assert event["event_type"] == "work_item_completed"

    def test_a_second_holder_takes_the_next_free_task(self, two_task_root, monkeypatch):
        first = get_next_task("engineering", cabinet_root=str(two_task_root))
        monkeypatch.setenv(claims.WORKER_ID_ENV, "a-second-session")
        second = get_next_task("engineering", cabinet_root=str(two_task_root))

        assert first is not None and second is not None
        assert first["task_id"] != second["task_id"]
        assert first["claim_id"] != second["claim_id"]

    def test_expired_lease_returns_the_task_to_the_next_puller(
        self, one_task_root, monkeypatch,
    ):
        first = get_next_task("engineering", cabinet_root=str(one_task_root))
        assert first is not None

        # Re-emit the same claim as if it had been taken an hour ago.
        past = claims.utcnow() - timedelta(seconds=3600)
        claims.claim("nothing", "nothing", "x")  # keeps the ledger non-trivial
        _expire_claim(first["task_id"], past)

        monkeypatch.setenv(claims.WORKER_ID_ENV, "a-second-session")
        second = get_next_task("engineering", cabinet_root=str(one_task_root))
        assert second is not None
        assert second["task_id"] == first["task_id"]
        assert second["claim_id"] != first["claim_id"]

    def test_format_prints_the_token_and_the_completion_command(self, one_task_root):
        task = get_next_task("engineering", cabinet_root=str(one_task_root))
        text = format_task_for_session(task)
        assert task["claim_id"] in text
        assert "--claim" in text
        assert "work-graph-complete.sh" in text

    def test_claim_path_failure_returns_none_and_records(
        self, one_task_root, monkeypatch, event_log_dir,
    ):
        """A2.5: the hook must exit 0 even when the claim path cannot run."""
        def _boom(*args, **kwargs):
            raise PermissionError("lock dir is not writable")

        monkeypatch.setattr(claims, "live_claims", _boom)
        assert get_next_task("engineering", cabinet_root=str(one_task_root)) is None
        assert "lock dir is not writable" in (
            event_log_dir / claims.ERROR_FILENAME
        ).read_text()


def _expire_claim(task_id, moment):
    """Rewrite the live claim's expiry into the past, in the ledger itself."""
    import json as _json

    log_dir = Path(os.environ["CABINET_EVENT_LOG_DIR"])
    for path in sorted(log_dir.glob("events-*.jsonl")):
        lines = path.read_text().splitlines()
        out = []
        for line in lines:
            event = _json.loads(line)
            payload = event.get("payload") or {}
            if (
                event["event_type"] == "work_item_started"
                and payload.get("task_id") == task_id
            ):
                payload["expires_at"] = moment.isoformat()
                event["payload"] = payload
            out.append(_json.dumps(event))
        path.write_text("\n".join(out) + "\n")


# ---------------------------------------------------------------------------
# Holder derivation through the real process shape (A2.2)
# ---------------------------------------------------------------------------


_HOOK_SHAPED_PULL = """
import json, os, sys
sys.path.insert(0, os.environ["CABINET_REPO_ROOT"])
from framework.missions.session_bridge import get_next_task
from framework.missions import claims
task = get_next_task("engineering", cabinet_root=os.environ["CABINET_TEST_ROOT"])
print(json.dumps({
    "holder": claims.derive_holder("engineering"),
    "task": None if task is None else task["task_id"],
    "claim": None if task is None else task["claim_id"],
}))
"""


def test_two_sessions_of_one_role_get_one_claim_without_a_worker_id(
    explicit_owner_root, tmp_path, event_log_dir, monkeypatch,
):
    """A2.2 drill arm: two distinct parent shells, CABINET_WORKER_ID unset.

    The process shape is the hook's — session shell → hook shell → python — so
    the derived holder names the SESSION, which is distinct between the two
    invocations. Both then race for the same node and exactly one claim exists.

    Without the session-pid half of A2.2 both processes would derive the bare
    role slug, share one holder, and the second would be handed the first one's
    claim as its own: two workers, one identity, and nothing to tell them apart
    until the germline ceremony ships a worker id.

    LIMIT, stated rather than implied: this reproduces the hook's PROCESS SHAPE
    against the live pull path; it does not execute the locked hook file, which
    is schg-locked and calls the box's own python3.
    """
    inner = tmp_path / "hook.sh"
    inner.write_text(
        "#!/bin/bash\n"
        '"$CABINET_TEST_PY" -c "$CABINET_TEST_SRC"\n'
        "exit 0\n"          # keeps bash from exec-ing python in place
    )
    inner.chmod(0o755)
    outer = tmp_path / "session.sh"
    outer.write_text("#!/bin/bash\nbash \"$1\"\nexit 0\n")
    outer.chmod(0o755)

    env = dict(os.environ)
    env.pop(claims.WORKER_ID_ENV, None)
    env.pop("PYTEST_CURRENT_TEST", None)
    env["CABINET_EVENT_LOG_DIR"] = str(event_log_dir)
    env["CABINET_REPO_ROOT"] = _ROOT
    env["CABINET_TEST_ROOT"] = str(explicit_owner_root)
    env["CABINET_TEST_PY"] = sys.executable
    env["CABINET_TEST_SRC"] = _HOOK_SHAPED_PULL
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    results = []
    for _ in range(2):
        proc = subprocess.run(
            ["bash", str(outer), str(inner)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
        )
        assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
        results.append(json.loads(proc.stdout.decode("utf-8").strip()))

    holders = {row["holder"] for row in results}
    assert len(holders) == 2, "two sessions of one role shared a holder: %r" % holders
    assert all(holder.startswith("engineering@session:") for holder in holders)

    claimed = [row for row in results if row["claim"]]
    assert len(claimed) == 1, results
    assert len(replay(event_types=["work_item_started"])) == 1
