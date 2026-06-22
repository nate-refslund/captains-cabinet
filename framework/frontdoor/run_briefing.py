"""framework.frontdoor.run_briefing — one pass of the recurring unified briefing.

Scheduled by launchd (cabinet/scripts/run-frontdoor-briefing.sh). Pulls real
signals into the durable intake (morning_synthesis) and runs the send path
(run_frontdoor.run_send_path) → ONE unified message to Nate on the single
channel, replacing the screenpipe morning-brief DM that the cutover silenced.

Send-only + gated end-to-end: run_send_path delegates to channel.send, which is
hard-gated on framework.env.allow_sends() (a dev/test session composes but does
NOT send). No reply handling here — the interactive reply→orchestration is the
LLM-Chair capstone.
"""
from __future__ import annotations

from framework.frontdoor import morning_synthesis, run_frontdoor


def run_briefing(
    *,
    hours: int = 72,
    limit: int = 8,
    enqueue_fn=None,
    send_fn=None,
    drain_fn=None,
    ack_fn=None,
) -> dict:
    """Enqueue a fresh synthesis, then run one send-path pass.

    Returns ``{'synthesis': <enqueue result>, 'send': <run_send_path result>}``.
    Seams: ``enqueue_fn`` overrides the synthesis enqueue; ``send_fn`` /
    ``drain_fn`` / ``ack_fn`` forward to run_send_path — all for tests (no real
    network / Redis). The token never appears in the result (channel.send scrubs;
    run_send_path only re-surfaces the scrubbed dict).
    """
    enqueue = enqueue_fn or morning_synthesis.enqueue_synthesis
    syn = enqueue(hours=hours, limit=limit)
    send = run_frontdoor.run_send_path(send_fn=send_fn, drain_fn=drain_fn, ack_fn=ack_fn)
    return {"synthesis": syn, "send": send}


if __name__ == "__main__":  # pragma: no cover — invoked by the launchd wrapper
    import json
    out = run_briefing()
    printable = {
        "synthesis": out["synthesis"],
        "send": {k: v for k, v in out["send"].items() if k != "text"},
    }
    print(json.dumps(printable, indent=2, default=str))
