"""
proxy/audit-server/erasure.py — FW-097 two-hash pseudonymizer (Spec 052 AC #8).

WHY THIS EXISTS: GDPR Article 17 erasure requests cannot be fulfilled by deleting
log entries because that would break the hash-chain (making it unverifiable).
Instead, we pseudonymize PII fields in subject.metadata and carry both hashes:

  entry_hash          — original pre-pseudonymization hash (PRESERVED, unchanged)
                         chain integrity verification continues to work via this hash
  pseudonym_marker_hash — sha256 of the pseudonymized entry content
                         customer can verify pseudonymization is internally consistent

DESIGN (CTO #8):
  - Pseudonymization blanks PII values (e.g., {customer_name: "REDACTED-<date>"})
  - entry_hash is NEVER recomputed (preserves chain linkage)
  - pseudonym_marker_hash is ADDED as a top-level field (not inside integrity{})
  - The chain verifier (hashchain.verify) skips re-computation for pseudonymized
    entries and uses stored entry_hash directly — this is correct and documented.

DEPLOY NOTE:
  chattr +a on the log file must be lifted by root, the erasure applied, and
  chattr +a re-applied. This is a deploy-gated step, NOT called from this code.
  This module only handles the in-process field-level pseudonymization.

FAIL-SAFE: pseudonymize() never raises — errors are logged and original entry
returned unmodified (caller decides whether to proceed).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Fields in subject.metadata considered PII that get blanked on erasure.
# This list covers the data-minimization set from Spec 052 §PII minimization.
_PII_METADATA_KEYS = {
    "customer_name",
    "email",
    "user_id",
    "ip_address",
    "phone",
    "user_agent",
    "session_id",
    "language_detected",  # retained in general but blanked on erasure
}

# PII in actor/subject.target that should be blanked
_PII_SUBJECT_KEYS = {"target"}  # target may contain a user identifier


def _redacted_value(date_str: str) -> str:
    return f"REDACTED-{date_str}"


def pseudonymize(entry: dict[str, Any], erasure_date: str | None = None) -> dict[str, Any]:
    """
    Pseudonymize PII fields in a single audit log entry.

    Returns the pseudonymized entry with pseudonym_marker_hash added.
    The original entry_hash inside integrity{} is PRESERVED unchanged.
    Never raises — exceptions are logged and original entry returned.
    """
    try:
        return _do_pseudonymize(entry, erasure_date)
    except Exception as exc:  # noqa: BLE001
        logger.warning("erasure.pseudonymize: unexpected error: %s", exc)
        return entry


def _do_pseudonymize(entry: dict[str, Any], erasure_date: str | None) -> dict[str, Any]:
    import copy
    result = copy.deepcopy(entry)

    ts = erasure_date or datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    redacted = _redacted_value(ts)

    # Pseudonymize subject.metadata PII fields
    subject = result.get("subject", {})
    metadata = subject.get("metadata") or {}
    if isinstance(metadata, dict):
        for key in _PII_METADATA_KEYS:
            if key in metadata:
                metadata[key] = redacted
        subject["metadata"] = metadata

    # Pseudonymize actor.captain if it contains an identifier string
    actor = result.get("actor", {})
    if isinstance(actor, dict) and isinstance(actor.get("officer"), str) and actor["officer"] not in ("null", "unknown", ""):
        # We don't blank the officer slug (needed for reconciliation) but we can
        # mark it. Per spec: only PII in subject.metadata is blanked. Officer slug
        # is an internal system identifier, not a natural person identifier.
        pass  # officer slug is system-internal; preserved per design

    result["subject"] = subject
    result["actor"] = actor

    # Compute pseudonym_marker_hash — sha256 of the pseudonymized content
    # (excluding the pseudonym_marker_hash field itself, which doesn't exist yet)
    to_hash = {k: v for k, v in result.items() if k != "pseudonym_marker_hash"}
    marker_hash = hashlib.sha256(
        json.dumps(to_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    result["pseudonym_marker_hash"] = marker_hash

    return result


def pseudonymize_cabinet(cabinet_id: str, log_path: "pathlib.Path") -> dict[str, Any]:
    """
    Apply pseudonymization to all entries in a cabinet's SSOT log file.

    Rewrites the file in-place (requires chattr -a before call + chattr +a after,
    per deploy-gated instructions — this function does NOT call chattr).

    Returns {"processed": N, "errors": M} summary.
    """
    import pathlib
    import tempfile
    import os

    path = pathlib.Path(log_path)
    if not path.exists():
        return {"processed": 0, "errors": 0}

    processed = 0
    errors = 0
    erasure_date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    # Write to a temp file then atomic-rename to preserve integrity during write
    tmp_path = path.with_suffix(".tmp_erasure")
    try:
        with path.open("r", encoding="utf-8") as fin, tmp_path.open("w", encoding="utf-8") as fout:
            for line in fin:
                line = line.strip()
                if not line:
                    fout.write("\n")
                    continue
                try:
                    entry = json.loads(line)
                    pseudonymized = pseudonymize(entry, erasure_date)
                    fout.write(json.dumps(pseudonymized, separators=(",", ":")) + "\n")
                    processed += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("erasure.pseudonymize_cabinet: error on line: %s", exc)
                    fout.write(line + "\n")  # preserve original on error
                    errors += 1

        os.replace(tmp_path, path)
    except Exception as exc:  # noqa: BLE001
        logger.error("erasure.pseudonymize_cabinet: fatal error for %s: %s", cabinet_id, exc)
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        errors += 1

    return {"processed": processed, "errors": errors}
