"""The Cortex belief record — identity, canonical bytes, chained hash.

COG-2 UNIT 1 (deterministic-rebuild core). Plan:
docs/plans/cognitive-core-phase-2-contract-2026-07-22.md §4 (field-by-field),
§5.1 (canonical hash — rows not bytes), §5.6 (never-a-score confidence).

IDENTITY (rev 2): belief_id is a recorder-dialect digest of the tuple
(kind, subject_key, dimension, provenance.event_id, adapter_ordinal). It is
NOT keyed on claim bytes — identity MUST survive a source-content purge, and
event_id survives an outbox payload-NULL (§4, A-B3/C-F12). A build-time ULID
is the pinned sim-1 mutant.

CANONICAL DIALECT (G-F5): one dialect, one place. This module imports the
FROZEN recorder's pure canonicalization (`framework.evidence.recorder._canonical`
/ `_digest`) rather than minting a second hashing dialect — a deliberately
recorded coupling to a private germline symbol whose standing tripwire is the
recorder-vs-cortex byte-parity test. The chained hash re-parses and
re-canonicalizes each row (never hashes file bytes — A-m11).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

# The single canonicalization dialect (private frozen-recorder symbols —
# recorded coupling G-F5; byte-parity is the standing tripwire).
from framework.evidence.recorder import _canonical as _recorder_canonical
from framework.evidence.recorder import _digest as _recorder_digest
from framework.triggers import schema_registry

# Bumping any of these is a hash EPOCH BUMP (§5.1 A-m13), never a determinism
# regression — a new honest hash lineage.
ENGINE_VERSION = "cortex-engine/1"

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
    """The recorder-dialect canonical bytes: json.dumps(sort_keys, compact,
    ensure_ascii=False) -> utf-8. Reused verbatim (G-F5), never re-implemented."""
    return _recorder_canonical(value)


def digest(value: Any) -> str:
    """Recorder-dialect sha256 hexdigest of the canonical bytes."""
    return _recorder_digest(value)


def compute_belief_id(kind: str, subject_key: str, dimension: str,
                      event_id: str, adapter_ordinal: int) -> str:
    """DETERMINISTIC identity (§4, rev 2): a recorder digest of the identity
    tuple — explicitly NOT the claim bytes (survives content purge). A dict
    with named keys keeps the digest self-describing and reorder-proof."""
    return digest({
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

        acc = sha256(SEED); for b in sorted(beliefs): acc = sha256(acc || row)

    Re-canonicalizes each belief (rows, never file bytes — A-m11)."""
    ordered = sorted(beliefs, key=lambda b: b.belief_id)
    acc = hashlib.sha256(_BELIEF_HASH_SEED).digest()
    for belief in ordered:
        acc = hashlib.sha256(acc + canonical_bytes(belief.to_canonical_dict())).digest()
    return acc.hex()


def hash_canonical_rows(rows: Iterable[dict]) -> str:
    """Chained hash over already-parsed belief dicts (the JSONL-reader path).
    Sorts each row's derived collections and re-canonicalizes so a re-read of
    the store reproduces the fold-time hash iff the store is intact."""
    def _sorted_row(row: dict) -> dict:
        out = dict(row)
        if isinstance(out.get("supersedes"), list):
            out["supersedes"] = sorted(out["supersedes"])
        if isinstance(out.get("contradicts"), list):
            out["contradicts"] = sorted(out["contradicts"])
        return out

    ordered = sorted(rows, key=lambda r: r["belief_id"])
    acc = hashlib.sha256(_BELIEF_HASH_SEED).digest()
    for row in ordered:
        acc = hashlib.sha256(acc + canonical_bytes(_sorted_row(row))).digest()
    return acc.hex()


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
