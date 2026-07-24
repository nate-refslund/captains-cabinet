"""The Cortex belief record — identity, canonical bytes, chained hash.

COG-2 UNIT 1 (deterministic-rebuild core). Plan:
docs/plans/cognitive-core-phase-2-contract-2026-07-22.md §4 (field-by-field),
§5.1 (canonical hash — rows not bytes), §5.6 (never-a-score confidence).

IDENTITY (rev 2): belief_id is a recorder-dialect digest of the tuple
(kind, subject_key, dimension, provenance.event_id, adapter_ordinal). It is
NOT keyed on claim bytes — identity MUST survive a source-content purge, and
event_id survives an outbox payload-NULL (§4, A-B3/C-F12). A build-time ULID
is the pinned sim-1 mutant.

CANONICAL DIALECT (G-F5): one dialect, one place. This module ROUTES its
canonical bytes / digest / identity / chained-hash through the extracted
projection kernel (`framework.projection.kernel`, COG-4 §6.4) — the stdlib
replica of the frozen recorder dialect, byte-identical to the recorder (the
standing tripwires: test_cog2_rebuild_determinism + test_cog4_kernel_parity).
The chained hash re-parses each row (never hashes file bytes — A-m11).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

# Store disciplines route through the ONE extracted projection kernel (COG-4
# §6.4 adoption of §6.1 (a) canonical bytes + recorder-dialect digest, (b) the
# content-excluded identity law, (c) the parameterized chained rows-hash). The
# kernel replicates the recorder dialect in stdlib, byte-identical to
# framework.evidence.recorder._canonical — the standing tripwires are
# test_cog2_rebuild_determinism.TestCanonicalDialectParity (kernel==recorder)
# and test_cog4_kernel_parity. One dialect, one place; no second hashing
# dialect is minted here.
from framework.projection import kernel as _kernel
from framework.triggers import schema_registry

# Bumping any of these is a hash EPOCH BUMP (§5.1 A-m13), never a determinism
# regression — a new honest hash lineage.
# /2: D1 (§6.1) stamps local cabinet_id into consequence provenance -> belief
# store bytes change -> honest epoch bump (belief IDENTITIES stay stable —
# compute_belief_id excludes provenance except event_id, :77-87).
ENGINE_VERSION = "cortex-engine/2"

# Closed epistemic kind enum (foundry.md:89). Frozen per engine version.
KINDS: frozenset[str] = frozenset({
    "entity", "relationship", "resource", "capability", "commitment",
    "constraint", "risk", "hypothesis", "observation",
})

# Derived status, single-valued, pinned priority (§4).
STATUS_ASSERTED = "asserted"
STATUS_SUPERSEDED = "superseded"
STATUS_CONTRADICTED = "contradicted"
STATUS_SOURCE_PURGED = "source_purged"

# claim_completeness (§4).
COMPLETENESS_INLINE = "inline"
COMPLETENESS_REF_ONLY = "ref_only"
COMPLETENESS_PURGED = "purged"

# Domain-separation seed for the belief chain — distinct from the cog1 replay
# stream over the same bytes. Frozen; changing it changes every hash.
_BELIEF_HASH_SEED = b"cortex-belief-hash/v1"

_BELIEF_SCHEMA_ID = "cortex/belief@1"
_SOURCE_TRUST_SCHEMA_ID = "cortex/source-trust@1"


def canonical_bytes(value: Any) -> bytes:
    """The recorder-dialect canonical bytes (kernel-routed, §6.4 (a)): one
    dialect, one place. Byte-identical to the frozen recorder's _canonical for
    every serializable payload (the standing kernel==recorder tripwire)."""
    return _kernel.canonical_bytes(value)


def digest(value: Any) -> str:
    """Recorder-dialect sha256 hexdigest of the canonical bytes (kernel-routed)."""
    return _kernel.digest(value)


def compute_belief_id(kind: str, subject_key: str, dimension: str,
                      event_id: str, adapter_ordinal: int) -> str:
    """DETERMINISTIC identity (§4, rev 2): a recorder digest of the identity
    tuple — explicitly NOT the claim bytes (survives content purge). A dict
    with named keys keeps the digest self-describing and reorder-proof. Routed
    through the kernel's identity law (§6.4 (b)) — a content-excluded digest,
    never a build-time ULID."""
    return _kernel.identity_digest({
        "kind": kind,
        "subject_key": subject_key,
        "dimension": dimension,
        "event_id": event_id,
        "adapter_ordinal": adapter_ordinal,
    })


@dataclass(frozen=True)
class Belief:
    """One bitemporal belief. Frozen: the fold rebuilds, never mutates."""

    belief_id: str
    kind: str
    subject_key: str
    dimension: str
    adapter_ordinal: int
    claim: Optional[dict]
    claim_digest: Optional[str]
    source_time: Optional[str]
    observation_time: Optional[str]
    confidence: Optional[int]
    source_trust: dict
    provenance: dict
    status: str
    claim_completeness: str
    supersedes: tuple[str, ...] = field(default_factory=tuple)
    superseded_by: Optional[str] = None
    contradicts: tuple[str, ...] = field(default_factory=tuple)

    def to_canonical_dict(self) -> dict:
        """The dict that enters the canonical hash AND the JSONL row. Every
        derived collection is SORTED (C-F3 — the only defense that makes the
        bytes invariant to set/dict iteration order under PYTHONHASHSEED).
        Wall-clock bookkeeping / index ids / cache state are excluded by
        construction (they are not belief fields — §4 exclusion list)."""
        return {
            "belief_id": self.belief_id,
            "kind": self.kind,
            "subject_key": self.subject_key,
            "dimension": self.dimension,
            "adapter_ordinal": self.adapter_ordinal,
            "claim": self.claim,
            "claim_digest": self.claim_digest,
            "source_time": self.source_time,
            "observation_time": self.observation_time,
            "confidence": self.confidence,
            "source_trust": self.source_trust,
            "provenance": self.provenance,
            "supersedes": sorted(self.supersedes),
            "superseded_by": self.superseded_by,
            "contradicts": sorted(self.contradicts),
            "status": self.status,
            "claim_completeness": self.claim_completeness,
        }


def canonical_row(belief: Belief) -> str:
    """The canonical JSONL text for one belief (recorder dialect). Writer bytes
    equal re-derived bytes: this is exactly what the writer emits per line and
    exactly what the verifier re-canonicalizes (A-m11)."""
    return canonical_bytes(belief.to_canonical_dict()).decode("utf-8")


def chained_hash(beliefs: Iterable[Belief]) -> str:
    """The §5.1 chained SHA-256 over beliefs in belief_id order (canonical
    order — independent of fold-processing/arrival order by construction).
    Kernel-routed (§6.4 (c)): the sha256-chain algebra, the frozen domain seed,
    id-order; each belief's canonical dict is re-canonicalized by the kernel
    (rows, never file bytes — A-m11)."""
    # sorting the canonical dicts by belief_id == sorting the beliefs by
    # belief_id (belief_id is unique and preserved in to_canonical_dict), so the
    # chain input order — and thus the hash — is byte-identical to the prior
    # inline sha256 loop.
    return _kernel.chained_rows_hash(
        (b.to_canonical_dict() for b in beliefs),
        algebra=_kernel.ALGEBRA_SHA256_CHAIN, seed=_BELIEF_HASH_SEED,
        order_key=lambda row: row["belief_id"])


def hash_canonical_rows(rows: Iterable[dict]) -> str:
    """Chained hash over already-parsed belief dicts (the JSONL-reader path) —
    kernel-routed (§6.4 (c)). Each row's derived collections are sorted (the
    domain-side normalize, §6.2) and re-canonicalized so a re-read of the store
    reproduces the fold-time hash iff the store is intact."""
    def _sorted_row(row: dict) -> dict:
        out = dict(row)
        if isinstance(out.get("supersedes"), list):
            out["supersedes"] = sorted(out["supersedes"])
        if isinstance(out.get("contradicts"), list):
            out["contradicts"] = sorted(out["contradicts"])
        return out

    return _kernel.chained_rows_hash(
        rows, algebra=_kernel.ALGEBRA_SHA256_CHAIN, seed=_BELIEF_HASH_SEED,
        order_key=lambda row: row["belief_id"], normalize=_sorted_row)


def validate_belief(belief: Belief, *, root=None) -> tuple:
    """Resolve cortex/belief@1 + cortex/source-trust@1 via the schema registry
    and return the combined issue tuple (() == valid). NEVER raises (the
    registry path is fail-closed on a broken registration). This is a BOUNDARY
    check the write step runs — it is NOT called inside the pure fold."""
    issues = list(schema_registry.validate_payload(
        belief.to_canonical_dict(), _BELIEF_SCHEMA_ID, root=root))
    issues += list(schema_registry.validate_payload(
        belief.source_trust, _SOURCE_TRUST_SCHEMA_ID, root=root))
    return tuple(issues)


def belief_from_row(row: dict) -> Belief:
    """Reconstruct a Belief from a canonical JSONL row dict (the query/serve
    path — the inverse of to_canonical_dict). The frozen collections are
    restored to tuples; a re-canonicalization of the result reproduces the
    stored bytes (rows-not-bytes, A-m11)."""
    return Belief(
        belief_id=row["belief_id"],
        kind=row["kind"],
        subject_key=row["subject_key"],
        dimension=row["dimension"],
        adapter_ordinal=row["adapter_ordinal"],
        claim=row.get("claim"),
        claim_digest=row.get("claim_digest"),
        source_time=row.get("source_time"),
        observation_time=row.get("observation_time"),
        confidence=row.get("confidence"),
        source_trust=row["source_trust"],
        provenance=row["provenance"],
        status=row["status"],
        claim_completeness=row["claim_completeness"],
        supersedes=tuple(row.get("supersedes") or ()),
        superseded_by=row.get("superseded_by"),
        contradicts=tuple(row.get("contradicts") or ()),
    )
