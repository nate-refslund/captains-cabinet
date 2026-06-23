"""Live adapters wiring the Cabinet acting lane to Nate's screenpipe brain.

These provide the gather / draft_fn deps that framework.acting.loop.run_lane (and
propose()) expect, by calling the existing, battle-tested draft_lib in-process —
the same cross-estate pattern the fidelity BrainAdapter uses. NOTHING here sends:
the present + dispatch (queue_draft / log_lesson / captain-patterns / task) deps
are wired separately and stay gated. This module is the gather→draft front-end of
the acting loop ONLY.
"""
from __future__ import annotations

import os
import sys

_PIPES = os.path.expanduser("~/.screenpipe/pipes")
for _p in (_PIPES, os.path.join(_PIPES, "_shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _dl():
    import draft_lib as dl  # imported lazily so the cabinet test suite needn't have it
    return dl


def _cl():
    import commitments_lib as cl  # lazy — same reason as _dl (screenpipe-only dep)
    return cl


def _pol():
    import product_ops_lib as pol  # lazy — screenpipe-only dep (Vercel REST helpers)
    return pol


def find_threads(hours: int = 48) -> list:
    """Awaiting-reply threads from the brain (each: slug, person, last, thread,
    audience). The acting lane proposes a draft for each that passes the gate."""
    return _dl().find_awaiting_threads(hours=hours)


def open_commitments(direction: str = "owed_by_nate") -> list:
    """Open commitments from the screenpipe ledger (Obsidian 6-Commitments/ — the
    source of truth for promises). Returns the raw frontmatter dicts (text,
    person, slug, due, source, source_date, status, direction) for items still
    open in the requested direction. The briefing surfaces the time-bound /
    overdue ones; the caller wraps this for best-effort behavior."""
    return [c for c in (_cl().load_all() or {}).values()
            if isinstance(c, dict)
            and c.get("status", "open") == "open"
            and c.get("direction") == direction]


def deploy_health(app: str, limit: int = 8) -> dict:
    """Recent Vercel deploy health for one app (read-only, via product_ops_lib's
    REST helper). Returns {app, total, latest_state, failed:[{state,created,creator}]}.
    The caller surfaces a briefing item ONLY when something is wrong (quiet when
    healthy). A missing VERCEL_API_KEY → product_ops_lib returns [] → empty health;
    the caller wraps this for best-effort behavior."""
    deps = _pol().vercel_deployments(app, limit=limit) or []
    failed = [{"state": d.get("state"), "created": d.get("created"),
               "creator": d.get("creator")}
              for d in deps if d.get("state") in ("ERROR", "CANCELED")]
    return {
        "app": app,
        "total": len(deps),
        "latest_state": (deps[0].get("state") if deps else None),
        "failed": failed,
    }


def gather(thread: dict) -> dict:
    """run_lane's gather(thread_ref) — assemble the as-of-now context + the
    should-Nate-reply gate decision for one thread."""
    dl = _dl()
    slug, person = thread["slug"], thread["person"]
    intel = dl.person_intel(slug)
    topic = (thread.get("last", {}).get("text", "") or "")[:200]
    brain = dl.search_brain(f"{person} {topic}", top_k=4)
    commits = dl.open_commitments_for(slug)
    gate = dl.should_nate_reply(thread["thread"], thread.get("audience", {}),
                                intel, brain, person=person)
    return {"intel": intel, "brain": brain, "commits": commits, "gate": gate}


def draft_fn(thread: dict, ctx: dict, *, min_confidence: float = 0.0):
    """run_lane's draft_fn(thread_ref, ctx) — returns the draft string, or None
    when the gate says no-reply or the draft is missing/low-confidence (None ==
    the lane stays silent on this thread, no proposal made)."""
    dl = _dl()
    if not (ctx.get("gate") or {}).get("should_reply"):
        return None
    res = dl.build_draft(thread["thread"], thread["slug"], thread["person"],
                         intel=ctx.get("intel"), commits=ctx.get("commits"),
                         brain=ctx.get("brain"))
    if not res or not res.get("draft"):
        return None
    if float(res.get("confidence", 0) or 0) < min_confidence:
        return None
    return res["draft"].strip()


def lane_for(thread: dict) -> str:
    aud = (thread.get("audience") or {}).get("kind", "direct")
    return "send-group-reply" if aud in ("group", "list") else "send-1to1-reply"
