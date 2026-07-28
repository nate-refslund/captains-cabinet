"""Independent continuity and integrity verifier.

This module deliberately does not call the recorder's append or purge paths.
It re-derives every hash, signature, sequence, previous-hash link, anchor, and
purge-receipt signature from disk and returns bounded findings only.

The one piece of DURABLE state it maintains is its own signed anti-rollback
watermark sidecar (``.verify-watermarks.json`` in the store root): a monotonic,
HMAC-signed high-water mark of every trial's verified length and tip hash,
keyed by hashed trial id so purge receipts stay content-free.  It also keeps
one in-process, non-durable memo of ledger prefixes it has already proved
clean, pinned to the sha256 of exactly those bytes (see ``_verify_events``);
that memo can make verification cheaper and never weaker, and a fresh process
re-derives everything from disk.  It never
mutates ledgers, anchors, controls, or receipts.  Residual limits, by design:
deleting the sidecar (or restoring the whole store directory including it)
resets the anti-rollback protection, because absence is not provable locally
and would need external anchoring; an attacker without the signing key cannot
forge a lowered watermark, because a present-but-invalid sidecar fails closed.
"""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import stat
import threading
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, NamedTuple

from .redaction import contains_secret_shape

EVENT_SCHEMA = "cabinet.evidence-event/v1"
ANCHOR_SCHEMA = "cabinet.evidence-anchor/v1"
PURGE_SCHEMA = "cabinet.evidence-purge-receipt/v1"
WATERMARK_SCHEMA = "cabinet.evidence-watermarks/v1"
WATERMARK_NAME = ".verify-watermarks.json"
WATERMARK_LOCK_NAME = ".verify-watermarks.lock"
HEX64_RE = re.compile(r"[a-f0-9]{64}")
TRIAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
ZERO_HASH = "0" * 64
EVENT_KEYS = frozenset({
    "schema", "event_id", "trial_id", "trace_id", "action_id",
    "correlation_id", "sequence", "phase", "status", "surface", "actor",
    "component", "ts", "timing", "detail", "links", "redactions",
    "diagnostic_mode", "trust", "previous_hash", "event_hash", "signature",
})
PHASES = frozenset({
    "intent", "policy", "execution", "verification", "receipt", "error",
    "undo", "outcome", "transport", "ui", "feedback", "system",
})
STATUSES = frozenset({
    "started", "allowed", "proposed", "succeeded", "refused", "failed",
    "retried", "interrupted", "recovered", "verified", "unverified",
    "undone", "duplicate", "paused", "revoked", "purged", "useful",
    "not_useful", "corrected", "diagnostic",
    # v1.1 absence vocabulary (R-2).  Enum widening is additive: every
    # stored v1 event keeps verifying.  Lockstep: recorder.STATUSES and
    # framework/schemas/evidence-event.schema.json move in the same commit.
    "missed", "skipped", "expired",
})
SURFACES = frozenset({
    "dashboard", "telegram", "world", "companion", "api", "core", "cli",
    "system", "test", "unknown",
})
ACTOR_KINDS = frozenset({"captain", "system", "surface", "officer", "verifier"})


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _key(store_root: Path) -> bytes:
    path = store_root / ".signing-key"
    if path.is_symlink():
        raise ValueError("signing_key_symlink")
    try:
        key = path.read_bytes()
    except OSError as exc:
        raise ValueError("signing_key_unavailable") from exc
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("signing_key_permissions")
    if len(key) < 32:
        raise ValueError("signing_key_invalid")
    return key


def _event_signature(key: bytes, trial_id: str, sequence: int, event_hash: str) -> str:
    message = f"event\n{trial_id}\n{sequence}\n{event_hash}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _object_signature(key: bytes, purpose: str, value: dict[str, Any]) -> str:
    message = purpose.encode("utf-8") + b"\n" + _canonical(value)
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _trial_hash(trial_id: str) -> str:
    return hashlib.sha256(trial_id.encode("utf-8")).hexdigest()


def _resolved(path: Path) -> Path:
    """Absolute, symlink-free spelling, so a memo key names the store DIRECTORY
    rather than the spelling used to reach it.

    Hygiene, not the safety property: soundness rests entirely on the byte
    digest and the key pin below, so even a shared key could not produce a
    wrong verdict — it would only make two stores evict each other's memo on
    every call.
    """
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _fsync_dir(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _load_watermarks(root: Path, key: bytes) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Load the signed anti-rollback watermark index.

    A missing sidecar is a first run and yields an empty index; a sidecar
    that is present but unreadable, unsigned, or malformed is tamper
    evidence and fails closed.
    """
    path = root / WATERMARK_NAME
    if path.is_symlink():
        return {}, ["watermark_invalid"]
    if not path.exists():
        return {}, []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, ["watermark_invalid"]
    if not isinstance(value, dict) or value.get("schema") != WATERMARK_SCHEMA:
        return {}, ["watermark_invalid"]
    supplied = value.get("watermark_signature")
    payload = {name: item for name, item in value.items() if name != "watermark_signature"}
    expected = _object_signature(key, "watermark", payload)
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
        return {}, ["watermark_invalid"]
    raw_trials = value.get("trials")
    if not isinstance(raw_trials, dict):
        return {}, ["watermark_invalid"]
    trials: dict[str, dict[str, Any]] = {}
    for name, item in raw_trials.items():
        if (
            not isinstance(name, str)
            or not HEX64_RE.fullmatch(name)
            or not isinstance(item, dict)
            or set(item) != {"sequence", "event_hash"}
            or isinstance(item.get("sequence"), bool)
            or not isinstance(item.get("sequence"), int)
            or item["sequence"] < 1
            or not isinstance(item.get("event_hash"), str)
            or not HEX64_RE.fullmatch(item["event_hash"])
        ):
            return {}, ["watermark_invalid"]
        trials[name] = {"sequence": item["sequence"], "event_hash": item["event_hash"]}
    return trials, []


def _store_watermarks(root: Path, key: bytes, trials: dict[str, dict[str, Any]]) -> None:
    payload = {"schema": WATERMARK_SCHEMA, "trials": trials}
    signed = {**payload, "watermark_signature": _object_signature(key, "watermark", payload)}
    tmp = root / f"{WATERMARK_NAME}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(signed, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, root / WATERMARK_NAME)
        _fsync_dir(root)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


@contextmanager
def _watermark_lock(root: Path) -> Iterator[None]:
    fd = os.open(
        root / WATERMARK_LOCK_NAME,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _watermark_check(
    root: Path,
    key: bytes,
    trial_id: str,
    event_count: int,
    last_hash: str,
    *,
    advance: bool,
) -> list[str]:
    """Anti-rollback high-water-mark check.

    Rejects any trial whose current length (or same-length tip hash) is below
    the signed watermark recorded on a previous clean verification, then
    advances the mark — never lowering it — when this verification was clean.
    The advance is best-effort: a read-only store skips it silently rather
    than manufacturing a verification failure, so recorded evidence stays
    reviewable anywhere.  A present-but-invalid sidecar is never rewritten;
    tamper evidence is preserved, not healed.
    """
    errors: list[str] = []
    marks, load_errors = _load_watermarks(root, key)
    errors.extend(load_errors)
    recorded = marks.get(_trial_hash(trial_id))
    if recorded is not None:
        if event_count < recorded["sequence"]:
            errors.append("rollback_detected")
        elif event_count == recorded["sequence"] and last_hash != recorded["event_hash"]:
            errors.append("rollback_divergent_history")
    if not advance or errors or event_count < 1:
        return errors
    if recorded is not None and recorded["sequence"] >= event_count:
        return errors
    try:
        with _watermark_lock(root):
            fresh, fresh_errors = _load_watermarks(root, key)
            if fresh_errors:
                errors.extend(fresh_errors)
                return errors
            current = fresh.get(_trial_hash(trial_id))
            if current is not None and current["sequence"] >= event_count:
                return errors
            fresh[_trial_hash(trial_id)] = {"sequence": event_count, "event_hash": last_hash}
            _store_watermarks(root, key, fresh)
    except OSError:
        return errors
    return errors


def _read_ledger_bytes(path: Path) -> tuple[bytes, list[str]]:
    """Raw ledger bytes plus the whole-file framing findings."""
    if not path.is_file():
        return b"", []
    try:
        raw = path.read_bytes()
    except OSError:
        return b"", ["ledger_unreadable"]
    return raw, ["partial_tail"] if raw and not raw.endswith(b"\n") else []


def _frame_event_lines(raw: bytes, first_line: int) -> tuple[list[dict[str, Any]], list[str]]:
    """Frame ledger bytes into rows, numbering findings from ``first_line``.

    Frame rows on b"\\n" ONLY.  bytes.splitlines() also splits on \\r and
    \\r\\n, so a reframed ledger like b'rowA\\rrowB\\n' — bytes the recorder
    never wrote — would silently parse as two chained rows.  The recorder
    writes exactly one JSON object per "\\n", and json.dumps escapes every
    control character inside strings, so a legitimate row never contains a
    raw \\r; any other framing byte is row content and must fail JSON
    parsing here.

    ``first_line`` exists so a suffix scan reports the SAME line numbers a
    whole-file scan would; it is the count of b"\\n" already consumed, plus 1.
    """
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(raw.split(b"\n"), start=first_line):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (UnicodeDecodeError, ValueError):
            errors.append(f"invalid_json_line:{number}")
            continue
        if not isinstance(row, dict):
            errors.append(f"non_object_line:{number}")
            continue
        rows.append(row)
    return rows, errors


class _VerifiedLedger(NamedTuple):
    """A ledger prefix proven clean, pinned to the exact bytes that proved it."""

    length: int           # bytes of events.jsonl the proof covers
    digest: str           # sha256 over exactly those bytes
    key_digest: str       # sha256 of the signing key that proved them
    lines: int            # b"\n" already consumed (finding line numbers)
    count: int            # events verified inside the prefix
    last_hash: str        # RECOMPUTED event_hash of the prefix's last event
    last_signature: str   # that event's stored signature


#: Bounded because a long-lived process can touch many day-bounded trials;
#: eviction only costs a full re-scan, never correctness.
_VERIFIED_MEMO_MAX = 128
_verified_memo: "OrderedDict[tuple[str, str], _VerifiedLedger]" = OrderedDict()
_verified_memo_lock = threading.Lock()


def reset_verified_ledger_memo() -> None:
    """Test seam: drop every memoized clean prefix (the memo is process-global)."""
    with _verified_memo_lock:
        _verified_memo.clear()


def _memo_get(memo_key: tuple[str, str]) -> "_VerifiedLedger | None":
    with _verified_memo_lock:
        entry = _verified_memo.get(memo_key)
        if entry is not None:
            _verified_memo.move_to_end(memo_key)
        return entry


def _memo_put(memo_key: tuple[str, str], entry: _VerifiedLedger) -> None:
    with _verified_memo_lock:
        _verified_memo[memo_key] = entry
        _verified_memo.move_to_end(memo_key)
        while len(_verified_memo) > _VERIFIED_MEMO_MAX:
            _verified_memo.popitem(last=False)


def _verify_events(
    ledger_path: Path,
    key: bytes,
    trial_id: str,
    memo_key: tuple[str, str],
) -> tuple[list[str], int, str, str]:
    """Verify every event in one ledger.

    Returns ``(errors, event_count, last_event_hash, last_signature)`` — the
    same four facts a whole-file scan produces, and byte-for-byte the same
    values, always.

    WHY THIS IS MEMOIZED.  The recorder verifies before it appends, so a
    whole-file re-scan per append makes filing O(n) in the trial and the trial
    O(n^2) overall: a 500-event trial (the R-8 per-trial envelope, so this is
    the LIVE ceiling, not a hypothetical) was costing ~9x a fresh one and
    eating most of the 50ms hook budget the acting chain is held to.

    WHY IT IS STILL THE SAME VERDICT.  The per-row checks are a pure function
    of (row bytes, position in the chain, signing key, trial id) — no clock,
    no environment, no filesystem.  So a prefix whose bytes hash identical to
    bytes that already verified clean under the SAME key yields, by identity
    of inputs, the identical verdict; only the suffix can carry news.  The
    memo therefore stores the sha256 of exactly the bytes it proved, and any
    edit, truncation, reordering or key change misses it and falls back to the
    full scan.  The ONE gate on storing a prefix is a ZERO-finding scan, which
    already excludes a partial tail and an unreadable ledger; the b"\\n"-boundary
    conjunct beside it is belt-and-suspenders, not a second independent guard.
    The permission and anchor checks are NOT memoized — they are properties of
    the filesystem and of anchor.json, not of these bytes, and still run every
    call.
    """
    raw, errors = _read_ledger_bytes(ledger_path)
    key_digest = hashlib.sha256(key).hexdigest()

    offset = 0
    first_line = 1
    sequence = 1
    previous = ZERO_HASH
    last_hash = ZERO_HASH
    last_signature = ""
    memo = _memo_get(memo_key)
    prefix_hash = None
    # The length test is a fast path only: a short ledger's bytes cannot hash to
    # a longer prefix's digest either. The digest and the key pin are the control.
    if memo is not None and memo.key_digest == key_digest and len(raw) >= memo.length:
        prefix_hash = hashlib.sha256(raw[: memo.length])
        if prefix_hash.hexdigest() == memo.digest:
            offset = memo.length
            first_line = memo.lines + 1
            sequence = memo.count + 1
            previous = memo.last_hash
            last_hash = memo.last_hash
            last_signature = memo.last_signature
        else:
            prefix_hash = None  # memo miss: the prefix bytes are not those bytes
    # sha256 over the WHOLE ledger, continuing the prefix hash on a memo hit so
    # the bytes are hashed exactly once on the common path.
    whole_hash = prefix_hash if offset else hashlib.sha256()
    whole_hash.update(raw[offset:])

    rows, frame_errors = _frame_event_lines(raw[offset:], first_line)
    errors.extend(frame_errors)
    for row in rows:
        prefix = f"event:{sequence}"
        errors.extend(_shape_errors(row, prefix))
        if row.get("schema") != EVENT_SCHEMA:
            errors.append(prefix + ":schema")
        if row.get("trial_id") != trial_id:
            errors.append(prefix + ":trial_id")
        if row.get("sequence") != sequence:
            errors.append(prefix + ":sequence")
        if row.get("previous_hash") != previous:
            errors.append(prefix + ":previous_hash")
        supplied_hash = row.get("event_hash")
        supplied_signature = row.get("signature")
        unsigned = {key_name: value for key_name, value in row.items() if key_name not in {"event_hash", "signature"}}
        computed_hash = _digest(unsigned)
        if supplied_hash != computed_hash:
            errors.append(prefix + ":event_hash")
        expected_signature = _event_signature(key, trial_id, sequence, computed_hash)
        if not isinstance(supplied_signature, str) or not hmac.compare_digest(supplied_signature, expected_signature):
            errors.append(prefix + ":signature")
        if contains_secret_shape(row):
            errors.append(prefix + ":secret_shape")
        previous = computed_hash
        last_hash = computed_hash
        last_signature = str(supplied_signature or "")
        sequence += 1

    event_count = sequence - 1
    if not errors and (not raw or raw.endswith(b"\n")):
        _memo_put(memo_key, _VerifiedLedger(
            length=len(raw),
            digest=whole_hash.hexdigest(),
            key_digest=key_digest,
            lines=raw.count(b"\n"),
            count=event_count,
            last_hash=last_hash,
            last_signature=last_signature,
        ))
    return errors, event_count, last_hash, last_signature


def _private_path_error(path: Path, label: str, *, directory: bool = False) -> str | None:
    if path.is_symlink():
        return f"{label}_symlink"
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return f"{label}_unreadable"
    expected_type = path.is_dir() if directory else path.is_file()
    if not expected_type:
        return f"{label}_type"
    return f"{label}_permissions" if mode & 0o077 else None


def _shape_errors(row: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []
    if set(row) != EVENT_KEYS:
        errors.append(prefix + ":fields")
    for name in ("event_id", "trial_id", "trace_id", "action_id", "correlation_id"):
        if not isinstance(row.get(name), str) or not TRIAL_ID_RE.fullmatch(row[name]):
            errors.append(prefix + f":{name}")
    if row.get("phase") not in PHASES:
        errors.append(prefix + ":phase")
    if row.get("status") not in STATUSES:
        errors.append(prefix + ":status")
    if row.get("surface") not in SURFACES:
        errors.append(prefix + ":surface")
    sequence = row.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        errors.append(prefix + ":sequence_shape")
    actor = row.get("actor")
    if not isinstance(actor, dict) or set(actor) != {"kind", "id"}:
        errors.append(prefix + ":actor")
    elif actor.get("kind") not in ACTOR_KINDS or not isinstance(actor.get("id"), str) or not TRIAL_ID_RE.fullmatch(actor["id"]):
        errors.append(prefix + ":actor")
    component = row.get("component")
    if not isinstance(component, dict) or set(component) != {"name", "version", "commit"}:
        errors.append(prefix + ":component")
    elif (
        not isinstance(component.get("name"), str)
        or not TRIAL_ID_RE.fullmatch(component["name"])
        or not isinstance(component.get("version"), str)
        or len(component["version"]) > 80
        or not isinstance(component.get("commit"), str)
        or len(component["commit"]) > 80
    ):
        errors.append(prefix + ":component")
    timing = row.get("timing")
    if not isinstance(timing, dict) or set(timing) != {"elapsed_ms", "duration_ms"}:
        errors.append(prefix + ":timing")
    else:
        for name in ("elapsed_ms", "duration_ms"):
            value = timing.get(name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
                errors.append(prefix + ":timing")
                break
    if not isinstance(row.get("detail"), dict):
        errors.append(prefix + ":detail")
    if (
        not isinstance(row.get("links"), list)
        or len(row["links"]) > 64
        or any(not isinstance(link, str) or len(link) > 512 for link in row["links"])
    ):
        errors.append(prefix + ":links")
    redactions = row.get("redactions")
    if (
        not isinstance(redactions, list)
        or any(not isinstance(item, str) for item in redactions)
        or len(redactions) != len(set(redactions))
    ):
        errors.append(prefix + ":redactions")
    if not isinstance(row.get("diagnostic_mode"), bool):
        errors.append(prefix + ":diagnostic_mode")
    if row.get("trust") != "untrusted_observation":
        errors.append(prefix + ":trust")
    try:
        timestamp = row.get("ts")
        if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
            raise ValueError
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        errors.append(prefix + ":ts")
    for name in ("previous_hash", "event_hash", "signature"):
        value = row.get(name)
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
            errors.append(prefix + f":{name}_shape")
    return errors


def verify_trial(
    store_root: Path | str,
    trial_id: str,
    *,
    require_anchor: bool = True,
) -> dict[str, Any]:
    """Verify one trial without mutating it."""
    root = Path(store_root)
    if not TRIAL_ID_RE.fullmatch(str(trial_id)):
        return {"ok": False, "trial_id": str(trial_id), "errors": ["trial_id_invalid"], "event_count": 0}
    trial = root / "trials" / str(trial_id)
    if not trial.is_dir():
        return {"ok": False, "trial_id": str(trial_id), "errors": ["trial_not_found"], "event_count": 0}
    if trial.is_symlink():
        return {
            "ok": False,
            "schema": "cabinet.evidence-verification/v1",
            "trial_id": str(trial_id),
            "event_count": 0,
            "last_event_hash": ZERO_HASH,
            "errors": ["trial_dir_symlink"],
            "checks": {"owner_permissions": "fail"},
        }
    try:
        key = _key(root)
    except ValueError as exc:
        return {"ok": False, "trial_id": str(trial_id), "errors": [str(exc)], "event_count": 0}

    errors: list[str] = []
    for path, label, directory in (
        (trial, "trial_dir", True),
        (trial / "events.jsonl", "ledger", False),
        (trial / ".lock", "trial_lock", False),
    ):
        permission_error = _private_path_error(path, label, directory=directory)
        if permission_error:
            errors.append(permission_error)
    ledger_path = trial / "events.jsonl"
    if ledger_path.is_symlink():
        # A symlinked ledger is refused above by _private_path_error; its bytes
        # are never read, so there is nothing to verify or memoize.
        event_count, last_hash, last_signature = 0, ZERO_HASH, ""
    else:
        ledger_errors, event_count, last_hash, last_signature = _verify_events(
            ledger_path, key, trial_id, (str(_resolved(root)), str(trial_id)),
        )
        errors.extend(ledger_errors)

    anchor_path = trial / "anchor.json"
    if require_anchor:
        permission_error = _private_path_error(anchor_path, "anchor")
        if permission_error:
            errors.append(permission_error)
        try:
            anchor = None if anchor_path.is_symlink() else json.loads(anchor_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            anchor = None
        if not isinstance(anchor, dict):
            # Fail closed, matching _verify_control/_verify_receipt: there is
            # no legitimate non-dict anchor, and skipping the anchor checks
            # here would let a key-free ledger truncation pass verification.
            errors.append("anchor_missing_or_unreadable")
        else:
            signature = anchor.get("anchor_signature")
            payload = {key_name: value for key_name, value in anchor.items() if key_name != "anchor_signature"}
            expected = _object_signature(key, "anchor", payload)
            if anchor.get("schema") != ANCHOR_SCHEMA:
                errors.append("anchor_schema")
            if anchor.get("trial_id") != trial_id:
                errors.append("anchor_trial_id")
            if anchor.get("sequence") != event_count:
                errors.append("anchor_sequence")
            if anchor.get("event_hash") != last_hash:
                errors.append("anchor_event_hash")
            if anchor.get("event_signature") != last_signature:
                errors.append("anchor_event_signature")
            if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
                errors.append("anchor_signature")

    errors.extend(_watermark_check(
        root, key, trial_id, event_count, last_hash, advance=not errors,
    ))

    unique = sorted(set(errors))
    return {
        "ok": not unique,
        "schema": "cabinet.evidence-verification/v1",
        "trial_id": trial_id,
        "event_count": event_count,
        "last_event_hash": last_hash,
        "errors": unique,
        "checks": {
            "schema_shape": "pass" if not any(any(
                marker in error for marker in (
                    ":fields", ":phase", ":status", ":surface", ":actor",
                    ":component", ":timing", ":detail", ":links",
                    ":redactions", ":diagnostic_mode", ":trust", ":ts",
                    ":event_id", ":trial_id", ":trace_id", ":action_id",
                    ":correlation_id",
                    "_shape",
                )
            ) for error in unique) else "fail",
            "json": "pass" if not any("json" in error or "tail" in error for error in unique) else "fail",
            "sequence": "pass" if not any("sequence" in error for error in unique) else "fail",
            "hash_chain": "pass" if not any("hash" in error for error in unique) else "fail",
            "local_signatures": "pass" if not any("signature" in error or "signing_key" in error for error in unique) else "fail",
            "secret_shapes": "pass" if not any("secret_shape" in error for error in unique) else "fail",
            "anchor": "pass" if not any(error.startswith("anchor") for error in unique) else "fail",
            "owner_permissions": "pass" if not any(
                marker in error for error in unique
                for marker in ("permission", "_symlink", "_type")
            ) else "fail",
        },
    }


def _verify_receipt(key: bytes, path: Path) -> tuple[list[str], dict[str, Any] | None]:
    """Verify one purge receipt; return (errors, receipt-if-validly-signed)."""
    if path.is_symlink():
        return [f"purge_receipt_symlink:{path.name}"], None
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [f"purge_receipt_unreadable:{path.name}"], None
    if not isinstance(receipt, dict) or receipt.get("schema") != PURGE_SCHEMA:
        return [f"purge_receipt_schema:{path.name}"], None
    supplied = receipt.get("receipt_signature")
    payload = {name: value for name, value in receipt.items() if name != "receipt_signature"}
    expected = _object_signature(key, "purge", payload)
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
        return [f"purge_receipt_signature:{path.name}"], None
    return [], receipt


def _verify_control(key: bytes, path: Path) -> list[str]:
    if path.is_symlink():
        return ["control_symlink"]
    try:
        control = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["control_unreadable"]
    if not isinstance(control, dict) or control.get("schema") != "cabinet.evidence-control/v1":
        return ["control_schema"]
    supplied = control.get("control_signature")
    payload = {name: value for name, value in control.items() if name != "control_signature"}
    expected = _object_signature(key, "control", payload)
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
        return ["control_signature"]
    return []


def verify_store(store_root: Path | str) -> dict[str, Any]:
    """Verify every live trial and every content-free purge receipt."""
    root = Path(store_root)
    try:
        key = _key(root)
    except ValueError as exc:
        return {"ok": False, "schema": "cabinet.evidence-store-verification/v1", "errors": [str(exc)], "trials": []}
    trials: list[dict[str, Any]] = []
    live: dict[str, str] = {}
    trial_root = root / "trials"
    if trial_root.is_dir():
        for path in sorted(trial_root.iterdir()):
            if path.is_dir() and TRIAL_ID_RE.fullmatch(path.name):
                trials.append(verify_trial(root, path.name))
                live[_trial_hash(path.name)] = path.name
    errors: list[str] = []
    for path, label, directory in (
        (root, "store_dir", True),
        (root / "control.json", "control", False),
        (root / "purge-receipts", "purge_receipts_dir", True),
    ):
        permission_error = _private_path_error(path, label, directory=directory)
        if permission_error:
            errors.append(permission_error)
    errors.extend(_verify_control(key, root / "control.json"))
    purged: dict[str, str] = {}
    receipt_root = root / "purge-receipts"
    if receipt_root.is_dir():
        for path in sorted(receipt_root.glob("purge-*.json")):
            receipt_errors, receipt = _verify_receipt(key, path)
            errors.extend(receipt_errors)
            if receipt is None:
                continue
            purged_hash = receipt.get("purged_trial_id_hash")
            if isinstance(purged_hash, str) and receipt.get("status") in {"started", "completed"}:
                purged[purged_hash] = str(receipt.get("status"))
    # A live trial whose hashed name matches a validly-signed purge receipt
    # was re-planted next to its own tombstone; purged evidence stays purged.
    for trial_hash, name in sorted(live.items()):
        if trial_hash in purged:
            errors.append(f"purged_trial_resurrected:{name}")
    # A watermarked trial with no live directory and no purge receipt was
    # removed outside the sanctioned purge path.
    marks, watermark_errors = _load_watermarks(root, key)
    errors.extend(watermark_errors)
    for trial_hash in sorted(marks):
        if trial_hash not in live and trial_hash not in purged:
            errors.append(f"trial_removed_without_receipt:{trial_hash[:16]}")
    if any(not result["ok"] for result in trials):
        errors.append("one_or_more_trials_failed")
    return {
        "ok": not errors,
        "schema": "cabinet.evidence-store-verification/v1",
        "trial_count": len(trials),
        "trials": trials,
        "errors": sorted(set(errors)),
    }
