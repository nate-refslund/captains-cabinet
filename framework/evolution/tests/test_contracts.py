from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None

from framework.authority.classifier import ACTION_TYPES, AMBIGUOUS
from framework.authority.matrix import RISK_CLASSES
from framework.evolution.contracts import (
    ValidationContext,
    canonical_fingerprint,
    holdout_receipt_payload_fingerprint,
    holdout_receipt_structural_issues,
    semantic_issues,
    structural_issues,
    trajectory_body_fingerprint,
    validate_trajectory,
    validate_holdout_receipt,
)


ROOT = Path(__file__).resolve().parents[3]
TRAJECTORY_SCHEMA = json.loads(
    (ROOT / "framework/schemas/cognitive-trajectory.schema.json").read_text()
)
HOLDOUT_SCHEMA = json.loads(
    (ROOT / "framework/schemas/holdout-evaluation-receipt.schema.json").read_text()
)
REFERENCE = Draft202012Validator(TRAJECTORY_SCHEMA) if Draft202012Validator else None
HOLDOUT_REFERENCE = Draft202012Validator(HOLDOUT_SCHEMA) if Draft202012Validator else None


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def _ref(name: str) -> dict:
    return {"ref": name, "digest": _digest(name)}


def _authority_catalog() -> dict[str, str]:
    matrix = yaml.safe_load((ROOT / "framework/policies/authority-matrix.yml").read_text())
    rows = matrix["policies"][0]["risk_classes"]
    catalog = {
        action_type: risk_class
        for risk_class, row in rows.items()
        for action_type in row["action_types"]
    }
    assert set(catalog) == set(ACTION_TYPES) - {AMBIGUOUS}
    assert set(catalog.values()) == set(RISK_CLASSES)
    return catalog


def _receipt(
    name: str,
    kind: str,
    *,
    subject_id: str = "fixture",
    actor_type: str = "system",
    content_time: str = "2026-07-19T11:00:00Z",
    recorded_time: str = "2026-07-19T11:30:00Z",
    cabinet_id: str = "cabinet-a",
    payload: dict | None = None,
) -> dict:
    return {
        "digest": _digest(name),
        "cabinet_id": cabinet_id,
        "kind": kind,
        "subject_id": subject_id,
        "actor_type": actor_type,
        "content_time": content_time,
        "recorded_time": recorded_time,
        "classification": "internal",
        "sharing": "local",
        "payload": payload or {},
    }


def _refresh_run_attestation(record: dict, receipts: dict) -> None:
    receipts["receipt:run-attestation"]["payload"] = {
        "trajectory_id": record["trajectory_id"],
        "run_id": record["execution_scope"]["run_id"],
        "candidate_id": record["genome"]["candidate_id"],
        "trajectory_body_fingerprint": trajectory_body_fingerprint(record),
    }


def valid_fixture(scope_kind: str = "project") -> tuple[dict, ValidationContext]:
    authority_scope = {
        "cabinet_id": "cabinet-a",
        "scope_kind": scope_kind,
    }
    execution_scope = {
        "run_id": "run-001",
        "correlation_id": "correlation-001",
        "causation_id": "cause-001",
    }
    if scope_kind in {"lane", "project"}:
        authority_scope["lane_id"] = "operations"
    if scope_kind == "project":
        authority_scope["project_id"] = "project-001"

    names = {
        "manifest": ("artifact:genome-manifest", "genome_manifest", "candidate-001"),
        "genome": ("artifact:genome", "genome_component", "candidate-001"),
        "objective": ("artifact:objective", "objective", "objective-001"),
        "constraint": ("artifact:constraint", "constraint", "constraint-001"),
        "snapshot": ("artifact:snapshot", "input_snapshot", "snapshot-001"),
        "model": ("artifact:model", "model", "model-001"),
        "tool": ("artifact:tool", "tool", "tool-001"),
        "skill": ("artifact:skill", "skill", "skill-001"),
        "context": ("artifact:context", "context", "context-001"),
        "output": ("artifact:output", "output", "output-001"),
        "prediction": ("artifact:prediction", "prediction", "prediction-001"),
        "metric": ("artifact:metric", "metric", "metric-001"),
        "span_resource": ("receipt:resource-span", "resource_usage", "span-001"),
        "run_resource": ("receipt:resource-run", "resource_usage", "trajectory-001"),
        "run_attestation": (
            "receipt:run-attestation",
            "trajectory_run_attestation",
            "trajectory-001",
        ),
    }
    receipts = {
        name: _receipt(name, kind, subject_id=subject)
        for name, kind, subject in names.values()
    }
    receipts["artifact:objective"]["actor_type"] = "objective_compiler"
    receipts["artifact:constraint"]["actor_type"] = "authority"
    receipts.update(
        {
            "receipt:classification": _receipt(
                "receipt:classification",
                "authority_classification",
                subject_id="effect-001",
                content_time="2026-07-19T11:55:00Z",
                recorded_time="2026-07-19T11:56:00Z",
                payload={"action_type": "local_edit", "risk_class": "reversible"},
            ),
            "receipt:captain-direction": _receipt(
                "receipt:captain-direction",
                "captain_direction_attestation",
                subject_id="objective-root-001",
                actor_type="captain",
            ),
            "receipt:authorization": _receipt(
                "receipt:authorization",
                "authority_decision",
                subject_id="effect-001",
                actor_type="authority",
                content_time="2026-07-19T12:00:00Z",
                recorded_time="2026-07-19T12:00:00Z",
            ),
            "receipt:effect": _receipt(
                "receipt:effect",
                "effect_outcome",
                subject_id="effect-001",
                content_time="2026-07-19T12:15:00Z",
                recorded_time="2026-07-19T12:16:00Z",
                payload={"action_type": "local_edit", "status": "verified"},
            ),
            "receipt:undo": _receipt(
                "receipt:undo",
                "undo_contract",
                subject_id="effect-001",
                content_time="2026-07-19T11:57:00Z",
                recorded_time="2026-07-19T11:58:00Z",
                payload={"action_type": "local_edit", "undo_contract": "journal:undo-001"},
            ),
            "artifact:value": _receipt(
                "artifact:value",
                "value",
                subject_id="outcome-001",
                content_time="2026-07-19T12:20:00Z",
                recorded_time="2026-07-19T12:21:00Z",
            ),
            "receipt:machine": _receipt(
                "receipt:machine",
                "machine_outcome",
                subject_id="outcome-001",
                content_time="2026-07-19T12:20:00Z",
                recorded_time="2026-07-19T12:21:00Z",
                payload={"status": "verified"},
            ),
        }
    )
    record = {
        "schema_version": "cognitive-trajectory/v1",
        "trajectory_id": "trajectory-001",
        "record_kind": "live",
        "authority_scope": authority_scope,
        "execution_scope": execution_scope,
        "started_at": "2026-07-19T10:00:00Z",
        "decision_cutoff_at": "2026-07-19T12:00:00Z",
        "completed_at": "2026-07-19T13:00:00Z",
        "genome": {
            "candidate_id": "candidate-001",
            "candidate_version": "v1",
            "incumbent_id": "champion-001",
            "incumbent_version": "v7",
            "manifest_ref": _ref("artifact:genome-manifest"),
            "component_refs": [_ref("artifact:genome")],
        },
        "intent": {
            "objective_refs": [_ref("artifact:objective")],
            "constraint_refs": [_ref("artifact:constraint")],
        },
        "input_snapshots": [
            {
                "snapshot_id": "snapshot-001",
                "artifact_ref": _ref("artifact:snapshot"),
                "maximum_content_time": "2026-07-19T11:30:00Z",
            }
        ],
        "spans": [
            {
                "span_id": "span-001",
                "status": "completed",
                "kind": "decision",
                "causation_id": "cause-001",
                "started_at": "2026-07-19T10:30:00Z",
                "completed_at": "2026-07-19T11:50:00Z",
                "genome_component_refs": [_ref("artifact:genome")],
                "model_refs": [_ref("artifact:model")],
                "tool_refs": [_ref("artifact:tool")],
                "skill_refs": [_ref("artifact:skill")],
                "context_refs": [_ref("artifact:context")],
                "input_refs": [_ref("artifact:snapshot")],
                "output_refs": [_ref("artifact:output")],
                "prediction_ref": _ref("artifact:prediction"),
                "confidence_ppm": 700000,
                "costs": {
                    "tokens": 800,
                    "tool_calls": 1,
                    "latency_ms": 4800000,
                    "external_spend_microunits": 0,
                    "resource_receipt_ref": _ref("receipt:resource-span"),
                },
            }
        ],
        "effects": [
            {
                "effect_id": "effect-001",
                "action_type": "local_edit",
                "status": "verified",
                "idempotency_key": "effect-001-attempt-001",
                "requested_at": "2026-07-19T11:54:00Z",
                "decision_at": "2026-07-19T12:00:00Z",
                "attempted_at": "2026-07-19T12:01:00Z",
                "observed_at": "2026-07-19T12:15:00Z",
                "classification_receipt_ref": _ref("receipt:classification"),
                "authority_decision_ref": _ref("receipt:authorization"),
                "effect_receipt_ref": _ref("receipt:effect"),
                "undo_receipt_ref": _ref("receipt:undo"),
            }
        ],
        "machine_outcomes": [
            {
                "outcome_id": "outcome-001",
                "status": "verified",
                "causal_basis": "intervention",
                "causal_ref": _ref("receipt:effect"),
                "measurement_started_at": "2026-07-19T12:15:00Z",
                "observed_at": "2026-07-19T12:20:00Z",
                "metric_ref": _ref("artifact:metric"),
                "value_ref": _ref("artifact:value"),
                "receipt_ref": _ref("receipt:machine"),
            }
        ],
        "human_verdicts": [],
        "judge_observations": [],
        "evaluation_basis": "machine_verifiable",
        "costs": {
            "tokens": 800,
            "tool_calls": 1,
            "latency_ms": 10800000,
            "external_spend_microunits": 0,
            "resource_receipt_ref": _ref("receipt:resource-run"),
        },
        "run_attestation_ref": _ref("receipt:run-attestation"),
        "classification": "internal",
    }

    run_binding = {
        "trajectory_id": record["trajectory_id"],
        "run_id": record["execution_scope"]["run_id"],
        "candidate_id": record["genome"]["candidate_id"],
    }
    receipts["artifact:genome-manifest"]["payload"] = {
        **run_binding,
        "candidate_version": record["genome"]["candidate_version"],
        "incumbent_id": record["genome"]["incumbent_id"],
        "incumbent_version": record["genome"]["incumbent_version"],
        "component_refs": copy.deepcopy(record["genome"]["component_refs"]),
    }
    receipts["artifact:objective"]["payload"] = {
        "objective_ref": _ref("artifact:objective"),
        "root_objective_ref": _ref("artifact:objective"),
        "authority_root_ref": _ref("receipt:captain-direction"),
        "authority_scope": copy.deepcopy(record["authority_scope"]),
    }
    receipts["receipt:captain-direction"]["payload"] = {
        "objective_ref": _ref("artifact:objective"),
        "authority_scope": copy.deepcopy(record["authority_scope"]),
    }
    receipts["artifact:constraint"]["payload"] = {
        "constraint_ref": _ref("artifact:constraint"),
        "authority_scope": copy.deepcopy(record["authority_scope"]),
    }
    receipts["artifact:snapshot"]["payload"] = {
        "snapshot_id": "snapshot-001",
        "artifact_ref": _ref("artifact:snapshot"),
        "maximum_content_time": "2026-07-19T11:30:00Z",
        "authority_scope": copy.deepcopy(record["authority_scope"]),
    }
    receipts["artifact:output"]["payload"] = {
        **run_binding,
        "span_id": "span-001",
        "artifact_ref": _ref("artifact:output"),
    }
    receipts["artifact:prediction"]["payload"] = {
        **run_binding,
        "span_id": "span-001",
        "artifact_ref": _ref("artifact:prediction"),
    }
    receipts["receipt:classification"]["payload"].update(
        {**run_binding, "effect_id": "effect-001", "decision_at": "2026-07-19T12:00:00Z"}
    )
    receipts["receipt:authorization"]["payload"].update(
        {
            **run_binding,
            "effect_id": "effect-001",
            "action_type": "local_edit",
            "risk_class": "reversible",
            "decision": "allowed",
            "idempotency_key": "effect-001-attempt-001",
            "requested_at": "2026-07-19T11:54:00Z",
            "decision_at": "2026-07-19T12:00:00Z",
            "classification_receipt_ref": _ref("receipt:classification"),
            "undo_receipt_ref": _ref("receipt:undo"),
        }
    )
    receipts["receipt:effect"]["payload"].update(
        {**run_binding, "effect_id": "effect-001", "decision": "allowed", "observed_at": "2026-07-19T12:15:00Z"}
    )
    receipts["receipt:undo"]["payload"].update(
        {**run_binding, "effect_id": "effect-001", "decision_at": "2026-07-19T12:00:00Z"}
    )
    receipts["receipt:machine"]["payload"].update(
        {
            **run_binding,
            "outcome_id": "outcome-001",
            "causal_basis": "intervention",
            "causal_ref": _ref("receipt:effect"),
            "measurement_started_at": "2026-07-19T12:15:00Z",
            "observed_at": "2026-07-19T12:20:00Z",
            "metric_ref": _ref("artifact:metric"),
            "value_ref": _ref("artifact:value"),
        }
    )
    for name in ("artifact:output", "artifact:prediction", "receipt:resource-span"):
        receipts[name]["content_time"] = "2026-07-19T11:50:00Z"
        receipts[name]["recorded_time"] = "2026-07-19T11:50:00Z"
    receipts["receipt:resource-span"]["payload"] = {
        **run_binding,
        "span_id": "span-001",
        "costs": {
            "tokens": 800,
            "tool_calls": 1,
            "latency_ms": 4800000,
            "external_spend_microunits": 0,
        },
    }
    receipts["receipt:resource-run"].update(
        {
            "content_time": "2026-07-19T13:00:00Z",
            "recorded_time": "2026-07-19T13:00:00Z",
            "payload": {
                **run_binding,
                "trajectory_id": "trajectory-001",
                "costs": {
                    "tokens": 800,
                    "tool_calls": 1,
                    "latency_ms": 10800000,
                    "external_spend_microunits": 0,
                },
                "latency_aggregation": "trajectory_wall_clock",
            },
        }
    )
    receipts["receipt:run-attestation"].update(
        {
            "actor_type": "trajectory_recorder",
            "content_time": "2026-07-19T13:00:00Z",
            "recorded_time": "2026-07-19T13:00:00Z",
            "payload": {
                **run_binding,
                "trajectory_body_fingerprint": trajectory_body_fingerprint(record),
            },
        }
    )
    return record, ValidationContext(receipts=receipts, action_risk_map=_authority_catalog())


def test_valid_project_lane_and_cabinet_scopes_pass():
    for kind in ("project", "lane", "cabinet"):
        record, context = valid_fixture(kind)
        assert structural_issues(record) == ()
        assert validate_trajectory(record, context) == ()


@pytest.mark.parametrize(
    "mutation",
    (
        lambda r: r["authority_scope"].pop("cabinet_id"),
        lambda r: r["authority_scope"].pop("lane_id"),
        lambda r: r["authority_scope"].update({"scope_kind": "cabinet"}),
        lambda r: r.update({"graduation_credit": True}),
        lambda r: r.update({"eligibility_evidence": {}}),
        lambda r: r["effects"][0].pop("effect_receipt_ref"),
        lambda r: r["intent"].update({"constraints": ["hidden holdout text"]}),
    ),
)
def test_structural_mutants_fail(mutation):
    record, _ = valid_fixture()
    mutation(record)
    assert structural_issues(record)


@pytest.mark.skipif(REFERENCE is None, reason="reference jsonschema not installed")
def test_stdlib_schema_interpreter_agrees_with_reference_engine():
    records = [valid_fixture(kind)[0] for kind in ("project", "lane", "cabinet")]
    for mutation in (
        lambda r: r["authority_scope"].pop("cabinet_id"),
        lambda r: r.update({"promotion_eligible": True}),
        lambda r: r["machine_outcomes"][0].update({"judge_score": 1.0}),
        lambda r: r["spans"][0].update({"confidence_ppm": 2000000}),
        lambda r: r["spans"][0].update({"status": "failed"}),
        lambda r: (r["spans"][0].update({"status": "completed", "output_refs": []}), r["spans"][0].pop("prediction_ref")),
        lambda r: r["spans"][0].update({"kind": "tool", "tool_refs": []}),
    ):
        record, _ = valid_fixture()
        mutation(record)
        records.append(record)
    for record in records:
        assert bool(structural_issues(record)) is bool(list(REFERENCE.iter_errors(record)))


def test_truth_channels_require_external_receipts_and_cannot_be_relabeled():
    record, context = valid_fixture()
    assert "verification.context_required" in {
        issue.code for issue in validate_trajectory(record, None)
    }

    relabeled = dict(context.receipts)
    relabeled["receipt:machine"] = {
        **relabeled["receipt:machine"],
        "kind": "judge_observation",
    }
    bad_context = ValidationContext(relabeled, context.action_risk_map)
    assert "receipt.kind_mismatch" in {
        issue.code for issue in semantic_issues(record, bad_context)
    }

    fake = copy.deepcopy(record)
    fake["machine_outcomes"][0]["receipt_ref"] = _ref("receipt:fabricated")
    assert "receipt.unresolved" in {
        issue.code for issue in semantic_issues(fake, context)
    }


def test_captain_verdict_requires_resolved_captain_attestation():
    record, context = valid_fixture()
    record["machine_outcomes"] = []
    record["evaluation_basis"] = "human_judgment"
    record["human_verdicts"] = [
        {
            "verdict_id": "verdict-001",
            "verdict": "approve",
            "observed_at": "2026-07-19T12:30:00Z",
            "attestation_ref": _ref("receipt:captain"),
        }
    ]
    assert structural_issues(record) == ()
    assert "receipt.unresolved" in {issue.code for issue in semantic_issues(record, context)}

    receipts = dict(context.receipts)
    receipts["receipt:captain"] = _receipt(
        "receipt:captain",
        "captain_attestation",
        subject_id="verdict-001",
        actor_type="captain",
        content_time="2026-07-19T12:30:00Z",
        recorded_time="2026-07-19T12:31:00Z",
        payload={
            "trajectory_id": record["trajectory_id"],
            "run_id": record["execution_scope"]["run_id"],
            "candidate_id": record["genome"]["candidate_id"],
            "verdict_id": "verdict-001",
            "verdict": "approve",
            "observed_at": "2026-07-19T12:30:00Z",
        },
    )
    _refresh_run_attestation(record, receipts)
    verified = ValidationContext(receipts, context.action_risk_map)
    assert semantic_issues(record, verified) == ()

    receipts["receipt:captain"] = {**receipts["receipt:captain"], "actor_type": "judge"}
    assert "receipt.actor_mismatch" in {
        issue.code for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }


def test_unknown_and_abstain_do_not_satisfy_mixed_evaluation():
    record, context = valid_fixture()
    record["evaluation_basis"] = "mixed"
    record["machine_outcomes"][0]["status"] = "unknown"
    receipts = dict(context.receipts)
    receipts["receipt:machine"] = {**receipts["receipt:machine"], "payload": {}}
    record["human_verdicts"] = [
        {
            "verdict_id": "verdict-001",
            "verdict": "abstain",
            "observed_at": "2026-07-19T12:30:00Z",
            "attestation_ref": _ref("receipt:captain"),
        }
    ]
    receipts["receipt:captain"] = _receipt(
        "receipt:captain",
        "captain_attestation",
        subject_id="verdict-001",
        actor_type="captain",
        content_time="2026-07-19T12:30:00Z",
        recorded_time="2026-07-19T12:31:00Z",
        payload={
            "trajectory_id": record["trajectory_id"],
            "run_id": record["execution_scope"]["run_id"],
            "candidate_id": record["genome"]["candidate_id"],
            "verdict_id": "verdict-001",
            "verdict": "abstain",
            "observed_at": "2026-07-19T12:30:00Z",
        },
    )
    _refresh_run_attestation(record, receipts)
    codes = {
        issue.code
        for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }
    assert {"evaluation.machine_evidence_required", "evaluation.human_evidence_required"} <= codes


def test_authority_catalog_and_effect_receipts_are_not_a_second_enum():
    record, context = valid_fixture()
    record["effects"][0]["action_type"] = "invented_action"
    assert "authority.unknown_action_type" in {
        issue.code for issue in semantic_issues(record, context)
    }

    record, context = valid_fixture()
    receipts = dict(context.receipts)
    receipts["receipt:classification"] = {
        **receipts["receipt:classification"],
        "payload": {"action_type": "local_edit", "risk_class": "deploy_prod"},
    }
    assert "authority.classification_mismatch" in {
        issue.code
        for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }


def test_cutoff_fences_inputs_and_old_corrections_cannot_mint_candidate_credit():
    record, context = valid_fixture()
    receipts = dict(context.receipts)
    receipts["artifact:snapshot"] = {
        **receipts["artifact:snapshot"],
        "content_time": "2026-07-19T12:01:00Z",
    }
    assert "receipt.post_cutoff_content" in {
        issue.code
        for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }

    receipts = dict(context.receipts)
    record["machine_outcomes"][0]["causal_basis"] = "correction"
    _refresh_run_attestation(record, receipts)
    receipts["receipt:machine"] = {
        **receipts["receipt:machine"],
        "content_time": "2026-07-19T11:59:00Z",
        "recorded_time": "2026-07-19T12:21:00Z",
        "payload": {
            **receipts["receipt:machine"]["payload"],
            "causal_basis": "correction",
        },
    }
    codes = {
        issue.code
        for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }
    assert codes == {"evaluation.machine_evidence_required"}

    receipts["artifact:snapshot"] = {**receipts["artifact:snapshot"], "content_time": None}
    assert "receipt.content_time_unknown" in {
        issue.code
        for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }


def test_cross_cabinet_receipt_fails_closed():
    record, context = valid_fixture()
    receipts = dict(context.receipts)
    receipts["artifact:objective"] = {**receipts["artifact:objective"], "cabinet_id": "cabinet-b"}
    assert "receipt.cross_cabinet" in {
        issue.code
        for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }


def test_lineage_and_machine_receipts_reject_proxy_rebinding():
    record, context = valid_fixture()

    different_metric = _ref("artifact:metric-2")
    receipts = dict(context.receipts)
    receipts[different_metric["ref"]] = _receipt(
        different_metric["ref"], "metric", subject_id="metric-002"
    )
    rebound_metric = copy.deepcopy(record)
    rebound_metric["machine_outcomes"][0]["metric_ref"] = different_metric
    codes = {
        issue.code
        for issue in semantic_issues(
            rebound_metric,
            ValidationContext(receipts, context.action_risk_map),
        )
    }
    assert "machine_outcome.receipt_mismatch" in codes

    rebound_candidate = copy.deepcopy(record)
    rebound_candidate["genome"]["candidate_id"] = "candidate-002"
    codes = {issue.code for issue in semantic_issues(rebound_candidate, context)}
    assert "genome.manifest_mismatch" in codes

    rebound_run = copy.deepcopy(record)
    rebound_run["execution_scope"]["run_id"] = "run-002"
    codes = {issue.code for issue in semantic_issues(rebound_run, context)}
    assert {
        "genome.manifest_mismatch",
        "machine_outcome.receipt_mismatch",
        "effect.outcome_binding_mismatch",
    } <= codes


@pytest.mark.parametrize(
    "mutation",
    (
        lambda r: r.update({"record_kind": "public_benchmark"}),
        lambda r: r["authority_scope"].update({"project_id": "project-002"}),
        lambda r: r.update({"decision_cutoff_at": "2026-07-19T11:59:59Z"}),
        lambda r: r["intent"]["objective_refs"].__setitem__(0, _ref("artifact:objective-2")),
        lambda r: r["spans"][0]["model_refs"].__setitem__(0, _ref("artifact:model-2")),
    ),
)
def test_run_attestation_binds_every_admission_claim(mutation):
    record, context = valid_fixture()
    receipts = dict(context.receipts)
    receipts["artifact:objective-2"] = _receipt(
        "artifact:objective-2", "objective", subject_id="objective-002"
    )
    receipts["artifact:model-2"] = _receipt(
        "artifact:model-2", "model", subject_id="model-002"
    )
    mutation(record)

    assert "trajectory.run_attestation_mismatch" in {
        issue.code
        for issue in semantic_issues(
            record,
            ValidationContext(receipts, context.action_risk_map),
        )
    }


def test_duplicate_ids_receipts_foreign_lineage_and_causation_fail():
    for collection in ("spans", "effects", "machine_outcomes"):
        record, context = valid_fixture()
        record[collection].append(copy.deepcopy(record[collection][0]))
        receipts = dict(context.receipts)
        _refresh_run_attestation(record, receipts)
        codes = {
            issue.code
            for issue in semantic_issues(
                record,
                ValidationContext(receipts, context.action_risk_map),
            )
        }
        assert "identity.duplicate" in codes
        assert "receipt.duplicate_use" in codes

    record, context = valid_fixture()
    foreign_component = _ref("artifact:foreign-component")
    receipts = dict(context.receipts)
    receipts[foreign_component["ref"]] = _receipt(
        foreign_component["ref"],
        "genome_component",
        subject_id=record["genome"]["candidate_id"],
    )
    record["spans"][0]["genome_component_refs"] = [foreign_component]
    _refresh_run_attestation(record, receipts)
    assert "span.foreign_genome_component" in {
        issue.code
        for issue in semantic_issues(
            record,
            ValidationContext(receipts, context.action_risk_map),
        )
    }

    record, context = valid_fixture()
    undeclared = _ref("artifact:undeclared-snapshot")
    receipts = dict(context.receipts)
    receipts[undeclared["ref"]] = _receipt(
        undeclared["ref"], "input_snapshot", subject_id="snapshot-002"
    )
    record["spans"][0]["input_refs"] = [undeclared]
    _refresh_run_attestation(record, receipts)
    assert "span.undeclared_input" in {
        issue.code
        for issue in semantic_issues(
            record,
            ValidationContext(receipts, context.action_risk_map),
        )
    }

    record, context = valid_fixture()
    record["spans"][0]["causation_id"] = "unrelated-cause"
    receipts = dict(context.receipts)
    _refresh_run_attestation(record, receipts)
    assert "span.causation_mismatch" in {
        issue.code
        for issue in semantic_issues(
            record,
            ValidationContext(receipts, context.action_risk_map),
        )
    }


def test_human_and_judge_ids_and_receipts_are_one_to_one():
    record, context = valid_fixture()
    receipts = dict(context.receipts)
    verdict = {
        "verdict_id": "verdict-001",
        "verdict": "approve",
        "observed_at": "2026-07-19T12:30:00Z",
        "attestation_ref": _ref("receipt:captain"),
    }
    receipts["receipt:captain"] = _receipt(
        "receipt:captain",
        "captain_attestation",
        subject_id="verdict-001",
        actor_type="captain",
        content_time=verdict["observed_at"],
        recorded_time="2026-07-19T12:31:00Z",
        payload={
            "trajectory_id": record["trajectory_id"],
            "run_id": record["execution_scope"]["run_id"],
            "candidate_id": record["genome"]["candidate_id"],
            **{key: verdict[key] for key in ("verdict_id", "verdict", "observed_at")},
        },
    )
    record["human_verdicts"] = [verdict, copy.deepcopy(verdict)]

    observation = {
        "observation_id": "observation-001",
        "observed_at": "2026-07-19T12:40:00Z",
        "verdict_ref": _ref("receipt:judge-verdict"),
        "receipt_ref": _ref("receipt:judge-observation"),
    }
    common_payload = {
        "trajectory_id": record["trajectory_id"],
        "run_id": record["execution_scope"]["run_id"],
        "candidate_id": record["genome"]["candidate_id"],
        "observation_id": observation["observation_id"],
        "observed_at": observation["observed_at"],
    }
    receipts["receipt:judge-verdict"] = _receipt(
        "receipt:judge-verdict",
        "judge_verdict",
        subject_id=observation["observation_id"],
        content_time=observation["observed_at"],
        recorded_time="2026-07-19T12:41:00Z",
        payload=common_payload,
    )
    receipts["receipt:judge-observation"] = _receipt(
        "receipt:judge-observation",
        "judge_observation",
        subject_id=observation["observation_id"],
        content_time=observation["observed_at"],
        recorded_time="2026-07-19T12:41:00Z",
        payload={**common_payload, "verdict_ref": observation["verdict_ref"]},
    )
    record["judge_observations"] = [observation, copy.deepcopy(observation)]
    receipts["receipt:run-attestation"]["payload"] = {
        "trajectory_id": record["trajectory_id"],
        "run_id": record["execution_scope"]["run_id"],
        "candidate_id": record["genome"]["candidate_id"],
        "trajectory_body_fingerprint": trajectory_body_fingerprint(record),
    }

    codes = {
        issue.code
        for issue in semantic_issues(
            record,
            ValidationContext(receipts, context.action_risk_map),
        )
    }
    assert {"identity.duplicate", "receipt.duplicate_use"} <= codes


@pytest.mark.parametrize(
    ("receipt_name", "changes", "expected"),
    (
        (
            "artifact:output",
            {"content_time": "2026-07-19T09:59:00Z", "recorded_time": "2026-07-19T09:59:00Z"},
            "receipt.content_time_mismatch",
        ),
        (
            "receipt:machine",
            {"content_time": "2026-07-19T12:20:00Z", "recorded_time": "2026-07-19T12:19:00Z"},
            "receipt.invalid_time_order",
        ),
        (
            "receipt:machine",
            {"content_time": "2026-07-19T12:18:00Z", "recorded_time": "2026-07-19T12:19:00Z"},
            "receipt.recorded_before_claim",
        ),
        (
            "receipt:classification",
            {"content_time": "2026-07-19T12:01:00Z", "recorded_time": "2026-07-19T12:02:00Z"},
            "receipt.recorded_after_deadline",
        ),
    ),
)
def test_receipt_chronology_fails_closed(receipt_name, changes, expected):
    record, context = valid_fixture()
    receipts = dict(context.receipts)
    receipts[receipt_name] = {**receipts[receipt_name], **changes}
    assert expected in {
        issue.code
        for issue in semantic_issues(
            record,
            ValidationContext(receipts, context.action_risk_map),
        )
    }


def test_costs_are_metered_additive_and_not_candidate_truth():
    record, context = valid_fixture()
    record["spans"][0]["costs"]["tokens"] = 0
    record["spans"][0]["costs"]["tool_calls"] = 0
    record["costs"]["tokens"] = 0
    record["costs"]["tool_calls"] = 0
    receipts = dict(context.receipts)
    _refresh_run_attestation(record, receipts)

    assert "cost.resource_receipt_mismatch" in {
        issue.code
        for issue in semantic_issues(
            record,
            ValidationContext(receipts, context.action_risk_map),
        )
    }

    record, context = valid_fixture()
    record["costs"]["tokens"] += 1
    receipts = dict(context.receipts)
    _refresh_run_attestation(record, receipts)
    assert "cost.additive_mismatch" in {
        issue.code
        for issue in semantic_issues(
            record,
            ValidationContext(receipts, context.action_risk_map),
        )
    }


def test_trajectory_classification_cannot_downgrade_receipts():
    record, context = valid_fixture()
    record["classification"] = "public"
    assert "receipt.classification_downgrade" in {
        issue.code for issue in semantic_issues(record, context)
    }


def test_holdout_receipt_is_aggregate_only_and_restricted():
    receipt = {
        "schema_version": "holdout-evaluation-receipt/v1",
        "cabinet_id": "cabinet-a",
        "candidate_fingerprint": "sha256:" + "a" * 64,
        "trajectory_fingerprint": "sha256:" + "b" * 64,
        "suite_version": "suite-v1",
        "suite_digest": "sha256:" + "c" * 64,
        "aggregate_verdict": "pass",
        "threshold_vector": {
            "threshold:safety": True,
            "threshold:generalization": True,
        },
        "evaluated_at": "2026-07-19T13:00:00Z",
        "attested_artifact_ref": _ref("receipt:holdout"),
        "classification": "restricted",
    }
    oracle_receipt = _receipt(
        "receipt:holdout",
        "holdout_oracle_attestation",
        subject_id=receipt["trajectory_fingerprint"],
        actor_type="holdout_oracle",
        content_time="2026-07-19T13:00:00Z",
        recorded_time="2026-07-19T13:01:00Z",
        payload={
            "holdout_receipt_fingerprint": holdout_receipt_payload_fingerprint(receipt)
        },
    )
    oracle_receipt["classification"] = "restricted"
    context = ValidationContext(
        receipts={"receipt:holdout": oracle_receipt},
        action_risk_map={},
        holdout_thresholds={
            receipt["suite_digest"]: frozenset(receipt["threshold_vector"])
        },
    )
    assert validate_holdout_receipt(receipt, context) == ()
    for forbidden in ("cases", "case_fingerprints", "per_case_scores", "outputs"):
        leaked = {**receipt, forbidden: ["secret"]}
        assert holdout_receipt_structural_issues(leaked)
    assert validate_holdout_receipt({**receipt, "evaluated_at": "not-a-date"}, context)
    assert validate_holdout_receipt({**receipt, "threshold_vector": {}}, context)
    assert validate_holdout_receipt(
        {**receipt, "threshold_vector": {"threshold:safety": False}}, context
    )
    assert validate_holdout_receipt(receipt, None)

    replayed = {
        **receipt,
        "candidate_fingerprint": "sha256:" + "d" * 64,
        "suite_digest": "sha256:" + "e" * 64,
        "aggregate_verdict": "fail",
        "threshold_vector": {"threshold:safety": False},
        "evaluated_at": "2026-07-19T13:02:00Z",
    }
    assert "holdout.attestation_payload_mismatch" in {
        issue.code for issue in validate_holdout_receipt(replayed, context)
    }


@pytest.mark.skipif(HOLDOUT_REFERENCE is None, reason="reference jsonschema not installed")
def test_holdout_schema_interpreter_matches_reference_and_blocks_key_leaks():
    record = {
        "schema_version": "holdout-evaluation-receipt/v1",
        "cabinet_id": "cabinet-a",
        "candidate_fingerprint": "sha256:" + "a" * 64,
        "trajectory_fingerprint": "sha256:" + "b" * 64,
        "suite_version": "suite-v1",
        "suite_digest": "sha256:" + "c" * 64,
        "aggregate_verdict": "pass",
        "threshold_vector": {"threshold:safety": True},
        "evaluated_at": "2026-07-19T13:00:00Z",
        "attested_artifact_ref": _ref("receipt:holdout"),
        "classification": "restricted",
    }
    mutants = [
        record,
        {**record, "threshold_vector": {"SECRET_CASE_prompt_password_abc": True}},
        {**record, "threshold_vector": {}},
        {**record, "evaluated_at": "2026-07-19T13Z"},
        {**record, "unexpected": True},
    ]
    for mutant in mutants:
        assert bool(holdout_receipt_structural_issues(mutant)) is bool(
            list(HOLDOUT_REFERENCE.iter_errors(mutant))
        )
    assert holdout_receipt_structural_issues(mutants[1])


@pytest.mark.parametrize(
    ("evaluated_at", "oracle_content", "oracle_recorded"),
    (
        ("2099-01-01T00:00:00Z", "2026-07-19T13:00:00Z", "2026-07-19T13:01:00Z"),
        ("2025-01-01T00:00:00Z", "2026-07-19T13:00:00Z", "2026-07-19T13:01:00Z"),
    ),
)
def test_holdout_time_registry_and_sentinel_identity_fail_closed(
    evaluated_at,
    oracle_content,
    oracle_recorded,
):
    record = {
        "schema_version": "holdout-evaluation-receipt/v1",
        "cabinet_id": "cabinet-a",
        "candidate_fingerprint": "sha256:" + "a" * 64,
        "trajectory_fingerprint": "sha256:" + "b" * 64,
        "suite_version": "suite-v1",
        "suite_digest": "sha256:" + "c" * 64,
        "aggregate_verdict": "pass",
        "threshold_vector": {"threshold:safety": True},
        "evaluated_at": evaluated_at,
        "attested_artifact_ref": _ref("receipt:holdout"),
        "classification": "restricted",
    }
    oracle = _receipt(
        "receipt:holdout",
        "holdout_oracle_attestation",
        subject_id=record["trajectory_fingerprint"],
        actor_type="holdout_oracle",
        content_time=oracle_content,
        recorded_time=oracle_recorded,
        payload={"holdout_receipt_fingerprint": holdout_receipt_payload_fingerprint(record)},
    )
    oracle["classification"] = "restricted"
    context = ValidationContext(
        {"receipt:holdout": oracle},
        {},
        {record["suite_digest"]: frozenset(record["threshold_vector"])},
    )
    assert "holdout.attestation_time_order" in {
        issue.code for issue in validate_holdout_receipt(record, context)
    }

    sentinel = {**record, "cabinet_id": "unknown"}
    oracle = {**oracle, "cabinet_id": "unknown"}
    oracle["payload"] = {
        "holdout_receipt_fingerprint": holdout_receipt_payload_fingerprint(sentinel)
    }
    assert "identity.sentinel" in {
        issue.code
        for issue in validate_holdout_receipt(
            sentinel,
            ValidationContext(
                {"receipt:holdout": oracle},
                {},
                {record["suite_digest"]: frozenset(record["threshold_vector"])},
            ),
        )
    }


def test_set_order_is_canonical_duplicates_fail_and_span_order_is_semantic():
    record, context = valid_fixture()
    second = _ref("artifact:constraint-2")
    record["intent"]["constraint_refs"].append(second)
    receipts = dict(context.receipts)
    receipts[second["ref"]] = _receipt(
        second["ref"], "constraint", subject_id="constraint-002", actor_type="authority"
    )
    receipts[second["ref"]]["payload"] = {
        "constraint_ref": second,
        "authority_scope": copy.deepcopy(record["authority_scope"]),
    }
    _refresh_run_attestation(record, receipts)
    context = ValidationContext(receipts, context.action_risk_map)
    first = canonical_fingerprint(record, context)

    reordered = copy.deepcopy(record)
    reordered["intent"]["constraint_refs"].reverse()
    assert canonical_fingerprint(reordered, context) == first

    duplicate = copy.deepcopy(record)
    duplicate["intent"]["constraint_refs"].append(copy.deepcopy(second))
    assert "collection.duplicate" in {
        issue.code for issue in semantic_issues(duplicate, context)
    }

    changed = copy.deepcopy(record)
    changed["spans"][0]["confidence_ppm"] = 600000
    changed_receipts = dict(context.receipts)
    _refresh_run_attestation(changed, changed_receipts)
    assert canonical_fingerprint(
        changed,
        ValidationContext(changed_receipts, context.action_risk_map),
    ) != first


def test_integral_json_numbers_canonicalize_and_timestamp_spellings_are_closed():
    record, context = valid_fixture()
    baseline = canonical_fingerprint(record, context)

    equivalent = copy.deepcopy(record)
    equivalent["spans"][0]["costs"]["latency_ms"] = 4800000.0
    equivalent["costs"]["external_spend_microunits"] = -0.0
    assert structural_issues(equivalent) == ()
    assert canonical_fingerprint(equivalent, context) == baseline

    noncanonical_time = copy.deepcopy(record)
    noncanonical_time["started_at"] = "2026-07-19T10Z"
    assert structural_issues(noncanonical_time)


def test_intent_requires_a_resolved_captain_root_and_authority_constraint():
    record, context = valid_fixture()
    receipts = dict(context.receipts)
    receipts["artifact:objective"] = {
        **receipts["artifact:objective"],
        "actor_type": "candidate_agent",
    }
    assert "intent.objective_authority_required" in {
        issue.code for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }

    receipts = dict(context.receipts)
    receipts["receipt:captain-direction"] = {
        **receipts["receipt:captain-direction"],
        "actor_type": "system",
    }
    assert "receipt.actor_mismatch" in {
        issue.code for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }

    receipts = dict(context.receipts)
    receipts["artifact:constraint"] = {
        **receipts["artifact:constraint"],
        "actor_type": "candidate_agent",
    }
    assert "intent.constraint_authority_required" in {
        issue.code for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }


def test_stable_authority_scope_inherits_and_survives_new_runs():
    record, context = valid_fixture("project")
    receipts = copy.deepcopy(context.receipts)
    cabinet_scope = {"cabinet_id": "cabinet-a", "scope_kind": "cabinet"}
    for name in ("artifact:objective", "receipt:captain-direction", "artifact:constraint"):
        receipts[name]["payload"]["authority_scope"] = cabinet_scope
    assert validate_trajectory(record, ValidationContext(receipts, context.action_risk_map)) == ()

    record["execution_scope"]["run_id"] = "run-002"
    for receipt in receipts.values():
        payload = receipt.get("payload")
        if isinstance(payload, dict) and "run_id" in payload:
            payload["run_id"] = "run-002"
    _refresh_run_attestation(record, receipts)
    assert validate_trajectory(record, ValidationContext(receipts, context.action_risk_map)) == ()

    record, context = valid_fixture("project")
    receipts = copy.deepcopy(context.receipts)
    lane_scope = {
        "cabinet_id": "cabinet-a",
        "scope_kind": "lane",
        "lane_id": "operations",
    }
    receipts["receipt:captain-direction"]["payload"]["authority_scope"] = lane_scope
    receipts["artifact:constraint"]["payload"]["authority_scope"] = lane_scope
    assert validate_trajectory(record, ValidationContext(receipts, context.action_risk_map)) == ()


@pytest.mark.parametrize(
    "bad_scope",
    (
        {"cabinet_id": "cabinet-a", "scope_kind": "lane", "lane_id": "sibling"},
        {"cabinet_id": "cabinet-b", "scope_kind": "cabinet"},
        {"cabinet_id": "unknown", "scope_kind": "cabinet"},
    ),
)
def test_authority_scope_rejects_siblings_cross_cabinet_and_sentinels(bad_scope):
    record, context = valid_fixture("project")
    receipts = copy.deepcopy(context.receipts)
    receipts["receipt:captain-direction"]["payload"]["authority_scope"] = bad_scope
    assert {"intent.authority_scope_mismatch", "intent.authority_scope_invalid"} & {
        issue.code for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }

    lane_record, lane_context = valid_fixture("lane")
    receipts = copy.deepcopy(lane_context.receipts)
    receipts["receipt:captain-direction"]["payload"]["authority_scope"] = {
        "cabinet_id": "cabinet-a",
        "scope_kind": "project",
        "lane_id": "operations",
        "project_id": "project-001",
    }
    assert "intent.authority_scope_mismatch" in {
        issue.code
        for issue in semantic_issues(
            lane_record,
            ValidationContext(receipts, lane_context.action_risk_map),
        )
    }


def test_effect_requires_authority_decision_and_preserves_denial_observations():
    record, context = valid_fixture()
    receipts = dict(context.receipts)
    receipts.pop("receipt:authorization")
    assert "receipt.unresolved" in {
        issue.code for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }

    denied, context = valid_fixture()
    denied["effects"][0]["status"] = "denied"
    denied["effects"][0].pop("attempted_at")
    receipts = dict(context.receipts)
    receipts["receipt:authorization"]["payload"] = {
        **receipts["receipt:authorization"]["payload"],
        "decision": "denied",
    }
    receipts["receipt:effect"]["payload"] = {
        **receipts["receipt:effect"]["payload"],
        "decision": "denied",
        "status": "denied",
    }
    _refresh_run_attestation(denied, receipts)
    assert validate_trajectory(denied, ValidationContext(receipts, context.action_risk_map)) == ()

    violation = copy.deepcopy(denied)
    violation["effects"][0]["status"] = "violation"
    violation["effects"][0]["attempted_at"] = "2026-07-19T12:01:00Z"
    violation_receipts = copy.deepcopy(receipts)
    violation_receipts["receipt:effect"]["payload"]["status"] = "violation"
    _refresh_run_attestation(violation, violation_receipts)
    assert validate_trajectory(
        violation,
        ValidationContext(violation_receipts, context.action_risk_map),
    ) == ()


def test_machine_credit_requires_linked_fresh_intervention():
    record, context = valid_fixture()
    record["machine_outcomes"][0]["causal_ref"] = _ref("artifact:unknown-output")
    receipts = dict(context.receipts)
    _refresh_run_attestation(record, receipts)
    assert "machine_outcome.unlinked_cause" in {
        issue.code for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }

    record, context = valid_fixture()
    receipts = dict(context.receipts)
    for name in ("artifact:value", "receipt:machine"):
        receipts[name] = {
            **receipts[name],
            "content_time": "2000-01-01T00:00:00Z",
        }
    assert "receipt.content_time_mismatch" in {
        issue.code for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }

    pure_cognitive, context = valid_fixture()
    pure_cognitive["effects"] = []
    pure_cognitive["machine_outcomes"][0]["causal_ref"] = _ref("artifact:output")
    pure_cognitive["machine_outcomes"][0]["measurement_started_at"] = "2026-07-19T12:00:00Z"
    receipts = dict(context.receipts)
    receipts["receipt:machine"] = {
        **receipts["receipt:machine"],
        "payload": {
            **receipts["receipt:machine"]["payload"],
            "causal_ref": _ref("artifact:output"),
            "measurement_started_at": "2026-07-19T12:00:00Z",
        },
    }
    _refresh_run_attestation(pure_cognitive, receipts)
    assert validate_trajectory(
        pure_cognitive,
        ValidationContext(receipts, context.action_risk_map),
    ) == ()


def test_snapshot_identity_and_span_provenance_fail_closed():
    record, context = valid_fixture()
    second = _ref("artifact:snapshot-2")
    record["input_snapshots"].append(
        {
            "snapshot_id": "snapshot-001",
            "artifact_ref": second,
            "maximum_content_time": "2026-07-19T11:30:00Z",
        }
    )
    receipts = dict(context.receipts)
    receipts[second["ref"]] = _receipt(
        second["ref"], "input_snapshot", subject_id="snapshot-001"
    )
    receipts[second["ref"]]["payload"] = {
        "snapshot_id": "snapshot-001",
        "artifact_ref": second,
        "maximum_content_time": "2026-07-19T11:30:00Z",
        "authority_scope": copy.deepcopy(record["authority_scope"]),
    }
    _refresh_run_attestation(record, receipts)
    assert "identity.duplicate" in {
        issue.code for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }

    record, context = valid_fixture()
    record["input_snapshots"].append(
        {
            "snapshot_id": "snapshot-002",
            "artifact_ref": _ref("artifact:snapshot"),
            "maximum_content_time": "2026-07-19T11:30:00Z",
        }
    )
    receipts = dict(context.receipts)
    _refresh_run_attestation(record, receipts)
    assert "receipt.duplicate_use" in {
        issue.code for issue in semantic_issues(record, ValidationContext(receipts, context.action_risk_map))
    }

    record, _ = valid_fixture()
    for field in ("genome_component_refs", "input_refs", "output_refs"):
        record["spans"][0][field] = []
    record["spans"][0].pop("prediction_ref")
    assert structural_issues(record)


def test_failed_span_requires_bound_failure_receipt():
    record, context = valid_fixture()
    span = record["spans"][0]
    span["status"] = "failed"
    span["output_refs"] = []
    span.pop("prediction_ref")
    span["failure_receipt_ref"] = _ref("receipt:span-failure")
    receipts = dict(context.receipts)
    receipts["receipt:span-failure"] = _receipt(
        "receipt:span-failure",
        "span_failure",
        subject_id="span-001",
        content_time="2026-07-19T11:50:00Z",
        recorded_time="2026-07-19T11:50:00Z",
        payload={
            "trajectory_id": "trajectory-001",
            "run_id": "run-001",
            "candidate_id": "candidate-001",
            "span_id": "span-001",
            "status": "failed",
        },
    )
    _refresh_run_attestation(record, receipts)
    assert validate_trajectory(record, ValidationContext(receipts, context.action_risk_map)) == ()


@pytest.mark.parametrize("value", (10**400, -(10**400)))
def test_huge_integers_return_bounded_issues_without_throwing(value):
    record, context = valid_fixture()
    record["costs"]["tokens"] = value
    issues = validate_trajectory(record, context)
    assert {issue.code for issue in issues} == {"envelope.integer_range"}


def test_oversized_and_cyclic_envelopes_return_bounded_issues():
    record, context = valid_fixture()
    record["trajectory_id"] = "x" * 5000
    assert {issue.code for issue in validate_trajectory(record, context)} == {
        "envelope.string_budget"
    }

    record, context = valid_fixture()
    record["spans"].append(record["spans"])
    assert {issue.code for issue in validate_trajectory(record, context)} == {
        "envelope.alias_or_cycle"
    }
