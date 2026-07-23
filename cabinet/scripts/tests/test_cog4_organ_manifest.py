"""COG-4 §4.3 — the ORGAN-MANIFEST negative-control battery (+ §5.2
operation-name-authority + §5.5 trajectory-v2 shape law).

Contract: docs/plans/cognitive-core-phase-4-contract-2026-07-23.md §4.2/§4.3
(validation mechanics + the named mutants), §5.2 (capability carries NO
authority), §5.5 (trajectory v2 version-dispatch), N-b (suite-level
state_ownership sweep), N-d (matrix consistency). The germline pair
(`framework/schemas/extension-manifest.schema.json` +
`cabinet/scripts/validate-extension.sh`) is schg-locked and UNTOUCHED this
wave — these controls are written AGAINST THE AMENDMENT PROPOSAL TEXT
(docs/proposals/germline-amendment-extension-manifest-organ-2026-07-23.md,
CG-33, on master), per contract §4.5 build sequencing: W4+ units build against
the proposed schema text; the actual edit is the Captain-windowed micro-unit.

Mechanics: a REFERENCE VALIDATOR transcribed field-for-field from the
proposal's §1a/§1b edit text lives in this module; every §4.3 negative
control is PROVEN NOW against fixture manifest dicts through it (live, no
skip — fixture machinery must bite today). Where the reference touches
existing closed vocabularies it binds to the REAL constants
(framework.authority.matrix.RISK_CLASSES, classifier.ACTION_TYPES, the loaded
authority-matrix policy) so vocabulary drift REDs this corpus honestly.

Controls (each with its biting fixture mutant):
  * missing `freshness_needs` REDs; missing `descriptor` REDs (§4.3)
  * a `domain_operations` id colliding with ANY of the 30 ACTION_TYPES members
    REDs — the namespace/separator law makes the flat vocabulary structurally
    un-collidable (all 30 proven)
  * duplicate `state_ownership` across two manifests REDs — SUITE-level by
    necessity (N-b: the per-file validator sees one manifest at a time)
  * declared `risk_class` != matrix-derived REDs; declared `ceiling` != the
    ceiling_frozenset_map derivation REDs (N-d)
  * a verdict predicate keyed on `capability` REDs (§5.2 operation-name-
    authority mutant: operation names carry NO authority)
  * trajectory v2: version dispatch decided BEFORE v1 checks (the
    framework/triggers/envelope.py precedent, cited by bytes); a namespaced id
    in `action_type` fails (the never-overload law) — fixture-proven now

VACUITY ARMS (the W1-u2 idiom; each with companion assertions that RED the
moment the surface lands):
  * the REAL germline pair — RETIREMENT CONDITION: retire the skip when the
    §4.5 Captain-windowed amendment (CG-33) lands (kind enum gains "organ");
    then run these fixture controls through the REAL validate-extension.sh on
    BOTH validator paths (proposal §4 gates A/B) and assert the .sh ORGAN
    BLOCK matches ORGAN_REQUIRED below.
  * the trajectory v2 schema — RETIREMENT CONDITION: retire the skip when
    framework/schemas/cognitive-trajectory.v2.schema.json lands (§5.5); then
    validate these fixtures against the REAL Draft-2020-12 document and assert
    contracts.py decides version dispatch before the v1 checks.

S0: python3.12, no DB, no network, deterministic. Provenance: authored per the
2026-07-07 full-autonomy grant + the 2026-07-20 cognitive-masterplan continuous
grant (COG-4 W2 corpus, unit T3).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from framework.authority import matrix as authority_matrix       # noqa: E402
from framework.authority.classifier import ACTION_TYPES          # noqa: E402
from framework.authority.policy_engine import risk_of            # noqa: E402

_SCHEMA_PATH = _REPO / "framework" / "schemas" / "extension-manifest.schema.json"
_VALIDATOR_SH = _REPO / "cabinet" / "scripts" / "validate-extension.sh"
_V1_TRAJECTORY = _REPO / "framework" / "schemas" / "cognitive-trajectory.schema.json"
_V2_TRAJECTORY_REL = "framework/schemas/cognitive-trajectory.v2.schema.json"
_CONTRACTS_PY = _REPO / "framework" / "evolution" / "contracts.py"
_PROPOSAL_DOC = (_REPO / "docs" / "proposals"
                 / "germline-amendment-extension-manifest-organ-2026-07-23.md")

# ---------------------------------------------------------------------------
# the proposal's §1a/§1b text, transcribed (the reference the controls bite on)
# ---------------------------------------------------------------------------
# §1b ORGAN BLOCK — thirteen required-when-organ fields; starvation_bound is
# DELIBERATELY ABSENT (optional-with-scheduler_policy-default, SF2).
ORGAN_REQUIRED = (
    "inputs", "outputs", "domain_operations", "descriptor", "permissions",
    "idempotency", "state_ownership", "cost_model", "freshness_needs",
    "trigger_policy", "health_proof", "fallback", "dependencies",
)
PROPOSED_FIELDS = ORGAN_REQUIRED + ("starvation_bound",)          # the fourteen
KIND_ENUM = ("channel", "source", "skill", "mcp", "organ")        # §1a edit 1
# §1a edit 2 — the full AUTHORITY undo grammar (one grammar, two spellings;
# drift-pinned against contracts.py bytes below)
UNDO_PATTERN = r"^(none|delete_window\([0-9]+\)|journal:[A-Za-z0-9._:/-]+)$"
UNDO_RE = re.compile(UNDO_PATTERN)
DOMAIN_OP_RE = re.compile(r"^[a-z0-9_-]+/[a-z0-9._-]+$")          # §4.2 namespaced ids
RISK_CLASS_ENUM = frozenset({
    "calendar_write", "credentials_grant", "deploy_nonprod", "deploy_prod",
    "draft_only", "external_comms", "internal_comms", "network_write",
    "pm_write", "read_only_dispatch", "reversible", "secrets", "spend",
})                                                                # the closed 13
FALLBACK_ENUM = ("skip", "safe_noop", "escalate")
TRIGGER_MODES = ("periodic", "event", "on_demand")

# the REAL base schema's property surface (live read — the reference validator's
# unknown-key law is anchored to real bytes, so it stays correct both before and
# after the amendment lands: base ∪ the 14 is stable across the edit)
_BASE_SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
_BASE_PROPS = frozenset(_BASE_SCHEMA["properties"].keys())
_BASE_REQUIRED = tuple(_BASE_SCHEMA["required"])
_ALLOWED_PROPS = _BASE_PROPS | frozenset(PROPOSED_FIELDS)

# the loaded authority-matrix policy (N-d's derivation source, read-only)
_POLICY = authority_matrix.matrix_policy(authority_matrix.load_matrix())
_RISK_MAP = _POLICY["risk_classes"]
_HARD_CEILING = frozenset(_POLICY["hard_ceiling"])
_CEILING_MAP = _POLICY["ceiling_frozenset_map"]


def _is_int(v: object) -> bool:
    """The proposal §1b integer-branch semantics: bool is NOT an integer."""
    return isinstance(v, int) and not isinstance(v, bool)


def _str_list_errors(manifest: dict, key: str, errs: list[str]) -> None:
    val = manifest.get(key)
    if not isinstance(val, list) or any(
            not isinstance(x, str) or not x for x in val):
        errs.append(f"{key}: must be an array of non-empty strings")


def _descriptor_member_errors(obj: dict, where: str, errs: list[str],
                              require_all: bool) -> None:
    """The four §5.2 members, per the proposal's descriptor block."""
    members = ("action_type", "risk_class", "ceiling", "undo_contract")
    if require_all:
        for m in members:
            if m not in obj:
                errs.append(f"{where}: missing required member {m!r}")
    if "action_type" in obj and (
            not isinstance(obj["action_type"], str) or not obj["action_type"]):
        errs.append(f"{where}.action_type: must be a non-empty string")
    if "risk_class" in obj and obj["risk_class"] not in RISK_CLASS_ENUM:
        errs.append(f"{where}.risk_class: {obj.get('risk_class')!r} is outside the "
                    f"closed 13-member enum")
    if "ceiling" in obj and (not isinstance(obj["ceiling"], list) or any(
            not isinstance(x, str) or not x for x in obj["ceiling"])):
        errs.append(f"{where}.ceiling: must be an array of non-empty strings")
    if "undo_contract" in obj and (
            not isinstance(obj["undo_contract"], str)
            or not UNDO_RE.fullmatch(obj["undo_contract"])):
        errs.append(f"{where}.undo_contract: {obj.get('undo_contract')!r} fails the "
                    f"undo grammar")


def validate_organ_manifest(manifest: object) -> list[str]:
    """The REFERENCE validator — the proposal's §1a schema features + §1b organ
    block, transcribed. Deep validation of the BASE members (entrypoints shape,
    axis lint, realpath containment) stays the real validate-extension.sh's
    law; this reference enforces exactly the organ amendment surface: top-level
    key closure, kind enum, undo grammar, the thirteen required-when-organ
    fields, and every organ-field shape of §1a edit 3."""
    errs: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest is not a mapping"]

    unknown = sorted(set(manifest) - _ALLOWED_PROPS)
    if unknown:
        errs.append(f"unknown top-level keys {unknown} (additionalProperties: false)")
    for k in _BASE_REQUIRED:
        if k not in manifest:
            errs.append(f"missing required base member {k!r}")
    kind = manifest.get("kind")
    if kind is not None and kind not in KIND_ENUM:
        errs.append(f"kind: {kind!r} is outside the enum {list(KIND_ENUM)}")
    if "undo_contract" in manifest and (
            not isinstance(manifest["undo_contract"], str)
            or not UNDO_RE.fullmatch(manifest["undo_contract"])):
        errs.append(f"undo_contract: {manifest.get('undo_contract')!r} fails the "
                    f"undo grammar")

    if kind != "organ":
        return errs

    # --- the §1b ORGAN BLOCK: thirteen required-when-organ fields -----------
    missing = sorted(k for k in ORGAN_REQUIRED if k not in manifest)
    if missing:
        errs.append(f"organ manifest missing required organ keys {missing}")

    declared_ops = manifest.get("domain_operations")
    ops_set = set(declared_ops) if isinstance(declared_ops, list) else set()

    for key in ("inputs", "outputs", "permissions", "state_ownership"):
        if key in manifest:
            _str_list_errors(manifest, key, errs)

    if "domain_operations" in manifest:
        if (not isinstance(declared_ops, list) or not declared_ops):
            errs.append("domain_operations: must be a non-empty array (minItems 1)")
        else:
            for op in declared_ops:
                if not isinstance(op, str) or not DOMAIN_OP_RE.fullmatch(op):
                    errs.append(
                        f"domain_operations: {op!r} must match "
                        f"'^[a-z0-9_-]+/[a-z0-9._-]+$' — the '/' separator is "
                        f"structurally required, so a flat ACTION_TYPES-style "
                        f"token can never appear here (§4.2)")

    if "descriptor" in manifest:
        d = manifest["descriptor"]
        if not isinstance(d, dict):
            errs.append("descriptor: must be an object")
        else:
            extra = sorted(set(d) - {"action_type", "risk_class", "ceiling",
                                     "undo_contract", "operations"})
            if extra:
                errs.append(f"descriptor: unknown keys {extra}")
            _descriptor_member_errors(d, "descriptor", errs, require_all=True)
            ops = d.get("operations")
            if ops is not None:
                if not isinstance(ops, dict):
                    errs.append("descriptor.operations: must be an object")
                else:
                    for op_id, override in ops.items():
                        if op_id not in ops_set:
                            errs.append(f"descriptor.operations: {op_id!r} is not a "
                                        f"declared domain_operations id")
                        if not isinstance(override, dict):
                            errs.append(f"descriptor.operations[{op_id!r}]: must be "
                                        f"an object")
                            continue
                        extra_o = sorted(set(override) - {"action_type", "risk_class",
                                                          "ceiling", "undo_contract"})
                        if extra_o:
                            errs.append(f"descriptor.operations[{op_id!r}]: unknown "
                                        f"keys {extra_o}")
                        _descriptor_member_errors(
                            override, f"descriptor.operations[{op_id!r}]", errs,
                            require_all=False)

    if "idempotency" in manifest:
        idem = manifest["idempotency"]
        if not isinstance(idem, dict) or not idem:
            errs.append("idempotency: must be a non-empty object (minProperties 1)")
        else:
            for k, v in idem.items():
                if k not in ops_set:
                    errs.append(f"idempotency: key {k!r} is not a declared "
                                f"domain_operations id")
                if not isinstance(v, str) or not v:
                    errs.append(f"idempotency[{k!r}]: must be a non-empty string")

    if "cost_model" in manifest:
        cm = manifest["cost_model"]
        if not isinstance(cm, dict):
            errs.append("cost_model: must be an object")
        else:
            if sorted(set(cm) - {"units_per_wake"}):
                errs.append("cost_model: unknown keys "
                            f"{sorted(set(cm) - {'units_per_wake'})}")
            if not _is_int(cm.get("units_per_wake")) or cm.get("units_per_wake") < 0:
                errs.append("cost_model.units_per_wake: must be an integer >= 0")

    if "starvation_bound" in manifest:            # OPTIONAL even for organs (SF2)
        sb = manifest["starvation_bound"]
        if not isinstance(sb, dict) or not sb:
            errs.append("starvation_bound: must be a non-empty object "
                        "(minProperties 1)")
        else:
            if sorted(set(sb) - {"max_wakes", "max_seconds"}):
                errs.append(f"starvation_bound: unknown keys "
                            f"{sorted(set(sb) - {'max_wakes', 'max_seconds'})}")
            for k in ("max_wakes", "max_seconds"):
                if k in sb and (not _is_int(sb[k]) or sb[k] < 1):
                    errs.append(f"starvation_bound.{k}: must be an integer >= 1")

    if "freshness_needs" in manifest:
        fn = manifest["freshness_needs"]
        if not isinstance(fn, dict):
            errs.append("freshness_needs: must be an object")
        else:
            if sorted(set(fn) - {"max_staleness_seconds", "expected_output"}):
                errs.append("freshness_needs: unknown keys "
                            f"{sorted(set(fn) - {'max_staleness_seconds', 'expected_output'})}")
            if not _is_int(fn.get("max_staleness_seconds")) \
                    or fn.get("max_staleness_seconds") < 1:
                errs.append("freshness_needs.max_staleness_seconds: must be an "
                            "integer >= 1")
            if not isinstance(fn.get("expected_output"), str) \
                    or not fn.get("expected_output"):
                errs.append("freshness_needs.expected_output: must be a non-empty "
                            "string")

    if "trigger_policy" in manifest:
        tp = manifest["trigger_policy"]
        if not isinstance(tp, dict) or tp.get("mode") not in TRIGGER_MODES:
            errs.append(f"trigger_policy: mode must be one of {list(TRIGGER_MODES)}")
        elif sorted(set(tp) - {"mode", "parameters"}):
            errs.append(f"trigger_policy: unknown keys "
                        f"{sorted(set(tp) - {'mode', 'parameters'})}")

    if "health_proof" in manifest:
        hp = manifest["health_proof"]
        if not isinstance(hp, dict) or not isinstance(hp.get("probe"), str) \
                or not hp.get("probe"):
            errs.append("health_proof: must be an object with a non-empty 'probe'")
        elif sorted(set(hp) - {"probe", "expectation"}):
            errs.append(f"health_proof: unknown keys "
                        f"{sorted(set(hp) - {'probe', 'expectation'})}")

    if "fallback" in manifest and manifest["fallback"] not in FALLBACK_ENUM:
        errs.append(f"fallback: {manifest.get('fallback')!r} must be one of "
                    f"{list(FALLBACK_ENUM)}")

    if "dependencies" in manifest:
        dep = manifest["dependencies"]
        if not isinstance(dep, dict) or sorted(set(dep) - {"organs", "capabilities"}):
            errs.append("dependencies: must be an object with only "
                        "organs/capabilities keys")
        else:
            for k in ("organs", "capabilities"):
                if k in dep and (not isinstance(dep[k], list) or any(
                        not isinstance(x, str) or not x for x in dep[k])):
                    errs.append(f"dependencies.{k}: must be an array of non-empty "
                                f"strings")
    return errs


# ---------------------------------------------------------------------------
# N-d — matrix consistency (declared vs DERIVED, through the real matrix)
# ---------------------------------------------------------------------------
def matrix_consistency_errors(descriptor: dict) -> list[str]:
    """§4.3 N-d: the manifest-declared `risk_class` must equal the matrix-derived
    class for the declared compat `action_type`, and the declared `ceiling` must
    equal the ceiling_frozenset_map derivation. Fail-closed: an action_type the
    matrix cannot derive (risk_of -> None) is an error, never a pass."""
    errs: list[str] = []
    at = descriptor.get("action_type")
    declared_risk = descriptor.get("risk_class")
    if at not in ACTION_TYPES:
        errs.append(f"action_type {at!r} is not an ACTION_TYPES member")
        return errs
    derived_risk = risk_of(at, _RISK_MAP)
    if derived_risk is None:
        errs.append(f"action_type {at!r} has no matrix-derived risk class "
                    f"(fail-safe propose_only territory — not declarable)")
        return errs
    if declared_risk != derived_risk:
        errs.append(f"risk_class {declared_risk!r} != matrix-derived "
                    f"{derived_risk!r} for action_type {at!r} (N-d)")
    derived_ceiling = ({_CEILING_MAP[derived_risk]}
                       if derived_risk in _HARD_CEILING else set())
    declared_ceiling = set(descriptor.get("ceiling") or [])
    if declared_ceiling != derived_ceiling:
        errs.append(f"ceiling {sorted(declared_ceiling)} != ceiling_frozenset_map "
                    f"derivation {sorted(derived_ceiling)} for risk_class "
                    f"{derived_risk!r} (N-d)")
    return errs


# ---------------------------------------------------------------------------
# N-b — the SUITE-level cross-manifest state_ownership sweep
# ---------------------------------------------------------------------------
def state_ownership_collisions(manifests: list[dict]) -> list[str]:
    """Two organs claiming one `state_ownership` path — detectable only across
    manifests (the per-file validator sees one at a time, §4.3 N-b). Output is
    symmetric + sorted (the assemble-collision law shape)."""
    owners: dict[str, list[str]] = {}
    for man in manifests:
        name = man.get("name", "<unnamed>")
        for path in man.get("state_ownership") or []:
            owners.setdefault(path, []).append(name)
    return sorted(
        f"state_ownership collision on {path!r}: {sorted(names)}"
        for path, names in owners.items() if len(names) > 1)


# ---------------------------------------------------------------------------
# §5.2 — operation names carry NO authority (the capability-blindness harness)
# ---------------------------------------------------------------------------
def capability_blindness_violations(predicate, pairs) -> list[str]:
    """For (op_a, op_b, descriptor) triples where BOTH operations carry the
    IDENTICAL constitutional descriptor, any verdict difference proves the
    predicate keys on the operation/capability name — the §5.2 mutant."""
    v: list[str] = []
    for op_a, op_b, descriptor in pairs:
        va = predicate(op_a, dict(descriptor))
        vb = predicate(op_b, dict(descriptor))
        if va != vb:
            v.append(f"verdict keys on the operation name: {op_a!r} -> {va!r} but "
                     f"{op_b!r} -> {vb!r} on an IDENTICAL descriptor "
                     f"(risk_class={descriptor.get('risk_class')!r})")
    return v


def _reference_verdict(_operation: str, descriptor: dict) -> str:
    """A LAWFUL shadow-verdict predicate: a pure function of the constitutional
    members only (risk_class / undo_contract / ceiling) — never the name."""
    if descriptor["risk_class"] in _HARD_CEILING:
        return "always_gated"
    if descriptor["undo_contract"] == "none":
        return "propose_only"
    return "shadow_ok"


def _capability_keyed_mutant(operation: str, descriptor: dict) -> str:
    """THE §5.2 MUTANT: special-cases a favored operation name."""
    if operation == "garden/water.plots":
        return "shadow_ok"
    return _reference_verdict(operation, descriptor)


# ---------------------------------------------------------------------------
# §5.5 — trajectory v2 reference shapes (version dispatch + effect law)
# ---------------------------------------------------------------------------
V1_CONST = "cognitive-trajectory/v1"
V2_CONST = "cognitive-trajectory/v2"
STATUS_ENUM = ("proposed", "denied", "attempted", "verified", "failed",
               "reversed", "violation")                     # v1 schema :266


def route_trajectory_version(record: object) -> tuple[str, str | None]:
    """The envelope-precedent dispatch (framework/triggers/envelope.py, cited by
    bytes): the version is decided FIRST, before ANY v1 shape check — a v2
    record can never be refused by v1's closed key set."""
    if not isinstance(record, dict):
        return ("error", "record is not a mapping")
    sv = record.get("schema_version")
    if sv == V2_CONST:
        return ("v2", None)
    if sv == V1_CONST:
        return ("v1", None)
    return ("error", f"unknown schema_version {sv!r}")


def _v1_first_mutant_dispatcher(record: dict) -> tuple[str, str | None]:
    """THE §5.5 MUTANT: applies the v1 closed-set check BEFORE reading the
    version — exactly the shape the envelope precedent forbids."""
    if record.get("schema_version") != V1_CONST:      # v1 closed-set check first
        return ("invalid", "v1: schema_version must be the v1 const")
    return ("v1", None)


def v2_effect_errors(effect: object) -> list[str]:
    """The v2 effect reference shape (§5.5): every v1 member kept INCLUDING
    `action_type` (compat — a bare closed-30 member; the landed validator binds
    it to contracts.py action_risk_map), plus required `domain_operation`
    ({organ, operation}) and `enforcement_descriptor` (the §5.2 block). The
    granular id lives ONLY in domain_operation: a namespaced id in action_type
    fails (charter L184 — never overload action_type)."""
    errs: list[str] = []
    if not isinstance(effect, dict):
        return ["effect is not a mapping"]
    for k in ("effect_id", "action_type", "status", "idempotency_key",
              "domain_operation", "enforcement_descriptor"):
        if k not in effect:
            errs.append(f"missing required member {k!r}")
    at = effect.get("action_type")
    if isinstance(at, str) and "/" in at:
        errs.append(f"action_type {at!r} carries a namespaced id — the granular id "
                    f"lives ONLY in domain_operation (§5.5 never-overload law)")
    elif at is not None and at not in ACTION_TYPES:
        errs.append(f"action_type {at!r} is not a closed-30 compat member")
    if effect.get("status") is not None and effect.get("status") not in STATUS_ENUM:
        errs.append(f"status {effect.get('status')!r} is outside the 7-status enum")
    do = effect.get("domain_operation")
    if do is not None:
        if (not isinstance(do, dict)
                or sorted(set(do) - {"organ", "operation"})
                or not isinstance(do.get("organ"), str) or not do.get("organ")
                or not isinstance(do.get("operation"), str)
                or not DOMAIN_OP_RE.fullmatch(do.get("operation") or "")):
            errs.append("domain_operation: must be {organ: <name>, operation: "
                        "<namespaced id>}")
    ed = effect.get("enforcement_descriptor")
    if ed is not None:
        if not isinstance(ed, dict):
            errs.append("enforcement_descriptor: must be an object")
        else:
            cap = ed.get("capability")
            if not isinstance(cap, str) or not DOMAIN_OP_RE.fullmatch(cap):
                errs.append("enforcement_descriptor.capability: must be a "
                            "namespaced '<domain>/<operation>' id")
            _descriptor_member_errors(ed, "enforcement_descriptor", errs,
                                      require_all=True)
    return errs


def _valid_v2_effect() -> dict:
    return {
        "effect_id": "eff-0001",
        "action_type": "investigation_run",
        "status": "proposed",
        "idempotency_key": "garden-rota-2026-07-23",
        "domain_operation": {"organ": "garden-rota",
                             "operation": "garden/rota.compile"},
        "enforcement_descriptor": {
            "capability": "garden/rota.compile",
            "action_type": "investigation_run",
            "risk_class": "read_only_dispatch",
            "ceiling": [],
            "undo_contract": "none",
        },
    }


# ---------------------------------------------------------------------------
# the fixture organ manifest (garden-rota — non-software vocabulary by design)
# ---------------------------------------------------------------------------
def _valid_organ_manifest() -> dict:
    return {
        "name": "garden-rota",
        "version": "1.0.0",
        "kind": "organ",
        "action_types": ["investigation_run"],
        "risk_classes": ["read_only_dispatch"],
        "undo_contract": "none",
        "entrypoints": {},          # base member — deep shape is the germline .sh's law
        "inputs": ["garden/beds.yml", "garden/volunteer-signups.yml"],
        "outputs": ["garden/rota-plan.json"],
        "domain_operations": ["garden/water.plots", "garden/rota.compile"],
        "descriptor": {
            "action_type": "investigation_run",
            "risk_class": "read_only_dispatch",
            "ceiling": [],
            "undo_contract": "none",
            "operations": {
                "garden/water.plots": {"undo_contract": "delete_window(3600)"},
            },
        },
        "permissions": ["files/read"],
        "idempotency": {"garden/water.plots": "bed-id + date",
                        "garden/rota.compile": "week-of"},
        "state_ownership": ["garden/rota-plan.json"],
        "cost_model": {"units_per_wake": 2},
        "starvation_bound": {"max_wakes": 6},
        "freshness_needs": {"max_staleness_seconds": 604800,
                            "expected_output": "garden/rota-plan.json"},
        "trigger_policy": {"mode": "periodic", "parameters": {"interval_s": 86400}},
        "health_proof": {"probe": "rota-plan parses", "expectation": "ok"},
        "fallback": "skip",
        "dependencies": {"organs": [], "capabilities": ["files/read"]},
    }


# ---------------------------------------------------------------------------
# live grounding — the reference is pinned to the REAL closed vocabularies
# ---------------------------------------------------------------------------
class TestReferenceGrounding:
    def test_risk_class_enum_matches_the_matrix(self):
        """The proposal's inline 13-member enum must equal the REAL
        framework.authority.matrix.RISK_CLASSES — vocabulary drift REDs the
        corpus, never silently diverges."""
        assert RISK_CLASS_ENUM == set(authority_matrix.RISK_CLASSES)

    def test_risk_class_enum_matches_the_base_schema_inline_enum(self):
        """The CURRENT germline schema already binds the 13-member vocabulary
        inline on `risk_classes` — the proposal duplicates exactly it."""
        inline = _BASE_SCHEMA["properties"]["risk_classes"]["items"]["enum"]
        assert set(inline) == RISK_CLASS_ENUM

    def test_action_types_ground(self):
        assert len(ACTION_TYPES) == 30
        assert all("/" not in m for m in ACTION_TYPES), (
            "an ACTION_TYPES member carrying '/' would break the §4.2 structural "
            "un-collidability law")

    def test_base_schema_required_members(self):
        assert set(_BASE_REQUIRED) == {"name", "version", "kind", "action_types",
                                       "risk_classes", "undo_contract", "entrypoints"}
        assert _BASE_SCHEMA.get("additionalProperties") is False

    def test_undo_grammar_is_the_contracts_grammar(self):
        """One grammar, two spellings (§4.2): the proposal pattern's language is
        byte-present in framework/evolution/contracts.py (the AUTHORITY grammar)
        — the drift tripwire that binds the spellings without importing the
        action plane."""
        src = _CONTRACTS_PY.read_text(encoding="utf-8")
        assert "none|delete_window\\([0-9]+\\)|journal:[A-Za-z0-9._:/-]+" in src
        # and the CURRENT germline pattern is a strict subset (superset proof:
        # both old alternatives survive verbatim under the proposed grammar)
        current = _BASE_SCHEMA["properties"]["undo_contract"]["pattern"]
        for probe in ("none", "delete_window(0)", "delete_window(86400)"):
            assert re.fullmatch(current, probe)
            assert UNDO_RE.fullmatch(probe)
        assert not re.fullmatch(current, "journal:outbox-flush")
        assert UNDO_RE.fullmatch("journal:outbox-flush")

    @pytest.mark.parametrize("bad", [
        "", "journal:", "delete_window()", "delete_window(-1)", "NONE",
        "journal:bad space", "none ", "delete_window(3.5)",
    ])
    def test_undo_grammar_rejects(self, bad):
        assert not UNDO_RE.fullmatch(bad)

    def test_proposal_doc_is_on_master(self):
        """These controls target the amendment PROPOSAL text — assert the doc
        exists and carries the organ kind + the thirteen-field block."""
        text = _PROPOSAL_DOC.read_text(encoding="utf-8")
        assert '"channel", "source", "skill", "mcp", "organ"' in text
        for field in PROPOSED_FIELDS:
            assert f'"{field}"' in text, f"proposal must define {field!r}"


# ---------------------------------------------------------------------------
# §4.3 negative controls — live, each mutant proven to bite NOW
# ---------------------------------------------------------------------------
class TestOrganManifestControls:
    def test_valid_organ_manifest_passes(self):
        assert validate_organ_manifest(_valid_organ_manifest()) == []

    def test_missing_freshness_needs_reds(self):
        man = _valid_organ_manifest()
        del man["freshness_needs"]
        errs = validate_organ_manifest(man)
        assert any("freshness_needs" in e and "missing required organ keys" in e
                   for e in errs), errs

    def test_missing_descriptor_reds(self):
        man = _valid_organ_manifest()
        del man["descriptor"]
        errs = validate_organ_manifest(man)
        assert any("descriptor" in e and "missing required organ keys" in e
                   for e in errs), errs

    def test_every_action_types_member_collides_red(self):
        """The namespace/separator law, proven over ALL 30 members: a flat
        ACTION_TYPES token in domain_operations fails the pattern — the central
        vocabulary is structurally un-collidable (§4.2/§4.3)."""
        for member in sorted(ACTION_TYPES):
            man = _valid_organ_manifest()
            man["domain_operations"] = [member]     # only the ops list is mutated
            errs = validate_organ_manifest(man)
            assert any("structurally required" in e and repr(member) in e
                       for e in errs), (member, errs)

    def test_namespaced_ops_pass_even_when_op_part_matches_a_member(self):
        """'email/send_email' is legal — the '/' separator IS the collision
        proof; only the flat spelling can collide, and it cannot validate."""
        man = _valid_organ_manifest()
        man["domain_operations"] = ["email/send_email", "garden/rota.compile",
                                    "garden/water.plots"]
        errs = [e for e in validate_organ_manifest(man)
                if "domain_operations" in e]
        assert errs == []

    def test_unknown_key_reds(self):
        man = _valid_organ_manifest()
        man["surprise_power"] = True
        errs = validate_organ_manifest(man)
        assert any("unknown top-level keys" in e and "surprise_power" in e
                   for e in errs), errs

    def test_non_organ_kinds_never_enter_the_organ_block(self):
        """Proposal §2.3: the organ block only ever REFUSES organs — a channel
        manifest without any organ field stays valid under the reference."""
        man = {"name": "outlook", "version": "1.0.0", "kind": "channel",
               "action_types": ["external_email"], "risk_classes": ["external_comms"],
               "undo_contract": "delete_window(300)", "entrypoints": {}}
        assert validate_organ_manifest(man) == []

    def test_unknown_kind_reds(self):
        man = _valid_organ_manifest()
        man["kind"] = "banana"
        assert any("outside the enum" in e for e in validate_organ_manifest(man))

    def test_descriptor_risk_class_outside_13_reds(self):
        man = _valid_organ_manifest()
        man["descriptor"]["risk_class"] = "quantum_write"
        assert any("closed 13-member enum" in e for e in validate_organ_manifest(man))

    def test_journal_undo_with_empty_id_reds(self):
        man = _valid_organ_manifest()
        man["descriptor"]["undo_contract"] = "journal:"
        assert any("fails the undo grammar" in e for e in validate_organ_manifest(man))

    def test_non_integer_staleness_reds(self):
        for bad in ("3600", True, 0, -5, 3.5):
            man = _valid_organ_manifest()
            man["freshness_needs"]["max_staleness_seconds"] = bad
            assert any("max_staleness_seconds" in e
                       for e in validate_organ_manifest(man)), bad

    def test_trigger_mode_and_fallback_enums_red(self):
        man = _valid_organ_manifest()
        man["trigger_policy"]["mode"] = "whenever"
        assert any("trigger_policy" in e for e in validate_organ_manifest(man))
        man2 = _valid_organ_manifest()
        man2["fallback"] = "retry_forever"
        assert any("fallback" in e for e in validate_organ_manifest(man2))

    def test_starvation_bound_stays_optional_but_shaped(self):
        man = _valid_organ_manifest()
        del man["starvation_bound"]
        assert validate_organ_manifest(man) == []      # SF2: optional for organs
        man["starvation_bound"] = {}
        assert any("minProperties 1" in e for e in validate_organ_manifest(man))
        man["starvation_bound"] = {"max_wakes": 0}
        assert any("integer >= 1" in e for e in validate_organ_manifest(man))

    def test_undeclared_op_ids_red(self):
        man = _valid_organ_manifest()
        man["idempotency"]["garden/uninvented.op"] = "nope"
        assert any("not a declared domain_operations id" in e
                   for e in validate_organ_manifest(man))
        man2 = _valid_organ_manifest()
        man2["descriptor"]["operations"]["garden/uninvented.op"] = {}
        assert any("not a declared domain_operations id" in e
                   for e in validate_organ_manifest(man2))


class TestSuiteLevelStateOwnership:
    def test_disjoint_manifests_are_clean(self):
        m1 = _valid_organ_manifest()
        m2 = _valid_organ_manifest()
        m2["name"] = "delivery-run"
        m2["state_ownership"] = ["delivery/route-plan.json"]
        assert state_ownership_collisions([m1, m2]) == []

    def test_duplicate_state_ownership_reds_suite_level(self):
        """§4.3 N-b: two organs claiming one state_ownership path — the SUITE
        sweep catches what the per-file validator structurally cannot."""
        m1 = _valid_organ_manifest()
        m2 = _valid_organ_manifest()
        m2["name"] = "delivery-run"          # same state_ownership as garden-rota
        collisions = state_ownership_collisions([m1, m2])
        assert collisions and "garden/rota-plan.json" in collisions[0]
        assert "delivery-run" in collisions[0] and "garden-rota" in collisions[0]
        # symmetric + sorted (the assemble-collision law shape)
        assert collisions == sorted(collisions)


class TestMatrixConsistencyNd:
    def test_consistent_descriptor_is_clean(self):
        d = _valid_organ_manifest()["descriptor"]
        assert matrix_consistency_errors(d) == []

    def test_declared_risk_class_mismatch_reds(self):
        """N-d mutant: declared risk_class != matrix-derived for the declared
        compat action_type."""
        d = _valid_organ_manifest()["descriptor"]
        d["risk_class"] = "reversible"       # matrix derives read_only_dispatch
        errs = matrix_consistency_errors(d)
        assert any("matrix-derived" in e and "read_only_dispatch" in e
                   for e in errs), errs

    def test_declared_ceiling_mismatch_reds(self):
        """N-d ceiling limb: a hard-ceiling action_type must declare EXACTLY the
        ceiling_frozenset_map derivation — an empty ceiling REDs; the derived
        spelling passes."""
        d = {"action_type": "external_email", "risk_class": "external_comms",
             "ceiling": [], "undo_contract": "none"}
        errs = matrix_consistency_errors(d)
        assert any("ceiling_frozenset_map" in e for e in errs), errs
        d["ceiling"] = ["external_comms"]
        assert matrix_consistency_errors(d) == []

    def test_unmapped_action_type_fails_closed(self):
        d = {"action_type": "ambiguous", "risk_class": "read_only_dispatch",
             "ceiling": [], "undo_contract": "none"}
        errs = matrix_consistency_errors(d)
        # `ambiguous` is an ACTION_TYPES member with NO matrix mapping — the
        # fail-safe propose_only hole; a manifest may never declare through it
        assert errs and "no matrix-derived risk class" in errs[0]


class TestOperationNameAuthority:
    _PAIRS = [
        ("garden/water.plots", "warehouse/pick.route",
         {"risk_class": "external_comms", "ceiling": ["external_comms"],
          "undo_contract": "none"}),
        ("garden/water.plots", "care-rota/visit.assign",
         {"risk_class": "read_only_dispatch", "ceiling": [],
          "undo_contract": "delete_window(3600)"}),
    ]

    def test_reference_predicate_is_capability_blind(self):
        assert capability_blindness_violations(_reference_verdict, self._PAIRS) == []

    def test_capability_keyed_mutant_reds(self):
        """THE §5.2 operation-name-authority mutant: a verdict function keying
        on `capability` REDs — identical constitutional tuple, divergent
        verdicts, named."""
        v = capability_blindness_violations(_capability_keyed_mutant, self._PAIRS)
        assert v, "the capability-keyed mutant must be caught"
        assert any("garden/water.plots" in x and "keys on the operation name" in x
                   for x in v), v
        # the mutant's escape is exactly the hard-ceiling bypass: it grants
        # shadow_ok where the descriptor demands always_gated
        assert any("'shadow_ok'" in x and "'always_gated'" in x for x in v), v


class TestTrajectoryV2Shapes:
    def test_version_dispatch_decided_before_v1_checks(self):
        v2 = {"schema_version": V2_CONST, "rows": []}
        assert route_trajectory_version(v2) == ("v2", None)
        assert route_trajectory_version({"schema_version": V1_CONST}) == ("v1", None)
        kind, reason = route_trajectory_version({"schema_version": "trajectory/v9"})
        assert kind == "error" and "unknown schema_version" in (reason or "")

    def test_v1_first_mutant_dispatcher_reds(self):
        """THE §5.5 MUTANT (the envelope-precedent inversion): a dispatcher
        applying v1's closed-set check before reading the version REFUSES a
        valid v2 record — the exact misroute the version-first law forbids."""
        v2 = {"schema_version": V2_CONST}
        assert route_trajectory_version(v2)[0] == "v2"          # lawful: routed
        kind, _reason = _v1_first_mutant_dispatcher(v2)
        assert kind == "invalid", (
            "the v1-first mutant should refuse the valid v2 record — if it routed "
            "it, the mutant no longer demonstrates the escape")

    def test_status_enum_matches_the_real_v1_schema(self):
        """The 7-status vocabulary is REUSED, not re-minted (§5.2): pin the
        transcription to the real v1 schema bytes."""
        schema = json.loads(_V1_TRAJECTORY.read_text(encoding="utf-8"))
        found: list[list] = []

        def walk(node):
            if isinstance(node, dict):
                enum = node.get("enum")
                if isinstance(enum, list) and set(enum) == set(STATUS_ENUM):
                    found.append(enum)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(schema)
        assert found, "the v1 schema must carry the 7-status effect enum"
        assert schema["properties"]["schema_version"]["const"] == V1_CONST

    def test_valid_v2_effect_passes(self):
        assert v2_effect_errors(_valid_v2_effect()) == []

    def test_namespaced_action_type_reds(self):
        """§5.5 mutant: a v2 instance carrying a namespaced id in `action_type`
        fails — the granular id lives ONLY in domain_operation."""
        eff = _valid_v2_effect()
        eff["action_type"] = "garden/water.plots"
        errs = v2_effect_errors(eff)
        assert any("never-overload" in e for e in errs), errs

    def test_missing_v2_members_red(self):
        for member in ("domain_operation", "enforcement_descriptor"):
            eff = _valid_v2_effect()
            del eff[member]
            assert any(repr(member) in e for e in v2_effect_errors(eff)), member

    def test_status_outside_the_seven_reds(self):
        eff = _valid_v2_effect()
        eff["status"] = "succeeded"
        assert any("7-status enum" in e for e in v2_effect_errors(eff))


# ---------------------------------------------------------------------------
# vacuity arms — the real germline pair + the real v2 schema
# ---------------------------------------------------------------------------
class TestRealSurfacesVacuityArms:
    def test_real_germline_validator_arm(self):
        """VACUITY GUARD — RETIREMENT CONDITION: retire this skip when the §4.5
        Captain-windowed amendment (CG-33) lands on the germline pair; the
        retired arm runs the fixture controls above through the REAL
        cabinet/scripts/validate-extension.sh on BOTH validator paths (proposal
        §4 gates A/B — jsonschema and hand_validate), asserts the .sh ORGAN
        BLOCK's required tuple equals ORGAN_REQUIRED, and asserts the landed
        schema's organ surface equals the proposal text. The COMPANION
        assertions below pin the CURRENT pre-amendment bytes and RED the moment
        the amendment lands, so the skip cannot silently persist (the W1-u2
        idiom). schg is never worked around: while the window is closed these
        controls bind the PROPOSAL text only (§4.5 build sequencing)."""
        kind_enum = _BASE_SCHEMA["properties"]["kind"]["enum"]
        assert "organ" not in kind_enum, (
            "the germline schema's kind enum has gained 'organ' — the CG-33 "
            "amendment has LANDED: retire this vacuity skip per the docstring "
            "RETIREMENT CONDITION")
        assert "journal:" not in _BASE_SCHEMA["properties"]["undo_contract"]["pattern"], (
            "the germline undo grammar has been extended — the CG-33 amendment has "
            "LANDED: retire this vacuity skip per the docstring RETIREMENT CONDITION")
        present = sorted(set(PROPOSED_FIELDS) & _BASE_PROPS)
        assert present == [], (
            f"proposed organ fields {present} are now IN the germline schema — the "
            f"CG-33 amendment has LANDED: retire this vacuity skip per the docstring "
            f"RETIREMENT CONDITION")
        sh_text = _VALIDATOR_SH.read_text(encoding="utf-8")
        assert "ORGAN_REQUIRED" not in sh_text, (
            "validate-extension.sh has gained the ORGAN BLOCK — the CG-33 amendment "
            "has LANDED: retire this vacuity skip per the docstring RETIREMENT "
            "CONDITION")
        pytest.skip(
            "VACUITY: the CG-33 germline amendment is filed but NOT applied (Captain "
            "window closed) — controls bind the proposal text via the reference "
            "validator above; retire when the window lands the edit.")

    def test_real_trajectory_v2_schema_arm(self):
        """VACUITY GUARD — RETIREMENT CONDITION: retire this skip when
        framework/schemas/cognitive-trajectory.v2.schema.json lands (§5.5); the
        retired arm validates the fixture effects above against the REAL
        Draft-2020-12 document (valid v2 effect PASSES; namespaced action_type
        REDs) and asserts framework/evolution/contracts.py decides version
        dispatch BEFORE the v1 checks. The COMPANION assertion REDs the moment
        the schema lands, so the skip cannot silently persist."""
        v2 = _REPO / _V2_TRAJECTORY_REL
        assert not v2.exists(), (
            f"{_V2_TRAJECTORY_REL} has LANDED — retire this vacuity skip and bind "
            f"the fixtures to the real v2 schema per the docstring RETIREMENT "
            f"CONDITION")
        # v1 stays frozen and validator-only meanwhile (§5.5): the v1 const is
        # byte-present and no v2 const has leaked into the v1 document
        v1_text = _V1_TRAJECTORY.read_text(encoding="utf-8")
        assert V1_CONST in v1_text and V2_CONST not in v1_text
        pytest.skip(
            f"VACUITY: {_V2_TRAJECTORY_REL} absent this phase-stage — v2 shape law "
            f"proven on fixtures via the reference checkers above; retire when the "
            f"v2 schema lands.")
