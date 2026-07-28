"""Canonical Cabinet Onboarding v2 journey.

This module is the one state/event/card core consumed by Dashboard, Telegram,
and Cabinet World.  Surfaces may render and submit actions; they do not own an
onboarding state machine.

The first production slice is deliberately narrow and useful:

1. capture a purpose and relationship *destination* (never an authority grant),
2. propose a read-only First Window over one local folder,
3. bind the exact scope, limits AND ownership class into an Orientation Charter,
4. read only after the Captain ratifies that Charter hash,
5. return one honest, source-cited First Dividend.

Entry into that slice is CLASSIFIED, not assumed (Captain ruling 2026-07-26):
``entry_plan`` returns the opening move for whatever the operator has actually
granted — sweep-and-assert with connectors, the human-shaped seed question plus
discovery probes with only local/web reach, or the residual questions and a
plain statement of what cannot be known with nothing at all — and it always
returns a next step. See the ENTRY MODES section below for why that invariant
is the point.

OWNERSHIP IS A PRECONDITION, not a field.  ``propose_window`` refuses a source
whose ownership class and authority basis the operator has not declared — see
``framework.authority.ownership``, which also states plainly what the framework
cannot enforce (the truth of the attestation).  Sources classified ``employer``
or ``third_party`` are structurally observe-only and default to no-egress, and
the record of each completed read SURVIVES a purge.

All state stays below ``instance/onboarding/v2`` — a surface the mission
compiler never reads.  Events are append-only, state/artifacts are atomic,
actions are idempotent, and a process lock serializes cross-surface races.
``purge`` is the sole destructive lifecycle operation: it requires the literal
confirmation ``PURGE`` and writes a content-free intent receipt before removing
state, event history, manifests, and derived excerpts. An interrupted purge is
completed on the next locked read rather than silently reopening onboarding.
A broken or already-tombstoned evidence plane never blocks that deletion: the
typed purge proceeds and the evidence failure is recorded inside the purge
receipt (the pending marker stays so recovery or a Captain force purge can
finish the evidence side).  Conversely, when retention or a Captain CLI purge
tombstones the LIVE evidence trial, the journey re-mints a fresh trial (its
genesis event links the tombstone hash) so onboarding keeps recording instead
of wedging — purge finality still holds for a purged journey.

No network, subprocess, connector, write into a granted source, or LLM call is
possible in this module.  The dividend detectors are deterministic so their
claims can be tested and cited rather than performed.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
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

from framework.authority.ownership import (
    ATTESTATION_LIMIT,
    SENSITIVE_NAME_RE,
    SENSITIVE_SUFFIXES,
    SENSITIVITY_CLASSES,
    OwnershipRefusal,
    access_record,
    egress_disposition,
    open_ingest,
    sensitivity_refusal,
    source_permissions,
)
from framework.evidence import (
    ActLifecycle,
    EvidenceError,
    EvidenceRecorder,
    remint_trial,
    valid_id_or_none,
)

SCHEMA = "cabinet.onboarding-journey/v2"
ACCESS_RECORD_SCHEMA = "cabinet.source-access-record/v1"
CARD_SCHEMA = "cabinet.onboarding-card/v1"
CHARTER_SCHEMA = "cabinet.orientation-charter/v1"
MANIFEST_SCHEMA = "cabinet.first-window-manifest/v1"
DIVIDEND_SCHEMA = "cabinet.first-dividend/v1"
EVENT_SCHEMA = "cabinet.onboarding-event/v1"

DATA_REL = "instance/onboarding/v2"
LOCK_REL = "instance/onboarding/.onboarding-v2.lock"
PURGE_RECEIPTS_REL = "instance/onboarding/purge-receipts"
# The per-source access record SURVIVES the read it describes, so it lives
# OUTSIDE the purged data directory (the purge-receipts precedent). Content-free
# by construction: roots, hashes, counts and refusal classes — never excerpts —
# so keeping the record after a purge does not keep the data.
ACCESS_RECORDS_REL = "instance/onboarding/access-records"
EVIDENCE_REL = "instance/evidence/v1"
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
#: What a citation from a non-owned source renders as until it is approved.
WITHHELD_EXCERPT = "[withheld: not the operator's content to send]"
#: Plain-language rendering of the ownership class on the approval card. The
#: operator approves what they can read, so the class they attested is shown
#: back to them in words before the Charter hash is theirs to accept.
OWNERSHIP_LABELS = {
    "self": "mine",
    "employer": "my employer's",
    "third_party": "someone else's",
}

# ── Three entry modes — "never a dead end" (Captain ruling, 2026-07-26) ───────
# The welcome card used to offer exactly one move: choose a folder. An operator
# with no folder to grant had no path at all, and the deep-orientation card was
# terminal (pause/revoke/purge only). Both are dead ends, and a dead end is the
# one outcome onboarding may never produce. So entry is CLASSIFIED from what the
# operator has actually granted, and each class has its own opening move:
#   connected  — sources are connected: sweep them, derive, and ASSERT with a
#                citation the operator can correct. Never ask what the data
#                answers.
#   seeded     — nothing connected but local files and/or the web are reachable:
#                ask the HUMAN-shaped question ("what do you do", "how can I
#                best serve you") and treat the answer as a SEED for discovery,
#                not as the data. A few words become search and sweep work.
#   ungranted  — nothing at all: the residual questions, plus a plain statement
#                of what this cabinet cannot know without access.
ENTRY_PLAN_SCHEMA = "cabinet.onboarding-entry-plan/v1"
ENTRY_MODE_CONNECTED = "connected"
ENTRY_MODE_SEEDED = "seeded"
ENTRY_MODE_UNGRANTED = "ungranted"
ENTRY_MODES = (ENTRY_MODE_CONNECTED, ENTRY_MODE_SEEDED, ENTRY_MODE_UNGRANTED)
GRANT_KEYS = ("connectors", "local_files", "web")

# The human-shaped question. Deliberately NOT the org-shaped one: the residual
# set below never asks what the company is, because at any altitude below
# founder that answer is either obvious to the asker or not the operator's to
# give — and because it teaches the operator that this is an interview.
SEED_QUESTION = "What do you do, and how can I best serve you?"

# The residual questionnaire — four questions, and none of them "what is your
# company". Both blind arms of the 2026-07-26 direction gate produced "which of
# these are yours to grant?" independently: it is UN-DERIVABLE BY CONSTRUCTION,
# because the answer is not in the data at any level of access. Everything else
# a sweep can reach is asserted with a citation and corrected, never asked.
RESIDUAL_QUESTIONS = (
    {
        "id": "rights",
        "prompt": "Which of these sources are yours to give me read access to?",
        "why": "No amount of access answers this. Permission is not written in the data.",
        "required": True,
    },
    {
        "id": "salience",
        "prompt": "Of everything I showed you, what actually matters to you this week?",
        "why": "I can rank by structure. I cannot see which of it you care about right now.",
        "required": True,
    },
    {
        "id": "limits",
        "prompt": "What must I never touch?",
        "why": "A limit that is never stated is a limit I will find by crossing it.",
        "required": True,
    },
    {
        "id": "purpose",
        "prompt": "A month from now, what should be true that is not true today?",
        "why": "Purpose is a choice, not a fact — it is the one thing no sweep can read.",
        "required": False,
    },
)

# What a read-only sweep may honestly DERIVE, versus what it must ASK — the
# 2026-07-26 adjudication, verbatim in effect. "partial" is the dangerous
# middle: the half that is derivable is genuinely derivable, and the half that
# is not is where fabrication happens, so both halves are stated.
DERIVABLE = "derivable"
PARTIALLY_DERIVABLE = "partial"
NOT_DERIVABLE = "not_derivable"
NEVER_DERIVABLE = "never"
DERIVABILITY = {
    "products": {
        "verdict": DERIVABLE,
        "note": "Given a read adapter, what is built is in the sources.",
    },
    "projects": {
        "verdict": DERIVABLE,
        "note": "Given a read adapter, in-flight work is in the sources.",
    },
    "tasks": {
        "verdict": DERIVABLE,
        "note": "Given a read adapter, open items are in the sources.",
    },
    "teams": {
        "verdict": PARTIALLY_DERIVABLE,
        "note": "Who works alongside whom is derivable as a collaboration graph.",
        "cannot": (
            "Roles, seniority and who decides are not in the data. If I stated "
            "them I would be inventing them."
        ),
    },
    "company": {
        "verdict": PARTIALLY_DERIVABLE,
        "note": "What is built, and in what stack, is derivable.",
        "cannot": "A code repository cannot tell me how the business makes money.",
    },
    "customers": {
        "verdict": NOT_DERIVABLE,
        "cannot": (
            "Nothing I can read names your customers — no mail, chat, calendar, "
            "support or billing source is connected."
        ),
    },
    "grant_rights": {
        "verdict": NEVER_DERIVABLE,
        "cannot": (
            "Which sources are yours to grant is not written anywhere I can "
            "read, at any level of access. It is the one thing I must ask."
        ),
    },
}

MAX_FILES = 200
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 128 * 1024
# Bound the total directory entries EXAMINED (not just accepted) during a scan
# so a folder with a few eligible files buried in a huge tree of skipped ones
# cannot hold the exclusive onboarding lock indefinitely and starve every
# surface's snapshot/act. 50k entries is far above any real First Window.
MAX_SCAN_ENTRIES = 50_000
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
# SENSITIVE_NAME_RE / SENSITIVE_SUFFIXES now live in
# framework.authority.ownership beside the five sensitivity classes they used
# to be the only member of, and are re-exported here byte-identically so the
# scanner's historical credential behaviour is unchanged.
SECRET_LINE_RES = (
    re.compile(r"(?i)\b(api[_ -]?key|secret|token|password|authorization|credential|private\s+key)\b"),
    re.compile(r"\b[0-9]{8,12}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
# A long run of key/token-shaped characters, entropy-tested in _redact_excerpt.
_LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_-]{32,}")
# ONE request-id shape for both planes (leading alphanumeric, then up to 127
# id chars) — identical to the Evidence Recorder's ID_RE.  The canonical
# onboarding event and the evidence trail must never accept different id
# alphabets, or a caller id valid in one plane forks the cross-plane
# correlation that makes the audit trail reviewable.
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
# Unpaired UTF-16 surrogates cannot be UTF-8 encoded: they would crash the
# charter hash and every JSON persistence write as a raw UnicodeEncodeError.
_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def _scrub_lone_surrogates(text: str) -> str:
    """Replace unpaired surrogates with U+FFFD so the event still records.

    Scrubbing happens BEFORE hashing and BEFORE persistence, so the stored
    bytes always equal the hashed bytes and a malformed caller string can
    never crash an action out of the audit trail.
    """
    return _SURROGATE_RE.sub("�", text)


class JourneyError(RuntimeError):
    """A user-correctable, code-bearing onboarding refusal."""

    def __init__(self, code: str, message: str, *, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


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
        "evidence_trial_id": f"onboarding-{uuid.uuid4().hex}",
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


def _as_revision(value: Any) -> int:
    """Coerce a persisted revision to int; an unreadable value sorts as -1 so it
    can never win the replay comparison (and never crashes it)."""
    if isinstance(value, bool):
        return -1
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


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
    if not isinstance(value.get("evidence_trial_id"), str):
        # Additive v2 migration for deployments created before Evidence
        # Recorder v1. No source data is copied into the evidence plane.
        value["evidence_trial_id"] = f"onboarding-{uuid.uuid4().hex}"
        if create:
            _atomic_json(path, value)
    # Crash recovery: the event is fsync'd before the projection is replaced.
    # If power is lost between those steps, replay the newest committed `after`
    # projection and its non-raw manifest instead of repeating the action.
    # Revisions are coerced defensively so a single semi-valid persisted row
    # yields a clean refusal below rather than a raw ValueError from every call.
    latest = next(
        (
            row for row in reversed(_read_events(root))
            if isinstance(row.get("after"), dict)
            and _as_revision(row["after"].get("revision")) > _as_revision(value.get("revision"))
        ),
        None,
    )
    if latest:
        value = deepcopy(latest["after"])
        if create:
            _atomic_json(path, value)
            _sync_artifacts(root, value, manifest=latest.get("manifest"))
    revision = value.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int):
        raise JourneyError("state_schema", "Onboarding state has an unreadable revision; no action was taken.")
    if not isinstance(value.get("evidence_trial_id"), str):
        value["evidence_trial_id"] = f"onboarding-{uuid.uuid4().hex}"
        if create:
            _atomic_json(path, value)
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


# The fields _finish_purge dereferences on a receipt; a started receipt missing
# any of them cannot be safely completed (see _recover_pending_purge).
_PURGE_RECEIPT_KEYS = ("purged_at", "action_id", "surface", "purged_journey_id_hash")


def _finish_purge(
    root: Path,
    receipt_path: Path,
    receipt: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Idempotently complete a content-free purge intent."""
    data = _data_dir(root)
    _annotate_access_records(root, receipt)
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
        "trace_id": str(receipt.get("trace_id") or ""),
        "correlation_id": str(receipt.get("correlation_id") or ""),
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
            "No source path or content is retained here. The content-free access "
            "record of each completed read survives and now carries this receipt."
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
        if not isinstance(receipt, dict):
            continue
        if receipt.get("status") == "started":
            # A malformed intent receipt (missing the fields _finish_purge needs)
            # must not KeyError out of every snapshot()/act() that runs recovery.
            # Leave it in place; a fresh purge from current state still works.
            if not all(isinstance(receipt.get(key), str) for key in _PURGE_RECEIPT_KEYS):
                continue
            _, receipt = _finish_purge(root, path, receipt)
        pending_trial = receipt.get("pending_evidence_trial_id")
        if isinstance(pending_trial, str):
            recorder = EvidenceRecorder(root / EVIDENCE_REL)
            trial_path = recorder.root / "trials" / pending_trial
            if trial_path.is_dir():
                try:
                    recorder.purge_trial(
                        pending_trial,
                        confirmation=f"PURGE {pending_trial}",
                        actor="captain",
                    )
                except EvidenceError:
                    # The pending evidence trial cannot be purged right now
                    # (for example an integrity-failed ledger awaiting a
                    # Captain force purge). Keep the pending marker so this
                    # recovery retries on the next locked read — a broken
                    # evidence plane must never wedge snapshot()/act() or
                    # make onboarding-derived data undeletable.
                    continue
            completed = {key: value for key, value in receipt.items() if key != "pending_evidence_trial_id"}
            completed["purged_evidence_trial_id_hash"] = hashlib.sha256(
                pending_trial.encode("utf-8")
            ).hexdigest()
            _atomic_json(path, completed)


def _complete_onboarding_evidence_purge(
    root: Path,
    *,
    action_id: str,
    trial_id: str,
) -> dict[str, Any] | None:
    """Scrub the transient clear trial id from the durable purge receipt."""
    receipts = root / PURGE_RECEIPTS_REL
    for path in sorted(receipts.glob("purge-*.json")):
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(receipt, dict) or receipt.get("action_id") != action_id:
            continue
        completed = {key: value for key, value in receipt.items() if key != "pending_evidence_trial_id"}
        completed["purged_evidence_trial_id_hash"] = hashlib.sha256(
            trial_id.encode("utf-8")
        ).hexdigest()
        _atomic_json(path, completed)
        return completed
    return None


def _annotate_purge_receipt(
    root: Path,
    action_id: str,
    extra: dict[str, Any],
) -> dict[str, Any] | None:
    """Record an evidence-plane failure inside the onboarding purge receipt.

    ``pending_evidence_trial_id`` is deliberately preserved so the next locked
    read (or a Captain force purge) can still finish the evidence-side
    deletion; the annotation only documents why it is still pending.
    """
    receipts = root / PURGE_RECEIPTS_REL
    for path in sorted(receipts.glob("purge-*.json")):
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(receipt, dict) or receipt.get("action_id") != action_id:
            continue
        annotated = {**receipt, **extra}
        _atomic_json(path, annotated)
        return annotated
    return None


def _event_for_action(root: Path, action_id: str | None) -> dict[str, Any] | None:
    if not action_id:
        return None
    for row in reversed(_read_events(root)):
        if row.get("action_id") == action_id:
            return row
    return None


_SEED_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#._/-]{1,39}")
# Ordinary English scaffolding a seed sentence is made of. Removing it is what
# turns "I run payments integrations for a bank" into terms worth searching.
_SEED_STOPWORDS = frozenset({
    "a", "about", "all", "am", "an", "and", "any", "are", "as", "at", "be",
    "been", "but", "by", "can", "day", "do", "does", "doing", "for", "from",
    "get", "have", "help", "here", "how", "i", "if", "in", "is", "it", "its",
    "just", "kind", "lot", "make", "me", "mostly", "much", "my", "of", "on",
    "one", "or", "our", "out", "over", "really", "run", "so", "some", "still",
    "that", "the", "their", "them", "then", "there", "these", "they", "thing",
    "things", "this", "to", "up", "us", "very", "want", "was", "we", "well",
    "what", "when", "where", "which", "who", "will", "with", "work", "working",
    "would", "you", "your",
})
MAX_SEED_TERMS = 8
MAX_SEED_PROBES = 6


def _normalized_grants(raw: Any) -> dict[str, Any]:
    """The three access facts entry classification turns on, fail-closed.

    Anything absent, malformed or merely truthy-looking is NOT a grant: only a
    literal ``True`` grants local/web, and only non-empty names grant
    connectors. The default is therefore ``ungranted``, which is also the honest
    state of a cabinet nobody has handed anything yet.
    """
    src = raw if isinstance(raw, dict) else {}
    connectors = src.get("connectors")
    if isinstance(connectors, str):
        connectors = [connectors]
    if isinstance(connectors, (list, tuple, set, frozenset)):
        names = sorted({str(c).strip() for c in connectors if str(c).strip()})
    else:
        names = []
    return {
        "connectors": names,
        "local_files": src.get("local_files") is True,
        "web": src.get("web") is True,
    }


def entry_mode(grants: Any) -> str:
    """Classify the entry into one of the three modes. Total by construction."""
    normalized = _normalized_grants(grants)
    if normalized["connectors"]:
        return ENTRY_MODE_CONNECTED
    if normalized["local_files"] or normalized["web"]:
        return ENTRY_MODE_SEEDED
    return ENTRY_MODE_UNGRANTED


def _seed_terms(seed: Any) -> list[str]:
    """Salient terms from a few words of free text — deterministic, no model.

    First occurrence wins so the operator's own ordering survives, which is the
    closest thing to salience available without asking a second question.
    """
    if not isinstance(seed, str) or not seed.strip():
        return []
    terms: list[str] = []
    for match in _SEED_TOKEN_RE.finditer(seed):
        token = match.group(0).strip("._/-")
        if len(token) < 2 or token.lower() in _SEED_STOPWORDS:
            continue
        if not any(token.lower() == existing.lower() for existing in terms):
            terms.append(token)
        if len(terms) >= MAX_SEED_TERMS:
            break
    return terms


def seed_probes(seed: Any, grants: Any) -> dict[str, Any]:
    """A few words → the discovery work they justify. PROPOSALS, never runs.

    This module makes no network call and opens no file outside a ratified
    Charter, so what comes back is the PLAN — typed probes for whichever plane
    holds egress or a ratified First Window to execute. A probe is emitted only
    for a grant that exists: no web grant, no web probe. That is what stops the
    seed question from becoming an interview whose answers go nowhere.
    """
    normalized = _normalized_grants(grants)
    terms = _seed_terms(seed)
    probes: list[dict[str, str]] = []
    if terms:
        joined = " ".join(terms[:4])
        if normalized["web"]:
            for query in (joined, f"{joined} how it works", f"{joined} common problems"):
                probes.append({"kind": "web_search", "query": query})
        if normalized["local_files"]:
            for term in terms[:3]:
                probes.append({"kind": "local_name_match", "pattern": f"*{term}*"})
            probes.append({"kind": "local_name_match", "pattern": "README*"})
    return {
        "terms": terms,
        "probes": probes[:MAX_SEED_PROBES],
        "executable": bool(probes),
    }


def _cannot_know(mode: str) -> list[dict[str, str]]:
    """What this cabinet cannot know, said plainly, for the given mode.

    ``grant_rights`` is in EVERY mode: it is un-derivable by construction, so
    connecting more sources never removes it. The rest appear only while the
    access that would derive them is missing — claiming permanent blindness a
    connector would fix is its own dishonesty.
    """
    subjects = ["grant_rights"]
    if mode != ENTRY_MODE_CONNECTED:
        subjects += ["products", "projects", "tasks", "teams", "company", "customers"]
    else:
        subjects += ["teams", "company", "customers"]
    out: list[dict[str, str]] = []
    for subject in subjects:
        row = DERIVABILITY[subject]
        statement = row.get("cannot")
        if not statement:
            statement = (
                f"Without a source I can read, {subject.replace('_', ' ')} are "
                "not something I can know."
            )
        out.append({"subject": subject, "verdict": row["verdict"], "statement": statement})
    return out


def entry_plan(grants: Any = None, *, seed: Any = None) -> dict[str, Any]:
    """The opening move for whatever the operator has actually granted.

    THE INVARIANT THIS EXISTS FOR: ``next_actions`` is never empty, in any of
    the eight grant combinations. Onboarding may return "I cannot know that";
    it may not return "there is nothing you can do here". ``propose_window`` is
    the floor — a folder is the one grant an operator can always make — and
    every mode carries the residual questions plus the honest cannot-know list
    on top of its own opening move.
    """
    normalized = _normalized_grants(grants)
    mode = entry_mode(normalized)
    discovery = seed_probes(seed, normalized)
    if mode == ENTRY_MODE_CONNECTED:
        opening_move = "sweep_and_assert"
        asks: tuple[dict[str, Any], ...] = tuple(
            q for q in RESIDUAL_QUESTIONS if q["id"] != "salience"
        )
        question = None
    elif mode == ENTRY_MODE_SEEDED:
        opening_move = "seed_then_discover"
        asks = tuple(q for q in RESIDUAL_QUESTIONS if q["id"] in {"rights", "limits"})
        question = SEED_QUESTION
    else:
        opening_move = "residual_questions"
        asks = RESIDUAL_QUESTIONS
        question = SEED_QUESTION
    next_actions = [{"action": "propose_window", "label": "Choose a folder I may read"}]
    payload = {
        "schema": ENTRY_PLAN_SCHEMA,
        "mode": mode,
        "opening_move": opening_move,
        "grants": normalized,
        "seed_question": question,
        "questions": [deepcopy(q) for q in asks],
        "discovery": discovery,
        "cannot_know": _cannot_know(mode),
        "next_actions": next_actions,
    }
    if not payload["next_actions"]:  # pragma: no cover — structurally unreachable
        raise JourneyError("entry_dead_end", "Onboarding produced no next step.")
    return payload


def _entry_grants(state: dict[str, Any]) -> dict[str, Any]:
    """The grants THIS journey can prove, read from its own state.

    Exactly one is provable here today, and it is provable exactly: a source
    whose status is ``ratified_read_only`` is a local-file grant the Captain
    made and has not revoked. Connectors and web come from an explicit
    ``entry_grants`` block when a surface supplies one, and are otherwise NOT
    granted — the fail-closed direction, because over-claiming a grant is how a
    cabinet reads something nobody gave it.
    """
    source = state.get("source")
    ratified = isinstance(source, dict) and source.get("status") == "ratified_read_only"
    supplied = state.get("entry_grants")
    supplied = supplied if isinstance(supplied, dict) else {}
    return _normalized_grants({
        "connectors": supplied.get("connectors"),
        "local_files": True if ratified else supplied.get("local_files"),
        "web": supplied.get("web"),
    })


def _entry_body(plan: dict[str, Any]) -> str:
    """The mode's opening move in the operator's words, plus what it cannot know.

    The cannot-know line is not decoration: a cabinet that quietly omits the
    limits of its own sight is the same failure as a sweep claiming a negative
    it never earned, one surface up.
    """
    mode = plan["mode"]
    if mode == ENTRY_MODE_CONNECTED:
        opening = (
            "You have connected sources, so I will read them first and tell you "
            "what I found with a citation you can correct. I will not ask you "
            "for anything they already answer."
        )
    elif mode == ENTRY_MODE_SEEDED:
        opening = (
            f"Nothing is connected yet, but I can look. {plan['seed_question']} "
            "A sentence is enough — I will take it as a starting point and go "
            "find out the rest, not as the answer."
        )
    else:
        opening = (
            "Nothing is connected and I cannot look anywhere yet, so I will not "
            f"pretend to know your work. {plan['seed_question']} "
            "Then give me one folder to read, and I will stop asking."
        )
    limits = " ".join(row["statement"] for row in plan["cannot_know"][:2])
    return f"{opening} What I cannot know without access: {limits}"


def _egress_for_card(state: dict[str, Any], finding: dict[str, Any]) -> dict[str, Any]:
    """Screen the First Dividend's outbound content by the source's ownership class.

    The card is the ONE object every channel renders, so it is where the egress
    gate has to bite: a citation's ``text`` is a verbatim line from the source,
    and rendering it into Telegram ships that line to a third-party messenger.

    GRADED, because a flat refusal here would be safety theatre. ``self`` and
    ``employer`` content leaves (an employee reading their own view of their
    employer's repo is the product at that altitude); the disposition is
    recorded either way. ``third_party`` content — a client's, a customer's —
    is WITHHELD, per item, until approved: paths, line numbers and counts still
    render, so the operator can see exactly what exists and what it would take
    to release it, but the borrowed words do not travel.
    """
    source = state.get("source") or {}
    ownership = str(source.get("ownership") or "")
    try:
        disposition = egress_disposition(ownership)
    except OwnershipRefusal:
        # A journey persisted before the ownership ceiling existed carries no
        # class. Unclassified is the STRICTEST case, never the loosest.
        ownership, disposition = "unclassified", "per_item_approval"
    approved = {str(i) for i in (state.get("egress_approved") or [])}
    citations = [dict(c) for c in finding.get("citations") or []]
    items = [
        {"id": f"{c.get('path')}:{c.get('line')}", "ownership": ownership}
        for c in citations
    ]
    withheld = 0
    if disposition == "per_item_approval":
        for citation, item in zip(citations, items):
            if item["id"] in approved:
                continue
            citation["excerpt"] = WITHHELD_EXCERPT
            citation["withheld_reason"] = "egress_refused_without_per_item_approval"
            withheld += 1
    summary = str(finding.get("summary") or "")
    if withheld:
        summary = (
            f"I found something in {len(citations)} cited place(s), and I am not "
            "sending the words themselves: this source is someone else's. Approve "
            "the citation you want released, or reclassify the source."
        )
    return {
        "summary": summary,
        "citations": citations,
        "disposition_block": {
            "ownership": ownership,
            "disposition": disposition,
            "items": len(citations),
            "withheld": withheld,
            "approved": sorted(approved),
        },
    }


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
    if stage == "welcome":
        plan = entry_plan(_entry_grants(state))
        common.update(
            kind="first_window",
            title="Let me earn my first responsibility",
            body=(
                _entry_body(plan)
                + " Whatever you approve, I show you exactly what I would read first; "
                "nothing is opened until you approve that Charter."
            ),
            entry=plan,
            options=list(plan["next_actions"]),
        )
    elif stage == "purged":
        common.update(
            kind="purged",
            title="Onboarding data was deleted",
            body=(
                "The Charter, onboarding history, bounded manifest, derived excerpts, "
                "and live evidence trial were removed. Stale actions cannot reopen them."
            ),
            status="complete",
            options=[],
        )
    elif stage == "charter_pending":
        charter = state["charter"]
        source = state["source"]
        common.update(
            kind="orientation_charter",
            title="Your First Window is ready for approval",
            body=(
                f"Read-only access to “{source['label']}” for this purpose: {state['purpose']}. "
                f"You told me this source is {OWNERSHIP_LABELS.get(str(source.get('ownership')), 'unclassified')} "
                f"({source.get('authority_basis')}). "
                f"I will inspect at most {MAX_FILES} supported text files ({MAX_TOTAL_BYTES // 1024 // 1024} MB total), "
                "skip secrets, personnel, pay, customer-personal, legal and corporate-finance files by name, "
                "skip hidden/system folders, binaries, and every symlink, and make no changes. "
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
        egress = _egress_for_card(state, finding)
        common["egress"] = egress["disposition_block"]
        coverage = dividend.get("coverage") or {}
        # A strong finding still rode an incomplete window, and the operator
        # cannot judge "is this the most important thing in there?" without
        # knowing how much of "in there" was opened.
        disclosure = ""
        if finding["quality"] == "strong" and coverage and not coverage.get("complete"):
            disclosure = (
                f" I read {coverage.get('examined_files', 0)} of "
                f"{coverage.get('eligible_files', 0)} supported files, most-informative "
                "first; the rest were left unopened by the First Window limits."
            )
        common.update(
            kind="first_dividend",
            title="I found something worth your attention" if finding["quality"] == "strong" else "Your first map is ready",
            body=egress["summary"] + disclosure,
            evidence=egress["citations"],
            options=[
                {"action": "continue", "label": "See the locked next step"},
                {"action": "pause", "label": "Pause here"},
                {"action": "revoke", "label": "Revoke folder access"},
                {"action": "purge", "label": "Delete onboarding data", "danger": True},
            ],
        )
    elif stage == "orientation_offered":
        plan = entry_plan(_entry_grants(state))
        common.update(
            kind="deep_orientation",
            title="Deeper Orientation has not started",
            body=(
                "A later, separately approved step could spend longer learning how your work fits together, "
                "reflect back priorities and conflicts, suggest a useful AI team, and show concrete examples "
                "of what each officer may observe, propose, or do. That work is disabled and has not started. "
                "No new access or authority was granted. What I can do now instead: "
                + _entry_body(plan)
            ),
            entry=plan,
            # ``propose_window`` is what stops this card being terminal. It was
            # pause/revoke/purge only — three ways to stop and none to continue —
            # so an operator who wanted to give MORE had to abandon onboarding.
            options=list(plan["next_actions"]) + [
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
            body="The Cabinet will not read this source again without a new First Window you approve. Derived onboarding artifacts remain until you undo or purge them.",
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
    try:
        # The Charter and state record str(resolved); a path holding
        # surrogate-escaped (non-UTF-8) bytes cannot be hashed or persisted,
        # and scrubbing it would silently point the Charter at a different
        # name. Refuse cleanly so the attempt is still a recorded refusal.
        str(resolved).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise JourneyError(
            "source_unencodable",
            "That folder's name cannot be recorded faithfully; rename it or choose another folder.",
        ) from exc
    if candidate.is_symlink():
        raise JourneyError("source_symlink", "Choose the real folder, not a shortcut or symlink.")
    home = Path.home().resolve()
    if resolved == Path(resolved.anchor) or resolved == home:
        raise JourneyError("source_too_broad", "Choose a specific folder, not the whole disk or home folder.")
    return resolved


def _validate_purpose(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise JourneyError("purpose_required", "Tell me what you want this First Window to make easier.")
    # Scrub unpaired surrogates at the request boundary: the Captain's intent
    # is recorded (with U+FFFD markers) instead of crashing the charter hash
    # and state write with a raw UnicodeEncodeError.
    purpose = " ".join(_scrub_lone_surrogates(raw).strip().split())
    if len(purpose) > 300:
        raise JourneyError("purpose_too_long", "Keep the first purpose under 300 characters.")
    return purpose


def _build_charter(
    source: Path, purpose: str, destination: str, ingest: dict[str, Any]
) -> dict[str, Any]:
    """Bind scope, limits AND ownership into the hash the Captain approves.

    ``ingest`` is the ingest ceiling's return (framework.authority.ownership.
    open_ingest): the declared class, the recorded authority basis, the
    permission block DERIVED from that class, and the attestation with its
    honest limit. Ownership rides inside the hashed payload, so a charter
    approved for the operator's own folder cannot be replayed against an
    employer's without the fingerprint changing.
    """
    permission = dict(source_permissions(ingest["ownership"]))
    permission.update(network=False, connectors=False, follow_symlinks=False)
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
            "ownership": ingest["ownership"],
            "authority_basis": ingest["authority_basis"],
        },
        "attestation": ingest["attestation"],
        "permission": permission,
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
            "sensitivity_classes": list(SENSITIVITY_CLASSES),
        },
        "retention": {
            "raw_file_contents": "not persisted",
            "derived_excerpts": "only cited, secret-redacted lines",
            "purge": "Captain may delete state, events, manifests, and derived excerpts",
            "access_record": (
                "a content-free per-source record (root, ownership class, "
                "authority basis, charter and manifest hashes, entry count, "
                "every refusal with its class) SURVIVES the purge and is "
                "annotated with the purge receipt"
            ),
        },
        "attestation_limit": ATTESTATION_LIMIT,
    }
    return {"payload": payload, "hash": _hash(payload), "status": "pending"}


def _is_hidden_rel(rel: Path) -> bool:
    return any(part.startswith(".") for part in rel.parts)


def _sensitivity_class(rel: Path) -> str | None:
    """The sensitivity class this path refuses under, or None.

    Delegates to the one vocabulary in framework.authority.ownership. The
    credential arm is byte-identical to the detector this scanner always
    carried; the five classes beside it — personnel, compensation, customer
    PII, live legal matters, corporate finance — are new, and each refuses
    under its OWN name so the manifest can say what it left behind.
    """
    return sensitivity_refusal(rel.as_posix())


def _is_sensitive(rel: Path) -> bool:
    return _sensitivity_class(rel) is not None


def _allowed_file(path: Path) -> bool:
    return path.suffix.lower() in ALLOWED_SUFFIXES or path.name.lower() in ALLOWED_BASENAMES


# ── Relevance ranking for the bounded read ───────────────────────────────────
# Walk order is not relevance. Measured 2026-07-26 on an employee-scale slice
# (docs/persona-employee-slice-2026-07-26.md §5): the alphabetical cap admitted
# 200 of 2103 eligible files, ALL from one top-level directory, leaving the repo
# and the tracker with zero coverage — "a cap resolved alphabetically is not a
# budget, it is a coin flip". Bucket 0 is the sharpest case: ``_command_drift``
# returns nothing AT ALL when no package.json is in the window, so a manifest
# file that never fits is not a weaker result, it is a silently disabled
# detector. Ranking is over path and name only — nothing is read to decide what
# to read, so the ordering cannot be steered by file CONTENT.
_RANK_MANIFEST_NAMES = frozenset({
    "package.json", "pyproject.toml", "cargo.toml", "go.mod", "pom.xml",
    "build.gradle", "composer.json", "gemfile", "makefile", "justfile",
    "taskfile.yml", "taskfile.yaml", "docker-compose.yml", "docker-compose.yaml",
    "requirements.txt", "setup.cfg", "procfile",
})
_RANK_ENTRY_STEMS = (
    "readme", "contributing", "changelog", "todo", "roadmap", "claude",
    "agents", "onboarding", "index", "overview",
)
_RANK_SIGNAL_TOKENS = (
    "runbook", "deploy", "release", "oncall", "on-call", "incident",
    "postmortem", "post-mortem", "migrat", "install", "setup",
    "getting-started", "decision", "adr", "rfc", "spec", "plan", "todo",
)
_PROSE_SUFFIXES = frozenset({".md", ".mdx", ".rst", ".txt"})
_CONFIG_SUFFIXES = frozenset({".json", ".yml", ".yaml", ".toml", ".csv", ".tsv"})


def _relevance_key(rel: Path) -> tuple[int, int, int, str]:
    """Rank one eligible path. Total, deterministic, content-blind.

    Ties break on depth then path, so the order is stable across filesystems
    and two runs over one tree produce byte-identical manifests.
    """
    name = rel.name.lower()
    stem = name.rsplit(".", 1)[0] if "." in name else name
    suffix = rel.suffix.lower()
    posix = rel.as_posix().lower()
    if name in _RANK_MANIFEST_NAMES:
        bucket = 0
    elif any(stem.startswith(entry) for entry in _RANK_ENTRY_STEMS):
        bucket = 1
    elif suffix in _PROSE_SUFFIXES:
        bucket = 2
    elif suffix in _CONFIG_SUFFIXES:
        bucket = 3
    else:
        bucket = 4
    signal = 0 if any(token in posix for token in _RANK_SIGNAL_TOKENS) else 1
    return (bucket, signal, len(rel.parts), rel.as_posix())


def _shannon_entropy(token: str) -> float:
    counts: dict[str, int] = {}
    for ch in token:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(token)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _redact_excerpt(text: str) -> str:
    clean = " ".join(text.strip().split())[:300]
    if any(rx.search(clean) for rx in SECRET_LINE_RES):
        return "[sensitive value redacted]"
    # Catch an unlabeled, high-entropy secret (API key/token) sitting on a cited
    # line even when no secret keyword or assignment shape flags it: a long,
    # mixed-class, high-entropy run redacts rather than leaking verbatim into the
    # first-dividend card. Long prose/paths stay (low entropy or no digits).
    for token in _LONG_TOKEN_RE.findall(clean):
        if any(c.isdigit() for c in token) and any(c.isalpha() for c in token) and _shannon_entropy(token) >= 3.5:
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
    """Read a bounded, RELEVANCE-ORDERED slice of one folder, and count the rest.

    Two passes, and the split is the whole point. Pass one stats the tree and
    counts EVERY eligible file, including the ones the budget will not reach —
    the old single pass stopped counting candidates the moment the cap tripped,
    so a 2103-file estate reported ``candidate_files == included_files == 200``
    with zero exclusions, a statistic that reads as complete coverage of a
    200-file folder. Pass two reads the eligible set in relevance order until
    the budget is spent, and what it could not reach is reported as
    ``unexamined`` rather than disappearing.
    """
    total = 0
    truncated = False
    visited = 0  # every directory entry EXAMINED, so a huge tree of skipped files still terminates
    excluded: dict[str, int] = {
        "hidden": 0,
        "sensitive_name": 0,
        "symlink": 0,
        "unsupported_type": 0,
        "non_regular": 0,
        "too_large": 0,
        "unreadable_or_raced": 0,
        "binary": 0,
    }
    # Per-CLASS refusal counts. `sensitive_name` above is one bucket for six
    # different reasons; a reviewer who cannot tell a skipped .env from a
    # skipped payroll export cannot audit the sweep at all. Every sensitivity
    # class is seeded at zero so an absent class reads as "nothing matched"
    # rather than "never checked".
    refused_by_class: dict[str, int] = {name: 0 for name in SENSITIVITY_CLASSES}
    candidates = 0
    eligible: list[tuple[tuple[int, int, int, str], Path, Path]] = []

    def _refuse_sensitive(rel: Path) -> None:
        excluded["sensitive_name"] += 1
        refused_by_class[str(_sensitivity_class(rel))] += 1

    for current, dirnames, filenames in os.walk(source, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_dirs = []
        for dirname in sorted(dirnames):
            visited += 1
            if visited >= MAX_SCAN_ENTRIES:
                truncated = True
                break
            child = current_path / dirname
            rel = child.relative_to(source)
            if dirname in SKIP_DIRS or _is_hidden_rel(rel):
                excluded["hidden"] += 1
                continue
            if _is_sensitive(rel):
                _refuse_sensitive(rel)
                continue
            if child.is_symlink():
                excluded["symlink"] += 1
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs
        for filename in sorted(filenames):
            visited += 1
            if visited >= MAX_SCAN_ENTRIES:
                truncated = True
                break
            path = current_path / filename
            rel = path.relative_to(source)
            candidates += 1
            if _is_hidden_rel(rel):
                excluded["hidden"] += 1
                continue
            if _is_sensitive(rel):
                _refuse_sensitive(rel)
                continue
            if not _allowed_file(path):
                excluded["unsupported_type"] += 1
                continue
            try:
                lst = path.lstat()
                if stat.S_ISLNK(lst.st_mode):
                    excluded["symlink"] += 1
                    continue
                if not stat.S_ISREG(lst.st_mode):
                    excluded["non_regular"] += 1
                    continue
                resolved = path.resolve(strict=True)
                resolved.relative_to(source)
                # A file bigger than the PER-FILE ceiling is excluded on its own
                # merits. Budget exhaustion is deliberately NOT counted here: a
                # file the window simply ran out of room for was never too
                # large, and filing it as such is how the loss hid.
                if lst.st_size > MAX_FILE_BYTES:
                    excluded["too_large"] += 1
                    continue
            except (OSError, RuntimeError, ValueError):
                excluded["unreadable_or_raced"] += 1
                continue
            eligible.append((_relevance_key(rel), path, rel))
        if visited >= MAX_SCAN_ENTRIES:
            truncated = True
            break
    eligible.sort(key=lambda item: item[0])
    eligible_count = len(eligible)
    entries: list[dict[str, Any]] = []
    reached = 0
    for _key, path, rel in eligible:
        reached += 1
        if len(entries) >= MAX_FILES or total >= MAX_TOTAL_BYTES:
            truncated = True
            reached -= 1
            break
        try:
            lst = path.lstat()
            if not stat.S_ISREG(lst.st_mode) or lst.st_size > MAX_FILE_BYTES:
                excluded["unreadable_or_raced"] += 1
                continue
            if total + lst.st_size > MAX_TOTAL_BYTES:
                truncated = True
                reached -= 1
                break
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            try:
                opened = os.fstat(fd)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_size > MAX_FILE_BYTES
                    or (opened.st_dev, opened.st_ino) != (lst.st_dev, lst.st_ino)
                ):
                    excluded["unreadable_or_raced"] += 1
                    continue
                with os.fdopen(fd, "rb", closefd=False) as fh:
                    raw = fh.read(MAX_FILE_BYTES + 1)
            finally:
                os.close(fd)
        except (OSError, RuntimeError, ValueError):
            excluded["unreadable_or_raced"] += 1
            continue
        if len(raw) > MAX_FILE_BYTES:
            excluded["too_large"] += 1
            continue
        if total + len(raw) > MAX_TOTAL_BYTES:
            truncated = True
            reached -= 1
            break
        if b"\x00" in raw[:4096]:
            excluded["binary"] += 1
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
    unexamined = max(eligible_count - reached, 0)
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
        "scan_statistics": {
            "candidate_files": candidates,
            "included_files": len(manifest_files),
            "excluded": excluded,
            "refused_by_sensitivity_class": refused_by_class,
            "refusals_total": sum(refused_by_class.values()),
        },
        # The claim surface for every negative the dividend states. ``complete``
        # is the ONLY thing that entitles the card to say "I did not find X" —
        # anything else scopes the sentence to the files actually opened.
        "coverage": {
            "eligible_files": eligible_count,
            "examined_files": len(manifest_files),
            "unexamined_files": unexamined,
            "complete": unexamined == 0 and not truncated,
            "ordering": "relevance",
        },
    }
    manifest = {**manifest_payload, "manifest_hash": _hash(manifest_payload)}
    return manifest, entries


def _source_integrity_fingerprint(source: Path) -> dict[str, Any]:
    """Hash bounded First-Window metadata without persisting paths or contents.

    The before/after proof covers the same eligible, non-sensitive source
    surface as the First Window.  It deliberately prunes hidden/system trees,
    sensitive names and symlinks, and stops at the same entry/file/byte limits.
    Otherwise a large ``.git`` or dependency tree could hold the onboarding
    lock for minutes even though the approved scan would never inspect it.
    """
    rows: list[tuple[str, int, int, int, int, int]] = []
    visited = 0
    total = 0
    truncated = False
    for current, dirnames, filenames in os.walk(source, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            visited += 1
            if visited >= MAX_SCAN_ENTRIES:
                truncated = True
                break
            child = current_path / dirname
            rel = child.relative_to(source)
            if dirname in SKIP_DIRS or _is_hidden_rel(rel) or _is_sensitive(rel):
                continue
            try:
                if stat.S_ISLNK(child.lstat().st_mode):
                    continue
            except OSError:
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs
        for name in sorted(filenames):
            visited += 1
            if len(rows) >= MAX_FILES or total >= MAX_TOTAL_BYTES or visited >= MAX_SCAN_ENTRIES:
                truncated = True
                break
            path = current_path / name
            try:
                meta = path.lstat()
                rel_path = path.relative_to(source)
            except (OSError, ValueError):
                continue
            if (
                _is_hidden_rel(rel_path)
                or _is_sensitive(rel_path)
                or not _allowed_file(path)
                or stat.S_ISLNK(meta.st_mode)
                or not stat.S_ISREG(meta.st_mode)
            ):
                continue
            if meta.st_size > MAX_FILE_BYTES or total + meta.st_size > MAX_TOTAL_BYTES:
                truncated = True
                continue
            rows.append((
                rel_path.as_posix(),
                int(meta.st_mode),
                int(meta.st_size),
                int(meta.st_mtime_ns),
                int(meta.st_dev),
                int(meta.st_ino),
            ))
            total += int(meta.st_size)
        if len(rows) >= MAX_FILES or total >= MAX_TOTAL_BYTES or visited >= MAX_SCAN_ENTRIES:
            truncated = True
            break
    return {
        "hash": _hash(rows),
        "entry_count": len(rows),
        "truncated_by_limits": truncated,
    }


def _command_drift(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    # Union of the declared scripts of EVERY package.json inside the First
    # Window. A documented command is drift only when NO package in the window
    # declares it. Checking a single package.json (e.g. packages[0]) raised
    # confident, citation-backed false "broken command" claims in any workspace
    # or monorepo where the script lives in a sibling package.
    declared: set[str] = set()
    package_count = 0
    for entry in entries:
        if Path(entry["path"]).name != "package.json":
            continue
        try:
            obj = json.loads(entry["text"])
        except ValueError:
            continue
        scripts = obj.get("scripts", {}) if isinstance(obj, dict) else {}
        if isinstance(scripts, dict):
            package_count += 1
            declared |= {str(k) for k in scripts}
    if package_count == 0:
        return findings
    # The script name must START with an alphanumeric character so an option
    # flag ("yarn --version") is never captured and reported as a missing
    # script — a leading hyphen was previously accepted by the character class.
    command_re = re.compile(
        r"\b(?:npm\s+run|pnpm(?:\s+run)?|yarn)\s+([A-Za-z0-9][A-Za-z0-9:_-]*)\b"
    )
    builtin = {"add", "audit", "exec", "help", "init", "install", "remove", "run", "update"}
    for entry in entries:
        if Path(entry["path"]).suffix.lower() not in {".md", ".mdx", ".rst", ".txt"}:
            continue
        for line_no, line in enumerate(entry["lines"], start=1):
            for match in command_re.finditer(line):
                command = match.group(1)
                if command in builtin or command in declared:
                    continue
                findings.append({
                    "score": 100,
                    "kind": "software_command_drift",
                    "quality": "strong",
                    "summary": (
                        f"The documentation tells someone to run “{command}”, but no package.json in the "
                        "approved folder declares that script. "
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
    # A strong claim needs an explicit status marker, not a word appearing in
    # ordinary prose.  The former substring regex treated "hook-blocked" in a
    # technical document as a blocked work item and made the headline dividend
    # lie.  Accept familiar Markdown prefixes and status labels, then require
    # the marker at the start of the meaningful text.
    markdown_prefix = re.compile(
        r"^\s*(?:(?:#{1,6}|[-*+]|\d+[.)]|\[[ xX]\])\s+|[*_`]+)*"
    )
    urgent = re.compile(
        r"^(?:(?:urgent|blocked|overdue|needs action|action required)\s*(?::|[-–—]\s|$)"
        r"|(?:status|state|priority)\s*:\s*(?:urgent|blocked|overdue|needs action|action required)\b)",
        re.I,
    )
    comment_prefix = re.compile(r"^\s*(?:(?://+|/\*+|<!--|#+|[-*+]|\[[ xX]\])\s*)+")
    todo = re.compile(r"^(?:todo|fixme|xxx)\s*(?::|[-–—(]|$)", re.I)
    out: list[dict[str, Any]] = []
    for entry in entries:
        for line_no, line in enumerate(entry["lines"], start=1):
            meaningful = markdown_prefix.sub("", line).lstrip("*_`")
            if urgent.search(meaningful):
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
            open_work = comment_prefix.sub("", line).lstrip("*_`")
            if not urgent.search(meaningful) and todo.search(open_work):
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
    coverage = manifest.get("coverage") or {}
    complete = bool(coverage.get("complete"))
    unexamined = int(coverage.get("unexamined_files") or 0)
    if findings:
        finding = findings[0]
    elif entries:
        first = entries[0]
        # EARN THE NEGATIVE OR SCOPE IT. The old sentence claimed a global "did
        # not find a broken documented command" over a window that had never
        # opened most of the folder — measured false on an employee-scale slice
        # while exactly such a command sat unread. A negative is only about the
        # set actually examined, and when that set is a subset the card says so
        # in the same breath rather than leaving the loss on a manifest field
        # no operator reads.
        if complete:
            summary = (
                f"I read all {manifest['file_count']} supported files in that folder and found no "
                "contradiction, broken documented command, or explicit urgent marker. Nothing was "
                "left unopened, so that negative covers the whole folder."
            )
        else:
            summary = (
                f"I read {manifest['file_count']} of {coverage.get('eligible_files', manifest['file_count'])} "
                f"supported files, most-informative first, and found no contradiction, broken documented "
                f"command, or explicit urgent marker IN WHAT I READ. {unexamined} eligible files were left "
                "unopened by the First Window limits, so this is not a clean bill of health for the folder — "
                "widen the window or point me at a narrower one and I will finish the job."
            )
        finding = {
            "score": 10,
            "kind": "orientation_map",
            "quality": "orientation_only",
            "summary": summary,
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
        # Carried on the dividend, not left on the manifest, because the
        # dividend is what every surface renders — a coverage figure an
        # operator never sees is not a disclosure.
        "coverage": deepcopy(coverage),
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
    trace_id: str,
    correlation_id: str,
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
        "trace_id": trace_id,
        "correlation_id": correlation_id,
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
    result = {
        "ok": True,
        "event": {k: row[k] for k in (
            "event_id", "action_id", "trace_id", "correlation_id", "action", "surface", "ts"
        )},
        "state": after,
        "card": _card(after),
    }
    if manifest is not None:
        result["evidence_summary"] = {
            "manifest_hash": manifest.get("manifest_hash"),
            "scan_statistics": manifest.get("scan_statistics"),
            "source_integrity": manifest.get("source_integrity"),
        }
    return result


def _purge(
    root: Path,
    state: dict[str, Any],
    request: dict[str, Any],
    *,
    surface: str,
    trace_id: str,
    correlation_id: str,
    now: str,
) -> dict[str, Any]:
    if request.get("confirmation") != "PURGE":
        raise JourneyError("purge_confirmation", "Type PURGE exactly to delete onboarding data.")
    action_id = str(request.get("action_id") or f"purge-{uuid.uuid4().hex}")
    receipt = {
        "schema": "cabinet.onboarding-purge-receipt/v1",
        "purged_at": now,
        "purged_journey_id_hash": hashlib.sha256(state["journey_id"].encode("utf-8")).hexdigest(),
        "surface": surface,
        "trace_id": trace_id,
        "correlation_id": correlation_id,
        "action_id": action_id,
        "pending_evidence_trial_id": state["evidence_trial_id"],
        "status": "started",
        "note": "Purge intent recorded; completion is pending.",
    }
    receipts = root / PURGE_RECEIPTS_REL
    _secure_dir(receipts)
    receipt_path = receipts / f"purge-{now.replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:6]}.json"
    _atomic_json(receipt_path, receipt)
    fresh, completed = _finish_purge(root, receipt_path, receipt)
    return {"ok": True, "purged": True, "state": fresh, "card": _card(fresh), "receipt": completed}


def _open_ingest_or_refuse(
    raw_ownership: Any, raw_basis: Any, now: str
) -> dict[str, Any]:
    """Run the ingest ceiling, translating its refusal into a JourneyError.

    The refusal CODE is carried through unchanged (``ownership_unclassified``,
    ``ownership_class_unknown``, ``authority_basis_required``,
    ``authority_basis_too_long``) so a surface can key its help text on the
    specific thing the operator has not answered yet.
    """
    try:
        return open_ingest(raw_ownership, raw_basis, attested_at=now)
    except OwnershipRefusal as exc:
        raise JourneyError(exc.code, str(exc), detail=exc.detail) from exc


def _write_access_record(
    root: Path, state: dict[str, Any], manifest: dict[str, Any], *, now: str
) -> Path:
    """Persist the content-free per-source record of THIS read.

    Written at ratification — the moment the read actually happens — and
    deliberately outside the purgeable data directory. A purge annotates it
    with its receipt rather than deleting it: an operator may delete what was
    read, but the fact that a read occurred, against whose data and under what
    claimed right, is the audit trail and does not belong to the read.
    """
    charter = state["charter"]
    source = state["source"]
    stats = manifest.get("scan_statistics") or {}
    record = access_record(
        schema=ACCESS_RECORD_SCHEMA,
        source_root=str(source["root"]),
        ownership=str(source["ownership"]),
        authority_basis=str(source["authority_basis"]),
        charter_hash=str(charter["hash"]),
        manifest_hash=str(manifest["manifest_hash"]),
        entry_count=int(manifest.get("file_count") or 0),
        refusals=dict(stats.get("refused_by_sensitivity_class") or {}),
        retention=str(charter["payload"]["retention"]["raw_file_contents"]),
        recorded_at=now,
    )
    record["journey_id_hash"] = hashlib.sha256(
        str(state["journey_id"]).encode("utf-8")
    ).hexdigest()
    record["other_exclusions"] = dict(stats.get("excluded") or {})
    records_dir = root / ACCESS_RECORDS_REL
    _secure_dir(records_dir)
    path = records_dir / f"access-{record['charter_hash'][:16]}.json"
    _atomic_json(path, record)
    return path


def _annotate_access_records(root: Path, receipt: dict[str, Any]) -> None:
    """Stamp the purge receipt onto every surviving access record, and REDACT the root.

    Two Captain-facing promises meet here and both are kept. The audit trail
    must survive the read it describes — an operator may delete what was read,
    but the fact that a read happened, against whose data and under what
    claimed right, is not theirs to erase. And purge promises that no source
    PATH is retained. So the record survives with its ownership class,
    authority basis, hashes, counts and refusals intact, while the root itself
    is replaced by its digest: still linkable to a later record of the same
    folder, no longer a readable path.

    Best effort: a record that cannot be re-read or re-written must never block
    a purge (the rule the evidence plane already follows — the deletion the
    Captain asked for wins over bookkeeping).
    """
    records_dir = root / ACCESS_RECORDS_REL
    if not records_dir.is_dir():
        return
    for path in sorted(records_dir.glob("access-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                continue
            root_value = str(record.get("source_root") or "")
            if root_value:
                record["source_root_sha256"] = hashlib.sha256(
                    root_value.encode("utf-8")
                ).hexdigest()
            record["source_root"] = None
            record["source_root_redacted_by_purge"] = True
            record["purge_receipt"] = str(receipt.get("action_id") or "")
            record["purged_at"] = str(receipt.get("purged_at") or "")
            _atomic_json(path, record)
        except (OSError, ValueError):
            continue


def _act_core(
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
    # _REQUEST_ID_RE is the SAME anchor the evidence plane enforces. A laxer
    # shape here (a leading punctuation character was previously accepted)
    # let the committed canonical event and the evidence trail carry
    # different ids for one action, breaking cross-plane audit correlation.
    if not _REQUEST_ID_RE.fullmatch(action_id):
        raise JourneyError("action_id_invalid", "The onboarding action id is invalid.")
    ts = _now(now)
    trace_id = str(request.get("trace_id") or f"trace-{uuid.uuid4().hex}")
    correlation_id = str(request.get("correlation_id") or f"corr-{uuid.uuid4().hex}")
    for name, value in (("trace_id", trace_id), ("correlation_id", correlation_id)):
        if not _REQUEST_ID_RE.fullmatch(value):
            raise JourneyError(f"{name}_invalid", f"The onboarding {name.replace('_', ' ')} is invalid.")

    with _locked(base):
        state = _load_state(base)
        # ``act`` performs an early lifecycle check before it records intent,
        # but releases that lock while writing evidence.  A concurrent purge
        # can complete in that interval.  The inner action lock is the commit
        # boundary, so it must independently refuse the stale action; otherwise
        # propose_window can recreate state after a successful purge.
        if state.get("stage") == "purged":
            raise JourneyError(
                "onboarding_purged",
                "Onboarding data was purged. No later action can reopen its evidence trial.",
            )
        duplicate = _event_for_action(base, action_id)
        if duplicate:
            # Idempotent replay only when the SAME action reuses the id. A reused
            # id carrying a DIFFERENT action would otherwise return ok:true while
            # silently dropping the new action — refuse it instead.
            if str(duplicate.get("action")) != action:
                raise JourneyError("action_id_reused", "That onboarding action id was already used for a different action.")
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
            return _purge(
                base, state, request, surface=surface, trace_id=trace_id,
                correlation_id=correlation_id, now=ts,
            )
        if action == "propose_window":
            source = _validate_source(request.get("source"))
            purpose = _validate_purpose(request.get("purpose"))
            destination = str(request.get("relationship_destination") or "reversible")
            if destination not in DESTINATIONS:
                raise JourneyError("destination_invalid", "Choose earn, reversible, or sovereign as the trust destination.")
            # THE INGEST CEILING, before any charter exists. A source the
            # operator cannot classify is refused here, not filed under a
            # plausible default — the refusal is a recorded event like any
            # other action, so "I could not say whose this was" survives.
            ingest = _open_ingest_or_refuse(
                request.get("ownership"), request.get("authority_basis"), ts
            )
            charter = _build_charter(source, purpose, destination, ingest)
            after = deepcopy(state)
            after.update(
                stage="charter_pending",
                purpose=purpose,
                relationship_destination=destination,
                orientation_mode=ORIENTATION_MODE,
                access="not_granted",
                source={
                    "kind": "folder",
                    "root": str(source),
                    "label": source.name,
                    "status": "proposed",
                    "ownership": ingest["ownership"],
                    "authority_basis": ingest["authority_basis"],
                },
                charter=charter,
                first_dividend=None,
            )
            return _commit(
                base, state, after, action=action, action_id=action_id,
                surface=surface, trace_id=trace_id,
                correlation_id=correlation_id, now=ts,
            )
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
            source_before = _source_integrity_fingerprint(source)
            manifest, entries = _scan_source(source, expected_hash)
            source_after = _source_integrity_fingerprint(source)
            integrity = {
                "before_hash": source_before["hash"],
                "after_hash": source_after["hash"],
                "before_entry_count": source_before["entry_count"],
                "after_entry_count": source_after["entry_count"],
                "before_truncated_by_limits": source_before["truncated_by_limits"],
                "after_truncated_by_limits": source_after["truncated_by_limits"],
                "unchanged": source_before == source_after,
            }
            manifest_payload = {key: value for key, value in manifest.items() if key != "manifest_hash"}
            manifest_payload["source_integrity"] = integrity
            manifest = {**manifest_payload, "manifest_hash": _hash(manifest_payload)}
            if not integrity["unchanged"]:
                raise JourneyError(
                    "source_changed_during_scan",
                    "The folder changed while I was reading it, so I did not publish a potentially stale result.",
                    detail={
                        "source_integrity": integrity,
                        "scan_statistics": manifest.get("scan_statistics"),
                    },
                )
            dividend = _first_dividend(manifest, entries, ts)
            # The record of the read outlives the read (and the purge).
            _write_access_record(base, state, manifest, now=ts)
            after = deepcopy(state)
            after["stage"] = "dividend_ready"
            after["access"] = "active_read_only"
            after["source"]["status"] = "ratified_read_only"
            after["source"]["manifest_hash"] = manifest["manifest_hash"]
            after["charter"]["status"] = "ratified"
            after["charter"]["ratified_at"] = ts
            after["first_dividend"] = dividend
            return _commit(
                base, state, after, action=action, action_id=action_id,
                surface=surface, trace_id=trace_id,
                correlation_id=correlation_id, now=ts, manifest=manifest,
            )
        if action == "continue":
            if state["stage"] not in {"dividend_ready", "paused", "orientation_offered"}:
                raise JourneyError("continue_unavailable", "There is nothing ready to continue yet.")
            after = deepcopy(state)
            after["stage"] = "orientation_offered"
            return _commit(
                base, state, after, action=action, action_id=action_id,
                surface=surface, trace_id=trace_id,
                correlation_id=correlation_id, now=ts,
            )
        if action == "pause":
            if state["stage"] not in {"dividend_ready", "orientation_offered"}:
                raise JourneyError("pause_unavailable", "This journey is not currently running.")
            after = deepcopy(state)
            after["stage"] = "paused"
            return _commit(
                base, state, after, action=action, action_id=action_id,
                surface=surface, trace_id=trace_id,
                correlation_id=correlation_id, now=ts,
            )
        if action == "revoke":
            if not state.get("source"):
                raise JourneyError("nothing_to_revoke", "No folder access has been granted.")
            after = deepcopy(state)
            after["stage"] = "revoked"
            after["access"] = "revoked"
            after["source"]["status"] = "revoked"
            return _commit(
                base, state, after, action=action, action_id=action_id,
                surface=surface, trace_id=trace_id,
                correlation_id=correlation_id, now=ts,
            )
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
                trace_id=trace_id, correlation_id=correlation_id, now=ts,
                reversible=False, undo_of=str(target["event_id"]),
                manifest=target.get("before_manifest"),
            )
        raise JourneyError("action_unknown", f"Unknown onboarding action: {action}.")


# The onboarding producer bindings for the shared act-class recording helper
# (framework.evidence.lifecycle).  These strings are byte-exact with every
# v1 event already on disk — do NOT "improve" them.
_EVIDENCE_COMPONENT = {"name": "onboarding-core", "version": "2+evidence-v1"}


def _evidence_actor(phase: str) -> dict[str, str]:
    captain = phase in {"intent", "feedback"}
    return {
        "kind": "captain" if captain else "system",
        "id": "captain" if captain else "onboarding-core",
    }


def _evidence_unavailable() -> JourneyError:
    return JourneyError(
        "evidence_unavailable",
        "The Cabinet could not preserve a trustworthy evidence receipt, so no further onboarding action was taken.",
    )


def _evidence_integrity() -> JourneyError:
    return JourneyError(
        "evidence_integrity",
        "The onboarding evidence chain needs review before another action can run.",
    )


def _remint_evidence_trial(
    base: Path,
    recorder: EvidenceRecorder,
    purged_trial_id: str,
    *,
    surface: str,
) -> str:
    """Mint a fresh evidence trial for a live journey whose trial was purged.

    Retention or a Captain CLI purge can legitimately tombstone the LIVE
    onboarding trial. Without a re-mint path every later ``act()``/
    ``observe()`` — including purge itself — would refuse forever with
    ``evidence_unavailable``, silently ending the record-everything mandate.
    The swap happens under the journey state lock; the fresh trial opens with
    a genesis event linking the tombstone hash so the audit trail shows
    exactly where (and why) the trial lineage restarted. Purge FINALITY still
    wins: a purged journey is never re-minted.
    """
    def swap_live_trial(purged: str) -> tuple[str, bool]:
        state = _load_state(base)
        if state.get("stage") == "purged":
            raise JourneyError(
                "onboarding_purged",
                "Onboarding data was purged. No later action can reopen its evidence trial.",
            )
        current = str(state.get("evidence_trial_id"))
        if current != purged:
            # A concurrent caller already re-minted; adopt its live trial so
            # the journey never forks into two evidence lineages.
            return current, False
        fresh = f"onboarding-{uuid.uuid4().hex}"
        state["evidence_trial_id"] = fresh
        _atomic_json(_state_path(base), state)
        return fresh, True

    return remint_trial(
        recorder,
        purged_trial_id,
        surface=surface,
        state_lock=lambda: _locked(base),
        swap_live_trial=swap_live_trial,
        actor_policy=_evidence_actor,
        component=dict(_EVIDENCE_COMPONENT),
        unavailable_error=_evidence_unavailable,
    )


def act(
    request: dict[str, Any],
    root: Path | str | None = None,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Record and apply one canonical action across every onboarding surface."""
    base = Path(root) if root else cabinet_root()
    with _locked(base):
        state = _load_state(base)
        trial_id = str(state["evidence_trial_id"])
        if state.get("stage") == "purged":
            raise JourneyError(
                "onboarding_purged",
                "Onboarding data was purged. No later action can reopen its evidence trial.",
            )

    raw = request if isinstance(request, dict) else {}
    requested_surface = str(raw.get("surface") or "unknown")
    surface = requested_surface if requested_surface in {
        "dashboard", "telegram", "world", "companion", "cli", "test", "unknown"
    } else "unknown"
    # The action name is free text until the core validates it; scrub lone
    # surrogates so it can be hashed into evidence (and echoed in a refusal)
    # instead of crashing canonicalization with a raw UnicodeEncodeError.
    action = _scrub_lone_surrogates(str(raw.get("action") or "invalid_request"))[:80]

    recorder = EvidenceRecorder(base / EVIDENCE_REL)
    recording = ActLifecycle(
        recorder,
        trial_id=trial_id,
        surface=surface,
        actor_policy=_evidence_actor,
        component=dict(_EVIDENCE_COMPONENT),
        producer_error=JourneyError,
        unavailable_error=_evidence_unavailable,
        integrity_error=_evidence_integrity,
        remint=lambda purged: _remint_evidence_trial(
            base, recorder, purged, surface=surface
        ),
        producer_purged_code="onboarding_purged",
        # Deletion must stay available even when the evidence ledger cannot
        # be verified; for ``purge`` evidence failures degrade and are
        # recorded in the onboarding purge receipt below instead of blocking.
        degrade_on_failure=action == "purge",
    )
    # Pre-flight reconcile before anything runs: a tombstoned live trial (a
    # crash-interrupted purge left its receipt) re-mints so onboarding keeps
    # recording instead of wedging forever; any other evidence failure
    # refuses the action (or degrades, purge only).
    recording.recover_interrupted()

    context = recording.begin(
        trace_id=valid_id_or_none(raw.get("trace_id")),
        action_id=valid_id_or_none(raw.get("action_id")),
        correlation_id=valid_id_or_none(raw.get("correlation_id")),
    )

    normalized = dict(raw)
    # The committed canonical event and the evidence trail must carry the
    # SAME ids: the helper overwrites trace/correlation with the recorder-
    # validated context ids and KEEPS a malformed caller action id for the
    # core's deterministic refusal (see ActLifecycle.unify_ids).
    recording.unify_ids(normalized)
    if isinstance(raw.get("action"), str):
        normalized["action"] = _scrub_lone_surrogates(raw["action"])
    recording.intent(
        detail={
            "action": action,
            "before_revision": state.get("revision"),
            "requested_surface": requested_surface,
            "request_shape_valid": isinstance(request, dict),
        },
    )
    recording.proposed(
        detail={
            "action": action,
            "reason_code": "validation_and_authority_check_started",
            "authority_effect": "none",
        },
    )
    try:
        result = _act_core(normalized if isinstance(request, dict) else request, base, now=now)
    except JourneyError as exc:
        recording.refused(
            refusal_detail={
                "action": action,
                "error_code": exc.code,
                "reason_code": "core_refusal",
                **exc.detail,
            },
            outcome_detail={"action": action, "error_code": exc.code},
        )
        raise
    except Exception as exc:
        error_code = f"unexpected_{type(exc).__name__.lower()}"
        recording.failed(
            error_detail={"action": action, "error_code": error_code},
            outcome_detail={"action": action, "error_code": error_code},
        )
        raise

    result_status = (
        "duplicate" if result.get("duplicate") else
        "paused" if action == "pause" else
        "revoked" if action == "revoke" else
        "undone" if action == "undo" else
        "purged" if action == "purge" else
        "succeeded"
    )
    summary = result.get("evidence_summary") if isinstance(result.get("evidence_summary"), dict) else {}
    after_revision = (result.get("state") or {}).get("revision")
    event_ref = result.get("event", {}).get("event_id") if isinstance(result.get("event"), dict) else result.get("event_id")
    recording.completed(
        result_status=result_status,
        allowed_detail={"action": action, "reason_code": "core_contract_satisfied"},
        execution_detail={
            "action": action,
            "before_revision": state.get("revision"),
            "after_revision": after_revision,
            "manifest_hash": summary.get("manifest_hash"),
            "excluded": (summary.get("scan_statistics") or {}).get("excluded") if isinstance(summary.get("scan_statistics"), dict) else None,
            "file_count": (summary.get("scan_statistics") or {}).get("included_files") if isinstance(summary.get("scan_statistics"), dict) else None,
        },
        verification_detail={
            "action": action,
            "revision": after_revision,
            "source_integrity": summary.get("source_integrity") or {"unchanged": True, "scope": "no_source_write_capability"},
            "verification": "canonical_state_and_receipt_present",
        },
        receipt_detail={"action": action, "receipt_id": event_ref or "idempotent-replay"},
        receipt_links=[f"onboarding-event:{event_ref}"] if event_ref else [],
        outcome_detail={"action": action, "result_code": result_status, "revision": after_revision},
    )
    # A mid-action re-mint swaps the live trial; report the ids the events
    # actually landed under.
    context = recording.context
    result["evidence"] = {
        "trial_id": context.trial_id,
        "trace_id": context.trace_id,
        "action_id": context.action_id,
        "correlation_id": context.correlation_id,
    }
    if action == "purge":
        purge_action_id = str(normalized.get("action_id") or context.action_id)
        try:
            result["evidence_purge"] = recorder.purge_trial(
                context.trial_id,
                confirmation=f"PURGE {context.trial_id}",
                actor="captain",
            )
            completed = _complete_onboarding_evidence_purge(
                base,
                action_id=purge_action_id,
                trial_id=context.trial_id,
            )
            if completed is not None:
                result["receipt"] = completed
        except EvidenceError as exc:
            if exc.code in {"trial_purged", "trial_not_found"}:
                # A concurrent purge (retention/CLI) already tombstoned the
                # trial: the deletion goal is met, so complete the receipt
                # instead of failing the Captain's purge.
                result["evidence_purge"] = {
                    "status": "already_purged",
                    "purged_trial_id_hash": hashlib.sha256(
                        context.trial_id.encode("utf-8")
                    ).hexdigest(),
                }
                completed = _complete_onboarding_evidence_purge(
                    base,
                    action_id=purge_action_id,
                    trial_id=context.trial_id,
                )
                if completed is not None:
                    result["receipt"] = completed
            else:
                # The onboarding purge already completed; reporting it as a
                # failure would tell the Captain the deletion did not happen.
                # Record the evidence-plane failure in the receipt and keep
                # the pending marker so recovery (or a Captain force purge)
                # finishes the evidence-side deletion later.
                result["evidence_purge"] = {"status": "pending", "error_code": exc.code}
                annotated = _annotate_purge_receipt(
                    base, purge_action_id,
                    {"evidence_purge_status": "pending", "evidence_purge_error": exc.code},
                )
                if annotated is not None:
                    result["receipt"] = annotated
        if recording.degraded_evidence is not None:
            annotated = _annotate_purge_receipt(
                base, purge_action_id,
                {"evidence_append_error": str(recording.degraded_evidence.get("error_code"))},
            )
            if annotated is not None:
                result["receipt"] = annotated
    return result


def observe(
    request: dict[str, Any],
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Record a bounded surface/transport/feedback observation.

    This is not a generic event writer. It can write only the three product
    observation phases and never accepts authority, hashes, timestamps,
    component provenance beyond the fixed onboarding components, or raw
    source content.
    """
    if not isinstance(request, dict):
        raise JourneyError("observation_shape", "The onboarding observation must be an object.")
    base = Path(root) if root else cabinet_root()
    with _locked(base):
        state = _load_state(base)
        if state.get("stage") == "purged":
            raise JourneyError(
                "onboarding_purged",
                "Onboarding data was purged. No later signal can reopen its evidence trial.",
            )
    trial_id = str(state["evidence_trial_id"])
    surface = str(request.get("surface") or "unknown")
    if surface not in {"dashboard", "telegram", "world", "companion", "api", "cli", "test", "unknown"}:
        raise JourneyError("surface_invalid", "Unknown onboarding surface.")
    phase = str(request.get("phase") or "")
    if phase not in {"transport", "ui", "feedback"}:
        raise JourneyError("observation_phase", "That onboarding observation phase is not available.")
    allowed_status = {
        "transport": {"started", "succeeded", "failed", "retried", "interrupted", "recovered"},
        "ui": {"started", "succeeded", "failed", "interrupted", "recovered"},
        "feedback": {"useful", "not_useful", "corrected"},
    }
    status = str(request.get("status") or "")
    if status not in allowed_status[phase]:
        raise JourneyError("observation_status", "That onboarding observation status is not available.")

    def safe_id(name: str, prefix: str) -> str:
        value = str(request.get(name) or f"{prefix}-{uuid.uuid4().hex}")
        if not _REQUEST_ID_RE.fullmatch(value):
            raise JourneyError(f"{name}_invalid", f"The onboarding {name.replace('_', ' ')} is invalid.")
        return value

    recorder = EvidenceRecorder(base / EVIDENCE_REL)
    context = recorder.trace(
        trial_id,
        surface=surface,
        trace_id=safe_id("trace_id", "trace"),
        action_id=safe_id("action_id", "observe"),
        correlation_id=safe_id("correlation_id", "corr"),
    )
    raw_detail = request.get("detail") if isinstance(request.get("detail"), dict) else {}
    allowed_keys = {
        "action", "error_code", "reason_code", "result_code", "transport",
        "retry_count", "http_status", "feedback_rating", "feedback_category",
        "comment", "revision", "rendered_stage", "app_shell_handoff",
    }
    # Free-text detail values (feedback comments, error strings) are scrubbed
    # of unpaired surrogates so the observation records instead of crashing
    # evidence canonicalization.
    detail = {
        key: (_scrub_lone_surrogates(value) if isinstance(value, str) else value)
        for key, value in raw_detail.items()
        if key in allowed_keys
    }

    def observe_append(ctx: Any) -> dict[str, Any]:
        return recorder.append(
            ctx,
            phase=phase,
            status=status,
            actor={"kind": "captain" if phase == "feedback" else "surface", "id": "captain" if phase == "feedback" else surface},
            component={"name": f"onboarding-{surface}", "version": "1"},
            detail=detail,
        )

    try:
        event = observe_append(context)
    except EvidenceError as exc:
        if exc.code == "trial_purged":
            # Retention/CLI tombstoned the live trial while the journey stayed
            # live: re-mint and retry once so the observation is still kept.
            trial_id = _remint_evidence_trial(base, recorder, trial_id, surface=surface)
            context = recorder.trace(
                trial_id, surface=surface, trace_id=context.trace_id,
                action_id=context.action_id, correlation_id=context.correlation_id,
            )
            try:
                event = observe_append(context)
            except EvidenceError as retry_exc:
                raise JourneyError("evidence_unavailable", "The onboarding observation could not be preserved.") from retry_exc
        else:
            raise JourneyError("evidence_unavailable", "The onboarding observation could not be preserved.") from exc
    return {
        "ok": True,
        "evidence": {
            "trial_id": context.trial_id,
            "event_id": event["event_id"],
            "trace_id": context.trace_id,
            "action_id": context.action_id,
            "correlation_id": context.correlation_id,
        },
    }


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="framework.onboarding.journey")
    parser.add_argument("command", choices=["snapshot", "act", "observe"])
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
            result = act(request) if args.command == "act" else observe(request)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except JourneyError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "error": str(exc)}, ensure_ascii=False))
        return 3


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
