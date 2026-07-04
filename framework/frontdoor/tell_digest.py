"""tell_digest.py — TI-5: the act-then-tell digest ORCHESTRATOR (impure seam).

``tell_surface`` is the PURE formatter (injected rows only, no clock, no I/O).
This module is its production counterpart — the missing wiring the 2026-07-04
checkpoint names Tier-0 #6 ("Wire TI-5 digest legs — ACTED/AWAITING/WATCHING/
SELF + manifest into composer.py/run_briefing.py; enables undo-by-index and
plugs the binder no-pid label leak — Nate's ruled flip prerequisite"). One call
per briefing run:

  1. GATHER — acted journal rows still inside their undo window (non-canary,
     not reversed/voided), pending propose-class proposals (the AWAITING leg —
     this is what plugs the no-pid leak: the Captain sees what is open instead
     of replying into a void), frozen kinds (SELF), scouted items (WATCHING —
     injectable; no default producer yet, see checkpoint PRO-2/PRO-3).
  2. INDEX — assign each acted row its STABLE ``undo_index``: an act keeps ONE
     number for its whole undo window, across every digest/manifest that renders
     it, and numbers are NEVER reused (monotonic ``next_index`` carried in the
     manifest). A renumbering digest would let a reply to an older rendered
     message ("undo 2") bind a DIFFERENT act than the line the Captain read —
     the wrong-target class the binder's manifest-or-nothing rule refuses.
  3. PERSIST the ``cabinet:digest:<date>`` manifest (48h TTL — the binder checks
     today + yesterday) BEFORE the digest text is enqueued, so an index reply
     arriving the moment the briefing lands always resolves. A manifest write
     failure ABORTS the digest (fail-closed toward no-tell: rendering handles
     that cannot bind would burn Captain taps — the exact leak this fixes).
  4. ENQUEUE the rendered digest as a ``batch`` intake item; it rides the same
     unified briefing send as every other front-door item (channel.send stays
     the ONE allow_sends-gated sender — this module never sends).

Every transport is injectable (tests run with dicts + lambdas; no Redis, no
ledger, no journal). Production defaults resolve lazily so importing is cheap.
Redis access is arg-list ``redis-cli`` subprocess only (house rule — never a
shell string). Kill-switch: ``CABINET_TELL_DIGEST=0`` skips the whole leg.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from framework.frontdoor import tell_surface

__all__ = ["enqueue_digest", "assign_undo_indexes", "gather_acted_rows",
           "gather_self_rows"]

# The binder resolves indexes via cabinet:digest:<today|yesterday>; 48h TTL
# matches both that lookback and the undo window itself.
_MANIFEST_TTL_S = 48 * 3600
_DIGEST_KEY_PREFIX = "cabinet:digest:"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _date_of(now_iso: str) -> str:
    return (now_iso or "")[:10]


def _yesterday_of(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return ""
    return (d - timedelta(days=1)).strftime("%Y-%m-%d")


def _enabled() -> bool:
    return os.environ.get("CABINET_TELL_DIGEST", "").strip() != "0"


# --- production transports (all injectable) -----------------------------------

def _default_redis_get(key: str) -> str:
    host = os.environ.get("REDIS_HOST", "localhost")
    out = subprocess.run(["redis-cli", "-h", host, "GET", key],
                         capture_output=True, text=True, timeout=10).stdout.strip()
    return "" if out in ("", "(nil)") else out


def _default_redis_set(key: str, value: str, ttl_s: int) -> None:
    """SET with TTL; raises on a non-OK reply so the caller can fail CLOSED
    (an unpersisted manifest must abort the digest, never ship dead indexes)."""
    host = os.environ.get("REDIS_HOST", "localhost")
    out = subprocess.run(
        ["redis-cli", "-h", host, "SET", key, value, "EX", str(int(ttl_s))],
        capture_output=True, text=True, timeout=10).stdout.strip()
    if out != "OK":
        raise RuntimeError(f"manifest SET {key} returned {out!r}")


def _default_enqueue(item: Dict[str, Any]) -> str:
    from framework.frontdoor import intake
    return intake.enqueue(item)


def _default_journal_rows() -> List[Dict[str, Any]]:
    from framework.frontdoor import action_undo
    return action_undo._read_journal()


def _default_pending() -> List[Dict[str, Any]]:
    from framework.acting import loop
    return loop.pending_proposals()


# --- gathers -------------------------------------------------------------------

def gather_acted_rows(*, now: str,
                      journal_rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """The acted journal rows the digest may offer an undo handle for: executed,
    non-canary, undo window still open, and NOT already reversed / failed-
    reversal / voided (the reversal journals a superseding status row for the
    same jid — its original ``executed`` row must not resurface with a dead
    handle). Sorted by execution time so index assignment is deterministic."""
    rows = journal_rows if journal_rows is not None else _default_journal_rows()
    dead: set = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("status") in ("reversed", "reversal_failed", "void"):
            dead.add((r.get("pid"), r.get("jid")))
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict) or r.get("canary"):
            continue
        if r.get("status") != "executed" or not r.get("executed_at"):
            continue
        if (r.get("pid"), r.get("jid")) in dead:
            continue
        exp = tell_surface._parse_iso(r.get("ttl_expires_at"))
        nowdt = tell_surface._parse_iso(now)
        if exp is not None and nowdt is not None and exp <= nowdt:
            continue                      # window closed — no live handle to offer
        out.append(dict(r))
    out.sort(key=lambda r: str(r.get("executed_at") or r.get("ts") or ""))
    return out


def gather_self_rows(*, journal_rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """The org's own self-state for the 🫀SELF leg: frozen act-first kinds, from
    the undo journal's ``op:freeze`` rows (no auto-unfreeze exists — CRIT-5 — so
    every freeze is live until a human clears it). Canary/breaker rows are the
    weekly runner's to contribute (unscheduled today — checkpoint Tier-0 #5);
    callers inject them via ``self_rows`` when they exist."""
    rows = journal_rows if journal_rows is not None else _default_journal_rows()
    frozen: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if isinstance(r, dict) and r.get("op") == "freeze" and r.get("kind"):
            frozen[str(r["kind"])] = {"type": "frozen", "kind": r["kind"],
                                      "reason": r.get("reason") or ""}
    return list(frozen.values())


# --- stable undo-index assignment ----------------------------------------------

def _load_manifest(raw: str) -> Dict[str, Any]:
    try:
        doc = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def assign_undo_indexes(acted_rows: List[Dict[str, Any]], *, date: str,
                        redis_get: Callable[[str], str]) -> List[Dict[str, Any]]:
    """Stamp each loud acted row's stable ``undo_index`` [RT-A9].

    Merges with the manifests the binder can still see (today then yesterday):
    a pid that already holds an index KEEPS it — today's assignment wins over
    yesterday's — and new pids mint from a monotonic ``next_index`` that starts
    ABOVE every index either manifest has ever issued, so an index is never
    reused while any rendered message carrying it can still bind (the manifests
    and the undo windows expire on the same 48h clock). Mutates copies only."""
    seen: Dict[str, int] = {}
    ceiling = 0
    y = _yesterday_of(date)
    for d in (y, date):                    # today second — its assignment wins
        if not d:
            continue
        try:
            raw = redis_get(_DIGEST_KEY_PREFIX + d)
        except Exception:
            raw = ""
        doc = _load_manifest(raw) if raw else {}
        ceiling = max(ceiling, int(doc.get("next_index") or 0) - 1)
        for it in (doc.get("items") or []):
            if not isinstance(it, dict):
                continue
            pid, idx = str(it.get("pid") or ""), it.get("index")
            if pid and isinstance(idx, int) and idx > 0:
                seen[pid] = idx
                ceiling = max(ceiling, idx)
    nxt = ceiling + 1
    out: List[Dict[str, Any]] = []
    for r in acted_rows:
        row = dict(r)
        pid = str(row.get("pid") or "")
        if row.get("quiet"):
            out.append(row)                # quiet rows carry no index (rollup)
            continue
        if pid in seen:
            row["undo_index"] = seen[pid]
        else:
            row["undo_index"] = nxt
            seen[pid] = nxt
            nxt += 1
        out.append(row)
    return out


# --- the one orchestration entry -------------------------------------------------

def enqueue_digest(*, now: Optional[str] = None,
                   acted_rows: Optional[List[Dict[str, Any]]] = None,
                   awaiting_rows: Optional[List[Dict[str, Any]]] = None,
                   watching_rows: Optional[List[Dict[str, Any]]] = None,
                   self_rows: Optional[List[Dict[str, Any]]] = None,
                   redis_get: Optional[Callable[[str], str]] = None,
                   redis_set: Optional[Callable[[str, str, int], None]] = None,
                   enqueue: Optional[Callable[[Dict[str, Any]], str]] = None) -> Dict[str, Any]:
    """Build + persist + enqueue one act-then-tell digest (see module header).

    Returns telemetry: ``{"digest": bool, "skipped"/"error": str?, "enqueued":
    id?, "date": str, "acted": n, "awaiting": n, "manifest": [...]}``. Never
    raises for the empty case (``digest=False, skipped=...``); a manifest
    persistence failure returns ``digest=False, error=...`` WITHOUT enqueueing
    (fail-closed: no digest whose indexes cannot bind). run_briefing wraps the
    call so even a crash never blocks the briefing send."""
    if not _enabled():
        return {"digest": False, "skipped": "disabled (CABINET_TELL_DIGEST=0)"}
    now_s = now or _now_iso()
    date = _date_of(now_s)
    rget = redis_get or _default_redis_get

    acted = acted_rows if acted_rows is not None else gather_acted_rows(now=now_s)
    awaiting = awaiting_rows if awaiting_rows is not None else _default_pending()
    watching = watching_rows or []
    selfr = self_rows if self_rows is not None else gather_self_rows()

    acted = assign_undo_indexes(acted, date=date, redis_get=rget)
    text = tell_surface.build_digest(acted, awaiting, watching, selfr, now=now_s)
    if not text:
        return {"digest": False, "skipped": "nothing to tell", "date": date,
                "acted": 0, "awaiting": 0}

    manifest_items = tell_surface.digest_manifest(acted)
    if manifest_items:
        # Persist BEFORE enqueue [ordering invariant]: the undo-by-index grammar
        # must resolve from the first moment the text can be read. next_index
        # continues past every index this or yesterday's manifest issued.
        doc = {"date": date,
               "next_index": max(it["index"] for it in manifest_items) + 1,
               "items": manifest_items}
        try:
            (redis_set or _default_redis_set)(
                _DIGEST_KEY_PREFIX + date,
                json.dumps(doc, ensure_ascii=False), _MANIFEST_TTL_S)
        except Exception as e:
            return {"digest": False, "date": date,
                    "error": f"manifest persist failed: {str(e)[:200]}"}

    item = {
        "source": "tell-digest",
        "kind": "digest",
        "ts": now_s,
        "urgency_tier": "batch",
        "payload": {"summary": text},
        "context": {"why": "act-then-tell digest (TI-5) — acted/awaiting/"
                           "watching/self; reply `undo <n>` / `👍 <n>` binds "
                           "via the server manifest"},
    }
    try:
        enq_id = (enqueue or _default_enqueue)(item)
    except Exception as e:
        return {"digest": False, "date": date,
                "error": f"intake enqueue failed: {str(e)[:200]}",
                "manifest": manifest_items}
    return {"digest": True, "enqueued": enq_id, "date": date,
            "acted": len([r for r in acted if not r.get("quiet")]),
            "awaiting": len(awaiting), "manifest": manifest_items}


if __name__ == "__main__":  # pragma: no cover — manual dev invocation (dry gather)
    # A bare run gathers + renders but persists/enqueues NOTHING — safe to eyeball.
    rows = gather_acted_rows(now=_now_iso())
    print(json.dumps({"acted_candidates": len(rows)}, indent=2))
