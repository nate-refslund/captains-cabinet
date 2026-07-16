"""Contracts for the shared act-class recording lifecycle (Phase 1 helper).

The byte-identical migration gate lives beside the producer
(``framework/onboarding/tests/test_act_bytestream.py``); these tests pin the
helper's own laws with a scripted fake recorder so every policy branch is
covered without a producer: fail-closed evidence-before-action, the
re-mint-once retry, purge degradation, purge finality, id unification, the
one-duration-per-branch rule, lifecycle ordering, re-mint lineage (genesis
under the producer lock, adopt-never-fork), and the no-generic-emit posture.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from framework.evidence import ActLifecycle, remint_trial, valid_id_or_none
from framework.evidence.lifecycle import append_event
from framework.evidence.recorder import EvidenceError, TraceContext


class ProducerError(RuntimeError):
    """A minimal producer refusal type carrying the required ``code``."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _unavailable() -> ProducerError:
    return ProducerError("evidence_unavailable")


def _integrity() -> ProducerError:
    return ProducerError("evidence_integrity")


def _actor(phase: str) -> dict[str, str]:
    captain = phase in {"intent", "feedback"}
    return {
        "kind": "captain" if captain else "system",
        "id": "captain" if captain else "test-core",
    }


COMPONENT = {"name": "test-core", "version": "1"}


class FakeRecorder:
    """Scripted stand-in exposing exactly the surface the helper touches."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.appends: list[dict] = []
        self.fail_codes: list[str] = []
        self.recover_calls: list[str] = []
        self.recover_error: EvidenceError | None = None

    def trace(self, trial_id, *, surface, trace_id=None, action_id=None, correlation_id=None):
        return TraceContext(
            trial_id=trial_id,
            trace_id=trace_id or "trace-minted",
            action_id=action_id or "action-minted",
            correlation_id=correlation_id or "corr-minted",
            surface=surface,
            started_monotonic_ns=0,
        )

    def recover_interrupted(self, trial_id):
        self.recover_calls.append(trial_id)
        if self.recover_error is not None:
            raise self.recover_error
        return []

    def append(self, context, *, phase, status, actor, component, detail=None, links=None, duration_ms=None):
        if self.fail_codes:
            raise EvidenceError(self.fail_codes.pop(0), "injected failure")
        row = {
            "trial_id": context.trial_id,
            "phase": phase,
            "status": status,
            "actor": actor,
            "component": component,
            "detail": detail,
            "links": links,
            "duration_ms": duration_ms,
        }
        self.appends.append(row)
        return row


def _lifecycle(recorder, *, remint=None, degrade=False, purged_code="producer_purged"):
    return ActLifecycle(
        recorder,
        trial_id="trial-1",
        surface="test",
        actor_policy=_actor,
        component=dict(COMPONENT),
        producer_error=ProducerError,
        unavailable_error=_unavailable,
        integrity_error=_integrity,
        remint=remint or (lambda purged: pytest.fail("remint must not run")),
        producer_purged_code=purged_code,
        degrade_on_failure=degrade,
    )


def test_append_event_translates_evidence_errors_and_keeps_the_cause():
    recorder = FakeRecorder(Path("/nonexistent"))
    recorder.fail_codes = ["io_error"]
    context = recorder.trace("trial-1", surface="test")
    with pytest.raises(ProducerError) as caught:
        append_event(
            recorder, context, phase="intent", status="started",
            actor=_actor("intent"), component=dict(COMPONENT),
            unavailable_error=_unavailable, detail={"action": "x"},
        )
    assert caught.value.code == "evidence_unavailable"
    assert caught.value.__cause__.code == "io_error"


def test_intent_failure_is_fail_closed_before_any_core_runs(tmp_path):
    recorder = FakeRecorder(tmp_path)
    recorder.fail_codes = ["io_error"]
    recording = _lifecycle(recorder)
    recording.begin()
    core_ran = []
    with pytest.raises(ProducerError) as caught:
        recording.intent({"action": "demo"})
        core_ran.append(True)  # pragma: no cover - must be unreachable
    assert caught.value.code == "evidence_unavailable"
    assert not core_ran and recorder.appends == []


def test_purge_degradation_goes_silent_and_never_appends_again(tmp_path):
    recorder = FakeRecorder(tmp_path)
    recorder.fail_codes = ["io_error", "must_never_be_consumed"]
    recording = _lifecycle(recorder, degrade=True)
    recording.begin()
    recording.intent({"action": "purge"})
    assert recording.degraded_evidence == {"error_code": "io_error", "phase": "intent"}
    recording.proposed({"action": "purge"})
    # Degraded recording is silent: no append attempt, injected queue intact.
    assert recorder.appends == []
    assert recorder.fail_codes == ["must_never_be_consumed"]


def test_preflight_remints_on_trial_purged_and_degrades_or_raises_otherwise(tmp_path):
    (tmp_path / "trials" / "trial-1").mkdir(parents=True)
    recorder = FakeRecorder(tmp_path)
    recorder.recover_error = EvidenceError("trial_purged", "tombstoned")
    minted = []

    def remint(purged):
        minted.append(purged)
        return "trial-2"

    recording = _lifecycle(recorder, remint=remint)
    recording.recover_interrupted()
    assert minted == ["trial-1"]
    assert recording.trial_id == "trial-2" and recording.reminted is True

    recorder.recover_error = EvidenceError("ledger_integrity", "broken")
    (tmp_path / "trials" / "trial-2").mkdir()
    strict = _lifecycle(recorder, remint=remint)
    strict.trial_id = "trial-2"
    with pytest.raises(ProducerError) as caught:
        strict.recover_interrupted()
    assert caught.value.code == "evidence_integrity"
    assert caught.value.__cause__.code == "ledger_integrity"

    degraded = _lifecycle(recorder, remint=remint, degrade=True)
    degraded.trial_id = "trial-2"
    degraded.recover_interrupted()
    assert degraded.degraded_evidence == {
        "error_code": "ledger_integrity",
        "phase": "recover_interrupted",
    }


def test_record_remints_once_retries_with_same_ids_and_never_twice(tmp_path):
    recorder = FakeRecorder(tmp_path)
    minted = []

    def remint(purged):
        minted.append(purged)
        return f"trial-{len(minted) + 1}"

    recording = _lifecycle(recorder, remint=remint)
    recording.begin(trace_id="trace-a", action_id="action-a", correlation_id="corr-a")

    recorder.fail_codes = ["trial_purged"]
    recording.intent({"action": "demo"})
    assert minted == ["trial-1"]
    assert recording.trial_id == "trial-2"
    # The retry landed on the fresh trial with the SAME ids.
    assert recorder.appends[-1]["trial_id"] == "trial-2"
    assert recording.context.trace_id == "trace-a"
    assert recording.context.action_id == "action-a"
    assert recording.context.correlation_id == "corr-a"

    # A second tombstone in the same action never re-mints again.
    recorder.fail_codes = ["trial_purged"]
    with pytest.raises(ProducerError) as caught:
        recording.proposed({"action": "demo"})
    assert caught.value.code == "evidence_unavailable"
    assert minted == ["trial-1"]


def test_remint_retry_honors_purge_finality_with_a_silent_return(tmp_path):
    recorder = FakeRecorder(tmp_path)

    def remint(purged):
        raise ProducerError("producer_purged")

    recording = _lifecycle(recorder, remint=remint)
    recording.begin()
    recorder.fail_codes = ["trial_purged"]
    assert recording.record(phase="intent", status="started", detail={}) is None
    assert recording.degraded_evidence is None


def test_unify_ids_overwrites_trace_and_correlation_but_keeps_action_id(tmp_path):
    recorder = FakeRecorder(tmp_path)
    recording = _lifecycle(recorder)
    recording.begin(trace_id="trace-a", action_id="action-a", correlation_id="corr-a")
    request = {"trace_id": "***forged***", "correlation_id": "x y z", "action_id": "!!!bad!!!"}
    recording.unify_ids(request)
    assert request["trace_id"] == "trace-a"
    assert request["correlation_id"] == "corr-a"
    # Malformed caller action ids are KEPT for the core's deterministic refusal.
    assert request["action_id"] == "!!!bad!!!"
    absent = {}
    recording.unify_ids(absent)
    assert absent["action_id"] == "action-a"


def test_valid_id_or_none_enforces_the_recorder_alphabet():
    assert valid_id_or_none("trace-Abc.1:2_ok") == "trace-Abc.1:2_ok"
    assert valid_id_or_none("-leading-dash") is None
    assert valid_id_or_none("has space") is None
    assert valid_id_or_none("x" * 129) is None
    assert valid_id_or_none(123) is None
    assert valid_id_or_none(None) is None


def test_lifecycle_orders_and_one_duration_per_branch(tmp_path, monkeypatch):
    ticks = iter(range(1, 100))
    monkeypatch.setattr(time, "monotonic_ns", lambda: next(ticks) * 1_000_000)
    recorder = FakeRecorder(tmp_path)
    recording = _lifecycle(recorder)
    recording.begin()
    recording.intent({"action": "demo"})
    recording.proposed({"action": "demo"})
    recording.completed(
        result_status="succeeded",
        allowed_detail={"action": "demo"},
        execution_detail={"action": "demo"},
        verification_detail={"action": "demo"},
        receipt_detail={"action": "demo"},
        receipt_links=["onboarding-event:evt-1"],
        outcome_detail={"action": "demo"},
    )
    assert [(row["phase"], row["status"]) for row in recorder.appends] == [
        ("intent", "started"),
        ("policy", "proposed"),
        ("policy", "allowed"),
        ("execution", "succeeded"),
        ("verification", "verified"),
        ("receipt", "succeeded"),
        ("outcome", "succeeded"),
    ]
    # intent/proposed carry no duration; the committed tail shares ONE value.
    assert [row["duration_ms"] for row in recorder.appends[:2]] == [None, None]
    tail = {row["duration_ms"] for row in recorder.appends[2:]}
    assert len(tail) == 1 and tail != {None}
    # Actor policy is applied per phase.
    assert recorder.appends[0]["actor"]["kind"] == "captain"
    assert recorder.appends[1]["actor"]["kind"] == "system"


def test_refused_and_failed_branch_tails(tmp_path):
    recorder = FakeRecorder(tmp_path)
    recording = _lifecycle(recorder)
    recording.begin()
    recording.intent({"action": "demo"})
    recording.refused(
        refusal_detail={"action": "demo", "error_code": "nope"},
        outcome_detail={"action": "demo", "error_code": "nope"},
    )
    assert [(row["phase"], row["status"]) for row in recorder.appends[-2:]] == [
        ("policy", "refused"),
        ("outcome", "refused"),
    ]
    recording2 = _lifecycle(recorder)
    recording2.begin()
    recording2.intent({"action": "demo"})
    recording2.failed(
        error_detail={"action": "demo", "error_code": "unexpected_x"},
        outcome_detail={"action": "demo", "error_code": "unexpected_x"},
    )
    assert [(row["phase"], row["status"]) for row in recorder.appends[-2:]] == [
        ("error", "failed"),
        ("outcome", "failed"),
    ]


def test_remint_trial_appends_genesis_under_the_producer_lock(tmp_path):
    recorder = FakeRecorder(tmp_path)
    lock_state = {"held": False}
    original_append = recorder.append

    def observing_append(context, **kwargs):
        assert lock_state["held"], "genesis must be appended while the producer lock is held"
        return original_append(context, **kwargs)

    recorder.append = observing_append

    @contextmanager
    def state_lock():
        lock_state["held"] = True
        try:
            yield
        finally:
            lock_state["held"] = False

    def swap_live_trial(purged):
        assert lock_state["held"]
        assert purged == "trial-old"
        return "trial-new", True

    live = remint_trial(
        recorder,
        "trial-old",
        surface="test",
        state_lock=state_lock,
        swap_live_trial=swap_live_trial,
        actor_policy=_actor,
        component=dict(COMPONENT),
        unavailable_error=_unavailable,
    )
    assert live == "trial-new"
    assert lock_state["held"] is False
    genesis = recorder.appends[-1]
    assert genesis["trial_id"] == "trial-new"
    assert genesis["phase"] == "system" and genesis["status"] == "recovered"
    import hashlib

    tombstone = hashlib.sha256(b"trial-old").hexdigest()
    assert genesis["detail"] == {
        "action": "remint_evidence_trial",
        "reason_code": "prior_trial_tombstoned",
        "purged_trial_id_hash": tombstone,
    }
    assert genesis["links"] == [f"evidence-tombstone:{tombstone}"]


def test_remint_trial_adopts_a_concurrent_swap_without_a_second_genesis(tmp_path):
    recorder = FakeRecorder(tmp_path)

    @contextmanager
    def state_lock():
        yield

    live = remint_trial(
        recorder,
        "trial-old",
        surface="test",
        state_lock=state_lock,
        swap_live_trial=lambda purged: ("trial-adopted", False),
        actor_policy=_actor,
        component=dict(COMPONENT),
        unavailable_error=_unavailable,
    )
    assert live == "trial-adopted"
    assert recorder.appends == []


def test_lifecycle_is_an_import_seam_not_a_generic_emit_surface():
    import framework.evidence.lifecycle as lifecycle_module

    source = Path(lifecycle_module.__file__).read_text(encoding="utf-8")
    assert "argparse" not in source and "def main" not in source and "def _cli" not in source
    main_source = (Path(lifecycle_module.__file__).parent / "__main__.py").read_text(encoding="utf-8")
    assert "lifecycle" not in main_source, "the evidence CLI must not expose the producer seam"
    # The helper never reads the store location from the environment.
    assert "os.environ" not in source and "getenv" not in source
