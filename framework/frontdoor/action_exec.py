"""Action executor — deliver an APPROVED action card's steps (2026-07-03 pivot).

The action-lane counterpart of chair_drafts.deliver_draft, with the same
contract: called by the binder's dispatch ONLY after the verdict has already
landed on the ledger (fail-closed ordering), returns {ok, via, dest, ...}.

v1 action kinds (low-blast, machine-verifiable):
  - monday_task_create  → Monday GraphQL create_item
  - monday_task_update  → Monday GraphQL change_multiple_column_values / status
  - reminder_create     → Apple Reminders via osascript (argv-passed, no
                          string-interpolated AppleScript with untrusted text)

Credentials: MONDAY_API_KEY from ~/.screenpipe/pipes/_shared/.env (the same
env the Plan-A pipes use). Never logged. All subprocess calls are arg-lists.
Steps execute IN ORDER; the first failure stops the chain (already-executed
steps are reported so nothing is silently half-done). An approve with
edit-text does NOT reinterpret the payload in v1 — the edit text is recorded
on the ledger as the correction; execution uses the stored payload verbatim
(reinterpreting free text into mutations without re-approval would act on
words Nate never saw as a card).

UNDO-1 (2026-07-04 trust-inversion): every step is WRITE-AHEAD journaled
through ``action_undo`` before its mutation and enriched with the created ids
after (``journal=True`` by default), and a strict per-kind payload-key assert
runs before ``_cid`` injection — so a landed card carries a 48h undo handle and
an attendee/assignee smuggle is a mechanical rejection. Journaling is
best-effort: it never breaks a delivery whose verdict already landed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable

from framework.frontdoor import action_undo

_SHARED = str(Path.home() / ".screenpipe" / "pipes" / "_shared")
MONDAY_API = "https://api.monday.com/v2"


class PayloadKeyError(ValueError):
    """A step payload carried a key outside its kind's closed schema — the
    fail-closed mechanical block on attendee/assignee/people smuggling [RT-B11].
    """


# Closed per-kind payload schemas. Anything outside these (except an injected
# ``_``-prefixed key) is REJECTED before the step runs — attendee/assignee/owner
# smuggling made mechanical, checked PRE-``_cid``-injection so the original
# proposer payload is validated clean.
_PAYLOAD_KEYS = {
    "monday_task_create": {"board_id", "board_hint", "title", "description"},
    "monday_task_update": {"monday_id", "board_id", "set", "why"},
    "reminder_create": {"title", "due_iso", "notes", "list"},
    "delegate_work": {"officer", "brief"},
}
# Closed key set for a monday_task_update ``set`` map (label writes + the
# per-column id overrides + the note leg). No people/assignee/subscriber key can
# ride in here.
_SET_KEYS = {"status", "priority", "due", "description", "note",
             "status_column", "priority_column", "due_column"}


def _assert_payload_keys(kind: str, payload: dict) -> None:
    """Reject any non-``_``-prefixed payload key outside the kind's closed
    schema (and any set-map key outside ``_SET_KEYS``). Raises PayloadKeyError —
    fail-closed: the step never journals or executes."""
    allowed = _PAYLOAD_KEYS.get(kind)
    if allowed is None:
        return                              # unknown kind: the exec dispatch rejects it
    for k in payload:
        if isinstance(k, str) and k.startswith("_"):
            continue                        # injected keys (e.g. _cid) — allowlisted
        if k not in allowed:
            raise PayloadKeyError(f"{kind}: disallowed payload key {k!r}")
    setmap = payload.get("set")
    if kind == "monday_task_update" and isinstance(setmap, dict):
        for k in setmap:
            if k not in _SET_KEYS:
                raise PayloadKeyError(f"{kind}: disallowed set-map key {k!r}")


def _backend_for(kind: str) -> str:
    """The concrete backend a step kind executes on — the inverse is derived
    from the ACTUAL backend used at write time [RT-B11]."""
    if kind in ("monday_task_create", "monday_task_update"):
        return "monday"
    if kind == "reminder_create":
        return ("apple_reminders"
                if os.environ.get("ACTION_LANE_REMINDER_BACKEND", "calendar") == "apple_reminders"
                else "calendar")
    if kind == "delegate_work":
        return "delegate"
    return "unknown"


def _redis(*args: str) -> str:
    host = os.environ.get("REDIS_HOST", "localhost")
    out = subprocess.run(["redis-cli", "-h", host, *args],
                         capture_output=True, text=True, timeout=10).stdout.strip()
    return "" if out in ("", "(nil)") else out


def _load_shared_env() -> None:
    """Load the Plan-A pipes env (MONDAY_API_KEY etc.) without clobbering
    already-set vars. Same source of truth the pipes use."""
    env_file = Path(_SHARED) / ".env"
    try:
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if v:                       # empty values never claim a key
                os.environ.setdefault(k.strip(), v)
    except OSError:
        pass


def _monday_post(query: str, variables: dict) -> dict:
    """One Monday GraphQL call. JSON-built body; key from env; never logged."""
    # Canonical var is MONDAY_API_TOKEN (per .env.example + the pipes' _shared/.env);
    # accept the legacy MONDAY_API_KEY name as a fallback. Fixes action-lane
    # deliveries failing "MONDAY_API_KEY not set" when only the TOKEN name is present.
    key = os.environ.get("MONDAY_API_TOKEN") or os.environ.get("MONDAY_API_KEY", "")
    if not key:
        raise RuntimeError("MONDAY_API_TOKEN / MONDAY_API_KEY not set")
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        MONDAY_API, data=body,
        headers={"Authorization": key, "Content-Type": "application/json",
                 "API-Version": "2024-10"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        out = json.load(resp)
    if out.get("errors"):
        raise RuntimeError(f"monday error: {out['errors'][:1]}")
    return out.get("data") or {}


# The Monday Tasks board in Nate's AI Workspace — the default landing board for
# lane-created tasks. A proposal's free-text board_hint routes here unless it
# carries an explicit numeric board_id (env ACTION_LANE_DEFAULT_BOARD overrides).
DEFAULT_TASKS_BOARD = "5091706356"


def _exec_monday_create(payload: dict, monday_post: Callable) -> dict:
    board = str(payload.get("board_id") or "").strip()
    if not board.isdigit():
        # free-text hints ("commitments", "polads") land on the default Tasks
        # board — the LLM cannot know board ids and must not have to
        board = os.environ.get("ACTION_LANE_DEFAULT_BOARD", DEFAULT_TASKS_BOARD)
    title = (payload.get("title") or "").strip()
    if not board.isdigit():
        raise RuntimeError(f"monday_task_create needs a numeric board_id (got {board!r})")
    if not title:
        raise RuntimeError("monday_task_create needs a title")
    cols: dict[str, Any] = {}
    if payload.get("description"):
        # long text lands as an update below; keep create minimal + robust
        pass
    data = monday_post(
        "mutation($board: ID!, $name: String!) {"
        " create_item(board_id: $board, item_name: $name) { id } }",
        {"board": board, "name": title[:250]})
    item_id = ((data.get("create_item") or {}).get("id"))
    if not item_id:
        raise RuntimeError("monday create returned no item id")
    desc = str(payload.get("description") or "")
    cid = str(payload.get("_cid") or "")
    if cid:
        # correlation footer (B2.1): makes the created item joinable to probe
        # outcomes — the evidence plane's stamp on lane-created artifacts.
        from framework.probes import correlation
        desc = (desc + "\n\n" if desc else "") + correlation.monday_footer(cid)
    update_id = None
    if desc:
        upd = monday_post(
            "mutation($item: ID!, $body: String!) {"
            " create_update(item_id: $item, body: $body) { id } }",
            {"item": str(item_id), "body": desc[:4000]})
        # capture the update id (previously discarded): the undo journal needs it
        # to delete the description post when reversing the create.
        update_id = ((upd.get("create_update") or {}).get("id"))
    return {"monday_id": str(item_id), "board_id": board, "update_id": update_id}


def _exec_monday_update(payload: dict, monday_post: Callable) -> dict:
    item = str(payload.get("monday_id") or "").strip()
    setmap = payload.get("set") or {}
    if not item.isdigit():
        raise RuntimeError(f"monday_task_update needs a numeric monday_id (got {item!r})")
    if not isinstance(setmap, dict) or not setmap:
        raise RuntimeError("monday_task_update needs a non-empty set map")
    applied = []
    note_update_id = None
    if setmap.get("description") or setmap.get("note") or payload.get("why"):
        body = str(setmap.get("description") or setmap.get("note") or payload.get("why"))
        upd = monday_post(
            "mutation($item: ID!, $body: String!) {"
            " create_update(item_id: $item, body: $body) { id } }",
            {"item": item, "body": body[:4000]})
        # capture the note update id so the undo journal can delete it on reverse
        note_update_id = ((upd.get("create_update") or {}).get("id"))
        applied.append("update-note")
    for col in ("status", "priority", "due"):
        if col not in setmap:
            continue
        # label-based writes only (people-board gotcha: NEVER index-based)
        board = str(payload.get("board_id") or "").strip()
        if not board.isdigit():
            raise RuntimeError(f"monday_task_update set.{col} needs board_id")
        column_id = str(setmap.get(f"{col}_column") or col)
        value = json.dumps({"label": str(setmap[col])}) if col != "due" \
            else json.dumps({"date": str(setmap[col])})
        monday_post(
            "mutation($board: ID!, $item: ID!, $col: String!, $val: JSON!) {"
            " change_column_value(board_id: $board, item_id: $item,"
            " column_id: $col, value: $val, create_labels_if_missing: true) { id } }",
            {"board": board, "item": item, "col": column_id, "val": value})
        applied.append(col)
    return {"monday_id": item, "applied": applied, "note_update_id": note_update_id}


def _monday_update_prestate(payload: dict, monday_post: Callable) -> dict:
    """Read the CURRENT value of exactly the columns a monday_task_update is
    about to touch — the prestate the undo journal compares against on reverse
    (restore only if the value is still what the lane wrote). Best-effort by
    contract: an unreadable prestate degrades undo to a dead-letter (never a
    clobber), it does not block the Captain-approved write."""
    item = str(payload.get("monday_id") or "").strip()
    setmap = payload.get("set") or {}
    if not item.isdigit() or not isinstance(setmap, dict):
        return {}
    col_ids = [str(setmap.get(f"{col}_column") or col)
               for col in ("status", "priority", "due") if col in setmap]
    if not col_ids:
        return {}
    return action_undo.query_columns(monday_post, item, col_ids)


def _exec_calendar_event(payload: dict, osascript: Callable) -> dict:
    """Reminder as a CALENDAR event (Captain ruling 2026-07-03: work reminders
    live on his calendar, not a personal to-do app). Calendar.app via argv-passed
    AppleScript; target calendar from ACTION_LANE_CALENDAR (default 'Work').
    30-minute block at due_iso; date-only due lands at 09:00."""
    title = (payload.get("title") or "").strip()
    if not title:
        raise RuntimeError("reminder_create needs a title")
    cal = os.environ.get("ACTION_LANE_CALENDAR", "Work").strip()
    due = (payload.get("due_iso") or "").strip()
    if not due:
        raise RuntimeError("calendar reminder needs due_iso")
    notes = (payload.get("notes") or "").strip()
    script = (
        'on run argv\n'
        'set calName to item 1 of argv\n'
        'set evTitle to item 2 of argv\n'
        'set evNotes to item 3 of argv\n'
        'set dueIso to item 4 of argv\n'
        'set startDate to my parseIso(dueIso)\n'
        'set endDate to startDate + (30 * minutes)\n'
        'tell application "Calendar"\n'
        ' if not (exists (first calendar whose name is calName)) then set calName to "Cabinet"\n'
        ' try\n'
        '  tell (first calendar whose name is calName)\n'
        '   set newEvent to make new event with properties {summary:evTitle, start date:startDate, end date:endDate, description:evNotes}\n'
        '  end tell\n'
        ' on error\n'
        # the named calendar is read-only (e.g. an Exchange view) or otherwise
        # unwritable — land on the dedicated writable "Cabinet" calendar instead
        '  set calName to "Cabinet"\n'
        '  if not (exists (first calendar whose name is calName)) then make new calendar with properties {name:calName}\n'
        '  tell (first calendar whose name is calName)\n'
        '   set newEvent to make new event with properties {summary:evTitle, start date:startDate, end date:endDate, description:evNotes}\n'
        '  end tell\n'
        ' end try\n'
        # return the created event UID so the undo journal can delete-by-UID on
        # reverse (the reversible handle the calendar backend earns act-first with)
        'end tell\n'
        'return "ok:" & calName & ":" & (uid of newEvent)\n'
        'end run\n'
        'on parseIso(s)\n'
        ' set d to current date\n'
        ' set year of d to (text 1 thru 4 of s) as integer\n'
        ' set month of d to (text 6 thru 7 of s) as integer\n'
        ' set day of d to (text 9 thru 10 of s) as integer\n'
        ' if (length of s) > 10 then\n'
        '  set hours of d to (text 12 thru 13 of s) as integer\n'
        '  set minutes of d to (text 15 thru 16 of s) as integer\n'
        ' else\n'
        '  set hours of d to 9\n'
        '  set minutes of d to 0\n'
        ' end if\n'
        ' set seconds of d to 0\n'
        ' return d\n'
        'end parseIso')
    res = osascript(["osascript", "-e", script, cal, title[:200], notes[:500], due])
    if "ok" not in res:
        raise RuntimeError(f"calendar returned {res!r}")
    # parse "ok:<calendar>:<uid>" (uid may contain colons — split at most twice).
    # Tolerant of the legacy "ok:<calendar>" shape (uid absent -> "").
    parts = (res or "").split(":", 2)
    out_cal = parts[1] if len(parts) > 1 and parts[1] else cal
    uid = parts[2] if len(parts) > 2 else ""
    return {"calendar": out_cal, "uid": uid, "title": title[:80]}


_DELEGATE_OFFICERS = {"cos", "polads-ceo", "stephie-ceo", "comms-officer"}


def _exec_delegate(payload: dict) -> dict:
    """delegate_work: dispatch an implementation brief to an officer lane via
    the durable trigger stream (+ tmux wake). The Captain-ruled 'SOLVE, don't
    just track' leg — an approved card puts real work in motion. Officer name
    is whitelist-validated; the brief travels as an argv value, never shell."""
    officer = (payload.get("officer") or "").strip()
    brief = (payload.get("brief") or "").strip()
    if officer not in _DELEGATE_OFFICERS:
        raise RuntimeError(f"delegate_work: unknown officer {officer!r}")
    if not brief:
        raise RuntimeError("delegate_work needs a brief")
    root = str(Path(__file__).resolve().parents[2])
    # [RT-A2] The brief is capture-derived (email/Teams → vault → proposer), so it
    # is UNTRUSTED text — framed as world-description the receiving officer must
    # verify, never as a command it should obey. Single source of truth for that
    # framing lives on the delegate_work kind (action_lane.DELEGATE_BRIEF_FRAME);
    # lazy-imported so this module never hard-depends on the proposer at load.
    from framework.acting.action_lane import DELEGATE_BRIEF_FRAME
    msg = DELEGATE_BRIEF_FRAME.format(brief=brief)
    r = subprocess.run(
        ["bash", "-c",
         '. "$1/cabinet/scripts/lib/triggers.sh" && OFFICER_NAME=action-lane trigger_send "$2" "$3"',
         "_", root, officer, msg],
        capture_output=True, text=True, timeout=20,
        env={**os.environ, "REDIS_HOST": os.environ.get("REDIS_HOST", "localhost")})
    if r.returncode != 0 or r.stderr.strip():
        raise RuntimeError(f"trigger_send failed: {r.stderr.strip()[:150] or r.returncode}")
    return {"delegated_to": officer, "brief_chars": len(brief)}


def _exec_reminder(payload: dict, osascript: Callable) -> dict:
    title = (payload.get("title") or "").strip()
    if not title:
        raise RuntimeError("reminder_create needs a title")
    lst = (payload.get("list") or "Screenpipe Work").strip()
    due = (payload.get("due_iso") or "").strip()
    notes = (payload.get("notes") or "").strip()
    # Values travel as argv → AppleScript reads them via `item N of argv`;
    # untrusted text never becomes AppleScript source.
    script = (
        'on run argv\n'
        'set listName to item 1 of argv\n'
        'set remTitle to item 2 of argv\n'
        'set remNotes to item 3 of argv\n'
        'set dueIso to item 4 of argv\n'
        'tell application "Reminders"\n'
        ' if not (exists (first list whose name is listName)) then set listName to "Screenpipe Work"\n'
        ' set theList to first list whose name is listName\n'
        ' set props to {name:remTitle}\n'
        ' if remNotes is not "" then set props to props & {body:remNotes}\n'
        ' set newRem to make new reminder at end of reminders of theList with properties props\n'
        ' if dueIso is not "" then\n'
        '  set remind me date of newRem to (my parseIso(dueIso))\n'
        ' end if\n'
        'end tell\n'
        'return "ok"\n'
        'end run\n'
        'on parseIso(s)\n'
        ' set d to current date\n'
        ' set year of d to (text 1 thru 4 of s) as integer\n'
        ' set month of d to (text 6 thru 7 of s) as integer\n'
        ' set day of d to (text 9 thru 10 of s) as integer\n'
        ' if (length of s) > 10 then\n'
        '  set hours of d to (text 12 thru 13 of s) as integer\n'
        '  set minutes of d to (text 15 thru 16 of s) as integer\n'
        ' else\n'
        '  set hours of d to 9\n'
        '  set minutes of d to 0\n'
        ' end if\n'
        ' set seconds of d to 0\n'
        ' return d\n'
        'end parseIso')
    res = osascript(["osascript", "-e", script, lst, title[:200], notes[:500], due])
    if "ok" not in res:
        raise RuntimeError(f"reminders returned {res!r}")
    return {"list": lst, "title": title[:80]}


def _default_osascript(cmd: list) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()


def _exec_step(kind: str, payload: dict, mp: Callable, osa: Callable) -> dict:
    """Dispatch one step to its executor. Raises on an unknown kind or a backend
    failure — the caller stops the chain and reports what already ran."""
    if kind == "monday_task_create":
        return _exec_monday_create(payload, mp)
    if kind == "monday_task_update":
        return _exec_monday_update(payload, mp)
    if kind == "reminder_create":
        # backend is per-instance config (Captain ruling: reminders on the
        # CALENDAR; Apple Reminders demoted to an optional plugin — other
        # captains may prefer it: ACTION_LANE_REMINDER_BACKEND)
        backend = os.environ.get("ACTION_LANE_REMINDER_BACKEND", "calendar")
        return (_exec_reminder(payload, osa) if backend == "apple_reminders"
                else _exec_calendar_event(payload, osa))
    if kind == "delegate_work":
        return _exec_delegate(payload)
    raise RuntimeError(f"unknown action kind {kind!r}")


def _best_effort(fn: Callable) -> None:
    """Run a side-effect that must NEVER break a delivery whose approval already
    landed (undo journaling + the Redis pointer/DEL) — parity with the existing
    best-effort ``cabinet:action`` cleanup."""
    try:
        fn()
    except Exception:
        pass


def deliver_action(pid: str, override_text: str = "", *,
                   redis_get: Callable[[str], str] | None = None,
                   monday_post: Callable | None = None,
                   osascript: Callable | None = None,
                   dry_run: bool = False,
                   journal: bool = True,
                   redis_set: Callable[[str, str, int | None], None] | None = None) -> dict:
    """Execute the stored action chain for an APPROVED card. deliver_draft-shaped
    return: {ok, via, dest, executed: [...], error?}. Injectable transports for
    tests; production defaults resolve lazily.

    ``journal`` (default True) write-ahead-journals every step through
    ``action_undo`` BEFORE its mutation and enriches the row with created ids
    after — so an approved (and, at the flip, an unattended) card carries a 48h
    undo handle. Journaling is best-effort: it never breaks a delivery whose
    verdict has already landed on the ledger."""
    rget = redis_get or (lambda k: _redis("GET", k))
    if override_text.strip():
        # EDIT on an action card: the verdict (edit→wrong + correction) has
        # already landed on the ledger — that label is the point. But we never
        # execute a payload the Captain just said is wrong, and we never
        # reinterpret free text into mutations he didn't see as a card.
        # The record is kept so the Chair can re-card the corrected chain.
        return {"ok": False, "edit_deferred": True,
                "error": "edit on action card — nothing executed; "
                         "Chair: re-card the corrected action"}
    raw = rget(f"cabinet:action:{pid}")
    if not raw:
        return {"ok": False, "error": f"no action {pid} (expired or already executed)"}
    try:
        rec = json.loads(raw)
    except (ValueError, TypeError):
        return {"ok": False, "error": "stored action record unparseable"}
    steps = rec.get("steps") or []
    if not steps:
        return {"ok": False, "error": "stored action has no steps"}

    _load_shared_env()
    mp = monday_post or _monday_post
    osa = osascript or _default_osascript

    executed: list[dict] = []
    journaled: list[dict] = []
    rec_cid = str(rec.get("cid") or "")
    lane = rec.get("lane", "?")
    subject = str(rec.get("subject") or "")
    actor = rec.get("actor") or {"kind": "officer", "id": "officer:cos"}
    for i, step in enumerate(steps, 1):
        kind = step.get("kind")
        payload = dict(step.get("payload") or {})
        # payload hygiene (fail-closed) BEFORE _cid injection — a smuggled
        # attendee/assignee key stops the step, nothing journals or executes.
        try:
            _assert_payload_keys(kind, payload)
        except PayloadKeyError as e:
            return {"ok": False, "via": "action-lane", "dest": lane,
                    "executed": executed,
                    "error": f"step {i}/{len(steps)} ({kind}) rejected: {e}"[:300]}
        if rec_cid:
            payload["_cid"] = rec_cid
        backend = _backend_for(kind)
        if dry_run:
            # no writes; surface the inverse spec so a dry chain proves its
            # inverse replays to a no-op (impl-plan verify) without touching disk.
            executed.append({"step": i, "kind": kind, "dry_run": True,
                             "inverse": action_undo.inverse_for(kind, backend, payload, {}, {})})
            continue

        # WRITE-AHEAD: prestate (update only) + a journal row with the inverse
        # spec, on disk BEFORE the mutation. A crash after this leaves a row with
        # no created ids / no executed_at — reconcilable, never re-executed.
        prestate: dict = {}
        if journal and kind == "monday_task_update":
            _best_effort(lambda: prestate.update(_monday_update_prestate(payload, mp)))
        jid = action_undo._mint()
        wa_row = None
        if journal:
            wa_row = action_undo.new_row(
                pid=pid, cid=rec_cid, step=i, kind=kind, backend=backend,
                lane=rec.get("lane"), subject=subject, actor=actor, prestate=prestate,
                inverse=action_undo.inverse_for(kind, backend, payload, {}, prestate),
                executed_at=None, jid=jid)
            _best_effort(lambda: action_undo.journal_step(wa_row))

        try:
            out = _exec_step(kind, payload, mp, osa)
        except Exception as e:  # stop the chain; report what DID run
            return {"ok": False, "via": "action-lane", "dest": lane,
                    "executed": executed,
                    "error": f"step {i}/{len(steps)} ({kind}) failed: {e}"[:300]}
        executed.append({"step": i, "kind": kind, **out})

        # ENRICH: same jid, now carrying the created ids + the fully-argumented
        # inverse. Last-write-wins collapses the pair to this committed state.
        if journal and wa_row is not None:
            enriched = {**wa_row, "created": dict(out),
                        "inverse": action_undo.inverse_for(kind, backend, payload, out, prestate),
                        "executed_at": action_undo._now()}
            _best_effort(lambda: action_undo.journal_step(enriched))
            journaled.append({"jid": jid, "step": i, "kind": kind})

    if dry_run:
        return {"ok": True, "via": "action-lane", "dest": lane, "executed": executed}
    # one-shot execution: clear the record so a re-delivered approve no-ops
    _best_effort(lambda: _redis("DEL", f"cabinet:action:{pid}"))
    if journal and journaled:
        # index the pid's undo window (Redis is the fast index; the JSONL is
        # durable, so a pointer-write failure only forces a journal scan).
        _best_effort(lambda: action_undo.write_pointer(
            pid, journaled, action_undo._now(), redis_set=redis_set))
    return {"ok": True, "via": "action-lane", "dest": lane, "executed": executed}
