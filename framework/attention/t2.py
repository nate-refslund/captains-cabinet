"""framework.attention.t2 — Chair-live judgment (attention-gateway P5, §4.6).

The mechanical gate (gate.py) routes routine traffic; EXCEPTIONAL items —
ping-now, act-carrying, novel class, low confidence, unclassified — are handed
to the Chair for a live judgment. This module is the plumbing around that:

- ``assemble_dossier`` — the compact context the Chair judges on (candidate
  content, situation history, recent feed rows, matching Captain patterns/
  intents, charter class, taint provenance). Pure + fail-soft: absent ledgers
  read empty, never crash.
- ``file_judgment_request`` — stores a pending request (dossier + SLA deadline)
  and fires a Redis trigger to ``cos`` carrying only the request id (a pointer,
  never the dossier). The Chair picks it up on its next turn.
- ``apply_verdict`` — the Chair's callback: send / edit-standing / merge /
  fold-to-briefing / suppress / escalate, with the Chair's AUTHORED text. The
  request is consumed and the outcome journaled.
- ``sweep_expired`` — the SLA fallback the surface service runs each drain: a
  past-deadline FLOOR request sends its mechanical render marked
  ``(chair-offline)`` (the channel never goes dark for a floor item); a
  non-floor one HOLDS to the briefing (never a spam send). Idempotent — a
  consumed request is gone, so no double-send.

Chair-down is therefore always safe: it neither spams nor silences. The Chair's
actual REASONING is prompt-side (``t2-rubric.md`` + the Chair session); this
module carries no LLM call.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from framework import env  # roster-resolved judgment recipient


def _attention_dir() -> Path:
    return Path(os.environ.get("CABINET_ATTENTION_DIR") or
                os.path.expanduser("~/Library/Application Support/cabinet/attention"))


def _requests_dir() -> Path:
    return _attention_dir() / "t2-requests"


def _utc(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# The versioned rubric (framework artifact; the charter may EXTEND, not delete)
# ---------------------------------------------------------------------------

_RUBRIC_FILE = Path(__file__).with_name("t2-rubric.md")


def _rubric_version() -> int:
    try:
        head = _RUBRIC_FILE.read_text(encoding="utf-8")[:200]
        m = re.search(r"T2-RUBRIC-VERSION:\s*(\d+)", head)
        return int(m.group(1)) if m else 1
    except OSError:
        return 1


RUBRIC_VERSION = _rubric_version()


def load_rubric() -> str:
    """The T2 self-review system-prompt core (new/true/valuable/terse/
    well-timed/already-answered). Framework-versioned."""
    try:
        return _RUBRIC_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Dossier
# ---------------------------------------------------------------------------

def _read_ledger_text(name: str) -> str:
    """A captain-law ledger's text, fail-soft (absent on a fresh box → '')."""
    from framework import env
    p = env._cabinet_root() / "shared/interfaces" / name
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def _standing_rules(text: str, cap: int = 12) -> str:
    """Captain patterns/intents are SHORT standing behavioral rules the Chair
    always needs (not situation-specific) — surface the first ``cap`` content
    lines (skip blanks + markdown comments/headers). Fail-soft on ''."""
    if not text:
        return ""
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith(("#", "<!--", "-->", "---", "|")):
            continue
        out.append(ln)
        if len(out) >= cap:
            break
    return "\n".join(out)


def assemble_dossier(item: dict, decision: dict, *,
                     feed_rows: "list | None" = None,
                     patterns_text: "str | None" = None,
                     intents_text: "str | None" = None,
                     charter_section: "dict | None" = None) -> dict:
    """The compact context the Chair judges on. Pure given injected sources;
    the defaults load the real feed + ledgers fail-soft (absent → empty)."""
    skey = decision.get("situation_key") or item.get("situation_key") or ""

    if feed_rows is None:
        try:
            from framework.attention import feed
            feed_rows = feed.recent_feed(50)
        except Exception:
            feed_rows = []
    # this situation's own history within the recent feed
    situation_history = [r for r in feed_rows
                         if isinstance(r, dict) and r.get("situation_key") == skey]

    if patterns_text is None:
        patterns_text = _read_ledger_text("captain-patterns.md")
    if intents_text is None:
        intents_text = _read_ledger_text("captain-intents.md")

    return {
        "situation_key": skey,
        "class_id": decision.get("class_id") or "",
        "candidate_text": decision.get("text") or "",
        "reason": decision.get("reason") or "",
        "feed_rows": list(feed_rows or []),
        "situation_history": situation_history,
        "patterns": _standing_rules(patterns_text),
        "intents": _standing_rules(intents_text),
        "charter_section": dict(charter_section or {}),
        "taint": {"injection_suspect": bool(item.get("injection_suspect"))},
        "rubric_version": RUBRIC_VERSION,
    }


# ---------------------------------------------------------------------------
# File a judgment request + fire the trigger
# ---------------------------------------------------------------------------

def _default_trigger(officer: str, message: str) -> None:
    """Fire a Redis trigger to an officer via notify-officer.sh (best-effort —
    a missing redis/tmux must not crash the gate; the request still persists,
    so the Chair finds it on its next drain regardless of the wake)."""
    from framework import env
    script = env._cabinet_root() / "cabinet/scripts/notify-officer.sh"
    try:
        subprocess.run(["bash", str(script), officer, message],
                       capture_output=True, timeout=15)
    except Exception as e:  # noqa: BLE001 — trigger is a nicety, never a blocker
        print(f"[t2] trigger to {officer} failed ({e}) — request still queued",
              file=sys.stderr)


def file_judgment_request(item: dict, decision: dict, dossier: dict, *,
                          sla_minutes: int, now: datetime,
                          fallback: str = "hold-briefing", floor: bool = False,
                          trigger_fn=None) -> str:
    """Persist a pending T2 request (dossier + deadline) and wake the Chair.
    Returns the request id. The trigger carries only the id — the dossier stays
    on disk (too big for a trigger message, and it is the Captain's private
    context)."""
    rid = "t2-" + uuid.uuid4().hex[:12]
    deadline = _utc(now + timedelta(minutes=int(sla_minutes)))
    record = {
        "request_id": rid,
        "situation_key": decision.get("situation_key") or "",
        "class_id": decision.get("class_id") or "",
        "filed_at": _utc(now),
        "deadline": deadline,
        "fallback": fallback,
        "floor": bool(floor),
        "item": item,
        "decision": decision,
        "dossier": dossier,
    }
    d = _requests_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (rid + ".json.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, default=str),
                   encoding="utf-8")
    os.replace(tmp, d / (rid + ".json"))

    trig = trigger_fn or _default_trigger
    trig(env.chair_officer(), f"⚖️ T2 judgment needed: {rid} "
                f"(class={record['class_id']}, deadline={deadline}) — "
                f"read framework.attention.t2.load_request('{rid}')")
    return rid


def pending_requests() -> list:
    """All open T2 requests (unread garbage lines skipped)."""
    d = _requests_dir()
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("t2-*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def load_request(rid: str) -> "dict | None":
    try:
        p = _requests_dir() / (_safe_rid(rid) + ".json")
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None   # absent, corrupt, OR malformed id → safe no-op upstream


def _safe_rid(rid: str) -> str:
    """Path-traversal fence: a request id is our own minted token shape."""
    if not re.fullmatch(r"t2-[0-9a-f]{6,}", str(rid or "")):
        raise ValueError(f"illegal request id {rid!r}")
    return rid


def _consume(rid: str) -> None:
    try:
        (_requests_dir() / (_safe_rid(rid) + ".json")).unlink()
    except (OSError, ValueError):
        pass


# ---------------------------------------------------------------------------
# Apply a Chair verdict (the callback)
# ---------------------------------------------------------------------------

_VERDICTS = {"send", "edit-standing", "merge", "fold-to-briefing", "suppress",
             "escalate"}


def apply_verdict(request_id: str, verdict: str, text: str = "", *,
                  gate_deliver=None, briefing_fn=None, now=None) -> dict:
    """The Chair's callback. Applies its verdict + AUTHORED text, consumes the
    request, and journals the outcome. An unknown request is a safe no-op (it
    already expired/was handled)."""
    req = load_request(request_id)
    if req is None:
        return {"applied": "unknown-request"}
    v = verdict if verdict in _VERDICTS else "suppress"
    skey = req.get("situation_key") or ""
    cid = req.get("class_id") or ""
    gate_deliver = gate_deliver or _default_gate_deliver
    briefing_fn = briefing_fn or _default_briefing_fn

    # send / edit-standing / merge / escalate all DELIVER the Chair's authored
    # text — escalate IS a send (the ask to the Captain the Chair could not
    # resolve; review cp5-gauntlet: it must surface, not just journal).
    if v in ("send", "edit-standing", "merge", "escalate"):
        decision = {"situation_key": skey, "class_id": cid, "text": text,
                    "silent": req.get("decision", {}).get("silent", False),
                    "action": "edit" if v == "edit-standing" else "send",
                    "reason": f"chair-{v}"}
        try:
            gate_deliver(decision, chair_authored=True)
        except Exception as e:  # noqa: BLE001 — journal the gap, never crash the callback
            print(f"[t2] verdict delivery failed for {request_id} ({e})", file=sys.stderr)
    elif v == "fold-to-briefing":
        item = req.get("item") or {}
        try:
            briefing_fn(item, {"situation_key": skey, "class_id": cid,
                               "text": text or req.get("decision", {}).get("text", "")})
        except Exception as e:  # noqa: BLE001
            print(f"[t2] verdict briefing failed for {request_id} ({e})", file=sys.stderr)
    # suppress: nothing sent (a journaled record of the Chair's call).

    # Journal BEFORE consume so a crash mid-consume never loses the audit.
    _journal_t2(request_id, skey, cid, f"verdict-{v}", now=now)
    _consume(request_id)
    return {"applied": v, "situation_key": skey}


# ---------------------------------------------------------------------------
# Default delivery — so a no-arg caller (the surface service) ACTUALLY delivers
# ---------------------------------------------------------------------------
# (review cp5-gauntlet CRITICAL): surface.py calls sweep_expired(now) with no
# fns. Without an internal default, a floor page past SLA was journaled
# "fallback-sent" and consumed while NOTHING sent — the channel went dark for
# the one class that must never go dark. These mirror gate.deliver's defaults
# so the real production path delivers; both fail-soft (delivery error →
# reported, request left for the next sweep, never a false success).

def _default_gate_deliver(decision: dict, **kw):
    from framework.attention import gate
    return gate.deliver(decision)


def _default_briefing_fn(item: dict, decision: dict):
    from framework.attention import gate
    return gate._default_briefing(item, decision)


def _delivered_ok(res) -> bool:
    """A delivery result counts as success when it says so; None/empty (a
    stub or a swallowed error) does NOT — we never journal a send that may
    not have happened."""
    if isinstance(res, dict):
        return bool(res.get("sent") or res.get("status") in ("sent", "noop"))
    return res is True


# ---------------------------------------------------------------------------
# SLA sweep / fallback (the surface service runs this each drain)
# ---------------------------------------------------------------------------

def _mechanical_marker(text: str) -> str:
    return f"{text}\n(chair-offline)" if text else "(chair-offline)"


_DEADLINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _is_due(deadline, now_iso: str) -> bool:
    """A request is due when its deadline is at/before now. A MALFORMED or
    absent deadline is treated as DUE (review cp5-gauntlet): a garbage string
    that sorts after ``now`` would otherwise make the request immortal — a
    stuck floor page. Fail toward sweeping, never toward a wedged request."""
    d = str(deadline or "")
    if not _DEADLINE_RE.match(d):
        return True                      # malformed/absent → expire it
    return d <= now_iso                  # well-formed: lexicographic == chronological


def sweep_expired(now: datetime, *, gate_deliver=None, briefing_fn=None) -> list:
    """For every pending request past its deadline, run the charter fallback:
    a FLOOR request sends its mechanical render marked ``(chair-offline)``; a
    non-floor one HOLDS to the briefing. Delivery defaults to the real
    gate/channel so a no-arg caller (the surface service) actually delivers.
    A request is consumed ONLY when its fallback delivered successfully — a
    failed floor send is journaled honestly and LEFT for the next sweep (never
    dropped, never a false 'sent'). Idempotent: a consumed request re-finds
    nothing, so no double-send."""
    gate_deliver = gate_deliver or _default_gate_deliver
    briefing_fn = briefing_fn or _default_briefing_fn
    now_iso = _utc(now)
    swept = []
    for req in pending_requests():
        if not _is_due(req.get("deadline"), now_iso):
            continue   # a WELL-FORMED deadline still in the future
        rid = req.get("request_id")
        skey = req.get("situation_key") or ""
        cid = req.get("class_id") or ""
        decision = dict(req.get("decision") or {})
        delivered = True
        if req.get("floor") and req.get("fallback") == "mechanical-with-marker":
            decision["text"] = _mechanical_marker(decision.get("text") or "")
            decision["action"] = "send"
            decision["reason"] = "chair-offline-floor"
            try:
                delivered = _delivered_ok(gate_deliver(decision, chair_authored=False))
            except Exception as e:  # noqa: BLE001
                delivered = False
                print(f"[t2] fallback send FAILED for {rid} ({e})", file=sys.stderr)
            outcome = "fallback-sent" if delivered else "fallback-send-failed"
        else:
            try:
                briefing_fn(req.get("item") or {}, decision)
            except Exception as e:  # noqa: BLE001
                delivered = False
                print(f"[t2] fallback briefing FAILED for {rid} ({e})", file=sys.stderr)
            outcome = "fallback-briefing" if delivered else "fallback-briefing-failed"
        _journal_t2(rid, skey, cid, outcome, now=now)
        if delivered:
            try:
                _consume(rid)
            except Exception:
                pass
        swept.append({"request_id": rid, "situation_key": skey,
                      "class_id": cid, "outcome": outcome})
    return swept


# ---------------------------------------------------------------------------
# Journaling — every T2 outcome lands on the feed (audit)
# ---------------------------------------------------------------------------

def _journal_t2(rid: str, skey: str, cid: str, outcome: str, *, now=None) -> None:
    try:
        from framework.attention import feed
        row = {"direction": "out", "kind": "t2", "situation_key": skey,
               "class_id": cid, "t2_request": rid, "t2_outcome": outcome}
        if now is not None:
            row["ts"] = _utc(now)
        feed.append_event(row)
    except Exception as e:  # noqa: BLE001 — a journal gap must be loud, not fatal
        print(f"[t2] JOURNAL-GAP: could not journal {outcome} for {rid} ({e})",
              file=sys.stderr)
