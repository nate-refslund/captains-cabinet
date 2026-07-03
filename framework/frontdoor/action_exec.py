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
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable

_SHARED = str(Path.home() / ".screenpipe" / "pipes" / "_shared")
MONDAY_API = "https://api.monday.com/v2"


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
    if desc:
        monday_post(
            "mutation($item: ID!, $body: String!) {"
            " create_update(item_id: $item, body: $body) { id } }",
            {"item": str(item_id), "body": desc[:4000]})
    return {"monday_id": str(item_id), "board_id": board}


def _exec_monday_update(payload: dict, monday_post: Callable) -> dict:
    item = str(payload.get("monday_id") or "").strip()
    setmap = payload.get("set") or {}
    if not item.isdigit():
        raise RuntimeError(f"monday_task_update needs a numeric monday_id (got {item!r})")
    if not isinstance(setmap, dict) or not setmap:
        raise RuntimeError("monday_task_update needs a non-empty set map")
    applied = []
    if setmap.get("description") or setmap.get("note") or payload.get("why"):
        body = str(setmap.get("description") or setmap.get("note") or payload.get("why"))
        monday_post(
            "mutation($item: ID!, $body: String!) {"
            " create_update(item_id: $item, body: $body) { id } }",
            {"item": item, "body": body[:4000]})
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
    return {"monday_id": item, "applied": applied}


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
        '   make new event with properties {summary:evTitle, start date:startDate, end date:endDate, description:evNotes}\n'
        '  end tell\n'
        ' on error\n'
        # the named calendar is read-only (e.g. an Exchange view) or otherwise
        # unwritable — land on the dedicated writable "Cabinet" calendar instead
        '  set calName to "Cabinet"\n'
        '  if not (exists (first calendar whose name is calName)) then make new calendar with properties {name:calName}\n'
        '  tell (first calendar whose name is calName)\n'
        '   make new event with properties {summary:evTitle, start date:startDate, end date:endDate, description:evNotes}\n'
        '  end tell\n'
        ' end try\n'
        'end tell\n'
        'return "ok:" & calName\n'
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
    return {"calendar": res.split(":", 1)[-1] or cal, "title": title[:80]}


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
    msg = (f"[action-lane] CAPTAIN-APPROVED WORK ITEM — execute and report back "
           f"to the Chair when done:\n\n{brief}")
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


def deliver_action(pid: str, override_text: str = "", *,
                   redis_get: Callable[[str], str] | None = None,
                   monday_post: Callable | None = None,
                   osascript: Callable | None = None,
                   dry_run: bool = False) -> dict:
    """Execute the stored action chain for an APPROVED card. deliver_draft-shaped
    return: {ok, via, dest, executed: [...], error?}. Injectable transports for
    tests; production defaults resolve lazily."""
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
    rec_cid = str(rec.get("cid") or "")
    for i, step in enumerate(steps, 1):
        kind = step.get("kind")
        payload = dict(step.get("payload") or {})
        if rec_cid:
            payload["_cid"] = rec_cid
        if dry_run:
            executed.append({"step": i, "kind": kind, "dry_run": True})
            continue
        try:
            if kind == "monday_task_create":
                out = _exec_monday_create(payload, mp)
            elif kind == "monday_task_update":
                out = _exec_monday_update(payload, mp)
            elif kind == "reminder_create":
                # backend is per-instance config (Captain ruling: reminders on
                # the CALENDAR; Apple Reminders demoted to an optional plugin —
                # other captains may prefer it: ACTION_LANE_REMINDER_BACKEND)
                backend = os.environ.get("ACTION_LANE_REMINDER_BACKEND", "calendar")
                out = (_exec_reminder(payload, osa) if backend == "apple_reminders"
                       else _exec_calendar_event(payload, osa))
            elif kind == "delegate_work":
                out = _exec_delegate(payload)
            else:
                raise RuntimeError(f"unknown action kind {kind!r}")
            executed.append({"step": i, "kind": kind, **out})
        except Exception as e:  # stop the chain; report what DID run
            return {"ok": False, "via": "action-lane", "dest": rec.get("lane", "?"),
                    "executed": executed,
                    "error": f"step {i}/{len(steps)} ({kind}) failed: {e}"[:300]}
    if not dry_run:
        # one-shot execution: clear the record so a re-delivered approve no-ops
        try:
            _redis("DEL", f"cabinet:action:{pid}")
        except Exception:
            pass
    return {"ok": True, "via": "action-lane", "dest": rec.get("lane", "?"),
            "executed": executed}
