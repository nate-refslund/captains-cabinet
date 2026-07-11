"""framework.attention.verdicts — the dashboard verdict door (Ruling A).

WRITE-CLASS-2 = YES with the EQUAL-AUTHORITY-DOOR LAW (captain-decisions
2026-07-10): the dashboard may accept Captain decisions, but only as an equal
authority door — NEVER a weaker second root. Concretely:

  * The door executes NOTHING itself. A decision is composed as the org's own
    reply grammar ("approve" / "skip: …" quoted against the card's `·pid·`
    marker) and submitted through the SAME parser + wire the Captain's typed
    Telegram replies use: ``framework.frontdoor.binder_wire.handle_captain_update``.
    The door forges nothing and never counterfeits identity — it speaks the
    org's grammar through the org's gate, tagged ``source:"dashboard"``.
  * Verify-at-fire applies to the door itself: freshness is re-derived from
    the live private census (pid present · content revision match · state
    undecided · census not stale) immediately before the wire is invoked.
  * Every receipt AND every denial is one journal row on the attention feed
    (``framework.attention.feed.append_event`` — locked module, imported
    read/append API only).

"later" is deliberately NOT sent through the wire for proposal-shaped cards:
the reply router treats a non-verdict reply as policy/instruction and would
EXPIRE (close) the proposal — the opposite of "come back later". A door
"later" is a surface-level defer: journaled honestly, ledger untouched, the
card comes back at the next briefing. (Need-kind cards do have a real
``later NEED-…`` grammar; when that wiring is armed the wire handles it.)

Bridge contract (spawned by the dashboard route — fixed argv, shell=False,
JSON over stdio, 30s wall clock):
    stdin : {"op":"fire","pid":…,"verb":"approve|no|later","revision":…}
          | {"op":"journal","rows":[{phase,code,pid,verb,detail,http_status}]}
    stdout: one JSON object; "ok" is the door's truth, never optimism.

FOUNDATION module: launcher-neutral, stdlib-only at import; the wire and the
feed are imported lazily so tests inject fakes and the bridge stays cheap.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from framework.attention import plain

# Census artifact resolution — same constants as framework.attention.queue
# (_ATTENTION_DIR_ENV/_ATTENTION_DIR_DEFAULT) and the dashboard's censusPath().
_ATTENTION_DIR_ENV = "CABINET_ATTENTION_DIR"
_ATTENTION_DIR_DEFAULT = "~/Library/Application Support/cabinet/attention"

#: Census staleness bar — mirrors the dashboard reader's CENSUS_MAX_AGE_MS.
CENSUS_MAX_AGE_S = 30 * 60

VERBS = ("approve", "no", "later")

_WIRE_SKIP_TEXT = "skip: declined from the dashboard (✗ No)"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: "str | None") -> "datetime | None":
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def census_path() -> Path:
    base = os.environ.get(_ATTENTION_DIR_ENV) or os.path.expanduser(
        _ATTENTION_DIR_DEFAULT)
    return Path(base) / "queue.json"


# ---------------------------------------------------------------------------
# Revision — a cross-language CONTENT fingerprint of the card (the census
# does not carry a revision counter; content is the honest clock). The
# dashboard computes the identical hash in TypeScript (golden-vector pinned).
# ---------------------------------------------------------------------------


def revision_of(row: dict) -> str:
    parts = [str(row.get(k) or "") for k in ("pid", "state", "what",
                                             "deadline_iso")]
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


# ---------------------------------------------------------------------------
# Freshness (verify-at-fire, applied to the door itself — spec §1.2d)
# ---------------------------------------------------------------------------


def read_census(path: "Path | None" = None, *,
                now: "datetime | None" = None) -> "dict | None":
    """The private census, or None when absent/unreadable/stale — the door
    fails CLOSED on a census it cannot prove fresh."""
    p = path or census_path()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict):
        return None
    gen = _parse_iso(doc.get("generated_at"))
    if gen is None:
        return None
    if ((now or _now()) - gen).total_seconds() > CENSUS_MAX_AGE_S:
        return None
    return doc


def _rows(census: dict) -> list[dict]:
    out: list[dict] = []
    for shelf in ("decisions", "directions"):
        v = census.get(shelf)
        if isinstance(v, list):
            out.extend(r for r in v if isinstance(r, dict))
    return out


def fresh_row(pid: str, revision: str, *,
              census: "dict | None" = None,
              now: "datetime | None" = None) -> "tuple[dict | None, str, dict | None]":
    """(row, code, refreshed) — code is 'ok' or the denial code.

    refreshed carries the CURRENT row (for the 409 payload) when the card
    still exists but no longer matches what the Captain saw."""
    doc = census if census is not None else read_census(now=now)
    if doc is None:
        return None, "stale_census", None
    row = next((r for r in _rows(doc) if r.get("pid") == pid), None)
    if row is None:
        return None, "gone", None
    if str(row.get("state") or "") in plain.DECIDED_STATES:
        return None, "decided", row
    if revision_of(row) != revision:
        return None, "stale", row
    return row, "ok", None


# ---------------------------------------------------------------------------
# Verb legality — census one_tap semantics decide what the door may accept.
# ---------------------------------------------------------------------------


def verb_allowed(row: dict, verb: str) -> "tuple[bool, str]":
    """(allowed, code). Ritual sign-offs (germline-handback /
    outcome-ratification) are REFUSED via the door by design."""
    if verb not in VERBS:
        return False, "bad_verb"
    tap = row.get("one_tap")
    if not isinstance(tap, dict) or not tap:
        return False, "not_here"
    if verb == "approve":
        sem = tap.get("approve")
        if sem == "ritual-print" or str(row.get("kind") or "") in plain.RITUAL_KINDS:
            return False, "ritual"
        return (sem in ("direct", "per-item-approval"), "bad_verb")
    if verb == "no":
        return (tap.get("veto") == "direct", "bad_verb")
    return (tap.get("defer") == "direct", "bad_verb")


# ---------------------------------------------------------------------------
# Canonical grammar composition — the door speaks the org's own verbs.
# ---------------------------------------------------------------------------


def canonical(verb: str, row: dict, *,
              skip_text: "str | None" = None) -> "tuple[str | None, str]":
    """(reply_text, quoted) for the wire — or (None, '') when the verb must
    NOT touch the wire (proposal-card 'later': see module docstring).
    ``skip_text`` lets an equal-authority caller that is NOT the dashboard
    (e.g. the Telegram tap door) record honest provenance in the skip reason;
    the grammar and the wire path are identical either way."""
    pid = str(row.get("pid") or "")
    kind = str(row.get("kind") or "")
    if kind == "need":
        # The needs grammar addresses the NEED id directly (no ·marker·).
        text = {"approve": f"grant {pid}", "no": f"deny {pid}",
                "later": f"later {pid}"}[verb]
        return text, ""
    if verb == "approve":
        return "approve", f"·{pid}·"
    if verb == "no":
        return skip_text or _WIRE_SKIP_TEXT, f"·{pid}·"
    return None, ""  # later: surface-level defer only — never the wire


# ---------------------------------------------------------------------------
# Journal — receipts and denials are feed rows (locked module, import-only).
# ---------------------------------------------------------------------------

_JOURNAL_FIELDS = ("phase", "code", "pid", "verb", "detail", "http_status",
                   "wire_status", "outcome")


def _default_journal(row: dict) -> dict:
    from framework.attention import feed
    return feed.append_event(row)


def journal_row(phase: str, *, journal: "Callable[[dict], dict] | None" = None,
                **fields: Any) -> "int | None":
    """One journal row per arm/fire/deny. Returns the feed seq, or None when
    the journal write failed — callers SURFACE that (never calmer than
    reality), they do not raise past it."""
    row: dict[str, Any] = {"direction": "in", "kind": "verdict",
                           "source": "dashboard", "phase": str(phase)[:24]}
    for k in _JOURNAL_FIELDS:
        if k == "phase" or fields.get(k) is None:
            continue
        v = fields[k]
        row[k] = v if isinstance(v, int) else str(v)[:300]
    try:
        stamped = (journal or _default_journal)(row)
        seq = stamped.get("seq") if isinstance(stamped, dict) else None
        return seq if isinstance(seq, int) else None
    except Exception as e:  # journal failure must be HEARD, not fatal
        print(f"[verdicts] journal write failed: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# FIRE — the full chain, fail-closed, equal authority.
# ---------------------------------------------------------------------------


def _default_wire(text: str, quoted: str) -> dict:
    from framework.frontdoor import binder_wire
    return binder_wire.handle_captain_update(
        text, quoted, log=lambda m: print(f"[verdicts] {m}", file=sys.stderr))


def _approve_result(wire_res: dict) -> str:
    delivery = wire_res.get("delivery")
    if isinstance(delivery, dict):
        if delivery.get("ok"):
            return plain.RESULTS["approved_underway"]
        return plain.RESULTS["approved_delivery_failed"]
    return plain.RESULTS["approved"]


def fire(pid: str, verb: str, revision: str, *,
         census: "dict | None" = None,
         wire: "Callable[[str, str], dict] | None" = None,
         journal: "Callable[[dict], dict] | None" = None,
         now: "datetime | None" = None,
         skip_text: "str | None" = None) -> dict:
    """Validate freshness + legality, then submit through the org's wire.

    Returns {"ok": bool, ...}; ok=False carries code + plain message (+ the
    refreshed row for stale/decided so the surface can repaint honestly)."""

    def deny(code: str, *, refreshed: "dict | None" = None,
             wire_reason: "str | None" = None) -> dict:
        seq = journal_row("deny", journal=journal, code=code, pid=pid,
                          verb=verb, detail=wire_reason)
        out: dict[str, Any] = {"ok": False, "code": code,
                               "message": plain.MESSAGES.get(
                                   code, plain.MESSAGES["bridge_fail"])}
        if seq is None:
            out["journal_warn"] = plain.MESSAGES["journal_warn"]
        if refreshed is not None:
            out["refreshed"] = {"pid": refreshed.get("pid"),
                                "state": refreshed.get("state"),
                                "revision": revision_of(refreshed),
                                "summary": plain.plain_summary(refreshed)}
        if wire_reason:
            out["wire_reason"] = wire_reason
        return out

    if verb not in VERBS:
        return deny("bad_verb")
    row, code, refreshed = fresh_row(pid, revision, census=census, now=now)
    if row is None:
        return deny(code, refreshed=refreshed)
    allowed, code = verb_allowed(row, verb)
    if not allowed:
        return deny(code)

    text, quoted = canonical(verb, row, skip_text=skip_text)

    if text is None:
        # Surface-level defer (proposal-card "later") — ledger untouched.
        seq = journal_row("fire", journal=journal, pid=pid, verb=verb,
                          outcome="deferred")
        out = {"ok": True, "receipt_seq": seq, "deferred": True,
               "plain_result": plain.RESULTS["deferred"]}
        if seq is None:
            out["journal_warn"] = plain.MESSAGES["journal_warn"]
        return out

    try:
        wire_res = (wire or _default_wire)(text, quoted)
    except Exception as e:
        return deny("bridge_fail", wire_reason=str(e)[:200])
    if not isinstance(wire_res, dict):
        return deny("bridge_fail", wire_reason="wire returned non-dict")

    if not wire_res.get("handled"):
        reason = str(wire_res.get("reason") or "unhandled")
        if verb == "later":
            # Need-kind later with the needs wiring dark: journaled defer.
            seq = journal_row("fire", journal=journal, pid=pid, verb=verb,
                              outcome="deferred", detail=reason)
            out = {"ok": True, "receipt_seq": seq, "deferred": True,
                   "plain_result": plain.RESULTS["deferred"]}
            if seq is None:
                out["journal_warn"] = plain.MESSAGES["journal_warn"]
            return out
        return deny("not_here", wire_reason=reason)

    status = str(wire_res.get("status") or "")
    if status == "already-decided":
        return deny("decided")

    if verb == "approve":
        result_text = _approve_result(wire_res)
    elif verb == "no":
        result_text = (plain.RESULTS["denied"]
                       if str(row.get("kind") or "") == "need"
                       else plain.RESULTS["declined"])
    else:
        result_text = plain.RESULTS["deferred"]

    # Receipt fan-out leg (b) — editing the TG standing card to its decided
    # ✅ face — deliberately lands at the integration pass: today's comms
    # edit_card is subject-keyed dedup, and a guessed subject would mint a
    # DUPLICATE card (violating P2). Arm B's card_ref-capable edit_card is
    # the correct hook; the feed receipt below is the durable truth either
    # surface can already repaint from.
    seq = journal_row("fire", journal=journal, pid=pid, verb=verb,
                      wire_status=status or None,
                      outcome=str(wire_res.get("verdict") or status or "ok"))
    out = {"ok": True, "receipt_seq": seq, "wire_status": status,
           "plain_result": result_text}
    if seq is None:
        out["journal_warn"] = plain.MESSAGES["journal_warn"]
    return out


# ---------------------------------------------------------------------------
# Bridge main — JSON over stdio (fixed argv, no shell, 30s wall clock owned
# by the spawner; a belt-and-braces alarm here).
# ---------------------------------------------------------------------------


def _op_journal(req: dict, *, journal: "Callable[[dict], dict] | None" = None) -> dict:
    rows = req.get("rows")
    if not isinstance(rows, list):
        return {"ok": False, "code": "bad_request"}
    written, failed = 0, 0
    for r in rows[:50]:
        if not isinstance(r, dict):
            failed += 1
            continue
        seq = journal_row(str(r.get("phase") or "deny"), journal=journal,
                          **{k: r.get(k) for k in _JOURNAL_FIELDS if k != "phase"})
        if seq is None:
            failed += 1
        else:
            written += 1
    return {"ok": failed == 0, "written": written, "failed": failed}


def handle_request(req: dict, *,
                   census: "dict | None" = None,
                   wire: "Callable[[str, str], dict] | None" = None,
                   journal: "Callable[[dict], dict] | None" = None) -> dict:
    if not isinstance(req, dict):
        return {"ok": False, "code": "bad_request",
                "message": plain.MESSAGES["bad_request"]}
    op = req.get("op")
    if op == "fire":
        pid, verb, revision = req.get("pid"), req.get("verb"), req.get("revision")
        if not (isinstance(pid, str) and pid and len(pid) <= 300
                and isinstance(verb, str) and isinstance(revision, str)
                and len(revision) <= 64):
            return {"ok": False, "code": "bad_request",
                    "message": plain.MESSAGES["bad_request"]}
        return fire(pid, verb, revision, census=census, wire=wire,
                    journal=journal)
    if op == "journal":
        return _op_journal(req, journal=journal)
    return {"ok": False, "code": "bad_request",
            "message": plain.MESSAGES["bad_request"]}


def main(stdin=None, stdout=None) -> int:
    import signal

    def _timeout(_sig, _frm):  # pragma: no cover — belt and braces
        print(json.dumps({"ok": False, "code": "bridge_fail",
                          "message": plain.MESSAGES["bridge_fail"]}))
        sys.exit(3)

    # Belt-and-braces wall clock (the spawner owns the real 30s kill). The
    # alarm MUST be cancelled and the prior handler restored on every exit —
    # main() is also called in-process by tests, and a leftover alarm would
    # detonate inside whatever runs 25s later.
    prev_handler = None
    if hasattr(signal, "SIGALRM"):
        prev_handler = signal.signal(signal.SIGALRM, _timeout)
        signal.alarm(25)
    try:
        fin = stdin or sys.stdin
        fout = stdout or sys.stdout
        try:
            req = json.loads(fin.read() or "null")
        except ValueError:
            print(json.dumps({"ok": False, "code": "bad_request",
                              "message": plain.MESSAGES["bad_request"]}),
                  file=fout)
            return 2
        res = handle_request(req)
        print(json.dumps(res, ensure_ascii=False, default=str), file=fout)
        return 0 if res.get("ok") or res.get("code") else 2
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
            if prev_handler is not None:
                signal.signal(signal.SIGALRM, prev_handler)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
