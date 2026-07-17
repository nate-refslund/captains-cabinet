"""Phase-2 Batch A per-wave acceptance harness (design §3 Ph2 item 5).

The dogfood pattern (framework/evidence/dogfood.py), applied to the Batch-A
telemetry MIRROR contract: mirrors are receipts about already-happened org
events — they append recorder events on day-bounded taxonomy trials
(``evt-<class>-<yyyymmdd>``) with a FIXED system identity, degrade loud and
never block the domain emit.  This suite pins the receipt contract the
chokepoint hooks (org-event emitter + consequence emitter) must satisfy,
end-to-end against a SCRATCH store:

  * lifecycle coverage — day trials, v1.1 absence vocabulary, terminality;
  * redaction on mirror-borne fields BEFORE hashing (plant secret-shaped
    values in an org-event payload excerpt; the stored bytes are clean AND
    the trial still verifies, so redaction preceded the hash);
  * recorder determinism — stored event bytes == returned event bytes;
  * producer identity never payload-derived (the mirrored org actor is DATA
    in ``detail``; the evidence actor is the fixed mirror constant) and the
    A10 env-provenance seam (mirrors must pass an explicit component);
  * WAL crash recovery — exactly-once reconciliation of an interrupted
    append (the dogfood power-loss idiom);
  * purge semantics over mirrored trials — Captain-only typed purge, signed
    content-free receipt, purge finality (absence is never health);
  * officer projection — mirror correlation keys are auto-dropped by the
    fail-closed ``PROJECTION_ALLOWED_DETAIL`` (never-a-score by
    construction; ``cabinet/scripts/evidence-read.sh`` stays the only
    officer path and is untouched by Batch A);
  * digest-anchor coexistence — the Phase-1 daily anchor producer and the
    Batch-A mirror trials share one store and verify together.

Non-germline home (framework/tests/), per the retention/doctrine-laws
precedent: framework/evidence/** is schg-locked and Batch A must not widen
the germline diff.  Scratch stores only: every recorder is rooted in
tmp_path, and the repo-root conftest fence keeps even a default-constructed
recorder out of the live instance/evidence store (pinned below).
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

import pytest

from framework.evidence import (
    EvidenceError,
    EvidenceRecorder,
    verify_store,
    verify_trial,
)
from framework.evidence.recorder import (
    PROJECTION_ALLOWED_DETAIL,
    TERMINAL_STATUSES,
    TRIAL_CLASS_RE,
)
import framework.evidence_anchor as evidence_anchor

# The fixed Batch-A mirror identities (seam map: identity is a constant,
# never derived from the mirrored payload; broker attestation is the later
# ceremony wave).
MIRROR_ACTOR = {"kind": "system", "id": "org-event-mirror"}
CONSEQUENCE_ACTOR = {"kind": "system", "id": "consequence-mirror"}
MIRROR_COMPONENT = {"name": "org-event-mirror", "version": "1", "commit": "unset"}

ORG_TRIAL = "evt-orgmirror-20260716"
CONSEQ_TRIAL = "evt-consequence-20260716"

# Fabricated secret SHAPES (never real credentials) matching the redaction
# families a hostile/buggy org payload could carry into mirror detail.
SECRET_SK = "sk-batcha-mirror-" + "x" * 24
SECRET_BOT = "8123456789:" + "A" * 35
SECRET_EMAIL = "captain-private@example.com"


def _store(tmp_path: Path, name: str = "store") -> EvidenceRecorder:
    return EvidenceRecorder(tmp_path / name)


def _receipt(
    recorder: EvidenceRecorder,
    trial_id: str = ORG_TRIAL,
    *,
    status: str = "succeeded",
    detail: dict | None = None,
    correlation_id: str | None = None,
    actor: dict | None = None,
    component: dict | None = None,
) -> dict:
    """Append one mirror-shaped receipt exactly as the chokepoint hooks do."""
    context = recorder.trace(
        trial_id, surface="system", correlation_id=correlation_id
    )
    return recorder.append(
        context,
        phase="system",
        status=status,
        actor=actor or MIRROR_ACTOR,
        component=component or MIRROR_COMPONENT,
        detail=detail if detail is not None else {
            "action": "org_event_mirrored",
            "org_event_id": uuid.uuid4().hex,
            "org_event_type": "need_created",
            "ledger_date": "2026-07-16",
        },
    )


def _raw_ledger(recorder: EvidenceRecorder, trial_id: str) -> str:
    return (recorder.root / "trials" / trial_id / "events.jsonl").read_text(
        encoding="utf-8"
    )


# --- lifecycle -------------------------------------------------------------

def test_mirror_receipt_day_trial_end_to_end(tmp_path):
    recorder = _store(tmp_path)
    org_ids = [uuid.uuid4().hex for _ in range(3)]
    for index, org_id in enumerate(org_ids):
        event = _receipt(
            recorder,
            detail={
                "action": "org_event_mirrored",
                "org_event_id": org_id,
                "org_event_type": ["need_created", "graduation_transition",
                                   "captain_gate_bounced"][index],
                "ledger_date": "2026-07-16",
            },
            correlation_id=org_id,
        )
        # The forward join key rides the recorder-native correlation field.
        assert event["correlation_id"] == org_id
        assert event["sequence"] == index + 1
        assert event["trust"] == "untrusted_observation"

    result = verify_trial(recorder.root, ORG_TRIAL)
    assert result["ok"], result["errors"]
    assert result["event_count"] == 3
    match = TRIAL_CLASS_RE.fullmatch(ORG_TRIAL)
    assert match and match.group(1) == "orgmirror"

    # The consequence chokepoint writes its own day trial in the same store.
    conseq_row = {
        "actor": "officer:cto", "action": "send_reply",
        "subject": "thread-42", "ts": "2026-07-16T08:00:00Z",
    }
    _receipt(
        recorder,
        CONSEQ_TRIAL,
        detail={
            "action": "consequence_mirrored",
            "row_sha256": hashlib.sha256(
                json.dumps(conseq_row, sort_keys=True).encode()
            ).hexdigest(),
            "ledger_date": "2026-07-16",
        },
        actor=CONSEQUENCE_ACTOR,
        component={"name": "consequence-mirror", "version": "1", "commit": "unset"},
    )
    store_result = verify_store(recorder.root)
    assert store_result["ok"], store_result["errors"]
    assert store_result["trial_count"] == 2


def test_mirror_status_vocabulary_includes_absence(tmp_path):
    """v1.1 absence statuses are valid, verifying, terminal mirror vocabulary."""
    recorder = _store(tmp_path)
    for status in ("succeeded", "missed", "skipped", "expired"):
        event = _receipt(recorder, status=status)
        assert event["status"] == status
        assert status in TERMINAL_STATUSES
    assert verify_trial(recorder.root, ORG_TRIAL)["ok"]


def test_trial_class_taxonomy_chaining_law():
    """Re-mint chain suffixes live INSIDE the class segment.

    ``evt-orgmirror-b-20260717`` keeps a per-class retention hook (class
    ``orgmirror-b``); ``evt-orgmirror-20260717-2`` silently loses it — the
    taxonomy anchors ``-\\d{8}$``.  Pinned so a cap/chaining implementation
    cannot drift onto the retention-losing spelling.
    """
    chained = TRIAL_CLASS_RE.fullmatch("evt-orgmirror-b-20260717")
    assert chained and chained.group(1) == "orgmirror-b"
    assert TRIAL_CLASS_RE.fullmatch("evt-orgmirror-20260717-2") is None


# --- redaction --------------------------------------------------------------

def test_benign_mirror_keys_survive_unredacted(tmp_path):
    """The Batch-A correlation keys dodge every redaction family."""
    recorder = _store(tmp_path)
    org_id = uuid.uuid4().hex
    event = _receipt(
        recorder,
        detail={
            "action": "org_event_mirrored",
            "org_event_id": org_id,
            "org_event_type": "need_created",
            "ledger_date": "2026-07-16",
        },
    )
    assert event["redactions"] == []
    assert event["detail"]["org_event_id"] == org_id
    assert event["detail"]["org_event_type"] == "need_created"


def test_secret_shaped_mirror_fields_redacted_before_hashing(tmp_path):
    """Plant secret-shaped values in an org payload excerpt; stored bytes are
    clean and the trial STILL verifies — redaction preceded hashing."""
    recorder = _store(tmp_path)
    event = _receipt(
        recorder,
        detail={
            "action": "org_event_mirrored",
            "org_event_id": uuid.uuid4().hex,
            "org_event_type": "need_created",
            "ledger_date": "2026-07-16",
            # A hostile/buggy producer payload: secret-shaped KEY...
            "api_key": SECRET_SK,
            # ...secret-shaped VALUES under benign keys...
            "note": f"token={SECRET_SK}",
            "excerpt": f"bot {SECRET_BOT} pinged {SECRET_EMAIL}",
        },
        # ...and a secret-shaped LINK.
    )
    raw = _raw_ledger(recorder, ORG_TRIAL)
    for sentinel in (SECRET_SK, SECRET_BOT, SECRET_EMAIL):
        assert sentinel not in raw
    assert "[REDACTED_SECRET_FIELD]" in raw   # the api_key field
    assert "[REDACTED_SECRET]" in raw         # the value shapes
    assert "secret_field" in event["redactions"]
    assert "secret_value" in event["redactions"]
    # Stored bytes == hashed bytes: a verifying trial proves the hash was
    # computed over the REDACTED form, never the raw payload.
    result = verify_trial(recorder.root, ORG_TRIAL)
    assert result["ok"], result["errors"]


def test_stored_bytes_equal_returned_event_bytes(tmp_path):
    """Recorder determinism: the ledger line is byte-identical to the
    canonical serialization of the event append() returned."""
    recorder = _store(tmp_path)
    event = _receipt(recorder)
    raw_line = _raw_ledger(recorder, ORG_TRIAL).splitlines()[0]
    assert raw_line == json.dumps(event, ensure_ascii=False, sort_keys=True)


# --- producer identity -------------------------------------------------------

def test_producer_identity_is_never_payload_derived(tmp_path):
    """The mirrored org event's claimed actor is DATA in detail; the evidence
    actor stays the fixed mirror constant."""
    recorder = _store(tmp_path)
    event = _receipt(
        recorder,
        detail={
            "action": "org_event_mirrored",
            "org_event_id": uuid.uuid4().hex,
            "org_event_type": "captain_gate_bounced",
            "ledger_date": "2026-07-16",
            # The org row claims to be the Captain — it must stay data.
            "org_actor": "captain",
        },
    )
    assert event["actor"] == MIRROR_ACTOR
    assert event["detail"]["org_actor"] == "captain"


def test_component_provenance_env_seam_documented(tmp_path, monkeypatch):
    """A10: env-fed provenance exists and is exactly why the mirror contract
    requires an EXPLICIT component — explicit values ignore the env."""
    monkeypatch.setenv("CABINET_BUILD_VERSION", "99.99-env-untrusted")
    monkeypatch.setenv("CABINET_GIT_COMMIT", "deadbeef-env")
    recorder = _store(tmp_path)
    explicit = _receipt(recorder)
    assert explicit["component"]["version"] == "1"
    assert explicit["component"]["commit"] == "unset"
    # Omitting the explicit fields rides the env fallback — the untrusted
    # seam the mirrors must never use for anything fuel-bearing.
    fallback = _receipt(recorder, component={"name": "org-event-mirror"})
    assert fallback["component"]["version"] == "99.99-env-untrusted"
    assert fallback["component"]["commit"] == "deadbeef-env"


# --- WAL crash recovery ------------------------------------------------------

def test_wal_crash_recovery_exactly_once(tmp_path):
    recorder = _store(tmp_path)
    _receipt(recorder)  # sequence 1, healthy

    original_anchor = recorder._anchor
    recorder._anchor = lambda _event: (_ for _ in ()).throw(
        OSError("simulated power loss")
    )
    try:
        with pytest.raises(OSError):
            _receipt(recorder)  # sequence 2 dies between ledger and anchor
    finally:
        recorder._anchor = original_anchor

    trial_dir = recorder.root / "trials" / ORG_TRIAL
    assert (trial_dir / "pending.json").is_file()  # the WAL survived

    recovered = recorder.recover_interrupted(ORG_TRIAL)
    assert [row["status"] for row in recovered] == ["interrupted", "recovered"]
    assert not (trial_dir / "pending.json").exists()

    result = verify_trial(recorder.root, ORG_TRIAL)
    assert result["ok"], result["errors"]
    # Exactly once: healthy + crashed + interrupted + recovered = 4 rows.
    assert result["event_count"] == 4
    rows = recorder.read_events(ORG_TRIAL)
    assert [row["sequence"] for row in rows] == [1, 2, 3, 4]

    # A second recovery pass synthesizes nothing (no fabricated history).
    assert recorder.recover_interrupted(ORG_TRIAL) == []
    assert verify_trial(recorder.root, ORG_TRIAL)["event_count"] == 4


# --- purge semantics ---------------------------------------------------------

def test_purge_semantics_over_mirror_trials(tmp_path):
    recorder = _store(tmp_path)
    for _ in range(3):
        _receipt(recorder)
    _receipt(recorder, CONSEQ_TRIAL, actor=CONSEQUENCE_ACTOR)

    # Captain-only, exact typed confirmation.
    with pytest.raises(EvidenceError) as officer_purge:
        recorder.purge_trial(
            ORG_TRIAL, confirmation=f"PURGE {ORG_TRIAL}", actor="officer"
        )
    assert officer_purge.value.code == "captain_required"
    with pytest.raises(EvidenceError) as mistyped:
        recorder.purge_trial(ORG_TRIAL, confirmation="purge", actor="captain")
    assert mistyped.value.code == "purge_confirmation"
    assert (recorder.root / "trials" / ORG_TRIAL).is_dir()  # nothing deleted

    receipt = recorder.purge_trial(
        ORG_TRIAL, confirmation=f"PURGE {ORG_TRIAL}", actor="captain"
    )
    assert receipt["event_count"] == 3
    assert receipt["purged_trial_id_hash"] == hashlib.sha256(
        ORG_TRIAL.encode()
    ).hexdigest()
    assert not (recorder.root / "trials" / ORG_TRIAL).exists()

    # The signed tombstone is content-free: no receipt byte carries the
    # mirrored detail.
    receipts = sorted((recorder.root / "purge-receipts").glob("purge-*.json"))
    assert len(receipts) == 1
    assert "org_event_mirrored" not in receipts[0].read_text(encoding="utf-8")

    # The rest of the store still verifies; the sibling day trial survives.
    store_result = verify_store(recorder.root)
    assert store_result["ok"], store_result["errors"]
    assert store_result["trial_count"] == 1


def test_purged_mirror_trial_stays_closed_and_absence_is_not_health(tmp_path):
    recorder = _store(tmp_path)
    _receipt(recorder)
    recorder.purge_trial(
        ORG_TRIAL, confirmation=f"PURGE {ORG_TRIAL}", actor="captain"
    )
    # Purge finality: the day trial cannot be silently re-minted.
    with pytest.raises(EvidenceError) as reopened:
        _receipt(recorder)
    assert reopened.value.code == "trial_purged"
    # Absence is never health: verifying the purged id fails rather than
    # passing vacuously.
    assert not verify_trial(recorder.root, ORG_TRIAL)["ok"]
    # The store as a whole stays green — the purge was sanctioned.
    assert verify_store(recorder.root)["ok"]


# --- officer projection -------------------------------------------------------

def test_officer_projection_drops_mirror_correlation_keys(tmp_path):
    """org_event_id / org_event_type / ledger_date are NOT in the fail-closed
    projection allow-list — they never reach the officer view, keeping
    never-a-score true by construction with zero germline change."""
    for key in ("org_event_id", "org_event_type", "ledger_date", "org_actor",
                "row_sha256"):
        assert key not in PROJECTION_ALLOWED_DETAIL
    recorder = _store(tmp_path)
    _receipt(recorder)
    projection = recorder.cabinet_projection(ORG_TRIAL)
    assert projection["mode"] == "read_only_redacted"
    (record,) = projection["records"]
    assert record["detail"] == {"action": "org_event_mirrored"}
    projected_text = json.dumps(projection, ensure_ascii=False)
    assert "org_event_id" not in projected_text
    assert "ledger_date" not in projected_text


# --- digest anchor coexistence -------------------------------------------------

def test_digest_anchor_coexists_with_mirror_trials(tmp_path):
    """The Phase-1 daily digest anchor (the R-13 wholesale tamper-evidence
    layer) and the Batch-A per-class mirror trials share one store."""
    recorder = _store(tmp_path)
    _receipt(recorder)
    _receipt(recorder, CONSEQ_TRIAL, actor=CONSEQUENCE_ACTOR)

    org_day = tmp_path / "events-2026-07-16.jsonl"
    org_day.write_text(
        json.dumps({"event_type": "need_created", "id": "x"}) + "\n",
        encoding="utf-8",
    )
    conseq_day = tmp_path / "consequence-events-2026-07-16.jsonl"
    conseq_day.write_text(
        json.dumps({"kind": "proposal", "action": "send"}) + "\n",
        encoding="utf-8",
    )
    trigger_dir = tmp_path / "triggers"
    trigger_dir.mkdir()
    (trigger_dir / "officer-cos.jsonl").write_text("{}\n", encoding="utf-8")

    detail = evidence_anchor.build_digest_detail(
        ledger_date="2026-07-16",
        org_events_file=org_day,
        consequence_file=conseq_day,
        trigger_archive_dir=trigger_dir,
    )
    event = evidence_anchor.append_digest_trial(
        recorder.root, detail, run_date="2026-07-16"
    )
    assert event["trial_id"] == "evt-digest-anchor-20260716"

    store_result = verify_store(recorder.root)
    assert store_result["ok"], store_result["errors"]
    assert store_result["trial_count"] == 3


# --- scratch-store discipline ---------------------------------------------------

def test_default_store_resolution_is_fenced_under_pytest():
    """The repo-root conftest fence (2026-07-16) points CABINET_EVIDENCE_DIR
    at a session sandbox, so even a default-constructed recorder in a
    fixture-less test can never touch the live instance store."""
    fence = os.environ.get("CABINET_EVIDENCE_DIR")
    assert fence, "repo-root conftest fence is not loaded"
    recorder = EvidenceRecorder()
    assert Path(recorder.root).is_relative_to(Path(fence))
    assert "instance/evidence" not in Path(recorder.root).as_posix()
