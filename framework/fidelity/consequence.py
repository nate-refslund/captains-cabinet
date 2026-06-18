"""F0 — consequence-event emitter + ledger reader (shared fidelity infra).

Emits the normalized `consequence-event` shape
(framework/schemas/consequence-event.schema.json) to an append-only JSONL
ledger, validating every event against the real schema first. Graduation
math reads ONLY this ledger (see docs/consequence-ledger.md). This module is
the first consumer per docs/fidelity-harness-design-2026-06-18.md §5.

Storage mirrors framework/events/emitter.py BUT uses a DISTINCT filename
family so the two ledgers never collide in the shared dir: one file per UTC
day at $CABINET_EVENT_LOG_DIR/consequence-events-YYYY-MM-DD.jsonl,
json.dumps(event, default=str) + newline, append-only. (events/emitter.py
owns events-YYYY-MM-DD.jsonl in the same dir.) Enrichment (decision/outcome/
review landing later) is a SUPERSEDING event with the same
(actor, action, subject, ts) identity tuple; the reader takes the last write
per identity (last-write-wins).

System Python is 3.9.6 with no `jsonschema` dependency, so validation is
hand-rolled against this ONE schema (additionalProperties:false everywhere +
the three documented cross-field invariants).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "consequence-event.schema.json"
)
SCHEMA: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text())


class ConsequenceValidationError(ValueError):
    """Raised when a consequence event violates the schema or its invariants."""


def _consequence_log_dir() -> Path:
    """Resolve the JSONL consequence-ledger directory.

    Mirrors framework/events/emitter.py:_event_log_dir(): CABINET_EVENT_LOG_DIR
    wins; default is the durable per-user location (NOT /tmp, which is wiped).
    """
    return Path(os.environ.get(
        "CABINET_EVENT_LOG_DIR",
        os.path.expanduser("~/Library/Application Support/cabinet/events"),
    ))


_ACTOR_KINDS = {"pipe", "officer", "crew"}
_PROPOSAL_DECISIONS = {"approved", "edited", "rejected", "expired", None}
_OUTCOME_STATUSES = {"ok", "failed", "unknown"}
_REVIEW_VERDICTS = {"confirmed", "wrong", "unknown"}

# Allowed keys per object (additionalProperties:false everywhere).
_ROOT_KEYS = {"ts", "actor", "lane", "action", "subject",
              "refs", "proposal", "outcome", "review"}
_ROOT_REQUIRED = ("ts", "actor", "lane", "action", "subject")
_ACTOR_KEYS = {"kind", "id"}
_PROPOSAL_KEYS = {"required", "decision", "decided_at"}
_OUTCOME_KEYS = {"status", "evidence"}
_REVIEW_KEYS = {"verdict", "reviewed_at", "lesson_ref"}


def _reject_extra(obj: dict[str, Any], allowed: set[str], where: str) -> None:
    extra = set(obj) - allowed
    if extra:
        raise ConsequenceValidationError(
            f"{where}: additional properties not allowed: {sorted(extra)}"
        )


def validate_consequence(event: dict[str, Any]) -> None:
    """Validate a consequence event against the real schema + invariants.

    Raises ConsequenceValidationError on any violation; returns None on pass.
    Hand-rolled because system Python 3.9.6 has no jsonschema dependency.
    Enforces additionalProperties:false at every level + the three documented
    cross-field invariants (see docs/consequence-ledger.md).
    """
    if not isinstance(event, dict):
        raise ConsequenceValidationError("event must be an object")

    for key in _ROOT_REQUIRED:
        if key not in event:
            raise ConsequenceValidationError(f"missing required field: {key}")
    _reject_extra(event, _ROOT_KEYS, "root")

    # ts / action / subject: non-empty strings
    for key in ("ts", "action", "subject"):
        val = event[key]
        if not isinstance(val, str) or not val:
            raise ConsequenceValidationError(f"{key} must be a non-empty string")

    # lane: string | null
    if event["lane"] is not None and not isinstance(event["lane"], str):
        raise ConsequenceValidationError("lane must be a string or null")

    # actor
    actor = event["actor"]
    if not isinstance(actor, dict):
        raise ConsequenceValidationError("actor must be an object")
    for key in ("kind", "id"):
        if key not in actor:
            raise ConsequenceValidationError(f"actor: missing required field: {key}")
    _reject_extra(actor, _ACTOR_KEYS, "actor")
    if actor["kind"] not in _ACTOR_KINDS:
        raise ConsequenceValidationError(
            f"actor.kind must be one of {sorted(_ACTOR_KINDS)}"
        )
    if not isinstance(actor["id"], str) or not actor["id"]:
        raise ConsequenceValidationError("actor.id must be a non-empty string")

    # refs: array of strings (optional)
    if "refs" in event:
        refs = event["refs"]
        if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
            raise ConsequenceValidationError("refs must be an array of strings")

    # proposal (optional)
    if "proposal" in event:
        prop = event["proposal"]
        if not isinstance(prop, dict):
            raise ConsequenceValidationError("proposal must be an object")
        if "required" not in prop:
            raise ConsequenceValidationError("proposal: missing required field: required")
        _reject_extra(prop, _PROPOSAL_KEYS, "proposal")
        if not isinstance(prop["required"], bool):
            raise ConsequenceValidationError("proposal.required must be a boolean")
        if prop.get("decision") not in _PROPOSAL_DECISIONS:
            raise ConsequenceValidationError(
                "proposal.decision must be one of "
                f"{sorted(d for d in _PROPOSAL_DECISIONS if d)} or null"
            )

    # outcome (optional)
    if "outcome" in event:
        outc = event["outcome"]
        if not isinstance(outc, dict):
            raise ConsequenceValidationError("outcome must be an object")
        if "status" not in outc:
            raise ConsequenceValidationError("outcome: missing required field: status")
        _reject_extra(outc, _OUTCOME_KEYS, "outcome")
        if outc["status"] not in _OUTCOME_STATUSES:
            raise ConsequenceValidationError(
                f"outcome.status must be one of {sorted(_OUTCOME_STATUSES)}"
            )

    # review (optional)
    if "review" in event:
        rev = event["review"]
        if not isinstance(rev, dict):
            raise ConsequenceValidationError("review must be an object")
        if "verdict" not in rev:
            raise ConsequenceValidationError("review: missing required field: verdict")
        _reject_extra(rev, _REVIEW_KEYS, "review")
        if rev["verdict"] not in _REVIEW_VERDICTS:
            raise ConsequenceValidationError(
                f"review.verdict must be one of {sorted(_REVIEW_VERDICTS)}"
            )

    _validate_invariants(event)


def _validate_invariants(event: dict[str, Any]) -> None:
    """The three cross-field rules the schema enum/required cannot express."""
    prop = event.get("proposal")
    if prop is not None:
        # decision may be non-null only when an approval gate exists.
        if prop.get("required") is False and prop.get("decision") is not None:
            raise ConsequenceValidationError(
                "proposal.decision must be null when proposal.required is false"
            )

    outc = event.get("outcome")
    if outc is not None:
        status = outc.get("status")
        evidence = outc.get("evidence")
        if status == "unknown" and evidence is not None:
            raise ConsequenceValidationError(
                "outcome.evidence must be null when status is 'unknown'"
            )
        if status in ("ok", "failed") and not evidence:
            raise ConsequenceValidationError(
                f"outcome.evidence must be present when status is '{status}'"
            )

    rev = event.get("review")
    if rev is not None:
        if rev.get("verdict") != "wrong" and rev.get("lesson_ref") is not None:
            raise ConsequenceValidationError(
                "review.lesson_ref must be null unless verdict is 'wrong'"
            )
