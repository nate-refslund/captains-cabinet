"""Bounded redaction for evidence payloads.

Evidence is operational metadata, never a second copy of a Captain's sources.
Every value is treated as untrusted data.  Secret-bearing fields, raw source
content, hidden reasoning, and absolute local paths are removed before a byte
can reach the ledger.

Personal-identifier scope: email-shaped values are redacted wherever they
appear, and values under chat-id-shaped keys are redacted like secrets — a
messaging chat id is a routing handle to a person.  Bare numeric identifiers
under other keys are out of scope by design: a raw integer is
indistinguishable from an operational counter (``total_bytes``,
``retry_count``), and redacting numbers wholesale would blind the audit this
evidence exists to serve.
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
    r"credential|private[_-]?key|session[_-]?id|chat[_-]?id)(?:$|[_-])",
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
    # Messaging bot tokens (<numeric id>:<secret>).  A digit-only negative
    # lookbehind instead of \b: URL forms such as .../bot<id>:<secret> glue a
    # word character onto the id, which defeats a word boundary.
    re.compile(r"(?<![0-9])[0-9]{8,12}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/-]{12,}=*"),
    # URI userinfo credentials (scheme://user:password@host).  The user part
    # may be empty (redis://:password@host), so it is a *, not a +.
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]*:[^/\s@]+@"),
    # Keyword assignments.  (?:\b|(?<=_)) keeps every boundary \b matched and
    # adds underscore-joined prefixes; the bounded possessive [_-] tail covers
    # underscore-joined suffixes (aws_secret_access_key=...); the optional
    # closing quote covers serialized forms ("api_key": "...").  The tail is
    # {1,32} chars per segment, {0,8} segments, possessive: an unbounded
    # backtracking tail stalls sanitize quadratically on keyword-dense input
    # ('token_' * 33000 took minutes), which would deny evidence recording.
    re.compile(
        r"(?i)(?:\b|(?<=_))(?:password|passwd|secret|token|api[_ -]?key)"
        r"(?:[_-][a-z0-9]{1,32}){0,8}+[\"']?\s*[:=]\s*[^\s,;]+"
    ),
    # Email addresses are personal identifiers; exports must be reviewable
    # without leaking them.  Ordered after the URI pattern so database hosts
    # survive as reviewable text instead of being consumed as email domains.
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
)
ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9_.-])(?:/[A-Za-z0-9_.~@+ -]+){2,}")


def _path_marker(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:12]
    try:
        label = PurePath(value).name[:80]
    except (TypeError, ValueError):
        label = "local"
    return f"[LOCAL_PATH:{label}:{digest}]"


def _scrub_unencodable(value: str) -> tuple[str, bool]:
    """Replace code points UTF-8 cannot encode (lone surrogates) with U+FFFD.

    A lone UTF-16 surrogate would otherwise crash canonical JSON encoding at
    write time and the action would go unrecorded — a denial of evidence.
    Scrubbing keeps the event.  The transform is the identity for every valid
    string, so previously recorded bytes never drift.
    """
    scrubbed = value.encode("utf-8", "replace").decode("utf-8")
    return scrubbed, scrubbed != value


def sanitize_string(value: str) -> tuple[str, list[str]]:
    """Return a bounded safe string and the redactions applied."""
    notes: list[str] = []
    clean = value.replace("\x00", "�")
    clean, was_invalid = _scrub_unencodable(clean)
    if was_invalid:
        notes.append("invalid_unicode")

    def apply_secret_patterns(text: str) -> str:
        for rx in SECRET_VALUE_RES:
            if rx.search(text):
                text = rx.sub("[REDACTED_SECRET]", text)
                notes.append("secret_value")
        return text

    clean = apply_secret_patterns(clean)
    stripped = clean.strip()
    if stripped.startswith(("/", "~/")) and ABSOLUTE_PATH_RE.search(stripped):
        clean = _path_marker(stripped)
        notes.append("absolute_path")
    else:
        def replace_path(match: re.Match[str]) -> str:
            notes.append("absolute_path")
            return _path_marker(match.group(0))

        clean = ABSOLUTE_PATH_RE.sub(replace_path, clean)
    # A path substitution rewrites the text around its match; never let that
    # rewrite strip the boundary a secret pattern relied on.  Re-running the
    # value patterns can only redact more, never less.
    clean = apply_secret_patterns(clean)
    if len(clean) > MAX_STRING:
        clean = clean[:MAX_STRING] + "…[TRUNCATED]"
        notes.append("string_truncated")
        # The cut plus marker can manufacture a secret shape the full string
        # never had (the marker supplies the word boundary a pattern needs:
        # 'a@bb.como12345' cut after 'm' stores 'a@bb.com…').  A manufactured
        # shape in a stored row makes the verifier refuse every later append
        # on the trial — denial of evidence.  Re-running the value patterns
        # is a no-op on benign strings and can only redact more, never less;
        # growth is bounded by the marker length.
        clean = apply_secret_patterns(clean)
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
            key, key_was_invalid = _scrub_unencodable(str(raw_key)[:80])
            if key_was_invalid:
                notes.append("invalid_unicode")
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
