"""COG-4 §5.5 — trajectory v2 landed-surface battery (version dispatch + the
v2 Draft-2020-12 document).

Contract: docs/plans/cognitive-core-phase-4-contract-2026-07-23.md §5.5
(version-dispatched trajectory v2, MR5) + §5.2 (the ONE enforcement descriptor).
This suite binds the REAL landed W4 surface — the new
`framework/schemas/cognitive-trajectory.v2.schema.json` and the version
dispatch added to `framework/evolution/contracts.py` — where the W2-t3 corpus
(`test_cog4_organ_manifest.py`) proved the shape on reference checkers only.

The dispatch clones the framework/triggers/envelope.py classify-then-dispatch
precedent (cited by bytes in the contract): the schema version is decided FIRST,
before the v1 closed-set check, so a v2 record can never be refused by v1's
const/closed-key set, and every v1 instance stays byte-identical. Trajectory's
two versions BOTH carry schema_version (unlike the envelope's absent-vs-present
marker), so the dispatch marker is the exact v2 literal value.

Laws proven here:
  * dispatch decided before the v1 checks — a valid v2 record passes
    structural_issues (routed to v2, NOT refused by v1's const); the
    envelope-precedent v1-first inversion would have refused it
  * v1 frozen — the v1 path is byte-identical (structural_issues on a v1
    record == the raw v1-schema interpretation)
  * forged-version mutants — an unknown schema_version, a v2 body tagged v1,
    and a v1 body tagged v2 are each REJECTED
  * never-overload (§5.5 / charter L184) — a namespaced id in `action_type`
    fails; the granular id lives ONLY in domain_operation
  * the §5.2 enforcement descriptor block — capability/action_type/risk_class/
    ceiling/undo_contract shapes, grounded to the REAL 13 RISK_CLASSES and the
    contracts.py undo grammar
  * wiring pins — the v2 route goes THROUGH the v2 seam; a v1/forged record
    never reaches it (monkeypatch mutants, the envelope suite idiom)

S0: python3.12, no DB, no network, deterministic. NEW file (corpus law §13 —
no existing test touched). Provenance: authored per the 2026-07-07
full-autonomy grant + the 2026-07-20 cognitive-masterplan continuous grant
(COG-4 W4, trajectory v2 unit).
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from framework.authority import matrix as authority_matrix       # noqa: E402
from framework.authority.classifier import ACTION_TYPES          # noqa: E402
from framework.evolution import contracts as C                   # noqa: E402

_V2_SCHEMA_PATH = _REPO / "framework" / "schemas" / "cognitive-trajectory.v2.schema.json"
_V1_SCHEMA_PATH = _REPO / "framework" / "schemas" / "cognitive-trajectory.schema.json"

V1_CONST = "cognitive-trajectory/v1"
V2_CONST = "cognitive-trajectory/v2"
STATUS_ENUM = ("proposed", "denied", "attempted", "verified", "failed",
               "reversed", "violation")
DOMAIN_OP_RE = re.compile(r"^[a-z0-9_-]+/[a-z0-9._-]+$")
_DIGEST = "sha256:" + "0" * 64


# ---------------------------------------------------------------------------
# fixtures — the garden-rota domain (non-software vocabulary by design, §12 N8);
# factory functions so every call yields FRESH dict objects (the trajectory
# envelope walker rejects shared object aliases as a cycle).
# ---------------------------------------------------------------------------
def _ref(name: str) -> dict:
    return {"ref": name, "digest": _DIGEST}


def _costs() -> dict:
    return {
        "tokens": 1,
        "tool_calls": 0,
        "latency_ms": 0,
        "external_spend_microunits": 0,
        "resource_receipt_ref": _ref("receipt:resource"),
    }


def _v2_effect() -> dict:
    """A full v2 effect — every v1 member kept INCLUDING action_type (a bare
    closed-30 compat member) plus the two required v2 additions."""
    return {
        "effect_id": "effect-0001",
        "action_type": "investigation_run",
        "domain_operation": {"organ": "garden-rota",
                             "operation": "garden/rota.compile"},
        "enforcement_descriptor": {
            "capability": "garden/rota.compile",
            "action_type": "investigation_run",
            "risk_class": "read_only_dispatch",
            "ceiling": [],
            "undo_contract": "none",
        },
        "status": "proposed",
        "idempotency_key": "garden-rota",
        "requested_at": "2026-07-19T11:54:00Z",
        "decision_at": "2026-07-19T12:00:00Z",
        "observed_at": "2026-07-19T12:15:00Z",
        "classification_receipt_ref": _ref("receipt:classification"),
        "authority_decision_ref": _ref("receipt:authorization"),
        "effect_receipt_ref": _ref("receipt:effect"),
        "undo_receipt_ref": _ref("receipt:undo"),
    }


def _base_record() -> dict:
    """The shared trajectory envelope (v1 top-level shape, which v2 keeps
    verbatim). Callers stamp schema_version + effects."""
    return {
        "trajectory_id": "trajectory-garden-001",
        "record_kind": "live",
        "authority_scope": {"cabinet_id": "cabinet-garden", "scope_kind": "cabinet"},
        "execution_scope": {"run_id": "run-1", "correlation_id": "corr-1",
                            "causation_id": "cause-1"},
        "started_at": "2026-07-19T10:00:00Z",
        "decision_cutoff_at": "2026-07-19T12:00:00Z",
        "completed_at": "2026-07-19T13:00:00Z",
        "genome": {
            "candidate_id": "candidate-1", "candidate_version": "v1",
            "incumbent_id": "incumbent-1", "incumbent_version": "v0",
            "manifest_ref": _ref("artifact:genome-manifest"),
            "component_refs": [_ref("artifact:genome")],
        },
        "intent": {"objective_refs": [_ref("artifact:objective")],
                   "constraint_refs": []},
        "input_snapshots": [{
            "snapshot_id": "snapshot-1", "artifact_ref": _ref("artifact:snapshot"),
            "maximum_content_time": "2026-07-19T11:30:00Z",
        }],
        "spans": [{
            "span_id": "span-1", "status": "completed", "kind": "decision",
            "causation_id": "cause-1",
            "started_at": "2026-07-19T10:30:00Z",
            "completed_at": "2026-07-19T11:50:00Z",
            "genome_component_refs": [_ref("artifact:genome")],
            "model_refs": [], "tool_refs": [], "skill_refs": [], "context_refs": [],
            "input_refs": [_ref("artifact:snapshot")],
            "output_refs": [_ref("artifact:output")],
            "confidence_ppm": 700000, "costs": _costs(),
        }],
        "machine_outcomes": [], "human_verdicts": [], "judge_observations": [],
        "evaluation_basis": "machine_verifiable",
        "costs": _costs(),
        "run_attestation_ref": _ref("receipt:run-attestation"),
        "classification": "internal",
    }


def v2_record() -> dict:
    r = _base_record()
    r["schema_version"] = V2_CONST
    r["effects"] = [_v2_effect()]
    return r


def v1_record() -> dict:
    """A structurally-valid v1 record — the v1 effect has NO domain_operation /
    enforcement_descriptor and its action_type is a plain v1 id."""
    r = _base_record()
    r["schema_version"] = V1_CONST
    r["effects"] = [{
        "effect_id": "effect-0001",
        "action_type": "local_edit",
        "status": "proposed",
        "idempotency_key": "garden-rota",
        "requested_at": "2026-07-19T11:54:00Z",
        "decision_at": "2026-07-19T12:00:00Z",
        "observed_at": "2026-07-19T12:15:00Z",
        "classification_receipt_ref": _ref("receipt:classification"),
        "authority_decision_ref": _ref("receipt:authorization"),
        "effect_receipt_ref": _ref("receipt:effect"),
        "undo_receipt_ref": _ref("receipt:undo"),
    }]
    return r


# ---------------------------------------------------------------------------
# the landed surface must actually exist (this whole suite is the retirement of
# the W2-t3 vacuity arm; if the schema regresses out, fail loud not skip)
# ---------------------------------------------------------------------------
def test_v2_schema_and_dispatch_have_landed():
    assert _V2_SCHEMA_PATH.is_file(), "the v2 schema document must be present"
    assert C.TRAJECTORY_V2_SCHEMA == _V2_SCHEMA_PATH
    assert C.V1_SCHEMA_VERSION == V1_CONST
    assert C.V2_SCHEMA_VERSION == V2_CONST
    # v1 stays frozen and validator-only — no v2 const leaked into the v1 file
    v1_text = _V1_SCHEMA_PATH.read_text(encoding="utf-8")
    assert V1_CONST in v1_text and V2_CONST not in v1_text


def test_v2_schema_is_full_draft_2020_12():
    doc = json.loads(_V2_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert doc["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert doc["properties"]["schema_version"]["const"] == V2_CONST
    assert doc["additionalProperties"] is False
    # $defs (a 2020-12 keyword), never draft-07 "definitions"
    assert "$defs" in doc and "definitions" not in doc


def test_v2_effect_keeps_every_v1_field_and_adds_the_two_required():
    """§5.5 — the effect def keeps every v1 field INCLUDING action_type and ADDS
    required domain_operation + enforcement_descriptor."""
    v1 = json.loads(_V1_SCHEMA_PATH.read_text(encoding="utf-8"))
    v2 = json.loads(_V2_SCHEMA_PATH.read_text(encoding="utf-8"))
    v1_eff, v2_eff = v1["$defs"]["effect"], v2["$defs"]["effect"]
    # every v1 effect property survives (superset), incl. action_type
    assert set(v1_eff["properties"]) <= set(v2_eff["properties"])
    assert "action_type" in v2_eff["properties"]
    # the two new required members
    assert set(v2_eff["properties"]) - set(v1_eff["properties"]) == {
        "domain_operation", "enforcement_descriptor"}
    assert "domain_operation" in v2_eff["required"]
    assert "enforcement_descriptor" in v2_eff["required"]
    # every v1 required member is still required
    assert set(v1_eff["required"]) <= set(v2_eff["required"])


# ---------------------------------------------------------------------------
# version dispatch — decided BEFORE the v1 closed-set check (§5.5)
# ---------------------------------------------------------------------------
class TestVersionDispatch:
    def test_valid_v2_routes_to_v2_and_is_not_refused_by_v1_const(self):
        """The version-first law: a valid v2 record passes structural_issues —
        it is judged by the v2 schema, never refused by v1's schema_version
        const (the exact misroute the envelope precedent forbids)."""
        assert C.structural_issues(v2_record()) == ()
        assert C._is_v2_record(v2_record()) is True

    def test_v1_record_routes_to_v1_frozen_byte_identical(self):
        """v1 stays frozen: structural_issues on a v1 record is byte-identical
        to the raw v1-schema interpretation (the dispatch adds nothing for v1)."""
        rec = v1_record()
        assert C._is_v2_record(rec) is False
        assert C.structural_issues(rec) == ()
        assert C.structural_issues(rec) == C._structural_issues(rec, C.TRAJECTORY_SCHEMA)

    def test_forged_version_routes_to_v1_and_is_rejected(self):
        """A forged/unknown schema_version is NOT the v2 marker — it falls to the
        frozen v1 path and dies on v1's const check."""
        for bad in ("cognitive-trajectory/v9", "cognitive-trajectory/v3",
                    "cognitive-trajectory/v2 ", " cognitive-trajectory/v2",
                    "trajectory/v2", "", "cognitive-trajectory/V2"):
            rec = v2_record()
            rec["schema_version"] = bad
            assert C._is_v2_record(rec) is False, bad
            assert C.structural_issues(rec), f"forged {bad!r} must be rejected"

    def test_v2_body_tagged_v1_dies_on_the_v1_closed_set(self):
        """A v2-shaped body carrying the v1 literal dispatches to frozen v1 and
        dies on its closed key set (the effect's domain_operation is an unknown
        key under v1's additionalProperties:false)."""
        rec = v2_record()
        rec["schema_version"] = V1_CONST
        assert C._is_v2_record(rec) is False
        issues = C.structural_issues(rec)
        assert issues
        assert any("additionalProperties" in i.code for i in issues)

    def test_v1_body_tagged_v2_dies_on_missing_v2_fields(self):
        """A v1-shaped body carrying the v2 literal dispatches to v2 and dies on
        the missing required v2 fields — you cannot tag a v1 body as v2."""
        rec = v1_record()
        rec["schema_version"] = V2_CONST
        assert C._is_v2_record(rec) is True
        issues = C.structural_issues(rec)
        assert issues
        assert any("required" in i.code for i in issues)

    def test_non_dict_routes_v1_and_never_raises(self):
        for garbage in (None, [], "x", 3, 3.5):
            assert C._is_v2_record(garbage) is False
            assert C.structural_issues(garbage)  # rejected, no exception

    def test_marker_is_the_exact_literal(self):
        assert C._is_v2_record({"schema_version": V2_CONST}) is True
        assert C._is_v2_record({"schema_version": V1_CONST}) is False
        assert C._is_v2_record({}) is False


# ---------------------------------------------------------------------------
# wiring pins — the v2 route goes THROUGH the v2 seam; v1/forged never reach it
# (monkeypatch mutants — the framework/triggers/tests/test_envelope_v2.py idiom)
# ---------------------------------------------------------------------------
class TestDispatchWiringPins:
    def test_v2_route_goes_through_the_v2_seam(self, monkeypatch):
        """An invalid v2 record is rejected normally; stubbing the v2 seam clean
        flips it to accepted — proof structural_issues routes v2 THROUGH the
        seam (the envelope test_dispatch_wiring_mutant_v2_route analog)."""
        bad = v2_record()
        bad["effects"][0].pop("domain_operation")
        assert C.structural_issues(bad)
        monkeypatch.setattr(C, "_structural_issues_v2", lambda record: ())
        assert C.structural_issues(bad) == ()

    def test_v1_and_forged_never_touch_the_v2_seam(self, monkeypatch):
        """Booby-trap the v2 seam: a v1 record and a forged-version record must
        validate without ever reaching it (the envelope
        test_dispatch_wiring_v1_route_never_touches_v2 analog)."""
        def boom(record):
            raise AssertionError("the v1/forged route must never call the v2 seam")
        monkeypatch.setattr(C, "_structural_issues_v2", boom)
        assert C.structural_issues(v1_record()) == ()          # v1 literal
        forged = v2_record()
        forged["schema_version"] = "cognitive-trajectory/v9"
        assert C.structural_issues(forged)                     # forged -> v1, rejected


# ---------------------------------------------------------------------------
# the v2 schema — accept/reject table (structural, against the REAL document)
# ---------------------------------------------------------------------------
class TestV2SchemaShape:
    def test_valid_garden_rota_fixture_passes(self):
        assert C.structural_issues(v2_record()) == ()

    def test_namespaced_action_type_rejected(self):
        """§5.5 never-overload (charter L184): a namespaced id in action_type
        fails — the granular id lives ONLY in domain_operation."""
        rec = v2_record()
        rec["effects"][0]["action_type"] = "garden/water.plots"
        issues = C.structural_issues(rec)
        assert issues
        assert any(i.path.endswith(".action_type") and "pattern" in i.code
                   for i in issues), [(_i.code, _i.path) for _i in issues]

    def test_every_action_types_member_is_an_acceptable_compat_member(self):
        """All 30 closed compat members pass the v2 action_type pattern; none
        carry a '/', so the never-overload pattern never rejects a real one."""
        doc = json.loads(_V2_SCHEMA_PATH.read_text(encoding="utf-8"))
        pat = re.compile(doc["$defs"]["compatActionType"]["pattern"])
        assert len(ACTION_TYPES) == 30
        for member in ACTION_TYPES:
            assert "/" not in member
            assert pat.match(member), member
        # a full record with each member as action_type validates
        for member in sorted(ACTION_TYPES):
            rec = v2_record()
            rec["effects"][0]["action_type"] = member
            rec["effects"][0]["enforcement_descriptor"]["action_type"] = member
            assert C.structural_issues(rec) == (), member

    @pytest.mark.parametrize("member", ["domain_operation", "enforcement_descriptor"])
    def test_missing_required_v2_member_rejected(self, member):
        rec = v2_record()
        rec["effects"][0].pop(member)
        assert C.structural_issues(rec)

    def test_domain_operation_shape(self):
        # extra key rejected (additionalProperties:false)
        rec = v2_record()
        rec["effects"][0]["domain_operation"]["extra"] = "x"
        assert C.structural_issues(rec)
        # empty organ rejected
        rec = v2_record()
        rec["effects"][0]["domain_operation"]["organ"] = ""
        assert C.structural_issues(rec)
        # flat (non-namespaced) operation rejected
        rec = v2_record()
        rec["effects"][0]["domain_operation"]["operation"] = "flatop"
        assert C.structural_issues(rec)
        # missing organ / operation each rejected
        for k in ("organ", "operation"):
            rec = v2_record()
            rec["effects"][0]["domain_operation"].pop(k)
            assert C.structural_issues(rec), k
        # the fixture's namespaced operation matches the §4.2 id shape
        assert DOMAIN_OP_RE.fullmatch(
            v2_record()["effects"][0]["domain_operation"]["operation"])

    def test_enforcement_descriptor_members(self):
        # flat (non-namespaced) capability rejected
        rec = v2_record()
        rec["effects"][0]["enforcement_descriptor"]["capability"] = "flatcap"
        assert C.structural_issues(rec)
        # risk_class outside the closed 13 rejected
        rec = v2_record()
        rec["effects"][0]["enforcement_descriptor"]["risk_class"] = "banana"
        assert C.structural_issues(rec)
        # undo grammar enforced
        for bad in ("delete_window()", "delete_window(-1)", "journal:", "NONE", ""):
            rec = v2_record()
            rec["effects"][0]["enforcement_descriptor"]["undo_contract"] = bad
            assert C.structural_issues(rec), bad
        # the full undo grammar accepts all three spellings
        for good in ("none", "delete_window(3600)", "journal:garden-flush"):
            rec = v2_record()
            rec["effects"][0]["enforcement_descriptor"]["undo_contract"] = good
            assert C.structural_issues(rec) == (), good
        # each of the four descriptor members is required
        for m in ("capability", "action_type", "risk_class", "ceiling",
                  "undo_contract"):
            rec = v2_record()
            rec["effects"][0]["enforcement_descriptor"].pop(m)
            assert C.structural_issues(rec), m
        # a namespaced descriptor.action_type is refused too (never-overload)
        rec = v2_record()
        rec["effects"][0]["enforcement_descriptor"]["action_type"] = "garden/water.plots"
        assert C.structural_issues(rec)

    def test_risk_class_enum_matches_the_real_matrix(self):
        """Vocabulary drift REDs honestly: the schema's inline 13-member enum
        equals framework.authority.matrix.RISK_CLASSES."""
        doc = json.loads(_V2_SCHEMA_PATH.read_text(encoding="utf-8"))
        inline = doc["$defs"]["enforcementDescriptor"]["properties"]["risk_class"]["enum"]
        assert set(inline) == set(authority_matrix.RISK_CLASSES)
        assert len(inline) == 13

    def test_status_enum_is_the_seven(self):
        rec = v2_record()
        rec["effects"][0]["status"] = "succeeded"
        assert C.structural_issues(rec)
        doc = json.loads(_V2_SCHEMA_PATH.read_text(encoding="utf-8"))
        assert set(doc["$defs"]["effect"]["properties"]["status"]["enum"]) == set(STATUS_ENUM)

    def test_attempted_at_conditional_preserved(self):
        # proposed must NOT carry attempted_at
        rec = v2_record()
        rec["effects"][0]["attempted_at"] = "2026-07-19T12:01:00Z"
        assert C.structural_issues(rec)
        # an acted status REQUIRES attempted_at
        rec = v2_record()
        rec["effects"][0]["status"] = "verified"
        assert C.structural_issues(rec)
        rec = v2_record()
        rec["effects"][0]["status"] = "verified"
        rec["effects"][0]["attempted_at"] = "2026-07-19T12:01:00Z"
        assert C.structural_issues(rec) == ()


def test_semantic_layer_runs_on_v2_without_crashing():
    """action_type is still validated at semantic-check time (§5.5): the v1
    semantic path runs over a v2 record's shared fields and, absent trusted
    context, fails closed with context_required — never raising."""
    issues = C.semantic_issues(v2_record(), None)
    assert any(i.code == "verification.context_required" for i in issues)
