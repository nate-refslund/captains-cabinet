"""Field-classification doctrine for evidence events (design §2.2 R1).

Every evidence event is stamped ``trust: untrusted_observation``.  This
module refines that blanket label into a per-field trust class so a later
fuel-integrity check (Phase 4) can reason about which fields may ever carry
weight, without re-litigating provenance per consumer:

``producer_asserted``
    The value entered through a producer's call.  The plane preserves it
    faithfully (sanitized, hashed, signed) but cannot vouch for its truth.
    A producer-asserted field is NEVER fuel-bearing on its own; at most it
    is a pointer that an independent checker may later corroborate.

``independently_established``
    The value is minted or re-derived by Ring-0 evidence code itself
    (recorder/verifier) independent of the producer: identifiers the
    recorder mints, the wall/monotonic clocks it reads, the hash chain,
    signatures, and sequence numbers the verifier re-derives from raw
    bytes.  Integrity-established is still not authority: these fields
    prove ordering and tamper-evidence, not that the described action was
    good.

Doctrine (Phase 1, ratified with the v1.1 vocabulary wave):

- TODAY every ``detail`` key is producer-asserted.  Promoting a key to
  independently_established requires the independent checker to actually
  exist (e.g. a lineage walker that resolves ``parent_trial_id`` against
  the store) and is a ceremony-gated content change to this registry.
- ``component.version`` / ``component.commit`` may fall back to the
  ``CABINET_BUILD_VERSION`` / ``CABINET_GIT_COMMIT`` environment variables
  (the A10 seam).  Env-derived provenance is UNTRUSTED and never
  fuel-bearing — no officer-controlled environment variable may ever feed
  an autonomy or trust decision.
- R-4 model/effort/skill provenance (``model_id``, ``effort_tier``,
  ``skill_revision``) must be sourced from broker/runtime state, never
  from environment variables, and stays producer-asserted until a broker
  attestation path exists.
- R-3 trial lineage is structured: a child trial minted by delegation or
  re-mint carries :data:`LINEAGE_KEY` in its genesis event ``detail``.
  The namespaced ``links`` entry (:data:`LINEAGE_LINK_PREFIX` + parent
  trial id) is an optional human-followable mirror; the structured detail
  key is authoritative.
- Never-a-score: cost/resource observations are recorded for the Captain's
  audit but are excluded from the officer projection
  (``recorder.PROJECTION_ALLOWED_DETAIL``) so no evidence-derived
  aggregate can drift into a score or gate.

This module is deliberately not imported by the recorder or verifier —
classification is doctrine consumed by audits, tests, and the Phase-4
fuel-integrity check, never a runtime behavior switch.
"""
from __future__ import annotations

from types import MappingProxyType

PRODUCER_ASSERTED = "producer_asserted"
INDEPENDENTLY_ESTABLISHED = "independently_established"
CLASSES = frozenset({PRODUCER_ASSERTED, INDEPENDENTLY_ESTABLISHED})

# R-3 structured lineage convention (see module doctrine above).
LINEAGE_KEY = "parent_trial_id"
LINEAGE_LINK_PREFIX = "evidence-parent:"

# Dotted top-level fields whose values can be sourced from environment
# variables.  UNTRUSTED (A10): never fuel-bearing, never an authority input.
UNTRUSTED_ENV_PROVENANCE = frozenset({"component.version", "component.commit"})

# Fields that must never feed an autonomy/trust/fuel decision regardless of
# any future attestation work.  Superset of the env-provenance seam.
NEVER_FUEL_BEARING = frozenset(UNTRUSTED_ENV_PROVENANCE)

# Reserved detail vocabulary added by the v1.1 wave.  Names deliberately
# avoid redaction.SECRET_KEY_RE collisions (e.g. ``input_tokens`` not
# ``token_count``; ``parent_trial_id`` never a ``*_session_id`` shape) so
# values survive sanitize; the vocabulary test enforces this.
RESERVED_DETAIL_KEYS_V11 = frozenset({
    # Delegation / spawn lineage (R-3).
    "parent_trial_id", "spawned_by", "delegation_depth",
    # Scheduled-trigger provenance (pairs with missed/skipped/expired).
    "scheduled_by", "trigger_kind", "scheduled_for",
    # Egress approval reference — an opaque approval id, never a
    # destination (URLs with userinfo and emails are redacted by value).
    "egress_approval_ref",
    # Cost/resource observations (never officer-projected — never-a-score).
    "input_tokens", "output_tokens", "cost_usd", "resource_kind",
    # Model/effort/skill provenance from broker/runtime state (R-4).
    "model_id", "effort_tier", "skill_revision",
})

# Top-level event fields.  Recorder-minted / verifier-re-derived fields are
# independently established; everything a producer supplies is asserted.
EVENT_FIELD_CLASSIFICATION = MappingProxyType({
    "schema": INDEPENDENTLY_ESTABLISHED,
    "event_id": INDEPENDENTLY_ESTABLISHED,
    "sequence": INDEPENDENTLY_ESTABLISHED,
    "ts": INDEPENDENTLY_ESTABLISHED,
    "timing": INDEPENDENTLY_ESTABLISHED,
    "redactions": INDEPENDENTLY_ESTABLISHED,
    "diagnostic_mode": INDEPENDENTLY_ESTABLISHED,
    "trust": INDEPENDENTLY_ESTABLISHED,
    "previous_hash": INDEPENDENTLY_ESTABLISHED,
    "event_hash": INDEPENDENTLY_ESTABLISHED,
    "signature": INDEPENDENTLY_ESTABLISHED,
    "trial_id": PRODUCER_ASSERTED,
    "trace_id": PRODUCER_ASSERTED,
    "action_id": PRODUCER_ASSERTED,
    "correlation_id": PRODUCER_ASSERTED,
    "phase": PRODUCER_ASSERTED,
    "status": PRODUCER_ASSERTED,
    "surface": PRODUCER_ASSERTED,
    "actor": PRODUCER_ASSERTED,
    "component": PRODUCER_ASSERTED,
    "detail": PRODUCER_ASSERTED,
    "links": PRODUCER_ASSERTED,
})

# Detail keys: the established v1 vocabulary (the projection allow-list and
# the onboarding producer's bounded keys) plus the v1.1 reserved keys.
# Phase-1 doctrine: ALL detail keys are producer-asserted today.
DETAIL_FIELD_CLASSIFICATION = MappingProxyType({key: PRODUCER_ASSERTED for key in (
    # v1 vocabulary already in officer projection or onboarding producer use.
    "action", "error_code", "reason_code", "result_code", "file_count",
    "total_bytes", "excluded", "verification", "source_integrity",
    "feedback_rating", "feedback_category", "transport", "retry_count",
    "revision", "before_revision", "after_revision", "receipt_id",
    "undo_of", "manifest_hash", "charter_hash", "purge_scope",
    "requested_surface", "request_shape_valid", "authority_effect",
    "purged_trial_id_hash",
    # v1.1 reserved vocabulary.
    "parent_trial_id", "spawned_by", "delegation_depth",
    "scheduled_by", "trigger_kind", "scheduled_for",
    "egress_approval_ref",
    "input_tokens", "output_tokens", "cost_usd", "resource_kind",
    "model_id", "effort_tier", "skill_revision",
)})


def classify_detail_key(key: str) -> str:
    """Return the trust class for a detail key.

    Unregistered keys default to ``producer_asserted`` — the fail-closed
    reading; nothing becomes independently established by omission.
    """
    return DETAIL_FIELD_CLASSIFICATION.get(key, PRODUCER_ASSERTED)


__all__ = [
    "CLASSES",
    "DETAIL_FIELD_CLASSIFICATION",
    "EVENT_FIELD_CLASSIFICATION",
    "INDEPENDENTLY_ESTABLISHED",
    "LINEAGE_KEY",
    "LINEAGE_LINK_PREFIX",
    "NEVER_FUEL_BEARING",
    "PRODUCER_ASSERTED",
    "RESERVED_DETAIL_KEYS_V11",
    "UNTRUSTED_ENV_PROVENANCE",
    "classify_detail_key",
]
