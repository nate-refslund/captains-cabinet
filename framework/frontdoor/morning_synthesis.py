"""framework.frontdoor.morning_synthesis — a front-door INTAKE SOURCE.

Pulls REAL current signals from the screenpipe brain and enqueues them as intake
items, so the Chair's send path weaves them into ONE unified message instead of
N separate pings. This is a "rewire" source per the committed architecture's pipe
disposition (docs/cabinet-architecture-cohesive-2026-06-22.md §5): screenpipe
provides the signal (System 1), the cabinet composes the single voice (System 2).

NOTHING here sends. It only enqueues to the durable intake; the one live send
stays in channel.send (allow_sends-gated). Signal gathering is best-effort — a
brain/capture hiccup yields fewer items, never a crash.
"""
from __future__ import annotations

import datetime

from framework.acting import screenpipe_adapter as sa
from framework.frontdoor import intake


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# Cheap, no-LLM noise markers — obvious automated / service-desk / notification
# mail that never warrants a reply. This is a coarse pre-filter so the first
# unified message isn't polluted by bot mail; the ACCURATE filter is the
# should_nate_reply gate (screenpipe_adapter.gather), wired in as a follow-on.
_NOISE_MARKERS = (
    "you don't often get email", "kundeservice", "no-reply", "noreply",
    "do-not-reply", "nulstil din adgangskode", "reset your password",
    "nyhedsbrev", "newsletter", "unsubscribe", "verifikationskode",
    "verification code", "notification@", "notifications@",
)


def _looks_like_noise(person: str, snippet: str) -> bool:
    blob = f"{person} {snippet}".lower()
    return any(m in blob for m in _NOISE_MARKERS)


def awaiting_reply_items(*, hours: int = 72, limit: int = 6) -> list[dict]:
    """Real awaiting-reply threads → intake items (batch tier).

    Each item surfaces (not drafts) a thread that has no reply from Nate yet,
    with provenance. Obvious automated/service-desk mail is pre-filtered out.
    Best-effort: any gather failure → empty list.
    """
    try:
        threads = sa.find_threads(hours=hours) or []
    except Exception:
        threads = []

    items: list[dict] = []
    for t in threads:
        if len(items) >= limit:
            break
        if not isinstance(t, dict):
            continue
        # 1:1 only — Nate rarely replies to group/list threads (the bias the
        # should_nate_reply gate encodes). Restricting to direct threads keeps
        # the synthesis to where a reply is genuinely expected.
        if ((t.get("audience") or {}).get("kind") or "direct") in ("group", "list"):
            continue
        person = t.get("person") or "someone"
        last = ((t.get("last") or {}).get("text") or "").strip().replace("\n", " ")
        if _looks_like_noise(person, last):
            continue
        snippet = (last[:140] + "…") if len(last) > 140 else last
        summary = f"{person} is awaiting your reply"
        if snippet:
            summary += f" — “{snippet}”"
        items.append({
            "source": "awaiting-reply",
            "kind": "thread",
            "ts": _now_iso(),
            "urgency_tier": "batch",
            "payload": {"summary": summary},
            "context": {
                "why": "inbound thread, no reply from you yet",
                "person": person,
                "slug": t.get("slug"),
            },
        })
    return items


def gather_items(*, hours: int = 72, limit: int = 6) -> list[dict]:
    """All synthesis items from every real source (currently: awaiting replies).

    Extend here as more sources are rewired in (commitments, deploy health,
    calendar) — each appends provenance-bearing items; the composer weaves them.
    """
    return awaiting_reply_items(hours=hours, limit=limit)


def enqueue_synthesis(*, hours: int = 72, limit: int = 6) -> dict:
    """Gather real signals and enqueue them to the durable intake.

    Returns {'enqueued': n, 'ids': [...], 'sources': [...]} — never sends.
    """
    items = gather_items(hours=hours, limit=limit)
    ids = [intake.enqueue(it) for it in items]
    return {
        "enqueued": len(ids),
        "ids": ids,
        "sources": sorted({it["source"] for it in items}),
    }


if __name__ == "__main__":  # pragma: no cover — manual dev invocation
    import json
    print(json.dumps(enqueue_synthesis(), indent=2, default=str))
