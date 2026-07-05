"""Lane instrument (2026-07-05) — tests for cabinet/scripts/work-graph-complete.sh.

The mission-loop defect this pins down: the script hard-gated on '*-task-*'
and REJECTED the ratified explicit node_id shapes from
instance/config/outcomes.yml (polads-001-ci, sys-001-parity, …), so a
completed outcome criterion could never be recorded — the compiler's DONE
overlay (framework/missions/compiler.py:279, keyed on payload.task_id) never
advanced. These tests run the real bash script as a subprocess against a
fixture outcomes file (OUTCOMES_FILE) and a per-test CABINET_EVENT_LOG_DIR,
then read the emitted org events back from the JSONL ledger.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "cabinet" / "scripts" / "work-graph-complete.sh"

# Mirrors the real outcomes.yml shapes: outcome ids carry the 'outcome-'
# prefix; node ids do NOT (and sys-001-parity's owner is outcome-system-
# self-001 — NOT a string-prefix relationship, the exact case split surgery
# gets wrong).
FIXTURE_OUTCOMES = """\
# fixture — same id shapes as instance/config/outcomes.yml
deployment: hq-macbook
outcomes:
  - id: outcome-alpha-001
    name: "Alpha closeout"
    status: active
    measurable_criteria:
      - node_id: alpha-001-ci
        title: "CI green"
      - node_id: alpha-001-uat
        title: "UAT wave closed"
  - id: outcome-system-self-001
    name: "Policy engine enforcing"
    status: active
    measurable_criteria:
      - node_id: sys-001-parity
        title: "CI parity proof"
"""


@pytest.fixture()
def env(tmp_path):
    """Subprocess env: fenced event dir + fixture outcomes file, no DB."""
    events = tmp_path / "events"
    outcomes = tmp_path / "outcomes.yml"
    outcomes.write_text(FIXTURE_OUTCOMES)
    e = dict(os.environ)
    e["CABINET_EVENT_LOG_DIR"] = str(events)
    e["OUTCOMES_FILE"] = str(outcomes)
    e["OFFICER_NAME"] = "test-officer"
    e.pop("DATABASE_URL", None)          # never touch Postgres from tests
    # Pin the repo root explicitly: framework/measurement role-eval modules
    # set os.environ["CABINET_ROOT"] = <tmp> PERSISTENTLY when their suites
    # run earlier in the same pytest process, and the script trusts the env —
    # an inherited stale value would cd the emitter into a dead tmp dir.
    e["CABINET_ROOT"] = str(REPO)
    return e, events


def _run(args, env):
    return subprocess.run(["bash", str(SCRIPT), *args], env=env,
                          capture_output=True, text=True, timeout=120)


def _events(events_dir: Path):
    out = []
    for f in sorted(events_dir.glob("events-*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def test_legacy_task_id_still_resolves_by_split(env):
    e, events = env
    r = _run(["outcome-alpha-001-task-002", "--status", "done",
              "--evidence", "tests green"], e)
    assert r.returncode == 0, r.stderr
    evs = _events(events)
    assert [ev["event_type"] for ev in evs] == ["work_item_completed"]
    p = evs[0]["payload"]
    assert p["task_id"] == "outcome-alpha-001-task-002"
    assert p["outcome_id"] == "outcome-alpha-001"
    assert p["task_index"] == 2
    assert p["evidence_text"] == "tests green"
    assert evs[0]["actor"] == "test-officer"
    # stdout leads with the event id for chaining
    assert r.stdout.strip()


def test_ratified_node_id_resolves_owning_outcome_from_outcomes_yml(env):
    """THE fix: sys-001-parity belongs to outcome-system-self-001 — only the
    outcomes file can say so."""
    e, events = env
    r = _run(["sys-001-parity", "--status", "verified"], e)
    assert r.returncode == 0, r.stderr
    evs = _events(events)
    assert [ev["event_type"] for ev in evs] == ["work_item_verified"]
    p = evs[0]["payload"]
    assert p["task_id"] == "sys-001-parity"
    assert p["outcome_id"] == "outcome-system-self-001"
    assert p["task_index"] == 1              # 1-based ordinal in its outcome


def test_node_ordinal_is_scoped_per_outcome(env):
    e, events = env
    r = _run(["alpha-001-uat"], e)           # default --status done
    assert r.returncode == 0, r.stderr
    p = _events(events)[0]["payload"]
    assert p["outcome_id"] == "outcome-alpha-001"
    assert p["task_index"] == 2              # second node of ITS outcome


def test_unknown_node_id_exits_2_and_emits_nothing(env):
    """FAIL-SAFE: a typo must never mint a completion event."""
    e, events = env
    r = _run(["no-such-node"], e)
    assert r.returncode == 2
    assert "neither" in r.stderr
    assert _events(events) == []


def test_missing_outcomes_file_exits_2_and_emits_nothing(env, tmp_path):
    e, events = env
    e["OUTCOMES_FILE"] = str(tmp_path / "absent.yml")
    r = _run(["sys-001-parity"], e)
    assert r.returncode == 2
    assert _events(events) == []


def test_invalid_status_still_rejected(env):
    e, events = env
    r = _run(["sys-001-parity", "--status", "shipped"], e)
    assert r.returncode == 2
    assert _events(events) == []
