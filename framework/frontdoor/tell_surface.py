"""TI-5 — the act-then-tell surface (grand-plan §3 WAVE 3 L4, RT-A3 / RT-B8).

The Captain's channel inverts at the flip from an approve-queue to an
act-then-tell digest: reversible acts land unattended, journaled + banner'd,
and are *told after* with a 48h undo handle. This module is the PURE FORMATTER
for that telling — it turns already-executed acts (undo-journal rows), still-
pending propose cards (consequence-ledger rows), scouted opportunities, and the
org's own self-state into the human-facing Telegram strings the surface emits:

  * ``receipt``              — the single act-then-tell receipt (instant tell).
  * ``build_digest``         — the daily ✅ACTED / ⚡AWAITING / 👁WATCHING / 🫀SELF
                               digest that rides the 07:30 + 19:30 briefings.
  * ``instant_tell_rules``   — the 5 cases that bypass the digest for a now-tell.
  * ``overflow_micro_digest``— a compact interim when ≥3 acts go untold.
  * ``should_quiet``         — the RT-B8 cell-quieting predicate (≥3 human
                               verdicts, all confirmed — one 👍 cannot buy silence).
  * ``digest_manifest``      — the index→pid map the binder's undo-by-index grammar
                               re-checks against ``cabinet:undo:<pid>``.

DOCTRINE BAKED IN HERE
  - PURE CORE, INJECTED ROWS. No file / network / subprocess / Redis anywhere in
    the formatters; every input is an injected dict and the wall-clock ``now`` is
    a frozen ISO-8601 string passed in — there is NO ``datetime.now()`` in the
    pure path (a single, clearly-fenced production reader at the bottom is the
    one impure seam, never exercised by the formatters or the tests).
  - MARKER HYGIENE [SEC-4 / RT-A9]. This surface renders UNTRUSTED text —
    email / Teams / OCR captured into the vault, then into proposal payloads and
    subjects. Every such string is run through ``action_lane._no_marker`` /
    ``_no_marker_deep`` to strip the U+00B7 ``·`` pid-marker char BEFORE it is
    rendered, so a planted ``·fakepid·`` can never ride a receipt and hijack the
    binder's undo/👍 grammar. Only the ONE server-issued real pid (the trusted
    journal ``pid`` field) is appended — LAST — after all stripping, so
    "the last marker wins" binds the legitimate action.
  - INDICES, NOT MARKERS, IN DIGESTS [RT-A9]. A digest lists many acts; if each
    carried a ``·pid·`` the binder's last-marker rule would bind the wrong one.
    So digest ACTED lines carry a numeric UNDO INDEX (``undo 3``) that the binder
    resolves through the ``cabinet:digest:<date>`` manifest re-checked against
    the ``cabinet:undo:<pid>`` pointer; digest lines carry NO ``·`` at all.
  - EXACT CONTENT, FAITHFULLY TRUNCATED [RT-A3]. Every acted line renders the
    exact written title/body/brief — the inspectable unit colleagues will see —
    truncated only with a visible "…(+N chars)" elision, never summarized. The
    Captain undoes/confirms what actually landed, not a paraphrase.

Stdlib-only. ``from __future__ import annotations`` + typing imports keep it
importable under both the system 3.9.6 interpreter (neighbouring modules) and
the 3.12 the suite runs on. The only cross-module import is the marker-hygiene
pair from the proposer lane — the single source of that stripping logic.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# The ONE source of the pid-marker stripping (SEC-4). We import rather than
# re-implement so this surface and the proposer card can never diverge on what
# "strip an injected marker" means.
from framework.acting.action_lane import _no_marker, _no_marker_deep

__all__ = [
    "receipt",
    "render_receipt",
    "build_digest",
    "digest_manifest",
    "instant_tell_rules",
    "overflow_micro_digest",
    "should_quiet",
]

# --- tuning constants --------------------------------------------------------

# A calendar event landing inside this window bypasses the digest for a now-tell
# (instant-tell rule 2) — the Captain should never be surprised by an imminent
# event an act just created.
INSTANT_CALENDAR_H = 6
# Overflow floor: once this many acts have gone untold since the last digest, a
# compact interim fires so the backlog never silently piles up (rule §3.4).
OVERFLOW_MIN = 3
# RT-B8: a graduated cell quiets to the weekly rollup ONLY after this many HUMAN
# verdicts, ALL confirmed — one tap can never buy silence.
QUIET_MIN_CONFIRMED = 3
# Per-value faithful-truncation cap (mirrors action_lane._CARD_VALUE_CAP): the
# render is exact, only marking how much was elided.
_VALUE_CAP = 400

# step-kind → the human verb the receipt/digest headline leads with.
_ACT_VERB: Dict[str, str] = {
    "monday_task_create": "Created task",
    "monday_task_update": "Updated task",
    "reminder_create": "Scheduled event",
    "calendar_event_create": "Scheduled event",
    "delegate_work": "Dispatched work",
    "investigation_run": "Ran investigation",
}

# The human-content fields of a payload / content dict, in render order. Anything
# not here (board_id, monday_id, _cid, *_column, list, …) is structural — it
# feeds the headline target, never a content line.
_TEXT_FIELDS = (
    ("title", "title"),
    ("name", "title"),
    ("item_name", "title"),
    ("subject", "subject"),
    ("body", "body"),
    ("description", "body"),
    ("brief", "brief"),
    ("message", "message"),
    ("notes", "notes"),
    ("why", "why"),
)
# Event-time keys probed (in order) for the "<6h out" instant rule + the "when:"
# content line.
_WHEN_KEYS = ("due_iso", "start_iso", "start", "when", "due", "event_start")

_ALERT_HEADS: Dict[str, str] = {
    "failure": "⚠ Action / reversal FAILED — manual cleanup may be needed",
    "freeze": "❄️ Act-first kind FROZEN",
    "tripwire": "🚨 Tripwire fired",
}


# --- time helpers (parse the injected `now`; never read the clock) -----------

def _parse_iso(value: Any) -> Optional[datetime]:
    """Parse an injected ISO-8601 timestamp (``...Z`` or ``+00:00``) or accept a
    datetime as-is. Returns a tz-aware UTC datetime, or None if unparseable —
    the pure core NEVER falls back to the wall clock on a parse miss."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    txt = value.strip()
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        try:
            dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _hours_between(start: Any, end: Any) -> Optional[float]:
    """(end - start) in hours, or None if either endpoint is missing/unparseable."""
    a = _parse_iso(start)
    b = _parse_iso(end)
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 3600.0


def _fmt_stamp(now: Any) -> str:
    dt = _parse_iso(now)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


# --- faithful, marker-safe content rendering ---------------------------------

def _clip(s: Optional[str], cap: int = _VALUE_CAP) -> str:
    s = s or ""
    return s if len(s) <= cap else s[:cap] + f"…(+{len(s) - cap} chars)"


def _truncate_deep(obj: Any, cap: int) -> Any:
    """Faithfully truncate long strings anywhere in a structure (mirrors
    action_lane._truncate_deep) so a rendered payload is exact, not summarized."""
    if isinstance(obj, str):
        return obj if len(obj) <= cap else obj[:cap] + f"…(+{len(obj) - cap} chars)"
    if isinstance(obj, dict):
        return {k: _truncate_deep(v, cap) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_truncate_deep(v, cap) for v in obj]
    return obj


def _json_clip(obj: Any) -> str:
    """A compact, marker-stripped, per-value-truncated JSON line for a structured
    value (e.g. a Monday ``set`` map) — exact, never a summary [RT-A3]."""
    clean = _truncate_deep(_no_marker_deep(obj), _VALUE_CAP)
    try:
        return json.dumps(clean, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return "{}"


def _as_text(v: Any) -> str:
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(v)


def _render_fields(d: Dict[str, Any]) -> str:
    """Render the human-content fields of a payload/content dict as ``  k: v``
    lines — every value marker-stripped and clipped. If no known field is
    present, the whole dict is dumped faithfully (still marker-safe) rather than
    dropped, so nothing a colleague will see goes unrendered."""
    lines: List[str] = []
    for key, label in _TEXT_FIELDS:
        val = d.get(key)
        if val in (None, "", {}, []):
            continue
        lines.append(f"  {label}: {_clip(_no_marker(_as_text(val)))}")
    setmap = d.get("set")
    if isinstance(setmap, (dict, list)) and setmap:
        lines.append(f"  set: {_json_clip(setmap)}")
    for wk in _WHEN_KEYS:
        if d.get(wk):
            lines.append(f"  when: {_clip(_no_marker(str(d[wk])))}")
            break
    if d.get("officer"):
        lines.append(f"  to: {_clip(_no_marker(str(d['officer'])))}")
    if not lines:
        return f"  {_json_clip(d)}"
    return "\n".join(lines)


def _render_content(row: Dict[str, Any]) -> str:
    """The exact written content of an acted row [RT-A3], in precedence:
    an explicit ``content`` (the orchestrator's captured title/body/brief), else
    the executed ``payload``, else the ``subject`` + a compact ``created`` id
    summary. Everything is marker-stripped before rendering."""
    content = row.get("content")
    if isinstance(content, dict) and content:
        return _render_fields(content)
    if isinstance(content, str) and content.strip():
        return f"  {_clip(_no_marker(content))}"
    payload = row.get("payload")
    if isinstance(payload, dict) and payload:
        return _render_fields(payload)
    lines: List[str] = []
    subj = _no_marker(str(row.get("subject") or "")).strip()
    if subj:
        lines.append(f"  {_clip(subj)}")
    created = _compact_created(row.get("created"))
    if created:
        lines.append(f"  {created}")
    return "\n".join(lines) if lines else "  (no content captured)"


def _compact_created(created: Any) -> str:
    if not isinstance(created, dict) or not created:
        return ""
    parts: List[str] = []
    if created.get("monday_id"):
        parts.append(f"item {_no_marker(str(created['monday_id']))}")
    if created.get("uid"):
        parts.append(f"event {_no_marker(str(created['uid']))}")
    if created.get("update_id") or created.get("note_update_id"):
        parts.append("note")
    return ", ".join(parts)


def _target_of(row: Dict[str, Any]) -> str:
    """The backend target for the headline (board / calendar / officer) — read
    from created ids first, then payload/content. Marker-stripped by the caller."""
    def _d(k: str) -> Dict[str, Any]:
        v = row.get(k)
        return v if isinstance(v, dict) else {}
    created, payload, content = _d("created"), _d("payload"), _d("content")
    kind = row.get("kind") or ""
    if kind in ("monday_task_create", "monday_task_update"):
        board = created.get("board_id") or payload.get("board_id") or content.get("board_id")
        item = created.get("monday_id") or payload.get("monday_id")
        if kind == "monday_task_update" and item:
            return f"item {item}" + (f" on board {board}" if board else "")
        return f"on board {board}" if board else ""
    if kind in ("reminder_create", "calendar_event_create"):
        cal = created.get("calendar") or payload.get("list") or content.get("calendar")
        return f"in {cal}" if cal else ""
    if kind == "delegate_work":
        off = payload.get("officer") or content.get("officer") or created.get("officer")
        return f"→ {off}" if off else ""
    return ""


def _headline(row: Dict[str, Any]) -> str:
    verb = _ACT_VERB.get(row.get("kind") or "", "Acted")
    tgt = _target_of(row)
    return _no_marker(verb + (f" {tgt}" if tgt else ""))


def _receipt_head(row: Dict[str, Any]) -> str:
    # No "·" separator here — that char is reserved for the trusted pid marker.
    at = _no_marker(str(row.get("action_type") or row.get("kind") or "action"))
    lane = row.get("lane")
    return f"✅ Acted — {at}" + (f" ({_no_marker(str(lane))})" if lane else "")


def _window(row: Dict[str, Any], now: Any) -> str:
    hrs = _hours_between(now, row.get("ttl_expires_at"))
    if hrs is None or hrs <= 0:
        return "48h"
    return f"{int(hrs)}h"


def _undo_line(row: Dict[str, Any], now: Any, *, alert: bool = False) -> str:
    # NB: the U+00B7 "·" char is the pid-marker char and is reserved for the ONE
    # trusted pid appended last — it must NEVER appear as decorative punctuation,
    # or a pair of them would forge a bindable `·…·` marker in the output.
    if alert:
        return "⚠ Needs your attention — reply here."
    return f"⏱ Undo within {_window(row, now)} — reply `undo`, or 👍 to confirm"


# --- instant-tell decision (rule §3.3, the 5 bypass cases) -------------------

def _is_calendar(row: Dict[str, Any]) -> bool:
    return (row.get("action_type") == "calendar_event_create"
            or row.get("kind") in ("reminder_create", "calendar_event_create"))


def _event_start(row: Dict[str, Any]) -> Any:
    for src in (row.get("content"), row.get("payload"), row.get("created")):
        if isinstance(src, dict):
            for k in _WHEN_KEYS:
                if src.get(k):
                    return src[k]
    return row.get("event_start") or row.get("due_iso")


def _is_dispatch(row: Dict[str, Any]) -> bool:
    return (row.get("kind") == "delegate_work"
            or row.get("action_type") == "officer_dispatch"
            or bool(row.get("dispatch")))


def _failure_kind(row: Dict[str, Any]) -> Optional[str]:
    """The alert class of a row (``failure`` / ``freeze`` / ``tripwire``) or None —
    read from an explicit ``event`` marker, the reversal status, or a flag."""
    ev = str(row.get("event") or "").lower()
    if ev in ("freeze", "frozen"):
        return "freeze"
    if ev == "tripwire":
        return "tripwire"
    if ev in ("failure", "failed"):
        return "failure"
    if row.get("status") == "reversal_failed":
        return "failure"
    if row.get("frozen") or row.get("freeze"):
        return "freeze"
    if row.get("tripwire"):
        return "tripwire"
    if row.get("failed") or row.get("failure"):
        return "failure"
    return None


def instant_tell_rules(acted_row: Dict[str, Any], *, now: Any = None) -> bool:
    """True iff this act must be told NOW instead of riding the next digest — the
    5 cases (grand-plan §3 L4): (1) ``ping-now`` urgency, (2) a calendar event
    landing inside ``INSTANT_CALENDAR_H`` of ``now``, (3) a delegate/dispatch
    notice, (4) a failure / tripwire / freeze, (5) the first-ever act of a cell.
    ``now`` is the frozen wall clock; the time-based rule (2) is skipped when it
    is absent, the flag-based rules still apply."""
    row = acted_row or {}
    if not isinstance(row, dict):
        return False
    if str(row.get("urgency") or "").lower() == "ping-now":
        return True
    if _is_calendar(row):
        hrs = _hours_between(now, _event_start(row))
        if hrs is not None and hrs < INSTANT_CALENDAR_H:
            return True
    if _is_dispatch(row):
        return True
    if _failure_kind(row):
        return True
    if row.get("first_ever_cell") is True or row.get("first_ever") is True:
        return True
    return False


# --- single act-then-tell receipt --------------------------------------------

def render_receipt(acted_row: Dict[str, Any], *, now: Any = None) -> str:
    """The receipt STRING for one acted row (always renders — the gating lives in
    ``receipt``). Layout: a head, the exact written content, an undo line, then
    the ONE real ``·pid·`` marker LAST — appended only after every content string
    has been marker-stripped, so the binder binds the legitimate action."""
    if not isinstance(acted_row, dict) or not acted_row:
        return ""
    row = acted_row
    pid = str(row.get("pid") or "").strip()
    alert = _failure_kind(row)
    body = _render_content(row)
    if alert:
        detail = _clip(_no_marker(str(row.get("reason") or row.get("detail") or "")))
        parts = [_ALERT_HEADS.get(alert, "⚠ Alert"),
                 (_headline(row) if row.get("kind") else ""),
                 body, detail, _undo_line(row, now, alert=True)]
    else:
        parts = [_receipt_head(row), _headline(row) + ":", body,
                 _undo_line(row, now)]
    text = "\n".join(p for p in parts if p)
    if pid:
        text = text + "\n·" + pid + "·"     # the ONE trusted marker, last
    return text


def receipt(acted_row: Dict[str, Any], *, now: Any = None) -> str:
    """The single act-then-tell receipt, or "" for a batch-eligible act.

    An act is told instantly only when ``instant_tell_rules`` fires; otherwise it
    is batch-eligible and rides the next digest (this returns ""). A synthetic
    canary act (``canary:true``, journal-only, zero ledger) is NEVER told —
    telling it would leak the guard's own probe traffic to the Captain."""
    row = acted_row or {}
    if not isinstance(row, dict) or row.get("canary"):
        return ""
    if not instant_tell_rules(row, now=now):
        return ""
    return render_receipt(row, now=now)


# --- daily digest ------------------------------------------------------------

def digest_manifest(acted_rows: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """The index→pid map for the ACTED section's undo-by-index grammar. Numbered
    over the LOUD rows only (quiet rows are folded to the weekly rollup and carry
    no index), 1..N, matching ``_acted_section``. The orchestrator persists this
    as the ``cabinet:digest:<date>`` manifest the binder re-checks against
    ``cabinet:undo:<pid>`` [RT-A9]."""
    out: List[Dict[str, Any]] = []
    loud = [r for r in (acted_rows or []) if r and not r.get("quiet")]
    for i, r in enumerate(loud, 1):
        out.append({"index": i, "pid": str(r.get("pid") or ""),
                    "jid": str(r.get("jid") or "")})
    return out


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.split("\n"))


def _acted_section(rows: List[Dict[str, Any]], *, now: Any) -> str:
    loud = [r for r in rows if r and not r.get("quiet")]
    quiet = [r for r in rows if r and r.get("quiet")]
    if not loud and not quiet:
        return ""
    lines = [f"✅ ACTED ({len(loud)})"]
    for i, r in enumerate(loud, 1):
        content = _indent(_render_content(r), "    ")
        lines.append(
            f" {i}. {_headline(r)}\n{content}\n"
            f"      undo: `undo {i}` ({_window(r, now)} left)")
    if quiet:
        n = len(quiet)
        lines.append(f" 🔁 {n} graduated-cell act{'s' if n != 1 else ''} "
                     "folded to the weekly rollup")
    return "\n".join(lines)


def _age_suffix(ts: Any, now: Any) -> str:
    hrs = _hours_between(ts, now)
    if hrs is None or hrs < 0:
        return ""
    if hrs < 1:
        return f" — pending {int(hrs * 60)}m"
    if hrs < 48:
        return f" — pending {int(hrs)}h"
    return f" — pending {int(hrs / 24)}d"


def _awaiting_section(rows: List[Dict[str, Any]], *, now: Any) -> str:
    if not rows:
        return ""
    lines = [f"⚡ AWAITING ({len(rows)})"]
    for r in rows:
        r = r or {}
        lane = _no_marker(str(r.get("lane") or "—"))
        subj = _clip(_no_marker(str(r.get("subject") or r.get("action") or "(proposal)")))
        lines.append(f" • [{lane}] {subj}{_age_suffix(r.get('ts'), now)}")
    return "\n".join(lines)


def _watching_section(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    lines = [f"👁 WATCHING ({len(rows)})"]
    for r in rows:
        r = r or {}
        title = _clip(_no_marker(str(
            r.get("title") or r.get("summary") or r.get("text") or "(item)")))
        src = r.get("source") or r.get("kind")
        lines.append(f" • {title}" + (f"  [{_no_marker(str(src))}]" if src else ""))
    return "\n".join(lines)


def _self_line(r: Dict[str, Any]) -> str:
    t = str(r.get("type") or "").lower()
    kind = _no_marker(str(r.get("kind") or r.get("action_type") or "")).strip() or "kind"
    detail = _clip(_no_marker(str(
        r.get("reason") or r.get("detail") or "")))
    tail = f" — {detail}" if detail else ""
    if t == "frozen" or r.get("frozen"):
        return f"❄️ {kind} frozen{tail}"
    if t == "breaker":
        return f"🚫 breaker: {kind}{tail}"
    if t == "canary":
        return f"🐤 canary {kind}: {_no_marker(str(r.get('status') or '?'))}"
    if t in ("silence", "silenced"):
        return f"🤫 {kind} silenced{tail}"
    return _clip(_no_marker(str(
        r.get("text") or r.get("label") or r.get("summary") or "(self-state)")))


def _self_section(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    lines = [f"🫀 SELF ({len(rows)})"]
    for r in rows:
        lines.append(" • " + _self_line(r or {}))
    return "\n".join(lines)


def _digest_footer() -> str:
    # No "·" anywhere here — it is reserved for the trusted pid marker (see
    # _undo_line); decorative dots would forge a bindable marker in the digest.
    return ("Per ACTED line: `undo <n>` reverses / `👍 <n>` confirms / "
            "`never: <why>` vetoes. Silence is fine — nothing waits on you.")


def build_digest(acted_rows: Optional[List[Dict[str, Any]]],
                 awaiting_rows: Optional[List[Dict[str, Any]]],
                 watching_rows: Optional[List[Dict[str, Any]]],
                 self_rows: Optional[List[Dict[str, Any]]],
                 *, now: Any) -> str:
    """The act-then-tell digest that rides the 07:30 + 19:30 briefings. Four
    sections — ✅ACTED (numbered, exact content + undo index), ⚡AWAITING
    (propose-class cards still pending a verdict), 👁WATCHING (scouted
    opportunities/health not yet carded), 🫀SELF (frozen kinds, breaker trips,
    canary status). Empty sections are omitted; an all-empty digest returns ""
    (silence costs nothing). Rows flagged ``quiet`` (a graduated, all-confirmed
    cell per ``should_quiet``) are folded to a one-line rollup rather than listed.
    The digest carries NO ``·`` marker — the Captain acts by index [RT-A9]."""
    sections = [
        _acted_section(acted_rows or [], now=now),
        _awaiting_section(awaiting_rows or [], now=now),
        _watching_section(watching_rows or []),
        _self_section(self_rows or []),
    ]
    sections = [s for s in sections if s]
    if not sections:
        return ""
    stamp = _fmt_stamp(now)
    header = "🗒 Act-then-tell digest" + (f" — {stamp}" if stamp else "")
    return "\n\n".join([header] + sections + [_digest_footer()])


# --- overflow micro-digest (rule §3.4) ---------------------------------------

def overflow_micro_digest(untold_rows: Optional[List[Dict[str, Any]]],
                          *, now: Any) -> str:
    """A compact interim emitted ONLY when ≥``OVERFLOW_MIN`` acts have gone untold
    since the last digest — one headline line per act (full content still rides
    the next digest), numbered so the same undo-by-index grammar works. Fewer
    than the floor returns "" (the acts keep waiting for the scheduled digest)."""
    rows = [r for r in (untold_rows or []) if r and not r.get("quiet")]
    if len(rows) < OVERFLOW_MIN:
        return ""
    lines = [f"📨 {len(rows)} acts since the last briefing "
             "(full detail rides the next digest):"]
    for i, r in enumerate(rows, 1):
        lines.append(f" {i}. {_headline(r)} — undo: `undo {i}`")
    lines.append("Reply `undo <n>` to reverse, or `👍 <n>` to confirm.")
    return "\n".join(lines)


# --- cell-quieting predicate (RT-B8) -----------------------------------------

def should_quiet(cell_stats: Optional[Dict[str, Any]]) -> bool:
    """RT-B8: a cell's acts collapse to the weekly rollup ONLY when the cell is
    graduated AND has ≥``QUIET_MIN_CONFIRMED`` HUMAN verdicts, ALL confirmed —
    one 👍 cannot buy silence, and a single human ``wrong`` keeps it loud.

    ``cell_stats`` carries the graduation ``state`` (or a ``graduated`` bool) and
    the human-verdict counts (``human_confirmed`` + ``human_wrong``; a
    ``human_verdicts`` total is honored when present). Machine (verdict_judge)
    verdicts never count here — quieting is fueled only by the Captain's taps,
    exactly as promotion is (flavor-A)."""
    s = cell_stats or {}
    graduated = (s.get("state") == "graduated") or (s.get("graduated") is True)
    if not graduated:
        return False
    confirmed = int(s.get("human_confirmed") or 0)
    if confirmed < QUIET_MIN_CONFIRMED:
        return False
    if "human_verdicts" in s:
        return confirmed == int(s.get("human_verdicts") or 0)
    return int(s.get("human_wrong") or 0) == 0


# --- production reader (the ONE impure seam — never used by the formatters) ---

def read_recent_acted(*, since: Optional[str] = None,
                      limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """THIN production reader — the single impure seam, kept out of the pure core
    (the formatters above take injected rows only). Pulls committed acted journal
    rows for a live tell; does NO formatting and NO enrichment (the orchestrator
    joins content/context and computes first_ever_cell/quiet before calling the
    formatters). Lazy-imports the journal owner; never exercised by the tests."""
    from framework.frontdoor import action_undo
    rows = [r for r in action_undo._read_journal()
            if r.get("status") == "executed" and r.get("executed_at")]
    if since is not None:
        rows = [r for r in rows if str(r.get("ts") or "") >= since]
    rows.sort(key=lambda r: r.get("ts", ""))
    if limit:
        rows = rows[-int(limit):]
    return rows
