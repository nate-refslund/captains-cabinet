"""The explicit trust ladder — the OPT-IN `earn_up` posture's climb surface.

HISTORY (read before wiring this anywhere): this module was DELETED by
0a9dda6e (2026-07-04) because, as a DEFAULT, "capability given day-one, trust
is EARNED" contradicted the ratified earn-demotion ruling (captain-decisions
2026-07-03): reversible classes act-with-undo from day one and trust is LOST
on evidence, never rung-earned. That ripout stays correct for the default
world — guardian and sovereign never consult this module. It RETURNS
(axes build, spec 2026-07-05 §1 L1) as the OPT-IN surface of the `earn_up`
posture: the cautious captain's leader-leader start, where every non-ceiling
cell floors at propose_only and ALL autonomy above the floor is rung-granted
here. Active ONLY when `framework.authority.posture.resolve_posture()`
resolves `earn_up`; under any other posture the surfacing path is inert and
the gate overlay never applies.

Extends the cabinet's graduated-autonomy with explicit, named rungs that climb
as cells prove out. This is the Captain-readable map that sits ABOVE the
per-cell `framework.fidelity.graduation.evaluate()` machine — it does NOT
re-implement it.

The rung vocabulary, and the FROZEN rung → verdict map the gate overlay lifts
through (axes spec 2026-07-05 §1 L1):

    would-like-to   propose-first (waits for approval)     -> propose_only
    intend-to       veto-window (acts unless vetoed)       -> auto_with_veto_window
    ive-done        acts, reports after                    -> notify_after
    ive-been-doing  fully graduated (reports periodically) -> auto

Climb is PER LANE, one rung at a time, EARNED by proven outcomes (every cell a
rung grants must be `graduated` per graduation.evaluate). Capability is given
day-one; trust is earned — under THIS posture only.

HARD LINE (unchanged from the original, now doubly load-bearing): there is NO
self-grant path. A rung that is *earned* is SURFACED as a one-tap card
(intake.enqueue) + a `trust_rung_proposed` event; the Captain grants it by
appending a `granted:` row to the Captain-locked
instance/config/trust-ladder.yml in an unlock window (germline-lock.sh
unlock → edit → re-lock) — the ATTESTED file is the ONLY authority source,
the same polarity as standing-grants (grants.py D6). `current_rung()` derives
from those attested rows and NEVER from the event ledger: the ledger is
same-uid-appendable, so `trust_rung_granted` (emitted by `grant_rung()`, the
Captain's audit surface) is an AUDIT record only — a forged event mints
nothing. A ceiling rung (any granted cell maps to a hard-ceiling risk_class)
is **un-earnable by auto-grant** — proposable, but the grant stays the
Captain's forever, matching the authority-matrix `always_gated` rows. And the
gate overlay (`rung_verdict_lift`) never lifts a ceiling row regardless of
rung — enforced in code, not config.

System Python 3.9.6; stdlib + yaml + in-repo modules only. Fail-closed: a
missing/broken ladder file degrades to a single `would-like-to` rung (propose
everything, lift nothing), and `granted:` rows in a present-but-UNATTESTED
(not Captain-locked) file are ignored — never an autonomy-widening default.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_FRAMEWORK_ROOT = str(Path(__file__).resolve().parents[2])
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework import env  # roster-resolved default role
from framework.events.emitter import emit  # noqa: E402

try:
    from yaml import safe_load as _yaml_load
except ImportError:  # pragma: no cover - yaml present in the cabinet runtime
    _yaml_load = None


# The grand-plan rung vocabulary, lowest -> highest. The ladder file may use a
# subset/ordering of these, but only these names are valid.
RUNG_ORDER = ("would-like-to", "intend-to", "ive-done", "ive-been-doing")

# The base rung — always present, always granted, the conservative default.
BASE_RUNG = "would-like-to"

# FROZEN rung -> verdict map (axes spec 2026-07-05 §1 L1) — the ONLY lift
# vocabulary the earn_up gate overlay may apply. The base rung maps to the
# static earn_up floor itself (propose_only), i.e. no lift.
RUNG_VERDICTS = {
    "would-like-to": "propose_only",
    "intend-to": "auto_with_veto_window",
    "ive-done": "notify_after",
    "ive-been-doing": "auto",
}

# The posture this module serves. Matches framework.authority.posture.EARN_UP;
# a literal here so the module stays importable without the posture kernel
# (absence then reads as "not earn_up" ⇒ inert, fail-closed).
EARN_UP_POSTURE = "earn_up"

_LADDER_REL = "instance/config/trust-ladder.yml"


# ---------------------------------------------------------------------------
# Rung / Ladder data model
# ---------------------------------------------------------------------------

class Rung:
    """One ordered rung: a name + the cells it grants + the proof bar."""

    __slots__ = ("name", "lane", "grants", "min_samples", "ceiling")

    def __init__(self, name: str, lane: Optional[str],
                 grants: list[tuple[Optional[str], str]],
                 min_samples: Optional[int], ceiling: list[str]):
        self.name = name
        self.lane = lane
        self.grants = grants            # [(lane, action_type), ...]
        self.min_samples = min_samples  # optional override; None = use matrix bar
        self.ceiling = ceiling          # hard-ceiling categories touched (computed)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "lane": self.lane,
            "grants": [list(g) for g in self.grants],
            "min_samples": self.min_samples, "ceiling": self.ceiling,
        }


def _ceiling_for_action_type(action_type: str) -> Optional[str]:
    """Return the hard-ceiling risk_class an action_type maps to, or None.

    Reads the same authority-matrix the gate uses (single source of truth). Any
    error -> None means "unknown" but `_grants_touch_ceiling` treats an
    unresolvable mapping conservatively (see there).
    """
    try:
        from framework.authority.matrix import load_matrix, matrix_policy
        policy = matrix_policy(load_matrix())
        hard = set(policy.get("hard_ceiling") or [])
        for rc, spec in (policy.get("risk_classes") or {}).items():
            if action_type in (spec.get("action_types") or []):
                return rc if rc in hard else None
        return None
    except Exception:
        return None


def _grants_touch_ceiling(grants: list[tuple[Optional[str], str]]) -> list[str]:
    """The sorted set of hard-ceiling risk_classes any granted cell touches."""
    touched: set[str] = set()
    for _lane, action_type in grants:
        rc = _ceiling_for_action_type(action_type)
        if rc is not None:
            touched.add(rc)
    return sorted(touched)


# ---------------------------------------------------------------------------
# Posture gate — the surfacing path is inert outside earn_up.
# ---------------------------------------------------------------------------

def _resolved_posture(lane: Optional[str] = None, posture_fn=None) -> str:
    """The posture this deployment/lane runs under, fail-closed: kernel
    absent, exception, or an out-of-vocab answer reads as guardian — which
    keeps every earn_up surface inert (the ripout's default world)."""
    fn = posture_fn
    if fn is None:
        try:
            from framework.authority.posture import resolve_posture as fn
        except Exception:
            return "guardian"
    try:
        posture = fn(lane)
    except Exception:
        return "guardian"
    return posture if isinstance(posture, str) else "guardian"


# ---------------------------------------------------------------------------
# load_ladder — fail-closed to a single would-like-to rung.
# ---------------------------------------------------------------------------

def _safe_default_ladder() -> list[Rung]:
    return [Rung(BASE_RUNG, None, [], None, [])]


def load_ladder(cabinet_root: str | Path | None = None) -> list[Rung]:
    """Load instance/config/trust-ladder.yml into an ordered Rung list.

    Fail-closed: a missing/broken/empty file -> [would-like-to] (propose
    everything). Invalid rung names or shapes are dropped (never widen). The
    base rung is always present and first.
    """
    root = Path(cabinet_root or os.environ.get("CABINET_ROOT") or _FRAMEWORK_ROOT)
    cfg = root / _LADDER_REL
    if _yaml_load is None or not cfg.exists():
        return _safe_default_ladder()
    try:
        data = _yaml_load(cfg.read_text()) or {}
    except Exception:
        return _safe_default_ladder()

    raw = data.get("rungs")
    if not isinstance(raw, list) or not raw:
        return _safe_default_ladder()

    rungs: list[Rung] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if name not in RUNG_ORDER:
            continue  # only the grand-plan vocabulary is valid
        lane = entry.get("lane")
        lane = str(lane) if lane else None
        grants: list[tuple[Optional[str], str]] = []
        for g in entry.get("grants") or []:
            if isinstance(g, dict) and g.get("action_type"):
                g_lane = g.get("lane", lane)
                grants.append((str(g_lane) if g_lane else None, str(g["action_type"])))
            elif isinstance(g, (list, tuple)) and len(g) == 2 and g[1]:
                grants.append((str(g[0]) if g[0] else None, str(g[1])))
        min_samples = entry.get("min_samples")
        try:
            min_samples = int(min_samples) if min_samples is not None else None
        except (TypeError, ValueError):
            min_samples = None
        ceiling = _grants_touch_ceiling(grants)
        rungs.append(Rung(name, lane, grants, min_samples, ceiling))

    if not rungs:
        return _safe_default_ladder()

    # Always ensure the base rung is present + first; sort the rest by the
    # canonical rung order then by lane (stable, Captain-readable).
    have_base = any(r.name == BASE_RUNG and r.lane is None for r in rungs)
    ordered = sorted(rungs, key=lambda r: (RUNG_ORDER.index(r.name), r.lane or ""))
    if not have_base:
        ordered = _safe_default_ladder() + ordered
    return ordered


# ---------------------------------------------------------------------------
# current_rung — the Captain-granted rung, derived ONLY from the ATTESTED
# (Captain-locked) ladder file's `granted:` rows.
# ---------------------------------------------------------------------------

# Closed `granted:` row shape — anything extra or malformed is line-dropped.
_GRANTED_KEYS = {"rung", "lane", "granted_at", "note"}


def _default_is_locked(path: Path) -> bool:
    """The deployment attestation (posture.is_locked: schg on macOS,
    ro_mount on docker; symlink-refusing). Lazy so this module stays
    importable without the posture kernel; an unresolvable or failing check
    reads as NOT attested — grants then resolve empty, never a widening
    default."""
    try:
        from framework.authority.posture import is_locked
        return bool(is_locked(path))
    except Exception:
        return False


def granted_rungs(cabinet_root: str | Path | None = None,
                  is_locked_fn=None) -> list[dict[str, Any]]:
    """The valid `granted:` rows of the ATTESTED trust-ladder.yml, else [].

    Rung grants MINT authority (propose_only → … → auto on graduated cells),
    so they are honored ONLY from the Captain-locked file — the
    standing-grants polarity (D6): absent / unparseable / NOT attested ⇒ [].
    The event ledger is NEVER consulted: `trust_rung_granted` events are
    same-uid-appendable audit records, so deriving authority from them would
    be an officer self-grant path. Rows are closed-shape
    ({rung, lane?, granted_at?, note?}); malformed or out-of-vocab rows are
    line-dropped (never widen).
    """
    root = Path(cabinet_root or os.environ.get("CABINET_ROOT") or _FRAMEWORK_ROOT)
    cfg = root / _LADDER_REL
    if _yaml_load is None:
        return []
    try:
        if not cfg.exists():
            return []
    except OSError:
        return []
    if not (is_locked_fn or _default_is_locked)(cfg):
        return []
    try:
        data = _yaml_load(cfg.read_text()) or {}
    except Exception:
        return []
    raw = data.get("granted") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) - _GRANTED_KEYS:
            continue
        if entry.get("rung") not in RUNG_ORDER:
            continue
        lane = entry.get("lane")
        rows.append({"rung": entry["rung"],
                     "lane": str(lane) if lane else None})
    return rows


def current_rung(lane: Optional[str] = None,
                 cabinet_root: str | Path | None = None,
                 is_locked_fn=None) -> str:
    """The highest rung the Captain has actually GRANTED for `lane` (default
    base).

    Derives ONLY from the `granted:` rows of the ATTESTED (Captain-locked)
    ladder file — never from `trust_rung_granted` events, which are audit
    records with no integrity boundary (the axes Corridor constraint pins
    authority changes to Captain-authenticated surfaces; the schg/ro_mount
    lock IS that surface). Absent / unlocked / corrupt file, or no applicable
    row ⇒ would-like-to (the conservative floor). A grant row with no lane
    applies to every lane; another lane's row never applies — including when
    the queried lane is None (estate-wide): only lane-less rows apply then,
    so a lane-scoped grant never lifts lane-less cells.
    """
    best_idx = RUNG_ORDER.index(BASE_RUNG)
    try:
        rows = granted_rungs(cabinet_root, is_locked_fn)
    except Exception:
        return RUNG_ORDER[best_idx]
    for row in rows:
        if row["lane"] is not None and row["lane"] != lane:
            continue
        idx = RUNG_ORDER.index(row["rung"])
        if idx > best_idx:
            best_idx = idx
    return RUNG_ORDER[best_idx]


# ---------------------------------------------------------------------------
# The gate overlay input (AX-2) — rung_verdict_lift, consumed by
# framework/authority/policy_engine._eval_authority_matrix under earn_up.
# ---------------------------------------------------------------------------

def ladder_rung_cap(lane: Optional[str] = None,
                    cabinet_root: str | Path | None = None) -> str:
    """The highest rung the Captain-authored ladder FILE defines that applies
    to `lane` (a rung with lane=None applies to every lane; a lane-scoped rung
    never applies to a lane=None query — same lane rule as current_rung).

    This is the overlay's file-side CAP: a granted rung only lifts up to what
    the ladder file still defines, so deleting/corrupting the file drops every
    lift back to the floor (load_ladder fail-closes to [would-like-to]) — the
    Captain's mechanical kill handle for the earn_up surface.
    """
    best_idx = RUNG_ORDER.index(BASE_RUNG)
    for rung in load_ladder(cabinet_root):
        if rung.name not in RUNG_ORDER:
            continue
        if rung.lane is not None and rung.lane != lane:
            continue
        best_idx = max(best_idx, RUNG_ORDER.index(rung.name))
    return RUNG_ORDER[best_idx]


def rung_verdict_lift(lane: Optional[str] = None, *,
                      posture: str,
                      cabinet_root: str | Path | None = None,
                      is_locked_fn=None) -> Optional[str]:
    """The earn_up gate-overlay verdict for `lane`, or None when no lift
    applies.

    THE CALLER'S CONTRACT (policy_engine step 3b): the gate applies this ONLY
    when its resolved posture == earn_up AND the cell's graduation state ==
    graduated AND the risk_class is not a hard ceiling — this function
    supplies the "Captain granted the rung for that lane" leg. `posture` is
    the caller's already-resolved posture, required so the ladder refuses to
    compute a lift for any other posture (belt-and-braces; the resolution
    itself stays single-sourced at the gate).

    effective rung = min(granted rung, ladder-file cap for the lane) by rung
    order — so the lift needs BOTH a Captain-authored `granted:` row in the
    ATTESTED (Captain-locked) ladder file and that same file still defining
    the rung level for the lane. Missing/corrupt/unattested ladder file, base
    rung, broken grant read, any exception ⇒ None (the static earn_up floor
    stands, fail-closed).
    """
    if posture != EARN_UP_POSTURE:
        return None
    try:
        granted = current_rung(lane, cabinet_root, is_locked_fn)
        cap = ladder_rung_cap(lane, cabinet_root)
        effective_idx = min(RUNG_ORDER.index(granted), RUNG_ORDER.index(cap))
    except Exception:
        return None
    effective = RUNG_ORDER[effective_idx]
    if effective == BASE_RUNG:
        return None  # base maps to the floor itself — no lift
    return RUNG_VERDICTS.get(effective)


# ---------------------------------------------------------------------------
# evaluate_ladder — which rungs are earned, pending, or ceiling-blocked.
# ---------------------------------------------------------------------------

def _cell_state(actor_id: str, cell: tuple[Optional[str], str],
                evaluate_fn=None) -> dict[str, Any]:
    """Read graduation.evaluate for one (lane, action_type) cell. Fail-safe ->
    unmeasured so a broken read can never read as graduated.
    """
    lane, action_type = cell
    fn = evaluate_fn
    if fn is None:
        from framework.fidelity.graduation import evaluate as fn  # type: ignore
    try:
        return fn((actor_id, lane, action_type)) or {"state": "unmeasured", "evidence": {}}
    except Exception:
        return {"state": "unmeasured", "evidence": {}}


def _rung_proof(actor_id: str, rung: Rung, evaluate_fn=None) -> dict[str, Any]:
    """Evaluate every cell a rung grants. A rung is EARNED iff every granted
    cell is `graduated` (and, when set, meets the rung's min_samples override).

    Returns {earned: bool, cells: [{cell, state, sample_count}], reason: str}.
    A rung with NO grants is never earned (nothing to prove).
    """
    if not rung.grants:
        return {"earned": False, "cells": [], "reason": "no grants to prove"}

    cells_out = []
    all_graduated = True
    for cell in rung.grants:
        res = _cell_state(actor_id, cell, evaluate_fn)
        state = res.get("state", "unmeasured")
        ev = res.get("evidence") or {}
        samples = ev.get("sample_count")
        cells_out.append({"cell": list(cell), "state": state, "sample_count": samples})
        if state != "graduated":
            all_graduated = False
        elif rung.min_samples is not None and (samples or 0) < rung.min_samples:
            all_graduated = False

    reason = "all granted cells graduated" if all_graduated else "not all cells graduated"
    return {"earned": all_graduated, "cells": cells_out, "reason": reason}


def evaluate_ladder(actor_id: str, lane: Optional[str] = None,
                    evaluate_fn=None,
                    cabinet_root: str | Path | None = None) -> dict[str, Any]:
    """For `actor_id` (e.g. 'officer:cos') on `lane`, classify each rung above
    the current granted rung as earned / pending / blocked-by-ceiling.

    Returns:
        {
          "current_rung": str,
          "earned": [ {rung, proof} ],            # earned, not yet granted, non-ceiling
          "pending": [ {rung, proof} ],           # not earned yet
          "blocked_by_ceiling": [ {rung, ceiling} ],  # earnable cells but ceiling -> Captain-only
        }
    """
    ladder = load_ladder(cabinet_root)
    cur = current_rung(lane, cabinet_root)
    cur_idx = RUNG_ORDER.index(cur) if cur in RUNG_ORDER else 0

    out: dict[str, Any] = {
        "current_rung": cur, "earned": [], "pending": [], "blocked_by_ceiling": [],
    }
    for rung in ladder:
        if rung.name not in RUNG_ORDER:
            continue
        if rung.lane is not None and rung.lane != lane:
            continue
        # only rungs strictly above the current granted rung are candidates
        if RUNG_ORDER.index(rung.name) <= cur_idx:
            continue
        proof = _rung_proof(actor_id, rung, evaluate_fn)
        if rung.ceiling:
            # ceiling rung: Captain-only grant, never auto — surfaced separately.
            out["blocked_by_ceiling"].append({"rung": rung.as_dict(), "ceiling": rung.ceiling})
        elif proof["earned"]:
            out["earned"].append({"rung": rung.as_dict(), "proof": proof})
        else:
            out["pending"].append({"rung": rung.as_dict(), "proof": proof})
    return out


# ---------------------------------------------------------------------------
# propose_next_rung — surface the lowest earned-but-not-granted rung.
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _render_rung_card(actor_id: str, lane: Optional[str], entry: dict[str, Any],
                      *, ceiling: bool) -> str:
    rung = entry["rung"]
    name = rung["name"]
    cells = (entry.get("proof") or {}).get("cells", [])
    lane_txt = lane or rung.get("lane") or "all lanes"
    lines = [f"🪜 Trust rung *{name}* {'(Captain-only)' if ceiling else 'earned'} "
             f"for {actor_id} on {lane_txt}."]
    if cells:
        cell_txt = ", ".join(
            f"{c['cell'][1]}({c['state']}, n={c.get('sample_count')})" for c in cells
        )
        lines.append(f"Proven cells: {cell_txt}")
    if ceiling:
        lines.append(
            f"⚠ Touches hard-ceiling {entry.get('ceiling')} — the ladder will "
            "NEVER auto-advance past this, and the gate overlay never lifts a "
            "ceiling row. Grant stays yours; approve only if you want this "
            "lane to act under the ceiling rung."
        )
    else:
        lines.append(
            f"Approve to grant rung *{name}* — graduated cells on this lane "
            f"then resolve to `{RUNG_VERDICTS.get(name)}` per the earn_up rung "
            "map. A demote on any cell drops it back to propose-first."
        )
    lane_key = lane or rung.get("lane")
    row_txt = ("{rung: %s}" % name) if not lane_key \
        else ("{rung: %s, lane: %s}" % (name, lane_key))
    lines.append(
        "Grant (Captain ritual — the ATTESTED ladder file is the only "
        f"authority source): sudo bash cabinet/scripts/germline-lock.sh "
        f"unlock {_LADDER_REL}, append granted row {row_txt}, re-lock. "
        "Officers cannot self-grant — bare trust_rung_granted events carry "
        "no authority."
    )
    return "\n".join(lines)


def propose_next_rung(actor_id: str, lane: Optional[str] = None,
                      *, urgency_tier: str = "batch", actor: "str | None" = None,
                      evaluate_fn=None, enqueue_fn=None, emit_fn=None,
                      posture_fn=None,
                      cabinet_root: str | Path | None = None) -> Optional[dict[str, Any]]:
    """Surface a one-tap card for the lowest earned-but-not-granted rung (or the
    lowest ceiling rung whose cells are all graduated, flagged Captain-only).

    ACTIVE ONLY UNDER earn_up: any other resolved posture (or a broken/absent
    posture kernel) returns None with NO side effects — guardian and sovereign
    never see rung cards. Returns the surfaced proposal dict, or None if
    nothing is ready. NEVER grants — only proposes. Best-effort surfacing
    (never raises on transport).
    """
    actor = actor or env.chair_officer()
    if _resolved_posture(lane, posture_fn) != EARN_UP_POSTURE:
        return None
    if urgency_tier not in ("ping-now", "batch", "fyi"):
        urgency_tier = "batch"
    ev = evaluate_ladder(actor_id, lane, evaluate_fn, cabinet_root)

    candidate = None
    is_ceiling = False
    if ev["earned"]:
        # lowest earned non-ceiling rung
        candidate = min(ev["earned"], key=lambda e: RUNG_ORDER.index(e["rung"]["name"]))
    elif ev["blocked_by_ceiling"]:
        # surface a ceiling rung ONLY if its cells are actually all graduated
        ready = []
        for e in ev["blocked_by_ceiling"]:
            proof = _rung_proof(actor_id, _rung_from_dict(e["rung"]), evaluate_fn)
            if proof["earned"]:
                e = {**e, "proof": proof}
                ready.append(e)
        if ready:
            candidate = min(ready, key=lambda e: RUNG_ORDER.index(e["rung"]["name"]))
            is_ceiling = True
    if candidate is None:
        return None

    rung = candidate["rung"]
    summary = _render_rung_card(actor_id, lane, candidate, ceiling=is_ceiling)
    proposal = {
        "actor_id": actor_id, "lane": lane, "rung": rung["name"],
        "ceiling": is_ceiling, "summary": summary,
        "urgency_tier": urgency_tier,
    }

    item = {
        "source": "trust-ladder",
        "kind": "trust-rung-proposal",
        "ts": _now_iso(),
        "urgency_tier": urgency_tier,
        "payload": {
            "summary": summary, "rung": rung["name"], "lane": lane,
            "actor_id": actor_id, "ceiling": is_ceiling,
        },
    }
    enqueue = enqueue_fn
    if enqueue is None:
        try:
            from framework.frontdoor import intake
            enqueue = intake.enqueue
        except Exception:
            enqueue = None
    proposal["enqueued_id"] = None
    if enqueue is not None:
        try:
            proposal["enqueued_id"] = enqueue(item)
        except Exception:
            proposal["enqueued_id"] = None

    _emit = emit_fn or emit
    try:
        _emit("trust_rung_proposed", actor=actor, payload={
            "actor_id": actor_id, "lane": lane, "rung": rung["name"],
            "ceiling": is_ceiling, "urgency_tier": urgency_tier,
        })
    except Exception:
        pass
    return proposal


def _rung_from_dict(d: dict[str, Any]) -> Rung:
    grants = [(g[0], g[1]) for g in (d.get("grants") or [])]
    return Rung(d["name"], d.get("lane"), grants, d.get("min_samples"), d.get("ceiling") or [])


# ---------------------------------------------------------------------------
# grant_rung — the Captain audit surface (records the AUDIT event; authority
# lives in the locked ladder file, never in the ledger).
# ---------------------------------------------------------------------------

def grant_rung(rung: str, lane: Optional[str] = None, *,
               actor: str = "captain", note: str = "",
               emit_fn=None) -> dict[str, Any]:
    """Record the `trust_rung_granted` AUDIT event for a grant the Captain
    applied to the locked ladder file. AUDIT ONLY — no authority derives from
    this event: the event ledger is same-uid-appendable, so `current_rung()`
    reads the `granted:` rows of the ATTESTED instance/config/trust-ladder.yml
    exclusively. The schg-locked file is the authority boundary (the axes
    Corridor constraint pins authority changes to Captain-authenticated
    surfaces; the lock ritual is that surface, exactly like
    standing-grants/grant-apply.sh — no runtime writer exists here on
    purpose).

    The grant ritual: `sudo bash cabinet/scripts/germline-lock.sh unlock
    instance/config/trust-ladder.yml` → append the granted row → re-lock →
    call this for the audit trail. Intentionally a separate, explicit call
    (not reachable from the propose path).

    Raises ValueError on an unknown rung name (fail-closed — no record of an
    invalid rung).
    """
    if rung not in RUNG_ORDER:
        raise ValueError(f"grant_rung: unknown rung '{rung}'; valid: {list(RUNG_ORDER)}")
    _emit = emit_fn or emit
    return _emit("trust_rung_granted", actor=actor, payload={
        "rung": rung, "lane": lane, "note": note,
    })


if __name__ == "__main__":  # tiny manual smoke (no live events)
    import json
    print("RUNG_ORDER:", RUNG_ORDER)
    print("RUNG_VERDICTS:", json.dumps(RUNG_VERDICTS))
    print("default ladder:", json.dumps([r.as_dict() for r in _safe_default_ladder()]))
