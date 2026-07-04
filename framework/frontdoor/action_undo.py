"""UNDO-1 — write-ahead undo journal + deterministic inverse executors.

The reversal half of the action executor (the 2026-07-04 trust-inversion pivot,
grand-plan §1 + impl-plan §1.1). ``action_exec.deliver_action`` writes a
WRITE-AHEAD journal row for every acted step BEFORE the mutating call, enriches
it with the created ids after, and drops a Redis pointer as an index. This
module owns that journal and the deterministic inverse ops that turn a landed
action back into a no-op — so any acted card carries a 48h undo handle and, when
the flip lands, an ``undo`` reply reverses the artifact and mints the estate's
first negative labels.

Doctrine baked in here (safety-spine §3 "undo honesty"):
  - WRITE-AHEAD, DURABLE: the journal is an append-only JSONL on disk (the
    ``consequence.py`` daily-rotated pattern); Redis is never the sole copy
    (CRIT-4). The pointer is an index; the file is the durable truth.
  - COMPARE-AND-RESTORE for board_status [RT-A11]: a column is restored only if
    its CURRENT value still equals what the lane wrote — otherwise a colleague
    edited it since and we DEAD-LETTER + tell, never clobber. The same
    quarantine applies BEFORE the restore when the journal row's prestate never
    captured a touched column (a failed prestate read — checkpoint 2026-07-04
    condition 1 / KILLED #2): restoring would write ``{}`` and CLEAR a value we
    never knew, so the row is dead-lettered, the kind FROZEN via
    ``actfirst_canary.freeze``, and the reverse never executes.
  - ARCHIVE, NEVER DELETE: a lane-created Monday item is reversed with
    ``archive_item`` (30-day trash), never ``delete_item``.
  - PER-ROW INVERSE FROM THE ACTUAL BACKEND [RT-B11]: the ``apple_reminders``
    reminder backend has no reliable inverse and is EXCLUDED from act-first v1
    (op ``none``); the calendar backend is the reversible one (delete-by-UID).
  - WIDENED REVERSIBLE KINDS (germline batch 2026-07-04): the four reversible
    classifier kinds {task_status_move, label, tier2_note, local_edit} carry
    registered deterministic inverses so the policy-engine allow-branch
    ("registered inverse exists, else propose-only") can grant their
    act_with_undo@unmeasured posture. Board-column kinds reuse the proven
    ``monday_compare_restore`` mechanic; file kinds get
    ``file_compare_restore`` — restore the captured prior content (or
    delete-if-created) ONLY while the file's sha256 still matches what the
    lane wrote; drift ⇒ dead-letter, never clobber. investigation_run is
    READ-ONLY (read_only_dispatch class) — no inverse, never through this
    door; deploy_nonprod / draft_only stay unregistered (NATE-DECISION:
    earn-up, see ``inverse_for``).
  - NO LLM anywhere in the reversal path — deterministic code only.

Stdlib-only, importable under system Python 3.9.6 (``from __future__`` +
Optional annotations, no runtime ``X | Y`` unions). All subprocess calls are
arg-lists; credentials are never touched here (reversal transports are injected
or resolved lazily from the executor's loaders). Fully unit-testable: every
external effect (Monday / AppleScript / Redis) is an injected callable.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from framework.fidelity.consequence import validate_consequence

# --- constants ---------------------------------------------------------------

# The 48h undo window every receipt advertises (grand-plan §1). The Redis
# pointer outlives it (9d) so a late undo still finds its index; the journal
# row's ttl_expires_at is the 48h survival clock the TTL sweep (UNDO-3) reads.
UNDO_WINDOW_H = 48
# Pointer TTL: 9 days = 48h window + late-undo grace, and it outlives the 7d
# ``cabinet:action:<pid>`` record. Redis is only ever the INDEX (never the sole
# copy — the JSONL is durable), so a lapsed pointer degrades to a journal scan.
POINTER_TTL_S = 777600
# Journal retention floor; the GC (UNDO-3, a later wave) prunes older files.
JOURNAL_RETENTION_D = 30

# Backends with no reliable inverse — EXCLUDED from act-first v1 [RT-B11]. The
# Apple Reminders surface cannot be deterministically reversed (no stable
# per-item handle we control end-to-end), so its rows journal op ``none`` and
# ``act_first_eligible`` returns False. Such cards execute ONLY when the Captain
# approves them on the binder — they never act unattended.
ACT_FIRST_EXCLUDED_BACKENDS = frozenset({"apple_reminders"})

# ``dead_letter`` is the TERMINAL quarantine state: a row whose reverse would
# be dishonest (e.g. a compare-restore with never-captured prestate) — never
# re-attempted, never reported as undone, surfaced loudly for manual review.
_ROW_STATUSES = frozenset({"executed", "reversed", "reversal_failed", "void",
                           "dead_letter"})

# step-kind -> classifier action_type is owned by the proposer lane as ONE map
# (action_lane.ACTION_TYPE_MAP, enum-guarded by action_lane.step_action_type).
# This module resolves through that single source (action_type_for) so the
# card's stamp and the executor's per-step acted events can never drift [RT-B6]
# — a local copy here already diverged once (missing investigation_run).


class UndoJournalError(ValueError):
    """Raised when a journal row is malformed (fail before any write)."""


# --- time / id helpers -------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_plus(ts: str, *, hours: int) -> str:
    try:
        base = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        base = datetime.now(timezone.utc)
    return (base + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mint() -> str:
    """A fresh opaque journal id (uuid4 hex) — the write-ahead row and its
    post-mutation enrichment share this id so last-write-wins collapses them."""
    return uuid.uuid4().hex


def action_type_for(kind: Optional[str]) -> Optional[str]:
    """The classifier action_type a step of this kind stamps, or None — resolved
    through the proposer lane's SINGLE source (action_lane.step_action_type over
    ACTION_TYPE_MAP) so the card stamp and the executor's per-step acted events
    can never drift [RT-B6]. Enum-guarded there: an unapplied germline type
    (task_create / calendar_event_create / officer_dispatch) resolves to None
    until its Moment lands. Lazy import — the reversal module never hard-depends
    on the proposer at load time."""
    from framework.acting import action_lane
    return action_lane.step_action_type(action_lane.ActionStep(kind=kind or "", title=""))


# --- journal store (durable, append-only JSONL) ------------------------------

def _undo_dir() -> Path:
    """The undo-journal directory. CABINET_UNDO_DIR overrides (tests point it at
    a tmp dir); default is the durable per-user location (NOT /tmp, which is
    wiped) — same override discipline as consequence.py's CABINET_EVENT_LOG_DIR."""
    return Path(os.environ.get(
        "CABINET_UNDO_DIR",
        os.path.expanduser("~/Library/Application Support/cabinet/undo"),
    ))


def _ensure_dir(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    try:                                    # 0700 — the journal holds prestate
        os.chmod(d, 0o700)                  # content that never leaves the box
    except OSError:
        pass


def _journal_file(base: Path) -> Path:
    # Fixed, non-user-controlled basename: the only variable part is a
    # strftime('%Y-%m-%d') date (digits + hyphens), so no caller input can
    # traverse out (Corridor path-safety, mirrors consequence.py:_write_to_log).
    return base / ("undo-journal-"
                   + datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl")


def _safe_journal_files(log_dir: Path) -> List[Path]:
    """The undo-journal-*.jsonl files that genuinely live under the resolved
    dir — a symlink planted in the dir pointing outside is skipped, never
    followed (mirrors consequence.py:_safe_ledger_files)."""
    base = log_dir.resolve()
    safe: List[Path] = []
    for f in sorted(log_dir.glob("undo-journal-*.jsonl")):
        try:
            real = f.resolve()
        except OSError:
            continue
        if real == base or base in real.parents:
            safe.append(f)
    return safe


def new_row(*, pid: str, cid: str, step: int, kind: str, backend: str,
            lane: Optional[str], subject: str, actor: Optional[dict],
            prestate: Optional[dict] = None, created: Optional[dict] = None,
            inverse: Optional[dict] = None, executed_at: Optional[str] = None,
            status: str = "executed", canary: bool = False,
            jid: Optional[str] = None, now: Optional[str] = None) -> Dict[str, Any]:
    """Build a journal row. ``prestate`` CONTENT lives ONLY here, never on the
    consequence ledger (the ledger stays lifecycle-only). ``created`` is empty
    on the write-ahead row and enriched after the mutation; ``inverse`` is the
    ``{op, args}`` derived from the ACTUAL backend used at write time."""
    ts = now or _now()
    return {
        "jid": jid or _mint(),
        "ts": ts,
        "pid": str(pid),
        "cid": str(cid or ""),
        "step": int(step),
        "kind": kind,
        "backend": backend,
        "lane": lane,
        "subject": str(subject or "")[:300],
        # CANONICAL ACTOR ID (germline batch 2026-07-04): the id is the BARE
        # role ("cos"), NEVER "officer:cos" — the demotion-evidence gate
        # composes "officer:"+role for its ledger query, so a pre-prefixed id
        # reads back as "officer:officer:cos" and SEVERS this row from the
        # demotion evidence it is supposed to supply.
        "actor": actor or {"kind": "officer", "id": "cos"},
        "action_type": action_type_for(kind),
        "prestate": prestate or {},
        "created": created or {},
        "inverse": inverse or {"op": "none", "args": {}},
        "executed_at": executed_at,
        "reversed_at": None,
        "ttl_expires_at": _iso_plus(ts, hours=UNDO_WINDOW_H),
        "status": status,
        "canary": bool(canary),
    }


def _validate_row(row: dict) -> None:
    if not isinstance(row, dict):
        raise UndoJournalError("journal row must be an object")
    for k in ("jid", "pid", "kind", "status"):
        if not row.get(k):
            raise UndoJournalError(f"journal row missing {k}")
    if not isinstance(row.get("step"), int):
        raise UndoJournalError("journal row step must be an int")
    if row["status"] not in _ROW_STATUSES:
        raise UndoJournalError(f"journal row status must be one of {sorted(_ROW_STATUSES)}")
    inv = row.get("inverse")
    if not isinstance(inv, dict) or "op" not in inv:
        raise UndoJournalError("journal row inverse must be an object with an op")


def journal_step(row: dict) -> Dict[str, Any]:
    """Validate then append ONE journal row (write-ahead before the mutation;
    again — same jid — after, to enrich with created ids). Last-write-wins by
    jid on read collapses the pair to the final state."""
    _validate_row(row)
    d = _undo_dir()
    _ensure_dir(d)
    base = d.resolve()
    with open(_journal_file(base), "a") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return row


def _read_journal(*, pid: Optional[str] = None) -> List[Dict[str, Any]]:
    """All journal rows collapsed by jid (last-write-wins), optionally filtered
    to one pid. Chronological by ts; equal-ts rows keep append order so an
    enrichment / reversal line still wins over the write-ahead line."""
    d = _undo_dir()
    if not d.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for f in _safe_journal_files(d):
        try:
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(r, dict) or "jid" not in r:
                        continue
                    if pid is not None and r.get("pid") != str(pid):
                        continue
                    rows.append(r)
        except OSError:
            continue
    rows.sort(key=lambda r: r.get("ts", ""))
    collapsed: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        collapsed[r["jid"]] = r
    return list(collapsed.values())


# --- Redis pointer (index only — never the sole copy) ------------------------

def _redis(*args: str) -> str:
    host = os.environ.get("REDIS_HOST", "localhost")
    out = subprocess.run(["redis-cli", "-h", host, *args],
                         capture_output=True, text=True, timeout=10).stdout.strip()
    return "" if out in ("", "(nil)") else out


def _default_redis_set(key: str, value: str, ttl_s: Optional[int]) -> None:
    args = ["SET", key, value]
    if ttl_s:
        args += ["EX", str(int(ttl_s))]
    _redis(*args)


def _default_redis_get(key: str) -> str:
    return _redis("GET", key)


def _default_redis_del(key: str) -> None:
    _redis("DEL", key)


def write_pointer(pid: str, steps: List[dict], executed_at: str, *,
                  redis_set: Optional[Callable[[str, str, Optional[int]], None]] = None,
                  ttl_s: int = POINTER_TTL_S) -> Dict[str, Any]:
    """Index the pid's acted steps: ``SET cabinet:undo:<pid> <json> EX 777600``.
    A convenience/fast lookup for the binder's undo grammar and the TTL sweep —
    the JSONL journal remains the durable copy, so a missing pointer only forces
    a journal scan, never data loss."""
    payload = {"pid": str(pid),
               "steps": [{"jid": s.get("jid"), "step": s.get("step"),
                          "kind": s.get("kind")} for s in (steps or [])],
               "executed_at": executed_at,
               "ttl_expires_at": _iso_plus(executed_at, hours=UNDO_WINDOW_H)}
    (redis_set or _default_redis_set)(f"cabinet:undo:{pid}", json.dumps(payload), ttl_s)
    return payload


def read_pointer(pid: str, *,
                 redis_get: Optional[Callable[[str], str]] = None) -> Optional[dict]:
    raw = (redis_get or _default_redis_get)(f"cabinet:undo:{pid}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


# --- inverse-op registry (open strings; future kinds slot in) ----------------

def query_columns(monday_post: Callable, item: str,
                  col_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Read the CURRENT value of specific columns of one item — the shared read
    used both for prestate capture (before write) and drift detection (before
    restore). Returns {column_id: {text, value, type}}; resilient to a fake /
    partial response (missing items -> {})."""
    data = monday_post(
        "query($item: [ID!], $cols: [String!]) {"
        " items(ids: $item) { column_values(ids: $cols) { id text value type } } }",
        {"item": [str(item)], "cols": [str(c) for c in col_ids]})
    items = (data or {}).get("items") or []
    cvs = (items[0].get("column_values") if items else []) or []
    out: Dict[str, Dict[str, Any]] = {}
    for cv in cvs:
        if isinstance(cv, dict) and cv.get("id") is not None:
            out[str(cv["id"])] = {"text": cv.get("text"),
                                  "value": cv.get("value"), "type": cv.get("type")}
    return out


def _restore_args(payload: dict, created: dict, prestate: dict) -> Dict[str, Any]:
    """Build the compare-and-restore args for a board_status inverse: per touched
    column, the value the lane wrote (for the drift check) + the prior value to
    restore (from prestate). The note leg (if any) is a delete_update by id.

    ``label`` joined the iterated columns with the germline widening
    (2026-07-04): a ``label`` / ``task_status_move`` step shares the
    monday_task_update payload contract ({monday_id, board_id?, set:{...}},
    real column id via ``<col>_column``), and a label column restores exactly
    like status/priority (``{"label": prior_text}`` — _restore_one_column's
    label leg). Additive for monday_task_update: its executor-enforced set-map
    schema (action_exec._SET_KEYS) doesn't carry ``label``, so nothing changes
    for existing cards."""
    setmap = (payload or {}).get("set") or {}
    columns: Dict[str, Any] = {}
    for col in ("status", "priority", "due", "label"):
        if col not in setmap:
            continue
        col_id = str(setmap.get(col + "_column") or col)
        prior = (prestate or {}).get(col_id) or {}
        columns[col_id] = {
            "wrote": str(setmap[col]),
            "prior_text": prior.get("text"),
            "kind": "date" if col == "due" else "label",
        }
    return {"board_id": (payload or {}).get("board_id"),
            "item_id": (payload or {}).get("monday_id"),
            "columns": columns,
            "update_id": (created or {}).get("note_update_id")}


def _file_restore_args(payload: dict, created: dict, prestate: dict) -> Dict[str, Any]:
    """Build the compare-and-restore args for a file-write inverse (tier2_note /
    local_edit — germline widening 2026-07-04).

    CAPTURE CONTRACT (the executor that journals a file kind writes these
    fields; this builder + ``_inv_file_compare_restore`` consume them):
      - prestate (on the WRITE-AHEAD row, read BEFORE the mutation):
          ``existed``: bool — did the file exist before the lane wrote?
          ``prior_content``: str | None — the FULL prior text (None iff
            existed is False; "" is a real, known-empty prior).
      - created (the enrichment row, AFTER the mutation):
          ``path``: str — the ABSOLUTE path actually written (absolute by
            contract: the inverse must never resolve against an ambient cwd).
          ``wrote_sha256``: str — sha256 hex of the file content AFTER the
            write. This is the drift fingerprint; for an append-style write
            the post-write content is prior+appended, which is why it MUST be
            read back from disk post-write, never derived from the payload.
    ``payload["path"]`` is only the write-ahead fallback for the path —
    ``created`` wins because it records what actually happened."""
    return {"path": (created or {}).get("path") or (payload or {}).get("path"),
            "existed": (prestate or {}).get("existed"),
            "prior_content": (prestate or {}).get("prior_content"),
            "wrote_sha256": (created or {}).get("wrote_sha256")}


def inverse_for(kind: str, backend: str, payload: Optional[dict],
                created: Optional[dict], prestate: Optional[dict]) -> Dict[str, Any]:
    """The ``{op, args}`` that reverses one executed step, derived from the
    ACTUAL backend used at write time. The op string is fixed by (kind, backend)
    even with empty args, so ``act_first_eligible`` can probe it cheaply."""
    payload = payload or {}
    created = created or {}
    prestate = prestate or {}
    if kind == "monday_task_create":
        return {"op": "monday_archive_item",
                "args": {"item_id": created.get("monday_id"),
                         "board_id": created.get("board_id") or payload.get("board_id"),
                         "update_id": created.get("update_id")}}
    if kind == "monday_task_update":
        return {"op": "monday_compare_restore",
                "args": _restore_args(payload, created, prestate)}
    # GERMLINE WIDENING (2026-07-04): the four reversible classifier kinds
    # {task_status_move, label, tier2_note, local_edit} get registered
    # deterministic inverses so the policy-engine allow-branch ("registered
    # inverse exists, else fall through to propose-only") can actually grant
    # their act_with_undo@unmeasured verdict. Deliberately NO backend branch
    # on these four: Monday is the only wired board-write surface, the file
    # ops are backend-agnostic by nature, and the eligibility probe may pass
    # the kind-fallback backend (run_action_lane._backend_for_step returns the
    # kind itself for unrouted kinds) — a genuinely-registered inverse must
    # not be gated out of the grant by a backend-string spelling. The journal
    # row still records the ACTUAL backend at write time [RT-B11], and every
    # restore is compare-first (drift ⇒ dead-letter, never clobber), so a
    # misrouted row degrades safe, not silent.
    if kind in ("task_status_move", "label"):
        # Same payload contract + restore mechanic as monday_task_update
        # ({monday_id, board_id?, set:{...}}): a status move / label write is
        # a Monday column write, reversed by compare-and-restore of exactly
        # the touched columns (_restore_args picks up the ``label`` leg).
        return {"op": "monday_compare_restore",
                "args": _restore_args(payload, created, prestate)}
    if kind in ("tier2_note", "local_edit"):
        # Restore the captured prior file content, or delete-if-created —
        # only while the file still matches what the lane wrote (sha256).
        return {"op": "file_compare_restore",
                "args": _file_restore_args(payload, created, prestate)}
    if kind == "reminder_create":
        if backend == "apple_reminders":
            return {"op": "none",
                    "args": {"reason": "apple_reminders has no reliable inverse "
                                       "— excluded from act-first v1"}}
        return {"op": "calendar_delete_by_uid",
                "args": {"uid": created.get("uid"), "calendar": created.get("calendar")}}
    if kind == "delegate_work":
        return {"op": "none",
                "args": {"reason": "delegate_work is propose-first — no act-first inverse"}}
    if kind == "investigation_run":
        # READ-ONLY by contract (read_only_dispatch class, germline batch
        # 2026-07-04): it commissions an investigation that returns a brief —
        # no side effects, so there is nothing to reverse and it must NEVER be
        # granted through the act-with-undo (inverse-backed) door. Its
        # notify_after posture is the policy layer's business; here it stays
        # op ``none`` (act_first_eligible False), exactly like delegate_work.
        return {"op": "none",
                "args": {"reason": "investigation_run is read-only — nothing to reverse"}}
    # NATE-DECISION (2026-07-04): deploy_nonprod and draft_only are NOT widened
    # — Captain judgment keeps them on the earn-up ladder, so they deliberately
    # have NO registered inverse and fall through to op ``none`` (⇒ propose-
    # only) like every other unregistered kind. Do not add them here without a
    # Captain ruling. Hard-ceiling kinds (outbound comms, prod deploy, spend,
    # secrets) must never appear in this registry at all.
    return {"op": "none", "args": {"reason": "unknown kind " + repr(kind)}}


def act_first_eligible(kind: str, backend: str) -> bool:
    """True iff this (kind, backend) has a REGISTERED, non-``none`` inverse and
    the backend is not on the act-first exclusion list. The mechanical perimeter
    (grand-plan §1): no inverse ⇒ no unattended act."""
    if backend in ACT_FIRST_EXCLUDED_BACKENDS:
        return False
    return inverse_for(kind, backend, {}, {}, {}).get("op") not in ("none", None)


def _inv_monday_archive_item(args: dict, *, monday_post: Callable,
                             osascript: Callable = None, **_) -> Dict[str, Any]:
    """Reverse a create: archive the item (30-day trash — NEVER delete_item) and
    delete the description update. Empty item_id (a crash row) is a safe no-op."""
    item_id = args.get("item_id")
    if not item_id:
        return {"ok": True, "skipped": "no item_id (crash/unexecuted row) — nothing to reverse"}
    detail: List[Any] = []
    monday_post("mutation($item: ID!) { archive_item(item_id: $item) { id } }",
                {"item": str(item_id)})
    detail.append(["archived_item", str(item_id)])
    upd = args.get("update_id")
    if upd:
        monday_post("mutation($u: ID!) { delete_update(id: $u) { id } }", {"u": str(upd)})
        detail.append(["deleted_update", str(upd)])
    return {"ok": True, "detail": detail}


def _restore_one_column(monday_post: Callable, board: str, item: str,
                        col_id: str, prior_text: Optional[str], kind: str) -> None:
    if prior_text in (None, ""):
        value = "{}"                                  # previously empty -> clear
    elif kind == "date":
        value = json.dumps({"date": str(prior_text)})
    else:                                             # status / priority label
        value = json.dumps({"label": str(prior_text)})
    monday_post(
        "mutation($board: ID!, $item: ID!, $col: String!, $val: JSON!) {"
        " change_column_value(board_id: $board, item_id: $item,"
        " column_id: $col, value: $val, create_labels_if_missing: true) { id } }",
        {"board": str(board), "item": str(item), "col": str(col_id), "val": value})


def _inv_monday_compare_restore(args: dict, *, monday_post: Callable,
                                osascript: Callable = None, **_) -> Dict[str, Any]:
    """Reverse a board_status write with COMPARE-AND-RESTORE [RT-A11]: re-read
    each touched column and restore its prior value ONLY if the current value is
    still what the lane wrote. A drifted column (a colleague edited it) is
    DEAD-LETTERED, never clobbered — its divergence is returned so the caller
    tells the Captain."""
    board = args.get("board_id")
    item = args.get("item_id")
    columns = args.get("columns") or {}
    restored: List[str] = []
    dead_letters: List[dict] = []
    if item and columns:
        current = query_columns(monday_post, str(item), list(columns.keys()))
        for col_id, spec in columns.items():
            cur_text = (current.get(col_id) or {}).get("text")
            if cur_text != spec.get("wrote"):
                dead_letters.append({"column_id": col_id, "reason": "drifted",
                                     "current": cur_text, "lane_wrote": spec.get("wrote")})
                continue
            if board:
                _restore_one_column(monday_post, str(board), str(item), col_id,
                                    spec.get("prior_text"), spec.get("kind"))
                restored.append(col_id)
    upd = args.get("update_id")
    if upd:
        monday_post("mutation($u: ID!) { delete_update(id: $u) { id } }", {"u": str(upd)})
    return {"ok": not dead_letters, "restored": restored, "dead_letters": dead_letters}


def _calendar_delete_script() -> str:
    # uid + calendar travel as argv (item N of argv), NEVER interpolated into
    # AppleScript source — same discipline as the executor's write path.
    return (
        'on run argv\n'
        'set calName to item 1 of argv\n'
        'set theUid to item 2 of argv\n'
        'tell application "Calendar"\n'
        ' if not (exists (first calendar whose name is calName)) then return "ok:absent"\n'
        ' tell (first calendar whose name is calName)\n'
        '  set matches to (every event whose uid is theUid)\n'
        '  repeat with ev in matches\n'
        '   delete ev\n'
        '  end repeat\n'
        ' end tell\n'
        'end tell\n'
        'return "ok"\n'
        'end run')


def _inv_calendar_delete(args: dict, *, monday_post: Callable = None,
                         osascript: Callable, **_) -> Dict[str, Any]:
    """Reverse a calendar event: delete by UID in the named calendar. Empty
    uid/calendar (a crash row) is a safe no-op."""
    uid = args.get("uid")
    cal = args.get("calendar")
    if not uid or not cal:
        return {"ok": True, "skipped": "no uid/calendar (crash/unexecuted row) — nothing to reverse"}
    res = osascript(["osascript", "-e", _calendar_delete_script(), str(cal), str(uid)])
    if "ok" in (res or ""):
        return {"ok": True, "detail": res}
    return {"ok": False, "error": "calendar delete returned " + repr(res)}


def _inv_file_compare_restore(args: dict, *, monday_post: Callable = None,
                              osascript: Callable = None, **_) -> Dict[str, Any]:
    """Reverse a file write (tier2_note / local_edit — germline widening
    2026-07-04) with COMPARE-AND-RESTORE: the [RT-A11] doctrine applied to
    files. Mutate ONLY if the file's CURRENT content is still byte-identical
    (sha256) to what the lane wrote — anything else means a colleague/officer
    touched it since, and we return a dead-letter, never clobber. Restore =
    write the captured prior content back; a file the lane CREATED
    (existed False) is deleted — the file only, never a directory, never
    recursive. Fail-closed on every unknown (missing fingerprint, relative
    path, uncaptured prior): a loud dead-letter, not a guess. The pre-flight
    honesty check lives in ``_prestate_quarantine_reason`` (dead-letter +
    freeze BEFORE execution); the checks here are the belt-and-braces stop
    for a row that reaches the executor anyway."""
    path = args.get("path")
    if not path:
        return {"ok": True, "skipped": "no path (crash/unexecuted row) — nothing to reverse"}
    path = str(path)

    def dead(reason: str) -> Dict[str, Any]:
        # ok:False + dead_letters mirrors _inv_monday_compare_restore's drift
        # return, so _reverse_rows journals reversal_failed + manual_cleanup.
        return {"ok": False, "dead_letters": [{"path": path, "reason": reason}]}

    # Never resolve against an ambient cwd — the capture contract
    # (_file_restore_args) journals ABSOLUTE paths; a relative one is a
    # malformed row, not a guessing game (Corridor path-safety, same posture
    # as _journal_file's fixed basename).
    if not os.path.isabs(path):
        return dead("relative path — the capture contract journals absolute "
                    "paths; refusing to guess a cwd")
    existed = args.get("existed")
    if existed not in (True, False):
        return dead("prestate never captured whether the file existed — "
                    "cannot know whether to delete or restore")
    if not os.path.exists(path):
        if existed is False:
            # The lane created it and it is already gone — the inverse's end
            # state already holds (mirrors the calendar "ok:absent" no-op).
            return {"ok": True, "skipped": "file already absent — nothing to reverse"}
        return dead("file deleted since the lane wrote it — restoring would "
                    "resurrect a colleague's deliberate delete")
    if os.path.isdir(path):
        return dead("path is a directory — the journal only ever records "
                    "regular files")
    wrote_sha = args.get("wrote_sha256")
    if not wrote_sha:
        return dead("no wrote_sha256 fingerprint on the row — cannot prove "
                    "the file is still what the lane wrote")
    try:
        with open(path, "rb") as fh:
            current_sha = hashlib.sha256(fh.read()).hexdigest()
    except OSError as e:
        return dead("unreadable file: " + str(e)[:120])
    if current_sha != str(wrote_sha):
        return dead("drifted — current content is not what the lane wrote "
                    "(edited since); never clobber")
    if existed is False:
        try:
            os.remove(path)             # the created FILE only — never a tree
        except OSError as e:
            return dead("delete failed: " + str(e)[:120])
        return {"ok": True, "detail": [["deleted_created_file", path]]}
    prior = args.get("prior_content")
    if not isinstance(prior, str):
        # existed True with no captured prior string — a restore would write
        # content the lane never knew. "" IS a valid known-empty prior (the
        # None/"" split mirrors the column rule in _prestate_quarantine_reason).
        return dead("prior content never captured — a restore would CLOBBER "
                    "the file with content the lane never knew")
    try:
        with open(path, "w") as fh:
            fh.write(prior)
    except OSError as e:
        return dead("restore write failed: " + str(e)[:120])
    return {"ok": True, "restored": [path]}


def _inv_none(args: dict, *, monday_post: Callable = None,
              osascript: Callable = None, **_) -> Dict[str, Any]:
    return {"ok": True,
            "skipped": (args or {}).get("reason")
            or "no reliable inverse — excluded from act-first v1"}


INVERSE_OPS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "monday_archive_item": _inv_monday_archive_item,
    "monday_compare_restore": _inv_monday_compare_restore,
    "calendar_delete_by_uid": _inv_calendar_delete,
    "file_compare_restore": _inv_file_compare_restore,
    "none": _inv_none,
}


# --- reversal (deterministic, no LLM) ----------------------------------------

def _prod_transports():
    """Lazy production transports for a live undo (deferred import breaks the
    action_exec<->action_undo cycle: action_exec imports us at module load; we
    import it only here, at call time)."""
    from framework.frontdoor import action_exec
    action_exec._load_shared_env()
    return action_exec._monday_post, action_exec._default_osascript


def _executed_rows_for(pid: str) -> List[Dict[str, Any]]:
    """The still-reversible rows for a pid: journaled, side-effect completed
    (executed_at set), not already reversed/void. Read from the DURABLE journal,
    so reversal works even if the Redis pointer lapsed."""
    return [r for r in _read_journal(pid=pid)
            if r.get("status") == "executed" and r.get("executed_at")]


def _summary(res: dict) -> Dict[str, Any]:
    return {k: v for k, v in (res or {}).items()
            if k in ("detail", "restored", "skipped")}


def _prestate_quarantine_reason(row: dict) -> Optional[str]:
    """The loud reason ``row`` must be DEAD-LETTERED instead of reversed, or
    None when the reverse is honest (checkpoint 2026-07-04 condition 1 /
    KILLED #2 leak (b)).

    A ``monday_compare_restore`` inverse restores each touched column from the
    row's prestate. When the prestate NEVER CAPTURED a touched column (the
    failed-prestate-read signature — usually the whole map is empty), the
    restore is indistinguishable from "the column was empty" and would write
    ``{}``, CLEARING a value the lane never knew — a clobber reported as
    success. A column entry that EXISTS with ``text: None`` is a KNOWN-empty
    prior and stays restorable. Fail-closed: no captured prior ⇒ no reverse.

    A ``file_compare_restore`` inverse (tier2_note / local_edit — germline
    widening 2026-07-04) consumes prestate the same way: ``existed`` must have
    been captured (else the inverse cannot know whether to delete or restore),
    and an existed-True row must carry the captured ``prior_content`` STRING
    (else the restore would clobber the file with content the lane never
    knew). An empty string IS a known-empty prior and stays restorable — the
    None/"" split mirrors the column ``text: None`` rule above."""
    inv = row.get("inverse") or {}
    op = inv.get("op")
    if op == "file_compare_restore":
        prestate = row.get("prestate") or {}
        if prestate.get("existed") not in (True, False):
            return ("prestate never captured whether the file existed — the "
                    "inverse cannot know whether to delete or restore; row "
                    "dead-lettered, kind frozen, artifact left standing for "
                    "manual review")
        if prestate.get("existed") is True \
                and not isinstance(prestate.get("prior_content"), str):
            return ("prestate never captured the prior file content — a "
                    "restore would CLOBBER the file with content the lane "
                    "never knew; row dead-lettered, kind frozen, artifact "
                    "left standing for manual review")
        return None
    if op != "monday_compare_restore":
        return None          # remaining registered ops don't consume prestate
    columns = (inv.get("args") or {}).get("columns") or {}
    if not columns:
        return None                     # note-only update: nothing restores from prestate
    prestate = row.get("prestate") or {}
    missing = sorted(c for c in columns if c not in prestate)
    if not missing:
        return None
    return ("prestate empty/missing for column(s) %s — the prior value was "
            "never captured, so a restore would CLOBBER the column to empty; "
            "row dead-lettered, kind frozen, artifact left standing for "
            "manual review" % ", ".join(missing))


def _quarantine_row(row: dict, reason: str, *, now: Optional[str]) -> Dict[str, Any]:
    """Dead-letter ``row`` (terminal — never re-attempted, never 'undone') and
    FREEZE its kind so no further unattended act of that kind runs until a
    manual green canary. Freeze goes through ``actfirst_canary.freeze`` — the
    one act-first control-plane surface — which resolves the breaker key
    (action_type) and writes the durable mirror first. A freeze-write failure
    never masks the quarantine: the dead-letter row is the durable truth."""
    result = {"ok": False, "dead_letter": True, "reason": reason}
    journal_step({**row, "status": "dead_letter", "reversed_at": now or _now(),
                  "reversal_result": result})
    try:
        # lazy import — actfirst_canary imports this module at load time.
        from framework.frontdoor import actfirst_canary
        actfirst_canary.freeze(row.get("kind") or "",
                               "prestate-clobber quarantine: " + reason, now=now)
    except Exception:
        pass                            # dead-letter row already quarantines
    return result


def _reverse_rows(rows: List[dict], *, pid: str, monday_post: Callable,
                  osascript: Callable, redis_del: Callable,
                  now: Optional[str]) -> Dict[str, Any]:
    """Execute the inverse ops for ``rows`` in REVERSE step order. Ledger-verdict
    ordering (fail-closed) is the caller's job (UNDO-2 binder); here we run the
    inverses, journal the reversal, and one-shot DEL the pointer on full success.
    Partial failure keeps a ``reversal_failed`` row + returns manual_cleanup."""
    lane = rows[0].get("lane") if rows else None
    reversed_steps: List[dict] = []
    manual: List[dict] = []
    for row in sorted(rows, key=lambda r: r.get("step", 0), reverse=True):
        inv = row.get("inverse") or {"op": "none", "args": {}}
        # PRESTATE-CLOBBER QUARANTINE (checkpoint condition 1 / KILLED #2): a
        # compare-restore whose prestate never captured the touched columns
        # must NEVER execute — it would restore-to-empty and clear a value the
        # lane never knew. Dead-letter + freeze + loud reason instead.
        quarantine = _prestate_quarantine_reason(row)
        if quarantine is not None:
            res = _quarantine_row(row, quarantine, now=now)
            manual.append({"step": row.get("step"), "kind": row.get("kind"),
                           "op": inv.get("op"), "result": res})
            continue
        op = INVERSE_OPS.get(inv.get("op"), _inv_none)
        try:
            res = op(inv.get("args") or {}, monday_post=monday_post, osascript=osascript)
        except Exception as e:                       # an inverse must never crash the sweep
            res = {"ok": False, "error": str(e)[:200]}
        rt = now or _now()
        if res.get("ok") and not res.get("dead_letters"):
            journal_step({**row, "status": "reversed", "reversed_at": rt})
            reversed_steps.append({"step": row.get("step"), "kind": row.get("kind"),
                                   **_summary(res)})
        else:
            journal_step({**row, "status": "reversal_failed", "reversed_at": rt,
                          "reversal_result": res})
            manual.append({"step": row.get("step"), "kind": row.get("kind"),
                           "op": inv.get("op"), "result": res})
    if manual:
        return {"ok": False, "via": "action-undo", "dest": lane,
                "reversed": reversed_steps, "manual_cleanup": manual,
                "error": (str(len(manual)) + " step(s) could not be reversed — "
                          "manual cleanup required; kind should be frozen")}
    try:                                             # one-shot: a re-undo no-ops
        redis_del("cabinet:undo:" + str(pid))
    except Exception:
        pass
    return {"ok": True, "via": "action-undo", "dest": lane, "reversed": reversed_steps}


def reverse(pid: str, *, monday_post: Optional[Callable] = None,
            osascript: Optional[Callable] = None,
            redis_del: Optional[Callable[[str], None]] = None,
            now: Optional[str] = None) -> Dict[str, Any]:
    """Reverse EVERY still-executed step of a pid, in reverse step order.
    Idempotent: once reversed the rows drop out, so a second call returns
    ``already_undone`` (mirrors the executor's one-shot no-op). A DEAD-LETTERED
    pid is the one exception: its artifact still STANDS, so re-undo surfaces
    the loud quarantine reason instead of a dishonest ``already_undone``."""
    rows = _executed_rows_for(pid)
    if not rows:
        dead = [r for r in _read_journal(pid=pid) if r.get("status") == "dead_letter"]
        if dead:
            return {"ok": False, "via": "action-undo",
                    "dest": dead[0].get("lane"), "reversed": [],
                    "dead_letter": True,
                    "error": str(((dead[0].get("reversal_result") or {}).get("reason"))
                                 or "row dead-lettered — artifact stands, manual review")}
        return {"ok": True, "already_undone": True, "via": "action-undo",
                "dest": None, "reversed": []}
    if monday_post is None or osascript is None:
        mp, osa = _prod_transports()
        monday_post = monday_post or mp
        osascript = osascript or osa
    return _reverse_rows(rows, pid=pid, monday_post=monday_post, osascript=osascript,
                         redis_del=redis_del or _default_redis_del, now=now)


def undo(target: str, *, monday_post: Optional[Callable] = None,
         osascript: Optional[Callable] = None,
         redis_del: Optional[Callable[[str], None]] = None,
         now: Optional[str] = None) -> Dict[str, Any]:
    """Public entry: reverse a whole pid OR a single journal id. If ``target``
    matches a known jid, reverse just that step; otherwise treat it as a pid.
    deliver_draft-shaped return ({ok, via, dest, reversed, ...})."""
    by_jid = {r.get("jid"): r for r in _read_journal()}
    row = by_jid.get(target)
    if row is None:
        return reverse(target, monday_post=monday_post, osascript=osascript,
                       redis_del=redis_del, now=now)
    if row.get("status") == "dead_letter":
        # quarantined: the artifact STANDS — surface the loud reason, never a
        # dishonest already_undone (checkpoint condition 1 / KILLED #2).
        return {"ok": False, "via": "action-undo", "dest": row.get("lane"),
                "reversed": [], "dead_letter": True,
                "error": str(((row.get("reversal_result") or {}).get("reason"))
                             or "row dead-lettered — artifact stands, manual review")}
    if row.get("status") != "executed" or not row.get("executed_at"):
        return {"ok": True, "already_undone": True, "via": "action-undo",
                "dest": row.get("lane"), "reversed": []}
    if monday_post is None or osascript is None:
        mp, osa = _prod_transports()
        monday_post = monday_post or mp
        osascript = osascript or osa
    return _reverse_rows([row], pid=row.get("pid"), monday_post=monday_post,
                         osascript=osascript, redis_del=redis_del or _default_redis_del,
                         now=now)


def find_reconcilable(*, pid: Optional[str] = None) -> List[Dict[str, Any]]:
    """Crash rows: journaled write-ahead but never enriched (no created ids / no
    executed_at). The intent-without-result reconciler (UNDO-3) re-probes or
    voids these; they are NEVER re-executed."""
    return [r for r in _read_journal(pid=pid)
            if r.get("status") == "executed" and not r.get("executed_at")
            and not (r.get("created") or {})]


# --- freeze / is_frozen (fail-closed) ----------------------------------------

def _frozen_mirror() -> Path:
    return _undo_dir() / "frozen-kinds.jsonl"


def freeze(kind: str, reason: str, *,
           redis_set: Optional[Callable[[str, str, Optional[int]], None]] = None,
           now: Optional[str] = None) -> Dict[str, Any]:
    """Freeze an act-first kind. Durable JSONL mirror FIRST (the source of
    truth), then the fast Redis flag. No TTL, no auto-unfreeze (CRIT-5): a kind
    is un-frozen only by a manually-triggered green canary (a later wave)."""
    row = {"ts": now or _now(), "kind": kind, "reason": str(reason)[:300], "op": "freeze"}
    d = _undo_dir()
    _ensure_dir(d)
    with open(_frozen_mirror(), "a") as fh:
        fh.write(json.dumps(row) + "\n")
    try:
        (redis_set or _default_redis_set)("cabinet:actfirst:frozen:" + str(kind),
                                          json.dumps(row), None)
    except Exception:
        pass                                # durable mirror is authoritative
    return row


def _kind_in_mirror(kind: str) -> bool:
    p = _frozen_mirror()
    if not p.exists():
        return False
    try:
        with open(p) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(r, dict) and r.get("kind") == kind and r.get("op") == "freeze":
                    return True
    except OSError:
        return True                         # can't read the mirror -> fail-closed
    return False


def is_frozen(kind: str, *,
              redis_get: Optional[Callable[[str], str]] = None) -> bool:
    """Fail-closed: Redis unreachable ⇒ treated frozen. A durable mirror hit
    also holds (Redis may have been flushed; a freeze is durable)."""
    getter = redis_get or _default_redis_get
    try:
        val = getter("cabinet:actfirst:frozen:" + str(kind))
    except Exception:
        return True
    if val:
        return True
    return _kind_in_mirror(kind)


# --- acted consequence event (per-STEP, RT-B1/RT-B6) -------------------------

def _acted_refs(row: dict) -> List[str]:
    refs: List[str] = []
    cid = row.get("cid")
    if cid:
        from framework.probes import correlation
        refs.append(correlation.ref_for(cid))
    jid = row.get("jid")
    if jid:
        refs.append("undo-journal:" + str(jid))
    return refs


def acted_event(step: Optional[dict], row: dict, *,
                action: Optional[str] = None) -> Dict[str, Any]:
    """The per-STEP acted consequence event. At EXECUTION time it carries
    ``proposal:{required:false, decision:null}`` + ``outcome:{status:"unknown"}``
    [RT-B1] so an acted row NEVER enters ``pending_proposals()`` and an
    unattended act NEVER counts as an approval. Each step stamps its OWN
    action_type [RT-B6] (guarded to real enum members). Validated against the
    consequence schema before returning — an invalid event is never emitted.

    NOT wired to live execution in Wave 1 — the executor journals; wiring the
    emit onto the ledger lands with the act-first branch (a later wave)."""
    kind = row.get("kind") or (step or {}).get("kind") or "action"
    ev: Dict[str, Any] = {
        "ts": row.get("executed_at") or row.get("ts") or _now(),
        # BARE role id — see the canonical-actor-id comment in new_row(): the
        # gate composes "officer:"+role, so "officer:cos" here would sever
        # this acted event from demotion evidence (germline batch 2026-07-04).
        "actor": row.get("actor") or {"kind": "officer", "id": "cos"},
        "lane": row.get("lane"),
        "action": action or ("acted:" + str(kind)),
        "subject": str(row.get("subject") or (step or {}).get("title") or kind)[:300],
        "refs": _acted_refs(row),
        "proposal": {"required": False, "decision": None},
        "outcome": {"status": "unknown"},
    }
    at = row.get("action_type")
    if at:                                  # guarded: only a real enum reaches the ledger
        ev["action_type"] = at
    validate_consequence(ev)                # raises before returning; never emit invalid
    return ev
