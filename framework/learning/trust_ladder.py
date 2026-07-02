"""Component 3 — the explicit trust ladder (Captain-authored rungs).

Extends the cabinet's graduated-autonomy with explicit, named rungs that climb
as cells prove out. This is the Captain-readable map that sits ABOVE the
per-cell `framework.fidelity.graduation.evaluate()` machine — it does NOT
re-implement it. See docs/prove-to-earn-expansion-2026-06-25.md §4.

The rung vocabulary is the one the grand plan already named
(docs/grand-plan-captain-agent-2026-06-21.md §autonomy-ladder):

    would-like-to   propose-first (waits for approval)        -> propose_only
    intend-to       veto-window (acts unless vetoed)          -> auto_with_veto_window
    ive-done        auto-when-proven, reversible (reports after) -> auto / notify_after
    ive-been-doing  fully graduated (reports periodically)    -> auto

Climb is PER LANE, one rung at a time, EARNED by proven outcomes (every cell a
rung grants must be `graduated` per graduation.evaluate). Capability is given
day-one; trust is earned.

HARD LINE (docs §0): there is NO auto-grant path in code by default. A rung that
is *earned* is SURFACED as a one-tap card (intake.enqueue) + a
`trust_rung_proposed` event; Nate grants it (recording `trust_rung_granted`).
A ceiling rung (any granted cell maps to a hard-ceiling risk_class) is
**un-earnable by auto-grant** — proposable, but the grant stays Nate's forever,
matching the authority-matrix `always_gated` rows. Enforced in code, not config.

System Python 3.9.6; stdlib + yaml + in-repo modules only. Fail-closed: a
missing/broken ladder file degrades to a single `would-like-to` rung (propose
everything), never an autonomy-widening default.
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

from framework.events.emitter import emit, replay  # noqa: E402

try:
    from yaml import safe_load as _yaml_load
except ImportError:  # pragma: no cover - yaml present in the cabinet runtime
    _yaml_load = None


# The grand-plan rung vocabulary, lowest -> highest. The ladder file may use a
# subset/ordering of these, but only these names are valid.
RUNG_ORDER = ("would-like-to", "intend-to", "ive-done", "ive-been-doing")

# The base rung — always present, always granted, the conservative default.
BASE_RUNG = "would-like-to"

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
# current_rung — replay trust_rung_granted events (per lane).
# ---------------------------------------------------------------------------

def current_rung(lane: Optional[str] = None) -> str:
    """The highest rung Nate has actually GRANTED for `lane` (default base).

    Replays `trust_rung_granted` events; the granted rung must be a valid
    vocabulary member. Default = would-like-to (the conservative floor).
    """
    granted = BASE_RUNG
    try:
        events = replay(event_types=["trust_rung_granted"])
    except Exception:
        return granted
    best_idx = RUNG_ORDER.index(BASE_RUNG)
    for ev in events:
        p = ev.get("payload") or {}
        if lane is not None and p.get("lane") not in (None, lane):
            continue
        name = p.get("rung")
        if name in RUNG_ORDER and RUNG_ORDER.index(name) > best_idx:
            best_idx = RUNG_ORDER.index(name)
            granted = name
    return granted


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
        return fn((actor_id, lane, action_type))
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
    cur = current_rung(lane)
    cur_idx = RUNG_ORDER.index(cur) if cur in RUNG_ORDER else 0

    out: dict[str, Any] = {
        "current_rung": cur, "earned": [], "pending": [], "blocked_by_ceiling": [],
    }
    for rung in ladder:
        if rung.name not in RUNG_ORDER:
            continue
        if lane is not None and rung.lane not in (None, lane):
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
            "NEVER auto-advance past this. Grant stays yours; approve only if you "
            "want this lane to act under the ceiling rung."
        )
    else:
        lines.append(
            f"Approve to grant rung *{name}* — the granted cells will then resolve "
            "to their matrix auto/veto verdict. A demote on any cell drops it back."
        )
    lines.append(
        "Grant: record a trust_rung_granted event "
        f"(rung={name}, lane={lane_txt}). The Chair does not self-grant authority."
    )
    return "\n".join(lines)


def propose_next_rung(actor_id: str, lane: Optional[str] = None,
                      *, urgency_tier: str = "batch", actor: str = "cos",
                      evaluate_fn=None, enqueue_fn=None, emit_fn=None,
                      cabinet_root: str | Path | None = None) -> Optional[dict[str, Any]]:
    """Surface a one-tap card for the lowest earned-but-not-granted rung (or the
    lowest ceiling rung whose cells are all graduated, flagged Captain-only).

    Returns the surfaced proposal dict, or None if nothing is ready. NEVER
    grants — only proposes. Best-effort surfacing (never raises on transport).
    """
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
# grant_rung — the Captain action surface (records the grant event).
# ---------------------------------------------------------------------------

def grant_rung(rung: str, lane: Optional[str] = None, *,
               actor: str = "captain", note: str = "",
               emit_fn=None) -> dict[str, Any]:
    """Record a `trust_rung_granted` event — the CAPTAIN action that advances the
    ladder. This is intentionally a separate, explicit call (not reachable from
    the propose path): only a Captain-initiated invocation grants a rung.

    Raises ValueError on an unknown rung name (fail-closed — no grant of an
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
    print("default ladder:", json.dumps([r.as_dict() for r in _safe_default_ladder()]))
