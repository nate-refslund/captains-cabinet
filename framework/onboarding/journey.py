"""Canonical Cabinet Onboarding v2 journey.

This module is the one state/event/card core consumed by Dashboard, Telegram,
and Cabinet World.  Surfaces may render and submit actions; they do not own an
onboarding state machine.

The first production slice is deliberately narrow and useful:

1. capture a purpose and relationship *destination* (never an authority grant),
2. propose a read-only First Window over one local folder,
3. bind the exact scope and limits into an Orientation Charter,
4. read only after the Captain ratifies that Charter hash,
5. return one honest, source-cited First Dividend.

All state stays below ``instance/onboarding/v2`` — a surface the mission
compiler never reads.  Events are append-only, state/artifacts are atomic,
actions are idempotent, and a process lock serializes cross-surface races.
``purge`` is the sole destructive lifecycle operation: it requires the literal
confirmation ``PURGE`` and writes a content-free intent receipt before removing
state, event history, manifests, and derived excerpts. An interrupted purge is
completed on the next locked read rather than silently reopening onboarding.

No network, subprocess, connector, write into a granted source, or LLM call is
possible in this module.  The dividend detectors are deterministic so their
claims can be tested and cited rather than performed.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = "cabinet.onboarding-journey/v2"
CARD_SCHEMA = "cabinet.onboarding-card/v1"
CHARTER_SCHEMA = "cabinet.orientation-charter/v1"
MANIFEST_SCHEMA = "cabinet.first-window-manifest/v1"
DIVIDEND_SCHEMA = "cabinet.first-dividend/v1"
EVENT_SCHEMA = "cabinet.onboarding-event/v1"

DATA_REL = "instance/onboarding/v2"
LOCK_REL = "instance/onboarding/.onboarding-v2.lock"
PURGE_RECEIPTS_REL = "instance/onboarding/purge-receipts"
STATE_NAME = "state.json"
EVENTS_NAME = "events.jsonl"
CHARTER_NAME = "orientation-charter.json"
MANIFEST_NAME = "first-window-manifest.json"
DIVIDEND_NAME = "first-dividend.json"

DESTINATIONS = {
    "earn": "Earn every responsibility",
    "reversible": "Be proactive where actions are reversible",
    "sovereign": "Aim for broad autonomy after it is earned",
}
ORIENTATION_MODE = "observe_only"

MAX_FILES = 200
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 128 * 1024
ALLOWED_SUFFIXES = {
    ".md", ".mdx", ".txt", ".rst", ".json", ".yml", ".yaml", ".toml",
    ".csv", ".tsv", ".py", ".ts", ".tsx", ".js", ".jsx", ".swift",
    ".go", ".rs", ".java", ".sh", ".sql",
}
ALLOWED_BASENAMES = {
    "readme", "license", "dockerfile", "makefile", "procfile",
}
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", "node_modules", "vendor",
    "dist", "build", ".next", ".cache", "coverage", "__pycache__", ".venv",
    "venv", "target",
}
SENSITIVE_NAME_RE = re.compile(
    r"(^|[._-])(\.env|secret|secrets|credential|credentials|token|tokens|"
    r"private[-_]?key|id_rsa|id_ed25519)([._-]|$)", re.I
)
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore"}
SECRET_LINE_RES = (
    re.compile(r"(?i)\b(api[_ -]?key|secret|token|password|authorization|credential|private\s+key)\b"),
    re.compile(r"\b[0-9]{8,12}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


class JourneyError(RuntimeError):
    """A user-correctable, code-bearing onboarding refusal."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def cabinet_root() -> Path:
    env_root = os.environ.get("CABINET_ROOT")
    return Path(env_root) if env_root else Path(__file__).resolve().parents[2]


def _now(now: str | None = None) -> str:
    return now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _data_dir(root: Path) -> Path:
    return root / DATA_REL


def _state_path(root: Path) -> Path:
    return _data_dir(root) / STATE_NAME


def _events_path(root: Path) -> Path:
    return _data_dir(root) / EVENTS_NAME


def _secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def _fsync_dir(path: Path) -> None:
    """Best-effort durability for newly replaced/created directory entries."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _atomic_json(path: Path, value: Any) -> None:
    _secure_dir(path.parent)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def _append_event(root: Path, row: dict[str, Any]) -> None:
    path = _events_path(root)
    _secure_dir(path.parent)
    encoded = (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    existed = path.exists()
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.fchmod(fd, 0o600)
    except OSError:
        pass
    with os.fdopen(fd, "a+b") as fh:
        # A killed process can leave a non-fsynced partial JSON tail. It was
        # never a committed event; trim only that tail before appending so it
        # cannot swallow the next valid row into one malformed line.
        fh.seek(0, os.SEEK_END)
        end = fh.tell()
        if end:
            fh.seek(end - 1)
            if fh.read(1) != b"\n":
                cursor = end
                newline_at = -1
                while cursor > 0 and newline_at < 0:
                    start = max(0, cursor - 8192)
                    fh.seek(start)
                    chunk = fh.read(cursor - start)
                    found = chunk.rfind(b"\n")
                    if found >= 0:
                        newline_at = start + found
                    cursor = start
                fh.truncate(newline_at + 1 if newline_at >= 0 else 0)
        fh.seek(0, os.SEEK_END)
        fh.write(encoded)
        fh.flush()
        os.fsync(fh.fileno())
    if not existed:
        _fsync_dir(path.parent)


@contextmanager
def _locked(root: Path) -> Iterator[None]:
    lock_path = root / LOCK_REL
    _secure_dir(lock_path.parent)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a+", encoding="utf-8") as lock:
        try:
            os.fchmod(lock.fileno(), 0o600)
        except OSError:
            pass
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _fresh_state(now: str | None = None, *, stage: str = "welcome") -> dict[str, Any]:
    ts = _now(now)
    return {
        "schema": SCHEMA,
        "journey_id": f"journey-{uuid.uuid4().hex[:12]}",
        "revision": 0,
        "stage": stage,
        "purpose": None,
        "relationship_destination": None,
        "orientation_mode": ORIENTATION_MODE,
        "access": "not_granted",
        "source": None,
        "charter": None,
        "first_dividend": None,
        "created_at": ts,
        "updated_at": ts,
    }


def _load_state(root: Path, *, create: bool = True) -> dict[str, Any]:
    _recover_pending_purge(root)
    path = _state_path(root)
    if not path.is_file():
        state = _fresh_state()
        if create:
            _atomic_json(path, state)
        return state
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise JourneyError("state_unreadable", "Onboarding state is unreadable; no action was taken.") from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise JourneyError("state_schema", "Onboarding state has an unsupported schema; no action was taken.")
    # Crash recovery: the event is fsync'd before the projection is replaced.
    # If power is lost between those steps, replay the newest committed `after`
    # projection and its non-raw manifest instead of repeating the action.
    latest = next(
        (
            row for row in reversed(_read_events(root))
            if isinstance(row.get("after"), dict)
            and int(row["after"].get("revision", -1)) > int(value.get("revision", -1))
        ),
        None,
    )
    if latest:
        value = deepcopy(latest["after"])
        if create:
            _atomic_json(path, value)
            _sync_artifacts(root, value, manifest=latest.get("manifest"))
    return value


def _read_events(root: Path) -> list[dict[str, Any]]:
    path = _events_path(root)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _finish_purge(
    root: Path,
    receipt_path: Path,
    receipt: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Idempotently complete a content-free purge intent."""
    data = _data_dir(root)
    if data.exists():
        shutil.rmtree(data)
    fresh = _fresh_state(str(receipt["purged_at"]), stage="purged")
    _atomic_json(_state_path(root), fresh)
    event = {
        "schema": EVENT_SCHEMA,
        "event_id": f"evt-{uuid.uuid4().hex}",
        "action_id": str(receipt["action_id"]),
        "action": "purge",
        "surface": str(receipt["surface"]),
        "ts": str(receipt["purged_at"]),
        "reversible": False,
        "purged_journey_id_hash": str(receipt["purged_journey_id_hash"]),
    }
    _append_event(root, event)
    completed = {
        **receipt,
        "status": "completed",
        "note": (
            "State, events, manifests, charter, and derived excerpts were removed. "
            "No source path or content is retained here."
        ),
    }
    _atomic_json(receipt_path, completed)
    return fresh, completed


def _recover_pending_purge(root: Path) -> None:
    receipts = root / PURGE_RECEIPTS_REL
    if not receipts.is_dir():
        return
    for path in sorted(receipts.glob("purge-*.json")):
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(receipt, dict) and receipt.get("status") == "started":
            _finish_purge(root, path, receipt)


def _event_for_action(root: Path, action_id: str | None) -> dict[str, Any] | None:
    if not action_id:
        return None
    for row in reversed(_read_events(root)):
        if row.get("action_id") == action_id:
            return row
    return None


def _card(state: dict[str, Any]) -> dict[str, Any]:
    stage = str(state["stage"])
    suffix = ""
    if state.get("charter"):
        suffix = ":" + str(state["charter"].get("hash", ""))[:12]
    card_id = f"onboarding:{state['journey_id']}:{stage}{suffix}"
    common: dict[str, Any] = {
        "schema": CARD_SCHEMA,
        "id": card_id,
        "journey_id": state["journey_id"],
        "revision": state["revision"],
        "stage": stage,
        "status": "open",
        "evidence": [],
        "options": [],
    }
    if stage in {"welcome", "purged"}:
        common.update(
            kind="first_window",
            title="Let me earn my first responsibility",
            body=(
                "Choose one folder and tell me what you want made easier. I will first show "
                "you exactly what I would read. Nothing is opened until you approve that Charter."
            ),
            options=[
                {"action": "propose_window", "label": "Choose a folder"},
            ],
        )
    elif stage == "charter_pending":
        charter = state["charter"]
        source = state["source"]
        common.update(
            kind="orientation_charter",
            title="Your First Window is ready for approval",
            body=(
                f"Read-only access to “{source['label']}” for this purpose: {state['purpose']}. "
                f"I will inspect at most {MAX_FILES} supported text files ({MAX_TOTAL_BYTES // 1024 // 1024} MB total), "
                "skip secrets, hidden/system folders, binaries, and every symlink, and make no changes. "
                f"Charter fingerprint: {charter['hash'][:12]}."
            ),
            options=[
                {"action": "ratify_charter", "label": "Approve and find one useful thing"},
                {"action": "propose_window", "label": "Change it"},
                {"action": "purge", "label": "Delete onboarding data", "danger": True},
            ],
        )
    elif stage == "dividend_ready":
        dividend = state["first_dividend"]
        finding = dividend["finding"]
        common.update(
            kind="first_dividend",
            title="I found something worth your attention" if finding["quality"] == "strong" else "Your first map is ready",
            body=finding["summary"],
            evidence=finding["citations"],
            options=[
                {"action": "continue", "label": "Show me the deeper orientation"},
                {"action": "pause", "label": "Pause here"},
                {"action": "revoke", "label": "Revoke folder access"},
                {"action": "purge", "label": "Delete onboarding data", "danger": True},
            ],
        )
    elif stage == "orientation_offered":
        common.update(
            kind="deep_orientation",
            title="The low floor is proven; the high ceiling stays gated",
            body=(
                "Next I can spend hours building a source map, Strategy Mirror, proposed officer shape, "
                "and lane-by-lane autonomy examples. This invitation grants no new access or authority; "
                "each additional source and every operational permission will be requested just in time."
            ),
            options=[
                {"action": "pause", "label": "Pause here"},
                {"action": "revoke", "label": "Revoke folder access"},
                {"action": "purge", "label": "Delete onboarding data", "danger": True},
            ],
        )
    elif stage == "paused":
        common.update(
            kind="paused",
            title="Onboarding is paused",
            body="Your First Window will not be read again while paused. You can continue, revoke access, undo, or purge.",
            options=[
                {"action": "continue", "label": "Continue"},
                {"action": "revoke", "label": "Revoke folder access"},
                {"action": "undo", "label": "Undo last choice"},
                {"action": "purge", "label": "Delete onboarding data", "danger": True},
            ],
        )
    elif stage == "revoked":
        common.update(
            kind="revoked",
            title="Folder access is revoked",
            body="The Cabinet will not read this source again. Derived onboarding artifacts remain until you undo or purge them.",
            options=[
                {"action": "undo", "label": "Restore the previous state"},
                {"action": "propose_window", "label": "Choose another folder"},
                {"action": "purge", "label": "Delete onboarding data", "danger": True},
            ],
        )
    else:
        common.update(
            kind="status",
            title="Onboarding status",
            body=f"Current stage: {stage}.",
            options=[{"action": "undo", "label": "Undo last choice"}],
        )
    return common


def snapshot(root: Path | str | None = None) -> dict[str, Any]:
    base = Path(root) if root else cabinet_root()
    with _locked(base):
        state = _load_state(base)
        return {"ok": True, "state": deepcopy(state), "card": _card(state)}


def _validate_source(raw: Any) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise JourneyError("source_required", "Choose a folder before continuing.")
    candidate = Path(raw.strip()).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise JourneyError("source_missing", "That folder could not be found.") from exc
    if not resolved.is_dir():
        raise JourneyError("source_not_folder", "The First Window must be a folder.")
    if candidate.is_symlink():
        raise JourneyError("source_symlink", "Choose the real folder, not a shortcut or symlink.")
    home = Path.home().resolve()
    if resolved == Path(resolved.anchor) or resolved == home:
        raise JourneyError("source_too_broad", "Choose a specific folder, not the whole disk or home folder.")
    return resolved


def _validate_purpose(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise JourneyError("purpose_required", "Tell me what you want this First Window to make easier.")
    purpose = " ".join(raw.strip().split())
    if len(purpose) > 300:
        raise JourneyError("purpose_too_long", "Keep the first purpose under 300 characters.")
    return purpose


def _build_charter(source: Path, purpose: str, destination: str) -> dict[str, Any]:
    payload = {
        "schema": CHARTER_SCHEMA,
        "purpose": purpose,
        "relationship_destination": {
            "id": destination,
            "label": DESTINATIONS[destination],
            "authority_effect": "none; this is a destination, not a grant",
        },
        "orientation_mode": ORIENTATION_MODE,
        "source": {
            "kind": "folder",
            "root": str(source),
            "label": source.name or str(source),
        },
        "permission": {
            "read_only": True,
            "writes_to_source": False,
            "network": False,
            "connectors": False,
            "follow_symlinks": False,
        },
        "limits": {
            "max_files": MAX_FILES,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "max_file_bytes": MAX_FILE_BYTES,
            "allowed_suffixes": sorted(ALLOWED_SUFFIXES),
        },
        "exclusions": {
            "directories": sorted(SKIP_DIRS),
            "sensitive_names": True,
            "hidden_entries": True,
            "binary_files": True,
        },
        "retention": {
            "raw_file_contents": "not persisted",
            "derived_excerpts": "only cited, secret-redacted lines",
            "purge": "Captain may delete state, events, manifests, and derived excerpts",
        },
    }
    return {"payload": payload, "hash": _hash(payload), "status": "pending"}


def _is_hidden_rel(rel: Path) -> bool:
    return any(part.startswith(".") for part in rel.parts)


def _is_sensitive(rel: Path) -> bool:
    name = rel.name
    return (
        bool(SENSITIVE_NAME_RE.search(name))
        or rel.suffix.lower() in SENSITIVE_SUFFIXES
        or any(SENSITIVE_NAME_RE.search(part) for part in rel.parts)
    )


def _allowed_file(path: Path) -> bool:
    return path.suffix.lower() in ALLOWED_SUFFIXES or path.name.lower() in ALLOWED_BASENAMES


def _redact_excerpt(text: str) -> str:
    clean = " ".join(text.strip().split())[:300]
    if any(rx.search(clean) for rx in SECRET_LINE_RES):
        return "[sensitive value redacted]"
    return clean


def _citation(entry: dict[str, Any], line_no: int, line: str) -> dict[str, Any]:
    return {
        "path": entry["path"],
        "line": line_no,
        "excerpt": _redact_excerpt(line),
        "sha256": entry["sha256"],
    }


def _scan_source(source: Path, charter_hash: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    total = 0
    truncated = False
    for current, dirnames, filenames in os.walk(source, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_dirs = []
        for dirname in sorted(dirnames):
            child = current_path / dirname
            rel = child.relative_to(source)
            if dirname in SKIP_DIRS or _is_hidden_rel(rel) or _is_sensitive(rel) or child.is_symlink():
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs
        for filename in sorted(filenames):
            if len(entries) >= MAX_FILES or total >= MAX_TOTAL_BYTES:
                truncated = True
                break
            path = current_path / filename
            rel = path.relative_to(source)
            if _is_hidden_rel(rel) or _is_sensitive(rel) or not _allowed_file(path):
                continue
            try:
                lst = path.lstat()
                if stat.S_ISLNK(lst.st_mode) or not stat.S_ISREG(lst.st_mode):
                    continue
                resolved = path.resolve(strict=True)
                resolved.relative_to(source)
                if lst.st_size > MAX_FILE_BYTES or total + lst.st_size > MAX_TOTAL_BYTES:
                    truncated = True
                    continue
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(path, flags)
                try:
                    opened = os.fstat(fd)
                    if (
                        not stat.S_ISREG(opened.st_mode)
                        or opened.st_size > MAX_FILE_BYTES
                        or (opened.st_dev, opened.st_ino) != (lst.st_dev, lst.st_ino)
                    ):
                        continue
                    with os.fdopen(fd, "rb", closefd=False) as fh:
                        raw = fh.read(MAX_FILE_BYTES + 1)
                finally:
                    os.close(fd)
            except (OSError, RuntimeError, ValueError):
                continue
            if len(raw) > MAX_FILE_BYTES or total + len(raw) > MAX_TOTAL_BYTES:
                truncated = True
                continue
            if b"\x00" in raw[:4096]:
                continue
            text = raw.decode("utf-8", errors="replace")
            digest = hashlib.sha256(raw).hexdigest()
            entries.append({
                "path": rel.as_posix(),
                "bytes": len(raw),
                "sha256": digest,
                "text": text,
                "lines": text.splitlines(),
            })
            total += len(raw)
        if len(entries) >= MAX_FILES or total >= MAX_TOTAL_BYTES:
            truncated = True
            break
    manifest_files = [
        {"path": e["path"], "bytes": e["bytes"], "sha256": e["sha256"]}
        for e in entries
    ]
    manifest_payload = {
        "schema": MANIFEST_SCHEMA,
        "charter_hash": charter_hash,
        "source_label": source.name,
        "files": manifest_files,
        "file_count": len(manifest_files),
        "total_bytes": total,
        "truncated_by_limits": truncated,
    }
    manifest = {**manifest_payload, "manifest_hash": _hash(manifest_payload)}
    return manifest, entries


def _command_drift(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    packages: list[tuple[dict[str, Any], set[str], str]] = []
    for entry in entries:
        if Path(entry["path"]).name != "package.json":
            continue
        try:
            obj = json.loads(entry["text"])
        except ValueError:
            continue
        scripts = obj.get("scripts", {}) if isinstance(obj, dict) else {}
        if isinstance(scripts, dict):
            packages.append((entry, {str(k) for k in scripts}, str(Path(entry["path"]).parent)))
    if not packages:
        return findings
    command_re = re.compile(
        r"\b(?:npm\s+run|pnpm(?:\s+run)?|yarn)\s+([a-zA-Z0-9:_-]+)\b"
    )
    builtin = {"add", "audit", "exec", "help", "init", "install", "remove", "run", "update"}
    for entry in entries:
        if Path(entry["path"]).suffix.lower() not in {".md", ".mdx", ".rst", ".txt"}:
            continue
        for line_no, line in enumerate(entry["lines"], start=1):
            for match in command_re.finditer(line):
                command = match.group(1)
                if command in builtin:
                    continue
                _, scripts, _ = packages[0]
                if command not in scripts:
                    findings.append({
                        "score": 100,
                        "kind": "software_command_drift",
                        "quality": "strong",
                        "summary": (
                            f"The documentation tells someone to run “{command}”, but that script is not declared in package.json. "
                            "That can break onboarding or a release at the exact moment someone follows the documented path."
                        ),
                        "citations": [_citation(entry, line_no, line)],
                    })
    return findings


def _contradictions(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labeled: dict[str, list[tuple[str, dict[str, Any], int, str]]] = {}
    label_re = re.compile(
        r"^\s*(?:[-*]\s*)?(launch(?:\s+date)?|go[- ]?live(?:\s+date)?|deadline|delivery\s+date)\s*[:=-]\s*(.+?)\s*$",
        re.I,
    )
    for entry in entries:
        for line_no, line in enumerate(entry["lines"], start=1):
            match = label_re.match(line)
            if not match:
                continue
            key = re.sub(r"[^a-z]", "", match.group(1).lower())
            value = " ".join(match.group(2).lower().split())
            labeled.setdefault(key, []).append((value, entry, line_no, line))
    out: list[dict[str, Any]] = []
    for key, rows in labeled.items():
        values = {r[0] for r in rows}
        if len(values) < 2:
            continue
        first_by_value: list[tuple[str, dict[str, Any], int, str]] = []
        seen: set[str] = set()
        for row in rows:
            if row[0] not in seen:
                first_by_value.append(row)
                seen.add(row[0])
        citations = [_citation(r[1], r[2], r[3]) for r in first_by_value[:3]]
        label = "launch/deadline"
        out.append({
            "score": 90,
            "kind": "conflicting_commitment",
            "quality": "strong",
            "summary": (
                f"I found conflicting {label} statements in the folder. Before work is planned around the wrong date, "
                "choose which source is current and retire the other wording."
            ),
            "citations": citations,
        })
    return out


def _risk_markers(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    urgent = re.compile(r"\b(urgent|blocked|overdue|needs action|action required)\b", re.I)
    todo = re.compile(r"\b(todo|fixme|xxx)\b", re.I)
    out: list[dict[str, Any]] = []
    for entry in entries:
        for line_no, line in enumerate(entry["lines"], start=1):
            if urgent.search(line):
                out.append({
                    "score": 80,
                    "kind": "attention_marker",
                    "quality": "strong",
                    "summary": (
                        "A source inside the First Window explicitly marks something as urgent, blocked, overdue, or needing action. "
                        "It is the clearest immediate candidate for Captain attention."
                    ),
                    "citations": [_citation(entry, line_no, line)],
                })
            elif todo.search(line):
                out.append({
                    "score": 50,
                    "kind": "open_work_marker",
                    "quality": "strong",
                    "summary": "I found an explicit open-work marker that may otherwise stay buried in the folder.",
                    "citations": [_citation(entry, line_no, line)],
                })
    return out


def _first_dividend(manifest: dict[str, Any], entries: list[dict[str, Any]], now: str) -> dict[str, Any]:
    findings = _command_drift(entries) + _contradictions(entries) + _risk_markers(entries)
    findings.sort(
        key=lambda item: (
            -int(item["score"]),
            str(item["citations"][0]["path"]) if item["citations"] else "",
            int(item["citations"][0]["line"]) if item["citations"] else 0,
        )
    )
    if findings:
        finding = findings[0]
    elif entries:
        first = entries[0]
        finding = {
            "score": 10,
            "kind": "orientation_map",
            "quality": "orientation_only",
            "summary": (
                f"I mapped {manifest['file_count']} supported files but did not find a strong contradiction, broken documented command, "
                "or explicit urgent marker. That is an honest orientation result, not a manufactured warning."
            ),
            "citations": [_citation(first, 1, first["lines"][0] if first["lines"] else first["path"])],
        }
    else:
        finding = {
            "score": 0,
            "kind": "empty_window",
            "quality": "orientation_only",
            "summary": "The approved folder contained no supported, non-sensitive text files within the First Window limits.",
            "citations": [],
        }
    payload = {
        "schema": DIVIDEND_SCHEMA,
        "generated_at": now,
        "manifest_hash": manifest["manifest_hash"],
        "finding": finding,
        "detectors": ["software_command_drift", "conflicting_commitment", "attention_marker"],
        "raw_source_persisted": False,
    }
    return {**payload, "dividend_hash": _hash(payload)}


def _sync_artifacts(root: Path, state: dict[str, Any], *, manifest: dict[str, Any] | None = None) -> None:
    data = _data_dir(root)
    _secure_dir(data)
    charter_path = data / CHARTER_NAME
    manifest_path = data / MANIFEST_NAME
    dividend_path = data / DIVIDEND_NAME
    if state.get("charter"):
        _atomic_json(charter_path, state["charter"])
    elif charter_path.exists():
        charter_path.unlink()
    if manifest is not None:
        _atomic_json(manifest_path, manifest)
    elif not state.get("first_dividend") and manifest_path.exists():
        manifest_path.unlink()
    if state.get("first_dividend"):
        _atomic_json(dividend_path, state["first_dividend"])
    elif dividend_path.exists():
        dividend_path.unlink()


def _current_manifest(root: Path, state: dict[str, Any]) -> dict[str, Any] | None:
    """Return the current bounded manifest only when it matches state.

    A proposal can replace a completed First Window. Its event needs the old
    non-content manifest so undo can restore a coherent dividend + manifest
    pair. Corrupt or stale artifacts are never copied into event history.
    """
    expected = (state.get("source") or {}).get("manifest_hash")
    path = _data_dir(root) / MANIFEST_NAME
    if not expected or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict) or value.get("manifest_hash") != expected:
        return None
    payload = {key: item for key, item in value.items() if key != "manifest_hash"}
    return value if _hash(payload) == expected else None


def _commit(
    root: Path,
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    action: str,
    action_id: str,
    surface: str,
    now: str,
    reversible: bool = True,
    undo_of: str | None = None,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    after = deepcopy(after)
    after["revision"] = int(before.get("revision", 0)) + 1
    after["updated_at"] = now
    row = {
        "schema": EVENT_SCHEMA,
        "event_id": f"evt-{uuid.uuid4().hex}",
        "action_id": action_id,
        "action": action,
        "surface": surface,
        "ts": now,
        "reversible": reversible,
        "undo_of": undo_of,
        "before": before,
        "after": after,
    }
    if before.get("first_dividend") and not after.get("first_dividend"):
        before_manifest = _current_manifest(root, before)
        if before_manifest is not None:
            row["before_manifest"] = before_manifest
    if manifest is not None:
        row["manifest"] = manifest
    _append_event(root, row)
    _atomic_json(_state_path(root), after)
    _sync_artifacts(root, after, manifest=manifest)
    return {"ok": True, "event": {k: row[k] for k in ("event_id", "action_id", "action", "surface", "ts")}, "state": after, "card": _card(after)}


def _purge(root: Path, state: dict[str, Any], request: dict[str, Any], *, surface: str, now: str) -> dict[str, Any]:
    if request.get("confirmation") != "PURGE":
        raise JourneyError("purge_confirmation", "Type PURGE exactly to delete onboarding data.")
    action_id = str(request.get("action_id") or f"purge-{uuid.uuid4().hex}")
    receipt = {
        "schema": "cabinet.onboarding-purge-receipt/v1",
        "purged_at": now,
        "purged_journey_id_hash": hashlib.sha256(state["journey_id"].encode("utf-8")).hexdigest(),
        "surface": surface,
        "action_id": action_id,
        "status": "started",
        "note": "Purge intent recorded; completion is pending.",
    }
    receipts = root / PURGE_RECEIPTS_REL
    _secure_dir(receipts)
    receipt_path = receipts / f"purge-{now.replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:6]}.json"
    _atomic_json(receipt_path, receipt)
    fresh, completed = _finish_purge(root, receipt_path, receipt)
    return {"ok": True, "purged": True, "state": fresh, "card": _card(fresh), "receipt": completed}


def act(
    request: dict[str, Any],
    root: Path | str | None = None,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Apply one canonical action and return the same snapshot every surface renders."""
    if not isinstance(request, dict):
        raise JourneyError("request_shape", "The onboarding action must be an object.")
    base = Path(root) if root else cabinet_root()
    action = str(request.get("action") or "").strip()
    if not action:
        raise JourneyError("action_required", "Choose an onboarding action.")
    surface = str(request.get("surface") or "unknown")
    if surface not in {"dashboard", "telegram", "world", "companion", "cli", "test", "unknown"}:
        raise JourneyError("surface_invalid", "Unknown onboarding surface.")
    action_id = str(request.get("action_id") or f"act-{uuid.uuid4().hex}")
    if len(action_id) > 128 or not re.fullmatch(r"[A-Za-z0-9._:-]+", action_id):
        raise JourneyError("action_id_invalid", "The onboarding action id is invalid.")
    ts = _now(now)

    with _locked(base):
        state = _load_state(base)
        duplicate = _event_for_action(base, action_id)
        if duplicate:
            current = _load_state(base)
            return {"ok": True, "duplicate": True, "event_id": duplicate.get("event_id"), "state": current, "card": _card(current)}
        expected = request.get("expected_revision")
        if expected is not None:
            if (
                isinstance(expected, bool)
                or not isinstance(expected, (int, str))
                or (isinstance(expected, str) and not re.fullmatch(r"[0-9]+", expected))
            ):
                raise JourneyError("revision_invalid", "The onboarding card revision is invalid.")
            try:
                expected_revision = int(expected)
            except (TypeError, ValueError) as exc:
                raise JourneyError("revision_invalid", "The onboarding card revision is invalid.") from exc
            if expected_revision != int(state["revision"]):
                raise JourneyError("revision_conflict", "This card changed on another surface. I refreshed it; please use the current choice.")
        if action == "purge":
            return _purge(base, state, request, surface=surface, now=ts)
        if action == "propose_window":
            source = _validate_source(request.get("source"))
            purpose = _validate_purpose(request.get("purpose"))
            destination = str(request.get("relationship_destination") or "reversible")
            if destination not in DESTINATIONS:
                raise JourneyError("destination_invalid", "Choose earn, reversible, or sovereign as the trust destination.")
            charter = _build_charter(source, purpose, destination)
            after = deepcopy(state)
            after.update(
                stage="charter_pending",
                purpose=purpose,
                relationship_destination=destination,
                orientation_mode=ORIENTATION_MODE,
                access="not_granted",
                source={"kind": "folder", "root": str(source), "label": source.name, "status": "proposed"},
                charter=charter,
                first_dividend=None,
            )
            return _commit(base, state, after, action=action, action_id=action_id, surface=surface, now=ts)
        if action == "ratify_charter":
            if state["stage"] != "charter_pending" or not state.get("charter") or not state.get("source"):
                raise JourneyError("charter_not_pending", "There is no current Charter waiting for approval.")
            supplied = str(request.get("charter_hash") or "")
            expected_hash = str(state["charter"]["hash"])
            if supplied != expected_hash or _hash(state["charter"]["payload"]) != expected_hash:
                raise JourneyError("charter_hash_mismatch", "That Charter is stale or changed. Review the current Charter before approving.")
            source = _validate_source(state["source"]["root"])
            if str(source) != state["charter"]["payload"]["source"]["root"]:
                raise JourneyError("source_changed", "The source path no longer matches the approved Charter.")
            manifest, entries = _scan_source(source, expected_hash)
            dividend = _first_dividend(manifest, entries, ts)
            after = deepcopy(state)
            after["stage"] = "dividend_ready"
            after["access"] = "active_read_only"
            after["source"]["status"] = "ratified_read_only"
            after["source"]["manifest_hash"] = manifest["manifest_hash"]
            after["charter"]["status"] = "ratified"
            after["charter"]["ratified_at"] = ts
            after["first_dividend"] = dividend
            return _commit(base, state, after, action=action, action_id=action_id, surface=surface, now=ts, manifest=manifest)
        if action == "continue":
            if state["stage"] not in {"dividend_ready", "paused", "orientation_offered"}:
                raise JourneyError("continue_unavailable", "There is nothing ready to continue yet.")
            after = deepcopy(state)
            after["stage"] = "orientation_offered"
            return _commit(base, state, after, action=action, action_id=action_id, surface=surface, now=ts)
        if action == "pause":
            if state["stage"] not in {"dividend_ready", "orientation_offered"}:
                raise JourneyError("pause_unavailable", "This journey is not currently running.")
            after = deepcopy(state)
            after["stage"] = "paused"
            return _commit(base, state, after, action=action, action_id=action_id, surface=surface, now=ts)
        if action == "revoke":
            if not state.get("source"):
                raise JourneyError("nothing_to_revoke", "No folder access has been granted.")
            after = deepcopy(state)
            after["stage"] = "revoked"
            after["access"] = "revoked"
            after["source"]["status"] = "revoked"
            return _commit(base, state, after, action=action, action_id=action_id, surface=surface, now=ts)
        if action == "undo":
            events = _read_events(base)
            undone = {str(e.get("undo_of")) for e in events if e.get("undo_of")}
            target = next(
                (e for e in reversed(events) if e.get("reversible") and e.get("event_id") not in undone and isinstance(e.get("before"), dict)),
                None,
            )
            if not target:
                raise JourneyError("nothing_to_undo", "There is no reversible onboarding choice to undo.")
            after = deepcopy(target["before"])
            return _commit(
                base, state, after, action=action, action_id=action_id, surface=surface,
                now=ts, reversible=False, undo_of=str(target["event_id"]),
                manifest=target.get("before_manifest"),
            )
        raise JourneyError("action_unknown", f"Unknown onboarding action: {action}.")


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="framework.onboarding.journey")
    parser.add_argument("command", choices=["snapshot", "act"])
    parser.add_argument("--request", help="JSON action object; omit to read stdin")
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            result = snapshot()
        else:
            raw = args.request if args.request is not None else sys.stdin.read()
            try:
                request = json.loads(raw)
            except ValueError as exc:
                raise JourneyError("request_json", "The onboarding action was not valid JSON.") from exc
            result = act(request)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except JourneyError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "error": str(exc)}, ensure_ascii=False))
        return 3


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
