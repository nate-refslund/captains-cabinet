"""
proxy/audit-server/validator.py — FW-097 PII minimization + entry validation.

WHY THIS EXISTS: Spec 052 AC #3 requires PII minimization at log-append time. This
module validates incoming audit entries (from BOTH app.py's officer POST and ingest.py's
proxy-stream transform) and rejects or minimizes anything that could carry PII/secrets.

MINIMIZATION MODEL — FAIL-CLOSED ALLOW-LIST (Spec 052 v3.4 AC #3, #234):
  The original deny-list (intersection of a fixed forbidden-key set against top-level
  metadata keys) had structural blind spots that bypassed it:
    - NESTED keys:   {"msg": {"body": "<PII>"}}   (top-level key is "msg", not "body")
    - CASE variants: {"Text": "<PII>"}            (exact-case intersection misses "Text")
    - ARBITRARY keys:{"customer_email": "<PII>"}  (not in the fixed forbidden set at all)
    - non-metadata blocks: PII in actor / cost / subject.target was NEVER inspected
  The allow-list is fail-closed: ONLY known-safe keys with scalar, length-bounded values
  survive into the SSOT; every other key is DROPPED. This mirrors the client-side minimizer
  in cabinet/scripts/lib/audit-emit.sh (the two metadata allow-lists MUST be kept in sync —
  see _ALLOWED_METADATA_KEYS note). This server layer is the BACKSTOP: it defends the SSOT
  even against a producer that bypasses the client lib — notably ingest.py, which builds
  entries as raw dicts and never calls the client lib (nor goes through pydantic).

COVERAGE — the whole entry, not just metadata (#234, Opus adversary F1/F2):
  - subject.metadata : recursive forbidden-key reject + fail-closed allow-list minimize.
  - subject.target   : secret-pattern redaction (ALL event types) + length bound.
  - actor / cost     : recursive forbidden-key reject + key allow-list to their known
                       typed schemas (drops arbitrary injected keys; keeps the schema,
                       incl. actor.officer == None for captain-action entries).

REJECT vs DROP (flagged for COO/DPO sign-off in the #234 PR):
  - FORBIDDEN keys (text/body/content/message/full_text/data/attachment_data/file_content)
    at ANY nesting depth, in ANY block, case-insensitive -> REJECT (fail-loud). These signal
    a producer actively trying to log PII/secret free-text or attachment bytes; a silent drop
    would mask the producer bug. (Generalizes the old per-event-type, top-level-only deny-list.)
  - OVERSIZED metadata (> MAX_METADATA_BYTES) -> REJECT (bloat / PII-overdraw guard).
  - UNKNOWN keys (not forbidden, not allow-listed) -> DROP (minimize). Keeps the audit
    trail + hash-chain flowing when a producer adds a benign field; only the field is lost.

ACCEPTED RESIDUAL (DPO sign-off): an allow-listed STRING key (e.g. command_head, path, model,
  subject.target) may carry up to MAX_VALUE_LEN chars of free-text, of which only secret=value
  patterns are redacted. This matches the client lib's posture; the server cannot semantically
  detect arbitrary PII inside a bounded free-text value. Secret-regex coverage gaps (bearer /
  colon-delimited / apikey-no-underscore) are a tracked LOW follow-up, not fixed here.

FAIL-SAFE: validator never crashes the server — unexpected exceptions return a reject
result with the exception message, never propagate.
"""

from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Maximum bytes for subject.metadata payload (prevents log-bloat + PII-overdraw)
MAX_METADATA_BYTES = 4096

# Maximum length of a scalar string value kept by the allow-list (mirrors audit-emit.sh
# _AUDIT_MAX_VALUE_LEN). Longer strings are DROPPED (metadata) or TRUNCATED (subject.target) —
# a single allow-listed key cannot be used to smuggle large free-text PII.
MAX_VALUE_LEN = 256

# ── Metadata allow-list (Spec 052 v3.4 AC #3, #234) ───────────────────────────────────────
# UNION of:
#   (a) officer/client-emitted keys — MUST stay in sync with cabinet/scripts/lib/audit-emit.sh
#       _AUDIT_ALLOWED_KEYS (officers emit officer/cabinet streams via that client minimizer); and
#   (b) proxy-ingest-only keys — request_pct_of_cap + fw096_status, carried into subject.metadata
#       by ingest.py _transform_fw096_to_052 (the FW-096 proxy stream has no Spec 052 slot for them;
#       they are NOT emitted by the client lib, so they live only here on the server allow-list).
# Any key NOT in this set is dropped from metadata (fail-closed). Adding a new safe key is a
# deliberate, GDPR-reviewed step that should update BOTH this set and audit-emit.sh.
_ALLOWED_METADATA_KEYS = frozenset({
    # (a) officer/client keys — keep in sync with audit-emit.sh _AUDIT_ALLOWED_KEYS:
    "length", "attachment_count", "language_detected", "direction", "path",
    "command_head", "request_id", "entry_id", "model", "provider", "status",
    "severity", "rotated_by", "by", "event", "event_name", "count", "ticket_id", "_truncated",
    # (b) proxy-ingest-only keys — ingest.py _transform_fw096_to_052:
    "request_pct_of_cap", "fw096_status",
})

# ── actor / cost block allow-lists (#234 F1) ──────────────────────────────────────────────
# These are typed blocks (app.py ActorModel / CostModel) with fixed known-safe schemas. The
# threat for them is arbitrary injected keys (a direct-dict producer like ingest, or a client
# that bypasses pydantic), not free-text values — so we key-allow-list them to their schemas.
# Allow-listed keys keep their value (incl. None for actor.officer on captain-action entries);
# non-allow-listed keys are dropped. Mirror these to ActorModel/CostModel if the schema grows.
_ALLOWED_ACTOR_KEYS = frozenset({"officer", "captain"})
_ALLOWED_COST_KEYS = frozenset({
    "model", "tokens_in", "tokens_out", "cost_raw_usd", "cost_marked_up_usd",
})

# ── Forbidden keys (case-insensitive, recursive, ALL blocks) ──────────────────────────────
# A key with any of these names — at ANY nesting depth, in ANY block (metadata/actor/cost/…),
# in ANY case — triggers a fail-loud REJECT. They name full free-text (text/content/body/
# message/full_text) or attachment bytes (data/attachment_data/file_content): a producer
# emitting them is leaking PII and must be fixed, not silently scrubbed. Matched as whole keys
# (lowercased) against this set — NOT as substrings (so "body_count", "content_type",
# "message_id" do NOT match).
_FORBIDDEN_KEYS_LOWER = frozenset({
    "text", "content", "body", "message", "full_text",   # full free-text
    "data", "attachment_data", "file_content",           # attachment bytes
})

# Regex for secret-pattern detection in argv/target/value content (Spec 052 edge case #3).
# Case-insensitive; matches key=value patterns with common secret key names.
# NOTE (LOW, tracked follow-up): misses bearer-style, colon-delimited, and apikey-no-underscore
# forms — defense-in-depth on top of the allow-list, expanded separately under FP review.
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

    Returns the (minimized) entry on success.
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


def _find_forbidden_keys(obj: Any) -> set[str]:
    """
    Recursively collect any forbidden keys (case-insensitive) at any nesting depth, walking
    through nested dicts AND lists. Returns the set of offending keys (original case) so the
    reject message can name them. Closes the deny-list nested/case-variant/whole-block blind
    spots. (JSON cannot produce tuples/sets, so dict+list coverage is complete for our inputs.)
    """
    found: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in _FORBIDDEN_KEYS_LOWER:
                found.add(k)
            found |= _find_forbidden_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            found |= _find_forbidden_keys(item)
    return found


def _allowlist_minimize(obj: dict[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    """
    Fail-closed allow-list filter: keep ONLY allow-listed keys (exact case, matching the
    client lib's case-sensitive IN check) whose value is None or a scalar (bool/int/float/str)
    and, if a string, within MAX_VALUE_LEN. Drops unknown keys, nested objects/arrays, and
    over-length strings — so a non-scalar value (the nested blind spot) can never survive even
    under an allow-listed key name. None is preserved (it carries no PII; e.g. actor.officer
    on a captain-action entry).
    """
    out: dict[str, Any] = {}
    for k, v in obj.items():
        if not isinstance(k, str) or k not in allowed:
            continue  # drop unknown / non-string key
        if v is None:
            out[k] = v                               # None carries no PII — preserve
        elif isinstance(v, bool):                    # bool before int (bool is an int subclass)
            out[k] = v
        elif isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, str) and len(v) <= MAX_VALUE_LEN:
            out[k] = v
        # else: nested dict/list or over-length string -> drop
    return out


def _redact_secrets(s: str) -> str:
    """Redact secret-pattern key=value substrings in a free-text string."""
    if _SECRET_PATTERN.search(s):
        return _SECRET_PATTERN.sub(lambda m: f"{m.group(1)}={_REDACTED}", s)
    return s


def _do_validate(entry: dict[str, Any]) -> dict[str, Any]:
    """Internal validation — may raise ValidationError."""
    import copy
    import json
    entry = copy.deepcopy(entry)

    # ── Rule 1 (generalized): recursive + case-insensitive forbidden-key REJECT ──────────────
    # Applies to the WHOLE entry (metadata + actor + cost + any nesting), ANY event type. A
    # producer emitting a full-text / attachment-bytes key anywhere is leaking PII and must
    # surface, not be silently scrubbed. (#234 F1: actor/cost were previously uninspected.)
    forbidden_found = _find_forbidden_keys(entry)
    if forbidden_found:
        raise ValidationError(
            f"PII violation: entry contains forbidden field(s) "
            f"(any block, any nesting depth, case-insensitive): {sorted(forbidden_found)}"
        )

    subject = entry.get("subject", {}) or {}
    subject_type = subject.get("type", "")
    metadata = subject.get("metadata", {})

    # ── Rule 2: metadata size cap on RAW metadata (bloat / PII-overdraw guard) ───────────────
    if isinstance(metadata, dict):
        metadata_bytes = len(json.dumps(metadata, separators=(",", ":")).encode("utf-8"))
        if metadata_bytes > MAX_METADATA_BYTES:
            raise ValidationError(
                f"PII minimization: subject.metadata exceeds {MAX_METADATA_BYTES} bytes "
                f"({metadata_bytes} bytes). Reduce payload before logging."
            )

        # ── Rule 3 (#234 core): fail-closed allow-list minimize ──────────────────────────────
        # Drops every key not on the union allow-list + non-scalar / over-length values. The
        # backstop the deny-list lacked: arbitrary/unknown keys (e.g. customer_email) and
        # non-scalar values are dropped here even when Rule 1 didn't name them.
        metadata = _allowlist_minimize(metadata, _ALLOWED_METADATA_KEYS)
        subject["metadata"] = metadata

    # ── Rule 4: subject.target — secret-redact (ALL event types) + length bound (#234 F2) ────
    target = subject.get("target", "")
    if isinstance(target, str):
        target = _redact_secrets(target)
        if len(target) > MAX_VALUE_LEN:
            target = target[:MAX_VALUE_LEN]
        subject["target"] = target

    # ── Rule 5: redact secret-pattern values in surviving metadata strings ───────────────────
    if isinstance(metadata, dict):
        for key in list(metadata.keys()):
            val = metadata[key]
            if isinstance(val, str):
                metadata[key] = _redact_secrets(val)

    entry["subject"] = subject

    # ── Rule 6 (#234 F1): key allow-list the typed actor / cost blocks ───────────────────────
    # Drops arbitrary injected keys while keeping the known schema (incl. actor.officer == None).
    actor = entry.get("actor")
    if isinstance(actor, dict):
        entry["actor"] = _allowlist_minimize(actor, _ALLOWED_ACTOR_KEYS)
    cost = entry.get("cost")
    if isinstance(cost, dict):
        entry["cost"] = _allowlist_minimize(cost, _ALLOWED_COST_KEYS)

    return entry


# ── cabinet_id slug validation (shared writer-side guard — Spec 052 v3.7/v3.8 AC#10/#12) ──
# THE single Python definition of the cabinet_id slug shape. Imported by BOTH app.py (#236
# GET/POST endpoint guards) AND ingest.py (#237 write-side ingest chokepoint), so the two
# CANNOT drift — one copy, structurally (no within-Python parity-test needed).
# cabinet_id is used to BUILD filesystem paths — audit/<slug>.jsonl (via hashchain),
# proxy-audit/<slug>.jsonl, .cursors/<slug>.cursor — so a non-slug value is a path-traversal /
# cross-cabinet-escape surface; it must be rejected BEFORE any path is built.
# \Z, NOT $: Python's $ also matches just before a lone trailing newline, so r"...$" would
# ACCEPT "valid\n" (a same-dir phantom file); \Z anchors the true end of the string.
# Cross-LANGUAGE peer (cannot share one def across languages): the bash slug regex in
# cabinet/scripts/customer-erasure.sh (~L73) ^[a-z0-9][a-z0-9-]{0,63} — keep the two shapes
# identical if either changes. The regex is stable, so a bash/python parity-test is optional.
_CABINET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}\Z")


def is_valid_cabinet_id(cabinet_id: object) -> bool:
    """True iff cabinet_id is a safe slug (see _CABINET_ID_RE). Type-safe: non-str -> False."""
    return isinstance(cabinet_id, str) and _CABINET_ID_RE.match(cabinet_id) is not None


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
