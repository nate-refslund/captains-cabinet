"""Independent, read-only continuity and integrity verifier.

This module deliberately does not call the recorder's append or purge paths.
It re-derives every hash, signature, sequence, previous-hash link, anchor, and
purge-receipt signature from disk and returns bounded findings only.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

from .redaction import contains_secret_shape

EVENT_SCHEMA = "cabinet.evidence-event/v1"
ANCHOR_SCHEMA = "cabinet.evidence-anchor/v1"
PURGE_SCHEMA = "cabinet.evidence-purge-receipt/v1"
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


def _read_event_lines(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if not path.is_file():
        return [], errors
    try:
        raw = path.read_bytes()
    except OSError:
        return [], ["ledger_unreadable"]
    if raw and not raw.endswith(b"\n"):
        errors.append("partial_tail")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(raw.splitlines(), start=1):
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
        rows = []
    else:
        rows, read_errors = _read_event_lines(ledger_path)
        errors.extend(read_errors)
    previous = ZERO_HASH
    last_hash = ZERO_HASH
    last_signature = ""
    for expected_sequence, row in enumerate(rows, start=1):
        prefix = f"event:{expected_sequence}"
        errors.extend(_shape_errors(row, prefix))
        if row.get("schema") != EVENT_SCHEMA:
            errors.append(prefix + ":schema")
        if row.get("trial_id") != trial_id:
            errors.append(prefix + ":trial_id")
        if row.get("sequence") != expected_sequence:
            errors.append(prefix + ":sequence")
        if row.get("previous_hash") != previous:
            errors.append(prefix + ":previous_hash")
        supplied_hash = row.get("event_hash")
        supplied_signature = row.get("signature")
        unsigned = {key_name: value for key_name, value in row.items() if key_name not in {"event_hash", "signature"}}
        computed_hash = _digest(unsigned)
        if supplied_hash != computed_hash:
            errors.append(prefix + ":event_hash")
        expected_signature = _event_signature(key, trial_id, expected_sequence, computed_hash)
        if not isinstance(supplied_signature, str) or not hmac.compare_digest(supplied_signature, expected_signature):
            errors.append(prefix + ":signature")
        if contains_secret_shape(row):
            errors.append(prefix + ":secret_shape")
        previous = computed_hash
        last_hash = computed_hash
        last_signature = str(supplied_signature or "")

    anchor_path = trial / "anchor.json"
    if require_anchor:
        permission_error = _private_path_error(anchor_path, "anchor")
        if permission_error:
            errors.append(permission_error)
        try:
            anchor = None if anchor_path.is_symlink() else json.loads(anchor_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            errors.append("anchor_missing_or_unreadable")
            anchor = None
        if isinstance(anchor, dict):
            signature = anchor.get("anchor_signature")
            payload = {key_name: value for key_name, value in anchor.items() if key_name != "anchor_signature"}
            expected = _object_signature(key, "anchor", payload)
            if anchor.get("schema") != ANCHOR_SCHEMA:
                errors.append("anchor_schema")
            if anchor.get("trial_id") != trial_id:
                errors.append("anchor_trial_id")
            if anchor.get("sequence") != len(rows):
                errors.append("anchor_sequence")
            if anchor.get("event_hash") != last_hash:
                errors.append("anchor_event_hash")
            if anchor.get("event_signature") != last_signature:
                errors.append("anchor_event_signature")
            if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
                errors.append("anchor_signature")

    unique = sorted(set(errors))
    return {
        "ok": not unique,
        "schema": "cabinet.evidence-verification/v1",
        "trial_id": trial_id,
        "event_count": len(rows),
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


def _verify_receipt(key: bytes, path: Path) -> list[str]:
    if path.is_symlink():
        return [f"purge_receipt_symlink:{path.name}"]
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [f"purge_receipt_unreadable:{path.name}"]
    if not isinstance(receipt, dict) or receipt.get("schema") != PURGE_SCHEMA:
        return [f"purge_receipt_schema:{path.name}"]
    supplied = receipt.get("receipt_signature")
    payload = {name: value for name, value in receipt.items() if name != "receipt_signature"}
    expected = _object_signature(key, "purge", payload)
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
        return [f"purge_receipt_signature:{path.name}"]
    return []


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
    trial_root = root / "trials"
    if trial_root.is_dir():
        for path in sorted(trial_root.iterdir()):
            if path.is_dir() and TRIAL_ID_RE.fullmatch(path.name):
                trials.append(verify_trial(root, path.name))
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
    receipt_root = root / "purge-receipts"
    if receipt_root.is_dir():
        for path in sorted(receipt_root.glob("purge-*.json")):
            errors.extend(_verify_receipt(key, path))
    if any(not result["ok"] for result in trials):
        errors.append("one_or_more_trials_failed")
    return {
        "ok": not errors,
        "schema": "cabinet.evidence-store-verification/v1",
        "trial_count": len(trials),
        "trials": trials,
        "errors": sorted(set(errors)),
    }
