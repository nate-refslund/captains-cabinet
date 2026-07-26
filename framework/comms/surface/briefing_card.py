"""framework.comms.surface.briefing_card — the briefing as ONE card (§3.4).

The 07:30/19:30 briefing stops being a wall of text: ONE ``send_card`` —
plain headline, "N decisions ready", a Triage control — and the decisions
themselves arrive as the paced single-decision cards (surface.pacing), never
embedded in the briefing body.

Foundation renderer + the briefing send path. ``maybe_send`` gates on the
``briefing_card`` knob, Captain-ratified TRUE by default since 2026-07-11;
a deployment opts out with ``briefing_card: false`` in
``instance/config/comms-surface.yml`` (or ``CABINET_BRIEFING_CARD=0``). This
module adds NO scheduling of its own — the frontdoor briefing runner calls it.

Identity: one card per briefing slot (``thread:comms-surface-briefing-
<date>-<am|pm>``), so a re-run edits the same card instead of duplicating.
"""
from __future__ import annotations

from datetime import datetime, timezone

from framework.comms.surface import config as _cfg
from framework.comms.surface import decision_card as _dc
from framework.comms.surface import links as _links

KIND = "briefing"


def _scrub(text) -> str:
    # marker-hygiene law: the headline never carries the U+00B7 marker char.
    return str(text or "").replace("·", "")


def _slot(now: datetime) -> str:
    local = now.astimezone(_cfg.captain_tz())
    return f"{local.strftime('%Y%m%d')}-{'pm' if local.hour >= 14 else 'am'}"


def render(headline: str, census: dict, *, now: "datetime | None" = None,
           cfg: "dict | None" = None) -> dict:
    """The ``send_card`` kwargs for the one briefing card.

    ``headline`` is the composer's one-sentence plain summary of the day —
    this renderer adds the decision count + the Triage entry point (§4) and
    nothing else. The count is the census's pending-on-you number."""
    now = now or datetime.now(timezone.utc)
    n = int(census.get("pending_captain_items") or 0)
    head = _scrub(str(headline or "").strip())[:300]
    if n > 0:
        ready = (f"▶ {n} decision(s) ready — they arrive one at a time, "
                 f"at your pace.")
        buttons = [[
            {"text": f"▶ Triage now ({n})", "data": _dc.cb("tri", "now")},
            {"text": "🗓 Later", "data": _dc.cb("tri", "brief")},
        ]]
    else:
        ready = "Nothing needs a decision from you right now."
        buttons = None
    url = _links.queue_url(cfg)
    if url and buttons:
        u = _links.url_button("🔎 Full list", url)
        if u:
            # Own row: 3-across already fills a phone width — a fourth
            # button truncates labels (same law as the pacing nudge card).
            buttons = buttons + [[u]]
    situation = " ".join(b for b in (head, ready) if b)
    local = now.astimezone(_cfg.captain_tz())
    subject = ("Morning briefing" if local.hour < 14 else "Evening briefing")
    return {
        "subject": subject,
        "situation": situation,
        "kind": KIND,
        "evidence": [f"thread:comms-surface-briefing-{_slot(now)}"],
        "state": "open",
        "buttons": buttons,
    }


def maybe_send(headline: str, *, census: "dict | None" = None,
               now: "datetime | None" = None, cfg: "dict | None" = None,
               adapter=None, ch=None) -> dict:
    """Send the briefing card unless the deployment opted out of it. An
    explicit opt-out returns ``{"status": "disabled"}`` and touches nothing —
    the classic briefing text path is unaffected."""
    cfg = cfg or _cfg.load()
    if not cfg.get("briefing_card"):
        return {"status": "disabled"}
    from framework.comms import tools
    now = now or datetime.now(timezone.utc)
    if census is None:
        from framework.attention.queue import build_queue
        census = build_queue(now=now)
    kwargs = render(headline, census, now=now, cfg=cfg)
    return tools.send_card(**kwargs, adapter=adapter, ch=ch, now=now)
