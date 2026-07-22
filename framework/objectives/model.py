"""framework.objectives.model — records, canonical bytes, recorder-dialect
identity digests, and the graph-owned vocabulary for the shadow objective/value
graph (COG-3 contract rev-1 §4).

CANONICAL DIALECT: identity digests reuse the FROZEN recorder's dialect
(json.dumps(sort_keys, compact, ensure_ascii=False) -> utf-8 -> sha256) exactly
as framework.cortex.belief.digest does (framework.evidence.recorder._canonical /
_digest). The dialect is REPLICATED here in stdlib rather than imported: the
symbol-level import pin (§6.5 bullet 3) admits ONLY the seven cortex query-surface
symbols, so framework.evidence.recorder / framework.cortex.belief are RED. Byte
parity with the recorder is verified against belief.digest at build time.

SCHEMA VALIDATION: `load_schema` resolves the objectives domain schema by its
registry PATH and returns the parsed document. It does NOT run jsonschema in-tree
(a third-party import is RED under the §6.5 pin); callers validate with the
reference Draft-2020-12 engine (the cross-check idiom at
test_schema_registry.py:301-354), exactly as the COG-3 schema suites do.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; U1 (the derivation core).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# --- id patterns (§4.2/§4.3) — DISJOINT namespaces, mirrored in the schemas ---
BELIEF_ID_RE = "^[0-9a-f]{64}$"
PREDICTION_ID_RE = "^pred-[0-9a-f]{64}$"

# --- the graph-owned CLOSED node-kind enum (§4.1) — NOT the belief kind enum ---
NODE_KINDS = frozenset({
    "direction_root", "objective", "outcome", "constraint",
    "instrument", "intervention",
})
# causal edges terminate on these ONLY — instrument is never a legal target (:110).
CAUSAL_TARGET_KINDS = frozenset({"outcome", "constraint"})
# relational (non-causal, no epistemic machinery) edge kinds; `indicates` is the
# instrument->outcome trend link the §5.6 divergence report needs.
RELATIONAL_KINDS = frozenset({"indicates", "depends_on", "conflicts_with", "derives_from"})
# the sanctioned (source_kind, target_kind) pairs for the `indicates` relation.
INDICATES_ALLOWED = frozenset({("instrument", "outcome")})

_SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas" / "domains" / "objectives"


# ===========================================================================
# Canonical bytes + recorder-dialect digest (replicated stdlib dialect)
# ===========================================================================

def canonical_bytes(value: Any) -> bytes:
    """Recorder-dialect canonical bytes: compact, sort_keys, ensure_ascii=False,
    utf-8. Byte-identical to framework.evidence.recorder._canonical (G-F5)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    """Recorder-dialect sha256 hexdigest of the canonical bytes — byte-identical
    to framework.cortex.belief.digest (verified against it at build time)."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def node_id(kind: str, subject_key: str) -> str:
    """DETERMINISTIC recorder-dialect digest of (kind, subject_key) — never a
    build-time ULID (COG-2 identity law; survives content change, §4.1)."""
    return digest([kind, subject_key])


def edge_id(source_node_id: str, target_node_id: str, discriminator: str,
            *, family: str) -> str:
    """Digest of (family, source, target, discriminator) — identity EXCLUDES
    content, so a directional restatement is an honest content change on a stable
    edge (§4.2). `family` ('causal'/'relational') is prefixed into the digest so a
    causal `dimension` string equal to a relation token (e.g. 'depends_on') can
    never collide ids with a relational edge between the SAME two nodes."""
    return digest([family, source_node_id, target_node_id, discriminator])


def prediction_id(*parts: Any) -> str:
    """A `pred-`-prefixed recorder digest (§4.3) — disjoint from the belief-id
    namespace by construction, so a prediction id is structurally unciteable."""
    return "pred-" + digest(list(parts))


# ===========================================================================
# Structural guards (§4.2 — build-fold, never a schema rejection)
# ===========================================================================

def assert_legal_causal_target(target_kind: str) -> None:
    """SIM-4 structural rule (§4.2, :110): a causal edge may terminate ONLY on an
    outcome/constraint node — an instrument is never a legal causal target. Raises
    the canonical structural-failure type (states.BuildFailure); `indicates`
    (instrument->outcome) stays legal as a relational edge with no epistemic
    machinery."""
    if target_kind not in CAUSAL_TARGET_KINDS:
        # lazy import keeps model import-inert and avoids a load-time cycle with
        # states (which imports model for the digest); the symbol is internal.
        from framework.objectives.states import BuildFailure
        raise BuildFailure(
            f"illegal causal target kind {target_kind!r}: a causal edge may "
            f"terminate only on {sorted(CAUSAL_TARGET_KINDS)} (instruments remain "
            "trend evidence, never targets — :110)")


def load_schema(name: str) -> dict:
    """Load an objectives domain schema by its registry PATH (stdlib only). The
    caller validates with the reference Draft-2020-12 engine (§6.5 forbids a
    third-party import in-tree)."""
    return json.loads((_SCHEMAS_DIR / f"{name}.v1.json").read_text(encoding="utf-8"))


# ===========================================================================
# Records (§4) — canonical-bytes serializable; digests are identity, never ULID
# ===========================================================================

@dataclass(frozen=True)
class Node:
    """A graph node (§4.1). `root_ref` is REQUIRED on objective nodes (schema);
    resolvability is a graph.py build-fold check (U2), never a schema rejection."""
    kind: str
    subject_key: str
    root_ref: Optional[dict] = None
    reversibility: Optional[str] = None
    captain_attention_cost: Optional[str] = None
    join_spec: tuple = ()
    floors: Optional[dict] = None

    @property
    def node_id(self) -> str:
        return node_id(self.kind, self.subject_key)

    def to_canonical_dict(self) -> dict:
        out: dict = {"node_id": self.node_id, "kind": self.kind,
                     "subject_key": self.subject_key}
        if self.root_ref is not None:
            out["root_ref"] = self.root_ref
        if self.reversibility is not None:
            out["reversibility"] = self.reversibility
        if self.captain_attention_cost is not None:
            out["captain_attention_cost"] = self.captain_attention_cost
        if self.join_spec:
            out["join_spec"] = [list(m) for m in self.join_spec]
        if self.floors is not None:
            out["floors"] = self.floors
        return out


@dataclass(frozen=True)
class CausalEdge:
    """A causal edge intervention -> outcome/constraint (§4.2). Epistemic state is
    NEVER stored here — it is derived at compile (states.derive_edge_state)."""
    source_node_id: str
    target_node_id: str
    target_kind: str
    dimension: str
    expected_effect: str
    admissible_subjects: tuple = ()
    evidence_bindings: tuple = ()
    assumptions: tuple = ()
    uncertainty: Optional[str] = None

    @property
    def edge_id(self) -> str:
        return edge_id(self.source_node_id, self.target_node_id, self.dimension,
                       family="causal")

    def to_canonical_dict(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "target_kind": self.target_kind,
            "dimension": self.dimension,
            "expected_effect": self.expected_effect,
            "admissible_subjects": sorted(self.admissible_subjects),
            "evidence_bindings": list(self.evidence_bindings),
            "assumptions": list(self.assumptions),
            "uncertainty": self.uncertainty if self.uncertainty is not None else "unknown",
        }


@dataclass(frozen=True)
class RelationalEdge:
    """A relational edge (§4.2) — depends_on/conflicts_with/derives_from/indicates
    with NO epistemic machinery; conflicts stored symmetric + SORTED."""
    source_node_id: str
    target_node_id: str
    relation: str
    dimension: Optional[str] = None

    @property
    def edge_id(self) -> str:
        return edge_id(self.source_node_id, self.target_node_id, self.relation,
                       family="relational")

    def to_canonical_dict(self) -> dict:
        out = {"edge_id": self.edge_id, "source_node_id": self.source_node_id,
               "target_node_id": self.target_node_id, "relation": self.relation}
        if self.dimension is not None:
            out["dimension"] = self.dimension
        return out


@dataclass(frozen=True)
class Prediction:
    """A counterfactual prediction record (§4.3) — an ORIGINAL record in its OWN
    store, EXCLUDED from N1, with a disjoint `pred-` id namespace."""
    edge_id: str
    assumption_set: dict
    cutoff: str
    predicted_claim: dict
    made_at_epoch: Any = None

    @property
    def prediction_id(self) -> str:
        return prediction_id(self.edge_id, self.assumption_set, self.cutoff)

    def to_canonical_dict(self) -> dict:
        return {
            "prediction_id": self.prediction_id,
            "edge_id": self.edge_id,
            "assumption_set": self.assumption_set,
            "cutoff": self.cutoff,
            "predicted_claim": self.predicted_claim,
            "made_at_epoch": self.made_at_epoch,
        }


@dataclass(frozen=True)
class ScorecardDimension:
    """One per-dimension scorecard cell (§4.4). Absent `value` => unknown, and
    unknown NEVER passes a floor. No aggregation exists over the vector."""
    floor: float
    value: Optional[float] = None
    evidence_binding_refs: tuple = ()

    def to_canonical_dict(self) -> dict:
        out: dict = {"floor": self.floor}
        if self.value is not None:
            out["value"] = self.value
        if self.evidence_binding_refs:
            out["evidence_binding_refs"] = list(self.evidence_binding_refs)
        return out
