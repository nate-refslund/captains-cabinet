"""framework.frontdoor.run_briefing — one pass of the recurring unified briefing.

Scheduled by launchd (cabinet/scripts/run-frontdoor-briefing.sh). Pulls real
signals into the durable intake (morning_synthesis) and runs the send path
(run_frontdoor.run_send_path) → ONE unified message to Nate on the single
channel, replacing the screenpipe morning-brief DM that the cutover silenced.

PM augmentation: the wrapper sets ``CABINET_RUN_MODE=PM`` for the evening run
(hour ≥ 17). In PM mode, AFTER the normal synthesis enqueue, we also enqueue the
comprehensive daily recap (framework.frontdoor.daily_recap) — which writes the
day's Monday Reflections item + the canonical vault daily note AND folds the
long-form recap into this same unified briefing. The AM run (CABINET_RUN_MODE
unset / "AM") is unchanged. The recap is best-effort: a failure logs into the
result and never blocks the briefing send.

Send-only + gated end-to-end: run_send_path delegates to channel.send, which is
hard-gated on framework.env.allow_sends() (a dev/test session composes but does
NOT send). No reply handling here — the interactive reply→orchestration is the
LLM-Chair capstone.
"""
from __future__ import annotations

import os

from framework.frontdoor import daily_recap, morning_synthesis, run_frontdoor


def _is_pm() -> bool:
    """True when the wrapper flagged this as the evening (PM) run.

    The launchd wrapper sets CABINET_RUN_MODE=PM for hour ≥ 17, else AM. We
    accept any case and treat ONLY an explicit "PM" as PM (default/unset → AM)
    so a missing env never accidentally fires the recap in the morning."""
    return os.environ.get("CABINET_RUN_MODE", "").strip().upper() == "PM"


def run_briefing(
    *,
    hours: int = 72,
    limit: int = 8,
    enqueue_fn=None,
    send_fn=None,
    drain_fn=None,
    ack_fn=None,
    recap_fn=None,
    run_mode: str | None = None,
) -> dict:
    """Enqueue a fresh synthesis (+ the PM daily recap), then run one send pass.

    Returns ``{'synthesis': <enqueue result>, 'recap': <recap result|None>,
    'send': <run_send_path result>}``.

    PM-only recap: when this is the evening run (``run_mode == 'PM'``, else the
    CABINET_RUN_MODE env), the daily recap is enqueued AFTER the synthesis so it
    rides the same unified briefing. ``recap`` is None on the AM run.

    Seams: ``enqueue_fn`` overrides the synthesis enqueue; ``recap_fn`` overrides
    the daily-recap enqueue; ``run_mode`` forces AM/PM; ``send_fn`` / ``drain_fn``
    / ``ack_fn`` forward to run_send_path — all for tests (no real network /
    Redis / brain). The token never appears in the result (channel.send scrubs;
    run_send_path only re-surfaces the scrubbed dict).
    """
    enqueue = enqueue_fn or morning_synthesis.enqueue_synthesis
    syn = enqueue(hours=hours, limit=limit)

    is_pm = (run_mode.strip().upper() == "PM") if run_mode is not None else _is_pm()
    recap = None
    if is_pm:
        recap_enqueue = recap_fn or daily_recap.enqueue_daily_recap
        try:
            recap = recap_enqueue()
        except Exception as e:  # best-effort: never block the briefing send
            recap = {"recap": False, "error": str(e)[:300]}

    send = run_frontdoor.run_send_path(send_fn=send_fn, drain_fn=drain_fn, ack_fn=ack_fn)
    return {"synthesis": syn, "recap": recap, "send": send}


if __name__ == "__main__":  # pragma: no cover — invoked by the launchd wrapper
    import json
    out = run_briefing()
    printable = {
        "synthesis": out["synthesis"],
        "recap": {k: v for k, v in (out["recap"] or {}).items()
                  if k not in ("item", "preview")} if out["recap"] else None,
        "send": {k: v for k, v in out["send"].items() if k != "text"},
    }
    print(json.dumps(printable, indent=2, default=str))
