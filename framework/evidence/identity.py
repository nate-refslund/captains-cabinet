"""Broker-attested producer identity — fixed at process start, never payload-derived.

The A6 forgery seam this module closes: a producer that copies an actor or
component out of the data it is recording (an org event's claimed actor, a
request payload, an environment variable) lets untrusted input impersonate a
producer.  Pattern source is ``cabinet/scripts/captain-law-broker.py``:
identity enters ONCE at process start through an explicit call (the broker's
``--officer`` argv), is validated against the fixed vocabulary, and is frozen
for the process lifetime — request/event bodies structurally cannot carry it.

Usage (a telemetry mirror or act-class producer, at process start)::

    from framework.evidence import identity

    identity.attest_process_identity("system", "org-event-mirror",
                                     "org-event-mirror")
    ...
    recorder.append(context, phase="system", status="succeeded",
                    actor=identity.attested_actor(),
                    component=identity.attested_component(),
                    detail={**identity.attestation_detail(), ...})

Laws:

- **Never payload-derived.**  The attested values come from an explicit
  startup call (argv/constant in the producer), never from the event being
  recorded.  A mirrored event's own claimed actor is DATA and belongs in
  ``detail``, never in the ``actor`` field.
- **Never env-derived (A10).**  This module never reads environment
  variables.  The attested component carries explicit ``version``/``commit``
  values so a producer using it never falls back to the recorder's
  ``CABINET_BUILD_VERSION``/``CABINET_GIT_COMMIT`` env seam.
- **Freeze-once.**  Re-attesting identical values is an idempotent no-op;
  re-attesting different values refuses (``identity_conflict``).  Accessors
  fail closed (``identity_unattested``) and return defensive copies.
- **Honesty caveat (R2).**  Process attestation proves the producer declared
  one fixed identity at startup — same-user code could still declare falsely.
  ``attestation_detail()`` therefore stamps ``attestation_mode: "process"``
  (a producer-asserted key in the Phase-1 classification registry), so a
  later fuel-integrity check can tell process-attested events from
  unattested ones without over-trusting either.  The out-of-process broker
  mode arrives with its own ceremony; Phase 6 hard-requires it.
- **Not an emit surface.**  This module returns identity dicts only: no
  recorder construction, no append wrapper, no CLI, so it cannot become a
  generic emit seam.  Imports are one-way (identity -> recorder/verifier/
  redaction constants); the recorder and verifier never import it.
"""
from __future__ import annotations

import threading
from typing import Any

from .recorder import ID_RE, PROVENANCE_RE, EvidenceError
from .redaction import contains_secret_shape
from .verifier import ACTOR_KINDS

# Reserved detail key (registered producer-asserted in classification.py).
# Deliberately NOT in the officer projection allow-list: attestation is
# audit/fuel-integrity vocabulary, never an officer-visible signal.
ATTESTATION_DETAIL_KEY = "attestation_mode"
ATTESTATION_MODE_PROCESS = "process"

__all__ = [
    "ATTESTATION_DETAIL_KEY",
    "ATTESTATION_MODE_PROCESS",
    "attest_process_identity",
    "attestation_detail",
    "attested_actor",
    "attested_component",
    "is_attested",
]

_LOCK = threading.Lock()
_ATTESTED: dict[str, Any] | None = None


def _validated_identity(
    actor_kind: Any,
    actor_id: Any,
    component_name: Any,
    component_version: Any,
    component_commit: Any,
) -> dict[str, Any]:
    if not isinstance(actor_kind, str) or actor_kind not in ACTOR_KINDS:
        raise EvidenceError(
            "identity_actor_invalid", "The attested actor kind is invalid."
        )
    if not isinstance(actor_id, str) or not ID_RE.fullmatch(actor_id):
        raise EvidenceError(
            "identity_actor_invalid", "The attested actor id is invalid."
        )
    if not isinstance(component_name, str) or not ID_RE.fullmatch(component_name):
        raise EvidenceError(
            "identity_component_invalid",
            "The attested component name is invalid.",
        )
    for value in (component_version, component_commit):
        # Fail closed at the seam: a secret-shaped provenance value refuses
        # here, loudly at startup, instead of being silently redacted later.
        if (
            not isinstance(value, str)
            or not PROVENANCE_RE.fullmatch(value)
            or contains_secret_shape(value)
        ):
            raise EvidenceError(
                "identity_component_invalid",
                "The attested component provenance is invalid.",
            )
    return {
        "actor": {"kind": actor_kind, "id": actor_id},
        "component": {
            "name": component_name,
            "version": component_version,
            "commit": component_commit,
        },
        "mode": ATTESTATION_MODE_PROCESS,
    }


def _snapshot(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "actor": dict(identity["actor"]),
        "component": dict(identity["component"]),
        "mode": identity["mode"],
    }


def attest_process_identity(
    actor_kind: str,
    actor_id: str,
    component_name: str,
    *,
    component_version: str = "1",
    component_commit: str = "unset",
) -> dict[str, Any]:
    """Fix this process's producer identity, once, from explicit values.

    Values must come from the producer's own startup (argv or constants),
    never from a payload it processes and never from the environment.  The
    first successful call freezes the identity for the process lifetime;
    an identical re-attest is an idempotent no-op; a differing re-attest
    raises ``identity_conflict``.  Returns a defensive copy of the frozen
    identity ``{"actor": ..., "component": ..., "mode": "process"}``.
    """
    global _ATTESTED
    candidate = _validated_identity(
        actor_kind, actor_id, component_name, component_version, component_commit
    )
    with _LOCK:
        if _ATTESTED is None:
            _ATTESTED = candidate
        elif _ATTESTED != candidate:
            raise EvidenceError(
                "identity_conflict",
                "This process already attested a different producer identity.",
            )
        return _snapshot(_ATTESTED)


def is_attested() -> bool:
    """Return whether this process has a frozen producer identity."""
    with _LOCK:
        return _ATTESTED is not None


def _require_attested() -> dict[str, Any]:
    with _LOCK:
        if _ATTESTED is None:
            raise EvidenceError(
                "identity_unattested",
                "No producer identity was attested for this process.",
            )
        return _ATTESTED


def attested_actor() -> dict[str, str]:
    """Return a copy of the frozen actor; fail closed when unattested."""
    return dict(_require_attested()["actor"])


def attested_component() -> dict[str, str]:
    """Return a copy of the frozen component identity (explicit
    version/commit, so the recorder's env provenance fallback is never
    consulted); fail closed when unattested."""
    return dict(_require_attested()["component"])


def attestation_detail() -> dict[str, str]:
    """Return the reserved detail stamp for attested events.

    Producers merge this into the event ``detail`` they pass to the
    recorder's ``append()`` so the stored event carries
    ``attestation_mode: "process"`` — producer-asserted vocabulary the
    Phase-4 fuel-integrity check reads; fails closed when unattested.
    """
    _require_attested()
    return {ATTESTATION_DETAIL_KEY: ATTESTATION_MODE_PROCESS}
