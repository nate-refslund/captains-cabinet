"""
proxy/audit-server/validator.py — FW-097 PII minimization + entry validation.

WHY THIS EXISTS: Spec 052 AC #3 requires PII minimization at log-append time.
This module validates incoming audit entries and rejects or redacts:
  - Oversized metadata payloads (> MAX_METADATA_BYTES)
  - Secret-pattern argv content (password=, secret=, token=, api_key=)
  - Full Telegram DM text (only length+language+attachment_count allowed)

Non-conforming entries are rejected with a structured error so the caller can
surface the problem to the officer/COO rather than silently dropping data.

FAIL-SAFE: validator never crashes the server — unexpected exceptions return
a reject result with the exception message, never propagate.
"""

from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Maximum bytes for subject.metadata payload (prevents log-bloat + PII-overdraw)
MAX_METADATA_BYTES = 4096

# Regex for secret-pattern detection in tool-call argv content (Spec 052 edge case #3)
# Case-insensitive; matches key=value patterns with common secret key names.
_SECRET_PATTERN = re.compile(
    r"(?i)(password|secret|token|api_key)\s*=\s*\S+",
)

# Replacement sentinel for redacted secrets
_REDACTED = "REDACTED"


class ValidationError(Exception):
    """Raised when an entry is rejected by the validator."""


def validate_and_minimize(entry: dict[str, Any]) -> dict[str, Any]:
    """
    Validate entry against PII minimization rules (Spec 052 AC #3).

    Returns the (possibly redacted) entry on success.
    Raises ValidationError if the entry must be rejected.
    Never propagates unexpected exceptions — wraps them in ValidationError.
    """
    try:
        return _do_validate(entry)
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("validator.validate_and_minimize: unexpected error: %s", exc)
        raise ValidationError(f"unexpected validation error: {exc}") from exc


def _do_validate(entry: dict[str, Any]) -> dict[str, Any]:
    """Internal validation — may raise ValidationError."""
    import copy
    entry = copy.deepcopy(entry)

    subject = entry.get("subject", {})
    subject_type = subject.get("type", "")
    metadata = subject.get("metadata", {})

    # ── Rule 1: No full Telegram DM text ──────────────────────────────────────
    # DM entries must only carry length, language_detected, attachment_count.
    # Any 'text', 'content', 'body', 'message' key in metadata of a DM event = reject.
    if subject_type in ("telegram_dm",) or entry.get("event_type") in ("dm_received", "dm_sent"):
        forbidden_dm_keys = {"text", "content", "body", "message", "full_text"}
        found = forbidden_dm_keys.intersection(metadata.keys())
        if found:
            raise ValidationError(
                f"PII violation: Telegram DM metadata contains full-text field(s): {sorted(found)}"
            )

    # ── Rule 2: Redact secret-pattern argv content in tool_call entries ───────
    if subject_type == "tool_call" or entry.get("event_type") == "tool_call":
        target = subject.get("target", "")
        if isinstance(target, str) and _SECRET_PATTERN.search(target):
            subject["target"] = _SECRET_PATTERN.sub(
                lambda m: f"{m.group(1)}={_REDACTED}", target
            )
        if isinstance(metadata, dict):
            for key in list(metadata.keys()):
                val = metadata[key]
                if isinstance(val, str) and _SECRET_PATTERN.search(val):
                    metadata[key] = _SECRET_PATTERN.sub(
                        lambda m: f"{m.group(1)}={_REDACTED}", val
                    )

    # ── Rule 3: Metadata size cap ──────────────────────────────────────────────
    import json
    metadata_bytes = len(json.dumps(metadata, separators=(",", ":")).encode("utf-8"))
    if metadata_bytes > MAX_METADATA_BYTES:
        raise ValidationError(
            f"PII minimization: subject.metadata exceeds {MAX_METADATA_BYTES} bytes "
            f"({metadata_bytes} bytes). Reduce payload before logging."
        )

    # ── Rule 4: Attachment content forbidden ──────────────────────────────────
    # Only filename + type + size allowed; 'content' or 'data' keys = reject.
    if isinstance(metadata, dict):
        forbidden_attachment_keys = {"content", "data", "attachment_data", "file_content"}
        found = forbidden_attachment_keys.intersection(metadata.keys())
        if found:
            raise ValidationError(
                f"PII violation: metadata contains attachment content field(s): {sorted(found)}"
            )

    # Write back potentially-mutated subject
    entry["subject"] = subject
    return entry


def is_valid_entry_schema(entry: dict[str, Any]) -> tuple[bool, str]:
    """
    Light schema check: required top-level fields present.
    Returns (True, "") on pass or (False, reason) on fail.
    """
    required = {"ts", "cabinet_id", "entry_id", "stream", "event_type", "actor", "subject", "integrity"}
    missing = required - set(entry.keys())
    if missing:
        return False, f"missing required fields: {sorted(missing)}"

    valid_streams = {"proxy", "officer", "cabinet"}
    if entry.get("stream") not in valid_streams:
        return False, f"invalid stream: {entry.get('stream')!r}; must be one of {valid_streams}"

    return True, ""
