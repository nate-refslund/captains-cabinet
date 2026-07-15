"""Bounded redaction for evidence payloads.

Evidence is operational metadata, never a second copy of a Captain's sources.
Every value is treated as untrusted data.  Secret-bearing fields, raw source
content, hidden reasoning, and absolute local paths are removed before a byte
can reach the ledger.
"""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import PurePath
from typing import Any

MAX_DEPTH = 5
MAX_KEYS = 64
MAX_ITEMS = 64
MAX_STRING = 512

SECRET_KEY_RE = re.compile(
    r"(?:^|[_-])(password|passwd|secret|token|api[_-]?key|authorization|cookie|"
    r"credential|private[_-]?key|session[_-]?id)(?:$|[_-])",
    re.I,
)
REASONING_KEY_RE = re.compile(
    r"chain[_ -]?of[_ -]?thought|hidden[_ -]?reasoning|scratchpad|internal[_ -]?monologue|raw[_ -]?prompt",
    re.I,
)
RAW_CONTENT_KEY_RE = re.compile(
    r"^(raw|raw_content|content|contents|file_content|source_content|body_bytes|stdin|stdout|stderr)$",
    re.I,
)
SECRET_VALUE_RES = (
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\b[0-9]{8,12}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/-]{12,}=*"),
    re.compile(r"(?i)\b(?:password|passwd|secret|token|api[_ -]?key)\s*[:=]\s*[^\s,;]+"),
)
ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9_.-])(?:/[A-Za-z0-9_.~@+ -]+){2,}")


def _path_marker(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:12]
    try:
        label = PurePath(value).name[:80]
    except (TypeError, ValueError):
        label = "local"
    return f"[LOCAL_PATH:{label}:{digest}]"


def sanitize_string(value: str) -> tuple[str, list[str]]:
    """Return a bounded safe string and the redactions applied."""
    notes: list[str] = []
    clean = value.replace("\x00", "�")
    for rx in SECRET_VALUE_RES:
        if rx.search(clean):
            clean = rx.sub("[REDACTED_SECRET]", clean)
            notes.append("secret_value")
    stripped = clean.strip()
    if stripped.startswith(("/", "~/")) and ABSOLUTE_PATH_RE.search(stripped):
        clean = _path_marker(stripped)
        notes.append("absolute_path")
    else:
        def replace_path(match: re.Match[str]) -> str:
            notes.append("absolute_path")
            return _path_marker(match.group(0))

        clean = ABSOLUTE_PATH_RE.sub(replace_path, clean)
    if len(clean) > MAX_STRING:
        clean = clean[:MAX_STRING] + "…[TRUNCATED]"
        notes.append("string_truncated")
    return clean, sorted(set(notes))


def sanitize(value: Any, *, _depth: int = 0) -> tuple[Any, list[str]]:
    """Recursively sanitize JSON-like data.

    Unknown objects become a type marker; their ``repr`` is never persisted.
    The returned redaction list contains categories only, never secret values.
    """
    if _depth > MAX_DEPTH:
        return "[MAX_DEPTH]", ["depth_truncated"]
    if value is None or isinstance(value, (bool, int)):
        return value, []
    if isinstance(value, float):
        if not math.isfinite(value):
            return "[NON_FINITE_NUMBER]", ["non_finite_number"]
        return value, []
    if isinstance(value, str):
        return sanitize_string(value)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        notes: list[str] = []
        for index, (raw_key, item) in enumerate(value.items()):
            if index >= MAX_KEYS:
                notes.append("mapping_truncated")
                break
            key = str(raw_key)[:80]
            if SECRET_KEY_RE.search(key):
                result[key] = "[REDACTED_SECRET_FIELD]"
                notes.append("secret_field")
                continue
            if REASONING_KEY_RE.search(key):
                result[key] = "[OMITTED_HIDDEN_REASONING]"
                notes.append("hidden_reasoning")
                continue
            if RAW_CONTENT_KEY_RE.search(key):
                result[key] = "[OMITTED_RAW_CONTENT]"
                notes.append("raw_content")
                continue
            safe, child_notes = sanitize(item, _depth=_depth + 1)
            result[key] = safe
            notes.extend(child_notes)
        return result, sorted(set(notes))
    if isinstance(value, (list, tuple, set, frozenset)):
        result: list[Any] = []
        notes: list[str] = []
        for index, item in enumerate(value):
            if index >= MAX_ITEMS:
                notes.append("sequence_truncated")
                break
            safe, child_notes = sanitize(item, _depth=_depth + 1)
            result.append(safe)
            notes.extend(child_notes)
        return result, sorted(set(notes))
    return f"[UNSUPPORTED:{type(value).__name__}]", ["unsupported_type"]


def contains_secret_shape(value: Any) -> bool:
    """Defense-in-depth scanner used by tests, exports, and the verifier."""
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)) and item != "[REDACTED_SECRET_FIELD]":
                return True
            if contains_secret_shape(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(contains_secret_shape(item) for item in value)
    if isinstance(value, str):
        return any(rx.search(value) for rx in SECRET_VALUE_RES)
    return False
