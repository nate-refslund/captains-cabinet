"""Lane instrument (2026-07-05) — tests for cabinet/scripts/work-graph-complete.sh.

The mission-loop defect this pins down: the script hard-gated on '*-task-*'
and REJECTED the ratified explicit node_id shapes from
instance/config/outcomes.yml (bakery-001-ci, sys-001-parity, …), so a
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


# ---------------------------------------------------------------------------
# The claim fence (2026-09-07)
# ---------------------------------------------------------------------------


def _claim(env_pair, task_id, outcome_id, holder):
    """Take a real claim in the same ledger the script will write to."""
    e, _ = env_pair
    source = (
        "import json, sys; sys.path.insert(0, %r)\n"
        "from framework.missions import claims\n"
        "print(json.dumps(claims.claim(%r, %r, %r)))\n"
    ) % (str(REPO), task_id, outcome_id, holder)
    out = subprocess.run(
        [os.environ.get("CABINET_PYTHON", "python3.12"), "-c", source],
        env=e, capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_completion_with_the_live_token_is_accepted(env):
    """RED before: --claim did not exist and the script emitted unconditionally."""
    e, events = env
    held = _claim(env, "alpha-001-ci", "outcome-alpha-001", "holder-1")
    r = _run(["alpha-001-ci", "--status", "done", "--evidence", "green",
              "--claim", held["claim_id"]], e)
    assert r.returncode == 0, r.stderr
    completed = [ev for ev in _events(events) if ev["event_type"] == "work_item_completed"]
    assert len(completed) == 1
    assert completed[0]["payload"]["claim_id"] == held["claim_id"]
    assert completed[0]["payload"]["task_index"] == 1
    assert completed[0]["actor"] == "test-officer"


def test_a_stale_token_exits_4_and_emits_nothing(env):
    e, events = env
    _claim(env, "alpha-001-ci", "outcome-alpha-001", "holder-1")
    r = _run(["alpha-001-ci", "--status", "done", "--claim", "not-the-token"], e)
    assert r.returncode == 4, (r.returncode, r.stdout, r.stderr)
    assert [ev for ev in _events(events) if ev["event_type"] == "work_item_completed"] == []


def test_a_second_completion_exits_4_and_the_replay_still_counts_one(env):
    """RED before: the script emitted a second work_item_completed every time."""
    e, events = env
    held = _claim(env, "alpha-001-ci", "outcome-alpha-001", "holder-1")
    first = _run(["alpha-001-ci", "--status", "done", "--claim", held["claim_id"]], e)
    assert first.returncode == 0, first.stderr
    second = _run(["alpha-001-ci", "--status", "done", "--claim", held["claim_id"]], e)
    assert second.returncode == 4, (second.returncode, second.stderr)
    completed = [ev for ev in _events(events) if ev["event_type"] == "work_item_completed"]
    assert len(completed) == 1


def test_a_completion_with_no_token_while_a_claim_is_live_exits_4(env):
    e, events = env
    _claim(env, "alpha-001-ci", "outcome-alpha-001", "holder-1")
    r = _run(["alpha-001-ci", "--status", "done"], e)
    assert r.returncode == 4, (r.returncode, r.stderr)
    assert [ev for ev in _events(events) if ev["event_type"] == "work_item_completed"] == []


def test_the_token_can_come_from_the_environment(env):
    e, events = env
    held = _claim(env, "alpha-001-ci", "outcome-alpha-001", "holder-1")
    e = dict(e)
    e["CABINET_CLAIM_ID"] = held["claim_id"]
    r = subprocess.run(["bash", str(SCRIPT), "alpha-001-ci", "--status", "done"],
                       env=e, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    completed = [ev for ev in _events(events) if ev["event_type"] == "work_item_completed"]
    assert len(completed) == 1


def test_a_wrong_holder_with_a_valid_token_exits_4(env):
    e, events = env
    held = _claim(env, "alpha-001-ci", "outcome-alpha-001", "holder-1")
    e = dict(e)
    e["CABINET_WORKER_ID"] = "somebody-else"
    r = subprocess.run(
        ["bash", str(SCRIPT), "alpha-001-ci", "--status", "done",
         "--claim", held["claim_id"]],
        env=e, capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 4, (r.returncode, r.stderr)
    assert [ev for ev in _events(events) if ev["event_type"] == "work_item_completed"] == []


def test_an_unclaimed_task_still_completes_without_a_token(env):
    """The compatibility path: nothing holds it, so nothing is being fenced."""
    e, events = env
    r = _run(["alpha-001-uat", "--status", "done", "--evidence", "signed off"], e)
    assert r.returncode == 0, r.stderr
    completed = [ev for ev in _events(events) if ev["event_type"] == "work_item_completed"]
    assert len(completed) == 1
    assert completed[0]["payload"]["claim_id"] is None


def test_verified_is_not_fenced_on_the_executors_claim(env):
    """Separation of duties: the verifier holds no claim and must not need one."""
    e, events = env
    _claim(env, "alpha-001-ci", "outcome-alpha-001", "holder-1")
    r = _run(["alpha-001-ci", "--status", "verified", "--actor", "auditor",
              "--evidence", "checked"], e)
    assert r.returncode == 0, r.stderr
    verified = [ev for ev in _events(events) if ev["event_type"] == "work_item_verified"]
    assert len(verified) == 1
    assert verified[0]["actor"] == "auditor"


def test_the_script_pins_its_interpreter():
    """A0.3, for THIS script: no bare `python3` from whatever the PATH offers.

    SCOPE, stated so this cannot be read as covering more than it does. A0.3
    also names two dashboard exec strings (`actions/gaps.ts`,
    `lib/capability-gaps.ts`), which are the GAP unit's files, not this one's —
    widening this sensor to them would make it a red assertion about code no
    commit on this branch may touch. They are an open residual against A0.3 and
    are named as one on the PR; a checked file here is not a claim about them.
    """
    text = SCRIPT.read_text()
    assert 'CABINET_PY="${CABINET_PYTHON:-python3.12}"' in text
    offenders = [
        (number, line)
        for number, line in enumerate(text.splitlines(), 1)
        if "python3" in line
        and "CABINET_PYTHON" not in line
        and not line.lstrip().startswith("#")
    ]
    assert offenders == [], "unpinned python3 in an unlocked script: %r" % offenders
