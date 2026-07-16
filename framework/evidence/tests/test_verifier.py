"""Adversarial regression tests for the independent verifier.

Every test builds a REAL store with the recorder, then attacks the files on
disk the way a post-hoc tamperer would — without, or deliberately with, the
store signing key — and asserts the verifier fails closed while clean stores
keep verifying green and legitimate recording keeps landing.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from framework.evidence.recorder import EvidenceRecorder
from framework.evidence.verifier import (
    _digest,
    _event_signature,
    _object_signature,
    verify_store,
    verify_trial,
)

TRIAL = "VERIFIER-TRIAL-001"


def _context(recorder: EvidenceRecorder, trial: str = TRIAL):
    return recorder.trace(
        trial,
        surface="test",
        trace_id="trace-verifier-001",
        action_id="action-verifier-001",
        correlation_id="corr-verifier-001",
    )


def _append(recorder: EvidenceRecorder, trial: str = TRIAL, *, step: str = "step") -> dict:
    return recorder.append(
        _context(recorder, trial),
        phase="execution",
        status="started",
        actor={"kind": "system", "id": "verifier-test"},
        component={"name": "verifier-test", "version": "1"},
        detail={"action": step},
    )


# --- finding #9: anchor checks must fail closed on any non-dict anchor ---

@pytest.mark.parametrize("payload", ["[]", "null", "42", '"anchor"'])
def test_non_dict_anchor_fails_closed_against_key_free_truncation(tmp_path: Path, payload: str):
    """anchor.json that parses as valid JSON but is not an object used to
    silently disable every anchor (anti-truncation) check, so a key-free
    ledger truncation passed verification."""
    recorder = EvidenceRecorder(tmp_path)
    _append(recorder, step="one")
    _append(recorder, step="two")
    trial = tmp_path / "trials" / TRIAL
    ledger = trial / "events.jsonl"
    first_row = ledger.read_bytes().split(b"\n")[0]
    ledger.write_bytes(first_row + b"\n")  # a self-consistent one-row prefix
    (trial / "anchor.json").write_text(payload)  # valid JSON, not a dict
    result = verify_trial(tmp_path, TRIAL)
    assert result["ok"] is False
    assert "anchor_missing_or_unreadable" in result["errors"]
    assert result["checks"]["anchor"] == "fail"


# --- finding #18: negative control pinning the secret-shape scan ---

def test_planted_resigned_secret_still_fails_verification(tmp_path: Path):
    """The planted row is re-signed with the real store key, so the hash
    chain, the signatures, and the anchor all pass — the defense-in-depth
    secret-shape scan must be the ONLY discriminator.  Disabling or
    monkeypatching the scan makes this trial verify, which fails this test.
    """
    recorder = EvidenceRecorder(tmp_path)
    _append(recorder)
    key = (tmp_path / ".signing-key").read_bytes()
    trial = tmp_path / "trials" / TRIAL
    ledger = trial / "events.jsonl"

    row = json.loads(ledger.read_text(encoding="utf-8"))
    row["detail"] = {"action": "step", "token": "sk-" + "a" * 30}
    unsigned = {name: value for name, value in row.items() if name not in {"event_hash", "signature"}}
    row["event_hash"] = _digest(unsigned)
    row["signature"] = _event_signature(key, TRIAL, 1, row["event_hash"])
    ledger.write_text(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    anchor = json.loads((trial / "anchor.json").read_text(encoding="utf-8"))
    payload = {name: value for name, value in anchor.items() if name != "anchor_signature"}
    payload["event_hash"] = row["event_hash"]
    payload["event_signature"] = row["signature"]
    signed = {**payload, "anchor_signature": _object_signature(key, "anchor", payload)}
    (trial / "anchor.json").write_text(
        json.dumps(signed, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )

    result = verify_trial(tmp_path, TRIAL)
    assert result["ok"] is False
    assert "event:1:secret_shape" in result["errors"]
    assert result["checks"]["secret_shapes"] == "fail"
    # The forgery is airtight everywhere else; only the scan catches it.
    assert result["checks"]["hash_chain"] == "pass"
    assert result["checks"]["local_signatures"] == "pass"
    assert result["checks"]["anchor"] == "pass"
    assert result["errors"] == ["event:1:secret_shape"]


# --- finding #24: signed monotonic watermark rejects rollback ---

def test_rollback_to_earlier_signed_state_is_rejected(tmp_path: Path):
    """Restoring a genuine earlier {ledger prefix + its validly-signed
    anchor} must not verify once a later state has been verified."""
    recorder = EvidenceRecorder(tmp_path)
    _append(recorder, step="one")
    assert verify_trial(tmp_path, TRIAL)["ok"] is True  # watermark at sequence 1
    trial = tmp_path / "trials" / TRIAL
    earlier_ledger = (trial / "events.jsonl").read_bytes()
    earlier_anchor = (trial / "anchor.json").read_bytes()
    _append(recorder, step="two")
    assert verify_trial(tmp_path, TRIAL)["ok"] is True  # watermark at sequence 2
    # Restore the genuine earlier prefix WITH its genuinely-signed anchor.
    (trial / "events.jsonl").write_bytes(earlier_ledger)
    (trial / "anchor.json").write_bytes(earlier_anchor)
    result = verify_trial(tmp_path, TRIAL)
    assert result["ok"] is False
    assert "rollback_detected" in result["errors"]
    assert result["event_count"] == 1


def test_wiped_and_regrown_trial_is_rejected_as_divergent(tmp_path: Path):
    recorder = EvidenceRecorder(tmp_path)
    _append(recorder, step="one")
    assert verify_trial(tmp_path, TRIAL)["ok"] is True
    shutil.rmtree(tmp_path / "trials" / TRIAL)  # out-of-band wipe, no purge receipt
    _append(recorder, step="one")  # same length, different history
    result = verify_trial(tmp_path, TRIAL)
    assert result["ok"] is False
    assert "rollback_divergent_history" in result["errors"]


@pytest.mark.parametrize("tamper", ["bad_signature", "garbage", "symlink"])
def test_tampered_watermark_sidecar_fails_closed(tmp_path: Path, tamper: str):
    """A present-but-invalid watermark sidecar is tamper evidence, never a
    silent reset, and the verifier must not self-heal it by rewriting."""
    recorder = EvidenceRecorder(tmp_path)
    _append(recorder)
    assert verify_trial(tmp_path, TRIAL)["ok"] is True
    sidecar = tmp_path / ".verify-watermarks.json"
    assert sidecar.is_file()  # the watermark exists after a clean verification
    original: bytes
    if tamper == "bad_signature":
        value = json.loads(sidecar.read_text(encoding="utf-8"))
        value["watermark_signature"] = "0" * 64
        sidecar.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    elif tamper == "garbage":
        sidecar.write_text("not-json", encoding="utf-8")
    else:
        target = tmp_path / "elsewhere.json"
        target.write_bytes(sidecar.read_bytes())
        sidecar.unlink()
        sidecar.symlink_to(target)
    original = sidecar.read_bytes() if tamper != "symlink" else b""
    result = verify_trial(tmp_path, TRIAL)
    assert result["ok"] is False
    assert "watermark_invalid" in result["errors"]
    if tamper != "symlink":
        assert sidecar.read_bytes() == original  # no self-heal of tamper evidence


def test_trial_removed_without_purge_receipt_fails_the_store(tmp_path: Path):
    recorder = EvidenceRecorder(tmp_path)
    _append(recorder)
    assert verify_store(tmp_path)["ok"] is True  # watermark recorded
    shutil.rmtree(tmp_path / "trials" / TRIAL)  # removal outside the purge path
    result = verify_store(tmp_path)
    assert result["ok"] is False
    assert any(error.startswith("trial_removed_without_receipt:") for error in result["errors"])


# --- finding #25: purged trials must stay purged ---

def test_purged_trial_resurrected_next_to_its_tombstone_fails_the_store(tmp_path: Path):
    store = tmp_path / "store"
    recorder = EvidenceRecorder(store)
    _append(recorder, step="one")
    _append(recorder, step="two")
    trial = store / "trials" / TRIAL
    stash = tmp_path / "stash"
    shutil.copytree(trial, stash)
    recorder.purge_trial(TRIAL, confirmation=f"PURGE {TRIAL}", actor="captain")
    clean = verify_store(store)
    assert clean["ok"] is True and clean["trial_count"] == 0
    shutil.copytree(stash, trial)  # re-plant the purged trial beside its receipt
    result = verify_store(store)
    assert result["ok"] is False
    assert f"purged_trial_resurrected:{TRIAL}" in result["errors"]
    # The planted copy itself verifies; the tombstone cross-check is the
    # only discriminator, so it must carry the failure alone.
    assert all(item["ok"] for item in result["trials"])
    assert "one_or_more_trials_failed" not in result["errors"]


# --- finding #6 (verifier half): ledger rows are framed by b"\n" ONLY ---

def test_carriage_return_is_ledger_content_not_a_row_separator(tmp_path: Path):
    """bytes.splitlines() also splits on \r, so a reframed ledger like
    b'rowA\rrowB\n' — bytes the recorder never wrote — used to parse as two
    clean chained rows and verify.  Rows are framed by b'\n' alone."""
    recorder = EvidenceRecorder(tmp_path)
    _append(recorder, step="one")
    _append(recorder, step="two")
    ledger = tmp_path / "trials" / TRIAL / "events.jsonl"
    raw = ledger.read_bytes()
    assert raw.endswith(b"\n") and raw.count(b"\n") == 2
    ledger.write_bytes(raw.replace(b"\n", b"\r", 1))
    result = verify_trial(tmp_path, TRIAL)
    assert result["ok"] is False
    assert any(error.startswith("invalid_json_line") for error in result["errors"])


# --- positive control: hardening never blocks legitimate recording ---

def test_clean_trials_and_stores_still_verify_green_and_keep_recording(tmp_path: Path):
    recorder = EvidenceRecorder(tmp_path)
    _append(recorder, step="one")
    _append(recorder, step="two")
    first = verify_trial(tmp_path, TRIAL)
    assert first["ok"] is True and first["event_count"] == 2
    # Repeated verification is stable: the watermark advance is monotonic.
    second = verify_trial(tmp_path, TRIAL)
    assert second["ok"] is True
    store = verify_store(tmp_path)
    assert store["ok"] is True and store["trial_count"] == 1
    # Appends keep landing after the watermark exists — verification
    # hardening must never cause a real action to go unrecorded.
    _append(recorder, step="three")
    third = verify_trial(tmp_path, TRIAL)
    assert third["ok"] is True and third["event_count"] == 3
