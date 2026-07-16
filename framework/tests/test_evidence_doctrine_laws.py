"""Phase-1 evidence doctrine laws, pinned as executable tests.

Behavioral half of golden eval eval-025-never-a-score (whole-cabinet
evidence design, 2026-07-16 — §2.2 R1, §2.4, §2.5; Phase-1 item 7 "laws
pinned as tests"). Each law is exercised against a sandbox store built in
tmp_path via the public framework.evidence API — never the live
instance/evidence store, never the germline lock lists.

Laws covered here:
  * INTEGRITY ≠ VERACITY — every event is recorder-stamped
    trust=untrusted_observation; verification success never upgrades it;
    even a key-holding forger cannot mint a trusted event (the verifier
    and schema pin trust as a const). Field classes (producer-asserted vs
    independently-established) are enforced the moment the Phase-1
    classification registry lands (forward pin, loud skip before then).
  * ABSENCE ≠ HEALTH — a missing trial verifies FALSE; a trial removed
    outside the sanctioned purge path trips store verification; the R-2
    absence statuses (missed/skipped/expired) are lockstep-pinned across
    recorder, verifier, schema, and TERMINAL_STATUSES the moment they land
    (forward pin, loud skip before then).
  * PURGE/RETENTION DISCIPLINE — Captain-only, exact confirmation,
    content-free signed tombstones, purge finality (no reopen, no
    resurrection), retention defaults to no-op and expiry purges only via
    tombstoned receipts. The PROMOTION-REVOCATION rule (§2.4: a promotion
    whose supporting evidence window was later purged is revoked pending
    re-derivation) has no executable home until the Phase-4 fuel-integrity
    check — it is carried verbatim by the eval body and the never-a-score
    fixture doctrine block, deliberately not faked here.
  * DIAGNOSTIC ANNOTATES, NEVER SUPPRESSES — diagnostic-mode events stay
    fully verified and fully projected (A9: no judge-blinding switch).
  * ENV PROVENANCE IS UNTRUSTED — malformed env build/commit values redact;
    valid ones are transcribed but never change the trust class; an
    explicit store root ignores CABINET_EVIDENCE_DIR (A10).
  * NEVER A SCORE at the boundary — score-shaped detail keys are dropped
    by the officer projection fail-closed (§2.5; the static half lives in
    cabinet/evals/never-a-score/harness.py, runner section
    EVAL-025-NEVER-A-SCORE).

House interpreter: python3.12 (hermetic suites pin HOME; CI runs
`pytest framework/`).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

import framework.evidence.recorder as recorder_module
import framework.evidence.verifier as verifier_module
from framework.evidence import EvidenceError, EvidenceRecorder
from framework.evidence.recorder import _atomic_json, _digest, _event_signature
from framework.evidence.verifier import verify_store, verify_trial

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "framework" / "schemas" / "evidence-event.schema.json"

TRIAL = "evt-doctrine-20260716"


def _append(rec: EvidenceRecorder, trial: str = TRIAL, *, phase: str = "execution",
            status: str = "succeeded", detail: dict | None = None,
            component: dict | None = None) -> dict:
    return rec.append(
        rec.trace(trial, surface="test"),
        phase=phase,
        status=status,
        actor={"kind": "system", "id": "doctrine-probe"},
        component=component or {"name": "doctrine-probe", "version": "1"},
        detail=detail or {"action": "doctrine_probe"},
    )


# --- integrity != veracity -------------------------------------------------

def test_every_event_is_untrusted_and_verification_never_upgrades_it(tmp_path):
    rec = EvidenceRecorder(tmp_path)
    event = _append(rec)
    assert event["trust"] == "untrusted_observation"
    result = verify_trial(tmp_path, TRIAL)
    assert result["ok"] is True
    stored = json.loads(
        (tmp_path / "trials" / TRIAL / "events.jsonl").read_text().splitlines()[0])
    assert stored["trust"] == "untrusted_observation"
    projection = rec.cabinet_projection(TRIAL)
    assert "UNTRUSTED OBSERVATIONS ONLY" in projection["instruction_boundary"]
    assert all(r["trust"] == "untrusted_observation"
               for r in projection["records"])


def test_even_a_key_holding_forger_cannot_mint_a_trusted_event(tmp_path):
    """Integrity is not veracity — and veracity can't be self-declared
    either: trust is a const, so a forged row with a correctly recomputed
    hash, a valid signature (same-user key), and a rebuilt anchor STILL
    fails verification on the trust field."""
    rec = EvidenceRecorder(tmp_path)
    _append(rec)
    _append(rec)  # second append verifies the trial and advances the watermark
    ledger = tmp_path / "trials" / TRIAL / "events.jsonl"
    lines = ledger.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[1])
    row["trust"] = "verified_truth"
    unsigned = {k: v for k, v in row.items() if k not in {"event_hash", "signature"}}
    row["event_hash"] = _digest(unsigned)
    key = (tmp_path / ".signing-key").read_bytes()
    row["signature"] = _event_signature(key, TRIAL, 2, row["event_hash"])
    ledger.write_text(
        lines[0] + "\n" + json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")
    _atomic_json(tmp_path / "trials" / TRIAL / "anchor.json", rec._anchor(row))
    result = verify_trial(tmp_path, TRIAL)
    assert result["ok"] is False
    assert "event:2:trust" in result["errors"]


def test_field_classification_registry_when_present():
    """Forward pin for the Phase-1 vocabulary wave (§2.2 R1): every detail
    key classed producer_asserted or independently_established; only the
    second class may ever bear fuel. Activates at integration."""
    spec = importlib.util.find_spec("framework.evidence.classification")
    if spec is None:
        pytest.skip(
            "framework.evidence.classification not landed yet — the "
            "field-classification registry ships with the Phase-1 "
            "vocabulary wave; this law activates the moment it exists")
    module = importlib.import_module("framework.evidence.classification")
    allowed_classes = {"producer_asserted", "independently_established"}
    mappings = [
        value for name, value in vars(module).items()
        if not name.startswith("__")
        and hasattr(value, "items") and not callable(value)
    ]
    registries = [
        m for m in mappings
        if m and all(isinstance(k, str) for k in m.keys())
        and all(isinstance(v, str) for v in m.values())
    ]
    assert registries, (
        "classification module exists but exports no str->str registry "
        "mapping — the field-class contract is absent")
    for registry in registries:
        rogue = {k: v for k, v in registry.items() if v not in allowed_classes}
        assert not rogue, (
            f"field classes outside producer_asserted/"
            f"independently_established: {rogue}")


# --- absence != health ------------------------------------------------------

def test_a_missing_trial_verifies_false_not_healthy(tmp_path):
    EvidenceRecorder(tmp_path)  # initialize an empty, valid store
    result = verify_trial(tmp_path, "evt-never-happened-20200101")
    assert result["ok"] is False
    assert "trial_not_found" in result["errors"]


def test_a_vanished_trial_trips_store_verification(tmp_path):
    rec = EvidenceRecorder(tmp_path)
    _append(rec)
    assert verify_trial(tmp_path, TRIAL)["ok"] is True  # advances watermark
    assert verify_store(tmp_path)["ok"] is True
    shutil.rmtree(tmp_path / "trials" / TRIAL)  # removal OUTSIDE the purge path
    store = verify_store(tmp_path)
    assert store["ok"] is False
    assert any(e.startswith("trial_removed_without_receipt")
               for e in store["errors"])


def test_absence_statuses_lockstep_when_present():
    """Forward pin for R-2: a scheduled thing that did not run must have an
    evidence shape. When missed/skipped/expired land they must land in ALL
    of recorder STATUSES, verifier STATUSES, the schema enum, and
    TERMINAL_STATUSES (a non-occurrence is final) — one lockstep wave."""
    absence = {"missed", "skipped", "expired"}
    if not (absence & recorder_module.STATUSES):
        pytest.skip(
            "absence statuses not landed yet — R-2 ships with the Phase-1 "
            "vocabulary wave; this lockstep law activates the moment any "
            "of missed/skipped/expired appears")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_statuses = set(schema["properties"]["status"]["enum"])
    assert absence <= recorder_module.STATUSES
    assert absence <= verifier_module.STATUSES
    assert absence <= schema_statuses
    assert absence <= recorder_module.TERMINAL_STATUSES


# --- purge / retention discipline -------------------------------------------

def test_purge_is_captain_only_with_exact_confirmation(tmp_path):
    rec = EvidenceRecorder(tmp_path)
    _append(rec)
    with pytest.raises(EvidenceError) as officer_attempt:
        rec.purge_trial(TRIAL, confirmation=f"PURGE {TRIAL}", actor="officer")
    assert officer_attempt.value.code == "captain_required"
    with pytest.raises(EvidenceError) as sloppy_confirmation:
        rec.purge_trial(TRIAL, confirmation="purge it", actor="captain")
    assert sloppy_confirmation.value.code == "purge_confirmation"
    assert (tmp_path / "trials" / TRIAL).is_dir()  # nothing was deleted


def test_purge_leaves_a_content_free_tombstone_and_is_final(tmp_path):
    rec = EvidenceRecorder(tmp_path)
    _append(rec)
    receipt = rec.purge_trial(TRIAL, confirmation=f"PURGE {TRIAL}", actor="captain")
    assert receipt["status"] == "completed"
    trial_hash = hashlib.sha256(TRIAL.encode("utf-8")).hexdigest()
    assert receipt["purged_trial_id_hash"] == trial_hash
    # Content-free: the completed tombstone never carries the trial id.
    assert "pending_trial_id" not in receipt
    assert all(value != TRIAL for value in receipt.values()
               if isinstance(value, str))
    assert not (tmp_path / "trials" / TRIAL).exists()
    # Finality: the purged trial can never be reopened by an appender.
    with pytest.raises(EvidenceError) as reopen:
        _append(rec)
    assert reopen.value.code == "trial_purged"
    # The tombstoned store still verifies healthy — purge is sanctioned.
    assert verify_store(tmp_path)["ok"] is True


def test_a_resurrected_purged_trial_fails_store_verification(tmp_path):
    rec = EvidenceRecorder(tmp_path)
    _append(rec)
    rec.purge_trial(TRIAL, confirmation=f"PURGE {TRIAL}", actor="captain")
    (tmp_path / "trials" / TRIAL).mkdir()  # re-plant beside the tombstone
    store = verify_store(tmp_path)
    assert store["ok"] is False
    assert any(e.startswith("purged_trial_resurrected") for e in store["errors"])


def test_retention_defaults_to_no_op_and_expiry_purges_via_tombstones(tmp_path):
    rec = EvidenceRecorder(tmp_path)
    old_trial = "evt-doctrine-old-20200101"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(recorder_module, "_utc_now",
                   lambda: "2020-01-01T00:00:00.000000Z")
        _append(rec, old_trial)
    _append(rec)  # a fresh trial that must survive
    with pytest.raises(EvidenceError) as officer_attempt:
        rec.enforce_retention(actor="officer")
    assert officer_attempt.value.code == "captain_required"
    # Default control: retention unset — enforcing purges NOTHING.
    result = rec.enforce_retention(actor="captain")
    assert result["retention_days"] is None
    assert result["purged"] == []
    assert (tmp_path / "trials" / old_trial).is_dir()
    # Captain sets a dial; only the expired trial is purged, via tombstone.
    rec.configure(actor="captain", retention_days=30, diagnostic_mode=False)
    result = rec.enforce_retention(actor="captain")
    old_hash = hashlib.sha256(old_trial.encode("utf-8")).hexdigest()
    assert [p["purged_trial_id_hash"] for p in result["purged"]] == [old_hash]
    assert not (tmp_path / "trials" / old_trial).exists()
    assert (tmp_path / "trials" / TRIAL).is_dir()
    assert list((tmp_path / "purge-receipts").glob("purge-*.json"))
    assert verify_store(tmp_path)["ok"] is True


# --- diagnostic annotates, never suppresses ---------------------------------

def test_diagnostic_mode_annotates_and_never_suppresses(tmp_path):
    rec = EvidenceRecorder(tmp_path)
    before = _append(rec)
    rec.configure(actor="captain", retention_days=None, diagnostic_mode=True)
    during = _append(rec)
    rec.configure(actor="captain", retention_days=None, diagnostic_mode=False)
    after = _append(rec)
    # Annotation: the flag is stamped per event, truthfully.
    assert (before["diagnostic_mode"], during["diagnostic_mode"],
            after["diagnostic_mode"]) == (False, True, False)
    # Never suppression: every event verifies and every event projects.
    result = verify_trial(tmp_path, TRIAL)
    assert result["ok"] is True
    assert result["event_count"] == 3
    projection = rec.cabinet_projection(TRIAL)
    assert len(projection["records"]) == 3


# --- env provenance is untrusted ---------------------------------------------

def test_malformed_env_provenance_redacts_and_never_changes_trust(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_BUILD_VERSION", "claude-opus-4-8[1m]")
    monkeypatch.setenv("CABINET_GIT_COMMIT", "deadbeef; rm -rf /")
    rec = EvidenceRecorder(tmp_path)
    event = _append(rec, component={"name": "doctrine-probe"})
    assert event["component"]["version"] == "redacted"
    assert event["component"]["commit"] == "redacted"
    assert "component_provenance" in event["redactions"]
    # A well-formed env value is transcribed — but it is CONTENT an officer
    # environment could have chosen, so the trust class never moves.
    monkeypatch.setenv("CABINET_BUILD_VERSION", "9.9.9+officer-owned")
    monkeypatch.setenv("CABINET_GIT_COMMIT", "cafebabe")
    event = _append(rec, component={"name": "doctrine-probe"})
    assert event["component"]["version"] == "9.9.9+officer-owned"
    assert event["trust"] == "untrusted_observation"
    assert verify_trial(tmp_path, TRIAL)["ok"] is True


def test_explicit_store_root_ignores_env_store_redirect(tmp_path, monkeypatch):
    bogus = tmp_path / "officer-controlled"
    monkeypatch.setenv("CABINET_EVIDENCE_DIR", str(bogus))
    explicit = tmp_path / "explicit"
    rec = EvidenceRecorder(explicit)
    assert rec.root == explicit
    _append(rec)
    assert (explicit / "trials" / TRIAL / "events.jsonl").is_file()
    assert not bogus.exists()


# --- never a score at the projection boundary --------------------------------

def test_projection_drops_score_shaped_detail_keys_fail_closed(tmp_path):
    """§2.5 behavioral half: the record layer honestly stores whatever a
    producer asserts, but the officer-visible projection drops every
    non-allow-listed key — so a score-shaped detail key never becomes an
    officer-visible number without a governance-reviewed allow-list edit
    (which the static harness then interrogates)."""
    rec = EvidenceRecorder(tmp_path)
    event = _append(rec, detail={
        "action": "doctrine_probe",
        "officer_score": 9.5,
        "success_rate": 0.99,
        "elo": 1600,
    })
    assert "officer_score" in event["detail"]  # recorded: the record is honest
    projection = rec.cabinet_projection(TRIAL)
    projected_detail = projection["records"][-1]["detail"]
    assert "action" in projected_detail
    for key in ("officer_score", "success_rate", "elo"):
        assert key not in projected_detail  # never officer-visible
