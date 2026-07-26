"""tell_digest.py — TI-5: the act-then-tell digest ORCHESTRATOR (impure seam).

``tell_surface`` is the PURE formatter (injected rows only, no clock, no I/O).
This module is its production counterpart — the missing wiring the 2026-07-04
checkpoint names Tier-0 #6 ("Wire TI-5 digest legs — ACTED/AWAITING/WATCHING/
SELF + manifest into composer.py/run_briefing.py; enables undo-by-index and
plugs the binder no-pid label leak — the Captain's ruled flip prerequisite"). One call
per briefing run:

  1. GATHER — acted journal rows still inside their undo window (non-canary,
     non-demo, not reversed/voided), pending propose-class proposals (the AWAITING leg —
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

LOOP READOUT (5th leg — lane instrument, 2026-07-05): the digest can carry a
``📈 LOOP`` section that makes loop-closure VISIBLE instead of only queryable:
per-card-kind approve/edit/skip/expired rates + the undo-rate trend from the
consequence ledger (``compute_card_rates`` / ``undo_rate_trend``), and the
daily falsifier series (``shared/interfaces/falsifier-series.jsonl``, written
by cabinet/scripts/falsifier-report.py but previously read by NOTHING —
``read_falsifier_series`` surfaces acted_7d / reversal_rate_7d /
cells_accumulating / cells_graduated). The leg lives HERE (unlocked) because
tell_surface.py is germline-locked; the readout is appended AFTER
``build_digest``'s output. The production wire point is run_briefing.py, which
passes ``readout=gather_loop_readout()``; ``readout=None`` (the default)
preserves the exact pre-2026-07-05 behavior so fixtured tests stay hermetic
(the gather reads the LIVE ledger + series file — callers, not this module,
decide when that is safe). ``gather_loop_readout`` never raises — a readout
failure must never cost the digest (fail-safe: no readout on error, never a
blocked tell).

RECEIPT GRAMMAR — the "— why" clause (Wave B RECEIPTS, 2026-07-09): after
``_build_digest_text`` renders the legs, ``action_language.digest_with_why``
appends each ACTED item's compact ``— why: …`` clause (the proposing card's
rationale, when a journal row carries the additive ``why`` field — see
framework/frontdoor/action_language.py for the grammar + the germline
handback). Same unlocked-decoration pattern as the LOOP readout above
(tell_surface._acted_section is germline-locked). Rows without a why — the
entire pre-grammar world — render BYTE-IDENTICALLY, and a decoration failure
never costs the digest.
"""
from __future__ import annotations

import inspect
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from framework.frontdoor import action_language, tell_surface

# RECONCILE 2026-07-05: kept both — HEAD's loop-readout exports (gather/render
# readout + card rates + undo trend + falsifier series) + sovereign's needs /
# gate-tell exports, unioned into ONE list.
__all__ = ["enqueue_digest", "assign_undo_indexes", "gather_acted_rows",
           "gather_self_rows", "gather_loop_readout", "render_loop_readout",
           "compute_card_rates", "undo_rate_trend", "read_falsifier_series",
           "gather_needs_rows", "gather_gate_tell_rows"]

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
    non-canary, non-demo, undo window still open, and NOT already reversed /
    failed-reversal / voided (the reversal journals a superseding status row
    for the same jid — its original ``executed`` row must not resurface with a
    dead handle). Sorted by execution time so index assignment is
    deterministic. The ``demo`` skip mirrors ``action_reconcile.run_sweep``'s
    (defense-in-depth: the hatch demo seeder never journals its row since the
    2026-07-10 fix pass, but any future demo-stamped row must never earn a
    digest line or an undo handle)."""
    rows = journal_rows if journal_rows is not None else _default_journal_rows()
    dead: set = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("status") in ("reversed", "reversal_failed", "void"):
            dead.add((r.get("pid"), r.get("jid")))
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict) or r.get("canary") or r.get("demo"):
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


# RECONCILE 2026-07-05: kept both — HEAD's 📈 LOOP readout section (below) AND
# sovereign's gather_needs_rows / gather_gate_tell_rows (after it); two distinct
# new digest legs, no overlap.
# --- loop readout (5th leg — acceptance/undo rates + falsifier series) ----------

# Default falsifier series location — the ONE file falsifier-report.py appends
# to (cabinet/scripts/falsifier-report.py SERIES_PATH). Kept as a module
# constant so tests and the report script can never drift silently on the path.
_FALSIFIER_SERIES_PATH = (Path(__file__).resolve().parents[2]
                          / "shared" / "interfaces" / "falsifier-series.jsonl")

# Card-rate window (days). Dated decision 2026-07-05: rates over the WHOLE
# ledger would dilute behavior changes under months of history; 30d is the
# shortest window that still spans several briefing/retro cycles. Rendered in
# the section label so the Captain always knows what he is reading.
_CARD_RATE_WINDOW_DAYS = 30


def compute_card_rates(ledger: List[Dict[str, Any]],
                       *, since: Optional[str] = None) -> Dict[str, Dict[str, int]]:
    """Per-card-kind decision counts from the consequence ledger.

    "Kind" is the stamped ``action_type`` enum — the same cell axis
    compute_ratios keys on (framework/fidelity/consequence.py:639), aggregated
    over actor+lane; unstamped rows surface under the visible ``__unstamped__``
    sentinel (no-silent-caps: hiding them would overstate coverage). Mapping
    (dated 2026-07-05): approve = proposal.decision "approved", edit =
    "edited", skip = "rejected" (the Captain's `skip` reply lands as a
    rejected proposal — consequence._PROPOSAL_DECISIONS has no "skipped"),
    expired = "expired" (TTL lapse). approved/edited/rejected come from
    compute_ratios' per-cell counts (the hinted, already-tested math);
    "expired" needs one raw pass because GraduationRatios deliberately
    excludes it from every rate denominator.
    """
    rows = ledger
    if since is not None:
        rows = [e for e in ledger
                if isinstance(e, dict) and e.get("ts", "") >= since]

    from framework.fidelity.consequence import (UNSTAMPED_ACTION_TYPE,
                                                compute_ratios)
    kinds: Dict[str, Dict[str, int]] = {}

    def _bucket(kind: str) -> Dict[str, int]:
        return kinds.setdefault(kind, {"approved": 0, "edited": 0,
                                       "skipped": 0, "expired": 0})

    for cell, ratios in compute_ratios(ledger=rows).items():
        b = _bucket(cell[2] if cell[2] else UNSTAMPED_ACTION_TYPE)
        b["approved"] += ratios.approved
        b["edited"] += ratios.edited
        b["skipped"] += ratios.rejected
    for ev in rows:
        if not isinstance(ev, dict):
            continue
        if (ev.get("proposal") or {}).get("decision") == "expired":
            _bucket(ev.get("action_type") or UNSTAMPED_ACTION_TYPE)["expired"] += 1
    # Kinds with zero decided cards carry no rate signal — drop them so the
    # readout never renders a wall of "0 cards" lines.
    return {k: v for k, v in kinds.items() if sum(v.values()) > 0}


def undo_rate_trend(ledger: List[Dict[str, Any]],
                    *, now: str) -> Dict[str, Any]:
    """Reversal-rate trend: current 7d window vs the 7d before it.

    Same acted-row semantics as the falsifier report (cabinet/scripts/
    falsifier-report.py:52 _acted_rows + :107 undone): an unattended act is
    ``proposal.required is False`` + a stamped ``action_type``; it counts as
    undone when ``review.verdict == "wrong"`` (Captain undo OR machine-detected
    silent revert). A window with zero acts reads None — an UNMEASURED rate,
    never a silent 0.0 (no-silent-caps)."""
    nowdt = tell_surface._parse_iso(now)
    if nowdt is None:
        return {"rate_7d": None, "prev_rate_7d": None,
                "acted_7d": 0, "undone_7d": 0}
    cur_lo = (nowdt - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    prev_lo = (nowdt - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _window(lo: str, hi: str) -> Dict[str, int]:
        acted = undone = 0
        for ev in ledger:
            if not isinstance(ev, dict):
                continue
            ts = ev.get("ts", "")
            if not (lo <= ts < hi):
                continue
            if (ev.get("proposal") or {}).get("required") is not False:
                continue
            if not ev.get("action_type"):
                continue
            acted += 1
            if (ev.get("review") or {}).get("verdict") == "wrong":
                undone += 1
        return {"acted": acted, "undone": undone}

    cur = _window(cur_lo, now)
    prev = _window(prev_lo, cur_lo)
    return {
        "rate_7d": (cur["undone"] / cur["acted"]) if cur["acted"] else None,
        "prev_rate_7d": (prev["undone"] / prev["acted"]) if prev["acted"] else None,
        "acted_7d": cur["acted"],
        "undone_7d": cur["undone"],
    }


def read_falsifier_series(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Parse falsifier-series.jsonl (one dict per line, oldest first).

    Missing file → [] (the daily job may not have run yet); corrupt lines are
    skipped, mirroring falsifier-report._already_reported's tolerance — a bad
    line must never cost the readout the good ones."""
    p = Path(path) if path is not None else _FALSIFIER_SERIES_PATH
    out: List[Dict[str, Any]] = []
    try:
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    doc = json.loads(line)
                except ValueError:
                    continue
                if isinstance(doc, dict):
                    out.append(doc)
    except OSError:
        return []
    return out


def gather_loop_readout(*, now: Optional[str] = None,
                        ledger: Optional[List[Dict[str, Any]]] = None,
                        series_path: Optional[Path] = None) -> Dict[str, Any]:
    """Assemble the 📈 LOOP readout inputs. NEVER raises (fail-safe: a readout
    failure must never block the act-then-tell digest — on any error the
    failing piece is simply absent and the reason lands in ``errors``).

    Production callers (run_briefing.py) pass nothing: the LIVE consequence
    ledger + the repo falsifier series are read. Tests inject ``ledger`` /
    ``series_path`` — enqueue_digest only consumes what is passed to it, so
    fixtured suites stay hermetic."""
    now_s = now or _now_iso()
    out: Dict[str, Any] = {"now": now_s, "kinds": {}, "undo": {},
                           "falsifier": None, "series_len": 0, "errors": []}
    try:
        if ledger is None:
            from framework.fidelity.consequence import read_ledger
            ledger = read_ledger()
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"ledger: {str(e)[:120]}")
        ledger = []
    try:
        nowdt = tell_surface._parse_iso(now_s)
        since = ((nowdt - timedelta(days=_CARD_RATE_WINDOW_DAYS))
                 .strftime("%Y-%m-%dT%H:%M:%SZ") if nowdt else None)
        out["kinds"] = compute_card_rates(ledger, since=since)
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"card_rates: {str(e)[:120]}")
    try:
        out["undo"] = undo_rate_trend(ledger, now=now_s)
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"undo_trend: {str(e)[:120]}")
    try:
        series = read_falsifier_series(series_path)
        out["series_len"] = len(series)
        out["falsifier"] = series[-1] if series else None
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"falsifier_series: {str(e)[:120]}")
    return out


def _pct(v: Optional[float]) -> str:
    return "–" if v is None else f"{round(v * 100)}%"


def render_loop_readout(readout: Optional[Dict[str, Any]]) -> str:
    """Pure text for the 📈 LOOP section ("" when there is nothing measured —
    silence costs nothing, same rule as build_digest). One line per card kind,
    one undo-trend line, one falsifier line. Errors are NOT rendered (no
    verdict on error — an unreadable metric must not masquerade as a metric);
    they stay in the gather dict for telemetry."""
    if not readout:
        return ""
    lines: List[str] = []

    kinds = readout.get("kinds") or {}
    for kind in sorted(kinds):
        c = kinds[kind]
        if not isinstance(c, dict):
            continue
        # .get(…, 0) hardening [checkpoint review cp1 finding 1]: gather always
        # builds all four keys, but a partial dict from any other caller must
        # degrade to a rendered 0, never a KeyError that costs the digest leg.
        a, e = c.get("approved", 0), c.get("edited", 0)
        s, x = c.get("skipped", 0), c.get("expired", 0)
        decided = a + e + s + x
        if not decided:
            continue
        lines.append(
            f" · {kind} ({_CARD_RATE_WINDOW_DAYS}d, {decided} decided): "
            f"{_pct(a / decided)} approve / "
            f"{_pct(e / decided)} edit / "
            f"{_pct(s / decided)} skip / "
            f"{x} expired")

    undo = readout.get("undo") or {}
    if undo.get("acted_7d"):
        cur, prev = undo.get("rate_7d"), undo.get("prev_rate_7d")
        arrow = ""
        if cur is not None and prev is not None:
            arrow = " ↑" if cur > prev else (" ↓" if cur < prev else " →")
        lines.append(f" · undo-rate 7d: {_pct(cur)} "
                     f"({undo['undone_7d']}/{undo['acted_7d']} acts; "
                     f"prev 7d {_pct(prev)}{arrow})")

    fal = readout.get("falsifier")
    if isinstance(fal, dict):
        lines.append(
            f" · falsifier {fal.get('date', '?')}: "
            f"acted_7d={fal.get('acted_7d')} · "
            f"reversal_7d={_pct(fal.get('reversal_rate_7d'))} · cells "
            f"{fal.get('cells_accumulating')} accumulating / "
            f"{fal.get('cells_graduated')} graduated")

    if not lines:
        return ""
    return "\n".join(["📈 LOOP — acceptance & undo rates"] + lines)


# --- sovereign legs (SOV-6: needs + gate tells) ----------------------------------

def gather_needs_rows(*, now: str,
                      root: Optional[str] = None) -> List[Dict[str, Any]]:
    """The 🙋NEEDS leg rows (SOV-6/FI-3): open + approved_pending_apply needs
    from the ONE needs ledger. Short-circuits to [] unless the needs plane is
    wired (``needs.needs_enabled()`` — sovereign posture / CABINET_NEEDS_WIRED
    / flag file), so the default-world digest stays BYTE-IDENTICAL. NEVER
    raises — a broken needs module means an empty leg, not a lost briefing."""
    try:
        from framework.authority import needs
        if not needs.needs_enabled(root):
            return []
        return needs.list_open(now, root=root)
    except Exception:
        return []


# Sovereign gate tells: window matches the 2x-daily digest cadence; capped so
# a chatty gate can never flood the briefing.
_GATE_TELL_WINDOW_H = 12
_GATE_TELL_CAP = 8


def gather_gate_tell_rows(*, now: str,
                          replay_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None
                          ) -> List[Dict[str, Any]]:
    """Sovereign gate tells for the 👁WATCHING leg (D4): a ``notify_after`` (or
    standing-grant-attributed) allow returns None at the officer gate, so no
    acted row exists — the ``policy_evaluated`` org_event SOV-3 emitted IS the
    audit, and this gather renders it as a digest line. Empty in guardian (the
    gate never emits these there). NEVER raises."""
    try:
        nowdt = tell_surface._parse_iso(now)
        if nowdt is None:
            return []
        since = (nowdt - timedelta(hours=_GATE_TELL_WINDOW_H)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        if replay_fn is None:
            # Production default: the gate only emits these tells when the
            # sovereign plane is wired, so the guardian default path does ZERO
            # event-dir I/O (needs_enabled ⊇ sovereign is the cheap proxy).
            # An injected replay_fn bypasses — tests own their world.
            from framework.authority import needs
            if not needs.needs_enabled():
                return []
            from framework.events.emitter import replay as replay_fn  # type: ignore
        rows: List[Dict[str, Any]] = []
        for ev in replay_fn(since=since, event_types=["policy_evaluated"]):
            p = ev.get("payload") if isinstance(ev, dict) else None
            p = p if isinstance(p, dict) else {}
            if p.get("kind") not in ("notify_after", "standing_grant_allow"):
                continue
            what = "/".join(str(p.get(k)) for k in ("risk_class", "action_type")
                            if p.get(k))
            title = f"gate allowed ({p.get('kind')}): {what or 'action'}"
            if p.get("lane"):
                title += f", lane {p['lane']}"
            if p.get("grant_id"):
                title += f" — grant {p['grant_id']}"
            rows.append({"title": title, "source": "gate-tell"})
        return rows[-_GATE_TELL_CAP:]
    except Exception:
        return []


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

def _build_digest_text(acted, awaiting, watching, selfr, needs, *, now: str) -> str:
    """Call tell_surface.build_digest, feature-detecting the SOV-6 needs leg —
    the 4-arg (pre-needs) and 5-leg signatures both work, so this module merges
    cleanly before OR after the tell_surface diff. When the param is absent the
    needs rows are dropped (the leg simply doesn't exist yet)."""
    try:
        has_needs = "needs_rows" in inspect.signature(
            tell_surface.build_digest).parameters
    except (TypeError, ValueError):
        has_needs = False
    if has_needs:
        return tell_surface.build_digest(acted, awaiting, watching, selfr,
                                         now=now, needs_rows=needs)
    return tell_surface.build_digest(acted, awaiting, watching, selfr, now=now)


def enqueue_digest(*, now: Optional[str] = None,
                   acted_rows: Optional[List[Dict[str, Any]]] = None,
                   awaiting_rows: Optional[List[Dict[str, Any]]] = None,
                   watching_rows: Optional[List[Dict[str, Any]]] = None,
                   self_rows: Optional[List[Dict[str, Any]]] = None,
                   # RECONCILE 2026-07-05: kept both kwargs — readout (HEAD 📈 LOOP
                   # leg) + needs_rows (sovereign 🙋NEEDS leg); both default-off.
                   readout: Optional[Dict[str, Any]] = None,
                   needs_rows: Optional[List[Dict[str, Any]]] = None,
                   redis_get: Optional[Callable[[str], str]] = None,
                   redis_set: Optional[Callable[[str, str, int], None]] = None,
                   enqueue: Optional[Callable[[Dict[str, Any]], str]] = None,
                   replay_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None
                   ) -> Dict[str, Any]:
    """Build + persist + enqueue one act-then-tell digest (see module header).

    Returns telemetry: ``{"digest": bool, "skipped"/"error": str?, "enqueued":
    id?, "date": str, "acted": n, "awaiting": n, "manifest": [...],
    "readout": bool}``. Never raises for the empty case (``digest=False,
    skipped=...``); a manifest persistence failure returns ``digest=False,
    error=...`` WITHOUT enqueueing (fail-closed: no digest whose indexes
    cannot bind). run_briefing wraps the call so even a crash never blocks the
    briefing send.

    RECONCILE 2026-07-05: kept both legs — HEAD's readout + sovereign's
    needs/gate-tells; both default-off, both fail-safe (empty leg, never a
    lost briefing).

    ``readout`` (lane instrument, 2026-07-05) is the pre-gathered 📈 LOOP
    readout dict (``gather_loop_readout()``); its rendered section is appended
    below the tell_surface legs. It is deliberately NOT auto-gathered here:
    the default (None → no leg) keeps every fixtured caller hermetic and
    byte-identical to the pre-readout behavior — run_briefing.py is the
    production wire point. A non-empty readout ships even when the core legs
    are empty (loop-closure stays visible on a quiet day).

    SOV-6 legs (needs + sovereign gate tells) gather only when their rows are
    not injected, and a crashing producer degrades to an empty leg — never a
    lost briefing. Both gathers short-circuit to [] unless the sovereign/needs
    plane is wired, so the default (guardian) digest stays BYTE-IDENTICAL."""
    if not _enabled():
        return {"digest": False, "skipped": "disabled (CABINET_TELL_DIGEST=0)"}
    now_s = now or _now_iso()
    date = _date_of(now_s)
    rget = redis_get or _default_redis_get

    acted = acted_rows if acted_rows is not None else gather_acted_rows(now=now_s)
    awaiting = awaiting_rows if awaiting_rows is not None else _default_pending()
    if watching_rows is None:
        # D4: sovereign notify_after/standing-grant allows are audited ONLY by
        # their org_event — fold them into the WATCHING leg. Guardian emits
        # none, so the default world renders identically.
        watching = gather_gate_tell_rows(now=now_s, replay_fn=replay_fn)
    else:
        watching = watching_rows
    selfr = self_rows if self_rows is not None else gather_self_rows()
    try:
        needs = (needs_rows if needs_rows is not None
                 else gather_needs_rows(now=now_s))
    except Exception:
        needs = []                # TI-5: a needs-producer crash never blocks

    acted = assign_undo_indexes(acted, date=date, redis_get=rget)
    # RECONCILE 2026-07-05: kept both — sovereign's _build_digest_text renders
    # the tell_surface legs incl. the SOV-6 needs leg (feature-detected on
    # build_digest's signature), then HEAD's 📈 LOOP readout is appended below
    # that output. Both legs ride ONE digest text.
    text = _build_digest_text(acted, awaiting, watching, selfr, needs, now=now_s)
    # RECEIPT GRAMMAR (Wave B, 2026-07-09): ACTED items whose journal row
    # carries the additive ``why`` field gain their compact "— why" clause
    # here in the unlocked orchestrator (tell_surface._acted_section is
    # germline-locked — same decoration pattern as the 📈 LOOP readout).
    # digest_with_why is internally defensive; the belt-and-braces wrap keeps
    # a decoration failure from ever costing the briefing. Rows without a
    # why render byte-identically.
    try:
        text = action_language.digest_with_why(text, acted)
    except Exception:
        pass
    # EVIDENCE CITATIONS (evidence Phase 3, 2026-07-17): ACTED items whose
    # journal row carries the Batch-B ``evidence_trial_id`` stamp
    # (action_exec write-ahead) cite their evidence trial on the same
    # headline — design §3 Phase 3 item 4. Same unlocked-decoration pattern
    # and belt-and-braces wrap as the why clause above; rows without the
    # stamp (every pre-evidence journal row) render byte-identically — an
    # honest gap, never a fabricated citation.
    try:
        text = action_language.digest_with_evidence(text, acted)
    except Exception:
        pass
    readout_text = render_loop_readout(readout)
    if text and readout_text:
        # Below the footer, not inside a tell_surface section — the germline
        # renderer is untouched and the reply-grammar footer stays adjacent to
        # the indexed ACTED lines it explains.
        text = text + "\n\n" + readout_text
    elif readout_text:
        # Readout-only digest: no acts/awaiting/watching/self/needs, but the
        # loop metrics still ride the briefing (visibility is the point). No
        # undo grammar implied — the section carries no indexes and no manifest.
        text = readout_text
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
            "awaiting": len(awaiting), "manifest": manifest_items,
            "readout": bool(readout_text)}


if __name__ == "__main__":  # pragma: no cover — manual dev invocation (dry gather)
    # A bare run gathers + renders but persists/enqueues NOTHING — safe to eyeball.
    rows = gather_acted_rows(now=_now_iso())
    print(json.dumps({"acted_candidates": len(rows)}, indent=2))
