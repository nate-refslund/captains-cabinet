"""Observation-only trajectory contracts for the future evolution lab.

The candidate-controlled record never authenticates itself and never carries
promotion or fitness state. Structural shape comes from the versioned JSON
schemas. Semantic validation requires a trusted receipt context supplied by
the existing evidence/authority plane; absent context fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
TRAJECTORY_SCHEMA = SCHEMA_DIR / "cognitive-trajectory.schema.json"
HOLDOUT_RECEIPT_SCHEMA = SCHEMA_DIR / "holdout-evaluation-receipt.schema.json"
SENTINEL_IDS = frozenset({"*", "default", "global", "none", "null", "unknown"})
SET_LIKE_KEYS = frozenset(
    {
        "component_refs",
        "objective_refs",
        "constraint_refs",
        "input_snapshots",
        "genome_component_refs",
        "model_refs",
        "tool_refs",
        "skill_refs",
        "context_refs",
        "input_refs",
        "output_refs",
    }
)
CLASSIFICATION_RANK = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
MAX_ENVELOPE_NODES = 10_000
MAX_ENVELOPE_STRING_BYTES = 4_096
MAX_ENVELOPE_TOTAL_STRING_BYTES = 4 * 1024 * 1024
MAX_PORTABLE_INTEGER = 9_007_199_254_740_991


@dataclass(frozen=True, order=True)
class ValidationIssue:
    kind: str
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ValidationContext:
    """Trusted facts supplied outside the candidate-controlled trajectory."""

    receipts: Mapping[str, Mapping[str, Any]]
    action_risk_map: Mapping[str, str]
    holdout_thresholds: Mapping[str, frozenset[str]] = field(default_factory=dict)


class TrajectoryContractError(ValueError):
    def __init__(self, issues: tuple[ValidationIssue, ...]):
        self.issues = issues
        super().__init__("; ".join(f"{issue.code}@{issue.path}" for issue in issues))


def _load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        if isinstance(value, int) and not isinstance(value, bool):
            return True
        return isinstance(value, float) and math.isfinite(value) and value.is_integer()
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _resolve_schema_ref(root: Mapping[str, Any], ref: str) -> Mapping[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"only local JSON Schema refs are supported: {ref}")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    if not isinstance(node, Mapping):
        raise ValueError(f"schema ref is not an object: {ref}")
    return node


def _schema_errors(
    value: Any,
    schema: Mapping[str, Any],
    root: Mapping[str, Any],
    path: str = "$",
) -> list[ValidationIssue]:
    """Interpret the closed Draft-2020-12 subset used by the two v1 schemas."""

    if "$ref" in schema:
        return _schema_errors(value, _resolve_schema_ref(root, schema["$ref"]), root, path)
    issues: list[ValidationIssue] = []

    def add(validator: str, message: str, issue_path: str = path) -> None:
        issues.append(ValidationIssue("structural", f"schema.{validator}", issue_path, message))

    for subschema in schema.get("allOf", []):
        issues.extend(_schema_errors(value, subschema, root, path))
    condition = schema.get("if")
    if isinstance(condition, Mapping):
        branch = "then" if not _schema_errors(value, condition, root, path) else "else"
        selected = schema.get(branch)
        if isinstance(selected, Mapping):
            issues.extend(_schema_errors(value, selected, root, path))
    negated = schema.get("not")
    if isinstance(negated, Mapping) and not _schema_errors(value, negated, root, path):
        add("not", "value matches a forbidden schema")
    alternatives = schema.get("anyOf")
    if isinstance(alternatives, list) and not any(
        not _schema_errors(value, candidate, root, path) for candidate in alternatives
    ):
        add("anyOf", "value matches none of the allowed schemas")
    if "const" in schema and value != schema["const"]:
        add("const", f"value must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        add("enum", f"value is not one of {schema['enum']!r}")

    expected = schema.get("type")
    if expected is not None:
        types = [expected] if isinstance(expected, str) else expected
        if not any(_json_type_matches(value, item) for item in types):
            add("type", f"value is not of type {expected!r}")
            return issues

    if isinstance(value, Mapping):
        if isinstance(schema.get("minProperties"), int) and len(value) < schema["minProperties"]:
            add("minProperties", f"object must contain at least {schema['minProperties']} properties")
        if isinstance(schema.get("maxProperties"), int) and len(value) > schema["maxProperties"]:
            add("maxProperties", f"object must contain no more than {schema['maxProperties']} properties")
        for key in schema.get("required", []):
            if key not in value:
                add("required", f"required property {key!r} is missing")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        property_names = schema.get("propertyNames")
        for key, child in value.items():
            if isinstance(property_names, Mapping):
                issues.extend(_schema_errors(key, property_names, root, f"{path}.{key}"))
            if key in properties:
                issues.extend(_schema_errors(child, properties[key], root, f"{path}.{key}"))
            elif additional is False:
                add("additionalProperties", f"additional property {key!r} is forbidden", f"{path}.{key}")
            elif isinstance(additional, Mapping):
                issues.extend(_schema_errors(child, additional, root, f"{path}.{key}"))

    if isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            add("minItems", f"array must contain at least {schema['minItems']} items")
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            add("maxItems", f"array must contain no more than {schema['maxItems']} items")
        if isinstance(schema.get("items"), Mapping):
            for index, child in enumerate(value):
                issues.extend(_schema_errors(child, schema["items"], root, f"{path}[{index}]"))

    if isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            add("minLength", f"string must contain at least {schema['minLength']} characters")
        if isinstance(schema.get("pattern"), str) and re.search(schema["pattern"], value) is None:
            add("pattern", f"string does not match {schema['pattern']!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            add("minimum", f"number must be at least {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            add("maximum", f"number must be no more than {schema['maximum']}")
    return issues


def _envelope_issues(record: Any) -> tuple[ValidationIssue, ...]:
    """Bound hostile in-memory inputs before recursive schema or JSON work."""

    stack = [(record, "$", 0)]
    containers: set[int] = set()
    nodes = 0
    string_bytes = 0
    while stack:
        node, path, depth = stack.pop()
        nodes += 1
        if nodes > MAX_ENVELOPE_NODES or depth > 32:
            return (ValidationIssue("structural", "envelope.complexity", path, "envelope exceeds bounded complexity"),)
        if isinstance(node, str):
            size = len(node.encode("utf-8"))
            string_bytes += size
            if size > MAX_ENVELOPE_STRING_BYTES or string_bytes > MAX_ENVELOPE_TOTAL_STRING_BYTES:
                return (ValidationIssue("structural", "envelope.string_budget", path, "envelope exceeds bounded string bytes"),)
        elif isinstance(node, int) and not isinstance(node, bool):
            if abs(node) > MAX_PORTABLE_INTEGER:
                return (ValidationIssue("structural", "envelope.integer_range", path, "integer exceeds portable JSON range"),)
        elif isinstance(node, float) and not math.isfinite(node):
            return (ValidationIssue("structural", "envelope.non_finite", path, "non-finite numbers are forbidden"),)
        elif isinstance(node, Mapping):
            identity = id(node)
            if identity in containers:
                return (ValidationIssue("structural", "envelope.alias_or_cycle", path, "envelope must be a JSON tree"),)
            containers.add(identity)
            for key, child in node.items():
                if not isinstance(key, str):
                    return (ValidationIssue("structural", "envelope.key_type", path, "object keys must be strings"),)
                stack.append((key, f"{path}.<key>", depth + 1))
                stack.append((child, f"{path}.{key}", depth + 1))
        elif isinstance(node, list):
            identity = id(node)
            if identity in containers:
                return (ValidationIssue("structural", "envelope.alias_or_cycle", path, "envelope must be a JSON tree"),)
            containers.add(identity)
            stack.extend((child, f"{path}[{index}]", depth + 1) for index, child in enumerate(node))
    return ()


def _structural_issues(record: Any, schema_path: Path) -> tuple[ValidationIssue, ...]:
    bounded = _envelope_issues(record)
    if bounded:
        return bounded
    schema = _load_schema(schema_path)
    return tuple(sorted(set(_schema_errors(record, schema, schema))))


def structural_issues(record: Any) -> tuple[ValidationIssue, ...]:
    return _structural_issues(record, TRAJECTORY_SCHEMA)


def holdout_receipt_structural_issues(record: Any) -> tuple[ValidationIssue, ...]:
    return _structural_issues(record, HOLDOUT_RECEIPT_SCHEMA)


def holdout_receipt_payload_fingerprint(record: Mapping[str, Any]) -> str:
    """Digest every admission-bearing field, excluding only its attestation pointer."""

    payload = {key: value for key, value in record.items() if key != "attested_artifact_ref"}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def trajectory_body_fingerprint(record: Mapping[str, Any]) -> str:
    """Bind every trajectory claim while avoiding the attestation pointer cycle."""

    body = {key: value for key, value in record.items() if key != "run_attestation_ref"}
    encoded = json.dumps(
        _normalize(body),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_holdout_receipt(
    record: Any,
    context: ValidationContext | None = None,
) -> tuple[ValidationIssue, ...]:
    structural = holdout_receipt_structural_issues(record)
    if structural:
        return structural
    issues: list[ValidationIssue] = []

    def add(code: str, path: str, message: str) -> None:
        issues.append(ValidationIssue("semantic", code, path, message))

    evaluated_at = _parse_utc(record["evaluated_at"])
    if evaluated_at is None:
        add("time.not_canonical_utc", "evaluated_at", "holdout receipt time must be canonical UTC Z")
    for field_name in ("cabinet_id", "suite_version"):
        if record[field_name].strip().lower() in SENTINEL_IDS:
            add("identity.sentinel", field_name, "holdout identities cannot be inferred sentinels")
    if record["aggregate_verdict"] == "pass" and not all(record["threshold_vector"].values()):
        add("holdout.aggregate_mismatch", "aggregate_verdict", "pass requires every threshold to pass")
    if record["aggregate_verdict"] == "fail" and all(record["threshold_vector"].values()):
        add("holdout.aggregate_mismatch", "aggregate_verdict", "fail requires at least one failed threshold")
    if context is None:
        add("verification.context_required", "$", "trusted holdout-oracle receipt context is required")
    else:
        expected_thresholds = context.holdout_thresholds.get(record["suite_digest"])
        if expected_thresholds is None:
            add("holdout.threshold_registry_unresolved", "threshold_vector", "suite threshold registry is unresolved")
        elif set(record["threshold_vector"]) != set(expected_thresholds):
            add("holdout.threshold_set_mismatch", "threshold_vector", "threshold ids differ from the trusted suite registry")
        ref = record["attested_artifact_ref"]
        receipt = context.receipts.get(ref["ref"])
        if not isinstance(receipt, Mapping):
            add("receipt.unresolved", "attested_artifact_ref", "oracle attestation is unresolved")
        else:
            expected = {
                "digest": ref["digest"],
                "cabinet_id": record["cabinet_id"],
                "kind": "holdout_oracle_attestation",
                "actor_type": "holdout_oracle",
                "subject_id": record["trajectory_fingerprint"],
                "classification": "restricted",
                "sharing": "local",
            }
            for field, value in expected.items():
                if receipt.get(field) != value:
                    add("holdout.attestation_mismatch", f"attested_artifact_ref.{field}", "oracle attestation binding mismatch")
            expected_payload_fingerprint = holdout_receipt_payload_fingerprint(record)
            if receipt.get("payload", {}).get("holdout_receipt_fingerprint") != expected_payload_fingerprint:
                add(
                    "holdout.attestation_payload_mismatch",
                    "attested_artifact_ref",
                    "oracle attestation does not bind every admission-bearing field",
                )
            content_time = _parse_utc(receipt.get("content_time"))
            recorded_time = _parse_utc(receipt.get("recorded_time"))
            if content_time is None or recorded_time is None:
                add("holdout.attestation_time_unknown", "attested_artifact_ref", "oracle attestation times are required")
            elif evaluated_at and not evaluated_at == content_time <= recorded_time:
                add(
                    "holdout.attestation_time_order",
                    "attested_artifact_ref",
                    "evaluation, oracle content, and recording times are not ordered/bound",
                )
    return tuple(sorted(set(issues)))


def _parse_utc(value: str) -> datetime | None:
    if not isinstance(value, str) or re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
        value,
    ) is None:
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    offset = parsed.utcoffset()
    return parsed if offset is not None and offset.total_seconds() == 0 else None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _walk(value: Any, path: str = "$"):
    yield path, value
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def semantic_issues(
    record: Mapping[str, Any],
    context: ValidationContext | None,
) -> tuple[ValidationIssue, ...]:
    if structural_issues(record):
        return ()
    issues: list[ValidationIssue] = []

    def add(code: str, path: str, message: str) -> None:
        issues.append(ValidationIssue("semantic", code, path, message))

    authority_scope = record["authority_scope"]
    execution_scope = record["execution_scope"]
    cabinet_id = authority_scope["cabinet_id"]
    for path, value in _walk(record):
        if isinstance(value, str) and path.rsplit(".", 1)[-1].endswith("_id"):
            if value.strip().lower() in SENTINEL_IDS:
                add("identity.sentinel", path, "identities cannot be inferred sentinels")

    started = _parse_utc(record["started_at"])
    cutoff = _parse_utc(record["decision_cutoff_at"])
    completed = _parse_utc(record["completed_at"])
    for field, parsed in (
        ("started_at", started),
        ("decision_cutoff_at", cutoff),
        ("completed_at", completed),
    ):
        if parsed is None:
            add("time.not_canonical_utc", field, "timestamp must be canonical UTC Z")
    if started and cutoff and completed and not started <= cutoff <= completed:
        add("time.invalid_order", "$", "started <= decision cutoff <= completed is required")

    if context is None:
        add("verification.context_required", "$", "trusted receipt and authority context is required")

    def verify_ref(
        ref_obj: Mapping[str, str],
        path: str,
        expected_kind: str,
        *,
        subject_id: str | None = None,
        actor_type: str | None = None,
        pre_cutoff: bool = False,
    ) -> Mapping[str, Any] | None:
        if context is None:
            return None
        receipt = context.receipts.get(ref_obj["ref"])
        if not isinstance(receipt, Mapping):
            add("receipt.unresolved", path, "receipt is absent from the trusted resolver")
            return None
        if receipt.get("digest") != ref_obj["digest"]:
            add("receipt.digest_mismatch", path, "resolved digest does not match the record")
        if receipt.get("cabinet_id") != cabinet_id:
            add("receipt.cross_cabinet", path, "receipt belongs to another Cabinet")
        if receipt.get("kind") != expected_kind:
            add("receipt.kind_mismatch", path, f"expected trusted {expected_kind} receipt")
        if subject_id is not None and receipt.get("subject_id") != subject_id:
            add("receipt.subject_mismatch", path, "receipt subject does not bind to the record")
        if actor_type is not None and receipt.get("actor_type") != actor_type:
            add("receipt.actor_mismatch", path, f"receipt requires actor_type={actor_type}")
        if receipt.get("sharing") != "local":
            add("receipt.sharing_mismatch", path, "Phase-0 trajectories accept local receipts only")
        if receipt.get("classification") not in {"public", "internal", "confidential", "restricted"}:
            add("receipt.classification_missing", path, "receipt needs a known classification")
        elif CLASSIFICATION_RANK[record["classification"]] < CLASSIFICATION_RANK[receipt["classification"]]:
            add("receipt.classification_downgrade", path, "trajectory classification is less restrictive than its receipt")
        content_time = _parse_utc(receipt.get("content_time"))
        recorded_time = _parse_utc(receipt.get("recorded_time"))
        if content_time is None:
            add("receipt.content_time_unknown", path, "missing content time is unknown, never pre-cutoff")
        if recorded_time is None:
            add("receipt.recorded_time_unknown", path, "missing recorded time is unknown")
        if content_time and recorded_time and content_time > recorded_time:
            add("receipt.invalid_time_order", path, "receipt content cannot postdate its recording")
        if pre_cutoff and cutoff:
            if content_time and content_time > cutoff:
                add("receipt.post_cutoff_content", path, "post-cutoff content cannot be an input")
            if recorded_time and recorded_time > cutoff:
                add("receipt.post_cutoff_record", path, "late-ingested content cannot be a decision input")
        if completed and recorded_time and recorded_time > completed:
            add("receipt.after_completion", path, "receipt was not available by trajectory completion")
        return receipt

    def require_payload_binding(
        receipt: Mapping[str, Any] | None,
        path: str,
        expected: Mapping[str, Any],
        code: str,
    ) -> bool:
        """Bind record claims to trusted receipt payloads, not merely receipt types."""

        if receipt is None:
            return False
        payload = receipt.get("payload")
        if not isinstance(payload, Mapping):
            add(code, path, "trusted receipt has no binding payload")
            return False
        mismatched = [field for field, value in expected.items() if payload.get(field) != value]
        if mismatched:
            add(code, path, f"trusted receipt does not bind: {', '.join(sorted(mismatched))}")
            return False
        return True

    def require_receipt_window(
        receipt: Mapping[str, Any] | None,
        path: str,
        *,
        content_at: datetime | None = None,
        content_by: datetime | None = None,
        not_before: datetime | None = None,
        recorded_at_or_after: datetime | None = None,
        recorded_by: datetime | None = None,
    ) -> bool:
        if receipt is None:
            return False
        content_time = _parse_utc(receipt.get("content_time"))
        recorded_time = _parse_utc(receipt.get("recorded_time"))
        if content_time is None or recorded_time is None:
            return False
        valid = True
        if content_at is not None and content_time != content_at:
            add("receipt.content_time_mismatch", path, "receipt content time does not bind the claim")
            valid = False
        if content_by is not None and content_time > content_by:
            add("receipt.content_after_claim", path, "receipt content postdates the bound claim")
            valid = False
        if not_before is not None and (content_time < not_before or recorded_time < not_before):
            add("receipt.before_run", path, "run-bound receipt predates the run")
            valid = False
        if recorded_at_or_after is not None and recorded_time < recorded_at_or_after:
            add("receipt.recorded_before_claim", path, "receipt was recorded before the bound claim")
            valid = False
        if recorded_by is not None and recorded_time > recorded_by:
            add("receipt.recorded_after_deadline", path, "receipt was recorded after its required deadline")
            valid = False
        return valid

    def payload_receipt_ref(
        receipt: Mapping[str, Any] | None,
        key: str,
        path: str,
    ) -> Mapping[str, str] | None:
        payload = receipt.get("payload") if receipt is not None else None
        ref = payload.get(key) if isinstance(payload, Mapping) else None
        valid = (
            isinstance(ref, Mapping)
            and set(ref) == {"ref", "digest"}
            and isinstance(ref.get("ref"), str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", ref["ref"]) is not None
            and isinstance(ref.get("digest"), str)
            and re.fullmatch(r"sha256:[0-9a-f]{64}", ref["digest"]) is not None
        )
        if not valid:
            add("receipt.payload_ref_invalid", path, f"trusted receipt requires a valid {key}")
            return None
        return ref

    def payload_authority_scope(
        receipt: Mapping[str, Any] | None,
        path: str,
    ) -> Mapping[str, str] | None:
        payload = receipt.get("payload") if receipt is not None else None
        value = payload.get("authority_scope") if isinstance(payload, Mapping) else None
        if not isinstance(value, Mapping):
            add("intent.authority_scope_invalid", path, "receipt requires a stable authority_scope")
            return None
        kind = value.get("scope_kind")
        expected_keys = {
            "cabinet": {"cabinet_id", "scope_kind"},
            "lane": {"cabinet_id", "scope_kind", "lane_id"},
            "project": {"cabinet_id", "scope_kind", "lane_id", "project_id"},
        }.get(kind)
        if expected_keys is None or set(value) != expected_keys or any(
            not isinstance(value.get(key), str) or not value[key]
            for key in expected_keys
        ) or any(
            key.endswith("_id") and value[key].strip().lower() in SENTINEL_IDS
            for key in expected_keys
        ):
            add("intent.authority_scope_invalid", path, "authority_scope shape is invalid")
            return None
        return value

    def authority_scope_applies(
        source: Mapping[str, str] | None,
        target: Mapping[str, str],
        path: str,
    ) -> bool:
        if source is None:
            return False
        applies = source["cabinet_id"] == target["cabinet_id"]
        if source["scope_kind"] == "lane":
            applies = applies and target["scope_kind"] in {"lane", "project"} and source["lane_id"] == target.get("lane_id")
        elif source["scope_kind"] == "project":
            applies = applies and target["scope_kind"] == "project" and source["lane_id"] == target.get("lane_id") and source["project_id"] == target.get("project_id")
        if not applies:
            add("intent.authority_scope_mismatch", path, "authority scope is not an ancestor of trajectory scope")
        return applies

    genome = record["genome"]
    run_binding = {
        "trajectory_id": record["trajectory_id"],
        "run_id": execution_scope["run_id"],
        "candidate_id": genome["candidate_id"],
    }
    run_attestation = verify_ref(
        record["run_attestation_ref"],
        "run_attestation_ref",
        "trajectory_run_attestation",
        subject_id=record["trajectory_id"],
        actor_type="trajectory_recorder",
    )
    require_payload_binding(
        run_attestation,
        "run_attestation_ref",
        {
            **run_binding,
            "trajectory_body_fingerprint": trajectory_body_fingerprint(record),
        },
        "trajectory.run_attestation_mismatch",
    )
    require_receipt_window(
        run_attestation,
        "run_attestation_ref",
        content_at=completed,
        not_before=started,
        recorded_at_or_after=completed,
        recorded_by=completed,
    )
    manifest = verify_ref(
        genome["manifest_ref"],
        "genome.manifest_ref",
        "genome_manifest",
        subject_id=genome["candidate_id"],
        pre_cutoff=True,
    )
    require_payload_binding(
        manifest,
        "genome.manifest_ref",
        {
            **run_binding,
            "candidate_version": genome["candidate_version"],
            "incumbent_id": genome["incumbent_id"],
            "incumbent_version": genome["incumbent_version"],
            "component_refs": sorted(genome["component_refs"], key=_canonical_json),
        },
        "genome.manifest_mismatch",
    )
    require_receipt_window(
        manifest,
        "genome.manifest_ref",
        not_before=started,
        recorded_by=cutoff,
    )
    for index, ref in enumerate(genome["component_refs"]):
        verify_ref(
            ref,
            f"genome.component_refs[{index}]",
            "genome_component",
            subject_id=genome["candidate_id"],
            pre_cutoff=True,
        )
    for field, kind in (("objective_refs", "objective"), ("constraint_refs", "constraint")):
        for index, ref in enumerate(record["intent"][field]):
            path = f"intent.{field}[{index}]"
            receipt = verify_ref(
                ref,
                path,
                kind,
                pre_cutoff=True,
            )
            if field == "objective_refs" and receipt is not None:
                if receipt.get("actor_type") not in {"captain", "objective_compiler"}:
                    add("intent.objective_authority_required", path, "objective must be Captain-rooted")
                require_payload_binding(
                    receipt,
                    path,
                    {"objective_ref": ref},
                    "intent.objective_binding_mismatch",
                )
                objective_scope = payload_authority_scope(receipt, f"{path}.authority_scope")
                authority_scope_applies(objective_scope, authority_scope, f"{path}.authority_scope")
                root_ref = payload_receipt_ref(receipt, "authority_root_ref", f"{path}.authority_root_ref")
                root_objective_ref = payload_receipt_ref(receipt, "root_objective_ref", f"{path}.root_objective_ref")
                if root_ref is not None and root_objective_ref is not None:
                    root = verify_ref(
                        root_ref,
                        f"{path}.authority_root_ref",
                        "captain_direction_attestation",
                        actor_type="captain",
                        pre_cutoff=True,
                    )
                    require_payload_binding(
                        root,
                        f"{path}.authority_root_ref",
                        {"objective_ref": root_objective_ref},
                        "intent.objective_root_mismatch",
                    )
                    root_scope = payload_authority_scope(root, f"{path}.authority_root_ref.authority_scope")
                    if authority_scope_applies(root_scope, authority_scope, f"{path}.authority_root_ref.authority_scope") and objective_scope is not None:
                        authority_scope_applies(root_scope, objective_scope, f"{path}.authority_root_ref.authority_scope")
            if field == "constraint_refs" and receipt is not None:
                require_payload_binding(
                    receipt,
                    path,
                    {"constraint_ref": ref},
                    "intent.constraint_binding_mismatch",
                )
                constraint_scope = payload_authority_scope(receipt, f"{path}.authority_scope")
                authority_scope_applies(constraint_scope, authority_scope, f"{path}.authority_scope")
            if field == "constraint_refs" and receipt is not None and receipt.get("actor_type") not in {"captain", "authority"}:
                add(
                    "intent.constraint_authority_required",
                    path,
                    "constraints must be attested by the Captain or constitutional authority",
                )

    seen_snapshot_ids: set[str] = set()
    seen_snapshot_refs: set[str] = set()
    for index, snapshot in enumerate(record["input_snapshots"]):
        if snapshot["snapshot_id"] in seen_snapshot_ids:
            add(
                "identity.duplicate",
                f"input_snapshots[{index}].snapshot_id",
                "snapshot ids must be unique",
            )
        seen_snapshot_ids.add(snapshot["snapshot_id"])
        snapshot_ref_key = _canonical_json(snapshot["artifact_ref"])
        if snapshot_ref_key in seen_snapshot_refs:
            add(
                "receipt.duplicate_use",
                f"input_snapshots[{index}].artifact_ref",
                "snapshot artifact receipts are one-to-one",
            )
        seen_snapshot_refs.add(snapshot_ref_key)
        maximum = _parse_utc(snapshot["maximum_content_time"])
        if maximum is None:
            add("time.not_canonical_utc", f"input_snapshots[{index}].maximum_content_time", "timestamp must be canonical UTC Z")
        elif cutoff and maximum > cutoff:
            add("snapshot.maximum_after_cutoff", f"input_snapshots[{index}]", "snapshot maximum exceeds decision cutoff")
        receipt = verify_ref(
            snapshot["artifact_ref"],
            f"input_snapshots[{index}].artifact_ref",
            "input_snapshot",
            subject_id=snapshot["snapshot_id"],
            pre_cutoff=True,
        )
        require_payload_binding(
            receipt,
            f"input_snapshots[{index}].artifact_ref",
            {
                "snapshot_id": snapshot["snapshot_id"],
                "artifact_ref": snapshot["artifact_ref"],
                "maximum_content_time": snapshot["maximum_content_time"],
                "authority_scope": authority_scope,
            },
            "snapshot.binding_mismatch",
        )
        if receipt and maximum:
            content_time = _parse_utc(receipt.get("content_time"))
            if content_time and content_time > maximum:
                add("snapshot.content_after_maximum", f"input_snapshots[{index}]", "receipt exceeds declared snapshot maximum")

    span_ref_kinds = {
        "genome_component_refs": "genome_component",
        "model_refs": "model",
        "tool_refs": "tool",
        "skill_refs": "skill",
        "context_refs": "context",
        "input_refs": "input_snapshot",
        "output_refs": "output",
    }
    declared_genome_refs = {_canonical_json(ref) for ref in genome["component_refs"]}
    declared_input_refs = {
        _canonical_json(snapshot["artifact_ref"]) for snapshot in record["input_snapshots"]
    }
    seen_spans: set[str] = set()
    seen_span_receipts: set[str] = set()
    for index, span in enumerate(record["spans"]):
        span_path = f"spans[{index}]"
        span_started = _parse_utc(span["started_at"])
        span_completed = _parse_utc(span["completed_at"])
        if not span_started or not span_completed:
            add("time.not_canonical_utc", span_path, "span timestamps must be canonical UTC Z")
        elif started and cutoff and not started <= span_started <= span_completed <= cutoff:
            add("time.span_outside_decision_window", span_path, "span must remain inside the decision window")
        if span["span_id"] in seen_spans:
            add("identity.duplicate", f"{span_path}.span_id", "span ids must be unique")
        parent = span.get("parent_span_id")
        if parent and parent not in seen_spans:
            add("span.parent_not_prior", f"{span_path}.parent_span_id", "parent span must precede its child")
        expected_cause = parent or execution_scope.get("causation_id")
        if expected_cause is None or span["causation_id"] != expected_cause:
            add("span.causation_mismatch", f"{span_path}.causation_id", "span causation must bind its parent or the trajectory root cause")
        seen_spans.add(span["span_id"])
        for field, kind in span_ref_kinds.items():
            for ref_index, ref in enumerate(span[field]):
                ref_path = f"{span_path}.{field}[{ref_index}]"
                if field == "genome_component_refs" and _canonical_json(ref) not in declared_genome_refs:
                    add("span.foreign_genome_component", ref_path, "span component is absent from the bound genome manifest")
                if field == "input_refs" and _canonical_json(ref) not in declared_input_refs:
                    add("span.undeclared_input", ref_path, "span input is absent from declared snapshots")
                resolved = verify_ref(
                    ref,
                    ref_path,
                    kind,
                    subject_id=genome["candidate_id"] if field == "genome_component_refs" else None,
                    pre_cutoff=True,
                )
                if field == "output_refs":
                    receipt_key = _canonical_json(ref)
                    if receipt_key in seen_span_receipts:
                        add("receipt.duplicate_use", ref_path, "span output receipts are one-to-one")
                    seen_span_receipts.add(receipt_key)
                    require_payload_binding(
                        resolved,
                        ref_path,
                        {**run_binding, "span_id": span["span_id"], "artifact_ref": ref},
                        "span.output_binding_mismatch",
                    )
                    require_receipt_window(
                        resolved,
                        ref_path,
                        content_at=span_completed,
                        not_before=span_started,
                        recorded_at_or_after=span_completed,
                        recorded_by=cutoff,
                    )
        if "prediction_ref" in span:
            prediction_path = f"{span_path}.prediction_ref"
            prediction = verify_ref(
                span["prediction_ref"],
                prediction_path,
                "prediction",
                pre_cutoff=True,
            )
            prediction_key = _canonical_json(span["prediction_ref"])
            if prediction_key in seen_span_receipts:
                add("receipt.duplicate_use", prediction_path, "span prediction receipts are one-to-one")
            seen_span_receipts.add(prediction_key)
            require_payload_binding(
                prediction,
                prediction_path,
                {
                    **run_binding,
                    "span_id": span["span_id"],
                    "artifact_ref": span["prediction_ref"],
                },
                "span.prediction_binding_mismatch",
            )
            require_receipt_window(
                prediction,
                prediction_path,
                content_at=span_completed,
                not_before=span_started,
                recorded_at_or_after=span_completed,
                recorded_by=cutoff,
            )
        if "failure_receipt_ref" in span:
            failure_path = f"{span_path}.failure_receipt_ref"
            failure = verify_ref(
                span["failure_receipt_ref"],
                failure_path,
                "span_failure",
                subject_id=span["span_id"],
                pre_cutoff=True,
            )
            require_payload_binding(
                failure,
                failure_path,
                {**run_binding, "span_id": span["span_id"], "status": span["status"]},
                "span.failure_binding_mismatch",
            )
            require_receipt_window(
                failure,
                failure_path,
                content_at=span_completed,
                not_before=span_started,
                recorded_at_or_after=span_completed,
                recorded_by=cutoff,
            )
        span_costs = span["costs"]
        resource_path = f"{span_path}.costs.resource_receipt_ref"
        resource = verify_ref(
            span_costs["resource_receipt_ref"],
            resource_path,
            "resource_usage",
            subject_id=span["span_id"],
            pre_cutoff=True,
        )
        resource_key = _canonical_json(span_costs["resource_receipt_ref"])
        if resource_key in seen_span_receipts:
            add("receipt.duplicate_use", resource_path, "resource receipts are one-to-one")
        seen_span_receipts.add(resource_key)
        require_payload_binding(
            resource,
            resource_path,
            {
                **run_binding,
                "span_id": span["span_id"],
                "costs": {key: value for key, value in span_costs.items() if key != "resource_receipt_ref"},
            },
            "cost.resource_receipt_mismatch",
        )
        require_receipt_window(
            resource,
            resource_path,
            content_at=span_completed,
            not_before=span_started,
            recorded_at_or_after=span_completed,
            recorded_by=cutoff,
        )

    seen_effect_ids: set[str] = set()
    seen_effect_receipts: set[str] = set()
    for index, effect in enumerate(record["effects"]):
        effect_path = f"effects[{index}]"
        if effect["effect_id"] in seen_effect_ids:
            add("identity.duplicate", f"{effect_path}.effect_id", "effect ids must be unique")
        seen_effect_ids.add(effect["effect_id"])
        requested = _parse_utc(effect["requested_at"])
        decided = _parse_utc(effect["decision_at"])
        attempted = _parse_utc(effect.get("attempted_at")) if "attempted_at" in effect else None
        observed = _parse_utc(effect["observed_at"])
        if not requested or not decided or not observed or ("attempted_at" in effect and not attempted):
            add("time.not_canonical_utc", effect_path, "effect timestamps must be canonical UTC Z")
        elif started and cutoff and completed and not (
            started <= requested <= decided <= cutoff <= (attempted or observed) <= observed <= completed
        ):
            add("time.observation_outside_window", effect_path, "effect request/decision/attempt/observation window is invalid")
        expected_decision = "denied" if effect["status"] in {"denied", "violation"} else "allowed"
        for field_name in (
            "classification_receipt_ref",
            "authority_decision_ref",
            "effect_receipt_ref",
            "undo_receipt_ref",
        ):
            receipt_key = _canonical_json(effect[field_name])
            if receipt_key in seen_effect_receipts:
                add("receipt.duplicate_use", f"{effect_path}.{field_name}", "effect receipts are one-to-one")
            seen_effect_receipts.add(receipt_key)
        classification = verify_ref(
            effect["classification_receipt_ref"],
            f"{effect_path}.classification_receipt_ref",
            "authority_classification",
            subject_id=effect["effect_id"],
        )
        authority_decision = verify_ref(
            effect["authority_decision_ref"],
            f"{effect_path}.authority_decision_ref",
            "authority_decision",
            subject_id=effect["effect_id"],
            actor_type="authority",
        )
        outcome = verify_ref(
            effect["effect_receipt_ref"],
            f"{effect_path}.effect_receipt_ref",
            "effect_outcome",
            subject_id=effect["effect_id"],
        )
        undo = verify_ref(
            effect["undo_receipt_ref"],
            f"{effect_path}.undo_receipt_ref",
            "undo_contract",
            subject_id=effect["effect_id"],
        )
        if context is not None:
            expected_risk = context.action_risk_map.get(effect["action_type"])
            if expected_risk is None:
                add("authority.unknown_action_type", f"{effect_path}.action_type", "action type is absent from the canonical authority catalog")
            if classification:
                payload = classification.get("payload", {})
                if payload.get("action_type") != effect["action_type"] or payload.get("risk_class") != expected_risk:
                    add("authority.classification_mismatch", effect_path, "classification receipt disagrees with the canonical catalog")
                require_payload_binding(
                    classification,
                    f"{effect_path}.classification_receipt_ref",
                    {
                        **run_binding,
                        "effect_id": effect["effect_id"],
                        "decision_at": effect["decision_at"],
                    },
                    "effect.classification_binding_mismatch",
                )
                require_receipt_window(
                    classification,
                    f"{effect_path}.classification_receipt_ref",
                    not_before=started,
                    recorded_by=decided,
                )
            if authority_decision:
                require_payload_binding(
                    authority_decision,
                    f"{effect_path}.authority_decision_ref",
                    {
                        **run_binding,
                        "effect_id": effect["effect_id"],
                        "action_type": effect["action_type"],
                        "risk_class": expected_risk,
                        "decision": expected_decision,
                        "idempotency_key": effect["idempotency_key"],
                        "requested_at": effect["requested_at"],
                        "decision_at": effect["decision_at"],
                        "classification_receipt_ref": effect["classification_receipt_ref"],
                        "undo_receipt_ref": effect["undo_receipt_ref"],
                    },
                    "effect.authority_decision_mismatch",
                )
                require_receipt_window(
                    authority_decision,
                    f"{effect_path}.authority_decision_ref",
                    content_at=decided,
                    not_before=started,
                    recorded_by=decided,
                )
            if outcome:
                payload = outcome.get("payload", {})
                if payload.get("action_type") != effect["action_type"] or payload.get("status") != effect["status"]:
                    add("effect.receipt_mismatch", effect_path, "effect receipt disagrees with the recorded effect")
                require_payload_binding(
                    outcome,
                    f"{effect_path}.effect_receipt_ref",
                    {
                        **run_binding,
                        "effect_id": effect["effect_id"],
                        "decision": expected_decision,
                        "observed_at": effect["observed_at"],
                    },
                    "effect.outcome_binding_mismatch",
                )
                require_receipt_window(
                    outcome,
                    f"{effect_path}.effect_receipt_ref",
                    content_by=observed,
                    not_before=decided,
                    recorded_at_or_after=observed,
                    recorded_by=completed,
                )
            if undo:
                payload = undo.get("payload", {})
                if payload.get("action_type") != effect["action_type"] or not re.fullmatch(r"none|delete_window\([0-9]+\)|journal:[A-Za-z0-9._:/-]+", str(payload.get("undo_contract", ""))):
                    add("effect.undo_mismatch", effect_path, "undo receipt lacks a valid bound contract")
                require_payload_binding(
                    undo,
                    f"{effect_path}.undo_receipt_ref",
                    {
                        **run_binding,
                        "effect_id": effect["effect_id"],
                        "decision_at": effect["decision_at"],
                    },
                    "effect.undo_binding_mismatch",
                )
                require_receipt_window(
                    undo,
                    f"{effect_path}.undo_receipt_ref",
                    not_before=started,
                    recorded_by=decided,
                )

    causal_artifacts = {
        _canonical_json(ref): _parse_utc(span["completed_at"])
        for span in record["spans"]
        for ref in span["output_refs"]
    }
    causal_artifacts.update(
        {
            _canonical_json(effect["effect_receipt_ref"]): _parse_utc(effect["observed_at"])
            for effect in record["effects"]
        }
    )
    contextual_artifacts = {
        _canonical_json(snapshot["artifact_ref"]): _parse_utc(snapshot["maximum_content_time"])
        for snapshot in record["input_snapshots"]
    }
    meaningful_machine = 0
    seen_outcome_ids: set[str] = set()
    seen_outcome_receipts: set[str] = set()
    for index, outcome in enumerate(record["machine_outcomes"]):
        path = f"machine_outcomes[{index}]"
        if outcome["outcome_id"] in seen_outcome_ids:
            add("identity.duplicate", f"{path}.outcome_id", "machine outcome ids must be unique")
        seen_outcome_ids.add(outcome["outcome_id"])
        measurement_started = _parse_utc(outcome["measurement_started_at"])
        observed = _parse_utc(outcome["observed_at"])
        if not measurement_started or not observed or (cutoff and completed and not cutoff <= measurement_started <= observed <= completed):
            add("time.observation_outside_window", path, "machine outcome must be observed after cutoff and by completion")
        verify_ref(outcome["metric_ref"], f"{path}.metric_ref", "metric", pre_cutoff=True)
        causal_key = _canonical_json(outcome["causal_ref"])
        allowed_causes = causal_artifacts if outcome["causal_basis"] == "intervention" else causal_artifacts | contextual_artifacts
        if causal_key not in allowed_causes:
            add(
                "machine_outcome.unlinked_cause",
                f"{path}.causal_ref",
                "machine outcome must cite a declared span output or effect receipt",
            )
        elif measurement_started and allowed_causes[causal_key] and measurement_started < allowed_causes[causal_key]:
            add("machine_outcome.measurement_before_cause", f"{path}.measurement_started_at", "measurement predates its cited cause")
        value_receipt = None
        if "value_ref" in outcome:
            value_receipt = verify_ref(outcome["value_ref"], f"{path}.value_ref", "value", subject_id=outcome["outcome_id"])
        machine_receipt = verify_ref(
            outcome["receipt_ref"],
            f"{path}.receipt_ref",
            "machine_outcome",
            subject_id=outcome["outcome_id"],
        )
        for field_name in ("value_ref", "receipt_ref"):
            if field_name not in outcome:
                continue
            receipt_key = _canonical_json(outcome[field_name])
            if receipt_key in seen_outcome_receipts:
                add("receipt.duplicate_use", f"{path}.{field_name}", "machine outcome receipts are one-to-one")
            seen_outcome_receipts.add(receipt_key)
        receipt_status_matches = require_payload_binding(
            machine_receipt,
            f"{path}.receipt_ref",
            {
                **run_binding,
                "outcome_id": outcome["outcome_id"],
                "status": outcome["status"],
                "causal_basis": outcome["causal_basis"],
                "causal_ref": outcome["causal_ref"],
                "measurement_started_at": outcome["measurement_started_at"],
                "observed_at": outcome["observed_at"],
                "metric_ref": outcome["metric_ref"],
                "value_ref": outcome.get("value_ref"),
            },
            "machine_outcome.receipt_mismatch",
        )
        value_time_matches = require_receipt_window(
            value_receipt,
            f"{path}.value_ref",
            content_at=observed if outcome["causal_basis"] == "intervention" else None,
            content_by=observed,
            not_before=cutoff if outcome["causal_basis"] == "intervention" else None,
            recorded_at_or_after=observed,
            recorded_by=completed,
        )
        receipt_time_matches = require_receipt_window(
            machine_receipt,
            f"{path}.receipt_ref",
            content_at=observed if outcome["causal_basis"] == "intervention" else None,
            content_by=observed,
            not_before=cutoff if outcome["causal_basis"] == "intervention" else None,
            recorded_at_or_after=observed,
            recorded_by=completed,
        )
        if (
            outcome["causal_basis"] == "intervention"
            and causal_key in causal_artifacts
            and outcome["status"] in {"verified", "failed"}
            and receipt_status_matches
            and receipt_time_matches
            and ("value_ref" not in outcome or value_time_matches)
        ):
            meaningful_machine += 1

    meaningful_human = 0
    seen_verdict_ids: set[str] = set()
    seen_verdict_receipts: set[str] = set()
    for index, verdict in enumerate(record["human_verdicts"]):
        path = f"human_verdicts[{index}]"
        if verdict["verdict_id"] in seen_verdict_ids:
            add("identity.duplicate", f"{path}.verdict_id", "human verdict ids must be unique")
        seen_verdict_ids.add(verdict["verdict_id"])
        receipt_key = _canonical_json(verdict["attestation_ref"])
        if receipt_key in seen_verdict_receipts:
            add("receipt.duplicate_use", f"{path}.attestation_ref", "Captain attestations are one-to-one")
        seen_verdict_receipts.add(receipt_key)
        observed = _parse_utc(verdict["observed_at"])
        if not observed or (cutoff and completed and not cutoff <= observed <= completed):
            add("time.observation_outside_window", path, "human verdict must be observed after cutoff and by completion")
        receipt = verify_ref(
            verdict["attestation_ref"],
            f"{path}.attestation_ref",
            "captain_attestation",
            subject_id=verdict["verdict_id"],
            actor_type="captain",
        )
        verdict_matches = require_payload_binding(
            receipt,
            f"{path}.attestation_ref",
            {
                **run_binding,
                "verdict_id": verdict["verdict_id"],
                "verdict": verdict["verdict"],
                "observed_at": verdict["observed_at"],
            },
            "human_verdict.receipt_mismatch",
        )
        verdict_time_matches = require_receipt_window(
            receipt,
            f"{path}.attestation_ref",
            content_by=observed,
            not_before=cutoff,
            recorded_at_or_after=observed,
            recorded_by=completed,
        )
        if verdict["verdict"] != "abstain" and verdict_matches and verdict_time_matches:
            meaningful_human += 1

    seen_judge_ids: set[str] = set()
    seen_judge_receipts: set[str] = set()
    for index, observation in enumerate(record["judge_observations"]):
        path = f"judge_observations[{index}]"
        if observation["observation_id"] in seen_judge_ids:
            add("identity.duplicate", f"{path}.observation_id", "judge observation ids must be unique")
        seen_judge_ids.add(observation["observation_id"])
        for field_name in ("verdict_ref", "receipt_ref"):
            receipt_key = _canonical_json(observation[field_name])
            if receipt_key in seen_judge_receipts:
                add("receipt.duplicate_use", f"{path}.{field_name}", "judge receipts are one-to-one")
            seen_judge_receipts.add(receipt_key)
        observed = _parse_utc(observation["observed_at"])
        if not observed or (cutoff and completed and not cutoff <= observed <= completed):
            add("time.observation_outside_window", path, "judge observation must be after cutoff and by completion")
        verdict_receipt = verify_ref(
            observation["verdict_ref"],
            f"{path}.verdict_ref",
            "judge_verdict",
            subject_id=observation["observation_id"],
        )
        observation_receipt = verify_ref(
            observation["receipt_ref"],
            f"{path}.receipt_ref",
            "judge_observation",
            subject_id=observation["observation_id"],
        )
        require_payload_binding(
            verdict_receipt,
            f"{path}.verdict_ref",
            {
                **run_binding,
                "observation_id": observation["observation_id"],
                "observed_at": observation["observed_at"],
            },
            "judge.verdict_binding_mismatch",
        )
        require_payload_binding(
            observation_receipt,
            f"{path}.receipt_ref",
            {
                **run_binding,
                "observation_id": observation["observation_id"],
                "observed_at": observation["observed_at"],
                "verdict_ref": observation["verdict_ref"],
            },
            "judge.observation_binding_mismatch",
        )
        require_receipt_window(
            verdict_receipt,
            f"{path}.verdict_ref",
            content_by=observed,
            not_before=cutoff,
            recorded_at_or_after=observed,
            recorded_by=completed,
        )
        require_receipt_window(
            observation_receipt,
            f"{path}.receipt_ref",
            content_by=observed,
            not_before=cutoff,
            recorded_at_or_after=observed,
            recorded_by=completed,
        )

    total_costs = record["costs"]
    cost_values = {
        key: value for key, value in total_costs.items() if key != "resource_receipt_ref"
    }
    for field_name in ("tokens", "tool_calls", "external_spend_microunits"):
        span_total = sum(span["costs"][field_name] for span in record["spans"])
        if total_costs[field_name] != span_total:
            add("cost.additive_mismatch", f"costs.{field_name}", "trajectory cost does not equal its span total")
    if started and completed:
        wall_latency_ms = int((completed - started).total_seconds() * 1000)
        if total_costs["latency_ms"] != wall_latency_ms:
            add("cost.latency_mismatch", "costs.latency_ms", "trajectory latency must be wall-clock duration")
    total_resource_path = "costs.resource_receipt_ref"
    total_resource = verify_ref(
        total_costs["resource_receipt_ref"],
        total_resource_path,
        "resource_usage",
        subject_id=record["trajectory_id"],
    )
    total_resource_key = _canonical_json(total_costs["resource_receipt_ref"])
    if total_resource_key in seen_span_receipts:
        add("receipt.duplicate_use", total_resource_path, "trajectory resource receipt must be unique")
    require_payload_binding(
        total_resource,
        total_resource_path,
        {
            **run_binding,
            "trajectory_id": record["trajectory_id"],
            "costs": cost_values,
            "latency_aggregation": "trajectory_wall_clock",
        },
        "cost.resource_receipt_mismatch",
    )
    require_receipt_window(
        total_resource,
        total_resource_path,
        content_at=completed,
        not_before=started,
        recorded_at_or_after=completed,
        recorded_by=completed,
    )

    basis = record["evaluation_basis"]
    if basis in {"machine_verifiable", "mixed"} and meaningful_machine == 0:
        add("evaluation.machine_evidence_required", "machine_outcomes", "unknown outcomes do not satisfy machine evidence")
    if basis in {"human_judgment", "mixed"} and meaningful_human == 0:
        add("evaluation.human_evidence_required", "human_verdicts", "abstentions and judges do not satisfy human evidence")

    for path, node in _walk(record):
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key in SET_LIKE_KEYS and isinstance(value, list):
                    encoded = [_canonical_json(item) for item in value]
                    if len(encoded) != len(set(encoded)):
                        add("collection.duplicate", f"{path}.{key}", "set-like collections reject duplicates")
        if isinstance(node, float) and not math.isfinite(node):
            add("cost.non_finite", path, "numeric values must be finite")

    return tuple(sorted(set(issues)))


def validate_trajectory(
    record: Any,
    context: ValidationContext | None = None,
) -> tuple[ValidationIssue, ...]:
    structural = structural_issues(record)
    if structural:
        return structural
    return semantic_issues(record, context)


def _normalize(value: Any, parent_key: str | None = None) -> Any:
    if isinstance(value, Mapping):
        return {key: _normalize(child, key) for key, child in sorted(value.items())}
    if isinstance(value, list):
        normalized = [_normalize(child) for child in value]
        if parent_key in SET_LIKE_KEYS:
            return sorted(normalized, key=_canonical_json)
        return normalized
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return value


def canonical_fingerprint(
    record: Mapping[str, Any],
    context: ValidationContext | None = None,
) -> str:
    issues = validate_trajectory(record, context)
    if issues:
        raise TrajectoryContractError(issues)
    canonical = json.dumps(
        _normalize(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()
