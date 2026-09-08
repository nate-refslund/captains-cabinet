"""Sensors for the claim primitive (framework/missions/claims.py).

Every arm here fails against pre-change bytes for a stated reason, and the
concurrency arms use real processes rather than threads: the property under
test is a cross-PROCESS lock, and a thread test would pass on a GIL that the
production shape does not have.

The subprocess arms export CABINET_EVENT_LOG_DIR explicitly. The repo-root
conftest exports it for the pytest process, but a child that inherits nothing
would resolve its own private ledger and every claimer would win.
"""

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

_ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.events.emitter import emit, replay  # noqa: E402
from framework.missions import claims  # noqa: E402


@pytest.fixture(autouse=True)
def ledger(tmp_path, monkeypatch):
    """A fresh ledger per test, and a holder identity that does not vary."""
    log_dir = tmp_path / "events"
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(log_dir))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CABINET_CLAIM_LEASE_SECONDS", raising=False)
    monkeypatch.delenv(claims.WORKER_ID_ENV, raising=False)
    return log_dir


def _started_events():
    return [
        event
        for event in replay(event_types=["work_item_started"])
        if (event.get("payload") or {}).get("claim_id")
    ]


# ---------------------------------------------------------------------------
# Exactly one winner
# ---------------------------------------------------------------------------


CONCURRENT_CLAIMER = textwrap.dedent(
    """
    import json, os, sys, time
    sys.path.insert(0, sys.argv[1])
    from framework.missions import claims

    barrier_dir = sys.argv[2]
    holder = sys.argv[3]
    # A start barrier: every child parks until the go file appears, so they all
    # reach the lock inside the same millisecond window. Without it the first
    # child would finish before the last had imported and the race the sensor
    # exists to provoke would never happen.
    go = os.path.join(barrier_dir, "go")
    open(os.path.join(barrier_dir, "ready-" + holder), "w").close()
    deadline = time.time() + 120
    while not os.path.exists(go) and time.time() < deadline:
        time.sleep(0.002)
    held = claims.claim("outcome-c-task-000", "outcome-c", holder)
    print(json.dumps({"holder": holder, "won": held is not None}))
    """
).strip()


def _run_concurrent_claimers(tmp_path, ledger, count):
    barrier = tmp_path / "barrier"
    barrier.mkdir()
    script = tmp_path / "claimer.py"
    script.write_text(CONCURRENT_CLAIMER)
    env = dict(os.environ)
    env["CABINET_EVENT_LOG_DIR"] = str(ledger)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTEST_CURRENT_TEST", None)

    procs = []
    for index in range(count):
        procs.append(
            subprocess.Popen(
                [sys.executable, str(script), _ROOT, str(barrier), "holder-%d" % index],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
        )
    # Wait for every child to be parked on the barrier before releasing it.
    deadline = time.time() + 120
    while len(list(barrier.glob("ready-*"))) < count and time.time() < deadline:
        time.sleep(0.01)
    assert len(list(barrier.glob("ready-*"))) == count, "claimers never parked"
    (barrier / "go").write_text("go")

    results = []
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err.decode("utf-8", "replace")
        results.append(json.loads(out.decode("utf-8").strip()))
    return results


def test_eight_concurrent_claimers_one_wins(tmp_path, ledger):
    """8 processes race for one task: one Claim, one started event.

    RED before: `framework.missions.claims` does not exist, and the pull path
    it replaces (session_bridge.get_next_task) hands the same node to every
    caller with no lock at all.
    """
    results = _run_concurrent_claimers(tmp_path, ledger, 8)

    winners = [row for row in results if row["won"]]
    assert len(winners) == 1, results
    assert len(_started_events()) == 1


def test_zero_claimers_is_the_degenerate_end(ledger):
    """Nothing claimed: no live claims, no events, no crash."""
    assert claims.live_claims() == {}
    assert claims.live_claim("outcome-c-task-000") is None
    assert claims.latest_claim_id("outcome-c-task-000") is None
    assert list(ledger.glob("events-*.jsonl")) == [] or _started_events() == []


# ---------------------------------------------------------------------------
# The claim itself
# ---------------------------------------------------------------------------


def test_started_payload_carries_both_ids_and_the_token():
    """The overlay keys on task_id + outcome_id; the fence keys on claim_id.

    RED before: the only producer of work_item_started
    (cabinet/scripts/hooks/on-subagent-start.sh) sends `task_ref`, so the
    overlay at compiler.py has never applied a started event at all.
    """
    held = claims.claim("outcome-a-task-000", "outcome-a", "holder-1")
    assert held is not None

    events = _started_events()
    assert len(events) == 1
    payload = events[0]["payload"]
    assert payload["task_id"] == "outcome-a-task-000"
    assert payload["outcome_id"] == "outcome-a"
    assert payload["claim_id"] == held["claim_id"]
    assert payload["holder"] == "holder-1"
    assert payload["lease_s"] == claims.DEFAULT_LEASE_SECONDS
    assert payload["expires_at"] > payload["started_at"]


def test_second_holder_gets_none_while_the_claim_is_live():
    claims.claim("outcome-a-task-000", "outcome-a", "holder-1")
    assert claims.claim("outcome-a-task-000", "outcome-a", "holder-2") is None
    assert len(_started_events()) == 1


def test_same_holder_reclaim_is_idempotent():
    first = claims.claim("outcome-a-task-000", "outcome-a", "holder-1")
    second = claims.claim("outcome-a-task-000", "outcome-a", "holder-1")
    assert second is not None
    assert second["claim_id"] == first["claim_id"]
    assert len(_started_events()) == 1  # no second event


def test_claim_token_is_not_guessable_from_the_task_id():
    """A counter would be forgeable by anything that can count."""
    held = claims.claim("outcome-a-task-000", "outcome-a", "holder-1")
    token = held["claim_id"]
    assert "outcome-a-task-000" not in token
    assert token not in {"1", "#1", "outcome-a-task-000#1"}
    assert len(token) >= 32


# ---------------------------------------------------------------------------
# The lease
# ---------------------------------------------------------------------------


def test_expired_lease_is_claimable_by_a_second_holder():
    past = claims.utcnow() - timedelta(seconds=3600)
    first = claims.claim("outcome-a-task-000", "outcome-a", "holder-1", now=past)
    assert first is not None
    assert claims.live_claim("outcome-a-task-000") is None

    second = claims.claim("outcome-a-task-000", "outcome-a", "holder-2")
    assert second is not None
    assert second["claim_id"] != first["claim_id"]

    released = replay(event_types=["work_item_claim_released"])
    assert len(released) == 1
    assert released[0]["payload"]["reason"] == "expired"
    assert released[0]["payload"]["holder"] == "holder-1"


def test_lease_bounds_are_clamped(monkeypatch):
    assert claims.resolve_lease(1) == claims.MIN_LEASE_SECONDS
    assert claims.resolve_lease(10 ** 9) == claims.MAX_LEASE_SECONDS
    monkeypatch.setenv(claims.LEASE_ENV, "1200")
    assert claims.resolve_lease() == 1200
    monkeypatch.setenv(claims.LEASE_ENV, "not-a-number")
    assert claims.resolve_lease() == claims.DEFAULT_LEASE_SECONDS


def test_default_lease_outlives_three_wake_ticks():
    """A 300 s tick with a 900 s lease must not lose the task between ticks."""
    assert claims.DEFAULT_LEASE_SECONDS >= 3 * 300


def test_renew_extends_the_expiry_for_the_holder_only():
    held = claims.claim("outcome-a-task-000", "outcome-a", "holder-1")
    assert claims.renew(held["claim_id"], "holder-2") is None

    renewed = claims.renew(held["claim_id"], "holder-1")
    assert renewed is not None
    assert renewed["expires_at"] > held["expires_at"]
    assert renewed["renewals"] == 1
    assert claims.live_claim("outcome-a-task-000")["expires_at"] == renewed["expires_at"]


def test_renew_refuses_an_expired_claim():
    """The lease IS the liveness signal — a dead holder cannot revive it."""
    past = claims.utcnow() - timedelta(seconds=3600)
    held = claims.claim("outcome-a-task-000", "outcome-a", "holder-1", now=past)
    assert claims.renew(held["claim_id"], "holder-1") is None


def test_release_hands_the_task_back_early():
    held = claims.claim("outcome-a-task-000", "outcome-a", "holder-1")
    assert claims.release(held["claim_id"], "holder-2", "released") is False
    assert claims.release(held["claim_id"], "holder-1", "released") is True
    assert claims.live_claim("outcome-a-task-000") is None
    # and it is claimable again
    assert claims.claim("outcome-a-task-000", "outcome-a", "holder-2") is not None


def test_release_refuses_an_unknown_reason():
    held = claims.claim("outcome-a-task-000", "outcome-a", "holder-1")
    with pytest.raises(ValueError):
        claims.release(held["claim_id"], "holder-1", "because")


# ---------------------------------------------------------------------------
# The fence
# ---------------------------------------------------------------------------


def test_completion_with_the_live_token_is_accepted():
    held = claims.claim("outcome-a-task-000", "outcome-a", "holder-1")
    event = claims.complete(
        "outcome-a-task-000", "outcome-a", "holder-1",
        claim_id=held["claim_id"], status="done", evidence_text="did it",
    )
    assert event["event_type"] == "work_item_completed"
    assert event["payload"]["claim_id"] == held["claim_id"]
    assert event["payload"]["holder"] == "holder-1"


def test_stale_token_is_refused_even_after_the_claim_expired():
    """A2.4: the fence compares against the LATEST token, not against liveness."""
    past = claims.utcnow() - timedelta(seconds=3600)
    stale = claims.claim("outcome-a-task-000", "outcome-a", "holder-1", now=past)
    claims.claim("outcome-a-task-000", "outcome-a", "holder-2")  # takes over

    before = len(replay(event_types=["work_item_completed"]))
    with pytest.raises(claims.ClaimRefused) as refused:
        claims.complete(
            "outcome-a-task-000", "outcome-a", "holder-1",
            claim_id=stale["claim_id"], status="done",
        )
    assert refused.value.code == "stale_claim"
    assert len(replay(event_types=["work_item_completed"])) == before


def test_a_token_for_a_task_that_was_never_claimed_is_stale():
    with pytest.raises(claims.ClaimRefused) as refused:
        claims.complete(
            "outcome-a-task-000", "outcome-a", "holder-1",
            claim_id="00000000-0000-4000-8000-000000000000", status="done",
        )
    assert refused.value.code == "stale_claim"


def test_wrong_holder_with_a_valid_token_is_refused():
    held = claims.claim("outcome-a-task-000", "outcome-a", "holder-1")
    with pytest.raises(claims.ClaimRefused) as refused:
        claims.complete(
            "outcome-a-task-000", "outcome-a", "holder-2",
            claim_id=held["claim_id"], status="done",
        )
    assert refused.value.code == "not_holder"


def test_completion_without_a_token_while_a_claim_is_live_is_refused():
    claims.claim("outcome-a-task-000", "outcome-a", "holder-1")
    with pytest.raises(claims.ClaimRefused) as refused:
        claims.complete("outcome-a-task-000", "outcome-a", "holder-2", status="done")
    assert refused.value.code == "no_token"


def test_completion_without_a_token_and_without_a_claim_is_the_compat_path():
    event = claims.complete("legacy-task", "outcome-legacy", "holder-1", status="done")
    assert event["event_type"] == "work_item_completed"
    assert event["payload"]["claim_id"] is None


def test_second_completion_is_refused_as_already_terminal():
    held = claims.claim("outcome-a-task-000", "outcome-a", "holder-1")
    claims.complete(
        "outcome-a-task-000", "outcome-a", "holder-1",
        claim_id=held["claim_id"], status="done",
    )
    with pytest.raises(claims.ClaimRefused) as refused:
        claims.complete(
            "outcome-a-task-000", "outcome-a", "holder-1",
            claim_id=held["claim_id"], status="done",
        )
    assert refused.value.code == "already_terminal"
    assert len(replay(event_types=["work_item_completed"])) == 1


def test_a_completed_task_is_not_claimable():
    held = claims.claim("outcome-a-task-000", "outcome-a", "holder-1")
    claims.complete(
        "outcome-a-task-000", "outcome-a", "holder-1",
        claim_id=held["claim_id"], status="done",
    )
    assert claims.claim("outcome-a-task-000", "outcome-a", "holder-2") is None


# ---------------------------------------------------------------------------
# The legacy started shape
# ---------------------------------------------------------------------------


def test_a_started_event_without_a_token_is_invisible_to_the_claim_plane():
    """The locked subagent hook emits exactly this shape and must not fence."""
    emit("work_item_started", actor="worker", payload={"task_id": "legacy-task",
                                                       "task_ref": "legacy-task"})
    assert claims.live_claim("legacy-task") is None
    assert claims.latest_claim_id("legacy-task") is None
    event = claims.complete("legacy-task", "outcome-legacy", "holder-1", status="done")
    assert event["payload"]["claim_id"] is None


# ---------------------------------------------------------------------------
# Holder derivation
# ---------------------------------------------------------------------------


def test_explicit_worker_id_wins(monkeypatch):
    monkeypatch.setenv(claims.WORKER_ID_ENV, "role@session:abc")
    assert claims.derive_holder("role") == "role@session:abc"


def test_derived_holder_names_the_session_process(monkeypatch):
    monkeypatch.delenv(claims.WORKER_ID_ENV, raising=False)
    holder = claims.derive_holder("role")
    assert holder.startswith("role@session:") or holder == "role"


def test_holder_weakening_is_written_down(monkeypatch, ledger):
    """A holder that two sessions would share is a fact, not a silent default."""
    monkeypatch.delenv(claims.WORKER_ID_ENV, raising=False)
    monkeypatch.setattr(claims, "session_pid", lambda: None)
    assert claims.derive_holder("role") == "role"
    assert "weakened" in (ledger / claims.ERROR_FILENAME).read_text()


# ---------------------------------------------------------------------------
# Failures never raise into the pull path
# ---------------------------------------------------------------------------


def test_unwritable_lock_records_and_does_not_raise_out_of_the_pull(ledger):
    """A2.5: the lock is unusable ⇒ one line in claims.err, no exception upward.

    The lock FILE is made unopenable while its directory stays writable, which
    is what the hook actually meets: the ledger dir is created by the emitter
    and the lock is the one file a stale root-owned run can leave behind.
    """
    if os.geteuid() == 0:
        pytest.fail(
            "this sensor is meaningless as root: mode 000 does not stop uid 0, "
            "so a pass here would prove nothing"
        )
    ledger.mkdir(parents=True, exist_ok=True)
    lock = ledger / claims.LOCK_FILENAME
    lock.write_text("")
    os.chmod(str(lock), 0o000)
    try:
        with pytest.raises(PermissionError):
            claims.claim("outcome-a-task-000", "outcome-a", "holder-1")
        assert claims.record_error("lock unusable") is True
        assert "lock unusable" in (ledger / claims.ERROR_FILENAME).read_text()
    finally:
        os.chmod(str(lock), 0o600)


def test_record_error_never_raises_when_the_ledger_dir_is_unwritable(tmp_path, monkeypatch):
    missing = tmp_path / "no" / "such" / "place"
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(missing))
    monkeypatch.setattr(Path, "mkdir", _raise_permission)
    assert claims.record_error("cannot land") is False


def _raise_permission(*args, **kwargs):
    raise PermissionError("read-only")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_claim_then_complete(ledger, capsys):
    rc = claims.main([
        "claim", "--json", "--task-id", "t1", "--outcome-id", "o1",
        "--holder", "holder-1",
    ])
    assert rc == 0
    held = json.loads(capsys.readouterr().out.strip())

    rc = claims.main([
        "claim", "--json", "--task-id", "t1", "--outcome-id", "o1",
        "--holder", "holder-2",
    ])
    assert rc == 3  # someone else holds it
    capsys.readouterr()

    rc = claims.main([
        "complete", "--json", "--task-id", "t1", "--outcome-id", "o1",
        "--holder", "holder-1", "--claim", held["claim_id"], "--status", "done",
    ])
    assert rc == 0


def test_cli_complete_with_a_stale_token_exits_4(ledger, capsys):
    claims.main(["claim", "--json", "--task-id", "t1", "--outcome-id", "o1",
                 "--holder", "holder-1"])
    capsys.readouterr()
    rc = claims.main([
        "complete", "--json", "--task-id", "t1", "--outcome-id", "o1",
        "--holder", "holder-1", "--claim", "not-the-token", "--status", "done",
    ])
    assert rc == 4
    assert replay(event_types=["work_item_completed"]) == []


def test_cli_has_no_release_verb(capsys):
    """A2.8: release() stays internal — no consumer, so no surface."""
    with pytest.raises(SystemExit):
        claims.main(["release", "--claim", "x", "--holder", "y", "--reason", "z"])


def test_cli_live_lists_live_claims(ledger, capsys):
    claims.claim("t1", "o1", "holder-1")
    assert claims.main(["live", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out.strip())
    assert "t1" in listed
