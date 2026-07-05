"""framework.frontdoor.run_briefing — one pass of the recurring unified briefing.

Scheduled by launchd (cabinet/scripts/run-frontdoor-briefing.sh). Pulls real
signals into the durable intake (morning_synthesis) and runs the send path
(run_frontdoor.run_send_path) → ONE unified message to the Captain on the single
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

from framework.frontdoor import (daily_recap, morning_synthesis, run_frontdoor,
                                 tell_digest)


def _is_pm() -> bool:
    """True when the wrapper flagged this as the evening (PM) run.

    The launchd wrapper sets CABINET_RUN_MODE=PM for hour ≥ 17, else AM. We
    accept any case and treat ONLY an explicit "PM" as PM (default/unset → AM)
    so a missing env never accidentally fires the recap in the morning."""
    return os.environ.get("CABINET_RUN_MODE", "").strip().upper() == "PM"


def _default_digest() -> dict:
    """Production TI-5 digest call: gather the 📈 LOOP readout (per-card-kind
    approve/edit/skip/expired rates + undo-rate trend + latest falsifier-series
    line — lane instrument, 2026-07-05) and enqueue the digest with it.

    Lives HERE, not in tell_digest, because enqueue_digest deliberately never
    auto-gathers the readout (its live-ledger/series reads would make fixtured
    callers non-hermetic — tell_digest.py module header). gather_loop_readout
    never raises (fail-safe: readout absent on error, digest never blocked)."""
    return tell_digest.enqueue_digest(readout=tell_digest.gather_loop_readout())


def run_briefing(
    *,
    hours: int = 72,
    limit: int = 8,
    enqueue_fn=None,
    send_fn=None,
    drain_fn=None,
    ack_fn=None,
    pending_fn=None,
    recap_fn=None,
    digest_fn=None,
    run_mode: str | None = None,
) -> dict:
    """Enqueue a fresh synthesis (+ the PM daily recap + the TI-5 digest), then
    run one send pass.

    Returns ``{'synthesis': <enqueue result>, 'recap': <recap result|None>,
    'digest': <tell_digest result>, 'send': <run_send_path result>}``.

    PM-only recap: when this is the evening run (``run_mode == 'PM'``, else the
    CABINET_RUN_MODE env), the daily recap is enqueued AFTER the synthesis so it
    rides the same unified briefing. ``recap`` is None on the AM run.

    TI-5 digest (BOTH runs — the twice-daily act-then-tell surface): the
    ACTED/AWAITING/WATCHING/SELF digest is enqueued before the send pass so it
    rides this same unified briefing, and its ``cabinet:digest:<date>`` manifest
    is persisted first so `undo <n>` / `👍 <n>` replies bind the moment the text
    lands (checkpoint 2026-07-04 Tier-0 #6 — the Captain's ruled flip prerequisite;
    plugs the binder no-pid label leak). The default digest also carries the
    📈 LOOP readout (acceptance/undo rates + falsifier series — see
    ``_default_digest``). Best-effort: a digest failure logs into
    the result and never blocks the briefing. Kill-switch CABINET_TELL_DIGEST=0.

    Seams: ``enqueue_fn`` overrides the synthesis enqueue; ``recap_fn`` overrides
    the daily-recap enqueue; ``digest_fn`` overrides the TI-5 digest enqueue;
    ``run_mode`` forces AM/PM; ``send_fn`` / ``drain_fn`` / ``ack_fn`` forward to
    run_send_path — all for tests (no real network / Redis / brain). The token
    never appears in the result (channel.send scrubs; run_send_path only
    re-surfaces the scrubbed dict).
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

    # TI-5: the act-then-tell digest rides BOTH the 07:30 and 19:30 briefings.
    # Enqueued BEFORE the send pass so this run's drain composes it in. The
    # default path (_default_digest) also carries the 📈 LOOP readout; the
    # digest_fn seam is unchanged and takes no readout.
    digest_enqueue = digest_fn or _default_digest
    try:
        digest = digest_enqueue()
    except Exception as e:  # best-effort: never block the briefing send
        digest = {"digest": False, "error": str(e)[:300]}

    # recover_pending=True is the fix for the single-voice comms-awareness gap:
    # surface.py (every 5 min) reads the intake with ">" and surfaces ONLY
    # ping-now in real time, leaving batch/fyi items delivered-but-unacked in the
    # consumer group's PEL "for the briefing to compose". Those items are then no
    # longer ">"-visible, so a plain briefing drain saw nothing and the batch/fyi
    # backlog — comms-officer FYIs, relevant-but-no-reply messages — surfaced
    # NEVER. The briefing is the designated place batch/fyi reaches the Captain, so it
    # recovers that pending backlog, composes it into the one voice, sends, and
    # ACKs. (surface.py is unchanged: still real-time ping-now only.)
    send = run_frontdoor.run_send_path(
        send_fn=send_fn, drain_fn=drain_fn, ack_fn=ack_fn, pending_fn=pending_fn,
        recover_pending=True)
    return {"synthesis": syn, "recap": recap, "digest": digest, "send": send}


if __name__ == "__main__":  # pragma: no cover — invoked by the launchd wrapper
    import json
    out = run_briefing()
    printable = {
        "synthesis": out["synthesis"],
        "recap": {k: v for k, v in (out["recap"] or {}).items()
                  if k not in ("item", "preview")} if out["recap"] else None,
        "digest": {k: v for k, v in (out["digest"] or {}).items()
                   if k != "manifest"},
        "send": {k: v for k, v in out["send"].items() if k != "text"},
    }
    print(json.dumps(printable, indent=2, default=str))
