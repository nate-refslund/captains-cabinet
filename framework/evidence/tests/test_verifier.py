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
    reset_verified_ledger_memo,
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


# --- the verified-prefix memo: it may make verification CHEAPER, never WEAKER

def _warm_memo(root: Path, trial: str = TRIAL) -> dict:
    """Verify once so the clean prefix is memoized, then hand back the verdict."""
    result = verify_trial(root, trial)
    assert result["ok"] is True, result["errors"]
    return result


def test_memoized_prefix_still_catches_mid_ledger_content_tampering(tmp_path: Path):
    """The memo keys on the sha256 of the exact bytes it proved.  Editing a row
    that sits INSIDE the memoized prefix changes those bytes, so the memo
    misses and the full scan runs — the tamper is caught with the same finding
    a cold verifier reports."""
    recorder = EvidenceRecorder(tmp_path)
    for step in ("one", "two", "three"):
        _append(recorder, step=step)
    _warm_memo(tmp_path)
    ledger = tmp_path / "trials" / TRIAL / "events.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    rows[1]["detail"] = {"action": "tampered"}  # hash/signature fields untouched
    ledger.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    result = verify_trial(tmp_path, TRIAL)
    assert result["ok"] is False
    assert "event:2:event_hash" in result["errors"]


def test_memoized_prefix_still_catches_tail_truncation(tmp_path: Path):
    """Dropping rows from the end leaves a byte PREFIX of what was proved —
    the one shape a naive prefix cache would wave through.  A shorter ledger
    can never satisfy the memo (which pins the length it covers), and the
    anchor plus the anti-rollback watermark both fail closed."""
    recorder = EvidenceRecorder(tmp_path)
    for step in ("one", "two", "three"):
        _append(recorder, step=step)
    _warm_memo(tmp_path)
    ledger = tmp_path / "trials" / TRIAL / "events.jsonl"
    lines = ledger.read_text().splitlines(keepends=True)
    ledger.write_text("".join(lines[:2]))
    result = verify_trial(tmp_path, TRIAL)
    assert result["ok"] is False
    assert "anchor_sequence" in result["errors"]
    assert "rollback_detected" in result["errors"]


def test_memoized_prefix_still_catches_a_swapped_signing_key(tmp_path: Path):
    """A prefix proved under one key proves nothing under another, so the memo
    pins the key digest too: rotate the key and every row is re-checked."""
    recorder = EvidenceRecorder(tmp_path)
    _append(recorder, step="one")
    _append(recorder, step="two")
    _warm_memo(tmp_path)
    (tmp_path / ".signing-key").write_bytes(b"z" * 64)
    result = verify_trial(tmp_path, TRIAL)
    assert result["ok"] is False
    assert "event:1:signature" in result["errors"]


def test_memo_hit_and_cold_scan_return_identical_verdicts(tmp_path: Path):
    """The whole claim in one assertion: warm and cold verification of the same
    bytes are the same dict.  Run cold (memo cleared) and warm (memo hit, one
    new row scanned) over a growing ledger and compare every field."""
    recorder = EvidenceRecorder(tmp_path)
    for index in range(6):
        _append(recorder, step=f"step-{index}")
        warm = verify_trial(tmp_path, TRIAL)
        reset_verified_ledger_memo()
        cold = verify_trial(tmp_path, TRIAL)
        assert warm == cold, (index, warm, cold)
        assert warm["ok"] is True and warm["event_count"] == index + 1


def test_a_ledger_lifted_from_another_store_is_rejected_with_a_warm_memo(tmp_path: Path):
    """Same trial id in two stores, each with its own random signing key.  Copy
    one store's ledger over the other's AFTER both have been verified clean:
    the second store's memo describes bytes that no longer exist, so it misses
    and the foreign rows are checked against the local key and refused."""
    first, second = tmp_path / "a", tmp_path / "b"
    for root in (first, second):
        recorder = EvidenceRecorder(root)
        _append(recorder, step="one")
        _append(recorder, step="two")
    assert verify_trial(first, TRIAL)["ok"] is True
    assert verify_trial(second, TRIAL)["ok"] is True
    # The stores really are distinct (independent random signing keys).
    assert (first / ".signing-key").read_bytes() != (second / ".signing-key").read_bytes()
    (second / "trials" / TRIAL / "events.jsonl").write_bytes(
        (first / "trials" / TRIAL / "events.jsonl").read_bytes()
    )
    result = verify_trial(second, TRIAL)
    assert result["ok"] is False
    assert "event:1:signature" in result["errors"]


def test_a_failing_verification_is_not_memoized_as_clean(tmp_path: Path):
    """A ledger that fails must fail EVERY time, not just the first time.

    Only a ZERO-finding scan may seed the memo.  Memoizing a prefix that
    carried findings would let the very next verification skip those rows and
    report the trial clean — a tamper that heals itself by being looked at
    twice.
    """
    recorder = EvidenceRecorder(tmp_path)
    for step in ("one", "two", "three"):
        _append(recorder, step=step)
    _warm_memo(tmp_path)
    ledger = tmp_path / "trials" / TRIAL / "events.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    rows[1]["detail"] = {"action": "tampered"}
    ledger.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))

    first = verify_trial(tmp_path, TRIAL)
    assert first["ok"] is False and "event:2:event_hash" in first["errors"]
    second = verify_trial(tmp_path, TRIAL)
    assert second["errors"] == first["errors"]
    assert second["ok"] is False


def test_warm_and_cold_agree_on_a_ledger_that_goes_bad_after_the_memo(tmp_path: Path):
    """The suffix scan must report what a whole-file scan reports — same
    findings, same LINE NUMBERS, same event count.  A suffix scanned as if it
    started at line 1 would mislabel every finding in it."""
    recorder = EvidenceRecorder(tmp_path)
    for step in ("one", "two", "three"):
        _append(recorder, step=step)
    _warm_memo(tmp_path)
    ledger = tmp_path / "trials" / TRIAL / "events.jsonl"
    ledger.write_bytes(ledger.read_bytes() + b"{not json}\n")

    warm = verify_trial(tmp_path, TRIAL)
    reset_verified_ledger_memo()
    cold = verify_trial(tmp_path, TRIAL)
    assert warm == cold, (warm, cold)
    assert warm["ok"] is False
    assert "invalid_json_line:4" in warm["errors"]
    assert warm["event_count"] == 3
