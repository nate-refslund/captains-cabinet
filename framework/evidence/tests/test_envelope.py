"""Phase-2 safety envelope: per-trial event cap + LOUD purge degradation.

Cap laws pinned here (R-8, provisional constant):
- a mint beyond ``MAX_TRIAL_EVENTS`` refuses with the typed
  ``trial_event_cap`` error BEFORE any byte is produced (no write-ahead
  record, no ledger growth), and the refusal is stable on retry;
- recovery is exempt: an already-signed write-ahead event reconciles
  exactly-once even when the cap has tightened past it, and the resulting
  over-cap trial keeps verifying and reading (v1 compatibility);
- the constant is a code constant with act-class headroom over the heaviest
  observed producer volume (the 15-scenario dogfood journey: 74 events).

Degradation-loudness laws pinned here:
- the ``degraded_evidence`` dict shape is byte-identical to Phase 1 —
  loudness is a separate side effect;
- one content-free marker line per FLIP (never per suppressed event) lands
  in the store-root ``degradations.jsonl`` sidecar; fields are id-validated
  so payload text can never leak into the marker;
- the marker write and the ``on_degrade`` callback are best-effort: a
  broken plane, an unwritable sidecar, or a raising callback never blocks
  the purge; the stderr signal is rate-limited, the marker line is not;
- the sidecar is NOT evidence: ``verify_store`` stays green with it present
  and it never enters a trial directory or the officer projection.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.evidence import EvidenceRecorder
from framework.evidence import lifecycle as lifecycle_mod
from framework.evidence import recorder as recorder_mod
from framework.evidence.lifecycle import DEGRADATION_SIDECAR, ActLifecycle
from framework.evidence.recorder import EvidenceError, TraceContext
from framework.evidence.verifier import verify_store, verify_trial

TRIAL = "evt-envelope-20260717"


def _append(recorder: EvidenceRecorder, trial: str = TRIAL) -> dict:
    return recorder.append(
        recorder.trace(trial, surface="system"),
        phase="system",
        status="started",
        actor={"kind": "system", "id": "envelope-test"},
        component={"name": "envelope-test", "version": "1", "commit": "abc123"},
        detail={"action": "envelope_probe"},
    )


# ---------------------------------------------------------------------------
# Per-trial event cap.
# ---------------------------------------------------------------------------
def test_cap_is_a_provisional_code_constant_with_act_class_headroom():
    cap = recorder_mod.MAX_TRIAL_EVENTS
    assert isinstance(cap, int) and not isinstance(cap, bool)
    # Headroom law: at least 2x the heaviest observed legitimate trial (the
    # full 15-scenario dogfood journey lands 74 events on one trial) and
    # bounded so the O(n^2) per-append verify cost stays inside the envelope.
    assert 2 * 74 <= cap <= 10_000
    # Code-constant law: the envelope is never env-derived and never a
    # control.json dial — no environment read may sit near the constant.
    source = Path(recorder_mod.__file__).read_text(encoding="utf-8")
    declaration = [
        line for line in source.splitlines()
        if line.startswith("MAX_TRIAL_EVENTS")
    ]
    assert declaration == [f"MAX_TRIAL_EVENTS = {cap}"]


def test_append_beyond_cap_refuses_typed_and_leaves_zero_bytes(
    tmp_path: Path, monkeypatch,
):
    monkeypatch.setattr(recorder_mod, "MAX_TRIAL_EVENTS", 3)
    recorder = EvidenceRecorder(tmp_path)
    for _ in range(3):
        _append(recorder)
    trial_dir = tmp_path / "trials" / TRIAL
    ledger_bytes = (trial_dir / "events.jsonl").read_bytes()
    for _ in range(2):  # the refusal is stable on retry
        with pytest.raises(EvidenceError) as caught:
            _append(recorder)
        assert caught.value.code == "trial_event_cap"
    # Zero bytes: no write-ahead record, no ledger growth, store still green.
    assert not (trial_dir / "pending.json").exists()
    assert (trial_dir / "events.jsonl").read_bytes() == ledger_bytes
    result = verify_trial(tmp_path, TRIAL)
    assert result["ok"] is True and result["event_count"] == 3
    assert verify_store(tmp_path)["ok"] is True
    assert len(recorder.read_events(TRIAL)) == 3


def test_recovery_reconciles_a_signed_pending_event_past_a_tightened_cap(
    tmp_path: Path, monkeypatch,
):
    """Exactly-once beats the envelope: signed write-ahead events always land.

    A crash leaves a signed ``pending.json``; if the cap later tightens past
    that sequence, reconciliation must still finish (determinism law) while
    NEW mints refuse — and the over-cap trial keeps verifying and reading
    (legacy compatibility).
    """
    recorder = EvidenceRecorder(tmp_path)
    _append(recorder)
    original_anchor = recorder._anchor
    monkeypatch.setattr(
        recorder, "_anchor",
        lambda event: (_ for _ in ()).throw(OSError("simulated power loss")),
    )
    with pytest.raises(OSError):
        _append(recorder)
    monkeypatch.setattr(recorder, "_anchor", original_anchor)
    trial_dir = tmp_path / "trials" / TRIAL
    assert (trial_dir / "pending.json").exists()

    monkeypatch.setattr(recorder_mod, "MAX_TRIAL_EVENTS", 1)
    with pytest.raises(EvidenceError) as caught:
        _append(recorder)  # reconciles seq 2 first, then refuses the mint
    assert caught.value.code == "trial_event_cap"
    assert not (trial_dir / "pending.json").exists()
    result = verify_trial(tmp_path, TRIAL)
    assert result["ok"] is True and result["event_count"] == 2
    events = recorder.read_events(TRIAL)  # over-cap trial still reads
    assert [event["sequence"] for event in events] == [1, 2]


# ---------------------------------------------------------------------------
# LOUD purge degradation.
# ---------------------------------------------------------------------------
class _ProducerError(RuntimeError):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


class _FakeRecorder:
    """Scripted stand-in exposing exactly the surface the helper touches."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.fail_codes: list[str] = []
        self.recover_error: EvidenceError | None = None

    def trace(self, trial_id, *, surface, trace_id=None, action_id=None,
              correlation_id=None):
        return TraceContext(
            trial_id=trial_id,
            trace_id=trace_id or "trace-minted",
            action_id=action_id or "action-minted",
            correlation_id=correlation_id or "corr-minted",
            surface=surface,
            started_monotonic_ns=0,
        )

    def recover_interrupted(self, trial_id):
        if self.recover_error is not None:
            raise self.recover_error
        return []

    def append(self, context, *, phase, status, actor, component,
               detail=None, links=None, duration_ms=None):
        if self.fail_codes:
            raise EvidenceError(self.fail_codes.pop(0), "injected failure")
        return {"trial_id": context.trial_id, "phase": phase, "status": status}


def _lifecycle(recorder, *, on_degrade=None):
    return ActLifecycle(
        recorder,
        trial_id="trial-1",
        surface="test",
        actor_policy=lambda phase: {"kind": "system", "id": "test-core"},
        component={"name": "test-core", "version": "1"},
        producer_error=_ProducerError,
        unavailable_error=lambda: _ProducerError("evidence_unavailable"),
        integrity_error=lambda: _ProducerError("evidence_integrity"),
        remint=lambda purged: "trial-2",
        producer_purged_code="producer_purged",
        degrade_on_failure=True,
        on_degrade=on_degrade,
    )


@pytest.fixture(autouse=True)
def _fresh_signal_window(monkeypatch):
    """Reset the per-process stderr rate limiter around every test."""
    monkeypatch.setattr(lifecycle_mod, "_last_degradation_signal_monotonic", None)


def _marker_lines(root: Path) -> list[dict]:
    path = root / DEGRADATION_SIDECAR
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_degradation_flip_writes_one_marker_and_keeps_the_pinned_shape(tmp_path):
    recorder = _FakeRecorder(tmp_path)
    recorder.fail_codes = ["io_error", "must_never_be_consumed"]
    recording = _lifecycle(recorder)
    recording.begin()
    recording.intent({"action": "purge"})
    # The producer-visible shape is byte-identical to Phase 1.
    assert recording.degraded_evidence == {
        "error_code": "io_error", "phase": "intent",
    }
    lines = _marker_lines(tmp_path)
    assert len(lines) == 1
    record = lines[0]
    assert record["schema"] == "cabinet.evidence-degradation/v1"
    assert record["trial_id"] == "trial-1"
    assert record["component"] == "test-core"
    assert record["phase"] == "intent"
    assert record["error_code"] == "io_error"
    assert record["ts"]
    assert set(record) == {
        "schema", "ts", "trial_id", "component", "phase", "error_code",
    }
    # Marker at the FLIP only: suppressed follow-up events add no lines.
    recording.proposed({"action": "purge"})
    assert len(_marker_lines(tmp_path)) == 1
    assert recorder.fail_codes == ["must_never_be_consumed"]


def test_recover_interrupted_flip_also_writes_the_marker(tmp_path):
    (tmp_path / "trials" / "trial-1").mkdir(parents=True)
    recorder = _FakeRecorder(tmp_path)
    recorder.recover_error = EvidenceError("ledger_integrity", "broken")
    recording = _lifecycle(recorder)
    recording.recover_interrupted()
    assert recording.degraded_evidence == {
        "error_code": "ledger_integrity", "phase": "recover_interrupted",
    }
    lines = _marker_lines(tmp_path)
    assert len(lines) == 1
    assert lines[0]["phase"] == "recover_interrupted"
    assert lines[0]["error_code"] == "ledger_integrity"


def test_marker_write_failure_never_blocks_the_degrade(tmp_path):
    # Missing parent directory: the sidecar append fails with ENOENT — the
    # flip must still complete silently (a broken plane never blocks purge).
    recorder = _FakeRecorder(tmp_path / "absent" / "store")
    recorder.fail_codes = ["io_error"]
    recording = _lifecycle(recorder)
    recording.begin()
    recording.intent({"action": "purge"})
    assert recording.degraded_evidence == {
        "error_code": "io_error", "phase": "intent",
    }
    assert not (tmp_path / "absent").exists()


def test_stderr_signal_is_rate_limited_but_every_flip_writes_a_marker(
    tmp_path, capsys,
):
    recorder = _FakeRecorder(tmp_path)
    for _ in range(2):
        recorder.fail_codes = ["io_error"]
        recording = _lifecycle(recorder)
        recording.begin()
        recording.intent({"action": "purge"})
    assert len(_marker_lines(tmp_path)) == 2
    err = capsys.readouterr().err
    assert err.count("evidence-lifecycle: WARN") == 1
    assert "degradations.jsonl" in err


def test_on_degrade_callback_is_best_effort(tmp_path):
    seen: list[dict] = []
    recorder = _FakeRecorder(tmp_path)
    recorder.fail_codes = ["io_error"]
    recording = _lifecycle(recorder, on_degrade=seen.append)
    recording.begin()
    recording.intent({"action": "purge"})
    assert len(seen) == 1
    assert seen[0]["error_code"] == "io_error" and seen[0]["phase"] == "intent"

    def explode(record):
        raise RuntimeError("loudness must never block the purge")

    recorder2 = _FakeRecorder(tmp_path / "second")
    (tmp_path / "second").mkdir()
    recorder2.fail_codes = ["io_error"]
    recording2 = _lifecycle(recorder2, on_degrade=explode)
    recording2.begin()
    recording2.intent({"action": "purge"})  # must not raise
    assert recording2.degraded_evidence == {
        "error_code": "io_error", "phase": "intent",
    }


def test_marker_fields_are_id_validated_and_content_free(tmp_path):
    recorder = _FakeRecorder(tmp_path)
    hostile = "two words sk-" + "Ab1" * 12
    record = lifecycle_mod._note_degradation(
        recorder,
        trial_id=hostile,        # not an id: must not be transcribed
        component_name=None,     # unknown
        phase="intent",
        error_code=None,         # unknown (a cause chain without a code)
    )
    assert record["trial_id"] == "invalid"
    assert record["component"] == "unknown"
    assert record["error_code"] == "unknown"
    raw = (tmp_path / DEGRADATION_SIDECAR).read_text(encoding="utf-8")
    assert hostile not in raw and "sk-" not in raw


def test_sidecar_is_not_evidence_and_the_store_stays_green(tmp_path):
    recorder = EvidenceRecorder(tmp_path)
    _append(recorder)
    lifecycle_mod._note_degradation(
        recorder,
        trial_id=TRIAL,
        component_name="envelope-test",
        phase="receipt",
        error_code="ledger_integrity",
    )
    assert (tmp_path / DEGRADATION_SIDECAR).is_file()
    # Unsigned sidecar at the store root: tolerated by store verification,
    # never inside a trial directory, and appends keep working.
    assert verify_store(tmp_path)["ok"] is True
    assert not (tmp_path / "trials" / TRIAL / DEGRADATION_SIDECAR).exists()
    _append(recorder)
    assert verify_trial(tmp_path, TRIAL)["ok"] is True
