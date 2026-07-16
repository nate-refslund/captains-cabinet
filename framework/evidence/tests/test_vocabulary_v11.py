"""Schema v1.1 vocabulary wave — lockstep, backward-compat, and redaction teeth.

Phase-1 invariants pinned here:
- the status vocabulary is TRIPLICATED (recorder, verifier, JSON schema) and
  must never drift;
- v1 events still verify and still validate under the widened schema;
- every reserved v1.1 detail key survives sanitize (no key-name redaction
  collision) while secret-shaped VALUES in those keys are destroyed at
  append, before hashing;
- the officer projection admits only the ratified new keys and never the
  cost/resource observations (never-a-score);
- the field-classification registry is total, frozen, and all detail keys
  are producer-asserted today.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from framework.evidence import EvidenceRecorder, classification
from framework.evidence import recorder as recorder_mod
from framework.evidence import verifier as verifier_mod
from framework.evidence.recorder import PROJECTION_ALLOWED_DETAIL, TERMINAL_STATUSES
from framework.evidence.redaction import (
    RAW_CONTENT_KEY_RE,
    REASONING_KEY_RE,
    SECRET_KEY_RE,
    contains_secret_shape,
    sanitize_string,
)
from framework.evidence.verifier import verify_trial

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "evidence-event.schema.json"
ABSENCE_STATUSES = frozenset({"missed", "skipped", "expired"})
NEVER_PROJECTED = frozenset({
    "input_tokens", "output_tokens", "cost_usd", "resource_kind",
    "effort_tier", "delegation_depth", "scheduled_for",
})
# Deliberately bare JWT (three base64url segments): the writer must redact
# it, the verify-time scan must NOT flag it (stored v1 rows keep verifying).
BARE_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvZmZpY2VyLWNvcyJ9.QWJjZGVmZ2hpamtsbW5vcA"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _context(recorder: EvidenceRecorder, trial: str):
    return recorder.trace(
        trial,
        surface="system",
        trace_id="trace-vocab-001",
        action_id="action-vocab-001",
        correlation_id="corr-vocab-001",
    )


def _append(recorder: EvidenceRecorder, trial: str, *, phase: str, status: str,
            detail: dict, links: list[str] | None = None) -> dict:
    return recorder.append(
        _context(recorder, trial),
        phase=phase,
        status=status,
        actor={"kind": "system", "id": "vocab-test"},
        component={"name": "vocab-test", "version": "1", "commit": "abc123"},
        detail=detail,
        links=links,
    )


def test_status_vocabulary_lockstep_across_recorder_verifier_and_schema():
    schema = _schema()
    schema_statuses = set(schema["properties"]["status"]["enum"])
    assert recorder_mod.STATUSES == verifier_mod.STATUSES == schema_statuses
    assert ABSENCE_STATUSES <= schema_statuses
    # The other duplicated vocabularies must not drift either.
    assert recorder_mod.PHASES == verifier_mod.PHASES == set(schema["properties"]["phase"]["enum"])
    assert recorder_mod.SURFACES == verifier_mod.SURFACES == set(schema["properties"]["surface"]["enum"])
    assert verifier_mod.ACTOR_KINDS == set(schema["properties"]["actor"]["properties"]["kind"]["enum"])
    # Top-level shape: verifier exact-set check and schema stay identical.
    assert verifier_mod.EVENT_KEYS == set(schema["required"]) == set(schema["properties"])


def test_absence_statuses_are_terminal():
    assert ABSENCE_STATUSES <= recorder_mod.STATUSES
    assert ABSENCE_STATUSES <= TERMINAL_STATUSES


def test_v1_vocabulary_events_still_verify_and_validate(tmp_path: Path):
    recorder = EvidenceRecorder(tmp_path)
    trial = "evt-vocab-v1-compat"
    first = _append(recorder, trial, phase="intent", status="started",
                    detail={"action": "propose_window"})
    second = _append(recorder, trial, phase="outcome", status="succeeded",
                     detail={"result_code": "charter_proposed"})
    result = verify_trial(tmp_path, trial)
    assert result["ok"] is True
    assert set(result["checks"].values()) == {"pass"}
    schema = _schema()
    jsonschema.validate(first, schema)
    jsonschema.validate(second, schema)


def test_absence_status_events_append_verify_and_validate(tmp_path: Path):
    recorder = EvidenceRecorder(tmp_path)
    trial = "evt-vocab-absence"
    schema = _schema()
    for status in sorted(ABSENCE_STATUSES):
        event = _append(
            recorder, trial, phase="outcome", status=status,
            detail={
                "action": "heartbeat_run",
                "scheduled_by": "launchd:com.cabinet.officer.cos",
                "trigger_kind": "cron",
                "scheduled_for": "2026-07-16T04:00:00Z",
            },
        )
        assert event["status"] == status
        jsonschema.validate(event, schema)
    result = verify_trial(tmp_path, trial)
    assert result["ok"] is True
    assert set(result["checks"].values()) == {"pass"}


def test_reserved_detail_keys_survive_sanitize_and_project_allow_listed(tmp_path: Path):
    recorder = EvidenceRecorder(tmp_path)
    trial = "evt-vocab-reserved"
    detail = {
        "action": "spawn_delegation",
        "parent_trial_id": "evt-parent-20260716",
        "spawned_by": "officer-cos",
        "delegation_depth": 1,
        "scheduled_by": "launchd:com.cabinet.officer.cos",
        "trigger_kind": "cron",
        "scheduled_for": "2026-07-16T04:00:00Z",
        "egress_approval_ref": "approval-20260716-001",
        "input_tokens": 1200,
        "output_tokens": 340,
        "cost_usd": 0.0132,
        "resource_kind": "llm",
        "model_id": "claude-opus-4-8[1m]",
        "effort_tier": "max",
        "skill_revision": "telegram-communication:v3",
    }
    event = _append(recorder, trial, phase="execution", status="succeeded", detail=dict(detail))
    # No reserved name collides with a redaction key pattern: every value is
    # stored byte-exact (model ids with brackets belong in detail — the
    # component provenance regex would reject them).
    assert event["detail"] == detail
    assert event["redactions"] == []
    assert verify_trial(tmp_path, trial)["ok"] is True
    jsonschema.validate(event, _schema())

    projection = recorder.cabinet_projection(trial)
    assert projection["mode"] == "read_only_redacted"
    record = projection["records"][-1]
    expected_visible = {
        "action", "parent_trial_id", "spawned_by", "scheduled_by",
        "trigger_kind", "model_id", "skill_revision", "egress_approval_ref",
    }
    assert set(record["detail"]) == expected_visible
    for key in expected_visible:
        assert record["detail"][key] == detail[key]


def test_projection_never_exposes_cost_or_resource_aggregates():
    # Never-a-score: cost/resource observations stay out of the officer
    # projection until the Captain explicitly rules them in.
    assert NEVER_PROJECTED.isdisjoint(PROJECTION_ALLOWED_DETAIL)
    # The ratified v1.1 additions are exactly these seven keys.
    assert classification.RESERVED_DETAIL_KEYS_V11 & PROJECTION_ALLOWED_DETAIL == {
        "parent_trial_id", "spawned_by", "scheduled_by", "trigger_kind",
        "model_id", "skill_revision", "egress_approval_ref",
    }


def test_secret_shaped_values_in_reserved_keys_are_redacted_before_hashing(tmp_path: Path):
    recorder = EvidenceRecorder(tmp_path)
    trial = "evt-vocab-redaction"
    event = _append(
        recorder, trial, phase="execution", status="failed",
        detail={
            "model_id": "sk-" + "Ab1" * 12,                # provider API key shape
            "egress_approval_ref": "captain@example.com",  # destination, not an opaque ref
            "skill_revision": BARE_JWT,                    # broker/session token
            "scheduled_by": "y" * 600,                     # oversize free text
            "spawned_by": "/Users/exampleuser/agent tools/run",  # absolute local path
        },
    )
    stored = event["detail"]
    assert stored["model_id"] == "[REDACTED_SECRET]"
    assert stored["egress_approval_ref"] == "[REDACTED_SECRET]"
    assert stored["skill_revision"] == "[REDACTED_SECRET]"
    assert stored["scheduled_by"].endswith("…[TRUNCATED]")
    assert stored["spawned_by"].startswith("[LOCAL_PATH:")
    assert "captain@example.com" not in json.dumps(event, ensure_ascii=False)
    assert BARE_JWT not in json.dumps(event, ensure_ascii=False)
    for note in ("secret_value", "string_truncated", "absolute_path"):
        assert note in event["redactions"]
    # Redaction ran before hashing: the stored trial verifies clean.
    result = verify_trial(tmp_path, trial)
    assert result["ok"] is True
    assert result["checks"]["secret_shapes"] == "pass"


def test_writer_side_patterns_do_not_widen_the_verify_time_scan():
    # Writer-side: the bare JWT and Slack token shapes are destroyed.
    for value in (BARE_JWT, "xoxb-1234567890-abcdefghijkl"):
        clean, notes = sanitize_string(value)
        assert clean == "[REDACTED_SECRET]"
        assert "secret_value" in notes
    # Verify-time: contains_secret_shape is deliberately UNCHANGED so every
    # already-stored v1 row keeps verifying byte-for-byte.  Widening it is a
    # ceremony that must re-baseline existing stores.
    assert contains_secret_shape(BARE_JWT) is False
    assert contains_secret_shape("xoxb-1234567890-abcdefghijkl") is False
    # Shared patterns still fire on both sides (sanity).
    assert contains_secret_shape("sk-" + "a" * 30) is True


def test_minted_parent_child_lineage_convention(tmp_path: Path):
    recorder = EvidenceRecorder(tmp_path)
    parent = "evt-parent-20260716"
    child = "evt-child-20260716"
    _append(recorder, parent, phase="intent", status="started",
            detail={"action": "delegate_subtask"})
    genesis = _append(
        recorder, child, phase="system", status="started",
        detail={
            "action": "spawn_delegation",
            classification.LINEAGE_KEY: parent,
            "spawned_by": "officer-cos",
            "delegation_depth": 1,
        },
        links=[f"{classification.LINEAGE_LINK_PREFIX}{parent}"],
    )
    assert genesis["detail"]["parent_trial_id"] == parent
    assert genesis["links"] == [f"evidence-parent:{parent}"]
    assert verify_trial(tmp_path, parent)["ok"] is True
    assert verify_trial(tmp_path, child)["ok"] is True
    jsonschema.validate(genesis, _schema())
    # The structured key is officer-visible; the depth aggregate is not.
    record = recorder.cabinet_projection(child)["records"][-1]
    assert record["detail"]["parent_trial_id"] == parent
    assert record["detail"]["spawned_by"] == "officer-cos"
    assert "delegation_depth" not in record["detail"]


def test_classification_registry_is_total_frozen_and_producer_asserted_today():
    assert classification.CLASSES == {
        classification.PRODUCER_ASSERTED,
        classification.INDEPENDENTLY_ESTABLISHED,
    }
    # Total over the shapes that exist: every top-level event key, every
    # projection-allow-listed key, and every reserved v1.1 key is classed.
    assert set(classification.EVENT_FIELD_CLASSIFICATION) == verifier_mod.EVENT_KEYS
    assert classification.RESERVED_DETAIL_KEYS_V11 <= set(classification.DETAIL_FIELD_CLASSIFICATION)
    assert PROJECTION_ALLOWED_DETAIL <= set(classification.DETAIL_FIELD_CLASSIFICATION)
    assert set(classification.EVENT_FIELD_CLASSIFICATION.values()) <= classification.CLASSES
    # Phase-1 doctrine: no detail key is independently established yet;
    # promoting one requires the independent checker plus a ceremony.
    assert set(classification.DETAIL_FIELD_CLASSIFICATION.values()) == {classification.PRODUCER_ASSERTED}
    assert classification.classify_detail_key("some_future_key") == classification.PRODUCER_ASSERTED
    # Env-derived component provenance is untrusted and never fuel-bearing.
    assert classification.UNTRUSTED_ENV_PROVENANCE == {"component.version", "component.commit"}
    assert classification.UNTRUSTED_ENV_PROVENANCE <= classification.NEVER_FUEL_BEARING
    # Lineage convention constants.
    assert classification.LINEAGE_KEY == "parent_trial_id"
    assert classification.LINEAGE_KEY in classification.RESERVED_DETAIL_KEYS_V11
    assert classification.LINEAGE_LINK_PREFIX == "evidence-parent:"
    # Frozen: the registry cannot be mutated at runtime.
    with pytest.raises(TypeError):
        classification.DETAIL_FIELD_CLASSIFICATION["x"] = "y"  # type: ignore[index]
    with pytest.raises(TypeError):
        classification.EVENT_FIELD_CLASSIFICATION["x"] = "y"  # type: ignore[index]


def test_registered_detail_keys_never_collide_with_redaction_key_patterns():
    # A detail key matching a redaction key pattern would silently destroy
    # its value forever (token_count would; input_tokens must not).  Pin the
    # whole registry clear of every key-name pattern.
    for key in classification.DETAIL_FIELD_CLASSIFICATION:
        assert not SECRET_KEY_RE.search(key), key
        assert not REASONING_KEY_RE.search(key), key
        assert not RAW_CONTENT_KEY_RE.search(key), key
